import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const testDirectory = path.dirname(fileURLToPath(import.meta.url));
const shopPath = path.resolve(testDirectory, '../../shop.html');
const shopHtml = fs.readFileSync(shopPath, 'utf8');

function markedBlock(source, startMarker, endMarker, label) {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker);
  assert.notEqual(start, -1, `${label} start marker is present`);
  assert.notEqual(end, -1, `${label} end marker is present`);
  assert.ok(end > start, `${label} end marker follows its start marker`);
  return source.slice(start + startMarker.length, end);
}

function sourceBetween(source, startMarker, endMarker, label) {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start + startMarker.length);
  assert.notEqual(start, -1, `${label} start is present`);
  assert.notEqual(end, -1, `${label} end is present`);
  assert.ok(end > start, `${label} end follows its start`);
  return source.slice(start, end);
}

function c043Exports() {
  const adapter = markedBlock(
    shopHtml,
    '// C043-E-EQUIPMENT-COMMERCE-FEEDBACK-START',
    '// C043-E-EQUIPMENT-COMMERCE-FEEDBACK-END',
    'C043-E adapter',
  );
  const sandbox = {
    Array,
    Date,
    JSON,
    Number,
    Object,
    Set,
    String,
    encodeURIComponent,
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(
    `${adapter}
this.__c043 = {
  c043EquipmentOffer,
  c043EquipmentOffers,
  c043EquipmentOwnershipFocus,
  c043EquipmentPurchaseResult,
};`,
    sandbox,
  );
  return sandbox.__c043;
}

const {
  c043EquipmentOffer,
  c043EquipmentOffers,
  c043EquipmentOwnershipFocus,
  c043EquipmentPurchaseResult,
} = c043Exports();

const offer = {
  offer_id: 'offer-server-weapon-1',
  item_id: 'server-weapon-1',
  quantity: 1,
  currency_type: 'COINS',
  price: 275,
  destination: 'player_inventory',
  acquisition_class: 'WEAPON',
  status: 'ACTIVE',
  presentation_metadata: {
    name_en: 'Server Blade',
    name: '伺服器之刃',
    description_en: 'A server-described equipment offer.',
    icon: '⚔️',
  },
};

function canonicalResult(overrides = {}) {
  return {
    source_type: 'SHOP_COIN_PURCHASE',
    source_operation_id: 'purchase-operation-1',
    source_reference: offer.offer_id,
    destination: 'PLAYER_INVENTORY',
    ownership_authority: 'player_inventory',
    ownership_reference: 'player_inventory:17',
    item_id: offer.item_id,
    quantity: 1,
    can_equip: true,
    can_wear: true,
    is_new: true,
    replayed: false,
    ...overrides,
  };
}

function successResponse(overrides = {}) {
  const result = canonicalResult(overrides.canonical_acquisition_result);
  return {
    ok: true,
    source_operation_id: result.source_operation_id,
    ownership_reference: result.ownership_reference,
    canonical_acquisition_result: result,
    ...overrides,
  };
}

function assertC043RegressionContract() {
  const normalized = c043EquipmentOffer(offer);
  assert.equal(normalized.offer_id, offer.offer_id);
  assert.equal(normalized.item_id, offer.item_id);
  assert.equal(normalized.quantity, 1);
  assert.equal(normalized.price, offer.price, 'the rendered price is the server offer price');
  assert.equal(normalized.currency_type, 'COINS');
  assert.equal(normalized.destination, 'player_inventory');
  assert.equal(normalized.acquisition_class, 'WEAPON');
  assert.equal(normalized.status, 'ACTIVE');
  assert.deepEqual(normalized.presentation_metadata, offer.presentation_metadata);

  assert.equal(
    c043EquipmentOffers({ equipment_offers: [offer, { ...offer, price: 0 }] }).length,
    1,
    'only valid server equipment offers render',
  );
  assert.equal(
    c043EquipmentOffers({ items: [offer] }).length,
    0,
    'legacy item data cannot become an equipment offer',
  );

  for (const [field, value] of [
    ['offer_id', ''],
    ['item_id', ''],
    ['quantity', 2],
    ['currency_type', 'USD'],
    ['price', 0],
    ['price', '275'],
    ['destination', 'shop_inventory'],
    ['acquisition_class', 'TROPHY'],
    ['status', 'INACTIVE'],
  ]) {
    assert.equal(
      c043EquipmentOffer({ ...offer, [field]: value }),
      null,
      `malformed or unauthorized server offer is rejected: ${field}`,
    );
  }
  for (const malformed of [null, undefined, 'offer', 42, []]) {
    assert.equal(c043EquipmentOffer(malformed), null, 'malformed item data fails closed');
  }
  assert.equal(
    Object.keys(c043EquipmentOffer({ ...offer, presentation_metadata: [] }).presentation_metadata).length,
    0,
    'non-object presentation metadata is normalized without inventing presentation data',
  );

  assert.equal(
    c043EquipmentOwnershipFocus('player_inventory:17'),
    '/inventory?equipment=17',
    'Backpack navigation uses the exact persisted ownership reference',
  );
  for (const reference of [
    'player_inventory:0',
    'player_inventory:017',
    'player_inventory:17:extra',
    'shop_inventory:17',
    'player_inventory:abc',
    null,
  ]) {
    assert.equal(
      c043EquipmentOwnershipFocus(reference),
      '',
      `ownership refresh rejects non-canonical reference ${reference}`,
    );
  }

  const canonical = canonicalResult();
  const response = successResponse({ canonical_acquisition_result: canonical });
  assert.deepEqual(
    c043EquipmentPurchaseResult(response, normalized),
    canonical,
    'success requires the canonical acquisition result',
  );
  assert.equal(
    c043EquipmentPurchaseResult({ ok: true }, normalized),
    null,
    'ok without canonical acquisition evidence is not a success',
  );

  for (const [field, value] of [
    ['item_id', 'other-item'],
    ['source_reference', 'other-offer'],
    ['destination', 'STACK_INVENTORY'],
    ['ownership_authority', 'shop_inventory'],
    ['ownership_reference', 'player_inventory:18'],
    ['can_equip', 'true'],
    ['can_wear', 1],
    ['is_new', 1],
    ['replayed', 0],
  ]) {
    assert.equal(
      c043EquipmentPurchaseResult(
        { ...response, canonical_acquisition_result: { ...canonical, [field]: value } },
        normalized,
      ),
      null,
      `inconsistent canonical result fails closed: ${field}`,
    );
  }
  assert.equal(
    c043EquipmentPurchaseResult(
      { ...response, source_operation_id: 'other-operation' },
      normalized,
    ),
    null,
    'top-level source operation identity must match the canonical result',
  );
  assert.equal(
    c043EquipmentPurchaseResult(
      { ...response, ownership_reference: 'player_inventory:18' },
      normalized,
    ),
    null,
    'top-level ownership identity must match the canonical result',
  );

  const equipmentCardSource = sourceBetween(
    shopHtml,
    'function c043EquipmentOfferCardHTML',
    'function renderEquipmentOffers',
    'C043 equipment card',
  );
  assert.match(
    equipmentCardSource,
    /money\(offer\.price\)/,
    'catalog cards render the server-provided offer price',
  );
  assert.match(
    equipmentCardSource,
    /data-equipment-purchase=.*offer\.offer_id/,
    'the CTA is keyed by the server offer identity',
  );

  const purchaseSource = sourceBetween(
    shopHtml,
    'async function purchaseEquipment(offerId, button)',
    'function productRegistryEntry',
    'C043 equipment purchase path',
  );
  assert.match(
    purchaseSource,
    /requestShopPurchase\(\s*['"]\/api\/shop\/buy['"]\s*,\s*offer\.offer_id\s*,\s*\{\s*item_key:\s*offer\.item_id\s*,\s*\}\s*\)/s,
    'equipment purchase uses the existing Shop buy route and item_key',
  );
  assert.doesNotMatch(
    purchaseSource,
    /requestShopPurchase\([\s\S]*?\{[^}]*\bprice\s*:/s,
    'equipment purchase does not send a client price authority',
  );
  assert.match(
    purchaseSource,
    /const result = c043EquipmentPurchaseResult\(response, offer\)/,
    'the purchase path validates the canonical result before visual success',
  );
  const resultIndex = purchaseSource.indexOf('const result = c043EquipmentPurchaseResult(response, offer)');
  const successMatch = /setEquipmentPurchaseFeedback\s*\(\s*['"]success['"]/.exec(purchaseSource);
  const successIndex = successMatch?.index ?? -1;
  assert.ok(resultIndex >= 0 && successIndex > resultIndex, 'success feedback follows canonical validation');
  assert.match(
    purchaseSource,
    /c043EquipmentOwnershipFocus\(result\.ownership_reference\)/,
    'success navigation uses the canonical ownership_reference',
  );
  assert.doesNotMatch(
    purchaseSource,
    /showPurchaseConfirmation|resolvePurchaseGrants|granted_items|granted_food/,
    'equipment success does not synthesize a second visual grant',
  );
  assert.doesNotMatch(
    shopHtml,
    /fetch\(\s*['"]\/api\/player\/inventory\/equip/,
    'the Shop does not auto-equip equipment',
  );

  console.log('C043 adapter regression contract: server fields, canonical result, exact Backpack reference, and no auto-equip passed');
}

function assertCatalogAndCoinsContract() {
  assert.match(shopHtml, /id="coin-bal"/, 'Shop has the Coins display');
  assert.match(shopHtml, /equipment_offers/, 'catalog rendering reads the server equipment_offers field');

  const catalogSource = sourceBetween(
    shopHtml,
    'async function loadCatalog()',
    'function renderDaily',
    'Shop catalog loading',
  );
  assert.match(catalogSource, /api\("\/api\/shop\/catalog"\)/, 'Coins/catalog state comes from the Shop catalog route');
  assert.match(
    catalogSource,
    /document\.getElementById\("coin-bal"\)\.textContent = money\(res\.coins\)/,
    'the displayed Coins value is refreshed from authoritative res.coins',
  );

  const purchaseSource = sourceBetween(
    shopHtml,
    'async function purchaseEquipment(offerId, button)',
    'function productRegistryEntry',
    'Shop equipment purchase path',
  );
  assert.match(
    purchaseSource,
    /Number\.isInteger\(response\.coins_after\)[\s\S]*document\.getElementById\('coin-bal'\)\.textContent = money\(response\.coins_after\)/,
    'a server-provided coins_after value may refresh the Coins display',
  );
  assert.match(purchaseSource, /await loadCatalog\(\)/, 'success refreshes the authoritative catalog and Coins state');
  assert.doesNotMatch(
    purchaseSource,
    /(?:catalog|equipmentOffers)\s*\.coins\s*[-+]=|coin-bal[\s\S]{0,100}(?:\+\+|--|\+=|-=)/,
    'the client does not locally debit or increment Coins',
  );

  const errorCodes = [
    'insufficient_coins',
    'already_owned',
    'unknown_product',
    'invalid_offer',
    'offer_not_ready',
    'purchase_operation_conflict',
    'purchase_operation_in_progress',
    'ownership_authority_unavailable',
    'schema_unavailable',
    'acquisition_failed',
    'canonical_result_unavailable',
    'invalid_operation_identity',
  ];
  for (const code of errorCodes) {
    assert.match(shopHtml, new RegExp(`${code}:`), `Shop has a user-facing contract for ${code}`);
  }
  assert.match(shopHtml, /Retry the same purchase/, 'retryable failures tell the player to retry the same purchase');
  assert.match(shopHtml, /HTTP 5\\d\\d/, 'server 5xx failures remain retryable');

  const pendingCount = (purchaseSource.match(/setEquipmentPurchaseFeedback\(\s*['"]pending['"]/g) || []).length;
  assert.ok(pendingCount >= 1, 'the purchase path has an explicit pending visual state');
  assert.ok(
    /c044EquipmentPurchaseInFlight\.delete\(offerId\)/.test(purchaseSource)
      && /c044ApplyEquipmentButtonStates\(\)/.test(purchaseSource),
    'error and unverified-result paths release the in-flight CTA state',
  );
  const buttonStateSource = sourceBetween(
    shopHtml,
    'function c044ApplyEquipmentButtonState',
    'function c044ApplyEquipmentButtonStates',
    'C044 equipment CTA state helper',
  );
  assert.ok(
    /button\.disabled\s*=\s*pending/.test(buttonStateSource)
      && /button\.removeAttribute\('aria-busy'\)/.test(buttonStateSource),
    'the shared CTA state helper clears pending and aria-busy after recovery',
  );

  console.log('Catalog/Coins/error contract: server price authority, refresh, terminal errors, and recovery copy passed');
}

function makeIntentHarness({ storageValues, generatedIds, responses, calls }) {
  const sandbox = {
    Array,
    Date,
    Error,
    JSON,
    Map,
    Number,
    Object,
    String,
    encodeURIComponent,
    globalThis: null,
    window: {
      sessionStorage: {
        getItem: key => storageValues.get(key) ?? null,
        setItem: (key, value) => storageValues.set(key, value),
        removeItem: key => storageValues.delete(key),
      },
    },
    crypto: {
      randomUUID: () => {
        const id = generatedIds.shift();
        assert.ok(id, 'deterministic operation-id fixture is available');
        return id;
      },
    },
    api: async (route, options) => {
      calls.push({ route, options });
      assert.ok(responses.length, `deterministic response fixture exists for ${route}`);
      const response = responses.shift();
      if (response instanceof Error) throw response;
      return response;
    },
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  const helper = markedBlock(
    shopHtml,
    '// E030-R1-SHOP-PURCHASE-INTENT-START',
    '// E030-R1-SHOP-PURCHASE-INTENT-END',
    'E030-R1 purchase-intent helper',
  );
  vm.runInContext(
    `${helper}
this.__requestShopPurchase = requestShopPurchase;`,
    sandbox,
  );
  return sandbox.__requestShopPurchase;
}

function bodyFor(call) {
  return JSON.parse(call.options.body);
}

function pendingIntentFor(storageValues, selector) {
  const intents = [...storageValues.values()].map(value => JSON.parse(value));
  return intents.find(intent => intent.selector === selector) || null;
}

async function assertE030RetryAndIdentityContract() {
  const storageValues = new Map();
  const generatedIds = [
    'operation-success-1',
    'operation-canonical-retry-2',
    'operation-in-progress-3',
    'operation-network-4',
    'operation-timeout-5',
    'operation-insufficient-6',
    'operation-owned-7',
    'operation-unknown-8',
    'operation-invalid-9',
    'operation-schema-10',
  ];
  const calls = [];
  const responses = [];
  const route = '/api/shop/buy';
  const itemPayload = { item_key: offer.item_id };
  let requestShopPurchase = makeIntentHarness({
    storageValues,
    generatedIds,
    responses,
    calls,
  });

  responses.push(successResponse({
    canonical_acquisition_result: canonicalResult({ source_operation_id: 'operation-success-1' }),
  }));
  await requestShopPurchase(route, offer.offer_id, itemPayload);
  assert.equal(bodyFor(calls.at(-1)).purchase_operation_id, 'operation-success-1');
  assert.equal(storageValues.size, 0, 'a confirmed purchase does not leave pending intent state');

  responses.push({ error: 'canonical_result_unavailable' });
  await requestShopPurchase(route, offer.offer_id, itemPayload);
  assert.equal(
    pendingIntentFor(storageValues, offer.offer_id).operationId,
    'operation-canonical-retry-2',
    'canonical-result recovery retains the same operation identity',
  );
  const canonicalReplay = successResponse({
    canonical_acquisition_result: canonicalResult({
      source_operation_id: 'operation-canonical-retry-2',
      replayed: true,
      is_new: false,
    }),
  });
  responses.push(canonicalReplay);
  await requestShopPurchase(route, offer.offer_id, itemPayload);
  assert.equal(bodyFor(calls.at(-1)).purchase_operation_id, 'operation-canonical-retry-2');
  assert.deepEqual(
    c043EquipmentPurchaseResult(canonicalReplay, c043EquipmentOffer(offer)),
    canonicalReplay.canonical_acquisition_result,
    'a replayed canonical result remains a valid C043 result, not a second grant',
  );
  assert.equal(storageValues.size, 0, 'successful canonical recovery clears pending state');

  const inProgressSelector = 'offer-server-weapon-replay';
  responses.push({ error: 'purchase_operation_in_progress' });
  await requestShopPurchase(route, inProgressSelector, itemPayload);
  const inProgressIntent = pendingIntentFor(storageValues, inProgressSelector);
  assert.equal(inProgressIntent.operationId, 'operation-in-progress-3');
  responses.push(successResponse({
    canonical_acquisition_result: canonicalResult({
      source_operation_id: 'operation-in-progress-3',
      source_reference: inProgressSelector,
      replayed: true,
      is_new: false,
    }),
  }));
  await requestShopPurchase(route, inProgressSelector, itemPayload);
  assert.equal(bodyFor(calls.at(-1)).purchase_operation_id, 'operation-in-progress-3');
  assert.equal(storageValues.size, 0, 'in-progress replay eventually leaves no stuck pending intent');

  const networkSelector = 'offer-server-weapon-network';
  responses.push(new Error('network timeout'));
  await assert.rejects(
    requestShopPurchase(route, networkSelector, itemPayload),
    /network timeout/,
    'a missing response is surfaced without pretending the purchase succeeded',
  );
  const networkIntent = pendingIntentFor(storageValues, networkSelector);
  assert.equal(networkIntent.operationId, 'operation-network-4');

  // A fresh VM models a reload: the persisted E030 intent is the source of
  // truth for retry, so a new random UUID must not be consumed.
  requestShopPurchase = makeIntentHarness({
    storageValues,
    generatedIds,
    responses,
    calls,
  });
  const generatedBeforeReloadRetry = generatedIds.length;
  responses.push(successResponse({
    canonical_acquisition_result: canonicalResult({
      source_operation_id: 'operation-network-4',
      source_reference: networkSelector,
      replayed: true,
      is_new: false,
    }),
  }));
  await requestShopPurchase(route, networkSelector, itemPayload);
  assert.equal(bodyFor(calls.at(-1)).purchase_operation_id, 'operation-network-4');
  assert.equal(generatedIds.length, generatedBeforeReloadRetry, 'reload retry does not generate a new identity');
  assert.equal(storageValues.size, 0, 'network recovery clears pending state after canonical confirmation');

  const timeoutSelector = 'offer-server-weapon-timeout';
  responses.push(new Error('request timeout'));
  await assert.rejects(
    requestShopPurchase(route, timeoutSelector, itemPayload),
    /request timeout/,
  );
  const timeoutIntent = pendingIntentFor(storageValues, timeoutSelector);
  assert.equal(timeoutIntent.operationId, 'operation-timeout-5');
  responses.push({ error: 'HTTP 504' });
  await requestShopPurchase(route, timeoutSelector, itemPayload);
  assert.equal(
    pendingIntentFor(storageValues, timeoutSelector).operationId,
    'operation-timeout-5',
    'server timeout retry retains the same operation identity',
  );
  responses.push(successResponse({
    canonical_acquisition_result: canonicalResult({
      source_operation_id: 'operation-timeout-5',
      source_reference: timeoutSelector,
      replayed: true,
      is_new: false,
    }),
  }));
  await requestShopPurchase(route, timeoutSelector, itemPayload);
  assert.equal(storageValues.size, 0, 'timeout recovery leaves no stuck pending intent');

  const terminalCases = [
    ['offer-insufficient', 'operation-insufficient-6', 'insufficient_coins'],
    ['offer-owned', 'operation-owned-7', 'already_owned'],
    ['offer-unknown', 'operation-unknown-8', 'unknown_product'],
    ['offer-malformed', 'operation-invalid-9', 'invalid_offer'],
    ['offer-schema', 'operation-schema-10', 'schema_unavailable'],
  ];
  for (const [selector, operationId, error] of terminalCases) {
    responses.push({ error });
    await requestShopPurchase(route, selector, { item_key: selector });
    assert.equal(bodyFor(calls.at(-1)).purchase_operation_id, operationId);
    assert.equal(
      pendingIntentFor(storageValues, selector),
      null,
      `${error} is terminal UI feedback and does not leave stale pending intent`,
    );
  }

  assert.equal(calls.length, 15, 'the deterministic scenarios issued exactly the expected requests');
  assert.equal(storageValues.size, 0, 'all terminal and recovered paths end in stable state');
  console.log('E030 retry/identity contract: insufficient, owned, unknown/malformed, server failure, network/timeout, replay, and reload recovery passed');
}

function assertC044BPlayerExperienceContract() {
  // C044-B owns this seam. It must be pure so this source-level contract can
  // inspect it with Node only; DOM wiring is asserted against Shop source
  // strings below.
  const c044 = markedBlock(
    shopHtml,
    '// C044-B-SHOP-PLAYER-UX-PURE-START',
    '// C044-B-SHOP-PLAYER-UX-PURE-END',
    'C044-B pure Shop player-UX helper',
  );
  assert.doesNotMatch(
    c044,
    /\b(?:document|window|fetch|localStorage|sessionStorage)\b/,
    'C044-B pure helper is DOM/browser-independent',
  );
  assert.match(c044, /\bc044[A-Za-z0-9_]*\b/, 'C044-B exposes a clearly named C044 helper');

  for (const field of [
    'canonical_acquisition_result',
    'source_operation_id',
    'source_reference',
    'ownership_reference',
    'coins_after',
    'can_equip',
    'can_wear',
    'is_new',
    'replayed',
    'purchase_operation_id',
  ]) {
    assert.match(c044, new RegExp(`\\b${field}\\b`), `C044-B preserves the real C043 field ${field}`);
  }
  for (const error of [
    'insufficient_coins',
    'already_owned',
    'invalid_offer',
    'schema_unavailable',
    'purchase_operation_in_progress',
    'canonical_result_unavailable',
  ]) {
    assert.match(c044, new RegExp(`\\b${error}\\b`), `C044-B handles the real Shop error ${error}`);
  }
  for (const state of ['pending', 'error', 'success']) {
    assert.match(c044, new RegExp(`['"]${state}['"]|\\b${state}\\b`), `C044-B has a stable ${state} state`);
  }
  assert.match(c044, /in.?flight|duplicate/i, 'C044-B names the in-flight/double-tap guard');

  const purchaseSource = sourceBetween(
    shopHtml,
    'async function purchaseEquipment(offerId, button)',
    'function productRegistryEntry',
    'C044 equipment purchase wiring',
  );
  const ctaStateSource = sourceBetween(
    shopHtml,
    'function c044ApplyEquipmentButtonState',
    'function c044ApplyEquipmentButtonStates',
    'C044 equipment CTA state helper',
  );
  const purchaseAndCtaStateSource = `${purchaseSource}\n${ctaStateSource}`;
  assert.match(purchaseSource, /c044/i, 'C044-B is integrated into the equipment purchase path');
  assert.match(
    purchaseSource,
    /(?:in.?flight|duplicate|pending)[\s\S]{0,180}(?:has|add|delete)|(?:has|add|delete)[\s\S]{0,180}(?:in.?flight|duplicate|pending)/i,
    'double-tap/in-flight CTA state is checked, entered, and released',
  );
  assert.match(purchaseAndCtaStateSource, /button\.disabled\s*=\s*(?:true|pending)/, 'the in-flight CTA is disabled');
  assert.match(purchaseAndCtaStateSource, /aria-busy/, 'the in-flight CTA exposes busy state');
  assert.equal(
    (purchaseSource.match(/setEquipmentPurchaseFeedback\(\s*['"]success['"]/g) || []).length,
    1,
    'one canonical completion produces one visual success grant',
  );
  assert.equal(
    (purchaseSource.match(/successToast/g) || []).length,
    1,
    'one canonical completion produces one success toast path',
  );
  assert.doesNotMatch(
    purchaseSource,
    /(?:inventory|ownership)[\s\S]{0,120}(?:equip|wear)\s*\(/i,
    'C044-B does not add auto-equip behavior to the Shop CTA',
  );

  // The C044 frontend slice has no permission to activate deployment,
  // migration, payment, or production gates.
  assert.doesNotMatch(shopHtml, /\bGO_[A-Z0-9_]+\b/, 'frontend source keeps owner gates OFF');
  assert.doesNotMatch(shopHtml, /GO_PRODUCTION_DB_MIGRATION|PRODUCTION_MUTATION|\/api\/payment\b/i, 'no protected mutation gate is added');

  console.log('C044-B player-UX integration contract: pure state seam, double-tap safety, stable completion, no auto-equip, and gates OFF passed');
}

assertC043RegressionContract();
assertCatalogAndCoinsContract();
await assertE030RetryAndIdentityContract();
assertC044BPlayerExperienceContract();

console.log('C044 equipment Shop player-experience contract: all source and deterministic retry assertions passed');
