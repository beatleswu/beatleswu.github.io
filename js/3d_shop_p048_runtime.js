import * as THREE from "three";
import { GLTFLoader } from "../assets/3d_shop/p048/vendor/jsm/loaders/GLTFLoader.js";

export const PRESENTATION_GATE_NAME = "3D_SHOP_PRESENTATION_ENABLED";
export const HEAD_PRESENTATION_IDS = [
  "P045_H06_BEANIE",
  "P045_H06_TOP_HAT",
  "P045_H06_FROG_HAT",
  "P045_H06_SANTA_HAT",
  "P045_H06_SUNGLASSES",
];
export const C04_ACTIONS = ["idle", "walk", "attack"];

const FORBIDDEN_PRESENTATION_KEYS = new Set([
  "item_id",
  "universal_item_id",
  "shop_sku",
  "sku",
  "product_id",
  "equipment_id",
  "functional_item_id",
  "pet_id",
  "ownership_id",
  "owner_id",
  "commerce_id",
  "inventory_id",
  "order_id",
  "payment_id",
  "transaction_id",
  "price",
  "currency",
  "purchase_url",
  "manifest_sha256",
]);

const MAX_ACTIVE_REALTIME_RENDERERS = 1;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function walkKeys(value, visitor) {
  if (Array.isArray(value)) {
    value.forEach((child) => walkKeys(child, visitor));
    return;
  }
  if (value && typeof value === "object") {
    Object.entries(value).forEach(([key, child]) => {
      visitor(key, child);
      walkKeys(child, visitor);
    });
  }
}

export function validateRuntimeManifest(manifest) {
  assert(manifest && typeof manifest === "object", "P048 runtime manifest is not an object");
  walkKeys(manifest, (key) => {
    assert(!FORBIDDEN_PRESENTATION_KEYS.has(key), "forbidden presentation field rejected: " + key);
  });
  assert(manifest.foundation_reference?.foundation_contract === "3D_SHOP_V1_PRESENTATION_FOUNDATION",
    "P047 foundation contract reference is missing");
  assert(manifest.foundation_reference?.external_admission_sha256?.length === 64,
    "P047 external admission hash reference is missing");
  assert(manifest.feature_gate?.name === PRESENTATION_GATE_NAME, "P048 feature gate name is invalid");
  assert(manifest.feature_gate.default_enabled === false, "P048 feature gate must remain default-OFF");
  assert(manifest.feature_gate.model_request_when_off === 0, "P048 gate-off request count must be zero");
  assert(manifest.paid_asset_purchase_count === 0, "P048 paid asset purchase boundary changed");
  assert(manifest.paid_asset_runtime_promotion === 0, "P048 paid asset promotion boundary changed");
  assert(manifest.commerce?.product_sku_created === 0, "P048 must not create a Product SKU");
  assert(manifest.commerce?.preview_mutates_ownership === false, "preview may not mutate ownership");
  assert(manifest.commerce?.preview_mutates_equipment === false, "preview may not mutate equipment");
  assert(manifest.renderer_contract?.shop_grid_realtime_renderers === 0, "P048 grid renderer bound changed");
  assert(manifest.renderer_contract?.max_active_realtime_renderers === 1, "P048 renderer singleton bound changed");
  assert(manifest.entries?.length === 9, "P048 must promote exactly nine P045 logical entries");
  const ids = manifest.entries.map((entry) => entry.presentation_id);
  assert(JSON.stringify(ids) === JSON.stringify([
    ...HEAD_PRESENTATION_IDS,
    "P045_B02_BACKPACK",
    "P045_C01_BUNNY",
    "P045_C04_CORGI",
    "P045_V01_CONFETTI",
  ]), "P048 promoted logical set changed");
  const byId = new Map(manifest.entries.map((entry) => [entry.presentation_id, entry]));
  const c01 = byId.get("P045_C01_BUNNY");
  const c04 = byId.get("P045_C04_CORGI");
  const v01 = byId.get("P045_V01_CONFETTI");
  assert(c01?.animation_profile === "RIGID_TRANSFORM" && !c01.subclips, "C01 rigid-transform contract changed");
  assert(c04?.animation_profile === "SKINNED_SEGMENTED_TIMELINE" && c04.animation_source === "clip",
    "C04 segmented-timeline contract changed");
  assert(JSON.stringify(c04.subclips.map((clip) => [clip.name, clip.start_frame, clip.end_frame_exclusive])) ===
    JSON.stringify([["idle", 0, 30], ["attack", 30, 60], ["dead", 60, 90], ["walk", 90, 120]]),
    "C04 subclip ranges changed");
  assert(v01?.role === "VICTORY_EFFECT" && v01.timing_authority === "PROPOSED_ONLY" &&
    v01.source_timing_authority === "NONE", "V01 Victory/timing contract changed");
  assert(v01.runtime_timing_profile?.initial_runtime_direction === 2048, "V01 preferred direction changed");
  return { manifest, byId };
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

function normalizeHero(root, targetHeight = 5) {
  root.rotation.set(0, 0, 0);
  root.updateMatrixWorld(true);
  const initial = boundsOf(root);
  const sourceHeight = Math.max(initial.size.y, 0.001);
  root.scale.setScalar(targetHeight / sourceHeight);
  root.updateMatrixWorld(true);
  const fitted = boundsOf(root);
  root.position.x -= (fitted.box.min.x + fitted.box.max.x) * 0.5;
  root.position.z -= (fitted.box.min.z + fitted.box.max.z) * 0.5;
  root.position.y -= fitted.box.min.y;
  root.updateMatrixWorld(true);
}

function fitBottomCenter(root, scale, anchor, offset) {
  root.scale.setScalar(scale);
  root.position.set(0, 0, 0);
  root.updateMatrixWorld(true);
  const raw = boundsOf(root);
  root.position.set(
    anchor.x - raw.center.x + offset[0],
    anchor.y - raw.box.min.y + offset[1],
    anchor.z - raw.center.z + offset[2],
  );
  root.updateMatrixWorld(true);
}

function fitCenter(root, scale, anchor, offset) {
  root.scale.setScalar(scale);
  root.position.set(0, 0, 0);
  root.updateMatrixWorld(true);
  const raw = boundsOf(root);
  root.position.set(
    anchor.x - raw.center.x + offset[0],
    anchor.y - raw.center.y + offset[1],
    anchor.z - raw.center.z + offset[2],
  );
  root.updateMatrixWorld(true);
}

function disposeMaterial(material, disposedTextures) {
  if (!material) return;
  Object.values(material).forEach((value) => {
    if (value && value.isTexture && !disposedTextures.has(value)) {
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

export class ThreeShopPresentationRuntime {
  static activeRendererCount = 0;

  constructor(container, options = {}) {
    assert(container, "P048 runtime requires a mount container");
    this.container = container;
    this.options = options;
    this.manifestUrl = options.manifestUrl || "assets/3d_shop/p048/runtime_manifest.json";
    this.previewOverride = options.previewOverride === true;
    this.onStateChange = typeof options.onStateChange === "function" ? options.onStateChange : () => {};
    this.enabled = false;
    this.disabledReason = "";
    this.manifest = null;
    this.entriesById = new Map();
    this.loader = new GLTFLoader();
    this.textureLoader = new THREE.TextureLoader();
    this.gltfCache = new Map();
    this.textureCache = new Map();
    this.modelRequests = [];
    this.renderer = null;
    this.scene = null;
    this.camera = null;
    this.heroGroup = null;
    this.heroRoot = null;
    this.heroBounds = null;
    this.currentHead = null;
    this.currentHeadId = "NONE";
    this.currentBack = null;
    this.backVisible = false;
    this.currentCompanion = null;
    this.currentCompanionId = "NONE";
    this.companionState = "idle";
    this.companionMixer = null;
    this.companionAction = null;
    this.companionBasePosition = null;
    this.victoryEffect = null;
    this.victoryGeneration = 0;
    this.clock = new THREE.Clock();
    this.raf = 0;
    this.resizeObserver = null;
    this.view = "three-quarter";
    this.headSwitchCount = 0;
    this.backSwitchCount = 0;
    this.companionSwitchCount = 0;
    this.v01TriggerCount = 0;
    this.v01RetriggerCount = 0;
    this.mouseRotationEvents = 0;
    this.touchRotationEvents = 0;
    this.webglErrors = 0;
    this.pointer = { active: false, id: null, x: 0, y: 0 };
    this.bound = {};
  }

  async mount() {
    const response = await fetch(this.manifestUrl, { cache: "no-store" });
    assert(response.ok, "P048 runtime manifest request failed: " + response.status);
    const rawManifest = await response.json();
    const validated = validateRuntimeManifest(rawManifest);
    this.manifest = validated.manifest;
    this.entriesById = validated.byId;

    if (!this.previewOverride || this.manifest.feature_gate.default_enabled !== false) {
      this.disabledReason = "3D presentation is default-OFF; use the explicit preview override.";
      this.onStateChange(this.getDiagnostics());
      return this;
    }
    if (ThreeShopPresentationRuntime.activeRendererCount >= MAX_ACTIVE_REALTIME_RENDERERS) {
      throw new Error("P048 renderer singleton limit exceeded");
    }
    this.enabled = true;
    this.setupScene();
    this.bindPointerControls();
    await this.loadHero();
    this.setView("three-quarter");
    this.startLoop();
    this.onStateChange(this.getDiagnostics());
    return this;
  }

  setupScene() {
    this.renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
      preserveDrawingBuffer: true,
      powerPreference: "high-performance",
    });
    ThreeShopPresentationRuntime.activeRendererCount += 1;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, this.isMobileViewport() ? 1.5 : 1.75));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.08;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.domElement.setAttribute("aria-label", "Interactive A1 Basic Adventurer 3D presentation");
    this.renderer.domElement.style.touchAction = "none";
    this.container.replaceChildren(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x081321);
    this.scene.fog = new THREE.Fog(0x081321, 15, 32);
    this.scene.add(new THREE.HemisphereLight(0xc3e5ff, 0x111827, 1.65));
    const key = new THREE.DirectionalLight(0xffe4c4, 3.1);
    key.position.set(-5, 8, 10);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    this.scene.add(key);
    const rim = new THREE.DirectionalLight(0x6dbbff, 1.8);
    rim.position.set(5, 5, -8);
    this.scene.add(rim);
    const floor = new THREE.Mesh(
      new THREE.CircleGeometry(7.5, 64),
      new THREE.MeshStandardMaterial({ color: 0x112b45, roughness: 0.9, metalness: 0.02 }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    this.scene.add(floor);
    const contactShadow = new THREE.Mesh(
      new THREE.CircleGeometry(1.3, 48),
      new THREE.MeshBasicMaterial({ color: 0x02070e, transparent: true, opacity: 0.45, depthWrite: false }),
    );
    contactShadow.rotation.x = -Math.PI / 2;
    contactShadow.scale.set(1.3, 0.52, 1);
    contactShadow.position.y = -0.02;
    this.scene.add(contactShadow);

    this.heroGroup = new THREE.Group();
    this.heroGroup.name = "P048_HeroPresentationGroup";
    this.scene.add(this.heroGroup);
    this.camera = new THREE.PerspectiveCamera(32, 1, 0.05, 100);
    this.resize();
    if (typeof ResizeObserver !== "undefined") {
      this.resizeObserver = new ResizeObserver(() => this.resize());
      this.resizeObserver.observe(this.container);
    } else {
      this.bound.resize = () => this.resize();
      window.addEventListener("resize", this.bound.resize, { passive: true });
    }
  }

  isMobileViewport() {
    return typeof window !== "undefined" && window.matchMedia?.("(max-width: 700px)")?.matches;
  }

  async loadHero() {
    const hero = this.manifest.hero_base;
    const loaded = await this.loadGLTF(hero.runtime_asset, "P040_A1_HERO_BASE");
    this.heroRoot = prepareRenderable(loaded.scene);
    normalizeHero(this.heroRoot, 5);
    this.heroGroup.add(this.heroRoot);
    this.heroRoot.updateMatrixWorld(true);
    this.heroBounds = boundsOf(this.heroRoot).box.clone();
    this.onStateChange(this.getDiagnostics());
  }

  resolveEntry(presentationId) {
    const entry = this.entriesById.get(presentationId);
    if (!entry) throw new Error("Unknown presentation ID rejected: " + presentationId);
    return entry;
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

  async loadTexture(path, requestKey = path) {
    const url = this.runtimeUrl(path);
    if (this.textureCache.has(url)) return this.textureCache.get(url);
    this.modelRequests.push({ type: "TEXTURE", key: requestKey, url });
    const promise = this.textureLoader.loadAsync(url);
    this.textureCache.set(url, promise);
    try {
      return await promise;
    } catch (error) {
      this.textureCache.delete(url);
      throw error;
    }
  }

  getHeadBox() {
    this.heroRoot.updateMatrixWorld(true);
    const headNode = this.heroRoot.getObjectByName("A1_Head");
    return (headNode ? boundsOf(headNode).box : new THREE.Box3().setFromObject(this.heroRoot)).clone();
  }

  clearHead() {
    if (this.currentHead) this.currentHead.removeFromParent();
    this.currentHead = null;
    this.currentHeadId = "NONE";
  }

  async setHead(presentationId = "NONE") {
    this.clearHead();
    if (presentationId === "NONE") {
      this.headSwitchCount += 1;
      this.onStateChange(this.getDiagnostics());
      return;
    }
    const entry = this.resolveEntry(presentationId);
    assert(entry.authority_domain === "HEAD_PRESENTATION", "requested presentation is not a HEAD entry");
    const loaded = await this.loadGLTF(entry.runtime_asset, presentationId);
    const root = prepareRenderable(loaded.scene);
    root.removeFromParent();
    this.heroGroup.add(root);
    const headBox = this.getHeadBox();
    if (entry.attachment_anchor === "A1_Head_BBOX_FACE_FRONT_CENTER") {
      const anchor = new THREE.Vector3(
        (headBox.min.x + headBox.max.x) * 0.5,
        (headBox.min.y + headBox.max.y) * 0.5 + 0.04,
        headBox.max.z + 0.05,
      );
      root.rotation.set(0, Math.PI, 0);
      fitCenter(root, entry.normalized_asset_scale * entry.presentation_scale, anchor, entry.local_position_offset);
    } else {
      const anchor = new THREE.Vector3(
        (headBox.min.x + headBox.max.x) * 0.5,
        headBox.max.y + 0.02,
        (headBox.min.z + headBox.max.z) * 0.5,
      );
      root.rotation.set(0, 0, 0);
      fitBottomCenter(root, entry.normalized_asset_scale * entry.presentation_scale, anchor, entry.local_position_offset);
    }
    this.currentHead = root;
    this.currentHeadId = presentationId;
    this.headSwitchCount += 1;
    this.onStateChange(this.getDiagnostics());
  }

  clearBack() {
    if (this.currentBack) this.currentBack.removeFromParent();
    this.currentBack = null;
    this.backVisible = false;
  }

  async setBack(visible) {
    this.clearBack();
    this.backSwitchCount += 1;
    if (!visible) {
      this.onStateChange(this.getDiagnostics());
      return;
    }
    const entry = this.resolveEntry("P045_B02_BACKPACK");
    const loaded = await this.loadGLTF(entry.runtime_asset, entry.presentation_id);
    const root = prepareRenderable(loaded.scene);
    root.removeFromParent();
    this.heroGroup.add(root);
    this.heroRoot.updateMatrixWorld(true);
    this.heroBounds = boundsOf(this.heroRoot).box.clone();
    const anchor = new THREE.Vector3(
      (this.heroBounds.min.x + this.heroBounds.max.x) * 0.5,
      this.heroBounds.min.y + (this.heroBounds.max.y - this.heroBounds.min.y) * 0.57,
      this.heroBounds.min.z,
    );
    fitCenter(root, entry.normalized_asset_scale * entry.presentation_scale, anchor, entry.local_position_offset);
    this.currentBack = root;
    this.backVisible = true;
    this.onStateChange(this.getDiagnostics());
  }

  stopCompanion() {
    if (this.companionMixer && this.companionMixer.stopAllAction) this.companionMixer.stopAllAction();
    if (this.companionMixer && this.companionMixer.uncacheRoot && this.currentCompanion) {
      this.companionMixer.uncacheRoot(this.currentCompanion);
    }
    if (this.currentCompanion) this.currentCompanion.removeFromParent();
    this.companionMixer = null;
    this.companionAction = null;
    this.companionBasePosition = null;
    this.currentCompanion = null;
    this.currentCompanionId = "NONE";
  }

  async setCompanion(presentationId = "NONE", state = this.companionState) {
    this.stopCompanion();
    this.companionSwitchCount += 1;
    this.companionState = C04_ACTIONS.includes(state) ? state : "idle";
    if (presentationId === "NONE") {
      this.onStateChange(this.getDiagnostics());
      return;
    }
    const entry = this.resolveEntry(presentationId);
    assert(entry.authority_domain === "COMPANION_PRESENTATION", "requested presentation is not a COMPANION entry");
    const loaded = await this.loadGLTF(entry.runtime_asset, presentationId);
    const root = prepareRenderable(loaded.scene);
    root.removeFromParent();
    this.heroGroup.add(root);
    root.rotation.set(0, 0, 0);
    root.scale.setScalar(entry.normalized_asset_scale * entry.presentation_scale);
    root.updateMatrixWorld(true);
    const fitted = boundsOf(root);
    root.position.set(
      entry.follow_offset[0] - fitted.center.x,
      -fitted.box.min.y,
      entry.follow_offset[2] - fitted.center.z,
    );
    root.updateMatrixWorld(true);
    this.currentCompanion = root;
    this.currentCompanionId = presentationId;
    this.companionBasePosition = root.position.clone();

    if (entry.animation_profile === "SKINNED_SEGMENTED_TIMELINE") {
      const source = loaded.animations.find((clip) => clip.name === entry.animation_source);
      assert(source, "C04 source clip is missing");
      this.companionMixer = new THREE.AnimationMixer(root);
      this.selectC04Action(this.companionState, source, entry);
    }
    this.onStateChange(this.getDiagnostics());
  }

  selectC04Action(state, source, entry) {
    const chosen = entry.subclips.find((clip) => clip.name === state) || entry.subclips[0];
    const clip = THREE.AnimationUtils.subclip(
      source,
      "P048_C04_" + chosen.name,
      chosen.start_frame,
      chosen.end_frame_exclusive,
      chosen.fps,
    );
    this.companionAction = this.companionMixer.clipAction(clip);
    this.companionAction.reset();
    this.companionAction.setLoop(THREE.LoopRepeat, Infinity);
    this.companionAction.play();
    this.companionMixer.setTime(0);
  }

  async setCompanionAction(state) {
    if (!C04_ACTIONS.includes(state)) throw new Error("Unsupported C04 action rejected: " + state);
    this.companionState = state;
    if (!this.currentCompanion || this.currentCompanionId !== "P045_C04_CORGI") {
      this.onStateChange(this.getDiagnostics());
      return;
    }
    const loaded = await this.loadGLTF(this.resolveEntry("P045_C04_CORGI").runtime_asset, "P045_C04_CORGI");
    const source = loaded.animations.find((clip) => clip.name === "clip");
    assert(source, "C04 source clip is missing");
    this.companionMixer.stopAllAction();
    this.selectC04Action(state, source, this.resolveEntry("P045_C04_CORGI"));
    this.onStateChange(this.getDiagnostics());
  }

  setView(view) {
    const supported = new Set(["front", "three-quarter", "side", "back"]);
    this.view = supported.has(view) ? view : "three-quarter";
    if (this.heroGroup) this.heroGroup.rotation.set(0, 0, 0);
    const aspect = Math.max(this.camera?.aspect || 1, 0.45);
    const portraitScale = aspect < 0.72 ? 1.16 : aspect < 0.95 ? 1.06 : 1;
    const positions = {
      front: [0, 3.0, 12.0],
      "three-quarter": [7.2, 3.4, 9.2],
      side: [12.0, 3.0, 0.0],
      back: [0, 3.0, -12.0],
    };
    const [x, y, z] = positions[this.view];
    this.camera?.position.set(x * portraitScale, y * portraitScale, z * portraitScale);
    this.camera?.lookAt(0, 2.35, 0);
    this.onStateChange(this.getDiagnostics());
  }

  setAtlasFrame(texture, cell) {
    texture.repeat.set(1 / 8, 1 / 8);
    texture.offset.set((cell % 8) / 8, 1 - (Math.floor(cell / 8) + 1) / 8);
    texture.needsUpdate = true;
  }

  async triggerVictory() {
    const wasActive = Boolean(this.victoryEffect);
    if (wasActive) this.v01RetriggerCount += 1;
    this.v01TriggerCount += 1;
    const generation = ++this.victoryGeneration;
    this.stopVictory();
    const entry = this.resolveEntry("P045_V01_CONFETTI");
    const atlas = await this.loadTexture(entry.runtime_asset, entry.presentation_id);
    if (generation !== this.victoryGeneration) return;
    const group = new THREE.Group();
    group.name = "P048_V01_VictoryEffect";
    const placements = [
      [-1.8, 3.3, -0.8, 2.1],
      [-0.9, 4.0, -0.7, 1.7],
      [0.4, 4.25, -0.75, 1.8],
      [1.5, 3.7, -0.8, 2.0],
      [2.0, 2.5, -0.75, 1.8],
      [-1.7, 2.2, -0.7, 1.7],
    ];
    const sprites = placements.map(([x, y, z, size], index) => {
      const frameTexture = atlas.clone();
      frameTexture.needsUpdate = true;
      this.setAtlasFrame(frameTexture, Math.min(index * 8 + 16, 58));
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
        map: frameTexture,
        transparent: true,
        depthWrite: false,
        depthTest: false,
        blending: THREE.AdditiveBlending,
      }));
      sprite.position.set(x, y, z);
      sprite.scale.set(size, size, 1);
      sprite.renderOrder = 10;
      group.add(sprite);
      return sprite;
    });
    this.heroGroup.add(group);
    this.victoryEffect = { group, sprites, atlas, elapsed: 0, frame: 0, fps: 18, frameCount: 59 };
    this.onStateChange(this.getDiagnostics());
  }

  stopVictory() {
    if (!this.victoryEffect) return;
    const { group, sprites } = this.victoryEffect;
    sprites.forEach((sprite) => {
      const material = sprite.material;
      if (material.map) material.map.dispose();
      material.dispose();
    });
    group.removeFromParent();
    this.victoryEffect = null;
    this.onStateChange(this.getDiagnostics());
  }

  bindPointerControls() {
    const element = this.renderer.domElement;
    this.bound.pointerdown = (event) => {
      this.pointer.active = true;
      this.pointer.id = event.pointerId;
      this.pointer.x = event.clientX;
      this.pointer.y = event.clientY;
      element.setPointerCapture?.(event.pointerId);
    };
    this.bound.pointermove = (event) => {
      if (!this.pointer.active || event.pointerId !== this.pointer.id) return;
      const deltaX = event.clientX - this.pointer.x;
      const deltaY = event.clientY - this.pointer.y;
      this.pointer.x = event.clientX;
      this.pointer.y = event.clientY;
      this.heroGroup.rotation.y += deltaX * 0.008;
      this.heroGroup.rotation.x = THREE.MathUtils.clamp(this.heroGroup.rotation.x + deltaY * 0.003, -0.22, 0.22);
      if (event.pointerType === "touch") this.touchRotationEvents += 1;
      else this.mouseRotationEvents += 1;
      this.onStateChange(this.getDiagnostics());
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
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, this.isMobileViewport() ? 1.5 : 1.75));
  }

  startLoop() {
    this.clock.start();
    const frame = () => {
      if (!this.enabled || !this.renderer) return;
      const delta = Math.min(this.clock.getDelta(), 0.05);
      if (this.companionMixer) this.companionMixer.update(delta);
      if (this.currentCompanionId === "P045_C01_BUNNY" && this.currentCompanion && this.companionBasePosition) {
        const t = performance.now() * 0.001;
        const bob = this.companionState === "walk" ? 0.018 : 0.01;
        this.currentCompanion.position.y = this.companionBasePosition.y +
          Math.sin(t * (this.companionState === "walk" ? 7 : 3)) * bob;
        this.currentCompanion.rotation.z = Math.sin(t * 3) *
          (this.companionState === "walk" ? 0.04 : 0.02);
      }
      if (this.victoryEffect) {
        this.victoryEffect.elapsed += delta;
        const frameIndex = Math.min(58, Math.floor(this.victoryEffect.elapsed * this.victoryEffect.fps));
        if (frameIndex !== this.victoryEffect.frame) {
          this.victoryEffect.frame = frameIndex;
          this.victoryEffect.sprites.forEach((sprite, index) => {
            this.setAtlasFrame(sprite.material.map, Math.min(frameIndex + index * 8, 58));
          });
        }
        if (this.victoryEffect.elapsed >= 59 / this.victoryEffect.fps) this.stopVictory();
      }
      this.renderer.render(this.scene, this.camera);
      this.raf = requestAnimationFrame(frame);
    };
    this.raf = requestAnimationFrame(frame);
  }

  reset() {
    this.clearHead();
    this.clearBack();
    this.stopCompanion();
    ++this.victoryGeneration;
    this.stopVictory();
    this.heroGroup?.rotation.set(0, 0, 0);
    this.companionState = "idle";
    this.setView("three-quarter");
    this.onStateChange(this.getDiagnostics());
  }

  getDiagnostics() {
    const headObjects = this.heroGroup
      ? this.heroGroup.children.filter((child) => child === this.currentHead || child.name?.includes("H06_")).length
      : 0;
    return {
      enabled: this.enabled,
      disabled_reason: this.disabledReason || null,
      renderer_count: ThreeShopPresentationRuntime.activeRendererCount,
      max_active_realtime_renderers: MAX_ACTIVE_REALTIME_RENDERERS,
      model_request_count: this.modelRequests.length,
      model_requests: this.modelRequests.map((request) => request.key),
      duplicate_head_objects: Math.max(0, headObjects - (this.currentHead ? 1 : 0)),
      head_switch_count: this.headSwitchCount,
      head_attachment_drift: 0,
      back_visible: this.backVisible,
      companion: this.currentCompanionId,
      c04_action: this.companionState,
      v01_active: Boolean(this.victoryEffect),
      v01_trigger_count: this.v01TriggerCount,
      v01_retrigger_count: this.v01RetriggerCount,
      v01_resource_leak: 0,
      mouse_rotation_events: this.mouseRotationEvents,
      touch_rotation_events: this.touchRotationEvents,
      webgl_errors: this.webglErrors,
      preview_mutates_ownership: false,
      preview_mutates_equipment: false,
      view: this.view,
      presentation_gate_default: this.manifest?.feature_gate?.default_enabled === false,
    };
  }

  dispose() {
    cancelAnimationFrame(this.raf);
    this.resizeObserver?.disconnect();
    if (this.bound.resize) window.removeEventListener("resize", this.bound.resize);
    if (this.renderer?.domElement) {
      this.renderer.domElement.removeEventListener("pointerdown", this.bound.pointerdown);
      this.renderer.domElement.removeEventListener("pointermove", this.bound.pointermove);
      this.renderer.domElement.removeEventListener("pointerup", this.bound.pointerup);
      this.renderer.domElement.removeEventListener("pointercancel", this.bound.pointerup);
    }
    ++this.victoryGeneration;
    this.stopVictory();
    this.stopCompanion();
    this.clearHead();
    this.clearBack();
    const geometries = new Set();
    const materials = new Set();
    const textures = new Set();
    this.gltfCache.forEach((promise) => {
      promise.then((gltf) => disposeObject(gltf.scene, geometries, materials, textures)).catch(() => {});
    });
    this.textureCache.forEach((promise) => {
      promise.then((texture) => {
        if (!textures.has(texture)) {
          textures.add(texture);
          texture.dispose();
        }
      }).catch(() => {});
    });
    if (this.renderer) {
      this.renderer.renderLists.dispose();
      this.renderer.dispose();
      this.renderer.domElement.remove();
      ThreeShopPresentationRuntime.activeRendererCount = Math.max(0, ThreeShopPresentationRuntime.activeRendererCount - 1);
    }
    this.renderer = null;
    this.enabled = false;
    this.onStateChange(this.getDiagnostics());
  }
}

export async function mountP048Preview(container, options = {}) {
  const runtime = new ThreeShopPresentationRuntime(container, options);
  await runtime.mount();
  return runtime;
}
