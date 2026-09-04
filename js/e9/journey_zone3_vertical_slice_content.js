/*
 * W1_03_JOURNEY_ZONE3_CINEMATIC_ASSET_SLOT_AND_RESPONSIVE_BINDING_005
 *
 * Presentation contract for the World-owned Zone 3 cinematic package.  The
 * ten frames are whole-frame assets; this file binds their committed IDs,
 * runtime paths, lifecycle phases, responsive metadata, and localized beat
 * identities.  It is not a source of gameplay, clear, reward, or unlock
 * truth.  Missing presentation data may still use the text-safe fallback.
 */
(function (global) {
  'use strict';

  var ZONE3_KEY = 'k16_20';
  var ZONE4_KEY = 'k11_15';
  var WORLD_CANDIDATE = '39c587a216f6cc13efe572066d9d8f0299960f1b';
  var WORLD_MANIFEST_PATH = 'assets/e10/art/zone3/zone3-world-asset-package.json';
  var CINEMATIC_MANIFEST_PATH = 'assets/e10/art/zone3/cinematic/zone3-cinematic-asset-package.json';
  var RUNTIME_URL_PREFIX = '/assets/e10/art/zone3/cinematic/';
  var SUBTITLE_MANIFEST_PATH = '/assets/e10/i18n/zone3/zone3-cinematic-subtitles.json';
  var SUBTITLE_MANIFEST_EN_US_PATH = '/assets/e10/i18n/zone3/zone3-cinematic-subtitles-en-US.json';
  var AUDIO_MANIFEST_PATH = '/assets/e10/audio/zone3/zone3-cinematic-audio-manifest.json';
  var AUDIO_MANIFEST_EN_US_PATH = '/assets/e10/audio/zone3/zone3-cinematic-audio-manifest-en-US.json';
  var PRODUCTION_VOICES = {
    HERO: { name: 'Roy', id: 'XXxvxx0YUt8icTEFE3c6' },
    GRIK: { name: 'Zack', id: 'DSyEP4HEaCKur8rFFOri' },
    CENTURION: { name: 'Kevin Tu', id: 'BrbEfHMQu0fyclQR7lfh' }
  };
  var PRODUCTION_VOICES_BY_LOCALE = {
    'zh-TW': PRODUCTION_VOICES,
    'en-US': {
      HERO: { name: 'Steve', id: 'RasuOwPKPBy67j7E43Su' },
      GRIK: { name: 'Nick', id: 'v4mOufztUtjxcpk65aWy' },
      CENTURION: { name: 'Mark', id: 'cso37AjcTkVqyjGkWbRz' }
    }
  };

  // Localized cinematic content is data-owned and presentation-only.  The
  // subtitle manifest is the visible text authority and a locale without an
  // approved voice stays subtitle-only; no other locale is substituted.
  var CINEMATIC_LOCALIZATION = {
    subtitleManifest: SUBTITLE_MANIFEST_PATH,
    audioManifest: AUDIO_MANIFEST_PATH,
    subtitleManifests: {
      'zh-TW': SUBTITLE_MANIFEST_PATH,
      'en-US': SUBTITLE_MANIFEST_EN_US_PATH
    },
    audioManifests: {
      'zh-TW': AUDIO_MANIFEST_PATH,
      'en-US': AUDIO_MANIFEST_EN_US_PATH
    },
    supportedLocales: ['zh-TW', 'en-US'],
    defaultLocale: 'zh-TW',
    applicationLocale: 'zh',
    localeAliases: { zh: 'zh-TW', en: 'en-US' },
    replaySource: 'same_localized_beat_manifest',
    missingVoicePolicy: 'SUBTITLE_ONLY',
    crossLocaleVoiceFallback: 'FORBIDDEN',
    textBakedIntoBaseImage: false,
    shuiHumanDialogue: false
  };

  var PHASES = [
    'IDLE',
    'ENTRY_PENDING',
    'ENTRY_CINEMATIC',
    'GAMEPLAY_HANDOFF',
    'MAP_BATTLE_TRAINING',
    'BATTLEFIELD_BOSS_PROGRESS',
    'LORD_READY',
    'LORD_CTA',
    'LORD_TRIAL',
    'CLEAR_REWARD',
    'POST_CLEAR_CINEMATIC',
    'ZONE4_HOOK',
    'RETURN'
  ];

  var EVENT_TYPES = {
    zoneSelected: 'journey:zone3-zone-selected',
    entry: 'journey:zone3-entry',
    firstEntryCinematic: 'journey:zone3-first-entry-cinematic',
    gameplayHandoff: 'journey:zone3-gameplay-handoff',
    mapBattle: 'journey:zone3-map-battle',
    battlefieldBossProgress: 'journey:zone3-battlefield-boss-progress',
    lordReady: 'journey:zone3-lord-ready',
    lordCta: 'journey:zone3-lord-cta',
    lordTrialStarted: 'journey:zone3-lord-trial-started',
    lordTrialProgress: 'journey:zone3-lord-trial-progress',
    lordClear: 'journey:zone3-lord-clear',
    reward: 'journey:zone3-reward',
    postClear: 'journey:zone3-post-clear',
    zone4Hook: 'journey:zone4-hook',
    returnToMap: 'journey:zone3-return'
  };

  function padded(value, width) {
    return String(value).padStart(width, '0');
  }

  function responsive(mode, objectPosition, genericSafe, customPositionRequired) {
    return {
      mode: mode,
      objectPosition: objectPosition,
      genericSafe: genericSafe,
      customPositionRequired: customPositionRequired
    };
  }

  function makeBeat(shotNumber, beatNumber, character) {
    var shotToken = padded(shotNumber, 2);
    var beatToken = padded(beatNumber, 3);
    var beatKey = padded(beatNumber, 2);
    var voices = {};
    Object.keys(PRODUCTION_VOICES_BY_LOCALE).forEach(function (locale) {
      var voice = PRODUCTION_VOICES_BY_LOCALE[locale][character] || null;
      voices[locale] = {
        status: voice ? 'OWNER_APPROVED_PRODUCTION' : 'PENDING_OWNER_SELECTION',
        name: voice ? voice.name : null,
        id: voice ? voice.id : null,
        audioPath: voice
          ? RUNTIME_URL_PREFIX.replace('/art/zone3/cinematic/', '/audio/zone3/dialogue/' + locale + '/')
            + 'zone3_shot' + shotToken + '_b' + beatToken + '_' + locale + '_' + character.toLowerCase() + '.mp3'
          : null,
        audioManifest: locale === 'en-US' ? AUDIO_MANIFEST_EN_US_PATH : AUDIO_MANIFEST_PATH
      };
    });
    var voice = voices['zh-TW'];
    return {
      beatId: 'Z3_S' + shotToken + '_B' + beatToken,
      character: character,
      i18nKey: 'e9.zone3.cinematic.shot' + shotToken + '.beat' + beatKey,
      locale: 'zh-TW',
      subtitleSource: SUBTITLE_MANIFEST_PATH,
      subtitleSources: {
        'zh-TW': SUBTITLE_MANIFEST_PATH,
        'en-US': SUBTITLE_MANIFEST_EN_US_PATH
      },
      voiceStatus: voice.status,
      voiceName: voice.name,
      voiceId: voice.id,
      audioPath: voice.audioPath,
      voiceStatusByLocale: Object.keys(voices).reduce(function (out, locale) {
        out[locale] = voices[locale].status;
        return out;
      }, {}),
      voiceNameByLocale: Object.keys(voices).reduce(function (out, locale) {
        out[locale] = voices[locale].name;
        return out;
      }, {}),
      voiceIdByLocale: Object.keys(voices).reduce(function (out, locale) {
        out[locale] = voices[locale].id;
        return out;
      }, {}),
      audioPathByLocale: Object.keys(voices).reduce(function (out, locale) {
        out[locale] = voices[locale].audioPath;
        return out;
      }, {}),
      audioManifestByLocale: Object.keys(voices).reduce(function (out, locale) {
        out[locale] = voices[locale].audioManifest;
        return out;
      }, {})
    };
  }

  function makeBeats(shotNumber, characters) {
    return characters.map(function (character, index) {
      return makeBeat(shotNumber, index + 1, character);
    });
  }

  function makeShot(number, phase, assetId, sourcePath, sourceSha256, runtimePath,
                    runtimeSha256, characters, desktop, landscape, portrait,
                    mobile) {
    return {
      shotId: 'SHOT' + padded(number, 2),
      shotNumber: number,
      phase: phase,
      imageAssetId: assetId,
      imagePath: runtimePath,
      sourcePath: sourcePath,
      sourceSha256: sourceSha256,
      runtimeSha256: runtimeSha256,
      ownerApproved: true,
      noBakedRuntimeText: true,
      desktopPresentation: desktop,
      ipadLandscapePresentation: landscape,
      ipadPortraitPresentation: portrait,
      mobilePresentation: mobile,
      subtitleBeatSource: SUBTITLE_MANIFEST_PATH,
      voiceBeatSource: AUDIO_MANIFEST_PATH,
      beats: makeBeats(number, characters)
    };
  }

  // These records are a normalized, immutable projection of the committed
  // WORLD manifest.  Source/runtime hashes are retained so tests and later
  // shell wiring can prove the exact approved bytes were bound.
  var CINEMATIC_SHOTS = [
    makeShot(1, 'FIRST_ENTRY', 'ZONE3_CINEMATIC_SHOT01',
      'assets/e10/art/zone3/cinematic/source/zone3_shot01_moving_refugees_owner_approved.jpeg',
      '381d94c09d1d37d921c461e3f6c80b9a37ba92ed0d63581e9015ac53440e470f',
      RUNTIME_URL_PREFIX + 'zone3_shot01.webp',
      'f689f568dc501452b6c00212d5cec50d341ef2ba5b6059ddb23ebaeebe8eeb8c',
      ['HERO', 'HERO', 'HERO', 'HERO'],
      responsive('cover', '50% 50%', true, false),
      responsive('cover', '50% 50%', true, false),
      responsive('contain', '50% 50%', false, false),
      responsive('contain', '50% 50%', false, false)),
    makeShot(2, 'FIRST_ENTRY', 'ZONE3_CINEMATIC_SHOT02',
      'assets/e10/art/zone3/cinematic/source/zone3_shot02_household_belongings_owner_approved.jpeg',
      'f2af78399c1603ba1df453f5efb9df22f344999d9fe6721ebeb418527155bbc0',
      RUNTIME_URL_PREFIX + 'zone3_shot02.webp',
      '66dd93e017fa3f20e1e24f7deb1c7375da969384062d4987a7cad83f2d67cda6',
      ['HERO', 'HERO', 'HERO', 'HERO', 'HERO'],
      responsive('cover', '50% 54%', true, false),
      responsive('cover', '50% 54%', true, false),
      responsive('contain', '50% 54%', false, false),
      responsive('contain', '52% 56%', false, false)),
    makeShot(3, 'FIRST_ENTRY', 'ZONE3_CINEMATIC_SHOT03',
      'assets/e10/art/zone3/cinematic/source/zone3_shot03_meet_grik_owner_approved.jpeg',
      'e7c08c827f213b3adc9db24ce419282d747cbfd7ee2ca08fbf2c4cfd32dad1a2',
      RUNTIME_URL_PREFIX + 'zone3_shot03.webp',
      '904d21f0f753eff5f3858d2f1a8c735c18ad35f96be61825977de1ad63180cc1',
      ['GRIK', 'GRIK', 'GRIK', 'HERO', 'HERO', 'GRIK', 'GRIK', 'HERO', 'GRIK', 'GRIK', 'GRIK'],
      responsive('cover', '50% 50%', true, false),
      responsive('cover', '50% 50%', true, false),
      responsive('contain', '50% 50%', false, false),
      responsive('contain', '58% 50%', false, false)),
    makeShot(4, 'FIRST_ENTRY', 'ZONE3_CINEMATIC_SHOT04',
      'assets/e10/art/zone3/cinematic/source/zone3_shot04_shrinking_living_space_owner_approved.jpeg',
      'bd4f1b818e49aa976a20cd82c5d48fef77c569c70ba23e4407942b50adb85a67',
      RUNTIME_URL_PREFIX + 'zone3_shot04.webp',
      '0dc20e776ec12dfe79aed8a988dbe3c7597982354885175a098871e9fda7e431',
      ['GRIK', 'GRIK', 'GRIK', 'GRIK', 'GRIK', 'GRIK', 'GRIK', 'HERO', 'HERO'],
      responsive('cover', '50% 50%', true, false),
      responsive('cover', '50% 50%', true, false),
      responsive('contain', '50% 50%', false, false),
      responsive('contain', '58% 50%', false, false)),
    makeShot(5, 'FIRST_ENTRY', 'ZONE3_CINEMATIC_SHOT05',
      'assets/e10/art/zone3/cinematic/source/zone3_shot05_blocked_water_route_owner_approved.jpeg',
      'f7261e5f42545327bb5960aec2d38f049ffba0cb94c11d405e2f2ac81d2d4f4f',
      RUNTIME_URL_PREFIX + 'zone3_shot05.webp',
      'ae506cfa36b766ff94fe0e3cdf690e9da9d9d1231b1eeecaf0db46f90c1d20e9',
      ['HERO', 'GRIK', 'GRIK', 'GRIK', 'HERO', 'HERO', 'HERO'],
      responsive('cover', '50% 50%', true, false),
      responsive('cover', '50% 50%', true, false),
      responsive('contain', '50% 50%', false, false),
      responsive('contain', '67% 50%', false, false)),
    makeShot(6, 'BOSS_READY', 'ZONE3_CINEMATIC_SHOT06',
      'assets/e10/art/zone3/cinematic/source/zone3_shot06_last_door_centurion_owner_approved.jpeg',
      '9309ba5bd565007a30666a018c904321df43d64baeeee3ac0286016dd4a8ab15',
      RUNTIME_URL_PREFIX + 'zone3_shot06.webp',
      '7722c6fe21d066ae6063072ba9e4c7c8e1df91f079711169d904506cc62af065',
      ['HERO', 'CENTURION', 'CENTURION', 'CENTURION', 'HERO', 'CENTURION', 'CENTURION', 'CENTURION', 'CENTURION'],
      responsive('cover', '50% 50%', true, false),
      responsive('cover', '50% 50%', true, false),
      responsive('contain', '50% 50%', false, false),
      responsive('contain', '58% 50%', false, false)),
    makeShot(7, 'BOSS_READY', 'ZONE3_CINEMATIC_SHOT07',
      'assets/e10/art/zone3/cinematic/source/zone3_shot07_lord_trial_challenge_owner_approved.png',
      'e861ef571c3b46ba7e8b93839da472a390ee8a9a25784cf860564a1c1627950f',
      RUNTIME_URL_PREFIX + 'zone3_shot07.webp',
      'c1bee63b305635ec4e65b52dc18424b92dddb3c895c38d3582275fccf4f2f780',
      ['CENTURION', 'CENTURION', 'HERO', 'CENTURION', 'HERO', 'HERO', 'HERO', 'HERO', 'HERO', 'CENTURION', 'CENTURION', 'CENTURION'],
      responsive('cover', '50% 50%', true, false),
      responsive('cover', '50% 50%', true, false),
      responsive('contain', '50% 50%', false, false),
      responsive('contain', '55% 50%', false, false)),
    makeShot(8, 'POST_CLEAR', 'ZONE3_CINEMATIC_SHOT08',
      'assets/e10/art/zone3/cinematic/source/zone3_shot08_fragile_truce_owner_approved.png',
      'ffecac99714b6f936df6e95aaccd4287f64bda73eeedf224bdcb7e93641edab2',
      RUNTIME_URL_PREFIX + 'zone3_shot08.webp',
      '7209bca8197b18dd498936caeb7d774051fa2733ddce3d7ec45a6cefd43ff238',
      ['CENTURION', 'CENTURION', 'HERO', 'HERO', 'CENTURION', 'CENTURION', 'CENTURION', 'GRIK', 'CENTURION', 'HERO', 'HERO'],
      responsive('cover', '50% 50%', true, false),
      responsive('cover', '50% 50%', true, false),
      responsive('contain', '50% 50%', false, false),
      responsive('contain', '60% 52%', false, false)),
    makeShot(9, 'POST_CLEAR', 'ZONE3_CINEMATIC_SHOT09',
      'assets/e10/art/zone3/cinematic/source/zone3_shot09_stone_shard_handoff_owner_approved.jpeg',
      '573e29b1176182705847dfbf89dc1cceff686567187a6514f6e8fe213b861344',
      RUNTIME_URL_PREFIX + 'zone3_shot09.webp',
      'b6d7456a485499f1ef25a32d23ca48ea70402aecb09912157f5d2994d09e739c',
      ['GRIK', 'HERO', 'GRIK', 'GRIK', 'GRIK', 'GRIK', 'GRIK', 'HERO', 'GRIK', 'GRIK', 'GRIK', 'GRIK', 'HERO', 'HERO'],
      responsive('cover', '50% 50%', true, false),
      responsive('cover', '50% 50%', true, false),
      responsive('cover', '58% 50%', true, true),
      responsive('cover', '58% 50%', true, true)),
    makeShot(10, 'POST_CLEAR', 'ZONE3_CINEMATIC_SHOT10',
      'assets/e10/art/zone3/cinematic/source/zone3_shot10_mist_forest_hook_owner_approved.jpeg',
      '06b276012e83971631a8ac352ba07325938bb06f61be3a49f6050314084e6646',
      RUNTIME_URL_PREFIX + 'zone3_shot10.webp',
      '159b843ac507b814dcec91eb020d9dd45d4513de4aa0100d693d4d981f8da7e4',
      ['HERO', 'GRIK', 'GRIK', 'GRIK', 'GRIK', 'GRIK', 'GRIK', 'HERO', 'HERO', 'HERO', 'HERO', 'HERO', 'HERO', 'GRIK', 'GRIK'],
      responsive('cover', '50% 50%', true, false),
      responsive('cover', '50% 50%', true, false),
      responsive('cover', '58% 50%', true, true),
      responsive('cover', '58% 50%', true, true))
  ];

  var CINEMATIC_PRESENTATION = {
    manifestVersion: 'w1-zone3-10shot-owner-approved-v1',
    worldCandidate: WORLD_CANDIDATE,
    worldManifestPath: WORLD_MANIFEST_PATH,
    cinematicManifestPath: CINEMATIC_MANIFEST_PATH,
    runtimeUrlPrefix: RUNTIME_URL_PREFIX,
    locale: 'zh-TW',
    lifecycle: {
      FIRST_ENTRY: ['SHOT01', 'SHOT02', 'SHOT03', 'SHOT04', 'SHOT05'],
      BOSS_READY: ['SHOT06', 'SHOT07'],
      POST_CLEAR: ['SHOT08', 'SHOT09', 'SHOT10']
    },
    shots: CINEMATIC_SHOTS,
    subtitleBeatSource: SUBTITLE_MANIFEST_PATH,
    voiceBeatSource: AUDIO_MANIFEST_PATH,
    localizedSubtitleBeatSources: CINEMATIC_LOCALIZATION.subtitleManifests,
    localizedVoiceBeatSources: CINEMATIC_LOCALIZATION.audioManifests,
    supportedLocales: CINEMATIC_LOCALIZATION.supportedLocales,
    replaySource: 'same_cinematic_presentation_manifest',
    imageLoadFailure: 'PRESENTATION_ONLY_NO_GAMEPLAY_AUTHORITY',
    noCharacterOverlay: true,
    noBakedRuntimeText: true,
    responsiveManifestReconciled: true,
    responsiveCounts: {
      ipadPortraitGenericSafe: 2,
      ipadPortraitCustomPositionRequired: 2,
      mobileGenericSafe: 2,
      mobileCustomPositionRequired: 2
    }
  };

  var ASSET_SLOTS = {
    zone3Entry: {
      slotId: 'zone3_entry_cinematic',
      runtimeAsset: {
        manifest: CINEMATIC_MANIFEST_PATH,
        candidate: WORLD_CANDIDATE,
        phase: 'FIRST_ENTRY',
        shotIds: CINEMATIC_PRESENTATION.lifecycle.FIRST_ENTRY,
        runtimeRoot: RUNTIME_URL_PREFIX,
        status: 'OWNER_APPROVED'
      },
      finalArtwork: CINEMATIC_MANIFEST_PATH,
      visualDetails: 'WORLD-owned whole-frame ten-shot cinematic package',
      status: 'READY',
      fallbackMode: 'SAFE_TEXT_ONLY',
      approved: true
    },
    zone3PostClear: {
      slotId: 'zone3_post_clear_cinematic',
      runtimeAsset: {
        manifest: CINEMATIC_MANIFEST_PATH,
        candidate: WORLD_CANDIDATE,
        phase: 'POST_CLEAR',
        shotIds: CINEMATIC_PRESENTATION.lifecycle.POST_CLEAR,
        runtimeRoot: RUNTIME_URL_PREFIX,
        status: 'OWNER_APPROVED'
      },
      finalArtwork: CINEMATIC_MANIFEST_PATH,
      visualDetails: 'WORLD-owned whole-frame ten-shot cinematic package',
      status: 'READY',
      fallbackMode: 'SAFE_TEXT_ONLY',
      approved: true
    },
    zone3BossReady: {
      slotId: 'zone3_boss_ready_cinematic',
      runtimeAsset: {
        manifest: CINEMATIC_MANIFEST_PATH,
        candidate: WORLD_CANDIDATE,
        phase: 'BOSS_READY',
        shotIds: CINEMATIC_PRESENTATION.lifecycle.BOSS_READY,
        runtimeRoot: RUNTIME_URL_PREFIX,
        status: 'OWNER_APPROVED'
      },
      finalArtwork: CINEMATIC_MANIFEST_PATH,
      visualDetails: 'WORLD-owned whole-frame ten-shot cinematic package',
      status: 'READY',
      fallbackMode: 'SAFE_TEXT_ONLY',
      approved: true
    }
  };

  var STAGE_CONTRACTS = {
    zone_entry: {
      phase: 'ENTRY_PENDING',
      authoritySource: 'adventure_bootstrap',
      selectedZoneIsPresentationOnly: true
    },
    first_entry_cinematic: {
      phase: 'ENTRY_CINEMATIC',
      authoritySource: 'world_manifest',
      assetSlot: ASSET_SLOTS.zone3Entry.slotId,
      presentationOnly: true,
      imageFailureAuthority: 'NONE'
    },
    gameplay_handoff: {
      phase: 'GAMEPLAY_HANDOFF',
      authoritySource: 'canonical_adventure_entry',
      serverBound: true
    },
    map_battle_training: {
      phase: 'MAP_BATTLE_TRAINING',
      authoritySource: 'map_battle_v1',
      endpoint: '/api/adventure/map-battles/v1/answers',
      serverBound: true,
      presentationOnly: true
    },
    battlefield_boss_progression: {
      phase: 'BATTLEFIELD_BOSS_PROGRESS',
      authoritySource: 'map_battle_v1',
      battlefieldBossDistinctFromLord: true,
      presentationOnly: true
    },
    lord_ready: {
      phase: 'LORD_READY',
      authoritySource: 'adventure_bootstrap',
      requiresExplicitCta: true,
      noAutoStart: true
    },
    lord_cta: {
      phase: 'LORD_CTA',
      authoritySource: 'existing_lord_cta',
      userInitiated: true,
      noClientUnlock: true
    },
    lord_trial: {
      phase: 'LORD_TRIAL',
      authoritySource: 'adventure_boss_start_and_review',
      startEndpoint: ['/api/adventure/', 'boss/', 'start'].join(''),
      finishEndpoint: ['/api/adventure/', 'boss/', 'finish'].join(''),
      serverBound: true
    },
    authoritative_clear_reward: {
      phase: 'CLEAR_REWARD',
      authoritySource: 'adventure_boss_finish',
      rewardConsumer: 'BattlefieldBossRewardConsumer',
      noClientUnlock: true,
      replayDoesNotGrant: true
    },
    post_clear_cinematic: {
      phase: 'POST_CLEAR_CINEMATIC',
      authoritySource: 'world_manifest',
      assetSlot: ASSET_SLOTS.zone3PostClear.slotId,
      presentationOnly: true,
      imageFailureAuthority: 'NONE'
    },
    zone4_hook: {
      phase: 'ZONE4_HOOK',
      authoritySource: 'adventure_bootstrap',
      targetZoneKey: ZONE4_KEY,
      hookOnly: true,
      autoNavigate: false
    },
    replay_safe_return: {
      phase: 'RETURN',
      authoritySource: 'canonical_return',
      presentationOnly: true,
      replaySafe: true
    }
  };

  var AUTHORITY = {
    zone3Key: ZONE3_KEY,
    zone4Key: ZONE4_KEY,
    selectedZone: 'presentation_selection_only',
    progressionZone: 'server_current_zone_key_only',
    mapBattle: {
      runtime: 'MapBattleV1.legacy',
      attemptEndpoint: '/api/adventure/map-battles/v1/attempts',
      answerEndpoint: '/api/adventure/map-battles/v1/answers',
      serverMonsterProjection: 'adventure_monster'
    },
    battlefieldBoss: {
      identity: 'battlefield_boss',
      distinctFrom: 'lord_trial',
      presentationOnly: true
    },
    lordTrial: {
      startEndpoint: ['/api/adventure/', 'boss/', 'start'].join(''),
      finishEndpoint: ['/api/adventure/', 'boss/', 'finish'].join(''),
      clearAuthority: 'server_finish_response'
    },
    reward: {
      consumer: 'BattlefieldBossRewardConsumer',
      identity: 'server_reward.entitlement_id_or_source_operation_id',
      replayPolicy: 'NO_REWARD'
    },
    zone4: {
      hookAuthority: 'adventure_bootstrap',
      unlockAuthority: 'server_only',
      autoNavigate: false
    },
    presentation: {
      imageFailure: 'NO_GAMEPLAY_AUTHORITY_CHANGE',
      subtitleCompleteDoesNotUnlock: true,
      voiceCompleteDoesNotUnlock: true,
      localeSwitchDoesNotProgress: true,
      replayDoesNotReward: true
    }
  };

  var STYLE_LOCK = {
    status: 'RESOLVED_BY_WORLD_CANDIDATE',
    affectedZoneKey: ZONE3_KEY,
    pendingSlots: [],
    visualDetails: 'WORLD candidate supplies the exact ten approved cinematic frames; final Zone 3/Lord art remains separate.',
    authoredCopy: null,
    noFakeFinalAssets: true
  };

  function deepFreeze(value) {
    if (!value || typeof value !== 'object' || Object.isFrozen(value)) return value;
    Object.keys(value).forEach(function (key) { deepFreeze(value[key]); });
    return Object.freeze(value);
  }

  deepFreeze(EVENT_TYPES);
  deepFreeze(CINEMATIC_PRESENTATION);
  deepFreeze(ASSET_SLOTS);
  deepFreeze(STAGE_CONTRACTS);
  deepFreeze(AUTHORITY);
  deepFreeze(STYLE_LOCK);
  deepFreeze(CINEMATIC_LOCALIZATION);
  Object.freeze(PHASES);

  global.GoOdysseyJourneyZone3Content = Object.freeze({
    version: 'W1_03_JOURNEY_ZONE3_CINEMATIC_ASSET_SLOT_AND_RESPONSIVE_BINDING_V1',
    zone3Key: ZONE3_KEY,
    zone4Key: ZONE4_KEY,
    phases: PHASES,
    eventTypes: EVENT_TYPES,
    assetSlots: ASSET_SLOTS,
    stageContracts: STAGE_CONTRACTS,
    authority: AUTHORITY,
    styleLock: STYLE_LOCK,
    cinematicLocalization: CINEMATIC_LOCALIZATION,
    cinematicPresentation: CINEMATIC_PRESENTATION,
    safeFallback: 'SAFE_TEXT_ONLY',
    noFakeFinalAssets: true
  });
}(typeof window !== 'undefined' ? window : this));
