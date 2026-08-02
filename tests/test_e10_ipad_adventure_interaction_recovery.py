import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHELL = (ROOT / "js/e9/shell.js").read_text(encoding="utf-8")
WORLD = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
RIGHT = (ROOT / "js/e9/right_cards.js").read_text(encoding="utf-8")
CSS = (ROOT / "css/e9/immersive_rpg.css").read_text(encoding="utf-8")
SHELL_CSS = (ROOT / "css/e9/shell.css").read_text(encoding="utf-8")
REFERENCE_CSS = (ROOT / "css/e9/reference_world_map.css").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")


def test_e9_zone_cta_uses_canonical_in_page_question_entry():
    assert "global.enterAdventureZoneInPage({ key: zoneKey })" in SHELL
    assert "action: 'start-zone-challenge'" in SHELL
    assert "global.location.href = '/?zone='" not in SHELL


def test_e9_question_runtime_waits_for_questions_and_srs_readiness():
    assert "window.__GO_ADVENTURE_QUESTION_RUNTIME_READY__ = false" in INDEX
    assert "needsImmediatePracticeState || e9ShellRequested" in INDEX
    assert "adventureQuestionSrsReady=true" in INDEX
    assert "adventure:question-runtime-ready" in INDEX
    assert "adventureEntryPhase === 'queued'" in SHELL
    assert "{ once: true }" in SHELL


def test_failed_in_page_filter_does_not_hide_map_before_question_exists():
    function = INDEX.split("function enterAdventureZoneInPage(zone) {", 1)[1].split("\n}\n", 1)[0]
    assert function.index("if (!unitQs.length) return false;") < function.index("_ws.classList.add('hidden')")


def test_e9_startup_tolerates_absent_legacy_mistake_badge():
    assert "const b=document.getElementById('mistake-badge');if(b){b.textContent=" in INDEX


def test_portrait_selected_detail_keeps_direct_cta_visible():
    cta_rule = CSS.split(".e9-zone-details__cta", 1)[1].split("}", 1)[0]
    assert "display: inline-flex" in cta_rule
    assert "display: none" not in cta_rule


def test_stacked_shell_does_not_capture_fixed_bottom_navigation():
    responsive = REFERENCE_CSS.split(
        '@media (max-width: 1279px) and (orientation: portrait), (max-width: 767px)',
        1,
    )[1]
    shell_rule = responsive.split('#e9-adventure-shell {', 1)[1].split('}', 1)[0]
    assert "position: relative" in shell_rule
    assert "top: auto" in shell_rule
    assert "left: auto" in shell_rule
    assert "transform: none" in shell_rule


def test_portrait_detail_exposes_complete_selected_zone_identity():
    detail = (ROOT / "components/adventure/world_stage.html").read_text(encoding="utf-8")
    for identity in (
        "e9-world-stage-details-number",
        "e9-world-stage-details-stars",
        "e9-world-stage-details-label",
        "e9-world-stage-details-state",
        "e9-world-stage-details-summary",
        "e9-world-stage-details-progress",
        "e9-world-stage-details-region-progress",
        "e9-world-stage-details-cta",
    ):
        assert f'id="{identity}"' in detail
    assert "zone.__e10Index" in WORLD
    assert "zone.stars" in WORLD


def test_all_responsive_ctas_share_one_selected_target_action():
    assert "window.E9.startAdventureFromE9(contract.targetZoneKey)" in WORLD
    assert "window.E9.startAdventureFromE9(inlineContract.targetZoneKey)" in WORLD
    assert "window.E9.startAdventureFromE9(root.__e10ChallengeTargetZoneKey)" in RIGHT
    assert "state.challengeTargetZoneKey = resolveChallengeTargetZoneKey(zone)" in WORLD


def test_e9_shell_yields_to_canonical_question_practice_state():
    selector = '#main-row #main-left #welcome-state.hidden'
    assert selector in SHELL_CSS
    assert selector in REFERENCE_CSS
    assert "display: none !important" in SHELL_CSS.split(selector, 1)[1].split("}", 1)[0]
    assert "display: none !important" in REFERENCE_CSS.split(selector, 1)[1].split("}", 1)[0]


def test_shell_adapter_enters_question_once_without_legacy_navigation(tmp_path):
    harness = tmp_path / "ipad_cta_adapter.js"
    harness.write_text(
        r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
const events = [];
const entries = [];
const listeners = {};
let questionActive = false;
const welcome = { classList: { contains(name) { return name === 'hidden' && questionActive; } } };
const document = {
  readyState: 'loading', body: { setAttribute() {}, focus() {} }, activeElement: null,
  querySelector(selector) { return selector === '#welcome-state' ? welcome : null; }, querySelectorAll() { return []; },
  addEventListener(type, handler, options) { (listeners[type] ||= []).push({ handler, once: !!(options && options.once) }); },
  dispatchEvent(event) {
    if (event.type === 'e9:adventure-command') events.push({ type: event.type, detail: event.detail });
    const active = (listeners[event.type] || []).slice();
    active.forEach((entry) => entry.handler(event));
    listeners[event.type] = (listeners[event.type] || []).filter((entry) => !entry.once);
  }
};
function CustomEvent(type, init) { this.type = type; this.detail = init && init.detail; }
const window = {
  document, CustomEvent, location: { href: '', hostname: 'localhost', search: '' },
  E9: { getFlags() { return { e9Shell: false }; } },
  enterAdventureZoneInPage(zone) {
    entries.push(zone.key);
    if (zone.key !== 'k16_20') return false;
    questionActive = true;
    return true;
  }
};
vm.runInNewContext(source, { window, document, CustomEvent, console });
const first = window.E9.startAdventureFromE9('k16_20');
const duplicate = window.E9.startAdventureFromE9('k16_20');
questionActive = false;
const locked = window.E9.startAdventureFromE9('d1_2');
const invalid = window.E9.startAdventureFromE9('');
const immediateEntries = entries.slice();
const immediateEvents = events.slice();
entries.length = 0;
events.length = 0;
window.E9.applyShellState('e9');
window.__GO_ADVENTURE_QUESTION_RUNTIME_READY__ = false;
const queued = window.E9.startAdventureFromE9('k16_20');
const duplicateQueued = window.E9.startAdventureFromE9('k16_20');
const beforeReadyEntries = entries.slice();
window.__GO_ADVENTURE_QUESTION_RUNTIME_READY__ = true;
document.dispatchEvent(new CustomEvent('adventure:question-runtime-ready'));
process.stdout.write(JSON.stringify({
  first, duplicate, locked, invalid, immediateEntries, immediateEvents,
  queued, duplicateQueued, beforeReadyEntries, queuedEntries: entries, queuedEvents: events,
  href: window.location.href
}));
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
    assert contract["first"] is True
    assert contract["duplicate"] is False
    assert contract["locked"] is False
    assert contract["invalid"] is False
    assert contract["immediateEntries"] == ["k16_20", "d1_2"]
    assert contract["href"] == ""
    assert [event["detail"]["zoneKey"] for event in contract["immediateEvents"]] == ["k16_20"]
    assert contract["queued"] is True
    assert contract["duplicateQueued"] is False
    assert contract["beforeReadyEntries"] == []
    assert contract["queuedEntries"] == ["k16_20"]
    assert [event["detail"]["zoneKey"] for event in contract["queuedEvents"]] == ["k16_20"]
    assert all(event["detail"]["action"] == "start-zone-challenge" for event in contract["queuedEvents"])
