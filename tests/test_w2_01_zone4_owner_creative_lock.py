"""W2-01 Zone 4 Owner-approved dialogue and creative-lock contracts."""

from __future__ import annotations

from adventure_zone4_misty_forest_content import load_zone4_manifest


def test_owner_lock_covers_the_ten_shot_visual_direction_and_story_contract():
    manifest = load_zone4_manifest()
    lock = manifest["ownerCreativeLock"]

    assert lock["status"] == "OWNER_APPROVED_CONTENT_LOCK"
    assert lock["approvedTenShotCount"] == 10
    assert lock["storyTheme"].startswith("When misleading visual information makes the Hero uncertain")
    assert lock["childReadabilitySequence"] == [
        "WHAT_HAPPENED",
        "WHAT_HERO_SEES",
        "WHY_HERO_IS_CONFUSED",
        "WHAT_CLUE_HERO_NOTICES",
        "WHAT_DECISION_HERO_MAKES",
        "WHAT_HAPPENS_NEXT",
    ]
    assert lock["englishAccentPolicy"] == "BRITISH_ENGLISH"

    visual = lock["visualDirection"]
    assert "no horror" in visual["globalStyle"]
    assert "no baked text/UI" in visual["globalStyle"]
    shot_briefs = visual["shots"]
    assert set(shot_briefs) == {f"Z4_S{number:02d}" for number in range(1, 11)}
    assert all(brief["status"] == "OWNER_APPROVED" and brief["brief"] for brief in shot_briefs.values())

    audio = lock["audioDirection"]
    assert audio["status"] == "CREATIVE_DIRECTION_APPROVED_PRODUCTION_NOT_GENERATED"
    assert audio["shuiVoice"] == "NONE"
    assert audio["shuiNonverbal"] is True
    assert audio["voiceGenerated"] is False
    assert audio["sfxGenerated"] is False
    assert audio["bgmGenerated"] is False

    relic = lock["storyRelic"]
    assert relic["status"] == "OWNER_APPROVED_STORY_MEMORY"
    assert relic["clientRewardGrant"] is False
    assert relic["inventoryMutation"] is False

    roster = lock["designRoster"]
    assert roster["status"] == "DESIGN_ROSTER_ONLY"
    assert roster["ids"] == [f"M{number:03d}" for number in range(34, 46)]
    assert roster["count"] == 12
    assert roster["adventureAuthorizedCount"] == 0


def test_owner_approved_dialogue_beats_are_unique_ordered_and_locale_aligned():
    manifest = load_zone4_manifest()
    story = manifest["story"]
    beats = story["dialogueBeats"]
    beat_by_id = {beat["beatId"]: beat for beat in beats}
    beat_keys = {beat["i18nKey"] for beat in beats}

    assert len(beats) == 24
    assert len(beat_by_id) == 24
    assert set(manifest["locales"]["zh-TW"]["dialogue"]) == beat_keys
    assert set(manifest["locales"]["en-US"]["dialogue"]) == beat_keys
    assert all(beat["voiceStatus"] == "NOT_GENERATED" for beat in beats)
    assert all(beat["character"] != "SHUI" for beat in beats)

    for shot in story["shots"]:
        shot_beats = [beat_by_id[beat_id] for beat_id in shot["dialogueBeatIds"]]
        assert all(beat["shotId"] == shot["id"] for beat in shot_beats)
        assert [beat["sequence"] for beat in shot_beats] == list(range(1, len(shot_beats) + 1))

    assert beat_by_id["Z4_S02_B001"]["canonicalStatus"] == "EXISTING_CANONICAL"
    assert beat_by_id["Z4_S05_B001"]["canonicalStatus"] == "EXISTING_CANONICAL"
    assert beat_by_id["Z4_S07_B001"]["canonicalStatus"] == "EXISTING_CANONICAL"
    assert sum(beat["canonicalStatus"] == "OWNER_APPROVED_NEW" for beat in beats) == 21
