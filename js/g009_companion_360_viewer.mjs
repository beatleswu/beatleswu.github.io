/*
 * G009 Companion independent real-GLB 360 preview (candidate).
 * One lazy WebGL renderer ONLY on the visible pet tab.
 * The account's pet_key/level are read from the authenticated server.
 * Canonical 18/18 Owner-approved asset IDs, byte counts and SHA-256 are
 * verified by the existing formal18 resolver before drawing any mesh.
 * The G008 Hero renderer retains exclusive ownership of its own scene.
 */
import * as THREE from "/assets/3d_shop/p048/vendor/three.module.js";
import { GLTFLoader } from "/assets/3d_shop/p048/vendor/jsm/loaders/GLTFLoader.js";
import { createFormal18AssetSource } from "./g009_companion_formal18_assets.mjs";
import { bindG009Turntable360 } from "./g008_future30_hero_renderer.js";

const shell = document.getElementById("g009-companion-3d-shell");
const viewport = document.getElementById("g009-companion-3d-viewport");
const statusEl = document.getElementById("g009-companion-3d-status");
const controlsRoot = document.getElementById("g009-companion-rotate-controls");
const loader = new GLTFLoader();
const assets = createFormal18AssetSource({
  THREE, parse: (bytes, url) => loader.parseAsync(bytes, url),
  // Preview-local layout: scaled and ground-centred, independent of Hero pose.
  getLayout: () => ({
    character_size: [0, 4.1, 0], ground_y: 0, anchor_position: [0, 0, 0],
  }),
});
let generation = 0;
let abort = null;
let resource = null;
let renderer = null;
let turntableControls = null;
let renderedKey = null;
let resizeListener = null;
let disposed = false;

function visible() {
  return !disposed && shell?.isConnected && viewport?.isConnected
    && document.body.dataset.g009HeroTab === "pet"
    && document.visibilityState !== "hidden";
}
function publish(state, reason = null, metadata = {}) {
  if (shell) shell.dataset.previewState = state;
  if (statusEl) statusEl.textContent = state === "loading"
    ? "正在驗證棋靈 3D 模型…"
    : state === "none" ? "尚未擁有出戰棋靈"
    : state === "unavailable" ? "目前無法顯示 3D 棋靈，可使用上方圖片及互動功能"
    : state === "ready" ? "" : "";
  window.__G009_COMPANION_360_STATE__ = Object.freeze({
    state, reason, ...metadata,
    // This is a presentation diagnostic, not proof of a production UAT.
    is_real_glb: state === "ready",
  });
}
function releaseRenderer() {
  turntableControls?.dispose();
  turntableControls = null;
  renderer?.setAnimationLoop(null);
  renderer?.renderLists?.dispose();
  renderer?.dispose();
  renderer?.domElement?.remove();
  renderer = null;
  if (resizeListener) {
    window.removeEventListener("resize", resizeListener);
    resizeListener = null;
  }
  resource?.disposeOwnedResources();
  resource = null;
  renderedKey = null;
  viewport?.replaceChildren();
}
function suspend() {
  generation += 1;
  abort?.abort();
  abort = null;
  releaseRenderer();
  publish("inactive");
}
function requireFresh(token) {
  return !disposed && token === generation && visible() && !abort?.signal.aborted;
}
async function refresh() {
  if (!shell || !viewport || !statusEl || !controlsRoot) return;
  if (!visible()) { suspend(); return; }
  const token = ++generation;
  abort?.abort();
  const controller = new AbortController();
  abort = controller;
  try {
    const status = await fetch("/api/pet/status", {
      credentials: "include", cache: "no-store", signal: controller.signal,
    });
    if (!status.ok) throw new Error("PET_STATUS_HTTP_" + status.status);
    const snapshot = await status.json();
    if (!requireFresh(token)) return;
    if (!snapshot || !Object.hasOwn(snapshot, "pet")) throw new Error("PET_STATUS_INVALID");
    if (!snapshot.pet) {
      releaseRenderer();
      publish("none");
      return;
    }
    const pet = snapshot.pet;
    const descriptor = await assets.resolve(
      Object.freeze({ pet_key: pet.pet_key, level: pet.level }), controller.signal);
    if (!requireFresh(token)) return;
    const key = descriptor.presentation_id + ":" + descriptor.asset_sha256;
    if (renderedKey === key && renderer && resource) return;
    releaseRenderer();
    publish("loading");
    // Formal18 loader checks the exact approved GLB bytes and SHA-256.
    const incoming = await assets.load(descriptor, controller.signal);
    if (!requireFresh(token)) {
      incoming.disposeOwnedResources();
      return;
    }
    resource = incoming;
    const node = incoming.node;
    if (!node?.isObject3D) throw new Error("COMPANION_REAL_MESH_REQUIRED");
    let meshCount = 0;
    node.traverse(child => { if (child.isMesh) meshCount++; });
    if (!meshCount) throw new Error("COMPANION_GLTF_HAS_NO_MESH");
    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xeaf6ff, 0x344d78, 2.1));
    const light = new THREE.DirectionalLight(0xffeaca, 2.7);
    light.position.set(-3, 5, 5);
    scene.add(light);
    const fill = new THREE.DirectionalLight(0xb1d9ff, 1.3);
    fill.position.set(3, 2, -4);
    scene.add(fill);
    const turntable = new THREE.Group();
    turntable.name = "G009_Companion_Formal18_360_Turntable";
    turntable.add(node);
    scene.add(turntable);
    const bounds = new THREE.Box3().setFromObject(node);
    const center = bounds.getCenter(new THREE.Vector3());
    const camera = new THREE.PerspectiveCamera(38, 1, 0.01, 30);
    camera.position.set(0, center.y + 0.15, 3.3);
    camera.lookAt(0, center.y, 0);
    // Never create two pet WebGL contexts. After a tab change/dispose the
    // original context is released before a new model may be accepted.
    const gl = new THREE.WebGLRenderer({
      alpha: true, antialias: true, powerPreference: "low-power",
    });
    renderer = gl;
    gl.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    gl.outputColorSpace = THREE.SRGBColorSpace;
    gl.toneMapping = THREE.ACESFilmicToneMapping;
    gl.toneMappingExposure = 1.15;
    function resize() {
      const width = Math.max(1, Math.round(viewport.clientWidth));
      const height = Math.max(1, Math.round(viewport.clientHeight));
      gl.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    }
    resizeListener = resize;
    window.addEventListener("resize", resize);
    resize();
    viewport.replaceChildren(gl.domElement);
    turntableControls = bindG009Turntable360(gl.domElement, turntable, {
      controlsRoot,
      label: "3D Companion: drag or swipe for real 360-degree rotation; use arrow keys or Home",
    });
    // Drawing is bounded by the visible tab and canceled on suspension.
    gl.setAnimationLoop(() => {
      // Fresh status reads can confirm the same authoritative model without
      // recreating it; those reads must NOT freeze this already-live renderer.
      if (!visible() || renderer !== gl) return;
      if (gl.domElement.clientWidth && gl.domElement.clientHeight) {
        const width = Math.max(1, Math.round(viewport.clientWidth));
        const height = Math.max(1, Math.round(viewport.clientHeight));
        if (Math.abs(width - gl.domElement.clientWidth) > 1
          || Math.abs(height - gl.domElement.clientHeight) > 1) resize();
      }
      gl.render(scene, camera);
    });
    renderedKey = key;
    publish("ready", null, {
      pet_key: descriptor.pet_key, stage: descriptor.stage,
      asset_sha256: descriptor.asset_sha256,
      meshes: meshCount, canvas_count: viewport.querySelectorAll("canvas").length,
    });
  } catch (error) {
    if (!requireFresh(token)) return;
    releaseRenderer();
    publish("unavailable", error instanceof Error ? error.message : String(error));
  }
}
if (shell && viewport && statusEl && controlsRoot) {
  // The G009 tabs are client-side. Observe ONLY the tab attribute and
  // fetch again when returning; do not preserve hidden WebGL GPU resources.
  const observer = new MutationObserver(mutations => {
    if (mutations.some(m => m.attributeName === "data-g009-hero-tab")) void refresh();
  });
  observer.observe(document.body, { attributes: true, attributeFilter: ["data-g009-hero-tab"] });
  window.addEventListener("g009:companion-status", () => { if (visible()) void refresh(); });
  document.addEventListener("visibilitychange", () => {
    if (visible()) void refresh();
    else suspend();
  });
  window.addEventListener("pagehide", () => {
    disposed = true;
    observer.disconnect();
    suspend();
  }, { once: true });
  void refresh();
}
