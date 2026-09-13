(function (root) {
  'use strict';

  // A single, lightweight report control shared by every SGF-facing surface.
  // Pages may call SGFReportWidget.setContext() whenever their real question
  // runtime advances; the widget never invents a question identity.
  var state = {
    context: null,
    host: null,
    panel: null,
    status: null,
    admin: false,
    csrfHeader: null,
    csrfToken: null,
    stagedItemId: null,
    locator: null,
    inline: {
      mode: null,
      pendingMove: null,
      side: null,
      originalSide: null,
      busy: false,
      status: '',
      error: false,
    },
  };
  var INLINE_ACTIONS = {
    CORRECT: 'CORRECT',
    REPLACE_ANSWER: 'REPLACE_ANSWER',
    ADD_ALTERNATIVE_CORRECT_MOVE: 'ADD_ALTERNATIVE_CORRECT_MOVE',
    EDIT_QUESTION: 'EDIT_QUESTION',
    UNSURE: 'UNSURE',
  };
  var reasons = [
    ['ALTERNATIVE_CORRECT_MOVE', '我認為這手也是正解'],
    ['SYSTEM_ANSWER_INCORRECT', '系統答案疑似錯誤'],
    ['QUESTION_CONTENT_PROBLEM', '題目內容有問題'],
    ['BOARD_OR_DISPLAY_PROBLEM', '棋盤或顯示問題'],
    ['OTHER', '其他']
  ];

  function inlineDirty() {
    return !!state.inline.mode && !state.inline.busy;
  }

  function inlineStatus(text, error) {
    state.inline.status = String(text || '');
    state.inline.error = !!error;
    renderInlineReview();
  }

  function clearInlineReview({ preserveStatus = false } = {}) {
    state.inline.mode = null;
    state.inline.pendingMove = null;
    state.inline.side = null;
    state.inline.originalSide = null;
    state.inline.busy = false;
    if (!preserveStatus) {
      state.inline.status = '';
      state.inline.error = false;
    }
    state.locator = null;
    root.dispatchEvent(new CustomEvent('sgf:inline-review-marker', { detail: { move: null } }));
    renderInlineReview();
  }

  function confirmInlineLeave() {
    if (!inlineDirty()) return true;
    return root.confirm('修改還沒儲存，要離開嗎？');
  }

  function transformReviewMove(move) {
    var context = state.context || {};
    if (!(context.displayCoordinates || (move && move.displayCoordinates)) || context.transform_index == null) return move;
    var x = Number(move && move.x), y = Number(move && move.y);
    var size = Number(context.board_size || 19);
    var t = Number(context.transform_index);
    if (!Number.isInteger(x) || !Number.isInteger(y) || !Number.isInteger(size)
      || size < 2 || size > 19 || t < 0 || t > 7) return null;
    var n = size - 1;
    var point;
    switch (t) {
      case 1: point = { x: y, y: n - x }; break;
      case 2: point = { x: n - x, y: n - y }; break;
      case 3: point = { x: n - y, y: x }; break;
      case 4: point = { x: n - x, y: y }; break;
      case 5: point = { x: x, y: n - y }; break;
      case 6: point = { x: y, y: x }; break;
      case 7: point = { x: n - y, y: n - x }; break;
      default: point = { x: x, y: y };
    }
    return point;
  }

  function currentQuestionId() {
    var id = Number(state.context && state.context.question_id);
    return Number.isFinite(id) && id > 0 ? id : null;
  }

  function reviewLocatorQuery() {
    var context = state.context || {};
    var params = new URLSearchParams();
    if (context.record_index != null && context.record_index !== '') {
      params.set('record_index', String(context.record_index));
    }
    var query = params.toString();
    return query ? '?' + query : '';
  }

  async function resolveAdminLocator() {
    var questionId = currentQuestionId();
    if (!state.admin || questionId == null) throw new Error('這題目前無法安全修改');
    var response = await fetch(
      '/api/admin/sgf-workbench/direct-context/' + encodeURIComponent(questionId) + reviewLocatorQuery(),
      { credentials: 'include', cache: 'no-store' },
    );
    var result = await response.json().catch(function () { return {}; });
    if (!response.ok || !result.ok || result.record_index == null || !result.predecessor_hash) {
      throw new Error('這題目前無法安全修改');
    }
    state.locator = result;
    state.context.record_index = result.record_index;
    return result;
  }

  function friendlyValidationError(result) {
    var errors = result && result.validation && result.validation.errors;
    var code = Array.isArray(errors) && errors.length ? String(errors[0]) : '';
    var messages = {
      candidate_not_accepted_by_runtime: '這個位置不是合法答案',
      removed_candidate_still_accepted_by_runtime: '這個答案仍會被系統判定為正解',
      canonical_content_basis_changed: '題目已被別人更新，請重新確認',
      canonical_record_basis_changed: '題目已被別人更新，請重新確認',
      original_question_content_changed: '題目已被別人更新，請重新確認',
      original_answer_state_changed: '答案已被別人更新，請重新確認',
      sgf_parse_failed: '題目格式需要重新檢查',
      question_content_missing: '題目內容目前無法安全修改',
      side_to_play_not_encoded: '先手設定目前無法安全修改',
    };
    return messages[code] || '檢查未通過，這次修改沒有儲存';
  }

  function isMainPracticeSurface(surface) {
    return surface === 'main_practice';
  }

  function isEmbeddedReviewSurface(surface) {
    return isMainPracticeSurface(surface) || surface === 'admin_questions';
  }

  function reportText(key, fallback) {
    var surface = document.body && document.body.getAttribute('data-sgf-report-surface');
    if (!isMainPracticeSurface(surface) || !root.I18n || typeof root.I18n.t !== 'function') return fallback;
    var value = root.I18n.t(key);
    return value && value !== key ? value : fallback;
  }

  function mainPracticeReasonLabels() {
    return [
      ['ALTERNATIVE_CORRECT_MOVE', reportText('mk.problemReport.reason.answer_seems_wrong', '答案疑似錯誤')],
      ['SYSTEM_ANSWER_INCORRECT', reportText('mk.problemReport.reason.answer_seems_wrong', '系統答案疑似錯誤')],
      ['QUESTION_CONTENT_PROBLEM', reportText('mk.problemReport.reason.broken_unanswerable', '題目內容有問題')],
      ['BOARD_OR_DISPLAY_PROBLEM', reportText('mk.problemReport.reason.display_glitch', '棋盤或顯示問題')],
      ['OTHER', reportText('mk.problemReport.reason.other', '其他')]
    ];
  }

  function isMainPracticeEnglish() {
    return document.body && isMainPracticeSurface(document.body.getAttribute('data-sgf-report-surface'))
      && root.I18n && typeof root.I18n.getLang === 'function' && root.I18n.getLang() === 'en';
  }

  function refreshMainPracticeLabels(host) {
    if (!host || !isMainPracticeSurface(host.getAttribute('data-sgf-report-surface'))) return;
    var setText = function (selector, key, fallback) {
      var node = host.querySelector(selector);
      if (node) node.textContent = reportText(key, fallback);
    };
    host.setAttribute('aria-label', reportText('mk.problemReport.title', '回報題目問題'));
    setText('[data-sgf-report-trigger]', 'mk.problemReport.trigger', '回報這題');
    setText('[data-sgf-report-sheet] strong', 'mk.problemReport.title', '回報題目問題');
    setText('[data-sgf-report-cancel]', 'mk.problemReport.close', '取消');
    setText('[data-sgf-report-submit]', 'mk.problemReport.submit', '送出回報');
    var comment = host.querySelector('[data-sgf-report-comment]');
    if (comment) comment.placeholder = reportText('mk.problemReport.notePlaceholder', '補充說明（可選）');
    var issueType = host.querySelector('[data-sgf-report-reasons]');
    if (issueType) issueType.setAttribute('aria-label', reportText('mk.problemReport.reasonLabel', '問題類型'));
    var labels = mainPracticeReasonLabels();
    host.querySelectorAll('[data-sgf-report-reasons] button').forEach(function (button) {
      var entry = labels.find(function (candidate) { return candidate[0] === button.dataset.reason; });
      if (entry) button.textContent = entry[1];
    });
    setText('[data-sgf-admin-tools] strong', 'mk.problemReport.title', '管理員工作台');
    setText('[data-sgf-admin-direct]', 'mk.problemReport.reason.display_glitch', isMainPracticeEnglish() ? 'Edit this question' : '修正此題');
    setText('[data-sgf-admin-direct-last]', 'mk.problemReport.reason.answer_seems_wrong', isMainPracticeEnglish() ? 'Add last move as correct' : '把剛才這一手加入正解');
    setText('[data-sgf-admin-flag]', 'mk.problemReport.submit', isMainPracticeEnglish() ? 'Flag for review' : '標記待審');
    setText('[data-sgf-admin-stage]', 'mk.problemReport.submit', isMainPracticeEnglish() ? 'Stage repair' : '建立 staged 修正');
    setText('[data-sgf-admin-retest]', 'mk.problemReport.submit', isMainPracticeEnglish() ? 'Retest this question' : '重新測試本題');
    var repair = host.querySelector('[data-sgf-admin-repair]');
    if (repair) repair.setAttribute('aria-label', isMainPracticeEnglish() ? 'Repair action' : 'repair action');
  }

  function inlineModeLabel(mode) {
    return mode === INLINE_ACTIONS.REPLACE_ANSWER ? '請在棋盤上點正確位置'
      : mode === INLINE_ACTIONS.ADD_ALTERNATIVE_CORRECT_MOVE ? '請在棋盤上點另一個正解'
      : mode === INLINE_ACTIONS.EDIT_QUESTION ? '請選擇要修改的先手'
      : '';
  }

  function renderInlineReview() {
    if (!state.host) return;
    var bar = state.host.querySelector('[data-sgf-inline-review-bar]');
    var panel = state.host.querySelector('[data-sgf-inline-review-panel]');
    var status = state.host.querySelector('[data-sgf-inline-review-status]');
    if (!bar || !panel) return;
    var visible = !!(state.admin && currentQuestionId() != null);
    bar.hidden = !visible;
    if (!visible) {
      panel.hidden = true;
      return;
    }
    var mode = state.inline.mode;
    panel.hidden = !mode && !state.inline.status;
    bar.querySelectorAll('[data-sgf-inline-action]').forEach(function (button) {
      button.disabled = !!state.inline.busy;
      button.setAttribute('aria-pressed', button.dataset.sgfInlineAction === mode ? 'true' : 'false');
    });
    var prompt = state.host.querySelector('[data-sgf-inline-review-prompt]');
    if (prompt) {
      var text = mode ? inlineModeLabel(mode) : '';
      if (mode && state.inline.pendingMove) {
        text += '（' + String.fromCharCode(65 + state.inline.pendingMove.x) + (state.inline.pendingMove.y + 1) + '）';
      }
      prompt.textContent = text;
    }
    var side = state.host.querySelector('[data-sgf-inline-side]');
    if (side) {
      side.hidden = mode !== INLINE_ACTIONS.EDIT_QUESTION;
      if (mode === INLINE_ACTIONS.EDIT_QUESTION && state.inline.side) side.value = state.inline.side;
    }
    var save = state.host.querySelector('[data-sgf-inline-save]');
    var saveNext = state.host.querySelector('[data-sgf-inline-save-next]');
    var needsMove = mode === INLINE_ACTIONS.REPLACE_ANSWER || mode === INLINE_ACTIONS.ADD_ALTERNATIVE_CORRECT_MOVE;
    var ready = !!mode && !state.inline.busy && (!needsMove || !!state.inline.pendingMove)
      && (mode !== INLINE_ACTIONS.EDIT_QUESTION || state.inline.side !== state.inline.originalSide);
    if (save) save.disabled = !ready;
    if (saveNext) saveNext.disabled = !ready;
    if (status) {
      status.textContent = state.inline.status || '';
      status.className = 'sgf-inline-review-status' + (state.inline.error ? ' error' : '');
    }
  }

  async function classifyInline(classification) {
    try {
      var locator = await resolveAdminLocator();
      var result = await adminPost('/api/admin/sgf-answer-review/v2a/reviews', {
        record_index: locator.record_index,
        legacy_question_id: locator.question_id,
        reviewed_record_sha256: locator.predecessor_hash,
        classification: classification,
      });
      if (!result || result.canonical_questions_mutated !== false) throw new Error('這題目前無法安全修改');
      inlineStatus(classification === 'CORRECT' ? '✓ 已儲存' : '已記為稍後處理', false);
    } catch (error) {
      inlineStatus(error.message || '這題目前無法安全修改', true);
    }
  }

  async function beginInlineAction(action) {
    if (!state.admin || currentQuestionId() == null || state.inline.busy) return;
    if (!confirmInlineLeave()) return;
    if (state.inline.mode) {
      root.dispatchEvent(new CustomEvent('sgf:inline-review-marker', { detail: { move: null } }));
    }
    state.inline.status = '';
    state.inline.error = false;
    state.inline.mode = null;
    state.inline.pendingMove = null;
    state.inline.side = null;
    state.inline.originalSide = null;
    if (action === INLINE_ACTIONS.CORRECT) return classifyInline('CORRECT');
    if (action === INLINE_ACTIONS.UNSURE) return classifyInline('UNSURE');
    try {
      var locator = await resolveAdminLocator();
      if (action === INLINE_ACTIONS.EDIT_QUESTION) {
        var content = String(locator.record && locator.record.content || '');
        var match = content.match(/(?:^|;)PL\[([BW])\]/i);
        state.inline.originalSide = (match && match[1] || 'B').toUpperCase();
        state.inline.side = state.inline.originalSide === 'B' ? 'W' : 'B';
      }
      state.inline.mode = action;
      state.inline.pendingMove = null;
      inlineStatus(inlineModeLabel(action), false);
    } catch (error) {
      inlineStatus(error.message || '這題目前無法安全修改', true);
    }
  }

  function consumeBoardMove(input) {
    var mode = state.inline.mode;
    if (mode !== INLINE_ACTIONS.REPLACE_ANSWER && mode !== INLINE_ACTIONS.ADD_ALTERNATIVE_CORRECT_MOVE) return false;
    var move = transformReviewMove(input || {});
    var max = Number((state.context || {}).board_size || 19) - 1;
    if (!move || move.x < 0 || move.y < 0 || move.x > max || move.y > max) {
      inlineStatus('這個位置不是合法答案', true);
      return true;
    }
    state.inline.pendingMove = { x: move.x, y: move.y };
    state.inline.status = '已選擇位置，請按儲存';
    state.inline.error = false;
    root.dispatchEvent(new CustomEvent('sgf:inline-review-marker', { detail: { move: state.inline.pendingMove } }));
    renderInlineReview();
    return true;
  }

  function mutationKey() {
    var base = [currentQuestionId(), state.context && state.context.record_index,
      state.inline.mode, state.inline.pendingMove && state.inline.pendingMove.x,
      state.inline.pendingMove && state.inline.pendingMove.y, state.inline.side].join(':');
    return 'inline-review:' + base + ':' + Date.now();
  }

  async function commitInlineEdit(advance) {
    var mode = state.inline.mode;
    if (!mode || state.inline.busy) return;
    var needsMove = mode === INLINE_ACTIONS.REPLACE_ANSWER || mode === INLINE_ACTIONS.ADD_ALTERNATIVE_CORRECT_MOVE;
    if ((needsMove && !state.inline.pendingMove)
      || (mode === INLINE_ACTIONS.EDIT_QUESTION && state.inline.side === state.inline.originalSide)) {
      inlineStatus(needsMove ? '請先在棋盤上選一個位置' : '請先選擇不同的先手', true);
      return;
    }
    state.inline.busy = true;
    renderInlineReview();
    try {
      var locator = state.locator || await resolveAdminLocator();
      var context = state.context || {};
      var issue = mode === INLINE_ACTIONS.ADD_ALTERNATIVE_CORRECT_MOVE
        ? 'ALTERNATIVE_CORRECT_MOVE'
        : mode === INLINE_ACTIONS.EDIT_QUESTION ? 'QUESTION_CONTENT_PROBLEM' : 'SYSTEM_ANSWER_INCORRECT';
      var flag = await adminPost('/api/admin/sgf-workbench/flag', {
        question_id: currentQuestionId(),
        record_index: locator.record_index,
        issue_type: issue,
        move: needsMove ? state.inline.pendingMove : null,
        surface: context.surface || 'admin_play',
        system_verdict: context.system_verdict || null,
        comment: 'INLINE_ADMIN_REVIEW',
        flag_id: mutationKey() + ':flag',
      });
      state.stagedItemId = flag.review_item_id;
      var stageBody = {
        action: mode === INLINE_ACTIONS.EDIT_QUESTION ? 'CHANGE_SIDE_TO_PLAY' : mode,
        candidate_move: needsMove ? state.inline.pendingMove : null,
        side_to_play: mode === INLINE_ACTIONS.EDIT_QUESTION ? state.inline.side : undefined,
        baseline_sha256: locator.content_sha256,
        mutation_key: mutationKey(),
        reason: 'INLINE_ADMIN_REVIEW',
      };
      var repair = await adminPost('/api/admin/sgf-workbench/items/' + encodeURIComponent(state.stagedItemId) + '/stage', stageBody);
      var validation = await adminPost('/api/admin/sgf-workbench/items/' + encodeURIComponent(state.stagedItemId) + '/validate', {
        repair_id: repair.repair && repair.repair.id,
      });
      if (validation.status !== 'PASS') throw new Error(friendlyValidationError(validation));
      state.inline.busy = false;
      state.inline.status = '✓ 已儲存修正版';
      state.inline.error = false;
      state.inline.mode = null;
      state.inline.pendingMove = null;
      state.inline.side = null;
      state.inline.originalSide = null;
      root.dispatchEvent(new CustomEvent('sgf:inline-review-marker', { detail: { move: null } }));
      renderInlineReview();
      if (advance && context.next_handler && typeof context.next_handler === 'function') {
        root.setTimeout(function () {
          try { context.next_handler(); } catch (_) {}
        }, 0);
      }
    } catch (error) {
      state.inline.busy = false;
      inlineStatus(error.message || '檢查未通過，這次修改沒有儲存', true);
    }
  }

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch];
    });
  }

  function ensureHost() {
    if (state.host && document.documentElement.contains(state.host)) return state.host;
    if (state.host && !document.documentElement.contains(state.host)) {
      state.host = null;
      state.panel = null;
      state.status = null;
    }
    if (!document.body) return state.host;
    var surface = document.body.getAttribute('data-sgf-report-surface');
    if (!surface) return null;
    if (surface === 'admin_questions' && !document.querySelector('#question-review-controls')) return null;
    var host = document.createElement('section');
    host.className = 'sgf-report-widget';
    host.dataset.sgfReportSurface = surface;
    host.setAttribute('aria-label', surface === 'admin_questions' ? '題目管理中心快速檢查' : (isMainPracticeSurface(surface) ? reportText('mk.problemReport.title', '回報題目問題') : 'SGF question report'));
    host.innerHTML = '<div class="sgf-inline-review-bar" data-sgf-inline-review-bar hidden>' +
      '<span class="sgf-inline-review-title">快速檢查</span>' +
      '<button type="button" data-sgf-inline-action="CORRECT">✓ 沒問題</button>' +
      '<button type="button" data-sgf-inline-action="REPLACE_ANSWER">✎ 改答案</button>' +
      '<button type="button" data-sgf-inline-action="EDIT_QUESTION">✎ 改題目</button>' +
      '<button type="button" data-sgf-inline-action="ADD_ALTERNATIVE_CORRECT_MOVE">＋ 補正解</button>' +
      '<button type="button" data-sgf-inline-action="UNSURE">⏭ 稍後</button>' +
      '</div>' +
      '<div class="sgf-inline-review-panel" data-sgf-inline-review-panel hidden>' +
      '<strong>快速修正</strong><p data-sgf-inline-review-prompt></p>' +
      '<select data-sgf-inline-side hidden aria-label="選擇先手"><option value="B">黑先</option><option value="W">白先</option></select>' +
      '<div class="sgf-inline-review-actions"><button type="button" data-sgf-inline-cancel>取消</button><button type="button" data-sgf-inline-save>儲存</button><button type="button" data-sgf-inline-save-next>儲存並下一題</button></div>' +
      '<div class="sgf-inline-review-status" data-sgf-inline-review-status role="status" aria-live="polite"></div>' +
      '</div>' +
      '<button type="button" class="sgf-report-trigger" data-sgf-report-trigger>回報這題</button>' +
      '<div class="sgf-report-sheet" data-sgf-report-sheet hidden>' +
      '<strong>回報這題</strong><p class="sgf-report-context" data-sgf-report-context>請先載入題目</p>' +
      '<div class="sgf-report-reasons" data-sgf-report-reasons></div>' +
      '<textarea maxlength="1000" rows="3" data-sgf-report-comment placeholder="補充說明（可選）"></textarea>' +
      '<div class="sgf-report-actions"><button type="button" data-sgf-report-cancel>取消</button><button type="button" data-sgf-report-submit disabled>送出回報</button></div>' +
      '<div class="sgf-report-status" data-sgf-report-status role="status" aria-live="polite"></div>' +
      '<div class="sgf-admin-tools" data-sgf-admin-tools hidden><strong>管理員工作台</strong><div class="sgf-admin-actions"><button type="button" data-sgf-admin-direct>修正此題</button><button type="button" data-sgf-admin-direct-last hidden>把剛才這一手加入正解</button><button type="button" data-sgf-admin-flag>標記待審</button><select data-sgf-admin-repair aria-label="repair action"><option value="NEEDS_RESEARCH">需要研究</option><option value="ADD_ALTERNATIVE_CORRECT_MOVE">加入另解</option><option value="REMOVE_INCORRECT_ACCEPTED_MOVE">移除錯誤答案</option><option value="REPLACE_ANSWER">替換答案</option><option value="DISABLE_BROKEN_QUESTION">停用破題</option></select><button type="button" data-sgf-admin-stage>建立 staged 修正</button><button type="button" data-sgf-admin-retest hidden>重新測試本題</button></div><div class="sgf-admin-status" data-sgf-admin-status role="status" aria-live="polite"></div></div></div>';
    var mount = surface === 'admin_questions'
      ? document.querySelector('#question-review-controls')
      : (isMainPracticeSurface(surface) ? document.querySelector('#board-col') : document.body);
    (mount || document.body).appendChild(host);
    var style = document.createElement('style');
    style.textContent = '.sgf-report-widget{position:fixed;z-index:70;right:max(14px,env(safe-area-inset-right));bottom:max(14px,env(safe-area-inset-bottom));font:14px/1.4 system-ui,sans-serif;color:#17231d}.sgf-inline-review-bar{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:8px;padding:8px;border:1px solid #b7d5c2;border-radius:14px;background:#f2fff5;box-shadow:0 8px 24px rgba(0,0,0,.18)}.sgf-inline-review-title{font-weight:800;margin-right:2px}.sgf-inline-review-bar button,.sgf-inline-review-actions button,.sgf-inline-review-panel select{min-height:44px;border:1px solid #9ec4aa;border-radius:10px;background:#fff;color:#173b28;padding:7px 10px;font-weight:700;touch-action:manipulation}.sgf-inline-review-bar button[aria-pressed=true]{background:#d8f2df;border-color:#2d8e59}.sgf-inline-review-bar button:disabled,.sgf-inline-review-actions button:disabled{opacity:.55}.sgf-inline-review-panel{width:min(380px,calc(100vw - 28px));margin-bottom:8px;padding:14px;border:1px solid #b7d5c2;border-radius:16px;background:#f8fff9;box-shadow:0 16px 42px rgba(0,0,0,.24)}.sgf-inline-review-panel strong{display:block;font-size:16px}.sgf-inline-review-panel p{margin:5px 0 10px;color:#356c49;font-size:13px}.sgf-inline-review-panel select{width:100%;margin-bottom:8px}.sgf-inline-review-actions{display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap}.sgf-inline-review-actions button:last-child{background:#2d8e59;color:#fff;border-color:#2d8e59}.sgf-inline-review-status{min-height:20px;margin-top:7px;color:#356c49;font-size:12px}.sgf-inline-review-status.error{color:#a43125}.sgf-report-trigger{min-height:48px;border:1px solid #80622b;border-radius:999px;padding:0 16px;background:#fff7df;color:#3a2a12;font-weight:800;box-shadow:0 8px 24px rgba(0,0,0,.2);touch-action:manipulation}.sgf-report-sheet{width:min(360px,calc(100vw - 28px));margin-top:8px;padding:14px;border:1px solid #d6c59c;border-radius:16px;background:#fffdf7;box-shadow:0 16px 42px rgba(0,0,0,.28)}.sgf-report-sheet strong{display:block;font-size:16px}.sgf-report-context{margin:5px 0 10px;color:#695b42;font-size:12px}.sgf-report-reasons{display:grid;gap:7px}.sgf-report-reasons button,.sgf-report-actions button,.sgf-admin-actions button,.sgf-admin-actions select{min-height:44px;border:1px solid #c9b98e;border-radius:11px;background:#fff;color:#352914;padding:7px 10px;text-align:left;touch-action:manipulation}.sgf-report-reasons button[aria-pressed=true]{border-color:#2d8e59;background:#e6f5eb}.sgf-report-sheet textarea{display:block;width:100%;margin-top:10px;border:1px solid #c9b98e;border-radius:10px;padding:8px;resize:vertical}.sgf-report-actions,.sgf-admin-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:10px;flex-wrap:wrap}.sgf-report-actions button:last-child,.sgf-admin-actions button{background:#2d8e59;color:#fff;border-color:#2d8e59}.sgf-report-actions button:disabled{opacity:.5}.sgf-report-status,.sgf-admin-status{min-height:20px;margin-top:7px;color:#356c49;font-size:12px}.sgf-report-status.error,.sgf-admin-status.error{color:#a43125}.sgf-admin-tools{margin-top:14px;padding-top:12px;border-top:1px solid #d6c59c}.sgf-admin-tools strong{font-size:13px}.sgf-admin-actions select{max-width:100%;flex:1 1 150px}@media(max-width:600px){.sgf-report-widget{left:14px;right:14px}.sgf-inline-review-bar{justify-content:stretch}.sgf-inline-review-bar button{flex:1 1 calc(50% - 8px)}.sgf-inline-review-panel,.sgf-report-sheet{width:100%}.sgf-report-trigger{width:100%}}' + (isEmbeddedReviewSurface(surface) ? '.sgf-report-widget[data-sgf-report-surface="main_practice"],.sgf-report-widget[data-sgf-report-surface="admin_questions"]{position:static!important;inset:auto!important;right:auto!important;bottom:auto!important;width:100%;margin:10px auto 0;z-index:2}.sgf-report-widget[data-sgf-report-surface="main_practice"] .sgf-report-trigger{width:100%}@media(max-width:600px){.sgf-report-widget[data-sgf-report-surface="main_practice"],.sgf-report-widget[data-sgf-report-surface="admin_questions"]{width:100%;margin-top:10px}}' : '')
      + (surface === 'admin_questions' ? '[data-sgf-report-surface="admin_questions"]{color:#eef3ee;font:14px/1.4 system-ui,"Noto Sans TC","PingFang TC",sans-serif}'
      + '[data-sgf-report-surface="admin_questions"] .sgf-inline-review-bar{margin:0;padding:14px;gap:8px;border:1px solid #25322b;border-radius:20px;background:linear-gradient(165deg,#1a2420,#121815);box-shadow:0 1px 0 rgba(255,255,255,.02) inset,0 10px 28px rgba(0,0,0,.28)}'
      + '[data-sgf-report-surface="admin_questions"] .sgf-inline-review-title{color:#9db2a4;font-weight:750;font-size:12px;text-transform:uppercase;letter-spacing:.04em;width:100%;margin:0 0 2px}'
      + '[data-sgf-report-surface="admin_questions"] .sgf-inline-review-bar button{flex:1 1 calc(20% - 8px);min-height:52px;border:1px solid #354438;border-radius:13px;background:#1e2921;color:#eef3ee;font-weight:700;font-size:13px}'
      + '[data-sgf-report-surface="admin_questions"] .sgf-inline-review-bar button:hover{border-color:#4fd39e}'
      + '[data-sgf-report-surface="admin_questions"] .sgf-inline-review-bar button[aria-pressed=true]{background:rgba(79,211,158,.16);border-color:#4fd39e;color:#4fd39e}'
      + '[data-sgf-report-surface="admin_questions"] .sgf-inline-review-bar button[data-sgf-inline-action=CORRECT][aria-pressed=true]{background:rgba(79,211,158,.22)}'
      + '[data-sgf-report-surface="admin_questions"] .sgf-inline-review-bar button:disabled{opacity:.4}'
      + '[data-sgf-report-surface="admin_questions"] .sgf-inline-review-panel{width:100%;margin:10px 0 0;padding:16px;border:1px solid #25322b;border-radius:20px;background:linear-gradient(165deg,#1a2420,#121815);box-shadow:0 1px 0 rgba(255,255,255,.02) inset,0 10px 28px rgba(0,0,0,.28)}'
      + '[data-sgf-report-surface="admin_questions"] .sgf-inline-review-panel strong{color:#e9c17a;font-size:13px;text-transform:uppercase;letter-spacing:.03em}'
      + '[data-sgf-report-surface="admin_questions"] .sgf-inline-review-panel p{color:#9db2a4;font-size:13.5px}'
      + '[data-sgf-report-surface="admin_questions"] .sgf-inline-review-panel select{background:#171f1a;border:1px solid #354438;color:#eef3ee;border-radius:12px;min-height:48px}'
      + '[data-sgf-report-surface="admin_questions"] .sgf-inline-review-actions button{min-height:52px;border-radius:13px;font-weight:750;font-size:14px}'
      + '[data-sgf-report-surface="admin_questions"] .sgf-inline-review-actions button[data-sgf-inline-cancel]{flex:0 1 auto;background:transparent;border:1px solid #354438;color:#9db2a4}'
      + '[data-sgf-report-surface="admin_questions"] .sgf-inline-review-actions button[data-sgf-inline-save]{flex:1 1 120px;background:#1e2921;border:1px solid #354438;color:#eef3ee}'
      + '[data-sgf-report-surface="admin_questions"] .sgf-inline-review-actions button[data-sgf-inline-save-next]{flex:2 1 200px;background:#39b585;border:1px solid #39b585;color:#04140d;box-shadow:0 8px 20px rgba(57,181,133,.28)}'
      + '[data-sgf-report-surface="admin_questions"] .sgf-inline-review-actions button:disabled{opacity:.4;box-shadow:none}'
      + '[data-sgf-report-surface="admin_questions"] .sgf-inline-review-status{color:#9db2a4;font-size:13px;font-weight:600}'
      + '[data-sgf-report-surface="admin_questions"] .sgf-inline-review-status.error{color:#f1897d}'
      + '@media(max-width:640px){[data-sgf-report-surface="admin_questions"] .sgf-inline-review-bar button{flex:1 1 calc(50% - 8px)}}'
      : '');
    document.head.appendChild(style);
    state.host = host;
    state.panel = host.querySelector('[data-sgf-report-sheet]');
    state.status = host.querySelector('[data-sgf-report-status]');
    host.querySelectorAll('[data-sgf-inline-action]').forEach(function (button) {
      button.addEventListener('click', function () {
        beginInlineAction(button.dataset.sgfInlineAction);
      });
    });
    host.querySelector('[data-sgf-inline-cancel]').addEventListener('click', function () {
      if (confirmInlineLeave()) clearInlineReview();
    });
    host.querySelector('[data-sgf-inline-save]').addEventListener('click', function () {
      commitInlineEdit(false);
    });
    host.querySelector('[data-sgf-inline-save-next]').addEventListener('click', function () {
      commitInlineEdit(true);
    });
    host.querySelector('[data-sgf-inline-side]').addEventListener('change', function (event) {
      state.inline.side = event.target.value === 'W' ? 'W' : 'B';
      renderInlineReview();
    });
    var reasonsHost = host.querySelector('[data-sgf-report-reasons]');
    (isMainPracticeSurface(surface) ? mainPracticeReasonLabels() : reasons).forEach(function (entry) {
      var button = document.createElement('button');
      button.type = 'button'; button.dataset.reason = entry[0]; button.textContent = entry[1];
      button.addEventListener('click', function () {
        reasonsHost.querySelectorAll('button').forEach(function (node) { node.setAttribute('aria-pressed', node === button ? 'true' : 'false'); });
        host.querySelector('[data-sgf-report-submit]').disabled = !state.context;
      });
      reasonsHost.appendChild(button);
    });
    refreshMainPracticeLabels(host);
    if (isMainPracticeSurface(surface)) {
      document.addEventListener('e9:i18n-changed', function () { refreshMainPracticeLabels(host); });
    }
    host.querySelector('[data-sgf-report-trigger]').addEventListener('click', function () {
      state.panel.hidden = !state.panel.hidden;
      if (!state.panel.hidden) host.querySelector('[data-sgf-report-context]').textContent = describeContext();
    });
    host.querySelector('[data-sgf-report-cancel]').addEventListener('click', function () { state.panel.hidden = true; });
    host.querySelector('[data-sgf-report-submit]').addEventListener('click', submit);
    host.querySelector('[data-sgf-admin-flag]').addEventListener('click', flagForReview);
    host.querySelector('[data-sgf-admin-direct]').addEventListener('click', openDirectWorkbench);
    host.querySelector('[data-sgf-admin-direct-last]').addEventListener('click', directApplyLastMove);
    host.querySelector('[data-sgf-admin-stage]').addEventListener('click', stageRepair);
    host.querySelector('[data-sgf-admin-retest]').addEventListener('click', retestStaged);
    if (surface === 'admin_questions') {
      host.querySelector('[data-sgf-report-trigger]').hidden = true;
      host.querySelector('[data-sgf-admin-tools]').hidden = true;
    }
    loadAdminCapabilities();
    renderInlineReview();
    return host;
  }

  async function loadAdminCapabilities() {
    try {
      var me = await fetch('/api/auth/me', { credentials: 'include', cache: 'no-store' }).then(function (response) { return response.json(); });
      if (!me || !me.is_admin) return;
      var bootstrap = await fetch('/api/admin/sgf-workbench/bootstrap', { credentials: 'include', cache: 'no-store' }).then(function (response) { return response.json(); });
      if (!bootstrap || !bootstrap.security) return;
      state.admin = true; state.csrfHeader = bootstrap.security.csrf_header; state.csrfToken = bootstrap.security.csrf_token;
      var tools = state.host.querySelector('[data-sgf-admin-tools]');
      if (tools && document.body.getAttribute('data-sgf-report-surface') !== 'admin_questions') tools.hidden = false;
      renderInlineReview();
    } catch (error) { /* unauthenticated players receive only the report control */ }
  }

  function describeContext() {
    var c = state.context || {};
    if (isMainPracticeEnglish()) {
      return c.question_id == null ? 'Question details will appear after a question loads' :
        'Question #' + c.question_id + (c.move ? ' · Move ' + (c.move.gtp || (c.move.x + ',' + c.move.y)) : '') +
        (c.system_verdict ? ' · System verdict ' + c.system_verdict : '');
    }
    return c.question_id == null ? '題目載入後即可自動帶入題號、落子與判定' :
      '題目 #' + c.question_id + (c.move ? ' · 落子 ' + (c.move.gtp || (c.move.x + ',' + c.move.y)) : '') +
      (c.system_verdict ? ' · 系統判定 ' + c.system_verdict : '');
  }

  function setContext(next) {
    next = next || {};
    var previous = state.context || {};
    var merged = {};
    Object.keys(next).forEach(function (key) { merged[key] = next[key]; });
    if (merged.question_id == null && state.context) merged.question_id = state.context.question_id;
    var changedQuestion = previous.question_id != null
      && (String(previous.question_id) !== String(merged.question_id)
        || String(previous.record_index ?? '') !== String(merged.record_index ?? ''));
    if (changedQuestion) clearInlineReview();
    state.context = merged;
    var host = ensureHost();
    if (host) {
      host.querySelector('[data-sgf-report-context]').textContent = describeContext();
      var shortcut = host.querySelector('[data-sgf-admin-direct-last]');
      if (shortcut) shortcut.hidden = !(state.admin && merged.move);
    }
    renderInlineReview();
    root.dispatchEvent(new CustomEvent('sgf:report-context', { detail: merged }));
    return merged;
  }

  function adminPayload() {
    var payload = {};
    Object.keys(state.context || {}).forEach(function (key) { payload[key] = state.context[key]; });
    payload.question_id = Number(payload.question_id);
    payload.surface = payload.surface || document.body.getAttribute('data-sgf-report-surface') || 'admin_play';
    payload.comment = state.host.querySelector('[data-sgf-report-comment]').value.slice(0, 1000);
    return payload;
  }

  async function adminPost(path, body) {
    var headers = { 'Content-Type': 'application/json', 'Accept': 'application/json' };
    if (state.csrfHeader && state.csrfToken) headers[state.csrfHeader] = state.csrfToken;
    var response = await fetch(path, { method: 'POST', credentials: 'include', headers: headers, body: JSON.stringify(body) });
    var result = await response.json().catch(function () { return {}; });
    if (!response.ok || !result.ok) throw new Error(result.error || '管理員工作台操作失敗');
    return result;
  }

  function setAdminStatus(text, error) {
    var target = state.host && state.host.querySelector('[data-sgf-admin-status]');
    if (!target) return;
    target.className = 'sgf-admin-status' + (error ? ' error' : ''); target.textContent = text;
  }

  async function flagForReview() {
    if (!state.admin || !state.context || state.context.question_id == null) return;
    try {
      var result = await adminPost('/api/admin/sgf-workbench/flag', adminPayload());
      state.stagedItemId = result.review_item_id;
      setAdminStatus('已建立 ADMIN_PLAY 待審項目。', false);
    } catch (error) { setAdminStatus(error.message || '標記失敗', true); }
  }

  function openDirectWorkbench() {
    if (!state.admin || !state.context || state.context.question_id == null) return;
    var params = new URLSearchParams({ question_id: String(state.context.question_id) });
    if (state.context.record_index != null) params.set('record_index', String(state.context.record_index));
    window.location.href = '/admin/questions?' + params.toString();
  }

  async function directApplyLastMove() {
    if (!state.admin || !state.context || !state.context.question_id || !state.context.move) return;
    try {
      var context = await fetch('/api/admin/sgf-workbench/direct-context/' + encodeURIComponent(state.context.question_id) + '?record_index=' + encodeURIComponent(state.context.record_index == null ? '' : state.context.record_index), { credentials: 'include' }).then(function (response) { return response.json(); });
      if (!context || !context.direct_apply_enabled) throw new Error('目前環境尚未開啟管理員直接套用');
      var result = await adminPost('/api/admin/sgf-workbench/direct-apply', {
        question_id: Number(state.context.question_id), record_index: Number(context.record_index),
        predecessor_hash: context.predecessor_hash,
        canonical_source_sha256: context.canonical_source_sha256,
        retest_moves: [state.context.move], action: 'ADD_ALTERNATIVE_CORRECT_MOVE',
        candidate_move: state.context.move, operation_id: 'admin-play-direct:' + Date.now() + ':' + Math.random().toString(16).slice(2)
      });
      setAdminStatus('修改已套用。已保存上一版本，可回到審題工作台重測。', false);
      state.host.querySelector('[data-sgf-admin-direct-last]').hidden = true;
      state.host.querySelector('[data-sgf-admin-retest]').hidden = false;
      state.directVersion = result.version;
    } catch (error) { setAdminStatus(error.message || '直接套用失敗', true); }
  }

  async function stageRepair() {
    if (!state.admin || !state.context || state.context.question_id == null) return;
    try {
      var flag = state.stagedItemId ? { review_item_id: state.stagedItemId } : await adminPost('/api/admin/sgf-workbench/flag', adminPayload());
      state.stagedItemId = flag.review_item_id;
      var action = state.host.querySelector('[data-sgf-admin-repair]').value;
      var repair = await adminPost('/api/admin/sgf-workbench/items/' + state.stagedItemId + '/stage', { action: action, candidate_move: state.context.move || state.context.reported_move || null, reason: adminPayload().comment });
      state.host.querySelector('[data-sgf-admin-retest]').hidden = !repair.staged;
      setAdminStatus('已儲存 STAGED 修正，Production 未變更。', false);
    } catch (error) { setAdminStatus(error.message || '建立 staged 修正失敗', true); }
  }

  async function retestStaged() {
    if (!state.admin || !state.stagedItemId) return;
    var moves = Array.isArray(state.context.moves) && state.context.moves.length ? state.context.moves : (state.context.move ? [state.context.move] : []);
    if (!moves.length) { setAdminStatus('目前題面沒有可重播的落子序列。', true); return; }
    try {
      var result = await adminPost('/api/admin/sgf-workbench/items/' + state.stagedItemId + '/retest', { moves: moves });
      setAdminStatus('Production: ' + result.production_verdict + ' · Staged: ' + result.staged_verdict, false);
    } catch (error) { setAdminStatus(error.message || '重測失敗', true); }
  }

  async function submit() {
    var host = ensureHost();
    var selected = host && host.querySelector('[data-sgf-report-reasons] button[aria-pressed="true"]');
    if (!state.context || !selected) return;
    var status = state.status;
    status.className = 'sgf-report-status'; status.textContent = reportText('mk.problemReport.sending', '送出中…');
    var payload = {};
    Object.keys(state.context).forEach(function (key) { payload[key] = state.context[key]; });
    payload.reason = selected.dataset.reason;
    payload.comment = host.querySelector('[data-sgf-report-comment]').value.slice(0, 1000);
    payload.surface = payload.surface || document.body.getAttribute('data-sgf-report-surface') || 'unknown';
    try {
      var response = await fetch('/api/question/report', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' }, body: JSON.stringify(payload) });
      var result = await response.json().catch(function () { return {}; });
      if (!response.ok || !result.ok) throw new Error(result.error || '回報失敗');
      status.textContent = reportText('mk.problemReport.sent', '已送出，證據會交由管理員審核。');
      host.querySelector('[data-sgf-report-comment]').value = '';
      host.querySelectorAll('[data-sgf-report-reasons] button').forEach(function (node) { node.setAttribute('aria-pressed', 'false'); });
      host.querySelector('[data-sgf-report-submit]').disabled = true;
    } catch (error) {
      status.className = 'sgf-report-status error'; status.textContent = error.message || reportText('mk.problemReport.fail', '回報失敗');
    }
  }

  root.addEventListener('beforeunload', function (event) {
    if (!inlineDirty()) return;
    event.preventDefault();
    event.returnValue = '修改還沒儲存，要離開嗎？';
  });
  document.addEventListener('click', function (event) {
    if (!inlineDirty()) return;
    var target = event.target && event.target.closest ? event.target.closest('a,button') : null;
    if (!target || (state.host && state.host.contains(target))) return;
    if (!target.matches('.btn-nav, .nav-link, [data-sgf-next], [data-next-question], a')) return;
    if (!confirmInlineLeave()) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);
  root.SGFReportWidget = {
    mount: ensureHost,
    setContext: setContext,
    consumeBoardMove: consumeBoardMove,
    open: function () { var host = ensureHost(); if (host) { state.panel.hidden = false; host.querySelector('[data-sgf-report-context]').textContent = describeContext(); } },
    submit: submit,
    getContext: function () { return state.context; },
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ensureHost, { once: true }); else ensureHost();
})(window);
