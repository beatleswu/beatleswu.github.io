(() => {
  window.__COLORFUL_GO_NAV_VERSION__ = '20260930-g009-phase3b-shell';
  const SOCKET_IO_CLIENT_SRC = 'https://cdn.socket.io/4.7.5/socket.io.min.js';

  // G009 Phase 3B locked global navigation.  Mistakes, Stats and Rating
  // remain reachable as secondary Learning Hub content; they are not global
  // destinations. Home is intentionally not a global item (#8).
  const NAV_ITEMS = [
    { href: '/curriculum', key: 'learning_hub', icon: 'book', label: '學習公會', i18n: 'g009.nav.learning_hub', pageI18n: 'g009.page.learning_hub' },
    { href: '/play',       key: 'arena',       icon: 'board', label: '競技場',   i18n: 'g009.nav.arena',       pageI18n: 'g009.page.arena' },
    { href: '/community',  key: 'tavern',      icon: 'team',  label: '酒館',     i18n: 'g009.nav.tavern',      pageI18n: 'g009.page.tavern' },
    { href: '/hero',       key: 'hero_hub',     icon: 'hero',  label: '英雄殿',   i18n: 'g009.nav.hero_hub',    pageI18n: 'g009.page.hero_hub' },
    { href: '/inventory',  key: 'backpack',     icon: 'backpack', label: '背包', i18n: 'g009.nav.backpack', pageI18n: 'g009.page.backpack' },
    { href: '/shop',       key: 'shop',         icon: 'coin', label: '商店',     i18n: 'g009.nav.shop',        pageI18n: 'g009.page.shop' },
    { href: '/upgrade',    key: 'premium',      icon: 'gem',  label: '通行證',   i18n: 'g009.nav.premium',     pageI18n: 'g009.page.premium' },
  ];

  const ICONS = {
    book: '<path d="M7 5.5c3.2-1.3 6.2-1.1 9 .7v13.3c-2.8-1.8-5.8-2-9-.7V5.5Zm9 .7c2.8-1.8 5.8-2 9-.7v13.3c-3.2-1.3-6.2-1.1-9 .7"/>',
    map: '<path d="M6 7l6-2 8 2 6-2v17l-6 2-8-2-6 2V7Zm6-2v17m8-15v17"/>',
    target: '<circle cx="16" cy="16" r="10"/><circle cx="16" cy="16" r="5"/><path d="M16 2v5m0 18v5M2 16h5m18 0h5"/>',
    note: '<path d="M9 5h11l4 4v17H9V5Zm11 0v5h5"/><path d="M12 14h9M12 19h9M12 24h6"/>',
    medal: '<path d="M11 4h10l-2 7h-6l-2-7Z"/><circle cx="16" cy="19" r="6"/><path d="M16 16l1.2 2.2 2.5.4-1.8 1.8.4 2.5-2.3-1.2-2.3 1.2.4-2.5-1.8-1.8 2.5-.4Z"/>',
    chart: '<path d="M6 25h20"/><path d="M9 21v-7m7 7V8m7 13V11"/>',
    team: '<circle cx="12" cy="12" r="4"/><circle cx="21" cy="11" r="3"/><path d="M5 25c1-5 4-8 7-8s6 3 7 8M18 18c3 .6 5 3 6 7"/>',
    mail: '<rect x="5" y="7" width="22" height="18" rx="3"/><path d="m7 10 9 7 9-7"/>',
    hero: '<path d="M16 4l8 4v7c0 6-3.6 10-8 13-4.4-3-8-7-8-13V8l8-4Z"/><path d="M12 15l3 3 6-7"/>',
    backpack: '<path d="M7 12h18l-1 15H8L7 12Z"/><path d="M11 12V9c0-3 2-5 5-5s5 2 5 5v3M8 17h16"/><rect x="12" y="19" width="8" height="5" rx="2"/>',
    board: '<rect x="5" y="5" width="22" height="22" rx="3"/><path d="M10 5v22M16 5v22M22 5v22M5 10h22M5 16h22M5 22h22"/><circle cx="10" cy="22" r="2.5"/><circle cx="22" cy="10" r="2.5"/>',
    coin: '<circle cx="16" cy="16" r="10"/><path d="M16 9v14M11 13c1.2-2 8.7-2 10 0M11 19c1.2 2 8.7 2 10 0"/>',
    gem: '<path d="M8 7h16l4 6-12 14L4 13l4-6Z"/><path d="M4 13h24M11 7l5 20 5-20"/>',
    rating: '<circle cx="16" cy="16" r="10"/><circle cx="16" cy="16" r="4"/><path d="M16 6v3M16 23v3M6 16h3M23 16h3M9.1 9.1l2.1 2.1M20.8 20.8l2.1 2.1M9.1 22.9l2.1-2.1M20.8 11.2l2.1-2.1"/>',
  };

  // Learning Hub owns these five secondary destinations.  They stay out of
  // the global seven-item shell while retaining one shared, responsive
  // presentation across the learning pages.
  const LEARNING_SECONDARY_ITEMS = [
    { href: '/curriculum', key: 'curriculum_map', label: '課程地圖', i18n: 'g009.learning.curriculum_map' },
    { href: '/stats', key: 'learning_progress', label: '學習進度', i18n: 'g009.learning.progress' },
    { href: '/daily-challenge', key: 'daily_bounty', label: '每日懸賞令', i18n: 'g009.learning.daily_bounty' },
    { href: '/mistakes', key: 'mistakes', label: '錯題本', i18n: 'g009.learning.mistakes' },
    { href: '/rating_test', key: 'rating_appraisal', label: '棋力鑑定', i18n: 'g009.learning.rating' },
  ];
  const LEARNING_SURFACES = new Set([
    'learning-hub', 'learning-progress', 'learning-daily', 'learning-mistakes', 'learning-rating',
  ]);

  const E10_VS1F_STATIC_CONTRACT = 'e10-vs1f-integrated-world-map';
  const E10_MAP_SHELL_OWNER = 'e10-map';
  const E10_BATTLE_SHELL_OWNER = 'e10-battle';
  const E10_BACKPACK_SHELL_OWNER = 'e10-backpack';

  function ownsE10Navigation() {
    const marker = document.querySelector('meta[name="go-odyssey-static-contract"]');
    const hasStaticContract = marker?.getAttribute('content') === E10_VS1F_STATIC_CONTRACT;
    if (!hasStaticContract) return false;
    const adventureShellOwner = window.__GO_ADVENTURE_SHELL_OWNER__
      || document.body?.getAttribute('data-adventure-shell-owner')
      || document.documentElement?.getAttribute('data-adventure-shell-owner');
    if ([E10_MAP_SHELL_OWNER, E10_BATTLE_SHELL_OWNER, E10_BACKPACK_SHELL_OWNER]
      .includes(adventureShellOwner)) return true;
    const activeShell = window.__GO_E9_ACTIVE_SHELL__
      || document.body?.getAttribute('data-adventure-shell-active');
    return activeShell === 'e9';
  }

  function ownsE10MapNavigation() {
    const marker = document.querySelector('meta[name="go-odyssey-static-contract"]');
    if (marker?.getAttribute('content') !== E10_VS1F_STATIC_CONTRACT) return false;
    const owner = window.__GO_ADVENTURE_SHELL_OWNER__
      || document.body?.getAttribute('data-adventure-shell-owner')
      || document.documentElement?.getAttribute('data-adventure-shell-owner');
    return owner === E10_MAP_SHELL_OWNER;
  }

  function normalize(path) {
    return (path || '/').replace(/\/+$/, '') || '/';
  }

  function isActive(href) {
    const cur = normalize(location.pathname);
    const target = normalize(new URL(href, location.origin).pathname);
    if (target === '/curriculum' && LEARNING_SURFACES.has(document.body?.dataset.g009Surface)) return true;
    if (target === '/') return cur === '/';
    return cur === target;
  }

  function currentPageItem() {
    return NAV_ITEMS.find(item => isActive(item.href)) || null;
  }

  function currentPageLabel() {
    const item = currentPageItem();
    const key = item?.pageI18n || 'g009.page.home';
    return typeof I18n !== 'undefined' && typeof I18n.t === 'function'
      ? I18n.t(key) : (item?.label || '首頁');
  }

  function icon(name) {
    return `<svg class="cg-nav-icon" viewBox="0 0 32 32" aria-hidden="true">${ICONS[name] || ICONS.book}</svg>`;
  }

  function isLearningSurface() {
    const surface = document.body?.dataset.g009Surface;
    return LEARNING_SURFACES.has(surface)
      || ['/curriculum', '/stats', '/daily-challenge', '/mistakes', '/rating_test'].includes(normalize(location.pathname));
  }

  function buildLearningSecondaryNav() {
    if (!isLearningSurface() || document.querySelector('[data-g009-learning-secondary]')) return;
    const nav = document.createElement('nav');
    nav.className = 'g009-learning-secondary';
    nav.dataset.g009LearningSecondary = '5';
    nav.dataset.g009VisualAuthority = 'locked-12-surfaces';
    nav.setAttribute('aria-label', 'Learning Hub secondary navigation');
    nav.setAttribute('data-i18n-aria-label', 'g009.learning.aria');
    const currentPath = normalize(location.pathname);
    nav.innerHTML = LEARNING_SECONDARY_ITEMS.map(item => {
      const active = normalize(item.href) === currentPath;
      return `<a class="g009-learning-secondary__item${active ? ' is-active' : ''}" href="${item.href}" data-g009-learning-secondary-key="${item.key}" data-i18n="${item.i18n}"${active ? ' aria-current="page"' : ''}>${item.label}</a>`;
    }).join('');
    const header = document.querySelector('header.cg-nav');
    if (header?.parentElement) header.insertAdjacentElement('afterend', nav);
    else if (document.body) document.body.insertBefore(nav, document.body.firstChild);
    if (typeof I18n !== 'undefined' && typeof I18n.apply === 'function') I18n.apply();
  }

  function buildNav() {
    // 只接管「導覽列 header」；行銷頁的 <header class="hero"> 不可被吃掉
    const isPremiumSurface = document.body?.dataset.g009Surface === 'premium'
      || normalize(location.pathname) === '/upgrade';
    const old = document.querySelector('header.cg-nav') || document.querySelector('header:not(.hero)');
    if (!old && !isPremiumSurface) return;
    const langSwitcher = old?.querySelector('[id^="lang-switcher-"]')
      || (isPremiumSurface ? document.querySelector('[id^="lang-switcher-"]') : null);
    const header = document.createElement('header');
    header.className = 'cg-nav';
    header.dataset.cgNav = '1';
    header.dataset.g009Surface = 'global-navigation';
    header.dataset.g009GlobalNav = '7';
    header.dataset.g009VisualAuthority = 'locked-12-surfaces';
    const activeItem = currentPageItem();
    header.innerHTML = `
      <div class="cg-nav-inner">
        <button class="cg-nav-hamburger" type="button" data-g009-hamburger aria-expanded="false" aria-controls="g009-global-drawer" data-i18n-aria-label="g009.nav.hamburger">
          <span aria-hidden="true"></span><span aria-hidden="true"></span><span aria-hidden="true"></span>
        </button>
        <a class="cg-brand" href="/" aria-label="弈境奇兵 (Go Odyssey) 公會大廳" data-i18n-aria-label="common.brand.home">
          <span class="cg-brand-mark" aria-hidden="true"><span></span></span>
          <span class="cg-brand-text" data-i18n="common.brand">弈境奇兵 (Go Odyssey)</span>
        </a>
        <span class="cg-nav-page-label" data-g009-current-page-label data-i18n="${activeItem?.pageI18n || 'g009.page.home'}">${activeItem?.label || '首頁'}</span>
        <nav class="cg-nav-links" aria-label="Global navigation" data-g009-global-nav="7" data-i18n-aria-label="g009.nav.aria">
          ${NAV_ITEMS.map(item => `
            <a class="cg-nav-link ${isActive(item.href) ? 'active' : ''}" href="${item.href}" data-nav-key="${item.key}" data-g009-nav-key="${item.key}" data-i18n-aria-label="${item.i18n}" ${isActive(item.href) ? 'aria-current="page"' : ''}>
              ${icon(item.icon)}
              <span data-i18n="${item.i18n}">${item.label}</span>
            </a>`).join('')}
        </nav>
        <div class="cg-nav-actions">
          <button class="cg-nav-player" type="button" data-g009-player-trigger aria-haspopup="menu" aria-expanded="false" aria-controls="g009-player-menu" data-i18n-aria-label="g009.account.open">
            <span class="cg-nav-player-avatar" aria-hidden="true">GO</span>
            <span class="cg-nav-user" id="username-display">Player</span>
            <span class="cg-nav-player-chevron" aria-hidden="true">⌄</span>
          </button>
          <span class="cg-nav-presence" id="cg-presence-chip" hidden>
            <span class="cg-nav-presence-dot"></span>
            <span class="cg-nav-presence-text" id="cg-presence-text" data-i18n="nav.presence.offline">離線</span>
            <span class="cg-nav-presence-count" id="cg-presence-count" hidden></span>
          </span>
          <span class="cg-nav-lang"></span>
        </div>
      </div>
      <div class="cg-nav-menu" id="g009-player-menu" role="menu" hidden>
        <a role="menuitem" href="/hero?tab=hero" data-g009-account="profile" data-i18n="g009.account.profile">Profile</a>
        <button role="menuitem" type="button" data-g009-account="settings" data-i18n="g009.account.settings">Settings</button>
        <button role="menuitem" type="button" data-g009-account="logout" data-i18n="g009.account.logout">Logout</button>
      </div>
      <div class="cg-nav-drawer" id="g009-global-drawer" data-g009-global-drawer hidden>
        <div class="cg-nav-drawer__backdrop" data-g009-drawer-close></div>
        <nav class="cg-nav-drawer__panel" role="dialog" aria-modal="true" aria-labelledby="g009-global-drawer-title">
          <div class="cg-nav-drawer__header"><h2 id="g009-global-drawer-title" data-i18n="g009.nav.aria">Global navigation</h2><button type="button" data-g009-drawer-close data-i18n-aria-label="g009.nav.close">×</button></div>
          <div class="cg-nav-drawer__links">
          ${NAV_ITEMS.map(item => `<a class="cg-nav-link" href="${item.href}" data-nav-key="${item.key}" data-g009-nav-key="${item.key}" data-g009-drawer-link><span>${icon(item.icon)}</span><span data-i18n="${item.i18n}">${item.label}</span></a>`).join('')}
          </div>
        </nav>
      </div>
      <div class="cg-nav-settings" data-g009-settings-dialog hidden>
        <div class="cg-nav-settings__backdrop" data-g009-settings-close></div>
        <section class="cg-nav-settings__panel" role="dialog" aria-modal="true" aria-labelledby="g009-settings-title">
          <div class="cg-nav-settings__header"><h2 id="g009-settings-title" data-i18n="g009.settings.title">Settings</h2><button type="button" data-g009-settings-close data-i18n-aria-label="g009.nav.close">×</button></div>
          <label data-i18n="g009.settings.language">Language</label><div data-g009-settings-language></div>
          <label class="cg-nav-settings__sound"><span data-i18n="g009.settings.sound">Sound</span><input type="checkbox" data-g009-settings-sound></label>
          <span data-g009-settings-sound-state aria-live="polite"></span>
        </section>
      </div>`;
    if (ownsE10Navigation()) {
      header.dataset.e10SessionStrip = '1';
      header.querySelector('.cg-nav-links')?.remove();
      if (!ownsE10MapNavigation()) header.querySelector('[data-g009-global-drawer]')?.remove();
    }
    if (old) old.replaceWith(header);
    else if (document.body) document.body.insertBefore(header, document.body.firstChild);
    // 語言切換鈕：搬移既有的；若該頁沒有，就現場生成一個（涵蓋所有用共用 nav 的頁面）
    const langSlot = header.querySelector('.cg-nav-lang');
    if (langSlot) {
      if (langSwitcher) {
        if (isPremiumSurface) {
          langSwitcher.style.position = 'static';
          langSwitcher.style.top = '';
          langSwitcher.style.right = '';
          langSwitcher.style.zIndex = '';
        }
        langSlot.appendChild(langSwitcher);
      } else if (typeof I18n !== 'undefined' && typeof I18n.renderSwitcher === 'function') {
        const box = document.createElement('span');
        box.id = 'lang-switcher-nav';
        langSlot.appendChild(box);
        I18n.renderSwitcher(box);
      }
    }
    // 套用翻譯到新建的 shared shell.
    if (typeof I18n !== 'undefined' && typeof I18n.apply === 'function') I18n.apply();
    bindShellControls(header);
    buildLearningSecondaryNav();
    window.dispatchEvent(new CustomEvent('cg-nav:ready', { detail: { version: window.__COLORFUL_GO_NAV_VERSION__ } }));
    buildVerifyBanner(header);
  }

  function bindShellControls(header) {
    if (!header || header.dataset.g009ShellBound === '1') return;
    header.dataset.g009ShellBound = '1';
    const hamburger = header.querySelector('[data-g009-hamburger]');
    const drawer = header.querySelector('[data-g009-global-drawer]');
    const playerTrigger = header.querySelector('[data-g009-player-trigger]');
    const playerMenu = header.querySelector('#g009-player-menu');
    const settingsDialog = header.querySelector('[data-g009-settings-dialog]');
    const pageLabel = header.querySelector('[data-g009-current-page-label]');
    const closePlayer = () => {
      if (!playerMenu) return;
      playerMenu.hidden = true;
      playerTrigger?.setAttribute('aria-expanded', 'false');
    };
    const closeDrawer = () => {
      if (drawer) drawer.hidden = true;
      hamburger?.setAttribute('aria-expanded', 'false');
      document.body.classList.remove('g009-nav-drawer-open');
      document.dispatchEvent(new CustomEvent('g009:global-nav-closed'));
    };
    const openSettings = () => {
      closePlayer();
      if (!settingsDialog) return;
      settingsDialog.hidden = false;
      document.body.classList.add('g009-settings-open');
      const language = settingsDialog.querySelector('[data-g009-settings-language]');
      if (language && typeof I18n !== 'undefined' && typeof I18n.renderSwitcher === 'function') I18n.renderSwitcher(language);
      const sound = settingsDialog.querySelector('[data-g009-settings-sound]');
      const state = settingsDialog.querySelector('[data-g009-settings-sound-state]');
      if (sound) sound.checked = !(window.SFX && window.SFX.muted);
      if (state) {
        const key = sound?.checked ? 'g009.settings.sound_on' : 'g009.settings.sound_off';
        state.dataset.i18n = key;
        state.textContent = t(key, sound?.checked ? 'On' : 'Off');
      }
      settingsDialog.querySelector('[data-g009-settings-close]')?.focus();
    };
    const closeSettings = () => {
      if (settingsDialog) settingsDialog.hidden = true;
      document.body.classList.remove('g009-settings-open');
    };
    const toggleDrawer = () => {
      const e10Owned = ownsE10Navigation();
      if (e10Owned && !ownsE10MapNavigation()) {
        const next = hamburger?.getAttribute('aria-expanded') !== 'true';
        hamburger?.setAttribute('aria-expanded', String(next));
        document.dispatchEvent(new CustomEvent('g009:global-nav-toggle', { detail: { open: next } }));
        return;
      }
      if (!drawer) return;
      const next = drawer.hidden;
      drawer.hidden = !next;
      hamburger?.setAttribute('aria-expanded', String(next));
      document.body.classList.toggle('g009-nav-drawer-open', next);
      if (next) drawer.querySelector('[data-g009-drawer-link]')?.focus();
      else closeDrawer();
    };
    hamburger?.addEventListener('click', toggleDrawer);
    drawer?.querySelectorAll('[data-g009-drawer-close]').forEach((el) => el.addEventListener('click', closeDrawer));
    drawer?.querySelectorAll('[data-g009-drawer-link]').forEach((el) => el.addEventListener('click', closeDrawer));
    playerTrigger?.addEventListener('click', (event) => {
      event.preventDefault();
      const next = playerMenu?.hidden !== false;
      closeDrawer();
      if (playerMenu) playerMenu.hidden = !next;
      playerTrigger.setAttribute('aria-expanded', String(next));
      if (next) playerMenu?.querySelector('[role="menuitem"]')?.focus();
    });
    header.querySelector('[data-g009-account="settings"]')?.addEventListener('click', openSettings);
    header.querySelector('[data-g009-account="logout"]')?.addEventListener('click', async () => {
      try { await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' }); } catch {}
      try { if (window.google?.accounts?.id) google.accounts.id.disableAutoSelect(); } catch {}
      location.href = '/login?from=logout';
    });
    if (header.querySelectorAll) {
      header.querySelectorAll('[data-g009-settings-close]').forEach((el) => el.addEventListener('click', closeSettings));
    }
    header.querySelector('[data-g009-settings-sound]')?.addEventListener('change', (event) => {
      if (window.SFX) window.SFX.muted = !event.currentTarget.checked;
      const state = settingsDialog?.querySelector('[data-g009-settings-sound-state]');
      if (state) {
        const key = event.currentTarget.checked ? 'g009.settings.sound_on' : 'g009.settings.sound_off';
        state.dataset.i18n = key;
        state.textContent = t(key, event.currentTarget.checked ? 'On' : 'Off');
      }
    });
    document.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape') return;
      closePlayer();
      closeDrawer();
      closeSettings();
    });
    if (pageLabel) {
      pageLabel.textContent = currentPageLabel();
      pageLabel.dataset.i18n = currentPageItem()?.pageI18n || 'g009.page.home';
    }
  }

  function reconcileNavigation() {
    const header = document.querySelector('header.cg-nav');
    if (!header) return;
    if (ownsE10Navigation()) {
      header.dataset.e10SessionStrip = '1';
      header.querySelector('.cg-nav-links')?.remove();
      if (ownsE10MapNavigation()) {
        if (!header.querySelector('[data-g009-global-drawer]')) buildNav();
      } else {
        header.querySelector('[data-g009-global-drawer]')?.remove();
      }
      return;
    }
    if (header.dataset.e10SessionStrip === '1' && !header.querySelector('.cg-nav-links')) {
      buildNav();
    }
  }

  // ── Email 未驗證提示橫幅 ─────────────────────────────────────
  const VERIFY_DISMISS_KEY = 'cg_verify_banner_dismissed';

  function todayStr() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }

  function t(key, fallback) {
    return (typeof I18n !== 'undefined' && typeof I18n.t === 'function' && I18n.t(key) !== key)
      ? I18n.t(key) : fallback;
  }

  function setI18nText(el, key, fallback) {
    if (!el) return;
    el.dataset.i18n = key;
    el.textContent = t(key, fallback);
  }

  function getAuthMe() {
    if (!window.__cgAuthMePromise) {
      window.__cgAuthMePromise = fetch('/api/auth/me', { credentials: 'include' })
        .then(res => res.json())
        .catch(() => null);
    }
    return window.__cgAuthMePromise;
  }

  async function buildVerifyBanner(header) {
    try {
      if (localStorage.getItem(VERIFY_DISMISS_KEY) === todayStr()) return;
    } catch {}
    let me;
    try {
      me = await getAuthMe();
    } catch { return; }
    if (!me || !me.logged_in || !me.has_email || me.email_verified) return;
    if (document.getElementById('cg-verify-banner')) return;

    const banner = document.createElement('div');
    banner.id = 'cg-verify-banner';
    banner.className = 'cg-verify-banner';
    banner.setAttribute('role', 'alert');
    banner.innerHTML = `
      <span class="cg-verify-icon" aria-hidden="true">✉️</span>
      <span class="cg-verify-msg" data-i18n="verify.banner.msg">你的 Email 尚未驗證，驗證後才能使用付款功能</span>
      <button type="button" class="cg-verify-resend" data-i18n="verify.banner.resend">重寄驗證信</button>
      <span class="cg-verify-status" aria-live="polite"></span>
      <button type="button" class="cg-verify-close" aria-label="關閉">✕</button>`;
    if (header && header.parentNode) {
      header.insertAdjacentElement('afterend', banner);
    } else {
      banner.classList.add('cg-verify-top');
      document.body.prepend(banner);
    }
    if (typeof I18n !== 'undefined' && typeof I18n.apply === 'function') I18n.apply();

    const resendBtn = banner.querySelector('.cg-verify-resend');
    const statusEl  = banner.querySelector('.cg-verify-status');
    resendBtn.addEventListener('click', async () => {
      resendBtn.disabled = true;
      statusEl.textContent = t('verify.banner.sending', '寄送中…');
      statusEl.className = 'cg-verify-status';
      try {
        const res = await fetch('/api/auth/resend_verification', {
          method: 'POST', credentials: 'include',
        });
        if (res.ok) {
          statusEl.textContent = t('verify.banner.sent', '已寄出，請收信');
          statusEl.classList.add('ok');
        } else if (res.status === 429) {
          statusEl.textContent = t('verify.banner.throttle', '寄送太頻繁，請稍後再試');
          statusEl.classList.add('warn');
          resendBtn.disabled = false;
        } else {
          statusEl.textContent = t('verify.banner.fail', '寄送失敗，請稍後再試');
          statusEl.classList.add('warn');
          resendBtn.disabled = false;
        }
      } catch {
        statusEl.textContent = t('verify.banner.fail', '寄送失敗，請稍後再試');
        statusEl.classList.add('warn');
        resendBtn.disabled = false;
      }
    });
    banner.querySelector('.cg-verify-close').addEventListener('click', () => {
      try { localStorage.setItem(VERIFY_DISMISS_KEY, todayStr()); } catch {}
      banner.remove();
    });
  }

  function ensureSocketIo() {
    if (window.io) return Promise.resolve();
    if (window.__cgSocketIoLoading) return window.__cgSocketIoLoading;
    window.__cgSocketIoLoading = new Promise((resolve, reject) => {
      const existing = document.querySelector('script[data-cg-socketio="1"]');
      if (existing) {
        existing.addEventListener('load', () => resolve(), { once: true });
        existing.addEventListener('error', () => reject(new Error('socket.io load failed')), { once: true });
        return;
      }
      const script = document.createElement('script');
      script.dataset.cgSocketio = '1';
      script.src = SOCKET_IO_CLIENT_SRC;
      script.crossOrigin = 'anonymous';
      script.onload = () => resolve();
      script.onerror = () => reject(new Error('socket.io load failed'));
      document.head.appendChild(script);
    });
    return window.__cgSocketIoLoading;
  }

  async function initPresence() {
    const path = normalize(location.pathname);
    if (path === '/play' || path === '/' || path === '/index.html' || path === '/login' || path === '/landing') return;
    const chip = document.getElementById('cg-presence-chip');
    const text = document.getElementById('cg-presence-text');
    const count = document.getElementById('cg-presence-count');
    if (!chip || !text || !count) return;

    let me = null;
    try {
      me = await getAuthMe();
    } catch {
      chip.hidden = true;
      return;
    }
    if (!me || !me.logged_in) {
      chip.hidden = true;
      return;
    }

    chip.hidden = false;
    chip.className = 'cg-nav-presence';
    setI18nText(text, 'nav.presence.connecting', '連線中');

    try {
      await ensureSocketIo();
      const sock = window.__cgArenaSocket && window.__cgArenaSocket.connected
        ? window.__cgArenaSocket
        : (window.__cgArenaSocket = io(location.origin, { transports: ['websocket', 'polling'] }));
      if (!sock.__cgNavPresenceBound) {
        sock.__cgNavPresenceBound = true;
        sock.on('connect_error', () => {
          chip.className = 'cg-nav-presence dnd';
          setI18nText(text, 'nav.presence.unavailable', '通知未連線');
        });
        sock.on('disconnect', () => {
          chip.className = 'cg-nav-presence dnd';
          setI18nText(text, 'nav.presence.reconnecting', '重新連線中');
        });
        sock.on('connect', () => {
          try {
            sock.emit('enter_lobby', {
              name: me.display_name || me.username || 'Player',
              activity: 'study',
              availability: 'open',
              focus_until: 0,
            });
          } catch {}
        });
        sock.on('lobby_update', payload => {
          const players = Array.isArray(payload) ? payload : (payload && payload.players) || [];
          const invites = Array.isArray(payload && payload.pending_invites) ? payload.pending_invites : [];
          const meRow = players.find(p => p.sid === sock.id) || players.find(p => p.username && me.username && p.username === me.username);
          if (meRow) {
            const availability = meRow.availability || (meRow.dnd ? 'dnd' : 'open');
            const activity = meRow.activity || 'study';
            chip.className = 'cg-nav-presence ' + (activity === 'study' ? 'study' : activity === 'match' ? 'match' : availability === 'dnd' ? 'dnd' : '');
            if (activity === 'study') {
              setI18nText(text, 'nav.presence.study', '做題中');
            } else if (activity === 'match') {
              setI18nText(text, 'nav.presence.match', '對局中');
            } else if (availability === 'quiet') {
              setI18nText(text, 'nav.presence.quiet', '安靜接收');
            } else if (availability === 'match_only') {
              setI18nText(text, 'nav.presence.match_only', '只接競技場');
            } else {
              setI18nText(text, 'nav.presence.online', '在線');
            }
          }
          const unread = invites.length;
          if (unread > 0) {
            count.hidden = false;
            count.textContent = String(unread);
          } else {
            count.hidden = true;
            count.textContent = '';
          }
        });
      }
      if (sock.connected) {
        try {
          sock.emit('enter_lobby', {
            name: me.display_name || me.username || 'Player',
            activity: 'study',
            availability: 'open',
            focus_until: 0,
          });
        } catch {}
      }
      if (!window.__cgArenaPresenceHeartbeat) {
        window.__cgArenaPresenceHeartbeat = setInterval(() => {
          if (sock.connected) {
            sock.emit('heartbeat', { activity: 'study', availability: 'open', focus_until: 0 });
          }
        }, 30000);
      }
    } catch {
      chip.className = 'cg-nav-presence dnd';
      setI18nText(text, 'nav.presence.unavailable', '通知未連線');
    }
  }

  // ── G009 Night Atlas shared visual layer ─────────────────────────
  // One token family + one definition per shared component for every
  // surface that loads the shared shell. Pages keep their own layout; the
  // skin (colour, border, radius, shadow, type) is owned here. Gold marks
  // selected/current; cyan is reserved for live character state.
  // It ships inside this script because every surface already loads it
  // network-first; a standalone stylesheet needs a new static route and
  // packaging entry, which is outside a visual-only change.
  const NA_PROGRESS = 'body[data-g009-surface="learning-progress"]';
  const NA_TAVERN = 'body[data-g009-surface="tavern"]';
  const NA_SHOP = 'body[data-g009-surface="shop"]';
  const NA_BACKPACK = 'body[data-g009-surface="backpack"]';
  const NIGHT_ATLAS_CSS = `
      :root {
        --na-navy-950: #070d22; --na-navy-900: #0b1430; --na-navy-800: #111d3d;
        --na-panel: rgba(17,29,61,.88); --na-panel-hi: rgba(35,53,96,.78);
        --na-inset: rgba(255,236,190,.045); --na-glass: rgba(9,16,38,.9);
        --na-gold-100: #fff1c4; --na-gold-300: #e3b457; --na-gold-500: #a9762b;
        --na-gold-edge: rgba(236,201,120,.42); --na-gold-hair: rgba(236,201,120,.2);
        --na-gold-tint: rgba(227,180,87,.13);
        --na-cyan-100: #d5fff2; --na-cyan-300: #45d6c0; --na-cyan-edge: rgba(69,214,192,.68);
        --na-text: #f7f1df; --na-text-soft: #c7cce0; --na-text-muted: #919bb8;
        --na-success: #7fe0a6; --na-danger: #f08a8a;
        --na-radius-xs: 8px; --na-radius-sm: 12px; --na-radius-md: 16px; --na-radius-lg: 22px;
        --na-shadow-1: 0 8px 22px rgba(0,0,0,.24); --na-shadow-2: 0 18px 50px rgba(0,0,0,.34);
        --na-space-1: 4px; --na-space-2: 8px; --na-space-3: 12px; --na-space-4: 16px;
        --na-space-5: 24px; --na-space-6: 32px;
        --na-text-xs: 12px; --na-text-sm: 14px; --na-text-md: 16px; --na-text-lg: 20px; --na-text-xl: 28px;
        --na-font-display: 'Cormorant Garamond', 'Noto Serif TC', 'Songti TC', 'PingFang TC', Georgia, serif;
        --na-font-body: 'DM Sans', 'Noto Sans TC', 'PingFang TC', 'Microsoft JhengHei', system-ui, sans-serif;
        --na-font-mono: 'DM Mono', ui-monospace, monospace;
        --na-target: 44px;
        --na-page-bg: radial-gradient(1100px 520px at 50% -8%, rgba(227,180,87,.1), transparent 62%), linear-gradient(180deg, #0b1430 0%, #070d22 62%);
      }
      @media (min-width: 768px) { :root { --na-target: 48px; } }

      /* Page canvas: the calm ledger tier shares one navy ground. Each page
         paints that ground itself (so first paint is already navy); this
         rule only aligns text colour and the body face. Curriculum Map keeps
         its own text colours. */
      ${NA_PROGRESS}, ${NA_TAVERN}, ${NA_SHOP}, ${NA_BACKPACK} {
        color: var(--na-text); font-family: var(--na-font-body);
      }

      /* Panel: one border, one radius. */
      .na-panel,
      ${NA_PROGRESS} .card, ${NA_PROGRESS} .stat-card, ${NA_PROGRESS} #xp-rank-bar-wrap,
      ${NA_TAVERN} .panel, ${NA_TAVERN} .hero,
      ${NA_SHOP} .panel, ${NA_SHOP} .wallet-tile, ${NA_SHOP} .status-tile, ${NA_SHOP} .shop-purchase-state,
      ${NA_SHOP} .cosmetic-modal-card,
      ${NA_BACKPACK} .stats-strip, ${NA_BACKPACK} .functional-equipment-detail {
        border: 1px solid var(--na-gold-hair); border-radius: var(--na-radius-md);
        background: linear-gradient(180deg, var(--na-panel-hi), var(--na-panel));
        box-shadow: var(--na-shadow-1); color: var(--na-text-soft);
      }

      /* Card: sits inside a panel or a grid; the item art supplies the colour. */
      .na-card,
      ${NA_TAVERN} .item-card, ${NA_TAVERN} .quick-row, ${NA_TAVERN} .task-card, ${NA_TAVERN} .progress-box,
      ${NA_SHOP} .item-card, ${NA_SHOP} .cosmetic-card, ${NA_SHOP} .equipment-detail,
      ${NA_SHOP} .equipment-purchase-feedback, ${NA_SHOP} .speech,
      ${NA_BACKPACK} .backpack-card, ${NA_BACKPACK} .functional-equipment-card,
      ${NA_BACKPACK} .functional-wearable-preview, ${NA_BACKPACK} .backpack-status,
      ${NA_BACKPACK} .functional-equipment-status {
        border: 1px solid var(--na-gold-hair); border-radius: var(--na-radius-sm);
        background: var(--na-inset); box-shadow: none; color: var(--na-text-soft);
      }
      ${NA_SHOP} .item-card::before { display: none; }
      ${NA_BACKPACK} .functional-equipment-card:hover,
      ${NA_BACKPACK} .functional-equipment-card:focus-visible {
        border-color: var(--na-gold-edge); box-shadow: var(--na-shadow-1); outline: none;
      }
      /* Gold = the selected item. */
      ${NA_BACKPACK} .functional-equipment-card[data-selected="true"],
      ${NA_SHOP} .equipment-card[aria-selected="true"], ${NA_SHOP} .equipment-card.is-selected {
        border-color: var(--na-gold-300); background: var(--na-gold-tint);
        box-shadow: 0 0 0 1px var(--na-gold-300);
      }
      ${NA_BACKPACK} .functional-equipment-card[data-equipped="true"]::after {
        background: var(--na-gold-300); color: #1b1404;
      }

      /* Buttons: primary, secondary, quiet. */
      .na-btn,
      ${NA_PROGRESS} .weakness-action,
      ${NA_TAVERN} .btn, ${NA_TAVERN} .roster-cta,
      ${NA_SHOP} .btn.secondary, ${NA_SHOP} .btn.ghost,
      ${NA_BACKPACK} .backpack-shop-link, ${NA_BACKPACK} .functional-equipment-link,
      ${NA_BACKPACK} .functional-detail-action.secondary {
        min-height: var(--na-target); border: 1px solid var(--na-gold-edge); border-radius: var(--na-radius-sm);
        background: var(--na-gold-tint); color: var(--na-gold-100); box-shadow: none; text-shadow: none;
        font-weight: 800;
      }
      .na-btn--primary,
      ${NA_PROGRESS} .stats-cta,
      ${NA_TAVERN} .btn-primary,
      ${NA_SHOP} .btn:not(.secondary):not(.ghost):not([data-g009-shop-purchase-disabled]) {
        min-height: var(--na-target); border: 1px solid rgba(255,241,196,.5); border-radius: var(--na-radius-sm);
        background: linear-gradient(180deg, #f6dd9a, var(--na-gold-300) 58%, var(--na-gold-500));
        color: #1b1404; box-shadow: 0 6px 16px rgba(0,0,0,.28); text-shadow: none; font-weight: 800;
      }
      .na-btn--quiet,
      ${NA_TAVERN} .btn-danger {
        border-color: rgba(240,138,138,.4); background: transparent; color: var(--na-danger);
      }
      ${NA_TAVERN} .btn[disabled], ${NA_TAVERN} .btn-disabled {
        border-color: var(--na-gold-hair); background: transparent; color: var(--na-text-muted); opacity: .7;
      }

      /* Status tag: owned / equipped / coming soon. Never an action. */
      .na-tag,
      ${NA_SHOP} .shop-preview-status,
      ${NA_SHOP} .btn[data-g009-shop-purchase-disabled="browse-preview"],
      ${NA_SHOP} .equipment-ownership-badge,
      ${NA_TAVERN} .pill, ${NA_TAVERN} .rank-badge,
      ${NA_BACKPACK} .functional-equipment-badge, ${NA_BACKPACK} .functional-detail-badge {
        display: inline-flex; align-items: center; width: auto; min-height: 26px; flex: 0 0 auto;
        padding: 2px 10px; border: 1px solid var(--na-gold-hair); border-radius: 999px;
        background: transparent; color: var(--na-text-muted); box-shadow: none;
        font: 700 12px/1.3 var(--na-font-body); letter-spacing: .02em; white-space: nowrap;
      }
      ${NA_SHOP} .btn[data-g009-shop-purchase-disabled="browse-preview"] {
        opacity: 1; cursor: default; transform: none; filter: none; justify-self: start; align-self: center;
      }
      ${NA_TAVERN} .pill.active, ${NA_BACKPACK} .backpack-action-state { color: var(--na-gold-100); border-color: var(--na-gold-edge); }
      /* D5: while the Shop is browse-preview, the equipment purchase control is
         the same quiet status tag ("Coming Soon" / "Owned"), not a gold button. */
      body[data-g009-surface="shop"][data-g009-shop-mode="browse-preview"] .btn[data-equipment-purchase]:not(.secondary):not(.ghost) {
        display: inline-flex; align-items: center; justify-content: center; width: auto; min-height: 26px; flex: 0 0 auto;
        padding: 2px 10px; border: 1px solid var(--na-gold-hair); border-radius: 999px;
        background: transparent; color: var(--na-text-muted); box-shadow: none;
        font: 700 12px/1.3 var(--na-font-body); white-space: nowrap;
        opacity: 1; cursor: default; transform: none; filter: none; justify-self: start; align-self: center;
      }
      ${NA_BACKPACK} .functional-detail-badge { max-width: 100%; white-space: normal; }

      /* Segmented tabs and filter chips. */
      .na-tabs,
      ${NA_TAVERN} .tabs {
        border: 1px solid var(--na-gold-hair); border-radius: var(--na-radius-md);
        background: linear-gradient(180deg, rgba(16,26,56,.96), rgba(8,14,34,.96)); box-shadow: var(--na-shadow-1);
      }
      .na-tab,
      ${NA_TAVERN} .tab, ${NA_TAVERN} .subtab,
      ${NA_BACKPACK} .backpack-filter, ${NA_BACKPACK} .functional-equipment-filter {
        min-height: var(--na-target); border: 1px solid transparent; border-radius: var(--na-radius-sm);
        background: transparent; color: var(--na-text-soft); box-shadow: none;
        font-size: 13px; font-weight: 800;
      }
      ${NA_TAVERN} .subtab, ${NA_BACKPACK} .backpack-filter, ${NA_BACKPACK} .functional-equipment-filter {
        border-color: var(--na-gold-hair); border-radius: 999px; padding: 0 16px;
      }
      .na-tab:hover,
      ${NA_TAVERN} .tab:hover, ${NA_TAVERN} .subtab:hover,
      ${NA_BACKPACK} .backpack-filter:hover, ${NA_BACKPACK} .functional-equipment-filter:hover {
        color: var(--na-gold-100); border-color: var(--na-gold-hair); background: rgba(227,180,87,.07);
      }
      .na-tab.is-active, .na-tab[aria-selected="true"],
      .g009-learning-secondary__item.is-active,
      ${NA_TAVERN} .tab.active, ${NA_TAVERN} .subtab.active,
      ${NA_BACKPACK} .backpack-filter[aria-selected="true"],
      ${NA_BACKPACK} .functional-equipment-filter[aria-selected="true"] {
        color: var(--na-gold-100); border-color: var(--na-gold-edge); background: var(--na-gold-tint);
        box-shadow: inset 0 -2px 0 var(--na-gold-300);
      }

      /* Section heading: kicker + title + hairline rule. */
      .na-kicker,
      ${NA_PROGRESS} .section-label, ${NA_PROGRESS} .today-sub-label,
      ${NA_TAVERN} .kicker, ${NA_TAVERN} .eyebrow,
      ${NA_SHOP} .section-kicker, ${NA_SHOP} .eyebrow,
      ${NA_BACKPACK} .section-label, ${NA_BACKPACK} .backpack-kicker, ${NA_BACKPACK} .functional-equipment-kicker,
      ${NA_BACKPACK} .functional-detail-section h3, ${NA_BACKPACK} .functional-wearable-preview-title {
        color: var(--na-gold-300); font: 800 12px/1.3 var(--na-font-body); letter-spacing: .12em;
        text-transform: uppercase; text-shadow: none;
      }
      .na-title,
      ${NA_TAVERN} .panel-title, ${NA_TAVERN} .item-title, ${NA_TAVERN} .hero h1,
      ${NA_SHOP} .section-title, ${NA_SHOP} h1,
      ${NA_BACKPACK} .backpack-heading h1 {
        color: var(--na-gold-100); font-family: var(--na-font-display); font-weight: 800;
        letter-spacing: .01em; text-shadow: none;
      }
      ${NA_SHOP} h1, ${NA_BACKPACK} .backpack-heading h1, ${NA_TAVERN} .hero h1 {
        font-size: clamp(26px, 3.6vw, 40px); line-height: 1.15;
      }
      ${NA_PROGRESS} .section-label::after, ${NA_BACKPACK} .section-label::after { background: var(--na-gold-hair); }

      /* Stat tile: one large readable figure, one quiet label. */
      .na-stat__value,
      ${NA_PROGRESS} .stat-card .stat-value, ${NA_PROGRESS} .today-big,
      ${NA_TAVERN} .stat-value,
      ${NA_SHOP} .tile-value,
      ${NA_BACKPACK} .strip-stat .s-val {
        color: var(--na-gold-100); font-family: var(--na-font-display); font-weight: 700;
        line-height: 1.05; text-shadow: none;
      }
      .na-stat__label,
      ${NA_PROGRESS} .stat-card .stat-label,
      ${NA_TAVERN} .stat-label,
      ${NA_SHOP} .tile-label, ${NA_SHOP} .tile-sub,
      ${NA_BACKPACK} .strip-stat .s-lbl {
        color: var(--na-text-muted); font: 600 12px/1.35 var(--na-font-body); letter-spacing: .02em; text-shadow: none;
      }

      /* Empty state: icon, one line, optional link. */
      .na-empty,
      ${NA_PROGRESS} .empty-state,
      ${NA_TAVERN} .empty,
      ${NA_SHOP} .load-state,
      ${NA_BACKPACK} .backpack-empty, ${NA_BACKPACK} .functional-equipment-empty {
        border: 1px dashed var(--na-gold-hair); border-radius: var(--na-radius-md);
        background: rgba(7,13,34,.4); color: var(--na-text-muted); font-size: 13px; line-height: 1.6;
      }
      ${NA_BACKPACK} .functional-equipment-detail[data-empty="true"] { color: var(--na-text-muted); }

      /* Fields. */
      .na-field,
      ${NA_TAVERN} .search, ${NA_TAVERN} .input, ${NA_TAVERN} .select, ${NA_TAVERN} textarea {
        min-height: var(--na-target); border: 1px solid var(--na-gold-hair); border-radius: var(--na-radius-sm);
        background: rgba(7,13,34,.6); color: var(--na-text);
      }
      ${NA_TAVERN} .search:focus, ${NA_TAVERN} .input:focus, ${NA_TAVERN} .select:focus, ${NA_TAVERN} textarea:focus {
        border-color: var(--na-gold-edge); outline: 2px solid rgba(227,180,87,.35); outline-offset: 1px;
      }

      /* Shared focus ring for the ledger tier. */
      ${NA_PROGRESS} a:focus-visible, ${NA_PROGRESS} button:focus-visible,
      ${NA_TAVERN} a:focus-visible, ${NA_TAVERN} button:focus-visible,
      ${NA_SHOP} a:focus-visible, ${NA_SHOP} button:focus-visible, ${NA_SHOP} .btn:focus-visible,
      ${NA_BACKPACK} a:focus-visible, ${NA_BACKPACK} button:focus-visible {
        outline: 2px solid var(--na-gold-100); outline-offset: 2px;
      }
  `;

  function injectStyles() {
    let style = document.getElementById('cg-nav-style');
    if (!style) {
      style = document.createElement('style');
      style.id = 'cg-nav-style';
      document.head.appendChild(style);
    }
    style.textContent = NIGHT_ATLAS_CSS + `
      :root { --cg-nav-h: 58px; }
      /* No backdrop-filter on the bar itself: Chromium treats a filtered
         element as the containing block for position:fixed descendants, which
         sized the drawer and the settings dialog to the 58px bar instead of
         the viewport. The bar is 96% opaque, so the blur was not visible. */
      .cg-nav {
        position: sticky; top: 0; z-index: 1000;
        height: var(--cg-nav-h); padding: 0 18px;
        background: linear-gradient(180deg, rgba(16,24,50,.96), rgba(7,13,34,.96));
        border-bottom: 1px solid var(--na-gold-hair);
        box-shadow: 0 10px 30px rgba(0,0,0,.32);
        font-family: var(--na-font-body);
      }
      .cg-nav-inner {
        max-width: 1480px; height: 100%; margin: 0 auto;
        display: grid; grid-template-columns: auto auto auto minmax(0,1fr) auto;
        align-items: center; gap: 14px;
      }
      .cg-nav-hamburger {
        width: 44px; height: 44px; min-width: 44px; min-height: 44px; display: none; flex-direction: column;
        align-items: center; justify-content: center; gap: 4px; padding: 0;
        border: 1px solid var(--na-gold-hair); border-radius: var(--na-radius-sm);
        color: var(--na-gold-100); background: var(--na-inset); cursor: pointer;
      }
      .cg-nav-hamburger span { width: 17px; height: 2px; border-radius: 99px; background: currentColor; }
      .cg-nav-hamburger:focus-visible { outline: 2px solid var(--na-gold-100); outline-offset: 2px; }
      .cg-brand {
        display: inline-flex; align-items: center; gap: 9px;
        color: var(--na-gold-100); text-decoration: none; min-width: 44px; min-height: 44px;
        box-sizing: border-box;
        font-family: var(--na-font-display);
        font-size: 18px; font-weight: 700; white-space: nowrap;
      }
      /* Round gold-ringed emblem: the goban glyph on a navy medallion. */
      .cg-brand-mark {
        width: 32px; height: 32px; border-radius: 50%; flex: 0 0 auto; overflow: hidden;
        background: radial-gradient(circle at 50% 32%, #2a3d72, var(--na-navy-900) 76%);
        border: 1px solid var(--na-gold-300); position: relative;
        box-shadow: 0 0 0 2px rgba(227,180,87,.16), 0 4px 12px rgba(0,0,0,.3);
      }
      .cg-brand-mark::before {
        content: ''; position: absolute; inset: 7px;
        background:
          linear-gradient(var(--na-gold-300) 1px, transparent 1px),
          linear-gradient(90deg, var(--na-gold-300) 1px, transparent 1px);
        background-size: 6px 6px; opacity: .42;
      }
      .cg-brand-mark span::before,
      .cg-brand-mark span::after {
        content: ''; position: absolute; width: 6px; height: 6px; border-radius: 50%;
        top: 17px; left: 10px; background: var(--na-navy-950); border: 1px solid var(--na-gold-300);
      }
      .cg-brand-mark span::after { top: 9px; left: 18px; background: var(--na-gold-100); border-color: var(--na-gold-100); }
      .cg-nav-links {
        justify-self: stretch; min-width: 0; max-width: 100%;
        display: flex; align-items: center; justify-content: center; gap: 3px;
        overflow-x: auto; overscroll-behavior-inline: contain; scrollbar-width: none;
      }
      .cg-nav-page-label {
        min-width: 72px; color: var(--na-gold-300); font-size: 12px; font-weight: 800;
        white-space: nowrap;
      }
      .cg-brand-en { display: inline; }
      @media (max-width: 1360px) { .cg-brand-en { display: none; } }
      .cg-nav-links::-webkit-scrollbar { display: none; }
      .cg-nav-link {
        height: 44px; min-height: 44px; min-width: 44px; box-sizing: border-box; flex: 0 0 auto;
        display: inline-flex; align-items: center; gap: 6px;
        padding: 0 10px; border-radius: var(--na-radius-sm);
        color: var(--na-text-soft); text-decoration: none; font-size: 13px; font-weight: 700;
        white-space: nowrap; border: 1px solid transparent;
        transition: background .16s, border-color .16s, color .16s, box-shadow .16s;
      }
      .cg-nav-badge {
        min-width: 17px; height: 17px; padding: 0 5px; border-radius: 99px;
        display: inline-flex; align-items: center; justify-content: center;
        font-size: 12px; font-weight: 800; line-height: 1;
        background: #dc2626; color: #fff;
      }
      .cg-nav-link:hover {
        color: var(--na-gold-100); background: rgba(227,180,87,.07); border-color: var(--na-gold-hair);
      }
      /* Gold = you are here: tinted ground with a gold underline. */
      .cg-nav-link.active {
        color: var(--na-gold-100); background: var(--na-gold-tint);
        border-color: var(--na-gold-hair); box-shadow: inset 0 -2px 0 var(--na-gold-300);
      }
      .cg-nav-link:focus-visible { outline: 2px solid var(--na-gold-100); outline-offset: 2px; }
      .cg-nav-icon {
        width: 18px; height: 18px; flex: 0 0 auto;
        fill: none; stroke: currentColor; stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round;
      }
      .cg-nav-actions { display: inline-flex; align-items: center; gap: 8px; justify-content: flex-end; min-width: 0; }
      .cg-nav-player {
        display: inline-flex; align-items: center; gap: 6px; min-width: 0; min-height: 44px; flex: 0 0 auto;
        border: 1px solid var(--na-gold-hair); border-radius: var(--na-radius-sm);
        padding: 4px 8px 4px 5px; color: var(--na-gold-100); background: var(--na-inset);
        cursor: pointer;
      }
      .cg-nav-player:focus-visible { outline: 2px solid var(--na-gold-100); outline-offset: 2px; }
      .cg-nav-player-avatar { width: 28px; height: 28px; display: inline-flex; align-items: center; justify-content: center; border-radius: 50%; border: 1px solid var(--na-gold-300); background: radial-gradient(circle at 50% 30%, #2a3d72, var(--na-navy-900) 78%); color: var(--na-gold-100); font-size: 12px; font-weight: 900; }
      .cg-nav-user {
        max-width: 110px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        color: var(--na-text-soft); font-size: 12px; font-weight: 700;
      }
      .cg-nav-player-chevron { color: var(--na-text-muted); font-size: 15px; line-height: 1; }
      .cg-nav-menu {
        position: absolute; top: calc(var(--cg-nav-h) - 2px); right: 18px; z-index: 1100;
        min-width: 172px; padding: 6px; border: 1px solid var(--na-gold-edge);
        border-radius: var(--na-radius-sm); background: linear-gradient(180deg, #17213f, #0b1430);
        box-shadow: var(--na-shadow-2);
      }
      .cg-nav-menu[hidden], .cg-nav-drawer[hidden], .cg-nav-settings[hidden] { display: none !important; }
      .cg-nav-menu a, .cg-nav-menu button {
        width: 100%; min-height: var(--na-target); display: flex; align-items: center;
        padding: 0 12px; border: 0; border-radius: var(--na-radius-xs); color: var(--na-text);
        background: transparent; text-decoration: none; text-align: left; cursor: pointer; font: inherit;
      }
      .cg-nav-menu a:hover, .cg-nav-menu button:hover,
      .cg-nav-menu a:focus-visible, .cg-nav-menu button:focus-visible { background: var(--na-gold-tint); color: var(--na-gold-100); outline: none; }
      .cg-nav-drawer, .cg-nav-settings { position: fixed; inset: 0; z-index: 1300; }
      .cg-nav-drawer__backdrop, .cg-nav-settings__backdrop { position: absolute; inset: 0; background: rgba(4,8,22,.68); }
      .cg-nav-drawer__panel, .cg-nav-settings__panel {
        position: absolute; top: 0; left: 0; bottom: 0; width: min(360px, 88vw);
        padding: 18px; overflow-y: auto; color: var(--na-text);
      }
      .cg-nav-drawer__header, .cg-nav-settings__header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
      .cg-nav-drawer__header h2, .cg-nav-settings__header h2 { margin: 0; font-size: 20px; }
      .cg-nav-drawer__header button, .cg-nav-settings__header button { width: 44px; min-width: 44px; height: 44px; min-height: 44px; border-radius: var(--na-radius-sm); font-size: 22px; cursor: pointer; }
      .cg-nav-drawer__links { display: grid; gap: 8px; }
      .cg-nav-drawer__links .cg-nav-link { justify-content: flex-start; min-height: 48px; font-size: 14px; }
      .cg-nav-drawer__links .cg-nav-link span { display: inline-flex; }

      /* Owner real-iPad corrective: the global drawer is part of the shared
         G009 app shell, so it uses the same dark navy / black-gold visual
         language as the top shell. Owner decision D6 moves the settings
         modal onto the same dark surface (see the settings rules below). */
      .cg-nav-drawer__panel {
        border-right: 1px solid rgba(251,191,36,.24);
        background:
          radial-gradient(520px 280px at 12% 0%, rgba(244,213,138,.12), transparent 62%),
          linear-gradient(180deg, #17213f 0%, #101832 48%, #070d24 100%);
        box-shadow: 18px 0 42px rgba(0,0,0,.48);
      }
      .cg-nav-drawer__header h2 {
        color: var(--na-gold-100);
        font-family: var(--na-font-display);
        font-weight: 800;
        letter-spacing: .01em;
      }
      .cg-nav-drawer__header button {
        border: 1px solid var(--na-gold-hair);
        background: var(--na-inset);
        color: var(--na-gold-100);
      }
      .cg-nav-drawer__header button:hover,
      .cg-nav-drawer__header button:focus-visible {
        border-color: var(--na-gold-edge);
        background: var(--na-gold-tint);
      }
      .cg-nav-drawer__links .cg-nav-link {
        color: var(--na-text);
        border-color: var(--na-gold-hair);
        background: var(--na-inset);
      }
      .cg-nav-drawer__links .cg-nav-link:hover,
      .cg-nav-drawer__links .cg-nav-link:focus-visible {
        color: var(--na-gold-100);
        border-color: var(--na-gold-edge);
        background: rgba(227,180,87,.08);
      }
      .cg-nav-drawer__links .cg-nav-link.active {
        color: var(--na-gold-100);
        border-color: var(--na-gold-edge);
        background: var(--na-gold-tint);
        box-shadow: inset 3px 0 0 var(--na-gold-300);
      }
      /* D6: the settings modal is a dark Night Atlas dialog, like the drawer. */
      .cg-nav-settings__panel {
        left: 50%; top: 50%; bottom: auto; transform: translate(-50%, -50%);
        width: min(420px, calc(100vw - 32px)); border: 1px solid var(--na-gold-edge);
        border-radius: var(--na-radius-md);
        background: linear-gradient(180deg, #17213f 0%, #101832 48%, #070d24 100%);
        box-shadow: var(--na-shadow-2);
      }
      .cg-nav-settings__header h2 { color: var(--na-gold-100); font-family: var(--na-font-display); font-weight: 800; }
      .cg-nav-settings__header button { border: 1px solid var(--na-gold-hair); background: var(--na-inset); color: var(--na-gold-100); }
      .cg-nav-settings__header button:hover,
      .cg-nav-settings__header button:focus-visible { border-color: var(--na-gold-edge); background: var(--na-gold-tint); }
      .cg-nav-settings__panel > label { display: block; margin: 14px 0 6px; color: var(--na-text); font-weight: 750; }
      .cg-nav-settings__sound { display: flex !important; align-items: center; justify-content: space-between; min-height: var(--na-target); }
      .cg-nav-settings__sound input { width: 22px; height: 22px; accent-color: var(--na-gold-300); }
      .cg-nav-settings__panel [data-g009-settings-sound-state] { display: block; margin-top: 5px; color: var(--na-text-muted); font-size: 12px; }
      .g009-learning-secondary {
        position: relative; z-index: 20; width: min(1480px, calc(100% - 36px)); margin: 14px auto 0;
        display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 6px;
        padding: 7px; border: 1px solid var(--na-gold-hair); border-radius: var(--na-radius-md);
        background: linear-gradient(180deg, rgba(16, 26, 56, .96), rgba(8, 14, 34, .96));
        box-shadow: var(--na-shadow-1); font-family: var(--na-font-body);
      }
      .g009-learning-secondary__item {
        min-width: 0; min-height: 48px; display: inline-flex; align-items: center; justify-content: center;
        padding: 0 10px; border: 1px solid transparent; border-radius: var(--na-radius-sm);
        color: var(--na-text-soft); text-decoration: none; text-align: center;
        font-size: 13px; font-weight: 800; line-height: 1.25; white-space: nowrap;
        transition: background .16s, border-color .16s, color .16s, box-shadow .16s;
      }
      .g009-learning-secondary__item:hover,
      .g009-learning-secondary__item:focus-visible {
        color: var(--na-gold-100); background: rgba(227,180,87,.07); border-color: var(--na-gold-hair);
      }
      .g009-learning-secondary__item:focus-visible { outline: 2px solid var(--na-gold-100); outline-offset: 2px; }
      .g009-surface-heading {
        display: grid; gap: 6px; max-width: 560px; margin: 0 0 12px;
        color: var(--na-text);
      }
      .g009-surface-heading__kicker {
        color: var(--na-gold-300); font: 800 12px/1.2 var(--na-font-mono); letter-spacing: .18em;
      }
      .g009-surface-heading h1 { margin: 0; color: var(--na-gold-100); font-family: var(--na-font-display); font-size: clamp(26px, 3.6vw, 40px); line-height: 1.15; }
      .g009-surface-heading p { margin: 0; color: var(--na-text-soft); line-height: 1.6; }
      body[data-g009-surface="learning-progress"] .stats-col-weak,
      body[data-g009-surface="learning-progress"] .stats-col-c,
      body[data-g009-surface="learning-progress"] .stat-delta { display: none !important; }
      body[data-g009-surface="learning-progress"] .stats-grid3 { grid-template-columns: minmax(0, 1fr) !important; }
      body[data-g009-surface="learning-progress"] [data-g009-surface-root]::before {
        content: 'PLAYER JOURNAL'; display: block; margin: 0 0 8px; color: var(--na-gold-300);
        font: 800 12px/1.2 var(--na-font-mono); letter-spacing: .16em;
      }
      body[data-g009-surface="backpack"] .backpack-use,
      body[data-g009-surface="backpack"] #functional-detail-action { display: none !important; }
      body[data-g009-surface="backpack"] .functional-detail-actions { justify-content: flex-end; }
      .cg-nav-presence {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 0 10px; height: 28px; border-radius: 999px;
        background: var(--na-inset); border: 1px solid var(--na-gold-hair);
        color: var(--na-text-soft); font-size: 12px; font-weight: 750; white-space: nowrap;
      }
      .cg-nav-presence-dot {
        width: 8px; height: 8px; border-radius: 50%;
        background: #86efac; box-shadow: 0 0 0 3px rgba(34,197,94,.14);
      }
      .cg-nav-presence.study .cg-nav-presence-dot {
        background: var(--na-gold-300); box-shadow: 0 0 0 3px rgba(227,180,87,.16);
      }
      .cg-nav-presence.match .cg-nav-presence-dot {
        background: #60a5fa; box-shadow: 0 0 0 3px rgba(96,165,250,.16);
      }
      .cg-nav-presence.dnd .cg-nav-presence-dot {
        background: #f87171; box-shadow: 0 0 0 3px rgba(248,113,113,.16);
      }
      .cg-nav-presence-count {
        min-width: 18px; height: 18px; padding: 0 6px; border-radius: 999px;
        display: inline-flex; align-items: center; justify-content: center;
        background: #dc2626; color: #fff; font-size: 12px; font-weight: 800;
      }
      .cg-nav-presence[hidden], .cg-nav-presence-count[hidden] { display: none; }
      .cg-nav-lang { display: inline-flex; align-items: center; }
      .cg-nav-lang .i18n-switcher-btn { min-width: 44px; min-height: 44px; }
      /* Language switch. i18n.js paints it with inline cream styles for the
         light pages; inside the dark shell and the settings dialog it is a
         Night Atlas segmented control, gold marking the current language.
         !important is the only way to out-rank those inline styles. The
         button keeps a full-size hit area; the visible chip is drawn inset. */
      .cg-nav-lang .i18n-switcher, .cg-nav-settings__panel .i18n-switcher {
        position: relative; z-index: 0; gap: 0 !important; padding: 0 4px !important;
        background: transparent !important;
      }
      .cg-nav-settings__panel .i18n-switcher { display: inline-flex !important; }
      .cg-nav-lang .i18n-switcher::before, .cg-nav-settings__panel .i18n-switcher::before {
        content: ''; position: absolute; inset: 6px 0; z-index: -1; border-radius: 999px;
        border: 1px solid var(--na-gold-hair); background: rgba(7,13,34,.6);
      }
      .cg-nav-lang .i18n-switcher-btn, .cg-nav-settings__panel .i18n-switcher-btn {
        position: relative; z-index: 0; min-width: 44px; min-height: var(--na-target);
        padding: 0 12px !important; background: transparent !important; box-shadow: none !important;
        color: var(--na-text-soft) !important; font-size: 12px !important; font-weight: 800 !important;
      }
      .cg-nav-lang .i18n-switcher-btn::before, .cg-nav-settings__panel .i18n-switcher-btn::before {
        content: ''; position: absolute; inset: 10px 2px; z-index: -1; border-radius: 999px;
      }
      .cg-nav-lang .i18n-switcher-btn:hover, .cg-nav-settings__panel .i18n-switcher-btn:hover { color: var(--na-gold-100) !important; }
      .cg-nav-lang .i18n-switcher-btn.active-lang, .cg-nav-settings__panel .i18n-switcher-btn.active-lang { color: #1b1404 !important; }
      .cg-nav-lang .i18n-switcher-btn.active-lang::before, .cg-nav-settings__panel .i18n-switcher-btn.active-lang::before {
        background: linear-gradient(180deg, #f6dd9a, var(--na-gold-300));
      }
      .cg-nav-lang .i18n-switcher-btn:focus-visible, .cg-nav-settings__panel .i18n-switcher-btn:focus-visible {
        outline: 2px solid var(--na-gold-100); outline-offset: -6px;
      }
      .cg-nav-logout {
        height: 44px; min-height: 44px; padding: 0 12px; border-radius: var(--na-radius-sm); cursor: pointer;
        border: 1px solid var(--na-gold-hair); background: var(--na-inset);
        color: var(--na-gold-100); font-size: 12px; font-weight: 700;
      }
      .cg-nav-logout:hover { color: #fff; background: rgba(220,38,38,.45); border-color: rgba(248,113,113,.55); }
      .cg-verify-banner {
        position: sticky; top: var(--cg-nav-h); z-index: 999;
        display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
        padding: 9px 18px;
        background: linear-gradient(180deg, rgba(227,180,87,.16), rgba(227,180,87,.06)), var(--na-navy-900);
        border-bottom: 1px solid var(--na-gold-edge);
        backdrop-filter: blur(12px);
        box-shadow: var(--na-shadow-1);
        color: var(--na-text); font-size: 13px; font-weight: 650;
      }
      .cg-verify-banner.cg-verify-top { top: 0; }
      .cg-verify-icon { flex: 0 0 auto; }
      .cg-verify-msg { min-width: 0; }
      .cg-verify-resend {
        height: 32px; padding: 0 12px; border-radius: var(--na-radius-xs); cursor: pointer;
        border: 1px solid var(--na-gold-edge);
        background: var(--na-gold-tint);
        color: var(--na-gold-100); font-size: 12px; font-weight: 750; white-space: nowrap;
        transition: background .16s, color .16s;
      }
      .cg-verify-resend:hover:not(:disabled) { background: rgba(227,180,87,.24); }
      .cg-verify-resend:disabled { opacity: .55; cursor: default; }
      .cg-verify-status { font-size: 12px; font-weight: 700; }
      .cg-verify-status.ok { color: var(--na-success); }
      .cg-verify-status.warn { color: var(--na-danger); }
      .cg-verify-close {
        margin-left: auto; width: 32px; height: 32px; border-radius: var(--na-radius-xs); cursor: pointer;
        border: 1px solid var(--na-gold-hair); background: var(--na-inset);
        color: var(--na-text-soft); font-size: 12px; line-height: 1; flex: 0 0 auto;
      }
      .cg-verify-close:hover { color: var(--na-gold-100); background: var(--na-gold-tint); }

      /* Responsive shell: three named layouts.
         - iPad landscape / desktop (>= 1024px wide, landscape): seven labelled
           links in the bar; the language switch stays visible.
         - iPad portrait and phone (portrait up to 1100px, or <= 520px): the
           hamburger opens the dark drawer.
         - Compact landscape (521-1023px, e.g. a phone on its side): there is
           no room for labels, so the seven links stay visible as icons with
           their accessible names. */
      @media (min-width: 768px) {
        .cg-nav-link { height: 48px; min-height: 48px; }
        .cg-nav-hamburger, .cg-nav-drawer__header button, .cg-nav-settings__header button { width: 48px; min-width: 48px; height: 48px; min-height: 48px; }
        .cg-nav-player { min-height: 48px; }
        .cg-brand { min-width: 48px; min-height: 48px; }
        .cg-nav-lang .i18n-switcher-btn { min-width: 48px; }
      }
      @media (max-width: 1279px) {
        .cg-nav { padding: 0 12px; }
        /* brand | seven links (scrolls if it must) | account */
        .cg-nav-inner { grid-template-columns: auto minmax(0,1fr) auto; gap: 8px; }
        .cg-nav-page-label { display: none; }
        .cg-nav-user { display: none; }
        .cg-nav-actions { gap: 6px; }
        .cg-brand-text { display: none; }
        .cg-nav-links { justify-content: flex-start; }
        .cg-nav-link { padding: 0 8px; gap: 5px; }
      }
      @media (max-width: 1023px) {
        .cg-nav { padding: 0 10px; }
        .cg-nav-actions { gap: 4px; }
        .cg-nav-lang { display: none; }
        .cg-nav-link { width: 44px; min-width: 44px; height: 44px; min-height: 44px; padding: 0; justify-content: center; }
        .cg-nav-link span { display: none; }
        .cg-nav-icon { width: 20px; height: 20px; }
      }
      @media (max-width: 1100px) and (orientation: portrait), (max-width: 520px) {
        .cg-nav-hamburger { display: inline-flex; }
        .cg-nav-links { display: none; }
        .cg-nav-inner { grid-template-columns: auto auto minmax(0, 1fr) auto; }
        .cg-nav-page-label { display: inline; min-width: 0; overflow: hidden; text-overflow: ellipsis; font-size: 14px; }
        /* The drawer always shows icon and label, whatever the bar does. */
        .cg-nav-drawer__links .cg-nav-link { width: 100%; height: auto; min-height: 48px; padding: 0 12px; justify-content: flex-start; }
        .cg-nav-drawer__links .cg-nav-link span { display: inline-flex; }
        .cg-nav-drawer__links .cg-nav-icon { width: 20px; height: 20px; }
        .g009-learning-secondary { width: min(calc(100% - 20px), 820px); margin-top: 10px; gap: 4px; padding: 5px; }
        .g009-learning-secondary__item { min-height: 52px; padding: 0 5px; font-size: 13px; }
      }
      @media (max-width: 520px) {
        :root { --cg-nav-h: 52px; }
        .cg-brand-mark { width: 28px; height: 28px; }
        /* Keep the non-interactive presence chip from shrinking the global
           nav scroller enough to clip the Backpack target on narrow phones. */
        .cg-nav-presence { display: none; }
        .cg-nav-link { width: 44px; min-width: 44px; height: 44px; min-height: 44px; border-radius: 11px; }
        .cg-nav-player { width: 44px; min-width: 44px; height: 44px; min-height: 44px; padding: 0; justify-content: center; }
        .cg-nav-player-chevron { display: none; }
        .g009-learning-secondary { width: calc(100% - 16px); border-radius: var(--na-radius-sm); }
        /* Five labels in a phone row: wrap instead of dropping below 12px. */
        .g009-learning-secondary__item { min-height: 56px; padding: 0 3px; font-size: 12px; line-height: 1.2; white-space: normal; overflow-wrap: anywhere; }
      }
      @media (max-width: 700px) {
        body[data-g009-surface="learning-progress"] .stats-grid3 { grid-template-columns: minmax(0, 1fr); }
      }
    `;
  }

  function init() {
    injectStyles();
    document.addEventListener('e9:shell-state-changed', reconcileNavigation);
    document.addEventListener('e10:adventure-shell-owner-changed', reconcileNavigation);
    buildNav();
    const startPresence = () => initPresence();
    if ('requestIdleCallback' in window) {
      window.requestIdleCallback(startPresence, { timeout: 5000 });
    } else {
      window.setTimeout(startPresence, 2500);
    }
    // 該頁沒有共用 nav 時（buildNav 提前 return），橫幅仍要顯示
    if (!document.querySelector('header.cg-nav')) buildVerifyBanner(null);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
