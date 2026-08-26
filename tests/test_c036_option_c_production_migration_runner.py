"""Disposable PostgreSQL acceptance tests for the governed Option C runner."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pytest

import scripts.release.option_c_production_migration as runner
from db import PostgresConnectionWrapper
from migrations.domain_event_outbox_v1 import upgrade as upgrade_event_outbox
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_b033


ROOT = Path(__file__).resolve().parents[1]
POSTGRES_IMAGE = "postgres:16.14-alpine"
POSTGRES_USER = "c036"
POSTGRES_PASSWORD = "c036_disposable_password"
POSTGRES_DATABASE = "c036"


def _docker(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _wait_for_postgres(database_url: str, timeout: float = 240.0) -> None:
    import psycopg2

    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            raw = psycopg2.connect(database_url, connect_timeout=2)
            raw.close()
            return
        except Exception as error:  # pragma: no cover - timing dependent
            last_error = error
            time.sleep(0.5)
    raise RuntimeError(f"disposable PostgreSQL did not become ready: {last_error}")


@pytest.fixture(scope="module")
def disposable_postgres() -> dict[str, str]:
    if shutil.which("docker") is None:
        pytest.skip("docker is unavailable; C036 PostgreSQL proof skipped")

    container_name = f"c036-pg-{uuid4().hex[:12]}"
    started = _docker(
        "run",
        "--rm",
        "--detach",
        "--name",
        container_name,
        "--env",
        f"POSTGRES_USER={POSTGRES_USER}",
        "--env",
        f"POSTGRES_PASSWORD={POSTGRES_PASSWORD}",
        "--env",
        f"POSTGRES_DB={POSTGRES_DATABASE}",
        "--publish",
        "127.0.0.1::5432",
        POSTGRES_IMAGE,
    )
    if started.returncode != 0:
        pytest.skip(
            "disposable PostgreSQL unavailable: "
            f"{started.stderr.strip() or started.stdout.strip()}"
        )

    try:
        port_result = _docker(
            "inspect",
            "--format",
            "{{(index (index .NetworkSettings.Ports \"5432/tcp\") 0).HostPort}}",
            container_name,
            check=True,
        )
        host_port = port_result.stdout.strip()
        if not host_port.isdigit():
            raise RuntimeError("disposable PostgreSQL host port was not published")
        database_url = (
            f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@127.0.0.1:"
            f"{host_port}/{POSTGRES_DATABASE}"
        )
        _wait_for_postgres(database_url)

        import psycopg2

        raw = psycopg2.connect(database_url)
        with raw.cursor() as cursor:
            cursor.execute("SELECT version()")
            server_version = str(cursor.fetchone()[0])
        raw.close()
        if "PostgreSQL 16.14" not in server_version:
            raise RuntimeError(f"unexpected disposable PostgreSQL version: {server_version}")
        yield {
            "database_url": database_url,
            "server_version": server_version,
        }
    finally:
        _docker("rm", "--force", container_name)


def _connect(database_url: str) -> PostgresConnectionWrapper:
    import psycopg2
    from psycopg2.extras import DictCursor

    raw = psycopg2.connect(database_url, cursor_factory=DictCursor)
    return PostgresConnectionWrapper(raw, pooled=False)


def _create_legacy_schema(conn: PostgresConnectionWrapper) -> None:
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
            created_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE public.player_inventory (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            equip_id TEXT NOT NULL,
            equipped INTEGER NOT NULL DEFAULT 0,
            obtained_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'drop'
        )"""
    )
    conn.execute(
        """CREATE TABLE public.shop_inventory (
            user_id INTEGER NOT NULL,
            item_key TEXT NOT NULL,
            qty INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, item_key)
        )"""
    )
    conn.execute(
        """CREATE TABLE public.player_wardrobe (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            obtained_at TEXT NOT NULL,
            source TEXT NOT NULL,
            UNIQUE (user_id, item_id)
        )"""
    )
    conn.execute(
        """INSERT INTO public.user_stats (user_id, coins)
           VALUES (1, 100)"""
    )
    conn.execute(
        """INSERT INTO public.player_inventory
             (user_id, equip_id, equipped, obtained_at, source)
           VALUES (1, 'iron_sword', 0, 'fixture', 'fixture')"""
    )
    upgrade_event_outbox(conn)


@pytest.fixture
def database_url(disposable_postgres: dict[str, str]) -> str:
    url = disposable_postgres["database_url"]
    conn = _connect(url)
    try:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        _create_legacy_schema(conn)
        conn.commit()
    finally:
        conn.close()
    return url


@pytest.fixture(autouse=True)
def gates_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CANONICAL_COIN_SHOP_PURCHASE_ENABLED", raising=False)
    monkeypatch.delenv("EQUIPMENT_CANONICAL_LOADOUT_ENABLED", raising=False)


def _head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def _run(
    url: str,
    *,
    execute: bool = False,
    owner_gate: str | None = None,
    target_environment: str = "disposable",
    freeze_confirmed: bool = False,
) -> dict:
    return runner.run_option_c_migration(
        repo_root=ROOT,
        expected_git_sha=_head(),
        target_environment=target_environment,
        execute=execute,
        owner_gate=owner_gate,
        inventory_mutation_freeze_confirmed=freeze_confirmed,
        database_url=url,
        expected_postgres_version="PostgreSQL 16.14",
    )


def _query(url: str, sql: str) -> list[tuple]:
    conn = _connect(url)
    try:
        return [tuple(row) for row in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def _table_exists(url: str, table: str) -> bool:
    return bool(
        _query(
            url,
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='%s'" % table,
        )
    )


def _equipment_definitions():
    return runner._load_equipment_definitions()


def test_source_hashes_and_cli_have_no_database_url_option() -> None:
    source = runner._check_source_binding(ROOT, _head())
    assert source["status"] == "PASS"
    assert source["migration_hashes"]["migrations/equipment_canonical_slot_v1.py"][
        "sha256"
    ] == "C4338B9270E68D0D32278A278426601A242B138A44352B828869374D213BEE06"
    assert {
        action.dest for action in runner._parser()._actions
    }.isdisjoint({"database_url", "DatabaseUrl"})


def test_default_dry_run_and_wrong_gate_never_mutate(database_url: str) -> None:
    dry_run = _run(database_url)
    assert dry_run["status"] == "DRY_RUN_READY"
    assert dry_run["mutation_guard"]["database_queries"] == "YES"
    assert dry_run["mutation_guard"]["writes"] == 0
    assert dry_run["mutation_guard"]["commits"] == 0
    assert dry_run["mutation_guard"]["migration_execution"] == 0
    assert not _table_exists(database_url, "coin_purchase_operations")


def test_postgres_preflight_session_rejects_writes(database_url: str) -> None:
    conn, pooled = runner._open_connection(database_url, read_only=True)
    try:
        with pytest.raises(Exception) as failure:
            conn.execute(
                "UPDATE public.user_stats SET coins=coins+1 WHERE user_id=1"
            )
        assert getattr(failure.value, "pgcode", None) == "25006"
    finally:
        runner._close_connection(conn, pooled=pooled, read_only=True)

    wrong_gate = _run(
        database_url,
        execute=True,
        owner_gate="GO_ENABLE",
    )
    assert wrong_gate["status"] == "BLOCKED_OWNER_GATE"
    assert wrong_gate["wrong_gate_rejected"] is True
    assert not _table_exists(database_url, "coin_purchase_operations")


def test_full_sequence_commits_b033_then_c019(
    database_url: str,
    disposable_postgres: dict[str, str],
) -> None:
    result = _run(database_url, execute=True, owner_gate=runner.OWNER_GATE)
    assert result["status"] == "EXECUTED"
    assert result["preflight"]["sequence_plan"] == "RUN_MISSING_APPROVED_MIGRATIONS"
    assert [phase["status"] for phase in result["phases"]] == [
        "COMMITTED",
        "COMMITTED",
    ]
    assert result["mutation_guard"]["commits"] == 2
    assert result["mutation_guard"]["rollbacks"] == 0
    assert disposable_postgres["server_version"].startswith("PostgreSQL 16.14")
    assert _query(
        database_url,
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='player_inventory' AND column_name='canonical_slot'",
    )
    assert _table_exists(database_url, "coin_purchase_operations")


def test_second_full_invocation_is_already_valid(database_url: str) -> None:
    first = _run(database_url, execute=True, owner_gate=runner.OWNER_GATE)
    assert first["status"] == "EXECUTED"
    second = _run(database_url, execute=True, owner_gate=runner.OWNER_GATE)
    assert second["status"] == "ALREADY_VALID"
    assert second["preflight"]["sequence_plan"] == "ALREADY_VALID"
    assert "phases" not in second
    assert second["mutation_guard"]["migration_execution"] == 0


def test_b033_already_valid_then_c019_runs(database_url: str) -> None:
    conn = _connect(database_url)
    try:
        upgrade_b033(conn, equipment_defs=_equipment_definitions())
        conn.commit()
    finally:
        conn.close()

    result = _run(database_url, execute=True, owner_gate=runner.OWNER_GATE)
    assert result["status"] == "EXECUTED"
    assert [phase["status"] for phase in result["phases"]] == [
        "ALREADY_VALID",
        "COMMITTED",
    ]
    assert result["mutation_guard"]["commits"] == 1
    assert result["mutation_guard"]["migration_execution"] == 1


def test_malformed_equipped_value_is_preflight_blocked_without_sequence(
    database_url: str,
) -> None:
    conn = _connect(database_url)
    try:
        conn.execute(
            "UPDATE public.player_inventory SET equipped=2 WHERE equip_id='iron_sword'"
        )
        conn.commit()
    finally:
        conn.close()

    result = _run(database_url, execute=True, owner_gate=runner.OWNER_GATE)
    assert result["status"] == "PRECHECK_FAIL"
    assert result["preflight"]["checks"]["equipped_state"][
        "malformed_equipped_values"
    ]["observed"] == 1
    assert not _table_exists(database_url, "coin_purchase_operations")
    assert not _query(
        database_url,
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='player_inventory' AND column_name='canonical_slot'",
    )


def test_b033_malformed_equipped_value_rolls_back_direct_migration(
    database_url: str,
) -> None:
    conn = _connect(database_url)
    try:
        conn.execute(
            "UPDATE public.player_inventory SET equipped=2 WHERE equip_id='iron_sword'"
        )
        conn.commit()
    finally:
        conn.close()

    result = runner._run_b033(
        database_url=database_url,
        equipment_definitions=_equipment_definitions(),
    )
    assert result["status"] in {"B033_MIGRATION_FAIL", "B033_POSTCHECK_FAIL"}
    assert result["transaction"] == "ROLLED_BACK"
    assert not _query(
        database_url,
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='player_inventory' AND column_name='canonical_slot'",
    )
    assert not _table_exists(database_url, "coin_purchase_operations")


def test_b033_postcheck_failure_rolls_back_and_stops(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_postcheck(*args, **kwargs):
        raise runner.PostcheckFailure("fixture_postcheck_failure")

    monkeypatch.setattr(runner, "_b033_postchecks", fail_postcheck)
    result = _run(database_url, execute=True, owner_gate=runner.OWNER_GATE)
    assert result["status"] == "B033_POSTCHECK_FAIL"
    assert result["phases"][0]["transaction"] == "ROLLED_BACK"
    assert not _table_exists(database_url, "coin_purchase_operations")
    assert not _query(
        database_url,
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='player_inventory' AND column_name='canonical_slot'",
    )


def test_c019_failure_rolls_back_only_second_transaction(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import migrations.coin_purchase_operations_v1 as c019

    def fail_upgrade(*args, **kwargs):
        raise RuntimeError("fixture_c019_failure")

    monkeypatch.setattr(c019, "upgrade", fail_upgrade)
    result = _run(database_url, execute=True, owner_gate=runner.OWNER_GATE)
    assert result["status"] == "B033_COMMITTED_COIN_PURCHASE_FAILED"
    assert [phase["status"] for phase in result["phases"]] == [
        "COMMITTED",
        "C019_MIGRATION_FAIL",
    ]
    assert result["phases"][1]["transaction"] == "ROLLED_BACK"
    assert result["partial_sequence"]["b033"] == "COMMITTED"
    assert result["partial_sequence"]["coin_purchase_operations"] == "ABSENT_OR_UNVERIFIED"
    assert _query(
        database_url,
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='player_inventory' AND column_name='canonical_slot'",
    )
    assert not _table_exists(database_url, "coin_purchase_operations")


def test_c019_postcheck_failure_preserves_committed_b033(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_postcheck(*args, **kwargs):
        raise runner.PostcheckFailure("fixture_c019_postcheck_failure")

    monkeypatch.setattr(runner, "_c019_postchecks", fail_postcheck)
    result = _run(database_url, execute=True, owner_gate=runner.OWNER_GATE)
    assert result["status"] == "B033_COMMITTED_COIN_PURCHASE_FAILED"
    assert result["phases"][0]["status"] == "COMMITTED"
    assert result["phases"][1]["status"] == "C019_POSTCHECK_FAIL"
    assert result["phases"][1]["transaction"] == "ROLLED_BACK"
    assert _query(
        database_url,
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='player_inventory' AND column_name='canonical_slot'",
    )
    assert not _table_exists(database_url, "coin_purchase_operations")


def test_partial_schema_is_never_repaired_automatically(database_url: str) -> None:
    conn = _connect(database_url)
    try:
        conn.execute(
            "ALTER TABLE public.player_inventory ADD COLUMN canonical_slot TEXT"
        )
        conn.commit()
    finally:
        conn.close()

    result = _run(database_url, execute=True, owner_gate=runner.OWNER_GATE)
    assert result["status"] == "PRECHECK_FAIL"
    assert (
        result["preflight"]["checks"]["schema_states"]["b033"]["state"]
        == "B033_PARTIAL_OR_INCOMPATIBLE"
    )
    assert not _table_exists(database_url, "coin_purchase_operations")


def test_partial_c019_schema_is_never_repaired_automatically(database_url: str) -> None:
    conn = _connect(database_url)
    try:
        conn.execute(
            "CREATE TABLE public.coin_purchase_operations "
            "(user_id INTEGER NOT NULL)"
        )
        conn.commit()
    finally:
        conn.close()

    result = _run(database_url, execute=True, owner_gate=runner.OWNER_GATE)
    assert result["status"] == "PRECHECK_FAIL"
    assert (
        result["preflight"]["checks"]["schema_states"]["c019"]["state"]
        == "C019_PARTIAL_OR_INCOMPATIBLE"
    )
    assert _table_exists(database_url, "coin_purchase_operations")
    assert not _query(
        database_url,
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='player_inventory' AND column_name='canonical_slot'",
    )


def test_production_execution_requires_external_inventory_freeze(
    database_url: str,
) -> None:
    result = _run(
        database_url,
        execute=True,
        owner_gate=runner.OWNER_GATE,
        target_environment="production",
        freeze_confirmed=False,
    )
    assert result["status"] == "BLOCKED_INVENTORY_MUTATION_FREEZE_REQUIRED"
    assert result["mutation_guard"]["writes"] == 0
    assert not _table_exists(database_url, "coin_purchase_operations")
