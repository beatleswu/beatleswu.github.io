(function (root, factory) {
    'use strict';
    if (typeof module === 'object' && module.exports) {
        module.exports = factory(null);
    } else {
        root.BattlefieldBossCosmeticDisplayV1 = factory(root);
    }
}(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
    'use strict';

    // Read-only browser projection of the existing canonical sources:
    // APPEARANCE_DEFS.id + PURE_COSMETIC_PRESENTATION_REGISTRY. This is not
    // Mapping A and never decides entitlement, ownership, or reward policy.
    var SOURCE_AUTHORITY = 'APPEARANCE_DEFS.id + PURE_COSMETIC_PRESENTATION_REGISTRY';
    var CATALOG = Object.freeze({
        back_pack: Object.freeze({
            canonical_cosmetic_id: 'back_pack',
            display_name: '棋具布包',
            display_name_key: 'shop.cosmetic.item.back_pack.name',
            display_asset: '/assets/hero/items/fullbody/back_pack.webp',
            display_asset_format: 'WEBP',
            display_category: 'back',
        }),
        hat_cloth: Object.freeze({
            canonical_cosmetic_id: 'hat_cloth',
            display_name: '布巾',
            display_name_key: 'shop.cosmetic.item.hat_cloth.name',
            display_asset: '/assets/hero/items/hat_cloth.svg',
            display_asset_format: 'SVG',
            display_category: 'hat',
        }),
        hat_bamboo: Object.freeze({
            canonical_cosmetic_id: 'hat_bamboo',
            display_name: '竹笠',
            display_name_key: 'shop.cosmetic.item.hat_bamboo.name',
            display_asset: '/assets/hero/items/hat_bamboo.svg',
            display_asset_format: 'SVG',
            display_category: 'hat',
        }),
        robe_crane: Object.freeze({
            canonical_cosmetic_id: 'robe_crane',
            display_name: '仙鶴袍',
            display_name_key: 'shop.cosmetic.item.robe_crane.name',
            display_asset: '/assets/hero/items/fullbody/robe_crane.webp',
            display_asset_format: 'WEBP',
            display_category: 'outfit',
        }),
        hat_onihorns: Object.freeze({
            canonical_cosmetic_id: 'hat_onihorns',
            display_name: '鬼角盔',
            display_name_key: 'shop.cosmetic.item.hat_onihorns.name',
            display_asset: '/assets/hero/items/hat_onihorns.svg',
            display_asset_format: 'SVG',
            display_category: 'hat',
        }),
        robe_dragon: Object.freeze({
            canonical_cosmetic_id: 'robe_dragon',
            display_name: '龍紋袍',
            display_name_key: 'shop.cosmetic.item.robe_dragon.name',
            display_asset: '/assets/hero/items/fullbody/robe_dragon.webp',
            display_asset_format: 'WEBP',
            display_category: 'outfit',
        }),
        acc_dragon_pendant: Object.freeze({
            canonical_cosmetic_id: 'acc_dragon_pendant',
            display_name: '龍形玉佩',
            display_name_key: 'shop.cosmetic.item.acc_dragon_pendant.name',
            display_asset: '/assets/hero/items/fullbody/acc_dragon_pendant.webp',
            display_asset_format: 'WEBP',
            display_category: 'accessory',
        }),
        back_cloak: Object.freeze({
            canonical_cosmetic_id: 'back_cloak',
            display_name: '星紋斗篷',
            display_name_key: 'shop.cosmetic.item.back_cloak.name',
            display_asset: '/assets/hero/items/fullbody/back_cloak.webp',
            display_asset_format: 'WEBP',
            display_category: 'back',
        }),
        hat_dragon_horn: Object.freeze({
            canonical_cosmetic_id: 'hat_dragon_horn',
            display_name: '龍角冠',
            display_name_key: 'shop.cosmetic.item.hat_dragon_horn.name',
            display_asset: '/assets/hero/items/hat_dragon_horn.svg',
            display_asset_format: 'SVG',
            display_category: 'hat',
        }),
        hat_celestial_crown: Object.freeze({
            canonical_cosmetic_id: 'hat_celestial_crown',
            display_name: '天龍金冠',
            display_name_key: 'shop.cosmetic.item.hat_celestial_crown.name',
            display_asset: '/assets/hero/items/hat_celestial_crown.svg',
            display_asset_format: 'SVG',
            display_category: 'hat',
        }),
    });

    function translatedName(record, options) {
        var i18n = options && options.i18n;
        if (!i18n && root && root.I18n) i18n = root.I18n;
        if (i18n && typeof i18n.t === 'function' && record.display_name_key) {
            try {
                var translated = i18n.t(record.display_name_key);
                if (translated && translated !== record.display_name_key) return String(translated);
            } catch (_) {
                // The canonical source name remains the safe fallback.
            }
        }
        return record.display_name;
    }

    function resolve(cosmeticId, options) {
        var key = typeof cosmeticId === 'string' ? cosmeticId.trim() : '';
        var record = CATALOG[key];
        if (!record) return null;
        return Object.freeze(Object.assign({}, record, {
            display_name: translatedName(record, options),
            source_authority: SOURCE_AUTHORITY,
        }));
    }

    return Object.freeze({
        SOURCE_AUTHORITY: SOURCE_AUTHORITY,
        CATALOG: CATALOG,
        resolve: resolve,
    });
}));
