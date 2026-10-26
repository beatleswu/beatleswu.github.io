/* Product Grimoire consumer: no solution tree, verdict, rights or gate in browser.
   Pending moves stay in memory. After reload the server's stable lesson scope
   and committed events recover progress; no token is persisted across accounts. */
(() => {
  'use strict';
  const el = id => document.getElementById(id);
  const api = '/api/g076/grimoire/product/';
  let token, step, game, board, color, pending = null, busy = false;
  const labels = {OPEN:'輪到你落子', CONTINUE:'輪到你落子', CORRECT:'修煉完成', INCORRECT:'這次未解開棋形'};
  const errors = {
    authentication_required:'請先登入，再返回法典。', rights_required:'目前無法使用這個課題，請確認會員資格。',
    grimoire_steps_disabled:'法典修煉暫未開放。', attempt_stale:'課題已過期，請返回大廳。',
    attempt_revision_changed:'課題已更新，請返回大廳重新選課。',
    canonical_provenance_unavailable:'課題來源尚未就緒，請稍後再試。'
  };
  async function post(path, body) {
    const abort = new AbortController(), timer = setTimeout(() => abort.abort(), 20000);
    try {
      const r = await fetch(api + path, {method:'POST', credentials:'same-origin', cache:'no-store',
        headers:{'Content-Type':'application/json','X-Grimoire-Request':'1'},
        body:JSON.stringify(body), signal:abort.signal});
      const data = await r.json();
      if (!r.ok) throw new Error(errors[data.error] || '暫時無法確認進度，請重新連線。');
      return data;
    } finally { clearTimeout(timer); }
  }
  function state() {
    el('status').textContent = labels[step?.status] || '正在連線…';
    el('retry').disabled = busy || !pending;
    el('resume').disabled = busy;
  }
  // WGo 2.x parses AB[aa:bb] as ONE stone, not the SGF rectangle.
  // Expand ONLY setup properties in the server's solution-free root preview;
  // never inspect or expand moves, branches, labels or answer variations.
  function expandSetupRectangles(sgf) {
    return sgf.replace(/(AB|AW|AE)((?:\[[a-z]{2}(?::[a-z]{2})?\])+)/g,
      (matched, property, entries) => {
        let expanded = '', count = 0;
        const cells = /\[([a-z]{2})(?::([a-z]{2}))?\]/g;
        for (const entry of entries.matchAll(cells)) {
          const low = entry[1], high = entry[2] || low;
          if (high.charCodeAt(0) < low.charCodeAt(0) ||
              high.charCodeAt(1) < low.charCodeAt(1)) throw new Error('無法讀取棋形。');
          for (let x = low.charCodeAt(0); x <= high.charCodeAt(0); x++) {
            for (let y = low.charCodeAt(1); y <= high.charCodeAt(1); y++) {
              if (++count > 625) throw new Error('無法讀取棋形。');
              expanded += '['+String.fromCharCode(x)+String.fromCharCode(y)+']';
            }
          }
        }
        return property + expanded;
      });
  }
  function render(row) {
    if (!row.board_only || typeof row.content !== 'string') throw new Error('無法讀取棋形。');
    const kifu = WGo.Kifu.fromSgf(expandSetupRectangles(row.content));
    if (kifu.root.children.length || kifu.root.move) throw new Error('無法讀取棋形。');
    // WGo parses SGF setup ranges, labels, escaped values and actual board size.
    const reader = new WGo.KifuReader(kifu, false, false);
    game = reader.game;
    color = game.turn;
    for (const event of row.previous_steps) {
      // A failed terminal answer may be an illegal move. Do not invent a stone.
      game.play(event.player_move[0], event.player_move[1], color);
      if (event.opponent_reply) game.play(event.opponent_reply[0], event.opponent_reply[1], -color);
    }
    el('board').replaceChildren();
    board = new WGo.Board(el('board'), {size:kifu.size, width:Math.min(580, el('board').clientWidth)});
    const position = game.getPosition();
    for (let x = 0; x < kifu.size; x++) for (let y = 0; y < kifu.size; y++) {
      const c = position.get(x, y);
      if (c) board.addObject({x,y,c});
    }
    if (kifu.root.markup) board.addObject(kifu.root.markup);
    board.addEventListener('click', (x,y) => {
      if (busy || pending || !['OPEN','CONTINUE'].includes(step?.status) || !game.isOnBoard(x,y)) return;
      pending = {attempt_token:token, step_index:step.step_index, step_nonce:step.step_nonce, move:{x,y}};
      submit();
    });
    const receipt = row.previous_steps.at(-1)?.settlement?.submission_id;
    el('receipt').textContent = receipt ? '修煉紀錄：' + receipt : '';
  }
  async function readback() {
    const row = await post('steps', {attempt_token:token});
    render(row); step = row;
  }
  async function submit() {
    if (busy || !pending) return;
    busy = true; state(); el('message').textContent = '正在確認這一手…';
    try {
      await post('steps', pending);
      // Render only committed server history. If readback fails, retry the
      // identical pending nonce/move; the service returns its durable receipt.
      await readback(); pending = null; el('message').textContent = '';
    } catch (e) {
      el('status').textContent = '尚未確認這一手'; el('message').textContent = e.message;
    } finally { busy = false; el('retry').disabled = !pending; el('resume').disabled = false;
      if (!pending) state(); }
  }
  async function resume() {
    if (busy) return;
    step = null;
    busy = true; state(); el('message').textContent = '';
    try {
      const admission = await post('admission', {});
      token = admission.attempt_token; el('lesson').textContent = admission.title;
      await readback(); pending = null;
    } catch (e) { el('message').textContent = e.message; }
    finally { busy = false; state(); }
  }
  el('retry').addEventListener('click', submit);
  el('resume').addEventListener('click', resume);
  resume();
})();
