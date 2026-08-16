"""E10 Frontend V1B B3 ReviewTransport contract preparation tests.

The source-characterization tests are current-base checks and do not import
the Flask application or touch a database.  The final test invokes the
future-facing Node runner.  On the pinned base it has one deliberate red with
the explicit reason MISSING_FUTURE_REVIEW_TRANSPORT_SEAM; no xfail/skip hides
that missing implementation seam.
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
RUNNER = ROOT / "tests" / "e2e" / "run_e10_review_transport_contract.mjs"
FUTURE_MODULE = ROOT / "js" / "game" / "review_transport.js"


def test_current_request_boundary_is_the_canonical_legacy_post():
    assert "fetch('/api/srs/review'" in SRS_SOURCE
    assert "credentials: 'include'" in SRS_SOURCE
    assert "method: 'POST'" in SRS_SOURCE
    assert "headers: { 'Content-Type': 'application/json' }" in SRS_SOURCE
    assert "question_id: qid, grade," in SRS_SOURCE
    assert "unit_name: unitName || null" in SRS_SOURCE
    assert "unit_done: !!unitDone" in SRS_SOURCE
    assert "response_ms: metadata.response_ms ?? null" in SRS_SOURCE
    assert "source_context: metadata.source_context || 'practice'" in SRS_SOURCE
    assert "training_set_id: metadata.training_set_id ?? null" in SRS_SOURCE
    assert "is_scaffolding: !!metadata.is_scaffolding" in SRS_SOURCE

    assert "@app.route('/api/srs/review', methods=['POST'])" in APP_SOURCE
    assert "if not internal and (qid is None or grade not in (0,3,5)):" in APP_SOURCE
    assert "source_context = str(data.get('source_context') or 'practice')" in APP_SOURCE


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
    assert "return _srs_review_operation(" in APP_SOURCE
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
