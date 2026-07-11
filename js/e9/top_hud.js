/*
 * E9 Top HUD — component init.
 * Operates only on its own root (never queries the full document).
 * No new API this sprint — placeholder values only; real wiring point
 * for later is /api/skills/profile + /api/user/coins (see audit).
 */
(function (document) {
  'use strict';

  function init(root) {
    if (root.getAttribute('data-e9-inited') === '1') return; // no duplicate binding
    root.setAttribute('data-e9-inited', '1');

    var nameEl = root.querySelector('#top-hud-name');
    var rankEl = root.querySelector('#top-hud-rank');
    var coinsEl = root.querySelector('#top-hud-coins');
    var streakEl = root.querySelector('#top-hud-streak');

    if (nameEl) nameEl.textContent = '(placeholder player)';
    if (rankEl) rankEl.textContent = '(placeholder rank)';
    if (coinsEl) coinsEl.textContent = '🪙 --';
    if (streakEl) streakEl.textContent = '🔥 --';
  }

  document.addEventListener('e9:component-loaded', function (e) {
    if (e.detail && e.detail.component === 'top_hud') {
      init(e.detail.root);
    }
  });
})(document);
