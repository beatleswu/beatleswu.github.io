/*
 * Go Odyssey Formal 3D Character + Equipment V1
 *
 * Presentation-only runtime contract.  The server remains the sole authority
 * for player_appearance.character_key.  This module resolves that exact key
 * against the admitted Future30 manifest and fails closed for legacy/unknown
 * keys; it never invents a key, writes a loadout, or mutates ownership.
 *
 * The module is intentionally shared by Hero, Shop, Backpack, and Equipment
 * preview surfaces.  A preview surface supplies the same asset identity and
 * receives the same socket/slot rules without creating a second catalog.
 */

import * as THREE from "three";
import { GLTFLoader } from "/assets/3d_shop/p048/vendor/jsm/loaders/GLTFLoader.js";
import { resolvePlayerCharacterRuntime } from "/js/player_character_3d_runtime_bridge.js";
import {
  createPlayerAppearance3DAttachmentAdapter,
  PLAYER_APPEARANCE_3D_ATTACHMENT_CONTRACT,
} from "/js/player_appearance_3d_attachment_adapter.js";
import {
  createG009RuntimeEquipmentIndex,
  resolveG009RuntimeEquipmentIdentity,
} from "/js/g009_d007_runtime_identity_resolver.mjs";

export const FORMAL_3D_CONTRACT = "FORMAL_3D_CHARACTER_EQUIPMENT_V1";
export const FORMAL_3D_CHARACTER_CAPACITY = 30;
export const FORMAL_3D_VISUAL_MODEL_CAPACITY = 33;
export const FORMAL_3D_SOCKET_NAMES = Object.freeze({
  MAIN_HAND: "hand.R",
  OFF_HAND: "hand.L",
  HEAD: "head",
  BACK: "back",
  AURA: "aura",
});

export const FORMAL_3D_ATTACHMENT_HOST_CONTRACT = Object.freeze({
  contract_version: "FORMAL_3D_ATTACHMENT_HOST_V1",
  CHARACTER_ROOT: "CHARACTER_ROOT",
  MAIN_HAND: "MAIN_HAND",
  OFF_HAND: "OFF_HAND",
  HEAD: "HEAD",
  BACK: "BACK",
  AURA: "AURA",
  excluded_capabilities: Object.freeze({
    PET_COMPANION: "EXCLUDED_UNRESOLVED_NODE_VALIDATION",
  }),
  lifecycle: Object.freeze(["mount", "replace", "unmount", "cleanup", "character_swap"]),
  main_hand_socket: "hand.R",
  off_hand_socket: "hand.L",
  companion_boundary: "existing server-owned Pet/Companion identity; presentation host only",
});

export const FORMAL_3D_SHARED_PREVIEW_CONTRACT = Object.freeze({
  contract_version: "FORMAL_3D_SHARED_PREVIEW_V1",
  asset_identity: "asset_id",
  mapping_source: "/schemas/g009_d007_runtime_prerequisite_v1.json#/equipment_catalog/items",
  mount_api: "mountShared3DPreview(container, payload)",
  lifecycle: Object.freeze(["mount", "replace", "unmount", "cleanup", "character_swap"]),
  supported_slots: Object.freeze(["MAIN_HAND", "OFF_HAND", "HEAD", "BACK", "AURA"]),
  supported_weapon_classes: Object.freeze(["ONE_HAND", "KNIFE_SMALL"]),
  supported_off_hand_classes: Object.freeze(["SHIELD"]),
  unsupported_reasons: Object.freeze({
    TWO_HANDED: "two-handed weapons are outside the product contract",
    POLEARM: "long-handled two-handed weapons are outside the product contract",
    OUTFIT: "Outfit V1 was cancelled",
    PRODUCTION_OFF_HAND: "Production off-hand flag is not enabled by D",
  }),
  authority: "server-owned identity/ownership; preview renderer is presentation-only",
});

const FORMAL_MANIFEST_URL = "/schemas/g009_d007_runtime_prerequisite_v1.json";
const DEFAULT_CHARACTER_MANIFEST_URL = "/schemas/future30_c005_real_asset_runtime_mapping_manifest.json";
const MAX_ACTIVE_RENDERERS = 1;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function isRecord(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function firstString(...values) {
  return values.find((value) => typeof value === "string" && value.trim())?.trim() || null;
}

function finiteArray(value, length) {
  return Array.isArray(value) && value.length === length && value.every(Number.isFinite);
}

function characterKeyFromAuthority(authority) {
  if (!isRecord(authority)) return null;
  const current = isRecord(authority.current_character)
    ? authority.current_character
    : isRecord(authority.currentCharacter) ? authority.currentCharacter : null;
  return firstString(
    authority.character_key,
    authority.characterKey,
    current?.character_key,
    current?.characterKey,
    current?.character_id,
    current?.characterId,
  );
}

function requestedVariantFromAuthority(authority) {
  if (!isRecord(authority)) return null;
  const current = isRecord(authority.current_character)
    ? authority.current_character
    : isRecord(authority.currentCharacter) ? authority.currentCharacter : null;
  return firstString(
    authority.character_variant,
    authority.characterVariant,
    current?.character_variant,
    current?.characterVariant,
    current?.variant,
  );
}

function safeLower(value) {
  return typeof value === "string" ? value.toLowerCase() : "";
}

function monotonicNow() {
  return typeof performance !== "undefined" && typeof performance.now === "function"
    ? performance.now()
    : Date.now();
}

function prepareRenderable(root) {
  root.traverse((node) => {
    if (!node.isMesh) return;
    node.castShadow = true;
    node.receiveShadow = true;
    const materials = Array.isArray(node.material) ? node.material : [node.material];
    materials.filter(Boolean).forEach((material) => {
      material.side = THREE.DoubleSide;
      material.needsUpdate = true;
    });
  });
  return root;
}

function boundsOf(root) {
  root.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(root);
  return {
    box,
    size: box.getSize(new THREE.Vector3()),
    center: box.getCenter(new THREE.Vector3()),
  };
}

function disposeMaterial(material, disposedTextures) {
  if (!material) return;
  Object.values(material).forEach((value) => {
    if (value?.isTexture && !disposedTextures.has(value)) {
      disposedTextures.add(value);
      value.dispose();
    }
  });
  material.dispose();
}

function disposeObject(root, disposedGeometries, disposedMaterials, disposedTextures) {
  if (!root) return;
  root.traverse((node) => {
    if (!node.isMesh && !node.isPoints && !node.isLine) return;
    if (node.geometry && !disposedGeometries.has(node.geometry)) {
      disposedGeometries.add(node.geometry);
      node.geometry.dispose();
    }
    const materials = Array.isArray(node.material) ? node.material : [node.material];
    materials.filter(Boolean).forEach((material) => {
      if (!disposedMaterials.has(material)) {
        disposedMaterials.add(material);
        disposeMaterial(material, disposedTextures);
      }
    });
  });
}

function cloneRigidScene(scene) {
  // All formal equipment and appearance assets are rigid presentation assets.
  // Character skins remain the original loaded scene and are never cloned.
  return prepareRenderable(scene.clone(true));
}

function normalizedNodeName(value) {
  return safeLower(value).replace(/[^a-z0-9]/g, "");
}

function findSemanticNode(root, semantic) {
  const wanted = semantic === "right"
    ? ["handr", "righthand", "mixamorigrighthand"]
    : ["handl", "lefthand", "mixamoriglefthand"];
  let found = null;
  root.traverse((node) => {
    if (found || !node.name) return;
    const name = normalizedNodeName(node.name);
    if (wanted.some((candidate) => name === candidate || name.endsWith(candidate))) found = node;
  });
  return found;
}

function scaleAndCenterInSocket(root, socket, targetHeight, offset = [0, 0, 0]) {
  root.scale.setScalar(1);
  root.position.set(0, 0, 0);
  root.rotation.set(0, 0, 0);
  root.updateMatrixWorld(true);
  const initial = boundsOf(root);
  const sourceHeight = Math.max(initial.size.y, 0.001);
  root.scale.setScalar(targetHeight / sourceHeight);
  root.updateMatrixWorld(true);
  const fitted = boundsOf(root);
  root.position.set(
    -((fitted.box.min.x + fitted.box.max.x) * 0.5) + offset[0],
    -((fitted.box.min.y + fitted.box.max.y) * 0.5) + offset[1],
    -((fitted.box.min.z + fitted.box.max.z) * 0.5) + offset[2],
  );
  socket.add(root);
}

function validateCharacterManifest(manifest) {
  assert(isRecord(manifest), "Future30 character manifest is not an object");
  assert(manifest.contract_version === "FUTURE30_CHARACTER_RUNTIME_MANIFEST_V1",
    "Future30 character manifest contract is invalid");
  assert(manifest.counts?.logical_character_count === FORMAL_3D_CHARACTER_CAPACITY,
    "Future30 logical character count is not 30");
  assert(manifest.counts?.visual_model_count === FORMAL_3D_VISUAL_MODEL_CAPACITY,
    "Future30 visual model count is not 33");
  assert(Array.isArray(manifest.roster) && manifest.roster.length === 30,
    "Future30 roster must contain exactly 30 logical characters");
  assert(Array.isArray(manifest.visual_models) && manifest.visual_models.length === 33,
    "Future30 manifest must contain exactly 33 visual models");
  const characterIds = new Set();
  manifest.roster.forEach((entry) => {
    assert(firstString(entry.character_id), "Future30 roster entry is missing character_id");
    assert(!characterIds.has(entry.character_id), "duplicate logical character id: " + entry.character_id);
    characterIds.add(entry.character_id);
    assert(entry.admission_state === "ENABLED", "logical character is not admitted: " + entry.character_id);
  });
  const visualIds = new Set();
  manifest.visual_models.forEach((entry) => {
    assert(firstString(entry.visual_model_id, entry.character_id, entry.runtime_glb),
      "Future30 visual model is incomplete");
    assert(!visualIds.has(entry.visual_model_id), "duplicate visual model id: " + entry.visual_model_id);
    visualIds.add(entry.visual_model_id);
    assert(entry.asset_status === "PRESENT", "visual model is not present: " + entry.visual_model_id);
    assert(typeof entry.runtime_glb === "string" && entry.runtime_glb.endsWith(".glb"),
      "visual model runtime GLB mapping is missing: " + entry.visual_model_id);
    assert(entry.placeholder_mapping === false, "placeholder visual mapping rejected: " + entry.visual_model_id);
  });
  return manifest;
}

export function validateFormal3DManifest(manifest) {
  assert(isRecord(manifest), "formal 3D manifest is not an object");
  assert(manifest.contract_version === "GO_ODYSSEY_G009_D007_RUNTIME_PREREQUISITE_V1",
    "G009 D007 runtime prerequisite contract version is invalid");
  assert(manifest.authority?.character_key === "server:player_appearance.character_key",
    "server character-key authority is missing");
  assert(manifest.authority?.never_infer_character_key_from_asset === true,
    "character identity inference must remain disabled");
  assert(manifest.character_catalog?.logical_character_count === 30,
    "formal character catalog logical count is invalid");
  assert(manifest.character_catalog?.visual_model_count === 33,
    "formal character catalog visual count is invalid");
  assert(manifest.equipment_catalog?.two_handed_supported === false,
    "two-handed weapon support must remain disabled");
  assert(manifest.equipment_catalog?.production_off_hand_flag === false,
    "off-hand Production flag must remain disabled");
  assert(manifest.boundaries?.outfit_v1 === "CANCELLED", "Outfit V1 boundary changed");
  assert(manifest.shared_preview_contract?.asset_identity === "asset_id",
    "shared preview asset identity is missing");
  assert(manifest.shared_preview_contract?.mount_api === "mountShared3DPreview(container, payload)",
    "shared preview mount API is missing");
  assert(manifest.owner_admission?.status === "APPROVED_FOR_CURRENT_G009_CANDIDATE",
    "current G009 Owner admission is missing");
  assert(manifest.owner_admission?.evidence_verification === "RETAINS_PRIOR_AUDIT_STATUS",
    "prior asset evidence status must be retained");
  const items = manifest.equipment_catalog?.items;
  assert(Array.isArray(items) && items.length === 12, "formal equipment catalog must contain 12 bounded items");
  const admittedAssetIds = manifest.owner_admission?.admitted_asset_ids;
  assert(Array.isArray(admittedAssetIds) && admittedAssetIds.length === 12,
    "Owner-admitted asset roster must contain exactly 12 identities");
  assert(new Set(admittedAssetIds).size === admittedAssetIds.length,
    "duplicate identity in Owner-admitted asset roster");
  const itemIds = new Set();
  const serverItemIds = new Set();
  const equipmentByServerItemId = new Map();
  const equipmentByCandidateItemId = new Map();
  items.forEach((item) => {
    assert(firstString(item.asset_id), "equipment asset identity is missing");
    assert(!itemIds.has(item.asset_id), "duplicate equipment asset identity: " + item.asset_id);
    itemIds.add(item.asset_id);
    assert(admittedAssetIds.includes(item.asset_id), "non-admitted equipment asset rejected: " + item.asset_id);
    assert(item.g009_owner_admission === "APPROVED_FOR_CURRENT_G009_CANDIDATE",
      "equipment asset lacks current-candidate Owner admission: " + item.asset_id);
    assert(item.evidence_verification === "RETAINS_PRIOR_AUDIT_STATUS",
      "equipment asset evidence status was changed: " + item.asset_id);
    assert(item.release_eligibility === "NOT_CLEARED" && item.equip_capability === false,
      "candidate admission cannot enable release or equip capability: " + item.asset_id);
    if (item.server_item_id === null) {
      assert(item.item_mapping_status === "UNRESOLVED_NO_CANONICAL_ITEM_ID",
        "missing item identity must remain explicitly unresolved: " + item.asset_id);
    } else {
      assert(firstString(item.server_item_id), "equipment server item identity is malformed");
      assert(["CURRENT_SERVER_ID", "D007_SOURCE_CANDIDATE_ONLY"].includes(item.item_mapping_status),
        "equipment item identity has an unsupported provenance status: " + item.asset_id);
      assert(!serverItemIds.has(item.server_item_id), "duplicate equipment server item identity: " + item.server_item_id);
      serverItemIds.add(item.server_item_id);
      if (item.item_mapping_status === "CURRENT_SERVER_ID") {
        equipmentByServerItemId.set(item.server_item_id, item);
      } else {
        equipmentByCandidateItemId.set(item.server_item_id, item);
      }
    }
    assert(item.slot === "MAIN_HAND" || item.slot === "OFF_HAND", "unsupported equipment slot");
    assert(item.slot === "MAIN_HAND"
      ? ["ONE_HAND", "KNIFE_SMALL"].includes(item.presentation_class)
      : item.presentation_class === "SHIELD", "equipment class violates socket contract");
    assert(!safeLower(item.presentation_class).includes("two"), "two-handed item rejected");
    assert(typeof item.runtime_asset === "string" && item.runtime_asset.endsWith(".glb"),
      "equipment runtime asset is missing: " + item.asset_id);
    assert(typeof item.runtime_sha256 === "string" && /^[a-f0-9]{64}$/i.test(item.runtime_sha256),
      "equipment runtime SHA256 is missing: " + item.asset_id);
    assert(item.socket === (item.slot === "MAIN_HAND" ? "hand.R" : "hand.L"),
      "equipment socket does not match slot: " + item.asset_id);
    assert(finiteArray(item.position, 3) && finiteArray(item.rotation, 3) && finiteArray(item.scale, 3),
      "equipment transform is incomplete: " + item.asset_id);
  });
  assert(itemIds.size === admittedAssetIds.length
    && admittedAssetIds.every((assetId) => itemIds.has(assetId)),
  "runtime rows must exactly match the 12 admitted asset identities");
  assert(isRecord(manifest.appearance_catalog?.slots?.HEAD), "HEAD appearance slot is missing");
  assert(isRecord(manifest.appearance_catalog?.slots?.BACK), "BACK appearance slot is missing");
  assert(isRecord(manifest.appearance_catalog?.slots?.AURA), "AURA appearance slot is missing");
  assert(manifest.excluded_capabilities?.PET_COMPANION === "EXCLUDED_UNRESOLVED_NODE_VALIDATION",
    "unresolved Pet/Companion capability must remain excluded");
  assert(!manifest.appearance_catalog?.COMPANION,
    "Pet/Companion models must not be admitted through this prerequisite");
  const equipmentIndex = createG009RuntimeEquipmentIndex(manifest);
  return {
    manifest,
    equipmentIndex,
    equipmentById: equipmentIndex.byAssetId,
    equipmentByServerItemId: equipmentIndex.byServerItemId,
    equipmentByCandidateItemId,
  };
}

export function resolveFormalEquipmentIdentity(manifestOrValidated, identifier, { allowAssetId = true } = {}) {
  if (typeof identifier !== "string" || !identifier.trim()) return null;
  const index = manifestOrValidated?.equipmentIndex
    || (manifestOrValidated?.byAssetId instanceof Map
      ? manifestOrValidated
      : createG009RuntimeEquipmentIndex(manifestOrValidated));
  return resolveG009RuntimeEquipmentIdentity(index, identifier, { allowAssetId });
}

export function resolveFormalCharacterAuthority(authority, characterManifest) {
  const characterKey = characterKeyFromAuthority(authority);
  const common = {
    contract_version: FORMAL_3D_CONTRACT,
    source: "server:player_appearance.character_key",
    character_key: characterKey,
    logical_character_capacity: FORMAL_3D_CHARACTER_CAPACITY,
    visual_model_capacity: FORMAL_3D_VISUAL_MODEL_CAPACITY,
  };
  if (!characterKey) {
    return { ...common, status: "fail_closed", reason: "MISSING_SERVER_CHARACTER_KEY", runtime_glb: null };
  }
  const rosterEntry = characterManifest.roster.find((entry) => entry.character_id === characterKey);
  if (!rosterEntry) {
    return { ...common, status: "fail_closed", reason: "CHARACTER_KEY_NOT_IN_FORMAL_CATALOG", runtime_glb: null };
  }
  const allowedVariants = characterManifest.variant_policy?.allowed_variants || ["RED", "BLUE"];
  const requestedVariant = requestedVariantFromAuthority(authority);
  const variant = requestedVariant && allowedVariants.includes(requestedVariant)
    ? requestedVariant
    : (rosterEntry.default_variant || characterManifest.variant_policy?.default_variant || "RED");
  const variantRef = rosterEntry.variants?.[variant] || rosterEntry.variants?.[rosterEntry.default_variant];
  const visualModelId = variantRef?.visual_model_id;
  const visual = characterManifest.visual_models.find((entry) =>
    entry.visual_model_id === visualModelId && entry.character_id === characterKey && entry.variant === variant,
  ) || (variant !== rosterEntry.default_variant
    ? characterManifest.visual_models.find((entry) =>
      entry.visual_model_id === rosterEntry.variants?.[rosterEntry.default_variant]?.visual_model_id &&
      entry.character_id === characterKey && entry.variant === rosterEntry.default_variant,
    )
    : null);
  if (!visual || !visual.runtime_glb) {
    return {
      ...common,
      status: "fail_closed",
      reason: "CHARACTER_RUNTIME_MAPPING_MISSING",
      variant,
      visual_model_id: visualModelId || null,
      runtime_glb: null,
    };
  }
  const mapping = {
    [visual.character_asset_id]: {
      character_id: visual.character_id,
      character_asset_id: visual.character_asset_id,
      runtime_glb: visual.runtime_glb,
      label: visual.visual_identity,
    },
  };
  const bridgeResult = resolvePlayerCharacterRuntime({
    authenticated: true,
    current_character: {
      character_id: characterKey,
      character_asset_id: visual.character_asset_id,
    },
    character_asset_mapping: mapping,
    catalog_logical_character_count: characterManifest.counts.logical_character_count,
    catalog_visual_model_count: characterManifest.counts.visual_model_count,
  });
  if (bridgeResult.status !== "ready") {
    return { ...common, ...bridgeResult, status: "fail_closed", reason: bridgeResult.reason || "BRIDGE_REJECTED" };
  }
  return {
    ...common,
    status: "ready",
    variant,
    visual_model_id: visual.visual_model_id,
    character_asset_id: visual.character_asset_id,
    runtime_sha256: visual.runtime_sha256,
    runtime_glb: bridgeResult.runtime_glb,
    visual_identity: visual.visual_identity,
  };
}

export class Formal3DCharacterEquipmentRuntime {
  static activeRendererCount = 0;

  constructor(container, options = {}) {
    assert(container, "formal 3D runtime requires a mount container");
    this.container = container;
    this.options = options;
    this.previewOnly = options.previewOnly !== false;
    this.manifestUrl = options.manifestUrl || FORMAL_MANIFEST_URL;
    this.characterManifestUrl = options.characterManifestUrl || DEFAULT_CHARACTER_MANIFEST_URL;
    this.authorityProvider = typeof options.authorityProvider === "function"
      ? options.authorityProvider
      : () => options.authority || null;
    this.onStateChange = typeof options.onStateChange === "function" ? options.onStateChange : () => {};
    this.manifest = null;
    this.characterManifest = null;
    this.equipmentById = new Map();
    this.equipmentByServerItemId = new Map();
    this.equipmentIndex = null;
    this.characterSelection = null;
    this.status = "not_mounted";
    this.reason = null;
    this.authority = null;
    this.loader = new GLTFLoader();
    this.gltfCache = new Map();
    this.modelRequests = [];
    this.renderer = null;
    this.scene = null;
    this.camera = null;
    this.heroRoot = null;
    this.heroGroup = null;
    this.sockets = {};
    this.currentMainHand = null;
    this.currentOffHand = null;
    this.currentAppearances = { HEAD: null, BACK: null, AURA: null };
    this.serverAppearanceItemIds = { HEAD: null, BACK: null, AURA: null };
    this.currentAppearanceRoots = { HEAD: null, BACK: null, AURA: null };
    this.appearanceAdapter = null;
    this.serverAppearanceSnapshot = null;
    this.appearanceStatus = "not_loaded";
    this.appearanceError = null;
    this.petRoot = null;
    this.petId = null;
    this.characterSwapCount = 0;
    this.lifecycleCounts = { mount: 0, replace: 0, unmount: 0, cleanup: 0, character_swap: 0 };
    this.timings = {
      character_load_ms: null,
      mount_total_ms: null,
      equipment_swap_ms: null,
      appearance_render_ms: null,
      character_swap_ms: null,
      unmount_ms: null,
    };
    this.clock = new THREE.Clock();
    this.raf = 0;
    this.resizeObserver = null;
    this.bound = {};
    this.pointer = { active: false, id: null, x: 0 };
    this.switchCounts = { MAIN_HAND: 0, OFF_HAND: 0, HEAD: 0, BACK: 0, AURA: 0 };
    this.uiBound = false;
    this.ui = {};
  }

  async mount() {
    const mountStarted = monotonicNow();
    this.lifecycleCounts.mount += 1;
    try {
      const [formalResponse, characterResponse] = await Promise.all([
        fetch(this.manifestUrl, { cache: "no-store" }),
        fetch(this.characterManifestUrl, { cache: "no-store" }),
      ]);
      assert(formalResponse.ok, "formal 3D manifest request failed: " + formalResponse.status);
      assert(characterResponse.ok, "Future30 character manifest request failed: " + characterResponse.status);
      const formal = validateFormal3DManifest(await formalResponse.json());
      const characterManifest = validateCharacterManifest(await characterResponse.json());
      this.manifest = formal.manifest;
      this.equipmentIndex = formal.equipmentIndex;
      this.equipmentById = formal.equipmentById;
      this.equipmentByServerItemId = formal.equipmentByServerItemId;
      this.characterManifest = characterManifest;
      this.authority = await this.authorityProvider();
      this.characterSelection = resolveFormalCharacterAuthority(this.authority, this.characterManifest);
      if (this.characterSelection.status !== "ready") {
        this.status = "fail_closed";
        this.reason = this.characterSelection.reason;
        this.emit();
        return this;
      }
      if (Formal3DCharacterEquipmentRuntime.activeRendererCount >= MAX_ACTIVE_RENDERERS) {
        throw new Error("formal 3D renderer singleton limit exceeded");
      }
      this.setupScene();
      await this.loadHero();
      this.createSockets();
      this.appearanceAdapter = createPlayerAppearance3DAttachmentAdapter(this);
      this.bindPointerControls();
      this.bindControls();
      this.status = "ready";
      this.reason = null;
      const initial = this.options.initialEquipment || {};
      const initialAppearance = this.options.initialAppearance || {};
      if (initial.main_hand) await this.setMainHand(initial.main_hand);
      if (initial.off_hand) await this.setOffHand(initial.off_hand);
      if (Array.isArray(this.authority?.wardrobe)) {
        await this.renderServerAppearanceSnapshot(this.authority);
      } else {
        if (initialAppearance.HEAD) await this.setHead(initialAppearance.HEAD);
        if (initialAppearance.BACK) await this.setBack(initialAppearance.BACK);
        if (initialAppearance.AURA) await this.setAura(initialAppearance.AURA);
      }
      if (this.options.initialCompanion) await this.setCompanion(this.options.initialCompanion);
      this.startLoop();
      this.timings.mount_total_ms = Math.round(monotonicNow() - mountStarted);
      this.emit();
      return this;
    } catch (error) {
      if (this.renderer) {
        try { this.dispose({ emit: false }); } catch (_) { /* preserve original failure */ }
      }
      this.status = "error";
      this.reason = error instanceof Error ? error.message : String(error);
      this.emit();
      throw error;
    }
  }

  runtimeUrl(path) {
    return new URL(path, document.baseURI).href;
  }

  async loadGLTF(path, requestKey = path) {
    const url = this.runtimeUrl(path);
    if (this.gltfCache.has(url)) return this.gltfCache.get(url);
    this.modelRequests.push({ type: "GLB", key: requestKey, url });
    const promise = this.loader.loadAsync(url);
    this.gltfCache.set(url, promise);
    try {
      return await promise;
    } catch (error) {
      this.gltfCache.delete(url);
      throw error;
    }
  }

  setupScene() {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "high-performance" });
    Formal3DCharacterEquipmentRuntime.activeRendererCount += 1;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.08;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.domElement.setAttribute("aria-label", "Formal 3D character equipment preview");
    this.renderer.domElement.style.touchAction = "none";
    this.container.replaceChildren(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x071422);
    this.scene.fog = new THREE.Fog(0x071422, 14, 30);
    this.scene.add(new THREE.HemisphereLight(0xc3e5ff, 0x111827, 1.65));
    const key = new THREE.DirectionalLight(0xffe4c4, 3.0);
    key.position.set(-5, 8, 10);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    this.scene.add(key);
    const rim = new THREE.DirectionalLight(0x6dbbff, 1.7);
    rim.position.set(5, 5, -8);
    this.scene.add(rim);
    const floor = new THREE.Mesh(
      new THREE.CircleGeometry(7.5, 64),
      new THREE.MeshStandardMaterial({ color: 0x112b45, roughness: 0.9, metalness: 0.02 }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    this.scene.add(floor);
    const shadow = new THREE.Mesh(
      new THREE.CircleGeometry(1.35, 48),
      new THREE.MeshBasicMaterial({ color: 0x02070e, transparent: true, opacity: 0.45, depthWrite: false }),
    );
    shadow.rotation.x = -Math.PI / 2;
    shadow.scale.set(1.35, 0.52, 1);
    shadow.position.y = -0.02;
    this.scene.add(shadow);
    this.heroGroup = new THREE.Group();
    this.heroGroup.name = "Formal3DCharacterEquipmentGroup";
    this.scene.add(this.heroGroup);
    this.camera = new THREE.PerspectiveCamera(30, 1, 0.05, 100);
    this.resize();
    if (typeof ResizeObserver !== "undefined") {
      this.resizeObserver = new ResizeObserver(() => this.resize());
      this.resizeObserver.observe(this.container);
    } else {
      this.bound.resize = () => this.resize();
      window.addEventListener("resize", this.bound.resize, { passive: true });
    }
  }

  async loadHero() {
    const started = monotonicNow();
    this.heroRoot = await this.buildCharacterRoot(this.characterSelection);
    this.heroGroup.add(this.heroRoot);
    this.heroRoot.updateMatrixWorld(true);
    this.timings.character_load_ms = Math.round(monotonicNow() - started);
  }

  async buildCharacterRoot(selection) {
    const loaded = await this.loadGLTF(selection.runtime_glb, selection.character_key);
    const root = prepareRenderable(loaded.scene);
    root.name = "Formal3D_CHARACTER_ROOT_" + selection.character_key;
    root.rotation.set(0, 0, 0);
    root.updateMatrixWorld(true);
    const initial = boundsOf(root);
    const targetHeight = 5;
    root.scale.setScalar(targetHeight / Math.max(initial.size.y, 0.001));
    root.updateMatrixWorld(true);
    const fitted = boundsOf(root);
    root.position.set(
      -((fitted.box.min.x + fitted.box.max.x) * 0.5),
      -fitted.box.min.y,
      -((fitted.box.min.z + fitted.box.max.z) * 0.5),
    );
    root.userData.character_key = selection.character_key;
    root.userData.character_asset_id = selection.character_asset_id || null;
    root.userData.visual_model_id = selection.visual_model_id || null;
    root.updateMatrixWorld(true);
    return root;
  }

  createSockets() {
    const heightBounds = boundsOf(this.heroRoot).box;
    const height = heightBounds.max.y - heightBounds.min.y;
    const rightHandBone = findSemanticNode(this.heroRoot, "right");
    const leftHandBone = findSemanticNode(this.heroRoot, "left");
    const make = (name, parent, position = [0, 0, 0]) => {
      const group = new THREE.Group();
      group.name = "Formal3D_" + name + "Socket";
      group.position.fromArray(position);
      parent.add(group);
      return group;
    };
    this.sockets.MAIN_HAND = rightHandBone
      ? make("MAIN_HAND", rightHandBone)
      : make("MAIN_HAND", this.heroRoot, [0.44, height * 0.45, 0]);
    this.sockets.OFF_HAND = leftHandBone
      ? make("OFF_HAND", leftHandBone)
      : make("OFF_HAND", this.heroRoot, [-0.44, height * 0.45, 0]);
    this.sockets.HEAD = make("HEAD", this.heroRoot, [0, height * 0.91, 0]);
    this.sockets.BACK = make("BACK", this.heroRoot, [0, height * 0.51, -0.19]);
    this.sockets.AURA = make("AURA", this.heroRoot, [0, height * 0.46, 0]);
    this.sockets.MAIN_HAND.userData.bone = rightHandBone?.name || null;
    this.sockets.OFF_HAND.userData.bone = leftHandBone?.name || null;
    this.sockets.MAIN_HAND.userData.fallback = !rightHandBone;
    this.sockets.OFF_HAND.userData.fallback = !leftHandBone;
  }

  getCharacterRoot() {
    return this.heroRoot;
  }

  getAppearanceAttachmentHost() {
    return this.sockets.AURA || this.heroGroup;
  }

  getAttachmentHost(slot) {
    return this.sockets[slot] || null;
  }

  clearCompanion() {
    if (this.petRoot) this.petRoot.removeFromParent();
    this.petRoot = null;
    this.petId = null;
  }

  clearAttachmentHost() {
    this.lifecycleCounts.cleanup += 1;
    this.appearanceAdapter?.dispose();
    this.appearanceAdapter = null;
    Object.keys(this.sockets).forEach((slot) => this.clearSocket(slot));
    this.clearCompanion();
    this.sockets = {};
    this.currentMainHand = null;
    this.currentOffHand = null;
    this.currentAppearances = { HEAD: null, BACK: null, AURA: null };
    this.serverAppearanceItemIds = { HEAD: null, BACK: null, AURA: null };
    this.currentAppearanceRoots = { HEAD: null, BACK: null, AURA: null };
    this.serverAppearanceSnapshot = null;
    this.appearanceStatus = "not_loaded";
    this.appearanceError = null;
  }

  clearSocket(slot) {
    const socket = this.sockets[slot];
    if (!socket) return;
    [...socket.children].forEach((child) => child.removeFromParent());
  }

  async setEquipment(slot, assetId = null) {
    const started = monotonicNow();
    const normalized = assetId || null;
    const item = normalized
      ? resolveG009RuntimeEquipmentIdentity(this.equipmentIndex, normalized, {
        allowAssetId: this.previewOnly,
      })
      : null;
    if (normalized && !item) {
      const reason = this.equipmentById.has(normalized) && !this.previewOnly
        ? "client asset identity cannot override the server equipment item"
        : "unknown or non-admitted formal equipment identity rejected";
      throw new Error(reason + ": " + normalized);
    }
    if (slot === "MAIN_HAND") {
      if (item && (item.slot !== "MAIN_HAND" || !["ONE_HAND", "KNIFE_SMALL"].includes(item.presentation_class))) {
        throw new Error("main-hand accepts one-hand items only");
      }
    } else if (slot === "OFF_HAND") {
      if (item && (item.slot !== "OFF_HAND" || item.presentation_class !== "SHIELD")) {
        throw new Error("off-hand accepts shields only");
      }
    } else {
      throw new Error("unsupported equipment socket: " + slot);
    }
    this.clearSocket(slot);
    if (!item) {
      if (slot === "MAIN_HAND") this.currentMainHand = null;
      else this.currentOffHand = null;
      this.switchCounts[slot] += 1;
      this.timings.equipment_swap_ms = Math.round(monotonicNow() - started);
      this.lifecycleCounts.replace += 1;
      this.emit();
      return this.getDiagnostics();
    }
    const loaded = await this.loadGLTF(item.runtime_asset, item.asset_id);
    const root = cloneRigidScene(loaded.scene);
    root.name = "Formal3D_" + item.asset_id;
    root.userData.asset_id = item.asset_id;
    root.userData.preview_only = true;
    root.position.fromArray(item.position);
    root.rotation.fromArray(item.rotation);
    root.scale.fromArray(item.scale);
    this.sockets[slot].add(root);
    if (slot === "MAIN_HAND") this.currentMainHand = item.asset_id;
    else this.currentOffHand = item.asset_id;
    this.switchCounts[slot] += 1;
    this.timings.equipment_swap_ms = Math.round(monotonicNow() - started);
    this.lifecycleCounts.replace += 1;
    this.emit();
    return this.getDiagnostics();
  }

  setMainHand(assetId = null) {
    return this.setEquipment("MAIN_HAND", assetId);
  }

  setOffHand(assetId = null) {
    return this.setEquipment("OFF_HAND", assetId);
  }

  clearMainHand() {
    return this.setMainHand(null);
  }

  clearOffHand() {
    return this.setOffHand(null);
  }

  clearAppearance(slot) {
    if (slot === "AURA" && this.appearanceAdapter) {
      // F009 is the single Aura ownership/apply path.  Do not clear the
      // entire Aura host, which would also risk removing a future companion
      // boundary child.
      this.appearanceAdapter.clearAura();
    } else {
      this.clearSocket(slot);
    }
    this.currentAppearanceRoots[slot] = null;
    this.currentAppearances[slot] = null;
    this.serverAppearanceItemIds[slot] = null;
  }

  async setHead(assetId = null) {
    this.clearAppearance("HEAD");
    this.switchCounts.HEAD += 1;
    const normalized = assetId === "NONE" || assetId === false ? null : assetId;
    if (normalized) {
      const path = this.manifest.appearance_catalog.slots.HEAD[normalized];
      if (!path) throw new Error("unknown HEAD presentation asset rejected: " + normalized);
      const loaded = await this.loadGLTF(path, normalized);
      const root = cloneRigidScene(loaded.scene);
      root.name = "Formal3D_HEAD_" + normalized;
      scaleAndCenterInSocket(root, this.sockets.HEAD, 0.9, [0, 0.08, 0.02]);
      this.currentAppearanceRoots.HEAD = root;
      this.currentAppearances.HEAD = normalized;
    }
    this.emit();
    return this.getDiagnostics();
  }

  async setBack(assetId = null) {
    this.clearAppearance("BACK");
    this.switchCounts.BACK += 1;
    const normalized = assetId === false || assetId === "NONE"
      ? null
      : (isRecord(assetId)
        ? firstString(assetId.presentation_id, assetId.presentationId, assetId.id)
        : assetId);
    if (normalized) {
      // A server snapshot may carry a presentation object.  Only its
      // canonical presentation id is accepted; runtime paths are never
      // trusted from a client or read-model payload.
      const path = this.manifest.appearance_catalog.slots.BACK[normalized];
      if (!path) throw new Error("unknown BACK presentation asset rejected: " + normalized);
      const loaded = await this.loadGLTF(path, normalized);
      const root = cloneRigidScene(loaded.scene);
      root.name = "Formal3D_BACK_" + normalized;
      scaleAndCenterInSocket(root, this.sockets.BACK, 2.25, [0, 0, -0.16]);
      this.currentAppearanceRoots.BACK = root;
      this.currentAppearances.BACK = normalized;
    }
    this.emit();
    return this.getDiagnostics();
  }

  async setAura(assetId = null) {
    this.clearAppearance("AURA");
    this.switchCounts.AURA += 1;
    if (assetId) {
      const entry = this.manifest.appearance_catalog.slots.AURA[assetId];
      assert(entry?.kind === "procedural_presentation_only", "unknown AURA presentation asset rejected: " + assetId);
      assert(this.appearanceAdapter, "appearance attachment adapter is not mounted");
      // Local preview controls use the canonical formal presentation id but
      // never create an ownership record.  F009 owns the procedural Aura
      // implementation for both server snapshots and preview state.
      this.appearanceAdapter.renderAura({
        id: assetId,
        type: "aura",
        owned: true,
        color: entry.color || "#45d6c0",
      }, "preview");
      this.currentAppearanceRoots.AURA = this.appearanceAdapter.auraGroup;
      this.currentAppearances.AURA = assetId;
    }
    this.emit();
    return this.getDiagnostics();
  }

  async renderServerAppearanceSnapshot(snapshot) {
    const started = monotonicNow();
    this.appearanceStatus = "loading";
    this.appearanceError = null;
    this.serverAppearanceSnapshot = snapshot;
    try {
      assert(this.appearanceAdapter, "appearance attachment adapter is not mounted");
      const projection = await this.appearanceAdapter.renderServerSnapshot(snapshot);
      assert(projection?.status === "rendered", "server appearance projection did not render");
      this.currentAppearances = {
        HEAD: projection.head_presentation_id || null,
        BACK: projection.back_presentation_id || null,
        AURA: projection.aura_presentation_id || null,
      };
      this.serverAppearanceItemIds = {
        HEAD: projection.head_id || null,
        BACK: projection.back_id || null,
        AURA: projection.aura_id || null,
      };
      this.switchCounts.AURA += 1;
      this.currentAppearanceRoots.AURA = this.appearanceAdapter.auraGroup;
      this.appearanceStatus = "ready";
      this.timings.appearance_render_ms = Math.round(monotonicNow() - started);
      this.emit();
      return this.getDiagnostics();
    } catch (error) {
      this.appearanceStatus = "error";
      this.appearanceError = error?.code || (error instanceof Error ? error.message : String(error));
      this.reason = this.appearanceError;
      this.emit();
      throw error;
    }
  }

  async previewAppearance(snapshot, draftAuraId) {
    assert(this.appearanceAdapter, "appearance attachment adapter is not mounted");
    const projection = await this.appearanceAdapter.previewAura(snapshot, draftAuraId);
    if (projection?.status === "rendered") {
      this.currentAppearances.AURA = projection.aura_presentation_id || null;
      this.serverAppearanceItemIds.AURA = projection.aura_id || null;
      this.currentAppearanceRoots.AURA = this.appearanceAdapter.auraGroup;
      this.switchCounts.AURA += 1;
    }
    this.emit();
    return this.getDiagnostics();
  }

  async cancelAppearancePreview(snapshot = this.serverAppearanceSnapshot) {
    assert(snapshot, "server appearance snapshot is required to cancel preview");
    assert(this.appearanceAdapter, "appearance attachment adapter is not mounted");
    const projection = await this.appearanceAdapter.cancelPreview(snapshot);
    if (projection?.status === "rendered") {
      this.currentAppearances.AURA = projection.aura_presentation_id || null;
      this.serverAppearanceItemIds.AURA = projection.aura_id || null;
      this.currentAppearanceRoots.AURA = this.appearanceAdapter.auraGroup;
      this.switchCounts.AURA += 1;
    }
    this.emit();
    return this.getDiagnostics();
  }

  async setCompanion(companionId = null) {
    this.clearCompanion();
    if (companionId) {
      throw new Error("Pet/Companion runtime excluded pending node-validation closure");
    }
    this.emit();
    return this.getDiagnostics();
  }

  async swapCharacter(authority, {
    appearanceSnapshot = null,
    initialEquipment = null,
    initialCompanion = null,
  } = {}) {
    const started = monotonicNow();
    const nextSelection = resolveFormalCharacterAuthority(authority, this.characterManifest);
    if (nextSelection.status !== "ready") {
      this.status = "fail_closed";
      this.reason = nextSelection.reason;
      this.emit();
      return this.getDiagnostics();
    }

    // Load the exact next canonical model before touching the current stage.
    // A failed request therefore cannot silently replace identity or leave a
    // partially-cleared Hero.
    const nextRoot = await this.buildCharacterRoot(nextSelection);
    const previousRoot = this.heroRoot;
    this.clearAttachmentHost();
    previousRoot?.removeFromParent();
    this.heroRoot = nextRoot;
    this.heroGroup.add(this.heroRoot);
    this.heroRoot.updateMatrixWorld(true);
    this.characterSelection = nextSelection;
    this.authority = authority;
    this.createSockets();
    this.appearanceAdapter = createPlayerAppearance3DAttachmentAdapter(this);
    this.status = "ready";
    this.reason = null;
    this.characterSwapCount += 1;
    this.lifecycleCounts.character_swap += 1;
    this.lifecycleCounts.replace += 1;
    this.timings.character_swap_ms = Math.round(monotonicNow() - started);

    const equipment = initialEquipment || {};
    if (equipment.main_hand) await this.setMainHand(equipment.main_hand);
    if (equipment.off_hand) await this.setOffHand(equipment.off_hand);
    if (Array.isArray(authority?.wardrobe)) {
      await this.renderServerAppearanceSnapshot(appearanceSnapshot || authority);
    }
    if (initialCompanion) await this.setCompanion(initialCompanion);
    this.emit();
    return this.getDiagnostics();
  }

  async resetAttachments() {
    await this.setMainHand(null);
    await this.setOffHand(null);
    await this.setHead(null);
    await this.setBack(null);
    await this.setAura(null);
    this.clearCompanion();
    this.emit();
    return this.getDiagnostics();
  }

  bindControls() {
    if (this.uiBound) return;
    this.uiBound = true;
    const panel = this.container.closest("[data-formal-3d-panel]");
    if (panel?.dataset.formal3dPreviewFixture !== "true") {
      this.ui = {};
      return;
    }
    this.ui = {
      mainHand: panel.querySelector("[data-formal-3d-main-hand]") || null,
      offHand: panel.querySelector("[data-formal-3d-off-hand]") || null,
      head: panel.querySelector("[data-formal-3d-head]") || null,
      back: panel.querySelector("[data-formal-3d-back]") || null,
      aura: panel.querySelector("[data-formal-3d-aura]") || null,
      reset: panel.querySelector("[data-formal-3d-reset]") || null,
    };
    const select = (element, options, selected = "") => {
      if (!element) return;
      element.replaceChildren(new Option("None / 卸下", ""));
      options.forEach(([value, label]) => element.append(new Option(label, value)));
      element.value = selected || "";
    };
    select(this.ui.mainHand, [...this.equipmentById.values()]
      .filter((item) => item.slot === "MAIN_HAND")
      .map((item) => [item.asset_id, item.display_name]), this.currentMainHand);
    select(this.ui.offHand, [...this.equipmentById.values()]
      .filter((item) => item.slot === "OFF_HAND")
      .map((item) => [item.asset_id, item.display_name]), this.currentOffHand);
    select(this.ui.head, Object.entries(this.manifest.appearance_catalog.slots.HEAD)
      .map(([value]) => [value, value.replace("P045_H06_", "")]), this.currentAppearances.HEAD);
    select(this.ui.back, Object.entries(this.manifest.appearance_catalog.slots.BACK)
      .map(([value]) => [value, value.replace("P045_", "")]), this.currentAppearances.BACK);
    select(this.ui.aura, Object.entries(this.manifest.appearance_catalog.slots.AURA)
      .map(([value]) => [value, value.replace("AURA_", "")]), this.currentAppearances.AURA);
    this.ui.mainHand?.addEventListener("change", () => this.setMainHand(this.ui.mainHand.value).catch((error) => this.showError(error)));
    this.ui.offHand?.addEventListener("change", () => this.setOffHand(this.ui.offHand.value).catch((error) => this.showError(error)));
    this.ui.head?.addEventListener("change", () => this.setHead(this.ui.head.value).catch((error) => this.showError(error)));
    this.ui.back?.addEventListener("change", () => this.setBack(this.ui.back.value).catch((error) => this.showError(error)));
    this.ui.aura?.addEventListener("change", () => this.setAura(this.ui.aura.value).catch((error) => this.showError(error)));
    this.ui.reset?.addEventListener("click", () => this.resetAttachments().catch((error) => this.showError(error)));
    this.updateControls();
  }

  updateControls() {
    if (!this.uiBound) return;
    if (this.ui.mainHand) this.ui.mainHand.value = this.currentMainHand || "";
    if (this.ui.offHand) this.ui.offHand.value = this.currentOffHand || "";
    if (this.ui.head) this.ui.head.value = this.currentAppearances.HEAD || "";
    if (this.ui.back) this.ui.back.value = this.currentAppearances.BACK || "";
    if (this.ui.aura) this.ui.aura.value = this.currentAppearances.AURA || "";
  }

  showError(error) {
    this.reason = error instanceof Error ? error.message : String(error);
    this.emit();
  }

  bindPointerControls() {
    const element = this.renderer.domElement;
    this.bound.pointerdown = (event) => {
      this.pointer.active = true;
      this.pointer.id = event.pointerId;
      this.pointer.x = event.clientX;
      element.setPointerCapture?.(event.pointerId);
    };
    this.bound.pointermove = (event) => {
      if (!this.pointer.active || event.pointerId !== this.pointer.id) return;
      const deltaX = event.clientX - this.pointer.x;
      this.pointer.x = event.clientX;
      this.heroGroup.rotation.y += deltaX * 0.008;
    };
    this.bound.pointerup = (event) => {
      if (event.pointerId === this.pointer.id) this.pointer.active = false;
    };
    element.addEventListener("pointerdown", this.bound.pointerdown);
    element.addEventListener("pointermove", this.bound.pointermove);
    element.addEventListener("pointerup", this.bound.pointerup);
    element.addEventListener("pointercancel", this.bound.pointerup);
  }

  resize() {
    if (!this.renderer || !this.camera) return;
    const rect = this.container.getBoundingClientRect();
    const width = Math.max(1, Math.floor(rect.width));
    const height = Math.max(1, Math.floor(rect.height));
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.camera.position.set(6.8, 3.2, 8.8);
    this.camera.lookAt(0, 2.3, 0);
  }

  startLoop() {
    this.clock.start();
    const frame = () => {
      if (this.status !== "ready" || !this.renderer) return;
      const delta = Math.min(this.clock.getDelta(), 0.05);
      this.appearanceAdapter?.update(delta);
      this.renderer.render(this.scene, this.camera);
      this.raf = requestAnimationFrame(frame);
    };
    this.raf = requestAnimationFrame(frame);
  }

  getDiagnostics() {
    return {
      contract_version: FORMAL_3D_CONTRACT,
      status: this.status,
      reason: this.reason,
      server_character_key: this.characterSelection?.character_key || characterKeyFromAuthority(this.authority),
      character_asset_id: this.characterSelection?.character_asset_id || null,
      visual_model_id: this.characterSelection?.visual_model_id || null,
      variant: this.characterSelection?.variant || null,
      runtime_glb: this.characterSelection?.runtime_glb || null,
      main_hand: this.currentMainHand,
      off_hand: this.currentOffHand,
      appearances: { ...this.currentAppearances },
      server_appearance_item_ids: { ...this.serverAppearanceItemIds },
      sockets: Object.fromEntries(Object.entries(this.sockets).map(([slot, socket]) => [slot, {
        name: socket.name,
        bone: socket.userData.bone || null,
        fallback: socket.userData.fallback === true,
      }])),
      switch_counts: { ...this.switchCounts },
      model_request_count: this.modelRequests.length,
      model_requests: this.modelRequests.map((request) => request.key),
      renderer_count: Formal3DCharacterEquipmentRuntime.activeRendererCount,
      preview_only: this.previewOnly,
      preview_mutates_ownership: false,
      preview_mutates_inventory: false,
      preview_mutates_equipment: false,
      production_off_hand_flag: false,
      attachment_host_contract: FORMAL_3D_ATTACHMENT_HOST_CONTRACT,
      appearance_adapter_contract: PLAYER_APPEARANCE_3D_ATTACHMENT_CONTRACT,
      appearance_status: this.appearanceStatus,
      appearance_error: this.appearanceError,
      pet_companion: this.petId,
      lifecycle_counts: { ...this.lifecycleCounts },
      character_swap_count: this.characterSwapCount,
      timings_ms: { ...this.timings },
      performance_observation: "timings_only; FPS_NOT_MEASURED; native_iPad_NOT_VERIFIED",
    };
  }

  emit() {
    this.updateControls();
    const diagnostics = this.getDiagnostics();
    const panel = this.container.closest("[data-formal-3d-panel]");
    if (panel) {
      panel.dataset.formal3dState = diagnostics.status;
      const status = panel.querySelector("[data-formal-3d-status]");
      if (status) {
        status.textContent = diagnostics.status === "ready"
          ? `${diagnostics.server_character_key} · ${diagnostics.main_hand || "no main hand"} · ${diagnostics.off_hand || "no shield"}`
          : (diagnostics.reason || diagnostics.status);
      }
      const authority = panel.querySelector("[data-formal-3d-authority]");
      if (authority) authority.textContent = diagnostics.server_character_key || "unavailable";
    }
    this.onStateChange(diagnostics);
    return diagnostics;
  }

  dispose({ emit = true } = {}) {
    const started = monotonicNow();
    this.lifecycleCounts.unmount += 1;
    cancelAnimationFrame(this.raf);
    this.resizeObserver?.disconnect();
    if (this.bound.resize) window.removeEventListener("resize", this.bound.resize);
    const canvas = this.renderer?.domElement;
    if (canvas) {
      canvas.removeEventListener("pointerdown", this.bound.pointerdown);
      canvas.removeEventListener("pointermove", this.bound.pointermove);
      canvas.removeEventListener("pointerup", this.bound.pointerup);
      canvas.removeEventListener("pointercancel", this.bound.pointerup);
    }
    this.appearanceAdapter?.dispose();
    this.appearanceAdapter = null;
    this.clearCompanion();
    const geometries = new Set();
    const materials = new Set();
    const textures = new Set();
    this.gltfCache.forEach((promise) => {
      promise.then((gltf) => disposeObject(gltf.scene, geometries, materials, textures)).catch(() => {});
    });
    this.scene?.traverse((node) => {
      if (node === this.scene || node === this.renderer?.domElement) return;
      if (node.isMesh && node.geometry && !geometries.has(node.geometry)) {
        geometries.add(node.geometry);
        node.geometry.dispose();
      }
      if (node.isMesh) {
        const materialsToDispose = Array.isArray(node.material) ? node.material : [node.material];
        materialsToDispose.filter(Boolean).forEach((material) => {
          if (!materials.has(material)) {
            materials.add(material);
            disposeMaterial(material, textures);
          }
        });
      }
    });
    if (this.renderer) {
      this.renderer.renderLists.dispose();
      this.renderer.dispose();
      this.renderer.domElement.remove();
      Formal3DCharacterEquipmentRuntime.activeRendererCount = Math.max(
        0,
        Formal3DCharacterEquipmentRuntime.activeRendererCount - 1,
      );
    }
    this.renderer = null;
    this.sockets = {};
    this.heroRoot = null;
    this.petRoot = null;
    this.timings.unmount_ms = Math.round(monotonicNow() - started);
    this.status = "disposed";
    if (emit) this.emit();
  }

  unmount(options = {}) {
    return this.dispose(options);
  }
}

export async function mountShared3DPreview(container, payload = {}) {
  const options = isRecord(payload?.options)
    ? { ...payload.options, ...payload }
    : payload;
  const runtime = new Formal3DCharacterEquipmentRuntime(container, options);
  await runtime.mount();
  return runtime;
}

export function getShared3DPreviewContract() {
  return {
    ...FORMAL_3D_SHARED_PREVIEW_CONTRACT,
    supported_slots: [...FORMAL_3D_SHARED_PREVIEW_CONTRACT.supported_slots],
    supported_weapon_classes: [...FORMAL_3D_SHARED_PREVIEW_CONTRACT.supported_weapon_classes],
    supported_off_hand_classes: [...FORMAL_3D_SHARED_PREVIEW_CONTRACT.supported_off_hand_classes],
    lifecycle: [...FORMAL_3D_SHARED_PREVIEW_CONTRACT.lifecycle],
    unsupported_reasons: { ...FORMAL_3D_SHARED_PREVIEW_CONTRACT.unsupported_reasons },
  };
}

export async function mountFormal3DPreview(container, options = {}) {
  return mountShared3DPreview(container, { ...options, previewOnly: true });
}

export async function mountFormal3DFromHero({ panel, viewport, authorityProvider, initialEquipment = {}, onStateChange } = {}) {
  if (!panel || !viewport) return null;
  const runtime = new Formal3DCharacterEquipmentRuntime(viewport, {
    authorityProvider,
    initialEquipment,
    onStateChange,
    previewOnly: false,
  });
  try {
    await runtime.mount();
    if (runtime.status === "ready") {
      panel.hidden = false;
      panel.setAttribute("aria-hidden", "false");
    } else {
      panel.hidden = true;
      panel.setAttribute("aria-hidden", "true");
    }
  } catch (error) {
    panel.hidden = true;
    panel.setAttribute("aria-hidden", "true");
    panel.dataset.formal3dState = "unavailable";
    if (typeof onStateChange === "function") onStateChange(runtime.getDiagnostics());
    // Keep the legacy Hero projection usable when a 3D asset is unavailable.
    console.warn("Formal 3D Hero presentation is unavailable", error);
  }
  return runtime;
}

if (typeof window !== "undefined") {
  window.GoOdysseyFormal3D = Object.freeze({
    contract: FORMAL_3D_CONTRACT,
    attachmentHostContract: FORMAL_3D_ATTACHMENT_HOST_CONTRACT,
    sharedPreviewContract: FORMAL_3D_SHARED_PREVIEW_CONTRACT,
    mountShared3DPreview,
    getShared3DPreviewContract,
    mountFormal3DPreview,
    resolveFormalCharacterAuthority,
    validateFormal3DManifest,
  });
}
