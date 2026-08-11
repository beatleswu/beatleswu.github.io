"""Static contracts for the E10 Zone POST_CLEAR authority boundary.

Ordinary Map Battle victories are encounter presentation only.  A Zone Lord
success returned by the server is the sole gameplay-success source that may
arm the Zone POST_CLEAR presentation and its server-derived map reveal.
"""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")


def _block(source, start_marker, end_marker):
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def _submit_block():
    return _block(
        INDEX,
        "async function _submitMapBattleV1IfActive(moves) {",
        "function isBeginnerVillageAdventureResult()",
    )


def _defeat_branch():
    submit = _submit_block()
    start = submit.index("if (response.next_action === 'monster_defeated')")
    end = submit.index("\n                }", start)
    return submit[start:end]


def _lord_result_block():
    return _block(
        INDEX,
        "function showZone1LordResultCard(result, zone) {",
        "function _triggerZone2PostClearFromBossWin(zone)",
    )


def _function_block(name, end_marker):
    return _block(INDEX, f"function {name}", end_marker)


def test_ordinary_monster_defeat_returns_to_map_without_zone_post_clear_trigger():
    branch = _defeat_branch()

    assert "showBeginnerVillageEncounterContinuation()" in branch
    assert "returnToAdventureMapAfterEncounter()" in branch
    assert "_triggerZone1PostClearFromBossWin" not in branch
    assert "_maybeTriggerZone1PostClearFilm" not in INDEX
    assert "playZone1PostClearFilm" not in branch


def test_ordinary_monster_defeat_does_not_mark_seen_or_unlock_next_zone():
    branch = _defeat_branch()

    assert "markAdventurePostClearPending" not in branch
    assert "markAdventurePostClearSeen" not in branch
    assert "showZone1UnlockReveal" not in branch
    assert "/api/adventure/boss/finish" not in branch


def test_lord_success_is_the_sole_post_clear_trigger():
    result_card = _lord_result_block()
    success = result_card.split("    } else {", 1)[0]

    assert "if (result.passed)" in result_card
    assert "_triggerZone1PostClearFromBossWin(zone)" in success
    assert success.count("_triggerZone1PostClearFromBossWin(zone)") == 1


def test_lord_failure_never_triggers_post_clear():
    result_card = _lord_result_block()
    failure = result_card.split("    } else {", 1)[1]

    assert "_triggerZone1PostClearFromBossWin" not in failure
    assert "markAdventurePostClearPending" not in failure
    assert "playZone1PostClearFilm" not in failure
    assert "firstQuestionHref(zone)" in failure


def test_server_boss_finish_feeds_authoritative_pass_into_zone_result_card():
    finish = _block(INDEX, "async function _finishBossBattle()", "function showZone1LordResultCard")

    assert "fetch('/api/adventure/boss/finish'" in finish
    assert "passed: data.passed" in finish
    assert "showZone1LordResultCard" in finish
    assert "monster_defeated" not in finish


def test_real_lord_success_pending_recovery_is_idempotent():
    trigger = _function_block("_triggerZone1PostClearFromBossWin", "function showZone1LordResultCard")
    recovery = _function_block("_resumeZone1PostClearIfPending", "function playZone1PostClearFilm")

    assert "zone.key !== 'k26_30'" in trigger
    assert "adventurePostClearSeen(zone)" in trigger
    assert "markAdventurePostClearPending(zone)" in trigger
    assert "playZone1PostClearFilm(zone)" in trigger
    assert "adventurePostClearSeen(zone)" in recovery
    assert "adventurePostClearPending(zone)" in recovery
    assert "_introFilmActiveOpts.phase === 'post_clear'" in recovery
    assert "playZone1PostClearFilm(zone)" in recovery


def test_post_clear_completion_only_records_presentation_and_reads_server_unlock_state():
    finish = _function_block("finishPostClearFilm", "// Pending timers for the reveal")
    reveal = _function_block("showZone1UnlockReveal", "function _triggerZone1PostClearFromBossWin")

    assert "markAdventurePostClearSeen(zone)" in finish
    assert "clearAdventurePostClearPending(zone)" in finish
    assert "showZone1UnlockReveal(zone)" in finish
    assert "fetch(" not in finish
    assert "if (!fromZone || !nextZone || !nextZone.unlocked) return;" in reveal
    assert "nextZone.unlocked =" not in reveal
    assert "unlockZone" not in reveal


def test_replay_story_is_presentational_only():
    replay = _function_block("replayIntroFilm", "// opts.timeline / opts.onComplete")

    assert "playZone1PostClearFilm(zone)" in replay
    assert "fetch(" not in replay
    assert "_triggerZone1PostClearFromBossWin" not in replay
    assert "markAdventurePostClearPending" not in replay


def test_zone1_post_clear_shots_remain_shot_9_then_shot_10():
    ordered_timelines = re.findall(
        r"postClearTimeline:\s*\[\s*\{\s*shot:\s*8,[\s\S]{0,1200}?\{\s*shot:\s*9,",
        INDEX,
    )

    # Zone 1 keeps its two localized POST_CLEAR arrays; Zone 2 owns a
    # separate 3-shot phase template.
    assert len(ordered_timelines) >= 2


def test_no_ordinary_map_battle_post_clear_call_site_remains():
    submit = _submit_block()
    trigger_calls = re.findall(
        r"(?<!function )_triggerZone1PostClearFromBossWin\s*\(zone\)",
        INDEX,
    )

    assert len(trigger_calls) == 1
    assert len(re.findall(
        r"(?<!function )_triggerZone2PostClearFromBossWin\s*\(zone\)",
        INDEX,
    )) == 1
    assert "_triggerZone1PostClearFromBossWin" not in submit
