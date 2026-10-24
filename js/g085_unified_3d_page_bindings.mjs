// The same G008 identity contract and G009 hand-slot loader power both pages.
// Viewer remains a READ-ONLY projection. No purchase/equip/coin writes.
import {createReadOnlyHero3DViewer} from "./g085_shared_hero3d_viewer.mjs";
const backpack=document.getElementById("functional-wearable-preview-host");
const shop=document.getElementById("g085-shop-character-3d");
const host=backpack||shop;
if(host){
  const view=createReadOnlyHero3DViewer(host,{
    label:backpack?"背包 3D 角色與裝備":"商城 3D 角色試穿"});
  const defaultTryOn=Boolean(shop);
  const api=Object.freeze({
    show(itemId,{tryOn=defaultTryOn}={}){
      return view.show(itemId||null,{tryOn}).catch(error=>{
        console.warn("G085 shared 3D preview remains fail-closed",
          error instanceof Error?error.message:String(error));
        return null;
      });
    },
    getSnapshot:()=>view.getSnapshot(),
    refresh:()=>view.refresh(),
    destroy:()=>view.destroy(),
  });
  window.GoOdysseyUnified3D=api;
  if(shop){
    void import("./g009_formal9_rights_cleared_replacement_catalog.js")
      .then(({G009_FORMAL9_REPLACEMENT_ROWS})=>{
        const options=document.getElementById("g085-shop-3d-options");
        if(!options)return;
        const labels={iron_sword:"鐵劍",fox_fang:"狐牙",
          riverstone_sabre:"河石刀",bamboo_shadow_blade:"竹影短刃"};
        for(const row of G009_FORMAL9_REPLACEMENT_ROWS){
          if(row.rights?.PUBLIC_3D_PREVIEW_ADMITTED!==true)continue;
          const button=document.createElement("button");
          button.type="button";button.dataset.g085Shop3dItemId=row.server_item_id;
          button.textContent=labels[row.server_item_id]||row.server_item_id;
          button.setAttribute("aria-pressed","false");
          button.addEventListener("click",()=>{
            options.querySelectorAll("button").forEach(b=>b.setAttribute("aria-pressed",
              String(b===button)));
            shop.dataset.g085SelectedItemId=row.server_item_id;
            void api.show(row.server_item_id,{tryOn:true});
          });
          options.appendChild(button);
        }
      }).catch(()=>{shop.dataset.g0853d="unavailable";});
  }
  document.addEventListener("g085:3d-selection",(event)=>{
    const selected=event.detail||{};
    void api.show(selected.itemId,{tryOn:defaultTryOn});
  });
  view.ready.then(()=>{
    const itemId=host.dataset.g085SelectedItemId||null;
    void api.show(itemId,{tryOn:defaultTryOn});
    document.dispatchEvent(new Event("g085:3d-ready"));
  }).catch(error=>{
    host.dataset.g0853d="unavailable";
    console.warn("G085 3D unavailable; no false equipped model",
      error instanceof Error?error.message:String(error));
  });
  window.addEventListener("pagehide",()=>view.destroy(),{once:true});
}
