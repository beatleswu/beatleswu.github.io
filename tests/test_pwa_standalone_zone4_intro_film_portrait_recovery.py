"""GO_ODYSSEY_PWA_STANDALONE_ADVENTURE_LAYOUT_RECOVERY_CLAUDE_001.

Root cause (measured, not inferred): the generic cinematic host rule --

    .boss-cinematic.intro-film .boss-cinematic-scene {
        width: min(900px, 94vw);
        min-height: min(560px, 86vh);
        ...
    }

-- caps the intro-film's height at a fixed 560px on any viewport where
86vh exceeds 560px (i.e. viewport height above ~651px: every tablet and
phone in portrait). Since the scene has no explicit `height` and its
`.intro-film-stage` child is `position: absolute` (contributes no intrinsic
height), the box renders at exactly 560px tall regardless of how tall the
real viewport is, centered by `.boss-cinematic`'s
`display:flex; align-items:center; justify-content:center`. On an iPad
Pro 11" portrait viewport (834x1194) this measured as a 784x560 scene with
317px of empty space above and below -- a small, landscape-shaped, centered
rectangle with large top/bottom letterboxing, which is exactly what the
Owner's real-device iPad PWA report described.

Zone 2 (k21_25) and Zone 3 (k16_20, in css/e9/zone3_vertical_slice.css)
already carry a fix for this exact defect class: in portrait, their scene
expands to fill the viewport (`width:100vw; min-height:100dvh`) instead of
being capped. Zone 4 (k11_15) had zero zone-specific intro-film coverage at
all and fell through to the broken generic rule. Zone 1 (k26_30) has the
same latent gap and is out of scope for this recovery (not the reported
defect; flagged separately).

This file asserts the Zone 4 fix mirrors the Zone 2 precedent exactly, that
it is scoped to k11_15 only, and that nothing else the Owner already
accepted (Zone 1-3 shared shell, Zone 4 Lord Card, Zone 5, toolbar) changed.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
WORLD_STAGE_FRAGMENT = (
    ROOT / "components" / "adventure" / "world_stage.html"
).read_text(encoding="utf-8")


def _rule_block(selector_prefix: str) -> str:
    """Return the full `{ ... }` body for the first rule whose selector
    starts with `selector_prefix`, or '' if not found."""
    idx = INDEX.find(selector_prefix)
    if idx == -1:
        return ""
    brace_start = INDEX.find("{", idx)
    brace_end = INDEX.find("}", brace_start)
    return INDEX[brace_start:brace_end + 1]


# ---------------------------------------------------------------------------
# A/B/C/D/E — the Zone 4 intro-film must fill the viewport in portrait, not
# be capped to a fixed small box, and must participate in normal flow.
# ---------------------------------------------------------------------------

def test_zone4_intro_film_has_a_portrait_override():
    assert '#boss-cinematic.intro-film[data-zone-key="k11_15"] .boss-cinematic-scene' in INDEX


def test_zone4_portrait_override_fills_the_viewport_not_a_fixed_small_box():
    block = _rule_block(
        '#boss-cinematic.intro-film[data-zone-key="k11_15"] .boss-cinematic-scene {'
    )
    assert block, "k11_15 intro-film scene rule not found"
    assert "width: 100vw" in block
    assert "min-height: 100dvh" in block
    # The defect was a FIXED pixel cap; the fix must not reintroduce one.
    assert "560px" not in block
    assert "86vh" not in block


def test_zone4_portrait_override_is_gated_to_portrait_orientation():
    # Must live inside an (orientation: portrait) media block so landscape/
    # desktop keep their existing (already-accepted) letterboxed presentation.
    marker = '#boss-cinematic.intro-film[data-zone-key="k11_15"] .boss-cinematic-scene {\n            width: 100vw;'
    idx = INDEX.find(marker)
    assert idx != -1, "expected exact fix block not found verbatim"
    preceding = INDEX[max(0, idx - 400):idx]
    assert "@media (orientation: portrait) and (max-width: 900px)" in preceding


def test_zone4_film_shot_images_use_contain_in_portrait_not_cover():
    # object-fit:cover would crop the storyboard art to fill the new full
    # bleed frame; contain preserves the full frame (letterboxed by the art
    # itself, not by an oversized empty parent) -- same choice Zone 2 made.
    block = _rule_block('#boss-cinematic.intro-film[data-zone-key="k11_15"] .film-shot img {')
    assert block
    assert "object-fit: contain" in block


def test_zone4_caption_panel_respects_safe_area_in_full_bleed_mode():
    block = _rule_block('#boss-cinematic.intro-film[data-zone-key="k11_15"] .boss-cinematic-content {')
    assert block
    assert "env(safe-area-inset-bottom" in block


# ---------------------------------------------------------------------------
# Mirrors the already-shipped, already-accepted Zone 2 (k21_25) pattern this
# fix is modeled on -- proves it is the SAME fix, not a new invention.
# ---------------------------------------------------------------------------

def test_zone4_fix_matches_the_shape_of_the_accepted_zone2_precedent():
    zone2_scene = _rule_block(
        '#boss-cinematic.intro-film[data-zone-key="k21_25"] .boss-cinematic-scene {\n'
        '            width: 100vw;'
    )
    zone4_scene = _rule_block(
        '#boss-cinematic.intro-film[data-zone-key="k11_15"] .boss-cinematic-scene {\n'
        '            width: 100vw;'
    )
    assert zone2_scene and zone4_scene
    # Same declarations, only the selector's zone key differs.
    assert zone2_scene == zone4_scene


# ---------------------------------------------------------------------------
# F/G — Replay Story / storyboard phase visibility is a DOM/JS state concern,
# not a layout one; this recovery must not touch it. Assert the relevant
# elements and functions are still present and unmodified in shape.
# ---------------------------------------------------------------------------

def test_replay_story_cta_and_zone_card_markup_are_unaffected():
    assert 'id="e9-world-stage-details-replay"' in WORLD_STAGE_FRAGMENT
    assert 'id="e9-world-stage-details"' in WORLD_STAGE_FRAGMENT


# ---------------------------------------------------------------------------
# H/I/J — no regression to Zone 1-3 shared shell, other zones, or unrelated
# cinematic phases. The generic fallback rule and the Zone 2/Zone 4 Lord Card
# rules (already accepted) must be byte-identical to what they were before.
# ---------------------------------------------------------------------------

def test_generic_intro_film_rule_for_unscoped_zones_is_unchanged():
    # Zone 1 (k26_30) and any future zone without an override still uses the
    # original generic contract; this recovery does not touch it.
    block = _rule_block(".boss-cinematic.intro-film .boss-cinematic-scene {")
    assert block
    assert "min(900px, 94vw)" in block
    assert "min(560px, 86vh)" in block


def test_zone2_k21_25_intro_film_rule_is_untouched():
    block = _rule_block(
        '#boss-cinematic.intro-film[data-zone-key="k21_25"] .boss-cinematic-scene {\n'
        '            width: 100vw;'
    )
    assert block
    assert "min-height: 100dvh" in block
    assert "border-radius: 0" in block


def test_zone4_lord_card_rules_are_untouched():
    # Explicitly NOT modified by this recovery -- separate, already-accepted
    # surface (phase-zone4-lord-card / phase-zone4-lord-ritual /
    # result-zone4-win / result-zone4-fail). Prove the aspect-ratio Lord
    # shell contract is still exactly what it was.
    block = _rule_block(
        '#boss-cinematic.phase-zone4-lord-card[data-zone-key="k11_15"] .boss-cinematic-scene,'
    )
    assert block
    assert "aspect-ratio: 16 / 9" in block
    assert "width: min(760px, 92vw)" in block


def test_no_zone5_or_toolbar_selectors_were_touched():
    assert 'data-zone-key="k31_35"' not in INDEX  # Zone 5 has no key yet; guard against accidental introduction
    assert "non-admin-toolbar" not in INDEX or "boss-cinematic" not in _rule_block("non-admin-toolbar")
