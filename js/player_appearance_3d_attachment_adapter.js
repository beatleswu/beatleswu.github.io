import * as THREE from "../assets/3d_shop/p048/vendor/three.module.js";

/**
 * Presentation-only bridge for the Appearance surface.
 *
 * This module deliberately does not import hero.html state, call an API, or
 * create an ownership/equipment authority.  It consumes a server snapshot
 * supplied by the caller and delegates HEAD/BACK attachment to the existing
 * P048 ThreeShopPresentationRuntime interface.  Aura is a procedural 3D
 * effect so V1 does not need an unapproved Aura GLB or product SKU.
 */

export const PLAYER_APPEARANCE_3D_ATTACHMENT_CONTRACT =
  "PLAYER_APPEARANCE_3D_ATTACHMENT_V1";

export const APPEARANCE_3D_SLOTS = Object.freeze(["HEAD", "BACK", "AURA"]);

const DEFAULT_AURA_COLOR = "#14b8a6";
const HEX_COLOR = /^#[0-9a-f]{3,8}$/i;

function isRecord(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function text(...values) {
  return values.find((value) => typeof value === "string" && value.trim())?.trim() || null;
}

function fail(code, message) {
  const error = new Error(message);
  error.code = code;
  throw error;
}

function canonicalSlot(value) {
  const slot = String(value || "").trim().toUpperCase();
  if (["HEAD", "HAT"].includes(slot)) return "HEAD";
  if (["BACK", "CAPE"].includes(slot)) return "BACK";
  if (slot === "AURA") return "AURA";
  return null;
}

export function appearanceSlotOf(item) {
  if (!isRecord(item)) return null;
  return canonicalSlot(item.type || item.slot || item.appearance_slot || item.appearanceSlot);
}

export function appearanceItemId(item) {
  if (!isRecord(item)) return null;
  return text(item.id, item.item_id, item.itemId, item.appearance_id, item.appearanceId);
}

function equippedContainer(snapshot) {
  return isRecord(snapshot?.equipped) ? snapshot.equipped : {};
}

export function readEquippedAppearanceId(snapshot, slot) {
  const canonical = canonicalSlot(slot);
  if (!canonical) return null;
  const equipped = equippedContainer(snapshot);
  if (canonical === "HEAD") {
    return text(equipped.head_id, equipped.headId, equipped.hat_id, equipped.hatId);
  }
  if (canonical === "BACK") {
    return text(equipped.back_id, equipped.backId, equipped.cape_id, equipped.capeId);
  }
  return text(equipped.aura_id, equipped.auraId);
}

export function findServerOwnedAppearanceItem(snapshot, slot, itemId = null) {
  const canonical = canonicalSlot(slot);
  if (!canonical) return null;
  const items = Array.isArray(snapshot?.wardrobe) ? snapshot.wardrobe : [];
  const requestedId = itemId == null ? readEquippedAppearanceId(snapshot, canonical) : String(itemId);
  return items.find((item) => (
    item && item.owned === true && appearanceSlotOf(item) === canonical &&
    (requestedId == null || appearanceItemId(item) === requestedId)
  )) || null;
}

function presentationObject(item) {
  if (!isRecord(item)) return null;
  return item.presentation_mapping || item.presentationMapping || item.presentation || null;
}

function presentationIdOf(item) {
  const presentation = presentationObject(item);
  return text(presentation?.presentation_id, presentation?.presentationId, item?.presentation_id);
}

function backAttachmentArgument(item) {
  const presentation = presentationObject(item);
  // P048 validates a full mapping against its runtime manifest.  A bare
  // presentation ID is safer when a server read model only carries the ID.
  if (isRecord(presentation) && presentationIdOf(item) &&
      presentation.runtime_asset && presentation.asset_sha256) {
    return presentation;
  }
  return presentationIdOf(item) || appearanceItemId(item);
}

export function normalizeServerAppearanceSnapshot(snapshot) {
  if (!isRecord(snapshot)) fail("INVALID_SERVER_SNAPSHOT", "server appearance snapshot is required");
  const characterKey = text(
    snapshot.character_key,
    snapshot.characterKey,
    snapshot.current_character?.character_key,
    snapshot.current_character?.character_id,
  );
  if (!characterKey) fail("MISSING_CHARACTER_KEY", "server snapshot character_key is required");
  if (!Array.isArray(snapshot.wardrobe)) {
    fail("MISSING_WARDROBE_SNAPSHOT", "server snapshot wardrobe is required");
  }
  return {
    ...snapshot,
    character_key: characterKey,
    equipped: { ...equippedContainer(snapshot) },
    wardrobe: snapshot.wardrobe.slice(),
  };
}

function selectionFromSnapshot(snapshot, draftAuraId = null) {
  const normalized = normalizeServerAppearanceSnapshot(snapshot);
  const headId = readEquippedAppearanceId(normalized, "HEAD");
  const backId = readEquippedAppearanceId(normalized, "BACK");
  const serverAuraId = readEquippedAppearanceId(normalized, "AURA");
  const auraId = draftAuraId == null ? serverAuraId : String(draftAuraId);
  const head = headId == null ? null : findServerOwnedAppearanceItem(normalized, "HEAD", headId);
  const back = backId == null ? null : findServerOwnedAppearanceItem(normalized, "BACK", backId);
  const aura = auraId == null ? null : findServerOwnedAppearanceItem(normalized, "AURA", auraId);

  if (headId != null && !head) fail("HEAD_NOT_SERVER_OWNED", "equipped Head is not server-owned in the snapshot");
  if (backId != null && !back) fail("BACK_NOT_SERVER_OWNED", "equipped Back is not server-owned in the snapshot");
  if (auraId != null && !aura) fail("AURA_NOT_SERVER_OWNED", "selected Aura is not server-owned in the snapshot");

  if (head && !presentationIdOf(head)) {
    fail("HEAD_PRESENTATION_UNRESOLVED", "server-owned Head has no presentation mapping");
  }
  if (back && !backAttachmentArgument(back)) {
    fail("BACK_PRESENTATION_UNRESOLVED", "server-owned Back has no presentation mapping");
  }

  return {
    snapshot: normalized,
    character_key: normalized.character_key,
    head,
    back,
    aura,
    server_aura_id: serverAuraId,
    displayed_aura_id: aura ? appearanceItemId(aura) : null,
  };
}

function p048RuntimeInterface(runtime) {
  if (!runtime || typeof runtime !== "object") {
    fail("RUNTIME_REQUIRED", "P048 runtime instance is required");
  }
  if (typeof runtime.setHead !== "function" || typeof runtime.setBack !== "function") {
    fail("RUNTIME_ATTACHMENT_INTERFACE_MISSING", "P048 setHead/setBack interface is required");
  }
  return {
    contract_version: PLAYER_APPEARANCE_3D_ATTACHMENT_CONTRACT,
    renderer: "ThreeShopPresentationRuntime",
    getAttachmentHost: () => runtime.getAppearanceAttachmentHost?.() || runtime.heroGroup || null,
    getCharacterRoot: () => runtime.getCharacterRoot?.() || runtime.heroRoot || null,
    attachHead: (presentationId) => runtime.setHead(presentationId || "NONE"),
    attachBack: (presentation) => runtime.setBack(presentation || false),
  };
}

export function createP048AppearanceAttachmentInterface(runtime) {
  return p048RuntimeInterface(runtime);
}

function normalizeAuraColor(aura) {
  const presentation = presentationObject(aura);
  const candidate = text(aura?.color, presentation?.color, presentation?.aura_color) || DEFAULT_AURA_COLOR;
  if (!HEX_COLOR.test(candidate)) return DEFAULT_AURA_COLOR;
  return candidate;
}

function disposeAuraTree(root) {
  if (!root) return;
  const geometries = new Set();
  const materials = new Set();
  root.traverse((node) => {
    if (node.geometry && !geometries.has(node.geometry)) {
      geometries.add(node.geometry);
      node.geometry.dispose();
    }
    const list = Array.isArray(node.material) ? node.material : [node.material];
    list.filter(Boolean).forEach((material) => {
      if (!materials.has(material)) {
        materials.add(material);
        material.dispose();
      }
    });
  });
}

function auraMaterial(color, opacity) {
  return new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity,
    depthWrite: false,
    depthTest: true,
    blending: THREE.AdditiveBlending,
    side: THREE.DoubleSide,
  });
}

export class PlayerAppearance3DAttachmentAdapter {
  constructor(runtime, options = {}) {
    this.runtime = runtime;
    this.interface = options.attachmentInterface || p048RuntimeInterface(runtime);
    this.auraGroup = null;
    this.auraState = null;
    this.renderGeneration = 0;
    this.lastProjection = null;
  }

  async renderServerSnapshot(snapshot) {
    return this.renderSnapshot(snapshot, { mode: "server" });
  }

  async previewAura(snapshot, draftAuraId) {
    return this.renderSnapshot(snapshot, { mode: "preview", draftAuraId });
  }

  async cancelPreview(snapshot) {
    return this.renderSnapshot(snapshot, { mode: "server" });
  }

  async renderSnapshot(snapshot, options = {}) {
    const mode = options.mode === "preview" ? "preview" : "server";
    const selection = selectionFromSnapshot(snapshot, options.draftAuraId ?? null);
    const generation = ++this.renderGeneration;

    await this.interface.attachHead(selection.head ? presentationIdOf(selection.head) : "NONE");
    if (generation !== this.renderGeneration) return { status: "stale", contract_version: PLAYER_APPEARANCE_3D_ATTACHMENT_CONTRACT };

    await this.interface.attachBack(selection.back ? backAttachmentArgument(selection.back) : false);
    if (generation !== this.renderGeneration) return { status: "stale", contract_version: PLAYER_APPEARANCE_3D_ATTACHMENT_CONTRACT };

    this.renderAura(selection.aura, mode);
    this.lastProjection = {
      contract_version: PLAYER_APPEARANCE_3D_ATTACHMENT_CONTRACT,
      mode,
      character_key: selection.character_key,
      head_id: appearanceItemId(selection.head),
      back_id: appearanceItemId(selection.back),
      aura_id: selection.displayed_aura_id,
      head_presentation_id: selection.head ? presentationIdOf(selection.head) : null,
      back_presentation_id: selection.back ? presentationIdOf(selection.back) : null,
      aura_presentation_id: selection.aura
        ? (presentationIdOf(selection.aura) || "AURA_PRESENTATION_RING")
        : null,
      server_aura_id: selection.server_aura_id,
      preview_mutates_ownership: false,
      preview_mutates_equipment: false,
      gameplay_authority: "none",
      xp_authority: "none",
    };
    return { status: "rendered", ...this.lastProjection };
  }

  renderAura(aura, mode = "server") {
    this.clearAura();
    if (!aura) return null;
    const host = this.interface.getAttachmentHost();
    const characterRoot = this.interface.getCharacterRoot();
    if (!host || !characterRoot) fail("CHARACTER_STAGE_UNAVAILABLE", "character stage is required for Aura presentation");

    characterRoot.updateMatrixWorld(true);
    host.updateMatrixWorld(true);
    const worldBox = new THREE.Box3().setFromObject(characterRoot);
    if (worldBox.isEmpty()) fail("CHARACTER_BOUNDS_EMPTY", "character bounds are required for Aura presentation");
    const worldCenter = worldBox.getCenter(new THREE.Vector3());
    const center = host.worldToLocal(worldCenter.clone());
    const size = worldBox.getSize(new THREE.Vector3());
    const radius = Math.max(0.7, Math.max(size.x, size.z) * 0.58);
    const color = normalizeAuraColor(aura);
    const group = new THREE.Group();
    const id = appearanceItemId(aura);
    group.name = `PLAYER_COSMETIC_AURA:${id}`;
    group.userData = {
      attachment_slot: "AURA",
      authority_domain: "COSMETIC_AURA",
      item_id: id,
      mode,
      color,
      gameplay_authority: "none",
      xp_authority: "none",
      persistence: "server_snapshot_only",
      procedural: true,
    };

    const base = new THREE.Mesh(
      new THREE.TorusGeometry(radius, Math.max(0.035, radius * 0.045), 16, 72),
      auraMaterial(color, 0.72),
    );
    base.name = "cosmetic-aura-ring-base";
    base.rotation.x = Math.PI / 2;
    base.position.set(center.x, center.y + size.y * 0.16, center.z);
    base.renderOrder = 8;

    const orbit = new THREE.Mesh(
      new THREE.TorusGeometry(radius * 1.04, Math.max(0.022, radius * 0.028), 12, 64),
      auraMaterial(color, 0.48),
    );
    orbit.name = "cosmetic-aura-ring-orbit";
    orbit.rotation.set(Math.PI / 2, Math.PI * 0.22, 0);
    orbit.position.set(center.x, center.y + size.y * 0.48, center.z);
    orbit.renderOrder = 8;

    const halo = new THREE.Mesh(
      new THREE.TorusGeometry(radius * 0.82, Math.max(0.018, radius * 0.022), 12, 64),
      auraMaterial(color, 0.34),
    );
    halo.name = "cosmetic-aura-ring-halo";
    halo.rotation.set(Math.PI / 2, -Math.PI * 0.3, 0);
    halo.position.set(center.x, center.y + size.y * 0.78, center.z);
    halo.renderOrder = 8;

    group.add(base, orbit, halo);
    host.add(group);
    this.auraGroup = group;
    this.auraState = { id, color, mode, elapsed: 0 };
    return group;
  }

  update(deltaSeconds = 1 / 60) {
    if (!this.auraGroup || !this.auraState) return;
    this.auraState.elapsed += Math.max(0, Number(deltaSeconds) || 0);
    const [base, orbit, halo] = this.auraGroup.children;
    const t = this.auraState.elapsed;
    if (base) base.rotation.z = t * 0.65;
    if (orbit) orbit.rotation.y = t * 0.9;
    if (halo) halo.rotation.z = -t * 0.45;
  }

  clearAura() {
    if (!this.auraGroup) {
      this.auraState = null;
      return;
    }
    this.auraGroup.removeFromParent();
    disposeAuraTree(this.auraGroup);
    this.auraGroup = null;
    this.auraState = null;
  }

  dispose() {
    ++this.renderGeneration;
    this.clearAura();
    this.lastProjection = null;
  }
}

export function createPlayerAppearance3DAttachmentAdapter(runtime, options = {}) {
  return new PlayerAppearance3DAttachmentAdapter(runtime, options);
}
