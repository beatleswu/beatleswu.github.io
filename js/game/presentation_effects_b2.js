/**
 * B2 response-presentation effects.
 *
 * The adapter consumes an accepted, read-only response snapshot.  All
 * dependencies are injected so this module cannot acquire review,
 * progression, battle, or durable-write authority by accident.
 */
(function (global) {
    'use strict';

    function errorDetails(error) {
        return {
            errorType: error?.name || 'Error',
            message: error?.message || String(error || ''),
        };
    }

    function create(dependencies) {
        const deps = dependencies || {};

        function dispatch(data, grade = 0, options = {}) {
            if (!data || data.ok !== true) {
                return { ok: false, skipped: true, failures: [] };
            }

            const failures = [];
            const onError = typeof options.onError === 'function'
                ? options.onError
                : (typeof deps.onError === 'function' ? deps.onError : null);
            const scope = options.scope || deps.scope || null;
            const documentImpl = options.document || deps.document || global.document;
            const setTimer = options.setTimeout || deps.setTimeout || global.setTimeout;
            const fetchImpl = options.fetch || deps.fetch
                || (typeof global.fetch === 'function' ? global.fetch.bind(global) : null);

            const reportFailure = (stage, error) => {
                const failure = { stage, ...errorDetails(error) };
                failures.push(failure);
                if (onError) {
                    try { onError(failure); } catch (observerError) { /* diagnostics only */ }
                }
            };

            const invoke = (stage, callback, ...args) => {
                if (typeof callback !== 'function') return undefined;
                try {
                    const result = callback(...args);
                    if (result && typeof result.catch === 'function') {
                        result.catch(error => reportFailure(stage, error));
                    }
                    return result;
                } catch (error) {
                    reportFailure(stage, error);
                    return undefined;
                }
            };

            const scopeIsCurrent = () => {
                if (!scope) return true;
                try {
                    if (typeof scope.isCurrent === 'function') {
                        return scope.isCurrent() !== false;
                    }
                    return scope.active !== false && scope.valid !== false;
                } catch (error) {
                    reportFailure('presentation_scope', error);
                    return false;
                }
            };

            const dispatchLater = (stage, callback, delay = 0) => {
                if (typeof setTimer !== 'function') {
                    reportFailure(stage, new Error('presentation_timer_unavailable'));
                    return null;
                }
                try {
                    return setTimer(() => {
                        if (!scopeIsCurrent()) return;
                        invoke(stage, callback);
                    }, delay);
                } catch (error) {
                    reportFailure(stage, error);
                    return null;
                }
            };

            const getLang = () => {
                if (typeof deps.getLang === 'function') {
                    try { return deps.getLang(); } catch (error) {
                        reportFailure('presentation_locale', error);
                    }
                }
                try {
                    return deps.i18n && typeof deps.i18n.getLang === 'function'
                        ? deps.i18n.getLang()
                        : '';
                } catch (error) {
                    reportFailure('presentation_locale', error);
                    return '';
                }
            };

            const isEnglish = () => getLang() === 'en';

            const translate = (key, fallback) => {
                try {
                    if (deps.i18n && typeof deps.i18n.t === 'function') {
                        return deps.i18n.t(key);
                    }
                } catch (error) {
                    reportFailure('shield_status', error);
                }
                return fallback;
            };

            const renderXpGain = () => {
                const lastGain = documentImpl?.getElementById?.('xp-last-gain');
                if (!lastGain) return;
                const english = isEnglish();
                const mult = data.combo_mult && data.combo_mult > 1
                    ? (english
                        ? ` · Combo ×${Number(data.combo_mult).toFixed(1)}`
                        : `，連擊 ×${Number(data.combo_mult).toFixed(1)}`)
                    : '';
                const petPart = data.pet_xp_added > 0
                    ? ` · 🐾+${data.pet_xp_added}`
                    : '';
                lastGain.textContent = `+${data.xp_gain} XP${mult}${petPart}`;
            };

            const refreshXpStatus = () => {
                if (typeof fetchImpl !== 'function') {
                    reportFailure('xp_status', new Error('presentation_fetch_unavailable'));
                    return;
                }
                let request;
                try {
                    request = fetchImpl('/api/xp/status', { credentials: 'include' });
                } catch (error) {
                    reportFailure('xp_status', error);
                    return;
                }
                Promise.resolve(request)
                    .then(response => {
                        if (response?.ok === false) {
                            throw new Error(`xp_status_${response.status}`);
                        }
                        return response.json();
                    })
                    .then(payload => {
                        invoke('xp_status', deps.updateXpHud,
                            payload?.xp,
                            payload?.rank_level,
                            payload?.rank_pct,
                            payload);
                        invoke('xp_status', deps.popRankBadge);
                    })
                    .catch(error => reportFailure('xp_status', error));
            };

            // B2 effect keys: shield_status, xp_gain_and_hud,
            // rank_up_presentation, streak_sound, monster_presentation,
            // pet_reaction, pet_status_and_xp_marker, player_hp_presentation,
            // sp_presentation, loot_toast, appearance_loot,
            // new_appearance_items, quest_panel, quest_pet_reward_toast.
            if (data.shield_used) {
                invoke('shield_status', deps.setMessage,
                    translate('shop.shieldUsed', 'shop.shieldUsed'), 'ok');
                invoke('shield_status', deps.refreshShopStatus);
            }

            if (grade >= 3 && data.xp_gain) {
                invoke('xp_gain_and_hud', deps.spawnXpFloat,
                    data.xp_gain, data.combo_mult);
                invoke('xp_gain_and_hud', renderXpGain);
                if (data.ranked_up && data.new_rank_level) {
                    invoke('rank_up_presentation', deps.showRankUpPopup,
                        data.new_rank_level, data);
                } else {
                    const comboStreak = data.combo_streak || 0;
                    let sound = null;
                    if (comboStreak === 3) sound = 'streak3';
                    else if (comboStreak === 7) sound = 'streak7';
                    else if (comboStreak >= 5 && comboStreak % 5 === 0) sound = 'streak5';
                    if (sound) invoke('streak_sound', deps.playSound, sound);
                }
                refreshXpStatus();
            }

            if (data.monster) {
                let adventurePractice = false;
                if (typeof deps.isAdventureZonePractice === 'function') {
                    try { adventurePractice = deps.isAdventureZonePractice() === true; }
                    catch (error) { reportFailure('monster_presentation', error); }
                }
                if (!adventurePractice) {
                    invoke('monster_presentation', deps.updateMonsterUI, data.monster);
                    let monsterType = data.monster.type;
                    if (!monsterType && typeof deps.getLastMonsterType === 'function') {
                        try { monsterType = deps.getLastMonsterType(); }
                        catch (error) { reportFailure('monster_presentation', error); }
                    }
                    if (data.monster.defeated) {
                        invoke('monster_presentation', deps.monsterSpeakDie, monsterType);
                    } else if (grade >= 3 && data.monster.dmg > 0) {
                        const pct = data.monster.max_hp > 0
                            ? Math.round(data.monster.hp / data.monster.max_hp * 100)
                            : 100;
                        invoke('monster_presentation', deps.monsterSpeakHurt,
                            monsterType, pct);
                    }
                }
            }

            let quizPet = null;
            if (typeof deps.getQuizPet === 'function') {
                try { quizPet = deps.getQuizPet(); }
                catch (error) { reportFailure('pet_reaction', error); }
            }
            if (quizPet) {
                if (grade >= 3) {
                    if (data.ranked_up) {
                        dispatchLater('pet_levelup', () => invoke(
                            'pet_reaction', deps.petReact, 'levelup'), 700);
                    } else if (data.monster && data.monster.defeated) {
                        dispatchLater('pet_victory', () => invoke(
                            'pet_reaction', deps.petReact, 'victory'), 650);
                    } else if (data.combo_streak && data.combo_streak % 5 === 0) {
                        invoke('pet_reaction', deps.petReact, 'combo');
                    } else {
                        invoke('pet_reaction', deps.petReact, 'correct');
                    }
                } else {
                    invoke('pet_reaction', deps.petReact, 'wrong');
                }
            }

            if (quizPet && grade >= 3 && Number(data.pet_xp_gained || 0) > 0) {
                invoke('pet_status_and_xp_marker', deps.showQuizPetMarker,
                    '+1', 'xp', Number(data.combo_streak || 0));
            }
            if (data.pet) {
                invoke('pet_status_and_xp_marker', deps.updateQuizPetStatusBadge, {
                    pet: data.pet,
                    practice: data.practice || {
                        active: Number(data.pet.fullness || 0) > 0,
                        ready: false,
                    },
                });
                if (Number(data.pet.fullness || 0) <= 0) {
                    invoke('pet_status_and_xp_marker', deps.showQuizPetMarker,
                        isEnglish() ? 'Feed' : '餵食', 'food');
                }
            }

            if (data.player) {
                invoke('player_hp_presentation', deps.updatePlayerHPUI, data.player);
            }
            if (data.sp) {
                invoke('sp_presentation', deps.updateSPUI, data.sp.current);
            }

            if (data.loot) {
                invoke('loot_toast', deps.showLootToast, data.loot);
            }
            if (data.appearance_loot) {
                dispatchLater('appearance_loot', () => invoke(
                    'appearance_loot', deps.showAppearToast, data.appearance_loot),
                data.loot ? 1800 : 0);
            }
            if (Array.isArray(data.new_appearance_items) && data.new_appearance_items.length) {
                const delay = (data.loot ? 1800 : 0)
                    + (data.appearance_loot ? 1800 : 0);
                data.new_appearance_items.forEach((item, index) => {
                    dispatchLater('new_appearance_items', () => invoke(
                        'new_appearance_items', deps.showAppearToast, item),
                    delay + index * 1800);
                });
            }

            if (data.quest_updates) {
                invoke('quest_panel', deps.updateQuestPanel, data.quest_updates);
                const baseDelay = (data.loot || data.appearance_loot) ? 1800 : 0;
                const rewards = (Array.isArray(data.quest_updates) ? data.quest_updates : [])
                    .map(quest => quest && quest.pet_reward)
                    .filter(Boolean);
                rewards.forEach((reward, index) => {
                    dispatchLater('quest_pet_reward_toast', () => {
                        const english = isEnglish();
                        const name = english
                            ? (reward.name_en || reward.name || reward.item_key || 'Pet Food')
                            : (reward.name || reward.item_key || '寵物食物');
                        const qty = Number(reward.qty || 1);
                        const label = english ? 'Companion Food' : '寵物夥伴食物';
                        invoke('quest_pet_reward_toast', deps.showItemToast,
                            'pet-toast', '🍬', `${name} × ${qty}`, label);
                    }, baseDelay + index * 900);
                });
            }

            return { ok: failures.length === 0, skipped: false, failures };
        }

        return { dispatch };
    }

    const api = { create, dispatch: (data, grade, options) =>
        create(options?.dependencies || options || {}).dispatch(data, grade, options) };
    global.GoOdysseyPresentationEffectsB2 = api;
})(typeof window !== 'undefined' ? window : globalThis);
