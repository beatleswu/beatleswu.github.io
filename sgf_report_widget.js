(function (root) {
  'use strict';

  // A single, lightweight report control shared by every SGF-facing surface.
  // Pages may call SGFReportWidget.setContext() whenever their real question
  // runtime advances; the widget never invents a question identity.
  var state = { context: null, host: null, panel: null, status: null, admin: false, csrfHeader: null, csrfToken: null, stagedItemId: null };
  var reasons = [
    ['ALTERNATIVE_CORRECT_MOVE', '我認為這手也是正解'],
    ['SYSTEM_ANSWER_INCORRECT', '系統答案疑似錯誤'],
    ['QUESTION_CONTENT_PROBLEM', '題目內容有問題'],
    ['BOARD_OR_DISPLAY_PROBLEM', '棋盤或顯示問題'],
    ['OTHER', '其他']
  ];

  function isMainPracticeSurface(surface) {
    return surface === 'main_practice';
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

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch];
    });
  }

  function ensureHost() {
    if (state.host || !document.body) return state.host;
    var surface = document.body.getAttribute('data-sgf-report-surface');
    if (!surface) return null;
    var host = document.createElement('section');
    host.className = 'sgf-report-widget';
    host.dataset.sgfReportSurface = surface;
    host.setAttribute('aria-label', isMainPracticeSurface(surface) ? reportText('mk.problemReport.title', '回報題目問題') : 'SGF question report');
    host.innerHTML = '<button type="button" class="sgf-report-trigger" data-sgf-report-trigger>回報這題</button>' +
      '<div class="sgf-report-sheet" data-sgf-report-sheet hidden>' +
      '<strong>回報這題</strong><p class="sgf-report-context" data-sgf-report-context>請先載入題目</p>' +
      '<div class="sgf-report-reasons" data-sgf-report-reasons></div>' +
      '<textarea maxlength="1000" rows="3" data-sgf-report-comment placeholder="補充說明（可選）"></textarea>' +
      '<div class="sgf-report-actions"><button type="button" data-sgf-report-cancel>取消</button><button type="button" data-sgf-report-submit disabled>送出回報</button></div>' +
      '<div class="sgf-report-status" data-sgf-report-status role="status" aria-live="polite"></div>' +
      '<div class="sgf-admin-tools" data-sgf-admin-tools hidden><strong>管理員工作台</strong><div class="sgf-admin-actions"><button type="button" data-sgf-admin-direct>修正此題</button><button type="button" data-sgf-admin-direct-last hidden>把剛才這一手加入正解</button><button type="button" data-sgf-admin-flag>標記待審</button><select data-sgf-admin-repair aria-label="repair action"><option value="NEEDS_RESEARCH">需要研究</option><option value="ADD_ALTERNATIVE_CORRECT_MOVE">加入另解</option><option value="REMOVE_INCORRECT_ACCEPTED_MOVE">移除錯誤答案</option><option value="REPLACE_ANSWER">替換答案</option><option value="DISABLE_BROKEN_QUESTION">停用破題</option></select><button type="button" data-sgf-admin-stage>建立 staged 修正</button><button type="button" data-sgf-admin-retest hidden>重新測試本題</button></div><div class="sgf-admin-status" data-sgf-admin-status role="status" aria-live="polite"></div></div></div>';
    var mount = isMainPracticeSurface(surface) ? document.querySelector('#board-col') : document.body;
    (mount || document.body).appendChild(host);
    var style = document.createElement('style');
    style.textContent = '.sgf-report-widget{position:fixed;z-index:70;right:max(14px,env(safe-area-inset-right));bottom:max(14px,env(safe-area-inset-bottom));font:14px/1.4 system-ui,sans-serif;color:#17231d}.sgf-report-trigger{min-height:48px;border:1px solid #80622b;border-radius:999px;padding:0 16px;background:#fff7df;color:#3a2a12;font-weight:800;box-shadow:0 8px 24px rgba(0,0,0,.2);touch-action:manipulation}.sgf-report-sheet{width:min(360px,calc(100vw - 28px));margin-top:8px;padding:14px;border:1px solid #d6c59c;border-radius:16px;background:#fffdf7;box-shadow:0 16px 42px rgba(0,0,0,.28)}.sgf-report-sheet strong{display:block;font-size:16px}.sgf-report-context{margin:5px 0 10px;color:#695b42;font-size:12px}.sgf-report-reasons{display:grid;gap:7px}.sgf-report-reasons button,.sgf-report-actions button,.sgf-admin-actions button,.sgf-admin-actions select{min-height:44px;border:1px solid #c9b98e;border-radius:11px;background:#fff;color:#352914;padding:7px 10px;text-align:left;touch-action:manipulation}.sgf-report-reasons button[aria-pressed=true]{border-color:#2d8e59;background:#e6f5eb}.sgf-report-sheet textarea{display:block;width:100%;margin-top:10px;border:1px solid #c9b98e;border-radius:10px;padding:8px;resize:vertical}.sgf-report-actions,.sgf-admin-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:10px;flex-wrap:wrap}.sgf-report-actions button:last-child,.sgf-admin-actions button{background:#2d8e59;color:#fff;border-color:#2d8e59}.sgf-report-actions button:disabled{opacity:.5}.sgf-report-status,.sgf-admin-status{min-height:20px;margin-top:7px;color:#356c49;font-size:12px}.sgf-report-status.error,.sgf-admin-status.error{color:#a43125}.sgf-admin-tools{margin-top:14px;padding-top:12px;border-top:1px solid #d6c59c}.sgf-admin-tools strong{font-size:13px}.sgf-admin-actions select{max-width:100%;flex:1 1 150px}@media(max-width:600px){.sgf-report-widget{left:14px;right:14px}.sgf-report-trigger{width:100%}.sgf-report-sheet{width:100%}}' + (isMainPracticeSurface(surface) ? '.sgf-report-widget[data-sgf-report-surface="main_practice"]{position:static!important;inset:auto!important;right:auto!important;bottom:auto!important;width:min(100%,360px);margin:10px auto 0;z-index:2}.sgf-report-widget[data-sgf-report-surface="main_practice"] .sgf-report-trigger{width:100%}@media(max-width:600px){.sgf-report-widget[data-sgf-report-surface="main_practice"]{width:100%;margin-top:10px}}' : '');
    document.head.appendChild(style);
    state.host = host;
    state.panel = host.querySelector('[data-sgf-report-sheet]');
    state.status = host.querySelector('[data-sgf-report-status]');
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
    loadAdminCapabilities();
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
      if (tools) tools.hidden = false;
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
    var merged = {};
    Object.keys(next).forEach(function (key) { merged[key] = next[key]; });
    if (merged.question_id == null && state.context) merged.question_id = state.context.question_id;
    state.context = merged;
    var host = ensureHost();
    if (host) {
      host.querySelector('[data-sgf-report-context]').textContent = describeContext();
      var shortcut = host.querySelector('[data-sgf-admin-direct-last]');
      if (shortcut) shortcut.hidden = !(state.admin && merged.move);
    }
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
    var params = new URLSearchParams({ direct_question_id: String(state.context.question_id) });
    if (state.context.record_index != null) params.set('record_index', String(state.context.record_index));
    window.location.href = '/admin/sgf-answer-review?' + params.toString();
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

  root.SGFReportWidget = { setContext: setContext, open: function () { var host = ensureHost(); if (host) { state.panel.hidden = false; host.querySelector('[data-sgf-report-context]').textContent = describeContext(); } }, submit: submit, getContext: function () { return state.context; } };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ensureHost, { once: true }); else ensureHost();
})(window);
