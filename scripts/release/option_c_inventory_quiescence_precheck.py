"""Read-only precheck for the temporary Option C inventory write drain.

This module is deliberately smaller than a maintenance-mode system.  It does
not stop a process, reject a route, acquire a migration lock, or execute a
migration.  It turns independently collected writer/process and PostgreSQL
observations into a fail-closed decision that can be handed to the accepted
C036 migration runner.

The PostgreSQL observer only issues SELECT statements.  The caller owns the
connection transaction cleanup; this module never commits or rolls back.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "C038_GOVERNED_INVENTORY_WRITE_QUIESCENCE_V1"
PLAYER_INVENTORY_TABLE = "player_inventory"
B033_ADVISORY_LOCK_KEY = 773310034
MIN_STABLE_OBSERVATION_SAMPLES = 2

# This is the only migration sequence accepted by the C035/C036 packet.  The
# C038 helper records the order but never imports or executes either migration.
MIGRATION_SEQUENCE = (
    "migrations/equipment_canonical_slot_v1.py",
    "migrations/coin_purchase_operations_v1.py",
)
C036_RUNNER_PATH = "scripts/release/option_c_production_migration.py"
C036_RUNNER_REFERENCE_HEAD = "aa9924a933ce52a438bd7a301e64059ffecdd473"

QUIESCENCE_READY = "QUIESCENCE_READY"
WRITER_ACTIVE = "WRITER_ACTIVE"
WRITER_STATE_UNKNOWN = "WRITER_STATE_UNKNOWN"
OPEN_CONFLICTING_TRANSACTION = "OPEN_CONFLICTING_TRANSACTION"
RUNTIME_NOT_B033_COMPATIBLE = "RUNTIME_NOT_B033_COMPATIBLE"
FEATURE_GATE_UNEXPECTED = "FEATURE_GATE_UNEXPECTED"
SCHEMA_STATE_UNEXPECTED = "SCHEMA_STATE_UNEXPECTED"

WRITER_STATE_DRAINED = "DRAINED"
WRITER_STATE_ACTIVE = "ACTIVE"
WRITER_STATE_UNKNOWN_VALUE = "UNKNOWN"
WRITER_STATES = frozenset(
    {WRITER_STATE_DRAINED, WRITER_STATE_ACTIVE, WRITER_STATE_UNKNOWN_VALUE}
)

EXPECTED_PRE_MIGRATION_SCHEMA = {
    "canonical_slot": "ABSENT",
    "b033_validity_constraint": "ABSENT",
    "b033_partial_unique_index": "ABSENT",
    "coin_purchase_operations": "ABSENT",
    "domain_event_outbox": "COMPATIBLE",
}


@dataclass(frozen=True)
class InventoryWriterContract:
    """One current source-level writer seam and its governed controls."""

    name: str
    classification: str
    caller: str
    process_or_service: str
    authority: str
    can_run_during_normal_production: bool
    stop_mechanism: str
    drain_signal: str
    resume_mechanism: str


_DRAIN = (
    "external app traffic/process drain at the existing service boundary; "
    "no app-local global freeze exists"
)
_DRAIN_SIGNAL = (
    "operator drain acknowledgement plus PostgreSQL observation with "
    "active_writer_count=0, open_conflicting_transaction_count=0, "
    "lock_wait_count=0, long_running_transaction_count=0, and "
    "migration_lock_wait_count=0"
)
_RESUME = (
    "operator resumes the drained service only after B033/C019/schema/runtime "
    "acceptance; feature gates remain independently OFF"
)


# Current-master source inventory.  This is a source-contract inventory, not a
# catalog and not an execution registry.  It was verified against app.py and
# the route-independent C019/B040/B041 writers for C038.
PLAYER_INVENTORY_WRITERS: tuple[InventoryWriterContract, ...] = (
    InventoryWriterContract(
        name="monster_functional_equipment_acquisition",
        classification="APP_REQUEST_WRITER",
        caller=(
            "app._settle_monster_defeat_in_tx.grant_functional_item -> "
            "grant_equipment_ownership"
        ),
        process_or_service="Flask request worker (battle/review settlement)",
        authority="B040 equipment_ownership_service -> player_inventory",
        can_run_during_normal_production=True,
        stop_mechanism=_DRAIN,
        drain_signal=_DRAIN_SIGNAL,
        resume_mechanism=_RESUME,
    ),
    InventoryWriterContract(
        name="admin_equipment_grant",
        classification="ADMIN_WRITER",
        caller=(
            "app.admin_set_equipment action=grant at "
            "/api/admin/users/<uid>/assets/equipment"
        ),
        process_or_service="Flask request worker (authenticated admin request)",
        authority="B040 equipment_ownership_service -> player_inventory",
        can_run_during_normal_production=True,
        stop_mechanism=_DRAIN,
        drain_signal=_DRAIN_SIGNAL,
        resume_mechanism=_RESUME,
    ),
    InventoryWriterContract(
        name="admin_equipment_remove",
        classification="ADMIN_WRITER",
        caller=(
            "app.admin_set_equipment action=remove at "
            "/api/admin/users/<uid>/assets/equipment"
        ),
        process_or_service="Flask request worker (authenticated admin request)",
        authority="app direct DELETE with user_id ownership predicate",
        can_run_during_normal_production=True,
        stop_mechanism=_DRAIN,
        drain_signal=_DRAIN_SIGNAL,
        resume_mechanism=_RESUME,
    ),
    InventoryWriterContract(
        name="player_equipment_equip_canonical",
        classification="APP_REQUEST_WRITER",
        caller=(
            "app.equip_item action=equip at /api/player/inventory/equip; "
            "canonical loadout gate ON"
        ),
        process_or_service="Flask request worker",
        authority="B041 equipment_loadout_service.equip_owned_item",
        can_run_during_normal_production=False,
        stop_mechanism=_DRAIN,
        drain_signal=_DRAIN_SIGNAL,
        resume_mechanism=_RESUME,
    ),
    InventoryWriterContract(
        name="player_equipment_unequip_canonical",
        classification="APP_REQUEST_WRITER",
        caller=(
            "app.equip_item action=unequip at /api/player/inventory/equip; "
            "canonical loadout gate ON"
        ),
        process_or_service="Flask request worker",
        authority="B041 equipment_loadout_service.unequip_owned_item",
        can_run_during_normal_production=False,
        stop_mechanism=_DRAIN,
        drain_signal=_DRAIN_SIGNAL,
        resume_mechanism=_RESUME,
    ),
    InventoryWriterContract(
        name="player_equipment_equip_legacy",
        classification="LEGACY_WRITER",
        caller=(
            "app.equip_item action=equip at /api/player/inventory/equip; "
            "canonical loadout gate OFF"
        ),
        process_or_service="Flask request worker",
        authority="app direct player_inventory UPDATE",
        can_run_during_normal_production=True,
        stop_mechanism=_DRAIN,
        drain_signal=_DRAIN_SIGNAL,
        resume_mechanism=_RESUME,
    ),
    InventoryWriterContract(
        name="player_equipment_unequip_legacy",
        classification="LEGACY_WRITER",
        caller=(
            "app.equip_item action=unequip at /api/player/inventory/equip; "
            "canonical loadout gate OFF"
        ),
        process_or_service="Flask request worker",
        authority="app direct player_inventory UPDATE",
        can_run_during_normal_production=True,
        stop_mechanism=_DRAIN,
        drain_signal=_DRAIN_SIGNAL,
        resume_mechanism=_RESUME,
    ),
    InventoryWriterContract(
        name="canonical_shop_functional_equipment_acquisition",
        classification="APP_REQUEST_WRITER",
        caller=(
            "app.shop_buy / app.shop_buy_appearance canonical dispatch -> "
            "C025/C029 -> C026 purchase_with_coins"
        ),
        process_or_service="Flask request worker; canonical Shop gate ON",
        authority="C026 SqlAcquisitionAuthority -> player_inventory",
        can_run_during_normal_production=False,
        stop_mechanism=_DRAIN,
        drain_signal=_DRAIN_SIGNAL,
        resume_mechanism=_RESUME,
    ),
)

KNOWN_WRITER_NAMES = frozenset(item.name for item in PLAYER_INVENTORY_WRITERS)

# B033 itself is also a player_inventory mutator because its backfill updates
# existing rows.  It is deliberately kept out of KNOWN_WRITER_NAMES: it is
# the controlled maintenance step that may begin only after the live writer
# set has reached QUIESCENCE_READY.  It has no service-resume lifecycle.
PLAYER_INVENTORY_MAINTENANCE_MUTATORS: tuple[InventoryWriterContract, ...] = (
    InventoryWriterContract(
        name="b033_equipment_canonical_slot_backfill",
        classification="MAINTENANCE_WRITER",
        caller="migrations.equipment_canonical_slot_v1.upgrade",
        process_or_service="C036 Option C release runner",
        authority="B033 canonical_slot backfill and schema enforcement",
        can_run_during_normal_production=False,
        stop_mechanism="not started until live writer quiescence is proven",
        drain_signal="not applicable before the controlled migration phase",
        resume_mechanism="not resumed; rerun only through the governed C036 runner",
    ),
)


class QuiescenceObservationError(RuntimeError):
    """Sanitized error for an unavailable read-only observation."""


def writer_inventory() -> list[dict[str, Any]]:
    """Return the current source-contract writer inventory as plain data."""

    return [asdict(writer) for writer in PLAYER_INVENTORY_WRITERS]


def maintenance_mutator_inventory() -> list[dict[str, Any]]:
    """Return controlled migration mutators separately from live writers."""

    return [asdict(writer) for writer in PLAYER_INVENTORY_MAINTENANCE_MUTATORS]


def _row_value(row: Any, name: str, index: int) -> Any:
    try:
        return row[name]
    except (KeyError, IndexError, TypeError):
        return row[index]


def _select(conn: Any, statement: str, parameters: Sequence[Any] = ()) -> Any:
    """Execute only a SELECT/WITH statement through the repository adapter."""

    first_word = statement.lstrip().split(None, 1)[0].upper()
    if first_word not in {"SELECT", "WITH"}:
        raise QuiescenceObservationError("non_select_observation_rejected")
    return conn.execute(statement, tuple(parameters))


def _nonnegative_count(row: Any, name: str) -> int:
    value = _row_value(row, name, 0)
    if isinstance(value, bool):
        raise QuiescenceObservationError("invalid_observation_count")
    try:
        count = int(value)
    except (TypeError, ValueError) as error:
        raise QuiescenceObservationError("invalid_observation_count") from error
    if count < 0:
        raise QuiescenceObservationError("invalid_observation_count")
    return count


def observe_postgres_inventory_activity(
    conn: Any,
    *,
    long_running_seconds: int = 30,
) -> dict[str, Any]:
    """Observe inventory writers and relevant waits without mutating DB state.

    The caller must provide the repository's PostgreSQL connection adapter,
    which uses ``?`` placeholders.  The function excludes its own backend,
    returns aggregate counts only, and never returns SQL text, PIDs, user IDs,
    or row contents.
    """

    if isinstance(long_running_seconds, bool) or not isinstance(
        long_running_seconds, int
    ) or long_running_seconds <= 0:
        raise ValueError("long_running_seconds must be a positive integer")

    relation = _select(
        conn,
        """SELECT c.oid::bigint AS relation_oid
             FROM pg_class AS c
             JOIN pg_namespace AS n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relname=?""",
        (PLAYER_INVENTORY_TABLE,),
    ).fetchone()
    if relation is None:
        raise QuiescenceObservationError("player_inventory_relation_unavailable")
    relation_oid = _row_value(relation, "relation_oid", 0)

    summary = _select(
        conn,
        r"""WITH inventory_sessions AS (
                SELECT a.pid,
                       a.state,
                       a.xact_start,
                       a.wait_event_type,
                       a.query,
                       COALESCE(
                           BOOL_OR(
                               l.granted AND l.mode IN (
                                   'RowShareLock',
                                   'RowExclusiveLock',
                                   'ShareUpdateExclusiveLock',
                                   'ShareRowExclusiveLock',
                                   'ExclusiveLock',
                                   'AccessExclusiveLock'
                               )
                           ), FALSE
                       ) AS holds_write_lock,
                       COALESCE(BOOL_OR(NOT l.granted), FALSE)
                           AS waits_on_inventory_lock
                  FROM pg_stat_activity AS a
                  LEFT JOIN pg_locks AS l
                    ON l.pid=a.pid AND l.relation=?
                 WHERE a.datname=current_database()
                   AND a.pid <> pg_backend_pid()
                 GROUP BY a.pid, a.state, a.xact_start,
                          a.wait_event_type, a.query
            ), classified AS (
                SELECT *,
                       (
                           holds_write_lock
                           OR query ~* '(insert[[:space:]]+into|update[[:space:]]+|delete[[:space:]]+from|merge[[:space:]]+into|copy[[:space:]]+.*from)[^;]*player_inventory'
                       ) AS writer_touch
                  FROM inventory_sessions
            )
            SELECT COUNT(*) FILTER (
                       WHERE writer_touch AND state <> 'idle'
                   ) AS active_writer_count,
                   COUNT(*) FILTER (
                       WHERE holds_write_lock AND state='idle in transaction'
                   ) AS open_conflicting_transaction_count,
                   COUNT(*) FILTER (
                       WHERE waits_on_inventory_lock
                          OR (wait_event_type='Lock' AND writer_touch)
                   ) AS lock_wait_count,
                   COUNT(*) FILTER (
                       WHERE writer_touch
                         AND xact_start IS NOT NULL
                         AND xact_start < clock_timestamp()
                             - (? * interval '1 second')
                   ) AS long_running_transaction_count
              FROM classified""",
        (relation_oid, long_running_seconds),
    ).fetchone()
    if summary is None:
        raise QuiescenceObservationError("inventory_activity_unavailable")

    migration_lock = _select(
        conn,
        """SELECT COUNT(*) AS migration_lock_wait_count
             FROM pg_locks AS l
             JOIN pg_stat_activity AS a ON a.pid=l.pid
            WHERE a.datname=current_database()
              AND a.pid <> pg_backend_pid()
              AND l.locktype='advisory'
              AND l.objid=?
              AND l.granted=false""",
        (B033_ADVISORY_LOCK_KEY,),
    ).fetchone()
    if migration_lock is None:
        raise QuiescenceObservationError("migration_lock_observation_unavailable")

    prepared = _select(
        conn,
        """SELECT COUNT(*) AS prepared_transaction_count
             FROM pg_prepared_xacts""",
    ).fetchone()
    if prepared is None:
        raise QuiescenceObservationError("prepared_transaction_observation_unavailable")

    return {
        "schema_relation_present": True,
        "active_writer_count": _nonnegative_count(summary, "active_writer_count"),
        "open_conflicting_transaction_count": _nonnegative_count(
            summary, "open_conflicting_transaction_count"
        ),
        "lock_wait_count": _nonnegative_count(summary, "lock_wait_count"),
        "long_running_transaction_count": _nonnegative_count(
            summary, "long_running_transaction_count"
        ),
        "migration_lock_wait_count": _nonnegative_count(
            migration_lock, "migration_lock_wait_count"
        ),
        "prepared_transaction_count": _nonnegative_count(
            prepared, "prepared_transaction_count"
        ),
        "observation_samples": 1,
        "database_queries": 4,
        "writes": 0,
        "commits": 0,
        "rollbacks": 0,
        "migration_execution": 0,
    }


def _normalize_gate(value: Any) -> str:
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    if value is None:
        return "UNKNOWN"
    return str(value).strip().upper() or "UNKNOWN"


def _normalize_writer_states(
    writer_states: Mapping[str, Any] | None,
) -> tuple[dict[str, str], list[str], list[str]]:
    if writer_states is None:
        return {}, sorted(KNOWN_WRITER_NAMES), []
    normalized: dict[str, str] = {}
    invalid: list[str] = []
    for name, value in writer_states.items():
        state = str(value).strip().upper() if value is not None else "UNKNOWN"
        if state not in WRITER_STATES:
            invalid.append(str(name))
            continue
        normalized[str(name)] = state
    missing = sorted(KNOWN_WRITER_NAMES - set(normalized))
    return normalized, missing, sorted(set(invalid))


def _count_value(observation: Mapping[str, Any] | None, key: str) -> int | None:
    if observation is None or key not in observation:
        return None
    value = observation[key]
    if isinstance(value, bool):
        return None
    try:
        count = int(value)
    except (TypeError, ValueError):
        return None
    return count if count >= 0 else None


def evaluate_quiescence(
    *,
    writer_states: Mapping[str, Any] | None,
    database_observation: Mapping[str, Any] | None,
    runtime_b033_compatible: bool | None,
    canonical_shop_gate: Any,
    canonical_equipment_loadout_gate: Any,
    schema_state: Mapping[str, Any] | None,
    target_environment: str = "disposable",
) -> dict[str, Any]:
    """Return a fail-closed quiescence decision from supplied evidence.

    No source, process, route, or database mutation occurs here.  All known
    writers must be explicitly ``DRAINED`` and all database counters must be
    observed as zero.  Missing evidence is never treated as drained.
    """

    states, missing_writers, invalid_writers = _normalize_writer_states(writer_states)
    extra_writers = sorted(set(states) - KNOWN_WRITER_NAMES)
    reasons: list[str] = []
    status = QUIESCENCE_READY

    active_names = sorted(
        name for name, state in states.items() if state == WRITER_STATE_ACTIVE
    )
    unknown_names = sorted(
        name
        for name, state in states.items()
        if state == WRITER_STATE_UNKNOWN_VALUE
    )
    if active_names:
        status = WRITER_ACTIVE
        reasons.append("active_writer_states:" + ",".join(active_names))
    if unknown_names or missing_writers or invalid_writers or extra_writers:
        if status == QUIESCENCE_READY:
            status = WRITER_STATE_UNKNOWN
        if unknown_names:
            reasons.append("unknown_writer_states:" + ",".join(unknown_names))
        if missing_writers:
            reasons.append("missing_writer_states:" + ",".join(missing_writers))
        if invalid_writers:
            reasons.append("invalid_writer_states:" + ",".join(invalid_writers))
        if extra_writers:
            reasons.append("unregistered_writer_states:" + ",".join(extra_writers))

    required_counts = (
        "active_writer_count",
        "open_conflicting_transaction_count",
        "lock_wait_count",
        "long_running_transaction_count",
        "migration_lock_wait_count",
        "prepared_transaction_count",
    )
    counts = {key: _count_value(database_observation, key) for key in required_counts}
    missing_counts = sorted(key for key, value in counts.items() if value is None)
    if missing_counts:
        if status == QUIESCENCE_READY:
            status = WRITER_STATE_UNKNOWN
        reasons.append("missing_database_observations:" + ",".join(missing_counts))
    else:
        assert all(value is not None for value in counts.values())
        if counts["active_writer_count"] > 0 or counts["lock_wait_count"] > 0:
            status = WRITER_ACTIVE
            reasons.append(
                "database_writer_activity:"
                f"active={counts['active_writer_count']},"
                f"lock_wait={counts['lock_wait_count']}"
            )
        if counts["long_running_transaction_count"] > 0:
            status = WRITER_ACTIVE
            reasons.append(
                "long_running_inventory_transaction:"
                f"{counts['long_running_transaction_count']}"
            )
        if (
            counts["open_conflicting_transaction_count"] > 0
            or counts["migration_lock_wait_count"] > 0
            or counts["prepared_transaction_count"] > 0
        ):
            if status == QUIESCENCE_READY:
                status = OPEN_CONFLICTING_TRANSACTION
            reasons.append(
                "open_or_waiting_conflict:"
                f"open={counts['open_conflicting_transaction_count']},"
                f"migration_wait={counts['migration_lock_wait_count']},"
                f"prepared={counts['prepared_transaction_count']}"
            )

    observation_samples = _count_value(database_observation, "observation_samples")
    if observation_samples is None or observation_samples < MIN_STABLE_OBSERVATION_SAMPLES:
        if status == QUIESCENCE_READY:
            status = WRITER_STATE_UNKNOWN
        reasons.append(
            "stable_observation_samples_required:"
            f"{MIN_STABLE_OBSERVATION_SAMPLES}"
        )

    if runtime_b033_compatible is False:
        if status == QUIESCENCE_READY:
            status = RUNTIME_NOT_B033_COMPATIBLE
        reasons.append("runtime_b033_compatible=false")
    elif runtime_b033_compatible is not True:
        if status == QUIESCENCE_READY:
            status = WRITER_STATE_UNKNOWN
        reasons.append("runtime_b033_compatible=unknown")

    shop_gate = _normalize_gate(canonical_shop_gate)
    loadout_gate = _normalize_gate(canonical_equipment_loadout_gate)
    bad_gates = [
        name
        for name, value in (
            ("canonical_shop", shop_gate),
            ("canonical_equipment_loadout", loadout_gate),
        )
        if value != "OFF"
    ]
    if bad_gates:
        if status == QUIESCENCE_READY:
            status = FEATURE_GATE_UNEXPECTED
        reasons.append(
            "feature_gates_not_proven_off:" + ",".join(bad_gates)
        )

    schema = dict(schema_state or {})
    schema_mismatches = sorted(
        key
        for key, expected in EXPECTED_PRE_MIGRATION_SCHEMA.items()
        if schema.get(key) != expected
    )
    if schema_mismatches:
        if status == QUIESCENCE_READY:
            status = SCHEMA_STATE_UNEXPECTED
        reasons.append(
            "unexpected_pre_migration_schema:" + ",".join(schema_mismatches)
        )

    if status == QUIESCENCE_READY:
        reasons = ["all_known_writers_drained_and_database_conflicts_zero"]

    return {
        "schema_version": SCHEMA_VERSION,
        "target_environment": str(target_environment),
        "status": status,
        "ready": status == QUIESCENCE_READY,
        "writers": {
            "known_count": len(PLAYER_INVENTORY_WRITERS),
            "maintenance_mutator_count": len(
                PLAYER_INVENTORY_MAINTENANCE_MUTATORS
            ),
            "states": states,
            "all_known_writers_explicitly_drained": (
                status == QUIESCENCE_READY
                or (
                    not missing_writers
                    and not invalid_writers
                    and not unknown_names
                    and not extra_writers
                    and not active_names
                )
            ),
        },
        "database_observation": dict(database_observation or {}),
        "runtime_b033_compatible": runtime_b033_compatible,
        "feature_gates": {
            "canonical_shop": shop_gate,
            "canonical_equipment_loadout": loadout_gate,
        },
        "schema_state": schema,
        "migration_sequence": list(MIGRATION_SEQUENCE),
        "c036_runner_reference": {
            "path": C036_RUNNER_PATH,
            "accepted_parent_head": C036_RUNNER_REFERENCE_HEAD,
            "invoked_by_c038": False,
        },
        "existing_inventory_mutation_freeze_mechanism": False,
        "reasons": reasons,
        "mutation_guard": {
            "database_queries": int(
                (database_observation or {}).get("database_queries", 0) or 0
            ),
            "writes": 0,
            "commits": 0,
            "rollbacks": 0,
            "migration_execution": 0,
        },
    }


def migration_recovery_plan(
    *,
    b033_status: str,
    c019_status: str | None = None,
    b033_postchecks_passed: bool = False,
    c019_postchecks_passed: bool = False,
) -> dict[str, Any]:
    """Describe the safe next action without executing or retrying anything."""

    b033_status = str(b033_status).strip().upper()
    c019_status = (
        None if c019_status is None else str(c019_status).strip().upper()
    )
    if b033_status != "COMMITTED":
        return {
            "status": b033_status or "B033_MIGRATION_FAIL",
            "action": "ROLLBACK_B033_AND_STOP",
            "safe_schema_state": "LEGACY",
            "safe_runtime_state": "PRE_B033_RUNTIME_ONLY",
            "gates": "OFF",
            "c019_attempted": False,
            "writers_remain_quiesced": True,
            "automatic_retry": False,
        }
    if c019_status != "COMMITTED":
        return {
            "status": "B033_COMMITTED_COIN_PURCHASE_FAILED",
            "action": "ROLLBACK_C019_TRANSACTION_ONLY_AND_STOP",
            "safe_schema_state": "B033_COMMITTED_C019_ABSENT_OR_UNVERIFIED",
            "safe_runtime_state": "B033_COMPATIBLE_RUNTIME_REQUIRED",
            "gates": "OFF",
            "c019_attempted": c019_status is not None,
            "writers_remain_quiesced": True,
            "automatic_retry": False,
        }
    if not b033_postchecks_passed or not c019_postchecks_passed:
        return {
            "status": "POST_MIGRATION_ACCEPTANCE_REQUIRED",
            "action": "STOP_FEATURE_ENABLEMENT_AND_KEEP_WRITERS_QUIESCED",
            "safe_schema_state": "B033_AND_C019_COMMITTED_UNACCEPTED",
            "safe_runtime_state": "B033_COMPATIBLE_RUNTIME_REQUIRED",
            "gates": "OFF",
            "c019_attempted": True,
            "writers_remain_quiesced": True,
            "automatic_retry": False,
        }
    return {
        "status": "FULL_SEQUENCE_ACCEPTED",
        "action": "RESUME_ONLY_COMPATIBLE_WRITERS",
        "safe_schema_state": "B033_AND_C019_COMMITTED_VALIDATED",
        "safe_runtime_state": "B033_COMPATIBLE_RUNTIME_REQUIRED",
        "gates": "OFF",
        "c019_attempted": True,
        "writers_remain_quiesced": False,
        "automatic_retry": False,
    }


def writers_may_resume_after_acceptance(
    *,
    b033_postchecks_passed: bool,
    c019_postchecks_passed: bool,
    runtime_acceptance_passed: bool,
    schema_acceptance_passed: bool,
) -> bool:
    """Return whether writer resumption prerequisites are all proven."""

    return all(
        (
            b033_postchecks_passed,
            c019_postchecks_passed,
            runtime_acceptance_passed,
            schema_acceptance_passed,
        )
    )


def _pairs(values: Sequence[str], *, label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in values:
        if "=" not in raw:
            raise ValueError(f"{label} must use NAME=VALUE")
        name, value = raw.split("=", 1)
        name = name.strip()
        if not name or name in result:
            raise ValueError(f"{label} contains an invalid or duplicate name")
        result[name] = value.strip()
    return result


def _optional_int(value: str | None) -> int | None:
    return None if value is None else int(value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only Option C inventory writer quiescence precheck; "
            "never connects, stops writers, or runs migrations"
        )
    )
    parser.add_argument(
        "--target-environment",
        choices=("disposable", "production", "other"),
        default="disposable",
    )
    parser.add_argument("--writer-state", action="append", default=[], metavar="NAME=STATE")
    parser.add_argument("--active-writer-count")
    parser.add_argument("--open-conflicting-transaction-count")
    parser.add_argument("--lock-wait-count")
    parser.add_argument("--long-running-transaction-count")
    parser.add_argument("--migration-lock-wait-count")
    parser.add_argument("--prepared-transaction-count")
    parser.add_argument("--observation-samples")
    parser.add_argument(
        "--runtime-b033-compatible",
        choices=("yes", "no", "unknown"),
        default="unknown",
    )
    parser.add_argument(
        "--canonical-shop-gate",
        choices=("OFF", "ON", "UNKNOWN"),
        default="UNKNOWN",
    )
    parser.add_argument(
        "--canonical-equipment-loadout-gate",
        choices=("OFF", "ON", "UNKNOWN"),
        default="UNKNOWN",
    )
    parser.add_argument("--schema-state", action="append", default=[], metavar="NAME=STATE")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    writer_states = _pairs(args.writer_state, label="--writer-state")
    schema_state = _pairs(args.schema_state, label="--schema-state")
    database_observation = {
        "active_writer_count": _optional_int(args.active_writer_count),
        "open_conflicting_transaction_count": _optional_int(
            args.open_conflicting_transaction_count
        ),
        "lock_wait_count": _optional_int(args.lock_wait_count),
        "long_running_transaction_count": _optional_int(
            args.long_running_transaction_count
        ),
        "migration_lock_wait_count": _optional_int(args.migration_lock_wait_count),
        "prepared_transaction_count": _optional_int(
            args.prepared_transaction_count
        ),
        "observation_samples": _optional_int(args.observation_samples),
        "database_queries": 0,
        "writes": 0,
        "commits": 0,
        "rollbacks": 0,
        "migration_execution": 0,
    }
    runtime_value: bool | None = {
        "yes": True,
        "no": False,
        "unknown": None,
    }[args.runtime_b033_compatible]
    result = evaluate_quiescence(
        writer_states=writer_states,
        database_observation=database_observation,
        runtime_b033_compatible=runtime_value,
        canonical_shop_gate=args.canonical_shop_gate,
        canonical_equipment_loadout_gate=args.canonical_equipment_loadout_gate,
        schema_state=schema_state,
        target_environment=args.target_environment,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "B033_ADVISORY_LOCK_KEY",
    "MIN_STABLE_OBSERVATION_SAMPLES",
    "C036_RUNNER_PATH",
    "EXPECTED_PRE_MIGRATION_SCHEMA",
    "MIGRATION_SEQUENCE",
    "OPEN_CONFLICTING_TRANSACTION",
    "PLAYER_INVENTORY_WRITERS",
    "PLAYER_INVENTORY_MAINTENANCE_MUTATORS",
    "QUIESCENCE_READY",
    "RUNTIME_NOT_B033_COMPATIBLE",
    "SCHEMA_STATE_UNEXPECTED",
    "FEATURE_GATE_UNEXPECTED",
    "WRITER_ACTIVE",
    "WRITER_STATE_UNKNOWN",
    "QuiescenceObservationError",
    "evaluate_quiescence",
    "main",
    "migration_recovery_plan",
    "observe_postgres_inventory_activity",
    "writer_inventory",
    "maintenance_mutator_inventory",
    "writers_may_resume_after_acceptance",
]
