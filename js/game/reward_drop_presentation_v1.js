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
    const ALREADY_OWNED = 'ALREADY_OWNED';
    const NOT_FIRST_CLEAR = 'NOT_FIRST_CLEAR';
    const UNAVAILABLE = 'UNAVAILABLE';
    const SKIPPED = 'SKIPPED';
    const COMMITTED_STATUSES = new Set(['COMMITTED', 'SETTLED', 'SUCCESS', 'APPLIED']);
    const PRESENTATION_STATUS_ALIASES = Object.freeze({
        ALREADY_OWNED,
        NO_OP: ALREADY_OWNED,
        NO_NEW_OWNERSHIP: ALREADY_OWNED,
        REPLAY_NO_REWARD: ALREADY_OWNED,
        NOT_FIRST_CLEAR,
        NO_NEW_ENTITLEMENT: NOT_FIRST_CLEAR,
        FIRST_CLEAR_ALREADY_CLAIMED: NOT_FIRST_CLEAR,
    });
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
        )) || Boolean(PRESENTATION_STATUS_ALIASES[normalizedStatus(payload.status)]);
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

    function normalizedStatus(value) {
        return cleanString(value).toUpperCase().replace(/[ -]+/g, '_');
    }

    function explicitPresentationStatus(payload) {
        if (!isObject(payload)) return null;
        const containers = [
            payload,
            payload.reward_result,
            payload.progression?.reward_result,
            payload.monster_settlement,
            payload.progression?.monster_settlement,
        ];
        for (const container of containers) {
            if (!isObject(container)) continue;
            for (const key of ['presentation_status', 'reward_status', 'outcome', 'status']) {
                const normalized = normalizedStatus(container[key]);
                const mapped = PRESENTATION_STATUS_ALIASES[normalized];
                if (mapped) return { status: mapped, reason: normalized.toLowerCase() };
            }
        }
        return null;
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
            inventory_id: null,
            action: 'NONE',
            pure_cosmetic_no_power: false,
        });
    }

    function noNewReward(status, reason) {
        return Object.freeze({
            contract_version: CONTRACT_VERSION,
            status,
            reason: cleanString(reason) || 'no_new_reward',
            item_id: null,
            name: '',
            name_en: '',
            category: '',
            image: '',
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

        const presentationStatus = explicitPresentationStatus(payload);
        if (presentationStatus) {
            const rewards = rewardContainer(payload);
            const hasConflictingReward = rewards && (
                rewards.loot || rewards.appearance_loot
                || rewards.functional_equipment || rewards.pure_cosmetic
                || firstString(
                    rewards.item_id,
                    rewards.cosmetic_id,
                    rewards.id,
                    rewards.display_name,
                    rewards.name,
                    rewards.icon,
                )
            );
            if (hasConflictingReward) return unavailable('conflicting_reward_status');
            return noNewReward(presentationStatus.status, presentationStatus.reason);
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
        if (model.status === NO_DROP) {
            const empty = document.createElement('span');
            empty.className = 'reward-drop-v1__no-drop-mark';
            empty.setAttribute('aria-hidden', 'true');
            host.appendChild(empty);
            host.setAttribute('data-art-state', 'none');
            return;
        }
        const unavailableArt = document.createElement('span');
        unavailableArt.className = 'reward-drop-v1__neutral-art';
        unavailableArt.setAttribute('aria-hidden', 'true');
        host.appendChild(unavailableArt);
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

        setText('reward-drop-v1-brand', textFor('弈境奇兵 · 冒險結果', 'GO ODYSSEY · ADVENTURE RESULT'));
        const title = model.status === FUNCTIONAL_EQUIPMENT
            ? textFor('獲得戰利品', 'Reward Acquired')
            : model.status === PURE_COSMETIC
                ? textFor('獲得外觀', 'Cosmetic Acquired')
                : model.status === NO_DROP
                    ? textFor('本次沒有掉落', 'No Drop This Time')
                    : model.status === ALREADY_OWNED
                        ? textFor('獎勵已擁有', 'Reward Already Owned')
                        : model.status === NOT_FIRST_CLEAR
                            ? textFor('非首次通關', 'Not a First Clear')
                    : textFor('獎勵資訊暫不可用', 'Reward Unavailable');
        const name = model.status === FUNCTIONAL_EQUIPMENT
            ? textFor(model.name, model.name_en)
            : model.status === PURE_COSMETIC
                ? textFor(model.name, model.name_en)
                : model.status === NO_DROP
                    ? ''
                    : model.status === ALREADY_OWNED
                        ? textFor('本次未新增所有權', 'No new ownership added')
                        : model.status === NOT_FIRST_CLEAR
                            ? textFor('未產生新首通獎勵', 'No new first-clear reward')
                    : textFor('未提供可顯示的物品。', 'No item was provided.');
        const meta = model.status === FUNCTIONAL_EQUIPMENT
            ? textFor('功能型裝備 · 已取得', 'Functional Equipment · Acquired')
            : model.status === PURE_COSMETIC
                ? textFor('純外觀 · 不提供戰鬥力', 'Pure Cosmetic · No combat power')
                : model.status === NO_DROP
                    ? textFor('沒有伺服器授權的獎勵', 'No server-authored reward')
                    : model.status === ALREADY_OWNED
                        ? textFor('既有獎勵 · 本次不新增所有權', 'Existing reward · No-op')
                        : model.status === NOT_FIRST_CLEAR
                            ? textFor('非首次通關 · 無新首通獎勵', 'Not first clear · No new entitlement')
                    : textFor('已安全關閉顯示', 'Presentation closed safely');
        const stateCopy = model.status === FUNCTIONAL_EQUIPMENT
            ? textFor('獎勵結果已確認，可在背包查看。', 'Reward confirmed. View it in your Backpack.')
            : model.status === PURE_COSMETIC
                ? textFor('此獎勵僅供外觀展示。', 'This reward is cosmetic only.')
                : model.status === NO_DROP
                    ? textFor('本次不補發其他物品。', 'No replacement item is granted.')
                    : model.status === ALREADY_OWNED
                        ? textFor('伺服器結果已確認，本次不重複發放獎勵。', 'Server result confirmed. No duplicate reward is granted.')
                        : model.status === NOT_FIRST_CLEAR
                            ? textFor('伺服器結果已確認，本次不產生新的首通獎勵。', 'Server result confirmed. No new first-clear reward is created.')
                : textFor('未提供可安全顯示的內容。', 'No safe presentation content was provided.');
        setText('reward-drop-v1-title', title);
        setText('reward-drop-v1-name', name);
        setText('reward-drop-v1-meta', meta);
        const state = document.getElementById('reward-drop-v1-state');
        if (state) {
            state.textContent = stateCopy;
            state.hidden = false;
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
        ALREADY_OWNED,
        NOT_FIRST_CLEAR,
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
