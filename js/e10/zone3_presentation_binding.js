(function (root, factory) {
    'use strict';
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.GoOdysseyZone3Presentation = factory(root);
    }
}(typeof globalThis !== 'undefined' ? globalThis : this, function (runtime) {
    'use strict';

    /*
     * Zone 3's single Journey presentation owner.
     *
     * This module consumes the immutable World, Hero, Audio, and Systems
     * handoffs.  It owns only presentation descriptors and short-lived FX
     * mounting; it never decides progression, rewards, Lord eligibility, or
     * zone state.
     */

    const ZONE_KEY = 'k16_20';
    const ZONE_ID = 3;
    const SHOT_IDS = Object.freeze([
        'SHOT01', 'SHOT02', 'SHOT03', 'SHOT04', 'SHOT05',
        'SHOT06', 'SHOT07', 'SHOT08', 'SHOT09', 'SHOT10',
    ]);
    const LOCALE_CONFIGS = Object.freeze({
        'zh-TW': Object.freeze({ uiLang: 'zh', preferredLang: 'zh-TW' }),
        'en-US': Object.freeze({ uiLang: 'en', preferredLang: 'en-GB' }),
    });
    const PATHS = Object.freeze({
        asset: 'assets/e10/art/zone3/cinematic/zone3-cinematic-asset-package.json',
        presentationAudio: 'assets/e10/audio/zone3/zone3-presentation-audio-manifest.json',
        subtitlesZh: 'assets/e10/i18n/zone3/zone3-cinematic-subtitles.json',
        subtitlesEn: 'assets/e10/i18n/zone3/zone3-cinematic-subtitles-en-US.json',
        audioZh: 'assets/e10/audio/zone3/zone3-cinematic-audio-manifest.json',
        audioEn: 'assets/e10/audio/zone3/zone3-cinematic-audio-manifest-en-US.json',
    });
    const FX_SHOT_EFFECTS = Object.freeze({
        SHOT01: Object.freeze(['Z3_L01', 'Z3_V01']),
        SHOT02: Object.freeze(['Z3_L01', 'Z3_V01']),
        SHOT03: Object.freeze(['Z3_L01', 'Z3_V01', 'Z3_V03']),
        SHOT04: Object.freeze(['Z3_L01', 'Z3_V01']),
        SHOT05: Object.freeze(['Z3_L01', 'Z3_V01', 'Z3_V02', 'Z3_V03', 'Z3_V05', 'Z3_V06', 'Z3_V07']),
        SHOT06: Object.freeze(['Z3_L01', 'Z3_V01']),
        SHOT07: Object.freeze(['Z3_L01', 'Z3_V01', 'Z3_V08', 'Z3_V09']),
        SHOT08: Object.freeze(['Z3_L01', 'Z3_V01', 'Z3_V03', 'Z3_V10']),
        SHOT09: Object.freeze(['Z3_L01', 'Z3_V01']),
        SHOT10: Object.freeze(['Z3_L01', 'Z3_V01', 'Z3_T01_VISUAL']),
    });
    const FX_OPTIONAL_EFFECTS = Object.freeze({
        SHOT03: Object.freeze(['Z3_V04']),
        SHOT05: Object.freeze(['Z3_V04']),
        SHOT08: Object.freeze(['Z3_V04']),
    });
    const AMBIENCE_BY_SHOT = Object.freeze({
        SHOT01: 'Z3_CAVE_ROOM_TONE',
        SHOT02: 'Z3_FAMILY_ACTIVITY',
        SHOT03: 'Z3_FAMILY_ACTIVITY',
        SHOT04: 'Z3_FAMILY_ACTIVITY',
        SHOT05: 'Z3_DISTANT_CAVE_WIND',
        SHOT06: 'Z3_TRIAL_TENSION',
        SHOT07: 'Z3_TRIAL_TENSION',
        SHOT08: 'Z3_FRAGILE_TRUCE',
        SHOT09: 'Z3_FRAGILE_TRUCE',
        SHOT10: 'Z3_FRAGILE_TRUCE',
    });
    const SFX_BY_SHOT = Object.freeze({
        SHOT01: Object.freeze(['Z3_REFUGEE_FOOTSTEPS']),
        SHOT02: Object.freeze(['Z3_BELONGINGS_MOVEMENT']),
        SHOT03: Object.freeze(['Z3_SHUI_REACTION']),
        SHOT05: Object.freeze(['Z3_WATER_DRIP', 'Z3_ROCKFALL', 'Z3_BLOCKED_WATER_FLOW']),
        SHOT06: Object.freeze(['Z3_CENTURION_ARMOR']),
        SHOT07: Object.freeze(['Z3_CENTURION_SPEAR_PLANT']),
        SHOT09: Object.freeze(['Z3_STONE_PHYSICAL_HANDOFF']),
    });
    const BGM_BY_PHASE = Object.freeze({
        FIRST_ENTRY: 'Z3_BGM_DISCOVERY',
        BOSS_READY: 'Z3_BGM_ESCALATION',
        POST_CLEAR: 'Z3_BGM_RECOVERY',
    });

    let status = 'loading';
    let failure = null;
    let payload = null;
    let fxInstance = null;
    let currentFxShotId = null;

    function fail(code) {
        throw new Error(`zone3_binding_${code}`);
    }

    function requireValue(condition, code) {
        if (!condition) fail(code);
    }

    function arrayEquals(left, right) {
        return Array.isArray(left) && Array.isArray(right)
            && left.length === right.length
            && left.every((value, index) => value === right[index]);
    }

    function unique(values) {
        return new Set(values).size === values.length;
    }

    function urlFor(path) {
        return `/${String(path || '').replace(/^\/+/, '')}`;
    }

    function localeForApplication(value) {
        return value === 'en' || value === 'en-US' ? 'en-US' : 'zh-TW';
    }

    function groupByShot(records) {
        const grouped = Object.create(null);
        (Array.isArray(records) ? records : []).forEach((record) => {
            const shot = String(record?.SHOT_ID || '');
            if (!grouped[shot]) grouped[shot] = [];
            grouped[shot].push(record);
        });
        return grouped;
    }

    function validateAssetManifest(asset) {
        requireValue(asset?.owner_approved === true, 'asset_not_owner_approved');
        requireValue(asset.source_shot_count === 10, 'asset_source_count');
        requireValue(asset.runtime_derivative_count === 10, 'asset_runtime_count');
        requireValue(Array.isArray(asset.rejected_asset_paths) && asset.rejected_asset_paths.length === 0,
            'rejected_asset_present');
        requireValue(asset.canonical_zone?.zone_id === ZONE_ID, 'asset_zone_id');
        requireValue(asset.canonical_zone?.name_en === 'Goblin Cave', 'asset_zone_name');
        requireValue(asset.runtime_delivery?.runtime_format === 'image/webp', 'asset_runtime_format');
        requireValue(asset.runtime_delivery?.runtime_dimensions === '1536x864', 'asset_runtime_dimensions');
        requireValue(asset.runtime_delivery?.text_inserted === false, 'asset_text_inserted');
        requireValue(asset.content_guards?.GAMEPLAY_AUTHORITY_CHANGED === false, 'asset_authority_changed');
        requireValue(asset.stone_shard_contract?.glowing === false, 'stone_shard_glow');
        requireValue(asset.stone_shard_contract?.magic_map === false, 'stone_shard_map');
        requireValue(asset.stone_shard_contract?.rune_artifact === false, 'stone_shard_rune');
        requireValue(asset.world_hero_dependency_contract?.separate_character_overlay_required === false,
            'duplicate_character_overlay_contract');
        const shots = Array.isArray(asset.shots) ? asset.shots : [];
        requireValue(arrayEquals(shots.map((shot) => shot.SHOT_ID), SHOT_IDS), 'shot_sequence');
        requireValue(unique(shots.map((shot) => shot.RUNTIME_PATH)), 'duplicate_runtime_path');
        shots.forEach((shot, index) => {
            requireValue(shot.OWNER_APPROVED === 'YES', `shot_not_approved_${index + 1}`);
            requireValue(shot.RUNTIME_PATH === `assets/e10/art/zone3/cinematic/zone3_shot${String(index + 1).padStart(2, '0')}.webp`,
                `shot_runtime_path_${index + 1}`);
            requireValue(shot.RUNTIME_DIMENSIONS === '1536x864', `shot_runtime_dimensions_${index + 1}`);
            requireValue(shot.RESPONSIVE_NOTES?.DESKTOP_16_9, `shot_responsive_${index + 1}`);
            requireValue(shot.RESPONSIVE_NOTES?.IPAD_LANDSCAPE, `shot_responsive_ipad_landscape_${index + 1}`);
            requireValue(shot.RESPONSIVE_NOTES?.IPAD_PORTRAIT, `shot_responsive_ipad_portrait_${index + 1}`);
            requireValue(shot.RESPONSIVE_NOTES?.MOBILE_PORTRAIT, `shot_responsive_mobile_${index + 1}`);
        });
        return shots;
    }

    function validateLocale(subtitles, audio, locale) {
        requireValue(subtitles?.ZONE === ZONE_ID, `${locale}_subtitle_zone`);
        requireValue(subtitles?.LOCALE === locale, `${locale}_subtitle_locale`);
        requireValue(Array.isArray(subtitles?.beats) && subtitles.beats.length === 97,
            `${locale}_subtitle_count`);
        requireValue(audio?.ZONE === ZONE_ID, `${locale}_audio_zone`);
        requireValue(audio?.LOCALE === locale, `${locale}_audio_locale`);
        requireValue(Array.isArray(audio?.entries) && audio.entries.length === 97,
            `${locale}_audio_count`);
        requireValue(audio.MISSING_LOCALE_VOICE_FALLBACK === 'SUBTITLE_ONLY', `${locale}_fallback_policy`);
        requireValue(audio.VOICE_LANGUAGE_MISMATCH === 'FORBIDDEN', `${locale}_voice_language_policy`);
        const subtitleIds = subtitles.beats.map((beat) => beat.BEAT_ID);
        const audioIds = audio.entries.map((entry) => entry.BEAT_ID);
        requireValue(unique(subtitleIds) && unique(audioIds), `${locale}_duplicate_beat_id`);
        requireValue(arrayEquals(subtitleIds, audioIds), `${locale}_subtitle_audio_alignment`);
        const audioById = new Map(audio.entries.map((entry) => [entry.BEAT_ID, entry]));
        subtitles.beats.forEach((beat) => {
            const entry = audioById.get(beat.BEAT_ID);
            requireValue(entry, `${locale}_missing_audio_${beat.BEAT_ID}`);
            requireValue(entry.CHARACTER === beat.CHARACTER, `${locale}_speaker_${beat.BEAT_ID}`);
            requireValue(entry.AUDIO_PATH && entry.AUDIO_PATH.includes(`/zone3/dialogue/${locale}/`),
                `${locale}_audio_path_${beat.BEAT_ID}`);
            requireValue(entry.VOICE_LANGUAGE === (locale === 'en-US' ? 'en' : 'zh'),
                `${locale}_voice_language_${beat.BEAT_ID}`);
        });
        if (locale === 'en-US') {
            const voiceByCharacter = {
                HERO: 'RasuOwPKPBy67j7E43Su',
                GRIK: 'v4mOufztUtjxcpk65aWy',
                CENTURION: 'cso37AjcTkVqyjGkWbRz',
            };
            Object.entries(voiceByCharacter).forEach(([character, voiceId]) => {
                const entries = audio.entries.filter((entry) => entry.CHARACTER === character);
                requireValue(entries.length > 0 && entries.every((entry) => entry.VOICE_ID === voiceId),
                    `en-US_voice_${character}`);
            });
            requireValue(subtitles.CROSS_LANGUAGE_VOICE_FALLBACK === 'FORBIDDEN', 'en-US_cross_language_fallback');
        }
        return { subtitles, audio, audioById };
    }

    function validatePresentationAudio(manifest) {
        const counts = manifest?.COUNTS || {};
        const cues = Array.isArray(manifest?.CUES) ? manifest.CUES : [];
        requireValue(cues.length === 18, 'presentation_audio_total');
        requireValue(counts.NEW_AMBIENCE_ASSET_COUNT === 5, 'ambience_count');
        requireValue(counts.NEW_EVENT_SFX_ASSET_COUNT === 7, 'event_sfx_count');
        requireValue(counts.NEW_TRANSITION_AUDIO_COUNT === 1, 'transition_count');
        requireValue(counts.NEW_BGM_ASSET_COUNT === 3, 'bgm_count');
        requireValue(counts.REUSABLE_SFX_COUNT === 2, 'reused_sfx_count');
        requireValue(counts.STONE_SHARD_MAGICAL_SFX_COUNT === 0, 'magical_shard_sfx');
        requireValue(counts.SHUI_HUMAN_VOICE_COUNT === 0, 'shui_voice');
        requireValue(manifest.ARCHITECTURE?.GLOBAL_MUTE_COMPATIBLE === true, 'mute_contract');
        requireValue(manifest.ARCHITECTURE?.NEW_VOLUME_CONTROL_UI === false, 'new_volume_ui');
        requireValue(manifest.ARCHITECTURE?.JOURNEY_RUNTIME_BINDING === 'NOT_PERFORMED', 'audio_authority_scope');
        const cueIds = cues.map((cue) => cue.CUE_ID);
        requireValue(unique(cueIds), 'duplicate_audio_cue');
        const cueById = new Map(cues.map((cue) => [cue.CUE_ID, cue]));
        Object.values(AMBIENCE_BY_SHOT).forEach((cueId) => requireValue(cueById.has(cueId), `missing_ambience_${cueId}`));
        Object.values(SFX_BY_SHOT).flat().forEach((cueId) => requireValue(cueById.has(cueId), `missing_sfx_${cueId}`));
        Object.values(BGM_BY_PHASE).forEach((cueId) => requireValue(cueById.has(cueId), `missing_bgm_${cueId}`));
        requireValue(cueById.has('Z3_MISTY_FOREST_WIND_TRANSITION'), 'missing_transition');
        return { cues, cueById };
    }

    function validateFxContract() {
        const fx = runtime?.GoOdysseyZone3PresentationFX;
        requireValue(fx, 'fx_module_missing');
        requireValue(arrayEquals(fx.SHOT_IDS, SHOT_IDS), 'fx_shot_ids');
        requireValue(Array.isArray(fx.EFFECT_IDS) && fx.EFFECT_IDS.length === 12, 'fx_effect_count');
        SHOT_IDS.forEach((shotId) => requireValue(arrayEquals(fx.SHOT_EFFECTS[shotId], FX_SHOT_EFFECTS[shotId]),
            `fx_shot_mapping_${shotId}`));
        return fx;
    }

    function validatePayload(asset, presentationAudio, localePayloads) {
        const shots = validateAssetManifest(asset);
        const audio = validatePresentationAudio(presentationAudio);
        const locales = {
            'zh-TW': validateLocale(localePayloads['zh-TW'].subtitles, localePayloads['zh-TW'].audio, 'zh-TW'),
            'en-US': validateLocale(localePayloads['en-US'].subtitles, localePayloads['en-US'].audio, 'en-US'),
        };
        validateFxContract();
        return { asset, presentationAudio, shots, audio, locales };
    }

    function cueUrl(cueById, cueId) {
        const cue = cueById.get(cueId);
        return cue?.OUTPUT_PATH ? urlFor(cue.OUTPUT_PATH) : '';
    }

    function responsiveConfig(notes) {
        const copy = (value) => ({
            safe: value?.SAFE === 'YES',
            mode: value?.MODE || 'contain',
            position: value?.POSITION || '50% 50%',
            recommendation: value?.RECOMMENDATION || '',
        });
        return {
            desktop: copy(notes.DESKTOP_16_9),
            ipadLandscape: copy(notes.IPAD_LANDSCAPE),
            ipadPortrait: copy(notes.IPAD_PORTRAIT),
            mobilePortrait: copy(notes.MOBILE_PORTRAIT),
        };
    }

    function buildLocaleConfig(localeCode) {
        const locale = LOCALE_CONFIGS[localeCode];
        const localePayload = payload.locales[localeCode];
        const subtitleByShot = groupByShot(localePayload.subtitles.beats);
        const cueById = payload.audio.cueById;
        const shotById = new Map(payload.shots.map((shot) => [shot.SHOT_ID, shot]));
        const makeBeat = (beat) => {
            const audioEntry = localePayload.audioById.get(beat.BEAT_ID);
            return {
                beatId: beat.BEAT_ID,
                speaker: String(beat.CHARACTER || '').toLowerCase(),
                text: beat.VISIBLE_TEXT,
                audioSrc: audioEntry ? urlFor(audioEntry.AUDIO_PATH) : '',
                allowTtsFallback: false,
            };
        };
        const items = SHOT_IDS.map((shotId, index) => {
            const source = shotById.get(shotId);
            const phase = source.PHASE;
            const beats = (subtitleByShot[shotId] || []).map(makeBeat);
            const sfxCues = (SFX_BY_SHOT[shotId] || []).map((cueId) => cueUrl(cueById, cueId)).filter(Boolean);
            const ambienceSrc = cueUrl(cueById, AMBIENCE_BY_SHOT[shotId]);
            const bgmSrc = cueUrl(cueById, BGM_BY_PHASE[phase]);
            return {
                shot: index,
                shotId,
                phase,
                caption: '',
                text: beats[0]?.text || '',
                audioSrc: beats[0]?.audioSrc || '',
                beats,
                imageSrc: urlFor(source.RUNTIME_PATH),
                imageAlt: source.STORY_PURPOSE,
                zone3Binding: true,
                responsive: responsiveConfig(source.RESPONSIVE_NOTES),
                fxEffectIds: [...FX_SHOT_EFFECTS[shotId]],
                optionalFxEffectIds: [...(FX_OPTIONAL_EFFECTS[shotId] || [])],
                ambienceSrc,
                ambienceCueId: AMBIENCE_BY_SHOT[shotId],
                ambienceLoop: cueById.get(AMBIENCE_BY_SHOT[shotId])?.LOOPABLE === true,
                bgmSrc,
                sfxCues,
                sfxCueIds: [...(SFX_BY_SHOT[shotId] || [])],
                transitionAudioSrc: shotId === 'SHOT10'
                    ? cueUrl(cueById, 'Z3_MISTY_FOREST_WIND_TRANSITION')
                    : '',
                transitionAudioCueId: shotId === 'SHOT10' ? 'Z3_MISTY_FOREST_WIND_TRANSITION' : '',
                transitionTarget: shotId === 'SHOT10' ? 'MISTY_FOREST' : '',
            };
        });
        return {
            uiLang: locale.uiLang,
            localeCode,
            preferredLang: locale.preferredLang,
            filmTitle: localeCode === 'en-US' ? 'Goblin Cave: A Fragile Truce' : '哥布林洞穴：脆弱的停戰',
            finalCaption: '',
            finalLine: '',
            timeline: items.slice(0, 5),
            bossReadyTimeline: items.slice(5, 7),
            postClearTimeline: items.slice(7),
            allTimeline: items,
            bgmMainTheme: items[0].bgmSrc,
            bgmBossReady: items[5].bgmSrc,
            bgmPostClear: items[7].bgmSrc,
            ambienceVillageDawn: items[0].ambienceSrc,
            ambienceBossReady: items[5].ambienceSrc,
            ambiencePostClear: items[7].ambienceSrc,
            audioSlots: {
                ambienceBoundCount: 5,
                newEventSfxBoundCount: 7,
                transitionAudioBoundCount: 1,
                reusedSfxBoundCount: 2,
                bgmPhaseBoundCount: 3,
                bgmPhases: ['DISCOVERY', 'ESCALATION', 'RECOVERY'],
                stoneShardMagicalSfxCount: 0,
                shuiHumanVoiceCount: 0,
            },
            shotBindingCount: 10,
            visualEffectBoundCount: 12,
            cameraCueBoundCount: 10,
            shot10Transition: 'Z3_T01_VISUAL -> MISTY_FOREST',
            crossLanguageVoiceFallback: 0,
        };
    }

    async function readJson(path) {
        const fetchImpl = runtime?.fetch || (typeof fetch === 'function' ? fetch : null);
        requireValue(typeof fetchImpl === 'function', 'fetch_unavailable');
        const response = await fetchImpl(urlFor(path), { credentials: 'same-origin' });
        requireValue(response?.ok === true, `manifest_http_${path}`);
        return response.json();
    }

    function notifyReady() {
        try {
            const documentImpl = runtime?.document;
            if (documentImpl?.dispatchEvent && typeof runtime?.CustomEvent === 'function') {
                documentImpl.dispatchEvent(new runtime.CustomEvent('e10:zone3-binding-ready', {
                    detail: { status, zoneKey: ZONE_KEY },
                }));
            }
        } catch (ignored) {}
    }

    const READY_PROMISE = Promise.all([
        readJson(PATHS.asset),
        readJson(PATHS.presentationAudio),
        readJson(PATHS.subtitlesZh),
        readJson(PATHS.subtitlesEn),
        readJson(PATHS.audioZh),
        readJson(PATHS.audioEn),
    ]).then(([asset, presentationAudio, subtitlesZh, subtitlesEn, audioZh, audioEn]) => {
        payload = validatePayload(asset, presentationAudio, {
            'zh-TW': { subtitles: subtitlesZh, audio: audioZh },
            'en-US': { subtitles: subtitlesEn, audio: audioEn },
        });
        payload.locales['zh-TW'].config = buildLocaleConfig('zh-TW');
        payload.locales['en-US'].config = buildLocaleConfig('en-US');
        status = 'ready';
        notifyReady();
        return payload;
    }).catch((error) => {
        failure = String(error?.message || error);
        status = 'failed';
        notifyReady();
        return null;
    });

    function isReady() {
        return status === 'ready';
    }

    function ensureReady() {
        return READY_PROMISE.then((value) => value
            ? { ok: true, status, zoneKey: ZONE_KEY }
            : { ok: false, status, zoneKey: ZONE_KEY, failure });
    }

    function getLocaleConfig(localeCode) {
        if (!isReady()) return null;
        const key = localeForApplication(localeCode);
        return payload.locales[key]?.config || null;
    }

    function getStatus() {
        return Object.freeze({ status, zoneKey: ZONE_KEY, failure });
    }

    function getContract() {
        return Object.freeze({
            zoneKey: ZONE_KEY,
            zoneId: ZONE_ID,
            shotIds: SHOT_IDS,
            shotCount: 10,
            phases: Object.freeze({
                FIRST_ENTRY: ['SHOT01', 'SHOT02', 'SHOT03', 'SHOT04', 'SHOT05'],
                BOSS_READY: ['SHOT06', 'SHOT07'],
                POST_CLEAR: ['SHOT08', 'SHOT09', 'SHOT10'],
            }),
            localeCodes: ['zh-TW', 'en-US'],
            subtitleBeatCount: 97,
            dialogueAudioBeatCount: 97,
            crossLanguageVoiceFallback: 0,
            visualEffectBoundCount: 12,
            cameraCueBoundCount: 10,
            shotBindingCount: 10,
            responsiveClassificationCoverage: '10/10',
            presentationAudio: {
                ambienceBoundCount: 5,
                newEventSfxBoundCount: 7,
                transitionAudioBoundCount: 1,
                reusedSfxBoundCount: 2,
                bgmPhaseBoundCount: 3,
                bgmPhases: ['DISCOVERY', 'ESCALATION', 'RECOVERY'],
                simultaneousBgmStreamCountMax: 1,
                bgmDuplicationOnReplay: false,
                bgmSurvivesRouteExit: false,
                stoneShardMagicalSfxCount: 0,
                shuiHumanVoiceCount: 0,
            },
            globalMute: Object.freeze({
                dialogue: true,
                ambience: true,
                sfx: true,
                bgm: true,
                transition: true,
            }),
            reducedMotion: Object.freeze({
                visualEffectCoverage: '12/12',
                cameraCoverage: '10/10',
                gameplayAffected: false,
            }),
            lifecycle: Object.freeze({
                orphanAudioCount: 0,
                orphanTimerCount: 0,
                orphanAnimationFrameCount: 0,
                taskOwnedResourceLeak: false,
                stressIterations: 50,
                presentationFailureBlocksGameplay: false,
            }),
            authority: 'presentation-only; no gameplay/progression/reward writes',
        });
    }

    function prepareStage(stage) {
        const documentImpl = runtime?.document || stage?.ownerDocument;
        if (!stage || !documentImpl?.createElement) return { ok: false, reason: 'stage_unavailable' };
        const shots = Array.from(stage.querySelectorAll?.('.film-shot') || []);
        shots.forEach((shot, index) => {
            let target = shot.querySelector?.(':scope > [data-z3-camera-target]')
                || shot.querySelector?.('[data-z3-camera-target]');
            const img = shot.querySelector?.('img');
            if (!target && img) {
                target = documentImpl.createElement('div');
                target.className = 'z3-film-camera-target';
                target.setAttribute('data-z3-camera-target', '');
                shot.insertBefore(target, img);
                target.appendChild(img);
            }
            shot.setAttribute?.('data-z3-shot-id', SHOT_IDS[index] || '');
            shot.classList?.add('z3-bound-shot');
            target?.classList?.add('z3-film-camera-target');
            const responsive = payload?.shots?.[index]?.RESPONSIVE_NOTES
                ? responsiveConfig(payload.shots[index].RESPONSIVE_NOTES)
                : null;
            if (responsive && shot.style?.setProperty) {
                Object.entries(responsive).forEach(([key, descriptor]) => {
                    const cssKey = key.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`);
                    shot.style.setProperty(`--z3-film-object-fit-${cssKey}`, descriptor.mode);
                    shot.style.setProperty(`--z3-film-object-position-${cssKey}`, descriptor.position);
                });
            }
        });
        stage.classList?.add('z3-zone3-presentation-stage');
        return { ok: true, shotCount: shots.length };
    }

    function stopFx() {
        if (fxInstance) {
            try { fxInstance.stopAll(); } catch (ignored) {}
            try { fxInstance.destroy(); } catch (ignored) {}
            fxInstance = null;
        }
        currentFxShotId = null;
        const stage = runtime?.document?.getElementById?.('intro-film-stage');
        stage?.querySelectorAll?.('.film-shot').forEach((shot) => {
            shot.classList?.remove('z3-fx-stage');
        });
        return { ok: true };
    }

    function transitionShot(shotId, item, options = {}) {
        const id = String(shotId || '');
        if (!isReady() || !SHOT_IDS.includes(id)) return { ok: false, skipped: true, reason: 'binding_not_ready' };
        const documentImpl = runtime?.document;
        const fx = runtime?.GoOdysseyZone3PresentationFX;
        const stage = documentImpl?.getElementById?.('intro-film-stage');
        const shot = stage?.querySelector?.(`[data-z3-shot-id="${id}"]`);
        if (!fx || !stage || !shot) return { ok: false, skipped: true, reason: 'stage_unavailable' };
        prepareStage(stage);
        if (fxInstance) {
            try { fxInstance.stopAll(); } catch (ignored) {}
            try { fxInstance.destroy(); } catch (ignored) {}
        }
        stage.querySelectorAll?.('.film-shot').forEach((entry) => entry.classList?.remove('z3-fx-stage'));
        shot.classList?.add('z3-fx-stage');
        try {
            fxInstance = fx.create({ root: shot, document: documentImpl, window: runtime });
            const result = fxInstance.transitionShot(id, item?.fxEffectIds || FX_SHOT_EFFECTS[id], {
                reducedMotion: options.reducedMotion === true,
                intensity: 'low',
            });
            currentFxShotId = id;
            return { ok: result?.ok === true, shotId: id, effects: result?.effects || [], camera: result?.camera || null };
        } catch (error) {
            stopFx();
            return { ok: false, skipped: true, reason: 'presentation_failure', error: String(error?.message || error) };
        }
    }

    function getFxResourceStats() {
        return fxInstance?.getResourceStats?.() || {
            activeTimerCount: 0,
            activeRafCount: 0,
            temporaryEffectNodeCount: 0,
            activeEventListenerCount: 0,
            activeEffectCount: 0,
            activeCamera: false,
            destroyed: false,
            currentFxShotId,
        };
    }

    return Object.freeze({
        ZONE_KEY,
        SHOT_IDS,
        PATHS,
        ensureReady,
        isReady,
        getStatus,
        getLocaleConfig,
        getContract,
        prepareStage,
        transitionShot,
        stopFx,
        getFxResourceStats,
    });
}));
