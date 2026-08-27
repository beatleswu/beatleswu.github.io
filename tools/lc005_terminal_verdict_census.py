"""LC005 — deterministic terminal-verdict remediation classifier (READ-ONLY).

Given a corpus record ``{"id": int, "content": "<SGF>", "accepted_moves"?: [...],
"source"?: str, "record_index"?: int}`` this module places it in exactly one
remediation class and computes the dry-run marker action for a
``SAFE_AUTO_CANDIDATE``.

It mutates NOTHING. It never writes a corpus file. The CLI, when given a
snapshot path, emits a census summary + a machine-readable manifest; without
a snapshot it is import-only (used by tests/test_lc005_terminal_verdict_census.py).

Classification is kept consistent with ``canonical_learning_judge`` by reusing
its terminal-verdict, colour, and tree helpers. The owner-locked semantics
(FAIL_CLOSED_UNTIL_EXPLICIT_VERDICT, FAIL_CLOSED_NO_BLIND_CHILD0) are NOT
weakened here — a bare leaf is never "safe" on its own.

SAFE_AUTO_CANDIDATE rule (see docs/planning/lc005_terminal_verdict_census.md):
  A record is SAFE_AUTO_CANDIDATE iff ALL of --
   1. it strict-parses, is non-empty, has a reachable player-move terminal;
   2. its answer line(s) are deterministic (no ambiguous opponent reply);
   3. its expected player colour is server-resolvable (root PL or first move);
   4. its legacy id is unique (not in a duplicate-id group);
   5. NO reachable terminal already carries a judge-honoured marker AND none
      carries an authored failure annotation;
   6. it carries an EXISTING explicit non-failure success annotation elsewhere
      in the same record -- specifically a game-info-root ``RE[...]`` whose
      value contains no failure token -- that the judge does not read only
      because it sits on the root container rather than the terminal node.
  The proposed (NOT applied) action is: copy that record's own root
  ``RE[<value>]`` verbatim onto each reachable bare terminal move node.
Anything with a bare terminal and no such existing annotation is
MANUAL_SEMANTIC_REVIEW, never SAFE_AUTO.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from canonical_learning_judge import (  # noqa: E402
    _FAILURE_RESULT_TOKENS,
    _explicit_terminal_is_correct,
    _is_leaf,
    _server_expected_player_color,
)
from sgf_engine.core.tree import SGFNode  # noqa: E402
from sgf_engine.parser.sgf_parser import parse_sgf  # noqa: E402

CENSUS_TOOL_VERSION = "lc005-terminal-verdict-census-v1"

# every record lands in exactly one of these
CLASSES = (
    "ALREADY_EXPLICIT",
    "SAFE_AUTO_CANDIDATE",
    "MANUAL_SEMANTIC_REVIEW",
    "AMBIGUOUS_AUTOREPLY",
    "MALFORMED_SOURCE",
    "EMPTY_OR_UNANSWERABLE",
    "DUPLICATE_IDENTITY_BLOCKED",
    "COLOR_AUTHORITY_INCOMPLETE",
    "OTHER_BLOCKED",
)


def _content_sha256(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def _opponent(colour: str) -> str:
    return "W" if colour == "B" else "B"


@dataclass
class _TreeAnalysis:
    has_reachable_move_terminal: bool = False
    ambiguous: bool = False
    ambiguity_kind: str | None = None            # TRUE_AMBIGUOUS_REPLY | OTHER_BRANCHING_SHAPE
    terminal_verdicts: list[bool | None] = field(default_factory=list)  # per reachable terminal
    root_child_count: int = 0
    max_depth_moves: int = 0


def _analyze_answer_tree(root: SGFNode, colour: str) -> _TreeAnalysis:
    """Walk every authored player line the judge could take (no client moves).

    A player line: root -> player move -> (unique opponent reply) -> player
    move -> ...  Ambiguity fires exactly where ``judge_answer`` would return
    AMBIGUOUS: a post-player node whose children are not exactly one single
    opponent move.
    """
    out = _TreeAnalysis()
    opp = _opponent(colour)
    out.root_child_count = len(root.children)

    def walk_after_player_move(node: SGFNode, depth: int) -> None:
        out.max_depth_moves = max(out.max_depth_moves, depth)
        if _is_leaf(node):
            out.has_reachable_move_terminal = True
            out.terminal_verdicts.append(_explicit_terminal_is_correct(node))
            return
        opp_children = [c for c in node.children if c.move is not None and c.move.color == opp]
        if len(node.children) != 1 or len(opp_children) != 1:
            out.ambiguous = True
            if any(c.move is not None and c.move.color == opp for c in node.children) and len(opp_children) > 1:
                out.ambiguity_kind = "TRUE_AMBIGUOUS_REPLY"
            else:
                out.ambiguity_kind = out.ambiguity_kind or "OTHER_BRANCHING_SHAPE"
            return
        reply = opp_children[0]
        if _is_leaf(reply):
            out.has_reachable_move_terminal = True
            out.terminal_verdicts.append(_explicit_terminal_is_correct(reply))
            return
        # after the opponent reply, the next authored player moves:
        player_children = [c for c in reply.children if c.move is not None and c.move.color == colour]
        if not player_children:
            # authored line ends with a non-terminal opponent node and no
            # player continuation -> treat the opponent node as the terminal
            out.has_reachable_move_terminal = True
            out.terminal_verdicts.append(_explicit_terminal_is_correct(reply))
            return
        for pc in player_children:
            walk_after_player_move(pc, depth + 1)

    first_player_moves = [c for c in root.children if c.move is not None and c.move.color == colour]
    if not first_player_moves:
        return out
    for fpm in first_player_moves:
        walk_after_player_move(fpm, 1)
    return out


def _has_any_move_node(node: SGFNode) -> bool:
    if node.move is not None:
        return True
    return any(_has_any_move_node(c) for c in node.children)


def _root_re_value(root: SGFNode) -> str | None:
    value = str((root.metadata or {}).get("game_result") or "").strip()
    return value or None


def _re_is_non_failure_success(value: str) -> bool:
    low = value.lower()
    return bool(value) and not any(tok in low for tok in _FAILURE_RESULT_TOKENS)


def _malformed_subtag(err: Exception) -> str:
    msg = str(err).lower()
    if "trailing" in msg or "expected ')'" in msg or "unterminated" in msg or "incomplete escape" in msg:
        return "TRUNCATED_SGF"
    if "invalid sgf move" in msg or "coordinate" in msg or "coord" in msg:
        return "INVALID_COORDINATE"
    if "property identifier" in msg or "has no value" in msg or "property" in msg:
        return "MALFORMED_SGF"
    return "OTHER_PARSE_FAILURE"


@dataclass
class CensusEntry:
    locator: dict[str, Any]
    legacy_question_id: Any
    record_index: Any
    source_record_uuid: Any
    content_sha256: str
    classification: str
    subtag: str | None
    current_terminal_semantics: str
    proposed_marker_action: dict[str, Any] | None
    evidence_basis: str
    confidence_class: str
    manual_review_required: bool
    blockers: list[str]
    reason_code: str

    def to_manifest_row(self) -> dict[str, Any]:
        return {
            "locator": self.locator,
            "legacy_question_id": self.legacy_question_id,
            "record_index": self.record_index,
            "source_record_uuid": self.source_record_uuid,
            "content_sha256": self.content_sha256,
            "classification": self.classification,
            "subtag": self.subtag,
            "current_terminal_semantics": self.current_terminal_semantics,
            "proposed_marker_action": self.proposed_marker_action,
            "evidence_basis": self.evidence_basis,
            "confidence_class": self.confidence_class,
            "manual_review_required": self.manual_review_required,
            "blockers": self.blockers,
            "reason_code": self.reason_code,
        }


def classify_record(
    record: dict[str, Any],
    *,
    duplicate_legacy_ids: frozenset[Any] = frozenset(),
    snapshot_sha256: str = "UNKNOWN",
) -> CensusEntry:
    content = record.get("content") or ""
    legacy_id = record.get("id", record.get("legacy_question_id"))
    record_index = record.get("record_index")
    uuid = record.get("source_record_uuid")  # LC005 does not generate one
    source = record.get("source")
    csha = _content_sha256(content)
    locator = {
        # NEVER legacy integer id alone (LC002/E1: 11 duplicate-id groups)
        "snapshot_sha256": snapshot_sha256,
        "record_index": record_index,
        "legacy_question_id": legacy_id,
        "content_sha256": csha,
        "source_path": source,
        "locator_type": "AUDIT_LOCATOR_ONLY",
    }
    blockers: list[str] = []
    if legacy_id in duplicate_legacy_ids:
        blockers.append("duplicate_legacy_id")

    def entry(cls, subtag, sem, action, ev, conf, manual, reason):
        return CensusEntry(
            locator=locator, legacy_question_id=legacy_id, record_index=record_index,
            source_record_uuid=uuid, content_sha256=csha, classification=cls,
            subtag=subtag, current_terminal_semantics=sem, proposed_marker_action=action,
            evidence_basis=ev, confidence_class=conf, manual_review_required=manual,
            blockers=blockers, reason_code=reason,
        )

    # 1. strict parse
    try:
        root = parse_sgf(content, strict=True)
    except ValueError as err:
        return entry("MALFORMED_SOURCE", _malformed_subtag(err), "unparseable", None,
                     "strict_parse_raised", "n/a", True, "strict_parse_valueerror")
    except Exception as err:  # noqa: BLE001
        return entry("MALFORMED_SOURCE", "OTHER_PARSE_FAILURE", "unparseable", None,
                     f"parser_exception:{type(err).__name__}", "n/a", True, "parser_exception")

    # 2. empty / no answer tree
    if not root.children:
        return entry("EMPTY_OR_UNANSWERABLE", "EMPTY_TREE", "no_terminal", None,
                     "root_has_no_children", "n/a", True, "empty_answer_tree")
    if not _has_any_move_node(root):
        return entry("EMPTY_OR_UNANSWERABLE", "MISSING_ANSWER_TREE", "no_terminal", None,
                     "tree_has_no_move_node", "n/a", True, "no_move_node")

    # 3. colour authority
    server_colour = _server_expected_player_color(root)
    if server_colour is None:
        return entry("COLOR_AUTHORITY_INCOMPLETE", None, "unknown_side_to_move", None,
                     "no_PL_and_no_first_move_colour", "n/a", True, "color_silent")

    analysis = _analyze_answer_tree(root, server_colour)

    # 4. ambiguous opponent reply — checked before "no reachable terminal"
    #    because a line that hits ambiguity never reaches a terminal.
    if analysis.ambiguous:
        return entry("AMBIGUOUS_AUTOREPLY", analysis.ambiguity_kind or "OTHER_BRANCHING_SHAPE",
                     "ambiguous", None, "multiple_or_non_unique_opponent_reply", "n/a", True,
                     "ambiguous_autoreply")

    if not analysis.has_reachable_move_terminal:
        return entry("EMPTY_OR_UNANSWERABLE", "MISSING_ANSWER_TREE", "no_terminal", None,
                     "no_reachable_player_move_terminal", "n/a", True, "unreachable_terminal")

    verdicts = analysis.terminal_verdicts
    any_success = any(v is True for v in verdicts)
    any_failure = any(v is False for v in verdicts)
    all_bare = all(v is None for v in verdicts)

    # 5. already explicit (judge returns a definite verdict at the terminal)
    if record.get("accepted_moves"):
        return entry("ALREADY_EXPLICIT", "ACCEPTED_MOVES", "explicit_success",
                     None, "server_accepted_moves_present", "high", False,
                     "accepted_moves_authority")
    if any_success:
        return entry("ALREADY_EXPLICIT", "TERMINAL_SUCCESS_MARKER", "explicit_success",
                     None, "honoured_success_marker_on_terminal", "high", False,
                     "terminal_success_marker")
    if any_failure and not any_success:
        return entry("ALREADY_EXPLICIT", "TERMINAL_FAILURE_MARKER", "explicit_failure",
                     None, "honoured_failure_marker_on_terminal", "high", False,
                     "terminal_failure_marker_only")

    # 6. bare terminal(s) -> blockers, then SAFE_AUTO rule, then MANUAL
    if not all_bare:
        return entry("OTHER_BLOCKED", None, "mixed_terminal_state", None,
                     "unexpected_mixed_verdict_set", "n/a", True, "mixed_terminal_state")

    if "duplicate_legacy_id" in blockers:
        return entry("DUPLICATE_IDENTITY_BLOCKED", None, "bare_terminal", None,
                     "record_in_duplicate_legacy_id_group", "n/a", True,
                     "duplicate_identity_blocks_auto_repair")

    root_re = _root_re_value(root)
    if root_re is not None and _re_is_non_failure_success(root_re):
        action = {
            "action": "PROPAGATE_ROOT_RE_TO_TERMINAL",
            "marker_property": "RE",
            "marker_value": root_re,                 # verbatim; nothing invented
            "targets": "every_reachable_bare_terminal_move_node",
            "applied": False,
        }
        return entry("SAFE_AUTO_CANDIDATE", None, "bare_terminal",
                     action, "existing_root_RE_non_failure + deterministic_line",
                     "medium", False, "root_re_propagation_candidate")

    return entry("MANUAL_SEMANTIC_REVIEW", None, "bare_terminal", None,
                 "bare_terminal_no_existing_success_annotation", "n/a", True,
                 "needs_human_semantic_decision")


def run_census(
    records: Iterable[dict[str, Any]],
    *,
    snapshot_sha256: str = "UNKNOWN",
) -> dict[str, Any]:
    rows = list(records)
    seen: dict[Any, int] = {}
    for r in rows:
        lid = r.get("id", r.get("legacy_question_id"))
        seen[lid] = seen.get(lid, 0) + 1
    dup_ids = frozenset(lid for lid, n in seen.items() if lid is not None and n > 1)

    entries = [classify_record(r, duplicate_legacy_ids=dup_ids, snapshot_sha256=snapshot_sha256) for r in rows]
    counts = {cls: 0 for cls in CLASSES}
    subtags: dict[str, dict[str, int]] = {cls: {} for cls in CLASSES}
    for e in entries:
        counts[e.classification] += 1
        if e.subtag:
            subtags[e.classification][e.subtag] = subtags[e.classification].get(e.subtag, 0) + 1

    total = len(rows)
    classification_total = sum(counts.values())
    terminal_answer_records = total - counts["MALFORMED_SOURCE"] - counts["EMPTY_OR_UNANSWERABLE"]
    already_success = sum(
        1 for e in entries
        if e.classification == "ALREADY_EXPLICIT" and e.current_terminal_semantics == "explicit_success"
    )
    safe_auto = counts["SAFE_AUTO_CANDIDATE"]

    def pct(n, d):
        return round(100.0 * n / d, 3) if d else 0.0

    remaining_blocked = (
        counts["AMBIGUOUS_AUTOREPLY"] + counts["MALFORMED_SOURCE"]
        + counts["EMPTY_OR_UNANSWERABLE"] + counts["DUPLICATE_IDENTITY_BLOCKED"]
        + counts["COLOR_AUTHORITY_INCOMPLETE"] + counts["OTHER_BLOCKED"]
    )
    return {
        "census_tool_version": CENSUS_TOOL_VERSION,
        "snapshot_sha256": snapshot_sha256,
        "input_record_total": total,
        "classification_total": classification_total,
        "classification_accounting_pass": classification_total == total,
        "counts": counts,
        "subtags": subtags,
        "duplicate_legacy_id_count": len(dup_ids),
        "duplicate_record_count": sum(n for n in seen.values() if n > 1),
        "terminal_answer_records": terminal_answer_records,
        "current_explicit_success_records": already_success,
        "current_explicit_verdict_coverage_pct": pct(already_success, terminal_answer_records),
        "projected_after_safe_auto_pct": pct(already_success + safe_auto, terminal_answer_records),
        "projected_after_manual_review_best_case_pct": pct(
            terminal_answer_records - counts["AMBIGUOUS_AUTOREPLY"]
            - counts["DUPLICATE_IDENTITY_BLOCKED"] - counts["COLOR_AUTHORITY_INCOMPLETE"]
            - counts["OTHER_BLOCKED"],
            terminal_answer_records,
        ),
        "remaining_blocked_records": remaining_blocked,
        "entries": [e.to_manifest_row() for e in entries],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_snapshot(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("snapshot must be a JSON list of records")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LC005 terminal-verdict remediation census (read-only).")
    parser.add_argument("--snapshot", type=Path, help="path to an immutable questions.json snapshot")
    parser.add_argument("--out-manifest", type=Path, help="write the machine-readable manifest JSON here")
    parser.add_argument("--snapshot-sha256", default="UNKNOWN")
    args = parser.parse_args(argv)

    if not args.snapshot:
        print("no --snapshot supplied; nothing to census. "
              "This tool is import-only without a snapshot; see "
              "tests/test_lc005_terminal_verdict_census.py")
        return 0
    if not args.snapshot.exists():
        raise SystemExit(f"snapshot not found: {args.snapshot}")

    records = _load_snapshot(args.snapshot)
    result = run_census(records, snapshot_sha256=args.snapshot_sha256)
    summary = {k: v for k, v in result.items() if k != "entries"}
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.out_manifest:
        args.out_manifest.write_text(
            json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"manifest written: {args.out_manifest} "
              f"({hashlib.sha256(args.out_manifest.read_bytes()).hexdigest()})")
    return 0 if result["classification_accounting_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
