/**
 * 弈境奇兵 (Go Odyssey) mobile bottom navigation.
 * Mirrors the RPG wording used by the shared desktop nav.
 */
(function () {
  const existingNav = document.getElementById('mobile-nav');
  if (existingNav && existingNav.dataset.cgMobileNav === '1') existingNav.remove();
  else if (existingNav) return;

  // G009 Night Atlas: the phone bar is the same navy shell as the top bar and
  // drawer (tokens from site-nav.js, literal fallbacks for pages without it).
  // Gold marks the current destination. Items and routes are unchanged.
  const css = `
#mobile-nav {
  display: none;
  position: fixed; bottom: 0; left: 0; right: 0; z-index: 200;
  background: linear-gradient(180deg, rgba(16,24,50,.97), rgba(7,13,34,.97));
  backdrop-filter: blur(12px);
  border-top: 1px solid var(--na-gold-hair, rgba(236,201,120,.2));
  height: 64px;
  padding: 0 8px env(safe-area-inset-bottom, 0);
  align-items: center; justify-content: space-around;
  box-shadow: 0 -12px 28px rgba(0,0,0,.28);
}
@media (max-width: 768px) {
  #mobile-nav { display: flex; }
  body { padding-bottom: 64px; }
  #mobile-nav .mnb { min-width: 44px; padding-left: 4px; padding-right: 4px; }
}
#mobile-nav .mnb {
  display: flex; flex-direction: column; align-items: center;
  gap: 2px; padding: 6px 8px; border-radius: 10px;
  text-decoration: none; color: var(--na-text-soft, #c7cce0);
  font-size: 12px; font-weight: 700;
  font-family: 'DM Sans', 'Noto Sans TC', 'PingFang TC', system-ui, sans-serif;
  letter-spacing: .3px; transition: all .15s;
  min-width: 52px; min-height: 48px; justify-content: center;
  border: 1px solid transparent;
  position: relative;
}
#mobile-nav .mnb .mi { font-size: 20px; line-height: 1; }
#mobile-nav .mnb:hover,
#mobile-nav .mnb.active {
  color: var(--na-gold-100, #fff1c4);
  background: var(--na-gold-tint, rgba(227,180,87,.13));
  border-color: var(--na-gold-hair, rgba(236,201,120,.2));
}
#mobile-nav .mnb.active { box-shadow: inset 0 -2px 0 var(--na-gold-300, #e3b457); }
#mobile-nav .mnb:focus-visible { outline: 2px solid var(--na-gold-100, #fff1c4); outline-offset: 2px; }
`;

  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  const ITEMS = [
    { href: '/',           icon: '🏰', zh: '大廳', en: 'Lobby' },
    { href: '/curriculum', icon: '📜', zh: '公會', en: 'Guild' },
    { href: '/mistakes',   icon: '📕', zh: '卷宗', en: 'Scrolls' },
    { href: '/stats',      icon: '📊', zh: '戰績', en: 'Record' },
    { href: '/hero',       icon: '🛡️', zh: '英雄', en: 'Hero' },
  ];

  const path = window.location.pathname.replace(/\/$/, '') || '/';
  function _label(item) {
    return (typeof I18n !== 'undefined' && I18n.getLang() === 'en') ? item.en : item.zh;
  }

  function buildNav() {
    nav.innerHTML = ITEMS.map(item => {
      const active = (path === item.href || (item.href !== '/' && path.startsWith(item.href)))
        ? ' active' : '';
      return `<a href="${item.href}" class="mnb${active}">` +
             `<span class="mi">${item.icon}</span>` +
             `<span>${_label(item)}</span>` +
             `</a>`;
    }).join('');
  }

  const nav = document.createElement('nav');
  nav.id = 'mobile-nav';
  nav.dataset.cgMobileNav = '1';
  buildNav();
  document.body.appendChild(nav);

  // 語言切換時重繪（不覆蓋頁面既有的 onLangChange，採鏈式包裝）
  const _prev = window.onLangChange;
  window.onLangChange = function (lang) {
    if (typeof _prev === 'function') { try { _prev(lang); } catch (e) {} }
    try { buildNav(); } catch (e) {}
  };
})();
