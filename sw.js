/**
 * sw.js — 弈境奇兵 (Go Odyssey) Service Worker
 * 策略：
 *   - 靜態殼層（HTML / JS / CSS / 字型）→ Cache First
 *   - API 請求 → Network Only（避免跨帳號快取個人資料）
 *   - 圖片 → Cache First（長效）
 */

const VERSION     = 'v198-e9-adventure-entry-contract-trace';
const SHELL_CACHE = `cg-shell-${VERSION}`;
const IMG_CACHE   = `cg-img-${VERSION}`;

// 只預快取公開、不需登入的靜態資源
// 登入後頁面（/hero、/curriculum 等）不預快取——安裝時 fetch 會跟 redirect 到 /login 快取到錯誤內容
const SHELL_URLS = [
  '/',
  '/landing',
  '/srs.js',
  '/i18n.js',
  '/manifest.json',
];

// ── Install ────────────────────────────────────────────────────
self.addEventListener('install', event => {
  // skipWaiting 必須在 cache.addAll 完成後才呼叫
  // 否則新 SW 會在快取尚未就緒時接管進行中的導覽請求，造成 ERR_FAILED
  event.waitUntil(
    caches.open(SHELL_CACHE)
      .then(cache => cache.addAll(SHELL_URLS))
      .then(() => self.skipWaiting())
  );
});

// ── Activate：清掉舊版快取 ─────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k !== SHELL_CACHE && k !== IMG_CACHE)
          .map(k => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// ── Fetch ──────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // 只處理同源請求
  if (url.origin !== self.location.origin) {
    // 外部字型等：Cache First
    if (request.destination === 'font' || request.destination === 'style') {
      event.respondWith(cacheFirst(request, IMG_CACHE));
    }
    return;
  }

  // API 回應可能包含登入者資料；Cache Storage 不會依 Cookie 隔離。
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(request));
    return;
  }

  // 靜態 JS / CSS
  if (url.pathname === '/site-nav.js' || url.pathname === '/mobile-nav.js') {
    event.respondWith(networkFirst(request, SHELL_CACHE));
    return;
  }

  if (url.pathname.startsWith('/wgo/') ||
      url.pathname.endsWith('.js') ||
      url.pathname.endsWith('.css')) {
    event.respondWith(cacheFirst(request, SHELL_CACHE));
    return;
  }

  // HTML 頁面：Network First（確保登入狀態最新）
  event.respondWith(networkFirst(request, SHELL_CACHE));
});

// ── 策略函數 ──────────────────────────────────────────────────

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response('離線中，此資源暫時無法取得', { status: 503 });
  }
}

async function networkFirst(request, cacheName) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    // HTML 頁面離線時回傳主頁快取
    if (request.destination === 'document') {
      const root = await caches.match('/');
      return root || new Response('離線中', { status: 503 });
    }
    return new Response(JSON.stringify({ error: '離線中', offline: true }),
      { status: 503, headers: { 'Content-Type': 'application/json' } });
  }
}

// ── 推播通知 ──────────────────────────────────────────────────
self.addEventListener('push', event => {
  const data = event.data ? event.data.json() : {};
  const title = data.title || '弈境奇兵 (Go Odyssey)';
  const options = {
    body:    data.body  || '今天還沒練習圍棋，點此開始！',
    icon:    '/icon-192.png',
    badge:   '/icon-192.png',
    tag:     'daily-reminder',
    renotify: false,
    data:    { url: data.url || '/' },
    actions: [
      { action: 'open',    title: '開始練習' },
      { action: 'dismiss', title: '稍後再說' },
    ]
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  if (event.action === 'dismiss') return;
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
      for (const client of list) {
        if (client.url === url && 'focus' in client) return client.focus();
      }
      return clients.openWindow(url);
    })
  );
});
