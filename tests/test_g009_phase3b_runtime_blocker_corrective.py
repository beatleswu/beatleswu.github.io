"""Focused source contracts for the Phase 3B runtime blocker corrective."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PWA = (ROOT / "pwa.js").read_text(encoding="utf-8")
WORLD_MAP_CSS = (ROOT / "css/e9/reference_world_map.css").read_text(encoding="utf-8")
WORLD_STAGE = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")


def test_mobile_pwa_banner_is_stacked_above_fixed_navigation():
    assert "#pwa-banner .pb-install" in PWA
    assert "#pwa-banner .pb-close" in PWA
    assert "@media (max-width: 768px)" in PWA
    assert "bottom: calc(64px + env(safe-area-inset-bottom, 0px) + 12px);" in PWA


def test_narrow_shared_nav_preserves_the_backpack_target_width():
    nav = (ROOT / "site-nav.js").read_text(encoding="utf-8")
    assert "@media (max-width: 520px)" in nav
    assert ".cg-nav-presence { display: none; }" in nav
    assert ".cg-nav-link { width: 44px; min-width: 44px;" in nav


def test_locked_zone_progress_hidden_attribute_is_a_render_boundary():
    selector = 'body[data-e10-visual-skin="immersive-rpg"] #e9-adventure-shell [hidden]'
    assert selector in WORLD_MAP_CSS
    rule_start = WORLD_MAP_CSS.index(selector)
    rule_end = WORLD_MAP_CSS.index("}", rule_start)
    rule = WORLD_MAP_CSS[rule_start:rule_end]
    assert "display: none !important" in rule
    assert "visibility: hidden !important" in rule
    assert "pointer-events: none !important" in rule
    assert "progressPanel.hidden = locked" in WORLD_STAGE


def test_locked_progress_fix_is_generic_not_zone_specific():
    assert "[data-g009-zone-progress]" in WORLD_STAGE
    assert "d7_plus" not in WORLD_MAP_CSS
