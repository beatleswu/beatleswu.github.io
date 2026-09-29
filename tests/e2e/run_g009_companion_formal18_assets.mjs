// Asset-byte and loader-boundary test; parse is a controlled Three node, not GPU acceptance.
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {createHash} from "node:crypto";
import * as THREE from "../../assets/3d_shop/p048/vendor/three.module.js";
import {createFormal18AssetSource, MANIFEST_SHA256} from "../../js/g009_companion_formal18_assets.mjs";
import {COMPANION_FORMAL_18_PET_KEYS, validateCompanionFormal18Manifest} from "../../js/companion_formal_18_mapping.js";
const root = new URL("../../",import.meta.url);
globalThis.location={href:"http://127.0.0.1/hero"};
let mode=null, parsed=0, lastNode=null;
const makeSource=()=>createFormal18AssetSource({
  THREE,
  getLayout:()=>({character_size:[1,2,1],anchor_position:[0.42,0.24,0.12],ground_y:0}),
  fetchImpl:async(url,options)=>{
    assert.equal(options.credentials,"same-origin");
    assert.equal(options.cache,"no-store");
    if(mode==="missing" && url.endsWith(".glb")) return {ok:false,status:404};
    const bytes=await readFile(new URL(url.slice(1),root));
    if(mode==="corrupt" && url.endsWith(".glb")) bytes[bytes.length-1]^=1;
    if(mode==="manifest" && url.endsWith(".json")) bytes[0]^=1;
    return {ok:true,arrayBuffer:async()=>bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.length)};
  },
  parse:async bytes=>{
    parsed++;
    assert.equal(new TextDecoder().decode(bytes.slice(0,4)),"glTF");
    const node=new THREE.Mesh(new THREE.BoxGeometry(1,2,1),new THREE.MeshStandardMaterial());
    node.userData.disposed=0;
    node.geometry.addEventListener("dispose",()=>node.userData.disposed++);
    lastNode=node;
    return {scene:node};
  },
});
const source=makeSource();
const paths=new Set();
for(const pet_key of COMPANION_FORMAL_18_PET_KEYS) {
  for(const [level,stage] of [[9,"I"],[10,"II"],[24,"II"],[25,"III"]]) {
    const d=await source.resolve({pet_key,level,stage:"III"});
    assert.equal(d.pet_key,pet_key); assert.equal(d.stage,stage);
    paths.add(d.asset_path);
    const loaded=await source.load(d);
    const bounds=new THREE.Box3().setFromObject(loaded.node);
    assert(Math.abs(bounds.min.y+0.24)<1e-6,"ground contact in anchor-local units");
    assert.equal(loaded.node.userData.goOdysseyCompanion.asset_sha256,d.asset_sha256);
    loaded.disposeOwnedResources(); assert.equal(lastNode.userData.disposed,1);
  }
}
assert.equal(paths.size,18);
for(const bad of ["Bunny","Corgi","unknown"]) await assert.rejects(source.resolve({pet_key:bad,level:1}));
const descriptor=await source.resolve({pet_key:"fatty",level:25});
for(const fault of ["missing","corrupt"]) {
  const before=parsed; mode=fault;
  await assert.rejects(source.load(descriptor)); assert.equal(parsed,before);
}
mode="manifest"; await assert.rejects(makeSource().resolve({pet_key:"fatty",level:1}),/MANIFEST_SHA_MISMATCH/);
mode=null;
const manifest=await readFile(new URL("assets/3d_shop/p048/companion/formal_18/mapping_manifest.json",root));
assert.equal(createHash("sha256").update(manifest).digest("hex"),MANIFEST_SHA256);
const incomplete=JSON.parse(manifest); incomplete.mappings.pop();
assert.throws(()=>validateCompanionFormal18Manifest(incomplete),/18 rows/);
const invalidStage=JSON.parse(manifest); invalidStage.mappings[0].stage="IV";
assert.throws(()=>validateCompanionFormal18Manifest(invalidStage),/unknown pet or stage/);
console.log("FORMAL18_ASSET_BYTES=18/18 PASS; KEYS=6/6; BOUNDARIES=9,10,24,25 PASS");
console.log("MANIFEST_ASSET_TAMPER_AND_MISSING=FAIL_CLOSED PASS; AUTHENTICATED_RELOG=NOT_RUN");
