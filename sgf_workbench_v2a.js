/* SGF Workbench V2-A: human review core, not a repair editor. */
(function () {
  "use strict";

  const API = "/api/admin/sgf-workbench-v2a";
  const labels = {
    CORRECT: ["1", "正確"], WRONG_ROOT: ["2", "根答案錯"],
    MISSING_ANSWER: ["3", "漏正解"], MISSING_VARIATION: ["4", "漏變化"],
    SPECIAL: ["5", "特殊"], UNSURE: ["6", "待確認"],
  };
  const state = {
    items: [], current: null, selectedNode: "0", fullBoard: false, replay: null,
    filter: "ALL", search: "", navigation: {}, csrfHeader: "", csrfToken: "",
    busy: false,
  };

  const esc = (value) => String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  const jsonFetch = async (path, options = {}) => {
    const response = await fetch(path, { credentials: "same-origin", ...options,
      headers: { "Accept": "application/json", ...(options.headers || {}) } });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.ok === false) {
      const error = new Error(payload.detail || payload.error || `HTTP ${response.status}`);
      error.payload = payload; error.status = response.status; throw error;
    }
    return payload;
  };
  const isTyping = (event) => {
    const target = event.target;
    return target && (target.matches("input,textarea,select,[contenteditable=true]") || target.isContentEditable);
  };

  function installMarkup() {
    document.body.innerHTML = `
      <div class="v2a-app">
        <header class="v2a-top"><div><b>SGF 審題工作台</b><small>Human Review Core · V2-A</small></div>
          <div class="v2a-top-actions"><span id="v2a-sync" class="v2a-chip">載入中</span><button id="v2a-focus" class="v2a-button">Focus</button></div></header>
        <main class="v2a-shell">
          <section class="v2a-toolbar"><label>搜尋 <input id="v2a-search" placeholder="題目 ID / source / 題號" autocomplete="off"></label>
            <label>Filter <select id="v2a-filter"><option value="ALL">全部</option><option value="UNREVIEWED">未審</option><option value="CORRECT">1 正確</option><option value="WRONG_ROOT">2 根答案錯</option><option value="MISSING_ANSWER">3 漏正解</option><option value="MISSING_VARIATION">4 漏變化</option><option value="SPECIAL">5 特殊</option><option value="UNSURE">6 待確認</option><option value="CONTENT_CHANGED">內容已變更</option></select></label>
            <span id="v2a-total" class="v2a-count"></span></section>
          <section class="v2a-layout">
            <div class="v2a-board-panel"><div id="v2a-meta" class="v2a-meta"></div><div id="v2a-warning" class="v2a-warning" hidden></div><canvas id="v2a-board" aria-label="SGF review board"></canvas>
              <div class="v2a-board-actions"><button id="v2a-prev" class="v2a-button">← 上一題</button><button id="v2a-next" class="v2a-button primary">下一題 →</button><button id="v2a-viewport" class="v2a-button">F 局部 / 全盤</button></div>
            </div>
            <aside class="v2a-side"><div class="v2a-card"><div class="v2a-card-title">Answer tree</div><div id="v2a-tree" class="v2a-tree"></div></div>
              <div class="v2a-card v2a-info"><div class="v2a-card-title">Question</div><div id="v2a-info"></div></div>
              <div class="v2a-card"><div class="v2a-card-title">人工分類</div><div id="v2a-classifications" class="v2a-classifications"></div><p class="v2a-hint">分類只記錄人工觀察，不會修改題庫。←/→ 題目、Space 下一手、Backspace 上一手、Home 初始、↑/↓ sibling、Enter 選擇。</p></div>
            </aside>
          </section>
          <div id="v2a-empty" class="v2a-empty" hidden>目前篩選沒有題目。</div>
        </main><div id="v2a-toast" class="v2a-toast" role="status" aria-live="polite"></div>
      </div>`;
    const style = document.createElement("style");
    style.textContent = `
      :root{color-scheme:dark;--a-bg:#0d1511;--a-panel:#17231d;--a-panel2:#1e3026;--a-line:#385244;--a-text:#f4f1e4;--a-muted:#a9b8ad;--a-green:#63d696;--a-gold:#e5bd68;--a-red:#ff8a7c}
      *{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 12% -12%,#2a4a35 0,transparent 34rem),var(--a-bg);color:var(--a-text);font:14px Inter,"Noto Sans TC",system-ui,sans-serif}.v2a-app{min-height:100vh}.v2a-top{position:sticky;top:0;z-index:4;display:flex;justify-content:space-between;align-items:center;padding:12px max(14px,env(safe-area-inset-left)) 12px max(14px,env(safe-area-inset-right));background:rgba(13,21,17,.94);border-bottom:1px solid var(--a-line);backdrop-filter:blur(12px)}.v2a-top b{display:block;font-size:18px}.v2a-top small{display:block;color:var(--a-muted);margin-top:3px}.v2a-top-actions{display:flex;align-items:center;gap:8px}.v2a-chip{padding:7px 11px;border:1px solid var(--a-line);border-radius:99px;color:var(--a-muted)}.v2a-button{min-height:44px;padding:8px 13px;border:1px solid var(--a-line);border-radius:12px;background:#20372b;color:var(--a-text);font-weight:750;cursor:pointer}.v2a-button.primary{background:#267847;border-color:#66ce91}.v2a-button:disabled{opacity:.4;cursor:not-allowed}.v2a-shell{width:min(1500px,100%);margin:auto;padding:14px max(12px,env(safe-area-inset-left)) 40px max(12px,env(safe-area-inset-right))}.v2a-toolbar{display:flex;gap:10px;align-items:end;flex-wrap:wrap;margin-bottom:12px}.v2a-toolbar label{display:flex;flex-direction:column;gap:5px;color:var(--a-muted);font-size:12px;min-width:190px}.v2a-toolbar input,.v2a-toolbar select{min-height:43px;padding:8px 10px;border:1px solid var(--a-line);border-radius:10px;background:#15231b;color:var(--a-text)}.v2a-count{margin-left:auto;color:var(--a-muted);padding-bottom:12px}.v2a-layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(300px,380px);gap:12px;align-items:start}.v2a-board-panel,.v2a-card{background:linear-gradient(160deg,rgba(30,48,38,.98),rgba(18,30,24,.98));border:1px solid var(--a-line);border-radius:18px;box-shadow:0 16px 45px rgba(0,0,0,.24)}.v2a-board-panel{padding:14px}.v2a-meta{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;min-height:28px;color:var(--a-muted)}#v2a-board{display:block;width:min(100%,760px);height:auto;aspect-ratio:1;margin:8px auto;background:#c79c59;border-radius:8px;touch-action:none}.v2a-board-actions{display:flex;gap:8px;flex-wrap:wrap;justify-content:center;margin-top:10px}.v2a-side{display:grid;gap:12px;position:sticky;top:78px}.v2a-card{padding:13px}.v2a-card-title{font-weight:850;color:var(--a-gold);margin-bottom:9px;letter-spacing:.04em}.v2a-tree{max-height:46vh;overflow:auto;padding-right:3px}.v2a-tree button{display:block;width:100%;text-align:left;border:0;border-left:3px solid transparent;background:transparent;color:var(--a-text);padding:7px 8px;border-radius:7px;cursor:pointer}.v2a-tree button:hover,.v2a-tree button.selected{background:#2b533b;border-left-color:var(--a-green)}.v2a-tree .tree-indent{display:inline-block}.v2a-info{line-height:1.8;color:var(--a-muted)}.v2a-info strong{color:var(--a-text)}.v2a-classifications{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.v2a-classifications button{min-height:56px;border:1px solid var(--a-line);border-radius:11px;background:#1a3024;color:var(--a-text);cursor:pointer;text-align:left;padding:7px 9px}.v2a-classifications button.current{border-color:var(--a-green);box-shadow:0 0 0 2px rgba(99,214,150,.2)}.v2a-classifications b{display:block;color:var(--a-gold);font-size:17px}.v2a-hint{color:var(--a-muted);font-size:12px;line-height:1.55;margin:10px 0 0}.v2a-warning{margin:7px 0;padding:8px 10px;border:1px solid #8c6334;border-radius:9px;color:#ffd99d;background:#3b2a16}.v2a-empty{padding:40px;text-align:center;color:var(--a-muted)}.v2a-toast{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);padding:10px 15px;border:1px solid var(--a-line);border-radius:12px;background:#172c20;opacity:0;pointer-events:none;transition:opacity .2s;z-index:8}.v2a-toast.show{opacity:1}@media(max-width:900px){.v2a-layout{grid-template-columns:1fr}.v2a-side{position:static}.v2a-board-panel{order:0}.v2a-tree{max-height:260px}}@media(max-width:550px){.v2a-toolbar label{min-width:calc(50% - 5px);flex:1}.v2a-count{width:100%;margin:0;padding:0}.v2a-board-actions .v2a-button{flex:1}.v2a-top{align-items:flex-start}.v2a-chip{font-size:11px}}.v2a-focus .v2a-meta,.v2a-focus .v2a-info{display:none}.v2a-focus .v2a-layout{grid-template-columns:minmax(0,1fr) 330px}.v2a-focus .v2a-side{gap:8px}
    `;
    document.head.appendChild(style);
  }

  function toast(message) { const node = document.getElementById("v2a-toast"); node.textContent = message; node.classList.add("show"); setTimeout(() => node.classList.remove("show"), 1500); }
  function setSync(text, kind) { const node = document.getElementById("v2a-sync"); node.textContent = text; node.dataset.state = kind || ""; }

  async function loadBootstrap(recordIndex) {
    const params = new URLSearchParams({ filter: state.filter, search: state.search, limit: "200" });
    if (recordIndex != null) params.set("record_index", String(recordIndex));
    setSync("載入中", "pending");
    try {
      const payload = await jsonFetch(`${API}/bootstrap?${params}`);
      state.items = payload.items || []; state.current = payload.current || null; state.replay = state.current?.playback || null; state.navigation = payload.navigation || {};
      state.csrfHeader = payload.security?.csrf_header || ""; state.csrfToken = payload.security?.csrf_token || "";
      state.selectedNode = "0"; render(); setSync("已同步", "saved");
    } catch (error) { setSync("載入失敗", "error"); toast(error.message); }
  }
  async function loadQuestion(index) {
    if (index == null || state.busy) return;
    state.busy = true; setSync("切題中", "pending");
    try {
      const payload = await jsonFetch(`${API}/questions/${encodeURIComponent(index)}`);
      state.current = payload.question; state.selectedNode = "0"; state.replay = state.current?.playback || null;
      const bootstrap = await jsonFetch(`${API}/bootstrap?filter=${encodeURIComponent(state.filter)}&search=${encodeURIComponent(state.search)}&record_index=${encodeURIComponent(index)}&limit=200`);
      state.items = bootstrap.items || state.items; state.navigation = bootstrap.navigation || {};
      state.csrfHeader = bootstrap.security?.csrf_header || state.csrfHeader; state.csrfToken = bootstrap.security?.csrf_token || state.csrfToken;
      render(); setSync("已同步", "saved");
    } catch (error) { toast(error.message); } finally { state.busy = false; }
  }
  function currentNode() { return (state.current?.tree?.nodes || []).find((node) => node.id === state.selectedNode); }
  function replayClient(tree, nodeId) {
    const nodes = Object.fromEntries((tree?.nodes || []).map((node) => [node.id, node]));
    if (!nodes["0"] || !nodes[nodeId]) return { status: "FAIL", error: "node_not_found", stones: [] };
    const path = []; let cursor = nodeId;
    while (cursor !== "0") { path.unshift(cursor); cursor = nodes[cursor]?.parent_id; if (!cursor || !nodes[cursor]) return { status: "FAIL", error: "broken_parent_link", stones: [] }; }
    const stones = new Map();
    (tree.initial_stones || []).forEach((stone) => { const key = `${stone.x},${stone.y}`; if (stone.color === "E") stones.delete(key); else stones.set(key, {x:stone.x,y:stone.y,color:stone.color}); });
    path.forEach((id) => { const move = nodes[id]?.move || {}; if (move.pass || move.invalid || !Number.isInteger(move.x) || !Number.isInteger(move.y)) return; stones.set(`${move.x},${move.y}`, {x:move.x,y:move.y,color:move.color}); });
    return { status: "PASS", path: ["0", ...path], stones: Array.from(stones.values()) };
  }
  function selectNode(id) { if (!state.current?.tree?.nodes?.some((node) => node.id === id)) return; state.selectedNode = id; state.replay = replayClient(state.current.tree, id); renderBoard(); renderTree(); renderMeta(); }
  function sibling(delta) {
    const node = currentNode(); if (!node || !node.parent_id) return;
    const parent = state.current.tree.nodes.find((candidate) => candidate.id === node.parent_id); const index = parent?.children?.indexOf(node.id) ?? -1;
    const next = parent?.children?.[index + delta]; if (next) selectNode(next);
  }
  function nextMove() { const node = currentNode(); const child = node?.children?.[0]; if (child) selectNode(child); }
  function previousMove() { const node = currentNode(); if (node?.parent_id) selectNode(node.parent_id); }
  function renderMeta() {
    const q = state.current; const node = currentNode(); if (!q) return;
    document.getElementById("v2a-meta").innerHTML = `<span><strong>${esc(q.legacy_question_id)}</strong> · record ${esc(q.record_index)} · ${esc(q.source || "未標來源")}</span><span>${esc(q.review_state)}${q.classification ? ` · ${esc(q.classification)}` : ""} · ${esc(node?.id || "0")}</span>`;
    document.getElementById("v2a-total").textContent = `${state.items.length ? state.items.findIndex((item) => item.record_index === q.record_index) + 1 : 0} / ${state.items.length || 0} · ${q.reviewed_record_sha256.slice(0, 10)}`;
    const info = document.getElementById("v2a-info"); info.innerHTML = `<div><strong>ID</strong> ${esc(q.legacy_question_id)}</div><div><strong>record</strong> ${esc(q.record_index)}</div><div><strong>先手</strong> ${esc(q.side_to_play || "—")}</div><div><strong>source</strong> ${esc(q.source || "—")}</div><div><strong>狀態</strong> ${esc(q.review_state)}${q.review_state === "CONTENT_CHANGED" ? "（需重新審核）" : ""}</div>`;
    const warning = document.getElementById("v2a-warning");
    if (q.playback?.status === "FAIL") { warning.hidden = false; warning.textContent = `本題只讀播放遇到技術問題：${q.playback.error || "replay_failed"}。不阻止繼續審題。`; } else { warning.hidden = true; }
  }
  function renderTree() {
    const tree = document.getElementById("v2a-tree"); const nodes = state.current?.tree?.nodes || [];
    if (!nodes.length) { tree.innerHTML = '<span class="v2a-hint">Answer tree 無法解析。</span>'; return; }
    tree.innerHTML = nodes.map((node) => {
      const depth = Math.max(0, String(node.id).split(".").length - 1); const move = node.move;
      const text = node.id === "0" ? "初始局面" : (move?.pass ? `${move.color} pass` : move?.invalid ? "無效手" : `${move?.color || "?"} ${String.fromCharCode(65 + (move?.x || 0))}${(move?.y || 0) + 1}`);
      return `<button type="button" class="${node.id === state.selectedNode ? "selected" : ""}" data-tree-node="${esc(node.id)}"><span class="tree-indent" style="width:${depth * 14}px"></span>${esc(text)}</button>`;
    }).join("");
    tree.querySelectorAll("[data-tree-node]").forEach((button) => button.addEventListener("click", () => selectNode(button.dataset.treeNode)));
  }
  function renderClassifications() {
    const root = document.getElementById("v2a-classifications"); const current = state.current?.classification;
    root.innerHTML = Object.entries(labels).map(([key, value]) => `<button type="button" data-classification="${key}" class="${key === current ? "current" : ""}"><b>${value[0]}</b>${value[1]}</button>`).join("");
    root.querySelectorAll("[data-classification]").forEach((button) => button.addEventListener("click", () => classify(button.dataset.classification)));
  }
  function boardGeometry(canvas, viewport) {
    const width = canvas.clientWidth || 640; const dpr = window.devicePixelRatio || 1; canvas.width = width * dpr; canvas.height = width * dpr;
    const ctx = canvas.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); const pad = Math.max(22, width * .055);
    const cols = Math.max(1, viewport.x1 - viewport.x0); const rows = Math.max(1, viewport.y1 - viewport.y0); const step = Math.min((width - pad * 2) / cols, (width - pad * 2) / rows);
    return { ctx, width, pad, step, x: (value) => pad + (value - viewport.x0) * step, y: (value) => pad + (value - viewport.y0) * step };
  }
  function renderBoard() {
    const q = state.current; const canvas = document.getElementById("v2a-board"); if (!q || !canvas) return;
    const viewport = q.viewport?.mode === "FULL" && !state.fullBoard ? q.viewport : (state.fullBoard ? {...q.viewport, mode:"FULL", x0:0,y0:0,x1:(q.tree.board_size||19)-1,y1:(q.tree.board_size||19)-1} : q.viewport);
    const geo = boardGeometry(canvas, viewport); const {ctx,width,pad,step,x,y} = geo; ctx.clearRect(0,0,width,width); ctx.fillStyle="#c79c59"; ctx.fillRect(0,0,width,width); ctx.strokeStyle="rgba(40,28,15,.78)"; ctx.lineWidth=1;
    for (let yy=viewport.y0; yy<=viewport.y1; yy++) { ctx.beginPath(); ctx.moveTo(x(viewport.x0),y(yy)); ctx.lineTo(x(viewport.x1),y(yy)); ctx.stroke(); }
    for (let xx=viewport.x0; xx<=viewport.x1; xx++) { ctx.beginPath(); ctx.moveTo(x(xx),y(viewport.y0)); ctx.lineTo(x(xx),y(viewport.y1)); ctx.stroke(); }
    const radius = Math.max(7, Math.min(19, step * .42));
    (state.replay?.stones || q.playback?.stones || []).forEach((stone) => { if (stone.x < viewport.x0 || stone.x > viewport.x1 || stone.y < viewport.y0 || stone.y > viewport.y1) return; ctx.beginPath(); ctx.arc(x(stone.x),y(stone.y),radius,0,Math.PI*2); ctx.fillStyle=stone.color === "B" ? "#111" : "#f4f0e4"; ctx.fill(); ctx.strokeStyle=stone.color === "B" ? "#555" : "#554b3b"; ctx.stroke(); });
    const selected = currentNode()?.move; if (selected && !selected.pass && Number.isInteger(selected.x) && Number.isInteger(selected.y)) { ctx.beginPath(); ctx.arc(x(selected.x),y(selected.y),Math.max(3,radius*.28),0,Math.PI*2); ctx.fillStyle="#e46759"; ctx.fill(); }
    ctx.fillStyle="#2a1f12"; ctx.font="11px system-ui"; ctx.fillText(viewport.touch_top ? "上邊" : "", pad, 14); ctx.fillText(viewport.touch_left ? "左邊" : "", 3, pad + 4);
  }
  function render() { const empty = document.getElementById("v2a-empty"); empty.hidden = !!state.current; renderMeta(); renderTree(); renderClassifications(); renderBoard(); }
  async function saveProgress() {
    const q = state.current; if (!q) return;
    await jsonFetch(`${API}/progress`, { method:"POST", headers:{"Content-Type":"application/json", [state.csrfHeader]: state.csrfToken}, body:JSON.stringify({record_index:q.record_index}) });
  }
  async function classify(classification) {
    const q = state.current; if (!q || state.busy) return; state.busy = true; setSync("保存中", "pending");
    try {
      const payload = await jsonFetch(`${API}/reviews`, { method:"POST", headers:{"Content-Type":"application/json", [state.csrfHeader]: state.csrfToken}, body:JSON.stringify({record_index:q.record_index, legacy_question_id:q.legacy_question_id, reviewed_record_sha256:q.reviewed_record_sha256, classification}) });
      q.classification = payload.review?.classification || classification; q.review_state = "CURRENT"; renderClassifications(); renderMeta(); setSync("已保存", "saved");
      await saveProgress();
      if (classification === "CORRECT") { setTimeout(() => goNext(), 80); }
    } catch (error) { toast(error.message); setSync("保存失敗", "error"); } finally { state.busy = false; }
  }
  async function goNext() { if (state.current) { try { await saveProgress(); } catch (error) { toast(error.message); return; } } if (state.navigation.next_record_index != null) return loadQuestion(state.navigation.next_record_index); toast("已到目前篩選最後一題"); }
  async function goPrevious() { if (state.current) { try { await saveProgress(); } catch (error) { toast(error.message); return; } } if (state.navigation.previous_record_index != null) return loadQuestion(state.navigation.previous_record_index); toast("已是第一題"); }
  function handleKey(event) {
    if (isTyping(event) || !state.current) return;
    const key = event.key; if ([" ","Backspace","Home","ArrowLeft","ArrowRight","ArrowUp","ArrowDown","Enter","f","F","1","2","3","4","5","6"].includes(key)) event.preventDefault();
    if (key === " ") nextMove(); else if (key === "Backspace") previousMove(); else if (key === "Home") selectNode("0"); else if (key === "ArrowLeft") goPrevious(); else if (key === "ArrowRight") goNext(); else if (key === "ArrowUp") sibling(-1); else if (key === "ArrowDown") sibling(1); else if (key === "Enter") { const node = currentNode(); if (node?.children?.[0]) selectNode(node.children[0]); } else if (key.toLowerCase() === "f") { state.fullBoard = !state.fullBoard; renderBoard(); } else if (labels[Object.keys(labels).find((name) => labels[name][0] === key)]) { const name = Object.keys(labels).find((candidate) => labels[candidate][0] === key); classify(name); }
  }
  function bind() {
    document.getElementById("v2a-filter").addEventListener("change", (event) => { state.filter = event.target.value; loadBootstrap(); });
    const search = document.getElementById("v2a-search"); search.addEventListener("keydown", (event) => { if (event.key === "Enter") { state.search = search.value; loadBootstrap(); } });
    document.getElementById("v2a-prev").addEventListener("click", goPrevious); document.getElementById("v2a-next").addEventListener("click", goNext);
    document.getElementById("v2a-viewport").addEventListener("click", () => { state.fullBoard = !state.fullBoard; renderBoard(); });
    document.getElementById("v2a-focus").addEventListener("click", () => document.body.classList.toggle("v2a-focus"));
    window.addEventListener("keydown", handleKey); window.addEventListener("resize", renderBoard);
  }
  installMarkup(); bind(); loadBootstrap();
})();
