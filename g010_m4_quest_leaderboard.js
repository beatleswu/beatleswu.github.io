/* G010 M4: Quest V2 + ranking real player UI. Server is sole reward authority.
   Missing/disabled V2 means no panel. No automatic grants, only a direct
   explicit click with durable browser operation identity for retry safety. */
(() => {
  'use strict';
  const shell = document.getElementById('g010-m4-quest-panel');
  if (!shell) return;
  const grid = document.getElementById('g010-m4-quest-grid');
  const status = document.getElementById('g010-m4-quest-status');
  const totals = document.getElementById('g010-m4-quest-totals');
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
  const storePrefix = 'g010:m4:quest:claim:';
  const pending = new Set();
  let current = null;
  const locale = () => (typeof I18n !== 'undefined' && I18n.getLang?.() === 'en');
  const label = (zh, en) => locale() ? en : zh;
  const int = n => Number.isSafeInteger(n) && n >= 0 ? n : 0;
  const questLabel = q => {
    const names = {
      'daily:streak_correct':label('連續答對任務','Correct-answer streak'),
      'daily:kill_monsters':label('擊敗怪物任務','Monster defeats'),
    };
    return names[q.quest_id] || q.display_metadata_key || q.quest_id;
  };
  const operationStorageKey = q => storePrefix + q.quest_id + ':' + q.period_key;
  const operationId = q => {
    const key = operationStorageKey(q);
    try {
      const existing = sessionStorage.getItem(key);
      if (existing && /^[a-zA-Z0-9_.:-]{8,128}$/.test(existing)) return existing;
    } catch {}
    const created = (crypto?.randomUUID?.() || 'g010-m4-'+Date.now()+'-'+Math.random().toString(16).slice(2));
    try { sessionStorage.setItem(key, created); } catch {}
    return created;
  };
  const clearOperation = q => {
    try { sessionStorage.removeItem(operationStorageKey(q)); } catch {}
  };
  function render() {
    if (!current || !Array.isArray(current.quests)) return;
    const quests = current.quests.filter(q => q.enabled === true && [
      'Daily','Weekly','Adventure','Chronicles'
    ].includes(q.tab));
    const claimable = quests.filter(q=>q.claimable === true && q.claimed !== true).length;
    const claimed = quests.filter(q=>q.claimed === true).length;
    totals.textContent = label(
      '可領 '+claimable+' · 已領 '+claimed+' · 以伺服器進度為準',
      claimable+' claimable · '+claimed+' claimed · Server-verified',
    );
    const selected = quests.filter(q => q.progress > 0 || q.claimed || q.claimable);
    grid.innerHTML = selected.map(q => {
      const progress = Math.min(int(q.progress),int(q.target));
      const target = int(q.target);
      const reward = q.reward_profile || {};
      const pieces = [];
      if (Number.isFinite(reward.xp) && reward.xp > 0) pieces.push('+'+reward.xp+' XP');
      if (Number.isFinite(reward.coins) && reward.coins > 0) pieces.push('+'+reward.coins+' Coins');
      if (Array.isArray(reward.items)) {
        for(const item of reward.items) {
          if (item.item_id && int(item.quantity)>0) pieces.push(esc(item.item_id)+' ×'+int(item.quantity));
        }
      }
      const claimable = q.claimable === true && q.claimed !== true;
      const processing = pending.has(q.quest_id+':'+q.period_key);
      return '<article class="g010-m4-quest-card" data-m4-quest="'+esc(q.quest_id)+'"'
        +' data-status="'+esc(q.status)+'" data-claimable="'+String(claimable)+'">'
        +'<strong>'+esc(questLabel(q))+'</strong>'
        +'<span>'+progress+' / '+target+'</span>'
        +'<progress max="'+Math.max(1,target)+'" value="'+progress+'"></progress>'
        +'<small>'+pieces.join(' · ')+'</small>'
        +(q.claimed ? '<span class="g010-m4-done">'+label('已領取','Claimed')+'</span>'
          : claimable
           ? '<button type="button" data-m4-claim="'+esc(q.quest_id)+'"'
             +' '+(processing?'disabled aria-busy="true"':'')+'>'
             +label(processing?'領取確認中…':'領取獎勵',processing?'Confirming…':'Claim reward')+'</button>'
           : '<span class="g010-m4-pending">'+label('尚未達成','Not yet complete')+'</span>')
        +'</article>';
    }).join('');
    if (!selected.length) {
      grid.innerHTML = '<p>'+label('尚無任務進度；完成冒險或修行後會在此更新。',
        'No progress yet. Complete adventures or practice to update this board.')+'</p>';
    }
  }
  async function refresh() {
    let response;
    try {
      response = await fetch('/api/quests/v2',{credentials:'include',cache:'no-store'});
      if (response.status === 404) { shell.hidden = true; current = null; return; }
      if (response.status === 401) { shell.hidden = true; current = null; return; }
      const json = await response.json();
      if (!response.ok || json?.enabled !== true || !Array.isArray(json.quests)) {
        shell.hidden = true; current = null; return;
      }
      current = json;
      shell.hidden = false;
      status.textContent = label('任務進度由伺服器判定，領獎後只會更新角色總 XP；週月榜仍按答對題數計算。',
        'Server-judged quests. Claim XP updates lifetime XP, not weekly/monthly correct-answer counts.');
      render();
    } catch {
      shell.hidden = true; current = null;
    }
  }
  async function claim(q) {
    if (!q || q.claimable !== true || q.claimed === true) return;
    const key = q.quest_id+':'+q.period_key;
    if (pending.has(key)) return;
    pending.add(key);
    render();
    const op = operationId(q);
    try {
      const res = await fetch('/api/quests/v2/claim',{
        method:'POST',credentials:'include',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          quest_id:q.quest_id,period_key:q.period_key,claim_operation_id:op,
        }),
      });
      const json=await res.json().catch(()=>({}));
      if (!res.ok || json.ok !== true) throw new Error(json.error || 'claim_unavailable');
      clearOperation(q);
      status.textContent=label('獎勵已由伺服器確認入帳。','Reward confirmed by server.');
      await refresh();
      // The leaderboard endpoint, never the client, computes all six boards.
      // Existing method redraws both active board and the bounty overview.
      if (typeof loadLeaderboard === 'function') await loadLeaderboard();
    } catch {
      status.textContent=label(
        '無法確認領獎結果；重試會沿用同一筆交易，不會要求伺服器重複發獎。',
        'Unable to confirm claim; retry reuses the same operation identity.',
      );
    } finally {
      pending.delete(key);
      if (current) render();
    }
  }
  grid.addEventListener('click', e=>{
    const btn=e.target.closest('button[data-m4-claim]');
    if(!btn || btn.disabled || !current) return;
    const q=current.quests.find(x=>x.quest_id===btn.dataset.m4Claim);
    if(q) claim(q);
  });
  document.getElementById('g010-m4-quest-refresh')?.addEventListener('click',refresh);
  document.addEventListener('DOMContentLoaded',refresh);
  window.addEventListener('focus',()=>{
    if (!shell.hidden) refresh();
  });
  window.G010M4QuestPanel={refresh};
})();
