(function (root, factory) {
  'use strict';

  var api = factory(root);
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.AdventureSpiritUnlockPresentation = api;
})(typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : this), function (global) {
  'use strict';

  var CONTRACT_VERSION = 'ADVENTURE_SPIRIT_UNLOCK_RESULT_V1';
  var TRANSPORT_CONTRACT_VERSION = 'ADVENTURE_SPIRIT_UNLOCK_RESULT_TRANSPORT_V1';
  var SOURCE_AUTHORITY = 'ADVENTURE_ZONE_MILESTONE';
  var SOURCE_FACT = 'adventure_boss_progress.cleared=1';
  var OPERATION_TYPE = 'SPIRIT_UNLOCK';
  var OWNERSHIP_STORE = 'pet_collection';
  var ROOT_ID = 'd031-adventure-spirit-result';
  var COMPLETION_EVENT = 'adventure-spirit-unlock-complete';
  var SYNC_CHANNEL_NAME = 'go-odyssey-spirit-sync-v1';

  var STATES = Object.freeze({
    NEW_SPIRIT_UNLOCK: 'NEW_SPIRIT_UNLOCK',
    ALREADY_OWNED_NO_OP: 'ALREADY_OWNED_NO_OP',
    NO_MILESTONE_UNLOCK: 'NO_MILESTONE_UNLOCK',
  });

  // These are presentation mappings only.  Ownership and eligibility remain
  // server-owned by spirit_adventure_milestone.py and the B023 unlock sink.
  var MILESTONES = Object.freeze({
    k11_15: Object.freeze({
      zoneNumber: 4,
      zoneNameZh: '迷霧森林',
      zoneNameEn: 'Misty Forest',
      spiritId: 'starpath_antlerling',
      spiritNameZh: 'Starpath Antlerling',
      spiritNameEn: 'Starpath Antlerling',
      asset: '/assets/pets/pet_starpath_antlerling_stage1.webp',
    }),
    k1_5: Object.freeze({
      zoneNumber: 6,
      zoneNameZh: '龍之谷',
      zoneNameEn: 'Dragon Valley',
      spiritId: 'fatty',
      spiritNameZh: '阿肥',
      spiritNameEn: 'Fatty',
      asset: '/assets/pets/pet_fatty_stage1.webp',
    }),
    d3_4: Object.freeze({
      zoneNumber: 8,
      zoneNameZh: '魔王城前線',
      zoneNameEn: 'Demon Castle Front',
      spiritId: 'obsidian_bastion',
      spiritNameZh: 'Obsidian Bastion',
      spiritNameEn: 'Obsidian Bastion',
      asset: '/assets/pets/pet_obsidian_bastion_stage1.webp',
    }),
  });

  var queue = [];
  var current = null;

  function isObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
  }

  function isPositiveInteger(value) {
    return typeof value === 'number' && isFinite(value) && Math.floor(value) === value && value > 0;
  }

  function isNonNegativeInteger(value) {
    return typeof value === 'number' && isFinite(value) && Math.floor(value) === value && value >= 0;
  }

  function isNonEmptyString(value) {
    return typeof value === 'string' && value.trim().length > 0;
  }

  function hasOwn(value, key) {
    return Object.prototype.hasOwnProperty.call(value, key);
  }

  function exactSourceReference(userId, zoneKey) {
    return 'adventure_boss_progress:' + String(userId) + ':' + zoneKey;
  }

  function exactOperationId(userId, zoneKey) {
    return 'adventure:spirit_unlock:' + String(userId) + ':' + zoneKey;
  }

  function languageIsZh() {
    var doc = global && global.document;
    var lang = doc && doc.documentElement && doc.documentElement.lang;
    return typeof lang === 'string' && lang.toLowerCase().indexOf('zh') === 0;
  }

  function normalizeResult(raw) {
    if (!isObject(raw)) return null;
    if (raw.contract_version !== TRANSPORT_CONTRACT_VERSION) return null;
    if (!isPositiveInteger(raw.user_id)) return null;
    if (!isNonEmptyString(raw.zone_key)) return null;

    var milestone = MILESTONES[raw.zone_key];
    if (!milestone) return null;
    if (raw.zone_number !== milestone.zoneNumber) return null;
    if (raw.spirit_id !== milestone.spiritId) return null;
    if (raw.source_authority !== SOURCE_AUTHORITY) return null;
    if (raw.source_fact !== SOURCE_FACT) return null;
    if (raw.operation_type !== OPERATION_TYPE) return null;
    if (raw.ownership_store !== OWNERSHIP_STORE) return null;
    if (raw.source_reference !== exactSourceReference(raw.user_id, raw.zone_key)) return null;
    if (raw.operation_id !== exactOperationId(raw.user_id, raw.zone_key)) return null;
    if (raw.client_completion_authority !== false) return null;
    if (raw.compensation_count !== 0 || raw.replacement_count !== 0) return null;
    if (!isNonNegativeInteger(raw.ownership_mutation_count)) return null;
    if (!isNonNegativeInteger(raw.new_unlock_count)) return null;
    if (typeof raw.replayed !== 'boolean') return null;
    if (typeof raw.eligible !== 'boolean' || typeof raw.cleared !== 'boolean') return null;
    if (!isNonEmptyString(raw.status)) return null;
    if (typeof raw.ownership_created !== 'boolean') return null;
    if (raw.already_owned !== null && typeof raw.already_owned !== 'boolean') return null;
    if (typeof raw.replay !== 'boolean') return null;
    if (!isNonEmptyString(raw.reason_code)) return null;
    if (!hasOwn(raw, 'historical_catchup')) return null;
    if (raw.historical_catchup !== null && typeof raw.historical_catchup !== 'boolean') return null;

    var state;
    if (raw.status === 'UNLOCKED') {
      if (!raw.eligible || !raw.cleared || raw.replayed !== false) return null;
      if (raw.operation_status !== 'COMPLETED') return null;
      if (raw.result_state !== 'UNLOCKED' || raw.ownership_created !== true ||
          raw.already_owned !== false || raw.replay !== false ||
          raw.reason_code !== 'MILESTONE_UNLOCKED') return null;
      if (raw.ownership_mutation_count !== 1 || raw.new_unlock_count !== 1) return null;
      state = STATES.NEW_SPIRIT_UNLOCK;
    } else if (raw.status === 'NO_OP') {
      if (!raw.eligible || !raw.cleared || raw.replayed !== false) return null;
      if (raw.operation_status !== 'COMPLETED') return null;
      if (raw.result_state !== 'NO_OP' || raw.ownership_created !== false ||
          raw.already_owned !== true || raw.replay !== false ||
          raw.reason_code !== 'MILESTONE_ALREADY_OWNED') return null;
      if (raw.ownership_mutation_count !== 0 || raw.new_unlock_count !== 0) return null;
      state = STATES.ALREADY_OWNED_NO_OP;
    } else if (raw.status === 'REPLAY') {
      if (!raw.eligible || !raw.cleared || raw.replayed !== true) return null;
      if (raw.operation_status !== 'COMPLETED') return null;
      if (raw.result_state !== 'NO_OP' || raw.ownership_created !== false ||
          raw.already_owned !== true || raw.replay !== true ||
          raw.reason_code !== 'MILESTONE_REPLAY') return null;
      if (raw.ownership_mutation_count !== 0 || raw.new_unlock_count !== 0) return null;
      state = STATES.ALREADY_OWNED_NO_OP;
    } else if (raw.status === 'NOT_ELIGIBLE') {
      if (raw.eligible || raw.cleared || raw.replayed !== false) return null;
      if (hasOwn(raw, 'operation_status') && raw.operation_status !== undefined) return null;
      if (raw.result_state !== 'NOT_ELIGIBLE' || raw.ownership_created !== false ||
          raw.already_owned !== null || raw.replay !== false ||
          raw.reason_code !== 'MILESTONE_NOT_ELIGIBLE') return null;
      if (raw.ownership_mutation_count !== 0 || raw.new_unlock_count !== 0) return null;
      state = STATES.NO_MILESTONE_UNLOCK;
    } else {
      return null;
    }

    var zh = languageIsZh();
    return Object.freeze({
      contractVersion: CONTRACT_VERSION,
      state: state,
      status: raw.status,
      replayed: raw.replayed,
      userId: raw.user_id,
      zoneKey: raw.zone_key,
      zoneNumber: milestone.zoneNumber,
      zoneName: zh ? milestone.zoneNameZh : milestone.zoneNameEn,
      spiritId: milestone.spiritId,
      spiritName: zh ? milestone.spiritNameZh : milestone.spiritNameEn,
      asset: milestone.asset,
      sourceOperationId: raw.operation_id,
      sourceReference: raw.source_reference,
    });
  }

  function normalizeResults(raw) {
    if (Array.isArray(raw)) {
      if (raw.length === 0) return [];
      var many = [];
      for (var i = 0; i < raw.length; i += 1) {
        var item = normalizeResult(raw[i]);
        if (!item) return null;
        many.push(item);
      }
      many.sort(function (left, right) {
        return left.zoneNumber - right.zoneNumber;
      });
      for (var j = 1; j < many.length; j += 1) {
        if (many[j - 1].userId === many[j].userId && many[j - 1].zoneKey === many[j].zoneKey) {
          return null;
        }
      }
      return many;
    }
    var one = normalizeResult(raw);
    return one ? [one] : null;
  }

  function presentationQueue(normalized) {
    var actionable = normalized.filter(function (item) {
      return item.state !== STATES.NO_MILESTONE_UNLOCK;
    });
    return actionable;
  }

  function addText(doc, parent, tag, className, value) {
    var element = doc.createElement(tag);
    element.className = className;
    element.textContent = value;
    parent.appendChild(element);
    return element;
  }

  function ensureRoot(doc) {
    var root = typeof doc.getElementById === 'function' ? doc.getElementById(ROOT_ID) : null;
    if (root) return root;
    root = doc.createElement('section');
    root.id = ROOT_ID;
    root.className = 'd031-spirit-result';
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'false');
    root.setAttribute('aria-live', 'polite');
    root.hidden = true;
    root.addEventListener('keydown', function (event) {
      if (event && event.key === 'Escape') {
        if (typeof event.preventDefault === 'function') event.preventDefault();
        advance();
      }
    });
    if (doc.body) doc.body.appendChild(root);
    return root;
  }

  function render(item) {
    var doc = global && global.document;
    if (!doc || !doc.body || typeof doc.createElement !== 'function') return false;
    var root = ensureRoot(doc);
    if (!root) return false;
    root.hidden = false;
    root.setAttribute('data-d031-presentation-state', item.state);
    root.setAttribute('data-zone-key', item.zoneKey);
    root.setAttribute('data-spirit-id', item.spiritId);
    root.textContent = '';

    var card = doc.createElement('article');
    card.className = 'd031-spirit-result__card d031-spirit-result__card--' + item.state.toLowerCase();
    card.setAttribute('aria-labelledby', 'd031-spirit-result-title');
    root.appendChild(card);

    var header = doc.createElement('header');
    header.className = 'd031-spirit-result__header';
    card.appendChild(header);
    addText(doc, header, 'span', 'd031-spirit-result__eyebrow', 'ADVENTURE MILESTONE · SERVER RESULT');
    var close = doc.createElement('button');
    close.type = 'button';
    close.className = 'd031-spirit-result__close';
    close.setAttribute('aria-label', 'Dismiss');
    close.textContent = '×';
    close.addEventListener('click', advance);
    header.appendChild(close);

    var body = doc.createElement('div');
    body.className = 'd031-spirit-result__body';
    card.appendChild(body);

    var art = doc.createElement('div');
    art.className = 'd031-spirit-result__art';
    art.setAttribute('aria-hidden', 'true');
    body.appendChild(art);
    if (item.state === STATES.NO_MILESTONE_UNLOCK) {
      var emptyMark = doc.createElement('span');
      emptyMark.className = 'd031-spirit-result__empty-mark';
      emptyMark.textContent = '—';
      art.appendChild(emptyMark);
    } else {
      var image = doc.createElement('img');
      image.className = 'd031-spirit-result__image';
      image.src = item.asset;
      image.alt = '';
      image.loading = 'eager';
      image.decoding = 'async';
      image.addEventListener('error', function () {
        // Asset availability is presentation-only and never changes the result.
        image.removeAttribute('src');
        image.setAttribute('data-d031-asset-fallback', 'true');
      });
      art.appendChild(image);
    }
    addText(doc, art, 'span', 'd031-spirit-result__zone-mark', 'ZONE ' + String(item.zoneNumber).padStart(2, '0'));

    var copy = doc.createElement('div');
    copy.className = 'd031-spirit-result__copy';
    body.appendChild(copy);

    var title;
    if (item.state === STATES.NEW_SPIRIT_UNLOCK) {
      title = 'A new Spirit joins your journey';
    } else if (item.state === STATES.ALREADY_OWNED_NO_OP) {
      title = 'This Spirit is already in your collection';
    } else {
      title = 'No new Spirit unlocked';
    }
    addText(doc, copy, 'h2', 'd031-spirit-result__title', title).id = 'd031-spirit-result-title';
    addText(doc, copy, 'p', 'd031-spirit-result__location', 'Zone ' + String(item.zoneNumber) + ' · ' + item.zoneName);

    if (item.state === STATES.NEW_SPIRIT_UNLOCK) {
      addText(doc, copy, 'p', 'd031-spirit-result__spirit-name', item.spiritName);
      addText(doc, copy, 'p', 'd031-spirit-result__message', item.spiritName + ' is now part of your Spirit collection.');
    } else if (item.state === STATES.ALREADY_OWNED_NO_OP) {
      addText(doc, copy, 'p', 'd031-spirit-result__spirit-name', item.spiritName);
      addText(doc, copy, 'p', 'd031-spirit-result__message', 'The Adventure milestone is already recorded. No new ownership was created.');
    } else {
      addText(doc, copy, 'p', 'd031-spirit-result__message', 'This Adventure milestone did not add a new Spirit to your collection.');
    }
    addText(doc, copy, 'p', 'd031-spirit-result__provenance', 'Adventure progress has the final say.');

    var actions = doc.createElement('div');
    actions.className = 'd031-spirit-result__actions';
    card.appendChild(actions);
    var continueButton = doc.createElement('button');
    continueButton.type = 'button';
    continueButton.className = 'd031-spirit-result__continue';
    continueButton.textContent = 'Continue';
    continueButton.addEventListener('click', advance);
    actions.appendChild(continueButton);
    if (typeof continueButton.focus === 'function') continueButton.focus();
    return true;
  }

  function advance() {
    if (queue.length) {
      current = queue.shift();
      render(current);
      return;
    }
    clear();
    notifyCompletion();
  }

  function present(raw) {
    var normalized = normalizeResults(raw);
    if (!normalized || normalized.length === 0) {
      clear();
      return [];
    }
    queue = presentationQueue(normalized);
    current = queue.shift() || null;
    if (!current) {
      clear();
      return [];
    }
    render(current);
    return [current].concat(queue).filter(Boolean).map(function (item) { return item.state; });
  }

  function clear() {
    queue = [];
    current = null;
    var doc = global && global.document;
    var root = doc && typeof doc.getElementById === 'function' ? doc.getElementById(ROOT_ID) : null;
    if (root) root.hidden = true;
  }

  function notifyCompletion() {
    if (!global || typeof global.dispatchEvent !== 'function') return;
    var event = null;
    try {
      if (typeof global.CustomEvent === 'function') {
        event = new global.CustomEvent(COMPLETION_EVENT);
      } else if (global.document && typeof global.document.createEvent === 'function') {
        event = global.document.createEvent('Event');
        event.initEvent(COMPLETION_EVENT, false, false);
      }
      if (event) global.dispatchEvent(event);
    } catch (_error) {
      // Completion notification is a refresh hint only; presentation remains complete.
    }
    try {
      if (typeof global.BroadcastChannel === 'function') {
        var channel = new global.BroadcastChannel(SYNC_CHANNEL_NAME);
        channel.postMessage({ type: COMPLETION_EVENT });
        if (typeof channel.close === 'function') channel.close();
      }
    } catch (_channelError) {
      // Cross-document refresh is best effort; server persistence remains authoritative.
    }
  }

  return Object.freeze({
    CONTRACT_VERSION: CONTRACT_VERSION,
    COMPLETION_EVENT: COMPLETION_EVENT,
    SYNC_CHANNEL_NAME: SYNC_CHANNEL_NAME,
    STATES: STATES,
    MILESTONES: MILESTONES,
    normalizeResult: normalizeResult,
    normalizeResults: normalizeResults,
    present: present,
    clear: clear,
  });
});
