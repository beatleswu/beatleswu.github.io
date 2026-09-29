import { createG009RuntimeEquipmentIndex } from "./g009_d007_runtime_identity_resolver.mjs";

export const G009_D007_HERO_ADAPTER_CONTRACT = "G009_D007_R1_SHARED_HERO_HOST_V1";
export const G009_D007_APPEARANCE_SLOTS = Object.freeze(["HEAD", "BACK", "AURA"]);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function plainRecord(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function normalizeAssetPath(value) {
  return typeof value === "string" ? value.replace(/^\/+/, "") : "";
}

function digestHex(bytes) {
  if (!globalThis.crypto?.subtle) throw new Error("webcrypto_sha256_unavailable");
  return globalThis.crypto.subtle.digest("SHA-256", bytes).then((digest) =>
    Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("")
  );
}

export function createG009D007PresentationIndex(schema, p048Manifest) {
  assert(plainRecord(schema)
    && schema.contract_version === "GO_ODYSSEY_G009_D007_RUNTIME_PREREQUISITE_V1",
  "d007_runtime_schema_contract_mismatch");
  assert(schema.authority?.character_key === "server:player_appearance.character_key"
    && schema.authority?.never_infer_character_key_from_asset === true,
  "d007_character_authority_mismatch");
  assert(schema.owner_admission?.status === "APPROVED_FOR_CURRENT_G009_CANDIDATE",
    "d007_owner_admission_missing");
  assert(schema.equipment_catalog?.release_eligibility === "NOT_CLEARED"
    && schema.equipment_catalog?.production_off_hand_flag === false
    && schema.equipment_catalog?.two_handed_supported === false,
  "d007_release_or_equipment_boundary_changed");
  assert(schema.excluded_capabilities?.PET_COMPANION === "EXCLUDED_UNRESOLVED_NODE_VALIDATION",
    "d007_companion_exclusion_changed");
  createG009RuntimeEquipmentIndex(schema);
  assert(p048Manifest?.feature_gate?.default_enabled === false
    && p048Manifest.feature_gate.model_request_when_off === 0,
  "p048_feature_gate_boundary_changed");
  assert(Array.isArray(p048Manifest.entries), "p048_runtime_entries_missing");

  const p048ById = new Map();
  for (const row of p048Manifest.entries) {
    assert(plainRecord(row) && typeof row.presentation_id === "string"
      && !p048ById.has(row.presentation_id), "p048_presentation_identity_ambiguous");
    p048ById.set(row.presentation_id, row);
  }

  const slots = schema.appearance_catalog?.slots;
  assert(plainRecord(slots) && JSON.stringify(Object.keys(slots).sort()) === JSON.stringify(["AURA", "BACK", "HEAD"]),
    "d007_appearance_slot_set_mismatch");
  const bySlot = new Map();
  for (const slot of ["HEAD", "BACK"]) {
    const rows = slots[slot];
    assert(plainRecord(rows) && Object.keys(rows).length > 0,
      "d007_appearance_catalog_missing:" + slot);
    const index = new Map();
    for (const [presentationId, schemaPath] of Object.entries(rows)) {
      const manifestRow = p048ById.get(presentationId);
      assert(manifestRow?.attachment_slot === slot
        && normalizeAssetPath(manifestRow.runtime_asset) === normalizeAssetPath(schemaPath)
        && /^[a-f0-9]{64}$/i.test(manifestRow.runtime_sha256),
      "d007_p048_identity_binding_mismatch:" + slot + ":" + presentationId);
      index.set(presentationId, Object.freeze({
        presentation_id: presentationId,
        slot,
        runtime_asset: "/" + normalizeAssetPath(manifestRow.runtime_asset),
        runtime_sha256: manifestRow.runtime_sha256.toLowerCase(),
        normalized_asset_scale: Number(manifestRow.normalized_asset_scale || 1),
        presentation_scale: Number(manifestRow.presentation_scale || 1),
        local_position_offset: Array.isArray(manifestRow.local_position_offset)
          ? manifestRow.local_position_offset.map(Number) : [0, 0, 0],
        attachment_anchor: manifestRow.attachment_anchor,
        orientation: manifestRow.orientation,
        authority_domain: manifestRow.authority_domain,
      }));
    }
    bySlot.set(slot, index);
  }

  const auraRows = slots.AURA;
  assert(plainRecord(auraRows) && Object.keys(auraRows).length === 1
    && plainRecord(auraRows.AURA_PRESENTATION_RING)
    && auraRows.AURA_PRESENTATION_RING.kind === "procedural_presentation_only"
    && /^#[0-9a-f]{6}$/i.test(auraRows.AURA_PRESENTATION_RING.color),
  "d007_aura_contract_mismatch");
  bySlot.set("AURA", new Map([[
    "AURA_PRESENTATION_RING",
    Object.freeze({
      presentation_id: "AURA_PRESENTATION_RING",
      slot: "AURA",
      kind: "procedural_presentation_only",
      color: auraRows.AURA_PRESENTATION_RING.color,
    }),
  ]]));

  return Object.freeze({
    bySlot,
    resolve(slot, presentationId) {
      return bySlot.get(slot)?.get(presentationId) || null;
    },
  });
}

function equippedId(snapshot, slot) {
  const equipped = plainRecord(snapshot?.equipped) ? snapshot.equipped : {};
  const fields = slot === "HEAD" ? ["hat_id", "hatId", "head_id", "headId"]
    : slot === "BACK" ? ["back_id", "backId"] : ["aura_id", "auraId"];
  for (const field of fields) {
    if (typeof equipped[field] === "string" && equipped[field].trim()) return equipped[field].trim();
  }
  return null;
}

function itemSlot(item) {
  const value = String(item?.slot || item?.type || item?.appearance_slot || "").trim().toUpperCase();
  if (["HEAD", "HAT"].includes(value)) return "HEAD";
  if (["BACK", "CAPE"].includes(value)) return "BACK";
  return value === "AURA" ? "AURA" : null;
}

function itemId(item) {
  for (const value of [item?.id, item?.item_id, item?.itemId]) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

function explicitPresentationId(item) {
  const presentation = item?.presentation_mapping || item?.presentationMapping || item?.presentation;
  for (const value of [presentation?.presentation_id, presentation?.presentationId, item?.presentation_id]) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

function selectedPresentation(snapshot, slot) {
  const selectedId = equippedId(snapshot, slot);
  if (!selectedId || !Array.isArray(snapshot?.wardrobe)) return null;
  const item = snapshot.wardrobe.find((candidate) => itemId(candidate) === selectedId
    && itemSlot(candidate) === slot && candidate.is_equipped === true);
  return item ? { item, presentationId: explicitPresentationId(item) } : null;
}

function makeAura(THREE, descriptor, item) {
  const colorValue = typeof item?.color === "string" && /^#[0-9a-f]{6}$/i.test(item.color)
    ? item.color : descriptor.color;
  const group = new THREE.Group();
  group.name = "G009_D007_AURA:" + descriptor.presentation_id;
  group.userData = {
    attachment_slot: "AURA",
    presentation_id: descriptor.presentation_id,
    authority_domain: "PRESENTATION_ONLY",
    selection_contract: "EXPLICIT_SERVER_APPEARANCE_PRESENTATION_ID",
    color: colorValue,
  };
  for (const [name, radius, tube, opacity] of [
    ["base", 0.9, 0.045, 0.68],
    ["orbit", 1.0, 0.028, 0.44],
    ["halo", 0.78, 0.022, 0.32],
  ]) {
    const mesh = new THREE.Mesh(
      new THREE.TorusGeometry(radius, tube, 12, 64),
      new THREE.MeshBasicMaterial({
        color: colorValue, transparent: true, opacity, depthWrite: false,
        blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
      }),
    );
    mesh.name = "d007-aura-" + name;
    mesh.rotation.x = Math.PI / 2;
    group.add(mesh);
  }
  return group;
}

export function createG009D007SharedHostAdapter({
  THREE,
  GLTFLoader,
  host,
  presentationIndex,
  fetchImpl = globalThis.fetch,
  baseUrl = globalThis.location?.href || "http://localhost/",
}) {
  assert(THREE?.Group && typeof GLTFLoader === "function", "d007_three_runtime_dependencies_missing");
  assert(host && typeof host.attach === "function" && typeof host.detach === "function",
    "d007_shared_host_required");
  assert(presentationIndex && typeof presentationIndex.resolve === "function",
    "d007_presentation_index_required");
  assert(typeof fetchImpl === "function", "d007_fetch_required");

  async function loadNode(descriptor, item) {
    if (descriptor.slot === "AURA") return makeAura(THREE, descriptor, item);
    const response = await fetchImpl(descriptor.runtime_asset, { cache: "no-store", credentials: "same-origin" });
    if (!response?.ok) throw new Error("d007_asset_http_failure:" + descriptor.presentation_id);
    const bytes = await response.arrayBuffer();
    if (await digestHex(bytes) !== descriptor.runtime_sha256) {
      throw new Error("d007_asset_sha256_mismatch:" + descriptor.presentation_id);
    }
    const loader = new GLTFLoader();
    const gltf = await loader.parseAsync(bytes, new URL(descriptor.runtime_asset, baseUrl).href);
    const root = gltf?.scene || gltf?.scenes?.[0];
    if (!root?.isObject3D) throw new Error("d007_asset_scene_missing:" + descriptor.presentation_id);
    root.traverse?.((node) => {
      if (!node.isMesh) return;
      const materials = Array.isArray(node.material) ? node.material : [node.material];
      materials.filter(Boolean).forEach((material) => {
        material.side = THREE.DoubleSide;
        material.needsUpdate = true;
      });
    });
    const scale = descriptor.normalized_asset_scale * descriptor.presentation_scale;
    if (!Number.isFinite(scale) || scale <= 0 || descriptor.local_position_offset.length !== 3
      || descriptor.local_position_offset.some((value) => !Number.isFinite(value))) {
      throw new Error("d007_asset_transform_invalid:" + descriptor.presentation_id);
    }
    root.scale.setScalar(scale);
    root.position.fromArray(descriptor.local_position_offset);
    root.rotation.set(0, descriptor.attachment_anchor === "A1_Head_BBOX_FACE_FRONT_CENTER" ? Math.PI : 0, 0);
    root.name = "G009_D007_" + descriptor.presentation_id;
    root.userData = {
      ...(root.userData || {}),
      attachment_slot: descriptor.slot,
      presentation_id: descriptor.presentation_id,
      authority_domain: descriptor.authority_domain,
      runtime_sha256: descriptor.runtime_sha256,
      selection_contract: "EXPLICIT_SERVER_APPEARANCE_PRESENTATION_ID",
    };
    return root;
  }

  async function renderServerSnapshot(snapshot) {
    const characterKey = snapshot?.character_key;
    assert(typeof characterKey === "string" && characterKey.trim()
      && snapshot?.character_key_source === "player_appearance.character_key"
      && snapshot?.character_key_authority === "player_appearance.character_key"
      && snapshot?.character_entitled === true
      && snapshot?.character_runtime?.character_key === characterKey,
    "d007_character_authority_fail_closed");

    const results = await Promise.all(G009_D007_APPEARANCE_SLOTS.map(async (slot) => {
      const selected = selectedPresentation(snapshot, slot);
      if (!selected?.presentationId) {
        return host.detach(slot);
      }
      const descriptor = presentationIndex.resolve(slot, selected.presentationId);
      if (!descriptor) {
        await host.detach(slot);
        return { status: "failed_closed", slot, reason: "unknown_d007_presentation" };
      }
      try {
        return await host.attach(slot, selected.presentationId,
          () => loadNode(descriptor, selected.item));
      } catch (error) {
        return {
          status: "failed_closed",
          slot,
          reason: error instanceof Error ? error.message : String(error),
        };
      }
    }));
    return {
      contract_version: G009_D007_HERO_ADAPTER_CONTRACT,
      status: "rendered",
      character_key: characterKey,
      slots: results,
      authority: "player_appearance.character_key",
      formal_item_mapping_created: false,
      equip_capability: false,
      release_eligibility: "NOT_CLEARED",
    };
  }

  return Object.freeze({ renderServerSnapshot });
}
