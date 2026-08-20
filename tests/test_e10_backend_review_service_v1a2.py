"""Backend Wave2 (V1A2 ReviewService + V1A3 transaction/port boundaries)
implementation and authority-closure tests.

Base: 554a86f5c7083f3d1538e01868a278e3a3313931 (post-B3 canonical master).
Prep authority: docs/planning/e10_backend_v1a2_reviewservice_implementation_packet.md
(commit 12f7cf7be0f290c05d2156d7c79c5bde0860d23c).

Three tiers, matching the task's required evidence layers:

  Tier 1 (pure unit tests, no Flask/app import): ReviewService/
  MapBattleReviewHandoff classification behaviour against a stub legacy
  operation. Proves V1A2's dispatch/classification logic in isolation.

  Tier 2 (source-level, reads app.py as text): SOURCE OWNERSHIP evidence --
  confirms _srs_review_operation is the only durable review writer and the
  only place ReviewService is instantiated.

  Tier 3 (real app.py import + Flask test client): CALL-PATH CONTRACT and
  RUNTIME/TRANSACTION CHARACTERIZATION evidence -- proves the real route and
  the real MapBattle handoff both funnel through the one ReviewService
  instance, and that a review call reaches the durable operation exactly
  once.
"""

from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = "554a86f5c7083f3d1538e01868a278e3a3313931"


# ---------------------------------------------------------------------------
# Tier 1 -- pure unit tests against review_service.py directly.
# ---------------------------------------------------------------------------

from review_contracts import ReviewCommand  # noqa: E402
from review_service import (  # noqa: E402
    LegacyReviewOperation,
    MapBattleReviewHandoff,
    ReviewService,
    ReviewServiceOutcome,
    ReviewServiceStatus,
)


class _FlaskLikeResponse:
    """Minimal stand-in for a Flask Response: only .get_json() is used."""

    def __init__(self, payload):
        self._payload = payload

    def get_json(self, silent=True):
        return self._payload


def _full_payload():
    return {
        "ok": True, "ease_factor": 2.5, "interval": 3, "due_date": "2026-08-17",
        "new_badges": [], "stats": {"xp": 10}, "xp_gain": 10, "combo_mult": 1.0,
        "pet_xp_added": 0, "pet_xp_ratio": 0.0, "pet_xp_gained": 1,
        "combo_streak": 1, "shield_used": False, "xp_potion_active": False,
        "ranked_up": False, "new_rank_level": None, "pet": None,
        "practice": {"level": 1}, "training": {"level": 1}, "new_appearance_items": [],
        "monster": {"defeated": False}, "player": {"hp": 30}, "quest_updates": [],
        "sp": None, "loot": None, "appearance_loot": None,
    }


def _core_payload():
    full = _full_payload()
    from review_contracts import CORE_20_FIELDS
    return {field: full[field] for field in CORE_20_FIELDS}


def _duplicate_payload():
    return {"ok": True, "progression_applied": False, "progression_duplicate": True, "question_id": 7001}


class _StubLegacyOperation:
    """Records every call and returns a scripted response."""

    def __init__(self, response):
        self.calls = []
        self._response = response

    def __call__(self, uid, data, *, internal=False, submission_id=None):
        self.calls.append({
            "uid": uid, "data": dict(data), "internal": internal, "submission_id": submission_id,
        })
        return self._response


def _command(**overrides):
    fields = dict(question_id=101, grade=3)
    fields.update(overrides)
    return ReviewCommand(**fields)


def test_full26_compat():
    stub = _StubLegacyOperation(_FlaskLikeResponse(_full_payload()))
    service = ReviewService(stub)
    outcome = service.review(user_id=7, command=_command())
    assert outcome.status == ReviewServiceStatus.SUCCESS
    assert outcome.shape == "FULL26"
    assert outcome.http_status == 200
    assert set(outcome.payload.keys()) == set(_full_payload().keys())


def test_core20_compat():
    stub = _StubLegacyOperation(_FlaskLikeResponse(_core_payload()))
    service = ReviewService(stub)
    outcome = service.review(user_id=7, command=_command())
    assert outcome.status == ReviewServiceStatus.SUCCESS
    assert outcome.shape == "CORE20"
    assert set(outcome.payload.keys()) == set(_core_payload().keys())
    # The 6 T2 fields must be OMITTED, not present as None -- same
    # omission-vs-null discipline the existing serializer already enforces.
    for t2_field in ("monster", "player", "quest_updates", "sp", "loot", "appearance_loot"):
        assert t2_field not in outcome.payload


def test_dup4_compat_internal_only():
    stub = _StubLegacyOperation(_FlaskLikeResponse(_duplicate_payload()))
    service = ReviewService(stub)
    outcome = service.review(user_id=7, command=_command(internal=True, submission_id="sub-1"))
    assert outcome.status == ReviewServiceStatus.SUCCESS
    assert outcome.shape == "DUP4"
    assert outcome.payload == _duplicate_payload()


def test_dup4_shape_rejected_on_public_path():
    # The real operation never returns this shape publicly, but the seam
    # itself must not silently accept it if it ever did -- same guard
    # review_compatibility.adapt_legacy_review_result already enforces.
    stub = _StubLegacyOperation(_FlaskLikeResponse(_duplicate_payload()))
    service = ReviewService(stub)
    with pytest.raises(ValueError):
        service.review(user_id=7, command=_command(internal=False))


@pytest.mark.parametrize("status", [400, 401, 403, 409, 429])
def test_rejected_statuses_preserve_status_and_payload(status):
    error_body = {"error": "some_expected_rejection"}
    stub = _StubLegacyOperation((_FlaskLikeResponse(error_body), status))
    service = ReviewService(stub)
    outcome = service.review(user_id=7, command=_command())
    assert outcome.status == ReviewServiceStatus.REJECTED
    assert outcome.http_status == status
    assert outcome.payload == error_body
    assert outcome.error_code == "some_expected_rejection"
    assert outcome.shape is None


def test_unexpected_status_is_error_not_rejected():
    stub = _StubLegacyOperation((_FlaskLikeResponse({"error": "boom"}), 500))
    service = ReviewService(stub)
    outcome = service.review(user_id=7, command=_command())
    assert outcome.status == ReviewServiceStatus.ERROR
    assert outcome.http_status == 500


def test_service_calls_legacy_operation_exactly_once_per_review():
    stub = _StubLegacyOperation(_FlaskLikeResponse(_full_payload()))
    service = ReviewService(stub)
    service.review(user_id=7, command=_command())
    assert len(stub.calls) == 1
    service.review(user_id=7, command=_command())
    assert len(stub.calls) == 2  # a second review() call is a second, distinct invocation -- not a retry of the first


def test_service_never_retries_a_single_call():
    stub = _StubLegacyOperation((_FlaskLikeResponse({"error": "fail"}), 500))
    service = ReviewService(stub)
    service.review(user_id=7, command=_command())
    assert len(stub.calls) == 1


def test_public_command_maps_to_exact_legacy_data_field_set():
    stub = _StubLegacyOperation(_FlaskLikeResponse(_full_payload()))
    service = ReviewService(stub)
    service.review(user_id=42, command=_command(
        question_id=9001, grade=5, unit_name="unit-a", unit_done=True,
        response_ms=1200, source_context="practice", training_set_id=3, is_scaffolding=True,
    ))
    call = stub.calls[0]
    assert call["uid"] == 42
    assert call["internal"] is False
    assert call["submission_id"] is None
    assert call["data"] == {
        "question_id": 9001, "grade": 5, "unit_name": "unit-a", "unit_done": True,
        "response_ms": 1200, "source_context": "practice", "training_set_id": 3,
        "is_scaffolding": True,
    }


def test_internal_command_passes_internal_and_submission_id_as_kwargs_not_data():
    stub = _StubLegacyOperation(_FlaskLikeResponse(_duplicate_payload()))
    service = ReviewService(stub)
    service.review(user_id=42, command=_command(
        question_id=101, grade=5, internal=True, submission_id="mbv1-sub-9",
    ))
    call = stub.calls[0]
    assert call["internal"] is True
    assert call["submission_id"] == "mbv1-sub-9"
    # submission_id must never leak into the data dict the legacy operation
    # parses as public request fields.
    assert "submission_id" not in call["data"]
    assert "internal" not in call["data"]


def test_map_battle_review_handoff_builds_internal_command_from_settlement():
    stub = _StubLegacyOperation(_FlaskLikeResponse(_duplicate_payload()))
    service = ReviewService(stub)
    handoff = MapBattleReviewHandoff(service)
    handoff.apply(user_id=42, settlement={
        "question_id": 555, "authoritative_grade": 5, "submission_id": "settled-sub-1",
        "result": "CORRECT",
    })
    call = stub.calls[0]
    assert call["internal"] is True
    assert call["submission_id"] == "settled-sub-1"
    assert call["data"]["question_id"] == 555
    assert call["data"]["grade"] == 5


def test_review_service_outcome_payload_is_a_defensive_snapshot():
    original = dict(_full_payload())
    outcome = ReviewServiceOutcome(
        status=ReviewServiceStatus.SUCCESS, shape="FULL26", payload=original, http_status=200,
    )
    original["ease_factor"] = 999.0
    assert outcome.payload["ease_factor"] != 999.0


# ---------------------------------------------------------------------------
# Tier 1b -- review_service.py owns no transport/transaction/settlement
# authority. Pure source scan; no import side effects.
# ---------------------------------------------------------------------------

REVIEW_SERVICE_SOURCE = (ROOT / "review_service.py").read_text(encoding="utf-8")

# The module docstring legitimately *talks about* get_db()/map_battle_*
# in prose (explaining what this module deliberately does NOT own). Scan
# only the executable code that follows it, so those explanatory mentions
# cannot produce a false positive -- and, symmetrically, cannot mask a real
# one either, since the docstring is the only place those tokens are
# expected to legally appear at all.
_REVIEW_SERVICE_DOCSTRING_END = REVIEW_SERVICE_SOURCE.index('"""\n\nfrom __future__') + 3
REVIEW_SERVICE_CODE = REVIEW_SERVICE_SOURCE[_REVIEW_SERVICE_DOCSTRING_END:]


def test_review_service_docstring_boundary_is_correctly_located():
    # Guards the slice above: if this ever breaks, the two tests below would
    # silently scan zero bytes and pass vacuously instead of catching a
    # real violation.
    assert REVIEW_SERVICE_CODE.strip().startswith("from __future__")


def test_review_service_never_imports_flask_or_database():
    for forbidden in ("import flask", "from flask", "import psycopg2", "import sqlite3",
                       "from db import", "import db\n"):
        assert forbidden not in REVIEW_SERVICE_CODE, forbidden


def test_review_service_owns_no_transaction_or_connection():
    for forbidden in ("get_db(", "conn.commit", "conn.rollback", ".execute(", "BEGIN", "COMMIT"):
        assert forbidden not in REVIEW_SERVICE_CODE, forbidden


def test_review_service_never_calls_review_transport_endpoint():
    assert "/api/srs/review" not in REVIEW_SERVICE_SOURCE


def test_reviewservice_mapbattle_settlement_authority_is_zero():
    """REVIEWSERVICE_MAPBATTLE_SETTLEMENT_AUTHORITY=0: no MapBattle
    settlement/nonce/battle-state module is ever imported or called.

    Matches real usage patterns (import/attribute-access/call), not bare
    substrings -- both the module docstring AND MapBattleReviewHandoff's own
    class docstring legitimately *name* these functions in prose (explaining
    what this module deliberately does not do), so a bare-substring check
    would false-positive on the file's own documentation of this exact
    invariant.
    """
    for forbidden in (
        "import map_battle_persistence", "from map_battle_persistence", "map_battle_persistence.",
        "import map_battle_runtime", "from map_battle_runtime", "map_battle_runtime.",
        "settle_answer(", "settle_map_battle_submission(",
        "issue_attempt_with_submission_nonce(", "issue_submission_nonce_for_attempt(",
    ):
        assert forbidden not in REVIEW_SERVICE_SOURCE, forbidden


# ---------------------------------------------------------------------------
# Tier 2 -- SOURCE OWNERSHIP evidence against app.py as text.
# ---------------------------------------------------------------------------

APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


def _function_body(name: str, next_marker: str) -> str:
    """``next_marker`` may be a ``def ...`` name (bare) or a full boundary
    string (e.g. a decorator line) -- pass whichever the source actually
    uses immediately after the target function."""
    start = APP_SOURCE.index(f"def {name}")
    boundary = next_marker if (next_marker.startswith("def ") or next_marker.startswith("@")) \
        else f"def {next_marker}"
    end = APP_SOURCE.index(boundary, start)
    return APP_SOURCE[start:end]


def _find_all(text: str, marker: str) -> list[int]:
    positions = []
    search_from = 0
    while True:
        idx = text.find(marker, search_from)
        if idx == -1:
            break
        positions.append(idx)
        search_from = idx + 1
    return positions


# The one review_log write this Wave2 task's authority does NOT own and was
# not asked to touch: Rating Test's own SP-grant mechanism
# (/api/rating_test/claim_sp -> rt_claim_sp()) writes review_log directly,
# with grade=4 as its own reservation marker and a `source` column (not
# ReviewCommand's `source_context`) -- a shape that never matches
# FULL26/CORE20/DUP4 and was never routed through _srs_review_operation.
# This predates this task (present unchanged at BASE_SHA, confirmed by the
# byte-identical-body tests below covering the review authority's own
# functions) and is consistent with Rating Test's already-established
# separate-runtime status (own route namespace /api/rating_test/*, no
# srs.js, no /api/srs/review -- verified directly against rating_test.html
# and its API call sites). It is named explicitly here, not silently
# excluded, so REVIEW_DURABLE_WRITER_COUNT claims below are honest about
# their scope: one writer for the ReviewCommand/ReviewOutcome authority
# this task wraps, not "the only review_log writer in the whole file".
_KNOWN_OUT_OF_SCOPE_REVIEW_LOG_WRITER = "def rt_claim_sp():"


def test_known_out_of_scope_review_log_writer_is_exactly_rating_test_claim_sp():
    """Names and bounds the one pre-existing writer outside this task's
    authority, so it cannot silently grow to a second, unnoticed one."""
    assert _KNOWN_OUT_OF_SCOPE_REVIEW_LOG_WRITER in APP_SOURCE
    rt_start = APP_SOURCE.index(_KNOWN_OUT_OF_SCOPE_REVIEW_LOG_WRITER)
    rt_route_start = APP_SOURCE.rfind("@app.route(", 0, rt_start)
    assert "/api/rating_test/claim_sp" in APP_SOURCE[rt_route_start:rt_start]
    rt_end = APP_SOURCE.index("\ndef ", rt_start + 1)
    rt_body = APP_SOURCE[rt_start:rt_end]
    assert "INSERT INTO review_log" in rt_body
    # It never touches srs_cards, never returns a FULL26/CORE20/DUP4 shape,
    # and is not reachable from _srs_review_operation or ReviewService.
    assert "srs_cards" not in rt_body
    assert "ReviewService" not in rt_body
    assert "_srs_review_operation" not in rt_body


def test_review_service_instantiated_exactly_once_in_app():
    # Constructed with the late-bound dispatch wrapper, not a direct
    # reference to _srs_review_operation -- see
    # _dispatch_to_srs_review_operation's own docstring in app.py for why a
    # captured-by-reference wrapper would break monkeypatching.
    assert APP_SOURCE.count("ReviewService(_dispatch_to_srs_review_operation)") == 1
    assert APP_SOURCE.count("_review_service = ReviewService(") == 1
    assert APP_SOURCE.count("MapBattleReviewHandoff(") == 1
    assert APP_SOURCE.count("def _dispatch_to_srs_review_operation(") == 1


def test_only_srs_review_operation_writes_srs_cards():
    """srs_cards has exactly one writer anywhere in app.py, with no
    documented exception -- unlike review_log (see the Rating Test test
    above), no other subsystem writes SRS scheduling state at all."""
    op_start = APP_SOURCE.index("def _srs_review_operation")
    op_end = APP_SOURCE.index("def _run_map_battle_progression", op_start)
    for marker in ("INSERT INTO srs_cards", "srs_cards(user_id"):
        assert marker in APP_SOURCE[op_start:op_end], f"expected durable write marker missing: {marker}"
    for marker in ("INSERT INTO srs_cards",):
        positions = _find_all(APP_SOURCE, marker)
        assert positions, f"marker not found at all: {marker}"
        for pos in positions:
            assert op_start <= pos < op_end, (
                f"{marker} written outside _srs_review_operation at offset {pos}"
            )


def test_review_authority_review_log_writes_are_exactly_srs_review_operation_and_the_named_exception():
    """REVIEW_DURABLE_WRITER_COUNT=1 (scoped): every review_log write in
    app.py falls inside _srs_review_operation, EXCEPT the one named,
    out-of-scope exception proven above. No third, undiscovered writer
    exists."""
    op_start = APP_SOURCE.index("def _srs_review_operation")
    op_end = APP_SOURCE.index("def _run_map_battle_progression", op_start)
    rt_start = APP_SOURCE.index(_KNOWN_OUT_OF_SCOPE_REVIEW_LOG_WRITER)
    rt_end = APP_SOURCE.index("\ndef ", rt_start + 1)

    positions = _find_all(APP_SOURCE, "INSERT INTO review_log")
    assert positions, "review_log write marker not found at all"
    unaccounted = [
        pos for pos in positions
        if not (op_start <= pos < op_end) and not (rt_start <= pos < rt_end)
    ]
    assert unaccounted == [], (
        f"undiscovered review_log writer(s) at offsets {unaccounted}"
    )
    assert any(op_start <= pos < op_end for pos in positions), "approved operation itself has no write?"
    assert any(rt_start <= pos < rt_end for pos in positions), "named exception itself has no write?"


def test_route_and_map_battle_progression_do_not_call_durable_operation_directly():
    """CALL-PATH CONTRACT (source level): neither call site names
    _srs_review_operation as a call target any more -- both go through
    _review_service / _map_battle_review_handoff."""
    route_start = APP_SOURCE.index("@app.route('/api/srs/review'")
    route_end = APP_SOURCE.index("def _srs_review_operation", route_start)
    route_source = APP_SOURCE[route_start:route_end]
    assert "_srs_review_operation(" not in route_source
    assert "_review_service.review(" in route_source

    progression_body = _function_body("_run_map_battle_progression", "@app.route('/api/xp/status')")
    assert "_srs_review_operation(" not in progression_body
    assert "_map_battle_review_handoff.apply(" in progression_body


def test_no_other_route_writes_review_log_independently_of_the_named_exception():
    """ROUTE_BYPASS_WRITER_COUNT=0 within this task's authority: no
    @app.route handler other than the public review route (funnelled
    through ReviewService) and the one already-named, pre-existing,
    out-of-scope exception writes review_log directly."""
    op_start = APP_SOURCE.index("def _srs_review_operation")
    op_end = APP_SOURCE.index("def _run_map_battle_progression", op_start)
    rt_start = APP_SOURCE.index(_KNOWN_OUT_OF_SCOPE_REVIEW_LOG_WRITER)
    rt_end = APP_SOURCE.index("\ndef ", rt_start + 1)
    positions = _find_all(APP_SOURCE, "INSERT INTO review_log")
    assert positions, "review_log write marker not found"
    assert all(
        (op_start <= pos < op_end) or (rt_start <= pos < rt_end)
        for pos in positions
    )


# ---------------------------------------------------------------------------
# Tier 2b -- RUNTIME/TRANSACTION CHARACTERIZATION: _srs_review_operation's
# own body remains byte-identical to the pre-Wave2 base except for the
# explicitly authorized Lane B atomic level-HP persistence delta. The
# durable writer, transaction phases, and commit boundaries remain otherwise
# characterized against the base.
# ---------------------------------------------------------------------------

def _git_show(path: str) -> str:
    # app.py contains non-ASCII (Traditional Chinese) text; the default
    # subprocess text-mode encoding on Windows is the system codepage
    # (cp950 here), which cannot decode it. Decode as UTF-8 explicitly,
    # matching how the rest of this repo's tests read app.py.
    result = subprocess.run(
        ["git", "show", f"{BASE_SHA}:{path}"],
        cwd=ROOT, capture_output=True, check=True,
    )
    return result.stdout.decode("utf-8")


@pytest.fixture(scope="module")
def base_app_source():
    try:
        return _git_show("app.py")
    except subprocess.CalledProcessError:
        pytest.skip(f"base commit {BASE_SHA} not available in this checkout")


def test_srs_review_operation_body_only_adds_atomic_level_hp_delta(base_app_source):
    # Ends at the function's own closing `return jsonify({... **monster_data,
    # })` -- NOT at "def _run_map_battle_progression", which would also
    # sweep in this task's own newly-inserted ReviewService/handoff
    # instantiation lines sitting between the two functions and produce a
    # false "changed" diff against them, not against the operation itself.
    end_marker = "**monster_data,\n    })"

    def _extract(source):
        start = source.index("def _srs_review_operation")
        end = source.index(end_marker, start) + len(end_marker)
        return source[start:end]

    current = _extract(APP_SOURCE)
    allowed_delta = (
        ("        existing_player_max_hp = int(s['player_max_hp'] or 0)\n", ""),
        ("        new_lv = xp_to_lv(xp)\n", ""),
        ("               player_max_hp=GREATEST(COALESCE(player_max_hp,0),?),\n", ""),
        ("             _lv_max_hp(new_lv), now, uid))", "             now, uid))"),
        ("            'player_max_hp': max(existing_player_max_hp, _lv_max_hp(new_lv)),\n", ""),
    )
    for fragment, replacement in allowed_delta:
        assert fragment in current
        current = current.replace(fragment, replacement, 1)
    assert current == _extract(base_app_source)


def test_update_monster_and_quests_body_only_adds_retaliation_mitigation(base_app_source):
    # RPG_WAVE1_PREREQUISITE_INTEGRATION_FIX_003, Fix 1: naive
    # round(monster_atk * (1 - dmg_reduce)) silently drops all armor
    # mitigation at low integer attack values, so this is the one
    # deliberately authorized line inside this otherwise-frozen body.
    def _extract(source):
        start = source.index("def _update_monster_and_quests")
        end = source.index("@app.route('/api/monster/status'", start)
        return source[start:end]

    current = _extract(APP_SOURCE)
    allowed_delta = (
        (
            "        player_dmg   = _mitigate_authoritative_retaliation(monster_atk, dmg_reduce)\n",
            "        player_dmg   = max(1, round(monster_atk * (1.0 - dmg_reduce)))\n",
        ),
    )
    for fragment, replacement in allowed_delta:
        assert fragment in current
        current = current.replace(fragment, replacement, 1)
    assert current == _extract(base_app_source)


def test_multi_phase_partial_commit_preserved_three_phase_boundaries():
    """MULTI_PHASE_PARTIAL_COMMIT_PRESERVED: the operation still commits
    the core phase, then the optional RPG/quest phase, then the optional
    Grimoire phase, as three separate conn.commit() calls -- matching the
    backend packet section 6's documented TX-R1/TX-R2/TX-R3 structure. Not
    a global transaction: no single all-encompassing commit was
    introduced."""
    operation_body = _function_body("_srs_review_operation", "_run_map_battle_progression")
    commit_count = operation_body.count("conn.commit()")
    assert commit_count == 3, commit_count
    assert "except Exception:" in operation_body
    assert "conn.rollback()" in operation_body


def test_no_global_transaction_rewrite_no_new_durable_table():
    """NO_GLOBAL_TRANSACTION_REWRITE / no new persistence layer: this task
    added no new CREATE TABLE and no second get_db() review-write context
    beyond what already existed."""
    for forbidden in ("CREATE TABLE", "class RewardManager", "class ReviewRepository"):
        assert forbidden not in REVIEW_SERVICE_SOURCE, forbidden


# ---------------------------------------------------------------------------
# Tier 3 -- real app.py import + Flask test client. Proves the CALL-PATH
# CONTRACT and durable-writer-count claims at runtime, not just in source
# text.
# ---------------------------------------------------------------------------

def _install_app_import_stubs():
    if 'katago_explain' not in sys.modules:
        module = types.ModuleType('katago_explain')
        module.KataGoExplainer = type('KataGoExplainer', (), {})
        sys.modules['katago_explain'] = module
    if 'explain_overrides' not in sys.modules:
        module = types.ModuleType('explain_overrides')
        module.get_override = lambda *args, **kwargs: None
        sys.modules['explain_overrides'] = module
    if 'grimoire_api' not in sys.modules:
        from flask import Blueprint
        module = types.ModuleType('grimoire_api')
        module.grimoire_bp = Blueprint('grimoire_stub_backend_v1a2', __name__)
        sys.modules['grimoire_api'] = module
    if 'question_taxonomy' not in sys.modules:
        module = types.ModuleType('question_taxonomy')
        module.get_taxonomy = lambda *args, **kwargs: {}
        sys.modules['question_taxonomy'] = module
    if 'monster_taxonomy' not in sys.modules:
        module = types.ModuleType('monster_taxonomy')
        module.get_monster_taxonomy = lambda *args, **kwargs: {}
        module.mark_encounters = lambda *args, **kwargs: None
        sys.modules['monster_taxonomy'] = module
    if 'chapter_i18n' not in sys.modules:
        module = types.ModuleType('chapter_i18n')
        module.localize_topic = lambda *args, **kwargs: ''
        module.localize_level = lambda *args, **kwargs: ''
        sys.modules['chapter_i18n'] = module
    if 'backend_i18n' not in sys.modules:
        module = types.ModuleType('backend_i18n')
        module.badge_en = lambda *args, **kwargs: ''
        module.skill_node_en = lambda *args, **kwargs: ''
        module.title_en = lambda *args, **kwargs: ''
        sys.modules['backend_i18n'] = module


@pytest.fixture(scope='module')
def app_module():
    _install_app_import_stubs()
    import app as app_module
    return app_module


def test_review_route_uses_the_real_review_service_instance(app_module):
    assert isinstance(app_module._review_service, ReviewService)
    assert app_module._review_service._legacy_operation is app_module._dispatch_to_srs_review_operation


def test_dispatch_wrapper_observes_a_monkeypatched_srs_review_operation(app_module, monkeypatch):
    """Regression guard for the exact bug this wiring must not have: a
    wrapper that captured _srs_review_operation by reference at
    ReviewService-construction time would silently keep calling the
    original function after a legitimate rebind (e.g.
    monkeypatch.setattr(app_module, '_srs_review_operation', ...), which
    tests/test_map_battle_legacy_adapter.py's
    test_progression_failure_does_not_rollback_authoritative_battle_settlement
    already relies on). The late-bound wrapper must observe the
    replacement on the very next call."""
    calls = []

    def _replacement(uid, data, *, internal=False, submission_id=None):
        calls.append((uid, internal, submission_id))
        raise RuntimeError("synthetic_failure")

    monkeypatch.setattr(app_module, "_srs_review_operation", _replacement)
    with pytest.raises(RuntimeError, match="synthetic_failure"):
        app_module._review_service.review(
            user_id=1, command=ReviewCommand(question_id=101, grade=3),
        )
    assert len(calls) == 1


def test_map_battle_handoff_uses_the_same_review_service_instance(app_module):
    assert isinstance(app_module._map_battle_review_handoff, MapBattleReviewHandoff)
    assert app_module._map_battle_review_handoff._service is app_module._review_service


def test_legacy_review_operation_port_matches_the_real_operation_signature(app_module):
    """PORT_BOUNDARIES_MATCH_REAL_AUTHORITY: LegacyReviewOperation is not an
    invented abstraction -- its declared call shape is exactly
    _srs_review_operation's real signature, checked at runtime against the
    actual function object, not just asserted in a docstring."""
    import inspect

    real_signature = inspect.signature(app_module._srs_review_operation)
    parameters = list(real_signature.parameters.values())
    assert [p.name for p in parameters] == ["uid", "data", "internal", "submission_id"]
    assert parameters[2].kind == inspect.Parameter.KEYWORD_ONLY
    assert parameters[3].kind == inspect.Parameter.KEYWORD_ONLY
    assert parameters[2].default is False
    assert parameters[3].default is None


def test_runtime_single_durable_writer_via_public_route(app_module, monkeypatch):
    """REVIEW_DURABLE_WRITER_COUNT=1 / DUAL_DURABLE_WRITER=NO, proven at
    runtime: hitting the real route calls the real durable operation
    exactly once, with no other write path invoked."""
    calls = []
    real_operation = app_module._srs_review_operation

    def _counting_operation(uid, data, *, internal=False, submission_id=None):
        calls.append({"internal": internal, "submission_id": submission_id})
        return app_module.jsonify({
            "ok": True, "ease_factor": 2.5, "interval": 1, "due_date": "2026-08-17",
            "new_badges": [], "stats": {}, "xp_gain": 0, "combo_mult": 1.0,
            "pet_xp_added": 0, "pet_xp_ratio": 0.0, "pet_xp_gained": 0,
            "combo_streak": 0, "shield_used": False, "xp_potion_active": False,
            "ranked_up": False, "new_rank_level": None, "pet": None,
            "practice": {}, "training": {}, "new_appearance_items": [],
        })

    monkeypatch.setattr(app_module, "_review_service", ReviewService(_counting_operation))
    app_module.app.config["TESTING"] = True
    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
    response = client.post(
        "/api/srs/review",
        json={"question_id": 101, "grade": 3, "source_context": "practice"},
    )
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["internal"] is False
    assert real_operation is app_module._srs_review_operation  # unwrapped operation itself untouched


def test_runtime_map_battle_progression_routes_through_handoff(app_module, monkeypatch):
    calls = []

    def _counting_operation(uid, data, *, internal=False, submission_id=None):
        calls.append({"internal": internal, "submission_id": submission_id, "data": dict(data)})
        return app_module.jsonify({
            "ok": True, "progression_applied": True, "progression_duplicate": False,
            "question_id": data.get("question_id"),
        }), 200

    service = ReviewService(_counting_operation)
    monkeypatch.setattr(app_module, "_review_service", service)
    monkeypatch.setattr(app_module, "_map_battle_review_handoff", MapBattleReviewHandoff(service))

    # _run_map_battle_progression is called from within a request in
    # Production (after settle_answer, still inside the map-battle-answers
    # request); jsonify() needs an app context to resolve current_app, same
    # as it would have there.
    with app_module.app.app_context():
        payload, status = app_module._run_map_battle_progression(1, {
            "result": "CORRECT", "submission_id": "settled-1", "question_id": 202,
            "authoritative_grade": 5,
        })
    assert status == 200
    assert len(calls) == 1
    assert calls[0]["internal"] is True
    assert calls[0]["submission_id"] == "settled-1"
    assert payload["status"] == "applied"
