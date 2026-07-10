# SGF OBSERVE-1 Shadow Judging Readiness Audit

Phase: OBSERVE-1
Status: Readiness audit baseline
Scope: Planning / contract baseline only
Runtime impact: None
Database impact: None
API impact: None
Frontend impact: None

## Purpose

This audit answers one question: is the current Shadow Judging pipeline ready
for a dashboard-backed S3 export without changing production behavior?

Current verdict: NOT READY.

The repository does not contain a production shadow judging runtime hook. The
only shadow judging contract in this checkout is the test-local Phase 19 helper
and the planning docs that describe future integration.

## Evidence Base

Verified planning sources used for this audit:

- `docs/planning/phase19_sgf_shadow_judging_readiness_spike.md`
- `docs/planning/phase20_production_integration_adr.md`
- `docs/planning/phase21_identity_alias_adr.md`
- `tests/sgf_engine/_phase19_shadow_judging_readiness_spike.py`

## Current Entry Points

### Current hook location(s)

There is no checked-in production shadow judging hook in this repository.

The production integration ADR lists the known answer-judging candidates as:

- `/api/daily-challenge/submit`
- `/api/challenges/friend/<id>/answer`
- `/api/rating_test/answer`

This audit cannot prove that production still only observes
`/api/rating_test/answer`. The documented production surface already includes
more than that one route.

### Current observe function(s)

The test-local readiness helper exposes the following contract functions:

- `classify_shadow_comparison()`
- `build_shadow_judging_event()`

These functions define the comparison and event shape used by the Phase 19
contract, but they are not runtime hooks.

### Call flow

Documented future call flow:

1. Production answer route receives the request.
2. Legacy production judgement is computed as today.
3. Shadow judgement is computed in a no-user-impact side path.
4. Legacy vs shadow comparison is classified.
5. A shadow event is serialized.
6. The event is appended to JSONL.

Current audit result:

- Step 1 exists in production.
- Steps 2 to 6 are only documented as future behavior in this checkout.
- This repository cannot prove the observation entry still routes through the existing Shadow Judging hook.

### Where JSONL is written

Not implemented in this checkout.

`phase20_production_integration_adr.md` says the first iteration should log to a
JSONL file instead of the database, but it does not define a production file
path or a checked-in writer.

### What data is recorded

The Phase 19 shadow event contract records:

- event identity
- legacy and canonical puzzle identity
- legacy and shadow judgements
- comparison classification
- move context
- human-readable reasons
- review flags
- GF-003 safety flags
- invalid-identity and legacy-unknown flags
- created timestamp

### What is NOT recorded

The current contract does not record:

- request id
- route name
- latency
- parser diagnostics
- parser failure reason
- exception type
- exception message
- raw request payload
- user id
- session id
- dashboard aggregation bucket
- schema version
- confidence score

## JSONL Schema

The table below describes every field currently emitted by the Phase 19
shadow event contract.

### Identity

| Field name | Type | Always present? | Nullable? | Example value | Used by dashboard? | Required for future phases? |
| --- | --- | --- | --- | --- | --- | --- |
| `event_id` | string | yes | no | `evt_20260710_0001` | yes, for dedupe and traceability | yes |
| `legacy_question_id` | integer | yes | yes | `29830` | yes, for legacy grouping | yes |
| `canonical_puzzle_id` | UUID string | yes | yes | `f47ac10b-58cc-4372-a567-0e02b2c3d479` | yes, once aliasing exists | yes |

### Runtime

| Field name | Type | Always present? | Nullable? | Example value | Used by dashboard? | Required for future phases? |
| --- | --- | --- | --- | --- | --- | --- |
| `player_color` | string | yes | no | `B` | yes, for filter context | yes |
| `player_move_sgf` | string | yes | no | `B[dd]` | yes, for move drill-down | yes |
| `player_move_board_coordinate` | string | yes | no | `D16` | yes, for move drill-down | yes |
| `created_at` | ISO-8601 string | yes | no | `2026-07-10T00:00:00Z` | yes, for time bucketing | yes |

### Engine comparison

| Field name | Type | Always present? | Nullable? | Example value | Used by dashboard? | Required for future phases? |
| --- | --- | --- | --- | --- | --- | --- |
| `source_judgement` | string | yes | no | `accept` | yes | yes |
| `shadow_judgement` | string | yes | no | `reject` | yes | yes |
| `classification` | string | yes | no | `legacy_accepts_shadow_rejects` | yes | yes |
| `review_recommended` | boolean | yes | no | `true` | yes | yes |
| `owner_decision_required` | boolean | yes | no | `false` | yes | yes |
| `candidate_only_detected` | boolean | yes | no | `false` | yes | yes |
| `gf003_related` | boolean | yes | no | `true` | yes | yes |
| `invalid_identity` | boolean | yes | no | `false` | yes | yes |
| `legacy_unknown` | boolean | yes | no | `false` | yes | yes |
| `user_facing_judgement_changed` | boolean | yes | no | `false` | yes | yes |

### Diagnostics

| Field name | Type | Always present? | Nullable? | Example value | Used by dashboard? | Required for future phases? |
| --- | --- | --- | --- | --- | --- | --- |
| `legacy_reason` | string | yes | no | `legacy accepted because candidate answer matched` | yes, for review context | yes |
| `shadow_reason` | string | yes | no | `shadow rejected because move was off-tree` | yes, for review context | yes |

## Dashboard Readiness

The S3 dashboard is not ready yet.

### MVP Metrics

| Metric | Status | Why |
| --- | --- | --- |
| total events | PARTIAL | `event_id` and `created_at` exist, but there is no verified production JSONL sink in this checkout. |
| successful comparisons | PARTIAL | `classification` can separate agreements from non-agreements, but no live shadow event writer is verified here. |
| identical verdicts | PARTIAL | `agreement_accept` and `agreement_reject` are defined, but only in the test-local contract. |
| mismatches | PARTIAL | disagreement classes are defined, but no production emitter is present. |
| parser failures | NOT AVAILABLE | no parser failure field or parser diagnostic envelope is emitted. |
| exceptions | NOT AVAILABLE | no exception field or exception envelope is emitted. |
| latency average | NOT AVAILABLE | no latency field is emitted. |
| latency p50 | NOT AVAILABLE | no latency field is emitted. |
| latency p95 | NOT AVAILABLE | no latency field is emitted. |
| top mismatch puzzles | PARTIAL | legacy and canonical identity exist, but the current contract does not guarantee a dashboard-ready alias or title field. |
| top parser failures | NOT AVAILABLE | parser failures are not recorded. |
| daily event count | PARTIAL | `created_at` supports bucketing, but the collection path is not verified in production. |

### Why not ready

- no verified production shadow hook in this checkout
- no verified JSONL file path
- no latency capture
- no parser diagnostics
- no exception capture
- no request id
- no schema version
- no dashboard export contract

## Data Quality

Status: NOT READY

The schema is internally consistent, but it is not operationally complete for
shadow-dashboards yet.

### Missing Information

- missing production hook verification
- missing JSONL sink path
- missing request id
- missing route label
- missing latency
- missing parser diagnostics
- missing parser failure reason
- missing exception type
- missing exception message
- missing schema version
- missing dashboard aggregation fields
- missing confidence score

## Roadmap

The roadmap is split into independent phases. Each phase is intended to be
independently mergeable.

### OBSERVE-2

Objective: freeze the production entry-point inventory and define the append-
only shadow JSONL contract at the route boundary.

Scope:

- enumerate all answer-judging entry points
- pin the shadow hook insertion point(s)
- define the JSONL file contract
- define the event versioning contract

Excluded scope:

- dashboard UI
- S3 publishing
- database schema changes
- parser changes
- judging semantic changes

Estimated risk: medium

### OBSERVE-3

Objective: add diagnostics and timing coverage so shadow events can support
debugging and failure analysis.

Scope:

- capture latency
- capture request correlation data
- capture parser diagnostics
- capture safe exception envelopes
- keep no-user-impact behavior intact

Excluded scope:

- dashboard UI
- S3 publishing
- database schema changes
- review queue UI
- judging semantic changes

Estimated risk: medium-high

### OBSERVE-4

Objective: produce dashboard-ready aggregates and an S3 export contract.

Scope:

- daily rollups
- mismatch leaderboards
- parser-failure leaderboards
- retention and export manifest rules
- S3 publishing contract

Excluded scope:

- runtime judging changes
- database schema changes
- frontend dashboard implementation
- answer-route behavior changes

Estimated risk: medium

## Summary

Shadow judging is not collecting enough information yet for a dashboard-first
S3 rollout.

The current contract is stable enough to describe the intended event shape, but
the production observation path, latency data, diagnostics, and export contract
are still missing.
