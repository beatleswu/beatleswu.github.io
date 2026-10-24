// G085H: one read-only 3D presentation engine for Backpack and Shop.
// Uses the exact G008 Future30 identity checks and G009 slots/asset mappings.
// This module never writes player, currency, wardrobe or equipment state.
import * as THREE from "/assets/3d_shop/p048/vendor/three.module.js";
import {GLTFLoader} from "/assets/3d_shop/p048/vendor/jsm/loaders/GLTFLoader.js";
import {verifyCurrentHeroProjection,loadVerified3DAsset}
  from "./g085_shared_authoritative_3d_core.mjs";
import {createG009SharedHeroAttachmentHost}
  from "./g009_shared_hero_attachment_host.js";
import {createHeroEquipmentAttachmentAdapter}
  from "./hero_equipment_attachment_adapter.js";
import {g009Formal9ReplacementRowForItem}
  from "./g009_formal9_rights_cleared_replacement_catalog.js";
import {projectServerEquippedHandItems}
  from "./g009_equipment_inventory_projection.js";

function exactVisual(itemId) {
  const d=g009Formal9ReplacementRowForItem(itemId);
  return d && d.server_item_id===itemId && d.slot==="MAIN_HAND"
    && d.presentation_class && d.rights?.PUBLIC_3D_PREVIEW_ADMITTED===true
    && d.equip_capability===false && d.rights?.PRODUCTION_ASSET_ADMISSION===false
    && d.asset_id==="WEAPON_"+d.runtime_sha256.slice(0,12).toUpperCase()
    ? {...d,presentation_id:d.asset_id}:null;
}
// Keep all texture/geometry disposal scoped to this scene, never global.
function disposeScene(root) {
  if(!root)return;
  root.traverse?.(node=>{
    node.geometry?.dispose?.();
    for(const m of (Array.isArray(node.material)?node.material:[node.material])){
      m?.dispose?.();
      for(const texture of Object.values(m||{}))if(texture?.isTexture)texture.dispose();
    }
  });
  root.removeFromParent?.();
}
function safeModel(d,glb) {
  const node=glb.scene||glb.scenes?.[0];
  if(!node?.isObject3D)throw new Error("g085_3d_model_missing_scene");
  node.position.fromArray(d.position.map(Number));
  node.rotation.fromArray(d.rotation.map(Number));
  node.scale.fromArray(d.scale.map(Number));
  node.name="G009_EQUIPMENT_"+d.presentation_id;
  node.userData={...node.userData,server_item_id:d.server_item_id,
    asset_id:d.asset_id,visual_only:true};
  return node;
}
async function readJson(path,signal) {
  const r=await fetch(path,{credentials:"include",cache:"no-store",signal});
  if(!r.ok)throw new Error("g085_server_authority_http_"+r.status);
  return r.json();
}
export function createReadOnlyHero3DViewer(host,{label="3D 主角"}={}) {
  if(!host?.isConnected)throw new Error("g085_3d_container_missing");
  let disposed=false,root=null,renderer=null,scene=null,hostSlots=null,adapter=null;
  let currentDescriptor=null,ownedInventory=[],playerAppearance=null;
  let camera=null,turntable=null,zoom=1,angle=0,drag=null;
  let lastStatus="loading",lastPresentation=null,shownItemId=null,version=0;
  const controller=new AbortController(),signal=controller.signal;
  const statusNode=document.createElement("div");
  statusNode.className="g085-3d-view-status";
  statusNode.setAttribute("role","status");
  statusNode.setAttribute("aria-live","polite");
  host.replaceChildren(statusNode);
  host.dataset.g0853d="loading";
  function message(state,msg) {
    if(disposed)return;
    lastStatus=state;
    host.dataset.g0853d=state;
    statusNode.textContent=msg;
  }
  function framing(){
    if(!root||!camera)return null;
    camera.updateMatrixWorld(true);
    const b=new THREE.Box3().setFromObject(root),values=[];
    for(const x of [b.min.x,b.max.x])
      for(const y of [b.min.y,b.max.y])
        for(const z of [b.min.z,b.max.z])
          values.push(new THREE.Vector3(x,y,z).project(camera));
    return {min_y:Math.min(...values.map(p=>p.y)),
      max_y:Math.max(...values.map(p=>p.y)),
      min_x:Math.min(...values.map(p=>p.x)),
      max_x:Math.max(...values.map(p=>p.x))};
  }
  function getSnapshot(){
    const hand=hostSlots?.diagnostics?.()?.slots?.find(slot=>slot.slot==="MAIN_HAND");
    return Object.freeze({framing_ndc:framing(),status:lastStatus,item_id:shownItemId,
      presentation_id:lastPresentation,character_key:playerAppearance?.character_key||null,
      visual_only:true,canvas_count:host.querySelectorAll("canvas").length,
      main_hand_id:hand?.presentation_id||null,main_hand_child_count:hand?.child_count||0,
      orbit_yaw_radians:angle,zoom});
  }
  function resize(){
    if(!renderer||!camera||disposed)return;
    const w=Math.max(1,host.clientWidth),h=Math.max(1,host.clientHeight);
    renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();
  }
  const pointers=new Map();
  let pinch=null;
  function down(e){
    if(disposed)return;
    pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
    host.setPointerCapture?.(e.pointerId);
    if(pointers.size===1)drag={x:e.clientX,y:e.clientY};
    if(pointers.size===2){const [a,b]=[...pointers.values()];
      pinch=Math.hypot(a.x-b.x,a.y-b.y);}
  }
  function move(e){
    if(!pointers.has(e.pointerId)||disposed)return;
    pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
    if(pointers.size===2&&pinch!=null){
      const [a,b]=[...pointers.values()],dist=Math.hypot(a.x-b.x,a.y-b.y);
      if(dist>0){zoom=THREE.MathUtils.clamp(zoom*pinch/dist,.5,2.3);pinch=dist;}
    }else if(drag){angle+=(e.clientX-drag.x)*.012;drag={x:e.clientX,y:e.clientY};}
  }
  function up(e){pointers.delete(e.pointerId);if(!pointers.size){drag=null;pinch=null;}}
  function wheel(e){if(disposed)return;e.preventDefault();
    zoom=THREE.MathUtils.clamp(zoom*(e.deltaY>0?1.09:.91),.5,2.3);}
  function keydown(e){if(e.key==="ArrowLeft"||e.key==="ArrowRight"){
    e.preventDefault();angle+=(e.key==="ArrowLeft"?-.2:.2);}
    else if(e.key==="Home"){angle=0;zoom=1;}}
  host.addEventListener("pointerdown",down);host.addEventListener("pointermove",move);
  host.addEventListener("pointerup",up);host.addEventListener("pointercancel",up);
  host.addEventListener("wheel",wheel,{passive:false});
  host.addEventListener("keydown",keydown);host.tabIndex=0;host.style.touchAction="none";
  const visibility=()=>{if(document.hidden)renderer?.setAnimationLoop(null);
    else if(renderer)renderer.setAnimationLoop(frame);};
  document.addEventListener("visibilitychange",visibility);
  const observer=typeof ResizeObserver!=="undefined"?new ResizeObserver(resize):null;
  observer?.observe(host);
  function fitSharedSceneCamera(){
    if(!root||!camera||!turntable)return;
    // G009 hand attachments can extend beyond the Future30 character mesh.
    // Frame the *actual unified character+equipped model* world bounds,
    // including both hands, rather than taking the avatar-only bounds once.
    turntable.updateMatrixWorld(true);
    const b=new THREE.Box3().setFromObject(turntable);
    if(b.isEmpty())throw new Error("g085_unified_3d_bounds_empty");
    const size=b.getSize(new THREE.Vector3());
    const center=b.getCenter(new THREE.Vector3());
    const tan=Math.tan(THREE.MathUtils.degToRad(camera.fov)/2);
    const distanceY=size.y/(2*tan);
    const distanceX=size.x/(2*tan*Math.max(.15,camera.aspect));
    const base=Math.max(3.4,Math.max(distanceX,distanceY)*1.48+size.z/2);
    camera.userData.g085base=base;
    camera.userData.g085target=center.clone();
    camera.position.set(center.x,center.y+.15,center.z+base*zoom);
    camera.lookAt(center);
    camera.updateMatrixWorld(true);
  }
  function frame(){
    if(disposed||!scene||!camera||!renderer||document.hidden||!host.isConnected)return;
    turntable.rotation.y=angle;
    const target=camera.userData.g085target;
    // G008 Hero focuses the actual character-model bounds. Camera origin
    // at (0,0,z) looks *upward* at that target and cropped the model head.
    camera.position.set(target.x,target.y+0.15,
      target.z+Math.max(1,camera.userData.g085base)*zoom);
    camera.lookAt(target);
    renderer.render(scene,camera);
  }
  async function load() {
    const [catalog,appearance,inventory]=await Promise.all([
      readJson("/api/player/character-catalog",signal),
      readJson("/api/player/appearance",signal),
      readJson("/api/player/inventory",signal)]);
    if(!Array.isArray(inventory))throw new Error("g085_inventory_authority_invalid");
    const {runtime}=verifyCurrentHeroProjection(catalog,appearance);
    const verified=await loadVerified3DAsset(runtime.runtime_glb,runtime.runtime_sha256,signal);
    const gltf=await new GLTFLoader().parseAsync(verified.bytes,new URL(verified.url,location.href).href);
    if(disposed)return;
    const model=gltf.scene||gltf.scenes?.[0];
    if(!model?.isObject3D)throw new Error("g085_character_3d_scene_missing");
    let meshes=0;model.traverse(n=>{if(n.isMesh)meshes++;});
    if(!meshes)throw new Error("g085_character_3d_mesh_missing");
    root=model;playerAppearance=appearance;ownedInventory=inventory;
    const bounds=new THREE.Box3().setFromObject(root),size=bounds.getSize(new THREE.Vector3());
    const center=bounds.getCenter(new THREE.Vector3());
    scene=new THREE.Scene();scene.add(new THREE.HemisphereLight(0xffffff,0x334155,2));
    const key=new THREE.DirectionalLight(0xffedce,2.6);key.position.set(-3,7,8);scene.add(key);
    turntable=new THREE.Group();turntable.add(root);scene.add(turntable);
    camera=new THREE.PerspectiveCamera(34,1,.01,100);
    camera.userData.g085base=Math.max(3.4,size.y*2.8);
    camera.userData.g085target=center.clone();
    renderer=new THREE.WebGLRenderer({alpha:true,antialias:true,powerPreference:"low-power"});
    renderer.setPixelRatio(Math.min(devicePixelRatio||1,2));
    renderer.outputColorSpace=THREE.SRGBColorSpace;
    host.prepend(renderer.domElement);resize();
    fitSharedSceneCamera();
    hostSlots=createG009SharedHeroAttachmentHost(root,THREE);
    hostSlots.registerResolver("MAIN_HAND",id=>
      currentDescriptor?.presentation_id===id?currentDescriptor:null);
    adapter=createHeroEquipmentAttachmentAdapter(
      {getHeroSharedAttachmentHost:()=>hostSlots},
      {loadPresentation:async desc=>{
        const data=await loadVerified3DAsset(desc.runtime_asset,desc.runtime_sha256,signal);
        const glb=await new GLTFLoader().parseAsync(data.bytes,new URL(data.url,location.href).href);
        return safeModel(desc,glb);
      }});
    renderer.setAnimationLoop(frame);
    message("ready","3D 主角已載入 · 裝備以伺服器資料為準");
  }
  async function select(itemId=null,{tryOn=false}={}){
    const request=++version;
    shownItemId=itemId;
    if(!playerAppearance){
      if(!ready)throw new Error("g085_3d_viewer_not_initialized");
      await ready;
    }
    if(disposed||request!==version)return;
    currentDescriptor=null;lastPresentation=null;
    adapter?.detach("MAIN_HAND");
    fitSharedSceneCamera();
    const actual=projectServerEquippedHandItems(ownedInventory,(id,slot)=>{
      const candidate=exactVisual(id);
      return candidate?.slot===slot?candidate:null;
    });
    let descriptor=null,note="";
    if(itemId){
      const owned=ownedInventory.some(x=>x?.item_id===itemId&&Number(x.owned_quantity??1)>0);
      if(tryOn) {
        descriptor=exactVisual(itemId);
        note=descriptor?"商城 3D 試穿 · 不會購買或裝備":"此商品缺少核准的 3D 預覽模型";
      }else if(!owned) {
        note="未持有此物品 · 不提供裝備展示";
      }else{
        descriptor=exactVisual(itemId);
        const equipped=ownedInventory.some(x=>x?.item_id===itemId&&x.equipped===true);
        note=descriptor?(equipped?"已裝備 · 伺服器權威":"已持有 · 僅供3D檢視，未正式裝備")
          :"此物品沒有核准的 3D 模型 · 不使用 2D 疊圖";
      }
    }else{
      const main=actual.slots.find(x=>x.slot==="MAIN_HAND");
      descriptor=main?.status==="resolved"?main.descriptor:null;
      note=actual.status==="failed_closed"?"裝備投影缺少核准 3D 對照 · 未套用錯誤模型":
        descriptor?"已裝備 · 伺服器權威":"目前沒有核准的手持 3D 裝備";
    }
    if(descriptor){
      currentDescriptor=descriptor;
      try{
        const result=await adapter.setHand("MAIN_HAND",descriptor,playerAppearance);
        if(request!==version||disposed)return;
        if(result.status==="attached"||result.status==="unchanged"||result.status==="reused"){
          lastPresentation=descriptor.presentation_id;
          fitSharedSceneCamera();
          message("ready",note);
        }else{
          message("unavailable","裝備模型未能掛載；不以其他物品替代");
        }
      }catch(error){
        if(request===version&&!disposed)message("unavailable","3D 裝備載入失敗 · 不影響持有權");
      }
    }else message("unsupported",note);
    return getSnapshot();
  }
  async function refresh(){message("loading","正在確認角色與裝備…");destroyModel();
    await load();return select(shownItemId,{tryOn:lastTryOn});}
  let lastTryOn=false,ready;
  function show(itemId=null,options={}){
    lastTryOn=options.tryOn===true;
    return select(itemId,{tryOn:lastTryOn});
  }
  function destroyModel(){
    ++version;adapter?.dispose();hostSlots?.destroy();hostSlots=null;adapter=null;
    renderer?.setAnimationLoop(null);renderer?.dispose();
    renderer?.domElement?.remove();renderer=null;disposeScene(root);
    root=null;scene=null;camera=null;turntable=null;currentDescriptor=null;
  }
  function destroy(){
    if(disposed)return;disposed=true;controller.abort();destroyModel();
    observer?.disconnect();document.removeEventListener("visibilitychange",visibility);
    host.removeEventListener("pointerdown",down);host.removeEventListener("pointermove",move);
    host.removeEventListener("pointerup",up);host.removeEventListener("pointercancel",up);
    host.removeEventListener("wheel",wheel);host.removeEventListener("keydown",keydown);
    host.dataset.g0853d="destroyed";pointers.clear();host.replaceChildren();
  }
  ready=load().catch(e=>{
    message("unavailable","3D 暫時無法使用 · 不以錯誤圖片充當已穿戴裝備");
    throw e;
  });
  return Object.freeze({ready,show,refresh,destroy,getSnapshot});
}
