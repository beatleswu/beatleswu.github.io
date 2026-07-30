/*
 * E9 Bottom Dock — component init (non-critical).
 * Operates only on its own root. Every action navigates to an existing
 * real route: /community (leaderboard + friends hub), /badges
 * (achievements), /profile/<username> (game records — own profile).
 * "Settings" has no route in this app and was deliberately dropped from
 * the fragment rather than linked to nothing.
 */
(function (document) {
  'use strict';

  var VS1F_STATIC_CONTRACT = 'e10-vs1f-integrated-world-map';
  var VS1F_DOCK_ICONS = {
    leaderboard: '<path d="M9 5h14v5c0 6-3 10-7 12-4-2-7-6-7-12V5Z"/><path d="M9 8H5c0 5 2 8 6 9m12-9h4c0 5-2 8-6 9M16 22v5m-6 0h12"/>',
    achievements: '<circle cx="16" cy="13" r="8"/><path d="m16 7 1.8 3.7 4.1.6-3 2.9.7 4.1-3.6-1.9-3.6 1.9.7-4.1-3-2.9 4.1-.6L16 7Zm-5 13-2 8 7-3 7 3-2-8"/>',
    records: '<path d="M8 5h16v22H8z"/><path d="M12 10h8m-8 5h8m-8 5h5"/><path d="m20 20 2 2 4-5"/>',
    friends: '<circle cx="11" cy="12" r="4"/><circle cx="22" cy="11" r="3.5"/><path d="M4 27c.7-5 3-8 7-8s6.3 3 7 8M18 20c1.2-1.7 2.6-2.5 4.5-2.5 3.1 0 5 2.4 5.5 6.5"/>'
  };

  var ROUTES = {
    leaderboard: '/community',
    achievements: '/badges',
    friends: '/community'
  };

  function goToOwnProfile(generation) {
    var current = function () {
      return !window.E9 || typeof window.E9.isLifecycleCurrent !== 'function' || window.E9.isLifecycleCurrent(generation);
    };
    fetch('/api/auth/me', { credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('auth/me HTTP ' + r.status);
        return r.json();
      })
      .then(function (me) {
        if (!current()) return;
        if (me && me.username) {
          window.location.href = '/profile/' + encodeURIComponent(me.username);
        } else {
          throw new Error('no username in /api/auth/me response');
        }
      })
      .catch(function (err) {
        console.error('[E9] bottom_dock: could not resolve own profile route (non-critical):', err);
      });
  }

  function applyVs1fIcons(root) {
    var marker = document.querySelector('meta[name="go-odyssey-static-contract"]');
    if (!marker || marker.getAttribute('content') !== VS1F_STATIC_CONTRACT) return;
    root.querySelectorAll('[data-e9-dock]').forEach(function (button) {
      var action = button.getAttribute('data-e9-dock');
      var key = button.getAttribute('data-i18n');
      var label = button.textContent;
      var markup = VS1F_DOCK_ICONS[action];
      if (!markup || !key) return;
      button.removeAttribute('data-i18n');
      var icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      icon.setAttribute('class', 'e9-dock__icon');
      icon.setAttribute('viewBox', '0 0 32 32');
      icon.setAttribute('aria-hidden', 'true');
      icon.setAttribute('focusable', 'false');
      icon.setAttribute('data-e10-vs1f-icon', '');
      icon.innerHTML = markup;
      var text = document.createElement('span');
      text.setAttribute('data-i18n', key);
      text.textContent = label;
      button.textContent = '';
      button.appendChild(icon);
      button.appendChild(text);
    });
  }

  function init(root, generation) {
    if (root.getAttribute('data-e9-inited') === '1') return;
    root.setAttribute('data-e9-inited', '1');
    applyVs1fIcons(root);

    root.querySelectorAll('[data-e9-dock]').forEach(function (btn) {
      var action = btn.getAttribute('data-e9-dock');
      var handler = function () {
        if (action === 'records') {
          goToOwnProfile(generation);
          return;
        }
        var route = ROUTES[action];
        if (route) {
          window.location.href = route;
        } else {
          console.error('[E9] bottom_dock: no route mapped for action', action);
        }
      };
      if (window.E9 && typeof window.E9.on === 'function') {
        window.E9.on(btn, 'click', handler, null, generation);
      } else {
        btn.addEventListener('click', handler);
      }
    });
  }

  document.addEventListener('e9:component-loaded', function (e) {
    if (e.detail && e.detail.component === 'bottom_dock') {
      init(e.detail.root, e.detail.generation);
    }
  });
})(document);
