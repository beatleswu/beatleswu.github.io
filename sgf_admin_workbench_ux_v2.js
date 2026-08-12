(function () {
  "use strict";

  const SOURCE_LABELS = {
    PLAYER_REPORT: "玩家回報",
    ADMIN_PLAY: "系統發現",
    CORPUS_SCAN: "自動掃描",
  };
  const ISSUE_LABELS = {
    ALTERNATIVE_CORRECT_MOVE: "玩家認為還有其他正解",
    SYSTEM_ANSWER_INCORRECT: "目前正解可能不正確",
    QUESTION_CONTENT_PROBLEM: "題目或局面需要檢查",
    BOARD_OR_DISPLAY_PROBLEM: "棋盤或顯示問題",
    OTHER: "其他問題",
  };
  const ACTION_LABELS = {
    ADD_ALTERNATIVE_CORRECT_MOVE: "新增另一個正解",
    REMOVE_INCORRECT_ACCEPTED_MOVE: "移除錯誤正解",
    REPLACE_ANSWER: "修改正解",
    DISABLE_BROKEN_QUESTION: "標記題目需重建",
    NEEDS_RESEARCH: "稍後研究",
  };
  const ACTION_TO_TEXT = {
    ADD_ALTERNATIVE_CORRECT_MOVE: "你準備新增另一個也成立的正解",
    REPLACE_ANSWER: "你準備把目前答案修改為",
  };
  const API = "/api/admin/sgf-workbench";
  const state = {
    items: [],
    questions: new Map(),
    currentIndex: 0,
    current: null,
    mode: null,
    directMode: false,
    directContext: null,
    directVersion: null,
    directHistory: [],
    directSide: null,
    boardEditTool: null,
    boardEditStones: [],
    directContent: "",
    selectedMove: null,
    proposal: null,
    csrfHeader: "",
    csrfToken: "",
    busy: false,
  };

  const esc = (value) => String(value == null ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
  const el = (id) => document.getElementById(id);
  const visibleItems = () => state.items.filter((item) => ["OPEN", "NEEDS_RESEARCH"].includes(item.status));
  const stagedItems = () => state.items.filter((item) => item.status === "STAGED");

  function moveFromSgf(value) {
    if (!value || typeof value !== "string" || value.length < 2) return null;
    const x = value.charCodeAt(0) - 97;
    const y = value.charCodeAt(1) - 97;
    return x >= 0 && x < 19 && y >= 0 && y < 19 ? { x, y } : null;
  }

  function gtp(move) {
    if (!move || !Number.isInteger(Number(move.x)) || !Number.isInteger(Number(move.y))) return "未選定";
    const letters = "ABCDEFGHJKLMNOPQRST";
    return `${letters[Number(move.x)] || "?"}${19 - Number(move.y)}`;
  }

  function sameMove(a, b) {
    return !!a && !!b && Number(a.x) === Number(b.x) && Number(a.y) === Number(b.y);
  }

  async function jsonFetch(url, options) {
    const response = await fetch(url, Object.assign({ credentials: "same-origin", headers: { Accept: "application/json" } }, options || {}));
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
    return payload;
  }

  async function postJson(url, body) {
    const headers = { "Content-Type": "application/json", Accept: "application/json" };
    if (state.csrfHeader && state.csrfToken) headers[state.csrfHeader] = state.csrfToken;
    return jsonFetch(url, { method: "POST", headers, body: JSON.stringify(body || {}) });
  }

  function toast(message, error) {
    const node = el("v2-toast");
    if (!node) return;
    node.textContent = message;
    node.classList.toggle("is-error", !!error);
    node.classList.add("is-visible");
    window.clearTimeout(toast.timer);
    toast.timer = window.setTimeout(() => node.classList.remove("is-visible"), 2800);
  }

  function injectMarkup() {
    if (el("ux-v2-root")) return;
    document.body.classList.add("ux-v2-active");
    document.title = "SGF 審題｜Go Odyssey";
    const style = document.createElement("style");
    style.id = "ux-v2-style";
    style.textContent = `
      .ux-v2-active .topbar,.ux-v2-active>.shell,.ux-v2-active>#sticky-nav,.ux-v2-active>#toast{display:none!important}
      .ux-v2-root{min-height:100vh;background:radial-gradient(circle at 8% -8%,#365b40 0,transparent 34rem),linear-gradient(150deg,#0d1511,#122019 62%,#0b100e);color:#f6f0df;padding:env(safe-area-inset-top) max(14px,env(safe-area-inset-right)) calc(30px + env(safe-area-inset-bottom)) max(14px,env(safe-area-inset-left));font-family:Inter,"Noto Sans TC","PingFang TC","Microsoft JhengHei",system-ui,sans-serif}
      .ux-v2-root *{box-sizing:border-box}.ux-v2-root button{font:inherit;min-height:50px;touch-action:manipulation}.ux-v2-root button:focus-visible{outline:3px solid #8dc8ff;outline-offset:3px}.ux-v2-root [hidden]{display:none!important}
      .v2-topbar{width:min(1180px,100%);margin:0 auto;padding:16px 0 12px;display:flex;align-items:center;justify-content:space-between;gap:12px}.v2-brand{display:flex;align-items:center;gap:11px}.v2-mark{display:grid;place-items:center;width:46px;height:46px;border-radius:15px;border:1px solid #a17f42;background:linear-gradient(145deg,#463820,#201d14);font-size:23px;color:#f8d98d}.v2-brand strong{display:block;font-size:clamp(18px,3vw,25px)}.v2-brand span{display:block;margin-top:3px;color:#a8b5aa;font-size:12px}.v2-badge{display:inline-flex;align-items:center;min-height:34px;padding:4px 11px;border:1px solid #b88943;border-radius:999px;color:#ffd994;background:#2b2517;font-size:12px;font-weight:800;white-space:nowrap}
      .v2-shell{width:min(1180px,100%);margin:0 auto}.v2-view{animation:v2-fade .18s ease}@keyframes v2-fade{from{opacity:.3;transform:translateY(5px)}to{opacity:1;transform:none}}
      .v2-card{border:1px solid #34483c;border-radius:24px;background:linear-gradient(160deg,rgba(30,45,37,.98),rgba(20,31,26,.98));box-shadow:0 20px 60px rgba(0,0,0,.3)}
      .v2-home-hero{position:relative;overflow:hidden;padding:clamp(24px,5vw,58px)}.v2-home-hero:after{content:"";position:absolute;width:370px;height:370px;border-radius:50%;right:-170px;top:-220px;border:74px solid rgba(229,189,104,.06);pointer-events:none}.v2-kicker{font-size:12px;letter-spacing:.2em;color:#e5bd68;font-weight:900}.v2-home-hero h1{margin:12px 0 9px;font-size:clamp(35px,7vw,66px);line-height:1.02;letter-spacing:-.04em}.v2-home-hero p{max-width:650px;margin:0;color:#c7d2ca;line-height:1.75;font-size:clamp(15px,2vw,18px)}
      .v2-stat-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:18px 0 0}.v2-stat{padding:16px;border:1px solid #34483c;border-radius:18px;background:rgba(8,15,11,.48)}.v2-stat strong{display:block;font-size:clamp(26px,4.5vw,40px);color:#fff}.v2-stat span{display:block;margin-top:2px;color:#a8b5aa;font-size:12px}.v2-actions{display:flex;align-items:center;flex-wrap:wrap;gap:10px;margin-top:22px}.v2-primary,.v2-secondary,.v2-quiet,.v2-warn{border:1px solid transparent;border-radius:16px;padding:11px 19px;color:#fff;font-weight:900;cursor:pointer}.v2-primary{background:linear-gradient(135deg,#2d925b,#1e7046);box-shadow:0 9px 26px rgba(35,146,87,.2)}.v2-secondary{background:#24372d;border-color:#496052}.v2-quiet{background:transparent;border-color:#405448;color:#d7e0da}.v2-warn{background:#4a3422;border-color:#98683d}.v2-primary:active,.v2-secondary:active,.v2-quiet:active,.v2-warn:active{transform:translateY(1px)}
      .v2-home-links{display:flex;flex-wrap:wrap;gap:10px;margin-top:14px}.v2-link{border:0;background:none;color:#bed8c5;text-decoration:underline;text-underline-offset:4px;cursor:pointer;padding:7px 3px;font-weight:750}.v2-safety{display:flex;gap:9px;align-items:flex-start;margin-top:19px;color:#a9c5ae;font-size:12px;line-height:1.55}.v2-safety strong{color:#8de4ad}.v2-details{margin-top:18px;border-top:1px solid #34483c;padding-top:14px}.v2-details summary{cursor:pointer;min-height:44px;display:flex;align-items:center;color:#c5d6c9;font-weight:800}.v2-details-body{color:#9fb0a4;font:12px/1.65 ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere}
      .v2-review-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:4px 0 14px}.v2-review-head h2{margin:0;font-size:clamp(19px,3vw,29px)}.v2-review-head p{margin:4px 0 0;color:#a8b5aa;font-size:13px}.v2-head-actions{display:flex;gap:8px;align-items:center}.v2-review-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(310px,390px);gap:16px;align-items:start}.v2-board-card{padding:14px}.v2-board-meta{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-bottom:12px}.v2-chip{display:inline-flex;align-items:center;min-height:34px;padding:5px 10px;border:1px solid #405548;border-radius:999px;background:#101a15;color:#d7e7da;font-size:12px;font-weight:850}.v2-chip.player{color:#bfe3ff;border-color:#416d8e}.v2-chip.scan{color:#ffd47e;border-color:#886a36}.v2-chip.admin{color:#a8e5bf;border-color:#397a53}.v2-board-title{margin:0 0 12px;font-size:clamp(18px,3vw,27px)}.v2-board-wrap{position:relative;width:min(100%,760px);aspect-ratio:1;margin:0 auto;border:1px solid #766038;border-radius:18px;overflow:hidden;background:#d5a85c;box-shadow:inset 0 0 0 6px rgba(70,43,13,.12),0 16px 38px rgba(0,0,0,.25)}.v2-board-wrap.selecting{box-shadow:0 0 0 4px #77bdfb,0 16px 38px rgba(0,0,0,.25)}#v2-go-board{display:block;width:100%;height:100%;touch-action:none}.v2-board-caption{display:flex;justify-content:center;gap:14px;flex-wrap:wrap;padding:12px 4px 2px;color:#d3ddd6;font-size:13px}.v2-board-caption b{display:inline-grid;place-items:center;width:25px;height:25px;border-radius:50%;margin-right:4px}.v2-answer{border:3px solid #5bd18b;color:#174527}.v2-candidate{border:3px solid #ff9c52;color:#6a3719}.v2-picked{border:3px solid #77bdfb;color:#183e5f}
      .v2-control{padding:18px;position:sticky;top:12px}.v2-progress{display:flex;justify-content:space-between;gap:8px;color:#a8b5aa;font-size:13px;margin-bottom:8px}.v2-progress-bar{height:8px;border-radius:99px;overflow:hidden;background:#0d1812;margin-bottom:18px}.v2-progress-bar span{display:block;height:100%;background:linear-gradient(90deg,#4ed181,#e5bd68);transition:width .2s}.v2-control h3{margin:0 0 10px;font-size:16px}.v2-prompt{margin:0 0 14px;padding:12px 13px;border-radius:14px;border:1px solid #405548;background:#101a15;color:#dbe7dd;line-height:1.55}.v2-decision-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.v2-decision{min-height:70px;padding:10px 12px;text-align:left;border:1px solid #415a4b;border-radius:16px;background:#22342a;color:#f6f5ed;font-weight:900;cursor:pointer}.v2-decision small{display:block;margin-top:4px;color:#aab9ae;font-size:11px;font-weight:550;line-height:1.4}.v2-decision.good{border-color:#3c8559;background:#1d4630}.v2-decision.alt{border-color:#456f93;background:#21384b}.v2-decision.wrong{border-color:#8d4945;background:#482927}.v2-decision.defer{border-color:#98683d;background:#4a3422}.v2-secondary-action{width:100%;margin-top:13px;border:1px solid #6a5541;border-radius:15px;background:#2b251d;color:#ffd694;padding:11px 13px;text-align:left;font-weight:850;cursor:pointer}.v2-broken-panel{margin-top:10px;padding:12px;border:1px solid #6a5541;border-radius:15px;background:#211c16}.v2-broken-grid{display:grid;gap:8px}.v2-broken-grid button{border:1px solid #735c3b;border-radius:12px;background:#30271c;color:#ffdda4;text-align:left;padding:9px 11px;font-weight:750;cursor:pointer}.v2-selection-banner{margin:0 0 12px;padding:12px 14px;border:1px solid #4384af;border-radius:15px;background:#15344a;color:#c8e8ff;font-weight:800;line-height:1.55}.v2-selection-banner strong{display:block;font-size:15px;color:#fff}.v2-proposal{margin-top:12px;padding:14px;border:1px solid #4384af;border-radius:16px;background:#152c3c}.v2-proposal h3{margin:0 0 10px;color:#c8e8ff;font-size:16px}.v2-proposal-compare{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:11px}.v2-proposal-compare div{padding:10px;border-radius:12px;background:#203f50;color:#e9f7ff}.v2-proposal-compare span{display:block;color:#a7cee7;font-size:11px;margin-bottom:3px}.v2-proposal-actions{display:flex;gap:8px}.v2-proposal-actions>*{flex:1}.v2-result{margin-top:12px;padding:15px;border:1px solid #397a53;border-radius:16px;background:#173b27}.v2-result h3{margin:0;color:#bdf5d0}.v2-result p{margin:5px 0 12px;color:#d6eedb}.v2-result-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px}.v2-verdict{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:11px}.v2-verdict div{padding:10px;border-radius:12px;background:#10271a}.v2-verdict span{display:block;color:#a9c5ae;font-size:11px}.v2-verdict strong{display:block;margin-top:4px;font-size:17px}.v2-detail-card{margin-top:14px;border-top:1px solid #34483c;padding-top:13px}.v2-detail-card summary{min-height:44px;display:flex;align-items:center;cursor:pointer;color:#c5d6c9;font-weight:800}.v2-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;font-size:12px}.v2-detail-grid div{padding:9px 10px;border:1px solid #34483c;border-radius:12px;background:#101a15}.v2-detail-grid span{display:block;color:#8fa394;margin-bottom:3px}.v2-detail-grid strong{display:block;color:#e4eee6;overflow-wrap:anywhere}
      .v2-pending-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin:4px 0 14px}.v2-pending-head h2{margin:0;font-size:clamp(22px,4vw,34px)}.v2-pending-head p{margin:6px 0 0;color:#a8b5aa}.v2-pending-list{display:grid;gap:10px}.v2-pending-card{padding:15px;display:flex;align-items:center;justify-content:space-between;gap:12px}.v2-pending-card h3{margin:0 0 5px;font-size:16px}.v2-pending-card p{margin:0;color:#a8b5aa;font-size:13px}.v2-pending-card .v2-chip{margin-top:8px}.v2-handoff{margin-top:14px;padding:14px;border:1px solid #405548;border-radius:16px;background:#101a15;color:#bcd2c1;line-height:1.55}.v2-handoff strong{color:#8de4ad}.v2-empty{padding:44px 22px;text-align:center;color:#a8b5aa}.v2-toast{position:fixed;z-index:100;left:50%;bottom:22px;transform:translate(-50%,18px);opacity:0;pointer-events:none;max-width:calc(100% - 28px);padding:12px 17px;border-radius:14px;background:#eef7f0;color:#16251c;font-weight:850;box-shadow:0 12px 40px rgba(0,0,0,.4);transition:.2s}.v2-toast.is-visible{opacity:1;transform:translate(-50%,0)}.v2-toast.is-error{background:#ffd7d3;color:#52211d}
      @media(max-width:899px){.ux-v2-root{padding-left:max(12px,env(safe-area-inset-left));padding-right:max(12px,env(safe-area-inset-right))}.v2-topbar{padding-top:max(12px,env(safe-area-inset-top))}.v2-brand span{display:none}.v2-review-grid{grid-template-columns:1fr}.v2-control{position:static}.v2-board-card{padding:10px}.v2-board-wrap{width:min(100%,calc(100vw - 38px))}.v2-stat-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.v2-pending-card{align-items:flex-start;flex-direction:column}.v2-pending-card button{width:100%}}
      @media(max-width:899px) and (orientation:landscape){.v2-board-wrap{width:min(72vh,calc(100vw - 38px))}.v2-review-grid{grid-template-columns:minmax(0,1fr) minmax(285px,350px)}.v2-control{position:sticky;top:10px}.v2-decision{min-height:60px}.v2-home-hero{padding:26px 22px}}
      @media(min-width:600px) and (max-width:899px) and (orientation:portrait){.v2-board-wrap{width:min(calc(100vw - 38px),calc(100vh - 465px))}.v2-board-card{padding:10px}.v2-control{padding:14px}.v2-decision{min-height:62px}.v2-prompt{margin-bottom:10px}.v2-detail-card{margin-top:8px}}
      @media(min-width:900px){.v2-home-hero{min-height:510px;display:flex;flex-direction:column;justify-content:center}.v2-review-grid{grid-template-columns:minmax(0,1fr) 390px}}
      @media(prefers-reduced-motion:reduce){.ux-v2-root *{animation:none!important;transition:none!important}}
    `;
    document.head.appendChild(style);
    const root = document.createElement("div");
    root.id = "ux-v2-root";
    root.className = "ux-v2-root";
    root.innerHTML = `
      <header class="v2-topbar"><div class="v2-brand"><div class="v2-mark">圍</div><div><strong>SGF 審題</strong><span>先看棋盤，再做一個決定</span></div></div><span class="v2-badge">非 Production 測試環境</span></header>
      <main class="v2-shell">
        <section id="v2-home" class="v2-view">
          <div class="v2-card v2-home-hero"><div class="v2-kicker">GO ODYSSEY · SGF REVIEW</div><h1>SGF 審題</h1><p>把注意力放在棋盤與答案上。每次只做一個清楚的判斷，修改會先暫存，不會影響目前玩家。</p>
            <div class="v2-stat-grid"><div class="v2-stat"><strong id="v2-count-pending">—</strong><span>待確認題目</span></div><div class="v2-stat"><strong id="v2-count-player">—</strong><span>玩家回報</span></div><div class="v2-stat"><strong id="v2-count-system">—</strong><span>系統發現</span></div><div class="v2-stat"><strong id="v2-count-deferred">—</strong><span>稍後處理</span></div></div>
            <div class="v2-actions"><button id="v2-start" class="v2-primary">開始審題</button><button id="v2-resume" class="v2-secondary">繼續上次進度</button><button id="v2-pending" class="v2-secondary">待套用修改 <span id="v2-pending-count">0</span></button></div>
            <div class="v2-home-links"><button id="v2-done" class="v2-link">查看已處理題目</button><button id="v2-home-details-toggle" class="v2-link">詳細資料</button></div>
            <div class="v2-safety"><span>●</span><div><strong>目前只在非 Production 暫存</strong><br>暫存修改、報告證據與批次交接都會留在這個測試環境。</div></div>
            <details id="v2-home-details" class="v2-details"><summary>工作台詳細資料</summary><div id="v2-home-details-body" class="v2-details-body">載入中…</div></details>
          </div>
        </section>
        <section id="v2-review" class="v2-view" hidden>
          <div class="v2-review-head"><div><button id="v2-review-home" class="v2-link">← 回到審題首頁</button><h2 id="v2-question-title">SGF 題目</h2><p id="v2-review-progress">正在載入</p></div><div class="v2-head-actions"><button id="v2-review-pending" class="v2-secondary">待套用修改</button></div></div>
          <div class="v2-review-grid"><section class="v2-card v2-board-card"><div id="v2-board-meta" class="v2-board-meta"></div><div id="v2-selection-banner" class="v2-selection-banner" hidden></div><div class="v2-board-wrap" id="v2-board-wrap"><canvas id="v2-go-board" aria-label="SGF 圍棋題目棋盤"></canvas></div><div class="v2-board-caption"><span><b class="v2-answer">A</b>目前正解</span><span><b class="v2-candidate">●</b>待確認候選</span><span><b class="v2-picked">＋</b>你選的落點</span></div></section>
            <aside class="v2-card v2-control"><div class="v2-progress"><span id="v2-reviewed-label">第 1 題</span><span id="v2-pending-label">待確認</span></div><div class="v2-progress-bar"><span id="v2-progress-fill" style="width:0%"></span></div><p id="v2-prompt" class="v2-prompt">這題目前的正解是否正確？</p><div id="v2-decision-grid" class="v2-decision-grid"><button id="v2-correct" class="v2-decision good">正解正確<small>確認目前答案沒有問題</small></button><button id="v2-alternative" class="v2-decision alt">還有其他正解<small>直接在棋盤上點另一個答案</small></button><button id="v2-wrong" class="v2-decision wrong">正解錯誤<small>直接點選你認為正確的位置</small></button><button id="v2-defer" class="v2-decision defer">看不出來／稍後處理<small>先保留，之後再回來</small></button></div><button id="v2-broken-toggle" class="v2-secondary-action">⚠ 題目本身有問題</button><div id="v2-broken-panel" class="v2-broken-panel" hidden><div class="v2-broken-grid"><button data-broken="SIDE_TO_MOVE">黑白先標示錯誤</button><button data-broken="BOARD_OR_SGF">棋譜／局面有問題</button><button data-broken="REBUILD">題目需要重建</button><button data-broken="OTHER">其他問題</button></div></div><div id="v2-proposal-confirm" class="v2-proposal" hidden><h3>確認你的修改</h3><div class="v2-proposal-compare"><div><span>目前正解</span><strong id="v2-current-point">—</strong></div><div><span id="v2-proposed-label">新增正解</span><strong id="v2-proposed-point">—</strong></div></div><div class="v2-proposal-actions"><button id="v2-confirm-proposal" class="v2-primary">確認修改</button><button id="v2-cancel-proposal" class="v2-quiet">重新選擇</button></div></div><div id="v2-staged-result" class="v2-result" hidden><h3>修改已暫存</h3><p>尚未發布，不會影響目前玩家作答。</p><div id="v2-verdict-compare" class="v2-verdict" hidden><div><span>目前線上判定</span><strong id="v2-production-verdict">—</strong></div><div><span>修改後判定</span><strong id="v2-staged-verdict">—</strong></div></div><div class="v2-result-actions"><button id="v2-retest" class="v2-secondary">用修改後答案重測</button><button id="v2-next" class="v2-primary">下一題</button><button id="v2-back-review" class="v2-quiet">返回</button></div></div><details id="v2-details" class="v2-detail-card"><summary>詳細資料</summary><div id="v2-detail-grid" class="v2-detail-grid"></div></details></aside></div>
        </section>
        <section id="v2-pending-view" class="v2-view" hidden><div class="v2-pending-head"><div><button id="v2-pending-home" class="v2-link">← 回到審題首頁</button><h2>待套用修改</h2><p>這裡集中查看已暫存的修改，再交給既有修正流程。</p></div><button id="v2-create-batch" class="v2-primary">準備批次交接</button></div><div id="v2-pending-list" class="v2-pending-list"></div><div id="v2-handoff-note" class="v2-handoff" hidden></div></section>
      </main><div id="v2-toast" class="v2-toast" role="status" aria-live="polite"></div>`;
    document.body.appendChild(root);
    augmentDirectMarkup(root);
  }

  function augmentDirectMarkup(root) {
    const control = root.querySelector('.v2-control');
    if (!control) return;
    const boardStyle = document.createElement('style');
    boardStyle.textContent = '.v2-board-tools{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px}.v2-board-tools button{border:1px solid #587c66;border-radius:12px;background:#152b20;color:#dff4e3;padding:9px 8px;font-weight:850;cursor:pointer}.v2-board-tools button.active{background:#397a53;border-color:#8de4ad;color:#fff}.v2-board-edit-note{margin:8px 0 0;color:#b9d9bf;font-size:12px;line-height:1.5}';
    document.head.appendChild(boardStyle);
    const note = document.createElement('div');
    note.id = 'v2-direct-note';
    note.className = 'v2-selection-banner';
    note.hidden = true;
    note.textContent = '管理員直接修正：套用前會自動保留上一版，失敗會保留原題。';
    control.querySelector('#v2-prompt')?.after(note);
    const shortcut = document.createElement('button');
    shortcut.id = 'v2-direct-shortcut';
    shortcut.className = 'v2-primary';
    shortcut.hidden = true;
    shortcut.textContent = '把剛才這一手加入正解';
    control.querySelector('#v2-decision-grid')?.after(shortcut);
    shortcut.addEventListener('click', () => {
      if (!state.current?.candidate_move) return;
      state.mode = 'ADD_ALTERNATIVE_CORRECT_MOVE';
      state.selectedMove = state.current.candidate_move;
      state.proposal = state.current.candidate_move;
      renderReview();
    });
    const advanced = document.createElement('div');
    advanced.className = 'v2-broken-grid';
    advanced.dataset.directAdvanced = 'true';
    advanced.hidden = true;
    [
      ['REMOVE_INCORRECT_ACCEPTED_MOVE', '移除錯誤答案／分支'],
      ['EDIT_BOARD_SETUP', '修正題目棋盤'],
      ['CHANGE_SIDE_TO_PLAY', '修正黑先／白先'],
    ].forEach(([action, label]) => {
      const button = document.createElement('button');
      button.type = 'button'; button.dataset.directAction = action; button.textContent = label;
      button.addEventListener('click', () => beginDirectAction(action));
      advanced.appendChild(button);
    });
    control.querySelector('#v2-broken-panel')?.appendChild(advanced);
    const boardTools = document.createElement('div');
    boardTools.id = 'v2-board-tools';
    boardTools.hidden = true;
    boardTools.innerHTML = '<div class="v2-board-tools"><button type="button" data-board-tool="B">放黑子</button><button type="button" data-board-tool="W">放白子</button><button type="button" data-board-tool="REMOVE">移除棋子</button></div><p class="v2-board-edit-note">選擇工具後直接在棋盤點擊；套用前會顯示棋盤前後差異。</p>';
    control.querySelector('#v2-broken-panel')?.appendChild(boardTools);
    boardTools.querySelectorAll('[data-board-tool]').forEach((button) => button.addEventListener('click', () => {
      state.boardEditTool = button.dataset.boardTool;
      boardTools.querySelectorAll('[data-board-tool]').forEach((candidate) => candidate.classList.toggle('active', candidate === button));
      toast(state.boardEditTool === 'REMOVE' ? '請在棋盤點擊要移除的棋子' : `請在棋盤點擊要放置的${state.boardEditTool === 'B' ? '黑子' : '白子'}`);
    }));
    const result = control.querySelector('#v2-staged-result');
    if (result) {
      const title = result.querySelector('h3');
      if (title) { title.id = 'v2-result-title'; }
      const copy = result.querySelector('p');
      if (copy) { copy.id = 'v2-result-copy'; }
      const rollback = document.createElement('button');
      rollback.id = 'v2-rollback'; rollback.className = 'v2-warn'; rollback.hidden = true;
      rollback.textContent = '還原上一版';
      result.querySelector('.v2-result-actions')?.insertBefore(rollback, result.querySelector('#v2-next'));
      rollback.addEventListener('click', rollbackDirect);
    }
  }

  function normalizeQuestion(payload) {
    return payload && payload.id ? payload : { accepted_moves: [], content: "" };
  }

  async function loadData() {
    const payload = await jsonFetch(`${API}/bootstrap`);
    const security = payload.security || {};
    state.csrfHeader = security.csrf_header || "";
    state.csrfToken = security.csrf_token || "";
    state.items = Array.isArray(payload.items) ? payload.items : [];
    await Promise.all(state.items.map(async (item) => {
      try {
        if ((item.source_types || []).includes("ADMIN_PLAY")) {
          const context = await jsonFetch(`${API}/direct-context/${encodeURIComponent(item.question_id)}?record_index=${encodeURIComponent(item.record_index ?? "")}`);
          item._direct = context;
          state.questions.set(item.question_id, normalizeQuestion(context.record));
        } else {
          state.questions.set(item.question_id, normalizeQuestion(await jsonFetch(`/api/question/${encodeURIComponent(item.question_id)}`)));
        }
      } catch (_) { state.questions.set(item.question_id, { accepted_moves: item.authority && item.authority.accepted_moves || [], content: "" }); }
    }));
    renderHome(payload);
  }

  function renderHome(payload) {
    const pending = visibleItems().length;
    const player = state.items.filter((item) => (item.source_types || []).includes("PLAYER_REPORT")).length;
    const system = state.items.filter((item) => (item.source_types || []).some((source) => source !== "PLAYER_REPORT")).length;
    const deferred = state.items.filter((item) => item.status === "NEEDS_RESEARCH").length;
    el("v2-count-pending").textContent = String(pending);
    el("v2-count-player").textContent = String(player);
    el("v2-count-system").textContent = String(system);
    el("v2-count-deferred").textContent = String(deferred);
    el("v2-pending-count").textContent = String(stagedItems().length);
    el("v2-home-details-body").textContent = `來源：玩家回報 ${player} · 系統/掃描 ${system}\n總項目：${state.items.length}\n伺服器暫存：${payload.staged_count || stagedItems().length}\nProduction 變更：${payload.production_mutation ? "不允許" : "未發生"}\nCanonical SGF 變更：${payload.canonical_mutation ? "不允許" : "未發生"}`;
  }

  function sourceLabel(item) {
    return (item.source_types || []).map((source) => SOURCE_LABELS[source] || source).join("、") || "待確認來源";
  }

  function acceptedMoves(item) {
    const question = state.questions.get(item.question_id) || {};
    return (item.authority && item.authority.accepted_moves) || question.accepted_moves || [];
  }

  function currentMove(item) {
    return acceptedMoves(item)[0] || null;
  }

  function parseStones(sgf) {
    const stones = [];
    const source = String(sgf || "");
    ["AB", "AW"].forEach((color) => {
      const pattern = new RegExp(`${color}((?:\\[[a-s]{2}\\])+?)`, "i");
      const group = source.match(pattern);
      if (!group) return;
      (group[1].match(/\[([a-s]{2})\]/gi) || []).forEach((token) => {
        const move = moveFromSgf(token.slice(1, 3));
        if (move) stones.push({ ...move, color: color === "AB" ? "B" : "W" });
      });
    });
    return stones;
  }

  function setupSgf(stones) {
    const grouped = { B: [], W: [] };
    (stones || []).forEach((stone) => {
      const coord = String.fromCharCode(97 + Number(stone.x)) + String.fromCharCode(97 + Number(stone.y));
      if (grouped[stone.color] && !grouped[stone.color].includes(coord)) grouped[stone.color].push(coord);
    });
    return Object.entries(grouped).filter(([, coords]) => coords.length)
      .map(([color, coords]) => `${color === 'B' ? 'AB' : 'AW'}${coords.sort().map((coord) => `[${coord}]`).join('')}`).join('');
  }

  function withSetupSgf(content, stones) {
    const source = String(content || '');
    const withoutSetup = source.replace(/A[BW](?:\[[a-s]{2}\])+/gi, '');
    const properties = setupSgf(stones);
    if (!properties) return withoutSetup;
    return withoutSetup.replace(/^(\s*\(\s*;)/, `$1${properties}`);
  }

  function boardEditSummary(stones) {
    const black = (stones || []).filter((stone) => stone.color === 'B').length;
    const white = (stones || []).filter((stone) => stone.color === 'W').length;
    return `黑子 ${black} 顆 · 白子 ${white} 顆`;
  }

  function drawBoard() {
    const canvas = el("v2-go-board");
    const wrap = el("v2-board-wrap");
    if (!canvas || !wrap || !state.current) return;
    const size = Math.max(240, Math.floor(wrap.clientWidth));
    const ratio = window.devicePixelRatio || 1;
    canvas.width = size * ratio; canvas.height = size * ratio;
    const ctx = canvas.getContext("2d"); ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, size, size);
    const pad = size * 0.055; const cell = (size - pad * 2) / 18;
    ctx.fillStyle = "#d5a85c"; ctx.fillRect(0, 0, size, size);
    ctx.strokeStyle = "rgba(65,42,14,.68)"; ctx.lineWidth = 1;
    for (let i = 0; i < 19; i += 1) { const p = pad + cell * i; ctx.beginPath(); ctx.moveTo(pad, p); ctx.lineTo(size - pad, p); ctx.stroke(); ctx.beginPath(); ctx.moveTo(p, pad); ctx.lineTo(p, size - pad); ctx.stroke(); }
    ctx.fillStyle = "rgba(65,42,14,.74)";
    [3, 9, 15].forEach((x) => [3, 9, 15].forEach((y) => { ctx.beginPath(); ctx.arc(pad + cell * x, pad + cell * y, Math.max(3, cell * .095), 0, Math.PI * 2); ctx.fill(); }));
    const q = state.questions.get(state.current.question_id) || {};
    const boardStones = state.mode === 'EDIT_BOARD_SETUP' ? state.boardEditStones : parseStones(q.content);
    boardStones.forEach((stone) => {
      const px = pad + cell * stone.x, py = pad + cell * stone.y, radius = cell * .44;
      ctx.beginPath(); ctx.arc(px, py, radius, 0, Math.PI * 2); ctx.fillStyle = stone.color === "B" ? "#17231d" : "#faf7ec"; ctx.fill(); ctx.strokeStyle = stone.color === "B" ? "#07100b" : "#81683a"; ctx.lineWidth = 1.5; ctx.stroke();
    });
    const answers = acceptedMoves(state.current);
    answers.forEach((move) => marker(ctx, move, pad, cell, "#5bd18b", "A"));
    if (state.current.candidate_move && !answers.some((move) => sameMove(move, state.current.candidate_move))) marker(ctx, state.current.candidate_move, pad, cell, "#ff9c52", "?");
    if (state.selectedMove) marker(ctx, state.selectedMove, pad, cell, "#77bdfb", "+");
  }

  function marker(ctx, move, pad, cell, color, text) {
    if (!move) return;
    const px = pad + cell * Number(move.x), py = pad + cell * Number(move.y);
    ctx.beginPath(); ctx.arc(px, py, cell * .32, 0, Math.PI * 2); ctx.fillStyle = "rgba(255,249,231,.92)"; ctx.fill(); ctx.strokeStyle = color; ctx.lineWidth = 4; ctx.stroke();
    ctx.fillStyle = color; ctx.font = `800 ${Math.max(12, cell * .34)}px system-ui`; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(text, px, py);
  }

  function pointFromEvent(event) {
    const canvas = el("v2-go-board"); const rect = canvas.getBoundingClientRect();
    const size = rect.width; const pad = size * .055; const cell = (size - pad * 2) / 18;
    const x = Math.round((event.clientX - rect.left - pad) / cell); const y = Math.round((event.clientY - rect.top - pad) / cell);
    return x >= 0 && x < 19 && y >= 0 && y < 19 ? { x, y } : null;
  }

  function renderReview() {
    const item = state.current;
    if (!item) return show("home");
    const all = visibleItems();
    const pos = Math.max(0, all.findIndex((row) => row.id === item.id));
    el("v2-question-title").textContent = `題目 #${item.question_id}`;
    el("v2-review-progress").textContent = `第 ${pos + 1} / ${Math.max(all.length, 1)} 題 · ${ISSUE_LABELS[item.issue_type] || "待確認問題"}`;
    el("v2-reviewed-label").textContent = `${pos + 1} / ${Math.max(all.length, 1)}`;
    el("v2-pending-label").textContent = item.status === "NEEDS_RESEARCH" ? "稍後處理" : "待確認";
    el("v2-progress-fill").style.width = `${Math.round(((pos + 1) / Math.max(all.length, 1)) * 100)}%`;
    const sourceClass = (item.source_types || []).includes("PLAYER_REPORT") ? "player" : ((item.source_types || []).includes("CORPUS_SCAN") ? "scan" : "admin");
    el("v2-board-meta").innerHTML = `<span class="v2-chip ${sourceClass}">${esc(sourceLabel(item))}</span><span class="v2-chip">${esc(ISSUE_LABELS[item.issue_type] || item.issue_type || "待確認")}</span><span class="v2-chip">${Number(item.report_count || 0)} 筆相關紀錄</span>`;
    const candidate = item.candidate_move ? `候選落點：${gtp(item.candidate_move)}` : "目前沒有候選落點";
    el("v2-prompt").textContent = state.mode === "ADD_ALTERNATIVE_CORRECT_MOVE" ? "請直接在棋盤上點選另一個也成立的正解。" : state.mode === "REPLACE_ANSWER" ? "請在棋盤上點選你認為正確的答案。" : state.mode === "EDIT_BOARD_SETUP" ? "請選擇放子或移除工具，再直接在棋盤上編輯題目局面。" : `${ISSUE_LABELS[item.issue_type] || "這題需要你的判斷"}。${candidate}`;
    const directNote = el("v2-direct-note");
    if (directNote) directNote.hidden = !state.directMode;
    const shortcut = el("v2-direct-shortcut");
    if (shortcut) shortcut.hidden = !(state.directMode && item.candidate_move && !acceptedMoves(item).some((move) => sameMove(move, item.candidate_move)) && !state.stagedResult);
    const advanced = document.querySelector('[data-direct-advanced="true"]');
    if (advanced) advanced.hidden = !state.directMode;
    const boardTools = el('v2-board-tools');
    if (boardTools) boardTools.hidden = !(state.directMode && state.mode === 'EDIT_BOARD_SETUP');
    const details = item.provenance || {};
    el("v2-detail-grid").innerHTML = [["來源", sourceLabel(item)], ["報告數", `${item.report_count || 0} 筆`], ["候選落點", item.candidate_move ? gtp(item.candidate_move) : "—"], ["目前正解", acceptedMoves(item).map(gtp).join("、") || "—"], ["第一筆紀錄", item.first_report_at || "—"], ["最後更新", item.updated_at || "—"], ["位置識別", item.position_identity || "—"], ["證據來源", details.fixture_path || details.source || "已保留於伺服器"]].map(([label, value]) => `<div><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join("");
    const banner = el("v2-selection-banner");
    banner.hidden = !state.mode;
    if (state.mode) {
      const title = state.mode === "ADD_ALTERNATIVE_CORRECT_MOVE" ? "選另一個正解" : state.mode === "REPLACE_ANSWER" ? "選新的正確答案" : state.mode === "EDIT_BOARD_SETUP" ? "編輯題目棋盤" : "確認先手修改";
      const instruction = state.mode === "ADD_ALTERNATIVE_CORRECT_MOVE" ? "請直接在棋盤上點選另一個也成立的正解。" : state.mode === "REPLACE_ANSWER" ? "請在棋盤上點選你認為正確的答案。" : state.mode === "EDIT_BOARD_SETUP" ? "請使用放子或移除工具修改題目局面。" : "確認後會先驗證，再保存上一版本。";
      banner.innerHTML = `<strong>${title}</strong>${instruction}`;
    }
    el("v2-proposal-confirm").hidden = !state.proposal;
    const confirmButton = el("v2-confirm-proposal");
    if (confirmButton) confirmButton.textContent = state.directMode ? "儲存並套用" : "暫存這項修改";
    if (state.proposal) {
      if (state.mode === 'EDIT_BOARD_SETUP') {
        el('v2-current-point').textContent = boardEditSummary(parseStones(state.directContext?.record?.content || ''));
        el('v2-proposed-point').textContent = boardEditSummary(state.boardEditStones);
        el('v2-proposed-label').textContent = '修改後棋盤';
      } else if (state.mode === 'CHANGE_SIDE_TO_PLAY') {
        el('v2-current-point').textContent = '目前先手';
        el('v2-proposed-point').textContent = state.directSide === 'W' ? '白先' : '黑先';
        el('v2-proposed-label').textContent = '修改為';
      } else {
        el("v2-current-point").textContent = gtp(currentMove(item));
        el("v2-proposed-point").textContent = gtp(state.proposal);
        el("v2-proposed-label").textContent = state.mode === "ADD_ALTERNATIVE_CORRECT_MOVE" ? "新增正解" : "修改為";
      }
    }
    el("v2-broken-panel").hidden = !state.brokenOpen;
    el("v2-staged-result").hidden = !state.stagedResult;
    const resultTitle = el("v2-result-title");
    const resultCopy = el("v2-result-copy");
    if (resultTitle) resultTitle.textContent = state.directMode && state.directVersion ? "修改已套用" : "修改已暫存";
    if (resultCopy) resultCopy.textContent = state.directMode && state.directVersion ? "已保存上一版本，可還原；目前玩家仍只會看到這個接受環境的版本。" : "尚未發布，不會影響目前玩家作答。";
    const rollback = el("v2-rollback");
    if (rollback) rollback.hidden = !(state.directMode && state.directVersion);
    const retestButton = el("v2-retest");
    if (retestButton) retestButton.textContent = state.directMode ? "重新測試本題" : "用修改後答案重測";
    el("v2-details").open = false;
    drawBoard();
  }

  function show(view) {
    el("v2-home").hidden = view !== "home";
    el("v2-review").hidden = view !== "review";
    el("v2-pending-view").hidden = view !== "pending";
  }

  async function openNext() {
    state.items = (await jsonFetch(`${API}/items`)).items || state.items;
    await Promise.all(state.items.filter((item) => (item.source_types || []).includes("ADMIN_PLAY")).map(async (item) => {
      try {
        const context = await jsonFetch(`${API}/direct-context/${encodeURIComponent(item.question_id)}?record_index=${encodeURIComponent(item.record_index ?? "")}`);
        item._direct = context;
        state.questions.set(item.question_id, normalizeQuestion(context.record));
      } catch (_) { /* Review Queue remains usable even when direct mode is gated. */ }
    }));
    const all = visibleItems();
    if (!all.length) { state.current = null; show("home"); renderHome({ staged_count: stagedItems().length }); toast("目前沒有待確認題目"); return; }
    state.currentIndex = Math.min(state.currentIndex, all.length - 1);
    state.current = all[state.currentIndex];
    state.directMode = (state.current.source_types || []).includes("ADMIN_PLAY") && !!state.current._direct;
    state.directContext = state.current._direct || null;
    state.directVersion = null;
    state.directHistory = state.directContext?.history || [];
    state.directSide = null;
    state.boardEditTool = null;
    state.boardEditStones = [];
    state.directContent = '';
    state.mode = null; state.selectedMove = null; state.proposal = null; state.stagedResult = false; state.brokenOpen = false;
    show("review"); renderReview();
  }

  function newOperationId(prefix) {
    const uuid = window.crypto && typeof window.crypto.randomUUID === "function" ? window.crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    return `${prefix || "direct"}:${uuid}`;
  }

  async function beginDirectAction(action) {
    if (!state.directMode || !state.current) return;
    state.brokenOpen = false;
    if (action === "CHANGE_SIDE_TO_PLAY") {
      const currentContent = state.directContext?.record?.content || '';
      const currentSide = (currentContent.match(/(?:^|;)PL\[([BW])\]/i) || [])[1]?.toUpperCase() || 'B';
      state.directSide = currentSide === 'B' ? 'W' : 'B';
      state.mode = action; state.proposal = { side_to_play: state.directSide }; renderReview(); return;
    }
    if (action === "EDIT_BOARD_SETUP") {
      const current = state.directContext?.record?.content || state.questions.get(state.current.question_id)?.content || "";
      state.directContent = current;
      state.boardEditStones = parseStones(current);
      state.boardEditTool = 'B';
      state.brokenOpen = true;
      state.mode = action; state.proposal = { content: current }; renderReview(); return;
    }
    state.mode = action; state.proposal = null; state.selectedMove = null; renderReview();
  }

  async function applyDirect(action, move) {
    if (!state.current || !state.directMode || state.busy) return;
    state.busy = true;
    try {
      const context = state.directContext || (await jsonFetch(`${API}/direct-context/${encodeURIComponent(state.current.question_id)}?record_index=${encodeURIComponent(state.current.record_index ?? "")}`));
      state.directContext = context;
      const body = {
        question_id: state.current.question_id,
        record_index: context.record_index,
        predecessor_hash: context.predecessor_hash,
        action,
        candidate_move: move || state.selectedMove || state.current.candidate_move || undefined,
        operation_id: newOperationId("admin-play-direct"),
      };
      if (action === "EDIT_BOARD_SETUP") body.proposed_content = state.directContent;
      if (action === "CHANGE_SIDE_TO_PLAY") body.side_to_play = state.directSide;
      const result = await postJson(`${API}/direct-apply`, body);
      state.directVersion = result.version;
      if (result.version?.new_record) {
        state.questions.set(state.current.question_id, result.version.new_record);
        if (state.directContext) state.directContext.record = result.version.new_record;
      }
      state.directHistory = [result.version, ...(state.directHistory || [])];
      state.stagedResult = true; state.mode = null; state.proposal = null; state.selectedMove = move || state.selectedMove;
      renderReview(); toast(result.duplicate ? "這項修改已經套用過" : "修改已套用，上一版已保存");
    } catch (error) { toast(error.message, true); } finally { state.busy = false; }
  }

  async function rollbackDirect() {
    if (!state.directVersion || state.busy) return;
    if (!window.confirm("確認還原上一版？系統會建立新的版本，不會刪除修改紀錄。")) return;
    state.busy = true;
    try {
      const result = await postJson(`${API}/direct-versions/${encodeURIComponent(state.directVersion.id)}/rollback`, { operation_id: newOperationId("admin-play-rollback") });
      state.directVersion = result.version; state.directHistory = [result.version, ...(state.directHistory || [])];
      state.stagedResult = true; renderReview(); toast("已還原上一版");
    } catch (error) { toast(error.message, true); } finally { state.busy = false; }
  }

  async function stage(action, move, reason) {
    if (!state.current || state.busy) return;
    if (state.directMode && action !== "NEEDS_RESEARCH") return applyDirect(action, move);
    state.busy = true;
    try {
      const payload = { action, reason: reason || "OWNER_UX_V2_REVIEW", candidate_move: move || undefined };
      const result = await postJson(`${API}/items/${state.current.id}/stage`, payload);
      state.current.status = result.staged ? "STAGED" : (result.status || "NEEDS_RESEARCH");
      state.current.staged_repairs = result.repair ? [result.repair] : [];
      state.stagedResult = !!result.staged;
      state.mode = null; state.proposal = null; state.selectedMove = move || null; state.brokenOpen = false;
      renderReview();
      el("v2-pending-count").textContent = String(stagedItems().length + (result.staged ? 0 : 0));
      toast(result.staged ? "修改已暫存，尚未發布" : "已放入稍後處理");
    } catch (error) { toast(error.message, true); } finally { state.busy = false; }
  }

  async function confirmCorrect() {
    if (!state.current || state.busy) return;
    state.busy = true;
    try {
      await postJson(`${API}/items/${state.current.id}/status`, { status: "REJECTED", note: "OWNER_CONFIRMED_CORRECT" });
      state.current.status = "REJECTED"; toast("已確認目前正解，沒有建立修改"); await openNext();
    } catch (error) { toast(error.message, true); } finally { state.busy = false; }
  }

  async function retest() {
    if (!state.current || state.busy) return;
    if (state.directMode && state.directVersion) {
      state.busy = true;
      try {
        const moves = [state.selectedMove || state.current.candidate_move || currentMove(state.current)].filter(Boolean);
        const result = await postJson(`${API}/direct-retest`, { question_id: state.current.question_id, record_index: state.current.record_index ?? state.directContext?.record_index, moves });
        el("v2-verdict-compare").hidden = false; el("v2-production-verdict").textContent = result.canonical_verdict || "未定"; el("v2-staged-verdict").textContent = result.applied_verdict || "未定"; toast("已重新測試目前已套用版本");
      } catch (error) { toast(error.message, true); } finally { state.busy = false; }
      return;
    }
    if (!state.current.staged_repairs?.length) return toast("請先暫存一個修改", true);
    state.busy = true;
    try {
      const moves = [state.selectedMove || state.current.candidate_move || currentMove(state.current)].filter(Boolean);
      const result = await postJson(`${API}/items/${state.current.id}/retest`, { moves });
      el("v2-verdict-compare").hidden = false; el("v2-production-verdict").textContent = result.production_verdict || "未定"; el("v2-staged-verdict").textContent = result.staged_verdict || "未定"; toast("已完成僅限管理員的重測");
    } catch (error) { toast(error.message, true); } finally { state.busy = false; }
  }

  async function showPending() {
    const payload = await jsonFetch(`${API}/items`); state.items = payload.items || state.items;
    const list = stagedItems();
    const enriched = await Promise.all(list.map(async (item) => {
      try { return (await jsonFetch(`${API}/items/${item.id}`)).item || item; } catch (_) { return item; }
    }));
    enriched.forEach((item) => { const index = state.items.findIndex((row) => row.id === item.id); if (index >= 0) state.items[index] = item; });
    const node = el("v2-pending-list");
    node.innerHTML = enriched.length ? enriched.map((item) => { const repair = (item.staged_repairs || [])[0] || {}; const action = repair.action || "已暫存修改"; return `<article class="v2-card v2-pending-card"><div><h3>題目 #${esc(item.question_id)}</h3><p>${esc(ACTION_LABELS[action] || action)} · ${esc(sourceLabel(item))}</p><span class="v2-chip">尚未發布，不會影響玩家</span></div><button class="v2-secondary" data-open-staged="${esc(item.id)}">查看題目</button></article>`; }).join("") : `<div class="v2-card v2-empty"><h3>目前沒有待套用修改</h3><p>審題時確認的修改會自動出現在這裡。</p></div>`;
    el("v2-handoff-note").hidden = true; show("pending");
  }

  async function createBatch() {
    if (!stagedItems().length) return toast("目前沒有可交接的暫存修改", true);
    try { const result = await postJson(`${API}/batches`, {}); el("v2-handoff-note").hidden = false; el("v2-handoff-note").innerHTML = `<strong>批次已準備好</strong><br>這只建立既有修正流程的 handoff 證據，沒有發布內容，也沒有修改 Production。批次識別：${esc(result.batch?.batch_key || result.batch?.manifest_sha256 || "已建立")}`; toast("已準備批次交接"); } catch (error) { toast(error.message, true); }
  }

  function bind() {
    el("v2-start").addEventListener("click", () => { state.currentIndex = 0; openNext().catch((error) => toast(error.message, true)); });
    el("v2-resume").addEventListener("click", () => openNext().catch((error) => toast(error.message, true)));
    el("v2-pending").addEventListener("click", () => showPending().catch((error) => toast(error.message, true)));
    el("v2-home-details-toggle").addEventListener("click", () => { el("v2-home-details").open = true; });
    el("v2-done").addEventListener("click", () => toast("已處理題目會保留在詳細資料與伺服器紀錄中"));
    el("v2-review-pending").addEventListener("click", () => showPending().catch((error) => toast(error.message, true)));
    el("v2-review-home").addEventListener("click", () => { show("home"); renderHome({ staged_count: stagedItems().length }); });
    el("v2-pending-home").addEventListener("click", () => { show("home"); renderHome({ staged_count: stagedItems().length }); });
    el("v2-correct").addEventListener("click", confirmCorrect);
    el("v2-alternative").addEventListener("click", () => { state.mode = "ADD_ALTERNATIVE_CORRECT_MOVE"; state.proposal = null; state.brokenOpen = false; el("v2-board-wrap").classList.add("selecting"); renderReview(); });
    el("v2-wrong").addEventListener("click", () => { state.mode = "REPLACE_ANSWER"; state.proposal = null; state.brokenOpen = false; el("v2-board-wrap").classList.add("selecting"); renderReview(); });
    el("v2-defer").addEventListener("click", () => stage("NEEDS_RESEARCH", null, "OWNER_DEFERRED"));
    el("v2-broken-toggle").addEventListener("click", () => { state.brokenOpen = !state.brokenOpen; renderReview(); });
    document.querySelectorAll("[data-broken]").forEach((button) => button.addEventListener("click", () => { const kind = button.dataset.broken; if (state.directMode && kind === "SIDE_TO_MOVE") return beginDirectAction("CHANGE_SIDE_TO_PLAY"); if (state.directMode && kind === "BOARD_OR_SGF") return beginDirectAction("EDIT_BOARD_SETUP"); stage(kind === "REBUILD" || kind === "BOARD_OR_SGF" ? "DISABLE_BROKEN_QUESTION" : "NEEDS_RESEARCH", null, `OWNER_BROKEN_${kind}`); }));
    el("v2-confirm-proposal").addEventListener("click", () => state.directMode ? applyDirect(state.mode, state.proposal?.x ? state.proposal : state.selectedMove) : stage(state.mode, state.proposal, "OWNER_BOARD_DECISION"));
    el("v2-cancel-proposal").addEventListener("click", () => { state.proposal = null; state.selectedMove = null; renderReview(); });
    el("v2-retest").addEventListener("click", retest);
    el("v2-next").addEventListener("click", () => { state.currentIndex += 1; openNext().catch((error) => toast(error.message, true)); });
    el("v2-back-review").addEventListener("click", () => { state.stagedResult = false; state.mode = null; renderReview(); });
    el("v2-create-batch").addEventListener("click", createBatch);
    el("v2-go-board").addEventListener("pointerup", (event) => {
      if (!state.mode || !state.current) return;
      const move = pointFromEvent(event); if (!move) return;
      if (state.mode === 'EDIT_BOARD_SETUP') {
        const existing = state.boardEditStones.findIndex((stone) => sameMove(stone, move));
        if (state.boardEditTool === 'REMOVE') {
          if (existing >= 0) state.boardEditStones.splice(existing, 1);
        } else {
          if (existing >= 0) state.boardEditStones.splice(existing, 1);
          state.boardEditStones.push({ ...move, color: state.boardEditTool || 'B' });
        }
        state.directContent = withSetupSgf(state.directContext?.record?.content || '', state.boardEditStones);
        state.proposal = { content: state.directContent };
        renderReview(); return;
      }
      state.selectedMove = move; state.proposal = move; renderReview();
    });
    window.addEventListener("resize", () => { if (!el("v2-review").hidden) drawBoard(); });
    el("v2-pending-list").addEventListener("click", (event) => { const button = event.target.closest("[data-open-staged]"); if (!button) return; const item = state.items.find((row) => String(row.id) === String(button.dataset.openStaged)); if (!item) return; state.current = item; state.mode = null; state.selectedMove = item.candidate_move || currentMove(item); state.stagedResult = true; state.proposal = null; state.brokenOpen = false; show("review"); renderReview(); });
  }

  async function boot() {
    injectMarkup();
    bind();
    try {
      await loadData();
      const directId = Number(new URLSearchParams(window.location.search).get("direct_question_id"));
      if (Number.isInteger(directId) && directId > 0) {
        const index = visibleItems().findIndex((item) => Number(item.question_id) === directId);
        if (index >= 0) { state.currentIndex = index; await openNext(); return; }
      }
      show("home");
    } catch (error) { el("v2-home-details-body").textContent = `工作台載入失敗：${error.message}`; toast("工作台暫時無法載入", true); }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true }); else boot();
})();
