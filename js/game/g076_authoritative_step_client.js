/* G076 isolated step-based Map Battle client adapter.
 * No answer tree, correctness claims, grade, XP, damage or settlement writes
 * may originate here. Browser adapter is not registered on the live page:
 * Owner rollout, authorized account E2E and iPad Safari remain separate.
 */
(function (global) {
  'use strict';

  function createClient({ fetcher, onState, onPlayerMove, onOpponentMove,
                          onSettlement, endpoint = '/api/adventure/map-battles/v2/steps' }) {
    if (typeof fetcher !== 'function') throw new Error('G076_REQUIRES_FETCH');
    let cursor = null;
    let attempt = null;
    let pending = false;
    let completed = false;
    let lastMove = null;

    async function request(url, body) {
      const response = await fetcher(url, {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(body),
      });
      const result = await response.json();
      if (!response.ok) {
        const error = new Error(result.error || 'g076_step_request_failed');
        error.code = result.error;
        error.status = response.status;
        throw error;
      }
      return result;
    }

    function state() {
      return Object.freeze({
        active: Boolean(attempt && cursor && !completed),
        busy: pending,
        completed,
        stepIndex: cursor && Number.isInteger(cursor.step_index) ? cursor.step_index : null,
      });
    }

    function notify() {
      if (typeof onState === 'function') onState(state());
    }

    async function open({ attemptId, submissionNonce }) {
      if (pending) throw new Error('G076_BUSY');
      if (!attemptId || !submissionNonce) throw new Error('G076_ATTEMPT_REQUIRED');
      pending = true;
      notify();
      try {
        const result = await request(endpoint + '/start', {
          attempt_id: attemptId, submission_nonce: submissionNonce,
        });
        if (!['READY','SETTLED'].includes(result.status)) {
          throw new Error('G076_INVALID_START_STATE');
        }
        attempt = { attemptId, submissionNonce };
        cursor = result.status === 'READY' ? {
          step_index: result.step_index, step_nonce: result.step_nonce,
        } : null;
        completed = result.status === 'SETTLED';
        lastMove = null;
        return result;
      } finally {
        pending = false;
        notify();
      }
    }

    async function play(x, y) {
      if (pending) throw new Error('G076_BUSY');
      if (!attempt || !cursor || completed) throw new Error('G076_NOT_ACTIVE');
      if (![x,y].every(v => Number.isInteger(v) && v >= 0 && v <= 24)) {
        throw new Error('G076_INVALID_POINT');
      }
      pending = true;
      notify();
      const issued = { ...cursor };
      const move = { x, y };
      lastMove = { issued, move };
      try {
        const result = await request(endpoint, {
          attempt_id: attempt.attemptId, submission_nonce: attempt.submissionNonce,
          step_index: issued.step_index, step_nonce: issued.step_nonce, move,
        });
        if (!['CONTINUE','CORRECT','INCORRECT'].includes(result.status)) {
          throw new Error('G076_INVALID_VERDICT');
        }
        if (typeof onPlayerMove === 'function') onPlayerMove(move, result);
        if (result.opponent_reply) {
          const [replyX, replyY] = result.opponent_reply;
          if (typeof onOpponentMove === 'function') {
            onOpponentMove({x:replyX,y:replyY}, result);
          }
        }
        if (result.status === 'CONTINUE') {
          if (!result.next_step_nonce || !Number.isInteger(result.step_index)) {
            throw new Error('G076_MISSING_SERVER_CURSOR');
          }
          cursor = { step_index: result.step_index,
                     step_nonce: result.next_step_nonce };
          lastMove = null;
        } else {
          if (!result.battle_settlement ||
              result.battle_settlement.accepted !== true) {
            throw new Error('G076_MISSING_AUTHORITATIVE_SETTLEMENT');
          }
          completed = true;
          cursor = null;
          if (typeof onSettlement === 'function') onSettlement(result.battle_settlement, result);
        }
        return result;
      } finally {
        pending = false;
        notify();
      }
    }

    async function retrySameStep() {
      if (!lastMove || pending || completed) throw new Error('G076_NO_RETRYABLE_STEP');
      // Network-retry proof comes from the unchanged server nonce and move;
      // never ask the user to substitute a different answer after timeout.
      const { issued, move } = lastMove;
      if (!cursor || issued.step_index !== cursor.step_index ||
          issued.step_nonce !== cursor.step_nonce) throw new Error('G076_STALE_RETRY');
      return play(move.x, move.y);
    }

    return Object.freeze({ open, play, retrySameStep, state });
  }

  global.GoOdysseyG076Steps = Object.freeze({createClient});
})(typeof window === 'object' ? window : globalThis);
