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

  var ROUTES = {
    leaderboard: '/community',
    achievements: '/badges',
    friends: '/community'
  };

  function goToOwnProfile() {
    fetch('/api/auth/me', { credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('auth/me HTTP ' + r.status);
        return r.json();
      })
      .then(function (me) {
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

  function init(root) {
    if (root.getAttribute('data-e9-inited') === '1') return;
    root.setAttribute('data-e9-inited', '1');

    root.querySelectorAll('[data-e9-dock]').forEach(function (btn) {
      var action = btn.getAttribute('data-e9-dock');
      btn.addEventListener('click', function () {
        if (action === 'records') {
          goToOwnProfile();
          return;
        }
        var route = ROUTES[action];
        if (route) {
          window.location.href = route;
        } else {
          console.error('[E9] bottom_dock: no route mapped for action', action);
        }
      });
    });
  }

  document.addEventListener('e9:component-loaded', function (e) {
    if (e.detail && e.detail.component === 'bottom_dock') {
      init(e.detail.root);
    }
  });
})(document);
