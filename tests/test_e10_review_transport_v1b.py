"""E10 Frontend V1B B3 ReviewTransport contract tests.

The source-characterization tests do not import the Flask application or
touch a database.  The final test invokes the Node contract runner directly;
no xfail/skip hides a missing implementation seam.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import review_contracts


APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
INDEX_SOURCE = (ROOT / "index.html").read_text(encoding="utf-8")
SRS_SOURCE = (ROOT / "srs.js").read_text(encoding="utf-8")
REVIEW_TRANSPORT_SOURCE = (ROOT / "js" / "game" / "review_transport.js").read_text(encoding="utf-8")
RUNNER = ROOT / "tests" / "e2e" / "run_e10_review_transport_contract.mjs"
FUTURE_MODULE = ROOT / "js" / "game" / "review_transport.js"


def test_review_transport_is_the_only_frontend_review_post():
    assert "fetch('/api/srs/review'" not in INDEX_SOURCE
    assert "fetch('/api/srs/review'" not in SRS_SOURCE
    assert "window.ReviewTransport.review(observerCommand)" in INDEX_SOURCE
    assert "_reviewTransport.legacyReview(" in SRS_SOURCE
    assert "request.question_id = value.question_id" in REVIEW_TRANSPORT_SOURCE
    assert "request.is_scaffolding = !!value.is_scaffolding" in REVIEW_TRANSPORT_SOURCE

    assert "@app.route('/api/srs/review', methods=['POST'])" in APP_SOURCE
    assert "if not internal and (qid is None or grade not in (0,3,5)):" in APP_SOURCE
    assert "source_context = str(data.get('source_context') or 'practice')" in APP_SOURCE


def test_rejected_review_paths_cannot_advance_or_dispatch():
    review_start = INDEX_SOURCE.index("data = await SRS.review")
    committed_start = INDEX_SOURCE.index("_e10AcceptanceTrace('REVIEW_COMMITTED'", review_start)
    failure_region = INDEX_SOURCE[review_start:committed_start]

    for forbidden in (
        "nextQuestion(",
        "loadQuestion(",
        "_handleBossAnswer(",
        "_submitMapBattleV1IfActive(",
        "_dispatchCommittedReviewPresentation(",
        "_syncGuildQuestProgress(",
    ):
        assert forbidden not in failure_region
    assert "return;" in failure_region
    assert "_applyDailyLimit();" in failure_region


def test_current_identity_and_mode_values_are_not_expanded_by_the_prep():
    assert "boss_trial:${_bossAttemptId}" in INDEX_SOURCE
    assert "setId?'premium_weekly':(_guildQuestMode?'guild_quest':'practice')" in INDEX_SOURCE
    assert "training_set_id:setId?Number(setId):null" in INDEX_SOURCE
    assert "is_scaffolding:params.get('scaffold')==='1'||!!_premiumWeeklyMode?.rescue" in INDEX_SOURCE
    assert "_mapBattleV1Mode === 'active'" in INDEX_SOURCE
    assert "await _submitMapBattleV1IfActive(_mapBattleV1Moves);" in INDEX_SOURCE


def test_b2_accepted_review_shape_sets_are_exact_and_legacy_compatible():
    assert len(review_contracts.CORE_20_FIELDS) == 20
    assert len(review_contracts.FULL_26_FIELDS) == 26
    assert review_contracts.FULL_26_FIELDS[:20] == review_contracts.CORE_20_FIELDS
    assert review_contracts.FULL_26_FIELDS[20:] == review_contracts.T2_OPTIONAL_FIELDS
    assert review_contracts.INTERNAL_DUPLICATE_4_FIELDS == (
        "ok",
        "progression_applied",
        "progression_duplicate",
        "question_id",
    )
    # V1A2 (backend Wave2 closure): the route now dispatches through
    # ReviewService rather than calling the durable operation directly --
    # see tests/test_e10_backend_review_service_v1a2.py for the seam's own
    # call-path-contract proof. The durable operation itself, whose field
    # set this test still characterizes below, is unchanged. Scoped to the
    # route's own source span: _dispatch_to_srs_review_operation
    # legitimately contains "return _srs_review_operation(" further down
    # the file (that late-bound call is the whole point of the wrapper --
    # see its docstring in app.py), so an unscoped file-wide check would be
    # a false positive against that, not a real route regression.
    route_start = APP_SOURCE.index("@app.route('/api/srs/review'")
    route_end = APP_SOURCE.index("def _srs_review_operation", route_start)
    route_source = APP_SOURCE[route_start:route_end]
    assert "_review_service.review(user_id=session['user_id'], command=command)" in route_source
    assert "return _srs_review_operation(" not in route_source
    for field in review_contracts.CORE_20_FIELDS:
        assert f"'{field}'" in APP_SOURCE
    for field in review_contracts.T2_OPTIONAL_FIELDS:
        assert f"'{field}'" in APP_SOURCE


def test_contract_runner_is_scaffolded_without_hidden_expected_red_markers():
    source = RUNNER.read_text(encoding="utf-8")
    assert "MISSING_FUTURE_REVIEW_TRANSPORT_SEAM" in source
    assert "js/game/review_transport.js" in source
    assert "pytest.mark.xfail" not in source
    assert "pytest.mark.skip" not in source


def test_future_review_transport_contract_runner():
    result = subprocess.run(
        ["node", str(RUNNER)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = f"stdout={result.stdout}\nstderr={result.stderr}"
    if not FUTURE_MODULE.exists():
        assert result.returncode == 2, output
        assert "MISSING_FUTURE_REVIEW_TRANSPORT_SEAM" in output, output
    assert result.returncode == 0, output
