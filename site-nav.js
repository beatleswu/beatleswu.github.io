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

  function injectStyles() {
    let style = document.getElementById('cg-nav-style');
    if (!style) {
      style = document.createElement('style');
      style.id = 'cg-nav-style';
      document.head.appendChild(style);
    }
    style.textContent = `
      :root { --cg-nav-h: 58px; }
      .cg-nav {
        position: sticky; top: 0; z-index: 1000;
        height: var(--cg-nav-h); padding: 0 18px;
        background: rgba(5,10,12,.94);
        border-bottom: 1px solid rgba(251,191,36,.16);
        backdrop-filter: blur(16px);
        box-shadow: 0 12px 34px rgba(0,0,0,.34);
      }
      .cg-nav-inner {
        max-width: 1480px; height: 100%; margin: 0 auto;
        display: grid; grid-template-columns: auto auto auto minmax(0,1fr) auto;
        align-items: center; gap: 14px;
      }
      .cg-nav-hamburger {
        width: 44px; height: 44px; min-width: 44px; min-height: 44px; display: inline-flex; flex-direction: column;
        align-items: center; justify-content: center; gap: 4px; padding: 0;
        border: 1px solid rgba(251,191,36,.22); border-radius: 10px;
        color: #f8e7bd; background: rgba(255,255,255,.06); cursor: pointer;
      }
      .cg-nav-hamburger span { width: 17px; height: 2px; border-radius: 99px; background: currentColor; }
      .cg-nav-hamburger:focus-visible { outline: 2px solid #ffe18a; outline-offset: 2px; }
      .cg-brand {
        display: inline-flex; align-items: center; gap: 9px;
        color: #f8e7bd; text-decoration: none; min-width: 44px; min-height: 44px;
        box-sizing: border-box;
        font-family: 'Cormorant Garamond', Georgia, serif;
        font-size: 18px; font-weight: 700; white-space: nowrap;
      }
      .cg-brand-mark {
        width: 30px; height: 30px; border-radius: 9px; flex: 0 0 auto;
        background: linear-gradient(135deg,#f7e8bd,#c99f4f);
        border: 1px solid #9f7934; position: relative;
        box-shadow: inset 0 0 0 2px rgba(255,255,255,.34), 0 5px 14px rgba(28,20,9,.13);
      }
      .cg-brand-mark::before {
        content: ''; position: absolute; inset: 6px;
        background:
          linear-gradient(#3a2e1d 1px, transparent 1px),
          linear-gradient(90deg,#3a2e1d 1px, transparent 1px);
        background-size: 6px 6px; opacity: .62;
      }
      .cg-brand-mark span::before,
      .cg-brand-mark span::after {
        content: ''; position: absolute; width: 6px; height: 6px; border-radius: 50%;
        top: 17px; left: 10px; background: #111827;
      }
      .cg-brand-mark span::after { top: 8px; left: 19px; background: #f8fafc; border: 1px solid #111827; }
      .cg-nav-links {
        justify-self: stretch; min-width: 0; max-width: 100%;
        display: flex; align-items: center; justify-content: center; gap: 3px;
        overflow-x: auto; overscroll-behavior-inline: contain; scrollbar-width: none;
      }
      .cg-nav-page-label {
        min-width: 72px; color: #fbbf24; font-size: 12px; font-weight: 800;
        white-space: nowrap;
      }
      .cg-brand-en { display: inline; }
      @media (max-width: 1360px) { .cg-brand-en { display: none; } }
      .cg-nav-links::-webkit-scrollbar { display: none; }
      .cg-nav-link {
        height: 44px; min-height: 44px; min-width: 44px; box-sizing: border-box; flex: 0 0 auto;
        display: inline-flex; align-items: center; gap: 6px;
        padding: 0 8px; border-radius: 12px;
        color: rgba(255,246,224,.78); text-decoration: none; font-size: 13px; font-weight: 650;
        white-space: nowrap; border: 1px solid transparent;
        transition: background .16s, border-color .16s, color .16s, transform .16s, box-shadow .16s;
      }
      .cg-nav-badge {
        min-width: 17px; height: 17px; padding: 0 5px; border-radius: 99px;
        display: inline-flex; align-items: center; justify-content: center;
        font-size: 10px; font-weight: 800; line-height: 1;
        background: #dc2626; color: #fff;
      }
      .cg-nav-link:hover {
        color: #fff3d1; background: rgba(251,191,36,.08); border-color: rgba(251,191,36,.18);
        transform: translateY(-1px);
      }
      .cg-nav-link.active {
        color: #fbbf24; background: linear-gradient(180deg, rgba(251,191,36,.2), rgba(120,53,15,.18));
        border-color: rgba(251,191,36,.35); box-shadow: 0 6px 16px rgba(0,0,0,.28);
      }
      .cg-nav-icon {
        width: 18px; height: 18px; flex: 0 0 auto;
        fill: none; stroke: currentColor; stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round;
      }
      .cg-nav-actions { display: inline-flex; align-items: center; gap: 8px; justify-content: flex-end; min-width: 0; }
      .cg-nav-player {
        display: inline-flex; align-items: center; gap: 6px; min-width: 0; min-height: 44px; flex: 0 0 auto;
        border: 1px solid rgba(251,191,36,.22); border-radius: 12px;
        padding: 4px 8px 4px 5px; color: #f8e7bd; background: rgba(255,255,255,.06);
        cursor: pointer;
      }
      .cg-nav-player:focus-visible { outline: 2px solid #ffe18a; outline-offset: 2px; }
      .cg-nav-player-avatar { width: 27px; height: 27px; display: inline-flex; align-items: center; justify-content: center; border-radius: 9px; background: linear-gradient(135deg,#f7e8bd,#c99f4f); color: #2f2412; font-size: 10px; font-weight: 900; }
      .cg-nav-user {
        max-width: 110px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        color: rgba(255,246,224,.78); font-size: 12px; font-weight: 700;
      }
      .cg-nav-player-chevron { color: rgba(255,246,224,.65); font-size: 15px; line-height: 1; }
      .cg-nav-menu {
        position: absolute; top: calc(var(--cg-nav-h) - 2px); right: 18px; z-index: 1100;
        min-width: 172px; padding: 6px; border: 1px solid rgba(251,191,36,.28);
        border-radius: 12px; background: rgba(18,24,24,.98); box-shadow: 0 18px 36px rgba(0,0,0,.38);
      }
      .cg-nav-menu[hidden], .cg-nav-drawer[hidden], .cg-nav-settings[hidden] { display: none !important; }
      .cg-nav-menu a, .cg-nav-menu button {
        width: 100%; min-height: 44px; display: flex; align-items: center;
        padding: 0 12px; border: 0; border-radius: 8px; color: #f8e7bd;
        background: transparent; text-decoration: none; text-align: left; cursor: pointer; font: inherit;
      }
      .cg-nav-menu a:hover, .cg-nav-menu button:hover { background: rgba(251,191,36,.12); }
      .cg-nav-drawer, .cg-nav-settings { position: fixed; inset: 0; z-index: 1300; }
      .cg-nav-drawer__backdrop, .cg-nav-settings__backdrop { position: absolute; inset: 0; background: rgba(5,10,12,.64); }
      .cg-nav-drawer__panel, .cg-nav-settings__panel {
        position: absolute; top: 0; left: 0; bottom: 0; width: min(360px, 88vw);
        padding: 18px; overflow-y: auto; background: #fff8e7; color: #2f2412;
        box-shadow: 18px 0 42px rgba(0,0,0,.32);
      }
      .cg-nav-drawer__header, .cg-nav-settings__header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
      .cg-nav-drawer__header h2, .cg-nav-settings__header h2 { margin: 0; font-size: 20px; }
      .cg-nav-drawer__header button, .cg-nav-settings__header button { width: 44px; min-width: 44px; height: 44px; min-height: 44px; border: 1px solid rgba(47,36,18,.2); border-radius: 9px; background: #fff; color: #2f2412; font-size: 22px; cursor: pointer; }
      .cg-nav-drawer__links { display: grid; gap: 8px; }
      .cg-nav-drawer__links .cg-nav-link { justify-content: flex-start; min-height: 48px; color: #2f2412; border-color: rgba(47,36,18,.12); background: rgba(255,255,255,.76); }
      .cg-nav-drawer__links .cg-nav-link span { display: inline-flex; }
      .cg-nav-settings__panel { left: 50%; top: 50%; bottom: auto; transform: translate(-50%, -50%); width: min(420px, calc(100vw - 32px)); border-radius: 16px; }
      .cg-nav-settings__panel > label { display: block; margin: 14px 0 6px; font-weight: 750; }
      .cg-nav-settings__sound { display: flex !important; align-items: center; justify-content: space-between; }
      .cg-nav-settings__panel [data-g009-settings-sound-state] { display: block; margin-top: 5px; color: #6b5740; font-size: 12px; }
      .cg-nav-presence {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 0 10px; height: 28px; border-radius: 999px;
        background: rgba(255,255,255,.06); border: 1px solid rgba(251,191,36,.18);
        color: #f8e7bd; font-size: 11px; font-weight: 750; white-space: nowrap;
      }
      .cg-nav-presence-dot {
        width: 8px; height: 8px; border-radius: 50%;
        background: #86efac; box-shadow: 0 0 0 3px rgba(34,197,94,.14);
      }
      .cg-nav-presence.study .cg-nav-presence-dot {
        background: #fbbf24; box-shadow: 0 0 0 3px rgba(251,191,36,.16);
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
        background: #dc2626; color: #fff; font-size: 10px; font-weight: 800;
      }
      .cg-nav-lang { display: inline-flex; align-items: center; }
      .cg-nav-lang .i18n-switcher-btn { min-width: 44px; min-height: 44px; }
      .cg-nav-logout {
        height: 44px; min-height: 44px; padding: 0 12px; border-radius: 11px; cursor: pointer;
        border: 1px solid rgba(251,191,36,.22); background: rgba(255,255,255,.06);
        color: #f8e7bd; font-size: 12px; font-weight: 700;
      }
      .cg-nav-logout:hover { color: #fff; background: rgba(220,38,38,.45); border-color: rgba(248,113,113,.55); }
      .cg-verify-banner {
        position: sticky; top: var(--cg-nav-h); z-index: 999;
        display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
        padding: 9px 18px;
        background: linear-gradient(180deg, rgba(120,53,15,.55), rgba(60,28,8,.6)), rgba(8,12,14,.95);
        border-bottom: 1px solid rgba(251,191,36,.32);
        backdrop-filter: blur(12px);
        box-shadow: 0 8px 22px rgba(0,0,0,.3);
        color: #f8e7bd; font-size: 13px; font-weight: 650;
      }
      .cg-verify-banner.cg-verify-top { top: 0; }
      .cg-verify-icon { flex: 0 0 auto; }
      .cg-verify-msg { min-width: 0; }
      .cg-verify-resend {
        height: 28px; padding: 0 12px; border-radius: 9px; cursor: pointer;
        border: 1px solid rgba(251,191,36,.45);
        background: linear-gradient(180deg, rgba(251,191,36,.24), rgba(120,53,15,.22));
        color: #fbbf24; font-size: 12px; font-weight: 750; white-space: nowrap;
        transition: background .16s, color .16s, transform .16s;
      }
      .cg-verify-resend:hover:not(:disabled) { color: #fff3d1; background: rgba(251,191,36,.32); transform: translateY(-1px); }
      .cg-verify-resend:disabled { opacity: .55; cursor: default; }
      .cg-verify-status { font-size: 12px; font-weight: 700; }
      .cg-verify-status.ok { color: #86efac; }
      .cg-verify-status.warn { color: #fca5a5; }
      .cg-verify-close {
        margin-left: auto; width: 26px; height: 26px; border-radius: 8px; cursor: pointer;
        border: 1px solid rgba(251,191,36,.2); background: rgba(255,255,255,.05);
        color: rgba(255,246,224,.7); font-size: 12px; line-height: 1; flex: 0 0 auto;
      }
      .cg-verify-close:hover { color: #fff; background: rgba(255,255,255,.12); }
      @media (max-width: 1200px) {
        .cg-nav { padding: 0 10px; }
        .cg-nav-inner { grid-template-columns: auto auto minmax(0,1fr) auto; gap: 8px; }
        .cg-nav-page-label { display: none; }
        .cg-nav-user { display: none; }
        .cg-nav-actions { gap: 4px; }
        .cg-nav-lang { display: none; }
        .cg-brand-text { display: none; }
        .cg-nav-links { justify-content: flex-start; }
        .cg-nav-link { width: 44px; min-width: 44px; height: 44px; min-height: 44px; padding: 0; justify-content: center; }
        .cg-nav-link span { display: none; }
        .cg-nav-icon { width: 20px; height: 20px; }
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
