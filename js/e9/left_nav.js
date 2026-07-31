/* Responsive primary navigation, generated from NavigationRegistry. */
(function (document) {
  'use strict';

  function renderItem(item, registry) {
    var li = document.createElement('li');
    li.setAttribute('data-e10-vs1f-nav', item.key);
    var control = document.createElement(item.disabled || item.command ? 'button' : 'a');
    control.className = 'e9-nav__item e10-nav-item--' + item.key;
    control.setAttribute('data-e10-nav-key', item.key);
    if (item.target) control.setAttribute('href', item.target);
    if (item.command) control.setAttribute('data-e10-command', item.command);
    if (item.disabled) {
      control.disabled = true;
      control.setAttribute('aria-disabled', 'true');
      control.setAttribute('data-e10-disabled', '');
      control.setAttribute('aria-describedby', 'e10-nav-status-' + item.key);
    }
    control.innerHTML = registry.icon(item.icon, 'e9-nav__icon')
      + '<span data-i18n="' + item.labelKey + '"></span>'
      + (item.disabled ? '<span class="e10-nav-status-lock" aria-hidden="true"></span>'
        + '<small class="e9-visually-hidden" id="e10-nav-status-' + item.key + '" data-i18n="inv.comingSoon"></small>' : '');
    li.appendChild(control);
    return li;
  }

  function init(root, generation) {
    if (root.getAttribute('data-e9-inited') === '1') return;
    root.setAttribute('data-e9-inited', '1');
    var registry = window.E9 && window.E9.NavigationRegistry;
    if (!registry || !registry.exactContract()) return;
    root.setAttribute('data-e10-vs1f-nav', 'primary');
    var list = root.querySelector('[data-e10-navigation-list]');
    registry.itemsFor('desktop-primary').forEach(function (item) { list.appendChild(renderItem(item, registry)); });
    registry.itemsFor('mobile-primary').forEach(function (item) {
      if (!list.querySelector('[data-e10-nav-key="' + item.key + '"]')) list.appendChild(renderItem(item, registry));
    });
    var adventure = list.querySelector('[data-e10-command="adventure"]');
    if (adventure) {
      var run = function () { if (window.E9 && window.E9.runAdventureCommand) window.E9.runAdventureCommand(); };
      window.E9.on(adventure, 'click', run, null, generation);
    }
    if (window.I18n && window.I18n.apply) window.I18n.apply();
  }

  document.addEventListener('e9:component-loaded', function (event) {
    if (event.detail && event.detail.component === 'left_nav') init(event.detail.root, event.detail.generation);
  });
})(document);
