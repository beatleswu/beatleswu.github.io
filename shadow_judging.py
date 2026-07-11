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
import threading
import time
import uuid

try:
    from flask import has_request_context, request as _flask_request
except Exception:  # pragma: no cover
    has_request_context = lambda: False  # type: ignore[assignment]
    _flask_request = None


_LOCK = threading.Lock()
_SCHEMA_VERSION = "shadow-v3"
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
}


def is_enabled() -> bool:
    return os.environ.get("SHADOW_JUDGING_ENABLED", "0") == "1"


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


def _sgf_to_xy(coord: str) -> tuple[int, int]:
    if not isinstance(coord, str) or len(coord) != 2:
        raise ValueError("invalid sgf coordinate")
    return ord(coord[0]) - ord("a"), ord(coord[1]) - ord("a")


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


def _extract_player_moves_from_mainline(sgf_text: str) -> list[dict[str, int]]:
    _size, moves = _parse_first_variation_sgf(sgf_text)
    if not moves:
        return []
    player_color = moves[0]["color"]
    player_moves: list[dict[str, int]] = []
    for move in moves:
        if move["color"] != player_color:
            continue
        x, y = _sgf_to_xy(move["coord"])
        player_moves.append({"x": x, "y": y})
    return player_moves


def _derive_rejecting_moves(sgf_text: str) -> list[dict[str, int]]:
    size, moves = _parse_first_variation_sgf(sgf_text)
    expected = _extract_player_moves_from_mainline(sgf_text)
    forbidden = {(mv["x"], mv["y"]) for mv in expected[:1]}
    for y in range(size):
        for x in range(size):
            if (x, y) not in forbidden:
                return [{"x": x, "y": y}]
    return [{"x": 0, "y": 0}]


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
    normalized = _normalize_moves(moves)
    if normalized:
        return normalized, ""
    if not sgf_text:
        return [], "missing canonical moves"
    try:
        if final_correct:
            derived = _extract_player_moves_from_mainline(sgf_text)
        else:
            derived = _derive_rejecting_moves(sgf_text)
        if derived:
            return derived, ""
        return [], "missing canonical moves"
    except Exception as exc:
        return [], f"parse failed: {type(exc).__name__}"


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
) -> None:
    started = time.perf_counter()
    route, request_id = _request_metadata()
    parser_status = "ok"
    parser_failure_reason = ""
    exception_class = ""
    exception_message = ""
    canonical_moves = []
    shadow = "error"
    reason = "shadow observation failed"
    legacy = "reject" if not final_correct else "accept"
    classification = "shadow_error"

    try:
        if not is_enabled():
            return

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
        parser_status, parser_failure_reason = _parser_metadata(shadow, reason)
    except Exception as exc:
        exception_class = type(exc).__name__
        exception_message = _sanitize_message(exc)
        shadow = "error"
        reason = f"sgf_engine unavailable or failed: {exception_class}"
        classification = "shadow_error"
        parser_status, parser_failure_reason = "failed", reason
    finally:
        if not is_enabled():
            return

        latency_ms = max(0, int(round((time.perf_counter() - started) * 1000)))
        event = {
            "schema_version": _SCHEMA_VERSION,
            "event_id": str(uuid.uuid4()),
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "route": route,
            "request_id": request_id,
            "latency_ms": latency_ms,
            "entry_point": entry_point,
            "legacy_question_id": question_id,
            "canonical_puzzle_id": None,
            "session_id": session_id,
            "transform_idx": transform_idx,
            "source_judgement": legacy,
            "client_judgement": "accept" if client_correct else "reject",
            "shadow_judgement": shadow,
            "shadow_reason": reason,
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
            line = json.dumps(event, ensure_ascii=False)
            with _LOCK:
                with open(_events_path(), "a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
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
                "user_facing_judgement_changed",
            }
            checks.append(("event has required fields", required <= set(event)))
            checks.append(("schema version bumped", event["schema_version"] == "shadow-v3"))
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
            checks.append(("daily route no unsupported placeholder", daily_event["parser_failure_reason"] != "route unsupported: daily_challenge"))
            checks.append(("daily route parser ok", daily_event["parser_status"] == "ok"))
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
