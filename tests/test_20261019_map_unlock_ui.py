"""Lane D offline UI checks. Synthetic state only; never closes D/A010 iPad Owner UAT.

Run with pytest, or: python tests/test_20261019_map_unlock_ui.py
Requires Node.js. No server, account, network or player data is used.
"""

import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
JS_PATH = ROOT / "js/e9/world_stage.js"
ADAPTER_PATH = ROOT / "js/e9/adapters/adventure_state.js"


class MapUnlockUI(unittest.TestCase):
    def run_js(self, assertions):
        harness = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
global.window = { E9: {} };
global.document = {
  querySelector: () => ({getAttribute: () => 'e10-vs1f-integrated-world-map'}),
  addEventListener() {}
};
const adapter = require(ADAPTER_PATH);
let source = fs.readFileSync(JS_PATH, 'utf8');
// Export closure functions only inside this test VM; production has no test API.
source = source.replace('})(document);', `
window.testApi = {zoneCompletionState, zoneStateText, recommendedEntryZone,
  configureRecommendedEntry, ctaContract, secondaryCtaContract,
  navigationSpies(render, dispatch) {
    renderSelectedZone = render; dispatchZoneSelection = dispatch;
  }};
})(document);`);
vm.runInThisContext(source);
const api = window.testApi;
function zone(overrides = {}) {
  return adapter.normalizeZone({key: 'k16_20', name: '測試洞窟', name_en: 'Test Cave',
    status: 'completed', can_enter: true, stars: 1, ...overrides});
}
function state(zones, overrides = {}) {
  return {zones, authoritativeCurrentZoneKey: zones[0]?.key,
    currentPlayerZoneKey: zones[0]?.key, questionRuntimeState: 'ready', ...overrides};
}
function button() {
  return {hidden: true, disabled: true, textContent: '', attrs: {}, handlers: new Set(),
    setAttribute(k,v) { this.attrs[k] = v; },
    removeAttribute(k) { delete this.attrs[k]; },
    addEventListener(_, fn) { this.handlers.add(fn); },
    removeEventListener(_, fn) { this.handlers.delete(fn); },
    click() { for (const fn of this.handlers) fn(); }};
}
"""
        harness = harness.replace("require(ADAPTER_PATH)", f"require({json.dumps(str(ADAPTER_PATH))})")
        harness = harness.replace("readFileSync(JS_PATH,", f"readFileSync({json.dumps(str(JS_PATH))},")
        result = subprocess.run(["node", "-e", harness + assertions], cwd=ROOT,
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_clear_and_three_stars_are_independent(self):
        self.run_js(r"""
for (const stars of [0, 1, 2]) {
  const z = zone({stars});
  assert.equal(api.zoneCompletionState(z), 'cleared');
  assert.equal(api.zoneStateText(z), `Boss cleared · Stars: ${stars} / 3`);
}
assert.equal(api.zoneCompletionState(zone({stars: 3})), 'three-star');
assert.equal(api.zoneStateText(zone({stars: 3})), 'Boss cleared · Stars: 3 / 3');
assert.equal(api.zoneCompletionState(zone({status: 'unlocked', stars: 3})), 'incomplete');
assert.equal(api.zoneStateText(zone({status: 'unlocked', stars: 3})), 'Available');
assert.equal(api.zoneCompletionState(zone({status: 'locked', stars: 3})), 'locked');
assert.equal(api.zoneStateText(zone({status: 'locked', stars: 3})), 'Locked');
""")

    def test_copy_uses_existing_locale_registry(self):
        self.run_js(r"""
const translations = {'index.adv.boss_defeated': '領主已通關', 'index.adv.stars_label': '星級'};
window.E9.I18nFallback = {t: (key, fallback) => translations[key] || fallback};
assert.equal(api.zoneStateText(zone()), '領主已通關 · 星級: 1 / 3');
""")

    def test_recommendation_is_server_primary_then_current_never_selection(self):
        self.run_js(r"""
const a = zone(), b = zone({key: 'k21_25', status: 'unlocked'});
const normalized = adapter.normalizeZones({zones: [
  {key: a.key, name: 'A', status: 'completed', can_enter: true, stars: 1},
  {key: b.key, name: 'B', status: 'unlocked', can_enter: true, stars: 0}],
  current_zone_key: b.key, primary_action: {kind: 'replenish_stars', zone_key: a.key}});
const s = state(normalized.zones, {primaryAction: normalized.primaryAction,
  authoritativeCurrentZoneKey: normalized.currentZoneKey, selectedZoneKey: b.key});
assert.equal(api.recommendedEntryZone(s).key, a.key);
s.primaryAction = null;
assert.equal(api.recommendedEntryZone(s).key, b.key);
s.authoritativeCurrentZoneKey = null;
assert.equal(api.recommendedEntryZone(s), null); // no first-zone/star/frontier guess
""")

    def test_issued_encounter_precedence_and_expiry(self):
        self.run_js(r"""
const a = zone(), b = zone({key: 'k21_25'});
const s = state([a,b], {primaryAction: {kind: 'normal_progression', zoneKey: b.key}});
window.__GO_E10_BATTLE_LIFECYCLE__ = {mode: 'active', hasNonce: true,
  attemptState: 'ISSUED', zoneKey: a.key, expiresAt: '2999-01-01T00:00:00Z'};
assert.equal(api.recommendedEntryZone(s).key, a.key);
window.__GO_E10_BATTLE_LIFECYCLE__.expiresAt = '2000-01-01T00:00:00Z';
assert.equal(api.recommendedEntryZone(s).key, b.key);
window.__GO_E10_BATTLE_LIFECYCLE__.expiresAt = '2999-01-01T00:00:00Z';
window.__GO_E10_BATTLE_LIFECYCLE__.hasNonce = false;
assert.equal(api.recommendedEntryZone(s).key, b.key);
""")

    def test_navigation_revalidates_and_does_not_start_gameplay(self):
        self.run_js(r"""
const a = zone(), b = zone({key: 'k21_25'}), s = state([a,b]);
const entry = button(), root = {__e9WorldStageState: s, querySelector: () => entry};
const navigations = [];
api.navigationSpies((r,z,key,focus) => navigations.push([key, focus]),
  (r,z) => navigations.push(['event', z.key]));
window.E9.startAdventureFromE9 = () => { throw Error('Navigation must not start gameplay'); };
api.configureRecommendedEntry(root, s);
api.configureRecommendedEntry(root, s);
assert.equal(entry.handlers.size, 1);
assert.equal(entry.hidden, false);
assert.equal(entry.attrs['data-recommended-zone'], a.key);
assert.ok(entry.textContent.includes('測試洞窟'));
// Click consumes live authority, not the closure's old target.
s.authoritativeCurrentZoneKey = b.key;
entry.click();
assert.deepEqual(navigations, [[b.key, true], ['event', b.key]]);
s.authorityUnavailable = true;
entry.click();
assert.equal(navigations.length, 2);
api.configureRecommendedEntry(root, s);
assert.equal(entry.hidden, true);
assert.equal(entry.disabled, true);
assert.equal(entry.handlers.size, 0);
assert.equal(entry.attrs['data-recommended-zone'], undefined);
""")

    def test_unknown_locked_and_nonenterable_targets_are_hidden(self):
        self.run_js(r"""
for (const z of [zone({status:'locked'}), zone({can_enter:false})]) {
  assert.equal(api.recommendedEntryZone(state([z])), null);
}
const a = zone(), s = state([a], {primaryAction: {zoneKey: 'unknown'}});
assert.equal(api.recommendedEntryZone(s), null);
assert.equal(api.recommendedEntryZone(state([a], {authorityUnavailable:true})), null);
""")

    def test_existing_clear_replay_and_star_practice_contracts_remain(self):
        self.run_js(r"""
const a = zone(), s = state([a]);
assert.equal(api.ctaContract(a,s).kind, 'replay_completed');
assert.equal(api.secondaryCtaContract(a,s).kind, 'replenish_stars');
const full = zone({stars:3});
assert.equal(api.ctaContract(full,s).kind, 'replay_completed');
assert.equal(api.secondaryCtaContract(full,s), null);
assert.equal(api.ctaContract(zone({status:'locked'}),s).enabled, false);
""")

    def test_render_wiring_and_keyboard_access(self):
        js = JS_PATH.read_text(encoding="utf-8")
        html = (ROOT / "components/adventure/world_stage.html").read_text(encoding="utf-8")
        css = (ROOT / "css/e9/reference_world_map.css").read_text(encoding="utf-8")
        self.assertIn("tile.setAttribute('data-zone-completion', zoneCompletionState(zone))", js)
        self.assertIn("configureRecommendedEntry(root, state);", js)
        self.assertIn("stateBadge.textContent = '\\u2605'", js)
        self.assertIn('id="e9-world-stage-recommended-entry"', html)
        self.assertIn('aria-controls="e9-world-stage-zones"', html)
        self.assertIn('data-zone-completion="three-star"', css)
        self.assertIn('data-zone-completion="cleared"', css)
        self.assertIn('#e9-world-stage-recommended-entry:focus-visible', css)


if __name__ == "__main__":
    unittest.main(verbosity=2)
