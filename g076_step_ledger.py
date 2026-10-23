"""G076 isolated server-owned step ledger for legacy Map Battle attempts.

No schema is auto-created in production. Feature and route stay OFF by default.
Callers own the SQL transaction. A final step delegates exactly once to the
existing authoritative Map Battle settlement, keeping HP/rewards in one writer.
"""
import hashlib
import hmac
import json
from typing import Any

from g076_server_step_authority import adjudicate_next_step, StepAuthorityUnavailable
from map_battle_runtime import (
    lookup_attempt_for_owner, _validate_submission_nonce, _attempt_expired,
    question_revision_for, settle_answer, RequestRejected,
)
from map_battle_persistence import load_authoritative_battle_state


class StepLedgerRejected(ValueError):
    def __init__(self, reason, status=409):
        super().__init__(reason)
        self.reason = reason
        self.status = status


def ensure_isolated_step_schema(conn):
    """MIGRATION HELPER FOR ISOLATED FIXTURES ONLY; never call from runtime."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS g076_step_sessions (
            attempt_id TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
            battle_id TEXT NOT NULL, question_id INTEGER NOT NULL,
            revision TEXT NOT NULL, step_index INTEGER NOT NULL DEFAULT 0,
            history_json TEXT NOT NULL DEFAULT '[]',
            state TEXT NOT NULL DEFAULT 'OPEN'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS g076_step_events (
            attempt_id TEXT NOT NULL, step_index INTEGER NOT NULL,
            request_hash TEXT NOT NULL, response_json TEXT NOT NULL,
            PRIMARY KEY (attempt_id, step_index)
        )
    """)


def _dict(row):
    return dict(row) if row is not None else None


def _one(conn, sql, values):
    return _dict(conn.execute(sql, values).fetchone())


def _raw_hmac(secret, *segments):
    if not isinstance(secret, (str, bytes)) or not secret:
        raise StepLedgerRejected("server_step_secret_unavailable", 503)
    key = secret.encode("utf-8") if isinstance(secret, str) else secret
    payload = "|".join(map(str, segments)).encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _nonce(secret, attempt, uid, index):
    return _raw_hmac(secret, "G076-v1", uid, attempt["id"],
                     attempt["question_revision"], index)


def _authorize(conn, *, uid, attempt_id, submission_nonce,
               question_loader, entitlement_admitter=None, now=None):
    if type(uid) is not int or uid < 1 or not isinstance(attempt_id, str):
        raise StepLedgerRejected("invalid_user_or_attempt", 400)
    attempt = lookup_attempt_for_owner(conn, user_id=uid, attempt_id=attempt_id)
    if not attempt:
        raise StepLedgerRejected("attempt_not_owned", 404)
    try:
        _validate_submission_nonce({"submission_nonce": submission_nonce}, attempt)
    except Exception as e:
        raise StepLedgerRejected("invalid_submission_nonce", 403) from e
    if _attempt_expired(attempt, now):
        raise StepLedgerRejected("attempt_expired", 409)
    if attempt.get("transform_id") != "identity":
        raise StepLedgerRejected("transform_unavailable_in_step_protocol", 409)
    question = question_loader(int(attempt["question_id"]))
    if not question or question_revision_for(question) != attempt["question_revision"]:
        raise StepLedgerRejected("stale_question_revision", 409)
    if entitlement_admitter:
        entitlement_admitter(conn, uid, question)
    return attempt, question


def _state(conn, uid, attempt):
    # Serialize all steps for this owner+attempt in PostgreSQL before judging
    # or touching the legacy Map Battle settlement. SQLite callers must own
    # BEGIN IMMEDIATE; the transaction is opened by the HTTP/fixture layer.
    statement = (
        "SELECT * FROM g076_step_sessions "
        "WHERE attempt_id=? AND user_id=? AND battle_id=?"
    )
    raw_conn = getattr(conn, "_conn", conn)
    if not raw_conn.__class__.__module__.startswith("sqlite3"):
        statement += " FOR UPDATE"
    return _one(conn, statement,
                (attempt["id"], uid, attempt["battle_id"]))


def _battle_open(conn, uid, attempt):
    battle = load_authoritative_battle_state(
        conn, user_id=uid, battle_id=str(attempt["battle_id"]))
    if (not battle or battle.get("state") != "OPEN" or
            int(battle["battle_revision"]) != int(attempt["battle_revision_at_issue"])):
        raise StepLedgerRejected("battle_stale_or_closed", 409)
    return battle


def open_steps(conn, *, uid, attempt_id, submission_nonce,
               question_loader, secret, entitlement_admitter=None, now=None):
    """Idempotently open the existing owned attempt; never reset progress."""
    attempt, question = _authorize(
        conn, uid=uid, attempt_id=attempt_id,
        submission_nonce=submission_nonce, question_loader=question_loader,
        entitlement_admitter=entitlement_admitter, now=now)
    state = _state(conn, uid, attempt)
    if state is None:
        if attempt.get("state") != "ISSUED":
            raise StepLedgerRejected("attempt_not_issuable")
        _battle_open(conn, uid, attempt)
        try:
            conn.execute(
                """INSERT INTO g076_step_sessions
                   (attempt_id,user_id,battle_id,question_id,revision,step_index,history_json,state)
                   VALUES (?,?,?,?,?,0,'[]','OPEN')""",
                (attempt["id"], uid, attempt["battle_id"],
                 attempt["question_id"], attempt["question_revision"]),
            )
        except Exception:
            # Race can only be resolved by the caller's transaction rollback
            # and retry; do not silently overwrite the concurrent writer.
            raise
        state = _state(conn, uid, attempt)
    if state["state"] != "OPEN":
        return {"status": "SETTLED", "step_index": state["step_index"],
                "retryable": False}
    _battle_open(conn, uid, attempt)
    return {"status": "READY", "step_index": state["step_index"],
            "step_nonce": _nonce(secret, attempt, uid, state["step_index"]),
            "question_id": state["question_id"], "board_size": attempt["board_size"]}


def submit_step(conn, *, uid, attempt_id, submission_nonce, step_index,
                step_nonce, move, question_loader, secret,
                entitlement_admitter=None, now=None,
                settlement_kwargs=None):
    """Mutate one step inside caller's atomic transaction.

    The client supplies ONLY one step. Previous moves are read from the
    server ledger. A terminal step settles the Map Battle once via the old
    canonical judge and battle transaction; nonterminal steps award nothing.
    """
    if type(step_index) is not int or not 0 <= step_index <= 100:
        raise StepLedgerRejected("invalid_step_index", 400)
    if (not isinstance(move, dict) or set(move) != {"x", "y"} or
            type(move["x"]) is not int or type(move["y"]) is not int):
        raise StepLedgerRejected("invalid_step_move", 400)
    attempt, question = _authorize(
        conn, uid=uid, attempt_id=attempt_id,
        submission_nonce=submission_nonce, question_loader=question_loader,
        entitlement_admitter=entitlement_admitter, now=now)
    expected = _nonce(secret, attempt, uid, step_index)
    if not isinstance(step_nonce, str) or not hmac.compare_digest(
            expected, step_nonce):
        raise StepLedgerRejected("step_nonce_invalid", 403)
    request_hash = _raw_hmac(secret, "G076-request", uid, attempt_id,
                             step_index, move["x"], move["y"])
    replay = _one(conn,
        "SELECT * FROM g076_step_events WHERE attempt_id=? AND step_index=?",
        (attempt_id, step_index))
    if replay:
        if not hmac.compare_digest(replay["request_hash"], request_hash):
            raise StepLedgerRejected("step_nonce_reused_with_different_move")
        response = json.loads(replay["response_json"])
        if response.get("status") == "CONTINUE":
            # Reconstruct the raw next-step token. A replay must NOT need
            # secret-bearing response JSON stored in the ledger.
            response["next_step_nonce"] = _nonce(
                secret, attempt, uid, step_index + 1)
        response["duplicate"] = True
        return response

    state = _state(conn, uid, attempt)
    if not state or state["state"] != "OPEN":
        raise StepLedgerRejected("step_session_missing_or_settled")
    if int(state["step_index"]) != step_index:
        raise StepLedgerRejected("stale_step_index")
    _battle_open(conn, uid, attempt)
    history = json.loads(state["history_json"])
    if not isinstance(history, list) or len(history) >= 100:
        raise StepLedgerRejected("bad_server_step_history")
    try:
        verdict = adjudicate_next_step(
            question, player_color=attempt["player_color"],
            board_size=int(attempt["board_size"]), trusted_history=history,
            move=(move["x"], move["y"]))
    except StepAuthorityUnavailable as e:
        raise StepLedgerRejected("step_judge_unavailable:" + str(e), 409) from e
    history.append([move["x"], move["y"]])
    terminal = verdict.status in ("CORRECT", "INCORRECT")
    response: dict[str, Any] = {
        "status": verdict.status, "reason": verdict.reason,
        "step_index": step_index + 1,
        "duplicate": False,
        "opponent_reply": list(verdict.opponent_reply)
        if verdict.opponent_reply else None,
    }
    if terminal:
        # Existing canonical settlement refuses client grades and writes
        # combat/reward exactly once. This is NOT a second battle writer.
        payload = {
            "battle_id": attempt["battle_id"],
            "attempt_id": attempt_id,
            "submission_nonce": submission_nonce,
            "battle_revision": int(attempt["battle_revision_at_issue"]),
            "question_revision": attempt["question_revision"],
            "player_color": attempt["player_color"],
            "transform_id": attempt["transform_id"],
            "transform_version": attempt["transform_version"],
            "moves": [{"x": x, "y": y} for x, y in history],
        }
        extra = dict(settlement_kwargs or {})
        extra.setdefault("mode_environ", {"E10_MAP_BATTLE_V1_MODE": "global"})
        if now is not None:
            extra["now"] = now
        result = settle_answer(
            conn, user_id=uid, payload=payload,
            question_loader=question_loader,
            entitlement_admitter=entitlement_admitter, **extra)
        if result.get("result") != verdict.status or result.get("accepted") is not True:
            raise StepLedgerRejected("step_battle_judge_disagreement", 503)
        response["battle_settlement"] = result
    else:
        # An accepted prefix never adjusts HP/XP/progression/SRS.
        response["next_step_nonce"] = _nonce(secret, attempt, uid, step_index + 1)
    cursor = conn.execute(
        """UPDATE g076_step_sessions SET step_index=?,history_json=?,state=?
            WHERE attempt_id=? AND user_id=? AND step_index=? AND state='OPEN'""",
        (step_index + 1, json.dumps(history), "SETTLED" if terminal else "OPEN",
         attempt_id, uid, step_index))
    if cursor.rowcount != 1:
        raise StepLedgerRejected("concurrent_step_conflict", 409)
    stored_response = dict(response)
    # Do not persist bearer-shaped next-step tokens, even encrypted or
    # hashed, in a materialized response; derive them on every retry.
    stored_response.pop("next_step_nonce", None)
    conn.execute(
        """INSERT INTO g076_step_events
           (attempt_id,step_index,request_hash,response_json) VALUES (?,?,?,?)""",
        (attempt_id, step_index, request_hash, json.dumps(stored_response)))
    return response
