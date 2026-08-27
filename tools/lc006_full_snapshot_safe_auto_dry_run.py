"""LC006 — full-snapshot SAFE_AUTO terminal-verdict dry-run (READ-ONLY).

Runs the LC005 classifier (tools/lc005_terminal_verdict_census) over the
byte-verified immutable canonical corpus snapshot and, for every
SAFE_AUTO_CANDIDATE, simulates the LC005 ROOT_RE_PROPAGATION action
in memory and re-judges it through canonical_learning_judge:

    before  -> must be UNVERIFIABLE
    after   -> must be CORRECT      (RE[<root value>] on the reached terminal)

Any candidate that does not satisfy before=UNVERIFIABLE / after=CORRECT is
removed from SAFE_AUTO and reclassified MANUAL_SEMANTIC_REVIEW. The final
SAFE_AUTO set therefore has a 100% projected judge pass rate by construction.

NOTHING is written to the corpus. No Production query. No marker apply.
The snapshot's expected identity is hard-pinned:

    EXPECTED_SNAPSHOT_SHA256 = 88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff
    EXPECTED_RECORD_COUNT    = 42804

If the supplied file does not hash-match, this tool STOPS (exit 2) and
substitutes nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from canonical_learning_judge import (  # noqa: E402
    Attempt,
    JudgeStatus,
    _server_expected_player_color,
    judge_answer,
)
from sgf_engine.core.tree import SGFNode  # noqa: E402
from sgf_engine.parser.sgf_parser import parse_sgf  # noqa: E402
from tools.lc005_terminal_verdict_census import (  # noqa: E402
    _root_re_value,
    run_census,
)

EXPECTED_SNAPSHOT_SHA256 = "88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff"
EXPECTED_RECORD_COUNT = 42804
LC006_TOOL_VERSION = "lc006-full-snapshot-safe-auto-dry-run-v1"


# ---------------------------------------------------------------------------
# minimal deterministic SGF re-serializer (only what the judge reads)
# ---------------------------------------------------------------------------

def _serialize_node(node: SGFNode, mark_terminals_with_re: str | None) -> str:
    """Emit `;<move>[...]` for one node plus its children/variations. When
    ``mark_terminals_with_re`` is set, append ``RE[<value>]`` to every
    childless node reached (the ROOT_RE_PROPAGATION dry-run)."""
    out = [";"]
    move = node.move
    if move is not None:
        if move.is_pass or move.coord is None:
            out.append(f"{move.color}[]")
        else:
            out.append(f"{move.color}[{move.coord}]")
    # keep an existing per-node result if the parser recorded one
    existing = str((node.metadata or {}).get("game_result") or "").strip()
    if existing:
        out.append(f"RE[{existing}]")
    if not node.children and mark_terminals_with_re and not existing:
        out.append(f"RE[{mark_terminals_with_re}]")
    if len(node.children) == 1:
        out.append(_serialize_node(node.children[0], mark_terminals_with_re))
    elif len(node.children) > 1:
        for child in node.children:
            out.append("(" + _serialize_node(child, mark_terminals_with_re) + ")")
    return "".join(out)


def serialize_tree(root: SGFNode, *, mark_terminals_with_re: str | None = None) -> str:
    """Round-trippable SGF for the judge: root game-info + move tree."""
    props = (root.metadata or {}).get("properties") or {}
    head = [";", "GM[1]", "FF[4]"]
    size = (root.metadata or {}).get("size")
    head.append(f"SZ[{int(size)}]" if isinstance(size, int) else "SZ[19]")
    pl = (root.metadata or {}).get("player_to_move")
    if pl in ("B", "W"):
        head.append(f"PL[{pl}]")
    for prop in ("AB", "AW", "AE"):
        vals = props.get(prop) or []
        if vals:
            head.append(prop + "".join(f"[{v}]" for v in vals))
    root_re = str((root.metadata or {}).get("game_result") or "").strip()
    if root_re:
        head.append(f"RE[{root_re}]")
    body_parts = []
    if len(root.children) == 1:
        body_parts.append(_serialize_node(root.children[0], mark_terminals_with_re))
    else:
        for child in root.children:
            body_parts.append("(" + _serialize_node(child, mark_terminals_with_re) + ")")
    return "(" + "".join(head) + "".join(body_parts) + ")"


# ---------------------------------------------------------------------------
# authored player lines (for the before/after attempt)
# ---------------------------------------------------------------------------

def _authored_player_lines(root: SGFNode, colour: str) -> list[list[tuple[int, int]]]:
    """Every deterministic authored player move sequence to a reachable
    terminal (mirrors canonical_learning_judge's walk)."""
    opp = "W" if colour == "B" else "B"
    lines: list[list[tuple[int, int]]] = []

    def coord_xy(m):
        return (ord(m.coord[0]) - 97, ord(m.coord[1]) - 97)

    def walk(node: SGFNode, acc: list[tuple[int, int]]) -> None:
        if node.move is not None and node.move.coord:
            acc = acc + [coord_xy(node.move)]
        if not node.children:
            lines.append(acc)
            return
        opp_children = [c for c in node.children if c.move is not None and c.move.color == opp]
        if len(node.children) != 1 or len(opp_children) != 1:
            return  # ambiguous -> not a SAFE_AUTO candidate anyway
        reply = opp_children[0]
        if not reply.children:
            lines.append(acc)
            return
        player_children = [c for c in reply.children if c.move is not None and c.move.color == colour]
        if not player_children:
            lines.append(acc)
            return
        for pc in player_children:
            walk(pc, acc)

    for fpm in [c for c in root.children if c.move is not None and c.move.color == colour]:
        walk(fpm, [])
    return [ln for ln in lines if ln]


def _simulate_safe_auto(record: dict[str, Any]) -> dict[str, Any]:
    """Run the ROOT_RE_PROPAGATION dry-run for one SAFE_AUTO candidate."""
    content = record.get("content") or ""
    root = parse_sgf(content, strict=True)
    colour = _server_expected_player_color(root)
    root_re = _root_re_value(root)
    lines = _authored_player_lines(root, colour)
    after_content = serialize_tree(root, mark_terminals_with_re=root_re)

    results = []
    ok = bool(lines) and root_re is not None
    for line in lines:
        attempt = Attempt.from_payload({
            "moves": [{"x": x, "y": y} for (x, y) in line],
            "player_color": colour, "transform": "identity",
        })
        before = judge_answer(question_content=content, attempt=attempt)
        after = judge_answer(question_content=after_content, attempt=attempt)
        line_ok = (before.status is JudgeStatus.UNVERIFIABLE
                   and after.status is JudgeStatus.CORRECT)
        ok = ok and line_ok
        results.append({
            "player_line": [f"{chr(97 + x)}{chr(97 + y)}" for (x, y) in line],
            "before_status": before.status.value,
            "before_reason": before.reason_code,
            "after_status": after.status.value,
            "after_reason": after.reason_code,
            "line_ok": line_ok,
        })
    return {
        "root_re": root_re,
        "player_colour": colour,
        "after_content_sha256": hashlib.sha256(after_content.encode("utf-8")).hexdigest(),
        "lines": results,
        "judge_pass": ok,
    }


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def verify_snapshot(path: Path) -> tuple[str, bool, list[dict[str, Any]]]:
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    match = sha == EXPECTED_SNAPSHOT_SHA256
    if not match:
        return sha, False, []
    data = json.loads(raw)
    if not isinstance(data, list):
        raise SystemExit("snapshot must be a JSON list of records")
    return sha, True, data


def run(path: Path, out_manifest: Path | None) -> dict[str, Any]:
    sha, match, records = verify_snapshot(path)
    if not match:
        raise SystemExit(
            f"SNAPSHOT_HASH_MISMATCH: got {sha}, expected {EXPECTED_SNAPSHOT_SHA256}. "
            "STOP -- LC006 substitutes nothing."
        )
    record_count = len(records)

    census = run_census(records, snapshot_sha256=sha)
    counts = dict(census["counts"])

    # judge simulation for every SAFE_AUTO candidate. run_census preserves input
    # order, so entries[i] <-> records[i]; the snapshot records carry no
    # "record_index" key, so alignment (not row["record_index"]) is authoritative.
    safe_auto_rows: list[dict[str, Any]] = []
    reclassified = 0
    safe_pass = 0
    safe_total = 0
    entries = census["entries"]
    for idx, row in enumerate(entries):
        if row["classification"] != "SAFE_AUTO_CANDIDATE":
            continue
        safe_total += 1
        rec = records[idx]
        sim = _simulate_safe_auto(rec)
        if sim["judge_pass"]:
            safe_pass += 1
            safe_auto_rows.append({
                "snapshot_sha256": sha,
                "record_index": idx,
                "legacy_question_id": row["legacy_question_id"],
                "source_record_uuid": row["source_record_uuid"],
                "content_sha256": row["content_sha256"],
                "root_RE": sim["root_re"],
                "player_colour": sim["player_colour"],
                "terminal_locators": [ln["player_line"] for ln in sim["lines"]],
                "proposed_action": {
                    "action": "PROPAGATE_ROOT_RE_TO_TERMINAL",
                    "marker_property": "RE",
                    "marker_value": sim["root_re"],
                    "targets": "every_reachable_bare_terminal_move_node",
                    "after_content_sha256": sim["after_content_sha256"],
                },
                "reason_code": "root_re_propagation_candidate",
                "confidence": "medium",
                "judge_before": "UNVERIFIABLE",
                "judge_after_projected": "CORRECT",
                "applied": False,
            })
        else:
            reclassified += 1
            counts["SAFE_AUTO_CANDIDATE"] -= 1
            counts["MANUAL_SEMANTIC_REVIEW"] += 1

    safe_auto_exact = len(safe_auto_rows)
    terminal_answer_records = census["terminal_answer_records"]
    already_success = census["current_explicit_success_records"]

    def pct(n: int, d: int) -> float:
        return round(100.0 * n / d, 6) if d else 0.0

    manual_remaining = counts["MANUAL_SEMANTIC_REVIEW"]
    source_level_blocked = (
        counts["AMBIGUOUS_AUTOREPLY"] + counts["MALFORMED_SOURCE"]
        + counts["EMPTY_OR_UNANSWERABLE"] + counts["DUPLICATE_IDENTITY_BLOCKED"]
        + counts["COLOR_AUTHORITY_INCOMPLETE"] + counts["OTHER_BLOCKED"]
    )
    classification_total = sum(counts.values())

    summary = {
        "lc006_tool_version": LC006_TOOL_VERSION,
        "snapshot_basename": path.name,
        "snapshot_location_note": (
            "byte-verified immutable canonical snapshot; lives untracked at the "
            "main-checkout root, absent from this worktree's git tree"
        ),
        "snapshot_sha256": sha,
        "snapshot_hash_match": match,
        "expected_snapshot_sha256": EXPECTED_SNAPSHOT_SHA256,
        "corpus_record_count": record_count,
        "expected_record_count": EXPECTED_RECORD_COUNT,
        "record_count_match": record_count == EXPECTED_RECORD_COUNT,
        "counts": counts,
        "subtags": census["subtags"],
        "classification_total": classification_total,
        "classification_accounting_pass": classification_total == record_count,
        "duplicate_legacy_id_groups": census["duplicate_legacy_id_count"],
        "duplicate_record_count": census["duplicate_record_count"],
        "terminal_answer_records": terminal_answer_records,
        "current_explicit_success_records": already_success,
        "current_explicit_verdict_coverage_pct": pct(already_success, terminal_answer_records),
        "safe_auto_exact_count": safe_auto_exact,
        "safe_auto_before_reclassification": safe_total,
        "safe_auto_reclassified_manual": reclassified,
        "safe_auto_projected_judge_pass": safe_pass,
        "safe_auto_projected_judge_pass_rate_pct": (
            round(100.0 * safe_pass / safe_total, 6) if safe_total else 100.0
        ),
        "projected_after_safe_auto_pct": pct(already_success + safe_auto_exact, terminal_answer_records),
        "manual_review_remaining": manual_remaining,
        "source_level_blocked_remaining": source_level_blocked,
        "corpus_mutation": False,
        "owner_marker_decision_required": True,
    }

    manifest = {
        "schema_version": "1.0",
        "authority": "LC006_FULL_SNAPSHOT_SAFE_AUTO_TERMINAL_VERDICT_DRY_RUN_001",
        "canonicality": "DRY_RUN__NO_MUTATION__NOT_APPLIED",
        "safe_auto_rule": "ROOT_RE_PROPAGATION (LC005, unchanged)",
        "summary": summary,
        "safe_auto_candidates": safe_auto_rows,
    }
    manifest_sha = None
    manifest_path = None
    if out_manifest is not None:
        out_manifest.write_bytes(
            (json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        )
        manifest_sha = hashlib.sha256(out_manifest.read_bytes()).hexdigest()
        manifest_path = out_manifest.as_posix()
    return {
        "summary": summary,
        "manifest": manifest,
        "safe_auto_manifest_path": manifest_path,
        "safe_auto_manifest_sha256": manifest_sha,
        "snapshot_path_resolved": str(path),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LC006 full-snapshot SAFE_AUTO dry-run (read-only).")
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--out-manifest", type=Path)
    args = p.parse_args(argv)
    if not args.snapshot.exists():
        raise SystemExit(f"snapshot not found: {args.snapshot}")
    result = run(args.snapshot, args.out_manifest)
    report = dict(result["summary"])
    report["snapshot_path_resolved"] = result["snapshot_path_resolved"]
    report["safe_auto_manifest_path"] = result["safe_auto_manifest_path"]
    report["safe_auto_manifest_sha256"] = result["safe_auto_manifest_sha256"]
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if result["summary"]["classification_accounting_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
