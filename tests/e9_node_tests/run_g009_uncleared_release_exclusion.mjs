import assert from "node:assert/strict";
import { readFile, stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import {
  G009_OWNER_APPROVED_FORMAL_EQUIPMENT_ROWS,
  G009_RIGHTS_CLEARED_FORMAL_ASSET_RIGHTS,
  resolveG009OwnerApprovedRuntimeEquipmentIdentity,
} from "../../js/g009_owner_approved_formal_equipment_mapping.js";
import {
  createG009RuntimeEquipmentIndex,
  resolveG009RuntimeEquipmentIdentity,
} from "../../js/g009_d007_runtime_identity_resolver.mjs";
import {
  G009_FORMAL9_REPLACEMENT_ROWS,
  G009_FORMAL9_RETIRED_ASSET_IDS,
} from "../../js/g009_formal9_rights_cleared_replacement_catalog.js";

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
const serviceWorker = await read("sw.js");
const standalone = "formal_3d_character_equipment_runtime.js";
const formalPrefix = "assets/3d_shop/formal_character_equipment_v1/";

const copySources = dockerfile.replace(/\\\r?\n/g, " ").split(/\r?\n/)
  .filter(line => line.startsWith("COPY "))
  .flatMap(line => line.trim().split(/\s+/).slice(1, -1));
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
// Formal9 rows now bind the Owner-selected rights-cleared replacements. Rights
// clearance is not release admission: every product/release flag stays closed.
for (const row of G009_OWNER_APPROVED_FORMAL_EQUIPMENT_ROWS) {
  assert.equal(row.rights, G009_RIGHTS_CLEARED_FORMAL_ASSET_RIGHTS);
  assert.equal(row.rights.RIGHTS_STATUS, "RIGHTS_CLEARED");
  assert(!G009_FORMAL9_RETIRED_ASSET_IDS.includes(row.asset_id));
  for (const field of ["EQUIP_ENABLED", "SHOP_ENABLED", "PURCHASE_ENABLED", "DROP_ENABLED",
    "PLAYER_SELECTABLE", "RELEASE_ENABLED", "PRODUCTION_ASSET_ADMISSION"]) {
    assert.equal(row.rights[field], false, `${row.asset_id}:${field}`);
  }
}

const rows = [];
const admittedPreviewRows = [];
for (const item of schema.equipment_catalog.items) {
  const path = item.runtime_asset.replace(/^\//, "");
  assert(path.startsWith(formalPrefix));
  assert.equal(item.release_eligibility, "NOT_CLEARED");
  assert.equal(item.equip_capability, false);
  assert((await stat(resolve(root, path))).isFile(), path);
  if (G009_FORMAL9_RETIRED_ASSET_IDS.includes(item.asset_id)) {
    assert.equal(staticFiles.has(path), false, `static release includes retired ${path}`);
    assert.equal(copied(path), false, `app image includes retired ${path}`);
    assert.equal(buildManifest.includes(path), false, `build manifest includes retired ${path}`);
    rows.push({ asset_id: item.asset_id, path, repo_present: true,
      source_route_reachable: true, static_package_included: false,
      app_image_included: false, release_manifest_included: false,
      production_served: "NOT_VERIFIED" });
  } else {
    // The eight non-retired D007 rows remain NOT_CLEARED preview bytes in the
    // accepted runtime closure. Packaging is not release/equip admission.
    assert.equal(staticFiles.has(path), false, `preview bytes entered static release ${path}`);
    assert.equal(copied(path), true, `preview image omits ${path}`);
    assert.equal(buildManifest.includes(path), true, `preview build omits ${path}`);
    admittedPreviewRows.push({ asset_id: item.asset_id, path,
      release_eligibility: item.release_eligibility, equip_capability: false,
      production_served: "NOT_VERIFIED" });
  }
}

// Retired formal9 visuals: historical bytes only. Not in the active mapping,
// any active resolver, legacy alias/fallback, Service Worker, static package,
// app image, or build/release manifest.
const d007Index = createG009RuntimeEquipmentIndex(schema);
const retired = [];
for (const assetId of G009_FORMAL9_RETIRED_ASSET_IDS) {
  const row = schema.equipment_catalog.items.find((item) => item.asset_id === assetId);
  assert(row, `retired asset stays historically traceable: ${assetId}`);
  const path = row.runtime_asset.replace(/^\//, "");
  assert.equal(G009_OWNER_APPROVED_FORMAL_EQUIPMENT_ROWS.some((entry) => entry.asset_id === assetId), false);
  assert.equal(resolveG009RuntimeEquipmentIdentity(d007Index, assetId), null, `active resolver: ${assetId}`);
  assert.equal(resolveG009RuntimeEquipmentIdentity(d007Index, row.server_item_id || "", { allowAssetId: false }), null,
    `legacy candidate alias: ${row.server_item_id}`);
  for (const slot of ["MAIN_HAND", "OFF_HAND"]) {
    assert.equal(resolveG009OwnerApprovedRuntimeEquipmentIdentity(d007Index, assetId, slot), null, `formal alias: ${assetId}`);
  }
  assert.equal(serviceWorker.includes(path) || serviceWorker.includes(assetId), false, `Service Worker precache: ${path}`);
  assert.equal(staticFiles.has(path), false);
  assert.equal(copied(path), false);
  assert.equal(buildManifest.includes(path), false);
  retired.push({ asset_id: assetId, path, active_mapping: false, runtime_reachable: false,
    legacy_alias: false, service_worker_precache: false, static_package_included: false,
    app_image_included: false, release_manifest_included: false, production_admission: false });
}

// The four selected replacement bytes are now declared for the isolated
// image/static package candidate. Product and Production admission stay false.
const replacements = [];
for (const row of G009_FORMAL9_REPLACEMENT_ROWS) {
  const path = row.runtime_asset.replace(/^\//, "");
  assert((await stat(resolve(root, path))).isFile(), path);
  assert.equal(staticFiles.has(path), true, `static candidate omits ${path}`);
  assert.equal(copied(path), true, `image candidate omits ${path}`);
  assert.equal(buildManifest.includes(path), true, `build manifest omits ${path}`);
  assert.equal(serviceWorker.includes(path), false);
  assert.equal(row.rights.RELEASE_ENABLED, false);
  assert.equal(row.rights.PRODUCTION_ASSET_ADMISSION, false);
  replacements.push({ asset_id: row.asset_id, path, rights_status: row.rights.RIGHTS_STATUS,
    release_eligibility: row.release_eligibility, static_candidate_included: true,
    image_candidate_included: true, product_release_admission: false,
    production_served: "NOT_VERIFIED" });
}

// The historical standalone renderer has no Hero entrypoint/import. The
// accepted Phase 3A successor explicitly packages the Formal9 runtime module
// behind the narrow allowlist route and closure manifests.
assert.equal(hero.includes(standalone), false);
assert.equal(d007Bootstrap.includes(standalone), false);
assert.equal(r2Bootstrap.includes(standalone), false);
assert.equal(app.includes(standalone), true);
assert.equal(staticFiles.has(`js/${standalone}`), true);
assert.equal(copied(`js/${standalone}`), true);
assert.equal(buildManifest.includes(standalone), true);

// The Phase 3A successor closes the accepted Hero/shared-host dependency
// graph in the image and through the narrow allowlist route. This is still a
// source/package check only; it does not claim browser or Production acceptance.
assert.equal(copied("js/g009_shared_hero_attachment_host.js"), true);
assert.equal(app.includes("@app.route('/js/<string:filename>')"), true);
assert.equal(hero.includes("/js/g009_d007_shared_host_bootstrap.js"), true);
assert.equal(hero.includes("/js/g009_d_r2_shared_host_bootstrap.js"), true);
console.log(JSON.stringify({ result: "PASS", scope: "source-release-boundary-only",
  uncleared_assets: rows, admitted_preview_assets: admittedPreviewRows,
  retired_formal9_assets: retired, rights_cleared_replacements: replacements,
  standalone_runtime_reference_count: 0,
  combined_release: "STOP_UNTIL_PRODUCT_RELEASE_AND_ROUTE_COPY_CLOSURE",
  production_served: "NOT_VERIFIED" }));
