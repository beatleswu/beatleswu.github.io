/**
 * srs.js  ─  SRS + Badge + 怪物 + 每日任務 前端模組
 */
const SRS = (() => {
    const GRADE = { AGAIN: 0, GOOD: 3, EASY: 5 };

    const DIFFICULTY_ORDER = [
        '30k','29k','28k','27k','26k','25k','24k','23k','22k','21k',
        '20k','19k','18k','17k','16k','15k','14k','13k','12k','11k',
        '10k','9k','8k','7k','6k','5k','4k','3k','2k','1k',
        '1d','2d','3d','4d','5d','6d','7d','8d','9d'
    ];

    const MONSTER_AVATARS = {
        caterpillar:'🐛', bee:'🐝', turtle:'🐢', rabbit:'🐇', raccoon:'🦝',
        wolf:'🐺', fox:'🦊', goblin:'👺', golem:'🗿', dragon:'🐉',
    };
    const QUEST_COLORS = {
        amber:  { bg:'#fffbeb', fill:'#d97706', text:'#92400e' },
        teal:   { bg:'#f0fdfa', fill:'#0d9488', text:'#134e4a' },
        purple: { bg:'#f5f3ff', fill:'#7c3aed', text:'#4c1d95' },
        red:    { bg:'#fff1f2', fill:'#dc2626', text:'#7f1d1d' },
    };

    let _dueSet    = null;
    let _seenSet   = null;   // 所有曾作答過的 question_id
    let _allCards  = {};
    let _badgeDefs = [];
    let _earned    = {};
    let _onBadge   = null;
    let _onMonster = null;  // callback(monsterData) 每次答題後呼叫
    let _onQuest   = null;  // callback(questList)   任務進度更新後呼叫

    // ── 初始化 ────────────────────────────────────────────────
    async function init(onBadgeCallback, onMonsterCallback, onQuestCallback) {
        _onBadge   = onBadgeCallback   || null;
        _onMonster = onMonsterCallback || null;
        _onQuest   = onQuestCallback   || null;
        const [dueData, allCards, defsRes, earnedRes] = await Promise.all([
            fetch('/api/srs/due', {credentials:'include'}).then(r => r.json()),
            fetch('/api/srs/all', {credentials:'include'}).then(r => r.json()),
            fetch('/api/badges/definitions', {credentials:'include'}).then(r => r.json()),
            fetch('/api/badges/earned', {credentials:'include'}).then(r => r.json()),
        ]);
        _dueSet  = new Set(dueData.due.map(d => d.question_id));
        _seenSet = new Set(allCards.map(c => c.question_id));
        allCards.forEach(c => { _allCards[c.question_id] = c; });
        dueData.due.forEach(d => { _allCards[d.question_id] = { ...(_allCards[d.question_id] || {}), ...d }; });
        _badgeDefs = defsRes;
        earnedRes.forEach(e => { _earned[e.badge_id] = e.earned_at; });
        return { dueData, defs: _badgeDefs, earned: _earned };
    }

    function isDue(qid)  { return !_dueSet  || _dueSet.has(qid); }
    function isSeen(qid) { return  _seenSet != null && _seenSet.has(qid); }
    function markSeen(qid) { if (_seenSet) _seenSet.add(qid); }  // 答題後即時更新
    function getCard(qid) { return _allCards[qid] || null; }
    function getBadgeDef(bid) { return _badgeDefs.find(b => b.id === bid) || null; }
    function isEarned(bid) { return !!_earned[bid]; }
    function allDefs() { return _badgeDefs; }
    function allEarned() { return _earned; }

    // ── localStorage 備份 ─────────────────────────────────────
    function _lsKey() { return 'go_badges_earned'; }
    function _lsLoad() {
        try { return JSON.parse(localStorage.getItem(_lsKey()) || '{}'); } catch { return {}; }
    }
    function _lsSave(obj) {
        try { localStorage.setItem(_lsKey(), JSON.stringify(obj)); } catch {}
    }
    function _lsMerge(newBadges) {
        const ls = _lsLoad();
        newBadges.forEach(bid => { if (!ls[bid]) ls[bid] = new Date().toISOString(); });
        _lsSave(ls);
    }

    // ── 送出評分 ──────────────────────────────────────────────
    async function review(qid, grade, unitName, unitDone, metadata = {}) {
        const res = await fetch('/api/srs/review', {
            credentials: 'include',
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question_id: qid, grade,
                unit_name: unitName || null,
                unit_done: !!unitDone,
                response_ms: metadata.response_ms ?? null,
                source_context: metadata.source_context || 'practice',
                training_set_id: metadata.training_set_id ?? null,
                is_scaffolding: !!metadata.is_scaffolding
            })
        });
        const data = await res.json();
        if (!res.ok && !['premium_required', 'daily_limit'].includes(data.error)) {
            throw new Error(data.error || `HTTP ${res.status}`);
        }
        if (data.ok) {
            _allCards[qid] = { ...(_allCards[qid]||{}), ...data, question_id: qid };
            if (grade >= 3 && _dueSet) _dueSet.delete(qid);

            // 處理新獎章
            if (data.new_badges && data.new_badges.length) {
                _lsMerge(data.new_badges);
                data.new_badges.forEach(bid => {
                    _earned[bid] = new Date().toISOString();
                    if (_onBadge) {
                        const def = getBadgeDef(bid);
                        if (def) _onBadge(def);
                    }
                });
                fetch('/api/badges/seen', {
                    credentials: 'include',
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ids: data.new_badges })
                });
            }

            // 怪物回調
            if (data.monster && _onMonster) {
                _onMonster(data.monster);
            }

            // 任務回調
            if (data.quest_updates && _onQuest) {
                _onQuest(data.quest_updates);
            }
        }
        return data;
    }

    // ── 載入今日任務 ──────────────────────────────────────────
    async function loadQuests() {
        const res = await fetch('/api/quests/today', {credentials:'include'}).then(r => r.json());
        return res.quests || [];
    }

    // ── 回報單元進度（答對時呼叫） ────────────────────────────
    async function reportUnitProgress(qid, unitName) {
        if (!unitName) return { unit_complete: false };
        try {
            const res = await fetch('/api/unit-progress', {
                credentials: 'include',
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question_id: qid, unit: unitName })
            });
            if (!res.ok) return { unit_complete: false };
            return res.json();
        } catch (e) {
            return { unit_complete: false };
        }
    }

    // ── UI 輔助 ───────────────────────────────────────────────
    function diffBadge(diff) {
        if (diff === '' || diff === null || diff === undefined) return '';
        // difficulty 可能是 kyu/dan 字串（'30k'/'1d'）或 KataGo 整數（1-10）
        const s = String(diff);
        if (!s || s === '0') return '';
        const isKyu = s.endsWith('k');
        const isInt = /^\d+$/.test(s);   // KataGo 1-10 整數難度
        const bg = isKyu ? '#3b82f6' : isInt ? '#7c3aed' : '#f59e0b';
        return `<span style="background:${bg};color:#fff;font-size:10px;padding:1px 7px;border-radius:4px;font-weight:bold;letter-spacing:.5px">${s}</span>`;
    }

    function intervalLabel(card) {
        const en = window.I18n && window.I18n.getLang && window.I18n.getLang() === 'en';
        if (!card || card.interval === 0) return en ? 'New' : '新題';
        if (card.interval === 1) return en ? 'Review tomorrow' : '明天複習';
        return en ? `Review in ${card.interval} days` : `${card.interval} 天後複習`;
    }

    function badgeHtml(def, earned) {
        const en = window.I18n && window.I18n.getLang && window.I18n.getLang() === 'en';
        const name = en ? (def.name_en || def.name || 'Badge') : def.name;
        const desc = en ? (def.desc_en || def.desc || '') : def.desc;
        const cls   = earned ? 'badge-item earned' : 'badge-item locked';
        const title = earned ? `${name}: ${desc}` : `${en ? '(Locked)' : '（未解鎖）'} ${desc}`;
        return `<div class="${cls}" title="${title}"><div class="badge-medallion"><span class="badge-emoji">${def.icon}</span></div><div class="badge-label">${name}</div></div>`;
    }

    // ── 怪物面板 HTML ─────────────────────────────────────────
    function monsterHtml(monster) {
        if (!monster) return '';
        const avatar = monster.defeated ? '💀' : (MONSTER_AVATARS[monster.type] || '👾');
        const pct    = Math.round(monster.hp / monster.max_hp * 100);
        const barClr = pct > 50 ? '#dc2626' : pct > 25 ? '#d97706' : '#16a34a';
        return `
          <div style="display:flex;align-items:center;gap:10px;padding:8px 10px;
                      background:var(--cream2,#f3ede3);border-radius:10px;">
            <span style="font-size:24px;line-height:1">${avatar}</span>
            <div style="flex:1;min-width:0">
              <div style="font-size:12px;font-weight:600;color:var(--ink,#1c1409)">${window.I18n && window.I18n.getLang() === 'en' ? (monster.name_en || 'Training Monster') : monster.name}</div>
              <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
                <div style="flex:1;height:5px;background:var(--cream3,#ede4d4);border-radius:5px;overflow:hidden">
                  <div style="width:${pct}%;height:100%;background:${barClr};border-radius:5px;transition:width .4s"></div>
                </div>
                <span style="font-size:10px;font-family:monospace;color:var(--ink3,#6b5740);white-space:nowrap">
                  HP ${monster.hp}/${monster.max_hp}
                </span>
              </div>
            </div>
          </div>`;
    }

    // ── 任務列表 HTML ─────────────────────────────────────────
    function questListHtml(quests) {
        if (!quests || !quests.length) return '';
        return quests.map(q => {
            const en = window.I18n && window.I18n.getLang && window.I18n.getLang() === 'en';
            const questName = en ? (q.name_en || q.name || 'Quest') : q.name;
            const c   = QUEST_COLORS[q.color] || QUEST_COLORS.amber;
            const pct = Math.min(100, Math.round(q.progress / q.target * 100));
            const locked = q.bonus && q.progress === 0 && !q.completed;
            return `
              <div style="display:flex;align-items:center;gap:8px;padding:7px 9px;
                          border-radius:10px;opacity:${locked?'.45':'1'};
                          background:${q.completed?'#f0fdfa':'var(--cream2,#f3ede3)'};
                          border:1px solid ${q.completed?'#99f6e4':'transparent'}">
                <div style="width:26px;height:26px;border-radius:8px;flex-shrink:0;
                            background:${c.bg};display:flex;align-items:center;
                            justify-content:center;font-size:14px">
                  ${locked ? '🔒' : q.icon}
                </div>
                <div style="flex:1;min-width:0">
                  <div style="display:flex;justify-content:space-between;align-items:center">
                    <span style="font-size:11px;font-weight:600;color:var(--ink,#1c1409)">${questName}</span>
                    <span style="font-size:10px;font-family:monospace;color:${c.text};margin-left:6px;flex-shrink:0">
                      ${q.completed ? '✓' : `${q.progress}/${q.target}`}
                    </span>
                  </div>
                  <div style="height:3px;background:var(--cream3,#ede4d4);border-radius:3px;margin-top:5px;overflow:hidden">
                    <div style="width:${pct}%;height:100%;background:${c.fill};border-radius:3px;transition:width .4s"></div>
                  </div>
                </div>
                <div style="font-size:10px;font-family:monospace;color:#16a34a;flex-shrink:0">+${q.xp}</div>
              </div>`;
        }).join('');
    }

    return {
        GRADE, DIFFICULTY_ORDER, MONSTER_AVATARS, QUEST_COLORS,
        init, isDue, isSeen, markSeen, getCard, getBadgeDef, isEarned, allDefs, allEarned,
        review, loadQuests, reportUnitProgress,
        diffBadge, intervalLabel, badgeHtml, monsterHtml, questListHtml
    };
})();
