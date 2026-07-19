(function (document) {
  'use strict';

  var ROUTES = { adventure: '/?adventure=1', dailyChallenge: '/daily-challenge' };
  function t(key, fallback) {
    if (window.E9 && window.E9.I18nFallback && typeof window.E9.I18nFallback.t === 'function') {
      var value = window.E9.I18nFallback.t(key, fallback);
      return value === key ? fallback : value;
    }
    return fallback;
  }
  function init(root, generation) {
    if (!root || root.getAttribute('data-e9-quest-inited') === '1') return;
    if (!window.E9 || !window.E9.QuestDefinitions || !window.E9.QuestEvaluator || typeof window.E9.createQuestStore !== 'function') return;
    root.setAttribute('data-e9-quest-inited', '1');
    var defsApi = window.E9.QuestDefinitions;
    var evaluator = window.E9.QuestEvaluator;
    var store = window.E9.createQuestStore(generation);
    window.E9.registerCleanup(store.destroy, generation);
    var tab = 'main';
    var title = root.querySelector('[data-e9-quest-title]');
    var summary = root.querySelector('[data-e9-quest-summary]');
    var list = root.querySelector('[data-e9-quest-list]');
    var status = root.querySelector('[data-e9-quest-status]');
    function current() { return store.isCurrent(); }
    function render(results) {
      if (!current() || !list) return;
      var visible = results.filter(function (q) { return q.category === tab; });
      list.innerHTML = '';
      if (!visible.length) {
        list.textContent = t('e9.quest.empty', 'No quests available right now.');
        return;
      }
      var completed = visible.filter(function (q) { return q.completed; }).length;
      if (summary) summary.textContent = t('e9.quest.summary', '{n} / {t} completed').replace('{n}', completed).replace('{t}', visible.length);
      visible.forEach(function (q) {
        var definition = defsApi.definitions.filter(function (d) { return d.id === q.id; })[0];
        var card = document.createElement('article');
        card.className = 'e9-quest-card' + (q.justCompleted ? ' is-just-completed' : '');
        card.setAttribute('data-quest-id', q.id);
        var heading = document.createElement('h4');
        heading.textContent = t(definition.titleKey, definition.id);
        card.appendChild(heading);
        var description = document.createElement('p');
        description.textContent = t(definition.descriptionKey, 'Continue your adventure.');
        card.appendChild(description);
        var badge = document.createElement('span');
        badge.className = 'e9-quest-badge';
        badge.textContent = q.completed ? t('e9.quest.completed', 'Completed') :
          (q.state === 'unavailable' ? t('e9.quest.unavailable', 'Unavailable') : t('e9.quest.in_progress', 'In progress'));
        card.appendChild(badge);
        var progress = document.createElement('progress');
        progress.max = 1; progress.value = q.ratio;
        progress.setAttribute('aria-label', t('e9.quest.progress', 'Quest progress'));
        progress.setAttribute('aria-valuetext', String(q.current === null ? 0 : q.current) + ' / ' + q.target);
        card.appendChild(progress);
        var label = document.createElement('span');
        label.className = 'e9-quest-progress-label';
        label.textContent = q.current === null ? t('e9.quest.unavailable', 'Unavailable') : String(q.current) + ' / ' + String(q.target);
        card.appendChild(label);
        var route = definition.cta && ROUTES[definition.cta.route];
        if (route && !q.completed && q.state !== 'unavailable') {
          var link = document.createElement('a');
          link.className = 'e9-quest-cta'; link.href = route;
          link.textContent = t('e9.quest.cta.' + definition.cta.route, 'Continue');
          card.appendChild(link);
        }
        list.appendChild(card);
      });
    }
    function setStatus(text) { if (status) status.textContent = text; }
    function load() {
      if (!current()) return;
      setStatus(t('e9.quest.loading', 'Loading quests…'));
      store.load().then(function (result) {
        if (!current()) return;
        var results = store.evaluate(defsApi.definitions, evaluator);
        setStatus(result.partial ? t('e9.quest.partial_error', 'Some quests are temporarily unavailable.') : '');
        render(results);
      }).catch(function () {
        if (!current()) return;
        setStatus(t('e9.quest.error', 'Quests are temporarily unavailable.'));
      });
    }
    var mainTab = root.querySelector('[data-e9-quest-tab="main"]');
    var dailyTab = root.querySelector('[data-e9-quest-tab="daily"]');
    function select(next, button) {
      tab = next;
      [mainTab, dailyTab].forEach(function (item) { if (item) item.setAttribute('aria-selected', item === button ? 'true' : 'false'); });
      load();
    }
    if (window.E9.on) {
      window.E9.on(mainTab, 'click', function () { select('main', mainTab); }, null, generation);
      window.E9.on(dailyTab, 'click', function () { select('daily', dailyTab); }, null, generation);
    }
    load();
  }
  document.addEventListener('e9:component-loaded', function (event) {
    if (event.detail && event.detail.component === 'right_cards') {
      init(event.detail.root.querySelector('[data-e9-quest-board]'), event.detail.generation);
    }
  });
})(document);
