"""Phase 22: sgf_engine shadow judging (observation only).

Contract (Phase 19 / ADR 20):
- Legacy judgement stays authoritative; this module never changes it.
- observe_answer_route() and observe_rating_test() are total functions: they
  never raise.
- No DB access. Events go to a local JSONL file and are safe to drop.
- Enabled only when SHADOW_JUDGING_ENABLED=1 (default off).
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
except Exception:  # pragma: no cover - Flask import is always available in app
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
    text = re.sub(r"(?i)\b(token|cookie|authorization|password|secret|session|header)\s*[:=]\s*([^\s,;]+)",
                  r"\1=[redacted]", str(message or ""))
    text = re.sub(r"(?i)\bBearer\s+[^\s,;]+", "Bearer [redacted]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:240]


def _parser_metadata(shadow: str, reason: str) -> tuple[str, str]:
    if shadow in {"error", "unsupported"} and reason.startswith(("import failed:", "parse failed:")):
        return "failed", reason
    return "ok", ""


def _shadow_verdict(sgf_text, moves):
    """Replay player moves on the sgf_engine tree.

    Returns (verdict, reason); verdict in:
    accept / reject / off_tree / unsupported / error.

    Mirrors legacy _rt_replay semantics: reaching a leaf = accept; explicit
    RESULT metadata (rare) takes precedence.

    Never calls sgf_engine.engine.apply_move because its off-tree path writes DB.
    """
    try:
        from sgf_engine.core import autoreply, matcher, tree
        from sgf_engine.core.coord_utils import xy_to_sgf
        from sgf_engine.parser.sgf_parser import parse_sgf
    except Exception as exc:
        return "error", f"import failed: {type(exc).__name__}"

    try:
        root = parse_sgf(sgf_text)
    except Exception as exc:
        return "unsupported", f"parse failed: {type(exc).__name__}"

    cur = root

    if not cur.children:
        return "unsupported", "answer tree has no children"

    player_color = cur.children[0].metadata.get("color", "B")

    if not moves:
        return "reject", "empty move list"

    for idx, mv in enumerate(moves):
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


_REVIEW_CLASSES = {
    "legacy_accepts_shadow_rejects",
    "legacy_rejects_shadow_accepts",
    "legacy_accepts_shadow_off_tree",
    "legacy_rejects_shadow_off_tree",
    "shadow_unsupported",
    "shadow_error",
}


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
    """Total function. Never raises. No-op when the flag is off."""
    started = time.perf_counter()
    route, request_id = _request_metadata()
    parser_status = "ok"
    parser_failure_reason = ""
    exception_class = ""
    exception_message = ""
    shadow = "error"
    reason = "shadow observation failed"
    legacy = "reject" if not final_correct else "accept"
    classification = "shadow_error"

    try:
        if not is_enabled():
            return

        if entry_point not in _SUPPORTED_ENTRY_POINTS:
            shadow, reason = "unsupported", f"route unsupported: {entry_point}"
            parser_status, parser_failure_reason = "failed", reason
        elif entry_point != "rating_test":
            shadow, reason = "unsupported", f"route unsupported: {entry_point}"
            parser_status, parser_failure_reason = "failed", reason
        elif moves is None:
            shadow, reason = "unsupported", "missing moves payload"
            parser_status, parser_failure_reason = "failed", reason
        else:
            shadow, reason = _shadow_verdict(sgf_transformed, moves)
            classification = _classify(legacy, shadow)
            parser_status, parser_failure_reason = _parser_metadata(shadow, reason)

        if classification == "shadow_error" and shadow != "error":
            classification = _classify(legacy, shadow)
    except Exception as exc:
        exception_class = type(exc).__name__
        exception_message = _sanitize_message(exc)
        classification = "shadow_error"
        parser_status, parser_failure_reason = _parser_metadata(shadow, reason)
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
            "moves_count": len(moves) if isinstance(moves, list) else 0,
            "katago_best_move": katago_best_move or "",
            "katago_best_move_present": bool(katago_best_move),
            "user_facing_judgement_changed": False,
        }

        try:
            line = json.dumps(event, ensure_ascii=False)

            with _LOCK:
                with open(_events_path(), "a", encoding="utf-8") as f:
                    f.write(line + "\n")
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
    """Compatibility wrapper for the legacy rating test route."""
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

    old_en = os.environ.get("SHADOW_JUDGING_ENABLED")
    old_path = os.environ.get("SHADOW_EVENTS_PATH")

    try:
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "ev.jsonl")

            os.environ["SHADOW_EVENTS_PATH"] = p

            os.environ["SHADOW_JUDGING_ENABLED"] = "0"
            observe_answer_route(entry_point="rating_test", **kwargs)
            checks.append(("flag off writes nothing", not os.path.exists(p)))

            os.environ["SHADOW_JUDGING_ENABLED"] = "1"
            observe_answer_route(entry_point="rating_test", **kwargs)

            with open(p, encoding="utf-8") as f:
                ev = json.loads(f.read().splitlines()[0])

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

            checks.append(("event has required fields", required <= set(ev)))
            checks.append(("schema version bumped", ev["schema_version"] == "shadow-v3"))
            checks.append(("classification agreement", ev["classification"] == "agreement_accept"))
            checks.append(("never changes judgement", ev["user_facing_judgement_changed"] is False))

            try:
                observe_answer_route(
                    entry_point="rating_test",
                    question_id=None,
                    session_id=None,
                    transform_idx=None,
                    sgf_transformed=None,
                    moves=[{"x": "bad"}],
                    client_correct=None,
                    final_correct=None,
                    katago_best_move=None,
                )
                checks.append(("observe is total", True))
            except Exception:
                checks.append(("observe is total", False))

    finally:
        for key, val in (
            ("SHADOW_JUDGING_ENABLED", old_en),
            ("SHADOW_EVENTS_PATH", old_path),
        ):
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    failed = [name for name, ok in checks if not ok]

    if failed:
        print("SELFTEST FAILED: " + ", ".join(failed))
        return 1

    print(f"SELFTEST OK ({len(checks)}/{len(checks)})")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        sys.exit(_selftest())
