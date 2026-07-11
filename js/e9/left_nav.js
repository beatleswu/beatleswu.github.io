/*
 * E9 Left Nav — component init.
 * Operates only on its own root. This sprint only Adventure is a real
 * target (the world_stage slot); other items are inert placeholders
 * until their real destination pages are wired in a later sprint.
 */
(function (document) {
  'use strict';

  function init(root) {
    if (root.getAttribute('data-e9-inited') === '1') return;
    root.setAttribute('data-e9-inited', '1');

    root.querySelectorAll('[data-e9-nav]').forEach(function (link) {
      link.addEventListener('click', function (evt) {
        evt.preventDefault();
        var target = link.getAttribute('data-e9-nav');
        console.log('[E9] left-nav click (placeholder, no navigation wired yet):', target);
      });
    });
  }

  document.addEventListener('e9:component-loaded', function (e) {
    if (e.detail && e.detail.component === 'left_nav') {
      init(e.detail.root);
    }
  });
})(document);
