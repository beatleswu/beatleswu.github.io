"""LC007 — terminal-verdict marker semantics + false-positive elimination.

Proves:
  * the record-8023 false positive (a success token matched as an unanchored
    substring inside explanatory prose) reproduces under the current policy;
  * every candidate safe policy (B / C / D / RECOMMENDED) refuses it;
  * an adversarial corpus of 正解-in-prose comments yields ZERO explanatory
    false positives under the safe policies;
  * the fail-closed invariants hold (bare leaf, unknown marker → never success);
  * Policy A is a faithful reproduction of the live judge primitive;
  * the simulation is deterministic on rerun.

The real 42,804-record snapshot is untracked; tests that need it are guarded
on its presence + hash and otherwise skipped. The logic is fully exercised on
synthetic records.
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

import tools.lc007_marker_policy_simulation as sim  # noqa: E402
from canonical_learning_judge import _explicit_terminal_is_correct  # noqa: E402
from sgf_engine.parser.sgf_parser import parse_sgf  # noqa: E402

_SNAPSHOT = Path("D:/go-website/questions.json")
_SNAPSHOT_SHA = "88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff"


def _snapshot_available() -> bool:
    if not _SNAPSHOT.exists():
        return False
    return hashlib.sha256(_SNAPSHOT.read_bytes()).hexdigest() == _SNAPSHOT_SHA


# 8023-shaped: two root W[ob] variations. Variation 1 = the solution, first move
# labelled N[正解], terminal bare. Variation 2 = the reference line, first move
# N[参考], terminal comment is a comparison sentence that mentions 正解 as a noun.
SGF_8023_SHAPED = (
    "(;GM[1]FF[4]SZ[19]PL[W]"
    "AB[mc][md][me][nc][ne][od][pd][qc][rc][sc]"
    "AW[lc][ld][le][mb][mf][nf][oe][pe][qd][qf][rd][sd]"
    "(;W[ob]N[正解];B[nb];W[oc];B[pc];W[na];B[nd];W[kb];B[pb];W[oa];B[pa];W[ma];B[ra])"
    "(;W[ob]N[参考];B[oc];W[pb];B[pc];W[nb];B[qb]C[黑地虽然和正解一样，但白增加4目。])"
    ")"
)

# adversarial terminal comments (LC007 §5). must_not_be_success is the hard
# requirement; "ideal" is the nicer-to-have bucket.
ADVERSARIAL = [
    # clean success labels — SHOULD be success under an anchored policy
    ("正解", False, "SUCCESS"),
    ("　正解　", False, "SUCCESS"),
    ("【正解】", False, "SUCCESS"),
    ("（正解）", False, "SUCCESS"),
    ("「正解」", False, "SUCCESS"),
    ("正解。", False, "SUCCESS"),
    ("正解！", False, "SUCCESS"),
    ("正解\n", False, "SUCCESS"),
    ("正解：", False, "SUCCESS"),
    ("正解？", True, "NONE"),   # interrogative -> not an assertion (LC7-E)
    ("成功", False, "SUCCESS"),
    ("correct", False, "SUCCESS"),
    ("success", False, "SUCCESS"),
    # explanatory / reference prose — MUST NOT be success
    ("正解です", True, "NONE"),
    ("これは正解", True, "NONE"),
    ("正解と同じ", True, "NONE"),
    ("正解より悪い", True, "NONE"),
    ("黒地は正解と同じだが白が4目増える", True, "NONE"),
    ("黑地虽然和正解一样，但白增加4目。", True, "NONE"),
    ("参考：正解では...", True, "NONE"),
    ("正解図参照", True, "NONE"),
    ("正解と同じ figure", True, "NONE"),
    ("正解ではない", True, "NONE"),
    ("not the correct answer", True, "NONE"),
    # explicit failure prose — MUST NOT be success
    ("不正解", True, "FAILURE"),
    ("これは不正解です", True, "NONE_OR_FAILURE"),
    ("incorrect", True, "FAILURE"),
    ("×", True, "FAILURE"),
]

SAFE_POLICIES = ("B", "C", "D", "RECOMMENDED")


def _leaf(sgf: str):
    """Parse a one-line SGF and return its single reachable terminal node."""
    root = parse_sgf(sgf, strict=True)
    node = root
    while node.children:
        node = node.children[0]
    return node


# --------------------------------------------------------------------------- #
# the live judge implements the RECOMMENDED model (LC009); Policy A is the
# frozen pre-LC009 substring reference and now deliberately diverges on prose
# --------------------------------------------------------------------------- #

class TestLiveJudgeMatchesRecommendedModel:
    @pytest.mark.parametrize("sgf", [
        "(;GM[1]SZ[19];B[qq];W[pp];B[cc])",                       # bare -> None
        "(;GM[1]SZ[19];B[qq];W[pp];B[cc]RE[B+R])",                # decisive RE -> True
        "(;GM[1]SZ[19];B[qq];W[pp];B[cc]RE[Void])",               # non-decisive RE -> None
        "(;GM[1]SZ[19];B[qq];W[pp];B[cc]RE[wrong])",              # failure RE -> False
        "(;GM[1]SZ[19];B[qq];W[pp];B[cc]TE[1])",                  # TE -> True
        "(;GM[1]SZ[19];B[qq];W[pp];B[cc]C[正解])",                # exact comment -> True
        "(;GM[1]SZ[19];B[qq];W[pp];B[cc]C[失敗])",                # exact failure -> False
        "(;GM[1]SZ[19];B[qq];W[pp];B[cc]C[黑地和正解一样，白多4目])",  # prose -> None
        "(;GM[1]SZ[19];B[qq];W[pp];B[cc]C[不正解])",              # exact 不正解 -> False
        "(;GM[1]SZ[19];B[qq];W[pp];B[cc]N[正解])",                # exact N -> True
        "(;GM[1]SZ[19];B[qq];W[pp];B[cc]N[参考])",                # N reference -> None
    ])
    def test_live_judge_equals_sim_recommended(self, sgf):
        leaf = _leaf(sgf)
        assert sim.verdict_recommended(leaf) is _explicit_terminal_is_correct(leaf)

    def test_policy_a_is_frozen_presubstring_reference(self):
        # Policy A still exhibits the OLD unanchored-substring behaviour the live
        # judge has now moved away from -- kept only as the impact baseline.
        prose = _leaf("(;GM[1]SZ[19];B[qq];W[pp];B[cc]C[黑地和正解一样，白多4目])")
        assert sim.verdict_policy_a(prose) is True
        assert _explicit_terminal_is_correct(prose) is None


# --------------------------------------------------------------------------- #
# record 8023 false positive
# --------------------------------------------------------------------------- #

class TestRecord8023:
    def test_current_policy_reproduces_false_positive(self):
        assert sim.bucket_for(SGF_8023_SHAPED, sim.POLICIES["A"]) == "EXPLICIT_SUCCESS"

    @pytest.mark.parametrize("policy", SAFE_POLICIES)
    def test_safe_policies_refuse_it(self, policy):
        assert sim.bucket_for(SGF_8023_SHAPED, sim.POLICIES[policy]) != "EXPLICIT_SUCCESS"
        assert sim.bucket_for(SGF_8023_SHAPED, sim.POLICIES[policy]) == "UNVERIFIABLE"

    def test_reference_variation_terminal_is_not_success_under_safe_policies(self):
        root = parse_sgf(SGF_8023_SHAPED, strict=True)
        ref_terminal = root.children[1]
        while ref_terminal.children:
            ref_terminal = ref_terminal.children[0]
        assert ref_terminal.move.coord == "qb"
        assert sim.verdict_policy_a(ref_terminal) is True           # the defect
        for p in SAFE_POLICIES:
            assert sim.POLICIES[p](ref_terminal) is not True

    @pytest.mark.skipif(not _snapshot_available(), reason="canonical snapshot absent")
    def test_real_record_8023(self):
        records = json.loads(_SNAPSHOT.read_bytes())
        rec = records[17147]
        assert rec["id"] == 8023
        assert sim.bucket_for(rec["content"], sim.POLICIES["A"]) == "EXPLICIT_SUCCESS"
        for p in SAFE_POLICIES:
            assert sim.bucket_for(rec["content"], sim.POLICIES[p]) == "UNVERIFIABLE"


# --------------------------------------------------------------------------- #
# adversarial marker corpus (LC007 §5)
# --------------------------------------------------------------------------- #

class TestAdversarialMarkerCorpus:
    @pytest.mark.parametrize("comment,must_not_be_success,ideal", ADVERSARIAL)
    def test_anchored_comment_verdict(self, comment, must_not_be_success, ideal):
        v = sim._anchored_comment_verdict(sim._norm(comment))
        if must_not_be_success:
            assert v is not True, f"{comment!r} became SUCCESS under anchored policy"
        if ideal == "SUCCESS":
            assert v is True
        elif ideal == "FAILURE":
            assert v is False
        elif ideal == "NONE":
            assert v is None

    def test_zero_explanatory_reference_false_positives(self):
        explanatory = [c for (c, must_not, _) in ADVERSARIAL if must_not and "不正解" not in c
                       and c not in ("incorrect", "×")]
        fps = [c for c in explanatory if sim._anchored_comment_verdict(sim._norm(c)) is True]
        assert fps == [], f"explanatory-reference false positives: {fps}"

    @pytest.mark.parametrize("comment,must_not_be_success,_ideal", ADVERSARIAL)
    def test_full_policy_bucket_never_wrongly_succeeds(self, comment, must_not_be_success, _ideal):
        sgf = f"(;GM[1]SZ[19];B[qq];W[pp];B[cc]C[{comment.strip()}])"
        try:
            parse_sgf(sgf, strict=True)
        except Exception:
            pytest.skip("comment not SGF-embeddable verbatim")
        for p in SAFE_POLICIES:
            b = sim.bucket_for(sgf, sim.POLICIES[p])
            if must_not_be_success:
                assert b != "EXPLICIT_SUCCESS", f"{comment!r} -> {b} under {p}"


# --------------------------------------------------------------------------- #
# fail-closed invariants (LC007 §8)
# --------------------------------------------------------------------------- #

class TestFailClosedInvariants:
    @pytest.mark.parametrize("policy", ("A",) + SAFE_POLICIES)
    def test_bare_leaf_never_correct(self, policy):
        leaf = _leaf("(;GM[1]SZ[19];B[qq];W[pp];B[cc])")
        assert sim.POLICIES[policy](leaf) is not True

    @pytest.mark.parametrize("policy", SAFE_POLICIES)
    def test_unknown_markers_fail_closed(self, policy):
        for prop in ("GB[1]", "GW[1]", "BM[1]", "DO[]", "N[参考]", "N[bad]", "TR[qq]", "LB[qq:A]"):
            leaf = _leaf(f"(;GM[1]SZ[19];B[qq];W[pp];B[cc]{prop})")
            assert sim.POLICIES[policy](leaf) is not True, f"{prop} became success under {policy}"

    def test_substring_only_success_is_gone_under_recommended(self):
        # the exact shape of the 8023 defect: token as a substring of prose
        leaf = _leaf("(;GM[1]SZ[19];B[qq];W[pp];B[cc]C[白は正解より2目多い])")
        assert sim.verdict_policy_a(leaf) is True
        assert sim.verdict_recommended(leaf) is None


# --------------------------------------------------------------------------- #
# node-name policy C
# --------------------------------------------------------------------------- #

class TestPolicyCNodeName:
    def test_exact_terminal_name_success(self):
        leaf = _leaf("(;GM[1]SZ[19];B[qq];W[pp];B[cc]N[正解])")
        assert sim.verdict_policy_c(leaf) is True
        assert sim.verdict_recommended(leaf) is True

    def test_name_on_nonterminal_is_ignored(self):
        # N[正解] on move 1, terminal bare -> C must not call it success
        assert sim.bucket_for(
            "(;GM[1]SZ[19];B[qq]N[正解];W[pp];B[cc])", sim.POLICIES["C"]
        ) == "UNVERIFIABLE"

    def test_reference_name_not_success(self):
        leaf = _leaf("(;GM[1]SZ[19];B[qq];W[pp];B[cc]N[参考])")
        assert sim.verdict_policy_c(leaf) is not True


# --------------------------------------------------------------------------- #
# determinism + accounting
# --------------------------------------------------------------------------- #

class TestSimulationProperties:
    def _mini(self):
        return [
            {"id": 1, "content": "(;GM[1]SZ[19];B[qq];W[pp];B[cc])"},
            {"id": 2, "content": SGF_8023_SHAPED},
            {"id": 3, "content": "(;GM[1]SZ[19];B[qq];W[pp];B[cc]N[正解])"},
            {"id": 4, "content": "(;GM[1]SZ[19];B[qq];W["},                       # malformed
            {"id": 5, "content": "(;GM[1]SZ[19];B[qq];W[pp](;B[cc])(;B[dd]))"},   # ambiguous shape
        ]

    def test_deterministic_rerun(self):
        a = sim.simulate(self._mini())
        b = sim.simulate(self._mini())
        assert a["per_policy_bucket"] == b["per_policy_bucket"]
        assert a["diffs"] == b["diffs"]
        assert a["changed_rows"] == b["changed_rows"]

    def test_buckets_partition_all_records(self):
        out = sim.simulate(self._mini())
        for policy, buckets in out["per_policy_bucket"].items():
            assert sum(buckets.values()) == 5, policy

    def test_8023_shape_is_the_only_newly_rejected(self):
        # index 1 == the 8023-shaped record (unanchored substring false positive);
        # index 2 == a synthetic terminal N[正解], legitimately gained by C/RECOMMENDED.
        out = sim.simulate(self._mini())
        for p in SAFE_POLICIES:
            assert out["diffs"][p]["newly_rejected"] == [1], p
        assert out["diffs"]["B"]["newly_accepted"] == []
        assert out["diffs"]["D"]["newly_accepted"] == []
        assert out["diffs"]["C"]["newly_accepted"] == [2]
        assert out["diffs"]["RECOMMENDED"]["newly_accepted"] == [2]

    @pytest.mark.skipif(not _snapshot_available(), reason="canonical snapshot absent")
    def test_full_snapshot_policy_simulation(self, tmp_path):
        out = sim.build_report(_SNAPSHOT, tmp_path / "impact.json")
        imp = out["impact"]
        assert imp["snapshot_hash_match"] is True
        assert imp["record_count"] == 42804
        assert imp["current_explicit_success_count"] == 1
        assert imp["recommended_explicit_success_count"] == 0
        for p in SAFE_POLICIES:
            d = imp["diffs_vs_current"][p]
            assert d["newly_accepted_count"] == 0
            assert d["changed_from_current"] == [17147]
        # every safe policy leaves MALFORMED / AMBIGUOUS untouched
        for p in ("A",) + SAFE_POLICIES:
            assert imp["per_policy_bucket"][p]["MALFORMED"] == 163
            assert imp["per_policy_bucket"][p]["AMBIGUOUS"] == 731
