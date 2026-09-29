import * as THREE from "/assets/3d_shop/p048/vendor/three.module.js";
import {GLTFLoader} from "/assets/3d_shop/p048/vendor/jsm/loaders/GLTFLoader.js";
import * as hero from "./g008_future30_hero_renderer.js";
import {createCompanionChild} from "./g009_companion_child.mjs";
import {createFormal18AssetSource} from "./g009_companion_formal18_assets.mjs";

const loader = new GLTFLoader();
const assets = createFormal18AssetSource({
  THREE, parse:(bytes,path)=>loader.parseAsync(bytes,path),
  getLayout:()=>hero.getHeroSharedAttachmentHost().getSlotLayout("COMPANION"),
});
// No mount, renderer, pagehide or animation loop: the G008 owner invokes us.
export const companion = createCompanionChild({
  hero, resolvePresentation:assets.resolve, loadPresentation:assets.load,
  onChange:state=>{ window.__G009_COMPANION_RENDER_STATE__ = state; },
});
