'use strict';

const fs = require('fs');
const path = require('path');
const { chromium } = require('D:\\go-website\\node_modules\\playwright-core');

const ROOT = path.resolve(__dirname, '..');
const PACK = path.join(ROOT, 'docs', 'planning', 'rpg_wave2_master_lane_a_pure_cosmetic_full_body_art_closure_003');
const SOURCE_DIR = path.join(ROOT, 'assets', 'hero', 'items');
const OUTPUT_DIR = path.join(PACK, 'matrices', 'existing_catalog_icons');
const IDS = [
  'hat_cloth', 'hat_bamboo', 'hat_student', 'hat_feather', 'hat_scholar',
  'hat_foxmask', 'hat_onihorns', 'hat_dragon_horn', 'hat_celestial_crown', 'hat_premium',
  'title_beginner', 'title_scholar', 'title_wanderer', 'title_streak', 'title_foxwit',
  'title_master', 'title_dragonslayer', 'title_godshand', 'title_celestial', 'title_eternity',
  'title_newbie_voyage', 'title_claire_recruit', 'title_premium'
];

function chromePath() {
  const candidates = [
    process.env.GO_ODYSSEY_CHROME,
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
  ].filter(Boolean);
  const found = candidates.find((candidate) => fs.existsSync(candidate));
  if (!found) throw new Error('No supported Chromium executable found');
  return found;
}

(async () => {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    executablePath: chromePath(),
    args: ['--disable-gpu', '--allow-file-access-from-files']
  });
  const page = await browser.newPage({ viewport: { width: 256, height: 256 }, deviceScaleFactor: 1 });
  try {
    for (const id of IDS) {
      const source = path.join(SOURCE_DIR, `${id}.svg`);
      if (!fs.existsSync(source)) throw new Error(`Missing SVG source: ${source}`);
      const svg = fs.readFileSync(source, 'utf8');
      const dataUri = `data:image/svg+xml;base64,${Buffer.from(svg, 'utf8').toString('base64')}`;
      await page.setContent(`<!doctype html><html><body style="margin:0;background:#ffffff;width:256px;height:256px;overflow:hidden"><img id="icon" style="display:block;width:256px;height:256px" src="${dataUri}"></body></html>`, { waitUntil: 'load' });
      await page.locator('#icon').screenshot({ path: path.join(OUTPUT_DIR, `${id}.png`) });
    }
  } finally {
    await browser.close();
  }
  console.log(`Rendered ${IDS.length} existing cosmetic SVG references to ${OUTPUT_DIR}`);
})();
