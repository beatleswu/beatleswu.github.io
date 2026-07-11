/* 棋子皮膚：全域覆寫 WGo 棋子繪製，所有 WGo 棋盤通用。
   棋子仍以 {x,y,c} 加入（提子/移除不受影響），只改「畫」的方式。 */
(function () {
  if (!window.WGo || !WGo.Board || !WGo.Board.drawHandlers) return;

  window.__STONE_SKIN = { set: '', imgs: null };

  // 覆寫各種 stone 繪製 handler（保留原本作 fallback）
  var H = WGo.Board.drawHandlers;
  ['NORMAL', 'PAINTED', 'GLOW', 'SHELL', 'MONO'].forEach(function (name) {
    var h = H[name];
    if (!h || !h.stone || typeof h.stone.draw !== 'function') return;
    var orig = h.stone.draw;
    h.stone.draw = function (a, b) {
      var sk = window.__STONE_SKIN;
      if (sk && sk.imgs) {
        var img = (a.c === WGo.W) ? sk.imgs.white : sk.imgs.black;
        if (img && img.complete && img.naturalWidth) {
          var x = b.getX(a.x), y = b.getY(a.y), d = b.stoneRadius;
          this.drawImage(img, x - d, y - d, 2 * d, 2 * d);
          return;
        }
      }
      return orig.call(this, a, b);
    };
  });

  // 頁面在建立棋盤後設定這個 hook，皮膚載入完會呼叫它重畫盤面
  window.__stoneSkinRedraw = null;

  window.applyStoneSkin = function (set) {
    set = set || '';
    window.__STONE_SKIN.set = set;
    if (!set) {
      window.__STONE_SKIN.imgs = null;
      if (typeof window.__stoneSkinRedraw === 'function') window.__stoneSkinRedraw();
      return;
    }
    var bl = new Image(), wh = new Image(), n = 0;
    function done() {
      if (++n === 2) {
        window.__STONE_SKIN.imgs = { black: bl, white: wh };
        if (typeof window.__stoneSkinRedraw === 'function') window.__stoneSkinRedraw();
      }
    }
    bl.onload = done; wh.onload = done;
    bl.onerror = wh.onerror = function () { window.__STONE_SKIN.imgs = null; };
    bl.src = '/assets/stones/stone_' + set + '_black.webp';
    wh.src = '/assets/stones/stone_' + set + '_white.webp';
  };

  // ── 棋盤皮膚 ──────────────────────────────────────────────
  var BOARD_LINE = { classic:'#3a2a14', jade:'#2f5d4a', marble:'#555555', cosmic:'rgba(220,225,255,0.62)', radiant:'#b8923a' };
  var BOARD_STAR = { classic:'#2a1c0c', jade:'#2f5d4a', marble:'#333333', cosmic:'#cdd6ff', radiant:'#9a7820' };
  window.__BOARD_SKIN = { set: '' };
  window.__skinBoardRef = null;   // 頁面建立棋盤後設成它的 board 實例

  window.applyBoardSkin = function () {
    var b = window.__skinBoardRef;
    if (!b || !b.element) return;
    // 第一次記住原始值，供「預設」還原
    if (b.__origBgImage === undefined) b.__origBgImage = b.element.style.backgroundImage || '';
    if (b.theme && b.__origLine === undefined) { b.__origLine = b.theme.gridLinesColor; b.__origStar = b.theme.starColor; }
    var set = window.__BOARD_SKIN.set;
    if (!set) {
      b.element.style.backgroundImage = b.__origBgImage || '';
      if (b.theme) { b.theme.gridLinesColor = b.__origLine; b.theme.starColor = b.__origStar; }
    } else {
      b.element.style.backgroundImage = "url('/assets/boards/board_" + set + ".webp')";
      b.element.style.backgroundSize = 'cover';
      b.element.style.backgroundPosition = 'center';
      if (b.theme) {
        if (BOARD_LINE[set]) b.theme.gridLinesColor = BOARD_LINE[set];
        if (BOARD_STAR[set]) b.theme.starColor = BOARD_STAR[set];
      }
    }
    try { b.redraw(); } catch (e) {}
  };
  window.setBoardSkin = function (set) { window.__BOARD_SKIN.set = set || ''; window.applyBoardSkin(); };

  // 自動登記：每個 new WGo.Board(...) 都自動套用棋盤皮膚（涵蓋所有棋盤頁，免逐頁改）
  try {
    var _OrigBoard = WGo.Board;
    if (_OrigBoard && !_OrigBoard.__skinWrapped) {
      var Patched = function () {
        var inst = new (Function.prototype.bind.apply(_OrigBoard, [null].concat([].slice.call(arguments))))();
        try { window.__skinBoardRef = inst; if (window.applyBoardSkin) window.applyBoardSkin(); } catch (e) {}
        return inst;
      };
      Patched.prototype = _OrigBoard.prototype;
      for (var k in _OrigBoard) { if (_OrigBoard.hasOwnProperty(k)) Patched[k] = _OrigBoard[k]; }
      Patched.__skinWrapped = true;
      WGo.Board = Patched;
    }
  } catch (e) {}

  // 自動從外觀讀取已裝備皮膚（棋子 + 棋盤）
  try {
    fetch('/api/player/appearance', { credentials: 'include' })
      .then(function (r) { return r.json(); })
      .then(function (a) {
        if (!a) return;
        if (a.stone_skin) window.applyStoneSkin(a.stone_skin);
        if (a.board_skin) { window.__BOARD_SKIN.set = a.board_skin; window.applyBoardSkin(); }
      })
      .catch(function () {});
  } catch (e) {}
})();
