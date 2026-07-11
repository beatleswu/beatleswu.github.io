/**
 * pwa.js — 弈境奇兵 (Go Odyssey) PWA 共用邏輯
 * 1. 注入 manifest / Apple meta tags（免得每頁重複寫）
 * 2. 註冊 Service Worker
 * 3. 顯示「安裝 APP」浮動提示
 */

// ── 1. 注入 PWA 必要 meta tags ─────────────────────────────────
(function injectPWAHead() {
  const head = document.head;
  function hasMeta(name) {
    return !!document.querySelector(`meta[name="${name}"]`);
  }
  function addMeta(name, content) {
    if (hasMeta(name)) return;
    const m = document.createElement('meta');
    m.name = name; m.content = content;
    head.appendChild(m);
  }
  function addLink(rel, href) {
    const existing = document.querySelector(`link[rel="${rel}"]`);
    if (existing) return;
    const l = document.createElement('link');
    l.rel = rel; l.href = href;
    head.appendChild(l);
  }

  addLink('manifest',        '/manifest.json');
  addMeta('theme-color',     '#0d9488');
  // Chromium 已棄用 apple-mobile-web-app-capable，新標準是 mobile-web-app-capable
  // 兩個都加，新瀏覽器讀新的，iOS Safari 仍讀 apple-* 那個
  addMeta('mobile-web-app-capable',                'yes');
  addMeta('apple-mobile-web-app-capable',          'yes');
  addMeta('apple-mobile-web-app-status-bar-style', 'default');
  addMeta('apple-mobile-web-app-title',            '弈境奇兵 (Go Odyssey)');
  addLink('apple-touch-icon', '/icon-192.png');
})();


// ── 2. 註冊 Service Worker ─────────────────────────────────────
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' })
      .catch(e => console.warn('[PWA] SW registration failed:', e));
  });
}


// ── 3. 安裝提示 Banner ─────────────────────────────────────────
let _deferredPrompt = null;

const BANNER_CSS = `
#pwa-banner {
  position: fixed; bottom: 20px; left: 50%;
  transform: translateX(-50%) translateY(0);
  z-index: 9999;
  display: flex; align-items: center; gap: 12px;
  background: #1c1409; color: #fff;
  border-radius: 16px; padding: 13px 16px 13px 18px;
  box-shadow: 0 8px 36px rgba(0,0,0,.30);
  font-family: 'DM Sans', system-ui, sans-serif; font-size: 13px;
  max-width: min(360px, calc(100vw - 32px));
  width: max-content;
  animation: pwa-up .32s cubic-bezier(.34,1.56,.64,1) both;
}
@keyframes pwa-up {
  from { opacity:0; transform: translateX(-50%) translateY(20px); }
  to   { opacity:1; transform: translateX(-50%) translateY(0); }
}
#pwa-banner .pb-icon { font-size: 24px; flex-shrink:0; line-height:1; }
#pwa-banner .pb-text { flex:1; min-width:0; }
#pwa-banner .pb-title { font-weight:700; font-size:13px; }
#pwa-banner .pb-sub   { font-size:11px; opacity:.55; margin-top:1px; }
#pwa-banner .pb-install {
  flex-shrink:0;
  background:#0d9488; color:#fff; border:none; border-radius:9px;
  padding:8px 14px; font-size:12px; font-weight:700; cursor:pointer;
  transition: background .15s;
}
#pwa-banner .pb-install:hover { background:#0f766e; }
#pwa-banner .pb-close {
  flex-shrink:0;
  background:none; border:none; color:rgba(255,255,255,.35);
  font-size:17px; cursor:pointer; padding:2px 0 2px 4px; line-height:1;
  transition: color .15s;
}
#pwa-banner .pb-close:hover { color:rgba(255,255,255,.8); }
`;

function showBanner() {
  if (document.getElementById('pwa-banner')) return;
  if (sessionStorage.getItem('pwa-banner-dismissed')) return;

  const style = document.createElement('style');
  style.textContent = BANNER_CSS;
  document.head.appendChild(style);

  const el = document.createElement('div');
  el.id = 'pwa-banner';
  el.innerHTML = `
    <div class="pb-icon">⚫</div>
    <div class="pb-text">
      <div class="pb-title">安裝 弈境奇兵 (Go Odyssey)</div>
      <div class="pb-sub">加到主畫面，隨時練棋</div>
    </div>
    <button class="pb-install" id="pwa-install-btn">安裝</button>
    <button class="pb-close"   id="pwa-close-btn" title="關閉">✕</button>
  `;
  document.body.appendChild(el);

  document.getElementById('pwa-install-btn').onclick = async () => {
    if (!_deferredPrompt) return;
    _deferredPrompt.prompt();
    const { outcome } = await _deferredPrompt.userChoice;
    _deferredPrompt = null;
    hideBanner();
  };

  document.getElementById('pwa-close-btn').onclick = () => {
    hideBanner();
    sessionStorage.setItem('pwa-banner-dismissed', '1');
  };
}

function hideBanner() {
  const el = document.getElementById('pwa-banner');
  if (el) el.remove();
}

window.addEventListener('beforeinstallprompt', e => {
  e.preventDefault();
  _deferredPrompt = e;
  // 稍微延遲，避免頁面剛載入就彈出
  setTimeout(showBanner, 3000);
});

window.addEventListener('appinstalled', () => {
  hideBanner();
  _deferredPrompt = null;
});


// ── 4. iOS 安裝引導 ────────────────────────────────────────────
(function iosGuide() {
  const ua = navigator.userAgent;
  const maxTouchPoints = navigator.maxTouchPoints || 0;

  // 只在 iOS 裝置上執行
  const isIPadOSDesktopUA = /Macintosh/.test(ua) && maxTouchPoints > 1;
  const isIOS = /iPhone|iPad|iPod/.test(ua) || isIPadOSDesktopUA;
  if (!isIOS) return;

  // 已經是 standalone 模式（已安裝），不顯示
  if (window.navigator.standalone) return;

  // 已關閉過，7 天內不再顯示
  const dismissed = localStorage.getItem('ios-guide-dismissed-v2');
  if (dismissed && Date.now() - parseInt(dismissed) < 7 * 86400_000) return;

  // 偵測是否為 Safari（非 CriOS/FxiOS/其他）
  const isSafari = /Safari/.test(ua) &&
    !/CriOS|FxiOS|OPiOS|EdgiOS|DuckDuckGo/.test(ua);

  window.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => showIOSGuide(isSafari), 2500);
  });
})();

const IOS_CSS = `
#ios-guide-overlay {
  position: fixed; inset: 0; z-index: 10000;
  background: rgba(0,0,0,.45);
  backdrop-filter: blur(3px);
  display: flex; align-items: flex-end; justify-content: center;
  padding-bottom: env(safe-area-inset-bottom, 0px);
  animation: ios-fade-in .25s ease both;
}
@keyframes ios-fade-in {
  from { opacity:0; } to { opacity:1; }
}
#ios-guide-sheet {
  background: #fff;
  border-radius: 20px 20px 0 0;
  padding: 24px 24px 32px;
  width: 100%; max-width: 480px;
  font-family: 'DM Sans', system-ui, sans-serif;
  animation: ios-slide-up .3s cubic-bezier(.32,1,.28,1) both;
}
@keyframes ios-slide-up {
  from { transform: translateY(100%); }
  to   { transform: translateY(0); }
}
#ios-guide-sheet .ig-handle {
  width: 36px; height: 4px; background: #e5ddd0;
  border-radius: 99px; margin: 0 auto 20px;
}
#ios-guide-sheet .ig-title {
  font-size: 17px; font-weight: 700; color: #1c1409;
  text-align: center; margin-bottom: 6px;
}
#ios-guide-sheet .ig-sub {
  font-size: 13px; color: #6b5740;
  text-align: center; margin-bottom: 24px; line-height: 1.5;
}
#ios-guide-sheet .ig-steps {
  display: flex; flex-direction: column; gap: 14px; margin-bottom: 24px;
}
#ios-guide-sheet .ig-step {
  display: flex; align-items: center; gap: 14px;
}
#ios-guide-sheet .ig-step-num {
  width: 28px; height: 28px; border-radius: 50%;
  background: #0d9488; color: #fff;
  font-size: 13px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
#ios-guide-sheet .ig-step-text {
  font-size: 14px; color: #1c1409; line-height: 1.4;
}
#ios-guide-sheet .ig-step-text strong { font-weight: 600; }
#ios-guide-sheet .ig-share-icon {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 5px;
  background: #007aff; color: #fff; font-size: 13px;
  vertical-align: middle; margin: 0 2px;
}
#ios-guide-sheet .ig-warn {
  background: #fffbeb; border: 1px solid #fde68a;
  border-radius: 10px; padding: 11px 14px;
  font-size: 12px; color: #92400e; line-height: 1.5;
  margin-bottom: 20px;
}
#ios-guide-sheet .ig-close {
  width: 100%; padding: 13px;
  background: #f3ede3; border: none; border-radius: 12px;
  font-size: 14px; font-weight: 600; color: #6b5740;
  cursor: pointer;
}
`;

function showIOSGuide(isSafari) {
  if (document.getElementById('ios-guide-overlay')) return;

  const style = document.createElement('style');
  style.textContent = IOS_CSS;
  document.head.appendChild(style);

  const overlay = document.createElement('div');
  overlay.id = 'ios-guide-overlay';

  if (isSafari) {
    // Safari：直接教操作步驟
    overlay.innerHTML = `
      <div id="ios-guide-sheet">
        <div class="ig-handle"></div>
        <div class="ig-title">⚫ 安裝 弈境奇兵 (Go Odyssey)</div>
        <div class="ig-sub">加到主畫面，像 APP 一樣使用</div>
        <div class="ig-steps">
          <div class="ig-step">
            <div class="ig-step-num">1</div>
            <div class="ig-step-text">
              點下方工具列的
              <span class="ig-share-icon">⬆</span>
              <strong>分享</strong>按鈕
            </div>
          </div>
          <div class="ig-step">
            <div class="ig-step-num">2</div>
            <div class="ig-step-text">
              往下滑，點選
              <strong>「加入主畫面」</strong>
            </div>
          </div>
          <div class="ig-step">
            <div class="ig-step-num">3</div>
            <div class="ig-step-text">
              點右上角<strong>「新增」</strong>即完成安裝
            </div>
          </div>
        </div>
        <button class="ig-close" id="ios-guide-close">我知道了</button>
      </div>
    `;
  } else {
    // Chrome / 其他瀏覽器：引導改用 Safari
    overlay.innerHTML = `
      <div id="ios-guide-sheet">
        <div class="ig-handle"></div>
        <div class="ig-title">⚫ 安裝 弈境奇兵 (Go Odyssey)</div>
        <div class="ig-sub">iOS 只支援透過 Safari 安裝到主畫面</div>
        <div class="ig-warn">
          ⚠️ 你目前使用的不是 Safari。<br>
          請複製網址，改用 <strong>Safari</strong> 開啟，再依步驟安裝。
        </div>
        <div class="ig-steps">
          <div class="ig-step">
            <div class="ig-step-num">1</div>
            <div class="ig-step-text">用 Safari 開啟 <strong>${location.hostname}</strong></div>
          </div>
          <div class="ig-step">
            <div class="ig-step-num">2</div>
            <div class="ig-step-text">
              點工具列的
              <span class="ig-share-icon">⬆</span>
              <strong>分享</strong>→<strong>「加入主畫面」</strong>
            </div>
          </div>
        </div>
        <button class="ig-close" id="ios-guide-close">知道了</button>
      </div>
    `;
  }

  document.body.appendChild(overlay);

  function dismiss() {
    overlay.remove();
    localStorage.setItem('ios-guide-dismissed-v2', Date.now().toString());
  }

  document.getElementById('ios-guide-close').onclick = dismiss;
  overlay.addEventListener('click', e => { if (e.target === overlay) dismiss(); });
}
