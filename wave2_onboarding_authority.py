"""Server-owned durable authority for the Wave 2 first-session journey.

This module is intentionally not a Flask route and does not decide learning,
combat, reward, or progression outcomes. It consumes facts that another
server authority has already committed. Request/browser values are selectors
only; they never become correctness, battle, reward, or XP authority.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Iterator, Mapping

TABLE_NAME = "wave2_onboarding_state_v1"
FIRST_ADVENTURE_ZONE = "k26_30"

NOT_ENROLLED = "NOT_ENROLLED"
NOT_STARTED = "NOT_STARTED"
IN_PROGRESS = "IN_PROGRESS"
SKIPPED = "SKIPPED"
COMPLETED = "COMPLETED"
STATUS_VALUES = (NOT_ENROLLED, NOT_STARTED, IN_PROGRESS, SKIPPED, COMPLETED)

STEP_START = "start"
STEP_FIRST_CONTEXT = "first_context"
STEP_FIRST_QUESTION = "first_question"
STEP_FIRST_REVIEW = "first_review"
STEP_FIRST_COMBAT = "first_combat"
STEP_FIRST_REWARD = "first_reward"
STEP_FIRST_GROWTH = "first_growth"
STEP_NEXT_ACTION = "next_action"
STEP_VALUES = (
    STEP_START,
    STEP_FIRST_CONTEXT,
    STEP_FIRST_QUESTION,
    STEP_FIRST_REVIEW,
    STEP_FIRST_COMBAT,
    STEP_FIRST_REWARD,
    STEP_FIRST_GROWTH,
    STEP_NEXT_ACTION,
)
COMPLETION_FRONTIER = STEP_NEXT_ACTION
_STEP_ORDER = {step: index for index, step in enumerate(STEP_VALUES)}

FACT_FIRST_CONTEXT = "first_context"
FACT_FIRST_QUESTION = "first_question"
FACT_REVIEW_ACCEPTED = "review_accepted"
FACT_COMBAT_RESULT = "combat_result"
FACT_REWARD_GRANTED = "reward_granted"
FACT_GROWTH_COMMITTED = "growth_committed"
FACT_NEXT_ACTION = "next_action"

_FACT_ALIASES = {
    "first_context": FACT_FIRST_CONTEXT,
    "first_context_attempt": FACT_FIRST_CONTEXT,
    "first_context_attempt_issued": FACT_FIRST_CONTEXT,
    "context_attempt_issued": FACT_FIRST_CONTEXT,
    "map_battle_attempt_issued": FACT_FIRST_CONTEXT,
    "adventure_started": FACT_FIRST_CONTEXT,
    "journey_adventure_started": FACT_FIRST_CONTEXT,
    "first_question": FACT_FIRST_QUESTION,
    "first_question_issued": FACT_FIRST_QUESTION,
    "first_question_ready": FACT_FIRST_QUESTION,
    "question_ready": FACT_FIRST_QUESTION,
    "journey_question_ready": FACT_FIRST_QUESTION,
    "review_accepted": FACT_REVIEW_ACCEPTED,
    "accepted_review": FACT_REVIEW_ACCEPTED,
    "review_committed": FACT_REVIEW_ACCEPTED,
    "journey_review_committed": FACT_REVIEW_ACCEPTED,
    "review_result": FACT_REVIEW_ACCEPTED,
    "combat_result": FACT_COMBAT_RESULT,
    "combat_result_committed": FACT_COMBAT_RESULT,
    "combat_settled": FACT_COMBAT_RESULT,
    "battle_result": FACT_COMBAT_RESULT,
    "battle_settled": FACT_COMBAT_RESULT,
    "first_victory": FACT_COMBAT_RESULT,
    "encounter_victory": FACT_COMBAT_RESULT,
    "reward_granted": FACT_REWARD_GRANTED,
    "reward_committed": FACT_REWARD_GRANTED,
    "reward_projection_committed": FACT_REWARD_GRANTED,
    "reward_settled": FACT_REWARD_GRANTED,
    "first_reward": FACT_REWARD_GRANTED,
    "growth_committed": FACT_GROWTH_COMMITTED,
    "growth_projection_committed": FACT_GROWTH_COMMITTED,
    "xp_committed": FACT_GROWTH_COMMITTED,
    "first_growth": FACT_GROWTH_COMMITTED,
    "next_action": FACT_NEXT_ACTION,
    "next_action_ready": FACT_NEXT_ACTION,
}

_PRESENTATION_FACTS = {
    "animation_complete",
    "attack_hit",
    "attack_resolved",
    "board_ready",
    "browser_rendered",
    "growth_feedback",
    "journey_attack_resolved",
    "journey_reward_revealed",
    "opening_ready",
    "presentation_ack",
    "rendered",
    "replay",
    "replay_reward",
    "replay_reward_granted",
    "reward_revealed",
    "review_rejected",
    "rejected_review",
    "zone3_arrival",
    "zone_progressed",
    "zone_progression",
    "unrelated_gameplay",
}

_ATTEMPT_ID_KEYS = (
    "attempt_id",
    "first_context_attempt_id",
    "context_attempt_id",
    "map_battle_attempt_id",
)
_QUESTION_ID_KEYS = ("question_id", "qid", "question")

class OnboardingAuthorityError(RuntimeError):
    """Base class for fail-closed onboarding authority errors."""

class OnboardingStateConflict(OnboardingAuthorityError):
    """A valid mutation could not be applied to the supplied state."""

class OnboardingSchemaError(OnboardingAuthorityError):
    """The explicit onboarding migration has not supplied the required table."""

@dataclass(frozen=True)
class OnboardingState:
    user_id: int
    state_version: int
    status: str
    current_step: str
    first_context_attempt_id: str | None
    updated_at: str

    @classmethod
    def initial(cls, user_id: int, *, updated_at: str = "") -> "OnboardingState":
        return cls(user_id, 0, NOT_ENROLLED, STEP_START, None, updated_at)

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "state_version": self.state_version,
            "status": self.status,
            "current_step": self.current_step,
            "first_context_attempt_id": self.first_context_attempt_id,
            "updated_at": self.updated_at,
        }

@dataclass(frozen=True)
class _Decision:
    changed: bool
    reason: str
    state: OnboardingState
    ok: bool = True
    status_code: int = 200

def _raw_connection(conn: Any) -> Any:
    return getattr(conn, "_conn", conn)


def _is_sqlite(conn: Any) -> bool:
    return _raw_connection(conn).__class__.__module__.startswith("sqlite3")


def _table_prefix(conn: Any) -> str:
    return "" if _is_sqlite(conn) else "public."


def _table_exists(conn: Any, table: str) -> bool:
    if _is_sqlite(conn):
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
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


def _fetchone(
    conn: Any,
    statement: str,
    parameters: tuple[Any, ...] = (),
) -> dict[str, Any] | None:
    cursor = conn.execute(statement, parameters)
    row = cursor.fetchone()
    if row is None:
        return None
    if isinstance(row, Mapping):
        return dict(row)
    keys = getattr(row, "keys", None)
    if callable(keys):
        return {key: row[key] for key in row.keys()}
    description = getattr(cursor, "description", None) or ()
    return {item[0]: row[index] for index, item in enumerate(description)}


def _fetchall(
    conn: Any,
    statement: str,
    parameters: tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    cursor = conn.execute(statement, parameters)
    rows = cursor.fetchall()
    if not rows:
        return []
    if isinstance(rows[0], Mapping):
        return [dict(row) for row in rows]
    keys = getattr(rows[0], "keys", None)
    if callable(keys):
        return [{key: row[key] for key in row.keys()} for row in rows]
    description = getattr(cursor, "description", None) or ()
    names = [item[0] for item in description]
    return [{name: row[index] for index, name in enumerate(names)} for row in rows]


def _validate_user_id(user_id: Any) -> int:
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("authenticated_user_id must be a positive integer")
    return user_id


def _validate_expected_version(expected_state_version: int | None) -> None:
    if expected_state_version is None:
        return
    if (
        isinstance(expected_state_version, bool)
        or not isinstance(expected_state_version, int)
        or expected_state_version < 0
    ):
        raise ValueError("expected_state_version must be a non-negative integer")


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


def _state_from_row(row: Mapping[str, Any]) -> OnboardingState:
    return OnboardingState(
        user_id=int(row["user_id"]),
        state_version=int(row["state_version"]),
        status=str(row["status"]),
        current_step=str(row["current_step"]),
        first_context_attempt_id=row.get("first_context_attempt_id"),
        updated_at=str(row["updated_at"]),
    )


def _select_state(
    conn: Any,
    user_id: int,
    *,
    for_update: bool = False,
) -> OnboardingState | None:
    statement = (
        f"SELECT user_id,state_version,status,current_step,"
        f"first_context_attempt_id,updated_at FROM {_table_prefix(conn)}{TABLE_NAME}"
        " WHERE user_id=?"
    )
    if for_update and not _is_sqlite(conn):
        statement += " FOR UPDATE"
    row = _fetchone(conn, statement, (user_id,))
    return _state_from_row(row) if row is not None else None


def _insert_initial_state(conn: Any, user_id: int) -> None:
    table = f"{_table_prefix(conn)}{TABLE_NAME}"
    timestamp = _timestamp()
    if _is_sqlite(conn):
        conn.execute(
            f"""INSERT OR IGNORE INTO {table}
                (user_id,state_version,status,current_step,
                 first_context_attempt_id,updated_at)
                VALUES (?,0,?,?,NULL,?)""",
            (user_id, NOT_ENROLLED, STEP_START, timestamp),
        )
    else:
        conn.execute(
            f"""INSERT INTO {table}
                (user_id,state_version,status,current_step,
                 first_context_attempt_id,updated_at)
                VALUES (?,0,?,?,NULL,?)
                ON CONFLICT (user_id) DO NOTHING""",
            (user_id, NOT_ENROLLED, STEP_START, timestamp),
        )


def _persist_state(
    conn: Any,
    previous: OnboardingState,
    next_state: OnboardingState,
) -> OnboardingState:
    table = f"{_table_prefix(conn)}{TABLE_NAME}"
    cursor = conn.execute(
        f"""UPDATE {table}
               SET state_version=?,status=?,current_step=?,
                   first_context_attempt_id=?,updated_at=?
             WHERE user_id=? AND state_version=?""",
        (
            next_state.state_version,
            next_state.status,
            next_state.current_step,
            next_state.first_context_attempt_id,
            next_state.updated_at,
            previous.user_id,
            previous.state_version,
        ),
    )
    if getattr(cursor, "rowcount", 1) != 1:
        raise OnboardingStateConflict("state version compare-and-set failed")
    return next_state


def _result(decision: _Decision) -> dict[str, Any]:
    state = decision.state.as_dict()
    return {
        "ok": decision.ok,
        "status_code": decision.status_code,
        "changed": decision.changed,
        "noop": decision.ok and not decision.changed,
        "reason": decision.reason,
        "state": state,
        **state,
    }


def _noop(state: OnboardingState, reason: str = "ALREADY_SATISFIED") -> _Decision:
    return _Decision(False, reason, state)


def _conflict(
    state: OnboardingState,
    reason: str,
    *,
    status_code: int = 409,
) -> _Decision:
    return _Decision(False, reason, state, ok=False, status_code=status_code)


def _advance(
    state: OnboardingState,
    *,
    status: str | None = None,
    current_step: str | None = None,
    first_context_attempt_id: str | None = None,
) -> _Decision:
    return _Decision(
        True,
        "ADVANCED",
        replace(
            state,
            state_version=state.state_version + 1,
            status=status if status is not None else state.status,
            current_step=current_step if current_step is not None else state.current_step,
            first_context_attempt_id=(
                state.first_context_attempt_id
                if first_context_attempt_id is None
                else first_context_attempt_id
            ),
            updated_at=_timestamp(),
        ),
    )


def _mutate(
    conn: Any,
    user_id: int,
    expected_state_version: int | None,
    decide: Callable[[OnboardingState], _Decision],
    *,
    create_if_missing: bool,
) -> dict[str, Any]:
    user_id = _validate_user_id(user_id)
    _validate_expected_version(expected_state_version)
    with _write_transaction(conn):
        state = _select_state(conn, user_id, for_update=True)
        if state is None and create_if_missing:
            _insert_initial_state(conn, user_id)
            state = _select_state(conn, user_id, for_update=True)
        if state is None:
            return _result(_conflict(OnboardingState.initial(user_id), "STATE_NOT_FOUND"))
        decision = decide(state)
        # Semantic satisfaction is checked before CAS, so response-loss
        # retries are NOOP even when the caller still has an old version.
        if not decision.changed and decision.ok:
            return _result(decision)
        if expected_state_version is not None and expected_state_version != state.state_version:
            return _result(_conflict(state, "STALE_STATE_VERSION"))
        if not decision.changed or not decision.ok:
            return _result(decision)
        persisted = _persist_state(conn, state, decision.state)
        return _result(_Decision(True, decision.reason, persisted))


def get_state(conn: Any, authenticated_user_id: int) -> OnboardingState | None:
    """Read state without inserting a NOT_ENROLLED row."""

    user_id = _validate_user_id(authenticated_user_id)
    return _select_state(conn, user_id)


load_state = get_state


def start(
    conn: Any,
    authenticated_user_id: int,
    expected_state_version: int | None = None,
) -> dict[str, Any]:
    def decide(state: OnboardingState) -> _Decision:
        if state.status != NOT_ENROLLED:
            return _noop(state, "START_ALREADY_SATISFIED")
        return _advance(state, status=NOT_STARTED, current_step=STEP_FIRST_CONTEXT)

    return _mutate(conn, authenticated_user_id, expected_state_version, decide, create_if_missing=True)


def skip(
    conn: Any,
    authenticated_user_id: int,
    expected_state_version: int | None = None,
) -> dict[str, Any]:
    def decide(state: OnboardingState) -> _Decision:
        if state.status in (SKIPPED, COMPLETED):
            return _noop(state, "SKIP_ALREADY_SATISFIED")
        return _advance(state, status=SKIPPED)

    return _mutate(conn, authenticated_user_id, expected_state_version, decide, create_if_missing=True)


def resume(
    conn: Any,
    authenticated_user_id: int,
    expected_state_version: int | None = None,
) -> dict[str, Any]:
    def decide(state: OnboardingState) -> _Decision:
        if state.status in (IN_PROGRESS, COMPLETED):
            return _noop(state, "RESUME_ALREADY_SATISFIED")
        if state.status in (SKIPPED, NOT_STARTED):
            step = STEP_FIRST_CONTEXT if state.current_step == STEP_START else state.current_step
            return _advance(state, status=IN_PROGRESS, current_step=step)
        if state.status == NOT_ENROLLED:
            return _advance(state, status=NOT_STARTED, current_step=STEP_FIRST_CONTEXT)
        return _conflict(state, "RESUME_INVALID_STATE")

    return _mutate(conn, authenticated_user_id, expected_state_version, decide, create_if_missing=True)


def finish(
    conn: Any,
    authenticated_user_id: int,
    expected_state_version: int | None = None,
) -> dict[str, Any]:
    def decide(state: OnboardingState) -> _Decision:
        if state.status == COMPLETED:
            return _noop(state, "FINISH_ALREADY_SATISFIED")
        if state.status == SKIPPED:
            return _conflict(state, "SKIPPED_STATE_REQUIRES_RESUME")
        if state.status != IN_PROGRESS or state.current_step != COMPLETION_FRONTIER:
            return _conflict(state, "COMPLETION_FRONTIER_NOT_REACHED")
        if state.first_context_attempt_id is None:
            return _conflict(state, "FIRST_CONTEXT_NOT_BOUND")
        return _advance(state, status=COMPLETED, current_step=COMPLETION_FRONTIER)

    return _mutate(conn, authenticated_user_id, expected_state_version, decide, create_if_missing=False)


def replay(
    conn: Any,
    authenticated_user_id: int,
    expected_state_version: int | None = None,
) -> dict[str, Any]:
    """Return a projection only; replay never creates or updates state."""

    user_id = _validate_user_id(authenticated_user_id)
    _validate_expected_version(expected_state_version)
    state = _select_state(conn, user_id)
    if state is None:
        state = OnboardingState.initial(user_id)
    return _result(_noop(state, "REPLAY_NOOP"))

def _normalise(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower().replace("-", "_").replace(".", "_").replace(":", "_")


def _payload_selector(payload: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _payload_question(payload: Mapping[str, Any]) -> int | None:
    value = _payload_selector(payload, _QUESTION_ID_KEYS)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _payload_user_matches(user_id: int, payload: Mapping[str, Any]) -> bool:
    for key in ("user_id", "player_id", "authenticated_user_id"):
        if key in payload and payload[key] != user_id:
            return False
    return True


def _attempt_row(
    conn: Any,
    user_id: int,
    attempt_id: str,
) -> dict[str, Any] | None:
    """Load an existing server-issued MapBattle attempt and its zone."""

    if not _table_exists(conn, "map_battle_attempts"):
        return None
    columns = _columns(conn, "map_battle_attempts")
    if not {"id", "user_id", "question_id"}.issubset(columns):
        return None
    if "battle_id" in columns and _table_exists(conn, "map_battles"):
        return _fetchone(
            conn,
            """SELECT a.*, b.zone_key AS battle_zone_key,
                      b.state AS battle_state,
                      b.monster_hp AS battle_monster_hp,
                      b.player_hp AS battle_player_hp
                 FROM map_battle_attempts a
                 JOIN map_battles b
                   ON b.id=a.battle_id AND b.user_id=a.user_id
                WHERE a.id=? AND a.user_id=?""",
            (attempt_id, user_id),
        )
    # An adapter test may materialize the already-authoritative zone on the
    # attempt itself. A caller-supplied zone is never accepted as a substitute.
    if "zone_key" not in columns:
        return None
    return _fetchone(
        conn,
        "SELECT * FROM map_battle_attempts WHERE id=? AND user_id=?",
        (attempt_id, user_id),
    )


def _attempt_is_eligible(row: Mapping[str, Any] | None) -> bool:
    if row is None:
        return False
    if str(row.get("battle_zone_key", row.get("zone_key", ""))).strip() != FIRST_ADVENTURE_ZONE:
        return False
    state = str(row.get("state", "") or "").upper()
    if state and state not in {"ISSUED", "RESERVED", "SETTLED"}:
        return False
    battle_state = str(row.get("battle_state", "") or "").upper()
    if battle_state and battle_state not in {"OPEN", "COMPLETED"}:
        return False
    return row.get("question_id") is not None


def _bound_attempt(
    conn: Any,
    state: OnboardingState,
    payload: Mapping[str, Any],
) -> dict[str, Any] | None:
    attempt_id = state.first_context_attempt_id
    if not attempt_id:
        return None
    row = _attempt_row(conn, state.user_id, attempt_id)
    if not _attempt_is_eligible(row):
        return None
    requested = _payload_selector(payload, _ATTEMPT_ID_KEYS)
    if requested is not None and requested != attempt_id:
        return None
    requested_question = _payload_question(payload)
    if requested_question is not None and int(row["question_id"]) != requested_question:
        return None
    return row


def _context_attempt_for_first_fact(
    conn: Any,
    state: OnboardingState,
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    requested = _payload_selector(payload, _ATTEMPT_ID_KEYS)
    if state.first_context_attempt_id is not None:
        if requested is not None and requested != state.first_context_attempt_id:
            return None, "FIRST_CONTEXT_ATTEMPT_IMMUTABLE"
        row = _attempt_row(conn, state.user_id, state.first_context_attempt_id)
        return (
            (row, None)
            if _attempt_is_eligible(row)
            else (None, "FIRST_CONTEXT_ATTEMPT_NOT_FOUND")
        )
    if requested is None:
        return None, "FIRST_CONTEXT_ATTEMPT_REQUIRED"
    row = _attempt_row(conn, state.user_id, requested)
    if not _attempt_is_eligible(row):
        return None, "FIRST_CONTEXT_REQUIRES_ZONE1_MAP_BATTLE_ATTEMPT"
    requested_question = _payload_question(payload)
    if requested_question is not None and int(row["question_id"]) != requested_question:
        return None, "QUESTION_IDENTITY_MISMATCH"
    return row, None


def _row_attempt_id(row: Mapping[str, Any]) -> str | None:
    for key in (
        "attempt_id",
        "first_context_attempt_id",
        "context_attempt_id",
        "map_battle_attempt_id",
        "source_attempt_id",
    ):
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _row_question_id(row: Mapping[str, Any]) -> int | None:
    for key in ("question_id", "attempt_question_id", "qid"):
        value = row.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def _truthy(value: Any) -> bool:
    return value is True or value == 1 or str(value).strip().lower() in {
        "1",
        "true",
        "yes",
        "committed",
        "settled",
        "complete",
        "completed",
    }


def _committed_row(row: Mapping[str, Any], *, allow_settled: bool = True) -> bool:
    for key in ("replay", "is_replay", "replayed"):
        if key in row and _truthy(row[key]):
            return False
    for key in ("committed", "is_committed", "persisted", "authoritative"):
        if key in row:
            return _truthy(row[key])
    if allow_settled:
        for key in ("settled", "is_settled"):
            if key in row:
                return _truthy(row[key])
    for key in ("status", "settlement_state", "state"):
        if key in row:
            return str(row[key]).strip().upper() in {
                "COMMITTED",
                "SETTLED",
                "COMPLETED",
                "APPLIED",
                "GRANTED",
            }
    for key in ("committed_at", "settled_at", "applied_at"):
        if key in row:
            return row[key] is not None and str(row[key]).strip() != ""
    return False


def _context_fact_rows(
    conn: Any,
    *,
    user_id: int,
    attempt_id: str,
    question_id: int,
    fact_types: set[str],
) -> list[dict[str, Any]]:
    """Read explicit context-bound facts without creating any evidence."""

    candidates = (
        "wave2_onboarding_server_facts",
        "onboarding_server_facts",
        "onboarding_fact_evidence",
        "onboarding_committed_facts",
        "authoritative_battle_results",
        "map_battle_results",
        "map_battle_settlements",
        "battle_settlements",
        "reward_settlements",
        "reward_events",
        "server_reward_events",
        "growth_settlements",
        "growth_events",
        "server_growth_events",
        "xp_settlements",
        "xp_events",
    )
    rows: list[dict[str, Any]] = []
    table_kinds = {
        "authoritative_battle_results": {
            "combat_result",
            "combat_result_committed",
            "first_victory",
            "encounter_victory",
        },
        "map_battle_results": {
            "combat_result",
            "combat_result_committed",
            "first_victory",
            "encounter_victory",
        },
        "map_battle_settlements": {
            "combat_result",
            "combat_result_committed",
            "first_victory",
            "encounter_victory",
        },
        "battle_settlements": {
            "combat_result",
            "combat_result_committed",
            "first_victory",
            "encounter_victory",
        },
        "reward_settlements": {
            "reward_granted",
            "reward_committed",
            "reward_settled",
        },
        "reward_events": {
            "reward_granted",
            "reward_committed",
            "reward_settled",
        },
        "server_reward_events": {
            "reward_granted",
            "reward_committed",
            "reward_settled",
        },
        "growth_settlements": {
            "growth_committed",
            "growth_projection_committed",
            "xp_committed",
        },
        "growth_events": {
            "growth_committed",
            "growth_projection_committed",
            "xp_committed",
        },
        "server_growth_events": {
            "growth_committed",
            "growth_projection_committed",
            "xp_committed",
        },
        "xp_settlements": {
            "growth_committed",
            "growth_projection_committed",
            "xp_committed",
        },
        "xp_events": {
            "growth_committed",
            "growth_projection_committed",
            "xp_committed",
        },
    }
    for table in candidates:
        if not _table_exists(conn, table):
            continue
        columns = _columns(conn, table)
        if "user_id" not in columns:
            continue
        for row in _fetchall(conn, f"SELECT * FROM {table} WHERE user_id=?", (user_id,)):
            if _row_attempt_id(row) != attempt_id:
                continue
            row_question = _row_question_id(row)
            if row_question is not None and row_question != question_id:
                continue
            raw_kind = row.get(
                "fact_type",
                row.get("event_type", row.get("kind", row.get("type"))),
            )
            if raw_kind is None:
                if not (table_kinds.get(table, set()) & fact_types):
                    continue
            else:
                normalized_kind = _normalise(str(raw_kind))
                canonical_kind = _FACT_ALIASES.get(normalized_kind, normalized_kind)
                if canonical_kind not in fact_types:
                    continue
            if not _committed_row(row):
                continue
            rows.append(row)
    return rows


def _settled_map_battle_submission(
    conn: Any,
    *,
    user_id: int,
    attempt_id: str,
    question_id: int,
) -> dict[str, Any] | None:
    required = ("map_battle_submissions", "map_battle_attempts", "map_battles")
    if not all(_table_exists(conn, table) for table in required):
        return None
    return _fetchone(
        conn,
        """SELECT s.*, a.question_id AS attempt_question_id,
                  a.state AS attempt_state,
                  b.zone_key AS battle_zone_key,
                  b.state AS battle_state,
                  b.monster_hp AS battle_monster_hp,
                  b.player_hp AS battle_player_hp
             FROM map_battle_submissions s
             JOIN map_battle_attempts a
               ON a.id=s.attempt_id AND a.battle_id=s.battle_id
              AND a.user_id=s.user_id
             JOIN map_battles b
               ON b.id=s.battle_id AND b.user_id=s.user_id
            WHERE s.user_id=? AND s.attempt_id=?
              AND a.question_id=?
              AND s.settlement_state='SETTLED'
              AND s.settled_at IS NOT NULL
            ORDER BY s.settled_at DESC
            LIMIT 1""",
        (user_id, attempt_id, question_id),
    )


def _authoritative_review_committed(
    conn: Any,
    *,
    user_id: int,
    attempt_id: str,
    question_id: int,
) -> bool:
    if _context_fact_rows(
        conn,
        user_id=user_id,
        attempt_id=attempt_id,
        question_id=question_id,
        fact_types={"review_committed", "review_accepted", "review_result"},
    ):
        return True
    submission = _settled_map_battle_submission(
        conn, user_id=user_id, attempt_id=attempt_id, question_id=question_id
    )
    if submission is None or not str(submission.get("judge_result") or "").strip():
        # A server-owned review adapter may bind the committed review
        # directly to the MapBattle attempt. It is still accepted only when
        # the adapter explicitly marks the row committed; a public review
        # row without this binding is never sufficient.
        if _table_exists(conn, "review_log") and "attempt_id" in _columns(conn, "review_log"):
            row = _fetchone(
                conn,
                """SELECT * FROM review_log
                    WHERE user_id=? AND question_id=? AND attempt_id=? LIMIT 1""",
                (user_id, question_id, attempt_id),
            )
            return row is not None and _committed_row(row)
        return False
    submission_id = str(submission.get("id") or "").strip()
    if not submission_id or not _table_exists(conn, "review_log"):
        return False
    columns = _columns(conn, "review_log")
    if not {"user_id", "question_id"}.issubset(columns):
        return False
    if "submission_id" in columns and "source_context" in columns:
        row = _fetchone(
            conn,
            """SELECT * FROM review_log
                WHERE user_id=? AND question_id=?
                  AND submission_id=? AND source_context=? LIMIT 1""",
            (user_id, question_id, submission_id, f"mbv1:{submission_id}"),
        )
        return row is not None
    if "attempt_id" in columns:
        row = _fetchone(
            conn,
            """SELECT * FROM review_log
                WHERE user_id=? AND question_id=? AND attempt_id=? LIMIT 1""",
            (user_id, question_id, attempt_id),
        )
        return row is not None and _committed_row(row)
    return False


def _authoritative_battle_victory(
    conn: Any,
    *,
    user_id: int,
    attempt_id: str,
    question_id: int,
) -> bool:
    for row in _context_fact_rows(
        conn,
        user_id=user_id,
        attempt_id=attempt_id,
        question_id=question_id,
        fact_types={
            "combat_result",
            "combat_result_committed",
            "first_victory",
            "encounter_victory",
        },
    ):
        outcome = str(
            row.get("outcome", row.get("result", row.get("battle_result", ""))) or ""
        ).upper()
        if not outcome or outcome in {
            "VICTORY",
            "DEFEATED",
            "MONSTER_DEFEATED",
            "SETTLED",
        }:
            return True
    submission = _settled_map_battle_submission(
        conn, user_id=user_id, attempt_id=attempt_id, question_id=question_id
    )
    if submission is None:
        return False
    return (
        str(submission.get("attempt_state") or "").upper() == "SETTLED"
        and str(submission.get("battle_state") or "").upper() == "COMPLETED"
        and int(submission.get("battle_monster_hp") or 0) == 0
        and int(submission.get("battle_player_hp") or 0) > 0
    )


def _authoritative_context_fact(
    conn: Any,
    *,
    user_id: int,
    attempt_id: str,
    question_id: int,
    fact_types: set[str],
) -> bool:
    return bool(
        _context_fact_rows(
            conn,
            user_id=user_id,
            attempt_id=attempt_id,
            question_id=question_id,
            fact_types=fact_types,
        )
    )

def _context_matches(
    conn: Any,
    state: OnboardingState,
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    attempt_id = state.first_context_attempt_id
    if not attempt_id:
        return None, "FIRST_CONTEXT_NOT_BOUND"
    row = _attempt_row(conn, state.user_id, attempt_id)
    if not _attempt_is_eligible(row):
        return None, "FIRST_CONTEXT_ATTEMPT_NOT_FOUND"
    requested = _payload_selector(payload, _ATTEMPT_ID_KEYS)
    if requested is not None and requested != attempt_id:
        return None, "FACT_CONTEXT_MISMATCH"
    requested_question = _payload_question(payload)
    if requested_question is not None and int(row["question_id"]) != requested_question:
        return None, "QUESTION_IDENTITY_MISMATCH"
    return row, None


def _fact_decision(
    conn: Any,
    state: OnboardingState,
    canonical_fact: str,
    payload: Mapping[str, Any],
) -> _Decision:
    targets = {
        FACT_FIRST_CONTEXT: (STEP_FIRST_CONTEXT, STEP_FIRST_QUESTION),
        FACT_FIRST_QUESTION: (STEP_FIRST_QUESTION, STEP_FIRST_REVIEW),
        FACT_REVIEW_ACCEPTED: (STEP_FIRST_REVIEW, STEP_FIRST_COMBAT),
        FACT_COMBAT_RESULT: (STEP_FIRST_COMBAT, STEP_FIRST_REWARD),
        FACT_REWARD_GRANTED: (STEP_FIRST_REWARD, STEP_FIRST_GROWTH),
        FACT_GROWTH_COMMITTED: (STEP_FIRST_GROWTH, STEP_NEXT_ACTION),
        FACT_NEXT_ACTION: (STEP_NEXT_ACTION, STEP_NEXT_ACTION),
    }
    prerequisite, target = targets[canonical_fact]
    current_order = _STEP_ORDER.get(state.current_step, -1)
    if state.status == COMPLETED or current_order > _STEP_ORDER[prerequisite]:
        return _noop(state, "FACT_ALREADY_SATISFIED")
    if state.status != IN_PROGRESS:
        return _conflict(state, "FACT_REQUIRES_IN_PROGRESS")
    if state.current_step != prerequisite:
        return _conflict(state, "FACT_OUT_OF_ORDER")

    if canonical_fact == FACT_FIRST_CONTEXT:
        row, reason = _context_attempt_for_first_fact(conn, state, payload)
        if row is None:
            return _conflict(state, reason or "FIRST_CONTEXT_NOT_PROVEN")
        return _advance(
            state,
            current_step=target,
            first_context_attempt_id=str(row["id"]),
        )

    row, reason = _context_matches(conn, state, payload)
    if row is None:
        return _conflict(state, reason or "FACT_CONTEXT_MISMATCH")
    attempt_id = str(row["id"])
    question_id = int(row["question_id"])

    if canonical_fact == FACT_FIRST_QUESTION:
        # The persisted attempt is the authority. Browser boardReady is only
        # presentation and is intentionally not required or trusted here.
        return _advance(state, current_step=target)
    if canonical_fact == FACT_REVIEW_ACCEPTED:
        if not _authoritative_review_committed(
            conn,
            user_id=state.user_id,
            attempt_id=attempt_id,
            question_id=question_id,
        ):
            return _noop(state, "COMMITTED_REVIEW_REQUIRED")
    elif canonical_fact == FACT_COMBAT_RESULT:
        if not _authoritative_battle_victory(
            conn,
            user_id=state.user_id,
            attempt_id=attempt_id,
            question_id=question_id,
        ):
            return _noop(state, "COMMITTED_BATTLE_RESULT_REQUIRED")
    elif canonical_fact == FACT_REWARD_GRANTED:
        if not _authoritative_context_fact(
            conn,
            user_id=state.user_id,
            attempt_id=attempt_id,
            question_id=question_id,
            fact_types={"reward_granted", "reward_committed", "reward_settled"},
        ):
            return _noop(state, "SAME_CONTEXT_REWARD_REQUIRED")
    elif canonical_fact == FACT_GROWTH_COMMITTED:
        if not _authoritative_context_fact(
            conn,
            user_id=state.user_id,
            attempt_id=attempt_id,
            question_id=question_id,
            fact_types={
                "growth_committed",
                "growth_projection_committed",
                "xp_committed",
            },
        ):
            return _noop(state, "SAME_CONTEXT_GROWTH_REQUIRED")
    elif canonical_fact == FACT_NEXT_ACTION:
        return _advance(state, status=COMPLETED, current_step=STEP_NEXT_ACTION)
    return _advance(state, current_step=target)


def advance_from_server_fact(
    conn: Any,
    authenticated_user_id: int,
    fact_type: str,
    fact_payload: Mapping[str, Any] | None = None,
    expected_state_version: int | None = None,
) -> dict[str, Any]:
    """Advance only from a persisted, context-bound server fact.

    fact_payload may identify an already committed attempt/question for
    lookup. Its values are never used as correctness, damage, defeat, reward,
    XP, or progression authority.
    """

    if fact_payload is None:
        payload: Mapping[str, Any] = {}
    elif isinstance(fact_payload, Mapping):
        payload = fact_payload
    else:
        raise ValueError("fact_payload must be a mapping")
    raw_fact = _normalise(fact_type)
    canonical_fact = _FACT_ALIASES.get(raw_fact)

    def decide(state: OnboardingState) -> _Decision:
        if not _payload_user_matches(state.user_id, payload):
            return _conflict(state, "FACT_USER_MISMATCH", status_code=403)
        if raw_fact in _PRESENTATION_FACTS or canonical_fact is None:
            return _noop(state, "FACT_PRESENTATION_OR_UNKNOWN_NOOP")
        return _fact_decision(conn, state, canonical_fact, payload)

    return _mutate(
        conn,
        authenticated_user_id,
        expected_state_version,
        decide,
        create_if_missing=False,
    )


__all__ = [
    "COMPLETED",
    "COMPLETION_FRONTIER",
    "FACT_COMBAT_RESULT",
    "FACT_FIRST_CONTEXT",
    "FACT_FIRST_QUESTION",
    "FACT_GROWTH_COMMITTED",
    "FACT_NEXT_ACTION",
    "FACT_REWARD_GRANTED",
    "FACT_REVIEW_ACCEPTED",
    "FIRST_ADVENTURE_ZONE",
    "IN_PROGRESS",
    "NOT_ENROLLED",
    "NOT_STARTED",
    "OnboardingAuthorityError",
    "OnboardingSchemaError",
    "OnboardingState",
    "OnboardingStateConflict",
    "SKIPPED",
    "STEP_FIRST_COMBAT",
    "STEP_FIRST_CONTEXT",
    "STEP_FIRST_GROWTH",
    "STEP_FIRST_QUESTION",
    "STEP_FIRST_REVIEW",
    "STEP_FIRST_REWARD",
    "STEP_NEXT_ACTION",
    "STEP_START",
    "TABLE_NAME",
    "advance_from_server_fact",
    "finish",
    "get_state",
    "load_state",
    "replay",
    "resume",
    "skip",
    "start",
]
