-- G077 B1 PROPOSED ONLY. NOT EXECUTED. NOT PRODUCT ADMISSION.
-- Prerequisites in a disposable PostgreSQL database only:
--   migrations/g076_nonmap_steps_PROPOSED.sql
--   migrations/g076_mistakes_steps_PROPOSED.sql
-- review_log identity migration and canonical product tables are separate
-- prerequisites. This proposal does not install a settlement implementation.
-- Explicit expected constraint name: schema drift must abort, not be guessed.
BEGIN;
LOCK TABLE g076_nonmap_sessions IN ACCESS EXCLUSIVE MODE;
ALTER TABLE g076_nonmap_sessions
    DROP CONSTRAINT g076_nonmap_sessions_flow_check;
ALTER TABLE g076_nonmap_sessions
    ADD CONSTRAINT g076_nonmap_sessions_flow_check
    CHECK (flow IN ('practice', 'daily', 'mistakes'));
COMMIT;

-- Rollback design (NOT executed): turn the Mistakes gate off, drain writers,
-- inventory sessions/events/attempts, preserve receipts, then restore the
-- practice/daily constraint ONLY when no Mistakes rows remain under an
-- independently approved retention/reconciliation procedure. Do not delete
-- player history automatically. Flag rollback alone does not undo settlement.
