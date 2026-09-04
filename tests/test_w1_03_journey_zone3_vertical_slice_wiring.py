"""W1_03 Zone 3 cinematic slot and responsive wiring contracts.

The browser-facing bridge remains intentionally thin: the existing Adventure
and Lord endpoints own gameplay, clear, reward, and unlock authority. These
tests lock the presentation contracts and the fail-safe style-lock boundary.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = "aa5c4c25e50e4cd0843e50cdc685f81cf8337f95"
CANONICAL_MASTER = "616d51b17abe010de1e862382ca4db7bec65936f"
SOURCE_AUTHORITY_HEADS = (
    "fd7a1bcee2a01723a716f20683a4411d593f2dab",
    "15cd275b8f4992c30e93d874c45244d87909d334",
    "aa5c4c25e50e4cd0843e50cdc685f81cf8337f95",
    "7bf4b5e1e7322e1d925f346c7d7096cee3b50faf",
)
INTEGRATION_PATHS = {
    "sound.js",
    "js/e9/journey_zone3_presentation_audio.js",
    "tests/e2e/fixtures/w1_03_journey_zone3_final_presentation_single_writer_binding_010.html",
    "tests/e2e/run_w1_03_journey_zone3_final_presentation_single_writer_binding_010.mjs",
    "tests/test_w1_03_journey_zone3_final_presentation_single_writer_binding_010.py",
    "docs/planning/w1_zone3_final_presentation_candidate_inventory_010.json",
}
CONTENT = ROOT / "js" / "e9" / "journey_zone3_vertical_slice_content.js"
CONTROLLER = ROOT / "js" / "e9" / "journey_zone3_vertical_slice.js"
VIEW = ROOT / "js" / "e9" / "journey_zone3_vertical_slice_view.js"
FRAGMENT = ROOT / "components" / "adventure" / "zone3_vertical_slice.html"
CSS = ROOT / "css" / "e9" / "zone3_vertical_slice.css"
WORLD_STAGE = ROOT / "js" / "e9" / "world_stage.js"
SHELL = ROOT / "js" / "e9" / "shell.js"
INDEX = ROOT / "index.html"
I18N = ROOT / "i18n.js"
RUNNER = ROOT / "tests" / "e2e" / "run_w1_03_journey_zone3_vertical_slice_wiring.mjs"


def read(path: Path) -> str:
    assert path.is_file(), f"missing required Zone 3 wiring file: {path}"
    return path.read_text(encoding="utf-8")


def accepted_authority_paths() -> set[str]:
    paths: set[str] = set()
    for head in SOURCE_AUTHORITY_HEADS:
        result = subprocess.run(
            ["git", "-c", "core.quotePath=false", "diff", "--name-only", CANONICAL_MASTER, head, "--"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        paths.update(item.replace("\\", "/") for item in result.stdout.splitlines() if item)
    return paths | INTEGRATION_PATHS


def git_paths(*args: str) -> set[str]:
    tracked = subprocess.run(
        ["git", "-c", "core.quotePath=false", "diff", "--name-only", BASE, "--", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
    ).stdout.splitlines()
    untracked = subprocess.run(
        ["git", "-c", "core.quotePath=false", "ls-files", "--others", "--exclude-standard", "--", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    # secret_key.txt is a protected local artifact that is intentionally not
    # part of the candidate and must not be read, staged, or classified here.
    return {
        item.replace("\\", "/")
        for item in tracked + untracked
        if item and item.replace("\\", "/") != "secret_key.txt"
    }


def test_required_zone3_files_exist():
    for path in (CONTENT, CONTROLLER, VIEW, FRAGMENT, CSS, WORLD_STAGE, SHELL, RUNNER):
        assert path.is_file()


def test_manifest_is_explicit_and_style_lock_safe():
    content = read(CONTENT)
    for marker in (
        "W1_03_JOURNEY_ZONE3_CINEMATIC_ASSET_SLOT_AND_RESPONSIVE_BINDING_V1",
        "var ZONE3_KEY = 'k16_20'",
        "var ZONE4_KEY = 'k11_15'",
        "zone3_entry_cinematic",
        "zone3_post_clear_cinematic",
        "WORLD_CANDIDATE = '39c587a216f6cc13efe572066d9d8f0299960f1b'",
        "CINEMATIC_MANIFEST_PATH",
        "responsiveManifestReconciled: true",
        "status: 'READY'",
        "imageFailure: 'NO_GAMEPLAY_AUTHORITY_CHANGE'",
        "SAFE_TEXT_ONLY",
        "RESOLVED_BY_WORLD_CANDIDATE",
        "noFakeFinalAssets: true",
    ):
        assert marker in content
    assert "assets/e10/art/zone3/cinematic/zone3-cinematic-asset-package.json" in content
    assert "/assets/e10/audio/zone3/zone3-cinematic-audio-manifest.json" in content


def test_phase_and_event_contract_covers_the_vertical_slice():
    content = read(CONTENT)
    expected_phases = [
        "ENTRY_PENDING",
        "ENTRY_CINEMATIC",
        "GAMEPLAY_HANDOFF",
        "MAP_BATTLE_TRAINING",
        "BATTLEFIELD_BOSS_PROGRESS",
        "LORD_READY",
        "LORD_CTA",
        "LORD_TRIAL",
        "CLEAR_REWARD",
        "POST_CLEAR_CINEMATIC",
        "ZONE4_HOOK",
        "RETURN",
    ]
    positions = [content.index(f"'{phase}'") for phase in expected_phases]
    assert positions == sorted(positions)
    for event in (
        "journey:zone3-entry",
        "journey:zone3-first-entry-cinematic",
        "journey:zone3-gameplay-handoff",
        "journey:zone3-map-battle",
        "journey:zone3-battlefield-boss-progress",
        "journey:zone3-lord-ready",
        "journey:zone3-lord-cta",
        "journey:zone3-lord-trial-started",
        "journey:zone3-lord-trial-progress",
        "journey:zone3-lord-clear",
        "journey:zone3-reward",
        "journey:zone3-post-clear",
        "journey:zone4-hook",
        "journey:zone3-return",
    ):
        assert event in content


def test_controller_is_presentation_only_and_has_authority_guards():
    controller = read(CONTROLLER)
    for forbidden in (
        "fetch(",
        "XMLHttpRequest",
        "localStorage",
        "sessionStorage",
        "document.",
        "reward.create",
        "equipItem",
        "window.location",
    ):
        assert forbidden not in controller
    for marker in (
        "baseServerFact(detail, 'adventure_bootstrap')",
        "baseServerFact(detail, 'map_battle_v1')",
        "baseServerFact(detail, 'adventure_boss_start')",
        "baseServerFact(detail, 'adventure_boss_review')",
        "baseServerFact(detail, 'adventure_boss_finish')",
        "baseServerFact(detail, 'battlefield_reward_consumer')",
        "duplicate_reward_event",
        "rewardEventIds",
        "replay !== true",
        "selectedZoneKey",
        "progressionZoneKey",
        "autoNavigate !== true",
    ):
        assert marker in controller


def test_battlefield_boss_and_lord_are_distinct():
    content = read(CONTENT)
    controller = read(CONTROLLER)
    assert "battlefieldBossDistinctFromLord: true" in content
    assert "distinctFrom: 'lord_trial'" in content
    assert "BATTLEFIELD_BOSS_PROGRESS" in controller
    assert "LORD_TRIAL" in controller
    assert "adventure_boss_finish" in controller


def test_fragment_and_view_are_short_safe_contextual_surfaces():
    fragment = read(FRAGMENT)
    view = read(VIEW)
    assert 'id="zone3-vertical-slice"' in fragment
    assert 'data-e9-component="zone3_vertical_slice"' in fragment
    assert 'role="region"' in fragment
    assert "data-i18n-aria-label=" in fragment
    assert 'data-zone3-action="lord-cta"' in fragment
    assert 'data-zone3-action="return"' in fragment
    assert "<img" not in fragment.lower()
    assert "storyboard" not in fragment.lower()
    assert "fetch(" not in fragment.lower()
    assert "journey:zone3-event" in view
    assert "journey:zone3-command" in view
    assert "__GO_ZONE3_JOURNEY_EVENT_QUEUE__" in view
    assert "data-e9-zone3-mounted" in view
    assert "global.E9.on" in view
    assert "global.E9.registerCleanup" in view
    assert "fetch(" not in view
    assert "localStorage" not in view
    assert "sessionStorage" not in view


def test_responsive_reduced_motion_styles_exist():
    css = read(CSS)
    assert "#e9-zone3-vertical-slice-slot" in css
    assert "@media (max-width: 767px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "position: fixed" not in css


def test_world_stage_uses_server_entry_and_readiness_projections():
    world = read(WORLD_STAGE)
    for marker in (
        "introCinematicKeyForZone",
        "zone3EntryInFlight",
        "journey:zone3-zone-selected",
        "journey:zone3-entry",
        "journey:zone3-lord-ready",
        "adventure_bootstrap",
    ):
        assert marker in world
    # Zone 3's approved package participates in the same generic replay model
    # as Zones 1-2; the predicate remains server-state based and fail-closed.
    assert "function zoneStoryReplayAvailable(zoneKey, zoneRecord)" in world
    assert "if (zoneKey === 'k16_20') return false;" not in world


def test_index_wires_only_the_allowed_shell_slots_and_existing_runtime():
    index = read(INDEX)
    for marker in (
        'id="e9-journey-onboarding-slot"',
        'id="e9-zone3-vertical-slice-slot"',
        'data-e9-slot="journeyOnboarding"',
        'data-e9-slot="zone3VerticalSlice"',
        "/js/e9/journey_zone3_vertical_slice_content.js",
        "/js/e9/journey_zone3_vertical_slice.js",
        "/js/e9/journey_zone3_vertical_slice_view.js",
        "function showZone3EntrySafeFallback",
        "function _zone3CinematicTimeline",
        "world_manifest",
        "zone3-image-load-failed",
        "function showZone3LordChallengeCard",
        "function _emitZone3Zone4Hook",
        "BattlefieldBossRewardConsumer.present",
        "data.reward?.entitlement_id",
        "data.reward?.source_operation_id",
        "_zone3ReturnToMap",
    ):
        assert marker in index
    assert "/css/e9/zone3_vertical_slice.css" in index
    assert "assets/e10/art/zone3/cinematic" not in index
    assert "/assets/e10/audio/zone3" not in index


def test_zone3_entry_fallback_does_not_use_generic_story_art():
    index = read(INDEX)
    start = index.index("async function showZone3EntrySafeFallback")
    end = index.index("async function showStageIntroCinematic", start)
    fallback = index[start:end]
    assert "ADVENTURE_STORY" not in fallback
    assert "storyboard" not in fallback.lower()
    assert "zone3_entry_cinematic" in fallback
    assert "PENDING_FINAL_ASSETS" in fallback
    assert "manifestReady" in fallback
    assert "SAFE_TEXT_ONLY" not in fallback  # manifest owns the semantic name


def test_skip_replay_and_return_are_non_authoritative():
    index = read(INDEX)
    world = read(WORLD_STAGE)
    for marker in (
        "dataset.zone3EntryFlow === 'true'",
        "mode: 'manual_replay'",
        "_zone3ReturnToMap('entry_cancel')",
        "function _zone3ReturnToMap(source = 'post_clear_card')",
        "replay !== true",
    ):
        assert marker in index or marker in world
    assert "zoneStoryReplayAvailable" in world
    assert "if (zoneKey === 'k16_20') return false;" not in world


def test_protected_boundaries_and_changed_paths_are_clean():
    changed = git_paths()
    unexpected = changed - accepted_authority_paths()
    assert not unexpected, sorted(unexpected)
    assert "app.py" not in changed
    assert "js/game/cinematic_replay.js" not in changed
    assert not any(path.startswith("migrations/") for path in changed)
    assert not any(path.startswith("db/") for path in changed)
    assert (changed & {"index.html", "i18n.js", "js/game/cinematic_replay.js"}) <= {
        "index.html", "i18n.js"
    }


def test_behavioral_runner_is_green():
    result = subprocess.run(
        ["node", str(RUNNER)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    output = f"stdout={result.stdout}\nstderr={result.stderr}"
    assert result.returncode == 0, output
    assert '"status":"PASS"' in result.stdout, output
    assert '"failures":[]' in result.stdout, output
