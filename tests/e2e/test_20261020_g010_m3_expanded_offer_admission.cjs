// M3 expanded-equipment catalog admission contract, no HTTP or bypass.
// Extract shipped pure functions unchanged; fail closed on bad server facts.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {test}=require('node:test');

const source=fs.readFileSync(path.join(__dirname,'../../shop.html'),'utf8');
const c043=source.slice(source.indexOf('const C043_EQUIPMENT_CLASSES ='),
  source.indexOf('function c043EquipmentOwnershipFocus('));
const c053=source.slice(source.indexOf('function c053ServerCatalogEnablesOptionB('),
  source.indexOf('function c053CoinCosmeticProducts('));
assert(c043.startsWith('const C043_EQUIPMENT_CLASSES'));
assert(c053.startsWith('function c053ServerCatalogEnablesOptionB('));
assert(source.includes('const G009_SHOP_BROWSE_PREVIEW_ONLY = true;'));
function evaluateCatalog(catalog){
 const code=c043+'\n'+c053+
 '\nc053ServerCatalogEnablesOptionB(JSON.parse('+JSON.stringify(JSON.stringify(catalog))+'));';
 return vm.runInNewContext(code,{});
}
const offer=i=>({
 offer_id:'server.'+i,item_id:'item_'+i,quantity:1,price:100+i,
 currency_type:'COINS',destination:'player_inventory',
 acquisition_class:i%2?'WEAPON':'ARMOR',status:'ACTIVE',
 presentation_metadata:{name:'Equipment '+i},
});
test('C053 preserves the 3-offer admitted starter contract',()=>{
 assert.equal(evaluateCatalog({coins:1000,equipment_offers:[1,2,3].map(offer)}),true);
});
test('C053 accepts exactly 9 legitimate server-enabled expanded offers',()=>{
 const x={coins:1000,purchase_enabled:true,equipment_offers:Array.from({length:9},(_,i)=>offer(i+1))};
 assert.equal(evaluateCatalog(x),true);
 assert.equal(evaluateCatalog({...x,purchase_enabled:false}),false);
 assert.equal(evaluateCatalog({...x,purchase_enabled:null}),false);
 assert.equal(evaluateCatalog({...x,coins:-1}),false);
 assert.equal(evaluateCatalog({...x,coins:'1000'}),false);
});
test('C053 rejects a malformed or duplicated expanded offer',()=>{
 const offers=Array.from({length:9},(_,i)=>offer(i+1));
 const bad=offers.map(x=>({...x}));
 bad[4].price=0;
 assert.equal(evaluateCatalog({coins:1000,purchase_enabled:true,equipment_offers:bad}),false);
 bad[4]=offer(1);
 assert.equal(evaluateCatalog({coins:1000,purchase_enabled:true,equipment_offers:bad}),false);
});
test('Shipped G009 preview remains immutable closed on Product pages',()=>{
 assert.equal(source.includes('if (G009_SHOP_BROWSE_PREVIEW_ONLY) return false;'),true);
 assert(source.includes('const G009_SHOP_BROWSE_PREVIEW_ONLY = true;'));
});
