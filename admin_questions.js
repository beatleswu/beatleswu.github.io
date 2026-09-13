(() => {
  "use strict";

  const SECTION_META = {
    pending: { label: "待處理", icon: "📥", description: "統一收件匣：來自玩家回報、系統偵測與人工標記的未處理項目。" },
    reports: { label: "玩家回報", icon: "💬", description: "玩家提交的問題或另解回報，原因會用清楚的文字顯示。" },
    duplicates: { label: "重複題", icon: "🧩", description: "相同題面群組；確認是否重複、或選擇要保留的版本。" },
    browse: { label: "題庫瀏覽", icon: "🔎", description: "搜尋和瀏覽目前題庫；選到題目後可直接檢查，不代表有問題。" },
    modified: { label: "已修改", icon: "✅", description: "查看最近已儲存或已處理的修正版。" },
    history: { label: "歷史紀錄", icon: "🕘", description: "查看修改紀錄與驗證結果。" },
  };
  const WORK_SECTIONS = new Set(["pending", "reports", "duplicates"]);

  const state = {
    payload: null,
    section: "pending",
    selected: null,
    context: null,
    marker: null,
    csrf: null,
  };

  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value == null ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

  async function jsonFetch(url, options) {
    const response = await fetch(url, Object.assign({ credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } }, options || {}));
    const body = await response.json().catch(() => ({}));
    if (!response.ok || body.ok === false) throw new Error(body.error || `HTTP ${response.status}`);
    return body;
  }

  async function getCsrf() {
    if (state.csrf) return state.csrf;
    const boot = await jsonFetch("/api/admin/sgf-workbench/bootstrap");
    state.csrf = boot.security || null;
    return state.csrf;
  }

  function currentItems() { return (state.payload?.sections?.[state.section] || []); }

  function itemText(item) {
    const q = item.identity?.question || {};
    return [q.question_id, q.topic, q.level, item.reason, item.note, item.source].join(" ").toLowerCase();
  }

  function filteredItems() {
    const query = String($("center-search")?.value || "").trim().toLowerCase();
    return query ? currentItems().filter((item) => itemText(item).includes(query)) : currentItems();
  }

  // ---------- source / status classification (UI-only; compatible with a future CORPUS_SCAN intake) ----------
  function classifySource(item) {
    const tech = item.technical || {};
    const types = Array.isArray(tech.source_types) ? tech.source_types : [];
    if (types.includes("CORPUS_SCAN")) return { key: "system", label: "系統偵測" };
    if (types.includes("PLAYER_REPORT")) return { key: "player", label: "玩家回報" };
    if (types.includes("ADMIN_PLAY")) return { key: "manual", label: "人工標記" };
    if (tech.report_type) return { key: "player", label: "玩家回報" };
    if (tech.system === "A") return { key: "system", label: "系統偵測" };
    const st = tech.source_type;
    if (st === "player_reported") return { key: "player", label: "玩家回報" };
    if (st === "manual_flag") return { key: "manual", label: "人工標記" };
    if (st) return { key: "system", label: "系統偵測" };
    return null;
  }

  function isDuplicateKind(item) {
    const tech = item.technical || {};
    return tech.source_type === "duplicate_group" || tech.system === "A";
  }

  function statusTone(status) {
    const s = String(status || "");
    if (/已套用|已修改|已確認|可安全查看|已納入候選/.test(s)) return "ok";
    if (/待確認|稍後處理|需要確認|可查看/.test(s)) return "warn";
    if (/無法安全修改|需要重新確認|AMBIGUOUS/.test(s)) return "danger";
    return "";
  }

  // ---------- rail: tabs + list ----------
  function renderTabs() {
    const host = $("rail-tabs");
    host.innerHTML = Object.entries(SECTION_META).map(([key, meta]) => {
      const count = state.payload?.counts?.[key] || 0;
      const active = key === state.section;
      const hasItems = count > 0 && WORK_SECTIONS.has(key);
      return `<button type="button" class="tab-btn${active ? " active" : ""}${hasItems ? " has-items" : ""}" data-section="${key}" role="tab" aria-selected="${active}">` +
        `<span aria-hidden="true">${meta.icon}</span><span>${meta.label}</span><span class="tab-count">${count}</span></button>`;
    }).join("");
  }

  function cardMarkup(item, index) {
    const identity = item.identity || {};
    const q = identity.question || {};
    const exact = identity.status === "EXACT";
    const source = classifySource(item);
    const title = exact ? `題目 #${esc(identity.question_id)}` : "身份需要重新確認";
    const reason = item.reason && item.reason !== "其他" ? item.reason : (item.note || item.reason || "");
    const typeChip = q.topic ? `<span class="badge badge-plain">${esc(q.topic)}</span>` : "";
    const levelChip = q.level ? `<span class="badge badge-plain">${esc(q.level)}</span>` : "";
    const statusChip = item.status ? `<span class="badge badge-status ${statusTone(item.status)}">${esc(item.status)}</span>` : "";
    const sourceChip = source ? `<span class="badge badge-source ${source.key}">${esc(source.label)}</span>` : "";
    const selected = state.selected === item;
    return `<button type="button" class="item-card${selected ? " selected" : ""}" data-open-index="${index}" role="tab" aria-selected="${selected}">` +
      `<div class="row1">${sourceChip}<h3>${title}</h3></div>` +
      `<p class="reason-line">${esc(reason) || "目前沒有更多摘要"}</p>` +
      `<div class="row2">${typeChip}${levelChip}${statusChip}</div>` +
      `</button>`;
  }

  function renderList() {
    const meta = SECTION_META[state.section];
    const items = filteredItems();
    $("rail-meta").textContent = `${meta.label} · ${items.length} 筆`;
    const list = $("center-list");
    if (!items.length) {
      list.innerHTML = `<div class="rail-empty"><h3>目前沒有內容</h3><p>換一個分區或搜尋條件即可。</p></div>`;
      return;
    }
    list.innerHTML = items.map((item, index) => cardMarkup(item, index)).join("");
  }

  function refreshSelectedHighlight() {
    document.querySelectorAll(".item-card").forEach((node) => {
      const index = Number(node.dataset.openIndex);
      const isSelected = filteredItems()[index] === state.selected;
      node.classList.toggle("selected", isSelected);
      node.setAttribute("aria-selected", String(isSelected));
    });
  }

  // ---------- selection lifecycle ----------
  function setSelectionMode(active) {
    $("app-root").dataset.selection = active ? "true" : "false";
  }

  function showEmptyStage() {
    $("stage").innerHTML = `<div class="stage-empty"><h3>選一題開始</h3><p>棋盤、原因和快速處理會在這裡出現。</p></div>`;
  }

  function showEmptyInfo() {
    $("info-panel").innerHTML = `<div class="info-hint">選一題之後，題號、類型、正解與修改狀態會顯示在這裡。</div>`;
  }

  function backToList() {
    state.selected = null;
    state.context = null;
    state.marker = null;
    setSelectionMode(false);
    showEmptyStage();
    showEmptyInfo();
    refreshSelectedHighlight();
  }

  function nextHandler() {
    const items = filteredItems();
    const currentIndex = items.indexOf(state.selected);
    const next = items[currentIndex + 1] || items[0];
    if (next) selectItem(next); else backToList();
  }

  // ---------- board ----------
  function goCoordinate(move, size = 19) {
    if (!move || !Number.isInteger(Number(move.x)) || !Number.isInteger(Number(move.y))) return "—";
    const letters = "ABCDEFGHJKLMNOPQRST";
    return `${letters[Number(move.x)] || "?"}${size - Number(move.y)}`;
  }

  function parseStones(content) {
    const stones = [];
    const source = String(content || "");
    [["AB", "B"], ["AW", "W"]].forEach(([property, color]) => {
      const match = source.match(new RegExp(`${property}((?:\\[[a-s]{2}\\])+?)`, "i"));
      if (!match) return;
      (match[1].match(/\[([a-s]{2})\]/gi) || []).forEach((token) => {
        const value = token.slice(1, 3).toLowerCase();
        stones.push({ x: value.charCodeAt(0) - 97, y: value.charCodeAt(1) - 97, color });
      });
    });
    return stones.filter((stone) => stone.x >= 0 && stone.x < 19 && stone.y >= 0 && stone.y < 19);
  }

  function boardPoint(event) {
    const canvas = $("question-board");
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const size = rect.width;
    const pad = size * 0.055;
    const cell = (size - pad * 2) / 18;
    const x = Math.round((event.clientX - rect.left - pad) / cell);
    const y = Math.round((event.clientY - rect.top - pad) / cell);
    return x >= 0 && x < 19 && y >= 0 && y < 19 ? { x, y } : null;
  }

  function drawBoard() {
    const canvas = $("question-board");
    if (!canvas || !state.context) return;
    const width = Math.max(240, Math.floor(canvas.clientWidth || 560));
    const ratio = window.devicePixelRatio || 1;
    canvas.width = width * ratio; canvas.height = width * ratio;
    const ctx = canvas.getContext("2d"); ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    const pad = width * 0.055; const cell = (width - pad * 2) / 18;
    ctx.fillStyle = "#d8ac60"; ctx.fillRect(0, 0, width, width);
    ctx.strokeStyle = "rgba(65,42,14,.68)"; ctx.lineWidth = 1;
    for (let i = 0; i < 19; i += 1) { const p = pad + cell * i; ctx.beginPath(); ctx.moveTo(pad, p); ctx.lineTo(width - pad, p); ctx.stroke(); ctx.beginPath(); ctx.moveTo(p, pad); ctx.lineTo(p, width - pad); ctx.stroke(); }
    ctx.fillStyle = "rgba(65,42,14,.74)";
    [3, 9, 15].forEach((x) => [3, 9, 15].forEach((y) => { ctx.beginPath(); ctx.arc(pad + cell * x, pad + cell * y, Math.max(3, cell * .095), 0, Math.PI * 2); ctx.fill(); }));
    parseStones(state.context.record?.content).forEach((stone) => {
      const px = pad + cell * stone.x, py = pad + cell * stone.y;
      ctx.beginPath(); ctx.arc(px, py, cell * .44, 0, Math.PI * 2); ctx.fillStyle = stone.color === "B" ? "#17231d" : "#faf7ec"; ctx.fill(); ctx.strokeStyle = stone.color === "B" ? "#07100b" : "#81683a"; ctx.lineWidth = 1.5; ctx.stroke();
    });
    const answers = state.context.authority?.accepted_moves || [];
    answers.forEach((move) => marker(ctx, move, pad, cell, "#5bd18b", "A"));
    if (state.marker) marker(ctx, state.marker, pad, cell, "#77bdfb", "+");
  }

  function marker(ctx, move, pad, cell, color, text) {
    const px = pad + cell * Number(move.x), py = pad + cell * Number(move.y);
    ctx.beginPath(); ctx.arc(px, py, cell * .32, 0, Math.PI * 2); ctx.fillStyle = "rgba(255,249,231,.92)"; ctx.fill(); ctx.strokeStyle = color; ctx.lineWidth = 4; ctx.stroke();
    ctx.fillStyle = color; ctx.font = `800 ${Math.max(12, cell * .34)}px system-ui`; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(text, px, py);
  }

  // ---------- report resolution (玩家回報 mini actions, shown in the right panel) ----------
  async function resolveReport(item, action) {
    const tech = item.technical || {};
    if (!tech.report_id) return;
    const isAlternative = tech.report_type === "alternative";
    const path = isAlternative
      ? `/api/admin/question-alternative-reports/${encodeURIComponent(tech.report_id)}/resolve`
      : `/api/admin/question-problem-reports/${encodeURIComponent(tech.report_id)}/resolve`;
    const body = isAlternative ? { action: action === "confirmed" ? "accept" : "dismiss" } : { action };
    await jsonFetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    await load();
    backToList();
  }

  function reportActionsCard(item) {
    const type = item.technical?.report_type;
    if (!type || isDuplicateKind(item)) return "";
    return `<div class="info-card"><h4>回報處理</h4><div class="dup-btn-row">` +
      `<button type="button" class="dup-btn reject" data-report-action="confirmed">${type === "alternative" ? "納入候選" : "已確認"}</button>` +
      `<button type="button" class="dup-btn pick" data-report-action="dismissed">先不處理</button>` +
      (type === "problem" ? `<button type="button" class="dup-btn confirm" data-report-action="duplicate">重複回報</button>` : "") +
      `</div><div class="dup-status" id="report-action-status"></div></div>`;
  }

  // ---------- duplicate contextual actions (重複題 items only) ----------
  async function duplicateResolve(item, action) {
    const queueId = item.technical?.queue_id;
    if (queueId != null) {
      await jsonFetch(`/api/admin/review-queue/${encodeURIComponent(queueId)}/resolve`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action }),
      });
      return action === "confirmed_needs_repair" ? "已確認為重複，將安排處理。" : "已標記為不是重複。";
    }
    if (action !== "confirmed_needs_repair") {
      return "已在本次工作階段中略過（此筆為唯讀證據，尚未進入待處理佇列）。";
    }
    const identity = item.identity || {};
    if (identity.status !== "EXACT") throw new Error("這題目前無法安全修改");
    const security = await getCsrf();
    const headers = { "Content-Type": "application/json" };
    if (security?.csrf_header && security?.csrf_token) headers[security.csrf_header] = security.csrf_token;
    await jsonFetch("/api/admin/sgf-workbench/flag", {
      method: "POST", headers, body: JSON.stringify({
        question_id: identity.question_id, record_index: identity.record_index,
        issue_type: "QUESTION_CONTENT_PROBLEM", surface: "admin_questions",
        comment: "DUPLICATE_CONFIRMED_BY_OWNER",
        flag_id: `dup:${identity.question_id}:${identity.record_index}:${Date.now()}`,
      }),
    });
    return "已標記為需要處理，將出現在待處理與已修改中。";
  }

  function duplicateActionsMarkup(item) {
    const identity = item.identity || {};
    const advancedHref = identity.status === "EXACT"
      ? `/admin/sgf-answer-review?direct_question_id=${encodeURIComponent(identity.question_id)}&record_index=${encodeURIComponent(identity.record_index ?? "")}`
      : "";
    return `<div class="dup-actions">` +
      `<div class="title">這是相同題面群組，請先確認</div>` +
      `<div class="dup-btn-row">` +
      `<button type="button" class="dup-btn confirm" data-dup-action="confirmed_needs_repair">確認重複</button>` +
      `<button type="button" class="dup-btn reject" data-dup-action="dismissed_false_positive">不是重複</button>` +
      `</div>` +
      (advancedHref ? `<button type="button" class="dup-btn pick" data-dup-pick="${esc(advancedHref)}">選擇保留版本（開啟進階比對）</button>` : "") +
      `<div class="dup-status" id="dup-status"></div>` +
      `</div>`;
  }

  // ---------- history (right panel summary + drawer) ----------
  function historyMini(history) {
    if (!history || !history.length) return `<p class="field-row"><span class="k">尚無紀錄</span></p>`;
    return `<div class="history-mini">` + history.slice(0, 2).map((v) => {
      const when = String(v.created_at || "").slice(0, 16).replace("T", " ");
      return `<div class="entry"><b>${esc(v.action_type || "EDIT_QUESTION")}</b><span>${esc(when)}</span></div>`;
    }).join("") + `</div>`;
  }

  function openHistoryDrawer(history) {
    const body = $("drawer-body");
    if (!history || !history.length) {
      body.innerHTML = `<div class="info-hint">這題目前沒有修改紀錄。</div>`;
    } else {
      body.innerHTML = history.map((v) => {
        const when = String(v.created_at || "").slice(0, 16).replace("T", " ");
        const validation = v.validation_result?.status || (v.validation_result && v.validation_result.status) || "";
        const reverted = v.rollback_reference ? `<span class="revert-tag"> · 已復原</span>` : "";
        return `<div class="version-row"><div class="top"><span>${esc(v.action_type || "EDIT_QUESTION")}</span><span>${esc(v.status || "")}</span></div>` +
          `<div class="meta">${esc(when)} · 驗證：${esc(validation || "已記錄")}${reverted}</div></div>`;
      }).join("");
    }
    $("history-drawer").hidden = false;
  }

  function closeHistoryDrawer() { $("history-drawer").hidden = true; }

  // ---------- right panel ----------
  function renderInfoPanel(item, context) {
    const identity = item.identity || {};
    const brief = identity.question || {};
    const source = classifySource(item);
    const accepted = (context?.authority?.accepted_moves || []).map((m) => goCoordinate(m, brief.board_size || 19)).join("、") || "尚未標示";
    const history = context?.history || [];
    const panel = $("info-panel");
    panel.innerHTML = `
      <div class="info-card">
        <h4>題目資訊</h4>
        <div class="field-row"><span class="k">題號</span><span class="v">${identity.status === "EXACT" ? esc(identity.question_id) : "—"}</span></div>
        <div class="field-row"><span class="k">類型</span><span class="v">${esc(brief.topic || "未分類")}</span></div>
        <div class="field-row"><span class="k">難度</span><span class="v">${esc(brief.level || "未標示")}</span></div>
        <div class="field-row"><span class="k">目前正解</span><span class="v">${esc(accepted)}</span></div>
        <div class="field-row"><span class="k">來源</span><span class="v">${esc(source ? source.label : (item.source || "—"))}</span></div>
        <div class="field-row"><span class="k">修改狀態</span><span class="v">${esc(item.status || "—")}</span></div>
      </div>
      ${reportActionsCard(item)}
      <div class="info-card">
        <h4>最近修改</h4>
        ${historyMini(history)}
        ${history.length ? `<button type="button" class="history-more" id="open-history">查看完整歷史（${history.length}）</button>` : ""}
        ${identity.status === "EXACT" ? `<a class="advanced-link" href="/admin/sgf-answer-review?direct_question_id=${encodeURIComponent(identity.question_id)}&record_index=${encodeURIComponent(identity.record_index ?? "")}">開啟進階歷史與復原 →</a>` : ""}
      </div>
      <details class="info-card">
        <summary style="cursor:pointer;color:var(--text-faint);font-size:12px">除錯資料</summary>
        <pre style="white-space:pre-wrap;overflow-wrap:anywhere;color:#9fb6a4;font:11.5px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;margin-top:8px">${esc(JSON.stringify({ item, context: context ? { question_id: context.question_id, record_index: context.record_index, predecessor_hash: context.predecessor_hash } : null }, null, 2))}</pre>
      </details>
    `;
    $("open-history")?.addEventListener("click", () => openHistoryDrawer(history));
    panel.querySelectorAll("[data-report-action]").forEach((button) => {
      button.addEventListener("click", async () => {
        button.disabled = true;
        const status = $("report-action-status");
        try { await resolveReport(item, button.dataset.reportAction); }
        catch (error) { if (status) { status.textContent = error.message || "回報狀態更新失敗"; status.classList.add("error"); } button.disabled = false; }
      });
    });
  }

  // ---------- stage (center workspace) ----------
  function reasonBannerMarkup(item, source) {
    if (state.section === "browse") return "";
    const label = source ? source.label : (item.source || "");
    const reason = item.reason && item.reason !== "其他" ? item.reason : (item.note || "");
    if (!reason && !label) return "";
    return `<div class="reason-banner"><span class="icon" aria-hidden="true">💡</span><div class="body"><strong>${esc(reason || "為什麼這題被送來")}</strong><span>${esc(label)}${item.note && item.note !== reason ? " · " + esc(item.note) : ""}</span></div></div>`;
  }

  async function selectItem(item) {
    state.selected = item;
    state.context = null;
    state.marker = null;
    setSelectionMode(true);
    renderList();
    const identity = item.identity || {};
    const q = identity.question || {};
    const source = classifySource(item);
    const dupKind = isDuplicateKind(item);

    $("stage").innerHTML = `
      <div class="stage-inner">
        <div class="stage-header">
          <button type="button" class="stage-back" id="stage-back" aria-label="返回列表">←</button>
          <div class="stage-title-wrap">
            <h2>${esc(identity.status === "EXACT" ? `題目 #${identity.question_id}` : "這題需要重新確認")}</h2>
            <p class="stage-sub">${esc([q.topic, q.level].filter(Boolean).join(" · "))}</p>
          </div>
        </div>
        ${reasonBannerMarkup(item, source)}
        <div class="center-status" id="center-status">${esc(identity.message || "正在載入棋盤…")}</div>
      </div>`;
    $("stage-back").addEventListener("click", backToList);
    renderInfoPanel(item, null);

    if (identity.status !== "EXACT") {
      $("stage").querySelector(".stage-inner").insertAdjacentHTML("beforeend", `<div class="empty-can"><h3>這題目前無法安全修改</h3><p>身份不夠明確，沒有猜測或套用修改。</p></div>`);
      return;
    }

    try {
      const context = await jsonFetch(`/api/admin/sgf-workbench/direct-context/${encodeURIComponent(identity.question_id)}?record_index=${encodeURIComponent(identity.record_index)}`);
      state.context = context;
      const actionArea = dupKind
        ? duplicateActionsMarkup(item)
        : `<div class="board-hint" id="board-hint">棋盤已載入，選擇下方的處理方式。</div><div id="question-review-controls"></div>`;
      $("stage").querySelector(".stage-inner").insertAdjacentHTML("beforeend", `
        <div class="board-shell">
          <div class="board-wrap"><canvas id="question-board" aria-label="題目棋盤"></canvas></div>
          <div class="board-legend"><span><i style="color:#5bd18b"></i>目前正解</span><span><i style="color:#77bdfb"></i>新選擇的位置</span></div>
        </div>
        ${actionArea}
      `);
      renderInfoPanel(item, context);
      drawBoard();
      $("question-board").addEventListener("pointerup", (event) => {
        const move = boardPoint(event);
        if (!move || !window.SGFReportWidget?.consumeBoardMove) return;
        window.SGFReportWidget.consumeBoardMove(move);
      });
      if (dupKind) {
        $("stage").querySelectorAll("[data-dup-action]").forEach((button) => {
          button.addEventListener("click", async () => {
            button.disabled = true;
            const status = $("dup-status");
            try {
              const message = await duplicateResolve(item, button.dataset.dupAction);
              if (status) { status.textContent = message; status.classList.remove("error"); }
              await load();
              backToList();
            } catch (error) {
              if (status) { status.textContent = error.message || "操作失敗"; status.classList.add("error"); }
              button.disabled = false;
            }
          });
        });
        $("stage").querySelector("[data-dup-pick]")?.addEventListener("click", (event) => {
          window.open(event.currentTarget.dataset.dupPick, "_blank", "noopener");
        });
        setStatus("這是相同題面群組；請先確認再繼續。", false);
      } else {
        window.SGFReportWidget?.mount?.();
        window.SGFReportWidget?.setContext({ question_id: identity.question_id, record_index: identity.record_index, surface: "admin_questions", board_size: q.board_size || 19, content: context.record?.content || "", authority: context.authority, next_handler: nextHandler });
        setStatus("棋盤已載入；請選擇一個簡單處理。", false);
      }
    } catch (error) {
      setStatus("這題目前無法安全修改", true);
      $("stage").querySelector(".stage-inner").insertAdjacentHTML("beforeend", `<div class="empty-can"><p>題目身份或目前版本已經變動，請重新整理後再確認。</p></div>`);
    }
  }

  function setStatus(text, error) {
    const node = $("center-status");
    if (node) { node.textContent = text || ""; node.className = `center-status${error ? " error" : ""}`; }
  }

  async function selectExactDeepLink(questionId, recordIndex) {
    const query = recordIndex == null ? "" : `?record_index=${encodeURIComponent(recordIndex)}`;
    const context = await jsonFetch(`/api/admin/sgf-workbench/direct-context/${encodeURIComponent(questionId)}${query}`);
    const record = context.record || {};
    const exactId = Number(context.question_id ?? questionId);
    const exactIndex = Number(context.record_index ?? recordIndex);
    const directItem = {
      id: `C:deep-link:${exactId}:${exactIndex}`,
      source: "題庫",
      reason: "",
      status: "可查看",
      updated_at: "",
      note: "從目前題目頁開啟的安全連結。",
      identity: {
        status: "EXACT",
        question_id: exactId,
        record_index: exactIndex,
        content_sha256: context.question_content_sha256 || context.content_sha256 || null,
        question: {
          question_id: exactId,
          record_index: exactIndex,
          topic: record.topic || "",
          level: record.level || record.difficulty || "",
          source: record.source || "",
          board_size: context.board_size || 19,
        },
      },
      can_edit: true,
      actions: ["CORRECT", "REPLACE_ANSWER", "ADD_ALTERNATIVE_CORRECT_MOVE", "EDIT_QUESTION", "UNSURE"],
      technical: { system: "C", deep_link: true },
    };
    await selectItem(directItem);
  }

  async function load() {
    try {
      $("sync-status").textContent = "更新中…";
      state.payload = await jsonFetch("/api/admin/questions/bootstrap");
      $("app-loading").hidden = true; $("app-root").hidden = false;
      renderTabs(); renderList();
      const params = new URLSearchParams(window.location.search);
      const requestedSection = params.get("section");
      if (SECTION_META[requestedSection]) { state.section = requestedSection; renderTabs(); renderList(); }
      if (!state.selected) { showEmptyStage(); showEmptyInfo(); }
      const requestedId = Number(params.get("question_id"));
      const requestedIndex = params.get("record_index");
      const match = requestedId ? Object.values(state.payload.sections).flat().find((item) => Number(item.identity?.question_id) === requestedId && (requestedIndex == null || String(item.identity?.record_index) === String(requestedIndex))) : null;
      if (match) await selectItem(match);
      else if (requestedId) {
        try { await selectExactDeepLink(requestedId, requestedIndex); }
        catch (error) { setStatus("這題目前無法安全修改", true); }
      } else if (WORK_SECTIONS.has(state.section) && window.matchMedia("(min-width:1024px)").matches) {
        const first = filteredItems()[0];
        if (first) await selectItem(first);
      }
      $("sync-status").textContent = "已就緒";
    } catch (error) {
      $("app-loading").textContent = "題目管理中心目前無法載入。";
      $("app-loading").classList.add("error");
    }
  }

  window.addEventListener("sgf:inline-review-marker", (event) => {
    state.marker = event.detail?.move || null;
    drawBoard();
    const hint = $("board-hint");
    if (hint) hint.classList.toggle("active", !!state.marker);
  });
  window.addEventListener("resize", () => { if (state.context) drawBoard(); });

  document.addEventListener("click", (event) => {
    const nav = event.target.closest("[data-section]");
    if (nav) {
      state.section = nav.dataset.section;
      state.selected = null;
      setSelectionMode(false);
      renderTabs(); renderList(); showEmptyStage(); showEmptyInfo();
      if (WORK_SECTIONS.has(state.section) && window.matchMedia("(min-width:1024px)").matches) {
        const first = filteredItems()[0];
        if (first) selectItem(first);
      }
      return;
    }
    const card = event.target.closest("[data-open-index]");
    if (card) { const item = filteredItems()[Number(card.dataset.openIndex)]; if (item) selectItem(item); return; }
  });

  $("center-search")?.addEventListener("input", () => { renderList(); });
  $("refresh-btn")?.addEventListener("click", () => {
    const button = $("refresh-btn");
    button.classList.add("spinning");
    load().finally(() => button.classList.remove("spinning"));
  });
  $("drawer-backdrop")?.addEventListener("click", closeHistoryDrawer);
  $("drawer-close")?.addEventListener("click", closeHistoryDrawer);

  load();
})();
