import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = (ROOT / "js/e9/navigation_registry.js").read_text(encoding="utf-8")
SHELL = (ROOT / "js/e9/shell.js").read_text(encoding="utf-8")
TOP = (ROOT / "components/adventure/top_hud.html").read_text(encoding="utf-8")
TOP_JS = (ROOT / "js/e9/top_hud.js").read_text(encoding="utf-8")
NAV_JS = (ROOT / "js/e9/left_nav.js").read_text(encoding="utf-8")
CSS = "\n".join(
    (ROOT / path).read_text(encoding="utf-8")
    for path in ("css/e9/navigation.css", "css/e9/top_hud.css", "css/e9/immersive_rpg.css")
)
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
SITE_NAV = (ROOT / "site-nav.js").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")


def test_registry_is_the_single_route_source_and_has_required_targets():
    expected = {
        "hero": "/hero?tab=hero",
        "equipment": "/hero?tab=equipment",
        "backpack": "/inventory",
        "go_spirit": "/hero?tab=pet",
        "shop": "/shop",
        "soul_records": "/mistakes",
        "battle_log": "/stats",
        "tavern": "/community",
        "heroes_hall": "/hero",
        "star_chart": "/rating_test",
        "arena": "/play",
        "pass": "/upgrade",
        "messages": "/messages",
        "daily_challenge": "/daily-challenge",
        "badges": "/badges",
        "game_records": "/games",
    }
    for key, target in expected.items():
        assert re.search(rf"key: '{key}'.*?target: '{re.escape(target)}'", REGISTRY)
    assert "/daily_challenge" not in REGISTRY
    assert not re.search(r"key: 'backpack'.*?disabled: true", REGISTRY)
    assert "desktop-primary" in REGISTRY and "mobile-primary" in REGISTRY
    assert "registry.itemsFor" in NAV_JS


def test_navigation_order_and_long_label_contract_are_explicit():
    assert "'desktop-primary': 3, 'mobile-primary': 5" in REGISTRY
    assert "'desktop-primary': 4, 'mobile-primary': 4" in REGISTRY
    assert "white-space: normal" in CSS
    assert "grid-template-columns: repeat(6, minmax(0, 1fr))" in CSS
    assert "env(safe-area-inset-bottom, 0px)" in CSS
    assert "min-height: 44px" in CSS


def test_i18n_navigation_keys_are_complete_in_both_languages():
    for key, en, zh in (
        ("e10.nav.go_spirit", "Go Spirit Companion", "棋靈夥伴"),
        ("e10.nav.all_features", "All Features", "全部功能"),
        ("e10.nav.close", "Close", "關閉"),
        ("e10.nav.language", "Language", "語言"),
        ("e10.nav.sound", "Sound", "音效"),
    ):
        assert f"'{key}'" in I18N
        assert f"en: '{en}'" in I18N
        assert f"zh: '{zh}'" in I18N
    assert "inv.comingSoon" in NAV_JS


def test_overlays_have_dialog_focus_and_escape_contracts():
    assert TOP.count('role="dialog"') == 2
    assert TOP.count('aria-modal="true"') == 2
    assert "focusables(overlay)" in TOP_JS
    assert "event.key === 'Escape'" in TOP_JS
    assert "event.key !== 'Tab'" in TOP_JS
    assert "document.body.style.overflow = 'hidden'" in TOP_JS
    assert "document.body.style.overflow = previousBodyOverflow" in TOP_JS
    assert "lastTrigger.focus()" in TOP_JS
    assert "aria-controls" in TOP_JS and "aria-expanded" in TOP_JS


def test_accessible_names_and_disabled_semantics_are_not_tooltip_only():
    assert 'data-i18n-aria-label="e10.nav.player_profile"' in TOP
    assert "control.disabled = true" in NAV_JS
    assert "aria-disabled" in NAV_JS
    assert "data-i18n-aria-label" in SITE_NAV
    assert "aria-current=\"page\"" in SITE_NAV
    assert "width: 44px" in SITE_NAV and "min-height: 44px" in SITE_NAV


def test_new_navigation_is_exact_marker_gated_and_fallback_removes_overlay_dom():
    assert "registry.exactContract()" in NAV_JS
    assert "registry.exactContract()" in TOP_JS
    assert "root.querySelectorAll('[data-e10-vs1f-nav]')" in TOP_JS
    assert "node.remove()" in TOP_JS
    assert "data-e10-vs1f-icon" in REGISTRY


def test_formal_ten_zone_names_are_runtime_and_fixture_contract():
    names = (
        "圍棋新手村", "史萊姆平原", "哥布林洞穴", "迷霧森林", "獸人部落",
        "龍之谷", "賢者之塔", "魔王城前線", "諸神黃昏", "上古終焉神殿",
    )
    visual = (ROOT / "tests/e2e/run_e10_vs1e_visual_contract.mjs").read_text(encoding="utf-8")
    for name in names:
        assert name in APP
        assert name in visual


def test_adventure_command_executes_without_mutating_progress_or_starting_challenge(tmp_path):
    harness = tmp_path / "adventure_command_test.js"
    harness.write_text(
        """
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
const events = [];
const scrollCalls = [];
let focused = false;
let reduced = false;
const selected = { selectedZoneKey: 'k16_20' };
const player = { locationKey: 'k21_25' };
const map = {
  attrs: {},
  hasAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k); },
  setAttribute(k, v) { this.attrs[k] = v; },
  scrollIntoView(opts) { scrollCalls.push(opts); },
  focus() { focused = true; }
};
const body = { setAttribute() {}, focus() {} };
const document = {
  readyState: 'complete', body, activeElement: null,
  querySelector(sel) { if (sel === '#e9-map-stage') return map; return null; },
  querySelectorAll() { return []; },
  addEventListener() {},
  dispatchEvent(event) { events.push(event.type); }
};
function CustomEvent(type) { this.type = type; }
const window = {
  document, CustomEvent, location: { href: '', hostname: 'localhost', search: '' },
  matchMedia() { return { matches: reduced }; },
  E9: { getFlags() { return { e9Shell: false }; } }
};
const context = { window, document, CustomEvent, console };
vm.runInNewContext(source, context);
let challengeCalls = 0;
window.E9.startAdventureFromE9 = () => { challengeCalls += 1; };
const before = JSON.stringify({ selected, player });
const result = window.E9.runAdventureCommand();
reduced = true;
window.E9.runAdventureCommand();
const after = JSON.stringify({ selected, player });
process.stdout.write(JSON.stringify({ before, after, result, challengeCalls, events, scrollCalls, focused }));
""",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["node", str(harness), str(ROOT / "js/e9/shell.js")],
        check=True,
        capture_output=True,
        text=True,
    )
    contract = json.loads(result.stdout)
    assert contract["before"] == contract["after"]
    assert contract["challengeCalls"] == 0
    assert contract["events"] == ["e9:adventure-command", "e9:adventure-command"]
    assert contract["scrollCalls"] == [
        {"behavior": "smooth", "block": "start"},
        {"behavior": "auto", "block": "start"},
    ]
    assert contract["focused"] is True
    assert contract["result"] is True
    assert "startAdventureFromE9" not in re.search(
        r"function runAdventureCommand\(\) \{.*?\n  \}", SHELL, re.S
    ).group(0)
