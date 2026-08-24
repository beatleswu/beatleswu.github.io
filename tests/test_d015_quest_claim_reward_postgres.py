from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import os
from urllib.parse import urlsplit

import pytest

from migrations.domain_event_outbox_v1 import TABLE_NAME as OUTBOX_TABLE, upgrade as upgrade_outbox
from migrations.quest_claim_v1 import TABLE_NAME as CLAIM_TABLE, upgrade as upgrade_claim, validate_schema
from migrations.quest_progress_v2 import (
    APPLICATION_TABLE_NAME,
    PROGRESS_TABLE_NAME,
    upgrade as upgrade_progress,
)
from quest_claim_authority import QuestClaimService
from tests.test_d015_quest_claim_reward import (
    NOW,
    PERIOD,
    _authorities,
    _completed,
    _count,
)


def _url() -> str:
    url = os.environ.get("D015_QUEST_POSTGRES_URL")
    if not url or os.environ.get("D015_QUEST_POSTGRES_DISPOSABLE") != "1":
        pytest.skip("requires explicitly marked disposable PostgreSQL")
    database = (urlsplit(url).path or "").lstrip("/").lower()
    if "test" not in database and "d015" not in database:
        pytest.fail("refusing PostgreSQL URL without a disposable test/d015 database")
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
    conn.execute("DROP TABLE IF EXISTS user_stats, currency_log, pet_inventory, player_wardrobe CASCADE")
    conn.execute(f"DROP TABLE IF EXISTS {CLAIM_TABLE}, {APPLICATION_TABLE_NAME}, {PROGRESS_TABLE_NAME}, {OUTBOX_TABLE} CASCADE")
    conn.commit()
    upgrade_outbox(conn)
    upgrade_progress(conn)
    upgrade_claim(conn)
    conn.execute(
        """CREATE TABLE user_stats(
               user_id TEXT PRIMARY KEY,
               coins BIGINT NOT NULL DEFAULT 0,
               xp BIGINT NOT NULL DEFAULT 0,
               rank_xp BIGINT NOT NULL DEFAULT 0
           )"""
    )
    conn.execute(
        """CREATE TABLE currency_log(
               id BIGSERIAL PRIMARY KEY,
               user_id TEXT NOT NULL,
               amount BIGINT NOT NULL,
               reason TEXT NOT NULL
           )"""
    )
    conn.execute(
        """CREATE TABLE pet_inventory(
               user_id TEXT NOT NULL,
               item_id TEXT NOT NULL,
               quantity BIGINT NOT NULL,
               PRIMARY KEY(user_id,item_id)
           )"""
    )
    conn.execute(
        """CREATE TABLE player_wardrobe(
               user_id TEXT NOT NULL,
               cosmetic_id TEXT NOT NULL,
               PRIMARY KEY(user_id,cosmetic_id)
           )"""
    )
    conn.execute("INSERT INTO user_stats(user_id) VALUES ('7'),('8')")
    conn.commit()
    return conn


def _cleanup(conn) -> None:
    conn.rollback()
    conn.execute("DROP TABLE IF EXISTS user_stats, currency_log, pet_inventory, player_wardrobe CASCADE")
    conn.execute(f"DROP TABLE IF EXISTS {CLAIM_TABLE}, {APPLICATION_TABLE_NAME}, {PROGRESS_TABLE_NAME}, {OUTBOX_TABLE} CASCADE")
    conn.commit()
    conn.close()


def _service(conn) -> QuestClaimService:
    from quest_catalog import CANONICAL_QUEST_CATALOG

    return QuestClaimService(
        conn,
        catalog=CANONICAL_QUEST_CATALOG,
        reward_authorities=_authorities(),
    )


def test_postgres_migration_preflight_and_rerun():
    url = _url()
    conn = _reset(url)
    try:
        version = conn.execute("SELECT version() AS version").fetchone()["version"]
        assert str(version).startswith("PostgreSQL ")
        assert validate_schema(conn)["valid"] is True
        assert upgrade_claim(conn)["valid"] is True
        conn.commit()
    finally:
        _cleanup(conn)


def test_postgres_concurrent_same_claim_has_one_settlement_and_one_lineage_event():
    url = _url()
    seed = _reset(url)
    _completed(seed, "daily:kill_monsters")
    seed.commit()
    seed.close()
    barrier = Barrier(2)

    def run():
        conn = _open(url)
        try:
            barrier.wait(timeout=10)
            result = _service(conn).claim(
                "7",
                "daily:kill_monsters",
                PERIOD,
                claim_operation_id="pg-concurrent-same",
                now=NOW,
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
            results = list(pool.map(lambda _unused: run(), (1, 2)))
        assert {result.status for result in results} == {"GRANTED"}
        assert sum(result.created for result in results) == 1
        assert sum(result.duplicate for result in results) == 1
        check = _open(url)
        try:
            assert _count(check, CLAIM_TABLE) == 1
            assert _count(check, OUTBOX_TABLE) == 1
            assert tuple(check.execute("SELECT coins,xp FROM user_stats WHERE user_id='7'").fetchone()) == (15, 30)
            assert check.execute(
                "SELECT quantity FROM pet_inventory WHERE user_id='7' AND item_id='go_spirit_candy'"
            ).fetchone()["quantity"] == 1
        finally:
            _cleanup(check)
    except Exception:
        cleanup = _open(url)
        _cleanup(cleanup)
        raise


def test_postgres_concurrent_different_operations_same_period_return_one_original_result():
    url = _url()
    seed = _reset(url)
    _completed(seed, "daily:streak_correct")
    seed.commit()
    seed.close()
    barrier = Barrier(2)

    def run(operation_id: str):
        conn = _open(url)
        try:
            barrier.wait(timeout=10)
            result = _service(conn).claim(
                "7",
                "daily:streak_correct",
                PERIOD,
                claim_operation_id=operation_id,
                now=NOW,
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
            results = list(pool.map(run, ("pg-different-a", "pg-different-b")))
        assert {result.status for result in results} == {"GRANTED"}
        assert sum(result.created for result in results) == 1
        assert all(result.claim_id == results[0].claim_id for result in results)
        check = _open(url)
        try:
            assert _count(check, CLAIM_TABLE) == 1
            assert _count(check, OUTBOX_TABLE) == 1
            assert tuple(check.execute("SELECT coins,xp FROM user_stats WHERE user_id='7'").fetchone()) == (15, 20)
        finally:
            _cleanup(check)
    except Exception:
        cleanup = _open(url)
        _cleanup(cleanup)
        raise


def test_postgres_claim_reward_lineage_rolls_back_as_one_transaction():
    url = _url()
    conn = _reset(url)
    _completed(conn, "daily:kill_monsters")
    try:
        with pytest.raises(RuntimeError, match="pg forced rollback"):
            _service(conn).claim(
                "7",
                "daily:kill_monsters",
                PERIOD,
                claim_operation_id="pg-rollback",
                now=NOW,
                fault_hook=lambda stage: (_ for _ in ()).throw(RuntimeError("pg forced rollback"))
                if stage == "after_lineage"
                else None,
            )
        conn.rollback()
        assert _count(conn, CLAIM_TABLE) == 0
        assert _count(conn, OUTBOX_TABLE) == 0
        assert tuple(conn.execute("SELECT coins,xp FROM user_stats WHERE user_id='7'").fetchone()) == (0, 0)
        assert _count(conn, "pet_inventory") == 0
    finally:
        _cleanup(conn)
