(function (root, factory) {
    'use strict';
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.BattlefieldBossRewardPresentationV1 = factory();
        root.showBattlefieldBossRewardResult = function (payload) {
            var target = document.getElementById('battlefield-boss-reward-result');
            return root.BattlefieldBossRewardPresentationV1.renderResult(target, payload);
        };
        root.clearBattlefieldBossRewardResult = function () {
            var target = document.getElementById('battlefield-boss-reward-result');
            return root.BattlefieldBossRewardPresentationV1.clearResult(target);
        };
    }
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    'use strict';

    // F025 is a presentation adapter only. The typed F023 result remains the
    // reward authority; this module never resolves Mapping A, grants an item,
    // changes combat, or writes World/Quest/Lord state.
    var VERSION = 'f025-v1';
    var CONTRACT_VERSION = 'F024_BATTLEFIELD_BOSS_REWARD_RESULT_TRANSPORT_V1';
    var STATUS = Object.freeze({
        NEW_COSMETIC: 'FIRST_CLEAR_NEW_COSMETIC',
        ALREADY_OWNED_NO_OP: 'FIRST_CLEAR_ALREADY_OWNED_NO_OP',
        NOT_FIRST_CLEAR: 'NOT_FIRST_CLEAR',
    });
    var FIELDS = Object.freeze([
        'contract_version',
        'status',
        'zone_key',
        'reward_policy_version',
        'mapped_cosmetic_id',
        'first_clear_entitlement_consumed',
        'cosmetic_newly_owned',
        'already_owned_no_op',
        'entitlement_replayed',
    ]);
    var FIELD_SET = Object.freeze(FIELDS.reduce(function (set, field) {
        set[field] = true;
        return set;
    }, Object.create(null)));

    function failure(code, message) {
        var error = new Error(code + ': ' + message);
        error.code = code;
        return error;
    }

    function isPlainObject(value) {
        if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
        var proto = Object.getPrototypeOf(value);
        return proto === Object.prototype || proto === null;
    }

    function requireText(value, field) {
        if (typeof value !== 'string' || !value.trim()) {
            throw failure('invalid_text', field + ' must be a non-empty string');
        }
        return value.trim();
    }

    function requireBoolean(value, field) {
        if (typeof value !== 'boolean') {
            throw failure('invalid_boolean', field + ' must be boolean');
        }
        return value;
    }

    function normalizeResult(payload) {
        if (!isPlainObject(payload)) {
            throw failure('invalid_payload', 'F024 result must be a plain object');
        }
        Object.keys(payload).forEach(function (field) {
            if (!FIELD_SET[field]) throw failure('unknown_payload_field', field);
        });
        FIELDS.forEach(function (field) {
            if (!Object.prototype.hasOwnProperty.call(payload, field)) {
                throw failure('missing_payload_field', field);
            }
        });
        if (payload.contract_version !== CONTRACT_VERSION) {
            throw failure('unsupported_contract', 'unsupported F024 contract');
        }
        if (typeof payload.status !== 'string'
                || !Object.values(STATUS).includes(payload.status)) {
            throw failure('unsupported_status', 'unsupported F024 reward status');
        }
        var model = {
            contract_version: payload.contract_version,
            status: payload.status,
            zone_key: requireText(payload.zone_key, 'zone_key'),
            reward_policy_version: requireText(payload.reward_policy_version, 'reward_policy_version'),
            mapped_cosmetic_id: requireText(payload.mapped_cosmetic_id, 'mapped_cosmetic_id'),
            first_clear_entitlement_consumed: requireBoolean(
                payload.first_clear_entitlement_consumed,
                'first_clear_entitlement_consumed'
            ),
            cosmetic_newly_owned: requireBoolean(payload.cosmetic_newly_owned, 'cosmetic_newly_owned'),
            already_owned_no_op: requireBoolean(payload.already_owned_no_op, 'already_owned_no_op'),
            entitlement_replayed: requireBoolean(payload.entitlement_replayed, 'entitlement_replayed'),
        };
        var expected = model.status === STATUS.NEW_COSMETIC
            ? [true, true, false]
            : model.status === STATUS.ALREADY_OWNED_NO_OP
            ? [true, false, true]
            : [false, false, false];
        var actual = [
            model.first_clear_entitlement_consumed,
            model.cosmetic_newly_owned,
            model.already_owned_no_op,
        ];
        if (actual.some(function (value, index) { return value !== expected[index]; })) {
            throw failure('status_flags_mismatch', 'F024 status flags are inconsistent');
        }
        if (model.status !== STATUS.NOT_FIRST_CLEAR && model.entitlement_replayed) {
            throw failure('replay_flag_mismatch', 'only NOT_FIRST_CLEAR may be replayed');
        }
        return Object.freeze(model);
    }

    function text(documentRef, tag, className, value) {
        var node = documentRef.createElement(tag);
        if (className) node.className = className;
        node.textContent = value;
        return node;
    }

    function isEnglish(documentRef, locale) {
        if (locale) return String(locale).toLowerCase().indexOf('en') === 0;
        var lang = documentRef && documentRef.documentElement
            ? documentRef.documentElement.lang : '';
        return String(lang || '').toLowerCase().indexOf('en') === 0;
    }

    function copyFor(model, english) {
        if (model.status === STATUS.NEW_COSMETIC) {
            return english
                ? {
                    eyebrow: 'BATTLEFIELD BOSS · FIRST CLEAR',
                    title: 'Cosmetic reward secured',
                    body: 'Your first-clear cosmetic was resolved and newly added to your wardrobe.',
                    state: 'NEWLY ACQUIRED',
                    entitlement: 'Entitlement consumed',
                }
                : {
                    eyebrow: '戰場首領 · 首次通關',
                    title: '外觀獎勵已取得',
                    body: '本區首次通關外觀已完成結算，並新增至你的衣櫃。',
                    state: '新取得',
                    entitlement: '首通權益已消耗',
                };
        }
        if (model.status === STATUS.ALREADY_OWNED_NO_OP) {
            return english
                ? {
                    eyebrow: 'BATTLEFIELD BOSS · FIRST CLEAR',
                    title: 'Reward resolved · already owned',
                    body: 'The first-clear entitlement was consumed. This cosmetic was already in your wardrobe; no compensation or replacement was issued.',
                    state: 'ALREADY OWNED · NO-OP',
                    entitlement: 'Entitlement consumed',
                }
                : {
                    eyebrow: '戰場首領 · 首次通關',
                    title: '獎勵已結算 · 已經擁有',
                    body: '首通權益已消耗；這件外觀已在你的衣櫃中，因此不補償、不替換。',
                    state: '已擁有 · 無操作',
                    entitlement: '首通權益已消耗',
                };
        }
        return english
            ? {
                eyebrow: 'BATTLEFIELD BOSS · RESULT',
                title: 'No first-clear reward',
                body: 'This result does not carry a new first-clear entitlement. No cosmetic claim was made.',
                state: 'NO NEW ENTITLEMENT',
                entitlement: 'No first-clear entitlement consumed',
            }
            : {
                eyebrow: '戰場首領 · 結果',
                title: '本次沒有首通獎勵',
                body: '本次結果沒有新的首通權益，也沒有提出外觀領取。',
                state: '沒有新權益',
                entitlement: '沒有消耗首通權益',
            };
    }

    function clearResult(container) {
        if (!container) return false;
        container.replaceChildren();
        container.hidden = true;
        container.removeAttribute('data-f025-status');
        container.removeAttribute('data-f025-replayed');
        return true;
    }

    function renderResult(container, payload, options) {
        if (!container || !container.ownerDocument) {
            return { ok: false, error: 'target_required' };
        }
        var model;
        try {
            model = normalizeResult(payload);
        } catch (error) {
            clearResult(container);
            container.dataset.f025Error = error.code || 'invalid_result';
            return { ok: false, error: error.code || 'invalid_result' };
        }

        var documentRef = container.ownerDocument;
        var english = isEnglish(documentRef, options && options.locale);
        var copy = copyFor(model, english);
        var card = text(documentRef, 'article', 'battlefield-boss-reward-card', '');
        card.setAttribute('aria-live', 'polite');
        card.dataset.f025Status = model.status;
        card.dataset.cosmeticId = model.mapped_cosmetic_id;
        card.dataset.rewardPolicyVersion = model.reward_policy_version;
        card.dataset.entitlementConsumed = String(model.first_clear_entitlement_consumed);
        card.dataset.cosmeticNewlyOwned = String(model.cosmetic_newly_owned);
        card.dataset.alreadyOwnedNoOp = String(model.already_owned_no_op);
        card.dataset.replayed = String(model.entitlement_replayed);

        var header = text(documentRef, 'header', 'battlefield-boss-reward-card__header', '');
        header.append(
            text(documentRef, 'span', 'battlefield-boss-reward-card__eyebrow', copy.eyebrow),
            text(documentRef, 'span', 'battlefield-boss-reward-card__state', copy.state)
        );
        card.appendChild(header);
        card.appendChild(text(documentRef, 'h2', 'battlefield-boss-reward-card__title', copy.title));
        card.appendChild(text(documentRef, 'p', 'battlefield-boss-reward-card__body', copy.body));

        if (model.status !== STATUS.NOT_FIRST_CLEAR) {
            var reward = text(documentRef, 'div', 'battlefield-boss-reward-card__reward', '');
            reward.append(
                text(documentRef, 'span', 'battlefield-boss-reward-card__reward-mark', '◇'),
                text(documentRef, 'span', 'battlefield-boss-reward-card__reward-kind', english ? 'PURE COSMETIC' : '純外觀'),
                text(documentRef, 'code', 'battlefield-boss-reward-card__reward-id', model.mapped_cosmetic_id),
                text(documentRef, 'span', 'battlefield-boss-reward-card__reward-note', copy.entitlement)
            );
            card.appendChild(reward);
        }

        var facts = text(documentRef, 'dl', 'battlefield-boss-reward-card__facts', '');
        function addFact(label, value) {
            facts.append(
                text(documentRef, 'dt', '', label),
                text(documentRef, 'dd', '', value)
            );
        }
        addFact(english ? 'Zone' : '區域', model.zone_key);
        addFact(english ? 'Reward policy' : '獎勵版本', model.reward_policy_version);
        if (model.entitlement_replayed) {
            addFact(english ? 'Delivery' : '傳遞狀態', english ? 'Committed result replay' : '已提交結果重播');
        }
        card.appendChild(facts);
        card.appendChild(text(
            documentRef,
            'p',
            'battlefield-boss-reward-card__power-note',
            english ? 'Cosmetic presentation only · no combat power or replacement reward.' : '純外觀呈現 · 不增加戰鬥能力，也沒有替換獎勵。'
        ));

        container.replaceChildren(card);
        container.hidden = false;
        container.dataset.f025Status = model.status;
        container.dataset.f025Replayed = String(model.entitlement_replayed);
        delete container.dataset.f025Error;
        return { ok: true, model: model, element: card };
    }

    return Object.freeze({
        VERSION: VERSION,
        CONTRACT_VERSION: CONTRACT_VERSION,
        STATUS: STATUS,
        FIELDS: FIELDS,
        normalizeResult: normalizeResult,
        renderResult: renderResult,
        clearResult: clearResult,
    });
}));
