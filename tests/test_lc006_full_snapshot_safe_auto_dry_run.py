"""LC006 — tests for the full-snapshot SAFE_AUTO terminal-verdict dry-run driver.

The real corpus snapshot (42,804 records, sha256 88da3e43...) is untracked and
absent from this worktree, so the 42k run itself is not exercised here. What IS
exercised is every mechanism the LC006 spec puts weight on:

  * the snapshot hash gate STOPs on any mismatch (substitutes nothing);
  * the SAFE_AUTO judge before/after simulation returns
    before=UNVERIFIABLE / after=CORRECT for a genuine ROOT_RE_PROPAGATION
    candidate (so "100% pass rate" is a demonstrated property, not a vacuous
    0/0 on the real corpus);
  * a candidate the stricter judge simulation cannot confirm is reclassified
    out of SAFE_AUTO into MANUAL_SEMANTIC_REVIEW;
  * the manifest row carries every field the spec enumerates, with applied=False;
  * classification accounting stays total-preserving.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import tools.lc006_full_snapshot_safe_auto_dry_run as lc006  # noqa: E402
from canonical_learning_judge import JudgeStatus  # noqa: E402
from tools.lc005_terminal_verdict_census import classify_record  # noqa: E402

# --------------------------------------------------------------------------- #
# synthetic records
# --------------------------------------------------------------------------- #

# genuine SAFE_AUTO candidate: game-info-root RE[B+R] the judge does not read,
# a deterministic B line, a bare terminal at B[cc].
SGF_SAFE_AUTO = "(;GM[1]FF[4]SZ[19]PL[B]RE[B+R];B[qq];W[pp];B[cc])"

# classifies SAFE_AUTO (LC005 treats the childless-of-player opponent node as a
# terminal) but the judge simulation cannot confirm it -> must be reclassified.
SGF_SAFE_AUTO_UNCONFIRMABLE = "(;GM[1]FF[4]SZ[19]PL[B]RE[B+R];B[qq];W[pp];W[dd])"

# plain bare terminal, no root RE -> MANUAL, never SAFE_AUTO.
SGF_MANUAL = "(;GM[1]FF[4]SZ[19]PL[B];B[qq];W[pp];B[cc])"

# already explicit: RE on the terminal move node itself.
SGF_ALREADY = "(;GM[1]FF[4]SZ[19]PL[B];B[qq];W[pp];B[cc]RE[B+R])"

# malformed.
SGF_MALFORMED = "(;GM[1]FF[4]SZ[19]PL[B];B[qq];W["


def _records() -> list[dict]:
    return [
        {"id": 900001, "content": SGF_SAFE_AUTO},
        {"id": 900002, "content": SGF_SAFE_AUTO_UNCONFIRMABLE},
        {"id": 900003, "content": SGF_MANUAL},
        {"id": 900004, "content": SGF_ALREADY},
        {"id": 900005, "content": SGF_MALFORMED},
    ]


@pytest.fixture()
def snapshot_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A tiny JSON-list snapshot whose real sha256 the driver is told to expect."""
    raw = json.dumps(_records()).encode("utf-8")
    path = tmp_path / "questions_synthetic.json"
    path.write_bytes(raw)
    monkeypatch.setattr(lc006, "EXPECTED_SNAPSHOT_SHA256", hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(lc006, "EXPECTED_RECORD_COUNT", len(_records()))
    return path


# --------------------------------------------------------------------------- #
# snapshot hash gate
# --------------------------------------------------------------------------- #

class TestSnapshotHashGate:
    def test_mismatch_stops_and_substitutes_nothing(self, tmp_path: Path):
        bogus = tmp_path / "not_the_snapshot.json"
        bogus.write_bytes(json.dumps([{"id": 1, "content": SGF_MANUAL}]).encode("utf-8"))
        with pytest.raises(SystemExit) as exc:
            lc006.run(bogus, None)
        assert "SNAPSHOT_HASH_MISMATCH" in str(exc.value)

    def test_exact_match_proceeds(self, snapshot_file: Path):
        sha, match, records = lc006.verify_snapshot(snapshot_file)
        assert match is True
        assert sha == lc006.EXPECTED_SNAPSHOT_SHA256
        assert len(records) == 5


# --------------------------------------------------------------------------- #
# SAFE_AUTO judge before/after simulation
# --------------------------------------------------------------------------- #

class TestSafeAutoJudgeSimulation:
    def test_genuine_candidate_before_unverifiable_after_correct(self):
        assert classify_record({"id": 1, "content": SGF_SAFE_AUTO}).classification == "SAFE_AUTO_CANDIDATE"
        sim = lc006._simulate_safe_auto({"id": 1, "content": SGF_SAFE_AUTO})
        assert sim["judge_pass"] is True
        assert sim["root_re"] == "B+R"
        assert sim["player_colour"] == "B"
        assert sim["lines"], "expected at least one authored player line"
        for line in sim["lines"]:
            assert line["before_status"] == JudgeStatus.UNVERIFIABLE.value
            assert line["after_status"] == JudgeStatus.CORRECT.value
            assert line["line_ok"] is True

    def test_serialize_tree_keeps_root_re_and_marks_terminal(self):
        from sgf_engine.parser.sgf_parser import parse_sgf

        root = parse_sgf(SGF_SAFE_AUTO, strict=True)
        after = lc006.serialize_tree(root, mark_terminals_with_re="B+R")
        assert "RE[B+R]" in after
        # terminal B[cc] now carries the propagated marker
        assert "B[cc]RE[B+R]" in after
        # and it is still a single well-formed game tree
        assert after.startswith("(;") and after.endswith(")")
        parse_sgf(after, strict=True)  # must not raise

    def test_unconfirmable_candidate_fails_simulation(self):
        assert classify_record(
            {"id": 1, "content": SGF_SAFE_AUTO_UNCONFIRMABLE}
        ).classification == "SAFE_AUTO_CANDIDATE"
        sim = lc006._simulate_safe_auto({"id": 1, "content": SGF_SAFE_AUTO_UNCONFIRMABLE})
        assert sim["judge_pass"] is False


# --------------------------------------------------------------------------- #
# end-to-end run() over the synthetic snapshot
# --------------------------------------------------------------------------- #

class TestRunOverSyntheticSnapshot:
    def test_accounting_is_total_preserving(self, snapshot_file: Path):
        out = lc006.run(snapshot_file, None)
        s = out["summary"]
        assert s["snapshot_hash_match"] is True
        assert s["corpus_record_count"] == 5
        assert s["classification_total"] == 5
        assert s["classification_accounting_pass"] is True
        assert sum(s["counts"].values()) == 5

    def test_unconfirmable_candidate_is_reclassified_manual(self, snapshot_file: Path):
        out = lc006.run(snapshot_file, None)
        s = out["summary"]
        # one genuine candidate survives, one is demoted
        assert s["safe_auto_before_reclassification"] == 2
        assert s["safe_auto_reclassified_manual"] == 1
        assert s["safe_auto_exact_count"] == 1
        assert s["counts"]["SAFE_AUTO_CANDIDATE"] == 1
        assert s["safe_auto_projected_judge_pass_rate_pct"] == pytest.approx(50.0)

    def test_manifest_row_has_every_spec_field(self, snapshot_file: Path, tmp_path: Path):
        manifest_path = tmp_path / "lc006_manifest.json"
        out = lc006.run(snapshot_file, manifest_path)
        rows = out["manifest"]["safe_auto_candidates"]
        assert len(rows) == 1
        row = rows[0]
        for field in (
            "snapshot_sha256", "record_index", "legacy_question_id",
            "source_record_uuid", "content_sha256", "root_RE",
            "terminal_locators", "proposed_action", "reason_code",
            "confidence", "applied",
        ):
            assert field in row, f"manifest row missing {field}"
        assert row["applied"] is False
        assert row["judge_before"] == "UNVERIFIABLE"
        assert row["judge_after_projected"] == "CORRECT"
        assert row["proposed_action"]["marker_property"] == "RE"
        assert row["proposed_action"]["marker_value"] == "B+R"
        # file written, hashable, LF-terminated
        assert manifest_path.read_bytes().endswith(b"\n")
        assert out["safe_auto_manifest_sha256"] == hashlib.sha256(
            manifest_path.read_bytes()
        ).hexdigest()

    def test_empty_candidate_run_reports_cleanly(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        raw = json.dumps([{"id": 1, "content": SGF_MANUAL}, {"id": 2, "content": SGF_ALREADY}]).encode()
        path = tmp_path / "q.json"
        path.write_bytes(raw)
        monkeypatch.setattr(lc006, "EXPECTED_SNAPSHOT_SHA256", hashlib.sha256(raw).hexdigest())
        out = lc006.run(path, tmp_path / "m.json")
        s = out["summary"]
        assert s["safe_auto_exact_count"] == 0
        # 0/0 is reported as 100%, not a crash
        assert s["safe_auto_projected_judge_pass_rate_pct"] == 100.0
        assert out["manifest"]["safe_auto_candidates"] == []
