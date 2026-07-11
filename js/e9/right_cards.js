/*
 * E9 Right Cards — component init.
 * Operates only on its own root. No new API this sprint; cards stay as
 * labeled placeholders (see components/adventure/right_cards.html for
 * the real endpoint each card maps to later).
 */
(function (document) {
  'use strict';

  function init(root) {
    if (root.getAttribute('data-e9-inited') === '1') return;
    root.setAttribute('data-e9-inited', '1');
    // Placeholder only — intentionally no data fetch this sprint.
  }

  document.addEventListener('e9:component-loaded', function (e) {
    if (e.detail && e.detail.component === 'right_cards') {
      init(e.detail.root);
    }
  });
})(document);
