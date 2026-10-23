-- PROPOSED ONLY. No runtime DDL; no production application in this worker.
-- Transactions must use the repository PostgreSQL qmark adapter / row mappings.
CREATE TABLE g076_nonmap_sessions (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    flow TEXT NOT NULL CHECK (flow IN ('practice','daily')),
    binding TEXT NOT NULL,
    step_index INTEGER NOT NULL DEFAULT 0,
    history_json TEXT NOT NULL DEFAULT '[]',
    state TEXT NOT NULL CHECK (state IN ('OPEN','SETTLED'))
);
CREATE TABLE g076_nonmap_events (
    session_id TEXT NOT NULL REFERENCES g076_nonmap_sessions(id),
    step_index INTEGER NOT NULL,
    request_hash TEXT NOT NULL,
    response_json TEXT NOT NULL,
    PRIMARY KEY (session_id, step_index)
);
