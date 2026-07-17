"""Shadow judging runtime helpers.

Observation only:
- never changes user-visible judgement
- never raises out of public observe helpers
- writes append-only JSONL when enabled
"""
from __future__ import annotations

import datetime
import json
import os
import re
import time
import uuid

from shadow_event_storage import append_event

try:
    from flask import has_request_context, request as _flask_request
except Exception:  # pragma: no cover
    has_request_context = lambda: False  # type: ignore[assignment]
    _flask_request = None


_SCHEMA_VERSION = "shadow-v4"
_DEFAULT_ROUTE = "/api/rating_test/answer"
_DEFAULT_ENTRY_POINT = "rating_test"
_SUPPORTED_ENTRY_POINTS = {
    "rating_test",
    "daily_challenge",
    "friend_challenge",
}
_REQUEST_ID_HEADERS = (
    "X-Request-Id",
    "X-Request-ID",
    "X-Correlation-Id",
    "X-Amzn-Trace-Id",
)
_REVIEW_CLASSES = {
    "legacy_accepts_shadow_rejects",
    "legacy_rejects_shadow_accepts",
    "legacy_accepts_shadow_off_tree",
    "legacy_rejects_shadow_off_tree",
    "shadow_unsupported",
    "shadow_error",
    "legacy_rejects_transform_candidate",
}

_TRUE_FLAG_VALUES = {"1", "true", "yes", "on"}
_FALSE_FLAG_VALUES = {"", "0", "false", "no", "off"}
_CANDIDATE_SOURCES = {"katago_best_move", "accepted_moves"}


def is_enabled() -> bool:
    raw = str(os.environ.get("SHADOW_JUDGING_ENABLED", "0") or "").strip().lower()
    if raw in _TRUE_FLAG_VALUES:
        return True
    if raw in _FALSE_FLAG_VALUES:
        return False
    # Unknown values fail closed.  Shadow observation must be explicitly on.
    return False


def _events_path() -> str:
    return os.environ.get("SHADOW_EVENTS_PATH", "shadow_events.jsonl")


def _request_metadata() -> tuple[str, str]:
    route = _DEFAULT_ROUTE
    request_id = str(uuid.uuid4())

    if not has_request_context():
        return route, request_id

    try:
        route = str(getattr(_flask_request, "path", "") or route)
    except Exception:
        route = _DEFAULT_ROUTE

    try:
        for header_name in _REQUEST_ID_HEADERS:
            header_value = (_flask_request.headers.get(header_name) or "").strip()
            if header_value:
                request_id = header_value[:128]
                break
    except Exception:
        request_id = str(uuid.uuid4())

    return route, request_id


def _sanitize_message(message) -> str:
    text = re.sub(
        r"(?i)\b(token|cookie|authorization|password|secret|session|header)\s*[:=]\s*([^\s,;]+)",
        r"\1=[redacted]",
        str(message or ""),
    )
    text = re.sub(r"(?i)\bBearer\s+[^\s,;]+", "Bearer [redacted]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:240]


def _parser_metadata(shadow: str, reason: str) -> tuple[str, str]:
    if shadow in {"error", "unsupported"} and reason.startswith(
        ("import failed:", "parse failed:", "missing canonical moves")
    ):
        return "failed", reason
    return "ok", ""


def _classify(legacy: str, shadow: str) -> str:
    if legacy == "unknown":
        return "legacy_unknown"
    if shadow == "unsupported":
        return "shadow_unsupported"
    if shadow == "error":
        return "shadow_error"
    if shadow == "off_tree":
        return f"legacy_{'accepts' if legacy == 'accept' else 'rejects'}_shadow_off_tree"
    if legacy == shadow:
        return f"agreement_{legacy}"
    return (
        f"legacy_{'accepts' if legacy == 'accept' else 'rejects'}_shadow_"
        f"{'rejects' if shadow == 'reject' else 'accepts'}"
    )


def _node_text(sgf_text: str, start: int) -> tuple[str, int]:
    i = start
    out = []
    bracket_depth = 0
    while i < len(sgf_text):
        ch = sgf_text[i]
        if ch == "[":
            bracket_depth += 1
            out.append(ch)
            i += 1
            continue
        if ch == "]" and bracket_depth:
            bracket_depth -= 1
            out.append(ch)
            i += 1
            continue
        if bracket_depth:
            out.append(ch)
            i += 1
            continue
        if ch in ";()":
            break
        out.append(ch)
        i += 1
    return "".join(out), i


def _extract_props(node_text: str) -> dict[str, list[str]]:
    props: dict[str, list[str]] = {}
    i = 0
    while i < len(node_text):
        if not node_text[i].isalpha():
            i += 1
            continue
        key_start = i
        while i < len(node_text) and node_text[i].isalpha():
            i += 1
        key = node_text[key_start:i]
        values = []
        while i < len(node_text) and node_text[i] == "[":
            i += 1
            buf = []
            while i < len(node_text):
                ch = node_text[i]
                if ch == "\\" and i + 1 < len(node_text):
                    buf.append(node_text[i + 1])
                    i += 2
                    continue
                if ch == "]":
                    i += 1
                    break
                buf.append(ch)
                i += 1
            values.append("".join(buf))
        props[key] = values
    return props


def _parse_first_variation_sgf(sgf_text: str) -> tuple[int, list[dict[str, str]]]:
    if not isinstance(sgf_text, str) or "(;" not in sgf_text:
        raise ValueError("not an sgf")

    size = 19
    moves: list[dict[str, str]] = []
    i = sgf_text.find("(;") + 1

    def parse_sequence(pos: int) -> int:
        nonlocal size
        while pos < len(sgf_text):
            ch = sgf_text[pos]
            if ch == ";":
                node, pos = _node_text(sgf_text, pos + 1)
                props = _extract_props(node)
                if "SZ" in props and props["SZ"]:
                    try:
                        size = int(props["SZ"][0])
                    except Exception:
                        size = 19
                for color in ("B", "W"):
                    if color in props and props[color]:
                        coord = props[color][0]
                        if coord:
                            moves.append({"color": color, "coord": coord})
                        break
                continue
            if ch == "(":
                pos = parse_sequence(pos + 1)
                while pos < len(sgf_text) and sgf_text[pos] == "(":
                    depth = 1
                    pos += 1
                    while pos < len(sgf_text) and depth:
                        if sgf_text[pos] == "(":
                            depth += 1
                        elif sgf_text[pos] == ")":
                            depth -= 1
                        pos += 1
                continue
            if ch == ")":
                return pos + 1
            pos += 1
        return pos

    parse_sequence(i)
    return size, moves


def _normalize_moves(moves) -> list[dict[str, int]]:
    if not isinstance(moves, list):
        return []
    normalized: list[dict[str, int]] = []
    for move in moves:
        if not isinstance(move, dict):
            continue
        try:
            x = int(move.get("x"))
            y = int(move.get("y"))
        except Exception:
            continue
        normalized.append({"x": x, "y": y})
    return normalized


def _canonical_moves(sgf_text, moves, final_correct) -> tuple[list[dict[str, int]], str]:
    """Return only player moves actually supplied by the answer path.

    Earlier Shadow versions synthesized a success or rejection path from the
    SGF and the legacy boolean when a route supplied no moves.  That is useful
    for exercising a parser, but it is not evidence of what the player played.
    V4 therefore fails closed instead of inventing diagnostic input.
    """
    normalized = _normalize_moves(moves)
    if normalized:
        return normalized, ""
    return [], "missing canonical moves"


def _board_size(sgf_text) -> int:
    match = re.search(r"SZ\[(\d+)\]", str(sgf_text or ""))
    try:
        size = int(match.group(1)) if match else 19
    except (TypeError, ValueError):
        return 19
    return size if 2 <= size <= 52 else 19


def _transform_point(x: int, y: int, size: int, transform_idx) -> tuple[int, int]:
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
    try:
        index = int(transform_idx)
    except (TypeError, ValueError):
        index = 0
    if index not in range(len(transforms)):
        index = 0
    return transforms[index](int(x), int(y))


def _gtp_to_xy(gtp, size: int):
    match = re.fullmatch(r"([A-HJ-Z])(\d{1,2})", str(gtp or "").strip().upper())
    if not match:
        return None
    letters = "ABCDEFGHJKLMNOPQRSTUVWXYZ"
    x = letters.find(match.group(1))
    row = int(match.group(2))
    if not (0 <= x < size and 1 <= row <= size):
        return None
    return x, size - row


def _xy_to_gtp(x: int, y: int, size: int):
    letters = "ABCDEFGHJKLMNOPQRSTUVWXYZ"
    if not (0 <= x < min(size, len(letters)) and 0 <= y < size):
        return None
    return f"{letters[x]}{size - y}"


def _player_context(sgf_text, moves):
    normalized = _normalize_moves(moves)
    if not normalized:
        return None, None, None
    size = _board_size(sgf_text)
    first = normalized[0]
    x, y = first["x"], first["y"]
    if not (0 <= x < size and 0 <= y < size):
        return None, None, None

    color = None
    try:
        _parsed_size, tree_moves = _parse_first_variation_sgf(sgf_text)
        if tree_moves and tree_moves[0].get("color") in {"B", "W"}:
            color = tree_moves[0]["color"]
    except Exception:
        color = None

    sgf_coord = chr(ord("a") + x) + chr(ord("a") + y)
    player_move_sgf = f"{color}[{sgf_coord}]" if color else None
    return color, player_move_sgf, _xy_to_gtp(x, y, size)


def _valid_uuid4(value):
    if value in (None, ""):
        return None
    try:
        parsed = uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None
    if parsed.version != 4 or parsed.variant != uuid.RFC_4122:
        return None
    return str(parsed)


def _candidate_diagnostics(
    *,
    sgf_text,
    moves,
    transform_idx,
    accepted_moves,
    katago_best_move,
    legacy,
    shadow,
):
    """Classify read-only candidate evidence without changing Legacy.

    Candidate-only evidence requires one real player move and a functioning
    SGF verdict that did not accept the move.  Engine errors/unsupported
    input cannot prove that a candidate is outside the canonical tree.
    """
    normalized = _normalize_moves(moves)
    if len(normalized) != 1 or shadow not in {"off_tree", "reject"}:
        return False, None, None

    size = _board_size(sgf_text)
    player = (normalized[0]["x"], normalized[0]["y"])
    source = None

    transformed_accepted = set()
    for candidate in _normalize_moves(accepted_moves):
        x, y = candidate["x"], candidate["y"]
        if 0 <= x < size and 0 <= y < size:
            transformed_accepted.add(_transform_point(x, y, size, transform_idx))
    if player in transformed_accepted:
        source = "accepted_moves"
    else:
        katago_xy = _gtp_to_xy(katago_best_move, size)
        if katago_xy is not None:
            transformed_katago = _transform_point(
                katago_xy[0], katago_xy[1], size, transform_idx
            )
            if player == transformed_katago:
                source = "katago_best_move"

    if source not in _CANDIDATE_SOURCES:
        return False, None, None
    if legacy == "accept":
        return True, source, "legacy_accepts_shadow_candidate_match"
    if legacy == "reject":
        return True, source, "legacy_rejects_transform_candidate"
    return False, None, None


def _gf003_related(canonical_puzzle_id, gf003_canonical_puzzle_id) -> bool:
    canonical = _valid_uuid4(canonical_puzzle_id)
    gf003 = _valid_uuid4(gf003_canonical_puzzle_id)
    return bool(canonical and gf003 and canonical == gf003)


def _shadow_verdict(sgf_text, moves):
    """Total-in-behavior only via the caller's own exception handling.

    sgf_engine is the sole correctness authority here. If it cannot be
    imported or raises, this function does not substitute any alternate
    parser or verdict logic — the exception is left to propagate so the
    caller can record an explicit, observable Shadow failure event instead
    of silently returning a normal-looking verdict.
    """
    from sgf_engine.core import autoreply, matcher, tree
    from sgf_engine.core.coord_utils import xy_to_sgf
    from sgf_engine.parser.sgf_parser import parse_sgf

    try:
        root = parse_sgf(sgf_text)
    except Exception as exc:
        return "unsupported", f"parse failed: {type(exc).__name__}"

    cur = root
    if not cur.children:
        return "unsupported", "answer tree has no children"

    player_color = cur.children[0].metadata.get("color", "B")
    normalized = _normalize_moves(moves)
    if not normalized:
        return "reject", "empty move list"

    for idx, mv in enumerate(normalized):
        try:
            coord = xy_to_sgf(int(mv.get("x")), int(mv.get("y")))
        except Exception:
            return "error", f"bad move format at index {idx}"

        try:
            matched = matcher.match_move(cur, coord, None)
        except Exception as exc:
            return "error", f"matcher failed: {type(exc).__name__}"

        if matched is not matcher.BRANCH:
            return "off_tree", f"move {idx} ({coord}) not in tree"

        cur = tree.find_child_by_move(cur, coord)
        if cur is None:
            return "error", f"matched child missing for {coord}"

        res = cur.metadata.get("result")
        if res == "success":
            return "accept", "explicit RESULT success"
        if res == "fail":
            return "reject", "explicit RESULT fail"

        try:
            reply = autoreply.get_auto_reply(cur, player_color)
        except Exception as exc:
            return "error", f"autoreply failed: {type(exc).__name__}"

        if reply is not None:
            nxt = tree.find_child_by_move(cur, reply.coord)
            if nxt is None:
                return "error", f"auto-reply {reply.coord} missing in tree"

            cur = nxt
            res = cur.metadata.get("result")
            if res == "success":
                return "accept", "explicit RESULT success"
            if res == "fail":
                return "reject", "explicit RESULT fail"

        if not cur.children:
            return "accept", "reached leaf (legacy leaf semantics)"

    return "reject", "moves ended before reaching a leaf"


def observe_answer_route(
    *,
    entry_point,
    question_id,
    session_id,
    transform_idx,
    sgf_transformed,
    moves,
    client_correct,
    final_correct,
    katago_best_move,
    accepted_moves=None,
    canonical_puzzle_id=None,
    invalid_identity=None,
    legacy_reason=None,
    gf003_canonical_puzzle_id=None,
) -> None:
    started = time.perf_counter()
    enabled_at_start = is_enabled()
    if not enabled_at_start:
        return
    route, request_id = _request_metadata()
    parser_status = "ok"
    parser_failure_reason = ""
    exception_class = ""
    exception_message = ""
    canonical_moves = []
    shadow = "error"
    reason = "shadow observation failed"
    legacy = (
        "unknown"
        if final_correct is None
        else ("accept" if bool(final_correct) else "reject")
    )
    classification = "shadow_error"
    candidate_only_detected = False
    candidate_source = None

    try:
        if entry_point not in _SUPPORTED_ENTRY_POINTS:
            shadow, reason = "unsupported", f"missing canonical moves: unsupported entry_point {entry_point}"
        else:
            canonical_moves, adapter_reason = _canonical_moves(
                sgf_transformed,
                moves,
                bool(final_correct),
            )
            if not canonical_moves:
                shadow, reason = "unsupported", adapter_reason or "missing canonical moves"
            else:
                shadow, reason = _shadow_verdict(sgf_transformed, canonical_moves)

        classification = _classify(legacy, shadow)
        (
            candidate_only_detected,
            candidate_source,
            candidate_classification,
        ) = _candidate_diagnostics(
            sgf_text=sgf_transformed,
            moves=canonical_moves,
            transform_idx=transform_idx,
            accepted_moves=accepted_moves,
            katago_best_move=katago_best_move,
            legacy=legacy,
            shadow=shadow,
        )
        if candidate_classification:
            classification = candidate_classification
        parser_status, parser_failure_reason = _parser_metadata(shadow, reason)
    except Exception as exc:
        exception_class = type(exc).__name__
        exception_message = _sanitize_message(exc)
        shadow = "error"
        reason = f"sgf_engine unavailable or failed: {exception_class}"
        classification = "shadow_error"
        parser_status, parser_failure_reason = "failed", reason
    finally:
        # A disable that lands while an observation is in flight suppresses
        # the write.  Conversely, an off->on transition cannot emit an event
        # for work that never ran because enabled_at_start was false.
        if not enabled_at_start or not is_enabled():
            return

        latency_ms = max(0, int(round((time.perf_counter() - started) * 1000)))
        validated_canonical_id = _valid_uuid4(canonical_puzzle_id)
        identity_is_invalid = validated_canonical_id is None or bool(invalid_identity)
        canonical_id = None if identity_is_invalid else validated_canonical_id
        player_color, player_move_sgf, player_move_board_coordinate = _player_context(
            sgf_transformed,
            canonical_moves,
        )
        event = {
            "schema_version": _SCHEMA_VERSION,
            "event_id": str(uuid.uuid4()),
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "route": route,
            "request_id": request_id,
            "latency_ms": latency_ms,
            "entry_point": entry_point,
            "legacy_question_id": question_id,
            "canonical_puzzle_id": canonical_id,
            "session_id": session_id,
            "transform_idx": transform_idx,
            "source_judgement": legacy,
            "client_judgement": (
                "unknown"
                if client_correct is None
                else ("accept" if bool(client_correct) else "reject")
            ),
            "shadow_judgement": shadow,
            "shadow_reason": reason,
            "player_color": player_color,
            "player_move_sgf": player_move_sgf,
            "player_move_board_coordinate": player_move_board_coordinate,
            "legacy_reason": _sanitize_message(legacy_reason) or None,
            "candidate_only_detected": candidate_only_detected,
            "candidate_source": candidate_source,
            "gf003_related": _gf003_related(
                canonical_id,
                gf003_canonical_puzzle_id,
            ),
            "invalid_identity": identity_is_invalid,
            "legacy_unknown": legacy == "unknown",
            "parser_status": parser_status,
            "parser_failure_reason": parser_failure_reason,
            "exception_class": exception_class,
            "exception_message": exception_message,
            "classification": classification,
            "review_recommended": classification in _REVIEW_CLASSES,
            "owner_decision_required": classification == "legacy_rejects_shadow_accepts",
            "moves_count": len(canonical_moves),
            "katago_best_move": katago_best_move or "",
            "katago_best_move_present": bool(katago_best_move),
            "user_facing_judgement_changed": False,
        }
        try:
            append_event(event, path=_events_path())
        except Exception:
            return


def observe_rating_test(
    *,
    question_id,
    session_id,
    transform_idx,
    sgf_transformed,
    moves,
    client_correct,
    final_correct,
    katago_best_move,
    accepted_moves=None,
    canonical_puzzle_id=None,
    invalid_identity=None,
    legacy_reason=None,
    gf003_canonical_puzzle_id=None,
) -> None:
    observe_answer_route(
        entry_point=_DEFAULT_ENTRY_POINT,
        question_id=question_id,
        session_id=session_id,
        transform_idx=transform_idx,
        sgf_transformed=sgf_transformed,
        moves=moves,
        client_correct=client_correct,
        final_correct=final_correct,
        katago_best_move=katago_best_move,
        accepted_moves=accepted_moves,
        canonical_puzzle_id=canonical_puzzle_id,
        invalid_identity=invalid_identity,
        legacy_reason=legacy_reason,
        gf003_canonical_puzzle_id=gf003_canonical_puzzle_id,
    )


def _selftest() -> int:
    import tempfile

    checks = []
    sgf = "(;SZ[19];B[qd](;W[od];B[oc]))"

    v, _ = _shadow_verdict(sgf, [{"x": 16, "y": 3}, {"x": 14, "y": 2}])
    checks.append(("verdict accept", v == "accept"))

    v, _ = _shadow_verdict(sgf, [{"x": 0, "y": 0}])
    checks.append(("verdict off_tree", v == "off_tree"))

    v, _ = _shadow_verdict("not an sgf", [{"x": 0, "y": 0}])
    checks.append(("verdict unsupported", v == "unsupported"))

    kwargs = dict(
        question_id=12345,
        session_id="selftest",
        transform_idx=0,
        sgf_transformed=sgf,
        moves=[{"x": 16, "y": 3}, {"x": 14, "y": 2}],
        client_correct=True,
        final_correct=True,
        katago_best_move="Q16",
    )

    old_enabled = os.environ.get("SHADOW_JUDGING_ENABLED")
    old_path = os.environ.get("SHADOW_EVENTS_PATH")
    try:
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "events.jsonl")
            os.environ["SHADOW_EVENTS_PATH"] = path

            os.environ["SHADOW_JUDGING_ENABLED"] = "0"
            observe_answer_route(entry_point="rating_test", **kwargs)
            checks.append(("flag off writes nothing", not os.path.exists(path)))

            os.environ["SHADOW_JUDGING_ENABLED"] = "1"
            observe_answer_route(entry_point="rating_test", **kwargs)
            with open(path, encoding="utf-8") as handle:
                event = json.loads(handle.read().splitlines()[0])

            required = {
                "schema_version",
                "event_id",
                "created_at",
                "route",
                "request_id",
                "latency_ms",
                "entry_point",
                "legacy_question_id",
                "classification",
                "shadow_judgement",
                "parser_status",
                "parser_failure_reason",
                "exception_class",
                "exception_message",
                "katago_best_move",
                "player_color",
                "player_move_sgf",
                "player_move_board_coordinate",
                "legacy_reason",
                "candidate_only_detected",
                "candidate_source",
                "gf003_related",
                "invalid_identity",
                "legacy_unknown",
                "user_facing_judgement_changed",
            }
            checks.append(("event has required fields", required <= set(event)))
            checks.append(("schema version bumped", event["schema_version"] == "shadow-v4"))
            checks.append(("classification agreement", event["classification"] == "agreement_accept"))
            checks.append(("never changes judgement", event["user_facing_judgement_changed"] is False))

            observe_answer_route(
                entry_point="daily_challenge",
                question_id=77,
                session_id="daily:test",
                transform_idx=0,
                sgf_transformed=sgf,
                moves=None,
                client_correct=True,
                final_correct=True,
                katago_best_move="",
            )
            with open(path, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
            daily_event = json.loads(lines[-1])
            checks.append(("daily route does not invent moves", daily_event["moves_count"] == 0))
            checks.append(("daily missing input is explicit", daily_event["parser_failure_reason"] == "missing canonical moves"))
    finally:
        if old_enabled is None:
            os.environ.pop("SHADOW_JUDGING_ENABLED", None)
        else:
            os.environ["SHADOW_JUDGING_ENABLED"] = old_enabled
        if old_path is None:
            os.environ.pop("SHADOW_EVENTS_PATH", None)
        else:
            os.environ["SHADOW_EVENTS_PATH"] = old_path

    failed = [name for name, ok in checks if not ok]
    if failed:
        print("SELFTEST FAILED: " + ", ".join(failed))
        return 1
    print(f"SELFTEST OK ({len(checks)}/{len(checks)})")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
