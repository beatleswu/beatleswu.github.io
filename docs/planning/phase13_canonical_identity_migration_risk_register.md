# Phase 13B Canonical Puzzle Identity Migration Risk Register

Phase: 13B
Status: Risk register contract baseline
Scope: Planning / contract baseline only
Runtime impact: None
Database impact: None
API impact: None
Frontend impact: None
SGF corpus impact: None

## Purpose

This risk register identifies known risks before any future migration or
implementation that persists `canonical_puzzle_id` or connects teacher admin
review queue records to canonical puzzle identity.

Phase 13B is not a DB implementation phase.

It is a risk-control contract for future C-level work.

## Owner Decision Being Protected

The future canonical puzzle identity is:

```text
canonical_puzzle_id = ingestion-generated stable UUID v4
```

The following are not canonical puzzle identity:

```text
source_path
fixture_path
gold_fixture_id
frontend temporary ID
runtime state
content hash
auto-increment integer as the primary canonical identity
```

## Risk Register

### R1 UUID Backfill Collision Risk

Risk:

```text
Existing puzzle records may receive duplicate UUIDs or inconsistent UUID
assignments during migration.
```

Mitigation:

```text
Require uuid_backfill_plan_gate.
Require uniqueness verification.
Require post-migration duplicate scan.
Require owner approval before migration.
```

Phase 13 action:

```text
Document only. No UUID backfill is performed.
```

### R2 Unique Constraint Rollout Risk

Risk:

```text
Adding a uniqueness constraint too early may fail if duplicate or missing
canonical_puzzle_id values exist.
```

Mitigation:

```text
Require staged verification before constraint enforcement.
Require dry-run duplicate detection.
Require rollback or forward-fix strategy.
```

Phase 13 action:

```text
Document only. No constraint is added.
```

### R3 Foreign Key / Reference Integrity Risk

Risk:

```text
Review queue items, feedback reports, owner decision traces, or future frontend
references may point to missing or unstable puzzle records.
```

Mitigation:

```text
Require foreign_key_reference_plan_gate.
Require orphan reference checks.
Require post-migration verification.
```

Phase 13 action:

```text
Document only. No foreign key is created.
```

### R4 Source Path Identity Regression Risk

Risk:

```text
Future implementation may accidentally treat source_path as canonical identity.
```

Mitigation:

```text
Keep source_path as provenance metadata only.
Require tests that reject source_path as canonical identity.
```

Phase 13 action:

```text
Document and test contract boundary only.
```

### R5 Fixture Identity Regression Risk

Risk:

```text
Future implementation may accidentally treat fixture_path or gold_fixture_id as
canonical identity.
```

Mitigation:

```text
Keep fixture references as test artifacts or audit references only.
Require tests that reject fixture identity as canonical puzzle identity.
```

Phase 13 action:

```text
Document and test contract boundary only.
```

### R6 Content Hash Identity Regression Risk

Risk:

```text
Future implementation may accidentally treat content hash as the primary
canonical identity.
```

Mitigation:

```text
Allow content hash only as audit fingerprint or import diagnostic.
Reject content hash as primary canonical identity.
```

Phase 13 action:

```text
Document and test contract boundary only.
```

### R7 Auto-Increment Identity Regression Risk

Risk:

```text
Future implementation may accidentally use an auto-increment integer as the
primary canonical identity.
```

Mitigation:

```text
Allow database integers only as internal storage implementation details if
needed.
Reject auto-increment integer as the primary canonical puzzle identity.
```

Phase 13 action:

```text
Document and test contract boundary only.
```

### R8 Review Queue Unsafe Transition Risk

Risk:

```text
A teacher admin flow may directly promote candidate_only_disabled to
ready_readonly.
```

Mitigation:

```text
Keep candidate_only_disabled -> ready_readonly blocked.
Require high-risk owner decision flow.
Require frontend review flow safety gate.
```

Phase 13 action:

```text
Document and test contract boundary only.
```

### R9 GF-003 Accidental Activation Risk

Risk:

```text
GF-003 / 431.sgf B[sd] / T16 may accidentally become active during review
queue, migration, or READY promotion work.
```

Mitigation:

```text
Require gf003_candidate_only_safety_gate.
Block one-click activation.
Require owner approval for any future production behavior change.
```

Phase 13 action:

```text
Document only. GF-003 remains disabled and candidate-only.
```

### R10 Rollback Ambiguity Risk

Risk:

```text
Identity migrations may not be cleanly reversible after external references or
teacher review records exist.
```

Mitigation:

```text
Require rollback_plan_gate.
Define what can be reverted.
Define what needs forward-fix.
Require post-migration verification before release.
```

Phase 13 action:

```text
Document only. No rollback script is created.
```

### R11 API / Frontend Coupling Risk

Risk:

```text
API or frontend work may begin before identity semantics and review queue
transition boundaries are stable.
```

Mitigation:

```text
Require api_contract_review_gate.
Require frontend_review_flow_safety_gate.
Do not expose unsafe direct transitions.
```

Phase 13 action:

```text
Document only. No API or frontend is created.
```

### R12 SGF Engine Semantic Regression Risk

Risk:

```text
Teacher admin implementation may accidentally change SGF engine judging
behavior.
```

Mitigation:

```text
Require sgf_engine_non_regression_gate.
Run safety tests.
Do not change production engine code without explicit owner authorization.
```

Phase 13 action:

```text
Document only. No SGF engine production code is changed.
```

## Required Future Migration Gates

Any future C-level identity migration must include:

```text
owner_approval_gate
migration_design_review
uuid_backfill_dry_run
uuid_uniqueness_check
orphan_reference_check
rollback_or_forward_fix_plan
post_migration_verification
sgf_engine_non_regression_check
gf003_candidate_only_safety_check
```

## Rollback / Recovery Requirements

Before any future identity migration begins, the implementation plan must
answer:

```text
What data is changed?
What data is newly generated?
Can generated UUIDs be rolled back?
What external references may exist?
What verification proves migration success?
What verification proves no GF-003 activation occurred?
What is the forward-fix strategy if rollback is unsafe?
```

## Current Phase Non-Goals

Phase 13B does not implement:

```text
runtime behavior
DB schema
DB migration
SQLAlchemy model
Alembic migration
API endpoint
backend queue model
frontend component
WGo.js review UI
production model
teacher_admin runtime package
production override activation
runtime override activation
READY promotion
SGF byte editing
SGF engine judging semantic changes
```

## Merge Policy

This phase is docs + tests only, but it prepares future C-level implementation.

PR may be created after tests and safety audit pass.

Do not auto-merge.

Owner review is required before merge.
