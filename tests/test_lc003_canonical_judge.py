"""LC003 — canonical_learning_judge behaviour + authority contract.

Groups (LC003 task section 20):
  A canonical judge result contract
  B malformed / parse failure fail-closed
  C ambiguous auto-reply fail-closed
  D leaf semantics fail-closed until explicit verdict
  E player colour enforced
  F all 8 transforms resolve consistently
  G accepted alternatives (server/content authority; client cannot declare)
  + resolve_srs_review_authority adapter unit behaviour (attempt vs no-attempt)

Pure — no Flask, no DB. Run:
  python -m pytest tests/test_lc003_canonical_judge.py -q
"""

from __future__ import annotations

import pytest

from canonical_learning_judge import (
    Attempt,
    AuthorityResolution,
    GradeBasis,
    JudgeInputError,
    JudgeResult,
    JudgeStatus,
    _mb_transform_point,
    judge_answer,
    resolve_srs_review_authority,
)


def xy(coord: str) -> tuple[int, int]:
    return ord(coord[0]) - 97, ord(coord[1]) - 97


def mk(moves, colour="B", transform="identity", board_size=None) -> Attempt:
    return Attempt.from_payload(
        {
            "moves": [{"x": x, "y": y} for (x, y) in moves],
            "player_color": colour,
            "transform": transform,
            **({"board_size": board_size} if board_size is not None else {}),
        }
    )


# hand-authored fixtures
SGF_LEAF_BARE = "(;SZ[19];B[pd])"                          # childless, no marker
SGF_LEAF_RE_OK = "(;SZ[19];B[pd]RE[Correct])"             # explicit correct
SGF_LEAF_RE_FAIL = "(;SZ[19];B[pd]RE[wrong])"            # explicit failure
SGF_LEAF_TE = "(;SZ[19];B[pd]TE[1])"                     # tesuji marker
SGF_LEAF_COMMENT_OK = "(;SZ[19];B[pd]C[正解])"            # success comment token
SGF_UNIQUE_REPLY = "(;SZ[19];B[pd];W[dd];B[qf]RE[Correct])"
SGF_AMBIGUOUS = "(;SZ[19];B[pd](;W[dd];B[qf]RE[Correct])(;W[dp];B[cf]RE[Correct]))"
SGF_TWO_ROOT_BRANCHES = "(;SZ[19](;B[pd]RE[Correct])(;B[dp]RE[Correct]))"
SGF_MALFORMED = "(;SZ[19];B[pd]"
SGF_GARBAGE = "not an sgf"
SGF_WHITE_TO_PLAY = "(;SZ[19];W[dd]RE[Correct])"


# ---------------------------------------------------------------------------
# A — result contract
# ---------------------------------------------------------------------------

class TestResultContract:
    def test_all_six_statuses_exist_and_are_distinct(self):
        names = {s.value for s in JudgeStatus}
        assert names == {
            "CORRECT", "INCORRECT", "CONTINUE",
            "AMBIGUOUS", "UNVERIFIABLE", "MALFORMED",
        }

    def test_fail_closed_statuses_are_not_verdicts(self):
        for s in (JudgeStatus.AMBIGUOUS, JudgeStatus.UNVERIFIABLE, JudgeStatus.MALFORMED):
            r = JudgeResult(s, "x")
            assert r.is_fail_closed is True
            assert r.is_verdict is False
            assert r.is_correct is False

    def test_verdict_statuses(self):
        assert JudgeResult(JudgeStatus.CORRECT, "x").is_verdict
        assert JudgeResult(JudgeStatus.INCORRECT, "x").is_verdict
        assert JudgeResult(JudgeStatus.CONTINUE, "x").is_verdict
        assert JudgeResult(JudgeStatus.CORRECT, "x").is_correct
        assert not JudgeResult(JudgeStatus.CONTINUE, "x").is_correct

    def test_result_carries_reason_transform_and_path(self):
        r = judge_answer(question_content=SGF_UNIQUE_REPLY, attempt=mk([xy("pd"), xy("qf")]))
        assert r.status is JudgeStatus.CORRECT
        assert r.reason_code
        assert r.transform_index == 0
        assert r.matched_path == ("pd", "dd", "qf")
        assert r.player_color == "B"
        assert r.judge_version == "canonical-learning-judge-v1"

    def test_status_ambiguous_unverifiable_malformed_are_not_collapsed(self):
        amb = judge_answer(question_content=SGF_AMBIGUOUS, attempt=mk([xy("pd"), xy("qf")]))
        unv = judge_answer(question_content=SGF_LEAF_BARE, attempt=mk([xy("pd")]))
        mal = judge_answer(question_content=SGF_MALFORMED, attempt=mk([xy("pd")]))
        assert (amb.status, unv.status, mal.status) == (
            JudgeStatus.AMBIGUOUS, JudgeStatus.UNVERIFIABLE, JudgeStatus.MALFORMED,
        )
        assert len({amb.status, unv.status, mal.status}) == 3


# ---------------------------------------------------------------------------
# B — malformed / parse failure fail-closed
# ---------------------------------------------------------------------------

class TestMalformedFailClosed:
    @pytest.mark.parametrize("content,expected", [
        (SGF_MALFORMED, JudgeStatus.MALFORMED),
        (SGF_GARBAGE, JudgeStatus.MALFORMED),
        ("(;SZ[19];B[pd];W[dd]", JudgeStatus.MALFORMED),   # truncated
        ("", JudgeStatus.UNVERIFIABLE),                    # missing SGF
        ("   ", JudgeStatus.UNVERIFIABLE),
    ])
    def test_bad_sgf_never_becomes_correct(self, content, expected):
        r = judge_answer(question_content=content, attempt=mk([xy("pd")]))
        assert r.status is expected
        assert r.is_fail_closed
        assert not r.is_correct

    def test_invalid_move_coordinate_is_malformed(self):
        r = judge_answer(
            question_content=SGF_LEAF_RE_OK,
            attempt=mk([(50, 50)]),   # off a 19x19 board
        )
        assert r.status is JudgeStatus.MALFORMED
        assert r.reason_code == "move_coordinate_out_of_bounds"

    def test_unsupported_transform_is_unverifiable_not_correct(self):
        r = judge_answer(
            question_content=SGF_LEAF_RE_OK,
            attempt=mk([xy("pd")], transform="rotate-99"),
        )
        assert r.status is JudgeStatus.UNVERIFIABLE
        assert r.reason_code == "unsupported_transform"

    def test_no_moves_submitted_is_unverifiable(self):
        r = judge_answer(question_content=SGF_LEAF_RE_OK, attempt=mk([]))
        assert r.status is JudgeStatus.UNVERIFIABLE
        assert r.reason_code == "no_moves_submitted"

    def test_a_correct_looking_client_cannot_smuggle_a_verdict_field(self):
        for bad in ("grade", "correct", "result", "verdict", "judge_result"):
            with pytest.raises(JudgeInputError):
                Attempt.from_payload({"moves": [], "player_color": "B", bad: True})


# ---------------------------------------------------------------------------
# C — ambiguous auto-reply fail-closed (NO blind children[0])
# ---------------------------------------------------------------------------

class TestAmbiguousAutoreplyFailClosed:
    def test_two_opponent_replies_yield_ambiguous_not_a_guess(self):
        r = judge_answer(question_content=SGF_AMBIGUOUS, attempt=mk([xy("pd"), xy("qf")]))
        assert r.status is JudgeStatus.AMBIGUOUS
        assert r.reason_code == "ambiguous_autoreply"
        assert not r.is_correct

    def test_ambiguous_even_when_first_branch_would_have_validated(self):
        # LC002 proved rating test accepts this by blindly taking children[0].
        # The canonical judge must not.
        r = judge_answer(question_content=SGF_AMBIGUOUS, attempt=mk([xy("pd"), xy("qf")]))
        assert r.status is JudgeStatus.AMBIGUOUS

    def test_single_non_opponent_child_is_not_a_valid_autoreply(self):
        # after B[pd] the only child is another Black move -> no unique
        # opponent reply -> ambiguous / unverifiable, never advance.
        sgf = "(;SZ[19];B[pd];B[qf]RE[Correct])"
        r = judge_answer(question_content=sgf, attempt=mk([xy("pd"), xy("qf")]))
        assert r.status in (JudgeStatus.AMBIGUOUS,)
        assert r.reason_code in ("ambiguous_autoreply", "no_unique_autoreply")

    def test_unique_opponent_reply_is_followed(self):
        r = judge_answer(question_content=SGF_UNIQUE_REPLY, attempt=mk([xy("pd"), xy("qf")]))
        assert r.status is JudgeStatus.CORRECT
        assert "dd" in r.matched_path


# ---------------------------------------------------------------------------
# D — leaf semantics: fail closed until explicit verdict
# ---------------------------------------------------------------------------

class TestLeafFailClosed:
    def test_bare_childless_leaf_is_unverifiable_not_correct(self):
        r = judge_answer(question_content=SGF_LEAF_BARE, attempt=mk([xy("pd")]))
        assert r.status is JudgeStatus.UNVERIFIABLE
        assert r.reason_code == "leaf_without_explicit_verdict"
        assert not r.is_correct

    def test_bare_leaf_stays_unverifiable_even_if_client_would_say_correct(self):
        # the judge has no client input at all; documented here for intent
        r = judge_answer(question_content=SGF_TWO_ROOT_BRANCHES.replace("RE[Correct]", ""),
                         attempt=mk([xy("pd")]))
        assert r.status is JudgeStatus.UNVERIFIABLE

    @pytest.mark.parametrize("content", [SGF_LEAF_RE_OK, SGF_LEAF_TE, SGF_LEAF_COMMENT_OK])
    def test_explicit_success_marker_yields_correct(self, content):
        r = judge_answer(question_content=content, attempt=mk([xy("pd")]))
        assert r.status is JudgeStatus.CORRECT

    def test_explicit_failure_marker_yields_incorrect(self):
        r = judge_answer(question_content=SGF_LEAF_RE_FAIL, attempt=mk([xy("pd")]))
        assert r.status is JudgeStatus.INCORRECT
        assert r.reason_code == "explicit_terminal_failure"

    def test_reply_leaf_without_marker_is_unverifiable(self):
        sgf = "(;SZ[19];B[pd];W[dd])"   # after autoreply W[dd] is a bare leaf
        r = judge_answer(question_content=sgf, attempt=mk([xy("pd")]))
        assert r.status is JudgeStatus.UNVERIFIABLE
        assert r.reason_code == "reply_leaf_without_explicit_verdict"

    def test_partial_sequence_is_continue_not_correct_not_incorrect(self):
        r = judge_answer(question_content=SGF_UNIQUE_REPLY, attempt=mk([xy("pd")]))
        assert r.status is JudgeStatus.CONTINUE
        assert r.reason_code == "valid_partial_sequence"


# ---------------------------------------------------------------------------
# E — player colour enforced
# ---------------------------------------------------------------------------

class TestPlayerColour:
    def test_correct_coord_wrong_colour_is_rejected(self):
        # SGF authored B[pd]; client claims to be White playing pd.
        # LC004 made the expected colour server-authored, so this is now
        # rejected because the server independently determined B-to-play,
        # not merely because the move missed. Either way: INCORRECT, not a pass.
        r = judge_answer(question_content=SGF_LEAF_RE_OK, attempt=mk([xy("pd")], colour="W"))
        assert r.status is JudgeStatus.INCORRECT
        assert r.reason_code in ("off_answer_tree", "player_color_contradicts_server")
        assert not r.is_correct

    def test_correct_coord_correct_colour_passes(self):
        r = judge_answer(question_content=SGF_LEAF_RE_OK, attempt=mk([xy("pd")], colour="B"))
        assert r.status is JudgeStatus.CORRECT

    def test_white_to_play_question_accepts_white(self):
        r = judge_answer(question_content=SGF_WHITE_TO_PLAY, attempt=mk([xy("dd")], colour="W"))
        assert r.status is JudgeStatus.CORRECT

    def test_white_to_play_question_rejects_black_at_same_point(self):
        r = judge_answer(question_content=SGF_WHITE_TO_PLAY, attempt=mk([xy("dd")], colour="B"))
        assert r.status is JudgeStatus.INCORRECT

    def test_attempt_rejects_missing_or_bad_colour(self):
        with pytest.raises(JudgeInputError):
            Attempt.from_payload({"moves": [], "player_color": "green"})
        with pytest.raises(JudgeInputError):
            Attempt.from_payload({"moves": []})


# ---------------------------------------------------------------------------
# F — all 8 transforms resolve consistently
# ---------------------------------------------------------------------------

class TestAllEightTransforms:
    CANONICAL = "(;SZ[19];B[pd]RE[Correct])"       # canonical answer = pd
    CANONICAL_MULTI = "(;SZ[19];B[pd];W[dd];B[qf]RE[Correct])"

    @pytest.mark.parametrize("t", list(range(8)))
    def test_transformed_correct_move_is_correct_for_every_transform(self, t):
        disp = _mb_transform_point(*xy("pd"), 19, t)
        r = judge_answer(
            question_content=self.CANONICAL,
            attempt=mk([disp], transform="identity" if t == 0 else f"t{t}"),
        )
        assert r.status is JudgeStatus.CORRECT, f"t={t} disp={disp} -> {r.status}"
        assert r.transform_index == t

    @pytest.mark.parametrize("t", list(range(8)))
    def test_transformed_wrong_move_is_incorrect_for_every_transform(self, t):
        disp = _mb_transform_point(*xy("qq"), 19, t)   # not the answer
        r = judge_answer(
            question_content=self.CANONICAL,
            attempt=mk([disp], transform="identity" if t == 0 else f"t{t}"),
        )
        assert r.status is JudgeStatus.INCORRECT

    @pytest.mark.parametrize("t", list(range(8)))
    def test_transformed_multi_move_line_is_correct_for_every_transform(self, t):
        seq = [_mb_transform_point(*xy(c), 19, t) for c in ("pd", "qf")]
        r = judge_answer(
            question_content=self.CANONICAL_MULTI,
            attempt=mk(seq, transform="identity" if t == 0 else f"t{t}"),
        )
        assert r.status is JudgeStatus.CORRECT, f"t={t} -> {r.status}/{r.reason_code}"

    @pytest.mark.parametrize("t", list(range(8)))
    def test_accepted_alternative_resolves_for_every_transform(self, t):
        # canonical answer is pd; reviewer accepts dd as an alternative.
        # client is served (and plays) the DISPLAY-space dd.
        disp = _mb_transform_point(*xy("dd"), 19, t)
        r = judge_answer(
            question_content=self.CANONICAL,
            attempt=mk([disp], transform="identity" if t == 0 else f"t{t}"),
            accepted_moves=[{"x": xy("dd")[0], "y": xy("dd")[1]}],
        )
        assert r.status is JudgeStatus.CORRECT, f"t={t} disp={disp} -> {r.status}"
        assert r.reason_code == "accepted_authoritative_alternative"

    def test_all_8_transform_summary(self):
        # single assertion the task's ALL_8_TRANSFORMS=PASS maps to
        results = []
        for t in range(8):
            disp = _mb_transform_point(*xy("pd"), 19, t)
            acc = _mb_transform_point(*xy("dd"), 19, t)
            ok = judge_answer(
                question_content=self.CANONICAL,
                attempt=mk([disp], transform="identity" if t == 0 else f"t{t}"),
            ).status is JudgeStatus.CORRECT
            acc_ok = judge_answer(
                question_content=self.CANONICAL,
                attempt=mk([acc], transform="identity" if t == 0 else f"t{t}"),
                accepted_moves=[{"x": xy("dd")[0], "y": xy("dd")[1]}],
            ).status is JudgeStatus.CORRECT
            results.append(ok and acc_ok)
        assert all(results), results


# ---------------------------------------------------------------------------
# G — accepted alternatives are server/content authority
# ---------------------------------------------------------------------------

class TestAcceptedAlternatives:
    CANONICAL = "(;SZ[19];B[pd]RE[Correct])"

    def test_client_cannot_declare_its_own_accepted_move(self):
        # the attempt payload has no channel for "accepted"; a move not in the
        # authored tree and not in the SERVER-supplied accepted set is INCORRECT.
        r = judge_answer(
            question_content=self.CANONICAL,
            attempt=mk([xy("dd")]),
            accepted_moves=None,
        )
        assert r.status is JudgeStatus.INCORRECT

    def test_server_supplied_accepted_move_is_honoured(self):
        r = judge_answer(
            question_content=self.CANONICAL,
            attempt=mk([xy("dd")]),
            accepted_moves=[{"x": xy("dd")[0], "y": xy("dd")[1]}],
        )
        assert r.status is JudgeStatus.CORRECT
        assert r.reason_code == "accepted_authoritative_alternative"

    def test_accepted_fast_path_is_single_move_only(self):
        r = judge_answer(
            question_content=self.CANONICAL,
            attempt=mk([xy("dd"), xy("qf")]),
            accepted_moves=[{"x": xy("dd")[0], "y": xy("dd")[1]}],
        )
        # two moves -> not the single-move accepted shortcut; falls to the
        # tree walk, where dd is off the authored B[pd] line -> INCORRECT
        assert r.status is JudgeStatus.INCORRECT

    def test_no_katago_additive_accept_in_canonical_judge(self):
        # judge_answer has no katago_best_move parameter at all
        import inspect

        assert "katago" not in inspect.signature(judge_answer).parameters
        src = inspect.getsource(judge_answer)
        assert "katago" not in src.lower()


# ---------------------------------------------------------------------------
# resolve_srs_review_authority — adapter behaviour
# ---------------------------------------------------------------------------

QUESTIONS = [
    {"id": 1, "content": "(;SZ[19];B[pd]RE[Correct])"},
    {"id": 2, "content": "(;SZ[19];B[pd])"},                # bare leaf -> UNVERIFIABLE
    {"id": 3, "content": "(;SZ[19];B[pd]"},                 # malformed
    {"id": 7, "content": "(;SZ[19];B[pd]RE[Correct])"},
    {"id": 7, "content": "(;SZ[19];B[dp]RE[Correct])"},     # duplicate legacy id
]


def _loader():
    return list(QUESTIONS)


class TestResolveAuthorityNoAttempt:
    def test_no_attempt_block_passes_client_grade_through_labelled_non_authoritative(self):
        res = resolve_srs_review_authority({"question_id": 1, "grade": 5}, load_questions=_loader)
        assert res.is_fail_closed is False
        assert res.server_authoritative is False
        assert res.grade == 5                        # unchanged self-report
        assert res.grade_basis is GradeBasis.CLIENT_SELF_REPORT_NO_SERVER_JUDGE

    def test_no_attempt_with_client_correct_boolean_is_still_non_authoritative(self):
        res = resolve_srs_review_authority(
            {"question_id": 1, "grade": 0, "correct": True}, load_questions=_loader
        )
        assert res.server_authoritative is False
        assert res.grade == 0


class TestResolveAuthorityAttemptPath:
    def _attempt(self, moves, colour="B", transform="identity"):
        return {"moves": [{"x": x, "y": y} for (x, y) in moves],
                "player_color": colour, "transform": transform}

    def test_server_correct_overrides_client_grade_0(self):
        res = resolve_srs_review_authority(
            {"question_id": 1, "grade": 0, "attempt": self._attempt([xy("pd")])},
            load_questions=_loader,
        )
        assert res.server_authoritative is True
        assert res.grade == 3
        assert res.grade_basis is GradeBasis.SERVER_JUDGE_CORRECT

    def test_server_incorrect_overrides_client_grade_5(self):
        res = resolve_srs_review_authority(
            {"question_id": 1, "grade": 5, "attempt": self._attempt([xy("qq")])},
            load_questions=_loader,
        )
        assert res.server_authoritative is True
        assert res.grade == 0
        assert res.grade_basis is GradeBasis.SERVER_JUDGE_INCORRECT

    def test_unverifiable_question_fails_closed_ignoring_client_correct(self):
        res = resolve_srs_review_authority(
            {"question_id": 2, "grade": 5, "attempt": self._attempt([xy("pd")])},
            load_questions=_loader,
        )
        assert res.is_fail_closed is True
        assert res.fail_closed_status == 422
        assert res.grade is None

    def test_malformed_question_fails_closed_with_400(self):
        res = resolve_srs_review_authority(
            {"question_id": 3, "grade": 5, "attempt": self._attempt([xy("pd")])},
            load_questions=_loader,
        )
        assert res.is_fail_closed is True
        assert res.fail_closed_status == 400

    def test_ambiguous_legacy_id_fails_closed_409(self):
        res = resolve_srs_review_authority(
            {"question_id": 7, "grade": 5, "attempt": self._attempt([xy("pd")])},
            load_questions=_loader,
        )
        assert res.is_fail_closed is True
        assert res.fail_closed_status == 409
        assert res.fail_closed_body["code"] == "ambiguous_question_identity"

    def test_unknown_question_fails_closed_422(self):
        res = resolve_srs_review_authority(
            {"question_id": 999, "grade": 5, "attempt": self._attempt([xy("pd")])},
            load_questions=_loader,
        )
        assert res.is_fail_closed is True
        assert res.fail_closed_status == 422

    def test_forbidden_attempt_field_fails_closed_400(self):
        res = resolve_srs_review_authority(
            {"question_id": 1, "grade": 0,
             "attempt": {"moves": [], "player_color": "B", "correct": True}},
            load_questions=_loader,
        )
        assert res.is_fail_closed is True
        assert res.fail_closed_status == 400

    def test_continue_maps_to_grade_0_with_retained_basis(self):
        res = resolve_srs_review_authority(
            {"question_id": 4, "grade": 5,
             "attempt": self._attempt([xy("pd")])},          # partial of the 3-ply line
            load_questions=lambda: [
                {"id": 4, "content": "(;SZ[19];B[pd];W[dd];B[qf]RE[Correct])"}
            ],
        )
        assert res.server_authoritative is True
        assert res.grade == 0
        assert res.grade_basis is GradeBasis.SERVER_JUDGE_CONTINUE_NOT_A_PASS

    def test_identity_fallback_flag_is_set_on_attempt_path(self):
        res = resolve_srs_review_authority(
            {"question_id": 1, "grade": 0, "attempt": self._attempt([xy("pd")])},
            load_questions=_loader,
        )
        assert res.identity_fallback_used is True   # no source_record_uuid at runtime
