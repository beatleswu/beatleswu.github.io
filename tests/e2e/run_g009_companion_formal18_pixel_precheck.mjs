// Controlled real-GLB WebGL visibility precheck, not authenticated or Owner acceptance.
import { chromium } from 'playwright-core';
import { createServer } from 'node:http';
import { createReadStream } from 'node:fs';
import { mkdir, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const output = path.resolve(process.env.G009_PIXEL_OUTPUT || path.join(tmpdir(), 'g009-companion-pixel-precheck'));
if (output.startsWith(root + path.sep)) throw new Error('PIXEL_OUTPUT_MUST_BE_OUTSIDE_APPLICATION_WORKTREE');
await mkdir(output, { recursive: true });

const html = `<!doctype html><html><head><script type="importmap">{"imports":{"three":"/assets/3d_shop/p048/vendor/three.module.js"}}</script></head><body style="margin:0"><script type="module">
import * as THREE from '/assets/3d_shop/p048/vendor/three.module.js';
import { GLTFLoader } from '/assets/3d_shop/p048/vendor/jsm/loaders/GLTFLoader.js';
import { createG009SharedHeroAttachmentHost } from '/js/g009_shared_hero_attachment_host.js';
import { createFormal18AssetSource } from '/js/g009_companion_formal18_assets.mjs';
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xdde5ef);
const hero = new THREE.Mesh(new THREE.BoxGeometry(0.8, 2, 0.5),
  new THREE.MeshBasicMaterial({ color: 0x6d819a, transparent: true, opacity: 0.1, depthWrite: false }));
hero.position.y = 1;
scene.add(hero);
for (const name of ['hand.R', 'hand.L']) { const bone = new THREE.Bone(); bone.name = name; hero.add(bone); }
const host = createG009SharedHeroAttachmentHost(hero, THREE);
const camera = new THREE.PerspectiveCamera(42, 1, 0.01, 30);
camera.position.set(1.7, 1.5, 4.2);
camera.lookAt(0.25, 0.95, 0);
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setSize(512, 512);
renderer.setPixelRatio(1);
renderer.outputColorSpace = THREE.SRGBColorSpace;
document.body.appendChild(renderer.domElement);
scene.add(new THREE.AmbientLight(0xffffff, 2));
const light = new THREE.DirectionalLight(0xffffff, 3);
light.position.set(3, 5, 4); scene.add(light);
const loader = new GLTFLoader();
const assets = createFormal18AssetSource({ THREE,
  parse: (bytes, url) => loader.parseAsync(bytes, url),
  getLayout: () => host.getSlotLayout('COMPANION'),
});
let descriptor = null;
host.registerResolver('COMPANION', id => descriptor?.presentation_id === id ? descriptor : null);
const gl = renderer.getContext();
const debug = gl.getExtension('WEBGL_debug_renderer_info');
const gpu = debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
function pixels() {
  renderer.render(scene, camera);
  const value = new Uint8Array(512 * 512 * 4);
  gl.readPixels(0, 0, 512, 512, gl.RGBA, gl.UNSIGNED_BYTE, value);
  return value;
}
window.__precheck = { gpu, async render(pet_key, level) {
  host.detach('COMPANION');
  const before = pixels();
  descriptor = await assets.resolve({ pet_key, level });
  const attached = await host.attach('COMPANION', descriptor.presentation_id, row => assets.load(row));
  if (attached.status !== 'attached') throw new Error('COMPANION_ATTACH_' + attached.status);
  const after = pixels();
  let changed = 0;
  for (let i = 0; i < after.length; i += 4) {
    if (Math.abs(after[i] - before[i]) + Math.abs(after[i+1] - before[i+1])
      + Math.abs(after[i+2] - before[i+2]) >= 30) changed++;
  }
  const companion = host.diagnostics().slots.find(row => row.slot === 'COMPANION');
  return { pet_key, stage: descriptor.stage, sha256: descriptor.asset_sha256,
    changed_pixels: changed, child_count: companion.child_count,
    canvas_count: document.querySelectorAll('canvas').length };
}, dispose() { host.destroy(); renderer.dispose(); renderer.domElement.remove(); } };
</script></body></html>`;

const mime = { '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.glb': 'model/gltf-binary' };
const server = createServer(async (request, response) => {
  try {
    const pathname = new URL(request.url, 'http://127.0.0.1').pathname;
    if (pathname === '/__precheck') {
      response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
      response.end(html);
      return;
    }
    const target = path.resolve(root, '.' + decodeURIComponent(pathname));
    if (!target.startsWith(root + path.sep)) throw new Error('PATH_OUTSIDE_ROOT');
    const info = await stat(target);
    if (!info.isFile()) throw new Error('NOT_FILE');
    response.writeHead(200, { 'content-type': mime[path.extname(target)] || 'application/octet-stream' });
    createReadStream(target).pipe(response);
  } catch (error) {
    response.writeHead(404); response.end(String(error));
  }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const port = server.address().port;
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: (process.env.G009_CHROME_GPU_ARGS || '--use-gl=angle,--use-angle=d3d11,--enable-webgl,--ignore-gpu-blocklist').split(','),
});
const page = await browser.newPage({ viewport: { width: 512, height: 512 }, deviceScaleFactor: 1 });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const results = [];
try {
  await page.goto(`http://127.0.0.1:${port}/__precheck`);
  await page.waitForFunction(() => Boolean(window.__precheck), { timeout: 30000 });
  const gpu = await page.evaluate(() => window.__precheck.gpu);
  for (const pet_key of ['ink_drop_kelpie', 'whispering_void_kit', 'star_shell_hatchling',
    'starpath_antlerling', 'fatty', 'obsidian_bastion']) {
    for (const [level, stage] of [[9, 'I'], [10, 'II'], [25, 'III']]) {
      const row = await page.evaluate(([key, petLevel]) => window.__precheck.render(key, petLevel), [pet_key, level]);
      if (row.stage !== stage || row.child_count !== 1 || row.canvas_count !== 1 || row.changed_pixels < 100) {
        throw new Error('PIXEL_OR_LIFECYCLE_FAILURE:' + JSON.stringify(row));
      }
      await page.screenshot({ path: path.join(output, `${pet_key}_${stage}.png`) });
      results.push(row);
    }
  }
  if (errors.length) throw new Error('BROWSER_PAGE_ERRORS:' + JSON.stringify(errors));
  await page.evaluate(() => window.__precheck.dispose());
  const receipt = { kind: 'CONTROLLED_WEBGL_PIXEL_PRECHECK_NOT_OWNER_OR_AUTHENTICATED',
    gpu, rows: results, browser_errors: errors, output };
  await writeFile(path.join(output, 'receipt.json'), JSON.stringify(receipt, null, 2) + '\n');
  console.log(JSON.stringify({ status: 'PASS', gpu, rows: results.length,
    min_changed_pixels: Math.min(...results.map(row => row.changed_pixels)), output }));
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
