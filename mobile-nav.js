/**
 * 弈境奇兵 (Go Odyssey) mobile bottom navigation.
 * Mirrors the RPG wording used by the shared desktop nav.
 */
(function () {
  const existingNav = document.getElementById('mobile-nav');
  if (existingNav && existingNav.dataset.cgMobileNav === '1') existingNav.remove();
  else if (existingNav) return;

  const css = `
#mobile-nav {
  display: none;
  position: fixed; bottom: 0; left: 0; right: 0; z-index: 200;
  background: rgba(17,12,8,.96);
  backdrop-filter: blur(12px);
  border-top: 1px solid rgba(217,170,85,.28);
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
  text-decoration: none; color: rgba(255,246,224,.72);
  font-size: 9px; font-family: 'DM Mono', monospace;
  letter-spacing: .3px; transition: all .15s;
  min-width: 52px; min-height: 44px; justify-content: center;
  border: 1px solid transparent;
  position: relative;
}
#mobile-nav .mnb .mi { font-size: 20px; line-height: 1; }
#mobile-nav .mnb:hover,
#mobile-nav .mnb.active {
  color: #fbbf24;
  background: rgba(251,191,36,.12);
  border-color: rgba(251,191,36,.22);
}
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
