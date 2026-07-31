/* Desktop legacy dock, generated from NavigationRegistry. */
(function (document) {
  'use strict';

  function init(root) {
    if (root.getAttribute('data-e9-inited') === '1') return;
    root.setAttribute('data-e9-inited', '1');
    var registry = window.E9 && window.E9.NavigationRegistry;
    if (!registry || !registry.exactContract()) return;
    root.setAttribute('data-e10-vs1f-nav', 'legacy-dock');
    var list = root.querySelector('[data-e10-navigation-list]');
    registry.itemsFor('desktop-legacy').forEach(function (item) {
      var link = document.createElement('a');
      link.className = 'e9-dock__item';
      link.href = item.target;
      link.setAttribute('data-e10-nav-key', item.key);
      link.setAttribute('data-e10-vs1f-nav', item.key);
      link.innerHTML = registry.icon(item.icon, 'e9-dock__icon') + '<span data-i18n="' + item.labelKey + '"></span>';
      list.appendChild(link);
    });
    if (window.I18n && window.I18n.apply) window.I18n.apply();
  }

  document.addEventListener('e9:component-loaded', function (event) {
    if (event.detail && event.detail.component === 'bottom_dock') init(event.detail.root);
  });
})(document);
