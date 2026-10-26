/* Server-step client. Product index.html activates only ordinary Practice. */
(function (global) {
  'use strict';
  function createClient({fetchImpl = global.fetch.bind(global), basePath = '/api/g076/nonmap'} = {}) {
    let binding = null, cursor = null, inflight = false, uncertain = null, settled = false;
    async function request(path, body) {
      const response = await fetchImpl(path, {
        method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
      });
      const value = await response.json();
      if (!response.ok) throw Object.assign(new Error(value.error || 'step_request_failed'), {status: response.status});
      return value;
    }
    function accept(value, opening) {
      if (!value || !['READY', 'CONTINUE', 'CORRECT', 'INCORRECT'].includes(value.status)
          || !Number.isInteger(value.step_index) || value.step_index < 0
          || (opening && value.status === 'CONTINUE')
          || (!opening && value.status === 'READY')) throw new Error('invalid_step_response');
      const terminal = ['CORRECT', 'INCORRECT'].includes(value.status);
      if (terminal ? !value.settlement?.submission_id : typeof value.step_nonce !== 'string') {
        throw new Error('missing_server_authority');
      }
      if (opening && !terminal && (value.board_only !== true || typeof value.content !== 'string')) {
        throw new Error('missing_private_board');
      }
      cursor = value;
      settled = terminal;
      uncertain = null;
      return value;
    }
    async function open(flow, attemptToken) {
      if (inflight) throw new Error('step_busy');
      // Clear old identity before fetching: a failed mode switch cannot keep
      // an earlier cursor alive. Resume must use server history, never a tree.
      binding = null; cursor = null; uncertain = null; settled = false;
      if (!['practice', 'daily', 'mistakes'].includes(flow) || typeof attemptToken !== 'string') {
        throw new Error('unsupported_step_flow');
      }
      inflight = true;
      try {
        const candidate = {flow, attempt_token: attemptToken};
        const value = accept(await request(basePath + '/steps/start', candidate), true);
        binding = candidate;
        return value;
      } finally { inflight = false; }
    }
    async function send(body) {
      inflight = true;
      uncertain = body;
      try {
        const value = await request(basePath + '/steps', body);
        if (value.step_index !== body.step_index + 1) throw new Error('unexpected_step_index');
        return accept(value, false);
      } finally { inflight = false; }
    }
    async function play(x, y) {
      if (inflight || uncertain) throw new Error('step_retry_required');
      if (!binding || !cursor || settled) throw new Error('step_not_active');
      if (!Number.isInteger(x) || !Number.isInteger(y) || x < 0 || y < 0) throw new Error('invalid_point');
      return send({...binding, step_index: cursor.step_index, step_nonce: cursor.step_nonce, move: {x, y}});
    }
    async function retry() {
      if (inflight || !uncertain) throw new Error('no_retryable_step');
      return send(uncertain);
    }
    return Object.freeze({open, play, retry});
  }
  global.GoOdysseyG076NonMapSteps = Object.freeze({createClient});
})(globalThis);
