"""Read-only Zone 4 Misty Forest content contract for W2-01.

This module is intentionally additive.  It consumes one checked-in JSON
manifest and exposes the existing Zone 4 presentation/content evidence to a
future shell integrator.  It does not import ``app.py`` and it never owns
progression, unlock, combat, reward, or locale-selection authority.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "assets" / "adventure" / "zone4" / "zone4-misty-forest-vertical-slice.json"
ZONE4_KEY = "k11_15"
SUPPORTED_LOCALES: tuple[str, ...] = ("zh-TW", "en-US")


class Zone4ContentContractError(ValueError):
    """Raised when the checked-in Zone 4 content contract is malformed."""


def load_zone4_manifest() -> dict[str, Any]:
    with MANIFEST_PATH.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    validate_zone4_manifest(manifest)
    return manifest


def validate_zone4_manifest(manifest: Mapping[str, Any]) -> None:
    if manifest.get("schemaVersion") != "w2-01.zone4.misty-forest.vertical-slice.v1":
        raise Zone4ContentContractError("Zone 4 schema version is invalid")
    zone = manifest.get("zone")
    if not isinstance(zone, Mapping) or zone.get("number") != 4 or zone.get("key") != ZONE4_KEY:
        raise Zone4ContentContractError("Zone 4 identity is invalid")
    if set(zone.get("names", {})) != set(SUPPORTED_LOCALES):
        raise Zone4ContentContractError("Zone 4 locale names are incomplete")

    creative_lock = manifest.get("ownerCreativeLock")
    if not isinstance(creative_lock, Mapping):
        raise Zone4ContentContractError("Zone 4 Owner creative lock is missing")
    if creative_lock.get("status") != "OWNER_APPROVED_CONTENT_LOCK":
        raise Zone4ContentContractError("Zone 4 Owner creative lock is not approved")
    if creative_lock.get("approvedTenShotCount") != 10:
        raise Zone4ContentContractError("Zone 4 Owner shot count is not approved")
    if creative_lock.get("childReadabilitySequence") != [
        "WHAT_HAPPENED",
        "WHAT_HERO_SEES",
        "WHY_HERO_IS_CONFUSED",
        "WHAT_CLUE_HERO_NOTICES",
        "WHAT_DECISION_HERO_MAKES",
        "WHAT_HAPPENS_NEXT",
    ]:
        raise Zone4ContentContractError("Zone 4 child-readability sequence is invalid")
    visual_direction = creative_lock.get("visualDirection")
    visual_shots = visual_direction.get("shots") if isinstance(visual_direction, Mapping) else None
    if not isinstance(visual_shots, Mapping) or set(visual_shots) != {f"Z4_S{n:02d}" for n in range(1, 11)}:
        raise Zone4ContentContractError("Zone 4 approved visual briefs are incomplete")
    if any(brief.get("status") != "OWNER_APPROVED" or not brief.get("brief") for brief in visual_shots.values()):
        raise Zone4ContentContractError("Zone 4 approved visual brief metadata is invalid")
    audio_direction = creative_lock.get("audioDirection")
    if not isinstance(audio_direction, Mapping) or audio_direction.get("shuiVoice") != "NONE" or audio_direction.get("shuiNonverbal") is not True:
        raise Zone4ContentContractError("Zone 4 Shui audio boundary is invalid")
    story_relic = creative_lock.get("storyRelic")
    if not isinstance(story_relic, Mapping) or story_relic.get("clientRewardGrant") is not False or story_relic.get("inventoryMutation") is not False:
        raise Zone4ContentContractError("Zone 4 story relic authority is invalid")
    design_roster = creative_lock.get("designRoster")
    if not isinstance(design_roster, Mapping) or design_roster.get("ids") != [f"M{n:03d}" for n in range(34, 46)] or design_roster.get("adventureAuthorizedCount") != 0:
        raise Zone4ContentContractError("Zone 4 design roster authority is invalid")

    story = manifest.get("story")
    if not isinstance(story, Mapping) or story.get("canonicalShotCount") != 10:
        raise Zone4ContentContractError("Zone 4 shot count is not canonical")
    if story.get("ownerApprovedDialogueLineCount") != 24 or story.get("existingCanonicalZhLineCount") != 3 or story.get("ownerApprovedNewZhLineCount") != 21:
        raise Zone4ContentContractError("Zone 4 Owner dialogue counts are invalid")
    shots = story.get("shots")
    if not isinstance(shots, list) or [shot.get("id") for shot in shots] != [f"Z4_S{n:02d}" for n in range(1, 11)]:
        raise Zone4ContentContractError("Zone 4 shot identity/order is invalid")
    lifecycle = story.get("lifecycle")
    if not isinstance(lifecycle, list):
        raise Zone4ContentContractError("Zone 4 lifecycle is missing")
    lifecycle_shots = [shot_id for phase in lifecycle for shot_id in phase.get("shots", [])]
    if lifecycle_shots != [shot.get("id") for shot in shots]:
        raise Zone4ContentContractError("Zone 4 lifecycle does not cover shots exactly once")
    phases = {phase.get("id"): phase.get("phase") for phase in lifecycle}
    if phases != {"first_entry": "PRE_PLAY", "post_clear": "POST_CLEAR", "post_clear_hook": "POST_CLEAR_HOOK"}:
        raise Zone4ContentContractError("Zone 4 lifecycle phases are invalid")
    if lifecycle[0].get("shots") != [f"Z4_S{n:02d}" for n in range(1, 8)]:
        raise Zone4ContentContractError("Zone 4 gameplay handoff boundary is invalid")

    beats = story.get("dialogueBeats")
    if not isinstance(beats, list) or len(beats) != 24:
        raise Zone4ContentContractError("Zone 4 dialogue beat registry is missing")
    beat_ids = [beat.get("beatId") for beat in beats]
    if len(beat_ids) != len(set(beat_ids)) or any(not beat_id for beat_id in beat_ids):
        raise Zone4ContentContractError("Zone 4 dialogue beat IDs are not unique")
    shot_by_id = {shot["id"]: shot for shot in shots}
    shot_beat_ids = [beat_id for shot in shots for beat_id in shot.get("dialogueBeatIds", [])]
    if shot_beat_ids != [beat["beatId"] for beat in beats] and set(shot_beat_ids) != set(beat_ids):
        raise Zone4ContentContractError("Zone 4 shot and dialogue beat registries do not align")
    if set(shot_beat_ids) != set(beat_ids) or len(shot_beat_ids) != 24:
        raise Zone4ContentContractError("Zone 4 dialogue beats do not cover the approved script")
    for beat in beats:
        if beat.get("shotId") not in shot_by_id:
            raise Zone4ContentContractError("Zone 4 dialogue beat references an unknown shot")
        if beat["beatId"] not in shot_by_id[beat["shotId"]].get("dialogueBeatIds", []):
            raise Zone4ContentContractError("Zone 4 dialogue beat is not bound to its shot")
        if not beat.get("i18nKey"):
            raise Zone4ContentContractError("Zone 4 dialogue beat has no i18n key")
        if not isinstance(beat.get("sequence"), int) or beat["sequence"] < 1:
            raise Zone4ContentContractError("Zone 4 dialogue beat sequence is invalid")
        if beat.get("canonicalStatus") not in {"EXISTING_CANONICAL", "OWNER_APPROVED_NEW"}:
            raise Zone4ContentContractError("Zone 4 dialogue beat approval status is invalid")
        if beat.get("voiceStatus") != "NOT_GENERATED":
            raise Zone4ContentContractError("Zone 4 voice generation is outside this task")
        if beat.get("character") in {"SHUI", "水靈馬"}:
            raise Zone4ContentContractError("Shui must remain nonverbal")

    locales = manifest.get("locales")
    if not isinstance(locales, Mapping) or set(locales) != set(SUPPORTED_LOCALES):
        raise Zone4ContentContractError("Zone 4 locale package is incomplete")
    zh_dialogue = locales["zh-TW"].get("dialogue", {})
    beat_keys = {beat["i18nKey"] for beat in beats}
    if set(zh_dialogue) != beat_keys:
        raise Zone4ContentContractError("zh-TW Zone 4 dialogue is not complete")
    if set(locales["en-US"].get("dialogue", {})) != beat_keys:
        raise Zone4ContentContractError("en-US Zone 4 dialogue is not complete")

    encounters = manifest.get("encounters")
    normal = encounters.get("normal") if isinstance(encounters, Mapping) else None
    if not isinstance(normal, list) or [entry.get("id") for entry in normal] != [f"M{n:03d}" for n in range(34, 46)]:
        raise Zone4ContentContractError("Zone 4 normal candidate roster is incomplete")
    boss = encounters.get("battlefieldBoss", {})
    lord = encounters.get("lord", {})
    if boss.get("id") == lord.get("id") or boss.get("id") != "legacy_bf_04_boss" or lord.get("id") != "misty_phantom_rabbit_king":
        raise Zone4ContentContractError("Zone 4 Battlefield Boss and Lord identities collapsed")
    if not isinstance(manifest.get("authorityGaps"), list) or not manifest["authorityGaps"]:
        raise Zone4ContentContractError("Zone 4 authority gaps must be explicit")


def localized_ui(locale: str) -> Mapping[str, str]:
    manifest = load_zone4_manifest()
    selected = locale if locale in SUPPORTED_LOCALES else SUPPORTED_LOCALES[0]
    return manifest["locales"][selected]["ui"]


def localized_dialogue(locale: str, i18n_key: str) -> str | None:
    manifest = load_zone4_manifest()
    if locale not in SUPPORTED_LOCALES:
        return None
    value = manifest["locales"][locale].get("dialogue", {}).get(i18n_key)
    return value if isinstance(value, str) else None


__all__ = [
    "MANIFEST_PATH",
    "SUPPORTED_LOCALES",
    "ZONE4_KEY",
    "Zone4ContentContractError",
    "load_zone4_manifest",
    "localized_dialogue",
    "localized_ui",
    "validate_zone4_manifest",
]
