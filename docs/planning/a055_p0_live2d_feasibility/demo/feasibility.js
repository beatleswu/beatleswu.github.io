const pageStartedAt = performance.now();
const modelUrl = "../rig-model.json";

const state = {
  weaponId: "wooden_sword",
  idle: false,
  showSocket: false,
  bodyX: 0,
  bodyY: 0,
  arm: 0,
  forearm: 0,
  wrist: 0,
  grip: 1,
  idleStartedAt: 0,
  fpsSample: { frames: 0, startedAt: 0, running: false }
};

let rigModel = null;
let animationFrame = 0;

const $ = (id) => document.getElementById(id);
const text = (id, value) => { const node = $(id); if (node) node.textContent = value; };

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return "not measurable";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatNumber(value, digits = 0) {
  return Number(value).toFixed(digits);
}

function setHref(node, url) {
  if (node) node.setAttribute("href", url);
}

function sourceAxisAngle(axis) {
  return Math.atan2(axis.y, axis.x) * 180 / Math.PI;
}

function applyWeaponTransform(weapon) {
  const socket = rigModel.attachments.RIGHT_HAND_WEAPON_SOCKET;
  const sourceAngle = sourceAxisAngle(weapon.sourceBladeAxis);
  const targetAngle = sourceAxisAngle(weapon.gripAxis);
  const semanticRotation = targetAngle - sourceAngle;
  // Arm/forearm/wrist motion is applied by the socket parent below. Keeping
  // the weapon's own transform limited to source-axis mapping prevents a
  // second, hidden wrist rotation from breaking the attachment contract.
  const wristCorrection = 0;
  const transform = [
    `translate(${socket.position[0]} ${socket.position[1]})`,
    `rotate(${semanticRotation + wristCorrection})`,
    `scale(${weapon.scale})`,
    `translate(${-weapon.gripPoint[0]} ${-weapon.gripPoint[1]})`
  ].join(" ");
  $("weapon-layer").setAttribute("transform", transform);
  text("transform-readout", `socket + axis (${formatNumber(semanticRotation + wristCorrection, 1)}°) + scale`);
  text("grip-point", `(${weapon.gripPoint[0]}, ${weapon.gripPoint[1]})`);
  text("grip-axis", `(${weapon.gripAxis.x.toFixed(2)}, ${weapon.gripAxis.y.toFixed(3)})`);
  text("grip-width", `${weapon.gripWidth} px`);
}

function applyBodyTransform(breathOffset = 0) {
  if (!rigModel) return;
  const bodyTransform = [
    `translate(0 ${breathOffset.toFixed(2)})`,
    `rotate(${state.bodyX} 528 760)`,
    `translate(0 ${state.bodyY * 0.35})`
  ].join(" ");
  $("mock-model").setAttribute("transform", bodyTransform);
}

function applyAttachmentTransform() {
  if (!rigModel) return;
  const socket = rigModel.attachments.RIGHT_HAND_WEAPON_SOCKET;
  const socketMotion = state.arm * 0.22 + state.forearm * 0.48 + state.wrist;
  $("attachment-parent").setAttribute(
    "transform",
    `translate(${socket.position[0]} ${socket.position[1]}) rotate(${socketMotion}) translate(${-socket.position[0]} ${-socket.position[1]})`
  );
  $("grip-layer").setAttribute("opacity", (0.62 + state.grip * 0.38).toFixed(2));
  applyWeaponTransform(rigModel.weapons[state.weaponId]);
}

function updateControls() {
  text("body-x-value", `${state.bodyX}°`);
  text("body-y-value", `${state.bodyY}°`);
  text("arm-value", `${state.arm}°`);
  text("forearm-value", `${state.forearm}°`);
  text("wrist-value", `${state.wrist}°`);
  text("grip-value", state.grip.toFixed(2));
  $("body-x").value = state.bodyX;
  $("body-y").value = state.bodyY;
  $("arm").value = state.arm;
  $("forearm").value = state.forearm;
  $("wrist").value = state.wrist;
  $("grip").value = state.grip;
}

function updateReadout() {
  if (!rigModel) return;
  const weapon = rigModel.weapons[state.weaponId];
  const socket = rigModel.attachments.RIGHT_HAND_WEAPON_SOCKET;
  text("socket-parent", socket.parent);
  text("socket-position", `(${socket.position[0]}, ${socket.position[1]})`);
  text("weapon-readout", weapon.id);
  text("rig-id", rigModel.characterRig.id);
  text("hand-rig-id", rigModel.characterRig.handRigId);
  text("weapon-chip", weapon.id.toUpperCase());
  text("swap-weapon", state.weaponId === "wooden_sword" ? "Swap to iron_sword" : "Swap to wooden_sword");
  $("weapon-chip").className = `chip ${state.weaponId === "wooden_sword" ? "chip-wood" : "chip-iron"}`;
  $("socket-overlay").setAttribute("opacity", state.showSocket ? "1" : "0");
  $("toggle-idle").setAttribute("aria-pressed", String(state.idle));
  text("toggle-idle", state.idle ? "Stop mock idle" : "Start mock idle");
  applyAttachmentTransform();
  updateControls();
}

function renderParameterTable() {
  const root = $("parameter-table");
  root.replaceChildren();
  const header = document.createElement("div");
  header.className = "parameter-row header";
  header.setAttribute("role", "row");
  header.innerHTML = "<span role=\"columnheader\">Parameter</span><span role=\"columnheader\">Default</span><span role=\"columnheader\">Purpose</span>";
  root.appendChild(header);
  rigModel.parameters.forEach((parameter) => {
    const row = document.createElement("div");
    row.className = "parameter-row";
    row.setAttribute("role", "row");
    const defaultValue = parameter.unit === "degrees" ? `${parameter.default}°` : parameter.default;
    row.innerHTML = `<code role="cell">${parameter.id}</code><span role="cell">${defaultValue}</span><span role="cell">${parameter.purpose}</span>`;
    root.appendChild(row);
  });
}

function setMetric(id, value) {
  text(id, value);
}

async function measureBytes(url) {
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) return null;
    const buffer = await response.arrayBuffer();
    return buffer.byteLength;
  } catch (_error) {
    return null;
  }
}

async function measureLocalAssets() {
  const urls = {
    model: modelUrl,
    identity: "/assets/hero/characters/wave2_p1/apprentice_p1.webp",
    grip: "/docs/planning/rpg_wave2_modular_2d_handheld_sword_prototype/pose_layers/apprentice_grip_forearm.png",
    wooden: "/assets/hero/equipment/functional/wooden_sword.svg",
    iron: "/assets/hero/equipment/functional/iron_sword.svg",
    viewer: "./feasibility.js"
  };
  const entries = await Promise.all(Object.entries(urls).map(async ([key, url]) => [key, await measureBytes(url)]));
  const bytes = Object.fromEntries(entries);
  const textureBytes = [bytes.identity, bytes.grip, bytes.wooden, bytes.iron].every(Number.isFinite)
    ? bytes.identity + bytes.grip + bytes.wooden + bytes.iron
    : null;
  setMetric("metric-model-bytes", Number.isFinite(bytes.model) ? `${formatBytes(bytes.model)} contract` : "not measurable");
  setMetric("metric-texture-bytes", formatBytes(textureBytes));
  setMetric("metric-runtime-bytes", Number.isFinite(bytes.viewer) ? `${formatBytes(bytes.viewer)} mock` : "not measurable");
  const detail = [
    `identity ${formatBytes(bytes.identity)}`,
    `grip reference ${formatBytes(bytes.grip)}`,
    `wooden ${formatBytes(bytes.wooden)}`,
    `iron ${formatBytes(bytes.iron)}`,
    "official runtime/model bytes: N/A"
  ].join(" · ");
  text("metric-detail", detail);
  window.__A055_METRICS = { bytes, textureBytes };
}

function measureMemory() {
  const memory = performance.memory;
  if (memory && Number.isFinite(memory.usedJSHeapSize)) {
    setMetric("metric-memory", formatBytes(memory.usedJSHeapSize));
    return;
  }
  setMetric("metric-memory", "not measurable");
}

function beginFpsMeasurement() {
  if (state.fpsSample.running) return;
  state.fpsSample = { frames: 0, startedAt: performance.now(), running: true };
  const sample = (now) => {
    state.fpsSample.frames += 1;
    if (now - state.fpsSample.startedAt < 1100) {
      requestAnimationFrame(sample);
      return;
    }
    const elapsed = now - state.fpsSample.startedAt;
    const fps = state.fpsSample.frames / (elapsed / 1000);
    state.fpsSample.running = false;
    setMetric("metric-fps", `${fps.toFixed(1)} fps`);
  };
  requestAnimationFrame(sample);
}

function idleTick(now) {
  if (state.idle) {
    if (!state.idleStartedAt) state.idleStartedAt = now;
    const seconds = (now - state.idleStartedAt) / 1000;
    const breath = Math.sin(seconds * Math.PI * 1.2) * 2.2;
    const idleWrist = Math.sin(seconds * Math.PI * 0.7) * 1.7;
    const socket = rigModel.attachments.RIGHT_HAND_WEAPON_SOCKET;
    const motion = state.arm * 0.22 + state.forearm * 0.48 + state.wrist + idleWrist;
    $("attachment-parent").setAttribute(
      "transform",
      `translate(${socket.position[0]} ${socket.position[1]}) rotate(${motion}) translate(${-socket.position[0]} ${-socket.position[1]})`
    );
    applyBodyTransform(breath);
    text("metric-detail", `mock idle active · PARAM_BREATH ${breath.toFixed(2)} · weapon follows socket · design mock only`);
  } else {
    state.idleStartedAt = 0;
    applyBodyTransform(0);
  }
  animationFrame = requestAnimationFrame(idleTick);
}

function wireControls() {
  $("swap-weapon").addEventListener("click", () => {
    state.weaponId = state.weaponId === "wooden_sword" ? "iron_sword" : "wooden_sword";
    const weapon = rigModel.weapons[state.weaponId];
    setHref($("weapon-layer"), weapon.asset);
    updateReadout();
  });
  $("toggle-idle").addEventListener("click", () => {
    state.idle = !state.idle;
    state.idleStartedAt = 0;
    updateReadout();
    beginFpsMeasurement();
  });
  $("reset-controls").addEventListener("click", () => {
    Object.assign(state, { bodyX: 0, bodyY: 0, arm: 0, forearm: 0, wrist: 0, grip: 1 });
    updateReadout();
  });
  $("show-socket").addEventListener("change", (event) => {
    state.showSocket = event.target.checked;
    updateReadout();
  });
  const controls = {
    "body-x": "bodyX",
    "body-y": "bodyY",
    arm: "arm",
    forearm: "forearm",
    wrist: "wrist",
    grip: "grip"
  };
  Object.entries(controls).forEach(([id, key]) => {
    $(id).addEventListener("input", (event) => {
      state[key] = Number(event.target.value);
      updateReadout();
    });
  });
}

async function boot() {
  document.documentElement.dataset.a055Runtime = "design-mockup";
  try {
    const response = await fetch(modelUrl, { cache: "no-store" });
    if (!response.ok) throw new Error(`model contract HTTP ${response.status}`);
    rigModel = await response.json();
    renderParameterTable();
    const firstRenderStart = performance.now();
    const weapon = rigModel.weapons[state.weaponId];
    setHref($("weapon-layer"), weapon.asset);
    wireControls();
    updateReadout();
    requestAnimationFrame(() => {
      setMetric("metric-first-render", `${(performance.now() - firstRenderStart).toFixed(1)} ms`);
    });
    setMetric("metric-detail", `viewer boot ${formatNumber(performance.now() - pageStartedAt, 1)} ms · measuring local resources…`);
    measureMemory();
    measureLocalAssets();
    beginFpsMeasurement();
    window.__A055_FEASIBILITY = {
      model: rigModel,
      state,
      snapshot: () => ({
        weaponId: state.weaponId,
        characterRigId: rigModel.characterRig.id,
        handRigId: rigModel.characterRig.handRigId,
        socketId: rigModel.attachments.RIGHT_HAND_WEAPON_SOCKET.id,
        idle: state.idle,
        designMockup: true,
        officialRuntimeExecuted: false
      })
    };
    animationFrame = requestAnimationFrame(idleTick);
  } catch (error) {
    setMetric("metric-detail", `Unable to load design contract: ${error.message}`);
    document.documentElement.dataset.a055Boot = "error";
  }
}

window.addEventListener("beforeunload", () => cancelAnimationFrame(animationFrame));
boot();
