import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(
  new URL('../../js/game/shop_presentation_v1.js', import.meta.url),
  'utf8',
);

const documentStub = {
  readyState: 'loading',
  addEventListener() {},
};
const context = {
  document: documentStub,
  window: {},
};
vm.runInNewContext(source, context, { filename: 'shop_presentation_v1.js' });

const adapter = context.window.ShopPresentationV1;
assert.equal(adapter.VERSION, 'A034_SHOP_PRESENTATION_V1');
assert.equal(Object.isFrozen(adapter), true);

const catalog = {
  inventory: { hint_ticket: 2 },
  shop_product_grant_registry: [{
    product_id: 'hint_ticket',
    category: 'training',
    current_asset: '/assets/shop/items/hint_ticket.webp',
    art_status: 'EXISTING_APPROVED',
  }],
};
const item = adapter.normalizeItem({
  product_id: 'hint_ticket',
  name: '提示卷',
  name_en: 'Hint Ticket',
  price: 30,
  available: true,
}, catalog);

assert.deepEqual({ ...item }, {
  item_id: 'hint_ticket',
  display_name: '提示卷',
  display_name_en: 'Hint Ticket',
  category: 'training',
  image: '/assets/shop/items/hint_ticket.webp',
  server_price: 30,
  owned: true,
  owned_quantity: 2,
  available: true,
  legal_action: '',
  art_status: 'EXISTING_APPROVED',
});
assert.equal(Object.isFrozen(item), true);

const missingValues = adapter.normalizeItem({ product_id: 'future_item' }, {});
assert.equal(missingValues.server_price, null);
assert.equal(missingValues.owned, null);
assert.equal(missingValues.available, null);
assert.equal(missingValues.image, '');
assert.equal('stock' in missingValues, false);
assert.equal('discount' in missingValues, false);
assert.equal('rarity' in missingValues, false);

const normalized = adapter.normalizeCatalog({
  coins: 12450,
  daily_items: [{ product_id: 'hint_ticket', price: 30 }],
  items: [{ product_id: 'future_item' }],
  ...catalog,
});
assert.equal(normalized.valid, true);
assert.equal(normalized.coins, 12450);
assert.equal(normalized.sections.daily_rotation.length, 1);
assert.equal(normalized.items.length, 1);
assert.equal(Object.isFrozen(normalized), true);
assert.equal(Object.isFrozen(normalized.sections), true);
assert.equal(Object.isFrozen(normalized.sections.daily_rotation), true);

const invalid = adapter.normalizeCatalog(null);
assert.equal(invalid.valid, false);
assert.equal(invalid.coins, null);

console.log('A034 Shop presentation contract: 18 assertions passed');
