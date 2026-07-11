/**
 * community_reward_notifications.js — Phase 4A login-time reward
 * notification for Community Leaderboard Rewards.
 *
 * Self-contained: builds its own modal DOM and injects its own <style>,
 * so any page can pick it up with a single <script> tag plus one call to
 * CommunityRewardNotifications.init() (or none at all -- it also
 * auto-runs on DOMContentLoaded). Never blocks normal site usage if the
 * fetch fails or the player isn't logged in -- it just does nothing.
 *
 * All visible copy goes through window.I18n.t(...) -- this file never
 * hardcodes a Chinese or English string for anything the player reads.
 */
(function () {
    const NOTIFICATIONS_ENDPOINT = '/api/community/leaderboard/reward-notifications';
    const ACK_ENDPOINT_PREFIX = '/api/community/leaderboard/reward-notifications/';
    const ACK_ENDPOINT_SUFFIX = '/ack';

    const BOARD_LABEL_KEYS = {
        weekly: 'communityRewards.board.weekly',
        monthly: 'communityRewards.board.monthly',
    };
    const RANK_BAND_LABEL_KEYS = {
        top1: 'communityRewards.rankBand.top1',
        top3: 'communityRewards.rankBand.top3',
        top10: 'communityRewards.rankBand.top10',
        top25: 'communityRewards.rankBand.top25',
        top50: 'communityRewards.rankBand.top50',
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
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
        ));
    }

    function tr(key) {
        // Falls back to the raw key if I18n isn't loaded yet -- this
        // should never happen in practice (i18n.js loads first on every
        // page this script is included on), but must never throw.
        if (window.I18n && typeof window.I18n.t === 'function') return window.I18n.t(key);
        return key;
    }

    function formatReason(notification) {
        const boardKey = BOARD_LABEL_KEYS[notification.board];
        const board = boardKey ? tr(boardKey) : notification.board;
        const bandKey = RANK_BAND_LABEL_KEYS[notification.rank_band];
        const band = bandKey ? tr(bandKey) : notification.rank_band;
        return `${notification.period_key} ${board}・${band}`;
    }

    function formatRewardLine(reward) {
        if (reward.type === 'coins') {
            return `🪙 ${tr('communityRewards.reward.coins')} +${reward.amount}`;
        }
        if (reward.type === 'item') {
            const icon = ITEM_ICONS[reward.key] || '🧪';
            const labelKey = ITEM_LABEL_KEYS[reward.key];
            const label = labelKey ? tr(labelKey) : tr('communityRewards.reward.unsupported');
            if (!labelKey) console.warn('[community_reward_notifications] unknown item key', reward.key);
            return `${icon} ${label} ×${reward.quantity}`;
        }
        if (reward.type === 'badge') {
            const labelKey = BADGE_LABEL_KEYS[reward.key];
            const label = labelKey ? tr(labelKey) : tr('communityRewards.reward.unsupported');
            if (!labelKey) console.warn('[community_reward_notifications] unknown badge key', reward.key);
            return `🏅 ${label}`;
        }
        console.warn('[community_reward_notifications] unsupported reward type', reward.type);
        return `❓ ${tr('communityRewards.reward.unsupported')}`;
    }

    const STYLE = `
.crn-modal-ov{position:fixed;inset:0;background:rgba(28,20,9,.5);display:none;
  align-items:center;justify-content:center;z-index:9999;padding:20px;}
.crn-modal-ov.crn-open{display:flex;}
.crn-modal{background:linear-gradient(180deg,#fffaf0,#fbf0d9);border-radius:20px;padding:26px 24px 22px;
  max-width:380px;width:100%;text-align:center;box-shadow:0 8px 40px rgba(28,20,9,.25);
  border:1px solid #e8d4a8;
  animation:crn-pop-in .22s cubic-bezier(.34,1.56,.64,1);font-family:inherit;color:#1c1409;}
@keyframes crn-pop-in{from{transform:scale(.85);opacity:0}to{transform:scale(1);opacity:1}}
.crn-chest{font-size:44px;line-height:1;margin-bottom:4px;}
.crn-modal-title{font-size:20px;font-weight:700;margin-bottom:2px;}
.crn-modal-subtitle{font-size:13px;color:#8a6d3f;font-weight:600;margin-bottom:14px;}
.crn-modal-section{margin-bottom:12px;text-align:left;}
.crn-modal-label{font-size:12px;color:#6b5740;margin-bottom:3px;font-weight:600;}
.crn-modal-reason{font-size:14px;color:#1c1409;}
.crn-modal-rewards{display:flex;flex-direction:column;gap:5px;}
.crn-reward-line{font-size:15px;background:#f4e8d0;border:1px solid #e8d4a8;border-radius:10px;
  padding:7px 11px;box-shadow:inset 0 1px 0 rgba(255,255,255,.6);}
.crn-modal-note{font-size:12px;color:#6b5740;line-height:1.5;margin:14px 0 18px;}
.crn-modal-btns{display:flex;gap:9px;}
.crn-modal-ack{flex:1;display:flex;align-items:center;justify-content:center;padding:12px;
  border:none;border-radius:12px;background:#2f9e5e;color:#fff;font-size:15px;font-weight:600;
  cursor:pointer;font-family:inherit;transition:background .15s;}
.crn-modal-ack:hover{background:#227a47;}
.crn-modal-ack:disabled{opacity:.5;cursor:not-allowed;}
@media (max-width:420px){
  .crn-modal{padding:20px 18px;max-width:100%;}
  .crn-modal-title{font-size:18px;}
  .crn-chest{font-size:38px;}
}
`;

    let styleInjected = false;
    let overlayEl = null;
    let queue = [];
    let acking = false;
    let lastSoundClaimId = null;

    // Phase 4A-1: short RPG-style "quest complete" sound when the
    // notification first appears. Reuses the site's existing synthesized
    // SFX engine (sound.js) -- no audio asset is added by this file.
    // Entirely decorative: if sound.js hasn't loaded, if the browser
    // blocks autoplay, or if the player has the existing global SFX mute
    // preference on, this silently does nothing. Never blocks the modal
    // or the acknowledgement flow.
    function playRewardSound() {
        try {
            if (typeof window.SFX === 'undefined' || typeof window.SFX.play !== 'function') return;
            if (window.SFX.muted) return;
            window.SFX.play('quest_complete');
        } catch (_err) {
            // Silent fallback -- sound is decorative only.
        }
    }

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
        overlayEl.className = 'crn-modal-ov';
        overlayEl.innerHTML = `
      <div class="crn-modal" role="dialog" aria-modal="true">
        <div class="crn-chest" aria-hidden="true">🎁</div>
        <div class="crn-modal-title">🎉 <span data-crn="questComplete"></span></div>
        <div class="crn-modal-subtitle" data-crn="weeklyReward"></div>
        <div class="crn-modal-section">
          <div class="crn-modal-label" data-crn="reasonLabel"></div>
          <div class="crn-modal-reason" data-crn="reasonValue"></div>
        </div>
        <div class="crn-modal-section">
          <div class="crn-modal-label" data-crn="rewardsReceived"></div>
          <div class="crn-modal-rewards" data-crn="rewardsValue"></div>
        </div>
        <div class="crn-modal-note" data-crn="alreadyAdded"></div>
        <div class="crn-modal-btns">
          <button type="button" class="crn-modal-ack" data-crn="collectButton"></button>
        </div>
      </div>`;
        document.body.appendChild(overlayEl);
    }

    function renderCurrent() {
        if (!queue.length) {
            if (overlayEl) overlayEl.classList.remove('crn-open');
            return;
        }
        ensureModal();
        const notification = queue[0];
        overlayEl.querySelector('.crn-chest').title = tr('communityRewards.visual.treasureChestAlt');
        overlayEl.querySelector('[data-crn="questComplete"]').textContent =
            tr('communityRewards.notification.questComplete');
        overlayEl.querySelector('[data-crn="weeklyReward"]').textContent =
            tr('communityRewards.notification.weeklyReward');
        overlayEl.querySelector('[data-crn="reasonLabel"]').textContent =
            tr('communityRewards.notification.reasonLabel');
        overlayEl.querySelector('[data-crn="reasonValue"]').textContent = formatReason(notification);
        overlayEl.querySelector('[data-crn="rewardsReceived"]').textContent =
            tr('communityRewards.notification.rewardsReceived');
        overlayEl.querySelector('[data-crn="rewardsValue"]').innerHTML =
            (notification.rewards || [])
                .map((r) => `<div class="crn-reward-line">${esc(formatRewardLine(r))}</div>`)
                .join('');
        overlayEl.querySelector('[data-crn="alreadyAdded"]').textContent =
            tr('communityRewards.notification.alreadyAdded');
        const collectButton = overlayEl.querySelector('[data-crn="collectButton"]');
        collectButton.textContent = tr('communityRewards.notification.collectButton');
        collectButton.disabled = false;
        collectButton.onclick = () => acknowledgeCurrent(notification.claim_id);
        overlayEl.classList.add('crn-open');
        if (lastSoundClaimId !== notification.claim_id) {
            lastSoundClaimId = notification.claim_id;
            playRewardSound();
        }
    }

    async function acknowledgeCurrent(claimId) {
        if (acking) return;
        acking = true;
        const ackButton = overlayEl && overlayEl.querySelector('[data-crn="collectButton"]');
        if (ackButton) ackButton.disabled = true;
        try {
            const res = await fetch(
                `${ACK_ENDPOINT_PREFIX}${encodeURIComponent(claimId)}${ACK_ENDPOINT_SUFFIX}`,
                { method: 'POST', credentials: 'same-origin' },
            );
            if (res.ok) {
                queue.shift();
            }
            // A non-ok ack response is left in the queue -- the button
            // re-enables below so the player can try again, and the
            // notification will simply reappear next load either way
            // (the button never grants or loses anything).
        } catch (_err) {
            // Network failure must never block normal site usage.
        } finally {
            acking = false;
            renderCurrent();
        }
    }

    async function init() {
        try {
            const res = await fetch(NOTIFICATIONS_ENDPOINT, { credentials: 'same-origin' });
            if (!res.ok) return; // not logged in, or a transient error -- do nothing
            const data = await res.json();
            if (!data || data.ok !== true || !Array.isArray(data.notifications)) return;
            if (!data.notifications.length) return;
            queue = data.notifications;
            renderCurrent();
        } catch (_err) {
            // API failure must never block normal site usage.
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.CommunityRewardNotifications = { init };
})();
