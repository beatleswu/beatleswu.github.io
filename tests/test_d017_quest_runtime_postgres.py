"""D017 disposable PostgreSQL concurrency and runtime integration proofs."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from threading import Barrier
from urllib.parse import urlsplit

import pytest

from migrations.domain_event_outbox_v1 import TABLE_NAME as OUTBOX_TABLE, upgrade as upgrade_outbox
from migrations.login_journey_v1 import (
    LOGIN_DAYS_TABLE_NAME,
    JOURNEY_TABLE_NAME,
    STREAK_TABLE_NAME,
    downgrade_for_isolated_test as downgrade_login,
    upgrade as upgrade_login,
)
from migrations.quest_claim_v1 import TABLE_NAME as CLAIM_TABLE, upgrade as upgrade_claim
from migrations.quest_progress_v2 import (
    APPLICATION_TABLE_NAME,
    PROGRESS_TABLE_NAME,
    upgrade as upgrade_progress,
)
from login_journey_authority import get_login_state, record_authenticated_login
from quest_catalog import CANONICAL_QUEST_CATALOG
from quest_claim_authority import QuestClaimService
from quest_reward_adapters import CallableQuestRewardAuthorities
from quest_runtime import apply_quest_runtime_event, build_monster_defeat_event, build_review_settlement_event


SERVER_NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def _url() -> str:
    url = os.environ.get("D017_QUEST_POSTGRES_URL")
    if not url or os.environ.get("D017_QUEST_POSTGRES_DISPOSABLE") != "1":
        pytest.skip("requires explicitly marked disposable PostgreSQL")
    database = (urlsplit(url).path or "").lstrip("/").lower()
    if "test" not in database and "d017" not in database:
        pytest.fail("refusing PostgreSQL URL without a disposable test/d017 database")
    return url


def _open(url: str):
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper

    raw = psycopg2.connect(url)
    raw.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw)


def _reset(url: str):
    conn = _open(url)
    conn.execute(
        "DROP TABLE IF EXISTS reward_sink, user_stats, currency_log, pet_inventory, player_wardrobe CASCADE"
    )
    conn.execute(
        f"DROP TABLE IF EXISTS {JOURNEY_TABLE_NAME}, {STREAK_TABLE_NAME}, {LOGIN_DAYS_TABLE_NAME}, "
        f"{CLAIM_TABLE}, {APPLICATION_TABLE_NAME}, {PROGRESS_TABLE_NAME}, {OUTBOX_TABLE} CASCADE"
    )
    conn.commit()
    upgrade_outbox(conn)
    upgrade_progress(conn)
    upgrade_claim(conn)
    upgrade_login(conn)
    conn.execute(
        "CREATE TABLE reward_sink(id BIGSERIAL PRIMARY KEY, user_id TEXT NOT NULL, component TEXT NOT NULL, amount BIGINT NOT NULL)"
    )
    conn.commit()
    return conn


def _cleanup(conn) -> None:
    conn.rollback()
    downgrade_login(conn)
    conn.execute(
        "DROP TABLE IF EXISTS reward_sink, user_stats, currency_log, pet_inventory, player_wardrobe CASCADE"
    )
    conn.execute(
        f"DROP TABLE IF EXISTS {CLAIM_TABLE}, {APPLICATION_TABLE_NAME}, {PROGRESS_TABLE_NAME}, {OUTBOX_TABLE} CASCADE"
    )
    conn.commit()
    conn.close()


def _authorities() -> CallableQuestRewardAuthorities:
    def grant_xp(conn, user_id, amount, reason, _profile_id):
        conn.execute(
            "INSERT INTO reward_sink(user_id,component,amount) VALUES (?,?,?)",
            (str(user_id), "xp", amount),
        )
        return amount

    def grant_coins(conn, user_id, amount, reason, _profile_id):
        conn.execute(
            "INSERT INTO reward_sink(user_id,component,amount) VALUES (?,?,?)",
            (str(user_id), "coins", amount),
        )
        return amount

    def grant_item(conn, user_id, item_id, quantity, reason, _profile_id):
        conn.execute(
            "INSERT INTO reward_sink(user_id,component,amount) VALUES (?,?,?)",
            (str(user_id), item_id, quantity),
        )
        return {
            "item_id": item_id,
            "granted_quantity": quantity,
            "ownership_authority": "fixture_inventory",
            "ownership_reference": f"fixture_inventory:{user_id}:{item_id}",
        }

    return CallableQuestRewardAuthorities(
        grant_xp=grant_xp,
        grant_coins=grant_coins,
        grant_item=grant_item,
    )


def _seed_kill_completion(conn):
    for index in range(5):
        apply_quest_runtime_event(
            conn,
            event=build_monster_defeat_event(
                user_id=7,
                submission_id=f"pg-d017-kill-{index}",
                occurred_at=f"2026-08-24T{index + 1:02d}:00:00Z",
                monster_family="wolf",
            ),
            server_now=SERVER_NOW,
        )
    conn.commit()


def test_postgres_16_14_preflight_and_candidate_migrations_are_rerunnable():
    url = _url()
    conn = _reset(url)
    try:
        version = str(conn.execute("SELECT version() AS version").fetchone()["version"])
        assert version.startswith("PostgreSQL 16.14")
        assert upgrade_outbox(conn)["table"] == OUTBOX_TABLE
        assert upgrade_progress(conn)["valid"] is True
        assert upgrade_claim(conn)["valid"] is True
        assert upgrade_login(conn)["valid"] is True
        conn.commit()
        assert conn.execute(f"SELECT COUNT(*) AS n FROM {PROGRESS_TABLE_NAME}").fetchone()["n"] == 0
        assert conn.execute(f"SELECT COUNT(*) AS n FROM {CLAIM_TABLE}").fetchone()["n"] == 0
    finally:
        _cleanup(conn)


def test_postgres_concurrent_duplicate_source_event_applies_progress_once():
    url = _url()
    setup = _reset(url)
    setup.commit()
    setup.close()
    event = build_review_settlement_event(
        user_id=7,
        submission_id="pg-d017-same-answer",
        occurred_at="2026-08-24T01:00:00Z",
        correct=True,
        monster_family="dragon",
    )
    barrier = Barrier(2)

    def worker(_index):
        conn = _open(url)
        try:
            barrier.wait(timeout=20)
            result = apply_quest_runtime_event(conn, event=event, server_now=SERVER_NOW)
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, (1, 2)))
        assert sum(all(not application.duplicate for application in result.applications) for result in results) == 1
        verify = _open(url)
        try:
            assert verify.execute(f"SELECT COUNT(*) AS n FROM {APPLICATION_TABLE_NAME}").fetchone()["n"] == 2
            assert verify.execute(
                f"SELECT COUNT(*) AS n FROM {PROGRESS_TABLE_NAME} WHERE progress=1"
            ).fetchone()["n"] == 2
        finally:
            _cleanup(verify)
    except Exception:
        _cleanup(_open(url))
        raise


def test_postgres_all_complete_is_derived_and_concurrent_claim_is_one_reward():
    url = _url()
    seed = _reset(url)
    try:
        _seed_kill_completion(seed)
        for index, (hour, family) in enumerate(((6, "dragon"), (7, None), (8, None))):
            event = build_review_settlement_event(
                user_id=7,
                submission_id=f"pg-d017-primary-{index}",
                occurred_at=f"2026-08-24T{hour:02d}:00:00Z",
                correct=True,
                monster_family=family,
            )
            result = apply_quest_runtime_event(seed, event=event, server_now=SERVER_NOW)
            if index == 2:
                assert len(result.derived_applications) == 1
        seed.commit()
    finally:
        seed.close()

    barrier = Barrier(2)

    def claim_worker(operation_id):
        conn = _open(url)
        try:
            barrier.wait(timeout=20)
            result = QuestClaimService(
                conn,
                catalog=CANONICAL_QUEST_CATALOG,
                reward_authorities=_authorities(),
            ).claim(
                7,
                "daily:all_complete",
                "2026-08-24",
                claim_operation_id=operation_id,
                now=SERVER_NOW,
            )
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim_worker, ("pg-d017-claim-a", "pg-d017-claim-b")))
        assert {result.status for result in results} == {"GRANTED"}
        assert sum(result.created for result in results) == 1
        assert sum(result.duplicate for result in results) == 1
        verify = _open(url)
        try:
            assert verify.execute(f"SELECT COUNT(*) AS n FROM {CLAIM_TABLE}").fetchone()["n"] == 1
            assert verify.execute(f"SELECT COUNT(*) AS n FROM {OUTBOX_TABLE}").fetchone()["n"] == 1
            assert verify.execute("SELECT COUNT(*) AS n FROM reward_sink").fetchone()["n"] == 3
        finally:
            _cleanup(verify)
    except Exception:
        _cleanup(_open(url))
        raise


def test_postgres_same_day_auth_events_count_one_login_day_and_journey_advance():
    url = _url()
    setup = _reset(url)
    setup.commit()
    setup.close()
    barrier = Barrier(10)

    def worker(index):
        conn = _open(url)
        try:
            barrier.wait(timeout=20)
            result = record_authenticated_login(
                conn,
                user_id=7,
                occurred_at="2026-08-24T01:00:00Z",
                source_authority="auth:d017-postgres-test",
                source_event_id=f"pg-d017-login-{index}",
                source_operation_id=f"pg-d017-login-op-{index}",
                server_now=SERVER_NOW,
            )
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    try:
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(worker, range(10)))
        assert sum(result.is_new_login_day for result in results) == 1
        verify = _open(url)
        try:
            state = get_login_state(verify, user_id=7)
            assert (state.total_login_days, state.current_streak_days, state.journey_day_completed) == (1, 1, 1)
            assert verify.execute(
                f"SELECT COUNT(*) AS n FROM {LOGIN_DAYS_TABLE_NAME} WHERE user_id=?", (7,)
            ).fetchone()["n"] == 1
        finally:
            _cleanup(verify)
    except Exception:
        _cleanup(_open(url))
        raise
