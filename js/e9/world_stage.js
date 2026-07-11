/*
 * E9 World Stage — component init.
 * Operates only on its own root. Zone list is static markup this
 * sprint (matches docs/planning/e9_zone_monster_matrix.csv); no avatar
 * animation, no monster animation, no new map art — out of scope for
 * E9.1A per sprint definition.
 */
(function (document) {
  'use strict';

  function init(root) {
    if (root.getAttribute('data-e9-inited') === '1') return;
    root.setAttribute('data-e9-inited', '1');

    root.querySelectorAll('[data-zone]').forEach(function (zoneEl) {
      zoneEl.addEventListener('click', function () {
        console.log('[E9] zone click (placeholder, no adventure API wired yet):', zoneEl.getAttribute('data-zone'));
      });
      zoneEl.addEventListener('keydown', function (evt) {
        if (evt.key === 'Enter' || evt.key === ' ') {
          evt.preventDefault();
          zoneEl.click();
        }
      });
    });
  }

  document.addEventListener('e9:component-loaded', function (e) {
    if (e.detail && e.detail.component === 'world_stage') {
      init(e.detail.root);
    }
  });
})(document);
