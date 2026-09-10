"""Owner postdeploy acceptance corrective, Issue B.

Zone 3 played Shots 1-10 as one continuous movie on entry, and replayed the
opening on every subsequent entry.

Two distinct defects, both in the Zone 3 entry helper:

1. `showZone3EntrySafeFallback` had NO seen gate at all. Every other zone goes
   through `showStageIntroCinematic`, which checks `adventureIntroSeen(zone)`
   before playing; Zone 3 short-circuits to its own helper *above* that check,
   so the opening autoplayed unconditionally -- including on an already-cleared
   zone.
2. The text safe-fallback branch never wrote the "seen" marker (only the
   manifest branch's `_finishZone3EntryManifest` did), so even with a gate the
   fallback would have re-armed itself on every entry.

Segmentation itself was already correct in the content manifest
(`journey_zone3_vertical_slice_content.js` lifecycle FIRST_ENTRY / BOSS_READY /
POST_CLEAR) and in the locale config; what was missing was the lifecycle gate.

The durable markers live in the server-side `account_cinematic_state` relation
via the pure-Python `E10_CINEMATIC_KEY_REGISTRY` allowlist -- no DDL, no schema
mutation.

This file is the Owner's 12-point acceptance matrix, pinned against source.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
CONTENT = (ROOT / "js/e9/journey_zone3_vertical_slice_content.js").read_text(encoding="utf-8")
WORLD_STAGE = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
CINEMATIC_REPLAY = (ROOT / "js/game/cinematic_replay.js").read_text(encoding="utf-8")
APP_PY = (ROOT / "app.py").read_text(encoding="utf-8")


def _function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    return source[start:source.index("\n}", start)]


# --- 1/2/7: Segment A lifecycle -------------------------------------------


def test_point_01_segment_a_is_shots_1_to_5_only():
    lifecycle = CONTENT[CONTENT.index("lifecycle: {"):CONTENT.index("shots: CINEMATIC_SHOTS")]
    assert "FIRST_ENTRY: ['SHOT01', 'SHOT02', 'SHOT03', 'SHOT04', 'SHOT05']" in lifecycle
    assert "BOSS_READY: ['SHOT06', 'SHOT07']" in lifecycle
    assert "POST_CLEAR: ['SHOT08', 'SHOT09', 'SHOT10']" in lifecycle
    # The entry helper must play the FIRST_ENTRY slice, and must refuse the
    # manifest path unless that slice is exactly five shots -- i.e. it can
    # never degrade into a ten-shot single movie.
    body = _function_body(INDEX, "async function showZone3EntrySafeFallback(zone, options = {}) {")
    assert "_zone3CinematicTimeline('FIRST_ENTRY')" in body
    assert "manifestTimeline.length === 5" in body


def test_point_02_segment_a_does_not_autoplay_on_repeat_entry():
    body = _function_body(INDEX, "async function showZone3EntrySafeFallback(zone, options = {}) {")
    gate = body[body.index("if (!zone || zone.key !== 'k16_20') return false;"):]
    assert "adventureIntroSeen(zone)" in gate, "Zone 3 entry must consult the seen marker"
    # The gate has to sit BEFORE any playback setup, or the opening still runs.
    assert gate.index("adventureIntroSeen(zone)") < gate.index("playNewbieVillageIntroFilm(")
    assert gate.index("adventureIntroSeen(zone)") < gate.index("_zone3CinematicTimeline('FIRST_ENTRY')")
    # ...and it must hand on to the next real surface rather than suppress a
    # message: the Zone Card for a map-node entry, gameplay for the legacy
    # "start training" CTA. Both live in the seen branch.
    seen_branch = gate[gate.index("adventureIntroSeen(zone)"):gate.index("_registerZone3PresentationLifecycleCleanup")]
    assert "window.E9.showAdventureZoneCard(zone.key)" in seen_branch
    assert "enterAdventureZoneInPage(zone)" in seen_branch
    assert "if (mode === 'first_entry') {" in seen_branch
    assert seen_branch.index("showAdventureZoneCard") < seen_branch.index("enterAdventureZoneInPage")


def test_point_07_cleared_reentry_autoplays_nothing():
    body = _function_body(INDEX, "async function showZone3EntrySafeFallback(zone, options = {}) {")
    assert "zone.cleared === true || adventureIntroSeen(zone)" in body
    # The E9 map dispatch path is gated on the same two authoritative facts.
    dispatch = _function_body(WORLD_STAGE, "function dispatchZone1Entry(root, zone, state) {")
    assert "zone.cleared === true || zone.status === 'completed'" in dispatch
    assert "cinematicSeen(state, cinematicKey)" in dispatch


def test_point_02b_the_fallback_branch_actually_records_seen():
    # Without this the gate above would never latch on the text fallback.
    body = _function_body(INDEX, "async function _continueZone3SafeEntry(zone, source = 'continue') {")
    assert "markAdventureIntroSeen(zone)" in body
    # Replay must bail out before that write.
    assert body.index("overlay?.dataset.zone3Replay === 'true'") < body.index(
        "markAdventureIntroSeen(zone)"
    )


# --- 3/4: Segment B --------------------------------------------------------


def test_point_03_segment_b_autoplays_on_first_authoritative_lord_ready():
    trigger = _function_body(INDEX, "function _maybeTriggerZone3BossReadyFilm(zones) {")
    # Readiness is re-derived from the server payload, never client-declared.
    assert "_adventureBossReady(zone)" in trigger
    assert "playZone3BossReadyFilm(zone)" in trigger
    ready = _function_body(INDEX, "function _adventureBossReady(zone) {")
    assert "zone?.cleared" in ready
    assert "cooldown_left" in ready
    # It is armed from the authoritative bootstrap payload, every fresh load.
    update = _function_body(INDEX, "function updateMapProgress(data) {")
    assert "_maybeTriggerZone3BossReadyFilm(zones);" in update


def test_point_03b_segment_b_is_never_spliced_onto_a_showing_segment_a():
    # The second half of the Owner's "Shots 1-10 as one movie" report. An
    # account that is ALREADY Lord-ready the first time it enters Zone 3
    # satisfies the readiness condition while Segment A is still on screen, and
    # updateMapProgress re-derives readiness on every bootstrap. The old guard
    # only refused a second BOSS_READY run, never a PRE_PLAY one -- despite its
    # own comment claiming "or any other intro-film run".
    busy = _function_body(INDEX, "function _zone3CinematicSurfaceBusy() {")
    assert "getElementById('boss-cinematic')" in busy
    assert "classList.contains('show')" in busy
    for trigger in (
        "function _maybeTriggerZone3BossReadyFilm(zones) {",
        "function _resumeZone3PostClearIfPending() {",
    ):
        body = _function_body(INDEX, trigger)
        assert "if (_zone3CinematicSurfaceBusy()) return;" in body, trigger
    # The genuine post-victory path closes the overlay before Segment C, so the
    # guard cannot block a real Lord success.
    lord_finish = INDEX[INDEX.index("btn.textContent = I18n.t('adventure.zone3.continue');"):]
    lord_finish = lord_finish[:lord_finish.index("_triggerZone3PostClearFromBossWin")]
    assert "hideBossCinematic();" in lord_finish


def test_point_04_segment_b_never_replays_on_lord_retry():
    trigger = _function_body(INDEX, "function _maybeTriggerZone3BossReadyFilm(zones) {")
    assert "adventureBossReadyFilmSeen(zone)" in trigger
    # Marking happens at onStarted, not onComplete: a retry that follows a
    # failed Trial must not find the marker still unwritten.
    play = _function_body(INDEX, "function playZone3BossReadyFilm(zone) {")
    assert "onStarted: () => markAdventureBossReadyFilmSeen(zone)" in play
    assert "phase: 'boss_ready'" in play
    assert "locale.bossReadyTimeline" in play


# --- 5/6: Segment C --------------------------------------------------------


def test_point_05_segment_c_requires_authoritative_lord_success():
    trigger = _function_body(INDEX, "function _triggerZone3PostClearFromBossWin(zone, options = {}) {")
    assert "zone.cleared === true || zone.completed === true || zone.status === 'completed'" in trigger
    assert "options.rewardSettled !== true" in trigger
    play = _function_body(INDEX, "function playZone3PostClearFilm(zone) {")
    assert "!zone.cleared" in play
    assert "phase: 'post_clear'" in play
    assert "locale.postClearTimeline" in play


def test_point_06_segment_c_never_plays_on_lord_failure():
    # The failure branch of the Lord result surface offers a retry CTA and
    # never reaches the post-clear trigger.
    start = INDEX.index("btn.textContent = I18n.t('e9.zone3.lord_failure.cta');")
    failure = INDEX[start:start + 400]
    assert "_triggerZone3PostClearFromBossWin" not in failure
    assert "playZone3PostClearFilm" not in failure
    # And the generic post-victory path refuses a second showing outright.
    generic = _function_body(INDEX, "function _triggerZonePostClearFromBossWin(zone, options = {}) {")
    assert "if (adventurePostClearSeen(zone)) return false;" in generic


# --- 8/9: manual replay ----------------------------------------------------


def test_point_08_manual_replay_still_works_and_bypasses_the_gate():
    body = _function_body(INDEX, "async function showZone3EntrySafeFallback(zone, options = {}) {")
    assert "mode !== 'manual_replay'" in body, "replay must not be blocked by the seen gate"
    # 「重溫故事」 on the map surface goes through the generic compilation, which
    # returns every unlocked segment rather than only Segment A.
    assert "playStoryReplay: playZoneStoryReplay," in INDEX
    replay = _function_body(INDEX, "function playZoneStoryReplay(zoneKey) {")
    assert "model.replaySequence(zone)" in replay
    assert "presentationOnly: true," in replay


def test_point_09_manual_replay_mutates_no_progression_or_settlement():
    replay = _function_body(INDEX, "function playZoneStoryReplay(zoneKey) {")
    for forbidden in ("fetch(", "markAdventure", "PostClearPending", "rewardSettled"):
        assert forbidden not in replay, forbidden
    finish = _function_body(INDEX, "function _finishZoneCinematicReplay(zone) {")
    for forbidden in ("fetch(", "markAdventure", "PostClearPending"):
        assert forbidden not in finish, forbidden
    # The replay model itself is untouched and still refuses an unearned ending.
    assert "post_clear" in CINEMATIC_REPLAY
    assert "defaultUnlock" in CINEMATIC_REPLAY or "isCleared" in CINEMATIC_REPLAY


# --- 10/11: durability -----------------------------------------------------


def test_point_10_seen_state_is_server_backed_not_session_memory():
    reader = _function_body(INDEX, "function adventureCinematicPhaseSeen(zone, phase) {")
    assert "_adventureCinematicState[key]" in reader
    assert "localStorage" not in reader and "sessionStorage" not in reader
    writer = _function_body(INDEX, "async function markAdventureCinematicPhaseSeen(zone, phase) {")
    assert "/api/adventure/cinematics/seen" in writer
    # The snapshot is (re)populated from the authoritative bootstrap payload.
    update = _function_body(INDEX, "function updateMapProgress(data) {")
    assert "_adventureCinematicState = data.cinematics" in update


def test_point_11_no_browser_local_story_seen_flag_survives():
    # The old browser-local seen flags are gone entirely; only the mid-playback
    # crash-recovery PENDING marker stays browser-local by design.
    assert "ADVENTURE_POSTCLEAR_STORAGE_KEY = " not in INDEX
    assert "ADVENTURE_BOSSREADY_STORAGE_KEY = " not in INDEX
    assert "'adventure_postclear_seen_v1'" not in INDEX
    assert "'adventure_bossready_seen_v1'" not in INDEX
    assert "ADVENTURE_POSTCLEAR_PENDING_STORAGE_KEY = 'adventure_postclear_pending_v1'" in INDEX
    for phase_reader in (
        "function adventureIntroSeen(zone) {",
        "function adventureBossReadyFilmSeen(zone) {",
        "function adventurePostClearSeen(zone) {",
    ):
        body = _function_body(INDEX, phase_reader)
        assert "adventureCinematicPhaseSeen(" in body
        assert "localStorage" not in body


# --- 12: no schema change --------------------------------------------------


def test_point_12_segment_markers_need_no_migration_or_schema_change():
    registry = APP_PY[APP_PY.index("E10_CINEMATIC_KEY_REGISTRY = {"):]
    registry = registry[:registry.index("E10_CINEMATIC_KEYS = ")]
    # Purely a Python allowlist comprehension over the EXISTING generic
    # account_cinematic_state key/value relation.
    assert "for zone_number in range(1, 11)" in registry
    assert "('intro', 'intro')" in registry or "('intro','intro')" in registry
    for ddl in ("ALTER TABLE", "ADD COLUMN", "CREATE INDEX"):
        assert ddl not in registry
    assert "account_cinematic_state" in APP_PY
    # The three phase keys the client writes must all be in the allowlist.
    for phase in ("intro", "boss_ready", "post_clear"):
        assert f"'{phase}'" in registry or f'"{phase}"' in registry


def test_zone3_keys_match_between_client_and_registry():
    key_builder = _function_body(
        INDEX, "function adventureCinematicKey(zone, phase = ADVENTURE_CINEMATIC_PHASES.INTRO) {"
    )
    assert "`e10_zone${index + 1}_${normalized}_v1`" in key_builder
    # world_stage.js resolves the same intro key independently.
    assert "if (zoneKey === 'k16_20') return 'e10_zone3_intro_v1';" in WORLD_STAGE
    # And the phase vocabulary is closed on the client too.
    phases = INDEX[INDEX.index("const ADVENTURE_CINEMATIC_PHASES = Object.freeze({"):]
    phases = phases[:phases.index("});")]
    assert set(re.findall(r"'([a-z_]+)'", phases)) == {"intro", "boss_ready", "post_clear"}


# --- the behavioral harness ------------------------------------------------


def test_behavioral_segmentation_runner_is_green():
    """Run the shipped entry/trigger bodies, do not merely read them.

    tests/e2e/run_w1_owner_zone3_story_segmentation.mjs evaluates the real
    showZone3EntrySafeFallback, _continueZone3SafeEntry,
    _maybeTriggerZone3BossReadyFilm and _resumeZone3PostClearIfPending against
    injected authority facts.

    On the pre-fix base the entry half of this harness reports
    ZONE3_SEGMENT_A_REPEAT_AUTOPLAY=YES -- the Owner's exact symptom. (The
    sequencing half cannot run there at all: it extracts
    _zone3CinematicSurfaceBusy, which does not exist before this corrective, so
    the runner aborts rather than producing a report. The pre-fix splice was
    confirmed separately by extracting only _maybeTriggerZone3BossReadyFilm from
    the base and supplying that predicate as a stub, which reported
    ZONE3_SEGMENT_B_SPLICED_ONTO_SEGMENT_A=YES.)
    """
    result = subprocess.run(
        ["node", str(ROOT / "tests/e2e/run_w1_owner_zone3_story_segmentation.mjs")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    output = f"stdout={result.stdout}\nstderr={result.stderr}"
    assert result.returncode == 0, output
    report = json.loads(result.stdout)
    assert report["status"] == "PASS", output
    assert report["failures"] == [], output
    evidence = report["evidence"]
    assert evidence["ZONE3_FIRST_ENTRY"] == ["PLAY:pre_play:5:first_entry"]
    assert evidence["ZONE3_SEGMENT_A_REPEAT_AUTOPLAY"] == "NO"
    assert evidence["ZONE3_CLEARED_REENTRY_AUTOPLAY"] == "NO"
    assert evidence["ZONE3_MANUAL_REPLAY_PLAYS"] == "YES"
    assert evidence["ZONE3_MANUAL_REPLAY_WRITES_STATE"] == "NO"
    assert evidence["ZONE3_SEGMENT_B_SPLICED_ONTO_SEGMENT_A"] == "NO"
    assert evidence["ZONE3_SEGMENT_B_ONCE_WHEN_SURFACE_FREE"] == ["SEGMENT_B"]
    assert evidence["ZONE3_SEGMENT_C_ONCE_ON_PENDING_RECOVERY"] == ["SEGMENT_C"]
