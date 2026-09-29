import {validateCompanionFormal18Manifest, resolveCompanionPresentation} from "./companion_formal_18_mapping.js";
export const MANIFEST_SHA256 = "124af40c1f62a39642f4345d3efa23fef8971f240a9a79d5450fcd5d516fe3af";
export async function digest(bytes) {
  return Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    byte => byte.toString(16).padStart(2,"0")).join("");
}
export function createFormal18AssetSource({fetchImpl = fetch, parse, THREE, getLayout}) {
  let manifest = null; // only cache successfully authenticated immutable bytes
  async function resolve(pet, signal) {
    if (!manifest) {
      const response = await fetchImpl("/assets/3d_shop/p048/companion/formal_18/mapping_manifest.json",
        {credentials:"same-origin",cache:"no-store",signal});
      if (!response.ok) throw new Error("COMPANION_MANIFEST_HTTP_" + response.status);
      const bytes = await response.arrayBuffer();
      if (await digest(bytes) !== MANIFEST_SHA256) throw new Error("COMPANION_MANIFEST_SHA_MISMATCH");
      manifest = validateCompanionFormal18Manifest(JSON.parse(new TextDecoder().decode(bytes)));
    }
    const selection = resolveCompanionPresentation(pet, manifest);
    const row = selection.presentation;
    return Object.freeze({presentation_id:"companion:" + selection.pet_key + ":" + selection.stage,
      pet_key:selection.pet_key, stage:selection.stage, slot:"COMPANION",
      asset_path:"/" + row.runtime_glb, asset_sha256:row.asset_sha256, asset_bytes:row.asset_bytes});
  }
  async function load(descriptor, signal) {
    const response = await fetchImpl(descriptor.asset_path, {credentials:"same-origin",cache:"no-store",signal});
    if (!response.ok) throw new Error("COMPANION_MODEL_HTTP_" + response.status);
    const bytes = await response.arrayBuffer();
    if (bytes.byteLength !== descriptor.asset_bytes
      || (await digest(bytes)).toUpperCase() !== descriptor.asset_sha256.toUpperCase()) {
      throw new Error("COMPANION_MODEL_SHA_OR_SIZE_MISMATCH");
    }
    const gltf = await parse(bytes, new URL(descriptor.asset_path, location.href).href);
    const node = gltf.scene || gltf.scenes?.[0];
    const disposeOwnedResources = () => {
      node?.removeFromParent();
      const resources = new Set();
      node?.traverse(child => {
        if (child.geometry) resources.add(child.geometry);
        for (const material of (Array.isArray(child.material) ? child.material : [child.material]).filter(Boolean)) {
          resources.add(material);
          for (const value of Object.values(material)) if (value?.isTexture) resources.add(value);
        }
      });
      resources.forEach(resource => resource.dispose());
    };
    try {
      if (!node?.isObject3D || node.parent) throw new Error("COMPANION_SCENE_INVALID");
      // Fit in host-local units; no dependency on character source model scale.
      const layout = getLayout();
      const bounds = new THREE.Box3().setFromObject(node);
      const size = bounds.getSize(new THREE.Vector3());
      const extent = Math.max(size.x,size.y,size.z);
      if (!Number.isFinite(extent) || extent <= 0) throw new Error("COMPANION_BOUNDS_INVALID");
      node.scale.multiplyScalar(Math.max(...layout.character_size) * 0.32 / extent);
      node.updateMatrixWorld(true);
      bounds.setFromObject(node);
      const center = bounds.getCenter(new THREE.Vector3());
      node.position.x += layout.character_size[0] * 0.25 - center.x;
      node.position.y += layout.ground_y - layout.anchor_position[1] - bounds.min.y;
      node.position.z -= center.z;
      node.updateMatrixWorld(true);
      node.userData.goOdysseyCompanion = {pet_key:descriptor.pet_key, stage:descriptor.stage,
        asset_sha256:descriptor.asset_sha256, asset_bytes:bytes.byteLength};
      return {node,disposeOwnedResources};
    } catch(error) {
      disposeOwnedResources();
      throw error;
    }
  }
  return Object.freeze({resolve,load});
}
