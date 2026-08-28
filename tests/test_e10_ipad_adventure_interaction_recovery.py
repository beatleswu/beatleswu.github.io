import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHELL = (ROOT / "js/e9/shell.js").read_text(encoding="utf-8")
WORLD = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
RIGHT = (ROOT / "js/e9/right_cards.js").read_text(encoding="utf-8")
CSS = (ROOT / "css/e9/immersive_rpg.css").read_text(encoding="utf-8")
WORLD_STAGE_CSS = (ROOT / "css/e9/world_stage.css").read_text(encoding="utf-8")
SHELL_CSS = (ROOT / "css/e9/shell.css").read_text(encoding="utf-8")
REFERENCE_CSS = (ROOT / "css/e9/reference_world_map.css").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")


def test_e9_zone_cta_uses_canonical_in_page_question_entry():
    assert "global.enterAdventureZoneInPage({ key: zoneKey })" in SHELL
    assert "action: 'start-zone-challenge'" in SHELL
    assert "global.location.href = '/?zone='" not in SHELL


def test_e9_question_runtime_waits_for_questions_and_srs_readiness():
    assert "window.__GO_ADVENTURE_QUESTION_RUNTIME_READY__ = false" in INDEX
    assert "window.__GO_ADVENTURE_QUESTION_RUNTIME_ERROR__ = null" in INDEX
    assert "notifyAdventureQuestionRuntimeError('questions', err)" in INDEX
    assert "notifyAdventureQuestionRuntimeError('srs', e)" in INDEX
    assert "needsImmediatePracticeState || e9ShellRequested" in INDEX
    assert "adventureQuestionSrsReady=true" in INDEX
    assert "adventure:question-runtime-ready" in INDEX
    assert "adventure:question-runtime-error" in INDEX
    assert "adventureEntryPhase === 'queued'" in SHELL
    assert "{ once: true }" in SHELL


def test_question_runtime_error_keeps_world_stage_visible_but_non_actionable():
    assert "state.questionRuntimeState = 'error';" in WORLD
    assert "setRetryButton(root, true);" in WORLD
    assert "state.authorityUnavailable || state.questionRuntimeState !== 'ready'" in WORLD
    assert "button.disabled = !enabled" in WORLD


def test_boss_finish_refreshes_world_stage_and_compact_progress():
    assert "document.dispatchEvent(new CustomEvent('e10:adventure-state-updated'" in INDEX
    assert "window.E9.on(document, 'e10:adventure-state-updated', onAdventureStateUpdated" in WORLD
    assert "window.E9.on(document, 'e10:adventure-state-updated', onAdventureStateUpdated" in RIGHT
    assert "setCompactProgressLoading(root);" in RIGHT


def test_changed_e10_static_resources_use_a_fresh_source_revision():
    assert "/js/e9/world_stage.js?v=20260828e040s1" in INDEX
    assert "/js/e9/right_cards.js?v=20260828e040s1" in INDEX
    assert "/css/e9/reference_world_map.css?v=20260828e040s1" in INDEX
    assert "/js/e9/world_stage.js?v=20260821e10xsurface002" not in INDEX
    assert "/js/e9/right_cards.js?v=20260821e10xsurface002" not in INDEX
    assert "/css/e9/reference_world_map.css?v=20260801e10art1" not in INDEX


def test_failed_in_page_filter_does_not_hide_map_before_question_exists():
    function = INDEX.split("async function enterAdventureZoneInPage(zone) {", 1)[1].split("\n}\n", 1)[0]
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


def test_stacked_layout_assigns_zone_detail_to_lower_card_only():
    assert "(max-width: 1279px) and (orientation: portrait), (max-width: 767px)" in RIGHT
    assert "if (lowerCardOwnsDetails) setOpen(false, false)" in RIGHT
    assert "root.hidden = lowerCardOwnsDetails" in RIGHT
    assert "root.inert = lowerCardOwnsDetails" in RIGHT
    assert "lowerCardOwnsDetails ? 'lower-card' : 'side-panel'" in RIGHT
    assert "toggle.tabIndex = -1" in RIGHT
    assert "window.E9.on(stackedDetailSurface, 'change', syncDetailSurfaceOwnership" in RIGHT
    assert '#e9-right-cards-slot[hidden][data-e10-detail-owner="lower-card"]' in CSS


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
        "e9-world-stage-details-boss-progress",
        "e9-world-stage-details-cta",
    ):
        assert f'id="{identity}"' in detail
    assert 'id="e9-world-stage-details-replay"' in detail
    assert "zone.__e10Index" in WORLD
    assert "zone.stars" in WORLD


def test_portrait_detail_uses_authoritative_boss_progress_and_replay_surface():
    assert "function zoneBossProgressText(zone)" in WORLD
    assert "if (zone.bossAvailable) return bossReadyText(zone);" in WORLD
    assert "if (zone.cleared) return clearedText(zone);" in WORLD
    assert "index.adv.boss_intro_progress" in WORLD
    assert "var bossProgress = root.querySelector('#e9-world-stage-details-boss-progress');" in WORLD
    assert "bossProgress.textContent = zoneBossProgressText(zone);" in WORLD
    assert "configureStoryReplayButton(replay, zone);" in WORLD


def test_ipad_zone_card_responsive_layout_preserves_replay_and_close_controls():
    portrait = CSS.split(
        '@media (min-width: 768px) and (max-width: 1279px) and (orientation: portrait)',
        1,
    )[1]
    detail_rule = portrait.split(
        '.e9-zone-details:not([hidden]) {',
        1,
    )[1].split('}', 1)[0]
    assert "position: relative" in detail_rule
    assert "overflow: visible" in detail_rule
    assert ".e9-zone-details__story-replay" in WORLD_STAGE_CSS
    assert "white-space: nowrap" in WORLD_STAGE_CSS
    assert ".e10-drawer-zone-summary {" in CSS
    summary_rule = CSS.split('.e10-drawer-zone-summary {', 1)[1].split('}', 1)[0]
    assert "clear: both" in summary_rule


def test_all_responsive_ctas_share_one_selected_target_action():
    # All three responsive CTA surfaces (desktop/details, mobile inline, and
    # the right-drawer zone panel) delegate to the SAME shared dispatcher --
    # world_stage.js's own routing decision (challenge_lord vs ordinary) is
    # never re-derived independently a third time.
    assert "function dispatchAdventureAction(contract)" in WORLD
    assert "window.E9.dispatchAdventureAction = dispatchAdventureAction;" in WORLD
    assert "dispatchAdventureAction(contract);" in WORLD
    assert "dispatchAdventureAction(inlineContract);" in WORLD
    assert "window.E9.dispatchAdventureAction(" in RIGHT
    assert "targetZoneKey: root.__e10ChallengeTargetZoneKey" in RIGHT
    assert "kind: root.__e10ChallengeTargetKind" in RIGHT
    assert "state.challengeTargetZoneKey = ctaContract(zone, state).targetZoneKey" in WORLD


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
(async () => {
  // enterAdventureQuestion()/startAdventureFromE9() now await the resume-
  // aware enterAdventureZoneInPage() (async since it also awaits
  // _resolveMapBattleV1Resume()) -- every call must be awaited in the same
  // sequence the old synchronous calls implied, or state set inside the
  // resolved chain (adventureEntryPhase, entries, dispatched events) would
  // not yet be visible to the next assertion.
  const first = await window.E9.startAdventureFromE9('k16_20');
  const duplicate = await window.E9.startAdventureFromE9('k16_20');
  questionActive = false;
  const locked = await window.E9.startAdventureFromE9('d1_2');
  const invalid = await window.E9.startAdventureFromE9('');
  const immediateEntries = entries.slice();
  const immediateEvents = events.slice();
  entries.length = 0;
  events.length = 0;
  window.E9.applyShellState('e9');
  window.__GO_ADVENTURE_QUESTION_RUNTIME_READY__ = false;
  const queued = await window.E9.startAdventureFromE9('k16_20');
  const duplicateQueued = await window.E9.startAdventureFromE9('k16_20');
  const beforeReadyEntries = entries.slice();
  window.__GO_ADVENTURE_QUESTION_RUNTIME_READY__ = true;
  document.dispatchEvent(new CustomEvent('adventure:question-runtime-ready'));
  // The queued listener itself calls the now-async enterAdventureQuestion()
  // synchronously-fired-but-asynchronously-resolving -- flush the microtask
  // queue before reading the state it sets.
  await new Promise((resolve) => setImmediate(resolve));
  process.stdout.write(JSON.stringify({
    first, duplicate, locked, invalid, immediateEntries, immediateEvents,
    queued, duplicateQueued, beforeReadyEntries, queuedEntries: entries, queuedEvents: events,
    href: window.location.href
  }));
})();
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
