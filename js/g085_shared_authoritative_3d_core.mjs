// A single authority contract shared by G008 Hero and read-only Backpack/Shop 3D.
// It validates the original server's applied, entitled Future30 character.
// No cookie, client item names, local storage or Shop state grants ownership.
const EXPECTED_C005_MANIFEST_SHA256 =
  "35746c1168152cbd3fd166fd0ba5a319f3bf1ba8916fed3a8669f487a2a83c1d";
const ACCEPTED_FUTURE30_ACQUISITION_SOURCES = new Set([
  "STARTER",
  "STAGE",
  "PREMIUM",
  "SHOP",
  "ACCEPTANCE_TEST",
]);

export function verifyCurrentHeroProjection(catalog, appearance) {
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

  return Object.freeze({key,entry,runtime});
}

export async function sha256GlbBytes(buffer) {
  const digest=await crypto.subtle.digest("SHA-256",buffer);
  return [...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,"0")).join("");
}

export async function loadVerified3DAsset(path,expectedSha,signal=undefined) {
  if(typeof path!=="string"||!/^(?:\/)?assets\/3d_shop\/[a-z0-9_\-/.]+\.glb$/.test(path)
    ||path.includes("..")||!/^[a-f0-9]{64}$/.test(expectedSha)) {
    throw new Error("g085_3d_asset_source_not_admitted");
  }
  const url=path.startsWith("/")?path:"/"+path;
  const response=await fetch(url,{credentials:"same-origin",cache:"no-store",signal});
  if(!response.ok)throw new Error("g085_3d_asset_http_"+response.status);
  const bytes=await response.arrayBuffer();
  if(await sha256GlbBytes(bytes)!==expectedSha)throw new Error("g085_3d_asset_sha_mismatch");
  return {bytes,url,status:response.status};
}
