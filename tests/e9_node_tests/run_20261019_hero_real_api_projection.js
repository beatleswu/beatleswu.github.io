// Bridge REAL Flask response envelopes from a disposable native PostgreSQL
// test into the exact shipped Hero A028 JavaScript renderer. No production I/O.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
assert.equal(data?.presentation?.contract_version, 'PLAYER_PRESENTATION_API_V1');
const source = fs.readFileSync(path.join(root,'hero.html'),'utf8');
const from = source.indexOf('// ── A028 Player Presentation read-only adoption');
const body = source.indexOf('\n',from)+1;
const to = source.indexOf('// ── End A028 Player Presentation read-only adoption',body);
assert(from>=0&&body>from&&to>body,'hero A028 source present');
const actual = source.slice(body,to);
assert.match(actual,/progression\.rank_xp/);
const elements = new Map();
for(const name of ['char-name','badge-lv','badge-go','char-xp','char-xp-bar',
  'char-xp-pct','hero-overview-name','hero-overview-rank','hero-overview-xp'])
  elements.set(name,{textContent:'',style:{}});
const ctx = {
  console:{warn(){}},
  document:{getElementById(id){return elements.get(id)??null;}},
  I18n:{getLang(){return 'en';},t(){return '';}},
  fetch:async url=>{
    assert.equal(url,'/api/player/presentation');
    return {ok:true,status:200,json:async()=>data.presentation};
  },
};
vm.runInNewContext(actual + `
this.__render = {loadPlayerPresentationSnapshot,a028HeroOverviewView,
  a028HeroXpPresentation,a028ApplyPlayerPresentationSafeFields};`,ctx,
{filename:'hero.html#a028'});
(async()=>{
 const snapshot = await ctx.__render.loadPlayerPresentationSnapshot();
 assert(snapshot,'real player envelope must pass client normalization');
 const {profile,presentation} = data;
 const expected = presentation.progression;
 assert.equal(snapshot.progression.xp,expected.xp);
 assert.equal(snapshot.progression.rank_xp,expected.rank_xp);
 const model = ctx.__render.a028HeroOverviewView(profile);
 assert.equal(model.xp,expected.xp);
 const applied = ctx.__render.a028ApplyPlayerPresentationSafeFields(snapshot,profile);
 assert.equal(applied,true);
 const pct = expected.level===100 ? 100 :
   Math.round(expected.rank_xp/profile.xp_next*100);
 const actualBar=elements.get('char-xp-bar').style.width;
 assert.equal(actualBar,pct+'%','real XP bar must reflect within-level, not cumulative XP');
 const label=elements.get('char-xp').textContent;
 assert(label.includes(expected.xp.toLocaleString('en-US')),'display total must match server');
 if(expected.level!==100) assert(label.includes(
   expected.rank_xp.toLocaleString('en-US')+' / '+profile.xp_next.toLocaleString('en-US')+' XP'));
 if(expected.xp !== expected.rank_xp)
   assert(!label.startsWith(expected.xp+' /'),'cumulative XP may not be numerator of level ratio');
 const stale = ctx.__render.a028HeroOverviewView({
   ...profile,total_xp:Number(profile.total_xp)+1,
 });
 assert.equal(stale.xpNext,null,'stale cross-API scale must not be trusted');
 const staleModel = ctx.__render.a028HeroXpPresentation(stale);
 assert.equal(staleModel.pct,null);
 console.log(JSON.stringify({
   verdict:'REAL_NATIVE_PG_API_TO_SHIPPED_HERO_VIEW_PASS',
   total_xp:expected.xp,
   rank_xp:expected.rank_xp,
   level:expected.level,
   level_xp_needed:profile.xp_next,
   xp_bar_percent:pct,
   stale_fails_closed:true,
   production_session:false,
   real_iPad:false,
 }));
})().catch(err=>{console.error(err.stack||String(err));process.exitCode=1});
