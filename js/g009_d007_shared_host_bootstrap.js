import * as THREE from "/assets/3d_shop/p048/vendor/three.module.js";
import { GLTFLoader } from "/assets/3d_shop/p048/vendor/jsm/loaders/GLTFLoader.js";
import {
  createG009D007PresentationIndex,
  createG009D007SharedHostAdapter,
  G009_D007_APPEARANCE_SLOTS,
} from "./g009_d007_shared_host_adapter.js";
import { createG009RuntimeEquipmentIndex } from "./g009_d007_runtime_identity_resolver.mjs";
import {
  registerHeroPresentationResolver,
  registerHeroPresentationRehydrator,
} from "./g008_future30_hero_renderer.js";

async function fetchJson(path) {
  const response = await fetch(path, { credentials: "same-origin", cache: "no-store" });
  if (!response.ok) throw new Error("d007_authority_http_failure:" + response.status);
  return response.json();
}

async function registerD007SharedHostAdapter() {
  const [schema, p048Manifest] = await Promise.all([
    fetchJson("/schemas/g009_d007_runtime_prerequisite_v1.json"),
    fetchJson("/assets/3d_shop/p048/runtime_manifest.json"),
  ]);
  const index = createG009D007PresentationIndex(schema, p048Manifest);
  const equipmentIndex = createG009RuntimeEquipmentIndex(schema);

  // The resolver accepts only exact admitted presentation IDs. It never maps
  // legacy item IDs, filenames, display names, or visual similarity.
  for (const slot of G009_D007_APPEARANCE_SLOTS) {
    registerHeroPresentationResolver(slot, (presentationId) => index.resolve(slot, presentationId));
  }

  const activeByGeneration = new Map();
  registerHeroPresentationRehydrator("G009_D007_R1_SHARED_HOST", async ({ appearance, host, generation }) => {
    if (activeByGeneration.has(generation)) return activeByGeneration.get(generation);
    const adapter = createG009D007SharedHostAdapter({
      THREE,
      GLTFLoader,
      host,
      presentationIndex: index,
    });
    const pending = adapter.renderServerSnapshot(appearance);
    activeByGeneration.set(generation, pending);
    try {
      return await pending;
    } finally {
      if (activeByGeneration.get(generation) === pending) activeByGeneration.delete(generation);
    }
  });
  return Object.freeze({ schema, p048Manifest, presentationIndex: index, equipmentIndex });
}

export const G009_D007_AUTHORITY_READY = registerD007SharedHostAdapter();
void G009_D007_AUTHORITY_READY.catch((error) => {
  console.warn("D007 Hero presentation remains fail-closed", error instanceof Error ? error.message : String(error));
});
