import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const testDirectory = path.dirname(fileURLToPath(import.meta.url));
const shopPath = path.resolve(testDirectory, '../../shop.html');
const shopHtml = fs.readFileSync(shopPath, 'utf8');

const adapterStart = shopHtml.indexOf('// C043-E-EQUIPMENT-COMMERCE-FEEDBACK-START');
const adapterEnd = shopHtml.indexOf('// C043-E-EQUIPMENT-COMMERCE-FEEDBACK-END');
assert.notEqual(adapterStart, -1, 'C043-E adapter start marker is present');
assert.notEqual(adapterEnd, -1, 'C043-E adapter end marker is present');

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
  `${shopHtml.slice(adapterStart, adapterEnd)}
this.__c043 = {
  c043EquipmentOffer,
  c043EquipmentOffers,
  c043EquipmentOwnershipFocus,
  c043EquipmentPurchaseResult,
};`,
  sandbox,
);

const {
  c043EquipmentOffer,
  c043EquipmentOffers,
  c043EquipmentOwnershipFocus,
  c043EquipmentPurchaseResult,
} = sandbox.__c043;

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

const normalized = c043EquipmentOffer(offer);
assert.equal(normalized.offer_id, offer.offer_id);
assert.equal(normalized.item_id, offer.item_id);
assert.equal(normalized.price, offer.price, 'price is preserved from the server offer');
assert.equal(normalized.currency_type, 'COINS');
assert.equal(normalized.destination, 'player_inventory');
assert.equal(normalized.acquisition_class, 'WEAPON');
assert.deepEqual(normalized.presentation_metadata, offer.presentation_metadata);
assert.equal(c043EquipmentOffers({ equipment_offers: [offer, { ...offer, price: 0 }] }).length, 1);
assert.equal(c043EquipmentOffers({ items: [offer] }).length, 0, 'legacy items do not become equipment offers');

for (const [field, value] of [
  ['currency_type', 'USD'],
  ['destination', 'shop_inventory'],
  ['acquisition_class', 'TROPHY'],
  ['status', 'INACTIVE'],
  ['quantity', 2],
  ['price', 0],
]) {
  assert.equal(c043EquipmentOffer({ ...offer, [field]: value }), null, `rejects invalid ${field}`);
}
assert.equal(c043EquipmentOffer({ ...offer, price: '275' }), null, 'rejects string prices');
assert.equal(c043EquipmentOffer({ ...offer, offer_id: '' }), null, 'requires server offer identity');

assert.equal(
  c043EquipmentOwnershipFocus('player_inventory:17'),
  '/inventory?equipment=17',
);
for (const reference of [
  'player_inventory:0',
  'player_inventory:017',
  'player_inventory:17:extra',
  'shop_inventory:17',
  null,
]) {
  assert.equal(c043EquipmentOwnershipFocus(reference), '', `rejects ownership reference ${reference}`);
}

const canonical = {
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
};
const response = {
  ok: true,
  source_operation_id: canonical.source_operation_id,
  ownership_reference: canonical.ownership_reference,
  canonical_acquisition_result: canonical,
};
assert.deepEqual(c043EquipmentPurchaseResult(response, normalized), canonical);

for (const [field, value] of [
  ['item_id', 'other-item'],
  ['source_reference', 'other-offer'],
  ['destination', 'STACK_INVENTORY'],
  ['ownership_authority', 'shop_inventory'],
  ['ownership_reference', 'player_inventory:18'],
  ['can_equip', 'true'],
  ['replayed', 0],
]) {
  assert.equal(
    c043EquipmentPurchaseResult(
      { ...response, canonical_acquisition_result: { ...canonical, [field]: value } },
      normalized,
    ),
    null,
    `rejects inconsistent canonical ${field}`,
  );
}
assert.equal(c043EquipmentPurchaseResult({ ok: true }, normalized), null, 'requires canonical result');
assert.equal(
  c043EquipmentPurchaseResult(
    { ...response, source_operation_id: 'other-operation' },
    normalized,
  ),
  null,
  'rejects top-level/source operation mismatch',
);

assert.match(shopHtml, /equipment_offers/, 'Shop reads the optional equipment-offer field');
assert.match(
  shopHtml,
  /requestShopPurchase\('\/api\/shop\/buy', offer\.offer_id/,
  'equipment purchase uses the existing Shop purchase route',
);
assert.match(shopHtml, /canonical_acquisition_result/, 'Shop requires canonical purchase evidence');
assert.doesNotMatch(
  shopHtml,
  /fetch\(['"]\/api\/player\/inventory\/equip/,
  'Shop does not auto-equip equipment',
);

console.log('C043-E equipment Shop adapter contract: server-offer validation and feedback evidence passed');
