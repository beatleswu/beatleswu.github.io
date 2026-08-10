"""E10 Lord Challenge end-to-end closure — regression tests for two
confirmed production regressions in js/e9/world_stage.js's CTA logic.

Root cause 1 (CTA_SCOPE_DEFECT): `ctaContract(zone, state)` applied the
single root-level arbitration (`state.primaryAction`, computed server-side
by app.py's `_adventure_primary_action_payload`) to ANY unlocked zone card,
without checking that the arbitration actually names *that* zone. Every
unlocked zone's card therefore inherited the same "Challenge Lord" label
and the same click target as the one zone the server actually intended.

Root cause 2 (CTA_ACTION_ROUTING_DEFECT): even when a card's contract kind
was 'challenge_lord', the click handler (`configureAdventureButton`'s
`__e9AdventureHandler`, and the mobile inline CTA's own duplicate handler)
unconditionally called `window.E9.startAdventureFromE9()` -- the ordinary,
ordinary-question entry point -- and never invoked the existing, canonical
Lord flow (`openAdventureBossFromQuestCard` -> `showBossCinematic` ->
`confirmBossBattle` -> `POST /api/adventure/boss/start`).

A related integration gap found during diagnosis: `openAdventureBossFromQuestCard`
looks up live boss/cleared state from the legacy `_adventureProgress` cache,
which is never populated while the E9 shell owns the page (index.html's own
init skips `ensureLegacyAdventureMapReady()` whenever the E9 shell is
active). Calling the existing Lord entry directly from the E9 World Stage
without first bridging that cache would silently fail closed ("此區域已封印")
even for a genuinely lord-ready zone. The fix reuses the existing,
already-reviewed bridge (`window.ensureLegacyAdventureMapReady({reuseE9Adapter:true})`)
rather than inventing a second lord system or a second data source.

A THIRD instance of the same routing defect was found during diagnosis:
js/e9/right_cards.js's own right-drawer zone-detail CTA (`[data-e10-zone-cta]`)
independently re-derived the same "call startAdventureFromE9 unconditionally"
logic, entirely separate from world_stage.js's two CTAs. Its label/enabled/
target-zone attributes were already correctly wired to the per-zone
`ctaContract()` output via `zoneSelectionDetail()` -- only its click handler
had drifted. Rather than fix this a third time independently (exactly how a
second copy of this logic went unnoticed here), world_stage.js now exports
`window.E9.dispatchAdventureAction` and right_cards.js calls that shared
function instead of re-implementing the routing decision.

A FOURTH instance (E10_PR283_TUTORIAL_LORD_ROUTING_AMENDMENT) was found
during the PR #283 owner merge precheck: `renderBeginnerVillageMainline`'s
own tutorial CTA (`#e9-newbie-mainline-cta`, the Beginner Village/k26_30
onboarding panel) also called `startAdventureFromE9(zone.key)`
unconditionally. Confirmed production-reachable (shown on desktop/tablet
whenever k26_30 is selected under the live `e10-vs1f-integrated-world-map`
static contract, unconditional on progress state -- not one-time onboarding,
not dead code, so deletion was out of scope). Its label
(`newbieCtaText(zone)`) already reflected boss-ready state via
`zone.bossAvailable`; only the click handler had never been wired to the
routing decision. Fixed the same way as the third instance: the function now
receives `state` and calls the existing `ctaContract(zone, state)` /
`dispatchAdventureAction(contract)` pair -- the tutorial CTA's own label
wording is unchanged, only its routing now matches the other three surfaces.

world_stage.js has no browser/DOM test harness in this repo (see the
existing convention in test_e9_multi_zone_adventure_cta.py) -- most of this
file's coverage is precise source-level structural assertion on the real
file. For the CTA scope and click-routing decisions specifically, this
extracts the EXACT function sources (resolvePlayerLocation() through
dispatchAdventureAction(), a single contiguous block with no external
world_stage.js dependencies beyond `t`/`window`) out of the real
world_stage.js on disk and executes them for real inside a Node vm context
-- not a reimplementation of the arbitration/routing algorithm in Python.
"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORLD_STAGE_PATH = ROOT / "js/e9/world_stage.js"
WORLD_STAGE = WORLD_STAGE_PATH.read_text(encoding="utf-8")
RIGHT_CARDS = (ROOT / "js/e9/right_cards.js").read_text(encoding="utf-8")


def _extract_block(start_marker, end_marker):
    start = WORLD_STAGE.index(start_marker)
    end = WORLD_STAGE.index(end_marker, start)
    return WORLD_STAGE[start:end]


def _cta_logic_block():
    # resolvePlayerLocation() through the end of dispatchAdventureAction():
    # every function ctaContract()/dispatchAdventureAction() depend on, and
    # nothing that touches the DOM (configureAdventureButton() onward takes
    # real button elements and is covered by structural assertions below).
    return _extract_block(
        "function resolvePlayerLocation(zones) {",
        "\n  function configureAdventureButton(",
    )


# ---------------------------------------------------------------------
# Structural guards: the two click-routing call sites must delegate to a
# single shared dispatcher, never re-inline the routing decision (the
# mobile inline CTA previously duplicated the buggy logic independently of
# the desktop/details CTA -- a second copy is exactly how this class of fix
# silently misses a surface).
# ---------------------------------------------------------------------

def test_configure_adventure_button_delegates_to_shared_dispatcher():
    start = WORLD_STAGE.index("function configureAdventureButton(")
    end = WORLD_STAGE.index("\n  function configurePrimaryCta(", start)
    body = WORLD_STAGE[start:end]
    assert "dispatchAdventureAction(contract);" in body
    # The old, unconditional call this bug consisted of must not reappear.
    assert "window.E9.startAdventureFromE9(contract.targetZoneKey);" not in body


def test_mobile_inline_cta_delegates_to_same_shared_dispatcher_not_a_second_copy():
    start = WORLD_STAGE.index("var inlineCta = document.createElement('button');")
    end = WORLD_STAGE.index("selectedTile.appendChild(inline);", start)
    body = WORLD_STAGE[start:end]
    assert "dispatchAdventureAction(inlineContract);" in body
    assert "window.E9.startAdventureFromE9(inlineContract.targetZoneKey);" not in body


def test_tutorial_cta_delegates_to_same_shared_dispatcher_not_a_fourth_copy():
    # E10_PR283_TUTORIAL_LORD_ROUTING_AMENDMENT: the fourth production-
    # reachable surface (Beginner Village/k26_30's own tutorial panel).
    start = WORLD_STAGE.index("function renderBeginnerVillageMainline(root, zone, state)")
    end = WORLD_STAGE.index("\n  // Progression summaries reuse existing", start)
    body = WORLD_STAGE[start:end]
    assert "var contract = ctaContract(zone, state);" in body
    assert "dispatchAdventureAction(contract);" in body
    # The old, unconditional call this amendment fixes must not reappear.
    assert "window.E9.startAdventureFromE9(zone.key);" not in body
    # The label stays tutorial-flavored -- this amendment only fixes routing.
    assert "cta.textContent = newbieCtaText(zone);" in body


def test_all_four_production_lord_capable_cta_entries_converge_on_one_dispatcher():
    # Desktop details, mobile inline, and tutorial CTAs all live in
    # world_stage.js; the right-drawer CTA lives in right_cards.js and calls
    # the same function via its window.E9 export. Four distinct call sites,
    # one routing decision.
    assert WORLD_STAGE.count("dispatchAdventureAction(contract);") == 2  # desktop + tutorial
    assert WORLD_STAGE.count("dispatchAdventureAction(inlineContract);") == 1  # mobile
    assert "window.E9.dispatchAdventureAction(" in RIGHT_CARDS  # right drawer
    assert WORLD_STAGE.count("function dispatchAdventureAction(") == 1


def _real_code_matches(source, pattern):
    # Filters out matches that are prose inside comments (top-of-file
    # /* ... */ doc headers, // line comments, and ' * ' block-comment
    # continuation lines) -- both this file's and right_cards.js's headers,
    # and several routing-fix explanatory comments, mention function names
    # like startAdventureFromE9 in prose, not as real calls.
    header_end = source.index("*/") + 2 if "/*" in source[:200] else 0
    matches = []
    for match in re.finditer(pattern, source):
        if match.start() < header_end:
            continue
        line_start = source.rfind("\n", 0, match.start()) + 1
        line_prefix = source[line_start:match.start()]
        if "//" in line_prefix or line_prefix.lstrip().startswith("*"):
            continue
        matches.append(match)
    return matches


def test_repository_search_finds_no_remaining_direct_lord_capable_cta_routing():
    # Repo-wide proof for the amendment's own explicit ask: every real (non-
    # comment) startAdventureFromE9(...) call site in world_stage.js must
    # fall INSIDE dispatchAdventureAction()'s own body (its one ordinary-path
    # branch) -- never in a CTA click handler that re-derives the routing
    # decision independently. right_cards.js must have no real call at all
    # (it only ever calls the shared dispatcher).
    dispatch_start = WORLD_STAGE.index("function dispatchAdventureAction(contract) {")
    dispatch_end = WORLD_STAGE.index("\n  function configureAdventureButton(", dispatch_start)

    world_matches = _real_code_matches(WORLD_STAGE, r"startAdventureFromE9\(")
    assert world_matches, "expected at least one startAdventureFromE9 call (the ordinary-path branch itself)"
    for match in world_matches:
        assert dispatch_start <= match.start() < dispatch_end, (
            f"world_stage.js: startAdventureFromE9( call at offset {match.start()} falls outside "
            f"dispatchAdventureAction()'s body -- context: {WORLD_STAGE[max(0, match.start()-80):match.start()+40]!r}"
        )

    right_cards_matches = _real_code_matches(RIGHT_CARDS, r"startAdventureFromE9\(")
    assert not right_cards_matches, (
        f"right_cards.js: found a real startAdventureFromE9 call outside the shared dispatcher -- "
        f"{[RIGHT_CARDS[max(0,m.start()-60):m.start()+40] for m in right_cards_matches]}"
    )


def test_only_one_dispatch_function_exists_for_all_world_stage_ctas():
    assert WORLD_STAGE.count("function dispatchAdventureAction(") == 1
    # Desktop details CTA + tutorial (Newbie Village) CTA both use a local
    # variable named `contract`; the mobile inline CTA uses `inlineContract`.
    # Three independent call sites inside world_stage.js, all delegating to
    # the one shared dispatcher (right_cards.js's drawer CTA is the fourth
    # production-reachable surface, calling this same function via its
    # window.E9 export -- covered by test_right_cards_* below).
    assert WORLD_STAGE.count("dispatchAdventureAction(contract);") == 2
    assert WORLD_STAGE.count("dispatchAdventureAction(inlineContract);") == 1


def test_primary_cta_targets_the_arbitrated_zone_not_merely_the_selected_zone():
    start = WORLD_STAGE.index("function configurePrimaryCta(")
    end = WORLD_STAGE.index("\n  function updateSelectedZoneCopy(", start)
    body = WORLD_STAGE[start:end]
    # Must resolve the root-level arbitration's OWN zone before computing a
    # contract -- not ctaContract(zone, state) on whatever zone the caller
    # (renderSelectedZone) merely has selected for viewing.
    assert "var primaryAction = resolvePrimaryCta(state, state.zones || []);" in body
    assert body.index("resolvePrimaryCta(") < body.index("ctaContract(targetZone, state)")


def test_ctacontract_gates_root_arbitration_on_matching_zone_key():
    start = WORLD_STAGE.index("function ctaContract(")
    end = WORLD_STAGE.index("\n  function usesLandmarkCards(", start)
    body = WORLD_STAGE[start:end]
    assert "primary.zoneKey === zone.key" in body
    # The old unconditional propagation this bug consisted of must not
    # reappear (matching on truthiness of primary.zoneKey alone, regardless
    # of which zone the contract is being computed for).
    assert re.search(r"if\s*\(primary\s*&&\s*primary\.zoneKey\)\s*\{", body) is None
    # Backstop: a zone's OWN authoritative bossAvailable flag must still be
    # able to produce challenge_lord even when it isn't the single
    # globally-arbitrated pick -- never inferred from seen/total.
    assert "zone.bossAvailable === true && !zone.cleared" in body


# ---------------------------------------------------------------------
# Behavioral execution: run the real ctaContract()/dispatchAdventureAction()
# source for real, against synthetic zones/state, inside a Node vm context.
# ---------------------------------------------------------------------

_CTA_NODE_HARNESS = r"""
'use strict';
const fs = require('fs');
const assert = require('assert');
const vm = require('vm');

const WORLD_STAGE_PATH = process.argv[1];
const source = fs.readFileSync(WORLD_STAGE_PATH, 'utf8');

function extractBlock(startMarker, endMarker) {
  const start = source.indexOf(startMarker);
  if (start === -1) throw new Error('start marker not found: ' + startMarker);
  const end = source.indexOf(endMarker, start);
  if (end === -1) throw new Error('end marker not found: ' + endMarker);
  return source.slice(start, end);
}

const ctaLogicBlock = extractBlock(
  'function resolvePlayerLocation(zones) {',
  '\n  function configureAdventureButton('
);

function makeZone(overrides) {
  return Object.assign({
    key: 'zX', name: 'Zone X', nameEn: 'Zone X', status: 'unlocked',
    locked: false, cleared: false, canEnter: true, stars: 1,
    bossAvailable: false, seen: 5, total: 20,
  }, overrides || {});
}

async function main() {
  const calls = { boss: [], ordinary: [], cinematic: [], ensure: [], events: [] };
  const sandbox = {
    console,
    t: function (key, fallback) { return fallback; },
    window: {
      __GO_E10_BATTLE_LIFECYCLE__: undefined,
      openAdventureBossFromQuestCard: function (zoneKey) { calls.boss.push(zoneKey); calls.events.push('boss:' + zoneKey); },
      startAdventureStage: function (zoneKey) { calls.cinematic.push(zoneKey); calls.events.push('cinematic:' + zoneKey); },
      ensureLegacyAdventureMapReady: function (opts) { calls.ensure.push(opts); calls.events.push('ensure'); return Promise.resolve(); },
      E9: { startAdventureFromE9: function (zoneKey) { calls.ordinary.push(zoneKey); } },
    },
  };
  vm.createContext(sandbox);
  new vm.Script(ctaLogicBlock).runInContext(sandbox);

  const failures = [];
  let passCount = 0;
  function check(label, fn) {
    try { fn(); passCount++; } catch (err) { failures.push(label + ': ' + (err.message || String(err))); }
  }

  // -- Case 1: exactly one zone is authoritatively lord-ready; a root-level
  // arbitration names it. The ready zone's OWN card must show challenge_lord;
  // a sibling zone must NOT inherit it (CTA_SCOPE_DEFECT + ROOT_ACTION_LEAK).
  const readyZone = makeZone({ key: 'k21_25', bossAvailable: true, cleared: false });
  const otherZone = makeZone({ key: 'k16_20', bossAvailable: false, stars: 0 });
  const lockedZone = makeZone({ key: 'k11_15', locked: true, canEnter: false, status: 'locked' });
  const zones = [readyZone, otherZone, lockedZone];
  const state = {
    zones: zones,
    currentPlayerZoneKey: 'k16_20',
    primaryAction: { kind: 'challenge_lord', zoneKey: 'k21_25' },
  };

  check('ready zone card resolves challenge_lord', () => {
    const contract = sandbox.ctaContract(readyZone, state);
    assert.strictEqual(contract.kind, 'challenge_lord');
    assert.strictEqual(contract.targetZoneKey, 'k21_25');
  });
  check('sibling zone card does not inherit challenge_lord (scope leak)', () => {
    const contract = sandbox.ctaContract(otherZone, state);
    assert.notStrictEqual(contract.kind, 'challenge_lord');
    assert.notStrictEqual(contract.targetZoneKey, 'k21_25');
  });
  check('sibling zone card targets itself, not the arbitrated zone', () => {
    const contract = sandbox.ctaContract(otherZone, state);
    assert.strictEqual(contract.targetZoneKey, 'k16_20');
  });
  check('locked zone is never an actionable challenge target', () => {
    const contract = sandbox.ctaContract(lockedZone, state);
    assert.strictEqual(contract.enabled, false);
    assert.strictEqual(contract.targetZoneKey, null);
  });

  // -- Case 2: no root-level arbitration at all (null primaryAction) --
  // a zone's own authoritative bossAvailable must still resolve to
  // challenge_lord (the backstop branch), independent of resolvePrimaryCta's
  // single global pick.
  const noArbitrationState = { zones: zones, currentPlayerZoneKey: 'k16_20', primaryAction: null };
  check('own bossAvailable resolves challenge_lord without root arbitration', () => {
    const contract = sandbox.ctaContract(readyZone, noArbitrationState);
    assert.strictEqual(contract.kind, 'challenge_lord');
    assert.strictEqual(contract.targetZoneKey, 'k21_25');
  });

  // -- Case 3: click routing. A challenge_lord contract must invoke the
  // existing canonical Lord entry (bridged through ensureLegacyAdventureMapReady),
  // never startAdventureFromE9 -- and a normal_progression contract must
  // still use the ordinary path unchanged.
  sandbox.dispatchAdventureAction({ enabled: true, targetZoneKey: 'k21_25', kind: 'challenge_lord' });
  await new Promise((resolve) => setImmediate(resolve));
  check('challenge_lord click enters the canonical Lord flow', () => {
    assert.deepStrictEqual(calls.boss, ['k21_25']);
    assert.deepStrictEqual(calls.ordinary, []);
  });
  check('challenge_lord click bridges the E9-to-legacy progress cache first', () => {
    // Cross-realm plain objects (this call argument is constructed inside
    // the vm sandbox) are not assert.deepStrictEqual-comparable to an
    // outer-realm object literal -- compare the property directly instead.
    assert.strictEqual(calls.ensure.length, 1);
    assert.strictEqual(calls.ensure[0].reuseE9Adapter, true);
  });

  sandbox.dispatchAdventureAction({ enabled: true, targetZoneKey: 'k16_20', kind: 'normal_progression' });
  await new Promise((resolve) => setImmediate(resolve));
  check('normal_progression click still uses the ordinary entry, unchanged', () => {
    assert.deepStrictEqual(calls.ordinary, ['k16_20']);
    assert.deepStrictEqual(calls.boss, ['k21_25']); // unchanged from the prior case
  });

  check('disabled/locked contract dispatches nothing', () => {
    const before = JSON.stringify(calls);
    sandbox.dispatchAdventureAction({ enabled: false, targetZoneKey: 'k11_15', kind: 'challenge_lord' });
    assert.strictEqual(JSON.stringify(calls), before);
  });

  // -- Case 4 (E10_PR283_TUTORIAL_LORD_ROUTING_AMENDMENT): the tutorial
  // (Newbie Village, k26_30) CTA calls this exact same ctaContract()/
  // dispatchAdventureAction() pair -- proved here using k26_30 by key,
  // not merely "any zone", since it's the fourth production-reachable
  // surface this amendment closes.
  const tutorialReadyZone = makeZone({ key: 'k26_30', bossAvailable: true, cleared: false });
  const tutorialNotReadyZone = makeZone({ key: 'k26_30', bossAvailable: false, cleared: false, stars: 0 });
  const tutorialReadyState = { zones: [tutorialReadyZone], currentPlayerZoneKey: 'k26_30', primaryAction: null };
  const tutorialNotReadyState = { zones: [tutorialNotReadyZone], currentPlayerZoneKey: 'k26_30', primaryAction: null };

  check('tutorial zone (k26_30) lord-ready resolves challenge_lord', () => {
    const contract = sandbox.ctaContract(tutorialReadyZone, tutorialReadyState);
    assert.strictEqual(contract.kind, 'challenge_lord');
    assert.strictEqual(contract.targetZoneKey, 'k26_30');
  });
  check('tutorial zone (k26_30) not lord-ready resolves ordinary progression', () => {
    const contract = sandbox.ctaContract(tutorialNotReadyZone, tutorialNotReadyState);
    assert.notStrictEqual(contract.kind, 'challenge_lord');
    assert.strictEqual(contract.targetZoneKey, 'k26_30');
  });

  const tutorialReadyContract = sandbox.ctaContract(tutorialReadyZone, tutorialReadyState);
  sandbox.dispatchAdventureAction(tutorialReadyContract);
  await new Promise((resolve) => setImmediate(resolve));
  check('tutorial zone lord-ready click enters the canonical Lord flow', () => {
    assert.ok(calls.boss.includes('k26_30'));
  });

  const tutorialNotReadyContract = sandbox.ctaContract(tutorialNotReadyZone, tutorialNotReadyState);
  const ordinaryBefore = calls.ordinary.length;
  const cinematicBefore = calls.cinematic.length;
  sandbox.dispatchAdventureAction(tutorialNotReadyContract);
  await new Promise((resolve) => setImmediate(resolve));
  check('tutorial zone not-ready click reaches the canonical cinematic host before training', () => {
    assert.strictEqual(calls.ordinary.length, ordinaryBefore);
    assert.strictEqual(calls.cinematic.length, cinematicBefore + 1);
    assert.strictEqual(calls.cinematic[calls.cinematic.length - 1], 'k26_30');
    assert.strictEqual(calls.events[calls.events.length - 2], 'ensure');
    assert.strictEqual(calls.events[calls.events.length - 1], 'cinematic:k26_30');
  });

  // -- Case 5: a completed/advanced Zone 1 remains replay training, not the
  // first-entry cinematic path introduced for normal_progression.
  const advancedZone = makeZone({ key: 'k26_30', status: 'completed', cleared: true, stars: 1 });
  const advancedState = {
    zones: [advancedZone], currentPlayerZoneKey: 'k26_30',
    primaryAction: { kind: 'replay_completed', zoneKey: 'k26_30' },
  };
  const advancedContract = sandbox.ctaContract(advancedZone, advancedState);
  check('completed Zone 1 keeps replay_completed contract', () => {
    assert.strictEqual(advancedContract.kind, 'replay_completed');
  });
  const advancedOrdinaryBefore = calls.ordinary.length;
  const advancedCinematicBefore = calls.cinematic.length;
  sandbox.dispatchAdventureAction(advancedContract);
  await new Promise((resolve) => setImmediate(resolve));
  check('completed Zone 1 does not enter the first-entry cinematic host', () => {
    assert.strictEqual(calls.ordinary.length, advancedOrdinaryBefore + 1);
    assert.strictEqual(calls.cinematic.length, advancedCinematicBefore);
  });

  if (failures.length) {
    console.error('FAILURES:');
    failures.forEach((f) => console.error('  - ' + f));
    console.error('\n' + passCount + ' passed, ' + failures.length + ' failed');
    process.exitCode = 1;
  } else {
    console.log(passCount + ' passed, 0 failed');
    process.exitCode = 0;
  }
}

main();
"""


def test_cta_scope_and_routing_production_linked_behavior_via_node():
    result = subprocess.run(
        ["node", "-e", _CTA_NODE_HARNESS, "--", str(WORLD_STAGE_PATH)],
        capture_output=True, text=True, timeout=30, cwd=str(ROOT),
    )
    assert result.returncode == 0, (
        f"production-linked CTA scope/routing tests failed:\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "passed" in result.stdout
    assert "0 failed" in result.stdout


# ---------------------------------------------------------------------
# No new i18n key: the fallback-branch label reuses the existing
# actionLabel() helper (already used by resolvePrimaryCta's own
# client-computed fallback) -- this fix introduces zero new translation
# keys.
# ---------------------------------------------------------------------

def test_bossavailable_fallback_reuses_existing_actionlabel_helper():
    start = WORLD_STAGE.index("function ctaContract(")
    end = WORLD_STAGE.index("\n  function usesLandmarkCards(", start)
    body = WORLD_STAGE[start:end]
    assert "actionLabel({ kind: 'challenge_lord', zoneKey: zone.key }, state)" in body


# ---------------------------------------------------------------------
# Lord entry integration bridge: calling the canonical Lord flow from the
# E9 shell without first populating _adventureProgress would silently fail
# closed. This guards against that regression reappearing.
# ---------------------------------------------------------------------

def test_dispatch_bridges_legacy_progress_cache_before_boss_entry():
    start = WORLD_STAGE.index("function dispatchAdventureAction(")
    end = WORLD_STAGE.index("\n  function configureAdventureButton(", start)
    body = WORLD_STAGE[start:end]
    assert "window.ensureLegacyAdventureMapReady" in body
    assert "reuseE9Adapter: true" in body
    assert "window.openAdventureBossFromQuestCard" in body


def test_open_adventure_boss_from_quest_card_exported_for_cross_file_call():
    index_html = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "window.openAdventureBossFromQuestCard = openAdventureBossFromQuestCard;" in index_html


def test_world_stage_boss_route_mention_is_a_comment_not_a_direct_e9_call():
    # E9's own JS must never call the boss challenge API routes directly
    # (test_adventure_boss_finish_server_authoritative.py /
    # test_adventure_first_clear_reward.py both grep-verify this across all
    # of js/e9/*.js) -- world_stage.js only ever hands off to the existing,
    # legacy-owned entry point that performs that call.
    assert "boss/start" not in WORLD_STAGE
    assert "boss/finish" not in WORLD_STAGE


# ---------------------------------------------------------------------
# Third surface: js/e9/right_cards.js's own right-drawer zone-detail CTA
# independently re-derived the same buggy routing logic. Its label/enabled/
# target attributes were already correctly scoped per-zone via
# zoneSelectionDetail() -- only its click handler had drifted from
# world_stage.js's two CTAs. Fixed by sharing world_stage.js's dispatcher
# via a new window.E9.dispatchAdventureAction export, rather than
# re-implementing the routing decision a third time.
# ---------------------------------------------------------------------

def test_world_stage_exports_shared_dispatcher_for_other_e9_components():
    assert "window.E9.dispatchAdventureAction = dispatchAdventureAction;" in WORLD_STAGE


def test_right_cards_captures_cta_kind_alongside_existing_target_and_enabled():
    assert "root.__e10ChallengeTargetKind = detail.ctaKind || null;" in RIGHT_CARDS


def test_right_cards_click_handler_delegates_to_shared_dispatcher():
    start = RIGHT_CARDS.index("window.E9.on(zoneCta, 'click', function () {")
    end = RIGHT_CARDS.index("}, null, generation);", start)
    body = RIGHT_CARDS[start:end]
    assert "window.E9.dispatchAdventureAction(" in body
    assert "targetZoneKey: root.__e10ChallengeTargetZoneKey" in body
    assert "kind: root.__e10ChallengeTargetKind" in body
    # The old, unconditional call this bug consisted of must not reappear.
    assert "window.E9.startAdventureFromE9(root.__e10ChallengeTargetZoneKey)" not in body


def test_right_cards_cta_target_and_label_already_scoped_per_zone_unchanged():
    # Confirms the pre-existing wiring this fix intentionally left alone:
    # the button's label/enabled/target-zone attributes already flow from
    # ctaContract()'s per-zone output via zoneSelectionDetail() -- only the
    # click handler needed fixing.
    assert "cta.setAttribute('data-challenge-target-zone', detail.challengeTargetZoneKey || '');" in RIGHT_CARDS
    assert "cta.textContent = detail.ctaLabel" in RIGHT_CARDS
