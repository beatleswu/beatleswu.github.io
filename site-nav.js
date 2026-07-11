(() => {
  window.__COLORFUL_GO_NAV_VERSION__ = '20260625-arena-presence-stable';
  const SOCKET_IO_CLIENT_SRC = 'https://cdn.socket.io/4.7.5/socket.io.min.js';

  const NAV_ITEMS = [
    { href: '/curriculum',  key: 'map',       icon: 'map',    label: '冒險公會', i18n: 'nav.rpg.guild' },
    { href: '/mistakes',    key: 'mistake',   icon: 'note',   label: '淨魂卷宗', i18n: 'nav.rpg.mistakes' },
    { href: '/stats',       key: 'stats',     icon: 'chart',  label: '戰績檔案', i18n: 'nav.rpg.stats' },
    { href: '/community',   key: 'community', icon: 'team',   label: '酒館',     i18n: 'nav.rpg.tavern' },
    { href: '/hero',        key: 'hero',      icon: 'hero',   label: '英雄殿',   i18n: 'nav.rpg.hero' },
    { href: '/rating_test', key: 'rating',    icon: 'rating', label: '星盤鑑定', i18n: 'nav.rpg.rating' },
    { href: '/play',        key: 'play',      icon: 'board',  label: '競技場',   i18n: 'nav.rpg.arena' },
    { href: '/shop',        key: 'shop',      icon: 'coin',   label: '商店',     i18n: 'nav.rpg.shop' },
    { href: '/upgrade',     key: 'upgrade',   icon: 'gem',    label: '通行證',   i18n: 'nav.rpg.pass' },
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
    board: '<rect x="5" y="5" width="22" height="22" rx="3"/><path d="M10 5v22M16 5v22M22 5v22M5 10h22M5 16h22M5 22h22"/><circle cx="10" cy="22" r="2.5"/><circle cx="22" cy="10" r="2.5"/>',
    coin: '<circle cx="16" cy="16" r="10"/><path d="M16 9v14M11 13c1.2-2 8.7-2 10 0M11 19c1.2 2 8.7 2 10 0"/>',
    gem: '<path d="M8 7h16l4 6-12 14L4 13l4-6Z"/><path d="M4 13h24M11 7l5 20 5-20"/>',
    rating: '<circle cx="16" cy="16" r="10"/><circle cx="16" cy="16" r="4"/><path d="M16 6v3M16 23v3M6 16h3M23 16h3M9.1 9.1l2.1 2.1M20.8 20.8l2.1 2.1M9.1 22.9l2.1-2.1M20.8 11.2l2.1-2.1"/>',
  };

  function normalize(path) {
    return (path || '/').replace(/\/+$/, '') || '/';
  }

  function isActive(href) {
    const cur = normalize(location.pathname);
    const target = normalize(new URL(href, location.origin).pathname);
    if (target === '/') return cur === '/';
    return cur === target;
  }

  function icon(name) {
    return `<svg class="cg-nav-icon" viewBox="0 0 32 32" aria-hidden="true">${ICONS[name] || ICONS.book}</svg>`;
  }

  function buildNav() {
    // 只接管「導覽列 header」；行銷頁的 <header class="hero"> 不可被吃掉
    const old = document.querySelector('header.cg-nav') || document.querySelector('header:not(.hero)');
    if (!old) return;
    const langSwitcher = old.querySelector('[id^="lang-switcher-"]');
    const header = document.createElement('header');
    header.className = 'cg-nav';
    header.dataset.cgNav = '1';
    header.innerHTML = `
      <div class="cg-nav-inner">
        <a class="cg-brand" href="/" aria-label="弈境奇兵 (Go Odyssey) 公會大廳" data-i18n-aria-label="common.brand.home">
          <span class="cg-brand-mark" aria-hidden="true"><span></span></span>
          <span class="cg-brand-text" data-i18n="common.brand">弈境奇兵 (Go Odyssey)</span>
        </a>
        <nav class="cg-nav-links" aria-label="主要導覽" data-i18n-aria-label="common.nav.aria">
          ${NAV_ITEMS.map(item => `
            <a class="cg-nav-link ${isActive(item.href) ? 'active' : ''}" href="${item.href}" data-nav-key="${item.key}">
              ${icon(item.icon)}
              <span data-i18n="${item.i18n}">${item.label}</span>
              ${item.key === 'mistake' ? '<span id="mistake-badge" class="cg-nav-badge" style="display:none;"></span>' : ''}
            </a>`).join('')}
        </nav>
        <div class="cg-nav-actions">
          <span class="cg-nav-user" id="username-display"></span>
          <span class="cg-nav-presence" id="cg-presence-chip" hidden>
            <span class="cg-nav-presence-dot"></span>
            <span class="cg-nav-presence-text" id="cg-presence-text" data-i18n="nav.presence.offline">離線</span>
            <span class="cg-nav-presence-count" id="cg-presence-count" hidden></span>
          </span>
          <span class="cg-nav-lang"></span>
          <button class="cg-nav-logout" type="button" data-i18n="nav.logout">登出</button>
        </div>
      </div>`;
    old.replaceWith(header);
    // 語言切換鈕：搬移既有的；若該頁沒有，就現場生成一個（涵蓋所有用共用 nav 的頁面）
    const langSlot = header.querySelector('.cg-nav-lang');
    if (langSlot) {
      if (langSwitcher) {
        langSlot.appendChild(langSwitcher);
      } else if (typeof I18n !== 'undefined' && typeof I18n.renderSwitcher === 'function') {
        const box = document.createElement('span');
        box.id = 'lang-switcher-nav';
        langSlot.appendChild(box);
        I18n.renderSwitcher(box);
      }
    }
    // 套用翻譯到新建的 nav（RPG 標籤 + 登出鈕）
    if (typeof I18n !== 'undefined' && typeof I18n.apply === 'function') I18n.apply();
    header.querySelector('.cg-nav-logout')?.addEventListener('click', async () => {
      try { await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' }); } catch {}
      try { if (window.google?.accounts?.id) google.accounts.id.disableAutoSelect(); } catch {}
      location.href = '/login?from=logout';
    });
    window.dispatchEvent(new CustomEvent('cg-nav:ready', { detail: { version: window.__COLORFUL_GO_NAV_VERSION__ } }));
    buildVerifyBanner(header);
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
        max-width: 1360px; height: 100%; margin: 0 auto;
        display: grid; grid-template-columns: auto minmax(0,1fr) auto;
        align-items: center; gap: 14px;
      }
      .cg-brand {
        display: inline-flex; align-items: center; gap: 9px;
        color: #f8e7bd; text-decoration: none; min-width: 0;
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
        justify-self: center; min-width: 0; max-width: 100%;
        display: flex; align-items: center; justify-content: center; gap: 3px;
        overflow-x: auto; overscroll-behavior-inline: contain; scrollbar-width: none;
      }
      .cg-brand-en { display: inline; }
      @media (max-width: 1360px) { .cg-brand-en { display: none; } }
      .cg-nav-links::-webkit-scrollbar { display: none; }
      .cg-nav-link {
        height: 38px; display: inline-flex; align-items: center; gap: 6px;
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
      .cg-nav-user {
        max-width: 92px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        color: rgba(255,246,224,.78); font-size: 12px; font-weight: 700;
      }
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
      .cg-nav-logout {
        height: 34px; padding: 0 12px; border-radius: 11px; cursor: pointer;
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
        .cg-nav-inner { grid-template-columns: auto minmax(0,1fr) auto; gap: 8px; }
        .cg-nav-user { display: none; }
        .cg-nav-logout {
          display: inline-flex; align-items: center; justify-content: center;
          width: 38px; height: 38px; padding: 0; font-size: 0; flex: 0 0 auto;
        }
        .cg-nav-logout::before { content: '🚪'; font-size: 17px; line-height: 1; }
        .cg-nav-actions { gap: 4px; }
        .cg-nav-lang { display: none; }
        .cg-brand-text { display: none; }
        .cg-nav-links { justify-content: flex-start; }
        .cg-nav-link { width: 38px; padding: 0; justify-content: center; }
        .cg-nav-link span { display: none; }
        .cg-nav-link .cg-nav-badge { display: none !important; }
        .cg-nav-icon { width: 20px; height: 20px; }
      }
      @media (max-width: 520px) {
        :root { --cg-nav-h: 52px; }
        .cg-brand-mark { width: 28px; height: 28px; }
        .cg-nav-link { width: 36px; height: 36px; border-radius: 11px; }
        .cg-nav-logout { width: 36px; height: 36px; border-radius: 11px; }
      }
    `;
  }

  function init() {
    injectStyles();
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
