"""Regression coverage for the final server-backed Zone 1 entry contract."""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / 'index.html').read_text(encoding='utf-8')
WORLD_STAGE = (ROOT / 'js/e9/world_stage.js').read_text(encoding='utf-8')
ADAPTER = (ROOT / 'js/e9/adapters/adventure_state.js').read_text(encoding='utf-8')
WORLD_STAGE_TEMPLATE = (ROOT / 'components/adventure/world_stage.html').read_text(encoding='utf-8')
RIGHT_CARDS_TEMPLATE = (ROOT / 'components/adventure/right_cards.html').read_text(encoding='utf-8')
WORLD_STAGE_CSS = (ROOT / 'css/e9/world_stage.css').read_text(encoding='utf-8')
IMMERSIVE_RPG_CSS = (ROOT / 'css/e9/immersive_rpg.css').read_text(encoding='utf-8')
I18N = (ROOT / 'i18n.js').read_text(encoding='utf-8')


def _block(source, start_marker, end_marker):
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def test_zone1_normal_progression_remains_the_zone_card_training_handoff():
    body = _block(
        WORLD_STAGE,
        'function dispatchAdventureAction(contract) {',
        '\n  function cinematicSeen(',
    )
    assert "contract.kind === 'challenge_lord'" in body
    assert 'window.E9.startAdventureFromE9(contract.targetZoneKey);' in body
    assert 'window.startAdventureStage(' not in body
    assert "targetZoneKey === 'k26_30'" not in body


def test_zone1_node_entry_uses_server_state_and_canonical_host():
    body = _block(
        WORLD_STAGE,
        'function cinematicSeen(state, cinematicKey) {',
        '\n  function configureStoryReplayButton(',
    )
    assert "ACTIVE_INTRO_ZONE_KEY = 'k26_30'" in WORLD_STAGE
    assert "ACTIVE_INTRO_CINEMATIC_KEY = 'e10_zone1_intro_v1'" in WORLD_STAGE
    assert "entry.seen === true" in body
    assert "mode: 'first_entry'" in body
    assert 'window.startAdventureStage' in body
    assert 'window.ensureLegacyAdventureMapReady({ reuseE9Adapter: true })' in body
    assert 'localStorage' not in body


def test_zone_card_replay_is_zone1_only_and_uses_same_host_in_manual_mode():
    body = _block(
        WORLD_STAGE,
        'function replayAdventureIntro(zoneKey) {',
        '\n  function updateAdventureCinematicState(',
    )
    assert "zoneKey !== ACTIVE_INTRO_ZONE_KEY" in body
    assert "mode: 'manual_replay'" in body
    assert 'window.startAdventureStage' in body
    assert "e10_zone2_intro_v1" not in body
    assert "data-e10-zone-replay" in RIGHT_CARDS_TEMPLATE
    assert "data-i18n=\"e10.world_stage.replay_story\"" in WORLD_STAGE_TEMPLATE
    assert "data-e10-zone-replay" in RIGHT_CARDS_TEMPLATE


def test_cinematic_state_is_server_backed_and_completion_returns_to_zone_card():
    start = INDEX.index('async function startAdventureStage(zoneKey, options = {})')
    end = INDEX.index('\nfunction adventureCinematicKey(zone)', start)
    start_body = INDEX[start:end]
    assert "options.mode || 'legacy'" in start_body
    assert 'showStageIntroCinematic(zone, {' in start_body

    cinematic = _block(INDEX, 'async function showStageIntroCinematic(zone, options = {})', '\n\n window.startAdventureStage')
    assert "const mode = options.mode || 'legacy';" in cinematic
    assert "mode === 'first_entry' && adventureIntroSeen(zone)" in cinematic
    assert 'hideBossCinematic();' in cinematic
    assert 'window.E9.showAdventureZoneCard(zone.key);' in cinematic

    finish = _block(INDEX, 'async function finishIntroFilm(zone) {', '\nfunction skipIntroFilm()')
    assert 'await markAdventureIntroSeen(zone)' in finish
    assert "mode === 'first_entry' || mode === 'manual_replay'" in finish
    assert 'window.E9.showAdventureZoneCard(zone.key);' in finish
    assert 'enterAdventureZoneInPage(zone)' not in finish


def test_intro_seen_state_has_no_browser_authority_or_legacy_backfill():
    assert 'adventure_intro_seen_v1' not in INDEX
    assert 'adventure_intro_seen_v2' not in INDEX
    assert "localStorage.getItem('adventure_intro" not in INDEX
    assert '/api/adventure/cinematics/seen' in INDEX
    assert '_adventureCinematicState' in INDEX
    assert 'data.cinematics' in INDEX


def test_adapter_normalizes_all_registered_keys_as_server_state():
    assert 'e10_zone1_intro_v1' in ADAPTER
    assert 'e10_zone10_intro_v1' in ADAPTER
    assert 'raw.cinematics' in ADAPTER
    assert "seen: !!(entry && entry.seen === true)" in ADAPTER
    assert 'localStorage' not in ADAPTER


def test_zone_card_replay_labels_are_i18n_backed_and_secondary():
    assert "'e10.world_stage.replay_story'" in I18N
    assert "en: 'Replay Story'" in I18N
    assert "zh: '重溫故事'" in I18N
    assert 'e9-zone-details__story-replay' in WORLD_STAGE_TEMPLATE
    assert 'e10-drawer-zone-summary__replay' in RIGHT_CARDS_TEMPLATE


def test_replay_control_has_responsive_non_overlapping_layout_contract():
    assert '.e9-zone-details {\n  position: relative;' in WORLD_STAGE_CSS
    assert '.e9-zone-details__story-replay {\n  position: absolute;' in WORLD_STAGE_CSS
    assert '.e9-zone-details__kicker { padding-right: 124px; }' in WORLD_STAGE_CSS
    assert 'max-width: calc(100% - 32px);' in WORLD_STAGE_CSS
    assert '[hidden] { display: none; }' in WORLD_STAGE_CSS
    assert '.e10-drawer-zone-summary {\n  position: relative;' in IMMERSIVE_RPG_CSS
    assert '.e10-drawer-zone-summary__kicker {\n  padding-right: 124px;' in IMMERSIVE_RPG_CSS
    assert 'max-width: calc(100% - 24px);' in IMMERSIVE_RPG_CSS


def test_interrupted_intro_has_no_mark_seen_path_before_legitimate_completion():
    play = _block(INDEX, 'async function playNewbieVillageIntroFilm(zone, opts = {})', '\nfunction playZone1BossReadyFilm(')
    assert 'markAdventureIntroSeen' not in play
    assert 'if (!item)' in play
    assert 'finishIntroFilm(zone);' in play


def test_later_cinematic_gates_and_progression_boundaries_are_unchanged():
    assert 'if (!_adventureBossReady(zone)) return;' in INDEX
    assert 'if (adventureBossReadyFilmSeen(zone)) return;' in INDEX
    assert 'challenge_lord' in WORLD_STAGE
    assert 'window.openAdventureBossFromQuestCard(contract.targetZoneKey)' in WORLD_STAGE
    assert 'monster_defeated' in INDEX
    assert '_maybeTriggerZone1PostClearFilm' in INDEX
    assert 'window.E9.replayAdventureIntro = replayAdventureIntro;' in WORLD_STAGE
    assert 'window.E9.showAdventureZoneCard = showAdventureZoneCard;' in WORLD_STAGE


_ENTRY_NODE_HARNESS = r"""
'use strict';
const fs = require('fs');
const assert = require('assert');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
function block(startMarker, endMarker) {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start);
  if (start < 0 || end < 0) throw new Error('source block not found');
  return source.slice(start, end);
}
const logic = block(
  'function cinematicSeen(state, cinematicKey) {',
  '  function configureStoryReplayButton('
);
const calls = [];
const sandbox = {
  console,
  document: { querySelector() { return null; } },
  window: {
    ensureLegacyAdventureMapReady() { calls.push('ensure'); return Promise.resolve(); },
    startAdventureStage(zoneKey, options) { calls.push(['cinematic', zoneKey, options.mode]); },
  },
};
vm.createContext(sandbox);
new vm.Script("const ACTIVE_INTRO_ZONE_KEY = 'k26_30'; const ACTIVE_INTRO_CINEMATIC_KEY = 'e10_zone1_intro_v1';").runInContext(sandbox);
new vm.Script(logic).runInContext(sandbox);

const zone = { key: 'k26_30', locked: false };
const unseen = { cinematics: { e10_zone1_intro_v1: { seen: false } } };
const seen = { cinematics: { e10_zone1_intro_v1: { seen: true } } };
sandbox.dispatchZone1Entry({}, zone, unseen);
sandbox.dispatchZone1Entry({}, zone, seen);
unseen.zone1EntryInFlight = true;
sandbox.dispatchZone1Entry({}, zone, unseen);
sandbox.replayAdventureIntro('k26_30');

setTimeout(() => {
  assert.deepStrictEqual(calls, [
    'ensure',
    'ensure',
    ['cinematic', 'k26_30', 'first_entry'],
    ['cinematic', 'k26_30', 'manual_replay'],
  ]);
  console.log('entry/replay server-state routing: 4 passed, 0 failed');
}, 0);
"""


def test_real_entry_helpers_cover_unseen_seen_and_manual_replay_modes():
    result = subprocess.run(
        ['node', '-e', _ENTRY_NODE_HARNESS, '--', str(ROOT / 'js/e9/world_stage.js')],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, f'entry/replay routing failed:\n{result.stdout}\n{result.stderr}'
    assert '4 passed, 0 failed' in result.stdout
