"""C037 disposable PostgreSQL proof for Option C migration concurrency.

This suite deliberately uses the repository's real B033/C019 migration
functions and the real C019 purchase authority.  It never connects to a
non-disposable database and it does not change application or migration
source files.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
import shutil
import subprocess
import threading
import time
import os
from typing import Any, Iterator
import uuid

import psycopg2
from psycopg2.errors import CheckViolation, IntegrityError, UniqueViolation
from psycopg2.extras import DictCursor
import pytest

from coin_purchase_authority import purchase_with_coins
from db import PostgresConnectionWrapper
from equipment_loadout_service import equip_owned_item, unequip_owned_item
from equipment_ownership_service import grant_equipment_ownership
from migrations import coin_purchase_operations_v1 as c019_migration
from migrations import domain_event_outbox_v1 as outbox_migration
from migrations import equipment_canonical_slot_v1 as b033_migration
from shop_offer_authority import CoinShopOffer, StaticShopOfferAuthority


POSTGRES_IMAGE = "postgres:16.14-alpine"
POSTGRES_USER = "c037"
POSTGRES_PASSWORD = "c037-disposable"
POSTGRES_DATABASE = "c037"
B033_ADVISORY_LOCK_KEY = b033_migration.ADVISORY_LOCK_KEY
C019_ADVISORY_LOCK_KEY = c019_migration.ADVISORY_LOCK_KEY

EQUIPMENT_DEFS = (
    {"id": "iron_sword", "slot": "weapon"},
    {"id": "iron_armor", "slot": "armor"},
    {"id": "jade_ring", "slot": "accessory"},
    {"id": "xp_amulet", "slot": "accessory"},
    {"id": "go_stone_black", "slot": None},
)


def _docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _connect(database_url: str) -> PostgresConnectionWrapper:
    raw = psycopg2.connect(database_url, cursor_factory=DictCursor)
    raw.autocommit = False
    return PostgresConnectionWrapper(raw, pooled=False)


def _close(conn: PostgresConnectionWrapper, *, commit: bool = False) -> None:
    try:
        if commit:
            conn.commit()
        else:
            conn.rollback()
    finally:
        conn.close()


def _wait_for_postgres(database_url: str, timeout: float = 240.0) -> str:
    deadline = time.monotonic() + timeout
    last_error: BaseException | None = None
    while time.monotonic() < deadline:
        try:
            raw = psycopg2.connect(database_url, connect_timeout=2)
            raw.autocommit = True
            with raw.cursor() as cursor:
                cursor.execute("SELECT version()")
                version = str(cursor.fetchone()[0])
            raw.close()
            return version
        except Exception as error:  # container startup is eventually consistent
            last_error = error
            time.sleep(0.5)
    raise RuntimeError(f"disposable PostgreSQL did not become ready: {type(last_error).__name__}")


@pytest.fixture(scope="module")
def disposable_postgres() -> dict[str, str]:
    injected_url = os.environ.get("C037_DISPOSABLE_POSTGRES_URL", "").strip()
    if injected_url:
        version = _wait_for_postgres(injected_url, timeout=30.0)
        if not version.startswith("PostgreSQL 16.14"):
            pytest.fail(f"unexpected injected disposable PostgreSQL version: {version}")
        yield {"database_url": injected_url, "version": version}
        return

    if shutil.which("docker") is None:
        pytest.skip("Docker is unavailable; C037 PostgreSQL proof skipped")

    container_name = f"c037-pg-{uuid.uuid4().hex[:12]}"
    started = _docker(
        "run",
        "--detach",
        "--rm",
        "--name",
        container_name,
        "-e",
        f"POSTGRES_USER={POSTGRES_USER}",
        "-e",
        f"POSTGRES_PASSWORD={POSTGRES_PASSWORD}",
        "-e",
        f"POSTGRES_DB={POSTGRES_DATABASE}",
        "-p",
        "127.0.0.1::5432",
        "--tmpfs",
        "/var/lib/postgresql/data:rw,exec,size=512m",
        POSTGRES_IMAGE,
    )
    if started.returncode != 0:
        pytest.skip("disposable PostgreSQL container could not be started")

    try:
        port_result = _docker(
            "inspect",
            "--format",
            "{{(index (index .NetworkSettings.Ports \"5432/tcp\") 0).HostPort}}",
            container_name,
        )
        host_port = port_result.stdout.strip()
        if port_result.returncode != 0 or not host_port.isdigit():
            pytest.skip("disposable PostgreSQL port was not published")
        database_url = (
            f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@127.0.0.1:"
            f"{host_port}/{POSTGRES_DATABASE}"
        )
        version = _wait_for_postgres(database_url)
        if not version.startswith("PostgreSQL 16.14"):
            pytest.fail(f"unexpected disposable PostgreSQL version: {version}")
        yield {"database_url": database_url, "version": version}
    finally:
        _docker("rm", "--force", container_name)


def _reset_schema(database_url: str, *, purchase_schema: bool = False) -> None:
    raw = psycopg2.connect(database_url)
    raw.autocommit = True
    with raw.cursor() as cursor:
        cursor.execute("DROP SCHEMA public CASCADE")
        cursor.execute("CREATE SCHEMA public")
    raw.close()

    conn = _connect(database_url)
    try:
        conn.execute(
            """CREATE TABLE public.user_stats (
                user_id INTEGER PRIMARY KEY,
                coins INTEGER NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE public.currency_log (
                id BIGSERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE public.player_inventory (
                id BIGSERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                equip_id TEXT NOT NULL,
                equipped INTEGER NOT NULL DEFAULT 0,
                obtained_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                source TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE public.shop_inventory (
                user_id INTEGER NOT NULL,
                item_key TEXT NOT NULL,
                qty INTEGER NOT NULL,
                PRIMARY KEY (user_id, item_key)
            )"""
        )
        conn.execute(
            """CREATE TABLE public.player_wardrobe (
                user_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                obtained_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                source TEXT NOT NULL,
                PRIMARY KEY (user_id, item_id)
            )"""
        )
        conn.execute("INSERT INTO user_stats(user_id, coins) VALUES(1, 100)")
        outbox_migration.upgrade(conn)
        if purchase_schema:
            c019_migration.upgrade(conn)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _run_b033(
    database_url: str,
    *,
    started: threading.Event | None = None,
    pid_ready: threading.Event | None = None,
    shared: dict[str, Any] | None = None,
) -> dict[str, Any]:
    outcome: dict[str, Any] = {"done": threading.Event()}
    conn = _connect(database_url)
    outcome["pid"] = conn._conn.get_backend_pid()
    if shared is not None:
        shared.update({"pid": outcome["pid"], "done": outcome["done"]})
    if pid_ready is not None:
        pid_ready.set()
    if started is not None:
        started.set()
    try:
        outcome["result"] = b033_migration.upgrade(
            conn,
            equipment_defs=EQUIPMENT_DEFS,
            dry_run=False,
        )
        conn.commit()
        outcome["committed"] = True
    except BaseException as error:
        outcome["error"] = error
        try:
            conn.rollback()
        except Exception as rollback_error:
            outcome["rollback_error"] = rollback_error
    finally:
        conn.close()
        outcome["done"].set()
    return outcome


def _start_b033(
    database_url: str,
    *,
    started: threading.Event | None = None,
    pid_ready: threading.Event | None = None,
) -> tuple[threading.Thread, dict[str, Any]]:
    holder: dict[str, Any] = {"done": threading.Event()}

    def target() -> None:
        holder.update(
            _run_b033(
                database_url,
                started=started,
                pid_ready=pid_ready,
                shared=holder,
            )
        )

    thread = threading.Thread(target=target, name="c037-b033")
    thread.start()
    return thread, holder


def _join(thread: threading.Thread, holder: dict[str, Any], timeout: float = 30.0) -> None:
    thread.join(timeout)
    assert not thread.is_alive(), "disposable migration thread did not finish"
    assert "error" not in holder, repr(holder.get("error"))
    assert holder.get("committed") is True


def _wait_for_activity(
    database_url: str,
    *,
    pid: int,
    query_pattern: str,
    timeout: float = 15.0,
) -> bool:
    conn = _connect(database_url)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            row = conn.execute(
                """SELECT EXISTS(
                    SELECT 1 FROM pg_stat_activity
                    WHERE pid=? AND state <> 'idle' AND query ILIKE ?
                ) AS found""",
                (pid, query_pattern),
            ).fetchone()
            conn.rollback()
            if row and bool(row["found"] if hasattr(row, "keys") else row[0]):
                return True
            time.sleep(0.05)
        return False
    finally:
        conn.close()


def _wait_for_ungranted_table_lock(
    database_url: str,
    *,
    pid: int,
    timeout: float = 15.0,
) -> bool:
    conn = _connect(database_url)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            row = conn.execute(
                """SELECT EXISTS(
                    SELECT 1
                    FROM pg_locks lock
                    JOIN pg_class relation ON relation.oid=lock.relation
                    WHERE lock.pid=?
                      AND relation.relname='player_inventory'
                      AND lock.mode='AccessExclusiveLock'
                      AND lock.granted=false
                ) AS found""",
                (pid,),
            ).fetchone()
            conn.rollback()
            if row and bool(row["found"] if hasattr(row, "keys") else row[0]):
                return True
            time.sleep(0.05)
        return False
    finally:
        conn.close()


def _run_legacy_insert(
    database_url: str,
    *,
    equip_id: str,
    equipped: int,
    started: threading.Event | None = None,
    commit: bool = True,
    barrier: threading.Barrier | None = None,
    canonical_slot: str | None = None,
) -> dict[str, Any]:
    outcome: dict[str, Any] = {}
    conn = _connect(database_url)
    try:
        if started is not None:
            started.set()
        if barrier is not None:
            barrier.wait(timeout=15)
        if canonical_slot is None:
            cursor = conn.execute(
                """INSERT INTO player_inventory
                    (user_id,equip_id,equipped,obtained_at,source)
                    VALUES(?,?,?,CURRENT_TIMESTAMP,?)""",
                (1, equip_id, equipped, "c037-writer"),
            )
        else:
            cursor = conn.execute(
                """INSERT INTO player_inventory
                    (user_id,equip_id,equipped,canonical_slot,obtained_at,source)
                    VALUES(?,?,?,?,CURRENT_TIMESTAMP,?)""",
                (1, equip_id, equipped, canonical_slot, "c037-writer"),
            )
        outcome["rowcount"] = cursor.rowcount
        if commit:
            conn.commit()
            outcome["committed"] = True
    except BaseException as error:
        outcome["error"] = error
        try:
            conn.rollback()
        except Exception as rollback_error:
            outcome["rollback_error"] = rollback_error
    finally:
        conn.close()
    return outcome


def _b033_is_valid(database_url: str) -> bool:
    conn = _connect(database_url)
    try:
        result = b033_migration.validate_schema(conn)
        conn.rollback()
        return bool(result["valid"])
    finally:
        conn.close()


def _inventory_rows(database_url: str, equip_id: str) -> list[dict[str, Any]]:
    conn = _connect(database_url)
    try:
        rows = conn.execute(
            "SELECT id,user_id,equip_id,equipped,canonical_slot FROM player_inventory "
            "WHERE equip_id=? ORDER BY id",
            (equip_id,),
        ).fetchall()
        conn.rollback()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _legacy_inventory_rows(database_url: str, equip_id: str) -> list[dict[str, Any]]:
    conn = _connect(database_url)
    try:
        rows = conn.execute(
            "SELECT id,user_id,equip_id,equipped FROM player_inventory "
            "WHERE equip_id=? ORDER BY id",
            (equip_id,),
        ).fetchall()
        conn.rollback()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _add_backfill_delay_trigger(database_url: str) -> None:
    conn = _connect(database_url)
    try:
        conn.execute(
            """CREATE FUNCTION c037_delay_backfill() RETURNS trigger
               LANGUAGE plpgsql AS $$
               BEGIN
                 PERFORM pg_sleep(1.5);
                 RETURN NEW;
               END $$"""
        )
        conn.execute(
            """CREATE TRIGGER c037_delay_backfill_trigger
               BEFORE UPDATE ON public.player_inventory
               FOR EACH ROW EXECUTE FUNCTION c037_delay_backfill()"""
        )
        conn.commit()
    finally:
        conn.close()


def _run_b033_and_commit(database_url: str) -> None:
    thread, holder = _start_b033(database_url)
    _join(thread, holder)


def test_disposable_postgres_version_is_exact(disposable_postgres: dict[str, str]) -> None:
    assert disposable_postgres["version"].startswith("PostgreSQL 16.14")


def test_writer_committed_before_b033_is_backfilled(disposable_postgres: dict[str, str]) -> None:
    url = disposable_postgres["database_url"]
    _reset_schema(url)
    writer = _run_legacy_insert(url, equip_id="iron_sword", equipped=0)
    assert writer.get("committed") is True

    _run_b033_and_commit(url)

    rows = _inventory_rows(url, "iron_sword")
    assert len(rows) == 1
    assert rows[0]["canonical_slot"] == "weapon"
    assert _b033_is_valid(url)


def test_writer_started_before_b033_waits_then_is_preserved(disposable_postgres: dict[str, str]) -> None:
    url = disposable_postgres["database_url"]
    _reset_schema(url)
    writer_conn = _connect(url)
    writer_conn.execute(
        """INSERT INTO player_inventory
           (user_id,equip_id,equipped,obtained_at,source)
           VALUES(1,'iron_armor',0,CURRENT_TIMESTAMP,'c037-before')"""
    )

    started = threading.Event()
    pid_ready = threading.Event()
    thread, holder = _start_b033(url, started=started, pid_ready=pid_ready)
    assert started.wait(5)
    assert pid_ready.wait(5)
    assert _wait_for_ungranted_table_lock(url, pid=holder["pid"])
    assert not holder.get("done", threading.Event()).is_set()

    writer_conn.commit()
    writer_conn.close()
    _join(thread, holder)

    rows = _inventory_rows(url, "iron_armor")
    assert len(rows) == 1
    assert rows[0]["canonical_slot"] == "armor"


def test_writer_begins_during_b033_and_legacy_equipped_write_fails_closed(
    disposable_postgres: dict[str, str],
) -> None:
    url = disposable_postgres["database_url"]
    _reset_schema(url)
    seed = _run_legacy_insert(url, equip_id="iron_sword", equipped=0)
    assert seed.get("committed") is True
    _add_backfill_delay_trigger(url)

    started = threading.Event()
    thread, holder = _start_b033(url, started=started)
    assert started.wait(5)
    assert _wait_for_activity(
        url,
        pid=holder["pid"],
        query_pattern="%UPDATE public.player_inventory SET canonical_slot%",
    )

    writer_started = threading.Event()
    writer_result: dict[str, Any] = {}

    def writer_target() -> None:
        writer_result.update(
            _run_legacy_insert(
                url,
                equip_id="jade_ring",
                equipped=1,
                started=writer_started,
            )
        )

    writer_thread = threading.Thread(target=writer_target, name="c037-during-writer")
    writer_thread.start()
    assert writer_started.wait(5)
    assert not writer_result

    _join(thread, holder, timeout=30)
    writer_thread.join(30)
    assert not writer_thread.is_alive()
    assert isinstance(writer_result.get("error"), CheckViolation)
    assert writer_result["error"].pgcode == "23514"
    assert _b033_is_valid(url)
    assert _inventory_rows(url, "jade_ring") == []


def test_b033_advisory_lock_serializes_migration_callers(disposable_postgres: dict[str, str]) -> None:
    url = disposable_postgres["database_url"]
    _reset_schema(url)
    holder = _connect(url)
    holder.execute("SELECT pg_advisory_xact_lock(?)", (B033_ADVISORY_LOCK_KEY,))

    started = threading.Event()
    thread, result = _start_b033(url, started=started)
    assert started.wait(5)
    time.sleep(0.4)
    assert not result.get("done", threading.Event()).is_set()

    holder.commit()
    holder.close()
    _join(thread, result)
    assert _b033_is_valid(url)


def test_b033_failure_rolls_back_while_legacy_writer_was_active(
    disposable_postgres: dict[str, str],
) -> None:
    url = disposable_postgres["database_url"]
    _reset_schema(url)
    writer_conn = _connect(url)
    writer_conn.execute(
        """INSERT INTO player_inventory
           (user_id,equip_id,equipped,obtained_at,source)
           VALUES(1,'unknown_equipment',1,CURRENT_TIMESTAMP,'c037-failure')"""
    )

    started = threading.Event()
    thread, result = _start_b033(url, started=started)
    assert started.wait(5)
    assert _wait_for_ungranted_table_lock(url, pid=result["pid"])
    writer_conn.commit()
    writer_conn.close()
    thread.join(30)
    assert not thread.is_alive()
    assert isinstance(result.get("error"), b033_migration.MalformedInventoryState)
    assert result.get("committed") is not True

    check = _connect(url)
    try:
        column = check.execute(
            """SELECT 1 FROM information_schema.columns
               WHERE table_schema='public' AND table_name='player_inventory'
                 AND column_name='canonical_slot'"""
        ).fetchone()
        assert column is None
        check.rollback()
    finally:
        check.close()
    rows = _legacy_inventory_rows(url, "unknown_equipment")
    assert len(rows) == 1


def test_writer_failure_during_b033_does_not_break_migration(
    disposable_postgres: dict[str, str],
) -> None:
    url = disposable_postgres["database_url"]
    _reset_schema(url)
    _run_legacy_insert(url, equip_id="iron_sword", equipped=0)
    _add_backfill_delay_trigger(url)

    started = threading.Event()
    thread, result = _start_b033(url, started=started)
    assert started.wait(5)
    assert _wait_for_activity(
        url,
        pid=result["pid"],
        query_pattern="%UPDATE public.player_inventory SET canonical_slot%",
    )

    writer_started = threading.Event()
    writer_holder: dict[str, Any] = {}

    def writer_target() -> None:
        writer_holder.update(
            _run_legacy_insert(
                url,
                equip_id="jade_ring",
                equipped=1,
                started=writer_started,
            )
        )

    writer_thread = threading.Thread(target=writer_target, name="c037-failing-writer")
    writer_thread.start()
    assert writer_started.wait(5)
    _join(thread, result, timeout=30)
    writer_thread.join(30)
    assert isinstance(writer_holder.get("error"), CheckViolation)
    assert _b033_is_valid(url)
    assert _inventory_rows(url, "jade_ring") == []


def test_two_post_b033_writers_preserve_rows_and_unique_equipped_slot(
    disposable_postgres: dict[str, str],
) -> None:
    url = disposable_postgres["database_url"]
    _reset_schema(url)
    _run_b033_and_commit(url)

    barrier = threading.Barrier(2)
    results: list[dict[str, Any]] = [{}, {}]

    def run_writer(index: int, equip_id: str) -> None:
        results[index].update(
            _run_legacy_insert(
                url,
                equip_id=equip_id,
                equipped=0,
                barrier=barrier,
            )
        )

    threads = [
        threading.Thread(target=run_writer, args=(0, "iron_sword")),
        threading.Thread(target=run_writer, args=(1, "iron_armor")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert all(not thread.is_alive() for thread in threads)
    assert all(result.get("committed") is True for result in results)

    conn = _connect(url)
    try:
        count = conn.execute("SELECT COUNT(*) AS count FROM player_inventory").fetchone()
        assert int(count["count"]) == 2
        conn.rollback()
    finally:
        conn.close()

    equipped_results: list[dict[str, Any]] = [{}, {}]
    equipped_barrier = threading.Barrier(2)

    def run_equipped(index: int) -> None:
        equipped_results[index].update(
            _run_legacy_insert(
                url,
                equip_id="jade_ring",
                equipped=1,
                barrier=equipped_barrier,
                canonical_slot="accessory",
            )
        )

    equipped_threads = [
        threading.Thread(target=run_equipped, args=(0,)),
        threading.Thread(target=run_equipped, args=(1,)),
    ]
    for thread in equipped_threads:
        thread.start()
    for thread in equipped_threads:
        thread.join(30)
    assert all(not thread.is_alive() for thread in equipped_threads)
    assert sum(result.get("committed") is True for result in equipped_results) == 1
    errors = [result.get("error") for result in equipped_results]
    assert sum(isinstance(error, (UniqueViolation, IntegrityError)) for error in errors) == 1

    conn = _connect(url)
    try:
        duplicate = conn.execute(
            """SELECT COUNT(*) AS count
               FROM player_inventory
               WHERE user_id=1 AND equipped=1 AND canonical_slot='accessory'"""
        ).fetchone()
        assert int(duplicate["count"]) == 1
        conn.rollback()
    finally:
        conn.close()


def test_c019_migration_does_not_lose_a_live_inventory_write(
    disposable_postgres: dict[str, str],
) -> None:
    url = disposable_postgres["database_url"]
    _reset_schema(url)
    _run_b033_and_commit(url)

    writer_started = threading.Event()
    writer_result: dict[str, Any] = {}

    def writer_target() -> None:
        writer_result.update(
            _run_legacy_insert(
                url,
                equip_id="iron_sword",
                equipped=0,
                started=writer_started,
            )
        )

    writer_thread = threading.Thread(target=writer_target, name="c037-c019-live-writer")
    writer_thread.start()
    assert writer_started.wait(5)

    conn = _connect(url)
    try:
        result = c019_migration.upgrade(conn)
        assert result["present"] is True
        assert result["missing"] == []
        conn.commit()
    finally:
        conn.close()
    writer_thread.join(30)
    assert not writer_thread.is_alive()
    assert writer_result.get("committed") is True
    assert len(_inventory_rows(url, "iron_sword")) == 1


def test_b040_monster_and_admin_writers_are_live_after_b033(
    disposable_postgres: dict[str, str],
) -> None:
    url = disposable_postgres["database_url"]
    _reset_schema(url)
    _run_b033_and_commit(url)

    barrier = threading.Barrier(2)
    results: list[dict[str, Any]] = [{}, {}]

    def run_b040(index: int, equip_id: str, source: str) -> None:
        conn = _connect(url)
        try:
            barrier.wait(timeout=15)
            result = grant_equipment_ownership(
                conn,
                1,
                equip_id,
                source,
                equipment_defs=EQUIPMENT_DEFS,
            )
            conn.commit()
            results[index]["result"] = result
        except BaseException as error:
            results[index]["error"] = error
            conn.rollback()
        finally:
            conn.close()

    threads = [
        threading.Thread(target=run_b040, args=(0, "iron_sword", "drop")),
        threading.Thread(target=run_b040, args=(1, "iron_armor", "admin")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert all(not thread.is_alive() for thread in threads)
    assert all("error" not in result for result in results)
    assert {result["result"].source for result in results} == {"drop", "admin"}
    assert {result["result"].canonical_slot for result in results} == {"weapon", "armor"}
    assert len(_inventory_rows(url, "iron_sword")) == 1
    assert len(_inventory_rows(url, "iron_armor")) == 1


def test_b034_equip_and_unequip_remain_exact_row_writers_after_b033(
    disposable_postgres: dict[str, str],
) -> None:
    url = disposable_postgres["database_url"]
    _reset_schema(url)
    _run_b033_and_commit(url)
    conn = _connect(url)
    try:
        owned = grant_equipment_ownership(
            conn,
            1,
            "iron_sword",
            "drop",
            equipment_defs=EQUIPMENT_DEFS,
        )
        conn.commit()
        equip_owned_item(
            conn,
            1,
            "iron_sword",
            ownership_row_id=owned.row_id,
            equipment_defs=EQUIPMENT_DEFS,
        )
        conn.commit()
        unequip_owned_item(
            conn,
            1,
            "iron_sword",
            ownership_row_id=owned.row_id,
            equipment_defs=EQUIPMENT_DEFS,
        )
        conn.commit()
    finally:
        conn.close()

    rows = _inventory_rows(url, "iron_sword")
    assert len(rows) == 1
    assert rows[0]["equipped"] == 0


def test_c019_failure_rolls_back_only_second_transaction(
    disposable_postgres: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = disposable_postgres["database_url"]
    _reset_schema(url)
    _run_b033_and_commit(url)

    original_validate = c019_migration.validate_schema
    calls = 0

    def fail_after_create(conn: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls >= 2:
            raise c019_migration.SchemaMismatch("c037-postcheck-failure")
        return original_validate(conn)

    conn = _connect(url)
    try:
        monkeypatch.setattr(c019_migration, "validate_schema", fail_after_create)
        with pytest.raises(c019_migration.SchemaMismatch):
            c019_migration.upgrade(conn)
        conn.rollback()
    finally:
        conn.close()

    assert _b033_is_valid(url)
    check = _connect(url)
    try:
        table = check.execute(
            "SELECT to_regclass('public.coin_purchase_operations') AS table_name"
        ).fetchone()
        assert table["table_name"] is None
        check.rollback()
    finally:
        check.close()


def test_c019_purchase_replay_is_exactly_once_after_schema_migrations(
    disposable_postgres: dict[str, str],
) -> None:
    url = disposable_postgres["database_url"]
    _reset_schema(url, purchase_schema=True)
    offer = CoinShopOffer(
        offer_id="shop.static.c037_material",
        item_id="c037_material",
        quantity=1,
        currency_type="COINS",
        price=20,
        destination="shop_inventory",
        acquisition_class="MATERIAL",
        offer_version="v1",
        duplicate_policy="STACK",
    )
    authority = StaticShopOfferAuthority([offer])
    fixed_time = datetime(2026, 8, 27, 5, 0, tzinfo=timezone.utc)

    first_conn = _connect(url)
    try:
        first = purchase_with_coins(
            first_conn,
            1,
            "c037-op-1",
            offer.offer_id,
            offer_authority=authority,
            now=fixed_time,
        )
        first_conn.commit()
    finally:
        first_conn.close()

    replay_conn = _connect(url)
    try:
        replay = purchase_with_coins(
            replay_conn,
            1,
            "c037-op-1",
            offer.offer_id,
            offer_authority=authority,
            now=fixed_time,
        )
        replay_conn.commit()
    finally:
        replay_conn.close()

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.canonical_payload() == first.canonical_payload()

    conn = _connect(url)
    try:
        coins = conn.execute("SELECT coins FROM user_stats WHERE user_id=1").fetchone()
        qty = conn.execute(
            "SELECT qty FROM shop_inventory WHERE user_id=1 AND item_key=?",
            (offer.item_id,),
        ).fetchone()
        operation_count = conn.execute(
            "SELECT COUNT(*) AS count FROM coin_purchase_operations"
        ).fetchone()
        event_count = conn.execute(
            """SELECT COUNT(*) AS count FROM domain_event_outbox
               WHERE player_id='1' AND event_type='ITEM_ACQUISITION'"""
        ).fetchone()
        assert int(coins["coins"]) == 80
        assert int(qty["qty"]) == 1
        assert int(operation_count["count"]) == 1
        assert int(event_count["count"]) == 1
        conn.rollback()
    finally:
        conn.close()
