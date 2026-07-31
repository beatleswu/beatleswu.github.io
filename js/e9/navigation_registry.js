/* E10 RPG navigation registry: one source for every responsive surface. */
(function (global, document) {
  'use strict';

  var CONTRACT = 'e10-vs1f-integrated-world-map';
  var ITEMS = [
    { key: 'adventure', command: 'adventure', labelKey: 'e9.left_nav.adventure', icon: 'compass', category: 'primary', placement: ['mobile-primary'], order: { 'mobile-primary': 1 } },
    { key: 'hero', target: '/hero?tab=hero', labelKey: 'e9.left_nav.hero', icon: 'hero', category: 'primary', placement: ['desktop-primary', 'mobile-primary'], order: { 'desktop-primary': 1, 'mobile-primary': 2 } },
    { key: 'equipment', target: '/hero?tab=equipment', labelKey: 'e9.left_nav.equipment', icon: 'equipment', category: 'primary', placement: ['desktop-primary', 'mobile-primary'], order: { 'desktop-primary': 2, 'mobile-primary': 3 } },
    { key: 'backpack', target: null, labelKey: 'e9.left_nav.backpack', icon: 'backpack', category: 'primary-disabled', placement: ['desktop-primary', 'mobile-primary'], disabled: true, order: { 'desktop-primary': 3, 'mobile-primary': 5 } },
    { key: 'go_spirit', target: '/hero?tab=pet', labelKey: 'e10.nav.go_spirit', icon: 'spirit', category: 'primary', placement: ['desktop-primary', 'mobile-primary'], order: { 'desktop-primary': 4, 'mobile-primary': 4 } },
    { key: 'shop', target: '/shop', labelKey: 'nav.rpg.shop', icon: 'shop', category: 'primary', placement: ['desktop-primary', 'mobile-primary'], order: { 'desktop-primary': 5, 'mobile-primary': 6 } },
    { key: 'soul_records', target: '/mistakes', labelKey: 'nav.rpg.mistakes', icon: 'records', category: 'legacy', placement: ['desktop-legacy', 'more'] },
    { key: 'battle_log', target: '/stats', labelKey: 'nav.rpg.stats', icon: 'chart', category: 'legacy', placement: ['desktop-legacy', 'more'] },
    { key: 'tavern', target: '/community', labelKey: 'nav.rpg.tavern', icon: 'tavern', category: 'legacy', placement: ['desktop-legacy', 'more'] },
    { key: 'heroes_hall', target: '/hero', labelKey: 'nav.rpg.hero', icon: 'hero', category: 'legacy-more', placement: ['more'] },
    { key: 'star_chart', target: '/rating_test', labelKey: 'nav.rpg.rating', icon: 'star', category: 'legacy', placement: ['desktop-legacy', 'more'] },
    { key: 'arena', target: '/play', labelKey: 'nav.rpg.arena', icon: 'board', category: 'legacy', placement: ['desktop-legacy', 'more'] },
    { key: 'pass', target: '/upgrade', labelKey: 'nav.rpg.pass', icon: 'gem', category: 'utility', placement: ['utility', 'more'] },
    { key: 'messages', target: '/messages', labelKey: 'nav.rpg.messages', icon: 'mail', category: 'utility', placement: ['utility', 'more'] },
    { key: 'settings', command: 'settings', labelKey: 'e9.bottom_dock.settings', icon: 'settings', category: 'utility', placement: ['utility', 'more'] },
    { key: 'daily_challenge', target: '/daily-challenge', labelKey: 'e9.right_cards.daily_challenge_title', icon: 'calendar', category: 'more', placement: ['more'] },
    { key: 'badges', target: '/badges', labelKey: 'nav.label.badges', icon: 'badge', category: 'more', placement: ['more'] },
    { key: 'game_records', target: '/games', labelKey: 'e9.bottom_dock.records', icon: 'game', category: 'more', placement: ['more'] }
  ];

  var ICONS = {
    compass: '<circle cx="16" cy="16" r="11"/><path d="m20 12-2.5 5.5L12 20l2.5-5.5L20 12Z"/>',
    hero: '<path d="M16 3 7 7v8c0 6 3.7 10.5 9 14 5.3-3.5 9-8 9-14V7l-9-4Z"/><path d="m12 16 3 3 6-7"/>',
    equipment: '<path d="m6 27 7-7m6-6 7-7-3-3-7 7m-3 3-3-3 4-4 3 3M6 5l21 21"/>',
    backpack: '<path d="M7 11h18l-1 17H8L7 11Z"/><path d="M11 11V8c0-3 2-5 5-5s5 2 5 5v3M12 17h8v5h-8z"/>',
    spirit: '<path d="M16 27c-6-3-9-7-9-12 0-6 4-10 9-10s9 4 9 10c0 5-3 9-9 12Z"/><circle cx="13" cy="14" r="1"/><circle cx="19" cy="14" r="1"/><path d="M12 19c2 2 6 2 8 0"/>',
    shop: '<path d="M5 12h22l-2-7H7l-2 7ZM7 12v16h18V12M12 28v-9h8v9"/>',
    records: '<path d="M8 5h16v22H8z"/><path d="M12 11h8m-8 5h8m-8 5h6"/>',
    chart: '<path d="M6 26h21M9 22v-7m7 7V8m7 14V12"/>',
    tavern: '<path d="M7 7h18l-2 20H9L7 7Z"/><path d="M10 12h12M13 7V4h6v3"/>',
    star: '<path d="m16 4 3.4 7 7.6 1.1-5.5 5.4 1.3 7.5-6.8-3.6L9.2 25l1.3-7.5L5 12.1l7.6-1.1L16 4Z"/>',
    board: '<rect x="5" y="5" width="22" height="22" rx="3"/><path d="M10 5v22M16 5v22M22 5v22M5 10h22M5 16h22M5 22h22"/>',
    gem: '<path d="M8 7h16l4 6-12 14L4 13l4-6ZM4 13h24"/>',
    mail: '<rect x="5" y="7" width="22" height="18" rx="3"/><path d="m7 10 9 7 9-7"/>',
    settings: '<circle cx="16" cy="16" r="4"/><path d="M16 4v4m0 16v4M4 16h4m16 0h4M7.5 7.5l3 3m11 11 3 3m0-17-3 3m-11 11-3 3"/>',
    calendar: '<rect x="5" y="7" width="22" height="20" rx="3"/><path d="M10 4v6m12-6v6M5 13h22"/>',
    badge: '<circle cx="16" cy="14" r="8"/><path d="m11 21-2 8 7-4 7 4-2-8"/>',
    game: '<path d="M7 6h18v22H7zM11 11h10m-10 5h10m-10 5h7"/>'
  };

  function exactContract() {
    var marker = document.querySelector('meta[name="go-odyssey-static-contract"]');
    return !!marker && marker.getAttribute('content') === CONTRACT;
  }

  function itemsFor(placement) {
    return ITEMS.filter(function (item) { return item.placement.indexOf(placement) !== -1; }).sort(function (a, b) {
      return ((a.order && a.order[placement]) || ITEMS.indexOf(a)) - ((b.order && b.order[placement]) || ITEMS.indexOf(b));
    });
  }

  function icon(iconId, className) {
    return '<svg class="' + (className || 'e10-nav-icon') + '" viewBox="0 0 32 32" aria-hidden="true" focusable="false" data-e10-vs1f-icon>' + (ICONS[iconId] || ICONS.compass) + '</svg>';
  }

  global.E9 = global.E9 || {};
  global.E9.NavigationRegistry = {
    contract: CONTRACT,
    exactContract: exactContract,
    items: ITEMS.slice(),
    itemsFor: itemsFor,
    get: function (key) { return ITEMS.filter(function (item) { return item.key === key; })[0] || null; },
    icon: icon
  };
})(window, document);
