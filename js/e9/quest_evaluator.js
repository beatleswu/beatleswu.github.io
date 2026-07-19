(function (global) {
  'use strict';

  function readSource(snapshot, source) {
    var parts = source.split('.');
    var value = snapshot;
    for (var i = 0; i < parts.length; i++) {
      if (!value || !Object.prototype.hasOwnProperty.call(value, parts[i])) return null;
      value = value[parts[i]];
    }
    return value;
  }

  function evaluateQuest(definition, snapshot) {
    var result = {
      id: definition && definition.id,
      version: definition && definition.version,
      category: definition && definition.category,
      current: null,
      target: definition && definition.target,
      ratio: 0,
      state: 'unavailable',
      completed: false,
      cta: definition && definition.cta,
      reason: 'invalid_definition'
    };
    if (!definition || !snapshot || typeof definition.target !== 'number' || definition.target <= 0) return result;
    var value = readSource(snapshot, definition.source);
    if (definition.progressType === 'boolean') {
      if (typeof value !== 'boolean') return result;
      result.current = value ? 1 : 0;
    } else if (definition.progressType === 'numeric') {
      if (typeof value !== 'number' || !isFinite(value) || value < 0) return result;
      result.current = value;
    } else {
      return result;
    }
    result.ratio = Math.max(0, Math.min(1, result.current / definition.target));
    result.completed = result.current >= definition.target;
    result.state = result.completed ? 'completed' : (result.current > 0 ? 'in_progress' : 'available');
    result.reason = 'evaluated';
    return result;
  }

  var api = { evaluateQuest: evaluateQuest, readSource: readSource };
  global.E9 = global.E9 || {};
  global.E9.QuestEvaluator = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : global);
