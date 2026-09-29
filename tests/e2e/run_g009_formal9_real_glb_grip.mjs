// Isolated real-GLB WebGL regression. This is not authenticated or Owner visual acceptance.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright-core");
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const fixture = path.join(root, "tests/e2e/fixtures/g009_formal9_real_glb_grip.html");
const catalog = JSON.parse(await readFile(path.join(root,
  "schemas/future30_c005_real_asset_runtime_mapping_manifest.json"), "utf8"));
const replacements = JSON.parse(await readFile(path.join(root,
  "provenance/g009_formal9_rights_cleared_v1/final_asset_manifest.json"), "utf8"));

function browserExecutable() {
  const candidates = [
    process.env.CHROME_BIN,
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  ].filter(Boolean);
  const found = candidates.find((candidate) => existsSync(candidate));
  if (!found) throw new Error("Chrome/Edge unavailable; set CHROME_BIN");
  return found;
}

for (const key of ["A1", "A3"]) {
  const row = catalog.visual_models.find((entry) => entry.character_id === key && entry.variant === "RED");
  assert(row, key + " accepted runtime visual missing");
  const bytes = await readFile(path.join(root, row.runtime_glb));
  assert.equal(createHash("sha256").update(bytes).digest("hex"), row.runtime_sha256, key + " GLB bytes");
}
assert.equal(replacements.assets.length, 4);
for (const entry of replacements.assets) {
  const bytes = await readFile(path.join(root, entry.FINAL_GLB));
  assert.equal(createHash("sha256").update(bytes).digest("hex"), entry.FINAL_GLB_SHA256);
}

const allowedPrefixes = [
  "assets/3d_shop/p048/vendor/",
  "assets/3d_shop/p048/hero/",
  "assets/3d_shop/p048/future30/c005/",
  "assets/3d_shop/formal9_rights_cleared_v1/weapons/",
];
const allowedModules = new Set([
  "js/g009_shared_hero_attachment_host.js",
  "js/g009_formal9_rights_cleared_replacement_catalog.js",
  "js/hero_equipment_attachment_adapter.js",
]);
const server = createServer(async (request, response) => {
  try {
    const relative = decodeURIComponent(new URL(request.url, "http://127.0.0.1").pathname).replace(/^\/+/, "");
    const source = relative === ""
      ? fixture
      : allowedPrefixes.some((prefix) => relative.startsWith(prefix)) || allowedModules.has(relative)
        ? path.resolve(root, relative)
        : null;
    if (!source || (!source.startsWith(root + path.sep) && source !== fixture)) {
      response.writeHead(404).end();
      return;
    }
    const bytes = await readFile(source);
    const type = source.endsWith(".html") ? "text/html; charset=utf-8"
      : source.endsWith(".js") ? "text/javascript; charset=utf-8"
        : source.endsWith(".glb") ? "model/gltf-binary" : "application/octet-stream";
    response.writeHead(200, { "Content-Type": type, "Cache-Control": "no-store" }).end(bytes);
  } catch (error) {
    response.writeHead(404).end(String(error));
  }
});

const evidenceDir = process.env.G009_GRIP_EVIDENCE_DIR
  ? path.resolve(process.env.G009_GRIP_EVIDENCE_DIR)
  : await mkdtemp(path.join(tmpdir(), "g009-formal9-real-grip-"));
if (process.env.G009_GRIP_EVIDENCE_DIR && !existsSync(evidenceDir)) {
  throw new Error("G009_GRIP_EVIDENCE_DIR must exist before the test runs");
}

let browser = null;
try {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({ headless: true, executablePath: browserExecutable(),
    args: ["--use-angle=d3d11"] });
  const page = await browser.newPage({ viewport: { width: 640, height: 720 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(origin, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.__g009RealGripReady === true);

  const cases = [];
  const screenshots = [];
  const heroInfo = [];
  for (const characterKey of ["A1", "A3"]) {
    const hero = catalog.visual_models.find((entry) => entry.character_id === characterKey && entry.variant === "RED");
    const info = await page.evaluate((value) => window.startHero(value),
      { characterKey, heroPath: `/${hero.runtime_glb}` });
    heroInfo.push(info);
    assert.equal(info.liveRenderers, 1);
    assert.equal(info.maxRenderers, 1);
    assert.equal(info.heroMeshCount, 1);
    const poses = characterKey === "A1" ? ["DEFAULT", "A1_CORRECT_MID"]
      : ["DEFAULT", "A3_RAISED_ARM"];
    for (const pose of poses) {
      await page.evaluate((value) => window.setGripPose(value), pose);
      for (const asset of replacements.assets) {
        const metric = await page.evaluate((value) => window.attachRealWeapon(value), asset.NEW_ASSET_ID);
        cases.push({ pose, ...metric });
        assert.equal(metric.attachStatus, "attached");
        assert.match(metric.mainAnchorSource, /^HAND_BONE:/);
        assert.match(metric.offAnchorSource, /^HAND_BONE:/);
        assert(metric.mainBoneMatrixDelta < 1e-3, `${characterKey}/${pose}/${asset.NEW_ASSET_ID}: MAIN_HAND drift`);
        assert(metric.offBoneMatrixDelta < 1e-3, `${characterKey}/${pose}/${asset.NEW_ASSET_ID}: OFF_HAND drift`);
        assert(metric.handOriginRatio < 0.15, `${characterKey}/${pose}/${asset.NEW_ASSET_ID}: grip detached`);
        assert(metric.centerHandRatio < 0.35, `${characterKey}/${pose}/${asset.NEW_ASSET_ID}: asset beside hero`);
        assert(metric.maxWeaponDimensionRatio < 0.8, `${characterKey}/${pose}/${asset.NEW_ASSET_ID}: bbox scale`);
        assert.equal(metric.intersectsExpandedHero, true, `${characterKey}/${pose}/${asset.NEW_ASSET_ID}: bbox separated`);
        assert.equal(metric.bboxEmpty, false);
        assert.equal(metric.mainChildCount, 1);
        assert.equal(metric.offChildCount, 1);
        assert.equal(metric.liveRenderers, 1);
        assert.equal(metric.maxRenderers, 1);
        if ((characterKey === "A1" && pose === "A1_CORRECT_MID" && asset.GAME_ITEM_KEY === "iron_sword")
          || (characterKey === "A3" && pose === "A3_RAISED_ARM" && asset.GAME_ITEM_KEY === "bamboo_shadow_blade")) {
          const screenshot = path.join(evidenceDir, `${characterKey}-${pose}-${asset.GAME_ITEM_KEY}.png`);
          await page.locator("canvas").screenshot({ path: screenshot });
          screenshots.push(screenshot);
        }
      }
    }
  }
  assert.deepEqual(errors, [], "browser page errors");
  const closed = await page.evaluate(() => window.closeGripScene());
  assert.equal(closed.liveRenderers, 0);
  assert.equal(closed.maxRenderers, 1);
  const output = { result: "PASS", scope: "isolated-real-GLB-WebGL-not-authenticated",
    cases: cases.length, characterKeys: ["A1", "A3"], realPoses: ["A1_CORRECT_MID", "A3_RAISED_ARM"],
    weapons: replacements.assets.map((entry) => entry.NEW_ASSET_ID), heroInfo, metrics: cases,
    screenshots, browserErrors: errors, singleRendererMaximum: closed.maxRenderers };
  const jsonPath = path.join(evidenceDir, "g009-formal9-real-glb-grip.json");
  await writeFile(jsonPath, JSON.stringify(output, null, 2) + "\n");
  console.log(JSON.stringify({ result: output.result, scope: output.scope, cases: output.cases,
    renderer: heroInfo.map((entry) => `${entry.characterKey}:${entry.glRenderer}`),
    screenshots, evidenceJson: jsonPath, singleRendererMaximum: closed.maxRenderers }));
} finally {
  await browser?.close();
  await new Promise((resolve) => server.close(resolve));
}
