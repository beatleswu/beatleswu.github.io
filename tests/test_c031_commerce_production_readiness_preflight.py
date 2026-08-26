"""C031 source-contract and disposable PostgreSQL preflight tests."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import time
from uuid import uuid4

import pytest

from db import PostgresConnectionWrapper
from migrations.coin_purchase_operations_v1 import upgrade as upgrade_purchase_operations
from migrations.domain_event_outbox_v1 import upgrade as upgrade_event_outbox
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_b033
from scripts.release.commerce_production_readiness_preflight import (
    BLOCKED,
    DEFAULT_MIGRATION_PATHS,
    EquipmentDefinition,
    FAIL,
    NOT_READY,
    PASS,
    READY_FOR_OPTION_C_MAINTENANCE,
    audit_database,
    audit_source_contract,
    load_equipment_definitions_from_source,
    run_preflight,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_MASTER_AT_TASK_START = "e10735cf580fb5074e07811f76ab60445562760c"
POSTGRES_IMAGE = "postgres:16.14-alpine"
POSTGRES_USER = "c031_disposable"
POSTGRES_PASSWORD = "c031_disposable_password"
POSTGRES_DATABASE = "c031_disposable"


def _current_master_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "origin/master"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _source_kwargs() -> dict[str, object]:
    current_master = _current_master_sha()
    return {
        "repo_root": ROOT,
        "expected_application_source_sha": current_master,
        "observed_application_source_sha": current_master,
        "current_master_sha": current_master,
        "feature_gate_facts": {
            "canonical_shop": False,
            "canonical_equipment_loadout": False,
        },
        "legacy_writer_compatibility": PASS,
        "target_environment": "disposable",
    }


def _run_docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _wait_for_postgres(database_url: str, timeout: float = 60.0) -> None:
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
        pytest.skip("docker is unavailable; C031 disposable PostgreSQL proof skipped")

    container_name = f"c031-pg-{uuid4().hex[:12]}"
    started = _run_docker(
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
        published = _run_docker(
            "inspect",
            "--format",
            "{{(index (index .NetworkSettings.Ports \"5432/tcp\") 0).HostPort}}",
            container_name,
        )
        host_port = published.stdout.strip()
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
        assert "PostgreSQL 16.14" in server_version
        yield {
            "database_url": database_url,
            "container_name": container_name,
            "server_version": server_version,
        }
    finally:
        _run_docker("rm", "--force", container_name)


@pytest.fixture()
def pg_connection(disposable_postgres: dict[str, str]):
    import psycopg2
    from psycopg2.extras import DictCursor

    raw = psycopg2.connect(
        disposable_postgres["database_url"],
        cursor_factory=DictCursor,
    )
    conn = PostgresConnectionWrapper(raw, pooled=False)
    try:
        _create_ready_schema(conn)
        conn.commit()
        conn._conn.set_session(readonly=True)
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _create_ready_schema(conn: PostgresConnectionWrapper) -> None:
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
            user_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            obtained_at TEXT NOT NULL,
            source TEXT NOT NULL,
            PRIMARY KEY (user_id, item_id)
        )"""
    )
    upgrade_b033(
        conn,
        equipment_defs=(
            {"id": "iron_sword", "slot": "weapon"},
            {"id": "cloth_robe", "slot": "armor"},
            {"id": "lucky_stone", "slot": "accessory"},
            {"id": "xp_amulet", "slot": "accessory"},
            {"id": "go_stone_black", "slot": "accessory"},
        ),
    )
    upgrade_purchase_operations(conn)
    upgrade_event_outbox(conn)


class ReadOnlyConnectionProbe:
    """Reject any non-SELECT statement made by the auditor under test."""

    def __init__(self, conn: PostgresConnectionWrapper):
        self._conn = conn
        self.statements: list[str] = []

    def _record(self, sql: str) -> None:
        keyword = sql.lstrip().split(None, 1)[0].upper()
        self.statements.append(keyword)
        if keyword not in {"SELECT", "WITH"}:
            raise AssertionError(f"C031 auditor attempted non-read SQL: {sql}")

    def execute(self, sql: str, parameters=None):
        self._record(sql)
        return self._conn.execute(sql, parameters)

    def cursor(self, *args, **kwargs):
        return _ReadOnlyCursor(self, self._conn.cursor(*args, **kwargs))


class _ReadOnlyCursor:
    def __init__(self, probe: ReadOnlyConnectionProbe, cursor):
        self._probe = probe
        self._cursor = cursor

    def execute(self, sql: str, parameters=None):
        self._probe._record(sql)
        return self._cursor.execute(sql, parameters)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def description(self):
        return self._cursor.description

    def __enter__(self):
        self._cursor.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._cursor.__exit__(exc_type, exc_val, exc_tb)


def test_source_contract_and_migration_hashes_pass_without_importing_app():
    checks = audit_source_contract(
        **_source_kwargs(),
        migration_paths=DEFAULT_MIGRATION_PATHS,
    )

    assert checks["application_source_sha"]["status"] == PASS
    assert checks["equipment_definition_source_contract"]["status"] == PASS
    assert checks["canonical_shop_feature_gate"]["status"] == PASS
    assert checks["canonical_equipment_loadout_feature_gate"]["status"] == PASS
    assert checks["legacy_text_timestamp_compatibility"]["status"] == PASS
    assert checks["runtime_writer_compatibility"]["status"] == FAIL
    assert checks["runtime_writer_compatibility"]["details"][
        "caller_evidence_role"
    ] == "secondary_only_ignored_for_readiness"
    assert checks["migration_manifest"]["status"] == PASS
    assert checks["no_revenue_enablement_implied"]["status"] == PASS


def test_source_identity_mismatch_fails_closed():
    kwargs = _source_kwargs()
    kwargs["observed_application_source_sha"] = "0" * 40
    result = run_preflight(**kwargs, conn=None)
    assert result["status"] == BLOCKED
    assert result["checks"]["application_source_sha"]["status"] == BLOCKED
    assert result["mutation_guard"]["writes"] == 0
    assert result["mutation_guard"]["commits"] == 0
    assert result["mutation_guard"]["rollbacks"] == 0
    assert result["mutation_guard"]["migration_execution"] == 0
    assert result["mutation_guard"]["database_queries"] == 0
    assert result["DATABASE_QUERY_PERFORMED_BY_C031"] == "NO"
    assert result["PRODUCTION_QUERY_PERFORMED_BY_C031"] == "NO"


def test_missing_connection_is_blocked_without_attempting_database_query():
    result = run_preflight(**_source_kwargs(), conn=None)
    assert result["status"] == BLOCKED
    assert result["checks"]["postgres_version"]["status"] == BLOCKED
    assert result["DATABASE_QUERY_PERFORMED_BY_C031"] == "NO"
    assert result["PRODUCTION_QUERY_PERFORMED_BY_C031"] == "NO"
    assert result["checks"]["target_environment"]["status"] == PASS


def test_equipment_source_contract_is_read_without_executing_app():
    definitions = load_equipment_definitions_from_source(ROOT)
    assert len(definitions) == 15
    assert {definition.item_id for definition in definitions} >= {
        "xp_amulet",
        "go_stone_black",
    }
    assert all(isinstance(definition, EquipmentDefinition) for definition in definitions)


def test_disposable_postgres_ready_report_is_select_only(
    pg_connection: PostgresConnectionWrapper,
    disposable_postgres: dict[str, str],
):
    definitions = load_equipment_definitions_from_source(ROOT)
    probe = ReadOnlyConnectionProbe(pg_connection)
    result = run_preflight(
        **_source_kwargs(),
        conn=probe,
        database_read_only_enforced=True,
        equipment_definitions=definitions,
        expected_postgres_version="PostgreSQL 16.14",
    )

    assert result["status"] == NOT_READY
    checks = result["checks"]
    for name in (
        "postgres_version",
        "user_stats_schema",
        "currency_log_schema",
        "player_inventory_schema",
        "shop_inventory_schema",
        "player_wardrobe_schema",
        "player_inventory_canonical_slot",
        "b033_invariant_index_state",
        "equipped_xp_amulet_count",
        "equipped_go_stone_black_count",
        "duplicate_equipped_canonical_slot_groups",
        "malformed_equipped_rows",
        "coin_purchase_operations_schema",
        "domain_event_outbox_schema",
        "currency_log_created_at_type",
        "player_inventory_obtained_at_type",
        "player_wardrobe_obtained_at_type",
    ):
        assert checks[name]["status"] == PASS, name

    assert checks["equipped_xp_amulet_count"]["observed"] == 0
    assert checks["equipped_go_stone_black_count"]["observed"] == 0
    assert checks["currency_log_created_at_type"]["observed"] == "text"
    assert checks["player_inventory_obtained_at_type"]["observed"] == "text"
    assert checks["player_wardrobe_obtained_at_type"]["observed"] == "text"
    assert probe.statements
    assert set(probe.statements) <= {"SELECT", "WITH"}
    assert result["mutation_guard"]["writes"] == 0
    assert result["DATABASE_QUERY_PERFORMED_BY_C031"] == "YES"
    assert result["PRODUCTION_QUERY_PERFORMED_BY_C031"] == "NO"
    assert result["mutation_guard"]["database_queries"] > 0
    assert result["checks"]["database_read_only_enforcement"]["status"] == PASS
    assert "16.14" in checks["postgres_version"]["observed"]
    assert disposable_postgres["server_version"].startswith("PostgreSQL 16.14")

    production_label_only = run_preflight(
        **{**_source_kwargs(), "target_environment": "production"},
        conn=probe,
        database_read_only_enforced=True,
        equipment_definitions=definitions,
        expected_postgres_version="PostgreSQL 16.14",
    )
    assert production_label_only["DATABASE_QUERY_PERFORMED_BY_C031"] == "YES"
    assert production_label_only["PRODUCTION_QUERY_PERFORMED_BY_C031"] == "YES"


def test_incompatible_database_status_is_not_ready():
    class MissingSchemaConnection:
        def execute(self, sql: str, parameters=None):
            if "SELECT version()" in sql:
                return _Rows([("PostgreSQL 16.14 disposable",)])
            if "information_schema.columns" in sql:
                return _Rows([])
            raise AssertionError(f"unexpected fixture SQL: {sql}")

    result = run_preflight(
        **_source_kwargs(),
        conn=MissingSchemaConnection(),
        equipment_definitions=load_equipment_definitions_from_source(ROOT),
    )
    assert result["status"] == NOT_READY
    assert result["checks"]["coin_purchase_operations_schema"]["status"] == FAIL
    assert result["checks"]["player_inventory_canonical_slot"]["status"] == FAIL


def test_query_metadata_other_target_is_unknown_without_hostname_inference():
    class QueryingFixture:
        def execute(self, sql: str, parameters=None):
            return _Rows([("PostgreSQL 16.14 disposable",)])

    result = run_preflight(
        **{**_source_kwargs(), "target_environment": "other"},
        conn=QueryingFixture(),
    )
    assert result["DATABASE_QUERY_PERFORMED_BY_C031"] == "YES"
    assert result["PRODUCTION_QUERY_PERFORMED_BY_C031"] == "UNKNOWN"


def _future_ready_source_fixture() -> dict[str, str]:
    return {
        "monster_runtime.py": (
            "from equipment_ownership_service import grant_equipment_ownership\n"
            "def settle_drop(conn, user_id, equip_id):\n"
            "    return grant_equipment_ownership(conn, user_id, equip_id, source='drop')\n"
        ),
        "admin_runtime.py": (
            "from equipment_ownership_service import grant_equipment_ownership\n"
            "def grant_admin(conn, user_id, equip_id):\n"
            "    return grant_equipment_ownership(conn, user_id, equip_id, source='admin')\n"
        ),
        "equipment_routes.py": (
            "from equipment_loadout_service import equip_owned_item, unequip_owned_item\n"
            "CANONICAL_EQUIPMENT_LOADOUT_ENABLED = False\n"
            "def equip(conn, user_id, equip_id, inv_id):\n"
            "    return equip_owned_item(conn, user_id, equip_id, ownership_row_id=inv_id)\n"
            "def unequip(conn, user_id, equip_id, inv_id):\n"
            "    return unequip_owned_item(conn, user_id, equip_id, ownership_row_id=inv_id)\n"
        ),
        "shop_routes.py": (
            "from shop_offer_identity_projection import project_shop_offer\n"
            "from coin_purchase_authority import purchase_with_coins\n"
            "from shop_acquisition_result_bridge import adapt_committed_shop_purchase\n"
            "CANONICAL_SHOP_RUNTIME_ENABLED = False\n"
            "def buy(facts, conn, user_id, operation_id):\n"
            "    offer = project_shop_offer(facts)\n"
            "    result = purchase_with_coins(conn, user_id=user_id, purchase_operation_id=operation_id, offer=offer)\n"
            "    return adapt_committed_shop_purchase(conn, result)\n"
        ),
    }


def test_future_ready_source_fixture_passes_without_modifying_app():
    checks = audit_source_contract(
        **_source_kwargs(),
        source_contract_fixture=_future_ready_source_fixture(),
    )
    for key in (
        "monster_equipment_writer_source_compatibility",
        "admin_equipment_writer_source_compatibility",
        "equipment_route_source_compatibility",
        "canonical_shop_runtime_source_compatibility",
        "runtime_writer_compatibility",
    ):
        assert checks[key]["status"] == PASS, key


def test_caller_pass_cannot_override_unsafe_current_source():
    checks = audit_source_contract(**_source_kwargs())
    assert checks["runtime_writer_compatibility"]["status"] == FAIL
    assert checks["runtime_writer_compatibility"]["details"][
        "caller_legacy_writer_compatibility"
    ] == PASS

    result = run_preflight(**_source_kwargs(), conn=None)
    assert result["status"] != READY_FOR_OPTION_C_MAINTENANCE
    assert result["checks"]["runtime_writer_compatibility"]["status"] == FAIL


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)
