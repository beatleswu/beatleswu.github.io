"""LC009 — Owner-approved explicit terminal-verdict marker semantics (live judge).

The LC007 RECOMMENDED policy is now wired into
``canonical_learning_judge._explicit_terminal_is_correct``. This suite proves:

  * the four approved channels (decisive-shape RE, terminal TE, anchored-exact
    comment token, exact terminal N[...]) behave exactly as approved;
  * every other terminal shape FAILS CLOSED to None (-> UNVERIFIABLE);
  * SUBSTRING_ONLY_SUCCESS is gone -- 正解 in prose is not a verdict;
  * record 8023 (index 17147) moves EXPLICIT_SUCCESS -> UNVERIFIABLE and no
    other snapshot record changes classification;
  * an earlier move-node N[正解] is never read as a terminal verdict;
  * judge_answer end-to-end honours only the approved markers;
  * the full-snapshot recount is deterministic and matches the approved buckets.

The 42,804-record snapshot is untracked; snapshot-bound tests are guarded on
its presence + hash.
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

import tools.lc009_live_judge_snapshot_recount as recount  # noqa: E402
from canonical_learning_judge import (  # noqa: E402
    CANONICAL_JUDGE_VERSION,
    Attempt,
    JudgeStatus,
    _exact_marker_verdict,
    _explicit_terminal_is_correct,
    _re_is_decisive,
    _terminal_name_verdict,
    judge_answer,
)
from sgf_engine.parser.sgf_parser import parse_sgf  # noqa: E402
from tools.lc005_terminal_verdict_census import classify_record  # noqa: E402

_SNAPSHOT = Path("D:/go-website/questions.json")
_SNAPSHOT_SHA = "88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff"


def _snapshot_ok() -> bool:
    return _SNAPSHOT.exists() and hashlib.sha256(_SNAPSHOT.read_bytes()).hexdigest() == _SNAPSHOT_SHA


def _leaf(sgf: str):
    n = parse_sgf(sgf, strict=True)
    while n.children:
        n = n.children[0]
    return n


# LC9-B verified RE decisive-shape vectors (True -> decisive, None -> non-decisive,
# False -> failure token).
RE_VECTORS = [
    ("B+R", True), ("B+Resign", True), ("W+R", True), ("W+Resign", True),
    ("B+T", True), ("B+Time", True), ("W+Time", True), ("B+F", True),
    ("B+Forfeit", True), ("W+Forfeit", True), ("B+1", True), ("B+12", True),
    ("W+3", True), ("B+0.5", True), ("B+3.5", True), ("W+65.5", True),
    ("B+", True), ("W+", True), ("b+r", True), ("B+RESIGN", True),
    ("w+time", True), (" B+R ", True), ("B+R\n", True),
    ("0", None), ("Draw", None), ("draw", None), ("Void", None), ("void", None),
    ("?", None), ("", None), ("   ", None), (None, None),
    ("B+0", None), ("B+0.0", None), ("B+00", None), ("B+-3", None),
    ("B", None), ("W", None), ("+R", None), ("+3", None), ("B++R", None),
    ("B+ R", None), ("BW+R", None), ("B+W", None), ("xB+R", None),
    ("B+R;", None), ("B+R extra", None), ("(B+R)", None), ("B+R.", None),
    ("B+Q", None), ("B+?", None), ("B+Resigns", None), ("B+timeout", None),
    ("B+score", None), ("3.5", None), ("3", None), ("correct", None),
    ("right", None), ("best", None), ("unknown", None), ("jigo", None),
    ("B\uff0bR", None), ("B+\uff13", None),
    ("wrong", False), ("incorrect", False), ("B+R fail", False),
    ("W+R (wrong side)", False), ("B+1 incorrect", False), ("\u00d7", False),
    ("\u5931\u6557", False), ("B+R \u932f\u8aa4", False),
]

# comment / node-name marker strings that MUST NOT become success by substring
NON_SUCCESS_MARKERS = [
    "和正解一樣", "正解より悪い", "請參考正解", "不正解", "正解？",
    "黑地虽然和正解一样，但白增加4目。", "正解と同じ", "これは正解", "正解図参照",
    "正解ではない", "not the correct answer",
]
EXACT_SUCCESS_MARKERS = ["正解", "正確", "成功", "correct", "success",
                         "【正解】", "（正解）", "  正解 ", "正解。"]
EXACT_FAILURE_MARKERS = ["不正解", "失敗", "錯誤", "×", "不正確", "错误"]

SGF_8023_SHAPED = (
    "(;GM[1]FF[4]SZ[19]PL[W]"
    "AB[mc][md][me][nc][ne][od][pd][qc][rc][sc]"
    "AW[lc][ld][le][mb][mf][nf][oe][pe][qd][qf][rd][sd]"
    "(;W[ob]N[正解];B[nb];W[oc];B[pc];W[na];B[nd];W[kb];B[pb];W[oa];B[pa];W[ma];B[ra])"
    "(;W[ob]N[参考];B[oc];W[pb];B[pc];W[nb];B[qb]C[黑地虽然和正解一样，但白增加4目。])"
    ")"
)


# --------------------------------------------------------------------------- #
# channel 1 — decisive-shape RE whitelist
# --------------------------------------------------------------------------- #

class TestREDecisiveWhitelist:
    @pytest.mark.parametrize("value,expected", RE_VECTORS)
    def test_re_is_decisive(self, value, expected):
        assert _re_is_decisive(value) is expected

    def test_non_decisive_re_on_terminal_fails_closed(self):
        for v in ("0", "Draw", "Void", "?", "B+0", "B+Q", "right"):
            assert _explicit_terminal_is_correct(_leaf(f"(;SZ[19];B[pd]RE[{v}])")) is None

    def test_decisive_re_on_terminal_is_success(self):
        for v in ("B+", "B+R", "W+3.5", "b+resign", "B+F"):
            assert _explicit_terminal_is_correct(_leaf(f"(;SZ[19];B[pd]RE[{v}])")) is True

    def test_failure_re_on_terminal_is_incorrect(self):
        assert _explicit_terminal_is_correct(_leaf("(;SZ[19];B[pd]RE[wrong])")) is False


# --------------------------------------------------------------------------- #
# channels 2-4 — TE / anchored comment / exact N
# --------------------------------------------------------------------------- #

class TestApprovedMarkerChannels:
    def test_terminal_te_preserved(self):
        assert _explicit_terminal_is_correct(_leaf("(;SZ[19];B[pd]TE[1])")) is True
        assert _explicit_terminal_is_correct(_leaf("(;SZ[19];B[pd]TE[])")) is True

    @pytest.mark.parametrize("marker", EXACT_SUCCESS_MARKERS)
    def test_exact_success_comment(self, marker):
        assert _exact_marker_verdict(marker) is True
        assert _explicit_terminal_is_correct(_leaf(f"(;SZ[19];B[pd]C[{marker.strip()}])")) is True

    @pytest.mark.parametrize("marker", EXACT_FAILURE_MARKERS)
    def test_exact_failure_comment(self, marker):
        assert _exact_marker_verdict(marker) is False

    @pytest.mark.parametrize("prose", NON_SUCCESS_MARKERS)
    def test_prose_reference_is_never_success(self, prose):
        assert _exact_marker_verdict(prose) is not True
        leaf = _leaf(f"(;SZ[19];B[pd]C[{prose}])")
        assert _explicit_terminal_is_correct(leaf) is not True

    def test_exact_terminal_name_success_and_reference(self):
        assert _terminal_name_verdict(["正解"]) is True
        assert _terminal_name_verdict("正解") is True
        assert _terminal_name_verdict(["参考"]) is None
        assert _terminal_name_verdict(None) is None
        assert _explicit_terminal_is_correct(_leaf("(;SZ[19];B[pd]N[正解])")) is True
        assert _explicit_terminal_is_correct(_leaf("(;SZ[19];B[pd]N[参考])")) is None


# --------------------------------------------------------------------------- #
# hard requirements
# --------------------------------------------------------------------------- #

class TestHardRequirements:
    def test_bare_leaf_correct_is_no(self):
        assert _explicit_terminal_is_correct(_leaf("(;SZ[19];B[pd])")) is None

    def test_substring_only_success_is_no(self):
        # the exact 8023 defect shape
        leaf = _leaf("(;SZ[19];B[pd]C[白は正解より2目多い])")
        assert _explicit_terminal_is_correct(leaf) is None

    def test_judge_version_bumped(self):
        assert CANONICAL_JUDGE_VERSION == "canonical-learning-judge-v2"

    def test_earlier_move_node_name_is_not_terminal_success(self):
        # N[正解] on move 1, bare terminal -> classifier must NOT call it explicit
        rec = {"id": 1, "content": "(;SZ[19];B[pd]N[正解];W[dd];B[qf])"}
        e = classify_record(rec, snapshot_sha256="t")
        assert e.classification != "ALREADY_EXPLICIT"
        assert e.current_terminal_semantics != "explicit_success"


# --------------------------------------------------------------------------- #
# record 8023
# --------------------------------------------------------------------------- #

class TestRecord8023:
    def test_shape_no_longer_explicit_success(self):
        e = classify_record({"id": 8023, "content": SGF_8023_SHAPED}, snapshot_sha256="t")
        assert e.classification == "MANUAL_SEMANTIC_REVIEW"
        assert e.current_terminal_semantics != "explicit_success"

    @pytest.mark.skipif(not _snapshot_ok(), reason="canonical snapshot absent")
    def test_real_record_8023_fixed(self):
        records = json.loads(_SNAPSHOT.read_bytes())
        rec = records[17147]
        assert rec["id"] == 8023
        e = classify_record(rec, snapshot_sha256=_SNAPSHOT_SHA)
        assert e.classification == "MANUAL_SEMANTIC_REVIEW"
        assert e.current_terminal_semantics != "explicit_success"


# --------------------------------------------------------------------------- #
# judge_answer end-to-end
# --------------------------------------------------------------------------- #

class TestJudgeAnswerEndToEnd:
    def _attempt(self, coords, colour="B"):
        return Attempt.from_payload({
            "moves": [{"x": ord(c[0]) - 97, "y": ord(c[1]) - 97} for c in coords],
            "player_color": colour, "transform": "identity",
        })

    def test_decisive_re_terminal_is_correct(self):
        r = judge_answer(question_content="(;SZ[19];B[pd]RE[B+])", attempt=self._attempt(["pd"]))
        assert r.status is JudgeStatus.CORRECT

    def test_non_decisive_re_terminal_is_unverifiable(self):
        r = judge_answer(question_content="(;SZ[19];B[pd]RE[Void])", attempt=self._attempt(["pd"]))
        assert r.status is JudgeStatus.UNVERIFIABLE

    def test_prose_comment_terminal_is_unverifiable(self):
        r = judge_answer(
            question_content="(;SZ[19];B[pd]C[黑地和正解一样，白多4目])",
            attempt=self._attempt(["pd"]),
        )
        assert r.status is JudgeStatus.UNVERIFIABLE

    def test_exact_comment_terminal_is_correct(self):
        r = judge_answer(question_content="(;SZ[19];B[pd]C[正解])", attempt=self._attempt(["pd"]))
        assert r.status is JudgeStatus.CORRECT


# --------------------------------------------------------------------------- #
# full-snapshot recount (guarded)
# --------------------------------------------------------------------------- #

class TestFullSnapshotRecount:
    @pytest.mark.skipif(not _snapshot_ok(), reason="canonical snapshot absent")
    def test_live_judge_matches_approved_buckets(self, tmp_path):
        out = recount.run(_SNAPSHOT, tmp_path / "impact.json")
        imp = out["impact"]
        assert imp["snapshot_hash_match"] is True
        assert imp["judge_version"] == "canonical-learning-judge-v2"
        assert imp["live_buckets"] == {
            "MALFORMED": 163, "AMBIGUOUS": 731, "EXPLICIT_SUCCESS": 0,
            "EXPLICIT_FAILURE": 0, "UNVERIFIABLE": 41910,
        }
        assert imp["buckets_match_approved"] is True
        assert imp["changed_record_count"] == 1
        assert imp["changed_record_indexes"] == [17147]
        assert imp["newly_accepted_count"] == 0
        assert imp["newly_rejected"] == [17147]

    @pytest.mark.skipif(not _snapshot_ok(), reason="canonical snapshot absent")
    def test_deterministic_rerun(self, tmp_path):
        a = recount.run(_SNAPSHOT, tmp_path / "a.json")["impact"]
        b = recount.run(_SNAPSHOT, tmp_path / "b.json")["impact"]
        assert a == b
        assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()
