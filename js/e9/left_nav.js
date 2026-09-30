/* G009 locked seven-item global navigation, generated from the registry. */
(function (document) {
  'use strict';

  function renderItem(item, registry) {
    var li = document.createElement('li');
    li.setAttribute('data-e10-vs1f-nav', item.key);
    var control = document.createElement(item.disabled || item.command ? 'button' : 'a');
    control.className = 'e9-nav__item e10-nav-item--' + item.key;
    control.setAttribute('data-g009-global-nav-item', item.key);
    control.setAttribute('data-e10-nav-key', item.key);
    control.setAttribute('data-e10-state', 'default');
    if (item.target) control.setAttribute('href', item.target);
    if (item.command) control.setAttribute('data-e10-command', item.command);
    if (item.disabled) {
      control.disabled = true;
      control.setAttribute('aria-disabled', 'true');
      control.setAttribute('data-e10-disabled', '');
      control.setAttribute('data-e10-state', 'locked');
      control.setAttribute('aria-describedby', 'e10-nav-status-' + item.key);
    }
    control.innerHTML = registry.icon(item.icon, 'e9-nav__icon')
      + '<span data-i18n="' + item.labelKey + '"></span>'
      + (item.disabled ? registry.icon('lock', 'e10-nav-status-lock')
        + '<small class="e9-visually-hidden" id="e10-nav-status-' + item.key + '" data-i18n="inv.comingSoon"></small>' : '');
    if (item.target) {
      var targetPath = new URL(item.target, window.location.origin).pathname;
      var currentPath = window.location.pathname.replace(/\/+$/, '') || '/';
      if (targetPath === currentPath && currentPath !== '/') {
        control.classList.add('is-active');
        control.setAttribute('data-e10-state', 'active');
        control.setAttribute('aria-current', 'page');
      }
    }
    li.appendChild(control);
    return li;
  }

  function init(root, generation) {
    if (root.getAttribute('data-e9-inited') === '1') return;
    root.setAttribute('data-e9-inited', '1');
    var registry = window.E9 && window.E9.NavigationRegistry;
    if (!registry || !registry.exactContract()) return;
    root.setAttribute('data-e10-vs1f-nav', 'global');
    root.setAttribute('data-g009-global-nav-count', '7');
    root.setAttribute('data-g009-nav-open', 'false');
    var list = root.querySelector('[data-e10-navigation-list]');
    registry.itemsFor('global').forEach(function (item) { list.appendChild(renderItem(item, registry)); });
    var setOpen = function (open) {
      var next = !!open;
      root.classList.toggle('is-open', next);
      root.setAttribute('data-g009-nav-open', next ? 'true' : 'false');
      root.setAttribute('aria-expanded', next ? 'true' : 'false');
    };
    if (window.E9 && window.E9.on) {
      window.E9.on(document, 'g009:global-nav-toggle', function (event) {
        setOpen(event.detail && event.detail.open);
      }, null, generation);
      window.E9.on(document, 'g009:global-nav-closed', function () { setOpen(false); }, null, generation);
    }
    if (window.I18n && window.I18n.apply) window.I18n.apply();
  }

  document.addEventListener('e9:component-loaded', function (event) {
    if (event.detail && event.detail.component === 'left_nav') init(event.detail.root, event.detail.generation);
  });
})(document);
