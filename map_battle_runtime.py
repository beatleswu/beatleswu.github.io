"""Universal server-authoritative Map Battle v1 runtime.

The persistence module owns the additive tables and transaction primitives.  This
module owns the protocol boundary: request canonicalisation, the versioned judge
adapter, server-side damage selection, feature eligibility, and the response
shape.  It deliberately has no Flask or application import so the same service
can be exercised by Legacy Adventure and E10 World Map adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import re
import secrets
from typing import Any, Callable, Mapping

from map_battle_persistence import (
    MAP_BATTLE_JUDGE_VERSION,
    SubmissionConflict,
    StaleBattleRevision,
    get_map_battle_v1_mode,
    hash_submission_nonce,
    issue_map_battle_attempt,
    load_authoritative_battle_state,
    lookup_attempt_for_owner,
    reserve_submission_nonce,
    settle_map_battle_submission,
)


RUNTIME_SERVICE_ID = "map-battle-v1-runtime"
OLD_CLIENT_HTTP_STATUS = 426
OLD_CLIENT_ERROR = "upgrade_required"
FEATURE_DISABLED_HTTP_STATUS = 503

_FORBIDDEN_CLIENT_FIELDS = frozenset({
    "grade",
    "correct",
    "correctness",
    "authoritative_grade",
    "damage_to_monster",
    "damage_to_player",
    "monster_hp",
    "player_hp",
    "judge_result",
    "reward",
    "zone_clear",
    "submission_id",
    "submission_nonce_hash",
    "issued_at",
    "received_at",
    "settled_at",
    "settlement_state",
    "state",
})
_REQUIRED_REQUEST_FIELDS = (
    "battle_id",
    "attempt_id",
    "submission_nonce",
    "battle_revision",
    "question_revision",
    "player_color",
    "transform_id",
    "transform_version",
    "moves",
)
_TRANSFORM_RE = re.compile(r"^(?:transform[-_:]?|t)?([0-7])$", re.IGNORECASE)
_SGF_COORD_RE = re.compile(r"^[a-s]{2}$")


class MapBattleRuntimeError(RuntimeError):
    """Expected protocol/runtime failure safe to expose as a stable code."""

    code = "map_battle_runtime_error"
    status = 400
    retryable = False

    def __init__(self, message: str | None = None, *, status: int | None = None):
        super().__init__(message or self.code)
        if status is not None:
            self.status = status


class RequestRejected(MapBattleRuntimeError):
    code = "invalid_map_battle_request"


class ForbiddenClientAuthority(RequestRejected):
    code = "client_authority_field_forbidden"


class FeatureDisabled(MapBattleRuntimeError):
    code = "map_battle_v1_disabled"
    status = FEATURE_DISABLED_HTTP_STATUS


class ModeNotEligible(MapBattleRuntimeError):
    code = "map_battle_mode_not_eligible"
    status = 403


class JudgeUnavailable(MapBattleRuntimeError):
    code = "map_battle_judge_unavailable"
    status = 503
    retryable = True


class AttemptExpired(RequestRejected):
    code = "map_battle_attempt_expired"
    status = 409


class SubmissionNonceNotIssued(RequestRejected):
    code = "submission_nonce_not_issued"
    status = 409


class SubmissionNonceAlreadyIssued(RequestRejected):
    code = "submission_nonce_already_issued"
    status = 409


class SubmissionNonceInvalid(RequestRejected):
    code = "invalid_submission_nonce"
    status = 409


class SubmissionRequestHashMismatch(RequestRejected):
    code = "submission_request_hash_mismatch"
    status = 409


def _is_sqlite_connection(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _row_to_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    keys = getattr(row, "keys", None)
    if callable(keys):
        return {key: row[key] for key in row.keys()}
    return dict(row)


def _column_names(conn: Any, table: str) -> set[str]:
    cursor = conn.execute(f"SELECT * FROM {table} LIMIT 0")
    return {description[0] for description in (cursor.description or ())}


def ensure_submission_lifecycle_schema(conn: Any) -> None:
    """Add only the columns needed for server-issued submission lifecycle.

    Sprint 1 owns the battle/attempt/submission tables.  This additive gate is
    deliberately separate so no existing battle column, state, or constraint is
    rewritten.  Existing rows remain readable; newly issued attempts must carry
    a nonce hash before settlement.
    """

    if not _is_sqlite_connection(conn):
        conn.execute("SELECT pg_advisory_xact_lock(778899789)")
    attempt_columns = _column_names(conn, "map_battle_attempts")
    if "submission_nonce_hash" not in attempt_columns:
        conn.execute(
            "ALTER TABLE map_battle_attempts ADD COLUMN submission_nonce_hash TEXT"
        )
    submission_columns = _column_names(conn, "map_battle_submissions")
    if "issued_at" not in submission_columns:
        conn.execute(
            "ALTER TABLE map_battle_submissions ADD COLUMN issued_at TEXT"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_map_battle_attempts_submission_nonce "
        "ON map_battle_attempts(user_id, battle_id, submission_nonce_hash)"
    )


def _timestamp_text(value: Any = None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


@dataclass(frozen=True)
class CanonicalAnswer:
    """Deterministic answer representation used for judging and hashing."""

    payload: dict[str, Any]
    result: str | None = None
    reason_code: str = "canonicalized"

    @property
    def is_invalid(self) -> bool:
        return self.result == "INVALID"


@dataclass(frozen=True)
class JudgeOutcome:
    result: str
    authoritative_grade: int | None
    judge_version: str
    reason_code: str


def _require_text(value: Any, name: str, maximum: int = 255) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise RequestRejected(f"{name} must be a non-empty string")
    return value.strip()


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RequestRejected(f"{name} must be a non-negative integer")
    return value


def normalize_player_color(value: Any) -> str:
    raw = _require_text(value, "player_color", 16).upper()
    if raw in ("B", "BLACK"):
        return "B"
    if raw in ("W", "WHITE"):
        return "W"
    raise RequestRejected("player_color must be black/B or white/W")


def question_revision_for(question: Mapping[str, Any]) -> str:
    """Return the immutable revision used when an attempt is issued."""

    for key in ("question_revision", "content_revision", "content_sha256"):
        value = question.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    content = question.get("content")
    if not isinstance(content, str) or not content:
        raise JudgeUnavailable("authoritative question content is unavailable")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _transform_index(transform_id: str) -> int:
    raw = transform_id.strip().lower()
    if raw in {"identity", "none", "original"}:
        return 0
    match = _TRANSFORM_RE.fullmatch(raw)
    if match:
        return int(match.group(1))
    raise JudgeUnavailable("authoritative transform identity is unsupported")


def _transform_point(x: int, y: int, size: int, transform_index: int) -> tuple[int, int]:
    n = size - 1
    transforms = (
        lambda c, r: (c, r),
        lambda c, r: (n - r, c),
        lambda c, r: (n - c, n - r),
        lambda c, r: (r, n - c),
        lambda c, r: (n - c, r),
        lambda c, r: (c, n - r),
        lambda c, r: (r, c),
        lambda c, r: (n - r, n - c),
    )
    return transforms[transform_index](x, y)


def _transform_sgf(content: str, transform_index: int) -> str:
    """Apply the existing runtime's deterministic board transform to SGF."""

    if transform_index == 0:
        return content
    size_match = re.search(r"SZ\[(\d+)\]", content)
    size = int(size_match.group(1)) if size_match else 19
    if size <= 1 or size > 25:
        raise JudgeUnavailable("authoritative board size is unsupported")

    def replace_property(match: re.Match[str]) -> str:
        prop = match.group(1)
        block = match.group(2)

        def replace_coord(coord_match: re.Match[str]) -> str:
            coord = coord_match.group(1)
            if coord == "tt":
                return "[tt]"
            x, y = ord(coord[0]) - 97, ord(coord[1]) - 97
            if not (0 <= x < size and 0 <= y < size):
                return f"[{coord}]"
            nx, ny = _transform_point(x, y, size, transform_index)
            return f"[{chr(nx + 97)}{chr(ny + 97)}]"

        return prop + re.sub(r"\[([a-s]{2}|tt)\]", replace_coord, block)

    return re.sub(
        r"(;?\s*(?:AB|AW|B|W))((?:\s*\[[a-s]{2}\]|\[tt\])+)",
        replace_property,
        content,
    )


def _coordinate_to_sgf(x: int, y: int) -> str:
    if not (0 <= x <= 18 and 0 <= y <= 18):
        raise ValueError("coordinate outside SGF range")
    return chr(97 + x) + chr(97 + y)


def canonicalize_answer(payload: Mapping[str, Any], attempt: Mapping[str, Any]) -> CanonicalAnswer:
    """Canonicalize only the client answer; authority fields are never accepted."""

    if not isinstance(payload, Mapping):
        raise RequestRejected("request JSON must be an object")
    forbidden = sorted(set(payload).intersection(_FORBIDDEN_CLIENT_FIELDS))
    if forbidden:
        raise ForbiddenClientAuthority("forbidden client authority field: " + forbidden[0])
    for field in _REQUIRED_REQUEST_FIELDS:
        if field not in payload:
            raise RequestRejected(f"missing request field: {field}")

    player_color = normalize_player_color(payload["player_color"])
    if player_color != str(attempt.get("player_color") or "").upper():
        raise RequestRejected("player_color does not match the issued attempt")
    board_size = attempt.get("board_size")
    if isinstance(board_size, bool) or not isinstance(board_size, int) or not (2 <= board_size <= 25):
        raise RequestRejected("issued attempt has an invalid board size")

    moves = payload["moves"]
    if not isinstance(moves, list) or len(moves) > 256:
        raise RequestRejected("moves must be a bounded list")
    canonical_moves: list[dict[str, Any]] = []
    seen_coordinates: set[tuple[int, int]] = set()
    invalid_reason: str | None = None
    for raw_move in moves:
        if not isinstance(raw_move, Mapping):
            invalid_reason = "malformed_move"
            break
        action = str(raw_move.get("action") or raw_move.get("type") or "play").strip().lower()
        if action in {"pass", "resign"}:
            if set(raw_move).intersection({"x", "y", "coord"}):
                invalid_reason = "malformed_special_move"
                break
            canonical_moves.append({"action": action, "color": player_color})
            if action == "pass" and not bool(attempt.get("pass_allowed")):
                invalid_reason = "pass_not_allowed"
            continue
        if action not in {"play", "move"}:
            invalid_reason = "malformed_move_action"
            break
        if "color" in raw_move and normalize_player_color(raw_move["color"]) != player_color:
            invalid_reason = "move_color_mismatch"
            break
        x, y = raw_move.get("x"), raw_move.get("y")
        if (x is None or y is None) and isinstance(raw_move.get("coord"), str):
            coord = raw_move["coord"].lower()
            if _SGF_COORD_RE.fullmatch(coord):
                x, y = ord(coord[0]) - 97, ord(coord[1]) - 97
        if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, int) or not isinstance(y, int):
            invalid_reason = "malformed_coordinate"
            break
        if not (0 <= x < board_size and 0 <= y < board_size):
            invalid_reason = "coordinate_out_of_bounds"
            break
        if (x, y) in seen_coordinates:
            invalid_reason = "duplicate_move"
            break
        seen_coordinates.add((x, y))
        canonical_moves.append({"action": "play", "color": player_color, "x": x, "y": y})

    if not canonical_moves and invalid_reason is None:
        invalid_reason = "empty_sequence"
    canonical = {
        "battle_id": _require_text(payload["battle_id"], "battle_id"),
        "attempt_id": _require_text(payload["attempt_id"], "attempt_id"),
        "question_revision": _require_text(payload["question_revision"], "question_revision"),
        "player_color": player_color,
        "transform_id": _require_text(payload["transform_id"], "transform_id"),
        "transform_version": _require_text(payload["transform_version"], "transform_version"),
        "battle_revision": _nonnegative_int(payload["battle_revision"], "battle_revision"),
        "moves": canonical_moves,
    }
    return CanonicalAnswer(
        payload=canonical,
        result="INVALID" if invalid_reason else None,
        reason_code=invalid_reason or "canonicalized",
    )


def request_hash_for(canonical: CanonicalAnswer) -> str:
    # The battle revision is optimistic-concurrency metadata, not answer
    # identity.  A transport retry may carry the authoritative revision that
    # was returned by the prior response; that must still identify the same
    # submission and replay its settled result.
    request_payload = dict(canonical.payload)
    request_payload.pop("battle_revision", None)
    serialized = json.dumps(request_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _question_answer_tree(content: str):
    """Use the repository's canonical SGF parser for the authoritative tree."""

    try:
        from sgf_engine.parser.sgf_parser import parse_sgf

        return parse_sgf(content, strict=True)
    except Exception as error:  # no client fallback when canonical judging fails
        raise JudgeUnavailable("canonical question content cannot be judged") from error


def _find_child(node: Any, color: str, coord: str):
    for child in getattr(node, "children", ()):
        move = getattr(child, "move", None)
        if move is not None and move.color == color and move.coord == coord:
            return child
    return None


def _auto_reply(node: Any, player_color: str):
    children = list(getattr(node, "children", ()) or ())
    if len(children) != 1:
        return node
    candidate = getattr(children[0], "move", None)
    if candidate is None:
        return node
    opponent = "W" if player_color == "B" else "B"
    return children[0] if candidate.color == opponent else node


def _first_move_children(root: Any):
    return [child for child in getattr(root, "children", ()) if getattr(child, "move", None) is not None]


def _accepted_moves(question: Mapping[str, Any], *, size: int, transform_index: int) -> set[tuple[int, int]]:
    values = question.get("accepted_moves") or question.get("accepted_answers") or []
    if isinstance(values, Mapping):
        values = [values]
    result: set[tuple[int, int]] = set()
    for value in values if isinstance(values, list) else []:
        if not isinstance(value, Mapping):
            continue
        try:
            x, y = int(value.get("x")), int(value.get("y"))
        except (TypeError, ValueError):
            continue
        if 0 <= x < size and 0 <= y < size:
            result.add(_transform_point(x, y, size, transform_index))
    return result


def _gtp_to_xy(value: Any, size: int) -> tuple[int, int] | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"([A-HJ-T])(\d{1,2})", value.strip().upper())
    if not match:
        return None
    x = "ABCDEFGHJKLMNOPQRST".find(match.group(1))
    row = int(match.group(2))
    if x < 0 or not (1 <= row <= size):
        return None
    return x, size - row


def judge_map_battle_answer_v1(
    question: Mapping[str, Any],
    attempt: Mapping[str, Any],
    canonical: CanonicalAnswer,
) -> JudgeOutcome:
    """Versioned server-only judge over the existing SGF judging primitives."""

    if canonical.is_invalid:
        return JudgeOutcome("INVALID", None, MAP_BATTLE_JUDGE_VERSION, canonical.reason_code)
    moves = canonical.payload["moves"]
    if moves and moves[0]["action"] == "resign":
        return JudgeOutcome("INCORRECT", 0, MAP_BATTLE_JUDGE_VERSION, "resign")
    if any(move["action"] != "play" for move in moves):
        return JudgeOutcome("INVALID", None, MAP_BATTLE_JUDGE_VERSION, "special_move_not_judged")

    content = question.get("content")
    if not isinstance(content, str) or not content.strip():
        raise JudgeUnavailable("authoritative question content is unavailable")
    size = int(attempt["board_size"])
    transform_index = _transform_index(str(attempt["transform_id"]))
    transformed = _transform_sgf(content, transform_index)
    tree_root = _question_answer_tree(transformed)
    move_pairs = [(move["x"], move["y"]) for move in moves]

    accepted = _accepted_moves(question, size=size, transform_index=transform_index)
    if len(move_pairs) == 1 and move_pairs[0] in accepted:
        return JudgeOutcome("CORRECT", 5, MAP_BATTLE_JUDGE_VERSION, "accepted_authoritative_alternative")

    current = tree_root
    player_color = canonical.payload["player_color"]
    for x, y in move_pairs:
        coord = _coordinate_to_sgf(x, y)
        child = _find_child(current, player_color, coord)
        if child is None:
            return JudgeOutcome("INCORRECT", 0, MAP_BATTLE_JUDGE_VERSION, "off_answer_tree")
        current = child
        if not getattr(current, "children", None):
            return JudgeOutcome("CORRECT", 5, MAP_BATTLE_JUDGE_VERSION, "answer_tree_leaf")
        current = _auto_reply(current, player_color)
        if not getattr(current, "children", None):
            return JudgeOutcome("CORRECT", 5, MAP_BATTLE_JUDGE_VERSION, "answer_tree_reply_leaf")
    return JudgeOutcome("INCORRECT", 0, MAP_BATTLE_JUDGE_VERSION, "partial_answer_sequence")


def calculate_damage(result: str, authoritative_grade: int | None, monster_hp_max: int, question: Mapping[str, Any] | None = None) -> tuple[int, int]:
    """Return existing game-balance damage as (monster_damage, player_damage)."""

    if result == "INVALID":
        return 0, 0
    if result == "CORRECT":
        grade = authoritative_grade or 0
        if grade < 3:
            return 0, 0
        percentage = {3: 0.04, 4: 0.06, 5: 0.08}.get(grade, 0.04)
        # This is the existing Legacy _calc_damage formula, shared by both
        # paths so Map Battle does not introduce a second balance calculation.
        import math

        return max(5, math.ceil(monster_hp_max * percentage)), 0
    if result == "INCORRECT":
        monster_attack = 8
        if question is not None:
            try:
                monster_attack = max(0, int(question.get("monster_atk", 8)))
            except (TypeError, ValueError):
                monster_attack = 8
        return 0, max(1, round(monster_attack))
    raise RequestRejected("unknown judge result")


def mode_eligible(mode: str, user_id: int, eligibility: Mapping[str, Any] | None = None) -> bool:
    """Resolve non-off modes without changing Production configuration."""

    eligibility = eligibility or {}
    if mode == "global":
        return True
    if mode == "admin":
        return bool(eligibility.get("admin"))
    if mode == "allowlist":
        return user_id in set(eligibility.get("allowlist") or ())
    if mode == "percentage":
        try:
            percentage = max(0, min(100, int(eligibility.get("percentage", 0))))
        except (TypeError, ValueError):
            percentage = 0
        bucket = int(hashlib.sha256(f"map-battle-v1:{user_id}".encode()).hexdigest()[:8], 16) % 100
        return bucket < percentage
    return False


def _metadata_matches(
    payload: Mapping[str, Any],
    attempt: Mapping[str, Any],
    *,
    check_battle_revision: bool = True,
) -> None:
    if str(payload["battle_id"]) != str(attempt.get("battle_id")):
        raise RequestRejected("battle_id does not match the issued attempt")
    if str(payload["attempt_id"]) != str(attempt.get("id")):
        raise RequestRejected("attempt_id does not match the issued attempt")
    if str(payload["question_revision"]) != str(attempt.get("question_revision")):
        raise RequestRejected("question_revision does not match the issued attempt")
    if str(payload["transform_id"]) != str(attempt.get("transform_id")):
        raise RequestRejected("transform_id does not match the issued attempt")
    if str(payload["transform_version"]) != str(attempt.get("transform_version")):
        raise RequestRejected("transform_version does not match the issued attempt")
    if check_battle_revision and _nonnegative_int(payload["battle_revision"], "battle_revision") != int(attempt.get("battle_revision_at_issue", 0)):
        # The authoritative current revision is checked again by the settlement
        # primitive under a row lock.  New submissions reject stale issued
        # metadata before reservation; an existing settled submission is
        # replayed before this check.
        raise StaleBattleRevision("battle revision is stale for this attempt")
    if str(attempt.get("judge_version")) != MAP_BATTLE_JUDGE_VERSION:
        raise JudgeUnavailable("attempt judge version is unsupported")


def _attempt_expired(attempt: Mapping[str, Any], now: Any = None) -> bool:
    """Reject open attempts after their server-issued expiry boundary."""

    if str(attempt.get("state") or "") not in ("ISSUED", "RESERVED"):
        return str(attempt.get("state") or "") == "EXPIRED"
    try:
        expires_at = datetime.fromisoformat(str(attempt["expires_at"]).replace("Z", "+00:00"))
        current = now if isinstance(now, datetime) else datetime.fromisoformat(
            str(now).replace("Z", "+00:00")
        ) if now is not None else datetime.now(timezone.utc)
    except (KeyError, TypeError, ValueError) as error:
        raise RequestRejected("attempt expiry metadata is invalid", status=409) from error
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current >= expires_at


def _response_from_settlement(
    result: Mapping[str, Any],
    *,
    duplicate: bool,
    outcome: JudgeOutcome | None = None,
    attempt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    submission = dict(result.get("submission") or {})
    battle = dict(result.get("battle") or {})
    result_name = submission.get("judge_result") or (outcome.result if outcome else "INVALID")
    issued_at = submission.get("issued_at") or (attempt or {}).get("issued_at")
    return {
        "accepted": result_name in ("CORRECT", "INCORRECT"),
        "duplicate": bool(duplicate),
        "submission_id": submission.get("id"),
        "submission_state": submission.get("settlement_state"),
        "submission_issued_at": issued_at,
        "submission_received_at": submission.get("received_at"),
        "submission_settled_at": submission.get("settled_at"),
        "request_hash": submission.get("request_hash"),
        "result": result_name,
        "authoritative_grade": submission.get("authoritative_grade"),
        "damage_to_monster": int(submission.get("damage_to_monster") or 0),
        "damage_to_player": int(submission.get("damage_to_player") or 0),
        "monster_hp_before": submission.get("monster_hp_before", battle.get("monster_hp")),
        "monster_hp_after": submission.get("monster_hp_after", battle.get("monster_hp")),
        "player_hp_before": submission.get("player_hp_before", battle.get("player_hp")),
        "player_hp_after": submission.get("player_hp_after", battle.get("player_hp")),
        "monster_defeated": int(battle.get("monster_hp") or 0) == 0,
        "player_defeated": int(battle.get("player_hp") or 0) == 0,
        "battle_revision": int(battle.get("battle_revision") or 0),
        "attempt_state": "settled" if submission.get("settlement_state") == "SETTLED" else "rejected",
        "next_action": (
            "monster_defeated" if int(battle.get("monster_hp") or 0) == 0 else
            "player_defeated" if int(battle.get("player_hp") or 0) == 0 else
            "continue"
        ),
        "judge_version": submission.get("judge_version") or MAP_BATTLE_JUDGE_VERSION,
        "runtime_service": RUNTIME_SERVICE_ID,
    }


def issue_attempt_for_context(
    conn,
    *,
    user_id: int,
    battle_id: str,
    question: Mapping[str, Any],
    initial_position_identity: str,
    board_size: int,
    player_color: str,
    transform_version: str,
    transform_id: str,
    attempt_id: str | None = None,
    issued_at: Any = None,
    expires_at: Any = None,
) -> str:
    """Shared Legacy/E10 attempt issuance contract; no public route is added."""

    revision = question_revision_for(question)
    battle = load_authoritative_battle_state(conn, user_id=user_id, battle_id=battle_id)
    if battle is None:
        raise RequestRejected("battle does not exist for owner", status=404)
    return issue_map_battle_attempt(
        conn,
        user_id=user_id,
        battle_id=battle_id,
        question_id=int(question["id"]),
        question_revision=revision,
        initial_position_identity=initial_position_identity,
        board_size=board_size,
        player_color=normalize_player_color(player_color),
        transform_version=_require_text(transform_version, "transform_version"),
        transform_id=_require_text(transform_id, "transform_id"),
        battle_revision_at_issue=int(battle["battle_revision"]),
        attempt_id=attempt_id,
        judge_version=MAP_BATTLE_JUDGE_VERSION,
        issued_at=issued_at,
        expires_at=expires_at,
    )


def _load_attempt_for_update(conn: Any, *, user_id: int, attempt_id: str) -> dict[str, Any] | None:
    statement = "SELECT * FROM map_battle_attempts WHERE id=? AND user_id=?"
    if not _is_sqlite_connection(conn):
        statement += " FOR UPDATE"
    return _row_to_dict(conn.execute(statement, (attempt_id, user_id)).fetchone())


def issue_submission_nonce_for_attempt(
    conn: Any,
    *,
    user_id: int,
    attempt_id: str,
    now: Any = None,
    mode_environ: Mapping[str, Any] | None = None,
    eligibility: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Issue one server nonce and return its raw value exactly once.

    The raw nonce never enters a SQL statement, response replay, log, or
    evidence path.  Only its SHA-256 hash is stored on the owner-scoped attempt.
    The attempt's issued/expiry timestamps bind the nonce lifetime.
    """

    user_id = int(user_id)
    mode = get_map_battle_v1_mode(mode_environ)
    if mode == "off" or mode == "dark":
        raise FeatureDisabled()
    if not mode_eligible(mode, user_id, eligibility):
        raise ModeNotEligible()
    attempt_id = _require_text(attempt_id, "attempt_id")
    attempt = _load_attempt_for_update(conn, user_id=user_id, attempt_id=attempt_id)
    if attempt is None:
        raise RequestRejected("attempt does not exist for owner", status=404)
    battle = load_authoritative_battle_state(
        conn, user_id=user_id, battle_id=str(attempt["battle_id"])
    )
    if battle is None:
        raise RequestRejected("battle does not exist for owner", status=404)
    if attempt.get("submission_nonce_hash"):
        raise SubmissionNonceAlreadyIssued("submission nonce was already issued")
    if str(attempt.get("state") or "") != "ISSUED":
        raise RequestRejected("attempt is not issuable", status=409)
    if _attempt_expired(attempt, now):
        raise AttemptExpired("map battle attempt has expired")

    raw_nonce = secrets.token_urlsafe(32)
    nonce_hash = hash_submission_nonce(raw_nonce)
    timestamp = _timestamp_text(now)
    cursor = conn.execute(
        """UPDATE map_battle_attempts
           SET submission_nonce_hash=?, updated_at=?
         WHERE id=? AND user_id=? AND battle_id=? AND state='ISSUED'
           AND submission_nonce_hash IS NULL""",
        (nonce_hash, timestamp, attempt_id, user_id, str(attempt["battle_id"])),
    )
    if cursor.rowcount != 1:
        raise SubmissionNonceAlreadyIssued("submission nonce was already issued")
    return {
        "attempt_id": attempt_id,
        "battle_id": str(attempt["battle_id"]),
        "issued_at": attempt["issued_at"],
        "expires_at": attempt["expires_at"],
        "submission_nonce": raw_nonce,
        "runtime_service": RUNTIME_SERVICE_ID,
    }


def issue_attempt_with_submission_nonce(
    conn: Any,
    *,
    user_id: int,
    battle_id: str,
    question: Mapping[str, Any],
    initial_position_identity: str,
    board_size: int,
    player_color: str,
    transform_version: str,
    transform_id: str,
    attempt_id: str | None = None,
    issued_at: Any = None,
    expires_at: Any = None,
    now: Any = None,
    mode_environ: Mapping[str, Any] | None = None,
    eligibility: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an attempt and issue its one-time submission nonce atomically."""

    mode = get_map_battle_v1_mode(mode_environ)
    if mode == "off" or mode == "dark":
        raise FeatureDisabled()
    if not mode_eligible(mode, int(user_id), eligibility):
        raise ModeNotEligible()
    created_attempt_id = issue_attempt_for_context(
        conn,
        user_id=user_id,
        battle_id=battle_id,
        question=question,
        initial_position_identity=initial_position_identity,
        board_size=board_size,
        player_color=player_color,
        transform_version=transform_version,
        transform_id=transform_id,
        attempt_id=attempt_id,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    return issue_submission_nonce_for_attempt(
        conn,
        user_id=user_id,
        attempt_id=created_attempt_id,
        now=now or issued_at,
        mode_environ=mode_environ,
        eligibility=eligibility,
    )


def _validate_submission_nonce(payload: Mapping[str, Any], attempt: Mapping[str, Any]) -> None:
    expected_hash = str(attempt.get("submission_nonce_hash") or "")
    if not expected_hash:
        raise SubmissionNonceNotIssued("attempt has no server-issued submission nonce")
    raw_nonce = payload.get("submission_nonce")
    if not isinstance(raw_nonce, str) or not raw_nonce.strip():
        raise SubmissionNonceInvalid("submission nonce is required")
    actual_hash = hash_submission_nonce(raw_nonce)
    if not hmac.compare_digest(actual_hash, expected_hash):
        raise SubmissionNonceInvalid("submission nonce is invalid")


def _validated_request_hash(payload: Mapping[str, Any], canonical: CanonicalAnswer) -> str:
    expected_hash = request_hash_for(canonical)
    claimed_hash = payload.get("request_hash")
    if claimed_hash is None:
        return expected_hash
    if not isinstance(claimed_hash, str) or not claimed_hash.strip():
        raise SubmissionRequestHashMismatch("request hash is invalid")
    if not hmac.compare_digest(claimed_hash.strip(), expected_hash):
        raise SubmissionRequestHashMismatch("request hash does not match canonical answer")
    return expected_hash


def _existing_submission_for_nonce(
    conn: Any,
    *,
    user_id: int,
    battle_id: str,
    attempt_id: str,
    submission_nonce: str,
) -> dict[str, Any] | None:
    """Read an owner-scoped submission before applying optimistic CAS."""

    row = conn.execute(
        """SELECT * FROM map_battle_submissions
           WHERE user_id=? AND battle_id=? AND attempt_id=?
             AND submission_nonce_hash=?""",
        (
            user_id,
            battle_id,
            attempt_id,
            hash_submission_nonce(submission_nonce),
        ),
    ).fetchone()
    return dict(row) if row is not None else None


def settle_answer(
    conn,
    *,
    user_id: int,
    payload: Mapping[str, Any],
    question_loader: Callable[[int], Mapping[str, Any] | None],
    now: Any = None,
    mode_environ: Mapping[str, Any] | None = None,
    eligibility: Mapping[str, Any] | None = None,
    judge: Callable[[Mapping[str, Any], Mapping[str, Any], CanonicalAnswer], JudgeOutcome] | None = None,
) -> dict[str, Any]:
    """Handle one answer inside the caller's transaction."""

    mode = get_map_battle_v1_mode(mode_environ)
    user_id = int(user_id)
    if mode == "off":
        raise FeatureDisabled()
    if mode == "dark":
        return {
            "accepted": False,
            "duplicate": False,
            "settlement": False,
            "result": "DARK_VALIDATION_ONLY",
            "reason_code": "dark_mode_no_settlement",
            "runtime_service": RUNTIME_SERVICE_ID,
        }
    if not mode_eligible(mode, user_id, eligibility):
        raise ModeNotEligible()
    if not isinstance(payload, Mapping):
        raise RequestRejected("request JSON must be an object")
    attempt_id = payload.get("attempt_id")
    if not isinstance(attempt_id, str) or not attempt_id.strip():
        raise RequestRejected("attempt_id is required")
    attempt = lookup_attempt_for_owner(conn, user_id=user_id, attempt_id=attempt_id.strip())
    if attempt is None:
        raise RequestRejected("attempt does not exist for owner", status=404)
    if _attempt_expired(attempt, now):
        raise AttemptExpired("map battle attempt has expired")
    canonical = canonicalize_answer(payload, attempt)
    _validate_submission_nonce(payload, attempt)
    # Validate owner/battle/attempt identity and the issued attempt metadata
    # before looking up a submission, but defer the optimistic-concurrency
    # check until an existing settled submission has had a chance to replay.
    _metadata_matches(payload, attempt, check_battle_revision=False)
    request_hash = _validated_request_hash(payload, canonical)
    existing = _existing_submission_for_nonce(
        conn,
        user_id=user_id,
        battle_id=str(attempt["battle_id"]),
        attempt_id=str(attempt["id"]),
        submission_nonce=payload["submission_nonce"],
    )
    if existing is not None and existing.get("request_hash") != request_hash:
        raise RequestRejected(
            "same submission nonce was reused for a different request",
            status=409,
        )
    if existing is not None and existing.get("settlement_state") in ("SETTLED", "REJECTED"):
        replay = {
            "submission": existing,
            "battle": load_authoritative_battle_state(
                conn, user_id=user_id, battle_id=str(attempt["battle_id"])
            ),
        }
        return _response_from_settlement(replay, duplicate=True, attempt=attempt)
    if existing is None:
        try:
            _metadata_matches(payload, attempt)
        except StaleBattleRevision as error:
            raise RequestRejected(str(error), status=409) from error
    try:
        reservation = reserve_submission_nonce(
            conn,
            user_id=user_id,
            battle_id=str(attempt["battle_id"]),
            attempt_id=str(attempt["id"]),
            submission_nonce=payload["submission_nonce"],
            request_hash=request_hash,
            canonical_move_json=canonical.payload,
            received_at=now,
        )
    except SubmissionConflict as error:
        raise RequestRejected(str(error), status=409) from error
    if reservation.get("created"):
        conn.execute(
            """UPDATE map_battle_submissions SET issued_at=?
               WHERE id=? AND user_id=? AND battle_id=? AND attempt_id=?""",
            (
                attempt["issued_at"],
                reservation["submission_id"],
                user_id,
                str(attempt["battle_id"]),
                str(attempt["id"]),
            ),
        )
    if reservation.get("duplicate") and reservation.get("record"):
        existing = reservation["record"]
        if existing.get("settlement_state") in ("SETTLED", "REJECTED"):
            replay = {
                "submission": existing,
                "battle": load_authoritative_battle_state(
                    conn, user_id=user_id, battle_id=str(attempt["battle_id"])
                ),
            }
            return _response_from_settlement(replay, duplicate=True, attempt=attempt)
    try:
        _metadata_matches(payload, attempt)
    except StaleBattleRevision as error:
        raise RequestRejected(str(error), status=409) from error
    question = question_loader(int(attempt["question_id"]))
    if not isinstance(question, Mapping):
        raise JudgeUnavailable("authoritative question is unavailable")
    expected_revision = question_revision_for(question)
    if expected_revision != str(attempt["question_revision"]):
        raise RequestRejected("question revision is stale", status=409)
    outcome = (judge or judge_map_battle_answer_v1)(question, attempt, canonical)
    if outcome.judge_version != MAP_BATTLE_JUDGE_VERSION:
        raise JudgeUnavailable("judge adapter version mismatch")
    damage_to_monster, damage_to_player = calculate_damage(
        outcome.result,
        outcome.authoritative_grade,
        int((load_authoritative_battle_state(conn, user_id=user_id, battle_id=str(attempt["battle_id"])) or {}).get("monster_hp_max") or 0),
        question,
    )
    try:
        settled = settle_map_battle_submission(
            conn,
            user_id=user_id,
            battle_id=str(attempt["battle_id"]),
            attempt_id=str(attempt["id"]),
            submission_id=reservation["submission_id"],
            expected_revision=int(payload["battle_revision"]),
            judge_result=outcome.result,
            authoritative_grade=outcome.authoritative_grade,
            damage_to_monster=damage_to_monster,
            damage_to_player=damage_to_player,
            settled_at=now,
        )
    except (StaleBattleRevision, SubmissionConflict) as error:
        raise RequestRejected(str(error), status=409) from error
    return _response_from_settlement(
        settled,
        duplicate=bool(settled.get("duplicate")),
        outcome=outcome,
        attempt=attempt,
    )


__all__ = [
    "CanonicalAnswer",
    "AttemptExpired",
    "FEATURE_DISABLED_HTTP_STATUS",
    "ForbiddenClientAuthority",
    "JudgeOutcome",
    "JudgeUnavailable",
    "MapBattleRuntimeError",
    "ModeNotEligible",
    "OLD_CLIENT_ERROR",
    "OLD_CLIENT_HTTP_STATUS",
    "RUNTIME_SERVICE_ID",
    "RequestRejected",
    "SubmissionNonceAlreadyIssued",
    "SubmissionNonceInvalid",
    "SubmissionNonceNotIssued",
    "SubmissionRequestHashMismatch",
    "canonicalize_answer",
    "calculate_damage",
    "ensure_submission_lifecycle_schema",
    "issue_attempt_for_context",
    "issue_attempt_with_submission_nonce",
    "issue_submission_nonce_for_attempt",
    "judge_map_battle_answer_v1",
    "mode_eligible",
    "question_revision_for",
    "request_hash_for",
    "settle_answer",
]
