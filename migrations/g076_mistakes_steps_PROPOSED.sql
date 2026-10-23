-- PROPOSED ONLY. No product/production application authorized.
-- Requires the existing g076_nonmap_sessions/events proposal too.
CREATE TABLE g076_mistakes_attempts (
    user_id BIGINT NOT NULL,
    question_id BIGINT NOT NULL,
    slot_date TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    rights_hash TEXT NOT NULL,
    attempt_token TEXT NOT NULL,
    PRIMARY KEY (user_id, question_id, slot_date)
);

-- Additional required schema compatibility change (PROPOSED, NOT APPLIED):
-- Existing g076_nonmap_sessions flow constraint currently accepts only practice/daily.
-- A future owner-authorized migration must replace that constraint to include
-- mistakes and perform mixed-mode rollback tests BEFORE opening the flag.
-- ALTER TABLE g076_nonmap_sessions DROP CONSTRAINT g076_nonmap_sessions_flow_check;
-- ALTER TABLE g076_nonmap_sessions ADD CONSTRAINT g076_nonmap_sessions_flow_check
-- CHECK (flow IN ('practice','daily','mistakes'));
