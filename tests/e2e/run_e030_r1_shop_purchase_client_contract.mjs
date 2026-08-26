import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const shopHtml = fs.readFileSync('shop.html', 'utf8');
const helperStart = shopHtml.indexOf('// E030-R1-SHOP-PURCHASE-INTENT-START');
const helperEnd = shopHtml.indexOf('// E030-R1-SHOP-PURCHASE-INTENT-END');
assert.notEqual(helperStart, -1, 'operation-id helper start marker is present');
assert.notEqual(helperEnd, -1, 'operation-id helper end marker is present');

const buyItemStart = shopHtml.indexOf('async function buyItem(key)');
const buyAppearanceStart = shopHtml.indexOf('async function buyAppearance(itemId)');
assert.notEqual(buyItemStart, -1, 'real buyItem caller is present');
assert.notEqual(buyAppearanceStart, -1, 'real buyAppearance caller is present');
assert.match(
  shopHtml.slice(buyItemStart, buyAppearanceStart),
  /requestShopPurchase\("\/api\/shop\/buy", key/,
  'buyItem uses the operation-id helper',
);
assert.match(
  shopHtml.slice(buyAppearanceStart, shopHtml.indexOf('async function doGacha', buyAppearanceStart)),
  /requestShopPurchase\("\/api\/shop\/buy_appearance", itemId/,
  'buyAppearance uses the operation-id helper',
);

const storageValues = new Map();
const calls = [];
const responses = [];
const generatedIds = ['UUID-A', 'UUID-B', 'UUID-C', 'UUID-D', 'UUID-E', 'UUID-F'];

const sandbox = {
  Date,
  JSON,
  Map,
  Number,
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
    randomUUID: () => generatedIds.shift(),
  },
  api: async (route, options) => {
    calls.push({ route, options });
    const response = responses.shift();
    if (response instanceof Error) throw response;
    return response;
  },
};
sandbox.globalThis = sandbox;

vm.createContext(sandbox);
vm.runInContext(
  `${shopHtml.slice(helperStart, helperEnd)}\nthis.__requestShopPurchase = requestShopPurchase;`,
  sandbox,
);

const requestShopPurchase = sandbox.__requestShopPurchase;
const bodyFor = call => JSON.parse(call.options.body);
const route = '/api/shop/buy';
const selector = 'hint_ticket';

responses.push({ ok: true });
await requestShopPurchase(route, selector, { item_key: selector });
assert.equal(bodyFor(calls.at(-1)).purchase_operation_id, 'UUID-A');
assert.equal(storageValues.size, 0, 'successful intent is cleared');

responses.push({ ok: true });
await requestShopPurchase(route, selector, { item_key: selector });
assert.equal(bodyFor(calls.at(-1)).purchase_operation_id, 'UUID-B');

responses.push(new Error('network timeout'));
await assert.rejects(
  requestShopPurchase(route, 'premium_hint_bundle', { item_key: 'premium_hint_bundle' }),
  /network timeout/,
);
const networkIntent = JSON.parse(
  [...storageValues.values()].find(value => value.includes('premium_hint_bundle')),
);
assert.equal(networkIntent.operationId, 'UUID-C', 'network failure keeps the pending identity');
responses.push({ ok: true });
await requestShopPurchase(
  route,
  'premium_hint_bundle',
  { item_key: 'premium_hint_bundle' },
);
assert.equal(bodyFor(calls.at(-1)).purchase_operation_id, 'UUID-C');
assert.equal(storageValues.size, 0, 'successful network retry clears the pending identity');

responses.push({ error: 'canonical_result_unavailable' });
await requestShopPurchase(route, 'hint_ticket', { item_key: 'hint_ticket' });
const postCommit503 = JSON.parse(
  [...storageValues.values()].find(value => value.includes('hint_ticket')),
);
assert.equal(postCommit503.operationId, 'UUID-D', 'post-commit recovery keeps the identity');
responses.push({ ok: true });
await requestShopPurchase(route, 'hint_ticket', { item_key: 'hint_ticket' });
assert.equal(bodyFor(calls.at(-1)).purchase_operation_id, 'UUID-D');
assert.equal(storageValues.size, 0, 'recovered committed intent is cleared after success');

responses.push({ error: 'purchase_operation_in_progress' });
await requestShopPurchase(route, 'extra_questions_small', { item_key: 'extra_questions_small' });
const inProgress = JSON.parse(
  [...storageValues.values()].find(value => value.includes('extra_questions_small')),
);
assert.equal(inProgress.operationId, 'UUID-E');
responses.push({ ok: true });
await requestShopPurchase(
  route,
  'extra_questions_small',
  { item_key: 'extra_questions_small' },
);
assert.equal(bodyFor(calls.at(-1)).purchase_operation_id, 'UUID-E');
assert.equal(storageValues.size, 0);

responses.push({ error: 'invalid_offer' });
await requestShopPurchase(route, 'invalid-product', { item_key: 'invalid-product' });
assert.equal(bodyFor(calls.at(-1)).purchase_operation_id, 'UUID-F');
assert.equal(storageValues.size, 0, 'terminal errors clear the pending identity');

console.log(`E030-R1 client operation-id contract: ${calls.length} requests passed`);
