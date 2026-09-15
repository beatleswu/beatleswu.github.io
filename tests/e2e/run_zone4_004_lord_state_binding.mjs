import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..", "..");
const matrix = JSON.parse(await readFile(path.join(root, "ZONE4_004_LORD_STATE_BINDING_MATRIX.json"), "utf8"));
const require = createRequire(import.meta.url);
const runtime = require(path.join(root, "js", "e10", "zone4_owner_story_runtime.js"));

class FakeAudio {
  static instances = [];
  static activeBySlot = new Map();
  static maxActiveBySlot = new Map();

  constructor(src, meta) {
    this.src = src;
    this.meta = meta || {};
    this.loop = false;
    this.paused = true;
    this.currentTime = 0;
    this.listeners = new Map();
    FakeAudio.instances.push(this);
  }

  addEventListener(name, handler) {
    if (!this.listeners.has(name)) this.listeners.set(name, new Set());
    this.listeners.get(name).add(handler);
  }

  removeEventListener(name, handler) {
    if (this.listeners.has(name)) this.listeners.get(name).delete(handler);
  }

  dispatch(name) {
    for (const handler of this.listeners.get(name) || []) handler();
  }

  play() {
    this.paused = false;
    const slot = this.meta.slot || "unknown";
    if (!FakeAudio.activeBySlot.has(slot)) FakeAudio.activeBySlot.set(slot, new Set());
    const active = FakeAudio.activeBySlot.get(slot);
    active.add(this);
    FakeAudio.maxActiveBySlot.set(slot, Math.max(FakeAudio.maxActiveBySlot.get(slot) || 0, active.size));
    if (!this.loop) setImmediate(() => {
      if (!this.paused) {
        this.dispatch("ended");
        active.delete(this);
      }
    });
    return Promise.resolve();
  }

  pause() {
    this.paused = true;
    const active = FakeAudio.activeBySlot.get(this.meta.slot || "unknown");
    if (active) active.delete(this);
  }
}

function controller() {
  return runtime.create({
    matrix,
    document: null,
    audioFactory: (src, meta) => new FakeAudio(src, meta),
  });
}

assert.equal(matrix.counts.main_story_visuals, 22);
assert.equal(matrix.counts.lord_state_visuals, 6);
assert.equal(matrix.main_story_order.length, 22);
assert.equal(matrix.main_story_order[15], "Z4_S2_08");
assert.equal(matrix.main_story_order[16], "Z4_S3_01");
assert.equal(matrix.main_story_order.some((id) => id.startsWith("Z4_LORD_")), false);
assert.equal(matrix.lord_state_machine.linear_story_exclusion.s3_06_to_lord_01_auto_advance, false);
assert.deepEqual(matrix.tracks.lord_trial.state_ids, [
  "challenge_entry",
  "challenge_domain",
  "challenge_active",
  "failure_retraining",
  "success_background",
  "success_portrait",
]);

const flow = controller();
assert.equal((await flow.jumpToBeat("Z4_S2_08")), true);
assert.equal(flow.getSnapshot().beatId, "Z4_S2_08");
assert.equal((await flow.next()), true);
assert.equal(flow.getSnapshot().lordState, "challenge_entry");
assert.equal(flow.getSnapshot().currentVisualId, "Z4-LORD-01");
assert.equal((await flow.next()), true);
assert.equal(flow.getSnapshot().lordState, "challenge_domain");
assert.deepEqual(flow.getCurrentBeat().dialogue_line_ids, [
  "Z4_LORD_PRE_RABBIT_001",
  "Z4_LORD_PRE_RABBIT_002",
  "Z4_LORD_PRE_RABBIT_003",
]);
assert.equal((await flow.next()), true);
assert.equal(flow.getSnapshot().lordState, "challenge_active");
assert.equal(flow.getSnapshot().currentVisualId, "Z4-LORD-06");

assert.equal((await flow.simulateFail()), true);
assert.equal(flow.getSnapshot().lordState, "failure_retraining");
assert.equal(flow.getSnapshot().currentVisualId, "Z4-LORD-03");
assert.deepEqual(flow.getCurrentBeat().dialogue_line_ids, [
  "Z4_LORD_FAIL_HERO_001",
  "Z4_LORD_FAIL_HERO_002",
]);
assert.equal(flow.getSnapshot().lordPass, false);
assert.equal((await flow.next()), true);
assert.equal(flow.getSnapshot().beatId, "Z4_S2_08");
assert.equal(flow.getSnapshot().trackId, "main_story");

assert.equal((await flow.next()), true);
assert.equal(flow.getSnapshot().lordState, "challenge_entry");
await flow.next();
await flow.next();
assert.equal(flow.getSnapshot().lordState, "challenge_active");
assert.equal((await flow.simulatePass()), true);
assert.equal(flow.getSnapshot().lordState, "success_background");
assert.equal(flow.getSnapshot().currentVisualId, "Z4-LORD-04");
assert.equal(flow.getSnapshot().lordPass, true);
assert.equal((await flow.next()), true);
assert.equal(flow.getSnapshot().lordState, "success_portrait");
assert.equal(flow.getSnapshot().currentVisualId, "Z4-LORD-05");
assert.equal((await flow.next()), true);
assert.equal(flow.getSnapshot().beatId, "Z4_S3_01");
assert.equal(flow.getSnapshot().trackId, "main_story");
assert.equal(flow.getSnapshot().lordPass, true);

assert.equal((await flow.jumpToBeat("Z4_S3_06")), true);
assert.equal((await flow.next()), false);
assert.equal(flow.getSnapshot().beatId, "Z4_S3_06");
assert.notEqual(flow.getSnapshot().trackId, "lord_trial");

const gated = controller();
assert.equal(gated.setTrack("scene_s3"), false);
assert.equal(gated.getSnapshot().status, "SCENE_LOCKED_LORD_PASS_REQUIRED");

const auto = controller();
assert.equal(auto.setAutoPlay(true), true);
await auto.jumpToBeat("Z4_S2_08");
await auto.start();
assert.equal(auto.getSnapshot().trackId, "lord_trial");
assert.equal(auto.getSnapshot().lordState, "challenge_entry");
assert.equal(auto.getSnapshot().currentVisualId, "Z4-LORD-01");
assert.equal(auto.getSnapshot().autoPlay, false);
assert.notEqual(auto.getSnapshot().currentVisualId, "Z4-S3-01");
await auto.next();
assert.equal(auto.getSnapshot().lordState, "challenge_domain");
const localeBefore = auto.getSnapshot().lordState;
await auto.setLocale("en-GB");
assert.equal(auto.getSnapshot().lordState, localeBefore);
assert.equal(auto.getSnapshot().locale, "en-GB");

await auto.next();
const replayOne = auto.getSnapshot().replaySignature;
await auto.replayCurrent();
const replayTwo = auto.getSnapshot().replaySignature;
assert.equal(replayTwo, "challenge_active|en-GB|NO_PASS");
assert.equal(replayOne, null);
assert.ok((FakeAudio.maxActiveBySlot.get("voice") || 0) <= 1);
assert.ok((FakeAudio.maxActiveBySlot.get("sfx") || 0) <= 1);

console.log(JSON.stringify({
  status: "PASS",
  checks: 34,
  main_story_order_exact: true,
  lord_assets_in_linear_main: false,
  s2_08_enters_lord: true,
  fail_visual: "Z4-LORD-03",
  pass_visuals: ["Z4-LORD-04", "Z4-LORD-05"],
  pass_to: "Z4_S3_01",
  s3_06_to_lord_auto_advance: false,
  auto_play_stops_at: "Z4-LORD-01",
  max_voice_overlap: FakeAudio.maxActiveBySlot.get("voice") || 0,
  max_sfx_overlap: FakeAudio.maxActiveBySlot.get("sfx") || 0,
}));
