/*
 * G010 3D Hero Asset Gallery. Genuine SHA-pinned GLB/WebGL presentation.
 * This cannot buy/equip/grant an item. All actual player state remains server-owned.
 * Models in the release-NOT-admitted mapping are preview-only in the isolated candidate.
 */
import * as THREE from "/assets/3d_shop/p048/vendor/three.module.js";
import { GLTFLoader } from "/assets/3d_shop/p048/vendor/jsm/loaders/GLTFLoader.js";
import { G009_FORMAL9_REPLACEMENT_ROWS } from "/js/g009_formal9_rights_cleared_replacement_catalog.js";

const G011_QA_MODE = ["localhost","127.0.0.1"].includes(location.hostname)
  && new URLSearchParams(location.search).get("g011_qa")==="1"
  && location.protocol==="http:";
const ROOT = document.getElementById("g010-3d-gallery");
const PANEL = document.getElementById("g009-panel-equipment");
const $ = (selector) => ROOT?.querySelector(selector);
const SHA = /^[0-9a-f]{64}$/i;
const MODELS = {
  character: "角色（33 款真實模型）",
  spirit: "棋靈（18 款成長模型）",
  accessory: "頭飾／背包（6 款）",
  weapon: "武器（4 款已確認權利模型）",
  bonus: "附加棋靈預覽（2 款）",
};
const state = { data: [], selected: null, renderer: null, scene: null, camera: null,
  group: null, frame: 0, resize: null, request: 0, drag: null, errors: [],
  loaded: 0, displayed: 0 };
let started = false;
function fail(message) {
  const el = $("#g010-3d-status");
  if (el) el.textContent = "3D 暫不可用：" + String(message);
  if (ROOT) ROOT.dataset.state = "unavailable";
}
function status(message) { const el = $("#g010-3d-status"); if (el) el.textContent = message; }
function admittedUrl(path) {
  if (typeof path !== "string" || !path.startsWith("assets/3d_shop/")
    || path.includes("..") || path.includes("\\") || path.includes("?") || path.includes("#")
    || !/\.glb$/i.test(path)) throw new Error("3d_asset_path_unapproved");
  return "/" + path;
}
function entry(kind, name, path, sha, id) {
  if (!SHA.test(sha)) throw new Error("3d_asset_missing_sha:" + id);
  return Object.freeze({ kind, name, url: admittedUrl(path), sha: sha.toLowerCase(), id });
}
async function fetchJson(url) {
  const response = await fetch(url, { credentials:"same-origin", cache:"no-store" });
  if (!response.ok) throw new Error("3d_manifest_http_" + response.status);
  return response.json();
}
async function catalog() {
  const [future, formal18, p048] = await Promise.all([
    fetchJson("/schemas/future30_c005_real_asset_runtime_mapping_manifest.json"),
    fetchJson("/assets/3d_shop/p048/companion/formal_18/mapping_manifest.json"),
    fetchJson("/assets/3d_shop/p048/runtime_manifest.json"),
  ]);
  if (future.authority?.authority_status !== "FINAL_V1_PRODUCT"
    || future.counts?.visual_model_count !== 33 || future.visual_models?.length !== 33
    || formal18.owner_approved_18_18 !== true || formal18.mappings?.length !== 18) {
    throw new Error("3d_catalog_authority_mismatch");
  }
  const models = [];
  for (const model of future.visual_models) {
    if (model.admission_state !== "ENABLED"
      || model.legal_provenance?.license_status !== "ADMITTED"
      || model.legal_provenance?.provenance_status !== "VERIFIED"
      || model.asset_status !== "PRESENT") throw new Error("character_admission_not_verified");
    models.push(entry("character", model.character_id + " · " + model.variant,
      model.runtime_glb, model.runtime_sha256, model.visual_model_id));
  }
  for (const mapping of formal18.mappings) {
    models.push(entry("spirit", mapping.pet_key.replaceAll("_"," ") + " · " + mapping.stage,
      mapping.runtime_glb, mapping.asset_sha256, mapping.pet_key + ":" + mapping.stage));
  }
  for (const item of p048.entries || []) {
    if (!["HEAD_PRESENTATION", "BACK_PRESENTATION", "COMPANION_PRESENTATION"].includes(item.authority_domain)) continue;
    if (item.source_provenance?.commercial_use_allowed !== true) continue;
    const kind = item.authority_domain === "COMPANION_PRESENTATION" ? "bonus" : "accessory";
    models.push(entry(kind, item.presentation_id.replaceAll("_"," "), item.runtime_asset,
      item.runtime_sha256, item.presentation_id));
  }
  for (const row of G009_FORMAL9_REPLACEMENT_ROWS) {
    if (row.rights?.RIGHTS_STATUS !== "RIGHTS_CLEARED"
      || row.rights?.LICENSE_TYPE !== "CC0-1.0"
      || row.release_eligibility !== "RIGHTS_CLEARED_RELEASE_NOT_ADMITTED") {
      throw new Error("weapon_rights_not_verified");
    }
    models.push(entry("weapon", row.server_item_id.replaceAll("_"," "), row.runtime_asset.slice(1),
      row.runtime_sha256, row.asset_id));
  }
  const totals = Object.fromEntries(Object.keys(MODELS).map(k=>[k,models.filter(x=>x.kind===k).length]));
  if (totals.character!==33 || totals.spirit!==18 || totals.accessory!==6
    || totals.weapon!==4 || totals.bonus!==2 || new Set(models.map(x=>x.id)).size!==63) {
    throw new Error("3d_catalog_count_or_identity_mismatch:" + JSON.stringify(totals));
  }
  // P038 historical 8 mainhand + 4 shields: isolated QA comparison ONLY.
  // Deliberately outside the 63 Product asset catalog and formal Docker pack.
  // Legacy D007/G009 NOT_CLEARED release gates remain unchanged.
  if (G011_QA_MODE) {
    const recovered=await fetchJson("/docs/handoffs/G011_P022_P038_QA_MODEL_RECOVERY_20261021.json");
    if (recovered.schema!=="G011_3D_P022_P038_RECOVERY_V1"
        || recovered.task!=="NON_PRODUCTION_VISUAL_TEST_ONLY"
        || recovered.release_status!=="NOT_ADMITTED"
        || recovered.expected_runtime_qa_models!==12
        || recovered.models?.length!==12
        || recovered.qa_preview_total!==28
        || recovered.p022_qa_derived_models?.length!==16) throw new Error("g011_qa_catalog_invalid");
    for(const model of recovered.models){
      if(model.formal_product_release!=="NOT_ADMITTED"
        || model.real_player_equip_enabled!==false
        || !["MAIN_HAND","OFF_HAND"].includes(model.slot)
        || !/^G011_P038_[A-Za-z0-9-]+$/.test(model.qa_id)) throw new Error("g011_qa_authority_invalid");
      const path=model.runtime_glb;
      if(!path.startsWith("assets/3d_shop/formal_character_equipment_v1/weapons/")
         && !/^tests\/e2e\/g011_private_qa_assets\/[A-Za-z0-9_-]+\.glb$/.test(path)){
        throw new Error("g011_qa_model_path_blocked");
      }
      const safeEntry=Object.freeze({kind:"p038_qa",name:model.name+" · "+model.slot,
        id:model.qa_id,sha:model.runtime_sha256.toLowerCase(),url:"/"+path});
      if(!SHA.test(safeEntry.sha))throw new Error("g011_qa_sha_invalid");
      models.push(safeEntry);
    }
    for (const model of recovered.p022_qa_derived_models) {
      if (model.qa_derived_only!==true || model.release_admitted!==false
        || model.real_player_equip_enabled!==false
        || !/^G011_P022_[A-Z0-9-]+$/.test(model.qa_id)
        || !/^tests\/e2e\/g011_private_qa_assets\/[A-Za-z0-9_-]+\.glb$/.test(model.runtime_glb)
        || !SHA.test(model.runtime_sha256)) {
        throw new Error("g011_p022_qa_unadmitted_model_blocked");
      }
      models.push(Object.freeze({kind:"p038_qa",
        name:model.name+" · "+model.category+"（QA）",
        id:model.qa_id,sha:model.runtime_sha256.toLowerCase(),
        url:"/"+model.runtime_glb}));
    }
    if(models.length!==91 || new Set(models.map(x=>x.id)).size!==91) {
      throw new Error("g011_qa_model_identity_conflict");
    }
  }
  return models;
}
function releaseResources(object) {
  const geo = new Set(), materials = new Set(), textures = new Set();
  object?.traverse?.(node=>{
    if (node.geometry) geo.add(node.geometry);
    for (const mat of (Array.isArray(node.material) ? node.material : [node.material]).filter(Boolean)) {
      materials.add(mat);
      for (const value of Object.values(mat)) if (value?.isTexture) textures.add(value);
    }
  });
  geo.forEach(x=>x.dispose()); materials.forEach(x=>x.dispose()); textures.forEach(x=>x.dispose());
  object?.removeFromParent?.();
}
function dispose() {
  ++state.request;
  cancelAnimationFrame(state.frame); state.frame=0;
  state.resize?.disconnect();state.resize=null;
  releaseResources(state.group);state.group=null;
  const canvas=state.renderer?.domElement;
  if (canvas) canvas.remove();
  state.renderer?.dispose();state.renderer?.forceContextLoss?.();
  state.renderer=null;state.camera=null;state.scene=null;state.drag=null;
  if (ROOT) ROOT.dataset.rendering="off";
}
function resize() {
  const host=$("#g010-3d-canvas");if (!host || !state.renderer) return;
  const rect=host.getBoundingClientRect();
  if (rect.width<32||rect.height<32)return;
  state.renderer.setPixelRatio(Math.min(devicePixelRatio||1,1.5));
  state.renderer.setSize(rect.width,rect.height,false);
  state.camera.aspect=rect.width/rect.height;state.camera.updateProjectionMatrix();
}
function mount() {
  if (state.renderer || !ROOT) return;
  const host=$("#g010-3d-canvas");
  if (!host)return;
  const scene=new THREE.Scene();scene.background=new THREE.Color(0x142439);
  const camera=new THREE.PerspectiveCamera(38,1,0.02,400);camera.position.set(4.1,2.3,6.5);
  camera.lookAt(0,0,0);
  scene.add(new THREE.HemisphereLight(0xffffff,0x41516f,2.2));
  const direct=new THREE.DirectionalLight(0xffe8c9,2.8);direct.position.set(3,7,6);scene.add(direct);
  const renderer=new THREE.WebGLRenderer({alpha:false,antialias:true,powerPreference:"low-power"});
  renderer.outputColorSpace=THREE.SRGBColorSpace;
  host.appendChild(renderer.domElement);
  const canvas=renderer.domElement;
  canvas.setAttribute("aria-label","可滑動旋轉的真實 3D 模型");
  canvas.style.touchAction="none";
  canvas.addEventListener("pointerdown",e=>{
    state.drag={id:e.pointerId,x:e.clientX,y:e.clientY};
    try{canvas.setPointerCapture(e.pointerId)}catch{}
  });
  canvas.addEventListener("pointermove",e=>{
    if (!state.drag||state.drag.id!==e.pointerId||!state.group)return;
    state.group.rotation.y+=(e.clientX-state.drag.x)*0.009;
    state.group.rotation.x=THREE.MathUtils.clamp(
      state.group.rotation.x+(e.clientY-state.drag.y)*0.002,-0.35,0.35);
    state.drag.x=e.clientX;state.drag.y=e.clientY;
  });
  for (const type of ["pointerup","pointercancel"])canvas.addEventListener(type,()=>state.drag=null);
  state.scene=scene;state.camera=camera;state.renderer=renderer;
  state.resize=new ResizeObserver(resize);state.resize.observe(host);resize();
  const animate=()=>{if (!state.renderer)return;state.renderer.render(scene,camera);state.frame=requestAnimationFrame(animate)};
  animate();ROOT.dataset.rendering="on";
}
async function showItem(model) {
  if (!model)return;
  state.selected=model.id;
  const token=++state.request;
  const old=state.group;if(old){releaseResources(old);state.group=null;}
  status("正在驗證並載入真實 GLB：" + model.name);
  try {
    const response=await fetch(model.url,{credentials:"same-origin"});
    if (!response.ok)throw new Error("model_http_"+response.status);
    const bytes=await response.arrayBuffer();
    if (token!==state.request||!state.renderer)return;
    const hash=[...new Uint8Array(await crypto.subtle.digest("SHA-256",bytes))]
      .map(b=>b.toString(16).padStart(2,"0")).join("");
    if (hash!==model.sha)throw new Error("model_integrity_rejected");
    const modelBase=new URL('.',new URL(model.url,location.origin)).href;
    const gltf=await new GLTFLoader().parseAsync(bytes,modelBase);
    const node=gltf.scene;if(!node?.isObject3D)throw new Error("model_has_no_scene");
    if (token!==state.request||!state.renderer){releaseResources(node);return;}
    const bounds=new THREE.Box3().setFromObject(node);
    if(bounds.isEmpty())throw new Error("model_has_no_geometry");
    const size=bounds.getSize(new THREE.Vector3());
    const max=Math.max(size.x,size.y,size.z);
    if(!Number.isFinite(max)||max<=0)throw new Error("invalid_model_dimensions");
    const center=bounds.getCenter(new THREE.Vector3());
    const holder=new THREE.Group();holder.add(node);
    node.position.sub(center);node.scale.setScalar(3.3/max);
    holder.rotation.set(0,0,0);
    state.scene.add(holder);state.group=holder;state.loaded+=1;state.displayed+=1;
    status("已載入 " + model.name + " · 真實 3D 可旋轉（僅展示，不代表已取得）");
    ROOT.dataset.state="ready";ROOT.dataset.assetId=model.id;ROOT.dataset.integrity="verified";
  } catch(error) {
    if(token!==state.request)return;
    state.errors.push(String(error));fail(error.message||error);
    ROOT.dataset.integrity="failed";
  }
}
function choices() {
  const type=$("#g010-3d-category"),select=$("#g010-3d-model");
  if (!type||!select)return;
  const group=type.value;
  select.replaceChildren();
  for(const item of state.data.filter(x=>x.kind===group)){
    const option=document.createElement("option");option.value=item.id;option.textContent=item.name;
    select.appendChild(option);
  }
  if(state.renderer)void showItem(state.data.find(x=>x.id===select.value));
}
async function init() {
  if(started)return;started=true;
  try{
    state.data=await catalog();
    const category=$("#g010-3d-category"),select=$("#g010-3d-model");
    if(G011_QA_MODE) MODELS.p038_qa="P022／P038 武器・盾牌・弓箭（28 件，內部測試）";
    Object.entries(MODELS).forEach(([name,label])=>{
      const opt=document.createElement("option");opt.value=name;opt.textContent=label;category.appendChild(opt);
    });
    category.addEventListener("change",choices);
    select.addEventListener("change",()=>{if(state.renderer)void showItem(state.data.find(x=>x.id===select.value))});
    $("#g010-3d-reset").addEventListener("click",()=>{if(state.group)state.group.rotation.set(0,0,0)});
    choices();
    status("已驗證資產清單：" + state.data.length + " 款；開啟裝備頁籤後載入");
    sync();
  }catch(e){state.errors.push(String(e));fail(e.message||e)}
}
function visible() {
  return PANEL&&!PANEL.hidden&&document.visibilityState!=="hidden"&&PANEL.getClientRects().length>0;
}
function sync(){
  if(!started||!state.data.length)return;
  if(!visible()){if(state.renderer)dispose();return;}
  if(state.renderer)return;
  try{mount();void showItem(state.data.find(x=>x.id===$("#g010-3d-model").value))}
  catch(e){state.errors.push(String(e));fail(e.message||e)}
}
if(ROOT&&PANEL){
  const observer=new MutationObserver(sync);
  observer.observe(PANEL,{attributes:true,attributeFilter:["hidden","style","class"]});
  for(const ancestor of [PANEL.parentElement,PANEL.parentElement?.parentElement].filter(Boolean)){
    observer.observe(ancestor,{attributes:true,attributeFilter:["hidden","style","class"]});
  }
  document.addEventListener("visibilitychange",sync);
  window.addEventListener("pagehide",dispose);
  document.addEventListener("click",()=>queueMicrotask(sync));
  void init();
}
export const G010_3D_GALLERY_CATEGORY_COUNTS=Object.freeze({character:33,spirit:18,accessory:6,weapon:4,bonus:2});
export function g010GalleryDiagnostics(){
  return Object.freeze({qa_only_p038_12:G011_QA_MODE,catalog_size:state.data.length,current:state.selected,
  loaded:state.loaded,rendered:state.displayed,live_canvas:!!state.renderer,
  integrity:ROOT?.dataset.integrity||"pending",errors:[...state.errors]});
}
