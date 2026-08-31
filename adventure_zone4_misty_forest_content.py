"""Canonical, non-authoritative Zone 4 content references.

The question rows are still selected by the existing ``app.ADVENTURE_ZONES``
book mapping during later app integration. This module only records the
already-published story/voice assets and the exact reusable-content boundary.
"""

from __future__ import annotations

from adventure_zone4_misty_forest_authority import (
    ZONE4_KEY,
    ZONE4_LORD_CLASSIFICATION,
    ZONE4_LORD_ID,
)


ZONE4_BOOKS = ("7迷霧森林", "8迷霧森林深處")
ZONE4_CANONICAL_ROW_SOURCE = "app.ADVENTURE_ZONES[k11_15].books"
ZONE4_CANONICAL_ROW_STATUS = "BOOK_BINDING_CANONICAL_QUESTION_DATA_NOT_TRACKED"

ZONE4_STORYBOARD_SCENE_PATHS = tuple(
    f"assets/storyboards/go_misty_forest_scene_{index:02d}.webp"
    for index in range(1, 5)
)
ZONE4_STORYBOARD_VOICE_PATHS = {
    "zh": tuple(
        f"assets/storyboards/go_misty_forest_voice_{index:02d}.mp3"
        for index in range(1, 5)
    ),
    "en": tuple(
        f"assets/storyboards/go_misty_forest_voice_en_{index:02d}.mp3"
        for index in range(1, 5)
    ),
}

# These are candidates for the lean slice's atmosphere; no new BGM or SFX is
# introduced here, and the later UI integration remains owner-gated.
ZONE4_REUSED_BGM_PATHS = (
    "assets/e10/audio/zone2/bgm/zone2_bgm_recovery.mp3",
    "assets/e10/audio/zone1/bgm/zone1_bgm_main_theme.mp3",
)
ZONE4_REUSED_AMBIENCE_PATHS = (
    "assets/e10/audio/zone2/ambience/zone2_ambience_plains_recovery.mp3",
)

ZONE4_STORYBOARD_AVAILABLE = True
ZONE4_VO_AVAILABLE = True
ZONE4_STORYBOARD_SHOT_COUNT = len(ZONE4_STORYBOARD_SCENE_PATHS)
ZONE4_VO_FILE_COUNT = sum(len(paths) for paths in ZONE4_STORYBOARD_VOICE_PATHS.values())
ZONE4_NEW_ART_REQUIRED_COUNT = 0
ZONE4_NEW_AUDIO_REQUIRED_COUNT = 0

ZONE4_LORD_METADATA = {
    "zone_key": ZONE4_KEY,
    "lord_id": ZONE4_LORD_ID,
    "classification": ZONE4_LORD_CLASSIFICATION,
    "source": "app.ADVENTURE_BOSS_META[k11_15]",
    "normal_defeat_does_not_clear_zone": True,
}


__all__ = [
    "ZONE4_BOOKS",
    "ZONE4_CANONICAL_ROW_SOURCE",
    "ZONE4_CANONICAL_ROW_STATUS",
    "ZONE4_LORD_METADATA",
    "ZONE4_NEW_ART_REQUIRED_COUNT",
    "ZONE4_NEW_AUDIO_REQUIRED_COUNT",
    "ZONE4_REUSED_AMBIENCE_PATHS",
    "ZONE4_REUSED_BGM_PATHS",
    "ZONE4_STORYBOARD_AVAILABLE",
    "ZONE4_STORYBOARD_SCENE_PATHS",
    "ZONE4_STORYBOARD_SHOT_COUNT",
    "ZONE4_STORYBOARD_VOICE_PATHS",
    "ZONE4_VO_AVAILABLE",
    "ZONE4_VO_FILE_COUNT",
]
