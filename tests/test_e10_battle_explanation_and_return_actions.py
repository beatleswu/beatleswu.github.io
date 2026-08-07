from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")


def _function_block(name: str, end_name: str) -> str:
    start = INDEX.index(f"function {name}")
    end = INDEX.index(f"function {end_name}", start)
    return INDEX[start:end]


def test_e10_battle_exposes_explicit_explanation_and_map_actions():
    assert 'id="btn-e10-battle-explain"' in INDEX
    assert 'onclick="showE10BattleExplanation()"' in INDEX
    assert 'id="btn-adventure-return"' in INDEX
    assert 'onclick="returnToAdventureMapAfterEncounter()"' in INDEX
    actions = _function_block("_syncE10BattleActions", "showE10BattleExplanation")
    action_state = _function_block("_isE10BattleActionState", "_syncE10BattleActions")
    assert "_isAdventureZonePractice()" in action_state
    assert "_isE10BattleShell()" in action_state
    assert "_mapBattleV1Mode === 'active'" in action_state
    assert "_mapBattleV1Mode === 'active'" not in actions
    assert "const battleVisible = active === true && _isE10BattleActionState();" in actions
    assert "const revealVisible = battleVisible && _isE10BattleRevealAvailable();" in actions
    assert "display = revealVisible ? 'inline-flex' : 'none'" in actions
    assert "explain.hidden = !revealVisible" in actions
    assert "explain.tabIndex = revealVisible ? 0 : -1" in actions


def test_explanation_action_reuses_canonical_explanation_path_without_settlement():
    action = _function_block("showE10BattleExplanation", "returnToAdventureMapAfterEncounter")
    assert "_isE10BattleRevealAvailable()" in action
    assert "showExplanation(_lastWrongMove || null)" in action
    assert "submitSRS" not in action
    assert "/api/srs/review" not in action
    assert "adapter.submit" not in action


def test_return_invalidates_battle_page_callbacks_and_refreshes_map_without_abandoning_attempt():
    action = _function_block("returnToAdventureMapAfterEncounter", "renderAdventureZoneMonster")
    assert "_mapBattleV1LifecycleGeneration += 1" in action
    assert "_mapBattleV1PrepareSerial += 1" in action
    assert "_clearMapBattleV1Transition()" in action
    assert "invalidateE9AdventureStateCache()" in action
    assert "publishAdventureShellOwner(E10_MAP_SHELL_OWNER)" in action
    assert "window.location.href = '/?adventure=1'" in action
    assert "_clearMapBattleV1Resume()" not in action


def test_in_page_map_to_battle_publishes_owner_before_action_reconciliation():
    entry = _function_block("enterAdventureZoneInPage", "adventureActiveZone")
    owner_position = entry.index("publishAdventureShellOwner(E10_BATTLE_SHELL_OWNER)")
    load_position = entry.index("loadQuestion(target, { resumeState:")
    assert owner_position < load_position
    assert "data-adventure-shell-owner" not in entry
    assert "publishAdventureShellOwner(E10_MAP_SHELL_OWNER)" in entry
    assert "entryGeneration" in entry
    # Same-page re-entry must consult the same server-issued resume the
    # reload path already uses -- otherwise it silently re-picks the first
    # eligible question instead of resuming wherever "下一題" already
    # advanced to (E10_BATTLE_REENTRY_I18N_IPAD_PORTRAIT_CLOSURE FIX A).
    assert "await _resolveMapBattleV1Resume(zone.key, unitQs)" in entry
    assert "resume?.target || _pickAdventureTarget(unitQs)" in entry


def test_active_attempt_resume_storage_remains_authoritative_for_return_flow():
    resume = _function_block("_persistMapBattleV1Resume", "_readMapBattleV1Resume")
    prepare = _function_block("_prepareMapBattleV1ForQuestion", "_mapBattleV1IsStaleError")
    assert "sessionStorage.setItem(_MAP_BATTLE_V1_RESUME_STORAGE_KEY" in resume
    assert "adapter.refreshBattle(state)" in prepare
    assert "_clearMapBattleV1Resume();" in prepare
