import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  G009_FORMAL9_REPLACEMENT_AUTHORITY,
  G009_FORMAL9_REPLACEMENT_ROWS,
  G009_FORMAL9_RETIRED_ASSET_IDS,
  G009_RIGHTS_CLEARED_FORMAL_ASSET_RIGHTS,
  G009_RIGHTS_CLEARED_RELEASE_NOT_ADMITTED,
  g009Formal9ReplacementRowForAsset,
  isG009RetiredFormalAssetId,
} from "../../js/g009_formal9_rights_cleared_replacement_catalog.js";

const root = fileURLToPath(new URL("../../", import.meta.url));
const PROV = "provenance/g009_formal9_rights_cleared_v1/";
const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
const read = (path) => readFile(resolve(root, path));

const EXPECTED = {
  iron_sword: ["WEAPON_C43E15596CA6", "ONE_HAND", 2.25],
  fox_fang: ["WEAPON_6F06505A7BED", "KNIFE_SMALL", 1.58],
  riverstone_sabre: ["WEAPON_EC86CE30E759", "ONE_HAND", 2.25],
  bamboo_shadow_blade: ["WEAPON_C84A8635BED2", "ONE_HAND", 2.25],
};

function parseGlb(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  assert.equal(view.getUint32(0, true), 0x46546c67, "GLB magic");
  assert.equal(view.getUint32(4, true), 2, "GLB container version 2");
  assert.equal(view.getUint32(8, true), bytes.byteLength, "GLB declared length");
  const jsonLength = view.getUint32(12, true);
  assert.equal(view.getUint32(16, true), 0x4e4f534a, "first chunk is JSON");
  const json = JSON.parse(new TextDecoder().decode(bytes.subarray(20, 20 + jsonLength)));
  const binOffset = 20 + jsonLength;
  assert.equal(view.getUint32(binOffset + 4, true), 0x004e4942, "second chunk is BIN");
  return json;
}

function isIdentityNode(node) {
  return !node.matrix && !node.rotation && !node.scale
    && (!node.translation || node.translation.every((value) => value === 0));
}

// 1. Catalog rows, IDs, and final bytes.
assert.equal(G009_FORMAL9_REPLACEMENT_ROWS.length, 4);
for (const row of G009_FORMAL9_REPLACEMENT_ROWS) {
  const [assetId, presentationClass, roleLength] = EXPECTED[row.server_item_id];
  assert.equal(row.asset_id, assetId);
  assert.equal(row.presentation_class, presentationClass);
  assert.equal(row.slot, "MAIN_HAND");
  assert.equal(row.socket, "hand.R");
  assert.equal(row.equip_capability, false);
  assert.equal(row.release_eligibility, G009_RIGHTS_CLEARED_RELEASE_NOT_ADMITTED);
  assert.equal(row.rights, G009_RIGHTS_CLEARED_FORMAL_ASSET_RIGHTS);
  assert(!isG009RetiredFormalAssetId(row.asset_id));
  assert.equal(g009Formal9ReplacementRowForAsset(row.asset_id), row);
  assert(row.runtime_asset.startsWith("/assets/3d_shop/formal9_rights_cleared_v1/weapons/"));
  const bytes = await read(row.runtime_asset.slice(1));
  const digest = sha256(bytes);
  assert.equal(digest, row.runtime_sha256, row.server_item_id + " GLB_VALID: bytes match bound SHA-256");
  assert.equal("WEAPON_" + digest.slice(0, 12).toUpperCase(), row.asset_id, "asset ID binds to final GLB hash");

  // 2. STRUCTURE_VALID / MATERIAL_VALID
  const gltf = parseGlb(bytes);
  assert.equal(gltf.asset?.version, "2.0");
  assert.deepEqual(gltf.extensionsRequired || [], []);
  assert.equal((gltf.cameras || []).length, 0);
  assert.equal((gltf.skins || []).length, 0);
  assert.equal((gltf.animations || []).length, 0);
  assert.equal((gltf.buffers || []).filter((buffer) => buffer.uri).length, 0, "no external buffers");
  assert.equal((gltf.images || []).filter((image) => image.uri).length, 0, "no external images");
  assert((gltf.meshes || []).length > 0);
  for (const mesh of gltf.meshes) {
    for (const primitive of mesh.primitives) {
      assert(Number.isInteger(primitive.material), "every primitive has a material");
      assert(gltf.materials[primitive.material], "material index resolves");
    }
  }
  for (const texture of gltf.textures || []) {
    assert(Number.isInteger(gltf.images[texture.source].bufferView), "texture image is embedded");
  }

  // 3. EXPECTED_ORIENTATION / EXPECTED_SCALE (mesh nodes carry no transforms).
  assert(gltf.nodes.every(isIdentityNode), "normalization is baked into vertices");
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (const mesh of gltf.meshes) {
    for (const primitive of mesh.primitives) {
      const accessor = gltf.accessors[primitive.attributes.POSITION];
      for (let axis = 0; axis < 3; axis += 1) {
        min[axis] = Math.min(min[axis], accessor.min[axis]);
        max[axis] = Math.max(max[axis], accessor.max[axis]);
      }
    }
  }
  const size = max.map((value, axis) => value - min[axis]);
  assert(size[1] > size[0] && size[1] > size[2], row.server_item_id + " blade axis is +Y");
  assert(Math.abs(size[1] - roleLength) < 0.01, row.server_item_id + " role length " + roleLength);
  assert(min[1] < 0 && max[1] > 0 && max[1] > -min[1], row.server_item_id + " grip origin sits below the blade");
  assert(Math.abs(min[0] + max[0]) < 1e-3 && Math.abs(min[2] + max[2]) < 1e-3, "centered on blade axis");
}

// 4. Retired visuals never alias to replacement bytes.
assert.deepEqual([...G009_FORMAL9_RETIRED_ASSET_IDS].sort(),
  ["WEAPON_2F4CB085CE4A", "WEAPON_9CD401DADF4C", "WEAPON_A70FD7AB666C", "WEAPON_A7C05D43F943"]);
for (const retired of G009_FORMAL9_RETIRED_ASSET_IDS) {
  assert.equal(g009Formal9ReplacementRowForAsset(retired), null);
}

// 5. Schema mirror equals the module.
const schema = JSON.parse(await read("schemas/g009_formal9_rights_cleared_replacement_v1.json"));
assert.equal(schema.contract_version, "GO_ODYSSEY_G009_FORMAL9_RIGHTS_CLEARED_REPLACEMENT_V1");
assert.deepEqual(schema.items, JSON.parse(JSON.stringify(G009_FORMAL9_REPLACEMENT_ROWS)));
assert.deepEqual(schema.retired_asset_ids, [...G009_FORMAL9_RETIRED_ASSET_IDS]);
assert.deepEqual(schema.authority, { ...G009_FORMAL9_REPLACEMENT_AUTHORITY });
assert.deepEqual(schema.intentionally_unmapped_item_ids,
  ["dragon_claw", "celestial_blade", "moonstar_rapier", "emberline_cutlass", "starglass_needle"]);

// 6. Durable provenance: every recorded file hash, lineage, licenses, Owner receipt.
const sums = (await read(PROV + "SHA256SUMS.txt")).toString("utf8").trim().split("\n");
assert(sums.length >= 30);
for (const line of sums) {
  const [digest, path] = [line.slice(0, 64), line.slice(66)];
  assert.equal(sha256(await read(path)), digest, "provenance hash " + path);
}
const manifest = JSON.parse(await read(PROV + "final_asset_manifest.json"));
for (const asset of manifest.assets) {
  const row = G009_FORMAL9_REPLACEMENT_ROWS.find((entry) => entry.server_item_id === asset.GAME_ITEM_KEY);
  assert.deepEqual(asset.lineage, [row.server_item_id, row.asset_id, row.runtime_sha256]);
  assert.equal(asset.RIGHTS_STATUS, "RIGHTS_CLEARED");
  assert.equal(asset.OWNER_SELECTED, "YES");
  for (const field of ["PRIMARY_LICENSE_FILE_PRESENT", "PRIMARY_LICENSE_RETAINED", "COMMERCIAL_USE_ALLOWED",
    "MODIFICATION_ALLOWED", "GAME_DISTRIBUTION_ALLOWED"]) assert.equal(asset[field], "YES");
  const license = (await read(asset.PRIMARY_LICENSE_FILE)).toString("utf8");
  assert.equal(sha256(await read(asset.PRIMARY_LICENSE_FILE)), asset.PRIMARY_LICENSE_SHA256);
  assert(license.includes("Creative Commons Zero, CC0"));
  assert(license.includes("http://creativecommons.org/publicdomain/zero/1.0/"));
  assert.equal(sha256(await read(asset.SOURCE_ARCHIVE)), asset.SOURCE_ARCHIVE_SHA256);
}
const receipt = JSON.parse(await read(PROV + "owner_selection_receipt.json"));
assert.equal(receipt.OWNER_SELECTION_4_OF_4, "YES");
assert.deepEqual(receipt.selections, {
  IRON_SWORD_SELECTED: "TMP_IRON_SWORD_A",
  FOX_FANG_SELECTED: "TMP_FOX_FANG_A",
  RIVERSTONE_SABRE_SELECTED: "TMP_RIVERSTONE_SABRE_B",
  BAMBOO_SHADOW_BLADE_SELECTED: "TMP_BAMBOO_SHADOW_BLADE_A",
});
assert.equal(receipt.substitution, "NONE");
const retirement = JSON.parse(await read(PROV + "old_asset_retirement_map.json"));
assert.equal(retirement.retired.length, 4);
for (const entry of retirement.retired) {
  assert.equal(entry.alias_to_new_bytes, false);
  assert.equal(entry.status, "RETIRED_HISTORICAL_ONLY");
  assert(G009_FORMAL9_RETIRED_ASSET_IDS.includes(entry.old_asset_id));
}

console.log("FORMAL9_REPLACEMENT_IDS=4/4 bound to final GLB SHA-256");
console.log("GLB_VALID=PASS; STRUCTURE_VALID=PASS; MATERIAL_VALID=PASS");
console.log("EXPECTED_ORIENTATION=PASS (+Y blade); EXPECTED_SCALE=PASS (sword 2.25 / dagger 1.58)");
console.log("SCHEMA_MIRROR=PASS; RETIRED_NO_ALIAS=PASS");
console.log("PROVENANCE_HASHES=" + sums.length + "/" + sums.length + " PASS; OWNER_RECEIPT=4/4");
