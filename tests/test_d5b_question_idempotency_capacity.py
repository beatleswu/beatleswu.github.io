"""Focused D5B tests: review identity, capacity lineage, and PG races."""

from __future__ import annotations

from contextlib import contextmanager
import os
import sqlite3
import threading
from urllib.parse import urlsplit

import pytest

from event_outbox import append_event, get_event_by_idempotency_key
from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox
from migrations.question_capacity_lineage_v1 import (
    downgrade_for_isolated_test as downgrade_capacity_schema,
    upgrade as upgrade_capacity_schema,
    validate_schema as validate_capacity_schema,
)
from migrations.review_log_submission_idempotency_v1 import (
    downgrade_for_isolated_test as downgrade_review_schema,
    upgrade as upgrade_review_schema,
    validate_schema as validate_review_schema,
)
from question_idempotency import (
    IdempotencyIdentityError,
    canonical_payload_digest,
    insert_review_log_with_identity,
    normalize_identity,
)


def _create_sqlite_fixture() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE review_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            grade INTEGER NOT NULL,
            topic TEXT,
            level TEXT,
            difficulty TEXT,
            reviewed_at TEXT NOT NULL,
            response_ms INTEGER,
            discipline TEXT,
            player_rating_snapshot REAL,
            question_rating_snapshot REAL,
            item_rating_version TEXT,
            question_version TEXT,
            source_context TEXT,
            is_scaffolding INTEGER NOT NULL DEFAULT 0,
            training_set_id INTEGER,
            source TEXT
        );
        CREATE TABLE active_effects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            effect_key TEXT NOT NULL,
            value REAL NOT NULL DEFAULT 1,
            expires_at TEXT,
            effect_date TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE shop_inventory (
            user_id INTEGER NOT NULL,
            item_key TEXT NOT NULL,
            qty INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, item_key)
        );
        """
    )
    conn.execute(
        """INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source)
           VALUES(?,?,?,?,?)""",
        (99, 9001, 5, "2026-08-22T00:00:00", "historical"),
    )
    upgrade_review_schema(conn)
    upgrade_capacity_schema(conn)
    upgrade_outbox(conn)
    conn.commit()
    return conn


def _review_kwargs(user_id: int, submission_id: str, payload_hash: str) -> dict:
    return {
        "user_id": user_id,
        "question_id": 101,
        "grade": 5,
        "topic": "whole",
        "level": "30k",
        "difficulty": "30k",
        "reviewed_at": "2026-08-22T00:00:01",
        "response_ms": 1200,
        "discipline": "whole_board",
        "player_rating_snapshot": 1400.0,
        "question_rating_snapshot": 1200.0,
        "item_rating_version": "v1",
        "question_version": "q-v1",
        "source_context": "practice",
        "is_scaffolding": 0,
        "training_set_id": None,
        "submission_id": submission_id,
        "submission_payload_hash": payload_hash,
    }


def test_identity_is_server_bound_and_digest_is_deterministic():
    generated, was_generated = normalize_identity(None, field="submission_id")
    assert was_generated is True
    assert generated.startswith("srv-")
    assert normalize_identity("client-1", field="submission_id") == ("client-1", False)
    with pytest.raises(IdempotencyIdentityError):
        normalize_identity("bad value", field="submission_id")
    assert canonical_payload_digest({"b": 2, "a": 1}) == canonical_payload_digest(
        {"a": 1, "b": 2}
    )
    assert canonical_payload_digest({"a": 1}) != canonical_payload_digest({"a": 2})


def test_review_log_identity_preserves_history_and_rejects_duplicate_player_identity():
    conn = _create_sqlite_fixture()
    try:
        review_status = validate_review_schema(conn)
        assert review_status["missing"] == []
        assert review_status["historical_null_identities_allowed"] is True
        assert conn.execute(
            "SELECT COUNT(*) FROM review_log WHERE submission_id IS NULL"
        ).fetchone()[0] == 1

        payload = {"question_id": 101, "grade": 5, "source_context": "practice"}
        digest = canonical_payload_digest(payload)
        first = insert_review_log_with_identity(
            conn, **_review_kwargs(7, "submission-1", digest)
        )
        retry = insert_review_log_with_identity(
            conn, **_review_kwargs(7, "submission-1", digest)
        )
        other_player = insert_review_log_with_identity(
            conn, **_review_kwargs(8, "submission-1", digest)
        )
        assert first["inserted"] is True
        assert retry["inserted"] is False
        assert retry["existing"]["question_id"] == 101
        assert other_player["inserted"] is True
        assert conn.execute(
            "SELECT COUNT(*) FROM review_log WHERE user_id=? AND submission_id=?",
            (7, "submission-1"),
        ).fetchone()[0] == 1

        different_payload_digest = canonical_payload_digest(
            {"question_id": 102, "grade": 5, "source_context": "practice"}
        )
        conflict = insert_review_log_with_identity(
            conn, **_review_kwargs(7, "submission-1", different_payload_digest)
        )
        assert conflict["inserted"] is False
        assert conflict["existing"]["submission_payload_hash"] == digest
    finally:
        conn.close()


def test_capacity_schema_has_operation_identity_and_outbox_fixture():
    conn = _create_sqlite_fixture()
    try:
        status = validate_capacity_schema(conn)
        assert status["missing"] == []
        conn.execute(
            "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(?,?,?)",
            (7, "extra_questions_small", 1),
        )
        updated = conn.execute(
            "UPDATE shop_inventory SET qty=qty-1 WHERE user_id=? AND item_key=? AND qty>0",
            (7, "extra_questions_small"),
        )
        assert updated.rowcount == 1
        effect = conn.execute(
            """INSERT INTO active_effects(
                   user_id,effect_key,value,effect_date,created_at,operation_id,source_item_key)
               VALUES(?,?,?,?,?,?,?)""",
            (7, "extra_questions", 5, "2026-08-22", "2026-08-22T00:00:01", "op-1", "extra_questions_small"),
        )
        assert effect.rowcount == 1
        effect_row = conn.execute(
            "SELECT * FROM active_effects WHERE user_id=? AND operation_id=?",
            (7, "op-1"),
        ).fetchone()
        event = append_event(
            conn,
            event_type="QUESTION_CAPACITY",
            player_id="7",
            lineage_id="op-1",
            source_event_id=f"active_effects:{effect_row['id']}",
            idempotency_key="question-capacity:op-1",
            outcome="SUCCESS",
            payload={
                "operation": "CONSUME",
                "item_id": "extra_questions_small",
                "capacity_delta": 5,
                "base_capacity": 20,
                "effective_capacity_after": 25,
                "business_date": "2026-08-22",
                "effect_id": effect_row["id"],
            },
        )
        conn.commit()
        assert conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=7 AND item_key=?",
            ("extra_questions_small",),
        ).fetchone()[0] == 0
        assert get_event_by_idempotency_key(
            conn,
            player_id="7",
            event_type="QUESTION_CAPACITY",
            idempotency_key="question-capacity:op-1",
        )["event_id"] == event["event_id"]
    finally:
        conn.close()


def test_additive_schema_candidates_have_disposable_sqlite_down_paths():
    conn = _create_sqlite_fixture()
    try:
        downgrade_capacity_schema(conn)
        downgrade_review_schema(conn)
        assert validate_capacity_schema(conn)["missing"] == [
            "operation_id",
            "source_item_key",
        ]
        assert validate_review_schema(conn)["missing"] == [
            "submission_id",
            "submission_payload_hash",
        ]
    finally:
        conn.close()


@pytest.fixture()
def app_module(monkeypatch):
    # Prevent app import from reading or creating the protected secret file.
    monkeypatch.setenv("SECRET_KEY", "d5b-test-only")
    import app as module

    module.app.config.update(TESTING=True)
    return module


def _install_app_db(monkeypatch, module, conn):
    @contextmanager
    def db_context():
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise

    monkeypatch.setattr(module, "get_db", lambda: db_context())


def test_runtime_shop_capacity_use_is_idempotent_and_lineaged(app_module, monkeypatch):
    module = app_module
    conn = _create_sqlite_fixture()
    _install_app_db(monkeypatch, module, conn)
    client = module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7

    deltas = {
        "extra_questions_small": 5,
        "extra_questions": 10,
        "grand_training_pass": 20,
    }
    expected_extra = 0
    for index, (item_key, delta) in enumerate(deltas.items(), start=1):
        conn.execute(
            "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(?,?,?) "
            "ON CONFLICT(user_id,item_key) DO UPDATE SET qty=excluded.qty",
            (7, item_key, 1),
        )
        operation_id = f"runtime-op-{index}"
        first = client.post(
            "/api/shop/use",
            json={"item_key": item_key, "operation_id": operation_id},
        )
        assert first.status_code == 200, first.get_json()
        first_body = first.get_json()
        assert first_body["value"] == delta
        expected_extra += delta
        assert first_body["effective_capacity_after"] == 20 + expected_extra

        retry = client.post(
            "/api/shop/use",
            json={"item_key": item_key, "operation_id": operation_id},
        )
        assert retry.status_code == 200, retry.get_json()
        assert retry.get_json()["capacity_duplicate"] is True
        assert conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=? AND item_key=?",
            (7, item_key),
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM active_effects WHERE user_id=? AND operation_id=?",
            (7, operation_id),
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM domain_event_outbox "
            "WHERE player_id=? AND event_type=? AND idempotency_key=?",
            ("7", "QUESTION_CAPACITY", f"question-capacity:{operation_id}"),
        ).fetchone()[0] == 1

    conn.execute(
        "UPDATE shop_inventory SET qty=1 WHERE user_id=? AND item_key=?",
        (7, "extra_questions"),
    )
    conn.commit()
    conflict = client.post(
        "/api/shop/use",
        json={"item_key": "extra_questions", "operation_id": "runtime-op-1"},
    )
    assert conflict.status_code == 409
    assert conflict.get_json()["code"] == "idempotency_conflict"

    conn.close()


def test_runtime_capacity_failure_rolls_back_inventory_effect_and_event(app_module, monkeypatch):
    module = app_module
    conn = _create_sqlite_fixture()
    conn.execute(
        "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(?,?,?)",
        (7, "extra_questions_small", 1),
    )
    conn.commit()
    _install_app_db(monkeypatch, module, conn)
    client = module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7

    def fail_event(*args, **kwargs):
        raise RuntimeError("forced D5B event failure")

    monkeypatch.setattr(module, "append_event", fail_event)
    with pytest.raises(RuntimeError, match="forced D5B event failure"):
        client.post(
            "/api/shop/use",
            json={"item_key": "extra_questions_small", "operation_id": "rollback-op"},
        )
    assert conn.execute(
        "SELECT qty FROM shop_inventory WHERE user_id=? AND item_key=?",
        (7, "extra_questions_small"),
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM active_effects WHERE operation_id=?", ("rollback-op",)
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM domain_event_outbox WHERE idempotency_key=?",
        ("question-capacity:rollback-op",),
    ).fetchone()[0] == 0
    conn.close()


def _pg_url():
    url = os.environ.get("D5B_OUTBOX_POSTGRES_URL")
    if not url or os.environ.get("D5B_OUTBOX_POSTGRES_DISPOSABLE") != "1":
        pytest.skip("requires explicitly marked disposable PostgreSQL")
    database = (urlsplit(url).path or "").lstrip("/").lower()
    if "test" not in database and "d5b" not in database:
        pytest.skip("refusing PostgreSQL URL without a test/d5b database name")
    return url


def _pg_connection(url):
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper

    raw = psycopg2.connect(url)
    raw.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw)


def _create_pg_schema(conn):
    conn.execute("DROP TABLE IF EXISTS domain_event_outbox CASCADE")
    conn.execute("DROP TABLE IF EXISTS active_effects CASCADE")
    conn.execute("DROP TABLE IF EXISTS shop_inventory CASCADE")
    conn.execute("DROP TABLE IF EXISTS review_log CASCADE")
    conn.execute(
        """CREATE TABLE review_log(
               id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL,
               question_id INTEGER NOT NULL, grade INTEGER NOT NULL,
               topic TEXT, level TEXT, difficulty TEXT,
               reviewed_at TEXT NOT NULL, response_ms INTEGER,
               discipline TEXT, player_rating_snapshot REAL,
               question_rating_snapshot REAL, item_rating_version TEXT,
               question_version TEXT, source_context TEXT,
               is_scaffolding INTEGER NOT NULL DEFAULT 0,
               training_set_id INTEGER, source TEXT)"""
    )
    conn.execute(
        """CREATE TABLE active_effects(
               id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL,
               effect_key TEXT NOT NULL, value REAL NOT NULL DEFAULT 1,
               expires_at TEXT, effect_date TEXT, created_at TEXT NOT NULL)"""
    )
    conn.execute(
        """CREATE TABLE shop_inventory(
               user_id INTEGER NOT NULL, item_key TEXT NOT NULL,
               qty INTEGER NOT NULL DEFAULT 0,
               PRIMARY KEY(user_id,item_key))"""
    )
    upgrade_review_schema(conn)
    upgrade_capacity_schema(conn)
    upgrade_outbox(conn)
    conn.commit()


def test_postgres_concurrent_duplicate_submission_and_capacity_atomicity():
    url = _pg_url()
    conn = _pg_connection(url)
    try:
        _create_pg_schema(conn)
        payload = canonical_payload_digest(
            {"question_id": 101, "grade": 5, "source_context": "practice"}
        )
        barrier = threading.Barrier(2)
        results = []
        errors = []

        def worker():
            worker_conn = _pg_connection(url)
            try:
                barrier.wait(timeout=10)
                result = insert_review_log_with_identity(
                    worker_conn, **_review_kwargs(7, "pg-concurrent", payload)
                )
                worker_conn.commit()
                results.append(result)
            except Exception as exc:  # pragma: no cover - reported below
                errors.append(exc)
                try:
                    worker_conn.rollback()
                except Exception:
                    pass
            finally:
                worker_conn.close()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        assert not errors
        assert len(results) == 2
        assert sorted(result["inserted"] for result in results) == [False, True]
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM review_log "
            "WHERE user_id=? AND submission_id=?",
            (7, "pg-concurrent"),
        ).fetchone()["n"] == 1

        conn.execute(
            "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(?,?,?)",
            (7, "extra_questions_small", 1),
        )
        conn.commit()
        conn.execute(
            "UPDATE shop_inventory SET qty=qty-1 WHERE user_id=? AND item_key=? AND qty>0",
            (7, "extra_questions_small"),
        )
        effect = conn.execute(
            """INSERT INTO active_effects(
                   user_id,effect_key,value,effect_date,created_at,operation_id,source_item_key)
               VALUES(?,?,?,?,?,?,?) RETURNING id""",
            (7, "extra_questions", 5, "2026-08-22", "2026-08-22T00:00:01", "pg-op", "extra_questions_small"),
        ).fetchone()
        event = append_event(
            conn,
            event_type="QUESTION_CAPACITY",
            player_id="7",
            lineage_id="pg-op",
            source_event_id=f"active_effects:{effect['id']}",
            idempotency_key="question-capacity:pg-op",
            outcome="SUCCESS",
            payload={
                "operation": "CONSUME",
                "item_id": "extra_questions_small",
                "capacity_delta": 5,
                "base_capacity": 20,
                "effective_capacity_after": 25,
                "business_date": "2026-08-22",
                "effect_id": effect["id"],
            },
        )
        conn.commit()
        assert event["published_at"] is None
        assert conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=? AND item_key=?",
            (7, "extra_questions_small"),
        ).fetchone()["qty"] == 0

        conn.execute(
            "UPDATE shop_inventory SET qty=qty+1 WHERE user_id=? AND item_key=?",
            (7, "extra_questions_small"),
        )
        rollback_effect = conn.execute(
            """INSERT INTO active_effects(
                   user_id,effect_key,value,effect_date,created_at,operation_id,source_item_key)
               VALUES(?,?,?,?,?,?,?) RETURNING id""",
            (7, "extra_questions", 5, "2026-08-22", "2026-08-22T00:00:02", "pg-rollback", "extra_questions_small"),
        ).fetchone()
        append_event(
            conn,
            event_type="QUESTION_CAPACITY",
            player_id="7",
            lineage_id="pg-rollback",
            source_event_id=f"active_effects:{rollback_effect['id']}",
            idempotency_key="question-capacity:pg-rollback",
            outcome="SUCCESS",
            payload={"item_id": "extra_questions_small", "capacity_delta": 5},
        )
        conn.rollback()
        assert conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=? AND item_key=?",
            (7, "extra_questions_small"),
    ).fetchone()["qty"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM active_effects WHERE operation_id=?",
            ("pg-rollback",),
        ).fetchone()["n"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM domain_event_outbox WHERE idempotency_key=?",
            ("question-capacity:pg-rollback",),
        ).fetchone()["n"] == 0
    finally:
        try:
            conn.rollback()
            conn.execute("DROP TABLE IF EXISTS domain_event_outbox CASCADE")
            conn.execute("DROP TABLE IF EXISTS active_effects CASCADE")
            conn.execute("DROP TABLE IF EXISTS shop_inventory CASCADE")
            conn.execute("DROP TABLE IF EXISTS review_log CASCADE")
            conn.commit()
        finally:
            conn.close()
