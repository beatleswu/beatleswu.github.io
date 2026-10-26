-- DOCUMENTATION ONLY / PROPOSED / NOT A MIGRATION / NOT EXECUTED.
-- No application bootstrap, deploy hook or schema installer references this.
-- Current GrimoireSteps explicitly REJECTS PostgreSQL connections. These are
-- interface design statements, not an implemented PG transaction adapter.
-- MASTER must review schema/rights/global + mode gates and authorize integration.

-- Existing node_mastery, player_grimoire_progress, daily_training_cache and
-- grimoires remain separately owned. Do NOT recreate/alter them from this file.
-- A trusted importer would freeze the COMPLETE questions.json membership in
-- the SAME database. No runtime JSON file or separate DB read during settlement.
CREATE TABLE g076_grimoire_catalog_members (
    question_id BIGINT PRIMARY KEY,
    grimoire_id BIGINT NOT NULL
);
-- No importer is supplied or run. This projection requires provenance of the
-- exact questions.json SHA and DB catalog snapshot. Missing projection => HOLD.

CREATE TABLE g076_grimoire_attempts (
    token TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    scope TEXT NOT NULL,
    question_id BIGINT NOT NULL,
    binding TEXT NOT NULL,
    expires BIGINT NOT NULL,
    step_index INTEGER NOT NULL DEFAULT 0,
    history TEXT NOT NULL DEFAULT '[]',
    state TEXT NOT NULL DEFAULT 'OPEN',
    UNIQUE (user_id, scope)
);
CREATE TABLE g076_grimoire_events (
    token TEXT NOT NULL REFERENCES g076_grimoire_attempts(token),
    step_index INTEGER NOT NULL,
    request_hash TEXT NOT NULL,
    response TEXT NOT NULL,
    PRIMARY KEY (token, step_index)
);
-- A per-owner lock is required in addition to attempt locks: two distinct
-- tokens can update the same first mastery/progress/cache row concurrently.
CREATE TABLE g076_grimoire_settlement_owners (
    user_id BIGINT PRIMARY KEY
);

-- Transaction pseudocode; :uid/:token are documentation parameters.
-- BEGIN;
-- INSERT INTO g076_grimoire_settlement_owners(user_id) VALUES (:uid)
--   ON CONFLICT DO NOTHING;
-- SELECT user_id FROM g076_grimoire_settlement_owners
--   WHERE user_id=:uid FOR UPDATE;
-- SELECT * FROM g076_grimoire_attempts
--   WHERE token=:token AND user_id=:uid FOR UPDATE;
-- Revalidate expiry, rights, full q binding (including catalog digest), nonce.
-- Serialize/protect catalog publication against settlement: per-owner locks
-- alone DO NOT prevent a concurrent catalog importer from changing membership.
-- Proposed PG publication barrier: reader SHARE table locks on grimoires and
-- g076_grimoire_catalog_members; importer requires conflicting EXCLUSIVE locks.
-- Acquire in that fixed order in ALL participating code. Importer and snapshot
-- lifecycle are unimplemented and require independent review.
-- Recompute digest with canonical JSON of sorted [id,node_count] and
-- [question_id,grimoire_id]; require q.g076_catalog_revision equality.
-- Read existing event: matching hash => reuse; different hash => reject.
-- Judge server move; if terminal, write unchanged node formula, aggregate,
-- single-step rank/counters and cache membership append on THIS connection.
-- Then update terminal attempt and insert replay event; COMMIT before response.
-- Any failure, including COMMIT => ROLLBACK and publish no success.
-- No ensure_node_mastery_table() here: legacy helper commits inside the call.
-- No get_ldb()/get_sdb() nested connections or external rewards/XP/SRS writes.
-- NOT_EXECUTED: PG DDL, SELECT FOR UPDATE, PG rollback and PG concurrency proof.
