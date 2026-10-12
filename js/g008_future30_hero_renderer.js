import * as THREE from "/assets/3d_shop/p048/vendor/three.module.js";
// Temporary G009 N20/N25 local-HTTP iPad UAT SHA-256 compatibility helper.
// FIPS 180-4 SHA-256, not a checksum bypass. Only the task-owned preview uses this module.
// Preserve equality against canonical runtime_sha256 in the original renderer.
const ROUND_CONSTANTS = new Uint32Array([1116352408,1899447441,3049323471,3921009573,961987163,1508970993,2453635748,2870763221,3624381080,310598401,607225278,1426881987,1925078388,2162078206,2614888103,3248222580,3835390401,4022224774,264347078,604807628,770255983,1249150122,1555081692,1996064986,2554220882,2821834349,2952996808,3210313671,3336571891,3584528711,113926993,338241895,666307205,773529912,1294757372,1396182291,1695183700,1986661051,2177026350,2456956037,2730485921,2820302411,3259730800,3345764771,3516065817,3600352804,4094571909,275423344,430227734,506948616,659060556,883997877,958139571,1322822218,1537002063,1747873779,1955562222,2024104815,2227730452,2361852424,2428436474,2756734187,3204031479,3329325298]);
const INITIAL_STATE = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
const rotateRight = (v, n) => (v >>> n) | (v << (32 - n));
function sha256Hex(input) {
  const bytes = input instanceof Uint8Array ? input : new Uint8Array(input);
  const paddedLength = Math.ceil((bytes.length + 9) / 64) * 64;
  const padded = new Uint8Array(paddedLength);
  padded.set(bytes);
  padded[bytes.length] = 0x80;
  const view = new DataView(padded.buffer);
  view.setUint32(paddedLength - 8, Math.floor(bytes.length / 0x20000000), false);
  view.setUint32(paddedLength - 4, (bytes.length * 8) >>> 0, false);
  const state = INITIAL_STATE.slice();
  const words = new Uint32Array(64);
  for (let offset = 0; offset < paddedLength; offset += 64) {
    for (let i = 0; i < 16; i++) words[i] = view.getUint32(offset + i * 4, false);
    for (let i = 16; i < 64; i++) {
      const x = words[i - 15], y = words[i - 2];
      const s0 = rotateRight(x, 7) ^ rotateRight(x, 18) ^ (x >>> 3);
      const s1 = rotateRight(y, 17) ^ rotateRight(y, 19) ^ (y >>> 10);
      words[i] = (words[i - 16] + s0 + words[i - 7] + s1) >>> 0;
    }
    let [a,b,c,d,e,f,g,h] = state;
    for (let i = 0; i < 64; i++) {
      const sumE = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
      const choose = (e & f) ^ (~e & g);
      const temp1 = (h + sumE + choose + ROUND_CONSTANTS[i] + words[i]) >>> 0;
      const sumA = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22);
      const majority = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (sumA + majority) >>> 0;
      h = g; g = f; f = e; e = (d + temp1) >>> 0;
      d = c; c = b; b = a; a = (temp1 + temp2) >>> 0;
    }
    for (const [i,value] of [a,b,c,d,e,f,g,h].entries()) {
      state[i] = (state[i] + value) >>> 0;
    }
  }
  return state.map(x => x.toString(16).padStart(8, "0")).join("");
}
import { GLTFLoader } from "/assets/3d_shop/p048/vendor/jsm/loaders/GLTFLoader.js";
import {
  createG009SharedHeroAttachmentHost,
  G009_HERO_PRESENTATION_SLOTS,
} from "./g009_shared_hero_attachment_host.js";

const EXPECTED_C005_MANIFEST_SHA256 =
  "35746c1168152cbd3fd166fd0ba5a319f3bf1ba8916fed3a8669f487a2a83c1d";
const ACCEPTED_FUTURE30_ACQUISITION_SOURCES = new Set([
  "STARTER",
  "STAGE",
  "PREMIUM",
  "SHOP",
  "ACCEPTANCE_TEST",
]);
export const HERO_PRESENTATION_SLOTS = G009_HERO_PRESENTATION_SLOTS;
let stage = null;
let avatar = null;

// This module alone owns the G008 Hero canvas. P048 remains a Shop preview.
let generation = 0;
let pending = null;
let controller = null;
let ownedRoot = null;
let ownedRenderer = null;
let sharedAttachmentHost = null;
let sharedAttachmentFacade = null;
let serverAppearance = null;
const slotResolvers = new Map();
const presentationRehydrators = new Map();
const presentationTeardowns = new Map();
const rehydratedGenerationByKey = new Map();
let cancelFrameWait = null;

function assertPresentationSlot(slot) {
  if (!HERO_PRESENTATION_SLOTS.includes(slot)) {
    throw new Error("unknown_hero_presentation_slot:" + String(slot));
  }
}

function createAttachmentFacade(host) {
  return Object.freeze({
    slots: HERO_PRESENTATION_SLOTS,
    attach(slot, presentationId, loadNode) {
      if (sharedAttachmentHost !== host) throw new Error("stale_hero_attachment_host_handle");
      return host.attach(slot, presentationId, loadNode);
    },
    detach(slot) {
      if (sharedAttachmentHost !== host) {
        assertPresentationSlot(slot);
        return { status: "stale_host", slot };
      }
      return host.detach(slot);
    },
    diagnostics() {
      return host.diagnostics();
    },
    getSlotLayout(slot) {
      if (sharedAttachmentHost !== host) throw new Error("stale_hero_attachment_host_handle");
      return host.getSlotLayout(slot);
    },
  });
}

function runPresentationRehydrator(key, callback, token, appearance, force = false) {
  if (!sharedAttachmentHost || token !== generation || !appearance) {
    return Promise.resolve({ key, status: "not_ready" });
  }
  if (!force && rehydratedGenerationByKey.get(key) === token) {
    return Promise.resolve({ key, status: "already_rehydrated" });
  }
  rehydratedGenerationByKey.set(key, token);
  const host = createAttachmentFacade(sharedAttachmentHost);
  const context = Object.freeze({
    character_key: appearance.character_key,
    appearance,
    host,
    generation: token,
  });
  return Promise.resolve().then(() => callback(context)).then(
    (result) => token === generation
      ? { key, status: "rehydrated", result: result ?? null }
      : { key, status: "stale" },
    (error) => {
      if (rehydratedGenerationByKey.get(key) === token) rehydratedGenerationByKey.delete(key);
      return {
        key,
        status: token === generation ? "failed_closed" : "stale",
        reason: error instanceof Error ? error.message : String(error),
      };
    },
  );
}

export function getHeroSharedAttachmentHost() {
  return sharedAttachmentFacade;
}

// Children register cleanup inside the single Hero owner lifecycle.
export function registerHeroPresentationTeardown(key, callback) {
  if (typeof key !== "string" || !key.trim() || typeof callback !== "function") {
    throw new Error("hero_presentation_teardown_invalid");
  }
  if (presentationTeardowns.has(key) && presentationTeardowns.get(key) !== callback) {
    throw new Error("hero_presentation_teardown_already_registered:" + key);
  }
  presentationTeardowns.set(key, callback);
  return () => {
    if (presentationTeardowns.get(key) !== callback) return false;
    return presentationTeardowns.delete(key);
  };
}

export function registerHeroPresentationResolver(slot, resolver) {
  assertPresentationSlot(slot);
  if (typeof resolver !== "function") throw new Error("hero_slot_resolver_required");
  const existing = slotResolvers.get(slot);
  if (existing && existing.resolver !== resolver) {
    throw new Error("hero_slot_resolver_already_registered:" + slot);
  }
  if (existing) {
    existing.references += 1;
  } else {
    slotResolvers.set(slot, { resolver, references: 1 });
    sharedAttachmentHost?.registerResolver(slot, resolver);
  }
  let active = true;
  return () => {
    if (!active) return false;
    active = false;
    const entry = slotResolvers.get(slot);
    if (!entry || entry.resolver !== resolver) return false;
    entry.references -= 1;
    if (entry.references <= 0) {
      slotResolvers.delete(slot);
      sharedAttachmentHost?.unregisterResolver?.(slot, resolver);
    }
    return true;
  };
}

export function attachHeroChildPresentation(slot, presentationId, loadNode) {
  assertPresentationSlot(slot);
  if (!sharedAttachmentHost) throw new Error("hero_attachment_host_unavailable");
  return sharedAttachmentHost.attach(slot, presentationId, loadNode);
}

export function detachHeroChildPresentation(slot) {
  assertPresentationSlot(slot);
  if (!sharedAttachmentHost) return { status: "not_ready", slot };
  return sharedAttachmentHost.detach(slot);
}

export function registerHeroPresentationRehydrator(key, callback) {
  if (typeof key !== "string" || !key.trim() || typeof callback !== "function") {
    throw new Error("hero_presentation_rehydrator_invalid");
  }
  const existing = presentationRehydrators.get(key);
  if (existing && existing !== callback) throw new Error("hero_presentation_rehydrator_already_registered:" + key);
  presentationRehydrators.set(key, callback);
  if (sharedAttachmentHost && serverAppearance) {
    void runPresentationRehydrator(key, callback, generation, serverAppearance, true);
  }
  return () => {
    if (presentationRehydrators.get(key) !== callback) return false;
    presentationRehydrators.delete(key);
    rehydratedGenerationByKey.delete(key);
    return true;
  };
}

export async function rehydrateHeroPresentations() {
  if (!sharedAttachmentHost || !serverAppearance) return { status: "not_ready", results: [] };
  const token = generation;
  const results = await Promise.all([...presentationRehydrators].map(([key, callback]) =>
    runPresentationRehydrator(key, callback, token, serverAppearance, true)));
  return {
    status: token === generation ? "complete" : "stale",
    character_key: serverAppearance?.character_key || null,
    results,
  };
}

function isCurrent(token) {
  if (token !== generation) return false;
  if (!stage?.isConnected || stage !== document.getElementById("g008-future30-hero-stage")) {
    destroyHeroAppearance();
    return false;
  }
  return true;
}

function disposeModel(root) {
  const resources = new Set();
  root?.removeFromParent();
  root?.traverse((node) => {
    if (node.geometry) resources.add(node.geometry);
    const materials = Array.isArray(node.material) ? node.material : [node.material];
    for (const material of materials.filter(Boolean)) {
      resources.add(material);
      for (const value of Object.values(material)) {
        if (value?.isTexture) resources.add(value);
      }
    }
  });
  resources.forEach((resource) => resource.dispose());
}

function releaseOwnedResources() {
  for (const callback of presentationTeardowns.values()) {
    try { callback(); } catch (error) { console.warn("Hero child teardown failed", error); }
  }
  cancelFrameWait?.();
  cancelFrameWait = null;
  sharedAttachmentHost?.destroy();
  sharedAttachmentHost = null;
  sharedAttachmentFacade = null;
  serverAppearance = null;
  if (ownedRenderer) {
    ownedRenderer.setAnimationLoop(null);
    ownedRenderer.renderLists?.dispose();
    ownedRenderer.dispose();
    ownedRenderer.domElement.remove();
    ownedRenderer = null;
  }
  disposeModel(ownedRoot);
  ownedRoot = null;
}

export function destroyHeroAppearance() {
  generation += 1;
  controller?.abort();
  controller = null;
  pending = null;
  window.removeEventListener("pagehide", destroyHeroAppearance);
  releaseOwnedResources();
  publish({ state: "inactive" });
}

export function mountHeroAppearance() {
  if (stage && !isCurrent(generation)) pending = null;
  stage = document.getElementById("g008-future30-hero-stage");
  avatar = document.getElementById("char-avatar");
  if (pending) return pending;
  if (ownedRenderer) return Promise.resolve(window.__G008_HERO_RENDER_STATE__);
  const token = ++generation;
  controller = new AbortController();
  window.addEventListener("pagehide", destroyHeroAppearance);
  pending = activate(token, controller.signal).catch((error) => {
    if (token !== generation) return;
    releaseOwnedResources();
    fail(error instanceof Error ? error.message : "runtime_failed");
  }).finally(() => {
    if (token === generation) pending = null;
  });
  return pending;
}

// Refresh always reads the same server APIs; callers cannot supply an identity.
export function refreshHeroAppearance() {
  destroyHeroAppearance();
  return mountHeroAppearance();
}

function publish(state) {
  window.__G008_HERO_RENDER_STATE__ = Object.freeze(state);
  if (stage) stage.dataset.state = state.state;
  if (avatar) {
    if (state.state === "ready") {
      avatar.dataset.g008Future30Render = "ready";
    } else {
      delete avatar.dataset.g008Future30Render;
    }
  }
}

function fail(reason, identity = {}) {
  publish({ state: "failed", reason, ...identity });
  console.warn("Future30 Hero presentation is unavailable", reason);
}

async function sha256(buffer) {
  // Isolated LAN-HTTP iPad acceptance only: non-secure origins can lack WebCrypto.
  // The exact canonical SHA256 byte-equality guard in activate() stays mandatory.
  if (!globalThis.crypto?.subtle?.digest) return sha256Hex(buffer);
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
}

function fitModel(root) {
  root.updateMatrixWorld(true);
  let bounds = new THREE.Box3().setFromObject(root);
  const size = bounds.getSize(new THREE.Vector3());
  if (![size.x, size.y, size.z].every(Number.isFinite) || Math.max(size.x, size.y, size.z) <= 0) {
    throw new Error("model_bounds_invalid");
  }
  const height = Math.max(size.y, size.x, size.z);
  root.scale.multiplyScalar(4.1 / height);
  root.updateMatrixWorld(true);
  bounds = new THREE.Box3().setFromObject(root);
  const center = bounds.getCenter(new THREE.Vector3());
  root.position.x -= center.x;
  root.position.y -= bounds.min.y;
  root.position.z -= center.z;
  root.updateMatrixWorld(true);
  return new THREE.Box3().setFromObject(root);
}

function renderModel(root, bounds, token) {
  if (!stage) throw new Error("hero_stage_missing");
  const width = Math.max(1, Math.round(stage.clientWidth));
  const height = Math.max(1, Math.round(stage.clientHeight));
  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xf1f7ff, 0x334155, 2.0));
  const keyLight = new THREE.DirectionalLight(0xffefd5, 2.8);
  keyLight.position.set(-3, 7, 8);
  scene.add(keyLight);
  const fillLight = new THREE.DirectionalLight(0xa9d9ff, 1.1);
  fillLight.position.set(4, 3, -4);
  scene.add(fillLight);
  // Isolated preview UAT: turntable around the normalized character center.
  // The model remains the same canonical server-owned GLB with unchanged SHA checks.
  const turntable = new THREE.Group();
  turntable.add(root);
  scene.add(turntable);

  const center = bounds.getCenter(new THREE.Vector3());
  const camera = new THREE.PerspectiveCamera(34, width / height, 0.01, 100);
  camera.position.set(center.x, center.y + 0.15, center.z + 8.4);
  camera.lookAt(center.x, center.y, center.z);

  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: "low-power" });
  ownedRenderer = renderer;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(width, height, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  stage.replaceChildren(renderer.domElement);
  const canvas = renderer.domElement;
  // Optional interaction enhancement: some renderer adapters expose only a
  // minimal canvas-like object. Keep 3D/model/attachment lifecycle working,
  // and bind gestures only when the renderer supplies a real DOM event target.
  // Native browser canvases pass this check and retain the full 360-degree UI.
  if (canvas?.style && typeof canvas.addEventListener === "function"
      && typeof canvas.setAttribute === "function") {
    // Bind controls to this canvas only so page navigation/scroll works elsewhere.
  canvas.style.touchAction = "none";
  canvas.style.pointerEvents = "auto";
  canvas.style.cursor = "grab";
  canvas.tabIndex = 0;
  canvas.setAttribute("aria-label", "3D 角色模型；左右拖曳可旋轉 360 度。鍵盤左右方向鍵旋轉，Home 回正面。");
  const drag = { pointerId: null, lastX: 0, lastY: 0 };
  canvas.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    drag.pointerId = event.pointerId;
    drag.lastX = event.clientX;
    drag.lastY = event.clientY;
    canvas.style.cursor = "grabbing";
    try { canvas.setPointerCapture(event.pointerId); } catch (_) {}
    event.preventDefault();
  });
  canvas.addEventListener("pointermove", (event) => {
    if (drag.pointerId !== event.pointerId) return;
    const deltaX = event.clientX - drag.lastX;
    const deltaY = event.clientY - drag.lastY;
    drag.lastX = event.clientX;
    drag.lastY = event.clientY;
    // Full horizontal revolution; clamp vertical pitch to avoid upside-down model.
    turntable.rotation.y += deltaX * 0.012;
    turntable.rotation.x = Math.max(-Math.PI * 0.42, Math.min(Math.PI * 0.42, turntable.rotation.x + deltaY * 0.009));
    event.preventDefault();
  });
  const finishDrag = (event) => {
    if (drag.pointerId !== event.pointerId) return;
    drag.pointerId = null;
    canvas.style.cursor = "grab";
    try { if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId); } catch (_) {}
  };
  canvas.addEventListener("pointerup", finishDrag);
  canvas.addEventListener("pointercancel", finishDrag);
  canvas.addEventListener("lostpointercapture", finishDrag);
  canvas.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft") turntable.rotation.y -= Math.PI / 12;
    else if (event.key === "ArrowRight") turntable.rotation.y += Math.PI / 12;
    else if (event.key === "ArrowUp") turntable.rotation.x = Math.max(-Math.PI * 0.42, turntable.rotation.x - Math.PI / 24);
    else if (event.key === "ArrowDown") turntable.rotation.x = Math.min(Math.PI * 0.42, turntable.rotation.x + Math.PI / 24);
    else if (event.key === "Home") { turntable.rotation.y = 0; turntable.rotation.x = 0; }
    else return;
    event.preventDefault();
  });
  }

  let renderFrames = 0;
  renderer.setAnimationLoop(() => {
    if (!isCurrent(token)) return;
    const currentWidth = Math.max(1, Math.round(stage.clientWidth));
    const currentHeight = Math.max(1, Math.round(stage.clientHeight));
    if (renderer.domElement.width !== Math.round(currentWidth * renderer.getPixelRatio())
      || renderer.domElement.height !== Math.round(currentHeight * renderer.getPixelRatio())) {
      renderer.setSize(currentWidth, currentHeight, false);
      camera.aspect = currentWidth / currentHeight;
      camera.updateProjectionMatrix();
    }
    renderer.render(scene, camera);
    renderFrames += 1;
  });
  return { renderer, renderFrames: () => renderFrames };
}

async function activate(token, signal) {
  if (!stage?.isConnected || !avatar) throw new Error("hero_mount_missing");
  publish({ state: "loading" });

  const [catalogResponse, appearanceResponse] = await Promise.all([
    fetch("/api/player/character-catalog", { credentials: "include", cache: "no-store", signal }),
    fetch("/api/player/appearance", { credentials: "include", cache: "no-store", signal }),
  ]);
  if (!catalogResponse.ok) throw new Error(`catalog_http_${catalogResponse.status}`);
  if (!appearanceResponse.ok) throw new Error(`appearance_http_${appearanceResponse.status}`);
  const [catalog, appearance] = await Promise.all([
    catalogResponse.json(), appearanceResponse.json(),
  ]);
  if (!isCurrent(token)) return;

  if (catalog.c005_manifest_sha256 !== EXPECTED_C005_MANIFEST_SHA256
    || catalog.logical_count !== 30 || catalog.visual_count !== 33
    || !Array.isArray(catalog.entries) || catalog.entries.length !== 30) {
    throw new Error("catalog_authority_mismatch");
  }
  const keys = catalog.entries.map((entry) => entry.character_key);
  if (new Set(keys).size !== 30 || keys.some((key) => typeof key !== "string" || !key)) {
    throw new Error("catalog_logical_identity_mismatch");
  }

  const key = appearance.character_key;
  const entry = catalog.entries.find((candidate) => candidate.character_key === key);
  const runtime = appearance.character_runtime;
  if (!entry || appearance.character_key_source !== "player_appearance.character_key"
    || appearance.character_key_authority !== "player_appearance.character_key"
    || appearance.character_entitled !== true || entry.owned !== true || entry.is_applied !== true
    || !ACCEPTED_FUTURE30_ACQUISITION_SOURCES.has(entry.acquisition_source)
    || !runtime || runtime.character_key !== key
    || runtime.default_variant !== "RED"
    || runtime.visual_model_id !== entry.visual_model_id
    || runtime.c005_manifest_sha256 !== EXPECTED_C005_MANIFEST_SHA256
    || runtime.runtime_glb !== entry.runtime_glb
    || runtime.runtime_sha256 !== entry.runtime_sha256) {
    throw new Error("server_character_projection_mismatch");
  }
  const redModel = (entry.visual_models || []).find((model) => model.variant === "RED");
  if (!redModel || redModel.visual_model_id !== entry.visual_model_id
    || redModel.runtime_glb !== runtime.runtime_glb
    || redModel.runtime_sha256 !== runtime.runtime_sha256) {
    throw new Error("canonical_red_asset_resolution_mismatch");
  }
  if (!runtime.runtime_glb.startsWith("assets/3d_shop/p048/")
    || runtime.runtime_glb.split("/").includes("..")
    || !/^[a-f0-9]{64}$/.test(runtime.runtime_sha256)) {
    throw new Error("runtime_asset_path_rejected");
  }
  serverAppearance = appearance;

  stage.dataset.state = "loading";
  const assetPath = `/${runtime.runtime_glb}`;
  const response = await fetch(assetPath, { credentials: "same-origin", cache: "no-store", signal });
  if (!response.ok) throw new Error(`asset_http_${response.status}`);
  const bytes = await response.arrayBuffer();
  const actualSha256 = await sha256(bytes);
  if (!isCurrent(token)) return;
  if (actualSha256 !== runtime.runtime_sha256) throw new Error("runtime_asset_sha256_mismatch");

  const loader = new GLTFLoader();
  const gltf = await loader.parseAsync(bytes, new URL(assetPath, location.href).href);
  const root = gltf.scene || gltf.scenes?.[0];
  if (!isCurrent(token)) {
    disposeModel(root);
    return;
  }
  if (!root) throw new Error("gltf_scene_missing");
  ownedRoot = root;
  let meshCount = 0;
  root.traverse((node) => {
    if (!node.isMesh) return;
    meshCount += 1;
    node.castShadow = true;
    node.receiveShadow = true;
    const materials = Array.isArray(node.material) ? node.material : [node.material];
    materials.filter(Boolean).forEach((material) => {
      material.side = THREE.DoubleSide;
      material.needsUpdate = true;
    });
  });
  if (meshCount < 1) throw new Error("gltf_mesh_missing");
  const bounds = fitModel(root);
  sharedAttachmentHost = createG009SharedHeroAttachmentHost(root, THREE);
  for (const [slot, entry] of slotResolvers) {
    sharedAttachmentHost.registerResolver(slot, entry.resolver);
  }
  sharedAttachmentFacade = createAttachmentFacade(sharedAttachmentHost);
  const viewport = renderModel(root, bounds, token);
  await new Promise((resolve, reject) => {
    const started = performance.now();
    let frame = 0;
    cancelFrameWait = () => { cancelAnimationFrame(frame); resolve(); };
    const check = () => {
      if (viewport.renderFrames() >= 2) return resolve();
      if (performance.now() - started > 5000) return reject(new Error("renderer_frame_timeout"));
      frame = requestAnimationFrame(check);
    };
    check();
  });
  if (!isCurrent(token)) return;
  cancelFrameWait = null;
  const childRehydration = await rehydrateHeroPresentations();
  if (!isCurrent(token)) return;

  publish({
    state: "ready",
    character_key: key,
    entitlement_source: entry.acquisition_source,
    character_key_source: appearance.character_key_source,
    visual_model_id: runtime.visual_model_id,
    variant: runtime.default_variant,
    runtime_glb: runtime.runtime_glb,
    expected_sha256: runtime.runtime_sha256,
    actual_sha256: actualSha256,
    asset_http_status: response.status,
    mesh_count: meshCount,
    render_frames: viewport.renderFrames(),
    canvas_width: viewport.renderer.domElement.width,
    canvas_height: viewport.renderer.domElement.height,
    draw_calls: viewport.renderer.info.render.calls,
    rendered_triangles: viewport.renderer.info.render.triangles,
    webgl2: viewport.renderer.capabilities.isWebGL2,
    renderer: "three.js-webgl",
    logical_count: catalog.logical_count,
    visual_count: catalog.visual_count,
    blue_optional_keys: catalog.blue_optional,
    c005_manifest_sha256: catalog.c005_manifest_sha256,
    child_rehydration: childRehydration.status,
  });

}

if (typeof window !== "undefined") {
  window.__G008_FUTURE30_REFRESH__ = refreshHeroAppearance;
}
mountHeroAppearance();
