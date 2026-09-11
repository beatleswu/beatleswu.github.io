"""Fail-closed transition policy for the retired legacy Newbie Quest.

The Wave 2 authority in :mod:`wave2_onboarding_authority` owns normal V2
progression.  This module owns only the boundary between that authority and
historical ``newbie_quest_state`` rows:

* a legacy stage is never treated as a V2 server-fact frontier;
* an explicit, valid legacy ``graduated=1`` terminal marker may be projected
  to V2 ``COMPLETED`` so a graduated player is never restarted;
* every other historical row remains on a read-only, grandfathered
  compatibility path;
* no legacy task, event, reward, tour, or user row is written here.

The transition functions are deliberately dark by default.  Materializing a
deterministic terminal mapping requires both ``allow_write=True`` and the
separate ``GO_PRODUCTION_DB_MIGRATION`` gate.  A caller still owns the
production decision and surrounding transaction.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator

from wave2_onboarding_authority import (
    COMPLETED,
    NOT_ENROLLED,
    STEP_NEXT_ACTION,
    STEP_START,
    TABLE_NAME as V2_TABLE_NAME,
    get_state,
)


LEGACY_STATE_TABLE = "newbie_quest_state"
LEGACY_TASK_TABLE = "newbie_quest_tasks"
LEGACY_EVENT_TABLE = "newbie_quest_events"
LEGACY_STAGE_VALUES = tuple(range(1, 8))

DETERMINISTIC_V2_MAPPING = "DETERMINISTIC_V2_MAPPING"
NO_SAFE_MAPPING = "NO_SAFE_MAPPING"

LEGACY_GRANDFATHERED = "LEGACY_GRANDFATHERED"
V2_CANONICAL = "V2"
GO_PRODUCTION_DB_MIGRATION = "GO_PRODUCTION_DB_MIGRATION"
LEGACY_COMPATIBILITY_RETIREMENT_CONDITION = (
    "V2_CUTOVER_ENABLED_AND_PRESERVATION_AUDIT_PASSED"
)


class OnboardingTransitionError(RuntimeError):
    """Base class for expected fail-closed transition errors."""


class LegacySchemaUnavailable(OnboardingTransitionError):
    """The legacy source schema is not available for a transition read."""


@dataclass(frozen=True)
class LegacyState:
    """A read-only historical Newbie Quest snapshot for one user."""

    user_id: int
    stage: int | None
    graduated: bool | None
    created_at: str | None = None
    updated_at: str | None = None
    task_keys: tuple[str, ...] = ()
    event_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class LegacyMapping:
    """The deterministic classification of one historical row."""

    user_id: int
    legacy_stage: int | None
    legacy_graduated: bool | None
    classification: str
    target_status: str | None
    target_step: str | None
    compatibility_path: str
    reason: str
    task_keys: tuple[str, ...] = ()
    event_keys: tuple[str, ...] = ()

    @property
    def deterministic(self) -> bool:
        return self.classification == DETERMINISTIC_V2_MAPPING

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "legacy_stage": self.legacy_stage,
            "legacy_graduated": self.legacy_graduated,
            "classification": self.classification,
            "target_status": self.target_status,
            "target_step": self.target_step,
            "compatibility_path": self.compatibility_path,
            "reason": self.reason,
            "task_keys": list(self.task_keys),
            "event_keys": list(self.event_keys),
        }


def _raw_connection(conn: Any) -> Any:
    return getattr(conn, "_conn", conn)


def _is_sqlite(conn: Any) -> bool:
    return _raw_connection(conn).__class__.__module__.lower().startswith("sqlite3")


def _table_prefix(conn: Any) -> str:
    return "" if _is_sqlite(conn) else "public."


def _table_exists(conn: Any, table: str) -> bool:
    if _is_sqlite(conn):
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
    else:
        row = conn.execute(
            """SELECT 1 FROM information_schema.tables
                 WHERE table_schema='public' AND table_name=?""",
            (table,),
        ).fetchone()
    return row is not None


def _columns(conn: Any, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    if _is_sqlite(conn):
        return {
            str(row[1])
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
    rows = conn.execute(
        """SELECT column_name FROM information_schema.columns
             WHERE table_schema='public' AND table_name=?""",
        (table,),
    ).fetchall()
    return {
        str(row[0] if not hasattr(row, "keys") else row["column_name"])
        for row in rows
    }


def _row_dict(cursor: Any, row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    if isinstance(row, Mapping):
        return dict(row)
    keys = getattr(row, "keys", None)
    if callable(keys):
        return {key: row[key] for key in row.keys()}
    description = getattr(cursor, "description", None) or ()
    return {item[0]: row[index] for index, item in enumerate(description)}


def _fetchone(
    conn: Any,
    statement: str,
    parameters: tuple[Any, ...] = (),
) -> dict[str, Any] | None:
    cursor = conn.execute(statement, parameters)
    return _row_dict(cursor, cursor.fetchone())


def _fetchall(
    conn: Any,
    statement: str,
    parameters: tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    cursor = conn.execute(statement, parameters)
    rows = cursor.fetchall()
    return [item for row in rows if (item := _row_dict(cursor, row)) is not None]


def _validate_user_id(user_id: Any) -> int:
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    return user_id


def _coerce_stage(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value in LEGACY_STAGE_VALUES else None
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed in LEGACY_STAGE_VALUES else None
    return None


def _coerce_flag(value: Any) -> bool | None:
    if value is True or value == 1:
        return True
    if value is False or value == 0:
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes"}:
            return True
        if normalized in {"0", "false", "no"}:
            return False
    return None


def _optional_value(row: Mapping[str, Any], name: str) -> str | None:
    value = row.get(name)
    return None if value is None else str(value)


def read_legacy_state(conn: Any, user_id: int) -> LegacyState | None:
    """Read one legacy row and its audit keys without writing anything."""

    user_id = _validate_user_id(user_id)
    if not _table_exists(conn, LEGACY_STATE_TABLE):
        raise LegacySchemaUnavailable(f"{LEGACY_STATE_TABLE} is not present")
    required = {"user_id", "stage", "graduated"}
    missing = sorted(required - _columns(conn, LEGACY_STATE_TABLE))
    if missing:
        raise LegacySchemaUnavailable(
            f"{LEGACY_STATE_TABLE} is missing required columns: {missing}"
        )
    state_columns = _columns(conn, LEGACY_STATE_TABLE)
    selected = ["user_id", "stage", "graduated"]
    selected.extend(name for name in ("created_at", "updated_at") if name in state_columns)
    row = _fetchone(
        conn,
        f"SELECT {','.join(selected)} FROM {LEGACY_STATE_TABLE} WHERE user_id=?",
        (user_id,),
    )
    if row is None:
        return None

    task_keys: tuple[str, ...] = ()
    if _table_exists(conn, LEGACY_TASK_TABLE):
        task_columns = _columns(conn, LEGACY_TASK_TABLE)
        if {"user_id", "task_key"}.issubset(task_columns):
            task_rows = _fetchall(
                conn,
                f"SELECT task_key FROM {LEGACY_TASK_TABLE} WHERE user_id=? "
                "ORDER BY task_key",
                (user_id,),
            )
            task_keys = tuple(sorted(str(item["task_key"]) for item in task_rows))

    event_keys: tuple[str, ...] = ()
    if _table_exists(conn, LEGACY_EVENT_TABLE):
        event_columns = _columns(conn, LEGACY_EVENT_TABLE)
        if {"user_id", "event_key"}.issubset(event_columns):
            event_rows = _fetchall(
                conn,
                f"SELECT event_key FROM {LEGACY_EVENT_TABLE} WHERE user_id=? "
                "ORDER BY event_key",
                (user_id,),
            )
            event_keys = tuple(sorted(str(item["event_key"]) for item in event_rows))

    return LegacyState(
        user_id=user_id,
        stage=_coerce_stage(row.get("stage")),
        graduated=_coerce_flag(row.get("graduated")),
        created_at=_optional_value(row, "created_at"),
        updated_at=_optional_value(row, "updated_at"),
        task_keys=task_keys,
        event_keys=event_keys,
    )


def classify_legacy_state(state: LegacyState) -> LegacyMapping:
    """Classify one row without guessing a V2 step from a legacy stage.

    ``graduated=1`` is the only deterministic terminal signal.  The legacy
    stage/task chain describes Pet, daily, curriculum, Hero, Bot, and Shop
    actions; it does not prove the V2 first-context/question/review/combat/
    reward/growth facts.  Therefore every incomplete stage 1--7 is explicitly
    grandfathered rather than projected to a guessed V2 frontier.
    """

    if state.stage not in LEGACY_STAGE_VALUES or state.graduated is None:
        return LegacyMapping(
            user_id=state.user_id,
            legacy_stage=state.stage,
            legacy_graduated=state.graduated,
            classification=NO_SAFE_MAPPING,
            target_status=None,
            target_step=None,
            compatibility_path=LEGACY_GRANDFATHERED,
            reason="LEGACY_STATE_INVALID_OR_INCOMPLETE_EVIDENCE",
            task_keys=state.task_keys,
            event_keys=state.event_keys,
        )

    if state.graduated:
        return LegacyMapping(
            user_id=state.user_id,
            legacy_stage=state.stage,
            legacy_graduated=True,
            classification=DETERMINISTIC_V2_MAPPING,
            target_status=COMPLETED,
            target_step=STEP_NEXT_ACTION,
            compatibility_path=V2_CANONICAL,
            reason="EXPLICIT_LEGACY_GRADUATED_TERMINAL",
            task_keys=state.task_keys,
            event_keys=state.event_keys,
        )

    return LegacyMapping(
        user_id=state.user_id,
        legacy_stage=state.stage,
        legacy_graduated=False,
        classification=NO_SAFE_MAPPING,
        target_status=None,
        target_step=None,
        compatibility_path=LEGACY_GRANDFATHERED,
        reason="LEGACY_STAGE_IS_NOT_A_V2_SERVER_FACT_FRONTIER",
        task_keys=state.task_keys,
        event_keys=state.event_keys,
    )


def legacy_stage_mapping_table() -> tuple[dict[str, Any], ...]:
    """Return the complete 1--7 mapping matrix used by the audit/handoff."""

    rows: list[dict[str, Any]] = []
    for stage in LEGACY_STAGE_VALUES:
        for graduated in (False, True):
            mapping = classify_legacy_state(
                LegacyState(user_id=1, stage=stage, graduated=graduated)
            )
            rows.append(
                {
                    "legacy_stage": stage,
                    "legacy_graduated": graduated,
                    "classification": mapping.classification,
                    "target_status": mapping.target_status,
                    "target_step": mapping.target_step,
                    "compatibility_path": mapping.compatibility_path,
                    "reason": mapping.reason,
                }
            )
    return tuple(rows)


def _read_all_legacy_states(conn: Any) -> tuple[LegacyState, ...]:
    if not _table_exists(conn, LEGACY_STATE_TABLE):
        return ()
    required = {"user_id", "stage", "graduated"}
    if not required.issubset(_columns(conn, LEGACY_STATE_TABLE)):
        return ()
    rows = _fetchall(
        conn,
        f"SELECT user_id,stage,graduated FROM {LEGACY_STATE_TABLE} ORDER BY user_id",
    )
    states: list[LegacyState] = []
    for row in rows:
        try:
            user_id = int(row["user_id"])
        except (TypeError, ValueError):
            continue
        if user_id <= 0:
            continue
        states.append(
            LegacyState(
                user_id=user_id,
                stage=_coerce_stage(row.get("stage")),
                graduated=_coerce_flag(row.get("graduated")),
            )
        )
    return tuple(states)


def analyze_legacy_users(conn: Any) -> dict[str, Any]:
    """Produce a read-only deterministic mapping report for all legacy rows."""

    source_present = _table_exists(conn, LEGACY_STATE_TABLE)
    states = _read_all_legacy_states(conn)
    mappings = tuple(classify_legacy_state(state) for state in states)
    deterministic = tuple(mapping for mapping in mappings if mapping.deterministic)
    grandfathered = tuple(mapping for mapping in mappings if not mapping.deterministic)
    return {
        "source_table": LEGACY_STATE_TABLE,
        "source_table_present": source_present,
        "legacy_user_count": len(mappings),
        "deterministically_mappable_count": len(deterministic),
        "grandfathered_count": len(grandfathered),
        "deterministic_user_ids": [mapping.user_id for mapping in deterministic],
        "grandfathered_user_ids": [mapping.user_id for mapping in grandfathered],
        "stage_mapping": list(legacy_stage_mapping_table()),
        "mappings": [mapping.as_dict() for mapping in mappings],
    }


def new_entrant_cutover_contract(
    *,
    onboarding_required: Any,
    onboarding_path: Any,
    legacy_state_present: bool = False,
) -> dict[str, Any]:
    """Return the non-mutating entry-path decision for eventual cutover.

    A pending account with no historical legacy row is V2-only.  The legacy
    path is never a candidate for a new entrant.  Existing historical rows are
    handled by :func:`classify_legacy_state` and remain grandfathered when no
    safe mapping exists.
    """

    pending = (
        _coerce_flag(onboarding_required) is True
        and not str(onboarding_path or "").strip()
    )
    if pending and not legacy_state_present:
        return {
            "entry_path": V2_CANONICAL,
            "legacy_allowed": False,
            "new_entrant": True,
            "reason": "NEW_ENTRANT_V2_ONLY",
        }
    if legacy_state_present:
        return {
            "entry_path": LEGACY_GRANDFATHERED,
            "legacy_allowed": True,
            "new_entrant": False,
            "reason": "EXISTING_LEGACY_COMPATIBILITY_ONLY",
        }
    return {
        "entry_path": None,
        "legacy_allowed": False,
        "new_entrant": False,
        "reason": "ONBOARDING_ENTRY_NOT_PENDING",
    }


def legacy_compatibility_retirement_condition(
    *,
    v2_cutover_enabled: bool,
    preservation_audit_passed: bool,
    legacy_state_preserved: bool = True,
) -> dict[str, Any]:
    """Return whether a grandfathered row is eligible for future retirement.

    This policy is intentionally non-mutating.  Compatibility may retire only
    after the V2 cutover is enabled and a preservation audit proves that the
    historical state is retained.  No table or history deletion is authorized
    by this adapter.
    """

    retirable = bool(
        v2_cutover_enabled
        and preservation_audit_passed
        and legacy_state_preserved
    )
    return {
        "retirable": retirable,
        "condition": LEGACY_COMPATIBILITY_RETIREMENT_CONDITION,
        "v2_cutover_enabled": bool(v2_cutover_enabled),
        "preservation_audit_passed": bool(preservation_audit_passed),
        "legacy_state_preserved": bool(legacy_state_preserved),
        "legacy_mutated": False,
        "deletion_authorized": False,
    }


def resolve_onboarding_question_identity(conn: Any, question_id: Any) -> dict[str, Any]:
    """Read the hot Puzzle Identity state for an onboarding question.

    This is a read-only preflight for the App-A/domain adapter.  When the
    identity registry is hot, only an exact active UUID binding is attachable.
    Cold, missing, unavailable, retired, and ambiguous results are returned as
    explicit non-attachable outcomes; no identity is created or guessed.
    """

    legacy_question_id = "" if question_id is None else str(question_id).strip()
    if not legacy_question_id:
        return {
            "status": "INVALID",
            "allowed": False,
            "attachable": False,
            "legacy_question_id": legacy_question_id,
            "reason": "QUESTION_ID_REQUIRED",
        }
    try:
        from identity_read_adapter import BootstrapGatedIdentityReader, IdentityKeyKind

        reader = BootstrapGatedIdentityReader(conn)
        bootstrap = reader.bootstrap_state()
        key = reader.key_for(legacy_question_id)
    except Exception as exc:  # pragma: no cover - defensive fail-closed seam
        return {
            "status": "UNAVAILABLE",
            "allowed": False,
            "attachable": False,
            "legacy_question_id": legacy_question_id,
            "reason": f"IDENTITY_READER_UNAVAILABLE:{type(exc).__name__}",
        }

    hot = bool(bootstrap.get("hot"))
    if hot:
        exact = key.kind == IdentityKeyKind.UUID and bool(key.attachable)
        if exact:
            status = "EXACT"
        elif bool(getattr(key, "retired", False)):
            status = "RETIRED"
        else:
            status = str(key.kind).upper()
        return {
            "status": status,
            "allowed": exact,
            "attachable": bool(key.attachable),
            "hot": True,
            "tables_present": bool(bootstrap.get("tables_present")),
            "legacy_question_id": legacy_question_id,
            "source_record_uuid": key.value if exact else None,
            "reason": key.reason,
            "candidates": list(key.candidates),
        }

    return {
        "status": "COLD" if bootstrap.get("tables_present") else "UNAVAILABLE",
        "allowed": False,
        "attachable": False,
        "hot": False,
        "tables_present": bool(bootstrap.get("tables_present")),
        "legacy_question_id": legacy_question_id,
        "source_record_uuid": None,
        "reason": (
            "IDENTITY_BOOTSTRAP_COLD"
            if bootstrap.get("tables_present")
            else "IDENTITY_TABLES_UNAVAILABLE"
        ),
        "candidates": list(key.candidates),
    }


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _transaction_active(conn: Any) -> bool:
    raw = _raw_connection(conn)
    if _is_sqlite(conn):
        return bool(getattr(raw, "in_transaction", False))
    status = getattr(raw, "status", None)
    return status is not None and status != 1


@contextmanager
def _write_transaction(conn: Any) -> Iterator[None]:
    started = not _transaction_active(conn)
    if started:
        conn.execute("BEGIN IMMEDIATE" if _is_sqlite(conn) else "BEGIN")
    try:
        yield
        if started:
            conn.commit()
    except Exception:
        if started:
            conn.rollback()
        raise


def _materialize_completed_mapping(
    conn: Any,
    mapping: LegacyMapping,
) -> dict[str, Any]:
    """Seed only a deterministic terminal V2 projection.

    This writer never updates legacy tables.  A pristine V2 placeholder may be
    promoted to the terminal state; any V2 progress that is already present is
    preserved rather than overwritten.
    """

    current = get_state(conn, mapping.user_id)
    if current is not None:
        if (
            current.status == NOT_ENROLLED
            and current.current_step == STEP_START
            and current.state_version == 0
            and current.first_context_attempt_id is None
        ):
            cursor = conn.execute(
                f"""UPDATE {_table_prefix(conn)}{V2_TABLE_NAME}
                       SET state_version=1,status=?,current_step=?,
                           first_context_attempt_id=NULL,updated_at=?
                     WHERE user_id=? AND state_version=0""",
                (COMPLETED, STEP_NEXT_ACTION, _timestamp(), mapping.user_id),
            )
            if getattr(cursor, "rowcount", 1) == 1:
                return {
                    "changed": True,
                    "reason": "LEGACY_GRADUATED_MATERIALIZED",
                    "state": get_state(conn, mapping.user_id).as_dict(),
                }
        return {
            "changed": False,
            "reason": "EXISTING_V2_STATE_PRESERVED",
            "state": current.as_dict(),
        }

    table = f"{_table_prefix(conn)}{V2_TABLE_NAME}"
    timestamp = _timestamp()
    if _is_sqlite(conn):
        cursor = conn.execute(
            f"""INSERT OR IGNORE INTO {table}
                (user_id,state_version,status,current_step,
                 first_context_attempt_id,updated_at)
                VALUES (?,1,?,?,NULL,?)""",
            (mapping.user_id, COMPLETED, STEP_NEXT_ACTION, timestamp),
        )
    else:
        cursor = conn.execute(
            f"""INSERT INTO {table}
                (user_id,state_version,status,current_step,
                 first_context_attempt_id,updated_at)
                VALUES (?,1,?,?,NULL,?)
                ON CONFLICT (user_id) DO NOTHING""",
            (mapping.user_id, COMPLETED, STEP_NEXT_ACTION, timestamp),
        )
    state = get_state(conn, mapping.user_id)
    if state is None:
        raise OnboardingTransitionError("terminal V2 mapping was not persisted")
    return {
        "changed": getattr(cursor, "rowcount", 1) == 1,
        "reason": (
            "LEGACY_GRADUATED_MATERIALIZED"
            if getattr(cursor, "rowcount", 1) == 1
            else "LEGACY_GRADUATED_ALREADY_MATERIALIZED"
        ),
        "state": state.as_dict(),
    }


def transition_existing_legacy_user(
    conn: Any,
    user_id: int,
    *,
    dry_run: bool = True,
    allow_write: bool = False,
    owner_gate: str | None = None,
) -> dict[str, Any]:
    """Plan or apply one historical transition; default behavior is read-only."""

    user_id = _validate_user_id(user_id)
    try:
        legacy = read_legacy_state(conn, user_id)
    except LegacySchemaUnavailable as exc:
        return {
            "ok": False,
            "changed": False,
            "status_code": 503,
            "reason": "LEGACY_SOURCE_UNAVAILABLE",
            "detail": str(exc),
        }
    if legacy is None:
        return {
            "ok": True,
            "changed": False,
            "reason": "NO_LEGACY_STATE",
            "entry_path": V2_CANONICAL,
            "legacy_allowed": False,
        }

    mapping = classify_legacy_state(legacy)
    result: dict[str, Any] = {"ok": True, "changed": False, **mapping.as_dict()}
    if not mapping.deterministic:
        result.update(
            {
                "action": "GRANDFATHER_LEGACY",
                "legacy_mutated": False,
                "v2_mutated": False,
            }
        )
        return result

    if not _table_exists(conn, V2_TABLE_NAME):
        return {
            **result,
            "ok": False,
            "status_code": 503,
            "reason": "V2_SCHEMA_REQUIRED",
            "action": "BLOCKED_NO_V2_SCHEMA",
            "legacy_mutated": False,
            "v2_mutated": False,
        }
    if dry_run:
        return {
            **result,
            "action": "PLAN_TERMINAL_V2_MAPPING",
            "planned": True,
            "legacy_mutated": False,
            "v2_mutated": False,
            "required_gate": GO_PRODUCTION_DB_MIGRATION,
        }
    if not allow_write or owner_gate != GO_PRODUCTION_DB_MIGRATION:
        return {
            **result,
            "ok": False,
            "status_code": 403,
            "reason": "GO_PRODUCTION_DB_MIGRATION_REQUIRED",
            "action": "BLOCKED_MIGRATION_GATE",
            "legacy_mutated": False,
            "v2_mutated": False,
        }

    with _write_transaction(conn):
        materialized = _materialize_completed_mapping(conn, mapping)
    return {
        **result,
        **materialized,
        "action": "MATERIALIZE_TERMINAL_V2_MAPPING",
        "legacy_mutated": False,
        "v2_mutated": bool(materialized["changed"]),
    }


def transition_existing_legacy_users(
    conn: Any,
    *,
    dry_run: bool = True,
    allow_write: bool = False,
    owner_gate: str | None = None,
) -> dict[str, Any]:
    """Plan/apply all deterministic terminal mappings as one unit of work."""

    report = analyze_legacy_users(conn)
    if not report["source_table_present"]:
        return {
            **report,
            "ok": False,
            "status_code": 503,
            "reason": "LEGACY_SOURCE_UNAVAILABLE",
            "results": [],
        }
    if not report["deterministic_user_ids"]:
        return {**report, "ok": True, "changed": False, "results": []}

    results: list[dict[str, Any]] = []
    if dry_run:
        for user_id in report["deterministic_user_ids"]:
            results.append(
                transition_existing_legacy_user(
                    conn,
                    user_id,
                    dry_run=True,
                    allow_write=False,
                    owner_gate=owner_gate,
                )
            )
    elif not allow_write or owner_gate != GO_PRODUCTION_DB_MIGRATION:
        for user_id in report["deterministic_user_ids"]:
            results.append(
                transition_existing_legacy_user(
                    conn,
                    user_id,
                    dry_run=False,
                    allow_write=allow_write,
                    owner_gate=owner_gate,
                )
            )
    else:
        with _write_transaction(conn):
            for user_id in report["deterministic_user_ids"]:
                result = transition_existing_legacy_user(
                    conn,
                    user_id,
                    dry_run=False,
                    allow_write=allow_write,
                    owner_gate=owner_gate,
                )
                results.append(result)
                if not result.get("ok"):
                    raise OnboardingTransitionError(result.get("reason", "transition_failed"))

    return {
        **report,
        "ok": all(result.get("ok") for result in results) if results else True,
        "changed": any(result.get("changed") for result in results),
        "results": results,
    }


__all__ = [
    "DETERMINISTIC_V2_MAPPING",
    "GO_PRODUCTION_DB_MIGRATION",
    "LEGACY_COMPATIBILITY_RETIREMENT_CONDITION",
    "LEGACY_EVENT_TABLE",
    "LEGACY_GRANDFATHERED",
    "LEGACY_STAGE_VALUES",
    "LEGACY_STATE_TABLE",
    "LEGACY_TASK_TABLE",
    "LegacyMapping",
    "LegacySchemaUnavailable",
    "LegacyState",
    "NO_SAFE_MAPPING",
    "OnboardingTransitionError",
    "V2_CANONICAL",
    "analyze_legacy_users",
    "classify_legacy_state",
    "legacy_stage_mapping_table",
    "legacy_compatibility_retirement_condition",
    "new_entrant_cutover_contract",
    "read_legacy_state",
    "resolve_onboarding_question_identity",
    "transition_existing_legacy_user",
    "transition_existing_legacy_users",
]
