import fs from 'node:fs/promises';
import fssync from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..');

function findChrome() {
  const candidates = [
    process.env.CHROME_BIN,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  ].filter(Boolean);
  const executable = candidates.find((candidate) => fssync.existsSync(candidate));
  if (!executable) throw new Error('No Chrome/Edge executable found.');
  return executable;
}

function contentTypeFor(filePath) {
  return ({
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.webp': 'image/webp',
    '.svg': 'image/svg+xml',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
  })[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
}

async function startServer() {
  const routeFiles = new Map([
    ['/', 'index.html'],
    ['/hero', 'hero.html'],
    ['/hero.html', 'hero.html'],
    ['/inventory', 'inventory.html'],
    ['/shop', 'shop.html'],
    ['/shop.html', 'shop.html'],
  ]);
  const server = http.createServer(async (request, response) => {
    try {
      const url = new URL(request.url, 'http://127.0.0.1');
      if (url.pathname === '/inventory.html') {
        response.writeHead(404);
        response.end('noncanonical inventory source filename');
        return;
      }
      if (url.pathname === '/socket.io/socket.io.js') {
        response.writeHead(200, { 'Content-Type': 'application/javascript; charset=utf-8' });
        response.end('window.io=function(){return {on:function(){},emit:function(){},disconnect:function(){}}};');
        return;
      }
      const relative = routeFiles.get(url.pathname) || decodeURIComponent(url.pathname).replace(/^\/+/, '');
      const absolute = path.resolve(repoRoot, relative);
      if (absolute !== repoRoot && !absolute.startsWith(`${repoRoot}${path.sep}`)) {
        response.writeHead(403);
        response.end('forbidden');
        return;
      }
      const stat = await fs.stat(absolute).catch(() => null);
      if (!stat?.isFile()) {
        response.writeHead(404);
        response.end('not found');
        return;
      }
      response.writeHead(200, { 'Content-Type': contentTypeFor(absolute) });
      fssync.createReadStream(absolute).pipe(response);
    } catch (error) {
      response.writeHead(500);
      response.end(String(error));
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return { server, origin: `http://127.0.0.1:${server.address().port}` };
}

const catalogItems = [
  { key:'extra_questions_small', name:'小型修行令', name_en:'Small Training Pass', icon:'📜', price:60, desc:'今日題數 +5', desc_en:'+5 questions today', usable:'activate', category:'training' },
  { key:'ai_explain_ticket', name:'AI 解說券', name_en:'AI Analysis Ticket', icon:'🔍', price:50, desc:'答題後自動使用', desc_en:'Auto-used after solving', usable:'auto', category:'training' },
  { key:'hint_ticket', name:'小提示卷', name_en:'Hint Ticket', icon:'💡', price:30, desc:'答題時條件使用', desc_en:'Used while solving', usable:'in_question', category:'training' },
  { key:'xp_potion', name:'XP 藥水', name_en:'XP Potion', icon:'🧪', price:120, desc:'成長加成', desc_en:'Growth boost', usable:'activate', category:'growth' },
  { key:'streak_shield', name:'連勝護盾', name_en:'Streak Shield', icon:'🛡️', price:80, desc:'保護連勝', desc_en:'Protects a streak', usable:'activate', category:'guard' },
  { key:'rare_appearance_fragment', name:'稀有外觀碎片', name_en:'Rare Appearance Fragment', icon:'✨', price:980, desc:'收藏兌換物', desc_en:'Collection exchange item', usable:'activate', category:'collection' },
  { key:'pet_evolution_core', name:'棋靈進化素材', name_en:'Spirit Evolution Core', icon:'🌱', price:1180, desc:'棋靈成長素材', desc_en:'Spirit growth material', usable:'activate', category:'pet' },
  { key:'spirit_feast_bundle', name:'棋靈盛宴組', name_en:'Spirit Feast Bundle', icon:'🍱', price:360, desc:'棋魂糖與星果組合', desc_en:'A Go Spirit Candy and Starfruit bundle', usable:'instant', category:'pet', grants_food:{ go_spirit_candy:3, starfruit:2 } },
];

function createState(mode = 'normal') {
  return {
    mode,
    inventory: mode === 'empty' ? {} : {
      extra_questions_small: 2,
      ai_explain_ticket: 3,
      hint_ticket: 1,
      xp_potion: 2,
      streak_shield: 1,
      rare_appearance_fragment: 1,
      pet_evolution_core: 1,
    },
    petInventory: mode === 'empty' ? {} : { go_spirit_candy:2, starfruit:1 },
    actionTrace: [],
  };
}

function catalogPayload(state) {
  return {
    coins: 12345,
    earned_today: 50,
    daily_cap: 500,
    items: catalogItems,
    inventory: state.inventory,
    daily_items: catalogItems.slice(0, 4),
    weekly_items: catalogItems.slice(4, 6),
    monthly_items: catalogItems.slice(6),
    daily_slots: [{ ...catalogItems[0], type:'item', item_key:catalogItems[0].key, orig_price:75 }],
    daily_slots_visible: 3,
    gacha: { cost:150, pity:30, pity_count:4, rates:{ item:0.6, pet_food:0.25, common:0.12, uncommon:0.03 } },
    gacha_collection: { owned:2, total:8 },
  };
}

function heroProfile() {
  return {
    user_id: 42,
    username: 'ia_fixture',
    display_name: '資訊架構棋士',
    nickname: 'IA',
    rank_level: 'LV12',
    go_rank: '3k',
    xp: 640,
    xp_next: 1000,
    total_xp: 8640,
    elo_rating: 1450,
    elo_provisional: false,
    is_premium: true,
    auto_title: '棋典學者',
    auto_title_en: 'Go Scholar',
    equipped_title: '學棋人',
    equipped_title_en: 'Go Student',
    character_key: 'apprentice',
    stone_skin: 'jade',
    board_skin: 'classic',
    equipped_labels: ['素布道袍', '學棋人'],
    wardrobe: [
      { id:'robe_plain', source_item_id:'wardrobe:robe_plain', type:'outfit', name:'素布道袍', name_en:'Plain Robe', icon:'🥋', rarity:'common', owned:true, equipped:true, effects:{} },
      { id:'hat_scholar', source_item_id:'wardrobe:hat_scholar', type:'hat', name:'仙鶴冠', name_en:'Crane Crown', icon:'👑', rarity:'uncommon', owned:true, equipped:false, effects:{} },
      { id:'back_scroll', source_item_id:'wardrobe:back_scroll', type:'back', name:'棋譜背飾', name_en:'Kifu Backpiece', icon:'📜', rarity:'rare', owned:true, equipped:false, effects:{} },
      { id:'acc_jade_ring', source_item_id:'wardrobe:acc_jade_ring', type:'accessory', name:'玉佩外觀', name_en:'Jade Charm', icon:'💠', rarity:'common', owned:true, equipped:false, effects:{} },
      { id:'aura_moon', source_item_id:'wardrobe:aura_moon', type:'aura', name:'霧光光環', name_en:'Mist Aura', icon:'🌫️', rarity:'rare', owned:true, equipped:false, hint:'完成區域挑戰', effects:{ xp_bonus:0.12, label:'XP +12%' } },
      { id:'pet_cat', source_item_id:'wardrobe:pet_cat', type:'pet', name:'墨滴棋靈外觀', name_en:'Ink Spirit Look', icon:'🐾', rarity:'common', owned:true, equipped:true, effects:{} },
      { id:'title_beginner', source_item_id:'wardrobe:title_beginner', type:'title', name:'學棋人', name_en:'Go Student', icon:'🏅', rarity:'common', owned:true, equipped:true, effects:{} },
      { id:'title_streak', source_item_id:'wardrobe:title_streak', type:'title', name:'不敗傳說', name_en:'Unbeaten Legend', icon:'🏆', rarity:'legendary', owned:false, equipped:false, hint:'完成連勝條件', effects:{} },
    ],
    milestones: { total_correct:320, streak:18, rank_level:'LV12' },
  };
}

function petStatus(state) {
  const active = {
    key:'ink_drop_kelpie', pet_key:'ink_drop_kelpie', name:'墨滴水靈馬', name_en:'Inkdrop Spirit Horse', role:'均衡', role_en:'Balanced',
    ability:'穩定陪練', ability_en:'Steady practice', nickname:'墨滴', accent:'#0d9488', image:'/assets/pets/pet_ink_drop_kelpie_lv1.webp',
    level:12, xp:40, xp_required:100, xp_pct:40, fullness:82, affection:76,
    next_evolution_level:25, next_evolution_label:'覺醒', levels_to_next_evolution:13,
  };
  return {
    catalog:[active],
    pet:active,
    inventory:[
      { key:'go_spirit_candy', name:'棋魂糖', name_en:'Go Spirit Candy', qty:Number(state.petInventory.go_spirit_candy || 0), fullness:24, xp:8, affection:4 },
      { key:'starfruit', name:'星果', name_en:'Starfruit', qty:Number(state.petInventory.starfruit || 0), fullness:38, xp:15, affection:7 },
      { key:'moon_drop', name:'月露', name_en:'Moon Drop', qty:Number(state.petInventory.moon_drop || 0), fullness:18, xp:25, affection:10 },
    ],
    interaction:{ pet_cooldown:0, train_cooldown:0, pet_full:false, train_full:false },
    training:{ active:false, ready:false, remaining:0, hours:0 },
    expedition:{ active:false, ready:false, remaining:0, hours:0 },
    bonus:{ current_pct:8, matched_pct:10, base_pct:6, affection_mult:1.2, always_matched:false, hungry:false, match_condition:'修行', match_condition_en:'Practice' },
    collection:{ collection:[{ ...active, active:true }], locked:[{ key:'whispering_void_kit', name:'虛空貓', name_en:'Void Cat', image:'/assets/pets/pet_whispering_void_kit_lv1.webp', unlock_level:16, claimable:false }] },
    reward_sources:[],
  };
}

function jsonResponse(body, status = 200) {
  return { status, contentType:'application/json', body:JSON.stringify(body) };
}

async function installFixture(page, state, diagnostics) {
  page.on('console', (message) => {
    const text = message.text();
    if (message.type() === 'error' && !(state.mode === 'error' && text.includes('503'))) diagnostics.console.push(text);
  });
  page.on('pageerror', (error) => diagnostics.console.push(error?.stack || String(error)));
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (response.status() >= 400 && url.hostname === '127.0.0.1') {
      const expectedCatalogError = state.mode === 'error' && url.pathname === '/api/shop/catalog';
      if (!expectedCatalogError && url.pathname !== '/favicon.ico') {
        diagnostics.network.push({ status:response.status(), method:response.request().method(), path:url.pathname });
      }
    }
  });
  await page.route('https://fonts.googleapis.com/**', (route) => route.fulfill({ status:200, contentType:'text/css', body:'' }));
  await page.route('https://fonts.gstatic.com/**', (route) => route.fulfill({ status:200, contentType:'font/woff2', body:'' }));
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const pathname = url.pathname;
    let body = { ok:true };
    let status = 200;
    if (pathname === '/api/shop/catalog') {
      if (state.mode === 'loading') await new Promise((resolve) => setTimeout(resolve, 650));
      if (state.mode === 'error') {
        body = { error:'fixture_catalog_unavailable' };
        status = 503;
      } else body = catalogPayload(state);
    } else if (pathname === '/api/shop/buy') {
      const input = request.postDataJSON();
      const key = input.item_key;
      if (key === 'spirit_feast_bundle') {
        state.petInventory.go_spirit_candy = Number(state.petInventory.go_spirit_candy || 0) + 3;
        state.petInventory.starfruit = Number(state.petInventory.starfruit || 0) + 2;
        state.actionTrace.push({ action:'purchase', itemKey:key, count:1 });
        body = { ok:true, coins:11985, item_key:key, qty:1, granted_items:[], granted_food:[
          { item_key:'go_spirit_candy', qty:3 }, { item_key:'starfruit', qty:2 },
        ] };
      } else {
        state.inventory[key] = Number(state.inventory[key] || 0) + 1;
        state.actionTrace.push({ action:'purchase', itemKey:key, count:state.inventory[key] });
        body = { ok:true, coins:12285, item_key:key, qty:1, granted_items:[{ item_key:key, qty:1 }], granted_food:[] };
      }
    } else if (pathname === '/api/shop/use') {
      const input = request.postDataJSON();
      const key = input.item_key;
      state.actionTrace.push({ action:'use', itemKey:key });
      body = { ok:true, effect:'extra_questions', value:5 };
    } else if (pathname === '/api/auth/me') {
      body = { logged_in:true, user_id:42, username:'ia_fixture', display_name:'資訊架構棋士', nickname:'IA', is_premium:true, tour_done:true };
    } else if (pathname === '/api/skills/profile') {
      body = heroProfile();
    } else if (pathname === '/api/player/appearance') {
      const profile = heroProfile();
      body = { wardrobe:profile.wardrobe, equipped:{ outfit_id:'robe_plain', pet_id:'pet_cat', title_id:'title_beginner' } };
    } else if (pathname === '/api/pet/status') {
      body = petStatus(state);
    } else if (pathname === '/api/class/profile') {
      body = { title:'棋士', discipline_counts:{}, skill_tree:{} };
    } else if (pathname === '/api/badges/definitions') {
      body = [
        { id:'scholar', name:'棋典學者', name_en:'Go Scholar', description:'完成研習', description_en:'Complete study', rarity:'gold' },
        { id:'legend', name:'不敗傳說', name_en:'Unbeaten Legend', description:'達成連勝', description_en:'Win streak', rarity:'legendary' },
      ];
    } else if (pathname === '/api/badges/earned') {
      body = [{ badge_id:'scholar' }];
    } else if (pathname === '/api/user/coins') {
      body = { coins:12345 };
    } else if (pathname === '/api/dm/unread_count') {
      body = { count:0 };
    } else if (pathname === '/api/auth/newbie_quest') {
      body = { active:false };
    } else if (pathname === '/api/newbie_quest/checkpoint' || pathname === '/api/analytics/events') {
      body = null;
      status = 204;
    }
    diagnostics.actions.push({ method:request.method(), path:pathname, status });
    if (status === 204) await route.fulfill({ status, body:'' });
    else await route.fulfill(jsonResponse(body, status));
  });
}

async function pageSnapshot(page) {
  return page.evaluate(() => {
    const duplicateIds = [...document.querySelectorAll('[id]')].map((node) => node.id)
      .filter((id, index, ids) => ids.indexOf(id) !== index);
    return {
      path:location.pathname,
      search:location.search,
      bodyWidth:document.body.scrollWidth,
      documentWidth:document.documentElement.scrollWidth,
      viewportWidth:window.innerWidth,
      horizontalOverflow:Math.max(document.body.scrollWidth, document.documentElement.scrollWidth) > window.innerWidth + 1,
      duplicateIds:[...new Set(duplicateIds)],
      activeNav:[...document.querySelectorAll('.cg-nav-link.active')].map((node) => node.dataset.navKey),
    };
  });
}

async function openPage(browser, origin, route, viewport, stateMode = 'normal') {
  const page = await browser.newPage({ viewport });
  const state = createState(stateMode);
  const diagnostics = { console:[], network:[], actions:[] };
  await installFixture(page, state, diagnostics);
  await page.addInitScript(() => {
    localStorage.setItem('prem_welcomed', '1');
    window.io = () => ({ connected:true, __cgNavPresenceBound:false, on() {}, emit() {}, disconnect() {} });
  });
  await page.goto(`${origin}${route}`, { waitUntil:'domcontentloaded' });
  return { page, state, diagnostics };
}

async function screenshot(page, outputDir, name) {
  const target = path.join(outputDir, name);
  await page.screenshot({ path:target, fullPage:true });
  return target;
}

async function runHeroContract(browser, origin, outputDir) {
  const { page, diagnostics } = await openPage(browser, origin, '/hero?tab=hero', { width:1440, height:900 });
  await page.locator('#hero-overview-name').waitFor({ state:'visible' });
  await page.waitForFunction(() => document.querySelector('#hero-overview-name')?.textContent?.includes('資訊架構棋士'));
  const defaultState = {
    ...(await pageSnapshot(page)),
    ...(await page.evaluate(() => ({
    activeTab:document.body.dataset.heroTab,
    tabCount:document.querySelectorAll('.main-tab[role="tab"]').length,
    selectedTabs:document.querySelectorAll('.main-tab[aria-selected="true"]').length,
    visiblePanels:[...document.querySelectorAll('[role="tabpanel"]')].filter((node) => !node.hidden).map((node) => node.dataset.heroDomain),
    overviewValues:[...document.querySelectorAll('.hero-overview-value')].map((node) => node.textContent.trim()),
    quickLinks:[...document.querySelectorAll('.hero-quick-link')].map((node) => node.getAttribute('href') || node.dataset.heroTargetTab),
    }))),
  };
  const screenshots = [await screenshot(page, outputDir, 'hero-desktop-1440-character.png')];
  await page.locator('#hero-tab-hero').focus();
  await page.keyboard.press('ArrowRight');
  await page.waitForFunction(() => document.body.dataset.heroTab === 'equipment');
  const keyboardArrow = await page.evaluate(() => ({
    activeTab:document.body.dataset.heroTab,
    focused:document.activeElement?.id,
    selected:document.querySelector('.main-tab[aria-selected="true"]')?.id,
  }));
  await page.keyboard.press('End');
  await page.waitForFunction(() => document.body.dataset.heroTab === 'honors');
  const keyboardEnd = await page.evaluate(() => ({
    activeTab:document.body.dataset.heroTab,
    focused:document.activeElement?.id,
    selected:document.querySelector('.main-tab[aria-selected="true"]')?.id,
  }));
  await page.keyboard.press('Home');
  await page.waitForFunction(() => document.body.dataset.heroTab === 'hero');
  const keyboardHome = await page.evaluate(() => ({ activeTab:document.body.dataset.heroTab, focused:document.activeElement?.id }));
  const domains = {};
  for (const tab of ['equipment','appearance','pet','honors']) {
    await page.locator(`#hero-tab-${tab}`).click();
    await page.waitForFunction((expected) => document.body.dataset.heroTab === expected, tab);
    if (tab === 'pet') await page.locator('#pet-companion-root .pet-main-card').waitFor({ state:'visible' });
    if (tab === 'honors') await page.locator('#hero-badge-grid > *').first().waitFor({ state:'visible' });
    domains[tab] = await page.evaluate((expected) => {
      const panel = document.querySelector(`#tab-${expected}`);
      return {
        activeTab:document.body.dataset.heroTab,
        url:location.pathname + location.search,
        visiblePanels:[...document.querySelectorAll('[role="tabpanel"]')].filter((node) => !node.hidden).map((node) => node.dataset.heroDomain),
        sourceIds:[...panel.querySelectorAll('[data-source-item-id]')].map((node) => node.dataset.sourceItemId),
        domains:[...new Set([...panel.querySelectorAll('[data-item-domain]')].map((node) => node.dataset.itemDomain))],
        projections:[...panel.querySelectorAll('[data-source-item-id]')].map((node) => ({
          sourceId:node.dataset.sourceItemId,
          domain:node.dataset.itemDomain,
          projection:node.dataset.itemProjection,
        })),
        disabledCount:panel.querySelectorAll(':disabled').length,
        duplicateSourceIds:[...panel.querySelectorAll('[data-source-item-id]')].map((node) => node.dataset.sourceItemId)
          .filter((id, index, ids) => ids.indexOf(id) !== index),
      };
    }, tab);
    screenshots.push(await screenshot(page, outputDir, `hero-desktop-1440-${tab}.png`));
  }
  await page.goBack();
  await page.waitForFunction(() => document.body.dataset.heroTab === 'pet');
  const backTab = await page.evaluate(() => document.body.dataset.heroTab);
  await page.reload({ waitUntil:'domcontentloaded' });
  await page.waitForFunction(() => document.body.dataset.heroTab === 'pet');
  const refreshTab = await page.evaluate(() => document.body.dataset.heroTab);
  const finalState = await pageSnapshot(page);
  const allDomainSources = Object.values(domains).flatMap(entry => entry.projections || []);
  const crossDomainDuplicates = allDomainSources.map(entry => entry.sourceId)
    .filter((id, index, ids) => ids.indexOf(id) !== index);
  const failures = [];
  if (defaultState.activeTab !== 'hero' || defaultState.tabCount !== 5 || defaultState.selectedTabs !== 1) failures.push('Hero default tab contract failed');
  if (defaultState.visiblePanels.join(',') !== 'character') failures.push('Hero default visible panel is not Character');
  if (defaultState.overviewValues.some((value) => !value || value === '—')) failures.push('Hero overview contains empty summary values');
  if (!defaultState.quickLinks.includes('/inventory')) failures.push('Hero overview does not link to Backpack');
  if (keyboardArrow.activeTab !== 'equipment' || keyboardArrow.focused !== 'hero-tab-equipment'
    || keyboardArrow.selected !== 'hero-tab-equipment' || keyboardEnd.activeTab !== 'honors'
    || keyboardEnd.focused !== 'hero-tab-honors' || keyboardEnd.selected !== 'hero-tab-honors'
    || keyboardHome.activeTab !== 'hero'
    || keyboardHome.focused !== 'hero-tab-hero') failures.push('Hero roving-tab keyboard contract failed');
  if (domains.equipment.domains.some((domain) => domain !== 'equipment')) failures.push(`Equipment leaked domains: ${domains.equipment.domains.join(',')}`);
  if (!domains.appearance.domains.includes('appearance')) failures.push('Appearance projection missing');
  if (!domains.equipment.sourceIds.includes('wardrobe:aura_moon') || domains.appearance.sourceIds.includes('wardrobe:aura_moon')) failures.push('Effect-bearing wardrobe item was not exclusively projected into Equipment');
  if (!domains.appearance.sourceIds.includes('wardrobe:acc_jade_ring')) failures.push('Real accessory type was not projected into Appearance');
  if (!domains.pet.domains.includes('spirit')) failures.push('Spirit appearance projection missing');
  if (!domains.honors.domains.includes('honors')) failures.push('Honors projection missing');
  if (Object.values(domains).some((entry) => entry.visiblePanels.length !== 1)) failures.push('Multiple Hero domain panels are visible');
  if (Object.values(domains).some((entry) => entry.duplicateSourceIds.length)) failures.push('Duplicate source identity within a Hero domain');
  if (crossDomainDuplicates.length) failures.push(`Duplicate source identity across Hero domains: ${[...new Set(crossDomainDuplicates)].join(',')}`);
  if (backTab !== 'pet' || refreshTab !== 'pet') failures.push('Hero back/refresh tab state failed');
  if (defaultState.horizontalOverflow || finalState.horizontalOverflow) failures.push('Hero has horizontal overflow');
  if (defaultState.duplicateIds.length) failures.push(`Hero duplicate IDs: ${defaultState.duplicateIds.join(',')}`);
  if (diagnostics.console.length || diagnostics.network.length) failures.push('Hero console/network errors detected');
  await page.close();
  return { defaultState, keyboardArrow, keyboardEnd, keyboardHome, domains, crossDomainDuplicates, backTab, refreshTab, diagnostics, screenshots, failures };
}

async function runBackpackContract(browser, origin, outputDir) {
  const { page, state, diagnostics } = await openPage(browser, origin, '/inventory', { width:820, height:1180 });
  await page.waitForFunction(() => document.querySelector('#backpack-status')?.dataset.state === 'ready');
  const initial = {
    ...(await pageSnapshot(page)),
    ...(await page.evaluate(() => ({
    status:document.querySelector('#backpack-status')?.dataset.state,
    cardCount:document.querySelectorAll('.backpack-card').length,
    sourceIds:[...document.querySelectorAll('.backpack-card')].map((node) => node.dataset.sourceItemId),
    capabilities:[...document.querySelectorAll('.backpack-card')].map((node) => ({ id:node.dataset.sourceItemId, capability:node.dataset.itemCapability, buttonCount:node.querySelectorAll('[data-use-item]').length })),
    filterCount:document.querySelectorAll('.backpack-filter').length,
    shopPriceCount:document.querySelectorAll('.price').length,
    shopPurchaseCount:document.querySelectorAll('[data-sfx="purchase"]').length,
    }))),
  };
  const screenshots = [await screenshot(page, outputDir, 'backpack-ipad-820x1180-default.png')];
  await page.locator('.backpack-filter[data-category="growth"]').click();
  await page.waitForFunction(() => new URLSearchParams(location.search).get('category') === 'growth');
  const growth = await page.evaluate(() => ({
    cards:[...document.querySelectorAll('.backpack-card')].map((node) => node.dataset.sourceItemId),
    selected:document.querySelector('.backpack-filter[aria-selected="true"]')?.dataset.category,
  }));
  await page.goBack();
  await page.waitForFunction(() => !new URLSearchParams(location.search).has('category'));
  const restored = await page.evaluate(() => document.querySelector('.backpack-filter[aria-selected="true"]')?.dataset.category);
  await page.locator('[data-use-item="extra_questions_small"]').click();
  await page.waitForFunction(() => document.querySelector('#backpack-toast')?.classList.contains('show'));
  const useActions = state.actionTrace.filter((entry) => entry.action === 'use');
  const failures = [];
  if (initial.status !== 'ready' || initial.cardCount !== 9 || new Set(initial.sourceIds).size !== initial.cardCount) failures.push('Backpack real inventory identity failed');
  if (!initial.activeNav.includes('backpack') || initial.activeNav.includes('shop')) failures.push('Backpack active navigation is not exclusive');
  if (initial.shopPriceCount || initial.shopPurchaseCount) failures.push('Backpack leaked Shop price/purchase controls');
  if (initial.capabilities.some((item) => item.capability === 'manual' ? item.buttonCount !== 1 : item.buttonCount !== 0)) failures.push('Backpack capability action semantics failed');
  if (!initial.capabilities.some(item => item.id === 'go_spirit_candy' && item.capability === 'managed' && item.buttonCount === 0)) failures.push('Spirit supply ownership/action semantics missing from Backpack');
  if (growth.cards.join(',') !== 'xp_potion' || growth.selected !== 'growth' || restored !== 'all') failures.push('Backpack category/back state failed');
  if (useActions.length !== 1 || useActions[0].itemKey !== 'extra_questions_small') failures.push('Backpack legal use action was not one-shot');
  if (initial.horizontalOverflow || initial.duplicateIds.length) failures.push('Backpack overflow or duplicate DOM IDs detected');
  if (diagnostics.console.length || diagnostics.network.length) failures.push('Backpack console/network errors detected');
  await page.close();
  return { initial, growth, restored, useActions, diagnostics, screenshots, failures };
}

async function runE10BackpackOwnershipContract(browser, origin, outputDir) {
  const { page, diagnostics } = await openPage(browser, origin, '/inventory?e10=1', { width:820, height:1180 });
  await page.waitForFunction(() => document.querySelector('#backpack-status')?.dataset.state === 'ready');
  const initial = await page.evaluate(() => ({
    ownerBody:document.body.getAttribute('data-adventure-shell-owner'),
    ownerDocument:document.documentElement.getAttribute('data-adventure-shell-owner'),
    e10Frame:document.documentElement.getAttribute('data-e10-backpack-shell'),
    e10HeaderVisible:document.querySelectorAll('[data-e10-backpack-only]:not([hidden])').length,
    legacyHeaderVisible:document.querySelectorAll('[data-legacy-backpack-header]:not([hidden])').length,
    globalNav:document.querySelectorAll('.cg-nav-links').length,
    shellCount:document.querySelectorAll('#inventory-page-header').length,
  }));
  await page.reload({ waitUntil:'domcontentloaded' });
  await page.waitForFunction(() => document.querySelector('#backpack-status')?.dataset.state === 'ready');
  const reloaded = await page.evaluate(() => ({
    ownerBody:document.body.getAttribute('data-adventure-shell-owner'),
    ownerDocument:document.documentElement.getAttribute('data-adventure-shell-owner'),
    e10Frame:document.documentElement.getAttribute('data-e10-backpack-shell'),
    e10HeaderVisible:document.querySelectorAll('[data-e10-backpack-only]:not([hidden])').length,
    legacyHeaderVisible:document.querySelectorAll('[data-legacy-backpack-header]:not([hidden])').length,
    globalNav:document.querySelectorAll('.cg-nav-links').length,
    shellCount:document.querySelectorAll('#inventory-page-header').length,
  }));
  await page.goto(`${origin}/inventory`, { waitUntil:'domcontentloaded' });
  await page.waitForFunction(() => document.querySelector('#backpack-status')?.dataset.state === 'ready');
  const generic = await page.evaluate(() => ({
    ownerBody:document.body.getAttribute('data-adventure-shell-owner'),
    ownerDocument:document.documentElement.getAttribute('data-adventure-shell-owner'),
    e10Frame:document.documentElement.getAttribute('data-e10-backpack-shell'),
    e10HeaderVisible:document.querySelectorAll('[data-e10-backpack-only]:not([hidden])').length,
    globalNav:document.querySelectorAll('.cg-nav-links').length,
  }));
  const failures = [];
  for (const [label, state] of [['initial', initial], ['reloaded', reloaded]]) {
    if (state.ownerBody !== 'e10-backpack' || state.ownerDocument !== 'e10-backpack') failures.push(`${label}: E10 Backpack owner was not restored`);
    if (state.e10Frame !== 'true' || state.e10HeaderVisible !== 1 || state.legacyHeaderVisible !== 0) failures.push(`${label}: E10 Backpack presentation boundary failed`);
    if (state.globalNav !== 0 || state.shellCount !== 1) failures.push(`${label}: E10 Backpack shell/nav exclusivity failed`);
  }
  if (generic.ownerBody || generic.ownerDocument || generic.e10Frame || generic.e10HeaderVisible !== 0 || generic.globalNav !== 1) {
    failures.push(`generic: E10 Backpack ownership leaked into generic inventory ${JSON.stringify(generic)}`);
  }
  const screenshots = [await screenshot(page, outputDir, 'backpack-generic-after-e10-context.png')];
  if (diagnostics.console.length || diagnostics.network.length) failures.push('E10 Backpack ownership console/network errors detected');
  await page.close();
  return { initial, reloaded, generic, diagnostics, screenshots, failures };
}

async function runBackpackStateCase(browser, origin, outputDir, mode) {
  const { page, diagnostics } = await openPage(browser, origin, '/inventory', { width:430, height:932 }, mode);
  let snapshot;
  if (mode === 'loading') {
    snapshot = await page.evaluate(() => ({ state:document.querySelector('#backpack-status')?.dataset.state, text:document.querySelector('#backpack-status')?.textContent }));
    await page.waitForFunction(() => document.querySelector('#backpack-status')?.dataset.state === 'ready');
  } else if (mode === 'error') {
    await page.waitForFunction(() => document.querySelector('#backpack-status')?.dataset.state === 'error');
    snapshot = await page.evaluate(() => ({ state:document.querySelector('#backpack-status')?.dataset.state, text:document.querySelector('#backpack-status')?.textContent, cards:document.querySelectorAll('.backpack-card').length }));
  } else {
    await page.waitForFunction(() => document.querySelector('#backpack-status')?.dataset.state === 'ready');
    snapshot = await page.evaluate(() => ({ state:document.querySelector('#backpack-status')?.dataset.state, empty:!!document.querySelector('.backpack-empty'), cards:document.querySelectorAll('.backpack-card').length }));
  }
  const shot = await screenshot(page, outputDir, `backpack-mobile-430-${mode}.png`);
  const failures = [];
  if (mode === 'loading' && snapshot.state !== 'loading') failures.push('Backpack loading state was not observable');
  if (mode === 'empty' && (snapshot.state !== 'ready' || !snapshot.empty || snapshot.cards !== 0)) failures.push('Backpack empty state failed');
  if (mode === 'error' && (snapshot.state !== 'error' || snapshot.cards !== 0)) failures.push('Backpack error-safe state failed');
  if (diagnostics.console.length || diagnostics.network.length) failures.push(`Backpack ${mode} console/network errors detected`);
  await page.close();
  return { mode, snapshot, diagnostics, screenshot:shot, failures };
}

async function runShopSeparationContract(browser, origin, outputDir) {
  const { page, state, diagnostics } = await openPage(browser, origin, '/shop', { width:1180, height:820 });
  await page.locator('#items-grid .item-card').first().waitFor({ state:'visible' });
  const before = {
    ...(await pageSnapshot(page)),
    ...(await page.evaluate(() => ({
    productCards:document.querySelectorAll('.item-card').length,
    backpackGrid:document.querySelectorAll('[data-authoritative-backpack-grid]').length,
    legacyMineGrid:document.querySelectorAll('#mine-grid').length,
    confirmationHidden:document.querySelector('#purchase-confirmation').hidden,
    }))),
  };
  const screenshots = [await screenshot(page, outputDir, 'shop-ipad-1180x820-no-backpack-grid.png')];
  await page.locator('.item-card[data-item-key="spirit_feast_bundle"] button').click();
  await page.locator('#purchase-confirmation').waitFor({ state:'visible' });
  const confirmation = await page.evaluate(() => ({
    title:document.querySelector('#purchase-confirmation-title')?.textContent,
    copy:document.querySelector('#purchase-confirmation-copy')?.textContent,
    href:document.querySelector('#purchase-confirmation-backpack')?.getAttribute('href'),
  }));
  screenshots.push(await screenshot(page, outputDir, 'shop-purchase-confirmation.png'));
  await page.locator('#purchase-confirmation-backpack').click();
  await page.waitForURL(/\/inventory$/);
  await page.waitForFunction(() => document.querySelector('#backpack-status')?.dataset.state === 'ready');
  const destination = {
    ...(await pageSnapshot(page)),
    ...(await page.evaluate(() => ({
    sourceIds:[...document.querySelectorAll('.backpack-card')].map(node => node.dataset.sourceItemId),
    backpackGrid:document.querySelectorAll('[data-authoritative-backpack-grid]').length,
    priceCount:document.querySelectorAll('.price').length,
    }))),
  };
  screenshots.push(await screenshot(page, outputDir, 'shop-to-backpack-destination.png'));
  await page.goBack();
  await page.waitForURL(/\/shop$/);
  await page.locator('#items-grid .item-card').first().waitFor({ state:'visible' });
  const afterBack = await pageSnapshot(page);
  const purchases = state.actionTrace.filter((entry) => entry.action === 'purchase');
  const failures = [];
  if (!before.activeNav.includes('shop') || before.activeNav.includes('backpack')) failures.push('Shop active navigation is not exclusive');
  if (!before.productCards || before.backpackGrid || before.legacyMineGrid || !before.confirmationHidden) failures.push('Shop still embeds Backpack or lacks products');
  if (purchases.length !== 1 || purchases[0].itemKey !== 'spirit_feast_bundle') failures.push('Shop bundle purchase action was not one-shot');
  if (!confirmation.copy.includes('目前持有') || !confirmation.copy.includes('棋魂糖: 5')
    || !confirmation.copy.includes('星果: 3') || confirmation.href !== '/inventory') failures.push('Shop multi-grant compact purchase confirmation contract failed');
  if (destination.path !== '/inventory' || !destination.activeNav.includes('backpack') || destination.activeNav.includes('shop')) failures.push('Shop to Backpack navigation failed');
  if (!destination.sourceIds.includes('go_spirit_candy') || !destination.sourceIds.includes('starfruit')
    || destination.backpackGrid !== 1 || destination.priceCount !== 0) failures.push('Backpack destination identity/role failed after purchase');
  if (!afterBack.activeNav.includes('shop') || afterBack.activeNav.includes('backpack')) failures.push('Browser back did not restore Shop state');
  if (before.horizontalOverflow || destination.horizontalOverflow || before.duplicateIds.length || destination.duplicateIds.length) failures.push('Shop/Backpack overflow or duplicate DOM IDs detected');
  if (diagnostics.console.length || diagnostics.network.length) failures.push('Shop journey console/network errors detected');
  await page.close();
  return { before, confirmation, destination, afterBack, purchases, diagnostics, screenshots, failures };
}

async function runResponsiveMatrix(browser, origin, outputDir) {
  const specs = [
    ['hero-1920x1080', '/hero?tab=hero', 1920,1080, '#tab-hero'],
    ['hero-1180x820', '/hero?tab=equipment', 1180,820, '#tab-equipment'],
    ['hero-1024x768', '/hero?tab=honors', 1024,768, '#tab-honors'],
    ['hero-820x1180', '/hero?tab=appearance', 820,1180, '#tab-appearance'],
    ['hero-430x932', '/hero?tab=equipment', 430,932, '#tab-equipment'],
    ['backpack-1024x768', '/inventory', 1024,768, '#backpack-grid'],
    ['backpack-820x1180', '/inventory', 820,1180, '#backpack-grid'],
    ['backpack-768x1024', '/inventory', 768,1024, '#backpack-grid'],
    ['backpack-390x844', '/inventory', 390,844, '#backpack-grid'],
    ['backpack-360x800', '/inventory', 360,800, '#backpack-grid'],
    ['shop-1440x900', '/shop', 1440,900, '#items-grid'],
    ['shop-768x1024', '/shop', 768,1024, '#items-grid'],
    ['shop-430x932', '/shop', 430,932, '#items-grid'],
  ];
  const results = [];
  for (const [name, route, width, height, ready] of specs) {
    const { page, diagnostics } = await openPage(browser, origin, route, { width, height });
    await page.locator(ready).waitFor({ state:'visible' });
    if (route.startsWith('/inventory')) await page.waitForFunction(() => document.querySelector('#backpack-status')?.dataset.state === 'ready');
    if (route.startsWith('/hero')) {
      await page.waitForFunction(() => {
        const value = document.querySelector('#hero-overview-name')?.textContent?.trim();
        return value && value !== '—';
      });
      if (route.includes('tab=honors')) await page.locator('#hero-badge-grid > *').first().waitFor({ state:'visible' });
    }
    await page.evaluate(() => window.scrollTo(0, document.scrollingElement?.scrollHeight || document.documentElement.scrollHeight));
    await page.waitForTimeout(50);
    const snapshot = {
      ...(await pageSnapshot(page)),
      ...(await page.evaluate(() => ({
        ...(() => {
          const visible = node => {
            const rect = node.getBoundingClientRect();
            const style = getComputedStyle(node);
            return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
          };
          const bottomNav = [...document.querySelectorAll('#mobile-nav, .cg-nav, .mobile-nav, .mob-nav')].find(node => {
            if (!visible(node)) return false;
            const rect = node.getBoundingClientRect();
            return getComputedStyle(node).position === 'fixed' && rect.width >= window.innerWidth * .5 && rect.bottom >= window.innerHeight - 2;
          });
          const lastTarget = document.querySelector('#backpack-grid .backpack-card:last-child')
            || document.querySelector('#items-grid .item-card:last-child')
            || document.querySelector('#right-panel [role="tabpanel"]:not([hidden]) .inv-section:last-of-type')
            || document.querySelector('main > :last-child');
          const root = document.querySelector('main') || document.body;
          const verticalScrollTraps = [...root.querySelectorAll('*')].filter(node => {
            const style = getComputedStyle(node);
            const rect = node.getBoundingClientRect();
            return visible(node) && /(auto|scroll)/.test(style.overflowY)
              && node.scrollHeight > node.clientHeight + 4 && rect.height < window.innerHeight - 20;
          }).map(node => node.id || node.className || node.tagName);
          const lastRect = lastTarget?.getBoundingClientRect();
          const navRect = bottomNav?.getBoundingClientRect();
          const safeBottom = navRect?.top ?? window.innerHeight;
          return {
            fixedBottomNavTop:navRect?.top ?? null,
            fixedBottomNavHeight:navRect?.height ?? 0,
            lastTarget:lastTarget ? (lastTarget.id || lastTarget.className || lastTarget.tagName) : null,
            lastTargetBottom:lastRect?.bottom ?? null,
            lastTargetReachable:!lastRect || lastRect.bottom <= safeBottom + 1,
            documentAtScrollEnd:(document.scrollingElement?.scrollTop || 0) + window.innerHeight >= (document.scrollingElement?.scrollHeight || 0) - 2,
            verticalScrollTraps,
            backpackGridCount:document.querySelectorAll('[data-authoritative-backpack-grid]').length,
            backpackCardCount:document.querySelectorAll('.backpack-card').length,
          };
        })(),
        mainBottom:document.querySelector('main')?.getBoundingClientRect().bottom,
        viewportHeight:window.innerHeight,
        tabsScrollWidth:document.querySelector('.main-tabs')?.scrollWidth || 0,
        tabsClientWidth:document.querySelector('.main-tabs')?.clientWidth || 0,
      }))),
    };
    const shot = await screenshot(page, outputDir, `${name}.png`);
    const failures = [];
    if (snapshot.horizontalOverflow) failures.push('horizontal overflow');
    if (snapshot.duplicateIds.length) failures.push(`duplicate ids ${snapshot.duplicateIds.join(',')}`);
    if (width <= 768 && snapshot.fixedBottomNavTop === null) failures.push('fixed mobile navigation was not detected');
    if (!snapshot.lastTargetReachable) failures.push('last content row is obstructed by fixed navigation');
    if (snapshot.verticalScrollTraps.length) failures.push(`nested vertical scroll trap ${snapshot.verticalScrollTraps.join(',')}`);
    if (route.startsWith('/shop') && (snapshot.backpackGridCount || snapshot.backpackCardCount)) failures.push('Shop responsive layout contains Backpack inventory content');
    if (diagnostics.console.length || diagnostics.network.length) failures.push('console/network errors');
    results.push({ name, route, viewport:{ width,height }, snapshot, diagnostics, screenshot:shot, failures });
    await page.close();
  }
  return results;
}

async function runEnglishRepresentatives(browser, origin, outputDir) {
  const specs = [
    ['hero-en', '/hero?tab=hero&lang=en', '#hero-tab-hero', 'Character'],
    ['backpack-en', '/inventory?lang=en', '#backpack-title', 'Backpack'],
    ['shop-en', '/shop?lang=en', '#shop-title', 'Shop'],
  ];
  const results = [];
  for (const [name, route, selector, expected] of specs) {
    const { page, diagnostics } = await openPage(browser, origin, route, { width:1180, height:820 });
    await page.locator(selector).waitFor({ state:'visible' });
    if (route.startsWith('/inventory')) await page.waitForFunction(() => document.querySelector('#backpack-status')?.dataset.state === 'ready');
    const state = await page.evaluate(({ selector, expected }) => ({
      lang:typeof I18n !== 'undefined' && I18n.getLang ? I18n.getLang() : null,
      text:document.querySelector(selector)?.textContent?.trim() || '',
      expected,
      horizontalOverflow:Math.max(document.body.scrollWidth, document.documentElement.scrollWidth) > window.innerWidth + 1,
    }), { selector, expected });
    const failures = [];
    if (state.lang !== 'en' || !state.text.includes(expected)) failures.push('English representative state did not apply');
    if (state.horizontalOverflow) failures.push('English representative has horizontal overflow');
    if (diagnostics.console.length || diagnostics.network.length) failures.push('English representative console/network errors');
    const shot = await screenshot(page, outputDir, `${name}.png`);
    results.push({ name, route, state, diagnostics, screenshot:shot, failures });
    await page.close();
  }
  return results;
}

async function main() {
  const args = process.argv.slice(2);
  const outputIndex = args.indexOf('--out');
  if (outputIndex < 0 || !args[outputIndex + 1]) throw new Error('--out <unique-directory> is required');
  const outputDir = path.resolve(args[outputIndex + 1]);
  if (fssync.existsSync(outputDir)) throw new Error(`output directory already exists: ${outputDir}`);
  await fs.mkdir(outputDir, { recursive:true });
  const { server, origin } = await startServer();
  const browser = await chromium.launch({ headless:true, executablePath:findChrome() });
  try {
    const hero = await runHeroContract(browser, origin, outputDir);
    const backpack = await runBackpackContract(browser, origin, outputDir);
    const e10BackpackOwnership = await runE10BackpackOwnershipContract(browser, origin, outputDir);
    const backpackStates = [];
    for (const mode of ['loading','empty','error']) backpackStates.push(await runBackpackStateCase(browser, origin, outputDir, mode));
    const shop = await runShopSeparationContract(browser, origin, outputDir);
    const responsive = await runResponsiveMatrix(browser, origin, outputDir);
    const englishRepresentatives = await runEnglishRepresentatives(browser, origin, outputDir);
    const failures = [
      ...hero.failures,
      ...backpack.failures,
      ...e10BackpackOwnership.failures,
      ...backpackStates.flatMap((entry) => entry.failures),
      ...shop.failures,
      ...responsive.flatMap((entry) => entry.failures.map((failure) => `${entry.name}: ${failure}`)),
      ...englishRepresentatives.flatMap((entry) => entry.failures.map((failure) => `${entry.name}: ${failure}`)),
    ];
    const report = {
      contract:'e10-adventure-hero-shop-backpack-information-architecture-v1',
      sourceRoot:repoRoot,
      runtimeOrigin:origin,
      ok:failures.length === 0,
      hero,
      backpack,
      e10BackpackOwnership,
      backpackStates,
      shop,
      responsive,
      englishRepresentatives,
      failures,
    };
    await fs.writeFile(path.join(outputDir, 'information-architecture-contract.json'), JSON.stringify(report, null, 2));
    process.stdout.write(JSON.stringify({ ok:report.ok, outputDir, screenshots:[...hero.screenshots, ...backpack.screenshots, ...e10BackpackOwnership.screenshots, ...backpackStates.map((entry) => entry.screenshot), ...shop.screenshots, ...responsive.map((entry) => entry.screenshot), ...englishRepresentatives.map((entry) => entry.screenshot)].length, failures }, null, 2));
    if (failures.length) process.exitCode = 1;
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

await main();
