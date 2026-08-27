"""LC007 — terminal-verdict marker-policy impact simulator (READ-ONLY).

Given the byte-verified canonical snapshot, this tool classifies every record's
*terminal semantics* under each candidate marker policy and diffs the result
against the current judge behaviour (Policy A).

It mutates NOTHING: no corpus write, no marker apply, no Production read. The
policies here are analysis objects only -- none is wired into
``canonical_learning_judge`` or ``app.py``. Choosing/enabling a policy is an
owner decision (see docs/planning/lc007_terminal_verdict_marker_semantics.md).

Policy summary (full text in the doc):
  A  current: substring success/failure token anywhere in the terminal comment,
     plus a move-node RE (game_result) and a terminal TE property.
  B  anchored comment token: a comment yields SUCCESS only if, after stripping
     wrapping decoration and trailing punctuation, it is *exactly* a success
     token, carries no failure token and no reference/comparison marker.
     Adds 不正解/不正確/不正确 as (anchored) failure tokens.
  C  node-name: an ``N[...]`` on the *reachable terminal* whose trimmed value is
     exactly a success/failure token. ``N`` on a non-terminal node is ignored.
  D  structured-only: comments are not read at all; SUCCESS/FAILURE only from a
     move-node RE or a terminal TE.
  RECOMMENDED  = move-node RE  OR  terminal TE  OR  anchored terminal comment (B)
     OR  exact terminal N[...] (C).  Fail-closed on anything else.

Terminal-semantics buckets (partition all records):
  MALFORMED | AMBIGUOUS | EXPLICIT_SUCCESS | EXPLICIT_FAILURE | UNVERIFIABLE
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from canonical_learning_judge import (  # noqa: E402
    _FAILURE_RESULT_TOKENS,
    _SUCCESS_COMMENT_TOKENS,
    _re_is_decisive,
    _server_expected_player_color,
)
from sgf_engine.core.tree import SGFNode  # noqa: E402
from sgf_engine.parser.sgf_parser import parse_sgf  # noqa: E402

LC007_TOOL_VERSION = "lc007-marker-policy-simulation-v1"
EXPECTED_SNAPSHOT_SHA256 = "88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff"
EXPECTED_RECORD_COUNT = 42804

BUCKETS = ("MALFORMED", "AMBIGUOUS", "EXPLICIT_SUCCESS", "EXPLICIT_FAILURE", "UNVERIFIABLE")

# ---------------------------------------------------------------------------
# marker-string helpers
# ---------------------------------------------------------------------------

_WRAP_CHARS = "　 \t\r\n【】〔〕［］[]（）()「」『』〈〉《》\"'“”‘’*_#-—―·・"
# NB: '?' / '？' are deliberately NOT stripped -- an interrogative comment
# ("正解？" = "correct?") is a question, not an assertion, and must stay
# fail-closed (LC7-E contract review).
_TRAIL_PUNCT = "。．.!！:：;；、,，…~〜　 \t\r\n"
# markers that make a success token a *reference to* the concept, not a label —
# kept as a defensive secondary reject even though the primary rule is exact-match
_REFERENCE_MARKERS = (
    "と同じ", "と同", "一样", "一樣", "一致", "より", "参照", "參照", "参考", "參考",
    "図参照", "圖參照", "ではない", "じゃない", "では", "比べ", "比較", "増える", "増加",
    "增加", "增", "増", "same as", "compared", "reference", "worse", "better than",
    "not ", "図", "圖",
)
# failure tokens the judge's list misses (simplified CJK + 不- negation)
_EXTRA_FAILURE_TOKENS = (
    "不正解", "不正確", "不正确", "錯", "错误", "错", "失败",
    "not correct", "not the correct", "incorrect",
)


def _norm(text: Any) -> str:
    return str(text or "").strip().lower()


def _strip_decoration(text: str) -> str:
    return text.strip(_WRAP_CHARS).strip(_TRAIL_PUNCT).strip(_WRAP_CHARS)


def _has_any(hay: str, needles) -> bool:
    return any(n.lower() in hay for n in needles)


def _node_props(node: SGFNode) -> dict:
    return (node.metadata or {}).get("properties") or {}


def _node_comment(node: SGFNode) -> str:
    return _norm((node.metadata or {}).get("comment"))


def _node_game_result(node: SGFNode) -> str:
    return _norm((node.metadata or {}).get("game_result"))


def _node_names(node: SGFNode) -> list[str]:
    raw = _node_props(node).get("N") or []
    if isinstance(raw, str):
        raw = [raw]
    return [_strip_decoration(_norm(v)) for v in raw]


# ---------------------------------------------------------------------------
# per-policy terminal verdict: True (success) / False (failure) / None (unknown)
# ---------------------------------------------------------------------------

def _re_or_te(node: SGFNode) -> bool | None:
    """Shared structured layer for policies B/C/D/RECOMMENDED: a move-node RE
    (decisive winning-side shape only -- LC009 wired _re_is_decisive into the
    live judge), then a terminal TE. Policy A keeps its own looser inline RE
    check as the frozen pre-LC009 reference."""
    re_verdict = _re_is_decisive((node.metadata or {}).get("game_result"))
    if re_verdict is not None:
        return re_verdict
    if "TE" in _node_props(node):
        return True
    return None


def verdict_policy_a(node: SGFNode) -> bool | None:
    """Exact reproduction of canonical_learning_judge._explicit_terminal_is_correct."""
    gr = _node_game_result(node)
    if gr:
        return not _has_any(gr, _FAILURE_RESULT_TOKENS)
    if "TE" in _node_props(node):
        return True
    comment = _node_comment(node)
    if comment:
        if _has_any(comment, _FAILURE_RESULT_TOKENS):
            return False
        if _has_any(comment, _SUCCESS_COMMENT_TOKENS):
            return True
    return None


def _anchored_comment_verdict(comment: str) -> bool | None:
    """Policy B core: a comment is a SUCCESS label only if, after trimming
    wrapping decoration and trailing punctuation, it is *exactly* a success
    token -- no prose, no comparison. A comment that is exactly a failure token
    (judge list + simplified-CJK / 不- gaps) is FAILURE. Anything else -> None
    (fail closed). Never an unanchored substring."""
    if not comment:
        return None
    core = _strip_decoration(comment)
    success = {_norm(t) for t in _SUCCESS_COMMENT_TOKENS}
    failure = {_norm(t) for t in _FAILURE_RESULT_TOKENS} | {_norm(t) for t in _EXTRA_FAILURE_TOKENS}
    if core in failure:
        return False
    if core in success:
        if _has_any(comment, _REFERENCE_MARKERS):  # e.g. decoration-strip edge
            return None
        return True
    # a failure token present only as prose is still not a success
    if _has_any(comment, tuple(failure)) and not _has_any(comment, tuple(success)):
        return False
    return None


def verdict_policy_b(node: SGFNode) -> bool | None:
    v = _re_or_te(node)
    if v is not None:
        return v
    return _anchored_comment_verdict(_node_comment(node))


def _name_verdict(node: SGFNode) -> bool | None:
    names = set(_node_names(node))
    if not names:
        return None
    if names & {_norm(t) for t in _SUCCESS_COMMENT_TOKENS}:
        return True
    if names & ({_norm(t) for t in _FAILURE_RESULT_TOKENS} | {_norm(t) for t in _EXTRA_FAILURE_TOKENS}):
        return False
    return None


def verdict_policy_c(node: SGFNode) -> bool | None:
    """Structured layer + exact terminal N[...]; comments NOT read."""
    v = _re_or_te(node)
    if v is not None:
        return v
    return _name_verdict(node)


def verdict_policy_d(node: SGFNode) -> bool | None:
    """Structured markers only."""
    return _re_or_te(node)


def verdict_recommended(node: SGFNode) -> bool | None:
    v = _re_or_te(node)
    if v is not None:
        return v
    v = _anchored_comment_verdict(_node_comment(node))
    if v is not None:
        return v
    return _name_verdict(node)


POLICIES: dict[str, Callable[[SGFNode], bool | None]] = {
    "A": verdict_policy_a,
    "B": verdict_policy_b,
    "C": verdict_policy_c,
    "D": verdict_policy_d,
    "RECOMMENDED": verdict_recommended,
}


# ---------------------------------------------------------------------------
# reachable-terminal walk (consistent with judge_answer / LC005)
# ---------------------------------------------------------------------------

@dataclass
class _Walk:
    malformed: bool = False
    ambiguous: bool = False
    has_terminal: bool = False
    terminals: list[SGFNode] = None  # type: ignore

    def __post_init__(self):
        if self.terminals is None:
            self.terminals = []


def _walk_terminals(content: str) -> _Walk:
    w = _Walk()
    try:
        root = parse_sgf(content, strict=True)
    except Exception:
        w.malformed = True
        return w
    if not root.children:
        return w
    colour = _server_expected_player_color(root)
    if colour is None:
        return w
    opp = "W" if colour == "B" else "B"

    def after_player(node: SGFNode) -> None:
        if not node.children:
            w.has_terminal = True
            w.terminals.append(node)
            return
        opp_children = [c for c in node.children if c.move is not None and c.move.color == opp]
        if len(node.children) != 1 or len(opp_children) != 1:
            w.ambiguous = True
            return
        reply = opp_children[0]
        if not reply.children:
            w.has_terminal = True
            w.terminals.append(reply)
            return
        player_children = [c for c in reply.children if c.move is not None and c.move.color == colour]
        if not player_children:
            w.has_terminal = True
            w.terminals.append(reply)
            return
        for pc in player_children:
            after_player(pc)

    firsts = [c for c in root.children if c.move is not None and c.move.color == colour]
    if not firsts:
        return w
    for f in firsts:
        after_player(f)
    return w


def bucket_for(content: str, verdict: Callable[[SGFNode], bool | None]) -> str:
    w = _walk_terminals(content)
    if w.malformed:
        return "MALFORMED"
    if w.ambiguous:
        return "AMBIGUOUS"
    if not w.has_terminal:
        return "UNVERIFIABLE"
    verdicts = [verdict(t) for t in w.terminals]
    if any(v is True for v in verdicts):
        return "EXPLICIT_SUCCESS"
    if any(v is False for v in verdicts):
        return "EXPLICIT_FAILURE"
    return "UNVERIFIABLE"


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def _content_sha(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def verify_snapshot(path: Path) -> tuple[str, bool, list[dict[str, Any]]]:
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != EXPECTED_SNAPSHOT_SHA256:
        return sha, False, []
    data = json.loads(raw)
    if not isinstance(data, list):
        raise SystemExit("snapshot must be a JSON list")
    return sha, True, data


def simulate(records: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(records)
    per_policy_bucket = {p: {b: 0 for b in BUCKETS} for p in POLICIES}
    base = []  # policy A bucket per record
    rows = []
    for idx, rec in enumerate(records):
        content = rec.get("content") or ""
        a_bucket = bucket_for(content, POLICIES["A"])
        base.append(a_bucket)
        per_policy_bucket["A"][a_bucket] += 1
        rec_row = {"record_index": idx, "legacy_question_id": rec.get("id"),
                   "content_sha256": _content_sha(content), "A": a_bucket}
        for p, fn in POLICIES.items():
            if p == "A":
                continue
            b = bucket_for(content, fn)
            per_policy_bucket[p][b] += 1
            rec_row[p] = b
        rows.append(rec_row)

    diffs = {}
    changed_rows = []
    for p in POLICIES:
        if p == "A":
            continue
        newly_accepted, newly_rejected, changed = [], [], []
        for r in rows:
            if r["A"] == r[p]:
                continue
            changed.append(r["record_index"])
            if r[p] == "EXPLICIT_SUCCESS" and r["A"] != "EXPLICIT_SUCCESS":
                newly_accepted.append(r["record_index"])
            if r["A"] == "EXPLICIT_SUCCESS" and r[p] != "EXPLICIT_SUCCESS":
                newly_rejected.append(r["record_index"])
        diffs[p] = {
            "newly_accepted": newly_accepted,
            "newly_rejected": newly_rejected,
            "changed_from_current": changed,
            "newly_accepted_count": len(newly_accepted),
            "newly_rejected_count": len(newly_rejected),
            "changed_from_current_count": len(changed),
        }
        for ridx in changed:
            r = rows[ridx]
            changed_rows.append({"record_index": ridx, "legacy_question_id": r["legacy_question_id"],
                                 "content_sha256": r["content_sha256"], "policy": p,
                                 "from_bucket": r["A"], "to_bucket": r[p]})

    # content-duplicate impact (§11): recompute counts on one record per content sha
    seen: set[str] = set()
    dedup_bucket = {p: {b: 0 for b in BUCKETS} for p in POLICIES}
    for r in rows:
        if r["content_sha256"] in seen:
            continue
        seen.add(r["content_sha256"])
        for p in POLICIES:
            dedup_bucket[p][r[p]] += 1

    return {
        "record_count": n,
        "per_policy_bucket": per_policy_bucket,
        "per_policy_bucket_dedup_by_content": dedup_bucket,
        "distinct_content_sha": len(seen),
        "diffs": diffs,
        "changed_rows": changed_rows,
        "rows": rows,
    }


def build_report(path: Path, out_impact: Path | None) -> dict[str, Any]:
    sha, match, records = verify_snapshot(path)
    if not match:
        raise SystemExit(
            f"SNAPSHOT_HASH_MISMATCH: got {sha}, expected {EXPECTED_SNAPSHOT_SHA256}. STOP."
        )
    sim = simulate(records)
    a = sim["per_policy_bucket"]["A"]
    rec = sim["per_policy_bucket"]["RECOMMENDED"]
    impact = {
        "lc007_tool_version": LC007_TOOL_VERSION,
        "snapshot_sha256": sha,
        "snapshot_hash_match": match,
        "record_count": sim["record_count"],
        "record_count_match": sim["record_count"] == EXPECTED_RECORD_COUNT,
        "buckets": BUCKETS,
        "per_policy_bucket": sim["per_policy_bucket"],
        "per_policy_bucket_dedup_by_content": sim["per_policy_bucket_dedup_by_content"],
        "distinct_content_sha": sim["distinct_content_sha"],
        "diffs_vs_current": sim["diffs"],
        "current_explicit_success_count": a["EXPLICIT_SUCCESS"],
        "current_explicit_failure_count": a["EXPLICIT_FAILURE"],
        "recommended_explicit_success_count": rec["EXPLICIT_SUCCESS"],
        "recommended_explicit_failure_count": rec["EXPLICIT_FAILURE"],
        "changed_rows": sim["changed_rows"],
        "corpus_mutation": False,
    }
    impact_sha = None
    if out_impact is not None:
        out_impact.write_bytes(
            (json.dumps(impact, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        )
        impact_sha = hashlib.sha256(out_impact.read_bytes()).hexdigest()
    return {"impact": impact, "impact_path": out_impact.as_posix() if out_impact else None,
            "impact_sha256": impact_sha}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LC007 marker-policy impact simulation (read-only).")
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--out-impact", type=Path)
    args = p.parse_args(argv)
    if not args.snapshot.exists():
        raise SystemExit(f"snapshot not found: {args.snapshot}")
    result = build_report(args.snapshot, args.out_impact)
    summary = {k: v for k, v in result["impact"].items()
              if k not in ("changed_rows", "per_policy_bucket_dedup_by_content")}
    summary["impact_path"] = result["impact_path"]
    summary["impact_sha256"] = result["impact_sha256"]
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
