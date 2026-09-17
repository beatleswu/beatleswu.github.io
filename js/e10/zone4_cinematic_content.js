(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory(null);
        return;
    }
    root.Zone4CinematicContent = factory(root);
}(typeof window !== 'undefined' ? window : this, function (browserRoot) {
    'use strict';

    var MANIFEST_PATH = '/ZONE4_RUNTIME_MANIFEST.json';
    var MANIFEST_SCHEMA = 'GO_ODYSSEY_ZONE4_OWNER_FINAL_STORY_RUNTIME_INTEGRATION_V1';
    var MAIN_STORY_COUNT = 22;
    var LORD_REVIEW_COUNT = 6;
    var SUPPORTED_LOCALES = ['zh-TW', 'en-GB'];
    var OLD_STORYBOARD_PREFIX = '/assets/storyboards/';
    var CINEMATIC_PREFIX = 'assets/e10/art/zone4/cinematic/';
    var AUDIO_PREFIXES = ['assets/e10/audio/zone4/', 'assets/e10/audio/shared/'];

    function asArray(value) {
        return Array.isArray(value) ? value : [];
    }

    function isRecord(value) {
        return !!value && typeof value === 'object' && !Array.isArray(value);
    }

    function fail(message) {
        throw new Error('Zone4 cinematic manifest rejected: ' + message);
    }

    function assertSafeAssetPath(path, kind) {
        if (typeof path !== 'string' || !path.trim()) fail(kind + ' path missing');
        if (path[0] === '/' || path.indexOf('://') !== -1 || path.indexOf('\\') !== -1) {
            fail(kind + ' path must be a local release path');
        }
        if (path.split('/').indexOf('..') !== -1) fail(kind + ' path traversal');
        if (path.indexOf(OLD_STORYBOARD_PREFIX.slice(1)) === 0 || path.indexOf(OLD_STORYBOARD_PREFIX) === 0) {
            fail(kind + ' path points at legacy storyboard content');
        }
    }

    function assertAudioAsset(asset, kind) {
        if (!asset) return;
        if (!isRecord(asset)) fail(kind + ' must be an object');
        assertSafeAssetPath(asset.path, kind);
        if (!AUDIO_PREFIXES.some(function (prefix) { return asset.path.indexOf(prefix) === 0; })) {
            fail(kind + ' path is outside the governed Zone4 audio closure');
        }
        if (typeof asset.sha256 !== 'string' || !/^[a-f0-9]{64}$/i.test(asset.sha256)) {
            fail(kind + ' SHA-256 missing');
        }
    }

    function validateDialogue(line, beatIndex) {
        if (!isRecord(line) || typeof line.line_id !== 'string') {
            fail('dialogue line ' + beatIndex + ' is malformed');
        }
        if (!isRecord(line.text)) fail(line.line_id + ' text is missing');
        if (!SUPPORTED_LOCALES.every(function (locale) { return typeof line.text[locale] === 'string'; })) {
            fail(line.line_id + ' must carry both supported locale texts');
        }
        if (!isRecord(line.voice_by_locale)) fail(line.line_id + ' voice mapping is missing');
        SUPPORTED_LOCALES.forEach(function (locale) {
            var voice = line.voice_by_locale[locale];
            if (!voice) fail(line.line_id + ' ' + locale + ' voice is missing');
            assertAudioAsset(voice, line.line_id + ' ' + locale + ' voice');
        });
    }

    function validateBeat(beat, index) {
        if (!isRecord(beat) || typeof beat.beat_id !== 'string') fail('main beat ' + index + ' is malformed');
        if (beat.track !== 'main_story') fail(beat.beat_id + ' is not a main_story beat');
        if (!isRecord(beat.visual)) fail(beat.beat_id + ' visual binding is missing');
        assertSafeAssetPath(beat.visual.path, beat.beat_id + ' visual');
        if (beat.visual.path.indexOf(CINEMATIC_PREFIX) !== 0) fail(beat.beat_id + ' visual is outside Zone4 cinematic closure');
        if (typeof beat.visual.sha256 !== 'string' || !/^[a-f0-9]{64}$/i.test(beat.visual.sha256)) {
            fail(beat.beat_id + ' visual SHA-256 missing');
        }
        if (beat.visual.fallback_policy !== 'FAIL_CLOSED_NO_LEGACY_SUBSTITUTION') {
            fail(beat.beat_id + ' visual fallback policy is not fail-closed');
        }
        asArray(beat.dialogue).forEach(validateDialogue);
        if (!isRecord(beat.audio)) fail(beat.beat_id + ' audio binding is missing');
        assertAudioAsset(beat.audio.bgm, beat.beat_id + ' BGM');
        assertAudioAsset(beat.audio.ambience, beat.beat_id + ' ambience');
        assertAudioAsset(beat.audio.shui, beat.beat_id + ' shui');
        asArray(beat.audio.sfx_event_bindings).forEach(function (binding, bindingIndex) {
            if (!isRecord(binding) || !isRecord(binding.asset)) fail(beat.beat_id + ' SFX binding ' + bindingIndex + ' is malformed');
            assertAudioAsset(binding.asset, beat.beat_id + ' SFX binding ' + bindingIndex);
            if (binding.play_policy !== 'EVENT_BOUND_REVIEW_CONTROL; NOT_AUTO_TRIGGERED_WITHOUT_EVENT') {
                fail(beat.beat_id + ' SFX binding must remain event-bound');
            }
        });
    }

    function validateManifest(manifest) {
        if (!isRecord(manifest)) fail('root is not an object');
        if (manifest.schema !== MANIFEST_SCHEMA) fail('unsupported schema');
        if (!isRecord(manifest.counts)) fail('counts are missing');
        if (!isRecord(manifest.tracks)) fail('tracks are missing');
        var mainTrack = manifest.tracks.main_story;
        var lordTrack = manifest.tracks.lord_review;
        if (!isRecord(mainTrack) || !Array.isArray(mainTrack.beats)) fail('main_story track is missing');
        if (!isRecord(lordTrack) || !Array.isArray(lordTrack.beats)) fail('lord_review track is missing');
        if (mainTrack.autoplay_allowed !== true) fail('main_story autoplay contract changed');
        if (lordTrack.autoplay_allowed !== false) fail('lord_review must remain non-autoplay');
        if (mainTrack.beats.length !== MAIN_STORY_COUNT || manifest.counts.main_story_beats !== MAIN_STORY_COUNT) {
            fail('main_story beat count is not ' + MAIN_STORY_COUNT);
        }
        if (lordTrack.beats.length !== LORD_REVIEW_COUNT || manifest.counts.lord_review_beats !== LORD_REVIEW_COUNT) {
            fail('lord_review beat count is not ' + LORD_REVIEW_COUNT);
        }
        if (!Array.isArray(manifest.beats) || manifest.beats.length !== MAIN_STORY_COUNT + LORD_REVIEW_COUNT) {
            fail('story beat registry is incomplete');
        }
        var byId = {};
        manifest.beats.forEach(function (beat, index) {
            if (!beat || typeof beat.beat_id !== 'string' || byId[beat.beat_id]) fail('duplicate or invalid beat id at ' + index);
            byId[beat.beat_id] = beat;
        });
        var mainIds = {};
        mainTrack.beats.forEach(function (beatId, index) {
            if (mainIds[beatId] || !byId[beatId]) fail('main_story order contains duplicate or unknown beat ' + beatId);
            mainIds[beatId] = true;
            validateBeat(byId[beatId], index);
        });
        lordTrack.beats.forEach(function (beatId) {
            if (!byId[beatId] || byId[beatId].track !== 'lord_review') fail('lord_review order contains unknown beat ' + beatId);
        });
        var oldRef = JSON.stringify(manifest).indexOf(OLD_STORYBOARD_PREFIX) !== -1;
        if (oldRef) fail('manifest contains a legacy storyboard reference');
        return manifest;
    }

    function publicPath(path) {
        return '/' + String(path).replace(/^\/+/, '');
    }

    function localeCode(value) {
        return String(value || '').toLowerCase().indexOf('en') === 0 ? 'en-GB' : 'zh-TW';
    }

    function dialogueBeat(line, locale) {
        var voice = line.voice_by_locale && line.voice_by_locale[locale];
        return {
            lineId: line.line_id,
            speaker: line.speaker || '',
            text: line.text[locale],
            audioSrc: voice ? publicPath(voice.path) : '',
            allowTtsFallback: false,
        };
    }

    function toLocaleConfig(manifest, language, zone) {
        validateManifest(manifest);
        var locale = localeCode(language);
        var byId = {};
        manifest.beats.forEach(function (beat) { byId[beat.beat_id] = beat; });
        var ids = manifest.tracks.main_story.beats;
        var timeline = ids.map(function (beatId, index) {
            var beat = byId[beatId];
            var bgm = beat.audio && beat.audio.bgm;
            var ambience = beat.audio && beat.audio.ambience;
            return {
                shot: index,
                ownerBeatId: beat.beat_id,
                caption: beat.beat_id,
                text: '',
                audioSrc: '',
                imageSrc: publicPath(beat.visual.path),
                imageAlt: beat.visual.asset_id || beat.beat_id,
                beats: asArray(beat.dialogue).map(function (line) { return dialogueBeat(line, locale); }),
                bgmSrc: bgm ? publicPath(bgm.path) : '',
                ambienceSrc: ambience ? publicPath(ambience.path) : '',
                // Shui and SFX remain governed event-bound assets. The generic
                // host must not auto-trigger them without the declared event.
                ownerAudioPolicy: 'EVENT_BOUND_AUDIO_NOT_AUTO_TRIGGERED',
            };
        });
        var lastBeat = byId[ids[ids.length - 1]];
        var finalLine = lastBeat && asArray(lastBeat.dialogue)[0];
        var firstBeat = byId[ids[0]];
        var firstBgm = firstBeat && firstBeat.audio && firstBeat.audio.bgm;
        var firstAmbience = firstBeat && firstBeat.audio && firstBeat.audio.ambience;
        return {
            uiLang: locale === 'en-GB' ? 'en' : 'zh',
            preferredLang: locale,
            filmTitle: zone && zone.filmTitle
                ? zone.filmTitle
                : locale === 'en-GB' ? 'Misty Forest: Phantoms and True Form' : '迷霧森林：幻影與真形',
            finalCaption: locale === 'en-GB' ? 'Final beat: Beyond the Light' : '終幕：光明的彼岸',
            finalLine: finalLine && finalLine.text ? finalLine.text[locale] : '',
            bgmMainTheme: firstBgm ? publicPath(firstBgm.path) : '',
            ambienceVillageDawn: firstAmbience ? publicPath(firstAmbience.path) : '',
            timeline: timeline,
            sourceManifest: MANIFEST_PATH,
            track: 'main_story',
        };
    }

    function create(options) {
        options = options || {};
        var fetchImpl = options.fetchImpl;
        var manifestPath = options.manifestPath || MANIFEST_PATH;
        var manifest = null;
        var error = null;
        var pending = null;

        function ready() {
            if (manifest) return Promise.resolve(true);
            if (pending) return pending;
            if (typeof fetchImpl !== 'function') {
                error = new Error('fetch is unavailable');
                return Promise.resolve(false);
            }
            pending = Promise.resolve().then(function () {
                return fetchImpl(manifestPath, { credentials: 'same-origin', cache: 'no-store' });
            }).then(function (response) {
                if (!response || response.ok === false) throw new Error('manifest request failed');
                return typeof response.json === 'function' ? response.json() : response;
            }).then(function (value) {
                manifest = validateManifest(value);
                error = null;
                return true;
            }).catch(function (reason) {
                manifest = null;
                error = reason instanceof Error ? reason : new Error(String(reason));
                return false;
            }).finally(function () {
                pending = null;
            });
            return pending;
        }

        return {
            manifestPath: manifestPath,
            ready: ready,
            retry: function () {
                manifest = null;
                error = null;
                pending = null;
                return ready();
            },
            isReady: function () { return !!manifest; },
            failure: function () { return error ? error.message : null; },
            getManifest: function () { return manifest; },
            localeConfig: function (language, zone) {
                if (!manifest) throw new Error('Zone4 cinematic manifest is not ready');
                return toLocaleConfig(manifest, language, zone);
            },
        };
    }

    if (!browserRoot) return { create: create, validateManifest: validateManifest, toLocaleConfig: toLocaleConfig };
    var browserFetch = typeof browserRoot.fetch === 'function'
        ? browserRoot.fetch.bind(browserRoot)
        : null;
    return create({ fetchImpl: browserFetch });
}));
