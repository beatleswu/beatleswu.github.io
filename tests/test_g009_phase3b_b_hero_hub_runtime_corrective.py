"""Focused source contracts for the Phase 3B-B runtime corrective."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HERO = (ROOT / "hero.html").read_text(encoding="utf-8")
RUNTIME = (ROOT / "js/g009_hero_hub_batch_a.js").read_text(encoding="utf-8")
CSS = (ROOT / "css/g009_hero_hub_batch_a.css").read_text(encoding="utf-8")
NAV = (ROOT / "site-nav.js").read_text(encoding="utf-8")
PWA = (ROOT / "pwa.js").read_text(encoding="utf-8")


def test_equipment_refresh_consumes_authenticated_inventory_instead_of_empty_legacy_state():
    assert "readJSON('/api/player/inventory')" in RUNTIME
    assert "const inventoryJob" in RUNTIME
    assert "Array.isArray(inventoryFromLegacy) && inventoryFromLegacy.length" in RUNTIME
    assert "Array.isArray(inventoryFromLegacy) ? Promise.resolve(inventoryFromLegacy)" not in RUNTIME
    assert "equipped === true" in RUNTIME


def test_hero_subnav_fits_all_five_tabs_at_narrow_viewports():
    assert "grid-template-columns: repeat(5, minmax(0, 1fr))" in CSS
    assert CSS.count("overflow: visible") >= 2
    assert "overflow-x: auto" not in CSS
    assert re.search(r"\.g009-subtab\s*\{[^}]*min-width:\s*0", CSS, re.S)


def test_shared_shell_interactive_targets_have_the_minimum_touch_size_contract():
    assert ".cg-brand" in NAV
    assert "min-width: 44px; min-height: 44px" in NAV
    assert "height: 44px; min-height: 44px; min-width: 44px" in NAV
    assert ".cg-nav-hamburger" in NAV and "width: 44px; height: 44px" in NAV


def test_honors_and_pwa_text_rebind_to_the_settled_locale_without_zh_fallback_in_en():
    assert "function badgeLocalizedText" in HERO
    assert "`${field}_en`" in HERO
    assert "badge?.[key]" in HERO
    assert "typeof b.description" not in HERO
    assert "e9:i18n-changed" in HERO
    for key in ("index.pwa_title", "index.pwa_sub", "index.pwa_install"):
        assert key in PWA
    assert "function pwaIsEnglish" in PWA
    assert "e9:i18n-changed" in PWA


def test_hero_hub_scope_stays_five_tabs_and_keeps_read_only_presentation():
    tabs = re.findall(r'data-g009-hub-tab="([^"]+)"', HERO)
    assert tabs == ["hero", "equipment", "appearance", "pet", "honors"]
    assert 'href="/inventory"' in HERO
    assert "AURA_PRESENTATION_RING" not in RUNTIME
    executable = re.sub(r"/\*.*?\*/", "", RUNTIME, flags=re.S)
    assert "84" not in executable
