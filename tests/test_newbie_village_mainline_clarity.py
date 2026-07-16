from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")


def test_newbie_village_is_first_zone_and_keeps_identity():
    first = INDEX.index("const ADVENTURE_ZONES")
    block = INDEX[first:first + 500]
    assert "key:'k26_30'" in block
    assert "name:'圍棋新手村'" in block
    assert "nameEn:'Beginner Village'" in block


def test_first_journey_copy_and_single_cta_are_defined():
    for key in (
        "adventure.newbie.first_stop_title",
        "adventure.newbie.summary",
        "adventure.newbie.step_battle",
        "adventure.newbie.step_progress",
        "adventure.newbie.step_boss",
        "adventure.newbie.cta_begin",
        "adventure.newbie.cta_continue",
        "adventure.newbie.cta_boss",
        "adventure.newbie.first_star_hint",
    ):
        assert key in I18N
    assert "_renderNewbieVillageMainline" in INDEX
    assert "newbie-first-journey-card" in INDEX
    assert "newbieFirstJourney = selectedZone.key === 'k26_30'" in INDEX


def test_first_journey_preserves_progress_rules_and_secondary_details():
    assert "unlock_pct: 30" in INDEX
    assert "boss_exam_size: 20" in INDEX
    assert "boss_pass_score: 16" in INDEX
    assert "adventure.newbie.training_details" in INDEX
    assert "_adventureQuestDetailLines(zone).join('')" in INDEX
    assert "_adventureBestScoreValue(zone)" in INDEX


def test_encounter_context_connects_beginner_village_to_adventure_goal():
    start = INDEX.index("function renderAdventureZoneMonster")
    block = INDEX[start:start + 1800]
    assert "adventure.newbie.encounter_title" in block
    assert "adventure.newbie.encounter_objective" in block
    assert "index.battle.adventure_encounter" in block
    assert "_isAdventureZonePractice" in INDEX
    assert "fetch('/api/monster/status'" in INDEX
    assert "if (_isAdventureZonePractice())" in INDEX


def test_first_journey_does_not_change_adventure_question_or_battlefield_boundaries():
    assert "startAdventureStage(zoneKey)" in INDEX
    assert "enterAdventureZoneInPage(zone)" in INDEX
    assert "/api/adventure/bootstrap" in INDEX
    assert "Daily Bounty" in I18N


def test_service_worker_version_is_current_for_this_frontend_change():
    assert "const VERSION     = 'v191-e9-newbie-village-integration'" in SW


def test_beginner_village_post_answer_continuation_controls_are_localized():
    assert "isBeginnerVillageAdventureResult" in INDEX
    assert "adventure.newbie.continue_training" in I18N
    assert "adventure.newbie.return_map" in I18N
    assert "adventure.newbie.encounter_complete" in I18N
    assert "showBeginnerVillageEncounterContinuation" in INDEX
    assert "returnToAdventureMapAfterEncounter" in INDEX
    assert "shouldAdvance = false" in INDEX


def test_post_answer_continuation_does_not_claim_fixed_progress_increment():
    start = INDEX.index("function showBeginnerVillageEncounterContinuation")
    end = INDEX.index("function returnToAdventureMapAfterEncounter", start)
    block = INDEX[start:end]
    assert "+1" not in block
