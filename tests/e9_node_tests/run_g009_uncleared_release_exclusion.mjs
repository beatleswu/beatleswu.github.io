import assert from "node:assert/strict";
import { readFile, stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import {
  G009_OWNER_APPROVED_FORMAL_EQUIPMENT_ROWS,
  G009_UNCLEARED_FORMAL_ASSET_RIGHTS,
} from "../../js/g009_owner_approved_formal_equipment_mapping.js";

const root = fileURLToPath(new URL("../../", import.meta.url));
const read = (path) => readFile(resolve(root, path), "utf8");
const schema = JSON.parse(await read("schemas/g009_d007_runtime_prerequisite_v1.json"));
const inventory = JSON.parse(await read("deploy/live-static-asset-inventory.json"));
const dockerfile = await read("Dockerfile");
const app = await read("app.py");
const hero = await read("hero.html");
const d007Bootstrap = await read("js/g009_d007_shared_host_bootstrap.js");
const r2Bootstrap = await read("js/g009_d_r2_shared_host_bootstrap.js");
const buildManifest = await read("deploy/build-manifest.json");
const standalone = "formal_3d_character_equipment_runtime.js";
const formalPrefix = "assets/3d_shop/formal_character_equipment_v1/";

const copySources = [...dockerfile.matchAll(/^COPY\s+(\S+)\s+/gm)].map((match) => match[1]);
const copied = (path) => copySources.some((source) => source === path
  || (source.endsWith("/") && path.startsWith(source)));
const staticFiles = new Set(inventory.eligible_files.entries);
for (const { manifest } of inventory.required_subtrees.entries) {
  const closure = JSON.parse(await read(manifest));
  for (const entry of closure.files) staticFiles.add(entry.path);
}
assert.equal(schema.equipment_catalog.items.length, 12);
assert.equal(schema.equipment_catalog.release_eligibility, "NOT_CLEARED");
assert.equal(G009_OWNER_APPROVED_FORMAL_EQUIPMENT_ROWS.length, 4);
for (const row of G009_OWNER_APPROVED_FORMAL_EQUIPMENT_ROWS) {
  assert.equal(row.rights, G009_UNCLEARED_FORMAL_ASSET_RIGHTS);
  assert.equal(row.rights.RIGHTS_STATUS, "NOT_CLEARED");
  for (const field of ["EQUIP_ENABLED", "SHOP_ENABLED", "PURCHASE_ENABLED", "DROP_ENABLED",
    "PLAYER_SELECTABLE", "RELEASE_ENABLED", "PRODUCTION_ASSET_ADMISSION"]) {
    assert.equal(row.rights[field], false, `${row.asset_id}:${field}`);
  }
}

const rows = [];
for (const item of schema.equipment_catalog.items) {
  const path = item.runtime_asset.replace(/^\//, "");
  assert(path.startsWith(formalPrefix));
  assert.equal(item.release_eligibility, "NOT_CLEARED");
  assert.equal(item.equip_capability, false);
  assert((await stat(resolve(root, path))).isFile(), path);
  assert.equal(staticFiles.has(path), false, `static release includes uncleared ${path}`);
  assert.equal(copied(path), false, `app image includes uncleared ${path}`);
  assert.equal(buildManifest.includes(path), false, `build manifest includes uncleared ${path}`);
  rows.push({ asset_id: item.asset_id, path, repo_present: true,
    source_route_reachable: true, static_package_included: false,
    app_image_included: false, release_manifest_included: false,
    production_served: "NOT_VERIFIED" });
}

// The historical renderer remains source evidence for D007 tests, but has no
// Hero entrypoint/import, Flask route, static membership, or image COPY.
assert.equal(hero.includes(standalone), false);
assert.equal(d007Bootstrap.includes(standalone), false);
assert.equal(r2Bootstrap.includes(standalone), false);
assert.equal(app.includes(standalone), false);
assert.equal(staticFiles.has(`js/${standalone}`), false);
assert.equal(copied(`js/${standalone}`), false);
assert.equal(buildManifest.includes(standalone), false);

// This is deliberately a STOP gate, not a claim that the combined Hero image
// is deployable: the current Dockerfile does not copy the new host/bootstrap
// dependency graph and app.py has no explicit routes for those modules.
assert.equal(copied("js/g009_shared_hero_attachment_host.js"), false);
assert.equal(app.includes("@app.route('/js/g009_shared_hero_attachment_host.js')"), false);
assert.equal(hero.includes("/js/g009_d007_shared_host_bootstrap.js"), true);
assert.equal(hero.includes("/js/g009_d_r2_shared_host_bootstrap.js"), true);
console.log(JSON.stringify({ result: "PASS", scope: "source-release-boundary-only",
  uncleared_assets: rows, standalone_runtime_reference_count: 0,
  combined_release: "STOP_UNTIL_RIGHTS_AND_ROUTE_COPY_CLOSURE",
  production_served: "NOT_VERIFIED" }));
