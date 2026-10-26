-- G076-R2: PROPOSED PostgreSQL migration, NOT APPLIED to production.
-- Requires separate Owner production-data DDL gate, a verified backup,
-- and SQL/index compatibility against the exact deployed app schema.
-- Creates no test data; no player progress is touched.
-- Run in a controlled transaction ONLY after approval.

BEGIN;

CREATE TABLE IF NOT EXISTS g076_step_sessions (
    attempt_id      TEXT PRIMARY KEY,
    user_id         INTEGER NOT NULL,
    battle_id       TEXT NOT NULL,
    question_id     INTEGER NOT NULL,
    revision        TEXT NOT NULL,
    step_index      INTEGER NOT NULL DEFAULT 0,
    history_json    TEXT NOT NULL DEFAULT '[]',
    state           TEXT NOT NULL DEFAULT 'OPEN',
    CONSTRAINT g076_step_sessions_state_ck
      CHECK (state IN ('OPEN', 'SETTLED')),
    CONSTRAINT g076_step_sessions_index_ck
      CHECK (step_index BETWEEN 0 AND 100),
    CONSTRAINT g076_step_sessions_history_ck
      CHECK (length(history_json) <= 8192),
    CONSTRAINT g076_step_sessions_revision_ck
      CHECK (length(revision) > 0),
    CONSTRAINT g076_step_sessions_owner_attempt_fk
      FOREIGN KEY (user_id, battle_id, attempt_id)
      REFERENCES map_battle_attempts(user_id, battle_id, id)
      ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS g076_step_events (
    attempt_id    TEXT NOT NULL,
    step_index    INTEGER NOT NULL,
    request_hash  TEXT NOT NULL,
    response_json TEXT NOT NULL,
    CONSTRAINT g076_step_events_pk PRIMARY KEY (attempt_id, step_index),
    CONSTRAINT g076_step_events_step_ck CHECK (step_index BETWEEN 0 AND 99),
    CONSTRAINT g076_step_events_hash_ck CHECK (length(request_hash) = 64),
    CONSTRAINT g076_step_events_response_ck
      CHECK (length(response_json) <= 32768),
    CONSTRAINT g076_step_events_attempt_fk
      FOREIGN KEY (attempt_id) REFERENCES g076_step_sessions(attempt_id)
      ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_g076_step_sessions_owner_battle
  ON g076_step_sessions(user_id, battle_id, state);

COMMIT;

-- NOT a new gameplay source of truth: Map Battle HP, review_log, SRS and
-- progression remain exclusively in their established authoritative tables.
-- A G076 step is a single-writer pre-settlement cursor for an existing
-- map_battle_attempts row. Rollback procedure: preserve rows for audit first;
-- do not DROP after player traffic without explicit separate Owner consent.
