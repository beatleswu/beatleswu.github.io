"""P0 Lane B regression contract for authenticated Adventure progression.

These tests keep the repair narrow: the server-owned Map Battle progression
writer is characterized, while the client boundary is exercised through a
small Node contract runner.  No Production configuration or historical data
is touched.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from map_battle_persistence import (
    DEFAULT_MAP_BATTLE_V1_MODE,
    MAP_BATTLE_V1_MODES,
    get_map_battle_v1_mode,
)
from map_battle_runtime import mode_eligible


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")
RUNNER = ROOT / "tests" / "e2e" / "run_p0_lane_b_adventure_forward_repair.mjs"


def _function_block(name: str, end_name: str) -> str:
    start = INDEX.index(f"function {name}")
    end = INDEX.index(f"function {end_name}", start)
    return INDEX[start:end]


def test_supported_modes_and_fail_closed_default_are_unchanged(monkeypatch):
    assert MAP_BATTLE_V1_MODES == ("off", "dark", "admin", "allowlist", "percentage", "global")
    assert DEFAULT_MAP_BATTLE_V1_MODE == "off"
    monkeypatch.delenv("E10_MAP_BATTLE_V1_MODE", raising=False)
    assert get_map_battle_v1_mode() == "off"


def test_global_target_admits_authenticated_admin_and_non_admin():
    assert mode_eligible("global", 101, {}) is True
    assert mode_eligible("global", 202, {"admin": True}) is True


def test_admin_mode_remains_admin_only_and_does_not_grant_privilege():
    assert mode_eligible("admin", 101, {"admin": False}) is False
    assert mode_eligible("admin", 202, {"admin": True}) is True


def test_anonymous_boundary_is_owned_by_login_required_routes():
    route_start = APP.index("@app.route('/api/adventure/map-battles/v1/attempts'")
    route_prefix = APP[APP.rfind("@login_required", 0, route_start):route_start]
    assert "@login_required" in route_prefix
    assert "if 'user_id' not in session" in APP
    assert "return jsonify({'error': '未登入', 'redirect': '/login'}), 401" in APP


def test_adventure_failure_has_explicit_non_practice_provenance():
    metadata = _function_block("_currentReviewMetadata", "_incident002ServerPracticeFlow")
    practice_start = INDEX.index("function _incident002ServerPracticeFlow")
    practice_end = INDEX.index("let playerColor", practice_start)
    practice = INDEX[practice_start:practice_end]
    assert "ADVENTURE_UNAVAILABLE_SOURCE_CONTEXT = 'adventure_unavailable'" in INDEX
    assert "adventureUnavailable" in metadata
    assert "ADVENTURE_UNAVAILABLE_SOURCE_CONTEXT" in metadata
    assert "!_isAdventureZonePractice()" in practice


def test_load_and_submit_paths_fail_closed_before_legacy_practice():
    submit = _function_block("submitSRS", "loadQuestion")
    load = _function_block("_loadQuestionImplementation", "onBoardClick")
    assert "_blockAdventureProgression('answer_submission_without_active_map_battle')" in submit
    assert submit.index("_blockAdventureProgression('answer_submission_without_active_map_battle')") < submit.index("const incident002Practice")
    assert "reason: 'adventure_progression_unavailable'" in load
    assert load.index("reason: 'adventure_progression_unavailable'") < load.index("_syncE10BattleActions(true)")


def test_disabled_and_ineligible_provider_results_are_blocked():
    prepare = _function_block("_prepareMapBattleV1ForQuestion", "_mapBattleV1IsStaleError")
    assert "code === 'map_battle_v1_disabled' || code === 'map_battle_mode_not_eligible'" in prepare
    assert "_blockAdventureProgression(code)" in prepare
    assert "no answer fallback was used" in INDEX


def test_server_success_path_and_practice_policy_remain_separate():
    assert "source_context = f'{_MAP_BATTLE_PROGRESS_MARKER_PREFIX}{submission_id}'" in APP
    assert "ProgressCreditPolicy.FIRST_PASS_ONLY if internal" in APP
    assert "else ProgressCreditPolicy.NEVER" in APP
    assert "_map_battle_progression_already_applied(conn, uid, source_context)" in APP
    assert "'progression_duplicate': True" in APP
    assert "SRS.practiceAnswer" in INDEX


def test_existing_duplicate_and_reward_guards_are_not_bypassed():
    assert "response.duplicate !== true" in INDEX
    assert "nextQuestion({ mapBattleV1Transition: true });" in INDEX
    assert "_update_monster_and_quests" not in _function_block("_submitMapBattleV1IfActive", "isBeginnerVillageAdventureResult")


def test_node_contract_covers_adventure_failure_practice_separation():
    result = subprocess.run(
        ["node", str(RUNNER)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = f"stdout={result.stdout}\nstderr={result.stderr}"
    assert result.returncode == 0, output
