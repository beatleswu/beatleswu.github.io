"""Lane F: source contracts and isolated Chromium UX checks.

Run with Python (stdlib only): python tests/test_20261019_shop_nav_ui.py
Browser dependencies: Node, playwright-core, Chrome/Edge. Override defaults with
SHOP_PLAYWRIGHT_CORE and CHROME_BIN. Every browser request is intercepted;
only explicit local frontend assets and synthetic API responses are served.
"""

import os
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SHOP = (ROOT / "shop.html").read_text(encoding="utf-8")
BACKPACK = (ROOT / "inventory.html").read_text(encoding="utf-8")

BROWSER_CHECK = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.SHOP_PLAYWRIGHT_CORE ||
  'D:/go-odyssey-acceptance-tools/playwright-v1a/node_modules/playwright-core');
const [root, surface, lang] = process.argv.slice(1);
const chrome = process.env.CHROME_BIN || [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].find(p => fs.existsSync(p));
(async () => {
  const browser = await chromium.launch({ executablePath: chrome, headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const writes = [];
    const errors = [];
    await context.route('**/*', async route => {
      const req = route.request();
      const url = new URL(req.url());
      if (req.method() !== 'GET') {
        writes.push(req.method() + ' ' + url.pathname);
        return route.fulfill({ status: 405, body: '{}' });
      }
      if (url.origin !== 'http://lane-f.test') return route.abort();
      const p = url.pathname;
      if (p.startsWith('/api/')) {
        let data = {};
        if (p === '/api/shop/catalog') data = {
          purchase_enabled: true, coins: 500,
          items: [{ key: 'pet_snack', category: 'pet', name: '寵物糖果包',
                    name_en: 'Pet Candy', desc: '購買即獲得棋魂糖 x3。' }],
          inventory: {}, daily_items: [], weekly_items: [], monthly_items: [],
        };
        if (p === '/api/auth/me') data = { logged_in: true, username: 'synthetic', equipment_loadout_enabled: true };
        if (p === '/api/pet/status') data = { pet: null, inventory: [
          { key: 'spirit_candy', name: '棋魂糖', name_en: 'Spirit Candy', qty: 3 },
        ] };
        if (p === '/api/player/inventory') data = [];
        return route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) });
      }
      // Exact page allowlist plus public frontend assets; never serve server files.
      const file = path.resolve(root, '.' + p);
      const inside = !path.relative(root, file).startsWith('..');
      const publicAsset = /\.(?:js|css|webp|png|svg)$/.test(p);
      if (inside && (publicAsset || ['/shop', '/inventory'].includes(p))) {
        const target = p === '/shop' ? path.join(root, 'shop.html') :
                       p === '/inventory' ? path.join(root, 'inventory.html') : file;
        if (fs.existsSync(target) && fs.statSync(target).isFile()) {
          const type = target.endsWith('.html') ? 'text/html' :
                       target.endsWith('.js') ? 'application/javascript' :
                       target.endsWith('.css') ? 'text/css' : 'image/' + path.extname(target).slice(1);
          return route.fulfill({ contentType: type + '; charset=utf-8', body: fs.readFileSync(target) });
        }
      }
      return route.fulfill({ status: 404, body: '' });
    });
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(`http://lane-f.test/${surface}?lang=${lang}`, { waitUntil: 'load' });
    await page.evaluate(lang => {
      I18n.setLang(lang);
      if (window.onLangChange) window.onLangChange();
    }, lang);
    if (surface === 'shop') {
      await page.waitForFunction(() => typeof shopPurchaseEnabled === 'function');
      // Actual page lock dominates strict true, false, absent and malformed server flags.
      for (const payload of [{ purchase_enabled: true }, { purchase_enabled: false }, {},
                             { purchase_enabled: 'true' }, { purchase_enabled: 1 }]) {
        const state = await page.evaluate(payload => {
          updateShopPurchaseState(payload);
          const banner = document.getElementById('shop-purchase-state');
          const card = itemCard({ key: 'pet_snack', category: 'pet' });
          return { enabled: shopPurchaseEnabled(payload), hidden: banner.hidden,
            text: banner.textContent, source: banner.dataset.purchaseEnabledSource,
            controls: card.querySelectorAll('button').length, card: card.textContent };
        }, payload);
        assert.equal(state.enabled, false);
        assert.equal(state.hidden, false);
        assert.equal(state.source, 'g009-browse-preview-locked');
        assert.equal(state.controls, 0);
        assert.match(state.text, lang === 'en' ? /pet food.*unavailable/ : /無法購買.*寵物食物/);
        assert.match(state.text, lang === 'en' ? /does not confirm a release date/ : /不代表已確定開放日期/);
        assert.doesNotMatch(state.card, /購買即獲得|Purchase adds|Buy adds/);
      }
      assert.match(await page.locator('[data-shop-availability-note]').innerText(), /Pet food cannot be bought here/);
      assert.equal(await page.locator('[data-shop-availability-note] a').getAttribute('href'), '/hero?tab=pet');
    } else {
      await page.waitForSelector('[data-backpack-spirit-link]');
      for (const tab of ['hero', 'pet', 'honors']) {
        const link = page.locator(`a[data-backpack-destination="${tab}"]`);
        assert.equal(await link.getAttribute('href'), `/hero?tab=${tab}`);
        assert.ok(await link.isVisible());
      }
      const link = page.locator('[data-backpack-spirit-link]');
      assert.equal(await link.getAttribute('href'), '/hero?tab=pet');
      assert.match(await link.innerText(), lang === 'en' ? /Visit Spirit/ : /前往棋靈/);
      const card = page.locator('[data-source-item-id="spirit_candy"]');
      assert.equal(await card.locator('[data-use-item]').count(), 0);
      assert.match(await card.innerText(), lang === 'en' ? /Check feeding options/ : /查看餵食條件/);
      const unknown = await page.evaluate(() => backpackCapability({}));
      assert.equal(unknown.kind, 'readonly');
      assert.doesNotMatch(unknown.label, /Passive|被動生效/);
      const gates = await page.evaluate(() => {
        return [undefined, false, 'true', true].map(flag => {
          applyFunctionalEquipmentLoadoutCapability({ equipment_loadout_enabled: flag });
          return functionalEquipmentLoadoutEnabled();
        });
      });
      assert.deepEqual(gates, [false, false, false, true]);
    }
    for (const width of [390, 1280]) {
      await page.setViewportSize({ width, height: 844 });
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
      assert.equal(overflow, false, `${surface}: overflow at ${width}px`);
    }
    assert.deepEqual(writes, [], 'no player mutations');
    assert.deepEqual(errors, [], 'no uncaught page errors');
    console.log(`${surface} ${lang}: PASS`);
  } finally { await browser.close(); }
})().catch(e => { console.error(e.stack); process.exitCode = 1; });
"""


class ShopNavigationUI(unittest.TestCase):
    def test_destinations_exist_in_canonical_hero(self):
        hero = (ROOT / "hero.html").read_text(encoding="utf-8")
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("@app.route('/hero')", app)
        for tab in ("hero", "pet", "honors"):
            self.assertIn(f'id="tab-{tab}"', hero)
            self.assertIn(f'href="/hero?tab={tab}"', BACKPACK)

    def test_shop_copy_separates_flags_and_actual_availability(self):
        self.assertIn("even if the server purchase flag is enabled", SHOP)
        self.assertIn("Pet food cannot be bought here", SHOP)
        self.assertIn("does not confirm a release date", SHOP)
        self.assertIn("const G009_SHOP_BROWSE_PREVIEW_ONLY = true;", SHOP)

    def test_backpack_does_not_promise_hidden_actions(self):
        self.assertIn("Ownership does not guarantee use or equip availability", BACKPACK)
        self.assertNotIn("被動生效／唯讀", BACKPACK)
        self.assertNotIn("/api/shop/buy", BACKPACK)

    def browser(self, surface, language):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for runtime verification")
        result = subprocess.run(
            [node, "-e", BROWSER_CHECK, str(ROOT), surface, language],
            cwd=ROOT, env=os.environ.copy(), capture_output=True, text=True,
            encoding="utf-8", timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_runtime_shop_english(self):
        self.browser("shop", "en")

    def test_runtime_shop_chinese(self):
        self.browser("shop", "zh")

    def test_runtime_backpack_english(self):
        self.browser("inventory", "en")

    def test_runtime_backpack_chinese(self):
        self.browser("inventory", "zh")


if __name__ == "__main__":
    unittest.main(verbosity=2)
