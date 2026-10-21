// Child-slot lifecycle only. The G008 Hero renderer remains the sole owner
// of the WebGL renderer, scene, character root, mount, and destroy lifecycle.
export const G009_HERO_PRESENTATION_SLOTS = Object.freeze([
  "HEAD",
  "BACK",
  "AURA",
  "MAIN_HAND",
  "OFF_HAND",
  "COMPANION",
]);

function assertSlot(slot) {
  if (!G009_HERO_PRESENTATION_SLOTS.includes(slot)) {
    throw new Error("unknown_hero_presentation_slot:" + String(slot));
  }
}

// Hand-held slots follow the Hero skeleton. Every Future30 visual model ships
// hand.R / hand.L joints (GLTFLoader sanitizes them to handR / handL). A hand
// slot never falls back to character bounding-box placement: without exactly
// one matching bone it fails closed.
const HAND_SLOT_BONE_NAMES = Object.freeze({
  MAIN_HAND: Object.freeze(["handr", "righthand", "mixamorigrighthand"]),
  OFF_HAND: Object.freeze(["handl", "lefthand", "mixamoriglefthand"]),
});

function findHandBone(characterRoot, slot) {
  const wanted = HAND_SLOT_BONE_NAMES[slot];
  const matches = [];
  characterRoot.traverse((node) => {
    if (!node.isBone || typeof node.name !== "string") return;
    if (wanted.includes(node.name.toLowerCase().replace(/[^a-z0-9]/g, ""))) matches.push(node);
  });
  return matches.length === 1 ? matches[0] : null;
}

// The anchor stays a direct child of the character root (slot layout and
// node ownership are unchanged), but its transform is taken from the hand
// bone every time world matrices update, so equipment follows the pose.
function bindAnchorToHandBone(anchor, bone, characterRoot, THREE) {
  const rootInverse = new THREE.Matrix4();
  anchor.matrixAutoUpdate = false;
  const sync = () => {
    bone.updateWorldMatrix(true, false);
    rootInverse.copy(characterRoot.matrixWorld).invert();
    anchor.matrix.multiplyMatrices(rootInverse, bone.matrixWorld);
    anchor.matrix.decompose(anchor.position, anchor.quaternion, anchor.scale);
    anchor.matrixWorld.copy(bone.matrixWorld);
    anchor.matrixWorldNeedsUpdate = false;
  };
  anchor.updateMatrixWorld = function updateFromHandBone() {
    sync();
    for (const child of this.children) child.updateMatrixWorld(true);
  };
  anchor.updateWorldMatrix = function updateWorldFromHandBone(updateParents, updateChildren) {
    sync();
    if (updateChildren) for (const child of this.children) child.updateWorldMatrix(false, true);
  };
  sync();
}

function disposeObject3D(root) {
  root?.removeFromParent?.();
  const resources = new Set();
  root?.traverse?.((node) => {
    if (node.geometry) resources.add(node.geometry);
    const materials = Array.isArray(node.material) ? node.material : [node.material];
    for (const material of materials.filter(Boolean)) {
      resources.add(material);
      for (const value of Object.values(material)) {
        if (value?.isTexture) resources.add(value);
      }
    }
  });
  resources.forEach((resource) => resource.dispose?.());
}

function localBoundsOf(root, THREE) {
  root.updateMatrixWorld(true);
  const worldBounds = new THREE.Box3().setFromObject(root);
  if (worldBounds.isEmpty()) throw new Error("hero_attachment_character_bounds_empty");
  const localBounds = new THREE.Box3();
  const { min, max } = worldBounds;
  for (const x of [min.x, max.x]) {
    for (const y of [min.y, max.y]) {
      for (const z of [min.z, max.z]) {
        localBounds.expandByPoint(root.worldToLocal(new THREE.Vector3(x, y, z)));
      }
    }
  }
  const size = localBounds.getSize(new THREE.Vector3());
  if (![size.x, size.y, size.z].every(Number.isFinite)
    || Math.max(size.x, size.y, size.z) <= 0) {
    throw new Error("hero_attachment_character_bounds_invalid");
  }
  return { localBounds, size };
}

function anchorPositions(bounds, size, THREE) {
  const center = bounds.getCenter(new THREE.Vector3());
  const width = Math.max(size.x, 0.1);
  const height = Math.max(size.y, 0.1);
  const depth = Math.max(size.z, 0.1);
  return {
    HEAD: [center.x, bounds.max.y - height * 0.06, center.z],
    BACK: [center.x, bounds.min.y + height * 0.52, center.z - depth * 0.28],
    AURA: [center.x, bounds.min.y + height * 0.46, center.z],
    COMPANION: [center.x + width * 0.42, bounds.min.y + height * 0.12, center.z + depth * 0.12],
  };
}

function loadedNodeOf(loaded) {
  if (loaded?.isObject3D) return loaded;
  if (loaded?.node?.isObject3D) return loaded.node;
  if (loaded?.scene?.isObject3D) return loaded.scene;
  return null;
}

function disposeLoaded(loaded, node) {
  node?.removeFromParent?.();
  const ownedDisposer = loaded?.disposeOwnedResources || loaded?.dispose;
  if (typeof ownedDisposer === "function") {
    ownedDisposer.call(loaded);
  } else if (node) {
    disposeObject3D(node);
  }
}

function disposeRejectedLoaded(loaded, node) {
  if (!node?.parent) {
    disposeLoaded(loaded, node);
    return;
  }
  // A parented node belongs to another scene owner. Clean up only resources
  // explicitly owned by the loader wrapper; do not detach or dispose the node.
  const ownedDisposer = loaded !== node
    ? loaded?.disposeOwnedResources || loaded?.dispose
    : null;
  if (typeof ownedDisposer === "function") ownedDisposer.call(loaded);
}

export function createG009SharedHeroAttachmentHost(characterRoot, THREE) {
  if (!characterRoot?.isObject3D || typeof characterRoot.add !== "function"
    || typeof characterRoot.worldToLocal !== "function" || typeof THREE?.Group !== "function") {
    throw new Error("hero_attachment_character_root_required");
  }

  const { localBounds, size } = localBoundsOf(characterRoot, THREE);
  const positions = anchorPositions(localBounds, size, THREE);
  const handBones = new Map(Object.keys(HAND_SLOT_BONE_NAMES)
    .map((slot) => [slot, findHandBone(characterRoot, slot)]));
  const anchors = new Map();
  const slotState = new Map();
  const resolvers = new Map();
  let disposed = false;
  let hostGeneration = 1;

  for (const slot of G009_HERO_PRESENTATION_SLOTS) {
    const anchor = new THREE.Group();
    anchor.name = "G009_SHARED_HERO_SLOT_" + slot;
    anchor.userData = {
      owner: "G008_FUTURE30_HERO_RENDERER",
      attachment_slot: slot,
    };
    characterRoot.add(anchor);
    if (handBones.has(slot)) {
      const bone = handBones.get(slot);
      anchor.userData.anchor_source = bone ? "HAND_BONE:" + bone.name : "UNRESOLVED_HAND_BONE";
      if (bone) bindAnchorToHandBone(anchor, bone, characterRoot, THREE);
    } else {
      anchor.position.fromArray(positions[slot]);
      anchor.userData.anchor_source = "CHARACTER_LAYOUT";
    }
    anchors.set(slot, anchor);
    slotState.set(slot, { generation: 0, record: null });
  }

  function ensureLive() {
    if (disposed) throw new Error("hero_attachment_host_destroyed");
  }

  function assertHandBone(slot) {
    if (handBones.has(slot) && !handBones.get(slot)) {
      throw new Error("hero_hand_bone_unresolved:" + slot);
    }
  }

  function detachSlot(slot) {
    assertSlot(slot);
    const state = slotState.get(slot);
    state.generation += 1;
    const record = state.record;
    state.record = null;
    if (record) disposeLoaded(record.loaded, record.node);
    return { status: "detached", slot };
  }

  function registerResolver(slot, resolver) {
    ensureLive();
    assertSlot(slot);
    if (typeof resolver !== "function") throw new Error("hero_slot_resolver_required");
    const current = resolvers.get(slot);
    if (current && current !== resolver) throw new Error("hero_slot_resolver_already_registered:" + slot);
    resolvers.set(slot, resolver);
    return () => {
      if (resolvers.get(slot) !== resolver) return false;
      resolvers.delete(slot);
      detachSlot(slot);
      return true;
    };
  }

  function unregisterResolver(slot, resolver) {
    assertSlot(slot);
    if (resolvers.get(slot) !== resolver) return false;
    resolvers.delete(slot);
    detachSlot(slot);
    return true;
  }

  async function attach(slot, presentationId, loadNode) {
    ensureLive();
    assertSlot(slot);
    assertHandBone(slot);
    const state = slotState.get(slot);
    const resolver = resolvers.get(slot);
    const descriptor = typeof presentationId === "string" && presentationId.length > 0
      ? resolver?.(presentationId)
      : null;
    if (!descriptor || descriptor.presentation_id !== presentationId || descriptor.slot !== slot) {
      throw new Error("unknown_hero_presentation:" + slot + ":" + String(presentationId));
    }
    if (typeof loadNode !== "function") throw new Error("hero_presentation_loader_required");

    // A valid request supersedes older pending loads, but the currently
    // attached child remains visible until its replacement is ready.
    state.generation += 1;
    const operationGeneration = state.generation;
    const operationHostGeneration = hostGeneration;

    const loaded = await loadNode(descriptor);
    const node = loadedNodeOf(loaded);
    if (disposed || operationHostGeneration !== hostGeneration
      || operationGeneration !== state.generation) {
      disposeRejectedLoaded(loaded, node);
      return { status: "stale", slot, presentation_id: presentationId };
    }
    if (!node) {
      disposeLoaded(loaded, null);
      throw new Error("hero_presentation_object3d_required");
    }
    if (node.parent) {
      disposeRejectedLoaded(loaded, node);
      throw new Error("hero_presentation_node_already_parented");
    }
    const previous = state.record;
    anchors.get(slot).add(node);
    state.record = { loaded, node, presentationId };
    if (previous) disposeLoaded(previous.loaded, previous.node);
    return { status: "attached", slot, presentation_id: presentationId };
  }

  function diagnostics() {
    return Object.freeze({
      disposed,
      generation: hostGeneration,
      slots: Object.freeze(G009_HERO_PRESENTATION_SLOTS.map((slot) => Object.freeze({
        slot,
        presentation_id: slotState.get(slot).record?.presentationId || null,
        child_count: anchors.get(slot).children.length,
      }))),
    });
  }

  function getSlotLayout(slot) {
    ensureLive();
    assertSlot(slot);
    assertHandBone(slot);
    // Hand slots report the hand bone's current position in character-root
    // space; other slots report their character layout anchor.
    const anchorPosition = handBones.has(slot)
      ? anchors.get(slot).position.toArray()
      : positions[slot];
    // Read-only geometric fact for isolated hand-attachment fitting.
    // Existing keys and slot authority are unchanged; never grants equipment.
    const boneScale = handBones.has(slot) && handBones.get(slot)
      ? handBones.get(slot).getWorldScale(new THREE.Vector3()).toArray()
      : null;
    return Object.freeze({
      character_size: Object.freeze([size.x, size.y, size.z]),
      anchor_position: Object.freeze([...anchorPosition]),
      ground_y: localBounds.min.y,
      hand_world_scale: boneScale ? Object.freeze([...boneScale]) : null,
    });
  }

  function destroy() {
    if (disposed) return { status: "already_destroyed" };
    disposed = true;
    hostGeneration += 1;
    for (const slot of G009_HERO_PRESENTATION_SLOTS) {
      detachSlot(slot);
      anchors.get(slot).removeFromParent();
    }
    resolvers.clear();
    return { status: "destroyed" };
  }

  return Object.freeze({
    slots: G009_HERO_PRESENTATION_SLOTS,
    registerResolver,
    unregisterResolver,
    attach,
    detach: detachSlot,
    diagnostics,
    getSlotLayout,
    destroy,
  });
}
