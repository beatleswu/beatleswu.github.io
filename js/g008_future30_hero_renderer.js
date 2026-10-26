import {verifyCurrentHeroProjection,sha256GlbBytes} from "./g085_shared_authoritative_3d_core.mjs";
import {relaxCurrentFuture30Pose} from "./g085j_shared_relaxed_idle_pose.mjs";
import * as THREE from "/assets/3d_shop/p048/vendor/three.module.js";
import { GLTFLoader } from "/assets/3d_shop/p048/vendor/jsm/loaders/GLTFLoader.js";
import {
  createG009SharedHeroAttachmentHost,
  G009_HERO_PRESENTATION_SLOTS,
} from "./g009_shared_hero_attachment_host.js";

export const HERO_PRESENTATION_SLOTS = G009_HERO_PRESENTATION_SLOTS;
let stage = null;
let avatar = null;

// This module alone owns the G008 Hero canvas. P048 remains a Shop preview.
let generation = 0;
let pending = null;
let controller = null;
let ownedRoot = null;
let ownedRenderer = null;
let heroTurntableControls = null;
let sharedAttachmentHost = null;
let sharedAttachmentFacade = null;
let serverAppearance = null;
const slotResolvers = new Map();
const presentationRehydrators = new Map();
const HAND_REHYDRATOR = "G009_D_R2_SERVER_EQUIPPED_HANDS";
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
    const token = generation;
    void runPresentationRehydrator(key, callback, token, serverAppearance, true)
      .then((result) => {
        // A child registered after the parent rendered: never leave a
        // formerly missing resolver reported as ready or permanently pending.
        if (key !== HAND_REHYDRATOR || token !== generation
            || presentationRehydrators.get(key) !== callback) return;
        const current = window.__G008_HERO_RENDER_STATE__;
        if (current?.state !== "ready") return;
        const status = handRehydrationStatus(result);
        publish({ ...current, equipment_status: status });
      });
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

function handRehydrationStatus(receipt) {
  // Missing resolver, not-yet-rehydrated and failed attachment must NOT
  // become a genuine ready status. A valid empty server inventory is ready.
  if (!receipt || receipt.status === "not_ready") return "pending";
  if (receipt.status !== "rehydrated") return "unavailable";
  return receipt.result?.status === "failed_closed" ? "unavailable" : "ready";
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
  heroTurntableControls?.dispose();
  heroTurntableControls = null;
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
  // An explicit user action restarts only the current Hero scene and
  // re-fetches the same server-owned appearance and equipped inventory.
  // Never invent a weapon or replay any equipment purchase.
  const retry = document.getElementById("g008-hero-retry");
  if (retry && retry.dataset.g008Bound !== "true") {
    retry.dataset.g008Bound = "true";
    retry.addEventListener("click", async () => {
      if (retry.disabled) return;
      retry.disabled = true;
      try { await refreshHeroAppearance(); }
      finally { retry.disabled = false; }
    });
  }
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
  const notice = document.getElementById("g008-hero-load-notice");
  const message = document.getElementById("g008-hero-load-message");
  const retry = document.getElementById("g008-hero-retry");
  if (notice && message && retry) {
    const unresolved = state.state === "ready" && state.equipment_status === "pending";
    const unavailable = state.state === "failed"
      || (state.state === "ready" && state.equipment_status === "unavailable");
    notice.hidden = state.state !== "loading" && !unavailable && !unresolved;
    retry.hidden = !unavailable && !unresolved;
    if (state.state === "loading") message.textContent = "正在同步 3D 角色與裝備…";
    else if (state.state === "failed") message.textContent = "3D 角色暫時無法載入";
    else if (unresolved) message.textContent = "正在等待裝備同步…";
    else if (unavailable) message.textContent = "裝備暫時無法同步";
    else message.textContent = "";
  }
  avatar?.setAttribute?.("aria-busy", state.state === "loading" ? "true" : "false");
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

// One true 360-degree model turntable. Rotates THREE.Object3D geometry rather
// than using CSS transforms on image assets. Shared with the independent
// Companion preview; no model, account or entitlement authority lives here.
export function bindG009Turntable360(canvas, turntable, {
  controlsRoot = null, label = "Drag to rotate the 3D model 360 degrees",
} = {}) {
  if (!canvas || !turntable?.rotation) throw new Error("turntable_geometry_required");
  const full = 2 * Math.PI;
  let activePointer = null;
  let previousX = 0;
  let disposed = false;
  const yaw = () => ((turntable.rotation.y % full) + full) % full;
  function rotate(delta) {
    if (disposed || !Number.isFinite(delta)) return;
    turntable.rotation.y = ((turntable.rotation.y + delta) % full + full) % full;
    if (canvas.dataset) canvas.dataset.rotationDegrees = String(
      Math.round(turntable.rotation.y * 180 / Math.PI) % 360);
  }
  function reset() {
    if (disposed) return;
    rotate(-turntable.rotation.y);
  }
  const start = event => {
    if (event.button !== undefined && event.button !== 0) return;
    if (activePointer !== null) return;
    activePointer = event.pointerId;
    previousX = event.clientX;
    try { canvas.setPointerCapture?.(event.pointerId); } catch (_) {
      // Synthetic touch / Safari may decline capture; pointer movement still works.
    }
  };
  const move = event => {
    if (activePointer !== event.pointerId) return;
    const x = event.clientX;
    rotate((x - previousX) * 0.012);
    previousX = x;
  };
  const stop = event => {
    if (activePointer !== event.pointerId) return;
    activePointer = null;
    if (canvas.hasPointerCapture?.(event.pointerId)) {
      canvas.releasePointerCapture?.(event.pointerId);
    }
  };
  const keyboard = event => {
    let delta = 0;
    if (event.key === "ArrowLeft") delta = -Math.PI / 8;
    if (event.key === "ArrowRight") delta = Math.PI / 8;
    if (event.key === "Home") {
      event.preventDefault();
      reset();
      return;
    }
    if (delta) {
      event.preventDefault();
      rotate(delta);
    }
  };
  const controls = [];
  if (typeof canvas.addEventListener === "function") {
    canvas.style.touchAction = "none";
    canvas.style.cursor = "grab";
    canvas.tabIndex = 0;
    canvas.setAttribute?.("role", "group");
    canvas.setAttribute?.("aria-label", label);
    for (const [event, fn] of [
      ["pointerdown", start], ["pointermove", move],
      ["pointerup", stop], ["pointercancel", stop],
      ["lostpointercapture", stop], ["keydown", keyboard],
    ]) canvas.addEventListener(event, fn);
  }
  for (const button of controlsRoot?.querySelectorAll?.("[data-turntable-action]") || []) {
    const action = button.dataset.turntableAction;
    if (!["left", "right", "reset"].includes(action)) continue;
    const click = () => {
      if (action === "reset") reset();
      else rotate(action === "left" ? -Math.PI / 4 : Math.PI / 4);
    };
    button.addEventListener("click", click);
    button.disabled = false;
    controls.push([button, click]);
  }
  if (controlsRoot?.dataset) controlsRoot.dataset.turntableReady = "true";
  rotate(0);
  return Object.freeze({
    rotate, reset, getYaw: yaw,
    dispose() {
      if (disposed) return;
      disposed = true;
      activePointer = null;
      if (typeof canvas.removeEventListener === "function") {
        for (const [event, fn] of [
          ["pointerdown", start], ["pointermove", move],
          ["pointerup", stop], ["pointercancel", stop],
          ["lostpointercapture", stop], ["keydown", keyboard],
        ]) canvas.removeEventListener(event, fn);
      }
      for (const [button, click] of controls) {
        button.removeEventListener("click", click);
        button.disabled = true;
      }
      if (controlsRoot?.dataset) controlsRoot.dataset.turntableReady = "false";
    },
  });
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
  // Preserve the canonical character and attached equipment/Companion as one
  // scene subtree. Rotate the *group* about ground-centred x/z = 0, not the
  // GLB's arbitrary origin, so all 360-degree viewpoints stay in frame.
  const turntable = new THREE.Group();
  turntable.name = "G008_Authoritative_3D_Turntable";
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
  heroTurntableControls?.dispose();
  const controlsRoot = document.getElementById?.("g009-hero-rotate-controls");
  heroTurntableControls = bindG009Turntable360(renderer.domElement, turntable, {
    controlsRoot,
    label: "3D character: drag left or right to rotate 360 degrees; arrow keys and Home also work",
  });

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

  // Keep the original G008 authority boundary explicit for older integrated
  // source-contract consumers. The complete C005/entitlement validation is
  // shared with Backpack and Shop through verifyCurrentHeroProjection.
  const key = appearance.character_key;
  const runtime = appearance.character_runtime;
  if (appearance.character_key_source !== "player_appearance.character_key"
    || appearance.character_key_authority !== "player_appearance.character_key"
    || !runtime || runtime.character_key !== key) {
    throw new Error("server_character_projection_mismatch");
  }
  const {entry}=verifyCurrentHeroProjection(catalog,appearance);
  serverAppearance = appearance;

  stage.dataset.state = "loading";
  const assetPath = `/${runtime.runtime_glb}`;
  const response = await fetch(assetPath, { credentials: "same-origin", cache: "no-store", signal });
  if (!response.ok) throw new Error(`asset_http_${response.status}`);
  const bytes = await response.arrayBuffer();
  const actualSha256 = await sha256GlbBytes(bytes);
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
  // Owner-requested shared natural idle: character-owned rig only.
  // The G009 hand slot keeps tracking the real hand bone each frame.
  const naturalPose = relaxCurrentFuture30Pose(root, THREE);
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
  // The parent WebGL scene can be ready while the hand attachment request
  // failed closed. Distinguish that from a genuinely empty equipped slot.
  let handRehydration = childRehydration.results?.find(
    (entry) => entry.key === HAND_REHYDRATOR);
  if (!handRehydration && presentationRehydrators.has(HAND_REHYDRATOR)) {
    // Resolver registered during the initial Promise.all snapshot. Await
    // that real resolver instead of publishing false-ready on empty results.
    handRehydration = await runPresentationRehydrator(
      HAND_REHYDRATOR, presentationRehydrators.get(HAND_REHYDRATOR),
      token, serverAppearance, true);
  }
  const equipmentStatus = handRehydrationStatus(handRehydration);
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
    natural_idle_pose_status: naturalPose.status,
    natural_idle_pose_arms: naturalPose.arms_applied,
    natural_idle_pose_side_deltas: naturalPose.side_deltas||[],
    logical_count: catalog.logical_count,
    visual_count: catalog.visual_count,
    blue_optional_keys: catalog.blue_optional,
    c005_manifest_sha256: catalog.c005_manifest_sha256,
    child_rehydration: childRehydration.status,
    equipment_status: equipmentStatus,
  });

}

if (typeof window !== "undefined") {
  window.__G008_FUTURE30_REFRESH__ = refreshHeroAppearance;
}
mountHeroAppearance();
