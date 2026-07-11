/*
 * E9 Bottom Dock — component init.
 * Operates only on its own root. Buttons are inert placeholders this
 * sprint; each maps to an existing real route documented in
 * components/adventure/bottom_dock.html.
 */
(function (document) {
  'use strict';

  function init(root) {
    if (root.getAttribute('data-e9-inited') === '1') return;
    root.setAttribute('data-e9-inited', '1');

    root.querySelectorAll('[data-e9-dock]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        console.log('[E9] bottom-dock click (placeholder, no action wired yet):', btn.getAttribute('data-e9-dock'));
      });
    });
  }

  document.addEventListener('e9:component-loaded', function (e) {
    if (e.detail && e.detail.component === 'bottom_dock') {
      init(e.detail.root);
    }
  });
})(document);
