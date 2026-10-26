import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const src = fs.readFileSync(path.join(root, 'inventory.html'), 'utf8');
function extracted(name, next) {
  const begin=src.indexOf('function '+name+'(');
  const end=src.indexOf('\nfunction '+next+'(',begin);
  assert.ok(begin>=0 && end>begin,name);
  return src.slice(begin,end);
}
const code = extracted('functionalEffectDetails','functionalUnsupportedEffects') +
  '\n'+extracted('functionalUnsupportedEffects','functionalEffectLabel');
const item = {
  canonical_equippable: true,
  active_effect_details: [{label:'傷害加成',value_label:'+6%'}],
  unsupported_effects: [{label:'經驗加成',value_label:'+20%'}]
};
for(const enabled of [false,true]) {
  const ctx={functionalEquipmentLoadoutEnabled:()=>enabled,
    functionalItemEquippable:item=>item.canonical_equippable===true};
  vm.runInNewContext(code,ctx);
  assert.equal(ctx.functionalEffectDetails(item).length,enabled?1:0);
  assert.equal(ctx.functionalUnsupportedEffects(item).length,enabled?1:0);
}
assert.ok(src.includes('if (selected) renderFunctionalEquipmentGrid();'));
console.log('G075_EQUIPMENT_OFF_BONUS_VISIBILITY 5 PASS / 0 FAIL');
