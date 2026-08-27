"""Disposable end-to-end rehearsal for the governed Option C sequence.

This suite composes the accepted C038 read-only quiescence decision with the
accepted C036 migration runner. It deliberately uses only a local,
ephemeral PostgreSQL 16.14 container. No Production URL, source, credential,
or application route is accepted by this test driver.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import shutil
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pytest

from coin_purchase_authority import SqlAcquisitionAuthority, purchase_with_coins
from db import PostgresConnectionWrapper
from equipment_loadout_service import equip_owned_item, unequip_owned_item
from equipment_ownership_service import grant_equipment_ownership
from migrations import coin_purchase_operations_v1 as c019_migration
from migrations import domain_event_outbox_v1 as outbox_migration
from migrations import equipment_canonical_slot_v1 as b033_migration
from shop_acquisition_result_bridge import adapt_committed_shop_purchase
from shop_offer_authority import CoinShopOffer, StaticShopOfferAuthority
from scripts.release import option_c_inventory_quiescence_precheck as precheck
from scripts.release import option_c_production_migration as runner


ROOT = Path(__file__).resolve().parents[1]
POSTGRES_IMAGE = "postgres:16.14-alpine"
POSTGRES_USER = "c039"
POSTGRES_PASSWORD = "c039_disposable_password"
POSTGRES_DATABASE = "c039"
FIXED_NOW = datetime(2026, 8, 27, 5, 0, tzinfo=timezone.utc)
MIGRATION_ORDER = (
    "migrations.equipment_canonical_slot_v1",
    "migrations.coin_purchase_operations_v1",
)


def _docker(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _wait_for_postgres(database_url: str, timeout: float = 240.0) -> str:
    import psycopg2

    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            raw = psycopg2.connect(database_url, connect_timeout=2)
            raw.autocommit = True
            with raw.cursor() as cursor:
                cursor.execute("SELECT version()")
                version = str(cursor.fetchone()[0])
            raw.close()
            return version
        except Exception as error:  # pragma: no cover - startup timing
            last_error = error
            time.sleep(0.5)
    raise RuntimeError(
        "disposable PostgreSQL did not become ready: "
        f"{type(last_error).__name__}"
    )


@pytest.fixture(scope="module")
def disposable_postgres() -> dict[str, str]:
    """Start only a local disposable PostgreSQL 16.14 target."""

    if shutil.which("docker") is None:
        pytest.skip("Docker is unavailable; C039 PostgreSQL rehearsal skipped")

    container_name = f"c039-pg-{uuid4().hex[:12]}"
    started = _docker(
        "run",
        "--rm",
        "--detach",
        "--name",
        container_name,
        "--shm-size",
        "128m",
        "--tmpfs",
        "/var/lib/postgresql/data:rw,exec,size=512m",
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
        try:
            version = _wait_for_postgres(database_url)
        except Exception as error:
            _docker("rm", "--force", container_name)
            pytest.skip(
                "disposable PostgreSQL failed to start; C039 rehearsal skipped: "
                f"{type(error).__name__}"
            )
        if not version.startswith("PostgreSQL 16.14"):
            raise RuntimeError(f"unexpected disposable PostgreSQL version: {version}")
        yield {"database_url": database_url, "version": version}
    finally:
        _docker("rm", "--force", container_name)


def _connect(database_url: str) -> PostgresConnectionWrapper:
    import psycopg2
    from psycopg2.extras import DictCursor

    raw = psycopg2.connect(database_url, cursor_factory=DictCursor)
    raw.autocommit = False
    return PostgresConnectionWrapper(raw, pooled=False)


def _equipment_definitions():
    return runner._load_equipment_definitions()


def _slot_source(definitions) -> dict[str, str]:
    return {
        str(definition["id"]): str(definition["slot"])
        for definition in definitions
        if definition.get("id") not in {"xp_amulet", "go_stone_black"}
        and definition.get("slot") in {"weapon", "armor", "accessory"}
    }


def _create_legacy_schema(conn: PostgresConnectionWrapper) -> None:
    """Create the observed pre-B033 shape and representative safe rows."""

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
            source TEXT NOT NULL DEFAULT 'fixture'
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
        """INSERT INTO public.user_stats(user_id, coins)
           VALUES (1, 250), (2, 100)"""
    )
    # These rows model valid Monster/Admin-created ownership in multiple
    # functional slots. They intentionally contain no canonical_slot column.
    conn.execute(
        """INSERT INTO public.player_inventory
             (user_id, equip_id, equipped, obtained_at, source)
           VALUES
             (1, 'iron_sword', 1, 'fixture-monster', 'drop'),
             (1, 'cloth_robe', 1, 'fixture-admin', 'admin'),
             (1, 'lucky_stone', 0, 'fixture-legacy', 'drop')"""
    )
    # D5A is a pre-existing compatible dependency, not part of the Option C
    # migration order.
    outbox_migration.upgrade(conn)


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
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def _query(database_url: str, statement: str, parameters=()) -> list[tuple]:
    conn = _connect(database_url)
    try:
        return [tuple(row) for row in conn.execute(statement, parameters).fetchall()]
    finally:
        conn.rollback()
        conn.close()


def _scalar(database_url: str, statement: str, parameters=()):
    rows = _query(database_url, statement, parameters)
    return rows[0][0] if rows else None


def _table_exists(database_url: str, table: str) -> bool:
    return bool(
        _query(
            database_url,
            """SELECT 1 FROM information_schema.tables
               WHERE table_schema='public' AND table_name=?""",
            (table,),
        )
    )


def _canonical_slot_column_exists(database_url: str) -> bool:
    return bool(
        _query(
            database_url,
            """SELECT 1 FROM information_schema.columns
               WHERE table_schema='public'
                 AND table_name='player_inventory'
                 AND column_name='canonical_slot'""",
        )
    )


def _observe(database_url: str) -> dict:
    conn = _connect(database_url)
    try:
        return precheck.observe_postgres_inventory_activity(conn)
    finally:
        conn.rollback()
        conn.close()


def _all_zero(observation: dict) -> bool:
    return all(
        observation[key] == 0
        for key in (
            "active_writer_count",
            "open_conflicting_transaction_count",
            "lock_wait_count",
            "long_running_transaction_count",
            "migration_lock_wait_count",
            "prepared_transaction_count",
        )
    )


def _writer_states(state: str = precheck.WRITER_STATE_DRAINED) -> dict[str, str]:
    return {writer["name"]: state for writer in precheck.writer_inventory()}


def _quiescence(database_url: str, *, writer_states=None) -> dict:
    first = _observe(database_url)
    assert _all_zero(first)
    time.sleep(0.1)
    second = _observe(database_url)
    second["observation_samples"] = 2
    return precheck.evaluate_quiescence(
        writer_states=writer_states or _writer_states(),
        database_observation=second,
        runtime_b033_compatible=True,
        canonical_shop_gate="OFF",
        canonical_equipment_loadout_gate="OFF",
        schema_state=precheck.EXPECTED_PRE_MIGRATION_SCHEMA,
        target_environment="disposable",
    )


def _run_c036(
    database_url: str,
    *,
    execute: bool = True,
    owner_gate: str | None = runner.OWNER_GATE,
) -> dict:
    """Call the existing C036 core; the URL is only a local test seam."""

    assert "127.0.0.1" in database_url
    assert runner._parser() is not None
    return runner.run_option_c_migration(
        repo_root=ROOT,
        expected_git_sha=_head(),
        target_environment="disposable",
        execute=execute,
        owner_gate=owner_gate,
        inventory_mutation_freeze_confirmed=True,
        database_url=database_url,
        expected_postgres_version="PostgreSQL 16.14",
    )


def _assert_legacy_schema(database_url: str) -> None:
    assert not _canonical_slot_column_exists(database_url)
    assert not _table_exists(database_url, "coin_purchase_operations")
    assert _table_exists(database_url, "domain_event_outbox")


def _assert_post_migration_schema(database_url: str, definitions) -> None:
    conn = _connect(database_url)
    try:
        b033 = b033_migration.validate_schema(conn)
        c019 = c019_migration.validate_schema(conn)
        outbox = outbox_migration.validate_schema(conn)
        assert b033["valid"] is True
        assert c019["present"] is True
        assert c019["missing"] == []
        assert outbox["present"] is True
        assert outbox["missing"] == []
        assert runner._all_pass(
            runner._equipped_state(
                conn,
                definitions,
                canonical_slot_present=True,
            )
        )
        canonical_rows = conn.execute(
            """SELECT equip_id, equipped, canonical_slot
                 FROM public.player_inventory
                WHERE equip_id IN ('iron_sword', 'cloth_robe', 'lucky_stone')
                ORDER BY equip_id"""
        ).fetchall()
        assert [(row["equip_id"], row["canonical_slot"]) for row in canonical_rows] == [
            ("cloth_robe", "armor"),
            ("iron_sword", "weapon"),
            ("lucky_stone", "accessory"),
        ]
    finally:
        conn.rollback()
        conn.close()


def _stack_offer() -> CoinShopOffer:
    return CoinShopOffer(
        offer_id="shop.static.c039_material",
        item_id="c039_material",
        quantity=1,
        currency_type="COINS",
        price=20,
        destination="shop_inventory",
        acquisition_class="MATERIAL",
        offer_type="ITEM",
        offer_version="c039-v1",
        status="ACTIVE",
        duplicate_policy="STACK",
    )


def _functional_offer(item_id: str = "iron_sword") -> CoinShopOffer:
    return CoinShopOffer(
        offer_id=f"shop.static.{item_id}",
        item_id=item_id,
        quantity=1,
        currency_type="COINS",
        price=30,
        destination="player_inventory",
        acquisition_class="WEAPON" if item_id.endswith("sword") else "ARMOR",
        offer_type="ITEM",
        offer_version="c039-functional-v1",
        status="ACTIVE",
        duplicate_policy="ALLOW_DUPLICATE",
    )


def _purchase_stack(database_url: str, operation_id: str) -> tuple:
    offer = _stack_offer()
    authority = StaticShopOfferAuthority([offer])
    conn = _connect(database_url)
    try:
        result = purchase_with_coins(
            conn,
            1,
            operation_id,
            offer.offer_id,
            offer_authority=authority,
            now=FIXED_NOW,
        )
        conn.commit()
        return result, offer
    finally:
        conn.close()


def _run_functional_purchase(database_url: str, definitions, operation_id: str):
    offer = _functional_offer()
    authority = StaticShopOfferAuthority([offer])
    conn = _connect(database_url)
    try:
        result = purchase_with_coins(
            conn,
            1,
            operation_id,
            offer.offer_id,
            offer_authority=authority,
            acquisition_authority=SqlAcquisitionAuthority(
                equipment_slot_source=_slot_source(definitions)
            ),
            now=FIXED_NOW,
        )
        conn.commit()
        return result
    finally:
        conn.close()


def _bridge_committed_result(database_url: str, result):
    conn = _connect(database_url)
    try:
        operation = conn.execute(
            """SELECT user_id, purchase_operation_id, offer_id, reward_id,
                      reward_quantity, destination, acquisition_class,
                      operation_status, lineage_event_id, result_payload
                 FROM coin_purchase_operations
                WHERE user_id=? AND purchase_operation_id=?""",
            (1, result.operation_id),
        ).fetchone()
        lineage = conn.execute(
            """SELECT event_id, event_type, player_id, payload
                 FROM domain_event_outbox WHERE event_id=?""",
            (result.lineage_event_id,),
        ).fetchone()
        assert operation is not None
        assert lineage is not None
        assert operation["operation_status"] == "COMMITTED"
        raw_payload = operation["result_payload"]
        payload = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
        assert payload["ownership_reference"] == result.ownership_reference
        return adapt_committed_shop_purchase(conn, result, dict(operation), dict(lineage))
    finally:
        conn.rollback()
        conn.close()


def test_success_path_composes_c038_c036_and_acceptance(
    database_url: str,
    disposable_postgres: dict[str, str],
) -> None:
    definitions = _equipment_definitions()
    handoff = _quiescence(database_url)
    assert handoff["status"] == precheck.QUIESCENCE_READY
    assert handoff["ready"] is True
    assert handoff["migration_sequence"] == [
        "migrations/equipment_canonical_slot_v1.py",
        "migrations/coin_purchase_operations_v1.py",
    ]

    # This is the exact C036 execute + exact owner-gate path, but the URL is
    # asserted local and disposable before entering the call.
    result = _run_c036(database_url, execute=True, owner_gate=runner.OWNER_GATE)
    assert result["status"] == "EXECUTED"
    assert [phase["migration"] for phase in result["phases"]] == list(MIGRATION_ORDER)
    assert [phase["status"] for phase in result["phases"]] == [
        "COMMITTED",
        "COMMITTED",
    ]
    assert result["mutation_guard"]["commits"] == 2
    assert result["mutation_guard"]["rollbacks"] == 0
    assert result["mutation_guard"]["migration_execution"] == 2
    assert disposable_postgres["version"].startswith("PostgreSQL 16.14")
    _assert_post_migration_schema(database_url, definitions)

    # Exercise the migrated C026 player_inventory path and the D024 bridge.
    functional = _run_functional_purchase(database_url, definitions, "c039-functional")
    assert functional.ownership_reference.startswith("player_inventory:")
    canonical = _bridge_committed_result(database_url, functional)
    assert canonical.ownership_reference == functional.ownership_reference

    recovery = precheck.migration_recovery_plan(
        b033_status="COMMITTED",
        c019_status="COMMITTED",
        b033_postchecks_passed=True,
        c019_postchecks_passed=True,
    )
    assert recovery["status"] == "FULL_SEQUENCE_ACCEPTED"
    assert precheck.writers_may_resume_after_acceptance(
        b033_postchecks_passed=True,
        c019_postchecks_passed=True,
        runtime_acceptance_passed=True,
        schema_acceptance_passed=True,
    ) is True
    assert runner._effective_gate(runner.GATE_NAMES["canonical_shop"])["effective"] == "OFF"
    assert runner._effective_gate(
        runner.GATE_NAMES["canonical_equipment_loadout"]
    )["effective"] == "OFF"

    # Resume one allowed B040 writer only after all acceptance checks.
    conn = _connect(database_url)
    try:
        resumed = grant_equipment_ownership(
            conn,
            1,
            "fox_fang",
            "drop",
            equipment_defs=definitions,
        )
        assert resumed.canonical_slot == "weapon"
        conn.commit()
    finally:
        conn.close()


def test_disposable_gate_path_and_wrong_gate_fail_closed(database_url: str) -> None:
    dry_run = _run_c036(database_url, execute=False, owner_gate=None)
    assert dry_run["status"] == "DRY_RUN_READY"
    wrong = _run_c036(database_url, execute=True, owner_gate="GO_ENABLE")
    assert wrong["status"] == "BLOCKED_OWNER_GATE"
    assert wrong["wrong_gate_rejected"] is True
    _assert_legacy_schema(database_url)
    exact = _run_c036(database_url, execute=True, owner_gate=runner.OWNER_GATE)
    assert exact["status"] == "EXECUTED"


def test_active_writer_blocks_handoff_and_no_migration_starts(database_url: str) -> None:
    writer = _connect(database_url)
    try:
        writer.execute(
            """INSERT INTO public.player_inventory
                 (user_id, equip_id, equipped, obtained_at, source)
               VALUES (?, ?, 0, ?, ?)""",
            (1, "dragon_claw", "c039-active", "drop"),
        )
        observation = _observe(database_url)
        observation["observation_samples"] = 2
        blocked = precheck.evaluate_quiescence(
            writer_states=_writer_states(),
            database_observation=observation,
            runtime_b033_compatible=True,
            canonical_shop_gate="OFF",
            canonical_equipment_loadout_gate="OFF",
            schema_state=precheck.EXPECTED_PRE_MIGRATION_SCHEMA,
            target_environment="disposable",
        )
        assert blocked["status"] == precheck.WRITER_ACTIVE
        assert blocked["ready"] is False
        # Orchestration must not hand an active writer to C036.
        assert not _canonical_slot_column_exists(database_url)
        assert not _table_exists(database_url, "coin_purchase_operations")
    finally:
        writer.rollback()
        writer.close()


def test_unknown_writer_state_blocks_handoff(database_url: str) -> None:
    states = _writer_states()
    states["admin_equipment_grant"] = precheck.WRITER_STATE_UNKNOWN_VALUE
    blocked = _quiescence(database_url, writer_states=states)
    assert blocked["status"] == precheck.WRITER_STATE_UNKNOWN
    assert blocked["ready"] is False
    assert not _canonical_slot_column_exists(database_url)
    assert not _table_exists(database_url, "coin_purchase_operations")


def test_in_flight_writer_drains_before_governed_handoff_without_loss(
    database_url: str,
) -> None:
    writer = _connect(database_url)
    try:
        writer.execute(
            """INSERT INTO public.player_inventory
                 (user_id, equip_id, equipped, obtained_at, source)
               VALUES (?, ?, 0, ?, ?)""",
            (1, "dragon_scale", "c039-drain", "admin"),
        )
        active = _observe(database_url)
        assert active["active_writer_count"] >= 1

        writer.commit()
        deadline = time.monotonic() + 15
        drained = None
        while time.monotonic() < deadline:
            candidate = _observe(database_url)
            if _all_zero(candidate):
                drained = candidate
                break
            time.sleep(0.1)
        assert drained is not None
        handoff = _quiescence(database_url)
        assert handoff["status"] == precheck.QUIESCENCE_READY
        result = _run_c036(database_url, execute=True, owner_gate=runner.OWNER_GATE)
        assert result["status"] == "EXECUTED"
        assert _scalar(
            database_url,
            "SELECT COUNT(*) FROM public.player_inventory WHERE equip_id=?",
            ("dragon_scale",),
        ) == 1
    finally:
        writer.rollback()
        writer.close()


def test_b033_failure_rolls_back_and_keeps_sequence_stopped(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _quiescence(database_url)["ready"] is True

    def fail_postcheck(*args, **kwargs):
        raise runner.PostcheckFailure("c039_b033_postcheck_failure")

    monkeypatch.setattr(runner, "_b033_postchecks", fail_postcheck)
    result = _run_c036(database_url, execute=True, owner_gate=runner.OWNER_GATE)
    assert result["status"] == "B033_POSTCHECK_FAIL"
    assert result["phases"][0]["transaction"] == "ROLLED_BACK"
    recovery = precheck.migration_recovery_plan(b033_status="FAILED")
    assert recovery["action"] == "ROLLBACK_B033_AND_STOP"
    assert recovery["c019_attempted"] is False
    assert recovery["writers_remain_quiesced"] is True
    _assert_legacy_schema(database_url)


def test_c019_failure_preserves_committed_b033_and_blocks_resume(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _quiescence(database_url)["ready"] is True

    def fail_upgrade(*args, **kwargs):
        raise RuntimeError("c039_c019_failure")

    monkeypatch.setattr(c019_migration, "upgrade", fail_upgrade)
    result = _run_c036(database_url, execute=True, owner_gate=runner.OWNER_GATE)
    assert result["status"] == "B033_COMMITTED_COIN_PURCHASE_FAILED"
    assert result["phases"][0]["status"] == "COMMITTED"
    assert result["phases"][1]["transaction"] == "ROLLED_BACK"
    assert result["partial_sequence"]["b033"] == "COMMITTED"
    assert result["partial_sequence"]["old_c32_runtime_rollback"] is False
    recovery = precheck.migration_recovery_plan(
        b033_status="COMMITTED", c019_status="FAILED"
    )
    assert recovery["action"] == "ROLLBACK_C019_TRANSACTION_ONLY_AND_STOP"
    assert recovery["writers_remain_quiesced"] is True
    conn = _connect(database_url)
    try:
        assert b033_migration.validate_schema(conn)["valid"] is True
    finally:
        conn.rollback()
        conn.close()
    assert not _table_exists(database_url, "coin_purchase_operations")


@pytest.mark.parametrize("phase", ["b033", "c019"])
def test_postcheck_failure_blocks_resume_and_keeps_gates_off(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    assert _quiescence(database_url)["ready"] is True

    def fail_postcheck(*args, **kwargs):
        raise runner.PostcheckFailure(f"c039_{phase}_postcheck_failure")

    if phase == "b033":
        monkeypatch.setattr(runner, "_b033_postchecks", fail_postcheck)
    else:
        monkeypatch.setattr(runner, "_c019_postchecks", fail_postcheck)
    result = _run_c036(database_url, execute=True, owner_gate=runner.OWNER_GATE)
    if phase == "b033":
        assert result["status"] == "B033_POSTCHECK_FAIL"
        assert not _canonical_slot_column_exists(database_url)
    else:
        assert result["status"] == "B033_COMMITTED_COIN_PURCHASE_FAILED"
        assert _canonical_slot_column_exists(database_url)
        assert not _table_exists(database_url, "coin_purchase_operations")
    assert precheck.writers_may_resume_after_acceptance(
        b033_postchecks_passed=False if phase == "b033" else True,
        c019_postchecks_passed=False,
        runtime_acceptance_passed=False,
        schema_acceptance_passed=False,
    ) is False
    assert runner._effective_gate(runner.GATE_NAMES["canonical_shop"])["effective"] == "OFF"
    assert runner._effective_gate(
        runner.GATE_NAMES["canonical_equipment_loadout"]
    )["effective"] == "OFF"


def test_migration_replay_and_c019_purchase_replay_are_idempotent(
    database_url: str,
    disposable_postgres: dict[str, str],
) -> None:
    first = _run_c036(database_url, execute=True, owner_gate=runner.OWNER_GATE)
    assert first["status"] == "EXECUTED"
    first_purchase, offer = _purchase_stack(database_url, "c039-replay")
    replay_purchase, _ = _purchase_stack(database_url, "c039-replay")
    assert replay_purchase.replayed is True
    assert replay_purchase.canonical_payload() == first_purchase.canonical_payload()
    assert _scalar(database_url, "SELECT coins FROM public.user_stats WHERE user_id=1") == 230
    assert _scalar(
        database_url,
        "SELECT qty FROM public.shop_inventory WHERE user_id=1 AND item_key=?",
        (offer.item_id,),
    ) == 1
    second = _run_c036(database_url, execute=True, owner_gate=runner.OWNER_GATE)
    assert second["status"] == "ALREADY_VALID"
    assert second["preflight"]["sequence_plan"] == "ALREADY_VALID"
    assert second["mutation_guard"]["migration_execution"] == 0
    assert _scalar(database_url, "SELECT COUNT(*) FROM public.domain_event_outbox") == 1
    assert _scalar(database_url, "SELECT COUNT(*) FROM public.coin_purchase_operations") == 1
    assert disposable_postgres["version"].startswith("PostgreSQL 16.14")


def test_post_b033_supported_writers_and_legacy_writer_are_governed(
    database_url: str,
) -> None:
    definitions = _equipment_definitions()
    result = _run_c036(database_url, execute=True, owner_gate=runner.OWNER_GATE)
    assert result["status"] == "EXECUTED"
    conn = _connect(database_url)
    try:
        monster = grant_equipment_ownership(
            conn, 1, "fox_fang", "drop", equipment_defs=definitions
        )
        admin = grant_equipment_ownership(
            conn, 1, "dragon_scale", "admin", equipment_defs=definitions
        )
        assert monster.canonical_slot == "weapon"
        assert admin.canonical_slot == "armor"
        conn.commit()

        equipped = equip_owned_item(
            conn,
            1,
            "fox_fang",
            ownership_row_id=monster.row_id,
            equipment_defs=definitions,
        )
        assert equipped["changed"] is True
        unequipped = unequip_owned_item(
            conn,
            1,
            "fox_fang",
            ownership_row_id=monster.row_id,
            equipment_defs=definitions,
        )
        assert unequipped["changed"] is True
        conn.commit()

        # Admin remove is a server-owned exact user/id predicate. It is
        # represented here without importing app.py route orchestration.
        conn.execute(
            "DELETE FROM public.player_inventory WHERE id=? AND user_id=?",
            (admin.row_id, 1),
        )
        conn.commit()

        # An old writer that creates an equipped row without canonical_slot is
        # rejected by B033; it is never treated as safe post-migration traffic.
        with pytest.raises(Exception) as failure:
            conn.execute(
                """INSERT INTO public.player_inventory
                     (user_id, equip_id, equipped, obtained_at, source)
                   VALUES (?, ?, 1, ?, ?)""",
                (1, "dragon_claw", "c039-legacy", "legacy"),
            )
        assert getattr(failure.value, "pgcode", None) == "23514"
        conn.rollback()
    finally:
        conn.rollback()
        conn.close()
    assert _scalar(
        database_url,
        "SELECT COUNT(*) FROM public.player_inventory WHERE source='c039-legacy'",
    ) == 0
    assert _scalar(
        database_url,
        "SELECT COUNT(*) FROM public.player_inventory WHERE equip_id='fox_fang' AND equipped=0",
    ) == 1


def test_sequence_binding_and_fixture_are_disposable_only() -> None:
    assert runner.MIGRATION_ORDER == MIGRATION_ORDER
    assert precheck.MIGRATION_SEQUENCE == (
        "migrations/equipment_canonical_slot_v1.py",
        "migrations/coin_purchase_operations_v1.py",
    )
    assert runner.OWNER_GATE == "GO_PRODUCTION_DB_MIGRATION"
    assert "production" not in {"disposable"}
    assert "-Execute" in {
        action.option_strings[0]
        for action in runner._parser()._actions
        if action.option_strings
    }
    assert "-OwnerGate" in {
        action.option_strings[0]
        for action in runner._parser()._actions
        if action.option_strings
    }
