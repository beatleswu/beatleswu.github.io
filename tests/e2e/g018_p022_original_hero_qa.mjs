// G018 disposable localhost-only P022 candidate. Works INSIDE the ORIGINAL /hero
// G008 3D renderer. No production P038 sale/equip/release authorization.
import * as THREE from "/assets/3d_shop/p048/vendor/three.module.js";
import {GLTFLoader} from "/assets/3d_shop/p048/vendor/jsm/loaders/GLTFLoader.js";
import {
 registerHeroPresentationResolver,registerHeroPresentationRehydrator,
 registerHeroPresentationTeardown
} from "/js/g008_future30_hero_renderer.js";
import {createHeroEquipmentAttachmentAdapter} from "/js/hero_equipment_attachment_adapter.js";
import {projectServerEquippedHandItems} from "/js/g009_equipment_inventory_projection.js";
const QA=location.protocol==="http:"&&location.hostname==="127.0.0.1"
 &&new URLSearchParams(location.search).get("g018_qa")==="1";
const SHA=/^[a-f0-9]{64}$/;
const index=new Map();
let once=false;
let currentAdapter=null;
let finalProof={state:"uninitialized",error:null};
function recordProof(x){finalProof=Object.freeze(x);window.__G018_P022_INPAGE_QA_PROOF__=finalProof;}
function fail(msg){throw new Error("G018_FAIL_CLOSED_"+msg);}
function fromManifest(x){
 if(x.formal_product_release!=="NOT_ADMITTED"
  ||x.equip_enabled!==false||x.shop_enabled!==false
  ||x.formal_item_id!==null||x.legal_admission_proven!==false
  ||!/^G017_P022_[A-Z0-9-]+$/.test(x.qa_id)
  ||!SHA.test(x.runtime_sha256)
  ||x.attach_test_slot!=="MAIN_HAND"
  ||!["MAIN_HAND_STATIC_QA","PROJECTILE_PROP_ONLY"].includes(x.functional_class)
  ||!/^tests\/e2e\/g011_private_qa_assets\/[A-Za-z0-9_]+_p022_qa\.glb$/.test(x.runtime_glb))
  fail("original_qa_asset_source_or_release_admission");
 if(x.functional_class==="PROJECTILE_PROP_ONLY")return null;
 const id="g018_qa_"+x.code.toLowerCase().replace(/-/g,"_");
 if(!/^g018_qa_[a-z0-9_]+$/.test(id)||index.has(id))
  fail("duplicated_item_id");
 const desc=Object.freeze({
  server_item_id:id,asset_id:x.qa_id,presentation_id:x.qa_id,
  slot:"MAIN_HAND",runtime_asset:"/"+x.runtime_glb,
  runtime_sha256:x.runtime_sha256,release_eligibility:"NOT_ADMITTED",
  equip_capability:false,test_only:true,real_player_equip_enabled:false,
  functional_class:x.functional_class});
 index.set(id,desc);return desc;
}
async function loadMesh(desc,ctx){
 if(!QA||!index.has(desc.server_item_id)||index.get(desc.server_item_id)!==desc
  ||desc.release_eligibility!=="NOT_ADMITTED"||desc.test_only!==true)
  fail("descriptor_is_not_authorized");
 const response=await fetch(desc.runtime_asset,{cache:"no-store",credentials:"same-origin"});
 if(!response.ok)fail("model_http_"+response.status);
 const bytes=await response.arrayBuffer();
 const sha=Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes)))
  .map(n=>n.toString(16).padStart(2,"0")).join("");
 if(sha!==desc.runtime_sha256)fail("source_SHA");
 const loaded=await new GLTFLoader().parseAsync(bytes,new URL(desc.runtime_asset,location.href).href);
 const model=loaded.scene||loaded.scenes?.[0];
 if(!model?.isObject3D)fail("missing_GLTF_scene");
 model.updateMatrixWorld(true);
 const box=new THREE.Box3().setFromObject(model);
 if(box.isEmpty())fail("missing_geometry");
 const size=box.getSize(new THREE.Vector3());
 const largest=Math.max(size.x,size.y,size.z);
 const pivot=box.getCenter(new THREE.Vector3());
 if(desc.slot==="MAIN_HAND")pivot.y=box.min.y;
 if(!largest||!Number.isFinite(largest))fail("invalid_geometry");
 const layout=ctx.host.getSlotLayout(desc.slot);
 const boneScale=layout.hand_world_scale;
 if(!Array.isArray(boneScale)||boneScale.length!==3
   ||boneScale.some(v=>!Number.isFinite(v)))fail("missing_bone_scale");
 const inherited=Math.max(...boneScale.map(Math.abs));
 const heroHeight=layout.character_size[1];
 if(inherited<=0||heroHeight<=0)fail("invalid_hand_scale");
 const scale=(heroHeight*(desc.slot==="MAIN_HAND"?0.27:0.31))/
   (largest*inherited);
 const group=new THREE.Group();
 group.name="G018_QA_UNRELEASED_"+desc.asset_id;
 group.userData={server_item_id:desc.server_item_id,asset_id:desc.asset_id,
   release_admitted:false,qa:true,runtime_sha256:sha};
 model.position.sub(pivot);
 group.scale.setScalar(scale);
 group.add(model);
 return group;
}
async function rehydrate({appearance,host,generation}){
 currentAdapter?.dispose();
 currentAdapter=createHeroEquipmentAttachmentAdapter(
   {getHeroSharedAttachmentHost:()=>host},
   {sharedHost:host,allowTestOnlyDescriptors:true,
    loadPresentation:(desc)=>loadMesh(desc,{host})});
 const r=await fetch("/api/player/inventory",{credentials:"include",cache:"no-store"});
 if(!r.ok)fail("server_inventory_http_"+r.status);
 const inventory=await r.json();
 const projection=projectServerEquippedHandItems(inventory,(itemId,slot)=>{
  const desc=index.get(itemId);
  return desc?.slot===slot?desc:null;
 });
 if(projection.status!=="projected")fail("server_equipment_conflict");
 const selected=projection.slots;
 if(selected.some(x=>x.status==="failed_closed"))fail("server_selection_failed_closed");
 const results=[];
 for(const x of selected){
  results.push(x.status==="resolved"?
   await currentAdapter.setHand(x.slot,x.descriptor,appearance):
   currentAdapter.detach(x.slot));
 }
 const diag=host.diagnostics();
 const proof={state:"ready",generation,character:appearance.character_key,
  inventory_authority:"authenticated:/api/player/inventory",
  exact_release_admission:false,server_definitions_persisted:false,
  slots:diag.slots.filter(x=>x.slot==="MAIN_HAND"||x.slot==="OFF_HAND"),
  results,model_count:index.size,projectile_equip_rejected:true,
  selected: selected.map(x=>({slot:x.slot,status:x.status,
    server_item_id:x.item_id||null,
    presentation_id:x.descriptor?.presentation_id||null}))};
 recordProof(proof);
 return proof;
}
export async function installG018P022OriginalHeroQA(){
 if(once)return;
 if(!QA)fail("not_loopback_explicit_opt_in");
 once=true;
 const response=await fetch("/docs/handoffs/G017_P022_16_QA_SOURCE_AND_ATTACHMENT_20261021.json",
  {cache:"no-store"});
 if(!response.ok)fail("manifest_missing");
 const manifest=await response.json();
 if(manifest.schema!=="G017_P022_16_SOURCED_QA_V1"
  ||manifest.release_status!=="NOT_ADMITTED"
  ||manifest.models?.length!==16)fail("manifest_invalid");
 const all=manifest.models.map(fromManifest);
 if(index.size!==13||all.filter(Boolean).length!==13
    ||all.filter(x=>x===null).length!==3
    ||[...index.values()].some(x=>x.slot!=="MAIN_HAND"))
  fail("manifest_count_or_projectile_gate");
 const resolver=slot=>(assetId)=>{
  for(const desc of index.values())if(desc.presentation_id===assetId&&desc.slot===slot)
   return desc;
  return null;
 };
 for(const slot of ["MAIN_HAND","OFF_HAND"]){
  registerHeroPresentationResolver(slot,resolver(slot));
 }
 registerHeroPresentationTeardown("G018_P022_LOCAL_QA_ONLY",
   ()=>{currentAdapter?.dispose();currentAdapter=null});
 registerHeroPresentationRehydrator("G018_P022_LOCALHOST_NATIVE_PG",
   async ctx=>{
    try{return await rehydrate(ctx);}
    catch(e){
     currentAdapter?.detach("MAIN_HAND");
     currentAdapter?.detach("OFF_HAND");
     recordProof({state:"failed_closed",error:String(e)});
     throw e;
    }
   });
 recordProof({state:"installed",model_count:index.size,asset_admitted:false});
}
