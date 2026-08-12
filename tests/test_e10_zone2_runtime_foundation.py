"""Focused contracts for the Owner-authorized E10 Zone 2 foundation.

These are source-level contracts for the runtime boundary: server-owned
Historical Mastery/Lord state, Zone 2-only cinematic phase slots, explicit
Lord Card -> ritual entry, and Lord-success-only POST_CLEAR presentation.
Owner-locked final art/audio bytes are verified separately by
test_e10_zone2_audio_integration.py.
"""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")
WORLD = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")


def _block(source, start, end):
    begin = source.index(start)
    finish = source.index(end, begin)
    return source[begin:finish]


def test_zone2_uses_slime_swarm_lord_authority_not_bee_humanoid():
    assert "'k21_25': {'key': 'swarm_lord'" in APP
    assert "'name': '史萊姆群領主'" in APP
    zone2_story = _block(INDEX, "    k21_25: {", "    k16_20: {")
    assert "boss: '史萊姆群領主'" in zone2_story
    assert "avatar: '🟢'" in zone2_story
    assert "🐝" not in zone2_story
    assert "Swarm Lord" in INDEX


def test_zone2_first_entry_and_replay_use_server_cinematic_key():
    assert "range(1, 11)" in APP
    assert "if (zoneKey === 'k21_25') return 'e10_zone2_intro_v1';" in WORLD
    dispatch = _block(WORLD, "function dispatchZone1Entry(root, zone, state)", "  function replayAdventureIntro")
    assert "cinematicSeen(state, cinematicKey)" in dispatch
    assert "mode: 'first_entry'" in dispatch
    replay = _block(WORLD, "function replayAdventureIntro(zoneKey)", "  function updateAdventureCinematicState")
    assert "zoneKey !== ACTIVE_INTRO_ZONE_KEY && zoneKey !== 'k21_25'" in replay
    assert "mode: 'manual_replay'" in replay


def test_zone2_first_entry_returns_to_zone_card():
    finish = _block(INDEX, "async function finishIntroFilm(zone) {", "\nfunction skipIntroFilm()")
    assert "zone?.key === 'k26_30' || zone?.key === 'k21_25'" in finish
    assert "await markAdventureIntroSeen(zone);" in finish
    assert "window.E9.showAdventureZoneCard(zone.key);" in finish


def test_zone2_replay_button_is_manual_and_presentational_only():
    replay = _block(INDEX, "function replayIntroFilm()", "// opts.timeline / opts.onComplete")
    assert "zone.key === 'k26_30' || zone.key === 'k21_25'" in replay
    assert "mode: replayMode" in replay
    assert "playNewbieVillageIntroFilm(zone, replayMode ? { mode: replayMode } : {});" in replay


def test_zone2_audio_slot_becomes_playable_only_after_owner_release():
    play_voice = _block(INDEX, "    function playVoice(beat, onDone) {", "    function activateShot(shotIndex)")
    assert "beat.audioSlot && beat.ownerAudioPending !== true" in play_voice
    assert "const playableBeat" in play_voice
    assert "playAssetVoice(playableBeat, onDone);" in play_voice


def test_zone2_phase_slots_are_4_3_3_and_owner_locked():
    slots = _block(INDEX, "function _zone2CinematicPhaseSlots", "\nfunction getIntroFilmLocaleConfig")
    assert "bossReadyTimeline" in slots
    assert "postClearTimeline" in slots
    assert re.search(r"shot\(4,", slots)
    assert re.search(r"shot\(5,", slots)
    assert re.search(r"shot\(6,", slots)
    assert re.search(r"shot\(7,", slots)
    assert re.search(r"shot\(8,", slots)
    assert re.search(r"shot\(9,", slots)
    assert "ownerArtPending: false" in slots
    assert "ownerAudioPending: false" in slots
    assert "/assets/storyboards/e10_z2_shot" in slots
    assert "/assets/e10/audio/zone2/" in INDEX


def test_zone2_boss_ready_is_presentational_and_does_not_auto_start_trial():
    ready = _block(INDEX, "function _maybeTriggerZone2BossReadyFilm", "\nfunction playZone2PostClearFilm")
    assert "_adventureBossReady(zone)" in ready
    assert "adventureBossReadyFilmSeen(zone)" in ready
    assert "markAdventureBossReadyFilmSeen(zone)" in ready
    assert "playZone2BossReadyFilm(zone)" in ready
    assert "fetch(" not in ready
    assert "_startBossBattleNow" not in ready


def test_zone2_lord_card_and_ritual_are_explicit_player_actions():
    start = _block(INDEX, "async function startBossBattle(zoneKey)", "\nasync function openAdventureBossFromQuestCard")
    assert "zone.key === 'k21_25'" in start
    assert "showZone2LordChallengeCard(zone)" in start
    card = _block(INDEX, "function showZone2LordChallengeCard(zone)", "\nfunction startZone2LordRitual")
    assert "e10.zone2.lord.title" in card
    assert "btn.onclick = () => startZone2LordRitual(zone);" in card
    ritual = _block(INDEX, "function startZone2LordRitual(zone)", "\n// 3-5s Go-themed entrance ritual")
    assert "_startBossBattleNow(zone)" in ritual
    assert "fetch(" not in ritual


def test_zone2_post_clear_is_gated_by_authoritative_pass_and_clear_state():
    finish = _block(INDEX, "async function _finishBossBattle()", "\n// Reads data.passed")
    assert "passed: data.passed" in finish
    assert "finishedZone?.key === 'k21_25'" in finish
    assert "showZone2LordResultCard" in finish
    trigger = _block(INDEX, "function _triggerZone2PostClearFromBossWin", "\nfunction showZone2LordResultCard")
    assert "zone.key !== 'k21_25' || !zone.cleared" in trigger
    assert "adventurePostClearSeen(zone)" in trigger
    assert "markAdventurePostClearPending(zone)" in trigger
    assert "playZone2PostClearFilm(zone)" in trigger
    ordinary = _block(INDEX, "async function _submitMapBattleV1IfActive(moves) {", "function isBeginnerVillageAdventureResult()")
    assert "_triggerZone2PostClearFromBossWin" not in ordinary
    assert "markAdventurePostClearPending" not in ordinary


def test_zone2_failure_has_no_post_clear_and_success_has_one_trigger():
    result = _block(INDEX, "function showZone2LordResultCard(result, zone)", "\nasync function showBossResultCinematic")
    success, failure = result.split("    } else {", 1)
    assert "_triggerZone2PostClearFromBossWin(zone)" in success
    assert "_triggerZone2PostClearFromBossWin" not in failure
    assert "firstQuestionHref(zone)" in failure
    assert "e10.zone2.result.fail.lock" in failure


def test_zone2_route_reveal_reads_server_unlock_without_writing_it():
    reveal = _block(INDEX, "function showZone2UnlockReveal(zone)", "\n// Compact result banner")
    assert "nextZone = stats.find(z => z.key === 'k16_20')" in reveal
    assert "!nextZone.unlocked" in reveal
    assert "nextZone.unlocked =" not in reveal
    assert "fetch(" not in reveal
    finish = _block(INDEX, "function finishPostClearFilm(zone)", "// Pending timers for the reveal")
    assert "showZone2UnlockReveal(zone)" in finish


def test_zone2_audio_slots_are_owner_locked_and_do_not_reuse_zone1_bytes():
    slots = _block(INDEX, "function _zone2CinematicPhaseSlots", "\nfunction getIntroFilmLocaleConfig")
    assert "ownerApprovalRequired: false" in slots
    assert "ownerAudioPending: false" in slots
    assert "/assets/e10/audio/zone1/" not in slots


def test_zone1_post_clear_audio_fallback_remains_final_shot_only():
    sequencer = _block(INDEX, "async function playNewbieVillageIntroFilm", "// 2026-08-09 (E10-Z1-CINEMATIC-TRIGGER-REALIGNMENT)")
    assert "phase !== 'post_clear' || Boolean(locale.bgmPostClear)" in sequencer
    assert "phase !== 'post_clear' || Boolean(locale.ambiencePostClear)" in sequencer
    assert "item.shot === 9 && phase === 'post_clear' && !locale.bgmPostClear" in sequencer


def test_shared_server_gate_remains_historical_correct_mastery_at_thirty_percent():
    state = _block(APP, "def _adventure_correct_question_ids", "\n\ndef _adventure_state")
    assert "review_log" in state
    assert "grade>=3" in state
    adventure = _block(APP, "def _adventure_state(uid):", "\n\n_ADVENTURE_STATE_CACHE")
    assert "seen = len([q for q in zone_qs if q['id'] in correct_ids])" in adventure
    assert "boss_ready = unlocked and pct >= BOSS_UNLOCK_PCT" in adventure
    assert "BOSS_UNLOCK_PCT = 30" in APP


def test_zone2_uses_existing_shared_lord_success_only_template():
    assert "ZONE2" not in _block(APP, "def _adventure_state(uid):", "\n\n_ADVENTURE_STATE_CACHE")
    assert "ZONE2" not in _block(INDEX, "async function _submitMapBattleV1IfActive(moves) {", "function isBeginnerVillageAdventureResult()")
    assert "Zone 2" in INDEX
    assert "Historical Mastery" in INDEX
    assert "_triggerZone2PostClearFromBossWin" in INDEX
