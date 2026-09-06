"""W1-A1 durable first-clear convergence and idempotency matrix.

These tests deliberately exercise the two transaction boundaries: the core
Boss/reward receipt is committed first, while Zone-star and immediate unlock
are retried from the append-only receipt in a separate transaction.
"""

from __future__ import annotations

import sqlite3
import sys
import types
from pathlib import Path

import pytest

from adventure_zone_star_progression import (
    EARNINGS_TABLE_NAME,
    ZoneStarSchemaUnavailable,
    award_zone_star_from_boss_clear,
    load_zone_star_rows,
    zone_star_value,
)
from migrations.adventure_zone_star_progression_v1 import upgrade as upgrade_zone_star_schema
from migrations.domain_event_outbox_v1 import upgrade as upgrade_domain_event_outbox


REPO_ROOT = Path(__file__).resolve().parent.parent
EVENT_TYPE = "ADVENTURE_FIRST_CLEAR_PROJECTION"
USER_ID = 701
ZONE = "k1_5"
NEXT_ZONE = "k2_5"
OPERATION_ID = f"adventure:first_clear:{USER_ID}:{ZONE}"
NOW = "2026-09-06T10:00:00"


def _install_app_import_stubs():
    if "katago_explain" not in sys.modules:
        module = types.ModuleType("katago_explain")
        module.KataGoExplainer = type("KataGoExplainer", (), {})
        sys.modules["katago_explain"] = module
    if "explain_overrides" not in sys.modules:
        module = types.ModuleType("explain_overrides")
        module.get_override = lambda *args, **kwargs: None
        sys.modules["explain_overrides"] = module
    if "grimoire_api" not in sys.modules:
        from flask import Blueprint

        module = types.ModuleType("grimoire_api")
        module.grimoire_bp = Blueprint("grimoire_stub_w1_a1", __name__)
        sys.modules["grimoire_api"] = module
    if "question_taxonomy" not in sys.modules:
        module = types.ModuleType("question_taxonomy")
        module.get_taxonomy = lambda *args, **kwargs: {}
        sys.modules["question_taxonomy"] = module
    if "monster_taxonomy" not in sys.modules:
        module = types.ModuleType("monster_taxonomy")
        module.get_monster_taxonomy = lambda *args, **kwargs: {}
        module.mark_encounters = lambda *args, **kwargs: None
        sys.modules["monster_taxonomy"] = module
    if "chapter_i18n" not in sys.modules:
        module = types.ModuleType("chapter_i18n")
        module.localize_topic = lambda *args, **kwargs: ""
        module.localize_level = lambda *args, **kwargs: ""
        sys.modules["chapter_i18n"] = module
    if "backend_i18n" not in sys.modules:
        module = types.ModuleType("backend_i18n")
        module.badge_en = lambda *args, **kwargs: ""
        module.skill_node_en = lambda *args, **kwargs: ""
        module.title_en = lambda *args, **kwargs: ""
        sys.modules["backend_i18n"] = module


@pytest.fixture(scope="module")
def app_module():
    _install_app_import_stubs()
    import app as loaded_app

    return loaded_app


class _FakeDbConnectionContext:
    """Keep separate app ``with get_db`` blocks on one SQLite transaction."""

    def __init__(self, connection: sqlite3.Connection):
        self._conn = connection

    def execute(self, statement, parameters=None):
        return self._conn.execute(statement, parameters or ())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()
        return False


@pytest.fixture()
def sqlite_conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE adventure_zone_unlocks(
            user_id INTEGER NOT NULL,
            zone_key TEXT NOT NULL,
            source TEXT NOT NULL,
            start_zone_key TEXT,
            unlocked_at TEXT NOT NULL,
            PRIMARY KEY (user_id, zone_key)
        )"""
    )
    connection.execute(
        """CREATE TABLE adventure_boss_progress(
            user_id INTEGER NOT NULL,
            zone_key TEXT NOT NULL,
            cleared INTEGER NOT NULL DEFAULT 0,
            stars INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            best_score INTEGER NOT NULL DEFAULT 0,
            cooldown_until_seen INTEGER NOT NULL DEFAULT 0,
            last_attempt_at TEXT,
            cleared_at TEXT,
            updated_at TEXT,
            PRIMARY KEY(user_id, zone_key)
        )"""
    )
    upgrade_domain_event_outbox(connection)
    upgrade_zone_star_schema(connection)
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture()
def wired(app_module, sqlite_conn, monkeypatch):
    monkeypatch.setattr(
        app_module,
        "get_db",
        lambda: _FakeDbConnectionContext(sqlite_conn),
    )
    monkeypatch.setattr(
        app_module,
        "ADVENTURE_ZONES",
        [{"key": ZONE}, {"key": NEXT_ZONE}],
    )
    monkeypatch.setattr(
        app_module,
        "_zone_by_key",
        lambda key: {"key": key} if key in {ZONE, NEXT_ZONE} else None,
    )
    monkeypatch.setattr(
        app_module,
        "_adventure_zone_index",
        lambda key: {ZONE: 0, NEXT_ZONE: 1}.get(key, 0),
    )
    return app_module, sqlite_conn


def _record_receipt(app_module, connection):
    with _FakeDbConnectionContext(connection) as conn:
        receipt = app_module.record_first_clear_projection_receipt(
            conn,
            user_id=USER_ID,
            zone_key=ZONE,
            operation_id=OPERATION_ID,
            occurred_at=NOW,
        )
        conn.commit()
    return receipt


def _event_rows(connection):
    return connection.execute(
        """SELECT event_id, outcome, idempotency_key, payload
             FROM domain_event_outbox
            WHERE player_id=? AND event_type=?
            ORDER BY idempotency_key""",
        (str(USER_ID), EVENT_TYPE),
    ).fetchall()


def _zone_stars(connection):
    return zone_star_value(
        load_zone_star_rows(connection, USER_ID),
        ZONE,
    )


def _unlock_count(connection):
    return connection.execute(
        "SELECT COUNT(*) FROM adventure_zone_unlocks WHERE user_id=? AND zone_key=?",
        (USER_ID, NEXT_ZONE),
    ).fetchone()[0]


def _run_reconciliation(app_module):
    return app_module._adventure_reconcile_first_clear_projections(USER_ID)


def test_first_clear_happy_path_writes_receipt_star_unlock_and_completion(wired):
    app_module, connection = wired
    receipt = _record_receipt(app_module, connection)

    result = app_module._adventure_attempt_first_clear_projection(
        USER_ID, ZONE, OPERATION_ID, NOW, receipt=receipt
    )

    assert result["status"] == "COMPLETED"
    assert result["converged"] is True
    assert _zone_stars(connection) == 1
    assert _unlock_count(connection) == 1
    rows = _event_rows(connection)
    assert len(rows) == 2
    assert [row["outcome"] for row in rows] == ["SUCCESS", "UNKNOWN"]


@pytest.mark.parametrize(
    "failure_kind",
    ["zone_star_schema", "generic_zone_star", "next_zone_unlock"],
)
def test_projection_failures_leave_durable_pending_and_retry_later(wired, monkeypatch, failure_kind):
    app_module, connection = wired
    receipt = _record_receipt(app_module, connection)
    real_star_writer = app_module.award_zone_star_from_boss_clear
    real_unlock_writer = app_module._persist_next_zone_unlock

    if failure_kind == "zone_star_schema":
        def fail_schema(*args, **kwargs):
            raise ZoneStarSchemaUnavailable("forced test failure")

        monkeypatch.setattr(app_module, "award_zone_star_from_boss_clear", fail_schema)
    elif failure_kind == "generic_zone_star":
        def fail_generic(*args, **kwargs):
            raise RuntimeError("forced test failure")

        monkeypatch.setattr(app_module, "award_zone_star_from_boss_clear", fail_generic)
    else:
        def fail_unlock(*args, **kwargs):
            raise RuntimeError("forced unlock failure")

        monkeypatch.setattr(app_module, "_persist_next_zone_unlock", fail_unlock)

    failed = app_module._adventure_attempt_first_clear_projection(
        USER_ID, ZONE, OPERATION_ID, NOW, receipt=receipt
    )
    assert failed["status"] == "PENDING"
    assert failed["converged"] is False
    assert failed["retryable"] is True
    assert failed["error_code"]
    assert _zone_stars(connection) == 0
    assert _unlock_count(connection) == 0
    assert connection.execute(
        "SELECT COUNT(*) FROM domain_event_outbox WHERE player_id=? AND event_type=? AND outcome='UNKNOWN'",
        (str(USER_ID), EVENT_TYPE),
    ).fetchone()[0] == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM domain_event_outbox WHERE player_id=? AND event_type=? AND outcome='FAILED'",
        (str(USER_ID), EVENT_TYPE),
    ).fetchone()[0] == 1

    monkeypatch.setattr(app_module, "award_zone_star_from_boss_clear", real_star_writer)
    monkeypatch.setattr(app_module, "_persist_next_zone_unlock", real_unlock_writer)
    retry = _run_reconciliation(app_module)
    assert retry["status"] == "COMPLETED"
    assert retry["converged"] is True
    assert _zone_stars(connection) == 1
    assert _unlock_count(connection) == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM domain_event_outbox WHERE player_id=? AND event_type=? AND outcome='SUCCESS'",
        (str(USER_ID), EVENT_TYPE),
    ).fetchone()[0] == 1


def test_request_termination_after_core_settlement_leaves_receipt_for_recovery(wired, monkeypatch):
    app_module, connection = wired
    receipt = _record_receipt(app_module, connection)
    real_projection_writer = app_module._adventure_settle_first_clear_projection

    def terminate_before_projection(*args, **kwargs):
        raise KeyboardInterrupt("request ended after core commit")

    monkeypatch.setattr(
        app_module,
        "_adventure_settle_first_clear_projection",
        terminate_before_projection,
    )
    with pytest.raises(KeyboardInterrupt):
        app_module._adventure_attempt_first_clear_projection(
            USER_ID, ZONE, OPERATION_ID, NOW, receipt=receipt
        )

    assert connection.execute(
        "SELECT COUNT(*) FROM domain_event_outbox WHERE player_id=? AND event_type=? AND outcome='UNKNOWN'",
        (str(USER_ID), EVENT_TYPE),
    ).fetchone()[0] == 1
    assert _zone_stars(connection) == 0
    assert _unlock_count(connection) == 0

    monkeypatch.setattr(
        app_module,
        "_adventure_settle_first_clear_projection",
        real_projection_writer,
    )
    # Restore the real writer for the actual repair after the simulated
    # request termination.
    pending = _run_reconciliation(app_module)
    assert pending["status"] == "COMPLETED"
    assert _zone_stars(connection) == 1
    assert _unlock_count(connection) == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM domain_event_outbox WHERE player_id=? AND event_type=? AND outcome='SUCCESS'",
        (str(USER_ID), EVENT_TYPE),
    ).fetchone()[0] == 1


def test_repeated_reconciliation_and_replay_are_idempotent(wired):
    app_module, connection = wired
    receipt = _record_receipt(app_module, connection)
    first = app_module._adventure_attempt_first_clear_projection(
        USER_ID, ZONE, OPERATION_ID, NOW, receipt=receipt
    )
    second = _run_reconciliation(app_module)
    third = app_module._adventure_attempt_first_clear_projection(
        USER_ID, ZONE, OPERATION_ID, NOW, receipt=receipt
    )

    assert first["converged"] is True
    assert second["status"] == "COMPLETED"
    assert third["status"] == "COMPLETED"
    assert _zone_stars(connection) == 1
    assert _unlock_count(connection) == 1
    rows = _event_rows(connection)
    assert len(rows) == 2
    assert connection.execute(
        f"SELECT COUNT(*) FROM {EARNINGS_TABLE_NAME} WHERE user_id=? AND zone_key=?",
        (USER_ID, ZONE),
    ).fetchone()[0] == 1


def test_core_receipt_is_atomic_with_first_clear_transaction(wired):
    app_module, connection = wired
    with _FakeDbConnectionContext(connection) as conn:
        app_module._adventure_boss_record_attempt(
            conn, USER_ID, ZONE, True, 20, 0, NOW
        )
        app_module.record_first_clear_projection_receipt(
            conn,
            user_id=USER_ID,
            zone_key=ZONE,
            operation_id=OPERATION_ID,
            occurred_at=NOW,
        )
        conn.rollback()

    assert connection.execute(
        "SELECT COUNT(*) FROM adventure_boss_progress WHERE user_id=? AND zone_key=?",
        (USER_ID, ZONE),
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT COUNT(*) FROM domain_event_outbox WHERE player_id=? AND event_type=?",
        (str(USER_ID), EVENT_TYPE),
    ).fetchone()[0] == 0


def test_receipt_schema_missing_fails_closed_before_core_settlement(app_module):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    try:
        with pytest.raises(app_module.FirstClearProjectionReceiptSchemaUnavailable):
            app_module.ensure_first_clear_projection_receipt_schema(connection)
    finally:
        connection.close()


def test_source_keeps_separate_transaction_and_reconciliation_seams(app_module):
    source = (REPO_ROOT / "app.py").read_text(encoding="utf-8")
    finish = app_module.adventure_boss_finish.__code__.co_firstlineno
    assert "record_first_clear_projection_receipt" in source
    assert "_adventure_reconcile_first_clear_projections" in source
    assert "zone_star_conn.commit()" in source
    assert finish > 0
