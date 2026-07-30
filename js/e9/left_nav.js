/*
 * E9 Left Nav — component init (non-critical).
 * Operates only on its own root. All links except "Adventure" are real
 * <a href> targets and need no JS to navigate — the browser handles them
 * natively. "Adventure" is the current view, so its click is a no-op
 * (prevented) rather than a real navigation.
 */
(function (document) {
  'use strict';

  var VS1F_STATIC_CONTRACT = 'e10-vs1f-integrated-world-map';
  var VS1F_ICONS = {
    adventure: '<circle cx="16" cy="16" r="11"/><path d="m16 5 2.7 8.3L27 16l-8.3 2.7L16 27l-2.7-8.3L5 16l8.3-2.7L16 5Z"/><path d="m16 11 2 5-2 5-2-5 2-5Z"/>',
    hero: '<path d="M16 3 6 7v7c0 7 4 12 10 15 6-3 10-8 10-15V7L16 3Z"/><path d="M10 15c1-5 3-8 6-8s5 3 6 8M11 16h10v7H11z"/><path d="M16 16v7"/>',
    equipment: '<path d="m6 27 7-7m6-6 7-7-3-3-7 7m-3 3-3-3 4-4 3 3"/><path d="m6 5 21 21m-7-3 3-3M8 12l4-4"/>',
    backpack: '<path d="M7 11h18l-1 17H8L7 11Z"/><path d="M11 11V8c0-3 2-5 5-5s5 2 5 5v3M7 15H4v8h4m17-8h3v8h-4"/><path d="M13 17h6v5h-6z"/>',
    missions: '<path d="M8 4h16v25H8z"/><path d="M12 4V2h8v2M12 11h8m-8 6h8m-8 6h5"/><path d="m21 23 2 2 4-5"/>',
    shop: '<path d="M5 12h22l-2-7H7l-2 7Z"/><path d="M7 12v16h18V12M12 28v-9h8v9"/><path d="M5 12c0 3 4 4 6 1 2 3 8 3 10 0 2 3 6 2 6-1"/>'
  };

  function exactVs1fStaticContract() {
    var marker = document.querySelector('meta[name="go-odyssey-static-contract"]');
    return !!marker && marker.getAttribute('content') === VS1F_STATIC_CONTRACT;
  }

  function applyVs1fIcons(root) {
    if (!exactVs1fStaticContract()) return;
    var names = ['adventure', 'hero', 'equipment', 'backpack', 'missions', 'shop'];
    root.querySelectorAll('.e9-nav__item').forEach(function (item, index) {
      var markup = VS1F_ICONS[names[index]];
      if (!markup) return;
      var key = item.getAttribute('data-i18n');
      var label = item.textContent;
      item.removeAttribute('data-i18n');
      var icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      icon.setAttribute('class', 'e9-nav__icon');
      icon.setAttribute('viewBox', '0 0 32 32');
      icon.setAttribute('aria-hidden', 'true');
      icon.setAttribute('focusable', 'false');
      icon.setAttribute('data-e10-vs1f-icon', '');
      icon.innerHTML = markup;
      var text = document.createElement('span');
      text.setAttribute('data-i18n', key);
      text.textContent = label;
      item.textContent = '';
      item.appendChild(icon);
      item.appendChild(text);
    });
  }

  function init(root, generation) {
    if (root.getAttribute('data-e9-inited') === '1') return;
    root.setAttribute('data-e9-inited', '1');
    applyVs1fIcons(root);

    var current = root.querySelector('[data-e9-nav="adventure"]');
    if (current) {
      var handler = function (evt) {
        evt.preventDefault(); // already on this view
      };
      if (window.E9 && typeof window.E9.on === 'function') {
        window.E9.on(current, 'click', handler, null, generation);
      } else {
        current.addEventListener('click', handler);
      }
    }
  }

  document.addEventListener('e9:component-loaded', function (e) {
    if (e.detail && e.detail.component === 'left_nav') {
      init(e.detail.root, e.detail.generation);
    }
  });
})(document);
