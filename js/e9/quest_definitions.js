(function (global) {
  'use strict';

  var definitions = [
    {
      id: 'main.earn_first_zone_star', version: 1, category: 'main',
      titleKey: 'e9.quest.main.earn_first_zone_star.title',
      descriptionKey: 'e9.quest.main.earn_first_zone_star.description',
      progressType: 'numeric', target: 1, source: 'adventure.maxStars', sortOrder: 10,
      cta: { route: 'adventure' }
    },
    {
      id: 'main.complete_three_star_zone', version: 1, category: 'main',
      titleKey: 'e9.quest.main.complete_three_star_zone.title',
      descriptionKey: 'e9.quest.main.complete_three_star_zone.description',
      progressType: 'numeric', target: 3, source: 'adventure.maxStars', sortOrder: 20,
      cta: { route: 'adventure' }
    },
    {
      id: 'main.defeat_first_boss', version: 1, category: 'main',
      titleKey: 'e9.quest.main.defeat_first_boss.title',
      descriptionKey: 'e9.quest.main.defeat_first_boss.description',
      progressType: 'numeric', target: 1, source: 'adventure.completedZoneCount', sortOrder: 30,
      cta: { route: 'adventure' }
    },
    {
      id: 'daily.complete_daily_challenge', version: 1, category: 'daily',
      titleKey: 'e9.quest.daily.complete_daily_challenge.title',
      descriptionKey: 'e9.quest.daily.complete_daily_challenge.description',
      progressType: 'boolean', target: 1, source: 'dailyChallenge.userSubmitted', sortOrder: 10,
      cta: { route: 'dailyChallenge' }
    }
  ];

  function validateCatalog(catalog) {
    if (!Array.isArray(catalog) || !catalog.length) return false;
    var ids = {};
    for (var i = 0; i < catalog.length; i++) {
      var q = catalog[i];
      if (!q || ids[q.id] || typeof q.id !== 'string' || !/^\w+\.[a-z0-9_]+$/.test(q.id) ||
          (q.category !== 'main' && q.category !== 'daily') ||
          typeof q.version !== 'number' || q.version < 1 ||
          (q.progressType !== 'numeric' && q.progressType !== 'boolean') ||
          typeof q.target !== 'number' || q.target <= 0 ||
          typeof q.source !== 'string' || !q.cta || typeof q.cta.route !== 'string' ||
          Object.keys(q).some(function (key) { return /^reward|claim|grant/i.test(key); })) return false;
      ids[q.id] = true;
    }
    return true;
  }

  var api = { definitions: definitions, validateCatalog: validateCatalog };
  global.E9 = global.E9 || {};
  global.E9.QuestDefinitions = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : global);
