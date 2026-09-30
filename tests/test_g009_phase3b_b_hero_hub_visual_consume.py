"""Focused source contracts for G009 Phase 3B-B Hero Hub Batch A."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HERO = (ROOT / "hero.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
RUNTIME = (ROOT / "js/g009_hero_hub_batch_a.js").read_text(encoding="utf-8")
CSS = (ROOT / "css/g009_hero_hub_batch_a.css").read_text(encoding="utf-8")
SHELL = HERO[HERO.index('<main id="g009-hero-hub"'):HERO.index('</main>', HERO.index('<main id="g009-hero-hub"'))]


def test_hero_hub_has_exactly_five_visible_tabs_and_one_initial_active_tab():
    tabs = re.findall(r'data-g009-hub-tab="([^"]+)"', SHELL)
    assert tabs == ["hero", "equipment", "appearance", "pet", "honors"]
    assert SHELL.count('class="g009-subtab is-active"') == 1
    assert 'data-g009-hero-hub="batch-a"' in HERO
    assert 'data-g009-hero-sections="5"' in HERO


def test_locked_surface_labels_and_scoped_i18n_are_present():
    for label in ("角色總覽", "裝備", "外觀", "夥伴", "榮譽"):
        assert label in SHELL
    for key in (
        "g009.hero.tab.character",
        "g009.hero.tab.equipment",
        "g009.hero.tab.appearance",
        "g009.hero.tab.companion",
        "g009.hero.tab.honors",
        "g009.hero.aura.teal_pulse_ring",
        "g009.hero.aura.note",
    ):
        assert f"'{key}'" in I18N
    assert "Teal Pulse Ring" in I18N
    assert "青漾脈環" in I18N


def test_future30_v2_names_are_connected_without_exposing_starter_codes():
    expected = {
        "A1": ("洛恩・赤巾", "Lorne Redscarf"),
        "R1": ("奧倫・雪鬚赤冠", "Oren Snowbeard"),
        "R2": ("凱恩・赤金冠", "Kaen Redgold"),
        "R3": ("珊洛・緋披", "Saro Scarletcape"),
        "S2": ("凱洛・黑髻", "Kyro Blackknot"),
    }
    for key, names in expected.items():
        assert key in RUNTIME
        for name in names:
            assert name in RUNTIME
        assert f">{key}<" not in SHELL
    assert "_characterAuthorityKey" in RUNTIME
    assert "player_appearance.character_key" in HERO
    assert "data-g009-character-key" in RUNTIME


def test_equipment_is_read_only_and_backpack_remains_the_management_action():
    assert 'href="/inventory"' in SHELL
    assert "server-owned" in RUNTIME.lower()
    assert "equipped === true" in RUNTIME
    assert "active_effect_details" not in RUNTIME
    assert "attack" not in SHELL.lower()
    assert "crit" not in SHELL.lower()
    assert "data-g009-character-key" not in SHELL


def test_appearance_hides_outfit_and_aura_has_no_bonus_semantics():
    assert "g009-aura-card" in SHELL
    assert "g009.hero.aura.teal_pulse_ring" in SHELL
    assert "g009.hero.aura.note" in SHELL
    assert "outfit" not in SHELL.lower()
    assert not re.search(r"(?:ATK|DEF|Crit|XP\s*\+|stat\s*bonus|combat\s*bonus)", SHELL, re.I)
    assert "AURA_PRESENTATION_RING" not in RUNTIME
    assert '"84"' not in RUNTIME


def test_companion_reuses_existing_six_key_catalog_and_server_level_stage_contract():
    for key in (
        "ink_drop_kelpie",
        "whispering_void_kit",
        "star_shell_hatchling",
        "starpath_antlerling",
        "fatty",
        "obsidian_bastion",
    ):
        assert key in RUNTIME
    assert "pet_key" in RUNTIME
    assert "n >= 25" in RUNTIME
    assert "n >= 10" in RUNTIME
    assert "/api/pet/status" in RUNTIME
    assert "entitlement" not in RUNTIME.lower()
    assert "second entitlement" not in RUNTIME.lower()


def test_honors_reuse_existing_badge_data_and_titles():
    assert "hero-badge-filters" in RUNTIME
    assert "hero-badge-grid" in RUNTIME
    assert "slot-title" in RUNTIME
    assert "loadBadgesTab" in RUNTIME
    assert "g009.hero.honors.badges" in SHELL
    assert "g009.hero.honors.titles" in SHELL
    assert "/api/badges/definitions" in HERO
    assert "/api/badges/earned" in HERO


def test_batch_a_responsive_contract_has_all_required_viewports_and_touch_targets():
    assert "orientation: landscape" in CSS
    assert "orientation: portrait" in CSS
    assert "max-width: 1100px" in CSS
    assert "max-width: 700px" in CSS
    assert "min-height: 44px" in CSS
    assert "overflow-x: hidden" in CSS
    assert CSS.count("overflow: visible") >= 2
    assert "overflow-x: auto" not in CSS


def test_pending_derived_84_assets_and_unaccepted_batches_are_not_consumed():
    for source in (HERO, RUNTIME, CSS):
        executable = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
        executable = re.sub(r"<!--.*?-->", "", executable, flags=re.S)
        assert "assets-candidate" not in executable
        assert "Batch B" not in executable
        assert "Batch C" not in executable
        assert "world-map-identity" not in executable
