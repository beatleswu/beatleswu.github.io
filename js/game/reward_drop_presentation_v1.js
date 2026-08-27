/*
 * Generic Monster V1 reward presentation.
 *
 * This module is deliberately a consumer only.  It accepts an already
 * committed server result and narrows the two explicit Monster reward
 * channels that the current runtime exposes: `loot` for functional
 * Equipment and `appearance_loot` for pure cosmetics.  It never rolls,
 * grants, equips, consumes, prices, or infers a reward.
 */
(function (global) {
    'use strict';

    const CONTRACT_VERSION = 'GENERIC_MONSTER_REWARD_PRESENTATION_V1';
    const FUNCTIONAL_EQUIPMENT = 'FUNCTIONAL_EQUIPMENT';
    const PURE_COSMETIC = 'PURE_COSMETIC';
    const NO_DROP = 'NO_DROP';
    const UNAVAILABLE = 'UNAVAILABLE';
    const SKIPPED = 'SKIPPED';
    const COMMITTED_STATUSES = new Set(['COMMITTED', 'SETTLED', 'SUCCESS', 'APPLIED']);
    let hideTimer = null;

    function isObject(value) {
        return value !== null && typeof value === 'object' && !Array.isArray(value);
    }

    function cleanString(value) {
        return typeof value === 'string' && value.trim() ? value.trim() : '';
    }

    function firstString(...values) {
        for (const value of values) {
            const cleaned = cleanString(value);
            if (cleaned) return cleaned;
        }
        return '';
    }

    function isCommittedEnvelope(payload) {
        if (!isObject(payload)) return false;
        if (payload.ok === true || payload.committed === true || payload.settled === true) {
            return true;
        }
        return [...COMMITTED_STATUSES].some(status => (
            typeof payload.status === 'string' && payload.status.trim().toUpperCase() === status
        ));
    }

    function settlementFor(payload) {
        if (!isObject(payload)) return null;
        if (isObject(payload.monster_settlement)) return payload.monster_settlement;
        if (isObject(payload.progression?.monster_settlement)) {
            return payload.progression.monster_settlement;
        }
        return null;
    }

    function rewardContainer(payload) {
        if (!isObject(payload)) return null;
        if (isObject(payload.reward_result)) return payload.reward_result;
        if (isObject(payload.progression?.reward_result)) return payload.progression.reward_result;
        return payload;
    }

    function defeatIsExplicit(payload) {
        const settlement = settlementFor(payload);
        return payload?.monster?.defeated === true
            || settlement?.defeated === true
            || payload?.next_action === 'monster_defeated';
    }

    function hasNoDropEvidence(payload) {
        const settlement = settlementFor(payload);
        if (!settlement || settlement.duplicate === true || !defeatIsExplicit(payload)) {
            return false;
        }
        return settlement.functional_lineage_count === 0
            && settlement.wardrobe_lineage_count === 0;
    }

    function explicitRewardType(payload) {
        const nested = isObject(payload?.reward_result) ? payload.reward_result : null;
        const candidates = [
            payload?.reward_type,
            payload?.rewardType,
            nested?.reward_type,
            nested?.type,
        ];
        for (const value of candidates) {
            const normalized = cleanString(value).toUpperCase().replace(/[ -]+/g, '_');
            if (normalized) return normalized;
        }
        return '';
    }

    function iconValue(item) {
        const candidate = firstString(
            item?.icon,
            item?.icon_path,
            item?.asset,
            item?.asset_path,
            item?.preview_asset?.asset,
        );
        if (candidate.startsWith('/assets/') || candidate.startsWith('assets/')) {
            return candidate;
        }
        return '';
    }

    function normalizeItem(kind, item) {
        if (!isObject(item)) return null;
        const itemId = firstString(item.item_id, item.cosmetic_id, item.id);
        const name = firstString(item.display_name, item.name);
        const nameEn = firstString(item.display_name_en, item.name_en, name);
        if (!itemId || !name || !nameEn) return null;

        const model = {
            contract_version: CONTRACT_VERSION,
            status: kind,
            item_id: itemId,
            name,
            name_en: nameEn,
            category: firstString(item.slot, item.category),
            image: iconValue(item),
            fallback_emoji: kind === PURE_COSMETIC ? firstString(item.emoji) : '',
            inventory_id: kind === FUNCTIONAL_EQUIPMENT
                ? (item.inv_id ?? item.inventory_id ?? null)
                : null,
            action: kind === FUNCTIONAL_EQUIPMENT && item.inv_id != null
                ? 'VIEW_BACKPACK'
                : 'NONE',
            pure_cosmetic_no_power: kind === PURE_COSMETIC,
        };
        return Object.freeze(model);
    }

    function unavailable(reason) {
        return Object.freeze({
            contract_version: CONTRACT_VERSION,
            status: UNAVAILABLE,
            reason: cleanString(reason) || 'reward_not_presentable',
            item_id: null,
            name: '',
            name_en: '',
            category: '',
            image: '',
            fallback_emoji: '',
            inventory_id: null,
            action: 'NONE',
            pure_cosmetic_no_power: false,
        });
    }

    function noDrop() {
        return Object.freeze({
            contract_version: CONTRACT_VERSION,
            status: NO_DROP,
            reason: 'no_server_authored_reward',
            item_id: null,
            name: '',
            name_en: '',
            category: '',
            image: '',
            fallback_emoji: '',
            inventory_id: null,
            action: 'NONE',
            pure_cosmetic_no_power: false,
        });
    }

    function skipped() {
        return Object.freeze({
            contract_version: CONTRACT_VERSION,
            status: SKIPPED,
            reason: 'duplicate_settlement',
            item_id: null,
            name: '',
            name_en: '',
            category: '',
            image: '',
            fallback_emoji: '',
            inventory_id: null,
            action: 'NONE',
            pure_cosmetic_no_power: false,
        });
    }

    function normalize(payload) {
        if (!isCommittedEnvelope(payload)) return unavailable('uncommitted_result');
        if (payload.contract_version && payload.contract_version !== CONTRACT_VERSION) {
            // A producer contract version is optional in the legacy result,
            // but a present, wrong version must fail closed.
            return unavailable('wrong_contract_version');
        }

        const rewardType = explicitRewardType(payload);
        if (rewardType && ![FUNCTIONAL_EQUIPMENT, PURE_COSMETIC, NO_DROP].includes(rewardType)) {
            return unavailable('unsupported_reward_type');
        }

        const settlement = settlementFor(payload);
        const rewards = rewardContainer(payload);
        if (settlement?.duplicate === true && !rewards.loot && !rewards.appearance_loot
            && !rewards.functional_equipment && !rewards.pure_cosmetic) {
            return skipped();
        }

        const functional = normalizeItem(
            FUNCTIONAL_EQUIPMENT,
            rewards.functional_equipment || rewards.loot,
        );
        if (functional && (!rewardType || rewardType === FUNCTIONAL_EQUIPMENT)) return functional;

        const cosmetic = normalizeItem(
            PURE_COSMETIC,
            rewards.pure_cosmetic || rewards.appearance_loot,
        );
        if (cosmetic && (!rewardType || rewardType === PURE_COSMETIC)) return cosmetic;

        if (rewardType === NO_DROP || (!rewardType && hasNoDropEvidence(payload))) return noDrop();
        return unavailable('malformed_or_missing_reward');
    }

    function isEnglish() {
        try {
            return typeof global.I18n !== 'undefined' && global.I18n.getLang() === 'en';
        } catch (_) {
            return false;
        }
    }

    function textFor(zh, en) {
        return isEnglish() ? en : zh;
    }

    function hideLegacyToasts() {
        ['loot-toast', 'appear-toast'].forEach(id => {
            const element = document.getElementById(id);
            if (element) element.style.display = 'none';
        });
    }

    function mount() {
        return document.getElementById('reward-drop-v1');
    }

    function setText(id, value) {
        const element = document.getElementById(id);
        if (element) element.textContent = value || '';
        return element;
    }

    function renderImage(model) {
        const host = document.getElementById('reward-drop-v1-art');
        if (!host) return;
        host.replaceChildren();
        if (model.image) {
            const image = document.createElement('img');
            image.src = model.image;
            image.alt = isEnglish() ? model.name_en : model.name;
            image.loading = 'eager';
            image.decoding = 'async';
            image.addEventListener('error', () => {
                host.replaceChildren();
                host.setAttribute('data-art-state', 'unavailable');
            }, { once: true });
            host.appendChild(image);
            host.setAttribute('data-art-state', 'asset');
            return;
        }
        if (model.fallback_emoji) {
            const fallback = document.createElement('span');
            fallback.setAttribute('aria-hidden', 'true');
            fallback.textContent = model.fallback_emoji;
            host.appendChild(fallback);
            host.setAttribute('data-art-state', 'legacy-fallback');
            return;
        }
        if (model.status === NO_DROP) {
            const empty = document.createElement('span');
            empty.className = 'reward-drop-v1__no-drop-mark';
            empty.setAttribute('aria-hidden', 'true');
            empty.textContent = '—';
            host.appendChild(empty);
            host.setAttribute('data-art-state', 'none');
            return;
        }
        const unavailableLabel = document.createElement('span');
        unavailableLabel.className = 'reward-drop-v1__art-unavailable';
        unavailableLabel.textContent = textFor('物品圖像暫不可用', 'Item art unavailable');
        host.appendChild(unavailableLabel);
        host.setAttribute('data-art-state', 'unavailable');
    }

    function render(model) {
        const root = mount();
        if (!root) return { ok: false, status: 'MOUNT_MISSING' };
        clearTimeout(hideTimer);
        hideLegacyToasts();
        if (!model || model.status === SKIPPED) {
            root.hidden = true;
            root.classList.remove('is-visible');
            return { ok: true, status: model?.status || SKIPPED };
        }

        root.dataset.rewardStatus = model.status;
        root.hidden = false;
        root.classList.remove('is-visible');
        void root.offsetWidth;
        root.classList.add('is-visible');
        renderImage(model);

        const title = model.status === FUNCTIONAL_EQUIPMENT
            ? textFor('怪物獎勵', 'Monster Reward')
            : model.status === PURE_COSMETIC
                ? textFor('獲得外觀', 'Cosmetic Acquired')
                : model.status === NO_DROP
                    ? textFor('戰鬥結果', 'Battle Result')
                    : textFor('獎勵資訊暫不可用', 'Reward Unavailable');
        const name = model.status === FUNCTIONAL_EQUIPMENT
            ? textFor(model.name, model.name_en)
            : model.status === PURE_COSMETIC
                ? textFor(model.name, model.name_en)
                : model.status === NO_DROP
                    ? textFor('本次沒有掉落', 'No drop this time')
                    : textFor('未提供可顯示的物品。', 'No item was provided.');
        const meta = model.status === FUNCTIONAL_EQUIPMENT
            ? textFor('功能型裝備 · 已取得', 'Functional Equipment · Acquired')
            : model.status === PURE_COSMETIC
                ? textFor('純外觀 · 不提供戰鬥力量', 'Pure Cosmetic · No combat power')
                : model.status === NO_DROP
                    ? textFor('沒有伺服器授權的獎勵', 'No server-authored reward')
                    : textFor('已安全關閉顯示', 'Presentation closed safely');
        setText('reward-drop-v1-title', title);
        setText('reward-drop-v1-name', name);
        setText('reward-drop-v1-meta', meta);
        const state = document.getElementById('reward-drop-v1-state');
        if (state) {
            state.textContent = '';
            state.hidden = true;
        }

        const backpack = document.getElementById('reward-drop-v1-backpack');
        if (backpack) {
            if (model.status === FUNCTIONAL_EQUIPMENT && model.inventory_id != null) {
                backpack.href = `/inventory?equipment=${encodeURIComponent(String(model.inventory_id))}`;
                backpack.textContent = textFor('查看背包', 'View in Backpack');
                backpack.hidden = false;
            } else {
                backpack.hidden = true;
                backpack.removeAttribute('href');
            }
        }
        const close = document.getElementById('reward-drop-v1-close');
        if (close) {
            close.textContent = textFor('關閉', 'Dismiss');
            close.hidden = false;
            if (close.dataset.rewardDropBound !== 'true') {
                close.addEventListener('click', hide);
                close.dataset.rewardDropBound = 'true';
            }
        }
        hideTimer = setTimeout(() => {
            root.hidden = true;
            root.classList.remove('is-visible');
        }, 6500);
        return { ok: true, status: model.status, item_id: model.item_id };
    }

    function showFunctional(item) {
        return render(normalize({ ok: true, functional_equipment: item }));
    }

    function showCosmetic(item) {
        return render(normalize({ ok: true, pure_cosmetic: item }));
    }

    function showNoDropFromCommittedResult(payload) {
        const model = normalize(payload);
        return render(model.status === NO_DROP ? model : unavailable('no_drop_evidence_missing'));
    }

    function renderCommittedResult(payload) {
        const model = normalize(payload);
        const result = render(model);
        if (model.status === FUNCTIONAL_EQUIPMENT) {
            const rewards = rewardContainer(payload);
            const cosmetic = normalize({ ok: true, pure_cosmetic: rewards.appearance_loot });
            if (cosmetic.status === PURE_COSMETIC) {
                setTimeout(() => render(cosmetic), 1800);
            }
        }
        return result;
    }

    function hide() {
        clearTimeout(hideTimer);
        const root = mount();
        if (root) {
            root.hidden = true;
            root.classList.remove('is-visible');
        }
    }

    const api = Object.freeze({
        CONTRACT_VERSION,
        FUNCTIONAL_EQUIPMENT,
        PURE_COSMETIC,
        NO_DROP,
        UNAVAILABLE,
        normalize,
        render,
        renderCommittedResult,
        showFunctional,
        showCosmetic,
        showNoDropFromCommittedResult,
        hide,
    });
    global.RewardDropPresentationV1 = api;
})(typeof window !== 'undefined' ? window : globalThis);
