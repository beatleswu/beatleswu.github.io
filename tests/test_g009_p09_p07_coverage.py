"""G009 P09 semantic successor and P07 coverage-support helpers.

This file intentionally does not import ``app`` or start a runtime.  The
successor checks the exported navigation authority, semantic destination
identity, route declarations, and i18n key availability.  It does not pin
DOM structure or require an English display string as the identity contract.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
NAVIGATION_REGISTRY = ROOT / "js/e9/navigation_registry.js"
I18N = ROOT / "i18n.js"
SITE_NAV = ROOT / "site-nav.js"
APP = ROOT / "app.py"


EXPECTED_DESTINATIONS = {
    "learning_hub": {
        "path": "/curriculum",
        "label_key": "g009.nav.learning_hub",
        "zh": "學習公會",
    },
    "arena": {
        "path": "/play",
        "label_key": "g009.nav.arena",
        "zh": "競技場",
    },
    "tavern": {
        "path": "/community",
        "label_key": "g009.nav.tavern",
        "zh": "酒館",
    },
    "hero_hub": {
        "path": "/hero",
        "label_key": "g009.nav.hero_hub",
        "zh": "英雄殿",
    },
    "backpack": {
        "path": "/inventory",
        "label_key": "g009.nav.backpack",
        "zh": "背包",
    },
    "shop": {
        "path": "/shop",
        "label_key": "g009.nav.shop",
        "zh": "商店",
    },
    "premium": {
        "path": "/upgrade",
        "label_key": "g009.nav.premium",
        "zh": "通行證",
    },
}


def _navigation_registry() -> dict:
    """Read the runtime-exported registry without starting the application."""

    harness = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const window = {};
const document = { querySelector() { return null; } };
vm.runInNewContext(source, { window, document, console }, { filename: process.argv[1] });
const registry = window.E9 && window.E9.NavigationRegistry;
if (!registry) throw new Error('NavigationRegistry was not exported');
process.stdout.write(JSON.stringify({ contract: registry.contract, items: registry.items }));
"""
    result = subprocess.run(
        ["node", "-e", harness, str(NAVIGATION_REGISTRY)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _i18n_labels() -> dict[str, dict[str, str]]:
    source = I18N.read_text(encoding="utf-8")
    pattern = re.compile(
        r"['\"](?P<key>g009\.nav\.[a-z_]+)['\"]\s*:\s*\{\s*"
        r"en:\s*['\"](?P<en>[^'\"]*)['\"]\s*,\s*"
        r"zh:\s*['\"](?P<zh>[^'\"]*)['\"]"
    )
    return {
        match.group("key"): {
            "en": match.group("en"),
            "zh": match.group("zh"),
        }
        for match in pattern.finditer(source)
    }


def _declared_routes() -> set[str]:
    source = APP.read_text(encoding="utf-8")
    return set(re.findall(r"@app\.route\(\s*['\"]([^'\"]+)", source))


def _site_nav_items() -> list[dict[str, str]]:
    source = SITE_NAV.read_text(encoding="utf-8")
    block = re.search(r"const NAV_ITEMS = \[(?P<body>.*?)\];", source, re.S)
    assert block, "site navigation semantic item registry is missing"
    return [
        {"key": key, "href": href, "label_key": label_key}
        for href, key, label_key in re.findall(
            r"\{\s*href:\s*'([^']+)'\s*,\s*key:\s*'([^']+)'"
            r".*?i18n:\s*'([^']+)'",
            block.group("body"),
        )
    ]


def test_p09_semantic_successor_covers_seven_destinations_and_backpack_identity():
    registry = _navigation_registry()
    global_items = [
        item
        for item in registry["items"]
        if item.get("category") == "global"
        and "global" in item.get("placement", [])
    ]

    assert len(global_items) == 7
    assert [item["key"] for item in global_items] == list(EXPECTED_DESTINATIONS)
    assert registry["contract"] == "e10-vs1f-integrated-world-map"

    routes = _declared_routes()
    labels = _i18n_labels()
    for key, expected in EXPECTED_DESTINATIONS.items():
        item = next(candidate for candidate in global_items if candidate["key"] == key)
        assert urlsplit(item["target"]).path == expected["path"]
        assert item["labelKey"] == expected["label_key"]
        assert item.get("disabled") is not True
        assert expected["path"] in routes

        # English is observed/reportable i18n data, not the semantic identity
        # contract.  The Owner-facing Chinese label is the locked semantic
        # authority for this check.
        assert expected["label_key"] in labels
        assert labels[expected["label_key"]]["en"]
        assert labels[expected["label_key"]]["zh"] == expected["zh"]

    backpack = next(item for item in global_items if item["key"] == "backpack")
    assert backpack["target"]
    assert backpack["category"] == "global"
    assert "global" in backpack["placement"]
    assert urlsplit(backpack["target"]).path == "/inventory"
    assert "/inventory" in routes
    assert not backpack.get("parent")
    assert backpack["key"] not in {"hero_hub", "shop"}


def test_p09_semantic_successor_keeps_site_navigation_identity_aligned():
    items = _site_nav_items()
    assert len(items) == 7
    assert [item["key"] for item in items] == list(EXPECTED_DESTINATIONS)
    for item in items:
        expected = EXPECTED_DESTINATIONS[item["key"]]
        assert urlsplit(item["href"]).path == expected["path"]
        assert item["label_key"] == expected["label_key"]
