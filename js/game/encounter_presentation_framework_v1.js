(function (root, factory) {
    'use strict';
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.EncounterPresentationV1 = factory();
    }
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    'use strict';

    // Presentation metadata only.  This module never chooses an encounter,
    // calculates damage, settles a result, or grants a reward.
    const VERSION = 'a023-v1';
    const TIERS = Object.freeze({
        COMMON: 'common',
        RARE: 'rare',
        ELITE: 'elite',
        BATTLEFIELD_BOSS: 'battlefield_boss',
        LORD_TRIAL: 'lord_trial',
    });

    const TIER_CONTRACT = Object.freeze({
        common: Object.freeze({
            label: 'Common',
            labelZh: '普通遭遇',
            symbol: '✦',
            frame: 'standard',
            entranceMsMax: 420,
            defeatMsMax: 700,
        }),
        rare: Object.freeze({
            label: 'Rare',
            labelZh: '稀有遭遇',
            symbol: '◇',
            frame: 'accent',
            entranceMsMax: 620,
            defeatMsMax: 820,
        }),
        elite: Object.freeze({
            label: 'Elite',
            labelZh: '精英遭遇',
            symbol: '✧',
            frame: 'reinforced',
            entranceMsMax: 780,
            defeatMsMax: 980,
        }),
        battlefield_boss: Object.freeze({
            label: 'Battlefield Boss',
            labelZh: '戰場首領',
            symbol: '✹',
            frame: 'boss',
            entranceMsMax: 1200,
            defeatMsMax: 1400,
        }),
        lord_trial: Object.freeze({
            label: 'Lord Trial',
            labelZh: '領主試煉',
            symbol: '♜',
            frame: 'lord-separate',
            entranceMsMax: 0,
            defeatMsMax: 0,
        }),
    });

    const TIER_ALIASES = Object.freeze({
        normal: TIERS.COMMON,
        common: TIERS.COMMON,
        ordinary: TIERS.COMMON,
        rare: TIERS.RARE,
        uncommon: TIERS.RARE,
        elite: TIERS.ELITE,
        chapter_boss: TIERS.ELITE,
        chapterboss: TIERS.ELITE,
        battlefield_boss: TIERS.BATTLEFIELD_BOSS,
        battlefieldboss: TIERS.BATTLEFIELD_BOSS,
        boss: TIERS.BATTLEFIELD_BOSS,
        book_boss: TIERS.BATTLEFIELD_BOSS,
        bookboss: TIERS.BATTLEFIELD_BOSS,
        lord_trial: TIERS.LORD_TRIAL,
        lordtrial: TIERS.LORD_TRIAL,
    });

    const FEEDBACK_STATES = Object.freeze({
        CORRECT_ATTACK: 'correct_attack',
        MONSTER_DAMAGED: 'monster_damaged',
        SPECIAL_PLACEHOLDER: 'special_placeholder',
        MONSTER_ATTACK: 'monster_attack',
        MONSTER_DEFEATED: 'monster_defeated',
    });

    const VARIANT_AXES = Object.freeze([
        'silhouette',
        'gear',
        'headgear',
        'accessory',
        'size',
        'posture',
        'markings',
        'texture',
        'aura',
        'prop',
        'proportion',
    ]);

    function asText(value) {
        return value === undefined || value === null ? '' : String(value).trim();
    }

    function firstText(source, keys) {
        for (const key of keys) {
            const value = asText(source && source[key]);
            if (value) return value;
        }
        return '';
    }

    function rawTier(source) {
        return firstText(source, [
            'presentation_tier',
            'encounter_rarity',
            'rarity',
            'encounter_class',
            'encounter_type',
        ]).toLowerCase().replace(/[\s-]+/g, '_');
    }

    function normalizeTier(source) {
        const value = rawTier(source);
        return TIER_ALIASES[value] || TIERS.COMMON;
    }

    function isLordTrial(source) {
        const authority = firstText(source, ['authority', 'source_authority', 'encounter_authority'])
            .toLowerCase().replace(/[\s-]+/g, '_');
        return normalizeTier(source) === TIERS.LORD_TRIAL
            || authority === TIERS.LORD_TRIAL
            || source && source.lord_trial === true;
    }

    function finiteNumber(value) {
        const number = Number(value);
        return Number.isFinite(number) ? number : null;
    }

    function normalizeHp(hp, maxHp) {
        const maximum = finiteNumber(maxHp);
        const current = finiteNumber(hp);
        if (maximum === null || maximum <= 0 || current === null) {
            return Object.freeze({ current: null, maximum: null, percent: null });
        }
        const safeMaximum = Math.max(1, maximum);
        const safeCurrent = Math.max(0, Math.min(safeMaximum, current));
        return Object.freeze({
            current: safeCurrent,
            maximum: safeMaximum,
            percent: Math.round((safeCurrent / safeMaximum) * 100),
        });
    }

    function normalizeVariant(source) {
        const raw = source && (source.variant_axes || source.variant || source.visual_variant);
        if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return Object.freeze({});
        const result = {};
        VARIANT_AXES.forEach((key) => {
            const value = asText(raw[key]);
            if (value) result[key] = value;
        });
        return Object.freeze(result);
    }

    function normalizeEncounter(source) {
        const input = source && typeof source === 'object' ? source : {};
        const lordTrial = isLordTrial(input);
        const tier = lordTrial ? TIERS.LORD_TRIAL : normalizeTier(input);
        const contract = TIER_CONTRACT[tier];
        const hp = normalizeHp(input.hp, input.max_hp !== undefined ? input.max_hp : input.hp_max);
        const title = firstText(input, ['name', 'display_name', 'monster_name']) || 'Encounter';
        return Object.freeze({
            tier,
            tierLabel: contract.label,
            tierLabelZh: contract.labelZh,
            tierSymbol: contract.symbol,
            frame: contract.frame,
            title,
            titleEn: firstText(input, ['name_en', 'display_name_en', 'monster_name_en']),
            artSrc: firstText(input, ['artSrc', 'art_src', 'avatar', 'image']),
            hp,
            defeated: input.defeated === true,
            variantAxes: normalizeVariant(input),
            serverResultPresent: !!(input.server_result || input.committed_result || input.result),
            lordTrialAuthoritySeparate: lordTrial,
        });
    }

    function feedbackClass(state) {
        return Object.values(FEEDBACK_STATES).includes(state) ? `is-${state}` : '';
    }

    function applyFeedback(root, outcome) {
        if (!root || !root.classList) return false;
        Object.values(FEEDBACK_STATES).forEach((state) => root.classList.remove(`is-${state}`));
        const state = outcome && outcome.committed === true ? asText(outcome.state) : '';
        const className = feedbackClass(state);
        if (!className) {
            root.removeAttribute('data-encounter-feedback');
            return false;
        }
        root.classList.add(className);
        root.setAttribute('data-encounter-feedback', state);
        return true;
    }

    function ensureBadge(documentRef, monsterCell) {
        if (!documentRef || !monsterCell) return null;
        let badge = monsterCell.querySelector('.encounter-rarity-badge');
        if (!badge) {
            badge = documentRef.createElement('span');
            badge.className = 'encounter-rarity-badge';
            badge.setAttribute('aria-live', 'polite');
            // Keep the existing avatar wrapper as :first-child: legacy E10
            // CSS owns its zoom rule. The badge is presentation metadata and
            // must not change that established art scaling contract.
            const name = monsterCell.querySelector('#monster-name');
            if (name) monsterCell.insertBefore(badge, name);
            else monsterCell.append(badge);
        }
        return badge;
    }

    function decoratePanel(panel, source) {
        if (!panel || !panel.classList) return null;
        const model = normalizeEncounter(source);
        const tierClasses = Object.values(TIERS).map((tier) => `encounter-tier-${tier}`);
        panel.classList.add('encounter-framework-v1');
        tierClasses.forEach((className) => panel.classList.remove(className));
        panel.classList.add(`encounter-tier-${model.tier}`);
        panel.dataset.encounterFramework = VERSION;
        panel.dataset.encounterTier = model.tier;
        panel.dataset.lordTrialAuthority = model.lordTrialAuthoritySeparate ? 'separate' : 'generic-monster';

        const monsterCell = panel.querySelector('.monster-cell');
        const avatar = panel.querySelector('#monster-avatar');
        const name = panel.querySelector('#monster-name');
        const hpRow = panel.querySelector('#monster-hp-row');
        if (monsterCell) {
            monsterCell.dataset.encounterTier = model.tier;
            monsterCell.dataset.encounterFrame = model.frame;
            const badge = ensureBadge(panel.ownerDocument, monsterCell);
            if (badge) {
                badge.textContent = `${model.tierSymbol} ${model.tierLabel}`;
                badge.dataset.encounterTier = model.tier;
                badge.setAttribute('aria-label', `${model.tierLabel} encounter`);
            }
        }
        if (avatar) {
            avatar.dataset.encounterTier = model.tier;
            avatar.dataset.encounterFrame = model.frame;
        }
        if (name) name.dataset.encounterTier = model.tier;
        if (hpRow) {
            hpRow.dataset.hpPresentation = VERSION;
            hpRow.dataset.hpTier = model.tier;
            hpRow.classList.add('encounter-hp-framework-v1');
        }
        return model;
    }

    function createText(documentRef, tagName, className, value) {
        const node = documentRef.createElement(tagName);
        if (className) node.className = className;
        node.textContent = value;
        return node;
    }

    function renderHp(documentRef, hp, tier, label) {
        const wrap = createText(documentRef, 'div', 'encounter-card__hp', '');
        wrap.dataset.hpPresentation = VERSION;
        wrap.dataset.hpTier = tier;
        const top = createText(documentRef, 'div', 'encounter-card__hp-top', '');
        top.append(
            createText(documentRef, 'span', 'encounter-card__hp-label', label || 'HP'),
            createText(documentRef, 'span', 'encounter-card__hp-value', hp.percent === null ? '—' : `${hp.current}/${hp.maximum}`),
        );
        const track = createText(documentRef, 'div', 'encounter-card__hp-track', '');
        const fill = createText(documentRef, 'div', 'encounter-card__hp-fill', '');
        fill.style.width = hp.percent === null ? '0%' : `${hp.percent}%`;
        track.append(fill);
        wrap.append(top, track);
        return wrap;
    }

    function createArt(documentRef, model, source) {
        if (source && source.artClass) {
            const art = createText(documentRef, 'div', `encounter-card__art ${source.artClass}`, '');
            art.setAttribute('role', 'img');
            art.setAttribute('aria-label', model.title);
            return art;
        }
        const image = documentRef.createElement('img');
        image.className = 'encounter-card__art';
        image.alt = model.title;
        image.loading = 'lazy';
        image.decoding = 'async';
        image.src = model.artSrc || '';
        return image;
    }

    function renderCard(container, source) {
        if (!container || !container.ownerDocument) return null;
        const input = source && typeof source === 'object' ? source : {};
        const model = normalizeEncounter(input);
        const documentRef = container.ownerDocument;
        const card = createText(documentRef, 'article', `encounter-card encounter-tier-${model.tier}`, '');
        card.dataset.encounterFramework = VERSION;
        card.dataset.encounterTier = model.tier;
        card.dataset.presentationOnly = 'true';
        if (model.lordTrialAuthoritySeparate) card.dataset.lordTrialAuthority = 'separate';

        const header = createText(documentRef, 'header', 'encounter-card__header', '');
        const badge = createText(documentRef, 'span', 'encounter-rarity-badge', `${model.tierSymbol} ${model.tierLabel}`);
        badge.dataset.encounterTier = model.tier;
        const kicker = createText(documentRef, 'span', 'encounter-card__kicker', input.zone || 'E10 Encounter');
        header.append(badge, kicker);

        const identity = createText(documentRef, 'div', 'encounter-card__identity', '');
        identity.append(
            createText(documentRef, 'h3', 'encounter-card__name', model.title),
            createText(documentRef, 'p', 'encounter-card__subtitle', input.identityHint || 'Server-settled encounter presentation'),
        );

        const artStage = createText(documentRef, 'div', 'encounter-card__portrait', '');
        artStage.dataset.encounterFrame = model.frame;
        artStage.append(createArt(documentRef, model, input));
        const frameMark = createText(documentRef, 'span', 'encounter-card__frame-mark', model.tierSymbol);
        frameMark.setAttribute('aria-hidden', 'true');
        artStage.append(frameMark);

        const footer = createText(documentRef, 'div', 'encounter-card__footer', '');
        footer.append(renderHp(documentRef, model.hp, model.tier, input.hpLabel || 'HP'));
        if (input.feedbackState) {
            const feedback = createText(documentRef, 'div', `encounter-card__feedback is-${input.feedbackState}`, input.feedbackLabel || input.feedbackState);
            footer.append(feedback);
        }

        card.append(header, identity, artStage, footer);
        container.append(card);
        return card;
    }

    function renderPrototypeGrid(container, prototypes) {
        if (!container || !Array.isArray(prototypes)) return [];
        container.replaceChildren();
        return prototypes.map((prototype) => renderCard(container, prototype)).filter(Boolean);
    }

    return Object.freeze({
        VERSION,
        TIERS,
        TIER_CONTRACT,
        FEEDBACK_STATES,
        VARIANT_AXES,
        normalizeTier,
        normalizeHp,
        normalizeVariant,
        normalizeEncounter,
        applyFeedback,
        decoratePanel,
        renderHp,
        renderCard,
        renderPrototypeGrid,
    });
}));
