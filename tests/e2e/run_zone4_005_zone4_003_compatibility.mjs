import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..", "..");
const parent = "530271be4f3720e15e52e4b1e1796db3cd5df514";
const legacyMatrix = JSON.parse(execFileSync(
  "git",
  ["show", `${parent}:ZONE4_STORY_BEAT_BINDING_MATRIX.json`],
  { cwd: root, encoding: "utf8" },
));
const require = createRequire(import.meta.url);
const runtime = require(path.join(root, "js", "e10", "zone4_owner_story_runtime.js"));

class FakeAudio {
  static active = new Map();
  static maxActive = new Map();

  constructor(src, meta) {
    this.src = src;
    this.meta = meta || {};
    this.paused = true;
    this.loop = false;
    this.currentTime = 0;
    this.listeners = new Map();
  }

  addEventListener(name, handler) {
    if (!this.listeners.has(name)) this.listeners.set(name, new Set());
    this.listeners.get(name).add(handler);
  }

  removeEventListener(name, handler) {
    this.listeners.get(name)?.delete(handler);
  }

  play() {
    this.paused = false;
    const slot = this.meta.slot || "unknown";
    if (!FakeAudio.active.has(slot)) FakeAudio.active.set(slot, new Set());
    const active = FakeAudio.active.get(slot);
    active.add(this);
    FakeAudio.maxActive.set(slot, Math.max(FakeAudio.maxActive.get(slot) || 0, active.size));
    if (!this.loop) setImmediate(() => {
      if (!this.paused) {
        for (const handler of this.listeners.get("ended") || []) handler();
        active.delete(this);
      }
    });
    return Promise.resolve();
  }

  pause() {
    this.paused = true;
    FakeAudio.active.get(this.meta.slot || "unknown")?.delete(this);
  }
}

function controller() {
  return runtime.create({
    matrix: legacyMatrix,
    document: null,
    audioFactory: (src, meta) => new FakeAudio(src, meta),
  });
}

const flow = controller();
await flow.start();
assert.equal(flow.getSnapshot().beatId, "Z4_S1_01");
assert.equal(await flow.setLocale("en-GB"), true);
assert.equal(await flow.jumpToBeat("Z4_S2_06"), true);
await flow.replayCurrent();
const replayOne = flow.getSnapshot().replaySignature;
await flow.replayCurrent();
assert.equal(flow.getSnapshot().replaySignature, replayOne);
assert.equal(replayOne, "Z4_S2_06|en-GB");
assert.equal(await flow.setTrack("lord_review"), true);
assert.equal(flow.getSnapshot().beatId, "Z4_LORD_01");
assert.equal(flow.setAutoPlay(true), false);
assert.equal(flow.getSnapshot().autoPlay, false);
assert.ok(flow.getEventCuesForCurrentBeat().length >= 1);
assert.equal(await flow.setTrack("main_story"), true);
assert.equal(flow.getSnapshot().beatId, "Z4_S1_01");
assert.equal(flow.pause(), true);
assert.equal(flow.getSnapshot().paused, true);

const autoplay = controller();
assert.equal(autoplay.setAutoPlay(true), true);
await autoplay.start();
assert.equal(autoplay.getSnapshot().beatId, "Z4_S3_06");
assert.equal(autoplay.getSnapshot().trackId, "main_story");
assert.ok((FakeAudio.maxActive.get("voice") || 0) <= 1);

console.log(JSON.stringify({
  status: "PASS",
  legacy_matrix_source: parent,
  replay_compatibility: true,
  legacy_lord_review_alias: true,
  legacy_autoplay_terminal: "Z4_S3_06",
  max_voice_overlap: FakeAudio.maxActive.get("voice") || 0,
}));
