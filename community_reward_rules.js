/**
 * community_reward_rules.js — Phase 4B leaderboard reward rules panel
 * for the Community Leaderboard page.
 *
 * Self-contained: builds its own modal DOM/CSS and wires the
 * "Reward Rules" button (#reward-rules-btn). Fetches structured rules
 * data from /api/community/leaderboard/reward-rules and localizes
 * every label/value through window.I18n.t(...) -- this file never
 * hardcodes Chinese or English display copy, and never fabricates a
 * reward amount or threshold: every number shown comes straight from
 * the API response.
 */
(function () {
    const RULES_ENDPOINT = '/api/community/leaderboard/reward-rules';

    const RANK_BAND_ORDER = ['top1', 'top3', 'top10', 'top25', 'top50'];
    const RANK_RANGE_KEYS = {
        top1: 'communityRewards.rules.rankRange.top1',
        top3: 'communityRewards.rules.rankRange.top3',
        top10: 'communityRewards.rules.rankRange.top10',
        top25: 'communityRewards.rules.rankRange.top25',
        top50: 'communityRewards.rules.rankRange.top50',
    };
    const ITEM_ICONS = { small_xp_potion: '🧪', xp_potion: '🧪' };
    const ITEM_LABEL_KEYS = {
        small_xp_potion: 'communityRewards.reward.item.small_xp_potion',
        xp_potion: 'communityRewards.reward.item.xp_potion',
    };
    const BADGE_LABEL_KEYS = {
        badge_lb_weekly_1: 'communityRewards.reward.badge.badge_lb_weekly_1',
    };

    function esc(s) {
        return String(s).replace(/[&<>"']/g, (c) => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] || c
        ));
    }

    function tr(key) {
        if (window.I18n && typeof window.I18n.t === 'function') return window.I18n.t(key);
        return key;
    }

    function formatReward(reward) {
        if (reward.type === 'coins') {
            return `🪙 ${tr('communityRewards.reward.coins')} +${reward.amount}`;
        }
        if (reward.type === 'item') {
            const icon = ITEM_ICONS[reward.key] || '🧪';
            const labelKey = ITEM_LABEL_KEYS[reward.key];
            const label = labelKey ? tr(labelKey) : tr('communityRewards.reward.unsupported');
            return `${icon} ${label} ×${reward.quantity}`;
        }
        if (reward.type === 'badge') {
            const labelKey = BADGE_LABEL_KEYS[reward.key];
            const label = labelKey ? tr(labelKey) : tr('communityRewards.reward.unsupported');
            return `🏅 ${label} ×1`;
        }
        return `❓ ${tr('communityRewards.reward.unsupported')}`;
    }

    function rankRangeLabel(band) {
        const key = RANK_RANGE_KEYS[band.key];
        return key ? tr(key) : `${band.rank_min}-${band.rank_max}`;
    }

    const STYLE = `
.crr-rules-btn{display:inline-flex;align-items:center;gap:6px;padding:6px 14px;border-radius:999px;
  border:1px solid #e8d4a8;background:#fffaf0;color:#6b5740;font-size:13px;font-weight:600;
  cursor:pointer;font-family:inherit;transition:background .15s;margin-top:6px;}
.crr-rules-btn:hover{background:#f4e8d0;}
.crr-rules-ov{position:fixed;inset:0;background:rgba(28,20,9,.55);display:none;
  align-items:center;justify-content:center;z-index:9998;padding:20px;}
.crr-rules-ov.crr-open{display:flex;}
.crr-rules-modal{background:#fffaf0;border-radius:18px;padding:24px 22px;max-width:520px;width:100%;
  max-height:85vh;overflow-y:auto;box-shadow:0 8px 40px rgba(28,20,9,.3);border:1px solid #e8d4a8;
  font-family:inherit;color:#1c1409;text-align:left;}
.crr-rules-title{font-size:19px;font-weight:700;margin-bottom:14px;}
.crr-rules-section{margin-bottom:16px;}
.crr-rules-heading{font-size:13px;font-weight:700;color:#8a6d3f;margin-bottom:6px;
  text-transform:uppercase;letter-spacing:.5px;}
.crr-rules-text{font-size:14px;line-height:1.6;color:#3d2f1a;margin-bottom:4px;}
.crr-rules-score{font-weight:700;color:#b45309;}
.crr-rules-table{width:100%;border-collapse:collapse;font-size:13px;}
.crr-rules-table th{text-align:left;padding:6px 8px;color:#8a6d3f;font-size:11px;
  text-transform:uppercase;border-bottom:1px solid #e8d4a8;}
.crr-rules-table td{padding:8px;border-bottom:1px solid #f0e6d2;vertical-align:top;}
.crr-rules-table tr:last-child td{border-bottom:none;}
.crr-rules-reward-line{display:block;}
.crr-rules-close{margin-top:10px;width:100%;padding:11px;border:none;border-radius:12px;
  background:#2f9e5e;color:#fff;font-size:14px;font-weight:600;cursor:pointer;font-family:inherit;}
.crr-rules-close:hover{background:#227a47;}
@media (max-width:480px){
  .crr-rules-modal{padding:18px 16px;max-height:90vh;}
  .crr-rules-table{font-size:12px;}
}
`;

    let styleInjected = false;
    let overlayEl = null;
    let cachedRules = null;

    function ensureStyle() {
        if (styleInjected) return;
        const styleEl = document.createElement('style');
        styleEl.textContent = STYLE;
        document.head.appendChild(styleEl);
        styleInjected = true;
    }

    function ensureModal() {
        if (overlayEl) return;
        ensureStyle();
        overlayEl = document.createElement('div');
        overlayEl.className = 'crr-rules-ov';
        overlayEl.innerHTML = `
      <div class="crr-rules-modal" role="dialog" aria-modal="true">
        <div class="crr-rules-title" data-crr="title"></div>

        <div class="crr-rules-section">
          <div class="crr-rules-heading" data-crr="periodHeading"></div>
          <div class="crr-rules-text" data-crr="periodText"></div>
        </div>

        <div class="crr-rules-section">
          <div class="crr-rules-heading" data-crr="eligibilityHeading"></div>
          <div class="crr-rules-text">1. <span data-crr="rankRequirement"></span></div>
          <div class="crr-rules-text">2. <span class="crr-rules-score" data-crr="minimumScore"></span></div>
          <div class="crr-rules-text" data-crr="belowThreshold"></div>
        </div>

        <div class="crr-rules-section">
          <div class="crr-rules-heading" data-crr="rewardsHeading"></div>
          <table class="crr-rules-table">
            <thead>
              <tr>
                <th data-crr="colRank"></th>
                <th data-crr="colRewards"></th>
                <th data-crr="colRequirement"></th>
              </tr>
            </thead>
            <tbody data-crr="rewardsBody"></tbody>
          </table>
        </div>

        <div class="crr-rules-section">
          <div class="crr-rules-heading" data-crr="deliveryHeading"></div>
          <div class="crr-rules-text" data-crr="deliveryAutomatic"></div>
          <div class="crr-rules-text" data-crr="deliveryNotification"></div>
        </div>

        <div class="crr-rules-section">
          <div class="crr-rules-heading" data-crr="notesHeading"></div>
          <div class="crr-rules-text">・<span data-crr="notesBelowThreshold"></span></div>
          <div class="crr-rules-text">・<span data-crr="notesCoinCapBypass"></span></div>
          <div class="crr-rules-text">・<span data-crr="notesMayChange"></span></div>
        </div>

        <button type="button" class="crr-rules-close" data-crr="closeButton"></button>
      </div>`;
        document.body.appendChild(overlayEl);
        overlayEl.addEventListener('click', (e) => {
            if (e.target === overlayEl) hide();
        });
        overlayEl.querySelector('[data-crr="closeButton"]').addEventListener('click', hide);
    }

    function hide() {
        if (overlayEl) overlayEl.classList.remove('crr-open');
    }

    function render(weekly) {
        ensureModal();
        const q = (sel) => overlayEl.querySelector(sel);
        q('[data-crr="title"]').textContent = tr('communityRewards.rules.title');
        q('[data-crr="periodHeading"]').textContent = tr('communityRewards.rules.period.heading');
        q('[data-crr="periodText"]').textContent = tr('communityRewards.rules.period.weekly');
        q('[data-crr="eligibilityHeading"]').textContent = tr('communityRewards.rules.eligibility.heading');
        q('[data-crr="rankRequirement"]').textContent = tr('communityRewards.rules.eligibility.rankRequirement');
        q('[data-crr="minimumScore"]').textContent =
            tr('communityRewards.rules.eligibility.minimumScore').replace('{score}', weekly.minimum_score);
        q('[data-crr="belowThreshold"]').textContent = tr('communityRewards.rules.eligibility.belowThreshold');
        q('[data-crr="rewardsHeading"]').textContent = tr('communityRewards.rules.rewards.heading');
        q('[data-crr="colRank"]').textContent = tr('communityRewards.rules.table.rank');
        q('[data-crr="colRewards"]').textContent = tr('communityRewards.rules.table.rewards');
        q('[data-crr="colRequirement"]').textContent = tr('communityRewards.rules.table.requirement');
        q('[data-crr="deliveryHeading"]').textContent = tr('communityRewards.rules.delivery.heading');
        q('[data-crr="deliveryAutomatic"]').textContent = tr('communityRewards.rules.delivery.automatic');
        q('[data-crr="deliveryNotification"]').textContent = tr('communityRewards.rules.delivery.notification');
        q('[data-crr="notesHeading"]').textContent = tr('communityRewards.rules.notes.heading');
        q('[data-crr="notesBelowThreshold"]').textContent = tr('communityRewards.rules.notes.belowThreshold');
        q('[data-crr="notesCoinCapBypass"]').textContent = tr('communityRewards.rules.notes.coinCapBypass');
        q('[data-crr="notesMayChange"]').textContent = tr('communityRewards.rules.notes.mayChange');
        q('[data-crr="closeButton"]').textContent = tr('communityRewards.rules.closeButton');

        const bandsByKey = {};
        (weekly.rank_bands || []).forEach((b) => { bandsByKey[b.key] = b; });
        const rowsHtml = RANK_BAND_ORDER
            .filter((key) => bandsByKey[key])
            .map((key) => {
                const band = bandsByKey[key];
                const rewardsHtml = (band.rewards || [])
                    .map((r) => `<span class="crr-rules-reward-line">${esc(formatReward(r))}</span>`)
                    .join('');
                return `<tr>
                  <td>${esc(rankRangeLabel(band))}</td>
                  <td>${rewardsHtml}</td>
                  <td>${esc(tr('communityRewards.rules.top50Requirement'))}</td>
                </tr>`;
            })
            .join('');
        q('[data-crr="rewardsBody"]').innerHTML = rowsHtml;

        overlayEl.classList.add('crr-open');
    }

    async function show() {
        if (cachedRules) { render(cachedRules); return; }
        try {
            const res = await fetch(RULES_ENDPOINT, { credentials: 'same-origin' });
            if (!res.ok) return;
            const data = await res.json();
            if (!data || data.ok !== true || !data.rules || !data.rules.weekly) return;
            cachedRules = data.rules.weekly;
            render(cachedRules);
        } catch (_err) {
            // Rules panel is informational only -- never block leaderboard usage.
        }
    }

    function init() {
        const btn = document.getElementById('reward-rules-btn');
        if (btn) btn.addEventListener('click', show);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.CommunityRewardRules = { show };
})();
