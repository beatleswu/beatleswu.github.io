"""Bounded Wave 1 acceptance harness for the Zone 3 Goblin Cave slice.

This selector checks only the Zone 3 presentation/content seams and the
already-accepted Wave 1 shell/accessibility/replay contracts.  It does not
import ``app.py``, mutate a database, run Production, or claim that a browser
viewport is a physical device.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path, PurePosixPath

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adventure_zone3_monster_authority import (
    ZONE3_BINDING_SOURCE,
    ZONE3_KEY,
    ZONE3_LORD_CLASSIFICATION,
    ZONE3_LORD_ID,
    ZONE3_MONSTER_PROFILE_REGISTRY,
    ZONE3_NORMAL_IDS,
    ZONE3_PRESENTATION_ASSET_FILENAMES,
    ZONE3_PROFILE_VERSION,
    get_zone3_binding,
)


MATRIX_PATH = ROOT / "tests" / "fixtures" / "w1_05_zone3_vertical_slice_acceptance_matrix.json"
INDEX = ROOT / "index.html"
WORLD_HTML = ROOT / "components" / "adventure" / "world_stage.html"
WORLD_JS = ROOT / "js" / "e9" / "world_stage.js"
WORLD_CSS = ROOT / "css" / "e9" / "world_stage.css"
RWD_CSS = ROOT / "css" / "e9" / "rwd.css"
SHELL_CSS = ROOT / "css" / "e9" / "shell.css"
SHELL_JS = ROOT / "js" / "e9" / "shell.js"
LOADER_JS = ROOT / "js" / "e9" / "component_loader.js"
REPLAY_JS = ROOT / "js" / "game" / "cinematic_replay.js"
ENCOUNTER_JS = ROOT / "js" / "game" / "encounter_presentation_framework_v1.js"
ADAPTER_JS = ROOT / "js" / "map_battle_v1_adapter.js"
MANIFEST = ROOT / "manifest.json"
SCREENPLAY = ROOT / "docs" / "planning" / "e10_final_screenplay_v1.md"

BASE = "ffcee93aab813d110ce0b70276a101a291f2b508"
CANONICAL_MASTER = "616d51b17abe010de1e862382ca4db7bec65936f"

EXPECTED_CASE_IDS = {
    "zone3_canonical_identity",
    "zone3_visual_asset_presence",
    "zone3_monster_roster_closure",
    "zone3_encounter_hierarchy",
    "zone3_entry_cinematic",
    "zone3_gameplay_handoff",
    "zone3_onboarding_reachability",
    "zone3_lord_ready_presentation",
    "zone3_lord_trial",
    "zone3_authoritative_clear_reward",
    "zone3_post_clear",
    "zone3_zone4_hook",
    "zone3_replay_safety",
    "zone3_bgm_ambience_candidate",
    "viewport_16_9",
    "viewport_4_3",
    "viewport_ipad_landscape",
    "viewport_ipad_portrait",
    "viewport_mobile_portrait",
    "reduced_motion",
    "keyboard_focus",
    "critical_information_not_audio_only",
    "missing_asset_fail_safe",
    "static_manifest_validity",
    "shell_static_integration_readiness",
    "physical_device_acceptance",
}

EXPECTED_DIMENSIONS = {
    "FUNCTIONAL",
    "CONTENT",
    "VISUAL",
    "ANIMATION",
    "SFX",
    "BGM_AMBIENCE",
    "ONBOARDING",
    "UX",
    "RESPONSIVE",
    "ACCESSIBILITY",
    "INTEGRATION",
    "TEST",
}


def read(path: Path) -> str:
    assert path.is_file(), f"missing Zone 3 acceptance source: {path}"
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(read(path))


def cases_by_id() -> dict[str, dict]:
    return {case["id"]: case for case in load_json(MATRIX_PATH)["cases"]}


def local_asset_path(url_or_path: str) -> Path:
    """Resolve a root-relative path without allowing traversal."""

    value = str(url_or_path).split("?", 1)[0].split("#", 1)[0]
    relative = PurePosixPath(value.lstrip("/"))
    candidate = (ROOT / Path(*relative.parts)).resolve()
    assert candidate.is_relative_to(ROOT.resolve()), value
    return candidate


def missing_asset_paths(paths: set[str] | list[str]) -> list[str]:
    return sorted(
        path
        for path in paths
        if not local_asset_path(path).is_file()
        or local_asset_path(path).stat().st_size <= 0
    )


def function_body(source: str, signature: str) -> str:
    """Return one JavaScript function body using balanced delimiters."""

    start = source.index(signature)
    cursor = source.index("(", start)
    paren_depth = 0
    for index in range(cursor, len(source)):
        if source[index] == "(":
            paren_depth += 1
        elif source[index] == ")":
            paren_depth -= 1
            if paren_depth == 0:
                cursor = index
                break
    brace = source.index("{", cursor)
    brace_depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            brace_depth += 1
        elif source[index] == "}":
            brace_depth -= 1
            if brace_depth == 0:
                return source[brace : index + 1]
    raise AssertionError(f"unbalanced braces for {signature}")


def zone3_locale_block() -> str:
    source = read(INDEX)
    start = source.index("if (zone?.key === 'k16_20')")
    end = source.index("if (zone?.key === 'k21_25')", start)
    return source[start:end]


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"not a PNG: {path}"
    return struct.unpack(">II", data[16:24])


def assert_viewport_only(case: dict) -> None:
    assert case["evidence"].startswith("automated browser viewport/")
    assert case["owner_gate"] == "physical device later"
    assert case["status"] == "verified_viewport_only"


def assert_replay_safe(before: dict[str, int], after: dict[str, int], writes: list[str]) -> None:
    protected = ("coins", "xp", "stars", "cleared", "unlocked", "current_zone_key")
    mutations = {
        key: (before.get(key), after.get(key))
        for key in protected
        if before.get(key) != after.get(key)
    }
    assert not mutations, f"replay mutated protected state: {mutations}"
    assert not writes, f"replay issued writes: {writes}"


def test_matrix_is_explicit_bounded_and_covers_all_dimensions():
    matrix = load_json(MATRIX_PATH)
    assert matrix["task"] == "W1_05_QUALITY_ZONE3_VERTICAL_SLICE_ACCEPTANCE_HARNESS_002"
    assert matrix["base"] == BASE
    assert matrix["canonical_master"] == CANONICAL_MASTER
    assert matrix["zone"] == {
        "number": 3,
        "key": "k16_20",
        "name_en": "Goblin Cave",
        "name_zh": "哥布林洞穴",
        "lord_id": "goblin_centurion",
        "lord_name_en": "Goblin Centurion",
    }
    assert set(matrix["dimensions"]) == EXPECTED_DIMENSIONS
    cases = cases_by_id()
    assert set(cases) == EXPECTED_CASE_IDS
    assert len(cases) == 26
    assert set().union(*(set(case["dimensions"]) for case in cases.values())) == EXPECTED_DIMENSIONS
    for case in cases.values():
        assert case["acceptance"]
        assert case["evidence"]
        assert case["owner_gate"]
        assert case["status"]


def test_matrix_preserves_known_debt_classifications_and_later_gates():
    matrix = load_json(MATRIX_PATH)
    debt = {item["id"]: item["classification"] for item in matrix["known_debt"]}
    assert debt == {
        "A019 stale assertion": "TEST_STALE",
        "Jade Ring changed-path base-ref issue": "HARNESS_DEBT",
        "whole-suite shared-state/setup errors": "HARNESS_DEBT / TEST_ISOLATION_SHARED_STATE",
    }
    cases = cases_by_id()
    assert cases["zone3_post_clear"]["status"] == "content_candidate_gate"
    assert cases["zone3_zone4_hook"]["status"] == "content_candidate_gate"
    assert cases["zone3_bgm_ambience_candidate"]["status"] == "content_candidate_gate"
    assert cases["physical_device_acceptance"]["status"] == "required_later"


def test_zone3_canonical_identity_contract():
    world = read(WORLD_JS)
    index = read(INDEX)
    assert "k16_20: '/assets/maps/e10-vs1f-landmarks/zone-03-goblin-cave.webp'" in world
    assert re.search(
        r"\{ key:'k16_20', label:'16–20級', labelEn:'16–20 kyu', name:'哥布林洞穴', nameEn:'Goblin Cave'",
        index,
    )
    assert "k16_20: { boss:'Goblin Centurion'" in index
    assert "boss: '哥布林百夫長'" in index
    assert "ZONE3_KEY = \"k16_20\"" in read(ROOT / "adventure_zone3_monster_authority.py")


def test_zone3_visual_asset_manifest_is_present_and_referenced():
    matrix = load_json(MATRIX_PATH)
    entries = matrix["required_assets"]
    assert len(entries) == 26
    assert len({entry["path"] for entry in entries}) == len(entries)
    assert missing_asset_paths({entry["path"] for entry in entries}) == []
    for entry in entries:
        path = local_asset_path(entry["path"])
        assert path.stat().st_size == entry["bytes"], entry["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], entry["path"]
    assert "/assets/maps/e10-vs1f-landmarks/zone-03-goblin-cave.webp" in read(WORLD_JS)
    cinematic = zone3_locale_block()
    for name in (
        "go_goblin_cave_scene_01.webp",
        "go_goblin_cave_scene_02.webp",
        "go_goblin_cave_scene_03.webp",
        "go_goblin_cave_scene_04.webp",
        "go_goblin_cave_voice_en_01.mp3",
        "go_goblin_cave_voice_01.mp3",
    ):
        assert name in cinematic


def test_zone3_monster_roster_is_closed_and_server_bound():
    assert ZONE3_KEY == "k16_20"
    assert ZONE3_NORMAL_IDS == (
        "M022", "M023", "M024", "M025", "M026", "M027", "M028",
        "M029", "M030", "M031", "M032", "M033", "M060",
    )
    assert len(set(ZONE3_NORMAL_IDS)) == 13
    assert len(ZONE3_MONSTER_PROFILE_REGISTRY.profiles) == 13
    assert ZONE3_LORD_ID not in ZONE3_NORMAL_IDS
    assert ZONE3_LORD_CLASSIFICATION == "LORD_ONLY"
    assert len(ZONE3_PRESENTATION_ASSET_FILENAMES) == 12
    for slot, monster_id in enumerate(ZONE3_NORMAL_IDS, start=1):
        binding = get_zone3_binding(monster_id)
        assert binding is not None
        assert binding.roster_slot == slot
        assert binding.zone_key == ZONE3_KEY
        assert binding.encounter_class == "NORMAL"
        assert binding.profile_version == ZONE3_PROFILE_VERSION
        assert binding.presentation_asset.startswith(("/assets/", "/art/monsters/"))
    assert get_zone3_binding("goblin_centurion") is None
    assert get_zone3_binding("M999") is None


def test_zone3_hierarchy_keeps_monster_elite_battlefield_boss_and_lord_distinct():
    encounter = read(ENCOUNTER_JS)
    boundary = read(ROOT / "world_monster_boundary_contract.py")
    catalog = read(ROOT / "battlefield_monster_catalog_authority.py")
    authority = read(ROOT / "adventure_zone3_monster_authority.py")
    for marker in (
        "COMMON: 'common'",
        "ELITE: 'elite'",
        "BATTLEFIELD_BOSS: 'battlefield_boss'",
        "LORD_TRIAL: 'lord_trial'",
        "frame: 'lord-separate'",
    ):
        assert marker in encounter
    assert 'BATTLEFIELD_BOSS_CLASS: Final[str] = "BATTLEFIELD_BOSS"' in boundary
    assert "BATTLEFIELD_BOSS_IS_LORD = False" in catalog
    assert 'ZONE3_ENCOUNTER_CLASS = "NORMAL"' in authority
    assert 'ZONE3_LORD_CLASSIFICATION = "LORD_ONLY"' in authority


def test_zone3_entry_cinematic_has_bilingual_beats_and_handoff():
    cinematic = zone3_locale_block()
    assert cinematic.count("go_goblin_cave_scene_") == 8
    assert cinematic.count("go_goblin_cave_voice_en_") == 4
    assert len(re.findall(r"go_goblin_cave_voice_(?!en_)[0-9]+\.mp3", cinematic)) == 4
    assert cinematic.count("sfx:") == 8
    for marker in (
        "filmTitle:",
        "timeline:",
        "imageAlt:",
        "function showStageIntroCinematic(zone, options = {})",
        "playNewbieVillageIntroFilm(zone, { mode });",
        "if (!(await enterAdventureZoneInPage(zone)))",
    ):
        assert marker in cinematic or marker in read(INDEX)
    assert "zone.key === 'k16_20'" in read(INDEX)


def test_zone3_gameplay_handoff_is_server_backed_and_presentation_only():
    app_source = read(ROOT / "app.py")
    adapter = read(ADAPTER_JS)
    index = read(INDEX)
    for marker in (
        "select_zone3_binding(question['id'])",
        "ZONE3_BINDING_SOURCE",
        "_adventure_zone3_binding",
        "monster_profile_resolver=_map_battle_monster_profile_resolver",
        "JOIN map_battles b",
        "forged_fields",
    ):
        assert marker in app_source
    for marker in (
        "state.adventureMonster",
        "adventureMonster",
        "showAdventureNormalEncounterContinuation",
        "adventure.zone3.continue",
        "adventure.zone3.return_map",
        "adventure.zone3.encounter_complete",
    ):
        assert marker in adapter or marker in index
    assert "select_zone3_binding" not in read(ROOT / "adventure_zone3_legacy_compatibility.py")
    assert "encode_zone3_binding" not in read(ROOT / "adventure_zone3_legacy_compatibility.py")


def test_zone3_onboarding_spine_remains_reachable():
    html = read(WORLD_HTML)
    world = read(WORLD_JS)
    index = read(INDEX)
    for marker in (
        'id="e9-newbie-mainline"',
        'id="e9-newbie-mainline-title"',
        'id="e9-newbie-mainline-summary"',
        'id="e9-newbie-mainline-steps"',
        'id="e9-newbie-mainline-cta"',
        'type="button"',
    ):
        assert marker in html
    for marker in (
        "function renderBeginnerVillageMainline(root, zone, state)",
        "adventure.newbie.step_battle",
        "adventure.newbie.step_progress",
        "adventure.newbie.step_boss",
        "dispatchAdventureAction(contract)",
        "panel.hidden = false",
    ):
        assert marker in world
    for marker in ('id="naming-modal"', 'id="guild-tour-btn"', "startTour()"):
        assert marker in index


def test_zone3_lord_ready_presentation_uses_generic_server_action():
    index = read(INDEX)
    start = index.index("async function startBossBattle(zoneKey)")
    end = index.index("\nasync function openAdventureBossFromQuestCard", start)
    dispatch = index[start:end]
    assert "if (zone.key === 'k26_30')" in dispatch
    assert "if (zone.key === 'k21_25')" in dispatch
    assert "await showBossCinematic(zone)" in dispatch
    for marker in (
        "function _adventureBossReady(zone)",
        "boss?.available === true",
        "function _adventureBossReplayAvailable(zone)",
        "function showBossCinematic(zone)",
        "Goblin Centurion",
        'id="boss-cinematic"',
        'id="boss-cinematic-btn"',
        'id="boss-cinematic-cancel-btn"',
    ):
        assert marker in index
    assert "zone.bossAvailable === true" in read(WORLD_JS)


def test_zone3_lord_trial_uses_existing_authoritative_start_and_finish():
    index = read(INDEX)
    start = function_body(index, "async function _startBossBattleNow(zone)")
    finish = function_body(index, "async function _finishBossBattle()")
    for marker in (
        "fetch('/api/adventure/boss/start'",
        "zone.key",
        "attempt_id",
        "question_ids",
        "_loadBossQuestion()",
    ):
        assert marker in start
    for marker in (
        "fetch('/api/adventure/boss/finish'",
        "body: JSON.stringify({ correct, total })",
        "data.passed",
        "data.zones",
        "BattlefieldBossRewardConsumer.present(data",
        "showBossResultCinematic({",
    ):
        assert marker in finish
    assert "zone.key === 'k16_20'" in index


def test_zone3_clear_and_reward_are_authoritative_and_idempotent():
    index = read(INDEX)
    reward = read(ROOT / "battlefield_boss_reward_service.py")
    consumer = read(ROOT / "js" / "game" / "battlefield_boss_reward_consumer.js")
    for marker in (
        "data.passed",
        "data.zones || _adventureProgress",
        "invalidateE9AdventureStateCache()",
        "BattlefieldBossRewardConsumer.present(data",
        "_adventureProgress = data.zones",
    ):
        assert marker in index
    for marker in (
        "is_first_clear",
        "is_replay",
        "NO_REWARD",
        "REPLAY_ALREADY_CLEARED",
        "BOSS_NOT_FIRST_CLEAR",
        "BOSS_NOT_PASSED",
    ):
        assert marker in reward
    assert "fetch(" not in consumer
    assert "localStorage" not in consumer


def test_zone3_post_clear_and_zone4_hook_are_explicit_candidate_boundaries():
    index = read(INDEX)
    replay = read(REPLAY_JS)
    screenplay = read(SCREENPLAY)
    zone3 = zone3_locale_block()
    assert "post_clear" in replay
    assert "post_clear_hook" in replay
    assert "postVictorySequence" in replay
    assert "ZONE_CINEMATIC_TIMELINE_KEYS" in index
    assert "postClearTimeline" in index
    assert "postClearHookTimeline" in index
    # The current later-zone locale declares only PRE_PLAY. This is a
    # deliberate readiness boundary, not permission to claim a post-clear film.
    assert "postClearTimeline" not in zone3
    assert "postClearHookTimeline" not in zone3
    story_block = screenplay[screenplay.index("## Zone 3 — Goblin Cave") : screenplay.index("## Zone 4 —", screenplay.index("## Zone 3 — Goblin Cave"))]
    assert "Grik gestures toward deeper cave/forest" in story_block
    assert "points toward Zone 4" in story_block
    # The existing ordered world topology places Zone 4 immediately after Z3.
    index_z3 = index.index("{ key:'k16_20'")
    index_z4 = index.index("{ key:'k11_15'")
    assert index_z3 < index_z4


def test_zone3_replay_is_presentation_only_and_zone_agnostic():
    index = read(INDEX)
    replay = read(REPLAY_JS)
    replay_body = function_body(index, "function playZoneStoryReplay(zoneKey)")
    assert "presentationOnly: true" in replay_body
    for forbidden in ("fetch(", "markAdventure", "localStorage", "finishPostClearFilm"):
        assert forbidden not in replay_body
    for forbidden in ("fetch(", "localStorage", "sessionStorage", "document."):
        assert forbidden not in replay
    for marker in (
        "SEGMENT_ORDER",
        "replaySequence",
        "hasReplayableStory",
        "POST_VICTORY_FROM",
        "return isCleared(zone)",
    ):
        assert marker in replay
    assert "if (!zone?.key)" in index[index.index("function _zoneCinematicSegmentDeclarations") : index.index("function _zoneCinematicSegmentDeclarations") + 1800]


def test_zone3_bgm_ambience_and_sfx_boundary_is_visible():
    index = read(INDEX)
    zone3 = zone3_locale_block()
    assert zone3.count("sfx:") == 8
    assert "mystic" in zone3 and "pulse" in zone3 and "woodhit" in zone3 and "journey" in zone3
    # No dedicated Zone 3 bed is declared yet. The generic sequencer supports
    # the slots, but the candidate gate must not silently borrow Zone 1/2 beds.
    assert "bgmMainTheme" not in zone3
    assert "ambienceVillageDawn" not in zone3
    for marker in (
        "const phaseBgm =",
        "const phaseAmbience =",
        "_startIntroBgm(phaseBgm",
        "_startIntroAmbience(phaseAmbience)",
        "function _stopIntroBgm()",
        "function _stopIntroAmbience()",
    ):
        assert marker in index


@pytest.mark.parametrize(
    ("case_id", "expected_markers"),
    [
        (
            "viewport_16_9",
            ("aspect-ratio: 1672 / 941", ".e9-map-stage__base", "object-fit: contain"),
        ),
        (
            "viewport_4_3",
            ("@media (max-width: 1024px)", '"nav"', '"stage"', '"cards"'),
        ),
        (
            "viewport_ipad_landscape",
            ("@media (min-width: 768px) and (max-width: 1279px)", "position: fixed", "overflow-y: auto"),
        ),
        (
            "viewport_ipad_portrait",
            ("@media (min-width: 768px) and (max-width: 1279px)", "@media (max-width: 1024px)", "grid-template-areas:"),
        ),
        (
            "viewport_mobile_portrait",
            ("@media (max-width: 767px)", "e9-zone__inline-details", "env(safe-area-inset-bottom", "overflow-x: auto"),
        ),
    ],
)
def test_zone3_responsive_viewport_contract_is_not_physical(case_id: str, expected_markers: tuple[str, ...]):
    case = cases_by_id()[case_id]
    width, height = (int(value) for value in case["viewport"].split("x"))
    assert width > 0 and height > 0
    assert_viewport_only(case)
    source = read(WORLD_CSS) + "\n" + read(RWD_CSS)
    for marker in expected_markers:
        assert marker in source, f"{case_id}: missing responsive marker {marker}"


def test_zone3_reduced_motion_contract():
    css = read(WORLD_CSS) + "\n" + read(SHELL_CSS) + "\n" + read(INDEX)
    shell = read(SHELL_JS)
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "transition: none" in css
    assert "animation: none" in css
    assert "prefers-reduced-motion: reduce" in shell
    assert "behavior: reduced ? 'auto' : 'smooth'" in shell


def test_zone3_keyboard_focus_contract():
    html = read(WORLD_HTML)
    world = read(WORLD_JS)
    css = read(WORLD_CSS)
    shell = read(SHELL_JS)
    for marker in (
        'id="e9-world-stage-details" tabindex="-1"',
        'id="e9-world-stage-details-cta"',
        'id="e9-world-stage-details-replay"',
        'type="button"',
    ):
        assert marker in html
    for marker in ("evt.key === 'Enter'", "evt.key === ' '", "evt.preventDefault()", "focusTarget.focus"):
        assert marker in world
    for marker in (".e9-zone:focus-visible", ".e9-adventure-cta:focus-visible", "outline-offset"):
        assert marker in css
    for marker in ("suspendTabbing", "restoreTabbing", "setAttribute('inert', '')", "data-e9-prev-tabindex"):
        assert marker in shell


def test_zone3_critical_information_has_visible_equivalents():
    html = read(WORLD_HTML)
    index = read(INDEX)
    zone3 = zone3_locale_block()
    for marker in (
        'id="e9-world-stage-status"',
        'id="e9-world-stage-details-label"',
        'id="e9-world-stage-details-summary"',
        'id="e9-world-stage-details-progress"',
        'id="e9-world-stage-details-cta"',
        'aria-live="polite"',
    ):
        assert marker in html
    for marker in (
        'id="boss-cinematic-title"',
        'id="boss-cinematic-line"',
        'id="boss-cinematic-btn"',
        'id="boss-cinematic-close-x"',
    ):
        assert marker in index
    assert "caption:" in zone3 and "imageAlt:" in zone3


def test_zone3_missing_asset_fail_safe_contract():
    paths = {entry["path"] for entry in load_json(MATRIX_PATH)["required_assets"]}
    assert missing_asset_paths(paths) == []
    loader = read(LOADER_JS)
    for marker in (
        "function fallbackHtml(component)",
        'data-e9-fallback="',
        'role="status"',
        "if (!res.ok)",
        ".catch(function (err)",
        "data-e9-loaded', 'error'",
    ):
        assert marker in loader


def test_negative_control_missing_asset_is_rejected():
    missing = "/assets/e10/w1-05-zone3-intentionally-missing-negative-control.webp"
    paths = {entry["path"] for entry in load_json(MATRIX_PATH)["required_assets"]}
    assert missing_asset_paths(paths | {missing}) == [missing]


def test_negative_control_replay_reward_delta_is_rejected():
    before = {
        "coins": 10,
        "xp": 4,
        "stars": 1,
        "cleared": 1,
        "unlocked": 1,
        "current_zone_key": "k16_20",
    }
    after = dict(before, coins=11)
    with pytest.raises(AssertionError, match="protected state"):
        assert_replay_safe(before, after, [])


def test_zone3_static_manifest_validity():
    manifest = load_json(MANIFEST)
    assert manifest["display"] == "standalone"
    assert manifest["orientation"] == "portrait"
    assert len(manifest["icons"]) == 2
    for icon in manifest["icons"]:
        path = local_asset_path(icon["src"])
        assert path.is_file() and path.stat().st_size > 0
        expected = tuple(int(part) for part in icon["sizes"].split("x"))
        assert png_dimensions(path) == expected
    entries = load_json(MATRIX_PATH)["required_assets"]
    assert all(len(entry["sha256"]) == 64 for entry in entries)
    assert all(entry["bytes"] > 0 for entry in entries)


def test_zone3_shell_static_integration_and_protected_scope():
    index = read(INDEX)
    expected_slots = (
        "e9-top-hud-slot",
        "e9-left-nav-slot",
        "e9-world-stage-slot",
        "e9-right-cards-slot",
        "e9-bottom-dock-slot",
    )
    for slot in expected_slots:
        assert f'id="{slot}"' in index
    for source in (
        "/js/e9/feature_flags.js",
        "/js/e9/component_loader.js",
        "/js/e9/world_stage.js",
        "/js/e9/shell.js",
    ):
        assert re.search(re.escape(source) + r"\?v=[^\"]+", index)
        assert local_asset_path(source).is_file()
    for stylesheet in (
        "/css/e9/shell.css",
        "/css/e9/world_stage.css",
        "/css/e9/rwd.css",
    ):
        assert re.search(re.escape(stylesheet) + r"\?v=[^\"]+", index)
        assert local_asset_path(stylesheet).is_file()
    assert 'name="go-odyssey-static-contract"' in index
    assert "loadComponent" in read(SHELL_JS)
    for relative in (
        "app.py",
        "index.html",
        "i18n.js",
        "sw.js",
        "js/e9/shell.js",
    ):
        result = subprocess.run(
            ["git", "diff", "--quiet", BASE, "--", relative],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"protected scope changed: {relative}\n{result.stderr}"


def test_negative_control_does_not_promote_viewport_to_physical_acceptance():
    fake = {
        "evidence": "automated browser viewport/CSS contract only",
        "owner_gate": "none",
        "status": "verified_viewport_only",
    }
    with pytest.raises(AssertionError, match="physical device later"):
        assert_viewport_only(fake)


def test_zone3_matrix_records_server_binding_source_and_no_production_gate():
    authority = read(ROOT / "adventure_zone3_monster_authority.py")
    matrix = load_json(MATRIX_PATH)
    assert ZONE3_BINDING_SOURCE in authority
    assert "No merge, deploy, database migration, or Production mutation occurs in this task." in matrix["limits"]
    assert any("Production acceptance remains" in item for item in matrix["limits"])
    assert any("does not modify app.py" in item for item in matrix["limits"])
