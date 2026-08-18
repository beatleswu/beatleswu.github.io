/* E10 RPG navigation registry: one source for every responsive surface. */
(function (global, document) {
  'use strict';

  var CONTRACT = 'e10-vs1f-integrated-world-map';
  var ITEMS = [
    { key: 'adventure', command: 'adventure', labelKey: 'e9.left_nav.adventure', icon: 'compass', category: 'primary', placement: ['mobile-primary'], order: { 'mobile-primary': 1 } },
    // UI-NAV-063: on the Adventure page itself, nav slot 1 ("冒險") is a no-op
    // for the player, so that one slot is swapped for the Guild entry.
    // /curriculum is the EXISTING canonical Guild page (HERO STATUS /
    // 公會委託榜 / 公會聲望; it self-labels as 冒險者公會 at
    // curriculum.html:2188). No new route was created. 'adventure-context' is
    // a marker placement only -- no surface renders it directly, left_nav.js
    // resolves it by key. Icon: guild.webp is the Owner-supplied Guild emblem,
    // normalised to the same 256x256 transparent square the rest of this icon
    // set uses (white plate removed, cropped to content, centred).
    { key: 'guild', target: '/curriculum', labelKey: 'e10.nav.guild', icon: 'guild', category: 'primary', placement: ['adventure-context'] },
    { key: 'hero', target: '/hero?tab=hero', labelKey: 'e9.left_nav.hero', icon: 'hero', category: 'primary', placement: ['desktop-primary', 'mobile-primary'], order: { 'desktop-primary': 1, 'mobile-primary': 2 } },
    { key: 'equipment', target: '/hero?tab=equipment', labelKey: 'e9.left_nav.equipment', icon: 'equipment', category: 'primary', placement: ['desktop-primary', 'mobile-primary'], order: { 'desktop-primary': 2, 'mobile-primary': 3 } },
    // E10 owns a presentation-only route marker; the generic /inventory
    // route remains the Legacy destination used by shared navigation.
    { key: 'backpack', target: '/inventory' + '?e10=1', labelKey: 'e9.left_nav.backpack', icon: 'backpack', category: 'primary', placement: ['desktop-primary', 'mobile-primary'], order: { 'desktop-primary': 3, 'mobile-primary': 5 } },
    { key: 'go_spirit', target: '/hero?tab=pet', labelKey: 'e10.nav.go_spirit', icon: 'spirit', category: 'primary', placement: ['desktop-primary', 'mobile-primary'], order: { 'desktop-primary': 4, 'mobile-primary': 4 } },
    { key: 'shop', target: '/shop', labelKey: 'nav.rpg.shop', icon: 'shop', category: 'primary', placement: ['desktop-primary', 'mobile-primary'], order: { 'desktop-primary': 5, 'mobile-primary': 6 } },
    { key: 'soul_records', target: '/mistakes', labelKey: 'nav.rpg.mistakes', icon: 'records', category: 'legacy', placement: ['desktop-legacy', 'more'] },
    { key: 'battle_log', target: '/stats', labelKey: 'nav.rpg.stats', icon: 'battle_log', category: 'legacy', placement: ['desktop-legacy', 'more'] },
    { key: 'tavern', target: '/community', labelKey: 'nav.rpg.tavern', icon: 'tavern', category: 'legacy', placement: ['desktop-legacy', 'more'] },
    { key: 'heroes_hall', target: '/hero', labelKey: 'nav.rpg.hero', icon: 'hall', category: 'legacy-more', placement: ['more'] },
    { key: 'star_chart', target: '/rating_test', labelKey: 'nav.rpg.rating', icon: 'star_chart', category: 'legacy', placement: ['desktop-legacy', 'more'] },
    { key: 'arena', target: '/play', labelKey: 'nav.rpg.arena', icon: 'arena', category: 'legacy', placement: ['desktop-legacy', 'more'] },
    { key: 'pass', target: '/upgrade', labelKey: 'nav.rpg.pass', icon: 'pass', category: 'utility', placement: ['utility', 'more'] },
    { key: 'messages', target: '/messages', labelKey: 'nav.rpg.messages', icon: 'messages', category: 'utility', placement: ['utility', 'more'] },
    { key: 'settings', command: 'settings', labelKey: 'e9.bottom_dock.settings', icon: 'settings', category: 'utility', placement: ['utility', 'more'] },
    { key: 'daily_challenge', target: '/daily-challenge', labelKey: 'e9.right_cards.daily_challenge_title', icon: 'daily', category: 'more', placement: ['more'] },
    { key: 'badges', target: '/badges', labelKey: 'nav.label.badges', icon: 'badge', category: 'more', placement: ['more'] },
    { key: 'game_records', target: '/games', labelKey: 'e9.bottom_dock.records', icon: 'game_records', category: 'more', placement: ['more'] }
  ];

  var ICONS = {
    compass: '<circle class="e10-icon__body" cx="16" cy="16" r="12"/><circle class="e10-icon__detail" cx="16" cy="16" r="8"/><path class="e10-icon__accent" d="m19.8 10.2-2.1 7.5-7.5 2.1 4.1-5.5 5.5-4.1Z"/><circle class="e10-icon__gem" cx="16" cy="16" r="1.7"/>',
    hero: '<path class="e10-icon__body" d="M16 3.5 6.5 8v7.2c0 6.4 3.9 10.8 9.5 14 5.6-3.2 9.5-7.6 9.5-14V8L16 3.5Z"/><path class="e10-icon__accent" d="M10 15.5c0-4 2.5-7 6-7s6 3 6 7v2H10v-2Z"/><path class="e10-icon__detail" d="M13 18v-4.5m6 4.5v-4.5M10 18h12M16 8.5V5"/>',
    equipment: '<path class="e10-icon__body" d="m5 25 5-1 13-13-3-3L7 21l-2 4Zm14-18 3-3 6 6-3 3"/><path class="e10-icon__detail" d="M7 6l19 19M4 4l6 2-4 4-2-6Zm17 17-3 3"/><path class="e10-icon__spark" d="M23 3v4m-2-2h4"/>',
    backpack: '<path class="e10-icon__body" d="M7 11.5h18l-1 16H8l-1-16Z"/><path class="e10-icon__detail" d="M11 11.5V8.8C11 5.6 13 4 16 4s5 1.6 5 4.8v2.7M7.5 16h17"/><rect class="e10-icon__accent" x="11.5" y="18" width="9" height="6" rx="2"/>',
    spirit: '<circle class="e10-icon__body" cx="16" cy="16" r="12"/><path class="e10-icon__accent" d="M16 6a10 10 0 0 1 0 20c3-2.4 3-7 0-10s-3-7 0-10Z"/><circle class="e10-icon__gem" cx="16" cy="11" r="2.2"/><circle class="e10-icon__detail e10-icon__detail--fill" cx="16" cy="21" r="2.2"/>',
    shop: '<path class="e10-icon__body" d="M6 12h20v16H6V12Z"/><path class="e10-icon__accent" d="M4.5 12 7 5h18l2.5 7c-1 2-3.7 2-5 0-1 2-4 2-5 0-1 2-4 2-5 0-1 2-4 2-5 0-1 2-2 2-3 0Z"/><path class="e10-icon__detail" d="M12 28v-9h8v9M9 5h14"/>',
    records: '<path class="e10-icon__body" d="M8 6h15v21H9c-2 0-3-1-3-2.5S7 22 9 22h14"/><path class="e10-icon__accent" d="M9 4h15v18H9c-2 0-3 1-3 2.5V7c0-1.7 1.3-3 3-3Z"/><path class="e10-icon__detail" d="M12 9h8m-8 4h8m-8 4h5"/>',
    battle_log: '<path class="e10-icon__body" d="M7 4v24M8 6h16l-4 5 4 5H8V6Z"/><path class="e10-icon__accent" d="M12 9h7l-2 2 2 2h-7V9Z"/><path class="e10-icon__detail" d="M12 21h13m-13 4h9"/>',
    tavern: '<path class="e10-icon__body" d="M8 10h14l-1.5 16h-11L8 10Z"/><path class="e10-icon__accent" d="M7 6h16v5H7V6Z"/><path class="e10-icon__detail" d="M22 13h3c2 0 3 1.5 3 3.5S27 20 24.5 20H21M12 15h6"/><circle class="e10-icon__gem" cx="15" cy="8.5" r="1.2"/>',
    hall: '<path class="e10-icon__body" d="M16 6 9 9v7c0 5 3 8 7 10 4-2 7-5 7-10V9l-7-3Z"/><path class="e10-icon__accent" d="m16 10 1.7 3.4 3.8.6-2.7 2.6.6 3.8-3.4-1.8-3.4 1.8.6-3.8-2.7-2.6 3.8-.6L16 10Z"/><path class="e10-icon__detail" d="M7 12c-3 4-2 9 2 13M25 12c3 4 2 9-2 13M5 17l3 1m19-1-3 1"/>',
    star_chart: '<circle class="e10-icon__body" cx="16" cy="16" r="12"/><circle class="e10-icon__detail" cx="16" cy="16" r="8"/><path class="e10-icon__accent" d="m16 8 2.1 5 5.4.4-4.1 3.5 1.3 5.2-4.7-2.8-4.7 2.8 1.3-5.2-4.1-3.5 5.4-.4L16 8Z"/>',
    arena: '<path class="e10-icon__body" d="M5 14c0-5 4.9-9 11-9s11 4 11 9v9c0 2.2-4.9 4-11 4S5 25.2 5 23v-9Z"/><ellipse class="e10-icon__accent" cx="16" cy="14" rx="11" ry="7"/><ellipse class="e10-icon__detail" cx="16" cy="14" rx="6" ry="3"/><path class="e10-icon__detail" d="M8 18v6m5-4v6m6-6v6m5-8v6"/>',
    pass: '<path class="e10-icon__body" d="M5 9h22v14H5V9Z"/><path class="e10-icon__detail" d="M9 9v14m14-14v14"/><path class="e10-icon__accent" d="m16 11 4 3-4 7-4-7 4-3Z"/>',
    messages: '<path class="e10-icon__body" d="M5 8h22v17H5V8Z"/><path class="e10-icon__accent" d="m6 10 10 8 10-8"/><path class="e10-icon__detail" d="m6 23 7-7m13 7-7-7"/><circle class="e10-icon__gem" cx="16" cy="18" r="2.4"/>',
    settings: '<path class="e10-icon__body" d="m13 4 1-2h4l1 2 3 1 2-1 3 3-1 2 1 3 2 1v4l-2 1-1 3 1 2-3 3-2-1-3 1-1 2h-4l-1-2-3-1-2 1-3-3 1-2-1-3-2-1v-4l2-1 1-3-1-2 3-3 2 1 3-1Z"/><circle class="e10-icon__accent" cx="16" cy="15" r="5"/><circle class="e10-icon__detail" cx="16" cy="15" r="2"/>',
    daily: '<circle class="e10-icon__accent" cx="21" cy="10" r="6"/><path class="e10-icon__detail" d="M21 1v3m0 12v3m-9-9h3m12 0h3m-15.4-6.4 2.1 2.1m8.6 8.6 2.1 2.1m0-12.8-2.1 2.1m-8.6 8.6-2.1 2.1"/><path class="e10-icon__body" d="M5 11h15v17H5V11Z"/><path class="e10-icon__detail" d="M9 16h7m-7 4h7m-7 4h5"/>',
    badge: '<circle class="e10-icon__body" cx="16" cy="13" r="9"/><path class="e10-icon__accent" d="m16 7 2 3.5 4 .8-2.8 3  .5 4-3.7-1.7-3.7 1.7.5-4-2.8-3 4-.8L16 7Z"/><path class="e10-icon__detail" d="m11 21-2 8 7-4 7 4-2-8"/>',
    game_records: '<path class="e10-icon__body" d="M7 5h18v23H7V5Z"/><path class="e10-icon__accent" d="M10 5h12v5H10V5Z"/><path class="e10-icon__detail" d="M11 14h10m-10 4h10m-10 4h7M7 5l4 3"/>',
    coin: '<circle class="e10-icon__body" cx="16" cy="16" r="12"/><circle class="e10-icon__accent" cx="16" cy="16" r="8"/><path class="e10-icon__detail" d="M18.8 11.5c-1-1.3-4.8-1.2-5.5.5-.8 2 1.3 2.8 3.1 3.2 2 .5 3.7 1.2 3.2 3.2-.5 2.1-5 2.5-6.5.4M16 8.5v15"/>',
    all_features: '<rect class="e10-icon__body" x="5" y="5" width="7" height="7" rx="2"/><rect class="e10-icon__accent" x="13" y="5" width="6" height="7" rx="2"/><rect class="e10-icon__body" x="20" y="5" width="7" height="7" rx="2"/><rect class="e10-icon__accent" x="5" y="13" width="7" height="6" rx="2"/><circle class="e10-icon__gem" cx="16" cy="16" r="3"/><rect class="e10-icon__accent" x="20" y="13" width="7" height="6" rx="2"/><rect class="e10-icon__body" x="5" y="20" width="7" height="7" rx="2"/><rect class="e10-icon__accent" x="13" y="20" width="6" height="7" rx="2"/><rect class="e10-icon__body" x="20" y="20" width="7" height="7" rx="2"/>',
    close: '<circle class="e10-icon__body" cx="16" cy="16" r="11"/><path class="e10-icon__detail" d="m11 11 10 10m0-10L11 21"/>',
    lock: '<rect class="e10-icon__body" x="8" y="13" width="16" height="14" rx="3"/><path class="e10-icon__accent" d="M11 13V9a5 5 0 0 1 10 0v4"/><circle class="e10-icon__gem" cx="16" cy="20" r="2"/>'
  };

  var ART_ICON_ROOT = '/assets/e10/ui/icons/';
  var ICON_ASSETS = {
    compass: 'adventure.webp',
    hero: 'hero.webp',
    equipment: 'equipment.webp',
    backpack: 'backpack.webp',
    spirit: 'go-spirit.webp',
    shop: 'shop.webp',
    records: 'soul-records.webp',
    battle_log: 'battle-log.webp',
    tavern: 'tavern.webp',
    guild: 'guild.webp',
    hall: 'heroes-hall.webp',
    star_chart: 'star-chart.webp',
    arena: 'arena.webp',
    pass: 'pass.webp',
    messages: 'messages.webp',
    settings: 'settings.webp',
    daily: 'daily-challenge.webp',
    badge: 'badges.webp',
    game_records: 'game-records.webp',
    coin: 'coins.webp',
    all_features: 'all-features.webp',
    close: 'close.webp',
    lock: 'lock.webp'
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
    if (!exactContract()) return '';
    var resolved = ICON_ASSETS[iconId] ? iconId : 'compass';
    var source = ART_ICON_ROOT + ICON_ASSETS[resolved];
    return '<i class="e10-rpg-icon e10-art-icon ' + (className || 'e10-nav-icon')
      + '" aria-hidden="true" data-e10-vs1f-icon data-e10-icon-id="' + resolved
      + '" data-e10-art-asset="' + source + '"><img src="' + source
      + '" alt="" width="256" height="256" decoding="async" draggable="false"></i>';
  }

  global.E9 = global.E9 || {};
  global.E9.NavigationRegistry = {
    contract: CONTRACT,
    exactContract: exactContract,
    iconIds: Object.keys(ICON_ASSETS),
    iconAssets: Object.assign({}, ICON_ASSETS),
    items: ITEMS.slice(),
    itemsFor: itemsFor,
    get: function (key) { return ITEMS.filter(function (item) { return item.key === key; })[0] || null; },
    icon: icon
  };
})(window, document);
