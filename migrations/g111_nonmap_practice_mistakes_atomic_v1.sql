-- G111 isolated candidate: atomic Nonmap/Practice/Mistakes additive schema.
-- Strict new installs only: no IF NOT EXISTS; controlled by caller transaction.
-- NOT APPROVED for Oracle DDL or migration of any existing user records.
-- Mutually exclusive with running original G076/G079 one-off proposed scripts.
CREATE TABLE g076_nonmap_sessions (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    flow TEXT NOT NULL CHECK (flow IN ('practice', 'daily', 'mistakes')),
    binding TEXT NOT NULL,
    step_index INTEGER NOT NULL DEFAULT 0,
    history_json TEXT NOT NULL DEFAULT '[]',
    state TEXT NOT NULL CHECK (state IN ('OPEN', 'SETTLED'))
);

CREATE TABLE g076_nonmap_events (
    session_id TEXT NOT NULL REFERENCES g076_nonmap_sessions(id),
    step_index INTEGER NOT NULL,
    request_hash TEXT NOT NULL,
    response_json TEXT NOT NULL,
    PRIMARY KEY (session_id, step_index)
);

CREATE TABLE g076_practice_attempts (
    user_id BIGINT NOT NULL,
    question_id BIGINT NOT NULL,
    slot_date TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    attempt_token TEXT NOT NULL,
    PRIMARY KEY (user_id, question_id, slot_date)
);

CREATE TABLE g076_mistakes_attempts (
    user_id BIGINT NOT NULL,
    question_id BIGINT NOT NULL,
    slot_date TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    rights_hash TEXT NOT NULL,
    attempt_token TEXT NOT NULL,
    PRIMARY KEY (user_id, question_id, slot_date)
);
