/*
 * E9 Left Nav — component init (non-critical).
 * Operates only on its own root. All links except "Adventure" are real
 * <a href> targets and need no JS to navigate — the browser handles them
 * natively. "Adventure" is the current view, so its click is a no-op
 * (prevented) rather than a real navigation.
 */
(function (document) {
  'use strict';

  function init(root, generation) {
    if (root.getAttribute('data-e9-inited') === '1') return;
    root.setAttribute('data-e9-inited', '1');

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
