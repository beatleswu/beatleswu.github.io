import * as THREE from "/assets/3d_shop/p048/vendor/three.module.js";
import { GLTFLoader } from "/assets/3d_shop/p048/vendor/jsm/loaders/GLTFLoader.js";
import { resolveG009OwnerApprovedRuntimeEquipmentIdentity } from "./g009_owner_approved_formal_equipment_mapping.js";
import { projectServerEquippedHandItems } from "./g009_equipment_inventory_projection.js";
import { createHeroEquipmentAttachmentAdapter } from "./hero_equipment_attachment_adapter.js";
import { G009_D007_AUTHORITY_READY } from "./g009_d007_shared_host_bootstrap.js";
import {
  G009_RIGHTS_CLEARED_RELEASE_NOT_ADMITTED,
  g009Formal9ReplacementRowForAsset,
  isG009RetiredFormalAssetId,
} from "./g009_formal9_rights_cleared_replacement_catalog.js";
import {
  registerHeroPresentationResolver,
  registerHeroPresentationRehydrator,
} from "./g008_future30_hero_renderer.js";

const HAND_SLOTS = Object.freeze(["MAIN_HAND", "OFF_HAND"]);
// Wooden Sword keeps its D007 NOT_CLEARED row; the formal9 replacements are
// rights-cleared but not release-admitted. Anything else fails closed.
const PRESENTABLE_RELEASE_STATES = Object.freeze(new Set(["NOT_CLEARED", G009_RIGHTS_CLEARED_RELEASE_NOT_ADMITTED]));

async function sha256(bytes) {
  if (!globalThis.crypto?.subtle) throw new Error("equipment_webcrypto_unavailable");
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
}

function presentationDescriptorFor(index, itemId, requestedSlot) {
  const row = resolveG009OwnerApprovedRuntimeEquipmentIdentity(index, itemId, requestedSlot);
  if (!row || row.server_item_id !== itemId || row.slot !== requestedSlot
    || isG009RetiredFormalAssetId(row.asset_id)
    || row.equip_capability !== false || !PRESENTABLE_RELEASE_STATES.has(row.release_eligibility)) {
    return null;
  }
  return Object.freeze({
    ...row,
    presentation_id: row.asset_id,
    slot: row.slot,
  });
}

async function registerEquipmentAdapter() {
  const { equipmentIndex } = await G009_D007_AUTHORITY_READY;
  const resolvers = new Map(HAND_SLOTS.map((slot) => [slot, (presentationId) => {
    const row = indexRowForPresentation(equipmentIndex, presentationId, slot);
    return row;
  }]));
  for (const [slot, resolver] of resolvers) registerHeroPresentationResolver(slot, resolver);

  const activeByGeneration = new Map();
  registerHeroPresentationRehydrator("G009_D_R2_SERVER_EQUIPPED_HANDS", async ({ appearance, host, generation }) => {
    if (activeByGeneration.has(generation)) return activeByGeneration.get(generation);
    const adapter = createHeroEquipmentAttachmentAdapter({ getHeroSharedAttachmentHost: () => host }, {
      loadPresentation: loadEquipmentPresentation,
    });
    const pending = applyServerInventoryProjection(adapter, appearance);
    activeByGeneration.set(generation, pending);
    try {
      return await pending;
    } finally {
      if (activeByGeneration.get(generation) === pending) activeByGeneration.delete(generation);
    }
  });
}

function indexRowForPresentation(index, presentationId, slot) {
  if (isG009RetiredFormalAssetId(presentationId)) return null;
  const replacement = g009Formal9ReplacementRowForAsset(presentationId);
  if (replacement) {
    if (replacement.slot !== slot || replacement.equip_capability !== false
      || replacement.release_eligibility !== G009_RIGHTS_CLEARED_RELEASE_NOT_ADMITTED) return null;
    return Object.freeze({ ...replacement, presentation_id: replacement.asset_id, slot: replacement.slot });
  }
  const byAssetId = index?.byAssetId;
  if (!(byAssetId instanceof Map)) return null;
  const source = byAssetId.get(presentationId);
  if (!source || source.item_mapping_status !== "CURRENT_SERVER_ID"
    || source.slot !== slot || source.equip_capability !== false
    || source.release_eligibility !== "NOT_CLEARED") return null;
  return Object.freeze({ ...source, presentation_id: source.asset_id, slot: source.slot });
}

async function loadEquipmentPresentation(descriptor) {
  const response = await fetch(descriptor.runtime_asset, {
    credentials: "same-origin", cache: "no-store",
  });
  if (!response.ok) throw new Error("equipment_asset_http_failure:" + descriptor.presentation_id);
  const bytes = await response.arrayBuffer();
  if (await sha256(bytes) !== descriptor.runtime_sha256) {
    throw new Error("equipment_asset_sha256_mismatch:" + descriptor.presentation_id);
  }
  const gltf = await new GLTFLoader().parseAsync(
    bytes,
    new URL(descriptor.runtime_asset, globalThis.location?.href || document.baseURI).href,
  );
  const root = gltf?.scene || gltf?.scenes?.[0];
  if (!root?.isObject3D) throw new Error("equipment_asset_scene_missing:" + descriptor.presentation_id);
  if (![descriptor.position, descriptor.rotation, descriptor.scale].every((values) =>
    Array.isArray(values) && values.length === 3 && values.every((value) => Number.isFinite(Number(value))))) {
    throw new Error("equipment_asset_transform_invalid:" + descriptor.presentation_id);
  }
  root.position.fromArray(descriptor.position.map(Number));
  root.rotation.fromArray(descriptor.rotation.map(Number));
  root.scale.fromArray(descriptor.scale.map(Number));
  root.name = "G009_EQUIPMENT_" + descriptor.presentation_id;
  root.userData = {
    ...(root.userData || {}),
    attachment_slot: descriptor.slot,
    server_item_id: descriptor.server_item_id,
    asset_id: descriptor.asset_id,
    runtime_sha256: descriptor.runtime_sha256,
    authority_route: "server:/api/player/inventory + " + (descriptor.visual_authority_route || "G009_D007_CURRENT_SERVER_ID"),
  };
  root.traverse?.((node) => {
    if (!node.isMesh) return;
    const materials = Array.isArray(node.material) ? node.material : [node.material];
    materials.filter(Boolean).forEach((material) => {
      material.side = THREE.DoubleSide;
      material.needsUpdate = true;
    });
  });
  return root;
}

async function applyServerInventoryProjection(adapter, appearance) {
  try {
    const response = await fetch("/api/player/inventory", {
      credentials: "include", cache: "no-store",
    });
    if (!response.ok) throw new Error("player_inventory_http_failure:" + response.status);
    const inventory = await response.json();
    const { equipmentIndex } = await G009_D007_AUTHORITY_READY;
    const projection = projectServerEquippedHandItems(inventory, (itemId, slot) =>
      presentationDescriptorFor(equipmentIndex, itemId, slot));
    const results = [];
    for (const selection of projection.slots) {
      if (selection.status !== "resolved") {
        results.push({ ...adapter.detach(selection.slot), reason: selection.reason || selection.status });
        continue;
      }
      results.push(await adapter.setHand(selection.slot, selection.descriptor, appearance));
    }
    return {
      status: projection.status,
      slots: results,
      equipped_state_authority: "server:/api/player/inventory",
      character_authority: "player_appearance.character_key",
      equip_capability: false,
      release_eligibility: "NOT_CLEARED",
    };
  } catch (error) {
    const slots = await Promise.all(HAND_SLOTS.map(async (slot) => {
      try { return adapter.detach(slot); }
      catch (_) { return { status: "failed_closed", slot }; }
    }));
    return {
      status: "failed_closed",
      reason: error instanceof Error ? error.message : String(error),
      slots,
      equipped_state_authority: "server:/api/player/inventory",
      character_authority: "player_appearance.character_key",
      equip_capability: false,
      release_eligibility: "NOT_CLEARED",
    };
  }
}

void registerEquipmentAdapter().catch((error) => {
  console.warn("Hero equipment presentation remains fail-closed", error instanceof Error ? error.message : String(error));
});
