"""LC005 — terminal-verdict census classifier + judge regression.

Proves the SAFE_AUTO_CANDIDATE rule is mechanically testable and that the
classifier never turns a bare leaf into a success on its own. Also runs
representative records through canonical_learning_judge to prove LC003/LC004
semantics are not weakened.

Read-only. No corpus mutation. Run:
  python -m pytest tests/test_lc005_terminal_verdict_census.py -q
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from canonical_learning_judge import Attempt, JudgeStatus, judge_answer  # noqa: E402
from tools.lc005_terminal_verdict_census import (  # noqa: E402
    CLASSES,
    classify_record,
    run_census,
)


def xy(c: str) -> tuple[int, int]:
    return ord(c[0]) - 97, ord(c[1]) - 97


def _mk(moves, colour="B"):
    return Attempt.from_payload({"moves": [{"x": x, "y": y} for x, y in moves],
                                "player_color": colour, "transform": "identity"})


# --------------------------------------------------------------------------
# synthetic corpus covering every class
# --------------------------------------------------------------------------

RECORDS = [
    # ALREADY_EXPLICIT — success marker on terminal
    {"id": 1, "record_index": 0, "content": "(;SZ[19];B[pd]RE[B+])"},
    # ALREADY_EXPLICIT — 正解 comment on terminal
    {"id": 2, "record_index": 1, "content": "(;SZ[19];B[pd]C[正解])"},
    # ALREADY_EXPLICIT — accepted_moves authority
    {"id": 3, "record_index": 2, "content": "(;SZ[19];B[pd])",
     "accepted_moves": [{"x": xy("pd")[0], "y": xy("pd")[1]}]},
    # ALREADY_EXPLICIT — explicit failure only
    {"id": 4, "record_index": 3, "content": "(;SZ[19];B[pd]C[失敗])"},
    # SAFE_AUTO_CANDIDATE — game-info root RE, deterministic bare line
    {"id": 5, "record_index": 4, "content": "(;GM[1]SZ[19]RE[B+];B[pd])"},
    # SAFE_AUTO_CANDIDATE — root RE, deep deterministic line, bare terminal
    {"id": 6, "record_index": 5, "content": "(;GM[1]SZ[19]RE[W+R];W[dd];B[pp];W[qf])"},
    # MANUAL_SEMANTIC_REVIEW — bare terminal, no annotation anywhere
    {"id": 7, "record_index": 6, "content": "(;SZ[19];B[pd])"},
    # MANUAL_SEMANTIC_REVIEW — bare deep line, no annotation
    {"id": 8, "record_index": 7, "content": "(;SZ[19];B[pd];W[dd];B[qf])"},
    # AMBIGUOUS_AUTOREPLY — two opponent replies
    {"id": 9, "record_index": 8,
     "content": "(;SZ[19];B[pd](;W[dd];B[qf]RE[B+])(;W[dp];B[cf]RE[B+]))"},
    # MALFORMED_SOURCE — truncated
    {"id": 10, "record_index": 9, "content": "(;SZ[19];B[pd];W[dd]"},
    # MALFORMED_SOURCE — bad property
    {"id": 11, "record_index": 10, "content": "(;SZ[19];B[pd]4[x])"},
    # EMPTY_OR_UNANSWERABLE — setup only, no move
    {"id": 12, "record_index": 11, "content": "(;SZ[19]AB[dd][pd])"},
    # COLOR_AUTHORITY_INCOMPLETE — no PL and root's only child is a move-less
    #   setup node, so _server_expected_player_color returns None even though a
    #   move exists deeper in the tree.
    {"id": 13, "record_index": 12, "content": "(;SZ[19];AB[pp];B[dd])"},
    # DUPLICATE_IDENTITY_BLOCKED — id 99 appears twice, both bare
    {"id": 99, "record_index": 13, "content": "(;SZ[19];B[pd])"},
    {"id": 99, "record_index": 14, "content": "(;SZ[19];B[dp])"},
    # root RE present but a FAILURE token -> NOT safe-auto -> MANUAL
    {"id": 15, "record_index": 15, "content": "(;GM[1]SZ[19]RE[failed];B[pd])"},
]


class TestClassificationAccounting:
    def test_every_record_gets_exactly_one_class(self):
        result = run_census(RECORDS, snapshot_sha256="test")
        assert result["classification_accounting_pass"] is True
        assert result["classification_total"] == result["input_record_total"] == len(RECORDS)
        assert set(result["counts"]) == set(CLASSES)

    def test_expected_class_per_record(self):
        expected = {
            1: "ALREADY_EXPLICIT", 2: "ALREADY_EXPLICIT", 3: "ALREADY_EXPLICIT",
            4: "ALREADY_EXPLICIT", 5: "SAFE_AUTO_CANDIDATE", 6: "SAFE_AUTO_CANDIDATE",
            7: "MANUAL_SEMANTIC_REVIEW", 8: "MANUAL_SEMANTIC_REVIEW",
            9: "AMBIGUOUS_AUTOREPLY", 10: "MALFORMED_SOURCE", 11: "MALFORMED_SOURCE",
            12: "EMPTY_OR_UNANSWERABLE", 13: "COLOR_AUTHORITY_INCOMPLETE",
            15: "MANUAL_SEMANTIC_REVIEW",
        }
        dup = frozenset({99})
        for rec in RECORDS:
            if rec["id"] == 99:
                e = classify_record(rec, duplicate_legacy_ids=dup, snapshot_sha256="t")
                assert e.classification == "DUPLICATE_IDENTITY_BLOCKED"
                continue
            e = classify_record(rec, snapshot_sha256="t")
            assert e.classification == expected[rec["id"]], (rec["id"], e.classification, e.reason_code)


class TestSafeAutoRuleIsConservative:
    def test_bare_leaf_alone_is_never_safe_auto(self):
        e = classify_record({"id": 1, "content": "(;SZ[19];B[pd])"}, snapshot_sha256="t")
        assert e.classification == "MANUAL_SEMANTIC_REVIEW"
        assert e.proposed_marker_action is None

    def test_safe_auto_requires_existing_non_failure_root_RE(self):
        ok = classify_record({"id": 1, "content": "(;GM[1]SZ[19]RE[B+];B[pd])"}, snapshot_sha256="t")
        assert ok.classification == "SAFE_AUTO_CANDIDATE"
        assert ok.proposed_marker_action["marker_property"] == "RE"
        assert ok.proposed_marker_action["marker_value"] == "B+"      # verbatim, nothing invented
        assert ok.proposed_marker_action["applied"] is False

        bad = classify_record({"id": 1, "content": "(;GM[1]SZ[19]RE[wrong];B[pd])"}, snapshot_sha256="t")
        assert bad.classification == "MANUAL_SEMANTIC_REVIEW"

    def test_safe_auto_requires_deterministic_line(self):
        # root RE present but the line is ambiguous -> AMBIGUOUS_AUTOREPLY wins
        e = classify_record(
            {"id": 1, "content": "(;GM[1]SZ[19]RE[B+];B[pd](;W[dd];B[qf])(;W[dp];B[cf]))"},
            snapshot_sha256="t",
        )
        assert e.classification == "AMBIGUOUS_AUTOREPLY"

    def test_safe_auto_never_fires_when_a_terminal_already_has_a_marker(self):
        e = classify_record(
            {"id": 1, "content": "(;GM[1]SZ[19]RE[B+];B[pd]TE[1])"}, snapshot_sha256="t",
        )
        assert e.classification == "ALREADY_EXPLICIT"

    def test_proposed_action_is_dry_run_only(self):
        result = run_census(RECORDS, snapshot_sha256="t")
        for row in result["entries"]:
            if row["proposed_marker_action"]:
                assert row["proposed_marker_action"]["applied"] is False


class TestSubtags:
    def test_malformed_subtags(self):
        trunc = classify_record({"id": 1, "content": "(;SZ[19];B[pd]"}, snapshot_sha256="t")
        assert trunc.subtag == "TRUNCATED_SGF"
        prop = classify_record({"id": 2, "content": "(;SZ[19];B[pd]4[x])"}, snapshot_sha256="t")
        assert prop.subtag in ("MALFORMED_SGF", "OTHER_PARSE_FAILURE")

    def test_ambiguous_subtag_true_reply(self):
        e = classify_record(
            {"id": 1, "content": "(;SZ[19];B[pd](;W[dd];B[qf]RE[B+])(;W[dp];B[cf]RE[B+]))"},
            snapshot_sha256="t",
        )
        assert e.subtag == "TRUE_AMBIGUOUS_REPLY"


class TestCoverageProjection:
    def test_projection_fields_present_and_ordered(self):
        result = run_census(RECORDS, snapshot_sha256="t")
        cur = result["current_explicit_verdict_coverage_pct"]
        after_auto = result["projected_after_safe_auto_pct"]
        after_manual = result["projected_after_manual_review_best_case_pct"]
        assert 0.0 <= cur <= after_auto <= after_manual <= 100.0
        # never claims 100% while blocked populations exist
        if result["remaining_blocked_records"] > 0:
            assert after_manual < 100.0
        assert result["remaining_blocked_records"] == (
            result["counts"]["AMBIGUOUS_AUTOREPLY"]
            + result["counts"]["MALFORMED_SOURCE"]
            + result["counts"]["EMPTY_OR_UNANSWERABLE"]
            + result["counts"]["DUPLICATE_IDENTITY_BLOCKED"]
            + result["counts"]["COLOR_AUTHORITY_INCOMPLETE"]
            + result["counts"]["OTHER_BLOCKED"]
        )


# --------------------------------------------------------------------------
# LC003/LC004 judge regression on representative records
# --------------------------------------------------------------------------

class TestJudgeRegressionNotWeakened:
    def test_already_explicit_regression_pass(self):
        assert judge_answer(question_content="(;SZ[19];B[pd]RE[B+])",
                            attempt=_mk([xy("pd")])).status is JudgeStatus.CORRECT

    def test_safe_auto_projected_judge_result_after_marker(self):
        # BEFORE the (unapplied) marker: bare terminal -> UNVERIFIABLE
        before = judge_answer(question_content="(;GM[1]SZ[19]RE[B+];B[pd])",
                              attempt=_mk([xy("pd")]))
        assert before.status is JudgeStatus.UNVERIFIABLE
        # AFTER the proposed marker (RE propagated verbatim onto the terminal):
        after = judge_answer(question_content="(;GM[1]SZ[19]RE[B+];B[pd]RE[B+])",
                             attempt=_mk([xy("pd")]))
        assert after.status is JudgeStatus.CORRECT

    def test_ambiguous_remains_fail_closed(self):
        r = judge_answer(
            question_content="(;SZ[19];B[pd](;W[dd];B[qf]RE[B+])(;W[dp];B[cf]RE[B+]))",
            attempt=_mk([xy("pd"), xy("qf")]),
        )
        assert r.status is JudgeStatus.AMBIGUOUS

    def test_malformed_remains_fail_closed(self):
        r = judge_answer(question_content="(;SZ[19];B[pd];W[dd]", attempt=_mk([xy("pd")]))
        assert r.status is JudgeStatus.MALFORMED

    def test_bare_unrepaired_remains_unverifiable(self):
        r = judge_answer(question_content="(;SZ[19];B[pd])", attempt=_mk([xy("pd")]))
        assert r.status is JudgeStatus.UNVERIFIABLE


# --------------------------------------------------------------------------
# CLI + manifest shape
# --------------------------------------------------------------------------

class TestCliAndManifest:
    def test_cli_without_snapshot_is_import_only(self):
        r = subprocess.run(
            [sys.executable, "-m", "tools.lc005_terminal_verdict_census"],
            capture_output=True, text=True, cwd=str(REPO), timeout=60,
        )
        assert r.returncode == 0
        assert "no --snapshot supplied" in r.stdout

    def test_cli_runs_a_synthetic_snapshot_and_writes_manifest(self, tmp_path):
        snap = tmp_path / "synthetic_snapshot.json"
        snap.write_text(json.dumps(RECORDS), encoding="utf-8")
        out = tmp_path / "manifest.json"
        r = subprocess.run(
            [sys.executable, "-m", "tools.lc005_terminal_verdict_census",
             "--snapshot", str(snap), "--out-manifest", str(out),
             "--snapshot-sha256", "deadbeef"],
            capture_output=True, text=True, cwd=str(REPO), timeout=60,
        )
        assert r.returncode == 0, r.stdout + r.stderr
        manifest = json.loads(out.read_text(encoding="utf-8"))
        assert manifest["classification_accounting_pass"] is True
        assert len(manifest["entries"]) == len(RECORDS)
        for row in manifest["entries"]:
            assert row["classification"] in CLASSES
            assert row["locator"]["locator_type"] == "AUDIT_LOCATOR_ONLY"
            # never legacy integer id alone as durable identity
            assert "content_sha256" in row["locator"]
            assert row["source_record_uuid"] is None    # LC005 generates none

    def test_manifest_row_has_every_required_field(self):
        e = classify_record(RECORDS[4], snapshot_sha256="t")   # a SAFE_AUTO_CANDIDATE
        row = e.to_manifest_row()
        for key in ("locator", "legacy_question_id", "record_index", "source_record_uuid",
                    "content_sha256", "classification", "current_terminal_semantics",
                    "proposed_marker_action", "evidence_basis", "confidence_class",
                    "manual_review_required", "reason_code", "blockers"):
            assert key in row
