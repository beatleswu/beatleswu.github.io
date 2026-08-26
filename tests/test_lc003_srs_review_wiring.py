"""LC003 — /api/srs/review server-authority wiring (route level).

Groups (LC003 task section 20):
  H  /api/srs/review ignores client correctness authority
  I  SRS grade derives from server judgement
  J  anti-farm behaviour unchanged
  + adversarial: client says correct/server wrong, client grade 5/server
    incorrect, malformed SGF + client correct=true, ambiguous + client
    correct=true, wrong colour + right coordinate.

Strategy: the durable operation ``_srs_review_operation`` is unchanged by
LC003 (see the app.py diff -- only the route and one import move). These
tests spy on ``ReviewService.review`` to prove the route hands the durable
operation a SERVER-derived grade, and that fail-closed cases never reach it.
The SM-2 / anti-farm math itself is covered by the LC002 SRS behaviour suite
and by direct assertions here that the server grades flow through the
unchanged anti-farm gate.

Run: python -m pytest tests/test_lc003_srs_review_wiring.py -q
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _install_stubs():
    from flask import Blueprint

    stubs = {
        "katago_explain": {"KataGoExplainer": type("KataGoExplainer", (), {})},
        "explain_overrides": {"get_override": lambda *a, **k: None},
        "question_taxonomy": {"get_taxonomy": lambda *a, **k: {}},
        "monster_taxonomy": {
            "get_monster_taxonomy": lambda *a, **k: {},
            "mark_encounters": lambda *a, **k: None,
        },
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
        m.grimoire_bp = Blueprint("grimoire_stub_lc003", __name__)
        sys.modules["grimoire_api"] = m


@pytest.fixture(scope="module")
def app_module():
    _install_stubs()
    import app as app_module

    return app_module


def xy(coord: str) -> tuple[int, int]:
    return ord(coord[0]) - 97, ord(coord[1]) - 97


QUESTIONS = [
    {"id": 1, "content": "(;SZ[19];B[pd]RE[Correct])"},          # solvable, answer = pd
    {"id": 2, "content": "(;SZ[19];B[pd])"},                     # bare leaf -> UNVERIFIABLE
    {"id": 3, "content": "(;SZ[19];B[pd]"},                      # malformed
    {"id": 4, "content": "(;SZ[19];B[pd]"
                          "(;W[dd];B[qf]RE[Correct])(;W[dp];B[cf]RE[Correct]))"},  # ambiguous
]


class _ReviewSpy:
    """Stands in for ReviewService; records the command, returns a 200."""

    def __init__(self):
        self.calls = []

    def review(self, *, user_id, command):
        self.calls.append((user_id, command))

        class _Outcome:
            payload = {"ok": True}
            http_status = 200

        return _Outcome()


@pytest.fixture
def spy_client(app_module, monkeypatch):
    spy = _ReviewSpy()
    monkeypatch.setattr(app_module, "_review_service", spy)
    monkeypatch.setattr(app_module, "_load_questions", lambda: list(QUESTIONS))
    app_module.app.config["TESTING"] = True
    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 5150
    return client, spy


def _post(client, body):
    return client.post("/api/srs/review", json=body)


def _attempt(moves, colour="B", transform="identity"):
    return {"moves": [{"x": x, "y": y} for (x, y) in moves],
            "player_color": colour, "transform": transform}


# ---------------------------------------------------------------------------
# H — client correctness authority is ignored on the attempt path
# ---------------------------------------------------------------------------

class TestClientCorrectnessAuthorityIgnored:
    def test_client_grade_5_but_server_incorrect_sends_grade_0(self, spy_client):
        client, spy = spy_client
        r = _post(client, {"question_id": 1, "grade": 5,
                           "correct": True, "attempt": _attempt([xy("qq")])})
        assert r.status_code == 200
        assert len(spy.calls) == 1
        assert spy.calls[0][1].grade == 0            # server INCORRECT wins

    def test_client_grade_0_but_server_correct_sends_grade_3(self, spy_client):
        client, spy = spy_client
        r = _post(client, {"question_id": 1, "grade": 0,
                           "correct": False, "attempt": _attempt([xy("pd")])})
        assert r.status_code == 200
        assert spy.calls[0][1].grade == 3            # server CORRECT wins

    def test_client_correct_boolean_true_does_not_make_a_wrong_move_pass(self, spy_client):
        client, spy = spy_client
        _post(client, {"question_id": 1, "grade": 3, "correct": True,
                       "attempt": _attempt([xy("dd")])})   # off-tree
        assert spy.calls[0][1].grade == 0

    def test_wrong_colour_right_coordinate_is_not_a_pass(self, spy_client):
        client, spy = spy_client
        _post(client, {"question_id": 1, "grade": 5, "correct": True,
                       "attempt": _attempt([xy("pd")], colour="W")})
        assert spy.calls[0][1].grade == 0            # colour enforced -> INCORRECT

    def test_accepted_alternative_still_needs_server_confirmation(self, spy_client, monkeypatch, app_module):
        # server supplies the accepted set; client cannot self-declare one
        monkeypatch.setattr(app_module, "_question_accepted_moves",
                            lambda q: [{"x": xy("dd")[0], "y": xy("dd")[1]}] if q.get("id") == 1 else [])
        client, spy = spy_client
        _post(client, {"question_id": 1, "grade": 0, "attempt": _attempt([xy("dd")])})
        assert spy.calls[0][1].grade == 3           # dd accepted by server -> CORRECT


# ---------------------------------------------------------------------------
# fail-closed: the review is never recorded, client input never consulted
# ---------------------------------------------------------------------------

class TestFailClosedNeverRecordsAReview:
    def test_malformed_sgf_plus_client_correct_true_fails_closed_400(self, spy_client):
        client, spy = spy_client
        r = _post(client, {"question_id": 3, "grade": 5, "correct": True,
                           "attempt": _attempt([xy("pd")])})
        assert r.status_code == 400
        assert spy.calls == []                       # nothing recorded
        assert r.get_json()["error"] == "malformed"

    def test_unverifiable_question_plus_client_correct_fails_closed_422(self, spy_client):
        client, spy = spy_client
        r = _post(client, {"question_id": 2, "grade": 5, "correct": True,
                           "attempt": _attempt([xy("pd")])})
        assert r.status_code == 422
        assert spy.calls == []

    def test_ambiguous_autoreply_plus_client_correct_true_fails_closed_422(self, spy_client):
        client, spy = spy_client
        r = _post(client, {"question_id": 4, "grade": 5, "correct": True,
                           "attempt": _attempt([xy("pd"), xy("qf")])})
        assert r.status_code == 422
        assert spy.calls == []
        assert r.get_json()["code"] == "ambiguous_autoreply"

    def test_forbidden_attempt_field_fails_closed_400(self, spy_client):
        client, spy = spy_client
        r = _post(client, {"question_id": 1, "grade": 0,
                           "attempt": {"moves": [], "player_color": "B", "grade": 5}})
        assert r.status_code == 400
        assert spy.calls == []

    def test_unknown_question_on_attempt_path_fails_closed(self, spy_client):
        client, spy = spy_client
        r = _post(client, {"question_id": 987654, "grade": 5,
                           "attempt": _attempt([xy("pd")])})
        assert r.status_code == 422
        assert spy.calls == []

    def test_bad_transform_fails_closed_not_pass(self, spy_client):
        client, spy = spy_client
        r = _post(client, {"question_id": 1, "grade": 5, "correct": True,
                           "attempt": _attempt([xy("pd")], transform="spin-42")})
        assert r.status_code == 422
        assert spy.calls == []


# ---------------------------------------------------------------------------
# legacy no-attempt path preserved (does not break the current client)
# ---------------------------------------------------------------------------

class TestLegacyNoAttemptPathUnchanged:
    def test_no_attempt_passes_client_grade_through(self, spy_client):
        client, spy = spy_client
        _post(client, {"question_id": 1, "grade": 3})
        assert spy.calls[0][1].grade == 3

    def test_no_attempt_grade_5_still_passes_through_as_self_report(self, spy_client):
        client, spy = spy_client
        _post(client, {"question_id": 1, "grade": 5})
        assert spy.calls[0][1].grade == 5

    def test_no_attempt_still_reaches_the_durable_operation(self, spy_client):
        client, spy = spy_client
        _post(client, {"question_id": 1, "grade": 0})
        assert len(spy.calls) == 1


# ---------------------------------------------------------------------------
# I — SRS grade derives from server judgement
# ---------------------------------------------------------------------------

class TestServerGradeDerivation:
    def test_server_grade_mapping_correct_is_3_incorrect_is_0(self, spy_client):
        client, spy = spy_client
        _post(client, {"question_id": 1, "grade": 0, "attempt": _attempt([xy("pd")])})
        _post(client, {"question_id": 1, "grade": 5, "attempt": _attempt([xy("qq")])})
        assert [c[1].grade for c in spy.calls] == [3, 0]

    def test_continue_maps_to_0(self, spy_client, monkeypatch, app_module):
        monkeypatch.setattr(
            app_module, "_load_questions",
            lambda: [{"id": 9, "content": "(;SZ[19];B[pd];W[dd];B[qf]RE[Correct])"}],
        )
        client, spy = spy_client
        _post(client, {"question_id": 9, "grade": 5, "attempt": _attempt([xy("pd")])})
        assert spy.calls[0][1].grade == 0


# ---------------------------------------------------------------------------
# J — anti-farm behaviour unchanged (server grades flow through the SAME gate)
# ---------------------------------------------------------------------------

class TestAntiFarmUnchanged:
    def test_durable_operation_still_uses_the_unchanged_srs_gate_and_math(self, app_module):
        src = Path(app_module.__file__).read_text(encoding="utf-8")
        start = src.index("def _srs_review_operation(")
        end = src.index("def _lane_b_review_with_level_value(")
        body = src[start:end]
        # LC003 edits only the import block and the srs_review route body;
        # the durable operation still drives SM-2 and the anti-farm gate.
        assert "should_grant_review_progress" in body
        assert "sm2_update" in body
        # and LC003's judge is NOT invoked from inside the durable operation
        assert "canonical_learning_judge" not in body
        assert "resolve_srs_review_authority" not in body

    def test_server_correct_grade_3_behaves_as_a_pass_in_the_unchanged_gate(self, app_module):
        f = app_module.should_grant_review_progress
        # server CORRECT -> grade 3 -> first pass grants, credited pass does not
        assert f(None, 3) is True
        assert f({"progress_credited": 1}, 3) is False

    def test_server_incorrect_grade_0_never_grants_in_the_unchanged_gate(self, app_module):
        f = app_module.should_grant_review_progress
        assert f(None, 0) is False
        assert f({"progress_credited": 0}, 0) is False

    def test_sm2_math_module_unchanged(self, app_module):
        # LC002 pinned these; LC003 must not have touched them
        ef, iv, rp, due = app_module.sm2_update(2.5, 0, 0, 3)
        assert (iv, rp) == (1, 1)
        assert ef == pytest.approx(2.36)
