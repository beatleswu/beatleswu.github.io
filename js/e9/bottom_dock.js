/* G009 Phase 3B: no second global navigation surface. */
(function (document) {
  'use strict';

  function init(root) {
    if (root.getAttribute('data-e9-inited') === '1') return;
    root.setAttribute('data-e9-inited', '1');
    var registry = window.E9 && window.E9.NavigationRegistry;
    if (!registry || !registry.exactContract()) return;
    root.setAttribute('data-e10-vs1f-nav', 'secondary-empty');
    root.setAttribute('data-g009-secondary-nav', 'none');
    var list = root.querySelector('[data-e10-navigation-list]');
    if (list) list.replaceChildren();
    if (window.I18n && window.I18n.apply) window.I18n.apply();
  }

  document.addEventListener('e9:component-loaded', function (event) {
    if (event.detail && event.detail.component === 'bottom_dock') init(event.detail.root);
  });
})(document);
