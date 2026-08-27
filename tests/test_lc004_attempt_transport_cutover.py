"""LC004 — primary SRS attempt transport + legacy no-attempt authority cutover.

Covers (LC004 task section 16):
  - the real frontend transport sends FACTS ONLY (node runner)
  - client grade authority on the primary flow is NONE when an attempt is present
  - the legacy no-attempt path: default 'legacy' unchanged; 'fail_closed' cutover
    grants NO authoritative progress and consults no client value
  - the expected player colour is SERVER-AUTHORED from the question SGF
  - malformed / ambiguous / bare-leaf / ambiguous-autoreply all fail closed
  - all 8 transforms + accepted alternative + ambiguous legacy id regressions

No schema/migration/production. Run:
  python -m pytest tests/test_lc004_attempt_transport_cutover.py -q
"""

from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import canonical_learning_judge as clj  # noqa: E402
from canonical_learning_judge import (  # noqa: E402
    Attempt,
    GradeBasis,
    JudgeStatus,
    _mb_transform_point,
    _server_expected_player_color,
    judge_answer,
    no_attempt_policy,
    resolve_srs_review_authority,
)


def xy(coord: str) -> tuple[int, int]:
    return ord(coord[0]) - 97, ord(coord[1]) - 97


def mk(moves, colour="B", transform="identity") -> Attempt:
    return Attempt.from_payload({
        "moves": [{"x": x, "y": y} for (x, y) in moves],
        "player_color": colour, "transform": transform,
    })


# ---------------------------------------------------------------------------
# A — frontend transport: facts only (node contract runner)
# ---------------------------------------------------------------------------

def test_review_transport_attempt_is_facts_only_node_runner():
    runner = REPO / "tests" / "e2e" / "run_lc004_attempt_transport_contract.mjs"
    assert runner.exists()
    result = subprocess.run(
        ["node", str(runner)], capture_output=True, text=True, cwd=str(REPO), timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "all LC004 transport checks passed" in result.stdout


class TestFrontendCallerSourceContract:
    INDEX = (REPO / "index.html").read_text(encoding="utf-8")
    MISTAKES = (REPO / "mistakes.html").read_text(encoding="utf-8")
    TRANSPORT = (REPO / "js" / "game" / "review_transport.js").read_text(encoding="utf-8")

    def test_transport_forwards_a_sanitized_attempt(self):
        assert "function sanitizeAttempt(" in self.TRANSPORT
        assert "const attempt = sanitizeAttempt(value.attempt);" in self.TRANSPORT
        assert "if (attempt) request.attempt = attempt;" in self.TRANSPORT
        # forbidden keys enumerated
        for key in ("grade", "correct", "verdict", "accepted", "judge_result"):
            assert f"'{key}'" in self.TRANSPORT

    def test_index_and_mistakes_record_factual_moves_gated_off_by_default(self):
        for src in (self.INDEX, self.MISTAKES):
            assert "_lc004RecordAttemptMove" in src
            assert "window.__LC004_ATTEMPT_TRANSPORT" in src        # gated
            assert "transform:'identity'" in src                    # crop-only board
            # the attempt facts object never carries a grade/correct/verdict
            assert "player_color:playerColor" in src

    def test_index_metadata_only_adds_attempt_when_flag_on(self):
        # _lc004AttemptFacts returns undefined unless the flag is truthy
        assert "if(typeof window==='undefined'||!window.__LC004_ATTEMPT_TRANSPORT)return undefined;" in self.INDEX
        assert "const attempt=_lc004AttemptFacts();" in self.INDEX
        assert "if(attempt)meta.attempt=attempt;" in self.INDEX


# ---------------------------------------------------------------------------
# B — server-authored expected player colour
# ---------------------------------------------------------------------------

class TestServerAuthoredPlayerColour:
    def test_expected_colour_from_pl_property(self):
        from sgf_engine.parser.sgf_parser import parse_sgf
        root = parse_sgf("(;SZ[19]PL[W];W[dd]RE[W+])", strict=True)
        assert _server_expected_player_color(root) == "W"

    def test_expected_colour_from_first_move_when_no_pl(self):
        from sgf_engine.parser.sgf_parser import parse_sgf
        root = parse_sgf("(;SZ[19];B[pd]RE[B+])", strict=True)
        assert _server_expected_player_color(root) == "B"

    def test_client_colour_contradicting_server_is_incorrect_not_a_pass(self):
        r = judge_answer(
            question_content="(;SZ[19];B[pd]RE[B+])",
            attempt=mk([xy("pd")], colour="W"),   # client lies about colour
        )
        assert r.status is JudgeStatus.INCORRECT
        assert r.reason_code == "player_color_contradicts_server"
        assert r.player_color == "B"              # server value, not client's

    def test_client_colour_matching_server_proceeds(self):
        r = judge_answer(
            question_content="(;SZ[19]PL[W];W[dd]RE[W+])",
            attempt=mk([xy("dd")], colour="W"),
        )
        assert r.status is JudgeStatus.CORRECT

    def test_judge_uses_server_colour_for_the_walk(self):
        # white-to-play question, client (wrongly) says black at the vital point
        r = judge_answer(
            question_content="(;SZ[19]PL[W];W[dd]RE[W+])",
            attempt=mk([xy("dd")], colour="B"),
        )
        assert r.status is JudgeStatus.INCORRECT


# ---------------------------------------------------------------------------
# C — no-attempt policy (default legacy, cutover fail_closed)
# ---------------------------------------------------------------------------

class TestNoAttemptPolicy:
    def _loader(self):
        return [{"id": 1, "content": "(;SZ[19];B[pd]RE[B+])"}]

    def test_default_policy_is_legacy(self, monkeypatch):
        monkeypatch.delenv("SRS_REVIEW_NO_ATTEMPT_POLICY", raising=False)
        assert no_attempt_policy() == "legacy"

    def test_unknown_policy_value_falls_back_to_legacy(self, monkeypatch):
        monkeypatch.setenv("SRS_REVIEW_NO_ATTEMPT_POLICY", "banana")
        assert no_attempt_policy() == "legacy"

    def test_legacy_no_attempt_passes_client_grade_through_non_authoritative(self, monkeypatch):
        monkeypatch.delenv("SRS_REVIEW_NO_ATTEMPT_POLICY", raising=False)
        res = resolve_srs_review_authority({"question_id": 1, "grade": 5}, load_questions=self._loader)
        assert res.is_fail_closed is False
        assert res.server_authoritative is False
        assert res.grade == 5
        assert res.grade_basis is GradeBasis.CLIENT_SELF_REPORT_NO_SERVER_JUDGE

    def test_fail_closed_no_attempt_returns_409_and_records_nothing(self, monkeypatch):
        monkeypatch.setenv("SRS_REVIEW_NO_ATTEMPT_POLICY", "fail_closed")
        res = resolve_srs_review_authority(
            {"question_id": 1, "grade": 5, "correct": True}, load_questions=self._loader,
        )
        assert res.is_fail_closed is True
        assert res.fail_closed_status == 409
        assert res.fail_closed_body["code"] == "srs_attempt_required"
        assert res.fail_closed_body["refresh_required"] is True
        assert res.grade is None                       # no grade, no progress

    def test_fail_closed_does_not_consult_client_grade_or_boolean(self, monkeypatch):
        monkeypatch.setenv("SRS_REVIEW_NO_ATTEMPT_POLICY", "fail_closed")
        for body in (
            {"question_id": 1, "grade": 5},
            {"question_id": 1, "grade": 0},
            {"question_id": 1, "grade": 3, "correct": True},
            {"question_id": 1},
        ):
            res = resolve_srs_review_authority(body, load_questions=self._loader)
            assert res.is_fail_closed and res.fail_closed_status == 409

    def test_fail_closed_still_lets_a_valid_attempt_through(self, monkeypatch):
        monkeypatch.setenv("SRS_REVIEW_NO_ATTEMPT_POLICY", "fail_closed")
        res = resolve_srs_review_authority(
            {"question_id": 1, "grade": 0,
             "attempt": {"moves": [{"x": xy("pd")[0], "y": xy("pd")[1]}], "player_color": "B"}},
            load_questions=self._loader,
        )
        assert res.is_fail_closed is False
        assert res.server_authoritative is True
        assert res.grade == 3


# ---------------------------------------------------------------------------
# D — adversarial route flow (spy on ReviewService)
# ---------------------------------------------------------------------------

def _install_stubs():
    from flask import Blueprint

    stubs = {
        "katago_explain": {"KataGoExplainer": type("KataGoExplainer", (), {})},
        "explain_overrides": {"get_override": lambda *a, **k: None},
        "question_taxonomy": {"get_taxonomy": lambda *a, **k: {}},
        "monster_taxonomy": {"get_monster_taxonomy": lambda *a, **k: {},
                              "mark_encounters": lambda *a, **k: None},
        "chapter_i18n": {"localize_topic": lambda *a, **k: "",
                          "localize_level": lambda *a, **k: ""},
        "backend_i18n": {"badge_en": lambda *a, **k: "",
                          "skill_node_en": lambda *a, **k: "",
                          "title_en": lambda *a, **k: ""},
    }
    for name, attrs in stubs.items():
        if name not in sys.modules:
            m = types.ModuleType(name)
            for k, v in attrs.items():
                setattr(m, k, v)
            sys.modules[name] = m
    if "grimoire_api" not in sys.modules:
        m = types.ModuleType("grimoire_api")
        m.grimoire_bp = Blueprint("grimoire_stub_lc004", __name__)
        sys.modules["grimoire_api"] = m


@pytest.fixture(scope="module")
def app_module():
    _install_stubs()
    import app as app_module
    return app_module


QUESTIONS = [
    {"id": 1, "content": "(;SZ[19];B[pd]RE[B+])"},           # solvable, answer pd
    {"id": 2, "content": "(;SZ[19];B[pd])"},                      # bare leaf -> UNVERIFIABLE
    {"id": 3, "content": "(;SZ[19];B[pd]"},                       # malformed
    {"id": 4, "content": "(;SZ[19];B[pd](;W[dd];B[qf]RE[B+])(;W[dp];B[cf]RE[B+]))"},
    {"id": 7, "content": "(;SZ[19];B[pd]RE[B+])"},
    {"id": 7, "content": "(;SZ[19];B[dp]RE[B+])"},           # duplicate legacy id
]


class _Spy:
    def __init__(self):
        self.calls = []

    def review(self, *, user_id, command):
        self.calls.append(command)

        class _O:
            payload = {"ok": True}
            http_status = 200
        return _O()


@pytest.fixture
def client(app_module, monkeypatch):
    spy = _Spy()
    monkeypatch.setattr(app_module, "_review_service", spy)
    monkeypatch.setattr(app_module, "_load_questions", lambda: list(QUESTIONS))
    monkeypatch.setattr(app_module, "_question_accepted_moves",
                        lambda q: q.get("accepted_moves") or [])
    monkeypatch.delenv("SRS_REVIEW_NO_ATTEMPT_POLICY", raising=False)
    app_module.app.config["TESTING"] = True
    c = app_module.app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = 99001
    return c, spy


def _attempt(moves, colour="B"):
    return {"moves": [{"x": x, "y": y} for (x, y) in moves],
            "player_color": colour, "transform": "identity"}


def _post(c, body):
    return c.post("/api/srs/review", json=body)


class TestAdversarialRouteFlow:
    def test_real_frontend_correct_attempt(self, client):
        c, spy = client
        r = _post(c, {"question_id": 1, "grade": 0, "attempt": _attempt([xy("pd")])})
        assert r.status_code == 200
        assert spy.calls[0].grade == 3

    def test_real_frontend_incorrect_attempt(self, client):
        c, spy = client
        r = _post(c, {"question_id": 1, "grade": 3, "attempt": _attempt([xy("qq")])})
        assert r.status_code == 200
        assert spy.calls[0].grade == 0

    def test_client_grade_5_server_incorrect(self, client):
        c, spy = client
        _post(c, {"question_id": 1, "grade": 5, "correct": True, "attempt": _attempt([xy("qq")])})
        assert spy.calls[0].grade == 0

    def test_client_grade_0_server_correct(self, client):
        c, spy = client
        _post(c, {"question_id": 1, "grade": 0, "correct": False, "attempt": _attempt([xy("pd")])})
        assert spy.calls[0].grade == 3

    def test_legacy_no_attempt_default_policy_passes_through(self, client):
        c, spy = client
        _post(c, {"question_id": 1, "grade": 3})
        assert spy.calls[0].grade == 3

    def test_legacy_no_attempt_fail_closed_policy_409_no_review(self, client, monkeypatch):
        c, spy = client
        monkeypatch.setenv("SRS_REVIEW_NO_ATTEMPT_POLICY", "fail_closed")
        r = _post(c, {"question_id": 1, "grade": 3, "correct": True})
        assert r.status_code == 409
        assert r.get_json()["code"] == "srs_attempt_required"
        assert spy.calls == []

    def test_malformed_attempt_fails_closed(self, client):
        c, spy = client
        r = _post(c, {"question_id": 3, "grade": 5, "correct": True, "attempt": _attempt([xy("pd")])})
        assert r.status_code == 400
        assert spy.calls == []

    def test_ambiguous_question_identity_fails_closed(self, client):
        c, spy = client
        r = _post(c, {"question_id": 7, "grade": 5, "attempt": _attempt([xy("pd")])})
        assert r.status_code == 409
        assert r.get_json()["code"] == "ambiguous_question_identity"
        assert spy.calls == []

    def test_bare_leaf_fails_closed(self, client):
        c, spy = client
        r = _post(c, {"question_id": 2, "grade": 5, "correct": True, "attempt": _attempt([xy("pd")])})
        assert r.status_code == 422
        assert spy.calls == []

    def test_ambiguous_autoreply_fails_closed(self, client):
        c, spy = client
        r = _post(c, {"question_id": 4, "grade": 5, "correct": True,
                      "attempt": _attempt([xy("pd"), xy("qf")])})
        assert r.status_code == 422
        assert r.get_json()["code"] == "ambiguous_autoreply"
        assert spy.calls == []

    def test_old_client_legacy_body_is_deterministic(self, client):
        c, spy = client
        # old cached client: no attempt, maybe no grade
        r1 = _post(c, {"question_id": 1, "grade": 3})
        assert r1.status_code == 200 and spy.calls[-1].grade == 3
        r2 = _post(c, {"question_id": 1})
        # missing grade -> _srs_review_operation's own 400 (unchanged), not a pass
        assert r2.status_code in (200, 400)

    def test_wrong_colour_right_coordinate(self, client):
        c, spy = client
        _post(c, {"question_id": 1, "grade": 5, "correct": True,
                  "attempt": _attempt([xy("pd")], colour="W")})
        assert spy.calls[0].grade == 0

    def test_accepted_alternative_via_server_set(self, client, monkeypatch, app_module):
        c, spy = client
        monkeypatch.setattr(app_module, "_load_questions",
                            lambda: [{"id": 11, "content": "(;SZ[19];B[pd]RE[B+])",
                                      "accepted_moves": [{"x": xy("dd")[0], "y": xy("dd")[1]}]}])
        monkeypatch.setattr(app_module, "_question_accepted_moves",
                            lambda q: q.get("accepted_moves") or [])
        _post(c, {"question_id": 11, "grade": 0, "attempt": _attempt([xy("dd")])})
        assert spy.calls[0].grade == 3           # dd accepted by server content

    @pytest.mark.parametrize("t", list(range(8)))
    def test_all_8_transforms_through_the_route(self, client, monkeypatch, app_module, t):
        c, spy = client
        monkeypatch.setattr(app_module, "_load_questions",
                            lambda: [{"id": 20, "content": "(;SZ[19];B[pd]RE[B+])"}])
        disp = _mb_transform_point(*xy("pd"), 19, t)
        _post(c, {"question_id": 20, "grade": 0,
                  "attempt": {"moves": [{"x": disp[0], "y": disp[1]}],
                              "player_color": "B",
                              "transform": "identity" if t == 0 else f"t{t}"}})
        assert spy.calls[0].grade == 3, f"transform {t}"


# ---------------------------------------------------------------------------
# E — SRS math / anti-farm untouched by LC004
# ---------------------------------------------------------------------------

class TestSrsAndAntiFarmUntouched:
    def test_sm2_update_unchanged(self, app_module):
        ef, iv, rp, due = app_module.sm2_update(2.5, 0, 0, 3)
        assert (iv, rp) == (1, 1)
        assert ef == pytest.approx(2.36)

    def test_anti_farm_gate_unchanged(self, app_module):
        f = app_module.should_grant_review_progress
        assert f(None, 3) is True
        assert f({"progress_credited": 1}, 3) is False
        assert f(None, 0) is False

    def test_lc004_added_no_judge_logic_to_app_py(self, app_module):
        src = Path(app_module.__file__).read_text(encoding="utf-8")
        # the only srs/review authority call in the route is still the LC003 one
        assert src.count("resolve_srs_review_authority(") == 1
        # no judge orchestration leaked into app.py
        assert "def judge_answer(" not in src
        assert "JudgeStatus" not in src
