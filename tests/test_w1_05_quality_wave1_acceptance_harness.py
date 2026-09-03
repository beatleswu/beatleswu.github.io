"""Bounded Wave 1 product-acceptance and static-integration harness.

This file intentionally avoids importing app.py or running the repository-wide
suite. It checks the small set of source, asset, accessibility, and replay
contracts that Wave 1 needs before later Owner-led static and physical-device
acceptance. The negative controls prove that the harness rejects a missing
asset, a replay reward mutation, and a false physical-device claim.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path, PurePosixPath

import pytest


ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "tests" / "fixtures" / "w1_05_wave1_acceptance_matrix.json"
INDEX = ROOT / "index.html"
WORLD_HTML = ROOT / "components" / "adventure" / "world_stage.html"
WORLD_JS = ROOT / "js" / "e9" / "world_stage.js"
WORLD_CSS = ROOT / "css" / "e9" / "world_stage.css"
RWD_CSS = ROOT / "css" / "e9" / "rwd.css"
SHELL_JS = ROOT / "js" / "e9" / "shell.js"
LOADER_JS = ROOT / "js" / "e9" / "component_loader.js"
REPLAY_JS = ROOT / "js" / "game" / "cinematic_replay.js"
FEATURE_FLAGS_JS = ROOT / "js" / "e9" / "feature_flags.js"
MANIFEST = ROOT / "manifest.json"
UI_MANIFEST = ROOT / "assets" / "e10" / "ui" / "e10-ui-assets.json"
ART_MANIFEST = ROOT / "assets" / "e10" / "art" / "zone1" / "lord_trial" / "zone1-lord-trial-art-package.json"

CANONICAL_MASTER = "616d51b17abe010de1e862382ca4db7bec65936f"
EXPECTED_MATRIX_IDS = {
    "zone_presentation_presence",
    "missing_fallback_asset_detection",
    "zone_entry_clear_replay",
    "boss_lord_distinction",
    "replay_no_reward",
    "onboarding_reachability",
    "mobile_portrait",
    "tablet_portrait",
    "tablet_landscape",
    "reduced_motion",
    "keyboard_focus",
    "audio_not_only_information",
    "static_asset_manifest_validity",
    "shell_static_integration_readiness",
    "physical_device_acceptance",
}


def read(path: Path) -> str:
    assert path.is_file(), f"missing Wave 1 source: {path}"
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(read(path))


def function_body(source: str, signature: str) -> str:
    """Return one JS function body using balanced parameter/brace scanning."""

    start = source.index(signature)
    cursor = source.index("(", start)
    depth = 0
    for index in range(cursor, len(source)):
        if source[index] == "(":
            depth += 1
        elif source[index] == ")":
            depth -= 1
            if depth == 0:
                cursor = index
                break
    brace = source.index("{", cursor)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace : index + 1]
    raise AssertionError(f"unbalanced braces for {signature}")


def local_asset_path(url_or_path: str) -> Path:
    """Resolve a root-relative static path without allowing traversal."""

    value = str(url_or_path).split("?", 1)[0].split("#", 1)[0]
    relative = PurePosixPath(value.lstrip("/"))
    candidate = (ROOT / Path(*relative.parts)).resolve()
    assert candidate.is_relative_to(ROOT.resolve()), value
    return candidate


def missing_asset_paths(paths: list[str] | set[str]) -> list[str]:
    return sorted(
        path
        for path in paths
        if not local_asset_path(path).is_file()
        or local_asset_path(path).stat().st_size <= 0
    )


def wave1_asset_paths() -> set[str]:
    world_js = read(WORLD_JS)
    index = read(INDEX)
    paths = set(re.findall(r"['\"](/assets/maps/[^'\"]+)['\"]", world_js))
    paths.update(
        re.findall(
            r"['\"](/assets/e10/art/zone[12]/lord_trial/[^'\"]+\.webp)['\"]",
            index,
        )
    )
    app_manifest = load_json(MANIFEST)
    paths.update(icon["src"] for icon in app_manifest["icons"])
    paths.update("/" + entry["path"] for entry in load_json(UI_MANIFEST)["assets"])
    return paths


def assert_no_missing_assets(paths: list[str] | set[str]) -> None:
    missing = missing_asset_paths(paths)
    assert not missing, f"missing or empty static assets: {missing}"


def assert_replay_safe(before: dict[str, int], after: dict[str, int], writes: list[str]) -> None:
    protected = ("coins", "xp", "stars", "cleared", "unlocked", "current_zone_key")
    mutations = {
        key: (before.get(key), after.get(key))
        for key in protected
        if before.get(key) != after.get(key)
    }
    assert not mutations, f"replay mutated protected state: {mutations}"
    assert not writes, f"replay issued writes: {writes}"


def assert_viewport_is_not_physical(case: dict) -> None:
    assert case.get("automation") == "automated"
    assert case.get("method", "").startswith("browser viewport/")
    assert case.get("owner_gate") == "physical device later"


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"not a PNG: {path}"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def test_matrix_is_explicit_and_bounded():
    matrix = load_json(MATRIX_PATH)
    assert matrix["task"] == "W1_05_QUALITY_WAVE1_ACCEPTANCE_HARNESS_001"
    assert matrix["canonical_master"] == CANONICAL_MASTER
    cases = {case["id"]: case for case in matrix["cases"]}
    assert set(cases) == EXPECTED_MATRIX_IDS
    assert len(cases) == 15
    for case in cases.values():
        assert case["method"]
        assert case["automation"] in {"automated", "manual_later"}
        assert case["owner_gate"]


def test_matrix_preserves_known_debt_classifications():
    debt = {
        item["id"]: item["classification"]
        for item in load_json(MATRIX_PATH)["known_debt"]
    }
    assert debt == {
        "A019 stale assertion": "TEST_STALE",
        "Jade Ring changed-path base-ref issue": "HARNESS_DEBT",
        "whole-suite shared-state/setup errors": "HARNESS_DEBT / TEST_ISOLATION_SHARED_STATE",
    }


def test_zone_presentation_presence_contract():
    html = read(WORLD_HTML)
    js = read(WORLD_JS)
    css = read(WORLD_CSS)
    assert '<main id="adventure-stage"' in html
    for marker in (
        'id="e9-map-stage"',
        'data-vs1d-src="/assets/maps/e10_world_stage_v1_base.webp"',
        'id="e9-world-stage-zones"',
        'id="e9-world-stage-details"',
        'id="e9-world-stage-details-cta"',
        'id="e9-world-stage-status"',
        'aria-live="polite"',
    ):
        assert marker in html
    for key in (
        "k26_30", "k21_25", "k16_20", "k11_15", "k6_10",
        "k1_5", "d1_2", "d3_4", "d5_6", "d7_plus",
    ):
        assert key in js
    assert "var ZONE_ANCHORS" in js
    assert "var BOSS_ANCHORS" in js
    assert "document.createElement('button')" in js
    assert "data-zone-boss-anchor" in js
    assert ".e9-map-stage__route" in css
    assert ".e9-zone-details[hidden]" in css


def test_missing_and_fallback_asset_contract():
    paths = wave1_asset_paths()
    assert len(paths) >= 60, "the Wave 1 asset probe should remain explicit, not collapse to one sentinel"
    assert_no_missing_assets(paths)
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
    missing = "/assets/e10/w1-05-intentionally-missing-negative-control.webp"
    assert missing_asset_paths(wave1_asset_paths() | {missing}) == [missing]


def test_zone_entry_clear_and_replay_contract():
    world = read(WORLD_JS)
    replay = read(REPLAY_JS)
    index = read(INDEX)
    for marker in (
        "e9:zone-selected",
        "dispatchZone1Entry",
        "renderSelectedZone",
        "zone.cleared",
        "zoneStoryReplayAvailable",
        "replayAdventureIntro",
        "configureStoryReplayButton",
    ):
        assert marker in world
    for marker in (
        "SEGMENT_ORDER",
        "postVictorySequence",
        "replaySequence",
        "hasReplayableStory",
    ):
        assert marker in replay
    for marker in (
        "function playZoneStoryReplay(zoneKey)",
        "function _finishZoneCinematicReplay(zone)",
        "function _triggerZonePostClearFromBossWin(zone, options = {})",
    ):
        assert marker in index


def test_boss_lord_distinction_and_routing_contract():
    world = read(WORLD_JS)
    for marker in (
        "challenge_lord",
        "replay_completed",
        "normal_progression",
        "function isServerBackedLordAction(action)",
        "zone.bossAvailable === true && !zone.cleared",
        "openAdventureBossFromQuestCard(contract.targetZoneKey)",
    ):
        assert marker in world
    assert "/api/adventure/boss/start" not in world
    assert "startAdventureFromE9(contract.targetZoneKey)" in world


def test_replay_no_reward_contract():
    index = read(INDEX)
    replay = read(REPLAY_JS)
    story_replay = function_body(index, "function playZoneStoryReplay(zoneKey)")
    for forbidden in (
        "markAdventure",
        "fetch(",
        "finishPostClearFilm",
    ):
        assert forbidden not in story_replay
    assert "presentationOnly: true" in story_replay

    trigger = function_body(
        index,
        "function _triggerZonePostClearFromBossWin(zone, options = {})",
    )
    replay_branch = trigger[trigger.index("if (replay) {") : trigger.index("// First clear")]
    for forbidden in ("markAdventurePostClear", "finishPostClearFilm", "fetch("):
        assert forbidden not in replay_branch
    assert "presentationOnly: true" in replay_branch
    for forbidden in ("fetch(", "localStorage", "sessionStorage", "document."):
        assert forbidden not in replay


def test_negative_control_replay_reward_delta_is_rejected():
    before = {
        "coins": 10,
        "xp": 4,
        "stars": 1,
        "cleared": 1,
        "unlocked": 1,
        "current_zone_key":  "k26_30",
    }
    after = dict(before, coins=11)
    with pytest.raises(AssertionError, match="protected state"):
        assert_replay_safe(before, after, [])


def test_onboarding_reachability_contract():
    html = read(WORLD_HTML)
    js = read(WORLD_JS)
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
        assert marker in js
    for marker in ('id="naming-modal"', 'id="guild-tour-btn"', "startTour()"):
        assert marker in index


@pytest.mark.parametrize(
    "case_id,expected_markers",
    [
        (
            "mobile_portrait",
            (
                "@media (max-width: 767px)",
                "padding-bottom: calc(var(--e9-shell-mobile-dock-reserve) + 18px)",
                ".e9-dock",
                "overflow-x: auto",
                "e9-zone__inline-details",
            ),
        ),
        (
            "tablet_portrait",
            (
                "@media (min-width: 768px) and (max-width: 1279px)",
                "grid-template-areas:",
                "#right-cards .e9-drawer-panel:not([hidden])",
                "position: fixed",
                "overflow-y: auto",
            ),
        ),
        (
            "tablet_landscape",
            (
                "@media (max-width: 1279px)",
                '"nav stage"',
                '"cards cards"',
                "grid-template-columns: minmax(0, 216px)",
                "#e9-right-cards-slot",
            ),
        ),
    ],
)
def test_responsive_contract_is_bounded(case_id: str, expected_markers: tuple[str, ...]):
    matrix = {case["id"]: case for case in load_json(MATRIX_PATH)["cases"]}
    assert_viewport_is_not_physical(matrix[case_id])
    source = read(RWD_CSS) + "\n" + read(WORLD_CSS)
    for marker in expected_markers:
        assert marker in source, f"{case_id}: missing responsive marker {marker}"


def test_reduced_motion_contract():
    css = read(WORLD_CSS) + "\n" + read(ROOT / "css" / "e9" / "shell.css") + "\n" + read(INDEX)
    shell = read(SHELL_JS)
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "transition: none" in css
    assert "animation: none" in css
    assert "prefers-reduced-motion: reduce" in shell
    assert "behavior: reduced ? 'auto' : 'smooth'" in shell


def test_keyboard_focus_contract():
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


def test_audio_is_not_the_only_critical_information_channel():
    html = read(WORLD_HTML)
    index = read(INDEX)
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


def test_static_asset_manifest_validity():
    app_manifest = load_json(MANIFEST)
    assert app_manifest["display"] == "standalone"
    assert app_manifest["orientation"] == "portrait"
    assert len(app_manifest["icons"]) == 2
    for icon in app_manifest["icons"]:
        path = local_asset_path(icon["src"])
        assert path.is_file() and path.stat().st_size > 0
        expected = tuple(int(part) for part in icon["sizes"].split("x"))
        assert png_dimensions(path) == expected

    ui = load_json(UI_MANIFEST)
    assert ui["total_assets"] == len(ui["assets"])
    assert ui["total_bytes"] == sum(entry["bytes"] for entry in ui["assets"])
    for entry in ui["assets"]:
        path = local_asset_path("/" + entry["path"])
        assert path.is_file() and path.stat().st_size == entry["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]

    art = load_json(ART_MANIFEST)
    assert art["assets"]
    for entry in art["assets"]:
        for variant in (entry["canonical_png"], entry["runtime_webp"]):
            path = local_asset_path("/" + variant["path"])
            assert path.is_file() and path.stat().st_size == variant["size_bytes"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == variant["sha256"]


def test_shell_static_integration_readiness():
    index = read(INDEX)
    flags = read(FEATURE_FLAGS_JS)
    shell = read(SHELL_JS)
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
    assert "var ASSET_VERSION =" in flags
    assert "PRODUCTION_FLAGS" in flags
    assert "loadComponent" in shell


def test_negative_control_does_not_promote_viewport_to_physical_acceptance():
    fake_case = {
        "automation": "automated",
        "method": "browser viewport/CSS contract only",
        "owner_gate": "none",
    }
    with pytest.raises(AssertionError, match="physical device later"):
        assert_viewport_is_not_physical(fake_case)


def test_protected_product_files_are_unchanged_from_canonical_master():
    for relative in ("app.py", "index.html", "i18n.js", "sw.js"):
        result = subprocess.run(
            ["git", "diff", "--quiet", CANONICAL_MASTER, "--", relative],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"protected scope changed: {relative}\n{result.stderr}"
