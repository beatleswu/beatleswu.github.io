(function (root) {
    'use strict';

    // F029 is deliberately a presentation boundary.  It accepts only the
    // additive F028 transport projection; it never derives a reward from a
    // zone, score, boss art, or local clear state.
    const CONTRACT_VERSION = 'F028_BATTLEFIELD_BOSS_MAPPING_A_FIRST_CLEAR_V1';
    const GRANTED = 'GRANTED';
    const ALREADY_OWNED = 'ALREADY_OWNED';
    const NO_REWARD = 'NO_REWARD';
    const RESULT_STATUSES = new Set([GRANTED, ALREADY_OWNED, NO_REWARD]);

    // Presentation allowlist only.  This is not a Zone -> reward authority;
    // the server has already resolved the item id.  It prevents malformed or
    // unrelated server payloads from becoming a player-visible reward card.
    const MAPPING_A_PRESENTATION = Object.freeze({
        back_pack: Object.freeze({
            slot: 'back',
            zh: '棋具布包',
            en: 'Go Kit Pack',
            fallbackIcon: '🎒',
            asset: '/assets/hero/items/back_pack.svg',
        }),
        hat_cloth: Object.freeze({
            slot: 'hat',
            zh: '布巾',
            en: 'Cloth Headwrap',
            fallbackIcon: '🧢',
            asset: '/assets/hero/items/hat_cloth.svg',
        }),
        hat_bamboo: Object.freeze({
            slot: 'hat',
            zh: '竹笠',
            en: 'Bamboo Hat',
            fallbackIcon: '👒',
            asset: '/assets/hero/items/hat_bamboo.svg',
        }),
        robe_crane: Object.freeze({
            slot: 'outfit',
            zh: '仙鶴袍',
            en: 'Crane Robe',
            fallbackIcon: '👘',
            asset: '/assets/hero/items/robe_crane.svg',
        }),
        hat_onihorns: Object.freeze({
            slot: 'hat',
            zh: '鬼角盔',
            en: 'Oni Horns',
            fallbackIcon: '👹',
            asset: '/assets/hero/items/hat_onihorns.svg',
        }),
        robe_dragon: Object.freeze({
            slot: 'outfit',
            zh: '龍紋袍',
            en: 'Dragon Robe',
            fallbackIcon: '🥻',
            asset: '/assets/hero/items/robe_dragon.svg',
        }),
        acc_dragon_pendant: Object.freeze({
            slot: 'accessory',
            zh: '龍形玉佩',
            en: 'Jade Dragon Pendant',
            fallbackIcon: '🔱',
            asset: '/assets/hero/items/acc_dragon_pendant.svg',
        }),
        back_cloak: Object.freeze({
            slot: 'back',
            zh: '星辰披風',
            en: 'Star Cloak',
            fallbackIcon: '🧥',
            asset: '/assets/hero/items/back_cloak.svg',
        }),
        hat_dragon_horn: Object.freeze({
            slot: 'hat',
            zh: '龍角冠',
            en: 'Dragon Horn Crown',
            fallbackIcon: '🐲',
            asset: '/assets/hero/items/hat_dragon_horn.svg',
        }),
        hat_celestial_crown: Object.freeze({
            slot: 'hat',
            zh: '天龍金冠',
            en: 'Celestial Dragon Crown',
            fallbackIcon: '✨',
            asset: '/assets/hero/items/hat_celestial_crown.svg',
        }),
    });

    const COPY = Object.freeze({
        en: Object.freeze({
            kicker: 'Battlefield Boss Reward',
            grantedTitle: 'Reward earned',
            grantedBody: 'Added to your wardrobe. It is not equipped automatically.',
            alreadyTitle: 'Already in your wardrobe',
            alreadyBody: 'Your collection is unchanged. No replacement reward was issued.',
            meta: 'Cosmetic appearance · no combat bonus',
            continue: 'Continue',
            refreshFailed: 'Reward recorded. Wardrobe refresh is unavailable; reload to verify your collection.',
        }),
        zh: Object.freeze({
            kicker: '戰場領主獎勵',
            grantedTitle: '獎勵已取得',
            grantedBody: '已加入你的衣櫃，不會自動裝備。',
            alreadyTitle: '衣櫃已有此物',
            alreadyBody: '收藏未變更，沒有發放替代獎勵。',
            meta: '純外觀 · 不增加戰力',
            continue: '繼續',
            refreshFailed: '獎勵已記錄，但衣櫃更新暫時失敗；請重新整理確認收藏。',
        }),
    });

    function isRecord(value) {
        return value !== null && typeof value === 'object' && !Array.isArray(value);
    }

    function invalid(reasonCode) {
        return Object.freeze({
            valid: false,
            hasReward: false,
            kind: 'invalid',
            reasonCode,
        });
    }

    function rewardPayload(response) {
        if (!isRecord(response)) return invalid('F028_REWARD_RESULT_MISSING');
        if (response.ok === false) return invalid('SERVER_REJECTED');
        const nested = isRecord(response.reward) && response.reward.contract_version
            ? response.reward
            : null;
        const direct = response.contract_version ? response : null;
        const payload = nested || direct;
        if (!payload) return invalid('F028_REWARD_RESULT_MISSING');
        if (payload.contract_version !== CONTRACT_VERSION) return invalid('F028_CONTRACT_UNSUPPORTED');
        if (Object.prototype.hasOwnProperty.call(response, 'reward_item')
            && response.reward_item !== null
            && isRecord(payload.reward_item)
            && response.reward_item.item_id !== payload.reward_item.item_id) {
            return invalid('REWARD_ITEM_PROJECTION_MISMATCH');
        }
        return payload;
    }

    function requiredBoolean(payload, key) {
        return typeof payload[key] === 'boolean';
    }

    function normalize(response) {
        const payload = rewardPayload(response);
        if (!isRecord(payload) || payload.valid === false) return payload;
        if (!RESULT_STATUSES.has(payload.status)) return invalid('REWARD_STATUS_INVALID');
        for (const key of ['passed', 'first_clear', 'replay', 'entitlement_consumed']) {
            if (!requiredBoolean(payload, key)) return invalid('REWARD_BOOLEAN_INVALID');
        }
        for (const key of ['auto_equip', 'auto_equipped', 'compensation', 'replacement_reward']) {
            if (payload[key] !== false) return invalid('PROTECTED_REWARD_FLAG_INVALID');
        }
        if (payload.combat_power !== 0) return invalid('COSMETIC_COMBAT_POWER_INVALID');
        if (payload.coins !== undefined && payload.coins !== 0) return invalid('COIN_COMPENSATION_FORBIDDEN');

        if (payload.status === NO_REWARD) {
            if (payload.first_clear || payload.entitlement_consumed) return invalid('NO_REWARD_ENTITLEMENT_INVALID');
            if (payload.item_id !== null || payload.reward_item !== null) return invalid('NO_REWARD_ITEM_EXPOSED');
            return Object.freeze({
                valid: true,
                hasReward: false,
                kind: 'no_reward',
                status: payload.status,
                replay: payload.replay,
                reasonCode: payload.reason_code || 'NO_REWARD',
            });
        }

        if (!payload.first_clear || payload.replay || !payload.entitlement_consumed) {
            return invalid('ACQUIRED_REWARD_NOT_FIRST_CLEAR');
        }
        if (!payload.ownership_persisted || payload.ownership_authority !== 'player_wardrobe') {
            return invalid('OWNERSHIP_PROJECTION_INVALID');
        }
        if (!isRecord(payload.reward_item)) return invalid('REWARD_ITEM_MISSING');
        const item = payload.reward_item;
        const itemId = payload.item_id;
        const presentation = MAPPING_A_PRESENTATION[itemId];
        if (!presentation) return invalid('UNKNOWN_MAPPING_A_ITEM');
        if (item.id !== itemId || item.item_id !== itemId || item.slot !== presentation.slot) {
            return invalid('REWARD_ITEM_IDENTITY_INVALID');
        }
        if (item.presentation_only !== true
            || item.equipped !== false
            || item.auto_equipped !== false
            || item.combat_power !== 0
            || item.duplicate !== false
            || item.ownership_authority !== 'player_wardrobe') {
            return invalid('REWARD_ITEM_PRESENTATION_INVALID');
        }
        if (payload.status === GRANTED && item.new !== true) return invalid('GRANTED_FLAG_INVALID');
        if (payload.status === ALREADY_OWNED && (item.new !== false || item.already_owned !== true)) {
            return invalid('ALREADY_OWNED_FLAG_INVALID');
        }
        return Object.freeze({
            valid: true,
            hasReward: true,
            kind: payload.status === GRANTED ? 'granted' : 'already_owned',
            status: payload.status,
            itemId,
            slot: presentation.slot,
            item,
            presentation,
            reasonCode: payload.reason_code || null,
        });
    }

    function lang(options) {
        if (options && (options.lang === 'en' || options.lang === 'zh')) return options.lang;
        if (root.I18n && typeof root.I18n.getLang === 'function' && root.I18n.getLang() === 'en') return 'en';
        if (root.document && /^en(?:-|$)/i.test(root.document.documentElement?.lang || '')) return 'en';
        return 'zh';
    }

    function text(key, options) {
        const currentLang = lang(options);
        const i18nKey = `index.boss.reward.${key}`;
        if (root.I18n && typeof root.I18n.t === 'function') {
            const translated = root.I18n.t(i18nKey);
            if (translated && translated !== i18nKey) return translated;
        }
        return COPY[currentLang][key] || COPY.zh[key] || key;
    }

    function itemName(model, options) {
        const currentLang = lang(options);
        const item = model.item || {};
        if (currentLang === 'en') {
            return (typeof item.name_en === 'string' && item.name_en.trim())
                || model.presentation.en;
        }
        return (typeof item.display_name === 'string' && item.display_name.trim())
            || model.presentation.zh;
    }

    function itemAsset(model) {
        const serverAsset = model.item && model.item.presentation && model.item.presentation.asset;
        if (typeof serverAsset === 'string' && serverAsset.startsWith('/assets/hero/items/')) return serverAsset;
        return model.presentation.asset;
    }

    function documentFor(options) {
        return options && options.document ? options.document : root.document;
    }

    function element(document, id) {
        return document && typeof document.getElementById === 'function'
            ? document.getElementById(id)
            : null;
    }

    function render(model, options = {}) {
        const document = documentFor(options);
        const panel = element(document, 'boss-reward-presentation');
        if (!panel) return false;
        if (!model || !model.valid || !model.hasReward) {
            panel.hidden = true;
            delete panel.dataset.status;
            delete panel.dataset.itemId;
            return true;
        }

        const name = itemName(model, options);
        const icon = element(document, 'boss-reward-presentation-icon');
        const image = element(document, 'boss-reward-presentation-image');
        const fallback = element(document, 'boss-reward-presentation-fallback');
        if (image) {
            image.src = itemAsset(model);
            image.alt = name;
            image.hidden = true;
            image.onload = () => {
                image.hidden = false;
                if (fallback) fallback.hidden = true;
            };
            image.onerror = () => {
                image.hidden = true;
                if (fallback) fallback.hidden = false;
            };
        }
        if (fallback) {
            fallback.textContent = model.item.icon || model.presentation.fallbackIcon;
            fallback.hidden = true;
        }
        if (icon) icon.setAttribute('aria-label', name);
        const kicker = element(document, 'boss-reward-presentation-kicker');
        const title = element(document, 'boss-reward-presentation-title');
        const itemLabel = element(document, 'boss-reward-presentation-item-name');
        const state = element(document, 'boss-reward-presentation-state');
        const meta = element(document, 'boss-reward-presentation-meta');
        if (kicker) kicker.textContent = text('kicker', options);
        if (title) title.textContent = model.kind === 'granted'
            ? text('grantedTitle', options)
            : text('alreadyTitle', options);
        if (itemLabel) itemLabel.textContent = name;
        if (state) state.textContent = model.kind === 'granted'
            ? text('grantedBody', options)
            : text('alreadyBody', options);
        if (meta) meta.textContent = text('meta', options);
        panel.hidden = false;
        panel.dataset.status = model.status;
        panel.dataset.itemId = model.itemId;
        panel.dataset.autoEquip = 'false';
        panel.dataset.combatPower = '0';
        return true;
    }

    function setRefreshFailure(options) {
        const document = documentFor(options);
        const state = element(document, 'boss-reward-presentation-state');
        if (state) state.textContent = text('refreshFailed', options);
        const panel = element(document, 'boss-reward-presentation');
        if (panel) panel.dataset.refreshStatus = 'failed';
    }

    async function present(response, options = {}) {
        const model = normalize(response);
        if (!model.valid || !model.hasReward) {
            reset(options);
            return Object.freeze({ ...model, rendered: false, refreshStatus: 'not_applicable' });
        }
        const rendered = render(model, options);
        let refreshStatus = 'not_requested';
        if (typeof options.refreshOwnership === 'function') {
            try {
                const refreshed = await options.refreshOwnership();
                if (refreshed === false) throw new Error('wardrobe refresh returned false');
                refreshStatus = 'refreshed';
            } catch (error) {
                refreshStatus = 'failed';
                setRefreshFailure(options);
                if (typeof options.onRefreshFailure === 'function') options.onRefreshFailure(error);
            }
        }
        return Object.freeze({ ...model, rendered, refreshStatus });
    }

    function reset(options = {}) {
        const document = documentFor(options);
        const panel = element(document, 'boss-reward-presentation');
        if (!panel) return false;
        panel.hidden = true;
        delete panel.dataset.status;
        delete panel.dataset.itemId;
        delete panel.dataset.refreshStatus;
        return true;
    }

    root.BattlefieldBossRewardConsumer = Object.freeze({
        CONTRACT_VERSION,
        GRANTED,
        ALREADY_OWNED,
        NO_REWARD,
        MAPPING_A_PRESENTATION,
        normalize,
        render,
        present,
        reset,
    });
}(typeof window !== 'undefined' ? window : globalThis));
