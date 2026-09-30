"""Focused source-contract checks for the G009 prebuild authority gates."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_g009_release_shop_and_equipment_flags_are_fail_closed():
    compose = (ROOT / "docker-compose.release.yml").read_text(encoding="utf-8")
    assert re.findall(
        r'CANONICAL_COIN_SHOP_PURCHASE_ENABLED:\s*"([^"]+)"', compose
    ) == ["false", "false"]
    assert re.findall(
        r'EQUIPMENT_CANONICAL_LOADOUT_ENABLED:\s*"([^"]+)"', compose
    ) == ["false", "false"]

    deploy = (ROOT / "scripts/release/deploy-release-image.ps1").read_text(
        encoding="utf-8"
    )
    assert 'env_map["CANONICAL_COIN_SHOP_PURCHASE_ENABLED"] = "false"' in deploy
    assert 'env_map["EQUIPMENT_CANONICAL_LOADOUT_ENABLED"] = "false"' in deploy
    assert 'env_map["CANONICAL_COIN_SHOP_PURCHASE_ENABLED"] = "true"' not in deploy
    assert 'env_map["EQUIPMENT_CANONICAL_LOADOUT_ENABLED"] = "true"' not in deploy

    recreate_lines = [
        line
        for line in deploy.splitlines()
        if "docker compose" in line
        and "force-recreate" in line
        and "$appComposeService" in line
    ]
    assert len(recreate_lines) == 1
    assert "$remoteEquipmentEnableOverridePath" not in recreate_lines[0]

    equipment_state = (
        ROOT / "scripts/release/set-equipment-enable-state.ps1"
    ).read_text(encoding="utf-8")
    assert "$expectedShopValue = 'false'" in equipment_state


def test_server_write_gates_remain_authoritative_when_release_flags_are_off():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "def _canonical_coin_shop_purchase_enabled" in app_source
    assert "if not _canonical_coin_shop_purchase_enabled():" in app_source
    assert "def _equipment_canonical_loadout_enabled" in app_source
    assert "if not loadout_enabled:" in app_source
    assert "'error': 'LOADOUT_DISABLED'" in app_source


def test_g009_hero_surface_has_no_visible_messages_shortcut_and_nav_counts():
    hero = (ROOT / "hero.html").read_text(encoding="utf-8")
    assert not re.search(
        r'<a\s+class="char-shortcut"\s+href="/messages"', hero
    )
    assert 'data-g009-hero-nav="5"' in hero

    site_nav = (ROOT / "site-nav.js").read_text(encoding="utf-8")
    nav_block = site_nav.split("const NAV_ITEMS = [", 1)[1].split("];", 1)[0]
    assert len(re.findall(r"\{\s*href:", nav_block)) == 7
    assert "key: 'messages'" not in nav_block


def test_reachable_lord_trial_fallbacks_use_canonical_zh_term():
    runtime_sources = (
        ROOT / "index.html",
        ROOT / "i18n.js",
        ROOT / "js/game/encounter_presentation_framework_v1.js",
    )
    for source_path in runtime_sources:
        assert "領主試煉" not in source_path.read_text(encoding="utf-8")

    assert "領主挑戰" in (ROOT / "index.html").read_text(encoding="utf-8")
    assert "領主挑戰" in (ROOT / "i18n.js").read_text(encoding="utf-8")
