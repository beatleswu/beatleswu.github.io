"""E042 contracts for the cleared-zone replay CTA regression.

These checks stay at the frontend contract boundary.  They do not import the
server or derive progression/reward state from client fields.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
ADAPTER = (ROOT / "js/e9/adapters/adventure_state.js").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
OWNER_E2E = (ROOT / "tests/e2e/run_e10_lord_trial_owner_acceptance_regression.mjs").read_text(
    encoding="utf-8"
)


def test_cleared_primary_replay_is_not_blocked_by_generic_question_runtime():
    assert "function isServerBackedLordAction(action)" in WORLD
    assert "action.kind === 'challenge_lord' || action.kind === 'replay_completed'" in WORLD
    assert "if (state.authorityUnavailable) return false;" in WORLD
    assert "return isServerBackedLordAction(action) || state.questionRuntimeState === 'ready';" in WORLD
    assert "var enabled = contract.enabled && adventureActionRuntimeReady(contract, state);" in WORLD
    assert "if (!adventureActionRuntimeReady(contract, state)) return false;" in WORLD


def test_cta_priority_keeps_replay_primary_and_star_repair_secondary():
    cleared_branch = WORLD.split("if (zone.cleared === true || zone.status === 'completed')", 1)[1]
    assert "kind: 'replay_completed'" in cleared_branch.split("function secondaryCtaContract", 1)[0]
    assert "if (zone.cleared === true && Number(zone.stars || 0) < 3)" in WORLD
    assert "kind: 'replenish_stars'" in WORLD
    assert "primary_action" in ADAPTER


def test_replay_uses_existing_lord_entry_and_server_settlement():
    assert "window.ensureLegacyAdventureMapReady({ reuseE9Adapter: true })" in WORLD
    assert "window.openAdventureBossFromQuestCard(contract.targetZoneKey)" in WORLD
    assert "fetch(" not in WORLD
    assert "fetch('/api/adventure/boss/finish'" in INDEX
    assert "const replay = Boolean(data.replay || data.attempt_mode === 'replay' || _bossReplay);" in INDEX
    assert "_adventureProgress = data.zones || _adventureProgress;" in INDEX
    assert "passed: data.passed" in INDEX
    assert "e10:adventure-state-updated" in INDEX


def test_selection_does_not_replace_authoritative_player_location():
    assert "current_zone_key is server authority" in WORLD
    assert "selectedZoneKey, recommended" in WORLD
    assert "state.currentPlayerZoneKey = current ? current.key : null;" in WORLD
    assert "state.selectedZoneKey = selected ? selected.key : null;" in WORLD
    assert "currentPlayerZoneKey: state.currentPlayerZoneKey" in WORLD
    assert "selectedZoneKey: state.selectedZoneKey" in WORLD
    assert "cleared: status === 'completed'" in ADAPTER
    assert "currentZoneKey: currentZoneKey" in ADAPTER
    assert "localStorage" not in ADAPTER


def test_replay_copy_is_bilingual_and_has_no_parallel_star_or_reward_authority():
    for key in (
        "index.adv.quest_rechallenge_boss",
        "e10.zone1.lord.replay_start",
        "e10.zone1.lord.replay_reward",
        "e10.zone1.result.replay.title",
        "e10.zone1.result.replay.line",
        "e10.zone1.result.replay.fail_line",
        "e10.world_stage.replenish_stars",
    ):
        start = I18N.index(f"'{key}'")
        entry = I18N[start:I18N.index("\n", start)]
        assert "en:" in entry and "zh:" in entry, key
    assert "No first-clear reward is granted." in I18N
    assert "清關狀態與獎勵維持不變。" in I18N


def test_static_cache_revision_covers_only_changed_world_stage_module():
    assert '/js/e9/world_stage.js?v=20260828e042s1' in INDEX
    assert '/js/e9/right_cards.js?v=20260828e040s1' in INDEX
    assert '/css/e9/reference_world_map.css?v=20260828e040s1' in INDEX


def test_owner_regression_distinguishes_replay_from_question_pool_star_repair():
    assert "questionPoolAvailable = false" in OWNER_E2E
    assert "body: JSON.stringify(questionPoolAvailable" in OWNER_E2E
    assert "secondary training CTA should fail closed without a question pool" in OWNER_E2E
    assert "runReplayCta(browser, origin, 1, { questionPoolAvailable: true })" in OWNER_E2E
