"""LC002 track LC-A — current judge divergence matrix (characterization).

Compares three UNCHANGED judges over deterministic hand-authored fixtures:

  A. map_battle_runtime.judge_map_battle_answer_v1   (Adventure + Daily)
  B. Rating Test legacy _rt_parse_answer_tree / _rt_replay core of
     app._rt_server_verify
  C. sgf_engine parser + matcher + autoreply (apply_move steps 2-5 minus the
     override-file load and the Postgres off-tree logger)

No judge is treated as canonical. Every assertion pins the CURRENT verdict of
each judge so a future authority cutover cannot change Go answer semantics
without a test turning red. The narrative matrix and the four isolated
semantic verdicts live in docs/planning/lc002_judge_divergence_matrix.md.

Run: python -m pytest tests/test_lc002_judge_divergence.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures.lc002_judge_fixtures import (  # noqa: E402
    SGF_AMBIGUOUS_REPLY,
    SGF_EMPTY_TREE,
    SGF_LOCAL_TSUMEGO,
    SGF_MALFORMED_GARBAGE,
    SGF_MALFORMED_UNBALANCED,
    SGF_MULTI_MOVE,
    SGF_PLAYER_THEN_REPLY_LEAF,
    SGF_SINGLE_ROOT,
    SGF_TWO_ROOT_BRANCHES,
    SGF_WHOLE_BOARD,
    install_app_import_stubs,
    judge_map_battle,
    judge_rating,
    judge_sgf_engine,
    transform_point,
    xy,
)

install_app_import_stubs()

PD = xy("pd")
DD = xy("dd")
DP = xy("dp")
QF = xy("qf")
QQ = xy("qq")
SB = xy("sb")


# ---------------------------------------------------------------------------
# 1. Full characterization matrix
# ---------------------------------------------------------------------------

# (id, sgf, moves, colour, map_battle_expected, rating_expected, sgf_engine_expected)
MATRIX = [
    (
        "single_correct_root_move",
        SGF_SINGLE_ROOT, [PD], "B",
        ("CORRECT", "answer_tree_leaf"),
        ("CORRECT", "rt_replay"),
        ("continue", "leaf"),
    ),
    (
        "wrong_root_move",
        SGF_SINGLE_ROOT, [DD], "B",
        ("INCORRECT", "off_answer_tree"),
        ("INCORRECT", "rt_replay"),
        ("OFF_TREE", "matcher"),
    ),
    (
        "multi_root_branch_play_first",
        SGF_TWO_ROOT_BRANCHES, [PD], "B",
        ("CORRECT", "answer_tree_leaf"),
        ("CORRECT", "rt_replay"),
        ("continue", "leaf"),
    ),
    (
        "multi_root_branch_play_second",
        SGF_TWO_ROOT_BRANCHES, [DP], "B",
        ("CORRECT", "answer_tree_leaf"),
        ("CORRECT", "rt_replay"),
        ("continue", "leaf"),
    ),
    (
        "multi_root_branch_play_wrong",
        SGF_TWO_ROOT_BRANCHES, [DD], "B",
        ("INCORRECT", "off_answer_tree"),
        ("INCORRECT", "rt_replay"),
        ("OFF_TREE", "matcher"),
    ),
    (
        "multi_move_full_continuation",
        SGF_MULTI_MOVE, [PD, QF], "B",
        ("CORRECT", "answer_tree_leaf"),
        ("CORRECT", "rt_replay"),
        ("continue", "leaf"),
    ),
    (
        "multi_move_only_first_ply",
        SGF_MULTI_MOVE, [PD], "B",
        ("INCORRECT", "partial_answer_sequence"),
        ("INCORRECT", "rt_replay"),
        ("continue", "nonleaf"),
    ),
    (
        "player_move_then_reply_is_leaf",
        SGF_PLAYER_THEN_REPLY_LEAF, [PD], "B",
        ("CORRECT", "answer_tree_reply_leaf"),
        ("CORRECT", "rt_replay"),
        ("continue", "leaf"),
    ),
    (
        "ambiguous_reply_then_continuation",
        SGF_AMBIGUOUS_REPLY, [PD, QF], "B",
        ("INCORRECT", "off_answer_tree"),      # map_battle stays put on ambiguity
        ("CORRECT", "rt_replay"),              # rating blindly takes children[0]
        ("OFF_TREE", "matcher"),               # sgf_engine: autoreply None, move off-tree
    ),
    (
        "wrong_colour_plays_authored_coord",
        SGF_SINGLE_ROOT, [PD], "W",
        ("INCORRECT", "off_answer_tree"),      # only map_battle checks player colour
        ("CORRECT", "rt_replay"),              # rating replay is colour-blind
        ("continue", "leaf"),                  # sgf_engine matcher is colour-blind
    ),
    (
        "whole_board_authored_move",
        SGF_WHOLE_BOARD, [QQ], "B",
        ("CORRECT", "answer_tree_leaf"),
        ("CORRECT", "rt_replay"),
        ("continue", "leaf"),
    ),
    (
        "local_tsumego_authored_move",
        SGF_LOCAL_TSUMEGO, [SB], "B",
        ("CORRECT", "answer_tree_leaf"),
        ("CORRECT", "rt_replay"),
        ("continue", "leaf"),
    ),
    (
        "empty_answer_tree_one_move",
        SGF_EMPTY_TREE, [PD], "B",
        ("INCORRECT", "off_answer_tree"),
        ("NO_VERDICT", "tree_none_client_boolean_trusted"),
        ("OFF_TREE", "matcher"),
    ),
    (
        "empty_answer_tree_zero_moves",
        SGF_EMPTY_TREE, [], "B",
        ("INCORRECT", "partial_answer_sequence"),
        ("NO_VERDICT", "tree_none_client_boolean_trusted"),
        ("continue", "leaf"),
    ),
    (
        "malformed_unbalanced_parens",
        SGF_MALFORMED_UNBALANCED, [PD], "B",
        ("JUDGE_UNAVAILABLE", "JudgeUnavailable"),   # strict parse_sgf raises
        ("CORRECT", "rt_replay"),                    # lenient hand parser accepts
        ("PARSE_FAIL", "Expected ')' at SGF offset 14, found ''."),
    ),
    (
        "malformed_garbage",
        SGF_MALFORMED_GARBAGE, [PD], "B",
        ("JUDGE_UNAVAILABLE", "JudgeUnavailable"),
        ("NO_VERDICT", "tree_none_client_boolean_trusted"),
        ("PARSE_FAIL", "Expected '(' at SGF offset 0, found 'g'."),
    ),
    (
        "empty_move_list_on_valid_tree",
        SGF_SINGLE_ROOT, [], "B",
        ("INCORRECT", "partial_answer_sequence"),
        ("INCORRECT", "rt_replay"),
        ("continue", "nonleaf"),
    ),
]


@pytest.mark.parametrize(
    "sgf,moves,colour,mb_expected",
    [(m[1], m[2], m[3], m[4]) for m in MATRIX],
    ids=[m[0] for m in MATRIX],
)
def test_map_battle_verdicts(sgf, moves, colour, mb_expected):
    assert judge_map_battle(sgf, moves, colour) == mb_expected


@pytest.mark.parametrize(
    "sgf,moves,colour,rt_expected",
    [(m[1], m[2], m[3], m[5]) for m in MATRIX],
    ids=[m[0] for m in MATRIX],
)
def test_rating_verdicts(sgf, moves, colour, rt_expected):
    assert judge_rating(sgf, moves, colour) == rt_expected


@pytest.mark.parametrize(
    "sgf,moves,colour,sgf_expected",
    [(m[1], m[2], m[3], m[6]) for m in MATRIX],
    ids=[m[0] for m in MATRIX],
)
def test_sgf_engine_verdicts(sgf, moves, colour, sgf_expected):
    assert judge_sgf_engine(sgf, moves, colour) == sgf_expected


def test_matrix_divergence_count_is_pinned():
    """Records how many of the fixtures produce a cross-judge disagreement.

    A disagreement = the three normalized verdict *classes* are not all the
    same, where class in {ACCEPT, REJECT, NO_VERDICT/PARSE}. "continue" from
    sgf_engine is NOT an accept.
    """
    def klass(verdict):
        head = verdict[0]
        if head == "CORRECT":
            return "ACCEPT"
        if head in ("INCORRECT", "OFF_TREE"):
            return "REJECT"
        return "OTHER"  # continue / NO_VERDICT / PARSE_FAIL / JUDGE_UNAVAILABLE

    diverging = []
    for row in MATRIX:
        classes = {
            klass(judge_map_battle(row[1], row[2], row[3])),
            klass(judge_rating(row[1], row[2], row[3])),
            klass(judge_sgf_engine(row[1], row[2], row[3])),
        }
        if len(classes) > 1:
            diverging.append(row[0])

    # Pinned by LC002. Only three fixtures produce NO cross-judge class split:
    #  - wrong_root_move / multi_root_branch_play_wrong : all three REJECT
    #  - malformed_garbage                              : all three OTHER
    # The remaining 14 diverge, driven mostly by sgf_engine never emitting
    # ACCEPT and by rating test's blind-first-child / lenient-parser / KataGo
    # behaviours.
    assert len(diverging) == 14
    assert "wrong_root_move" not in diverging
    assert "multi_root_branch_play_wrong" not in diverging
    assert "malformed_garbage" not in diverging
    assert "ambiguous_reply_then_continuation" in diverging
    assert "wrong_colour_plays_authored_coord" in diverging


# ---------------------------------------------------------------------------
# 2. LEAF_SEMANTICS — isolated
# ---------------------------------------------------------------------------

class TestLeafSemantics:
    """map_battle and rating: any childless node reached == CORRECT.
    sgf_engine: a leaf yields status 'continue' (no verdict channel — see
    lc002_sgf_engine_behaviour_report defect #3)."""

    def test_map_battle_accepts_on_player_move_leaf(self):
        assert judge_map_battle(SGF_SINGLE_ROOT, [PD], "B") == (
            "CORRECT", "answer_tree_leaf",
        )

    def test_map_battle_accepts_on_reply_leaf(self):
        assert judge_map_battle(SGF_PLAYER_THEN_REPLY_LEAF, [PD], "B") == (
            "CORRECT", "answer_tree_reply_leaf",
        )

    def test_rating_accepts_on_leaf(self):
        assert judge_rating(SGF_SINGLE_ROOT, [PD], "B") == ("CORRECT", "rt_replay")

    def test_sgf_engine_has_no_leaf_verdict(self):
        status, shape = judge_sgf_engine(SGF_SINGLE_ROOT, [PD], "B")
        assert shape == "leaf"
        assert status == "continue"           # NOT "correct"
        assert status not in ("correct", "CORRECT")

    def test_leaf_semantics_verdict_is_DIFFERENT(self):
        mb = judge_map_battle(SGF_SINGLE_ROOT, [PD], "B")[0]
        rt = judge_rating(SGF_SINGLE_ROOT, [PD], "B")[0]
        sgf = judge_sgf_engine(SGF_SINGLE_ROOT, [PD], "B")[0]
        assert mb == "CORRECT" and rt == "CORRECT"
        assert sgf == "continue"
        assert {mb, sgf} == {"CORRECT", "continue"}   # DIFFERENT


# ---------------------------------------------------------------------------
# 3. AMBIGUOUS_AUTOREPLY — isolated
# ---------------------------------------------------------------------------

class TestAmbiguousAutoreply:
    """After B[pd] the tree offers TWO white replies.

    map_battle  _auto_reply: len(children) != 1 -> stay on the pre-reply node
    rating      _rt_replay : reply = children[0] unconditionally (blind pick)
    sgf_engine  get_auto_reply: len(children) != 1 -> None (do not advance)
    """

    def test_map_battle_stays_and_then_rejects_continuation(self):
        assert judge_map_battle(SGF_AMBIGUOUS_REPLY, [PD, QF], "B") == (
            "INCORRECT", "off_answer_tree",
        )

    def test_rating_blindly_follows_first_branch_and_accepts(self):
        assert judge_rating(SGF_AMBIGUOUS_REPLY, [PD, QF], "B") == (
            "CORRECT", "rt_replay",
        )

    def test_sgf_engine_does_not_advance_then_move_is_off_tree(self):
        assert judge_sgf_engine(SGF_AMBIGUOUS_REPLY, [PD, QF], "B") == (
            "OFF_TREE", "matcher",
        )

    def test_ambiguous_autoreply_verdict_is_DIFFERENT(self):
        mb = judge_map_battle(SGF_AMBIGUOUS_REPLY, [PD, QF], "B")[0]
        rt = judge_rating(SGF_AMBIGUOUS_REPLY, [PD, QF], "B")[0]
        sgf = judge_sgf_engine(SGF_AMBIGUOUS_REPLY, [PD, QF], "B")[0]
        assert (mb, rt, sgf) == ("INCORRECT", "CORRECT", "OFF_TREE")


# ---------------------------------------------------------------------------
# 4. TRANSFORM_SEMANTICS — isolated
# ---------------------------------------------------------------------------

class TestTransformSemantics:
    """map_battle and rating share the SAME 8-entry transform table
    (byte-identical lambdas). Both accept the transformed correct move for
    every t. sgf_engine has no transform concept at all."""

    @pytest.mark.parametrize("t", list(range(8)))
    def test_map_battle_and_rating_agree_on_transformed_correct_move(self, t):
        tp = transform_point(PD[0], PD[1], 19, t)
        mb = judge_map_battle(
            SGF_SINGLE_ROOT, [tp], "B",
            transform_id="identity" if t == 0 else f"t{t}",
        )
        rt = judge_rating(SGF_SINGLE_ROOT, [tp], "B", transform=t)
        assert mb[0] == "CORRECT"
        assert rt[0] == "CORRECT"

    def test_sgf_engine_has_no_transform_input(self):
        # judge_sgf_engine takes no transform argument; it is out of scope.
        import inspect

        sig = inspect.signature(judge_sgf_engine)
        assert "transform" not in sig.parameters

    def test_transform_semantics_verdict_is_CONSISTENT_between_the_two_that_have_it(self):
        for t in range(8):
            tp = transform_point(PD[0], PD[1], 19, t)
            mb = judge_map_battle(
                SGF_SINGLE_ROOT, [tp], "B",
                transform_id="identity" if t == 0 else f"t{t}",
            )[0]
            rt = judge_rating(SGF_SINGLE_ROOT, [tp], "B", transform=t)[0]
            assert mb == rt == "CORRECT"


# ---------------------------------------------------------------------------
# 5. ACCEPTED_MOVE_SEMANTICS — isolated (the transform-space bug)
# ---------------------------------------------------------------------------

class TestAcceptedMoveSemantics:
    """Question SGF answer is B[pd]; a reviewer-accepted alternative is dd.
    The client is served the *displayed* (transformed) accepted coordinate by
    app._strip_question and plays it back.

      map_battle _accepted_moves : applies _transform_point to stored coords
                                   -> compares in the SAME (display) space  -> CORRECT for all t
      rating _rt_server_verify   : compares stored coords UNTRANSFORMED      -> only t where
                                   dd is transform-invariant (0 and 6) agree
    """

    ACCEPTED = [{"x": DD[0], "y": DD[1]}]

    @pytest.mark.parametrize("t", list(range(8)))
    def test_map_battle_accepts_the_displayed_alternative_for_every_transform(self, t):
        displayed = transform_point(DD[0], DD[1], 19, t)
        assert judge_map_battle(
            SGF_SINGLE_ROOT, [displayed], "B",
            transform_id="identity" if t == 0 else f"t{t}",
            accepted=self.ACCEPTED,
        ) == ("CORRECT", "accepted_authoritative_alternative")

    @pytest.mark.parametrize(
        "t,expected_head",
        [
            (0, "CORRECT"),
            (1, "INCORRECT"),
            (2, "INCORRECT"),
            (3, "INCORRECT"),
            (4, "INCORRECT"),
            (5, "INCORRECT"),
            (6, "CORRECT"),   # dd == (3,3) is invariant under transpose (t=6)
            (7, "INCORRECT"),
        ],
    )
    def test_rating_rejects_the_displayed_alternative_when_transform_moves_it(
        self, t, expected_head
    ):
        displayed = transform_point(DD[0], DD[1], 19, t)
        assert judge_rating(
            SGF_SINGLE_ROOT, [displayed], "B", transform=t, accepted=self.ACCEPTED
        )[0] == expected_head

    def test_accepted_move_semantics_verdict_is_DIFFERENT(self):
        # for t=1 the two judges disagree on a legitimately-accepted move
        displayed = transform_point(DD[0], DD[1], 19, 1)
        mb = judge_map_battle(
            SGF_SINGLE_ROOT, [displayed], "B", transform_id="t1", accepted=self.ACCEPTED
        )[0]
        rt = judge_rating(
            SGF_SINGLE_ROOT, [displayed], "B", transform=1, accepted=self.ACCEPTED
        )[0]
        assert (mb, rt) == ("CORRECT", "INCORRECT")


# ---------------------------------------------------------------------------
# 6. KATAGO additive tolerance — rating test only
# ---------------------------------------------------------------------------

class TestKatagoTolerance:
    """A single off-tree move equal to the stored katago_best_move:
    rating test accepts it additively; the other two do not know KataGo."""

    KATAGO_GTP = "D4"          # -> (3, 15) on 19x19
    OFF_TREE_XY = (3, 15)

    def test_rating_accepts_off_tree_move_matching_katago_best(self):
        assert judge_rating(
            SGF_SINGLE_ROOT, [self.OFF_TREE_XY], "B",
            katago_best_move=self.KATAGO_GTP,
        ) == ("CORRECT", "katago_best_move_tolerance")

    def test_map_battle_rejects_that_same_move(self):
        assert judge_map_battle(SGF_SINGLE_ROOT, [self.OFF_TREE_XY], "B") == (
            "INCORRECT", "off_answer_tree",
        )

    def test_sgf_engine_rejects_that_same_move(self):
        assert judge_sgf_engine(SGF_SINGLE_ROOT, [self.OFF_TREE_XY], "B") == (
            "OFF_TREE", "matcher",
        )


# ---------------------------------------------------------------------------
# 7. Parser leniency divergence
# ---------------------------------------------------------------------------

class TestParserLeniencyDivergence:
    def test_rating_hand_parser_accepts_unbalanced_sgf_that_strict_rejects(self):
        assert judge_rating(SGF_MALFORMED_UNBALANCED, [PD], "B") == (
            "CORRECT", "rt_replay",
        )
        assert judge_map_battle(SGF_MALFORMED_UNBALANCED, [PD], "B")[0] == (
            "JUDGE_UNAVAILABLE"
        )
        assert judge_sgf_engine(SGF_MALFORMED_UNBALANCED, [PD], "B")[0] == "PARSE_FAIL"
