"""Focused C038 tests for governed inventory-write quiescence."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest

from db import PostgresConnectionWrapper
from scripts.release import option_c_inventory_quiescence_precheck as precheck


ROOT = Path(__file__).resolve().parents[1]
POSTGRES_IMAGE = "postgres:16.14-alpine"
POSTGRES_USER = "c038"
POSTGRES_PASSWORD = "c038_disposable_password"
POSTGRES_DATABASE = "c038"


def _docker(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _wait_for_postgres(database_url: str, timeout: float = 120.0) -> None:
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
            time.sleep(0.25)
    raise RuntimeError(f"disposable PostgreSQL did not become ready: {last_error}")


@pytest.fixture(scope="module")
def disposable_postgres() -> dict[str, str]:
    if shutil.which("docker") is None:
        pytest.skip("docker is unavailable; C038 PostgreSQL proof skipped")

    container_name = f"c038-pg-{uuid4().hex[:12]}"
    started = _docker(
        "run",
        "--rm",
        "--detach",
        "--name",
        container_name,
        "--shm-size",
        "128m",
        "--tmpfs",
        "/var/lib/postgresql/data",
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
            _wait_for_postgres(database_url)
        except Exception as error:
            _docker("rm", "--force", container_name)
            pytest.skip(
                "disposable PostgreSQL failed to start; C038 PostgreSQL proof skipped: "
                f"{type(error).__name__}"
            )

        import psycopg2

        raw = psycopg2.connect(database_url)
        with raw.cursor() as cursor:
            cursor.execute("SELECT version()")
            server_version = str(cursor.fetchone()[0])
        raw.close()
        if "PostgreSQL 16.14" not in server_version:
            raise RuntimeError(f"unexpected disposable PostgreSQL version: {server_version}")
        yield {"database_url": database_url, "server_version": server_version}
    finally:
        _docker("rm", "--force", container_name)


def _connect(database_url: str) -> PostgresConnectionWrapper:
    import psycopg2
    from psycopg2.extras import DictCursor

    raw = psycopg2.connect(database_url, cursor_factory=DictCursor)
    return PostgresConnectionWrapper(raw, pooled=False)


def _reset_schema(database_url: str) -> None:
    conn = _connect(database_url)
    try:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute(
            """CREATE TABLE public.player_inventory (
                id BIGSERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                equip_id TEXT NOT NULL,
                equipped INTEGER NOT NULL DEFAULT 0,
                canonical_slot TEXT,
                obtained_at TEXT NOT NULL
            )"""
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def database_url(disposable_postgres: dict[str, str]) -> str:
    url = disposable_postgres["database_url"]
    _reset_schema(url)
    return url


def _zero_observation() -> dict[str, int]:
    return {
        "active_writer_count": 0,
        "open_conflicting_transaction_count": 0,
        "lock_wait_count": 0,
        "long_running_transaction_count": 0,
        "migration_lock_wait_count": 0,
        "prepared_transaction_count": 0,
        "observation_samples": 2,
        "database_queries": 0,
        "writes": 0,
        "commits": 0,
        "rollbacks": 0,
        "migration_execution": 0,
    }


def _ready_result(**overrides: object) -> dict:
    observation = _zero_observation()
    observation.update(overrides.pop("database_observation", {}))
    states = {
        writer["name"]: precheck.WRITER_STATE_DRAINED
        for writer in precheck.writer_inventory()
    }
    arguments: dict[str, object] = {
        "writer_states": states,
        "database_observation": observation,
        "runtime_b033_compatible": True,
        "canonical_shop_gate": "OFF",
        "canonical_equipment_loadout_gate": "OFF",
        "schema_state": dict(precheck.EXPECTED_PRE_MIGRATION_SCHEMA),
        "target_environment": "disposable",
    }
    arguments.update(overrides)
    return precheck.evaluate_quiescence(
        **arguments,
    )


def test_writer_inventory_is_complete_and_separates_b033_mutator() -> None:
    live = precheck.writer_inventory()
    maintenance = precheck.maintenance_mutator_inventory()

    assert len(live) == 8
    assert len(maintenance) == 1
    assert {
        writer["name"] for writer in live
    } == {
        "monster_functional_equipment_acquisition",
        "admin_equipment_grant",
        "admin_equipment_remove",
        "player_equipment_equip_canonical",
        "player_equipment_unequip_canonical",
        "player_equipment_equip_legacy",
        "player_equipment_unequip_legacy",
        "canonical_shop_functional_equipment_acquisition",
    }
    assert maintenance[0]["name"] == "b033_equipment_canonical_slot_backfill"
    for writer in [*live, *maintenance]:
        assert writer["stop_mechanism"]
        assert writer["drain_signal"]
        assert writer["resume_mechanism"]


def test_quiescence_requires_explicit_drain_and_zero_database_conflicts() -> None:
    result = _ready_result()
    assert result["status"] == precheck.QUIESCENCE_READY
    assert result["ready"] is True
    assert result["mutation_guard"]["writes"] == 0

    states = {
        writer["name"]: precheck.WRITER_STATE_DRAINED
        for writer in precheck.writer_inventory()
    }
    states["admin_equipment_grant"] = precheck.WRITER_STATE_ACTIVE
    blocked = precheck.evaluate_quiescence(
        writer_states=states,
        database_observation=_zero_observation(),
        runtime_b033_compatible=True,
        canonical_shop_gate="OFF",
        canonical_equipment_loadout_gate="OFF",
        schema_state=precheck.EXPECTED_PRE_MIGRATION_SCHEMA,
    )
    assert blocked["status"] == precheck.WRITER_ACTIVE
    assert blocked["ready"] is False


def test_single_database_sample_is_not_a_drain_proof() -> None:
    observation = _zero_observation()
    observation["observation_samples"] = 1
    result = _ready_result(database_observation=observation)
    assert result["status"] == precheck.WRITER_STATE_UNKNOWN
    assert result["ready"] is False


def test_unknown_missing_or_extra_writer_state_fails_closed() -> None:
    states = {
        writer["name"]: precheck.WRITER_STATE_DRAINED
        for writer in precheck.writer_inventory()
    }
    states.pop("admin_equipment_grant")
    states["unregistered_writer"] = precheck.WRITER_STATE_DRAINED
    result = precheck.evaluate_quiescence(
        writer_states=states,
        database_observation=_zero_observation(),
        runtime_b033_compatible=True,
        canonical_shop_gate="OFF",
        canonical_equipment_loadout_gate="OFF",
        schema_state=precheck.EXPECTED_PRE_MIGRATION_SCHEMA,
    )
    assert result["status"] == precheck.WRITER_STATE_UNKNOWN
    assert result["ready"] is False


@pytest.mark.parametrize(
    ("field", "status"),
    [
        ("active_writer_count", precheck.WRITER_ACTIVE),
        ("lock_wait_count", precheck.WRITER_ACTIVE),
        ("long_running_transaction_count", precheck.WRITER_ACTIVE),
        ("open_conflicting_transaction_count", precheck.OPEN_CONFLICTING_TRANSACTION),
        ("migration_lock_wait_count", precheck.OPEN_CONFLICTING_TRANSACTION),
        ("prepared_transaction_count", precheck.OPEN_CONFLICTING_TRANSACTION),
    ],
)
def test_database_activity_blocks_nonzero_observations(field: str, status: str) -> None:
    result = _ready_result(database_observation={field: 1})
    assert result["status"] == status
    assert result["ready"] is False


def test_runtime_gate_and_schema_evidence_fail_closed() -> None:
    runtime = _ready_result(runtime_b033_compatible=False)
    assert runtime["status"] == precheck.RUNTIME_NOT_B033_COMPATIBLE

    gate = _ready_result(canonical_shop_gate="ON")
    assert gate["status"] == precheck.FEATURE_GATE_UNEXPECTED

    unknown_gate = _ready_result(canonical_equipment_loadout_gate=None)
    assert unknown_gate["status"] == precheck.FEATURE_GATE_UNEXPECTED

    schema = dict(precheck.EXPECTED_PRE_MIGRATION_SCHEMA)
    schema["coin_purchase_operations"] = "PRESENT"
    schema_result = _ready_result(schema_state=schema)
    assert schema_result["status"] == precheck.SCHEMA_STATE_UNEXPECTED


def test_recovery_and_resume_contracts_are_fail_closed() -> None:
    b033_failure = precheck.migration_recovery_plan(b033_status="FAILED")
    assert b033_failure["action"] == "ROLLBACK_B033_AND_STOP"
    assert b033_failure["c019_attempted"] is False
    assert b033_failure["writers_remain_quiesced"] is True

    c019_failure = precheck.migration_recovery_plan(
        b033_status="COMMITTED", c019_status="FAILED"
    )
    assert c019_failure["status"] == "B033_COMMITTED_COIN_PURCHASE_FAILED"
    assert c019_failure["action"] == "ROLLBACK_C019_TRANSACTION_ONLY_AND_STOP"
    assert c019_failure["safe_schema_state"] == "B033_COMMITTED_C019_ABSENT_OR_UNVERIFIED"

    acceptance = precheck.migration_recovery_plan(
        b033_status="COMMITTED",
        c019_status="COMMITTED",
        b033_postchecks_passed=True,
        c019_postchecks_passed=True,
    )
    assert acceptance["status"] == "FULL_SEQUENCE_ACCEPTED"
    assert precheck.writers_may_resume_after_acceptance(
        b033_postchecks_passed=True,
        c019_postchecks_passed=True,
        runtime_acceptance_passed=True,
        schema_acceptance_passed=True,
    ) is True
    assert precheck.writers_may_resume_after_acceptance(
        b033_postchecks_passed=True,
        c019_postchecks_passed=True,
        runtime_acceptance_passed=True,
        schema_acceptance_passed=False,
    ) is False


def test_observer_rejects_non_select_and_reports_no_mutation() -> None:
    with pytest.raises(precheck.QuiescenceObservationError):
        precheck._select(object(), "UPDATE player_inventory SET equipped=0")

    class Result:
        def __init__(self, row: dict[str, int]):
            self.row = row

        def fetchone(self) -> dict[str, int]:
            return self.row

    class RecordingConnection:
        def __init__(self):
            self.statements: list[str] = []

        def execute(self, statement: str, parameters: tuple) -> Result:
            self.statements.append(statement)
            if len(self.statements) == 1:
                return Result({"relation_oid": 123})
            if len(self.statements) == 2:
                return Result(
                    {
                        "active_writer_count": 0,
                        "open_conflicting_transaction_count": 0,
                        "lock_wait_count": 0,
                        "long_running_transaction_count": 0,
                    }
                )
            if len(self.statements) == 3:
                return Result(
                    {
                        "migration_lock_wait_count": 0,
                    }
                )
            return Result({"prepared_transaction_count": 0})

    conn = RecordingConnection()
    result = precheck.observe_postgres_inventory_activity(conn)
    assert len(conn.statements) == 4
    assert all(statement.lstrip().split(None, 1)[0].upper() in {"SELECT", "WITH"}
               for statement in conn.statements)
    assert result["writes"] == 0
    assert result["commits"] == 0
    assert result["rollbacks"] == 0
    assert result["migration_execution"] == 0


def test_cli_is_read_only_and_fails_closed_without_evidence(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = precheck.main([])
    assert exit_code != 0
    output = json.loads(capsys.readouterr().out)
    assert output["ready"] is False
    assert output["mutation_guard"]["writes"] == 0
    assert output["mutation_guard"]["migration_execution"] == 0


def _observe(database_url: str) -> dict:
    conn = _connect(database_url)
    try:
        return precheck.observe_postgres_inventory_activity(conn)
    finally:
        conn.rollback()
        conn.close()


def test_postgres_observer_detects_active_writer_and_drain(
    database_url: str,
    disposable_postgres: dict[str, str],
) -> None:
    writer = _connect(database_url)
    try:
        writer.execute(
            "INSERT INTO public.player_inventory "
            "(user_id, equip_id, obtained_at) VALUES (?, ?, ?)",
            (1, "c038_sword", "fixture"),
        )
        active = _observe(database_url)
        assert disposable_postgres["server_version"].startswith("PostgreSQL 16.14")
        assert active["active_writer_count"] >= 1
        assert active["open_conflicting_transaction_count"] >= 1

        writer.commit()
        deadline = time.monotonic() + 10
        drained = active
        while time.monotonic() < deadline:
            drained = _observe(database_url)
            if all(
                drained[key] == 0
                for key in (
                    "active_writer_count",
                    "open_conflicting_transaction_count",
                    "lock_wait_count",
                    "long_running_transaction_count",
                    "migration_lock_wait_count",
                    "prepared_transaction_count",
                )
            ):
                break
            time.sleep(0.1)
        assert drained["active_writer_count"] == 0
        assert drained["open_conflicting_transaction_count"] == 0
        time.sleep(0.1)
        second_sample = _observe(database_url)
        assert second_sample["active_writer_count"] == 0
        assert second_sample["lock_wait_count"] == 0
        second_sample["observation_samples"] = 2
        states = {
            writer["name"]: precheck.WRITER_STATE_DRAINED
            for writer in precheck.writer_inventory()
        }
        ready = precheck.evaluate_quiescence(
            writer_states=states,
            database_observation=second_sample,
            runtime_b033_compatible=True,
            canonical_shop_gate="OFF",
            canonical_equipment_loadout_gate="OFF",
            schema_state=precheck.EXPECTED_PRE_MIGRATION_SCHEMA,
        )
        assert ready["status"] == precheck.QUIESCENCE_READY
    finally:
        writer.rollback()
        writer.close()


def test_postgres_observer_detects_relation_lock_wait_and_drain(
    database_url: str,
) -> None:
    blocker = _connect(database_url)
    writer_done = threading.Event()
    writer_error: list[Exception] = []

    try:
        blocker.execute(
            "LOCK TABLE public.player_inventory IN ACCESS EXCLUSIVE MODE"
        )

        def write_once() -> None:
            conn = _connect(database_url)
            try:
                conn.execute(
                    "INSERT INTO public.player_inventory "
                    "(user_id, equip_id, obtained_at) VALUES (?, ?, ?)",
                    (2, "c038_armor", "fixture"),
                )
                conn.commit()
            except Exception as error:  # pragma: no cover - diagnostic path
                writer_error.append(error)
                conn.rollback()
            finally:
                conn.close()
                writer_done.set()

        thread = threading.Thread(target=write_once, daemon=True)
        thread.start()
        observed = None
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            observed = _observe(database_url)
            if observed["lock_wait_count"] > 0:
                break
            time.sleep(0.1)
        assert observed is not None
        assert observed["lock_wait_count"] > 0
        assert not writer_done.is_set()

        blocker.rollback()
        assert writer_done.wait(10)
        thread.join(timeout=1)
        assert writer_error == []
    finally:
        blocker.rollback()
        blocker.close()


def test_postgres_observer_detects_b033_advisory_lock_wait(
    database_url: str,
) -> None:
    holder = _connect(database_url)
    waiter_done = threading.Event()
    waiter_error: list[Exception] = []

    try:
        holder.execute("SELECT pg_advisory_xact_lock(?)", (precheck.B033_ADVISORY_LOCK_KEY,))

        def wait_for_lock() -> None:
            conn = _connect(database_url)
            try:
                conn.execute(
                    "SELECT pg_advisory_xact_lock(?)",
                    (precheck.B033_ADVISORY_LOCK_KEY,),
                )
                conn.commit()
            except Exception as error:  # pragma: no cover - diagnostic path
                waiter_error.append(error)
                conn.rollback()
            finally:
                conn.close()
                waiter_done.set()

        thread = threading.Thread(target=wait_for_lock, daemon=True)
        thread.start()
        observed = None
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            observed = _observe(database_url)
            if observed["migration_lock_wait_count"] > 0:
                break
            time.sleep(0.1)
        assert observed is not None
        assert observed["migration_lock_wait_count"] > 0
        assert not waiter_done.is_set()

        holder.rollback()
        assert waiter_done.wait(10)
        thread.join(timeout=1)
        assert waiter_error == []
    finally:
        holder.rollback()
        holder.close()
