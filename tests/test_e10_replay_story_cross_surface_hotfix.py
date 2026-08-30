"""Cross-surface Replay Story contracts (E10_REPLAY_STORY_CROSS_SURFACE_IPAD_HOTFIX_002).

Owner real-device evidence this file pins, from Production v236:

    DEFECT_1  iPad landscape, Zone 1 completed -- Replay Story button visible,
              a real finger tap does nothing.
    DEFECT_2  iPad landscape, Zone 2 completed -- Replay Story button absent.
    DEFECT_3  iPad portrait, completed Zone card -- Replay Story absent while
              the sibling CTAs (rechallenge Lord / replenish stars) render.

All three share one cause and one secondary cause, and both are pinned here:

  * The availability predicate resolved its zone record from
    ``_adventureProgress``, a global only the Legacy Adventure Map's bootstrap
    ever populates.  On the E9 Adventure Shell it fell through to the static
    ADVENTURE_ZONES literal, which carries no cleared/unlock state, so a
    genuinely cleared zone reported "nothing to replay" -- dead tap in
    landscape (the button was shown by a different authority), missing button
    in portrait.

  * ``right_cards.js`` decided the landscape button's visibility from a
    hardcoded ``detail.zoneKey === 'k26_30'`` allowlist while dispatching
    through the predicate.  Visibility and dispatch answered to two different
    authorities, which is precisely how a visible-but-inert button exists at
    all, and why Zone 2 never got one.

Every test here fails against the exact Production v236 bytes.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AVAILABILITY_RUNNER = (
    ROOT / "tests" / "e2e" / "run_e10_replay_story_availability_contract.mjs"
)
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
WORLD_STAGE = (ROOT / "js" / "e9" / "world_stage.js").read_text(encoding="utf-8")
RIGHT_CARDS = (ROOT / "js" / "e9" / "right_cards.js").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")

ZONE_KEYS = ("k26_30", "k21_25", "k16_20", "k11_15", "k6_10", "k1_5")


def _strip_line_comments(source: str) -> str:
    """Drop // line comments so a contract never matches its own rationale."""
    return "\n".join(re.sub(r"(^|\s)//.*$", "", line) for line in source.splitlines())


def _function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    depth = 0
    cursor = source.index("(", start)
    for index in range(cursor, len(source)):
        char = source[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                cursor = index
                break
    brace = source.index("{", cursor)
    depth = 0
    for index in range(brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[brace : index + 1]
    raise AssertionError(f"unbalanced braces for {signature}")


# --------------------------------------------------------------------------
# B. Zone 2 availability contract / no zone-key allowlist on ANY surface
# --------------------------------------------------------------------------


def test_landscape_surface_has_no_zone_key_allowlist():
    """DEFECT_2's exact cause: right_cards.js gated visibility on Zone 1's key.

    Fails on v236, where the landscape drawer literally reads
    ``detail.zoneKey === 'k26_30'``.
    """
    code = _strip_line_comments(RIGHT_CARDS)
    for key in ZONE_KEYS:
        assert key not in code, f"right_cards.js still hardcodes zone key {key}"


def test_landscape_visibility_uses_the_shared_availability_authority():
    code = _strip_line_comments(RIGHT_CARDS)
    assert "zoneReplayStoryAvailable" in code, (
        "the landscape Replay Story surface must ask the one shared "
        "availability authority, not decide for itself"
    )


def test_world_stage_publishes_the_single_availability_authority():
    assert "window.E9.zoneReplayStoryAvailable = zoneStoryReplayAvailable;" in WORLD_STAGE


# --------------------------------------------------------------------------
# A. Real hit-test / event-path contract -- visibility and dispatch must be
#    answerable by the SAME predicate, or a visible-but-inert button returns.
# --------------------------------------------------------------------------


def test_visibility_and_dispatch_share_one_predicate():
    """A surface may never show the button on an authority the dispatcher
    would refuse. That mismatch is DEFECT_1 exactly."""
    configure = _function_body(
        WORLD_STAGE, "function configureStoryReplayButton(button, zone)"
    )
    dispatch = _function_body(WORLD_STAGE, "function replayAdventureIntro(zoneKey)")
    assert "zoneStoryReplayAvailable(zone.key" in configure
    assert "zoneStoryReplayAvailable(zoneKey)" in dispatch


def test_ineligible_button_does_not_retain_a_stale_zone_handler():
    """Returning early on ineligibility used to leave the previous zone's
    click handler bound to the button."""
    configure = _function_body(
        WORLD_STAGE, "function configureStoryReplayButton(button, zone)"
    )
    detach = configure.index("removeEventListener('click'")
    bail = configure.index("if (!enabled) return;")
    assert detach < bail, (
        "the stale handler must be detached BEFORE the eligibility bail-out, "
        "or an ineligible button keeps dispatching the previous zone"
    )
    assert "button.__e9StoryReplayHandler = null;" in configure


# --------------------------------------------------------------------------
# D. Shared dispatch authority -- exactly one entry point, no legacy readiness
# --------------------------------------------------------------------------


def test_all_surfaces_converge_on_one_dispatch_authority():
    assert "window.E9.replayAdventureIntro = replayAdventureIntro;" in WORLD_STAGE
    assert "window.E9.replayAdventureIntro(" in RIGHT_CARDS
    # The landscape surface must not carry its own copy of the playback call.
    assert "playStoryReplay" not in _strip_line_comments(RIGHT_CARDS), (
        "right_cards.js must delegate, never re-implement replay dispatch"
    )


def test_dispatch_does_not_wait_on_legacy_adventure_readiness():
    body = _function_body(WORLD_STAGE, "function replayAdventureIntro(zoneKey)")
    primary = body[: body.index("Narrow fail-safe")] if "Narrow fail-safe" in body else body
    assert "ensureLegacyAdventureMapReady" not in primary
    assert "playStoryReplay" in primary


# --------------------------------------------------------------------------
# C. Portrait affordance / authoritative zone resolution (DEFECT_1 + DEFECT_3
#    root cause: the model could not see authoritative state on the E9 shell)
# --------------------------------------------------------------------------


def test_cinematic_model_can_resolve_zones_from_the_e9_shell_snapshot():
    """The load-bearing fix. Fails on v236, where _zoneForCinematic knows only
    _adventureProgress and the stateless static ADVENTURE_ZONES literal."""
    body = _function_body(INDEX, "function _zoneForCinematic(zoneKey)")
    assert "_e9AuthoritativeZones" in body, (
        "the cinematic model still cannot see the E9 shell's authoritative "
        "zones, so a cleared zone reports no replayable story there"
    )
    # Ordering matters: the legacy global still wins when populated, so the
    # legacy shell's behaviour is unchanged.
    assert body.index("_adventureProgress") < body.index("_e9AuthoritativeZones")
    assert body.index("_e9AuthoritativeZones") < body.index("ADVENTURE_ZONES")


def test_authoritative_zone_registration_is_exposed_and_used():
    assert "setAuthoritativeZones: setCinematicAuthoritativeZones," in INDEX
    assert "window.E10Cinematic.setAuthoritativeZones(zones)" in WORLD_STAGE


def test_registration_is_read_only_and_never_writes_progression():
    body = _function_body(INDEX, "function setCinematicAuthoritativeZones(zones)")
    for forbidden in (
        "fetch(",
        "markAdventure",
        "grantReward",
        "localStorage",
        "sessionStorage",
    ):
        assert forbidden not in body, f"registration must not {forbidden}"


def test_availability_requires_all_four_authoritative_conditions():
    """The Owner's product rule (002A), pinned as source structure.

    The executable proof is test_availability_contract_runner_is_green below;
    this keeps the four conditions individually greppable so a future edit that
    silently drops one is visible in review.
    """
    body = _function_body(
        WORLD_STAGE, "function zoneStoryReplayAvailable(zoneKey, zoneRecord)"
    )
    # (1) authoritative record required -- fail closed without one
    assert "if (!zone) return false;" in body
    # (2) not locked
    assert "zone.locked === true" in body
    # (3) cleared REQUIRED
    assert "zone.cleared !== true" in body, (
        "Replay Story must require an authoritative clear"
    )
    # (4) canonical replayable segments, and no identity-based guessing when
    # the model is absent
    assert "hasReplayableStory" in body
    assert "introCinematicKeyForZone" not in body, (
        "a missing model must fail closed, never fall back to zone identity"
    )


def test_availability_contract_runner_is_green():
    """Executes the real predicate against synthetic authoritative records."""
    result = subprocess.run(
        ["node", str(AVAILABILITY_RUNNER)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    output = f"stdout={result.stdout}\nstderr={result.stderr}"
    assert result.returncode == 0, output
    report = json.loads(result.stdout)
    assert report["status"] == "PASS", output
    assert report["failures"] == 0, output
    assert report["checks"] >= 14, output


def test_selection_detail_carries_the_authoritative_clear_flag():
    """The landscape drawer consumes `detail`, so the clear flag must travel
    with it -- otherwise that surface cannot satisfy condition 3 without
    inventing a second authority (e.g. parsing a display status string)."""
    body = _function_body(WORLD_STAGE, "function zoneSelectionDetail(zone, state)")
    assert "cleared: zone.cleared === true," in body
    assert "locked: !!zone.locked," in body


# --------------------------------------------------------------------------
# Cache / release identity
# --------------------------------------------------------------------------


def test_cache_identity_was_bumped_off_v236():
    version = re.search(r"const VERSION\s*=\s*'([^']+)'", SW).group(1)
    assert version != "v236-e10-replay-story-button-hotfix"
    assert version == "v240-a028-hero-player-presentation-readonly"


def test_changed_runtime_modules_carry_a_new_cache_tag():
    for src in (
        "/js/e9/world_stage.js?v=20260828e042s1",
        "/js/e9/right_cards.js?v=20260828e040s1",
    ):
        assert src in INDEX, f"{src} missing -- cached clients keep the broken copy"
    assert "/js/e9/world_stage.js?v=20260821e10xsurface002" not in INDEX
    assert "/js/e9/right_cards.js?v=20260821e10xsurface002" not in INDEX
    assert "/js/e9/world_stage.js?v=20260820e10replaybtn001" not in INDEX
    assert "/js/e9/right_cards.js?v=20260801e10art1" not in INDEX
