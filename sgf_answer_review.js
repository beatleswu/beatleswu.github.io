(function (root, factory) {
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.SGFAnswerReviewQueue = api;
  if (typeof document !== "undefined") {
    document.addEventListener("DOMContentLoaded", function () {
      api.boot().catch(function (error) {
        api.renderFatalError(error);
      });
    });
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function (root) {
  "use strict";

  const API_ROOT = "/api/admin/sgf-answer-review";
  const STATUS_LABELS = {
    NO_ISSUE: "沒問題",
    CONFIRMED_ISSUE: "確認有問題",
    POSSIBLE_MULTIPLE_SOLUTION: "可能多解",
    UNCERTAIN: "不確定",
  };
  const REASON_LABELS = {
    GLOBAL_TENUKI: "全局脫先／歷史 X 不合理",
    WRONG_PRIMARY_ANSWER: "目前主要答案錯誤",
    WRONG_CONTINUATION: "後續變化錯誤",
    MISSING_EQUIVALENT_SOLUTION: "遺漏等價解",
    SOURCE_CONVERSION_OR_SIDE_TO_MOVE_ERROR: "題面轉換／黑白先錯誤",
    SGF_OR_BOARD_STRUCTURE_ERROR: "SGF／題面結構錯誤",
    OTHER: "其他（才需要文字備註）",
  };
  const PROPOSAL_LABELS = {
    REPLACE_PRIMARY_ANSWER: "修改主要正解",
    ADD_EQUIVALENT_SOLUTION: "新增等價正解",
    REJECT_HISTORICAL_PRECOMPUTED_FALLBACK: "拒絕歷史預算 X",
    SET_SIDE_TO_MOVE: "修正黑白先",
    SOURCE_POSITION_INCLUDES_ANSWER: "題面可能已包含答案",
    NEEDS_SOURCE_RECONSTRUCTION: "需要題面重建",
  };
  const REASON_CODE_LABELS = {
    PARSER_FAILURE: "SGF 解析失敗",
    EMPTY_SOLUTION_TREE: "空解答樹",
    NO_VALID_ROOT_ANSWER: "沒有有效根節點答案",
    STRUCTURAL_SGF_ISSUE: "SGF 結構異常",
    PRECOMPUTED_KATAGO_ONLY_FALLBACK: "僅有歷史預算答案",
    KATAGO_NATIVE_TREE_DISAGREEMENT: "歷史預算與原生解答樹不一致",
    HISTORICAL_ANSWER_CONFLICT: "歷史答案衝突",
    HIGH_CONFIDENCE_GLOBAL_TENUKI_SUSPECT: "高信心全局脫先疑慮",
    POSSIBLE_GLOBAL_TENUKI_SUSPECT: "可能全局脫先",
    PLAYER_REPORTED: "玩家回報",
    REPEATED_REJECTED_MOVE: "重複遭拒落點",
    MULTIPLE_SOLUTION_REVIEW: "多解檢查",
    ANSWER_PROVENANCE_UNKNOWN: "答案來源不明",
    SIDE_TO_MOVE_UNKNOWN: "先手不明",
  };

  const runtime = {
    owner: null,
    csrfHeader: null,
    csrfToken: null,
    queueSource: null,
    groups: [],
    states: {},
    progress: null,
    filteredGroups: [],
    currentIndex: 0,
    filters: { status: "pending", priority: "all", focus: "all" },
    editMode: null,
    candidateMove: null,
    busy: false,
    resizeFrame: null,
    toastTimer: null,
  };

  function element(id) {
    return document.getElementById(id);
  }

  function boardGeometry(boardSize, width, height) {
    const shortSide = Math.max(1, Math.min(Number(width) || 1, Number(height) || 1));
    const padding = Math.max(18, Math.min(42, shortSide * 0.0625));
    const span = Math.max(1, shortSide - padding * 2);
    return { boardSize, width, height, padding, span, step: span / (boardSize - 1) };
  }

  function intersectionToCanvas(x, y, geometry) {
    return {
      x: geometry.padding + x * geometry.step,
      y: geometry.padding + y * geometry.step,
    };
  }

  function clientPointToIntersection(clientX, clientY, rect, boardSize) {
    if (!rect || rect.width <= 0 || rect.height <= 0) return null;
    const localX = clientX - rect.left;
    const localY = clientY - rect.top;
    const geometry = boardGeometry(boardSize, rect.width, rect.height);
    const x = Math.round((localX - geometry.padding) / geometry.step);
    const y = Math.round((localY - geometry.padding) / geometry.step);
    if (x < 0 || y < 0 || x >= boardSize || y >= boardSize) return null;
    const snapped = intersectionToCanvas(x, y, geometry);
    if (Math.hypot(localX - snapped.x, localY - snapped.y) > geometry.step * 0.49) return null;
    return { x, y };
  }

  function gtpCoordinate(x, y, boardSize) {
    const alphabet = "ABCDEFGHJKLMNOPQRSTUVWXYZ";
    if (!Number.isInteger(x) || !Number.isInteger(y) || x < 0 || y < 0 || x >= boardSize || y >= boardSize) return "?";
    return `${alphabet[x] || "?"}${boardSize - y}`;
  }

  function pendingStorageKey(snapshotSha, ownerUserId) {
    return `sgf-owner-review-pending:${snapshotSha}:${ownerUserId}`;
  }

  function dedupePendingMutations(operations) {
    const seen = new Set();
    const result = [];
    (Array.isArray(operations) ? operations : []).forEach(function (operation) {
      const mutationId = operation && operation.body && operation.body.mutation_id;
      if (!mutationId || seen.has(mutationId)) return;
      seen.add(mutationId);
      result.push(operation);
    });
    return result;
  }

  function indexAfterSave(currentIndex, length, saveSucceeded) {
    if (!saveSucceeded || length <= 0) return currentIndex;
    return Math.min(currentIndex + 1, length - 1);
  }

  function mutationId(prefix) {
    const random = root.crypto && root.crypto.randomUUID
      ? root.crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
    return `${prefix || "review"}:${random}`;
  }

  function blankState(group) {
    return {
      review_group_key: group.review_group_key,
      review_status: null,
      issue_reason: null,
      owner_note: "",
      current_sgf_answer_preserved: false,
      historical_precomputed_rejected: false,
      proposals: [],
      revision: 0,
    };
  }

  function stateFor(group) {
    return runtime.states[group.review_group_key] || blankState(group);
  }

  function computeSummary(groups, states) {
    const summary = {
      total_groups: groups.length,
      pending: groups.length,
      reviewed: 0,
      confirmed_issue: 0,
      possible_multiple_solution: 0,
      uncertain: 0,
      no_issue: 0,
      staged_repair_groups: 0,
      staged_proposals: 0,
    };
    groups.forEach(function (group) {
      const state = states[group.review_group_key];
      if (!state || !state.review_status) return;
      summary.reviewed += 1;
      summary.pending -= 1;
      if (state.review_status === "CONFIRMED_ISSUE") summary.confirmed_issue += 1;
      if (state.review_status === "POSSIBLE_MULTIPLE_SOLUTION") summary.possible_multiple_solution += 1;
      if (state.review_status === "UNCERTAIN") summary.uncertain += 1;
      if (state.review_status === "NO_ISSUE") summary.no_issue += 1;
      const count = (state.proposals || []).length;
      if (count) {
        summary.staged_repair_groups += 1;
        summary.staged_proposals += count;
      }
    });
    return summary;
  }

  function groupMatchesFilters(group, state, filters) {
    const reviewed = Boolean(state && state.review_status);
    if (filters.status === "pending" && reviewed) return false;
    if (filters.status === "reviewed" && !reviewed) return false;
    if (!["all", "pending", "reviewed"].includes(filters.status) && (!state || state.review_status !== filters.status)) return false;
    if (filters.priority !== "all" && group.priority_tier !== filters.priority) return false;
    const codes = new Set(group.reason_codes || []);
    if (filters.focus === "tenuki" && !codes.has("HIGH_CONFIDENCE_GLOBAL_TENUKI_SUSPECT")) return false;
    if (filters.focus === "duplicate" && group.group_size < 2) return false;
    if (filters.focus === "source" && !(group.side_to_move == null || codes.has("PARSER_FAILURE") || codes.has("STRUCTURAL_SGF_ISSUE"))) return false;
    if (filters.focus === "multiple" && !(codes.has("MULTIPLE_SOLUTION_REVIEW") || group.current_first_solution_moves.length > 1)) return false;
    return true;
  }

  function currentGroup() {
    return runtime.filteredGroups[runtime.currentIndex] || null;
  }

  function showScreen(name) {
    ["loading", "home", "queue", "staged"].forEach(function (screen) {
      const target = element(`${screen}-screen`);
      if (target) target.hidden = screen !== name;
    });
    element("sticky-nav").hidden = name !== "queue" || runtime.filteredGroups.length === 0;
    if (name === "home") renderHome();
    if (name === "staged") renderStaged();
  }

  function showToast(message, isError) {
    const toast = element("toast");
    toast.textContent = message;
    toast.classList.toggle("error", Boolean(isError));
    toast.classList.add("show");
    clearTimeout(runtime.toastTimer);
    runtime.toastTimer = setTimeout(function () { toast.classList.remove("show"); }, 2600);
  }

  function syncIndicator(state, text) {
    const target = element("sync-state");
    if (!target) return;
    target.dataset.state = state;
    target.textContent = text;
  }

  function storageKey() {
    return pendingStorageKey(runtime.queueSource.source_snapshot.sha256, runtime.owner.user_id);
  }

  function readPending() {
    try {
      return dedupePendingMutations(JSON.parse(root.localStorage.getItem(storageKey()) || "[]"));
    } catch (_error) {
      return [];
    }
  }

  function writePending(operations) {
    const cleaned = dedupePendingMutations(operations);
    try {
      if (cleaned.length) root.localStorage.setItem(storageKey(), JSON.stringify(cleaned));
      else root.localStorage.removeItem(storageKey());
    } catch (_error) {
      // Server state remains authoritative; storage failure only removes offline retry.
    }
    if (cleaned.length) syncIndicator("pending", `● ${cleaned.length} 筆待同步`);
    else syncIndicator("saved", "● 已同步");
  }

  function enqueueOperation(operation) {
    writePending(readPending().concat([operation]));
  }

  function removePending(mutationIdValue) {
    writePending(readPending().filter(function (operation) {
      return operation.body.mutation_id !== mutationIdValue;
    }));
  }

  async function transmit(operation) {
    let response;
    try {
      if (!runtime.csrfHeader || !runtime.csrfToken) {
        const error = new Error("Review security token is unavailable; reload required");
        error.retryable = true;
        throw error;
      }
      const headers = { "Content-Type": "application/json", "Accept": "application/json" };
      headers[runtime.csrfHeader] = runtime.csrfToken;
      response = await root.fetch(operation.url, {
        method: operation.method || "POST",
        headers,
        credentials: "same-origin",
        body: JSON.stringify(operation.body),
      });
    } catch (error) {
      error.retryable = true;
      throw error;
    }
    const payload = await response.json().catch(function () { return {}; });
    if (!response.ok) {
      const error = new Error(payload.detail || payload.error || `HTTP ${response.status}`);
      error.status = response.status;
      error.retryable = response.status >= 500;
      throw error;
    }
    return payload;
  }

  async function sendOperation(operation) {
    enqueueOperation(operation);
    try {
      const result = await transmit(operation);
      removePending(operation.body.mutation_id);
      return result;
    } catch (error) {
      if (!error.retryable) removePending(operation.body.mutation_id);
      else syncIndicator("pending", `● ${readPending().length} 筆待同步`);
      throw error;
    }
  }

  function absorbOperationResult(operation, result) {
    if (result.state) runtime.states[result.state.review_group_key] = result.state;
    if (result.progress) runtime.progress = result.progress;
    if (operation.kind === "progress" && result.progress) runtime.progress = result.progress;
  }

  async function retryPendingOperations() {
    if (!runtime.queueSource || !root.navigator.onLine) return;
    const pending = readPending();
    if (!pending.length) return;
    syncIndicator("pending", `● ${pending.length} 筆待同步`);
    for (const operation of pending) {
      try {
        const result = await transmit(operation);
        removePending(operation.body.mutation_id);
        absorbOperationResult(operation, result);
      } catch (error) {
        if (!error.retryable) {
          removePending(operation.body.mutation_id);
          showToast("另一台裝置已更新，未覆蓋較新的決定", true);
          await reloadBootstrap(false);
          return;
        }
        syncIndicator("pending", `● ${readPending().length} 筆待同步`);
        return;
      }
    }
    renderAll();
    showToast("離線操作已安全同步");
  }

  function escapeText(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function renderHome() {
    const summary = computeSummary(runtime.groups, runtime.states);
    const stats = [
      [summary.pending, "待審 group"],
      [summary.reviewed, "已審"],
      [summary.confirmed_issue, "確認有問題"],
      [summary.possible_multiple_solution, "可能多解"],
      [summary.staged_repair_groups, "待套用 group"],
      [summary.staged_proposals, "結構化提案"],
    ];
    stats[4] = [summary.uncertain, "\u4e0d\u78ba\u5b9a"];
    stats[5] = [summary.staged_repair_groups, "\u5f85\u6b63\u5f0f\u5957\u7528\u4fee\u6b63"];
    element("home-stats").innerHTML = stats.map(function (item) {
      return `<div class="stat"><strong>${item[0]}</strong><span>${item[1]}</span></div>`;
    }).join("");
    element("staged-btn").textContent = `待套用修正（${summary.staged_proposals}）`;
  }

  function applyFilters(overrides) {
    runtime.filters = Object.assign({}, runtime.filters, overrides || {});
    runtime.filteredGroups = runtime.groups.filter(function (group) {
      return groupMatchesFilters(group, runtime.states[group.review_group_key], runtime.filters);
    });
    runtime.currentIndex = 0;
    const resumeKey = runtime.progress && runtime.progress.current_review_group_key;
    const resumeIndex = runtime.filteredGroups.findIndex(function (group) {
      return group.review_group_key === resumeKey;
    });
    if (resumeIndex >= 0) runtime.currentIndex = resumeIndex;
    renderQueue();
  }

  function displayLegacyId(group) {
    const ids = group.linked_records.map(function (record) {
      return record.legacy_question_id == null ? `index ${record.audit_locator.record_index}` : record.legacy_question_id;
    });
    return ids.join("、");
  }

  function renderBadges(group) {
    const badges = [
      `<span class="badge">題號 ${escapeText(displayLegacyId(group))}</span>`,
      `<span class="badge priority">${escapeText(group.priority_tier)} · rank ${group.first_deterministic_rank}</span>`,
      `<span class="badge side">${escapeText(group.side_to_move_display)}</span>`,
    ];
    if (group.group_size > 1) badges.push(`<span class="badge duplicate">同內容 ${group.group_size} 筆，一次審核</span>`);
    element("board-badges").innerHTML = badges.join("");
  }

  function renderQueue() {
    const group = currentGroup();
    const empty = !group;
    element("queue-empty").hidden = !empty;
    element("review-layout").hidden = empty;
    element("sticky-nav").hidden = empty || element("queue-screen").hidden;
    if (empty) return;
    cancelEdit();
    element("side-repair-panel").hidden = true;
    const loadedState = stateFor(group);
    element("source-includes-answer").checked = (loadedState.proposals || []).some(function (proposal) {
      return proposal.type === "SOURCE_POSITION_INCLUDES_ANSWER" ||
        Boolean(proposal.source_position_includes_answer);
    });

    renderBadges(group);
    element("queue-title").textContent = `${runtime.filters.focus === "tenuki" ? "高信心脫先" : "疑題"}審查`;
    element("group-progress").textContent = `${runtime.currentIndex + 1} / ${runtime.filteredGroups.length}`;
    element("reason-summary").textContent = (group.reason_codes || []).map(function (code) {
      return REASON_CODE_LABELS[code] || code;
    }).join(" · ");
    const hasComparableAnswers = group.current_first_solution_moves.length > 0 && group.historical_precomputed_moves.some(function (historical) {
      return !group.current_first_solution_moves.some(function (nativeMove) {
        return nativeMove.x === historical.x && nativeMove.y === historical.y;
      });
    });
    element("fast-a-correct").disabled = !hasComparableAnswers;
    element("fast-both").disabled = !hasComparableAnswers;
    element("mobile-fast-a-correct").disabled = !hasComparableAnswers;
    element("mobile-fast-both").disabled = !hasComparableAnswers;
    element("prev-btn").disabled = runtime.currentIndex === 0;
    element("next-btn").disabled = runtime.currentIndex >= runtime.filteredGroups.length - 1;
    renderDecision(group);
    renderProgress();
    drawBoard();
  }

  function renderProgress() {
    const summary = computeSummary(runtime.groups, runtime.states);
    element("reviewed-progress").textContent = `已審 ${summary.reviewed}`;
    element("pending-progress").textContent = `待審 ${summary.pending}`;
    const ratio = summary.total_groups ? summary.reviewed / summary.total_groups : 0;
    element("progress-fill").style.width = `${Math.round(ratio * 100)}%`;
  }

  function proposalPointText(proposal, group) {
    if (proposal.proposed_move) return gtpCoordinate(proposal.proposed_move.x, proposal.proposed_move.y, group.board_size);
    if (proposal.proposed_side_to_move && proposal.source_position_includes_answer) {
      const side = proposal.proposed_side_to_move === "B" ? "\u9ed1\u5148" : "\u767d\u5148";
      return `${side} \u00b7 \u984c\u9762\u53ef\u80fd\u5df2\u5305\u542b\u7b54\u6848`;
    }
    if (proposal.proposed_side_to_move) return proposal.proposed_side_to_move === "B" ? "黑先" : "白先";
    return "";
  }

  function renderDecision(group) {
    const state = stateFor(group);
    const stateTarget = element("current-state");
    if (!state.review_status) {
      stateTarget.textContent = "尚未審題；canonical SGF 與玩家判題均未改動。";
    } else {
      const reason = state.issue_reason ? ` · ${REASON_LABELS[state.issue_reason] || state.issue_reason}` : "";
      const proposalRows = (state.proposals || []).map(function (proposal) {
        const point = proposalPointText(proposal, group);
        return `<div class="proposal-pill"><span>${escapeText(PROPOSAL_LABELS[proposal.type] || proposal.type)}${point ? ` · ${escapeText(point)}` : ""}</span><span>待套用</span></div>`;
      }).join("");
      stateTarget.innerHTML = `<strong>${escapeText(STATUS_LABELS[state.review_status] || state.review_status)}${escapeText(reason)}</strong>${proposalRows}<div class="muted">revision ${state.revision} · server-side staging</div>`;
    }
    document.querySelectorAll("[id^='status-']").forEach(function (button) { button.removeAttribute("aria-pressed"); });
    const mapping = { NO_ISSUE: "status-no-issue", CONFIRMED_ISSUE: "status-confirmed", POSSIBLE_MULTIPLE_SOLUTION: "status-multiple", UNCERTAIN: "status-uncertain" };
    if (mapping[state.review_status]) element(mapping[state.review_status]).setAttribute("aria-pressed", "true");
    element("undo-btn").disabled = state.revision === 0;
    element("previous-reviewed-btn").disabled = !findPreviousReviewedGroup();
    const sideProposal = (state.proposals || []).find(function (proposal) { return proposal.type === "SET_SIDE_TO_MOVE"; });
    document.querySelectorAll("[data-side]").forEach(function (button) {
      if (sideProposal && sideProposal.proposed_side_to_move === button.dataset.side) button.setAttribute("aria-pressed", "true");
      else button.removeAttribute("aria-pressed");
    });

    const currentMoves = group.current_first_solution_moves.map(function (move) { return gtpCoordinate(move.x, move.y, group.board_size); });
    element("repair-current").textContent = `目前答案：${currentMoves.length ? currentMoves.join("、") : "無原生根答案"}`;
    element("proposal-legend").hidden = !(state.proposals || []).some(function (proposal) { return proposal.proposed_move; });
    element("technical-details").textContent = [
      `AUDIT_LOCATOR_ONLY · ${group.review_group_key}`,
      `snapshot ${runtime.queueSource.source_snapshot.sha256}`,
      `linked records ${group.group_size}: ${displayLegacyId(group)}`,
      `native answers ${currentMoves.join(", ") || "none"}`,
      `historical X ${group.historical_precomputed_moves.map(function (move) { return gtpCoordinate(move.x, move.y, group.board_size); }).join(", ") || "none"}`,
      `reason codes ${(group.reason_codes || []).join(", ")}`,
      `identity: review deduplication only; not canonical puzzle identity`,
    ].join("\n");
  }

  function stoneAt(group, x, y) {
    return group.board_preview.initial_stones.some(function (stone) { return stone.x === x && stone.y === y; });
  }

  function starCoordinates(size) {
    if (size === 19) return [3, 9, 15];
    if (size === 13) return [3, 6, 9];
    if (size === 9) return [2, 4, 6];
    return size % 2 ? [Math.floor(size / 2)] : [];
  }

  function drawStone(ctx, point, color, radius) {
    const gradient = ctx.createRadialGradient(point.x - radius * 0.34, point.y - radius * 0.38, radius * 0.08, point.x, point.y, radius);
    if (color === "B") {
      gradient.addColorStop(0, "#575757");
      gradient.addColorStop(0.45, "#191919");
      gradient.addColorStop(1, "#020202");
    } else {
      gradient.addColorStop(0, "#ffffff");
      gradient.addColorStop(0.55, "#e7e5dd");
      gradient.addColorStop(1, "#aaa89f");
    }
    ctx.beginPath(); ctx.arc(point.x, point.y, radius, 0, Math.PI * 2); ctx.fillStyle = gradient; ctx.fill();
    ctx.strokeStyle = color === "B" ? "rgba(255,255,255,.12)" : "rgba(40,40,35,.35)"; ctx.lineWidth = 1; ctx.stroke();
  }

  function drawMarker(ctx, move, geometry, label, color, offset) {
    const point = intersectionToCanvas(move.x, move.y, geometry);
    const radius = Math.max(8, geometry.step * 0.39);
    ctx.beginPath(); ctx.arc(point.x + (offset || 0), point.y, radius, 0, Math.PI * 2);
    ctx.strokeStyle = color; ctx.lineWidth = Math.max(3, geometry.step * 0.1); ctx.stroke();
    ctx.fillStyle = color; ctx.font = `800 ${Math.max(12, geometry.step * 0.48)}px system-ui`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(label, point.x + (offset || 0), point.y + 0.5);
  }

  function drawBoard() {
    const group = currentGroup();
    const canvas = element("go-board");
    if (!group || !canvas) return;
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const dpr = Math.min(root.devicePixelRatio || 1, 2.5);
    canvas.width = Math.round(rect.width * dpr);
    canvas.height = Math.round(rect.height * dpr);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const geometry = boardGeometry(group.board_size, rect.width, rect.height);
    const wood = ctx.createLinearGradient(0, 0, rect.width, rect.height);
    wood.addColorStop(0, "#e3bc75"); wood.addColorStop(0.5, "#d4a45e"); wood.addColorStop(1, "#bd8848");
    ctx.fillStyle = wood; ctx.fillRect(0, 0, rect.width, rect.height);
    ctx.strokeStyle = "rgba(62,40,17,.76)"; ctx.lineWidth = Math.max(1, geometry.step * 0.035);
    for (let index = 0; index < group.board_size; index += 1) {
      const startH = intersectionToCanvas(0, index, geometry); const endH = intersectionToCanvas(group.board_size - 1, index, geometry);
      const startV = intersectionToCanvas(index, 0, geometry); const endV = intersectionToCanvas(index, group.board_size - 1, geometry);
      ctx.beginPath(); ctx.moveTo(startH.x, startH.y); ctx.lineTo(endH.x, endH.y); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(startV.x, startV.y); ctx.lineTo(endV.x, endV.y); ctx.stroke();
    }
    const stars = starCoordinates(group.board_size);
    stars.forEach(function (x) { stars.forEach(function (y) {
      const point = intersectionToCanvas(x, y, geometry); ctx.beginPath(); ctx.arc(point.x, point.y, Math.max(2.3, geometry.step * 0.09), 0, Math.PI * 2); ctx.fillStyle = "#3b2814"; ctx.fill();
    }); });
    const stoneRadius = Math.max(7, geometry.step * 0.45);
    group.board_preview.initial_stones.forEach(function (stone) {
      drawStone(ctx, intersectionToCanvas(stone.x, stone.y, geometry), stone.color, stoneRadius);
    });
    group.current_first_solution_moves.forEach(function (move) { drawMarker(ctx, move, geometry, "A", "#35d47a", 0); });
    group.historical_precomputed_moves.forEach(function (move) {
      const overlaps = group.current_first_solution_moves.some(function (nativeMove) { return nativeMove.x === move.x && nativeMove.y === move.y; });
      drawMarker(ctx, move, geometry, "X", "#ff8738", overlaps ? geometry.step * 0.2 : 0);
    });
    const state = stateFor(group);
    (state.proposals || []).forEach(function (proposal) {
      if (proposal.proposed_move) drawMarker(ctx, proposal.proposed_move, geometry, "●", "#5cbcff", 0);
    });
    if (runtime.candidateMove) drawMarker(ctx, runtime.candidateMove, geometry, "+", "#d7f1ff", 0);
    canvas.setAttribute("aria-label", `${group.board_size} 路棋盤；${group.side_to_move_display}；目前答案 ${group.current_first_solution_moves.length} 個；歷史答案 ${group.historical_precomputed_moves.length} 個`);
  }

  function cancelEdit() {
    runtime.editMode = null;
    runtime.candidateMove = null;
    const banner = element("edit-banner");
    const confirm = element("repair-confirm");
    const wrapper = element("board-wrap");
    if (banner) banner.hidden = true;
    if (confirm) confirm.hidden = true;
    if (wrapper) wrapper.classList.remove("editing");
  }

  function beginBoardEdit(mode) {
    const group = currentGroup();
    if (!group) return;
    runtime.editMode = mode;
    runtime.candidateMove = null;
    element("edit-banner").hidden = false;
    element("edit-title").textContent = mode === "REPLACE_PRIMARY_ANSWER" ? "正在修改主要正解" : "正在新增等價正解";
    element("edit-help").textContent = "直接點棋盤交叉點；不需輸入座標";
    element("board-wrap").classList.add("editing");
    element("repair-confirm").hidden = true;
    element("side-repair-panel").hidden = true;
    drawBoard();
    element("board-wrap").scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function selectBoardPoint(event) {
    if (!runtime.editMode || runtime.busy) return;
    const group = currentGroup();
    const canvas = element("go-board");
    const point = clientPointToIntersection(event.clientX, event.clientY, canvas.getBoundingClientRect(), group.board_size);
    if (!point) return;
    if (stoneAt(group, point.x, point.y)) {
      showToast("這個交叉點已有棋子，請選其他落點", true);
      return;
    }
    runtime.candidateMove = Object.assign({}, point, group.side_to_move ? { color: group.side_to_move } : {}, { gtp: gtpCoordinate(point.x, point.y, group.board_size) });
    element("repair-point").textContent = `建議新答案：${runtime.candidateMove.gtp}`;
    element("repair-confirm").hidden = false;
    drawBoard();
  }

  function upsertProposal(proposals, raw) {
    const result = (proposals || []).filter(function (proposal) {
      if (raw.type === "REPLACE_PRIMARY_ANSWER" || raw.type === "ADD_EQUIVALENT_SOLUTION") {
        return !(proposal.type === raw.type && proposal.proposed_move && raw.proposed_move && proposal.proposed_move.x === raw.proposed_move.x && proposal.proposed_move.y === raw.proposed_move.y);
      }
      return proposal.type !== raw.type;
    });
    result.push(raw);
    return result;
  }

  function nextGroupKey() {
    if (!runtime.filteredGroups.length) return null;
    const nextIndex = Math.min(runtime.currentIndex + 1, runtime.filteredGroups.length - 1);
    return runtime.filteredGroups[nextIndex].review_group_key;
  }

  async function saveDecision(decision, options) {
    if (runtime.busy) return false;
    const group = currentGroup();
    if (!group) return false;
    const current = stateFor(group);
    const body = Object.assign({
      mutation_id: mutationId("save"),
      expected_revision: current.revision,
      review_status: current.review_status || "UNCERTAIN",
      issue_reason: current.issue_reason,
      owner_note: current.owner_note || "",
      current_sgf_answer_preserved: current.current_sgf_answer_preserved,
      historical_precomputed_rejected: current.historical_precomputed_rejected,
      proposals: current.proposals || [],
      resume_group_key: (options && options.advance) ? nextGroupKey() : group.review_group_key,
    }, decision || {});
    runtime.busy = true;
    syncIndicator("pending", "● 正在保存");
    try {
      const operation = { kind: "review", method: "POST", url: `${API_ROOT}/groups/${group.review_group_key}`, body };
      const result = await sendOperation(operation);
      absorbOperationResult(operation, result);
      runtime.busy = false;
      if (options && options.advance) {
        applyFilters({});
      } else {
        renderHome();
        renderQueue();
      }
      if (options && options.advance) showToast("已保存，下一題");
      else showToast("決定已保存到伺服器");
      return true;
    } catch (error) {
      runtime.busy = false;
      syncIndicator(error.retryable ? "pending" : "error", error.retryable ? "● 尚未同步" : "● 保存衝突");
      showToast(error.retryable ? "網路中斷：決定尚未同步，也沒有跳到下一題" : `未覆蓋伺服器資料：${error.message}`, true);
      return false;
    }
  }

  async function saveProgress(group) {
    if (!group) return;
    const operation = {
      kind: "progress",
      method: "POST",
      url: `${API_ROOT}/progress`,
      body: { mutation_id: mutationId("progress"), review_group_key: group.review_group_key },
    };
    try {
      const result = await sendOperation(operation);
      absorbOperationResult(operation, result);
    } catch (error) {
      if (!error.retryable) showToast("進度已被另一台裝置更新，請重新整理", true);
    }
  }

  async function moveBy(delta) {
    if (runtime.busy || !runtime.filteredGroups.length) return;
    const next = Math.max(0, Math.min(runtime.currentIndex + delta, runtime.filteredGroups.length - 1));
    if (next === runtime.currentIndex) return;
    runtime.currentIndex = next;
    renderQueue();
    await saveProgress(currentGroup());
  }

  async function setSimpleStatus(status) {
    const clearsRepair = status === "NO_ISSUE" || status === "UNCERTAIN";
    await saveDecision({
      review_status: status,
      issue_reason: null,
      owner_note: "",
      current_sgf_answer_preserved: status === "NO_ISSUE",
      historical_precomputed_rejected: false,
      proposals: clearsRepair ? [] : stateFor(currentGroup()).proposals,
    }, { advance: true });
  }

  function showReasonPicker() {
    element("reason-panel").hidden = false;
    element("reason-panel").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function confirmReason(reason) {
    await saveDecision({
      review_status: "CONFIRMED_ISSUE",
      issue_reason: reason,
      owner_note: "",
    }, { advance: true });
    element("reason-panel").hidden = true;
  }

  async function fastACorrectXWrong() {
    const group = currentGroup();
    if (!group || !group.historical_precomputed_moves.length) return;
    const proposal = { type: "REJECT_HISTORICAL_PRECOMPUTED_FALLBACK" };
    await saveDecision({
      review_status: "CONFIRMED_ISSUE",
      issue_reason: "GLOBAL_TENUKI",
      owner_note: "",
      current_sgf_answer_preserved: true,
      historical_precomputed_rejected: true,
      proposals: upsertProposal(stateFor(group).proposals, proposal),
    }, { advance: true });
  }

  async function fastBothPossible() {
    const group = currentGroup();
    if (!group || !group.historical_precomputed_moves.length) return;
    let proposals = stateFor(group).proposals;
    group.historical_precomputed_moves.forEach(function (move) {
      const native = group.current_first_solution_moves.some(function (answer) { return answer.x === move.x && answer.y === move.y; });
      if (!native) proposals = upsertProposal(proposals, { type: "ADD_EQUIVALENT_SOLUTION", proposed_move: move });
    });
    await saveDecision({
      review_status: "POSSIBLE_MULTIPLE_SOLUTION",
      issue_reason: null,
      owner_note: "",
      current_sgf_answer_preserved: true,
      historical_precomputed_rejected: false,
      proposals,
    }, { advance: true });
  }

  async function confirmBoardRepair() {
    const group = currentGroup();
    if (!runtime.editMode || !runtime.candidateMove || !group) return;
    const type = runtime.editMode;
    const proposals = upsertProposal(stateFor(group).proposals, { type, proposed_move: runtime.candidateMove });
    const status = type === "ADD_EQUIVALENT_SOLUTION" ? "POSSIBLE_MULTIPLE_SOLUTION" : "CONFIRMED_ISSUE";
    const reason = type === "ADD_EQUIVALENT_SOLUTION" ? null : "WRONG_PRIMARY_ANSWER";
    const saved = await saveDecision({
      review_status: status,
      issue_reason: reason,
      owner_note: "",
      current_sgf_answer_preserved: type === "ADD_EQUIVALENT_SOLUTION",
      historical_precomputed_rejected: false,
      proposals,
    }, { advance: false });
    if (saved) cancelEdit();
  }

  async function saveSideProposal(side) {
    const group = currentGroup();
    const includeAnswer = element("source-includes-answer").checked;
    const proposals = upsertProposal(stateFor(group).proposals, {
      type: "SET_SIDE_TO_MOVE",
      proposed_side_to_move: side,
      source_position_includes_answer: includeAnswer,
    });
    await saveDecision({
      review_status: "CONFIRMED_ISSUE",
      issue_reason: "SOURCE_CONVERSION_OR_SIDE_TO_MOVE_ERROR",
      owner_note: "",
      proposals,
    }, { advance: false });
  }

  async function saveSourceIncludesAnswer() {
    const group = currentGroup();
    const checked = element("source-includes-answer").checked;
    let proposals = stateFor(group).proposals.slice();
    const sideProposal = proposals.find(function (proposal) { return proposal.type === "SET_SIDE_TO_MOVE"; });
    if (sideProposal) {
      proposals = upsertProposal(proposals, {
        type: "SET_SIDE_TO_MOVE",
        proposed_side_to_move: sideProposal.proposed_side_to_move,
        source_position_includes_answer: checked,
      });
    } else if (checked) {
      proposals = upsertProposal(proposals, { type: "SOURCE_POSITION_INCLUDES_ANSWER" });
    } else {
      proposals = proposals.filter(function (proposal) { return proposal.type !== "SOURCE_POSITION_INCLUDES_ANSWER"; });
    }
    await saveDecision({
      review_status: "CONFIRMED_ISSUE",
      issue_reason: "SOURCE_CONVERSION_OR_SIDE_TO_MOVE_ERROR",
      owner_note: "",
      proposals,
    }, { advance: false });
  }

  async function saveReconstructionProposal() {
    const group = currentGroup();
    const proposals = upsertProposal(stateFor(group).proposals, {
      type: "NEEDS_SOURCE_RECONSTRUCTION",
      source_position_includes_answer: element("source-includes-answer").checked,
    });
    await saveDecision({
      review_status: "CONFIRMED_ISSUE",
      issue_reason: "SGF_OR_BOARD_STRUCTURE_ERROR",
      owner_note: "",
      proposals,
    }, { advance: false });
  }

  async function undoCurrent() {
    if (runtime.busy) return;
    const group = currentGroup();
    const state = stateFor(group);
    if (!group || !state.revision) return;
    runtime.busy = true;
    syncIndicator("pending", "● 正在撤銷");
    const operation = {
      kind: "undo",
      method: "POST",
      url: `${API_ROOT}/groups/${group.review_group_key}/undo`,
      body: { mutation_id: mutationId("undo"), expected_revision: state.revision, resume_group_key: group.review_group_key },
    };
    try {
      const result = await sendOperation(operation);
      absorbOperationResult(operation, result);
      runtime.busy = false;
      applyFilters({});
      showToast("已撤銷上一步，審計紀錄仍保留");
    } catch (error) {
      runtime.busy = false;
      syncIndicator(error.retryable ? "pending" : "error", error.retryable ? "● 尚未同步" : "● 撤銷衝突");
      showToast("撤銷未完成，沒有覆蓋較新資料", true);
    }
  }

  async function deleteProposal(groupKey, proposalId) {
    const index = runtime.groups.findIndex(function (group) { return group.review_group_key === groupKey; });
    if (index < 0) return;
    const previousFiltered = runtime.filteredGroups;
    const previousIndex = runtime.currentIndex;
    runtime.filteredGroups = runtime.groups;
    runtime.currentIndex = index;
    const group = currentGroup();
    const state = stateFor(group);
    const proposals = (state.proposals || []).filter(function (proposal) { return proposal.proposal_id !== proposalId; });
    await saveDecision({
      review_status: state.review_status,
      issue_reason: state.issue_reason,
      owner_note: state.owner_note || "",
      current_sgf_answer_preserved: state.current_sgf_answer_preserved,
      historical_precomputed_rejected: proposals.some(function (proposal) { return proposal.type === "REJECT_HISTORICAL_PRECOMPUTED_FALLBACK"; }),
      proposals,
    }, { advance: false });
    runtime.filteredGroups = previousFiltered;
    runtime.currentIndex = previousIndex;
    renderStaged();
  }

  function findPreviousReviewedGroup() {
    const current = currentGroup();
    if (!current) return null;
    const globalIndex = runtime.groups.findIndex(function (group) {
      return group.review_group_key === current.review_group_key;
    });
    for (let index = globalIndex - 1; index >= 0; index -= 1) {
      const candidate = runtime.groups[index];
      if (runtime.states[candidate.review_group_key] && runtime.states[candidate.review_group_key].review_status) return candidate;
    }
    return null;
  }

  function openPreviousReviewed() {
    const previous = findPreviousReviewedGroup();
    if (previous) openGroup(previous.review_group_key);
  }

  function openGroup(groupKey) {
    runtime.filters = { status: "all", priority: "all", focus: "all" };
    runtime.filteredGroups = runtime.groups.slice();
    runtime.currentIndex = runtime.filteredGroups.findIndex(function (group) { return group.review_group_key === groupKey; });
    if (runtime.currentIndex < 0) runtime.currentIndex = 0;
    showScreen("queue");
    renderQueue();
    saveProgress(currentGroup());
  }

  function renderStaged() {
    const target = element("staged-list");
    const staged = [];
    runtime.groups.forEach(function (group) {
      const state = runtime.states[group.review_group_key];
      (state && state.proposals || []).forEach(function (proposal) { staged.push({ group, state, proposal }); });
    });
    if (!staged.length) {
      target.innerHTML = `<div class="panel empty"><h2>目前沒有待套用修正</h2><p class="muted">Owner 決定只會先形成結構化提案，不會直接改 SGF。</p></div>`;
      return;
    }
    target.innerHTML = "";
    staged.forEach(function (item) {
      const card = document.createElement("article");
      card.className = "panel staged-card";
      const point = proposalPointText(item.proposal, item.group);
      card.innerHTML = `<div><h3>${escapeText(PROPOSAL_LABELS[item.proposal.type] || item.proposal.type)}${point ? ` · ${escapeText(point)}` : ""}</h3><p>題號 ${escapeText(displayLegacyId(item.group))} · ${escapeText(item.group.priority_tier)} · ${escapeText(item.group.side_to_move_display)} · OWNER_APPROVED_REPAIR_PROPOSAL / STAGED_NOT_APPLIED</p></div><div class="staged-actions"><button class="quiet" data-open-group="${item.group.review_group_key}">回棋盤修改</button><button class="danger" data-delete-proposal="${item.proposal.proposal_id}" data-group-key="${item.group.review_group_key}">移除提案</button></div>`;
      target.appendChild(card);
    });
  }

  function renderAll() {
    renderHome();
    if (!element("queue-screen").hidden) renderQueue();
    if (!element("staged-screen").hidden) renderStaged();
  }

  async function reloadBootstrap(showLoading) {
    if (showLoading !== false) showScreen("loading");
    const response = await root.fetch(`${API_ROOT}/bootstrap`, { headers: { "Accept": "application/json" }, credentials: "same-origin", cache: "no-store" });
    const payload = await response.json().catch(function () { return {}; });
    if (!response.ok || !payload.ok) throw new Error(payload.detail || payload.error || "無法載入審題資料");
    if (!payload.security || !payload.security.csrf_header || !payload.security.csrf_token) {
      throw new Error("Review security token is unavailable");
    }
    runtime.csrfHeader = payload.security.csrf_header;
    runtime.csrfToken = payload.security.csrf_token;
    runtime.owner = payload.owner;
    runtime.queueSource = payload.queue_source;
    runtime.groups = payload.groups;
    runtime.states = payload.states || {};
    runtime.progress = payload.progress || null;
    if (payload.queue_source.detector_signatures.detector_ranking_changed !== false) throw new Error("Detector ranking signature changed; queue stopped safely");
    runtime.filteredGroups = runtime.groups.slice();
    renderAll();
    if (showLoading !== false) showScreen("home");
    return payload;
  }

  function bindEvents() {
    const mobileFastBar = document.createElement("div");
    mobileFastBar.id = "mobile-fast-bar";
    mobileFastBar.className = "mobile-fast-bar";
    [
      ["mobile-fast-a-correct", "A \u5c0d \u00b7 X \u932f", "action-btn good"],
      ["mobile-fast-both", "A\u3001X \u90fd\u53ef\u80fd", "action-btn info"],
      ["mobile-fast-a-wrong", "\u4fee\u6539 A", "action-btn bad"],
      ["mobile-fast-later", "\u7a0d\u5f8c\u518d\u770b", "action-btn warn"],
    ].forEach(function (config) {
      const button = document.createElement("button");
      button.id = config[0];
      button.className = config[2];
      button.textContent = config[1];
      mobileFastBar.appendChild(button);
    });
    element("sticky-nav").insertBefore(mobileFastBar, element("sticky-nav").firstChild);

    const previousReviewedButton = document.createElement("button");
    previousReviewedButton.id = "previous-reviewed-btn";
    previousReviewedButton.className = "quiet";
    previousReviewedButton.style.cssText = "width:100%;margin-top:9px";
    previousReviewedButton.textContent = "\u56de\u5230\u4e0a\u4e00\u500b\u5df2\u5be9\u984c";
    element("undo-btn").insertAdjacentElement("afterend", previousReviewedButton);

    element("continue-btn").addEventListener("click", function () {
      applyFilters({ status: element("home-status-filter").value, priority: element("home-priority-filter").value, focus: element("home-focus-filter").value });
      showScreen("queue"); renderQueue(); saveProgress(currentGroup());
    });
    element("tenuki-start-btn").addEventListener("click", function () {
      element("home-status-filter").value = "pending";
      element("home-focus-filter").value = "tenuki";
      applyFilters({ status: "pending", priority: "all", focus: "tenuki" });
      showScreen("queue"); renderQueue(); saveProgress(currentGroup());
    });
    ["staged-btn", "staged-from-queue-btn"].forEach(function (id) { element(id).addEventListener("click", function () { showScreen("staged"); }); });
    ["home-btn", "staged-home-btn"].forEach(function (id) { element(id).addEventListener("click", function () { showScreen("home"); }); });
    element("prev-btn").addEventListener("click", function () { moveBy(-1); });
    element("next-btn").addEventListener("click", function () { moveBy(1); });
    element("later-btn").addEventListener("click", function () { setSimpleStatus("UNCERTAIN"); });
    element("fast-later").addEventListener("click", function () { setSimpleStatus("UNCERTAIN"); });
    element("fast-a-correct").addEventListener("click", fastACorrectXWrong);
    element("fast-both").addEventListener("click", fastBothPossible);
    element("fast-a-wrong").addEventListener("click", function () { beginBoardEdit("REPLACE_PRIMARY_ANSWER"); });
    element("mobile-fast-later").addEventListener("click", function () { setSimpleStatus("UNCERTAIN"); });
    element("mobile-fast-a-correct").addEventListener("click", fastACorrectXWrong);
    element("mobile-fast-both").addEventListener("click", fastBothPossible);
    element("mobile-fast-a-wrong").addEventListener("click", function () { beginBoardEdit("REPLACE_PRIMARY_ANSWER"); });
    element("status-no-issue").addEventListener("click", function () { setSimpleStatus("NO_ISSUE"); });
    element("status-multiple").addEventListener("click", function () { setSimpleStatus("POSSIBLE_MULTIPLE_SOLUTION"); });
    element("status-uncertain").addEventListener("click", function () { setSimpleStatus("UNCERTAIN"); });
    element("status-confirmed").addEventListener("click", showReasonPicker);
    element("replace-answer-btn").addEventListener("click", function () { beginBoardEdit("REPLACE_PRIMARY_ANSWER"); });
    element("add-answer-btn").addEventListener("click", function () { beginBoardEdit("ADD_EQUIVALENT_SOLUTION"); });
    element("cancel-edit-btn").addEventListener("click", function () { cancelEdit(); drawBoard(); });
    element("cancel-repair-btn").addEventListener("click", function () { cancelEdit(); drawBoard(); });
    element("confirm-repair-btn").addEventListener("click", confirmBoardRepair);
    element("go-board").addEventListener("pointerup", selectBoardPoint);
    element("side-repair-btn").addEventListener("click", function () {
      cancelEdit();
      const panel = element("side-repair-panel"); panel.hidden = !panel.hidden;
    });
    document.querySelectorAll("[data-side]").forEach(function (button) {
      button.addEventListener("click", function () { saveSideProposal(button.dataset.side); });
    });
    element("source-includes-answer").addEventListener("change", saveSourceIncludesAnswer);
    element("reconstruct-btn").addEventListener("click", saveReconstructionProposal);
    element("undo-btn").addEventListener("click", undoCurrent);
    element("previous-reviewed-btn").addEventListener("click", openPreviousReviewed);
    element("staged-list").addEventListener("click", function (event) {
      const open = event.target.closest("[data-open-group]");
      if (open) return openGroup(open.dataset.openGroup);
      const remove = event.target.closest("[data-delete-proposal]");
      if (remove) deleteProposal(remove.dataset.groupKey, remove.dataset.deleteProposal);
    });
    Object.keys(REASON_LABELS).forEach(function (reason) {
      const button = document.createElement("button"); button.className = "reason-chip"; button.dataset.reason = reason; button.textContent = REASON_LABELS[reason];
      button.addEventListener("click", function () { confirmReason(reason); });
      element("reason-grid").appendChild(button);
    });
    root.addEventListener("resize", function () {
      cancelAnimationFrame(runtime.resizeFrame);
      runtime.resizeFrame = requestAnimationFrame(drawBoard);
    });
    root.addEventListener("online", retryPendingOperations);
  }

  async function boot() {
    bindEvents();
    await reloadBootstrap(true);
    await retryPendingOperations();
  }

  function renderFatalError(error) {
    if (typeof document === "undefined") return;
    const loading = element("loading-screen");
    loading.innerHTML = `<div class="panel empty"><h2>審題佇列安全停止</h2><p class="muted">${escapeText(error && error.message ? error.message : error)}</p><p>沒有修改 SGF、題庫或玩家判題。</p></div>`;
    syncIndicator("error", "● 未載入");
  }

  return {
    boot,
    renderFatalError,
    boardGeometry,
    intersectionToCanvas,
    clientPointToIntersection,
    gtpCoordinate,
    pendingStorageKey,
    dedupePendingMutations,
    indexAfterSave,
    groupMatchesFilters,
    computeSummary,
  };
});
