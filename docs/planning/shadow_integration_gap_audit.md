# Shadow Integration Gap Audit

Status: Updated production readiness audit
Canonical reference: `ead3a59eecf4eb8bbca6a9fb4e28ae9082ccfded`
Scope: Documentation and contract only
Runtime impact: None
Database impact: None
API impact: None
Frontend impact: None

## Purpose

This audit compares the canonical Shadow Judging contract from SGF Engine PR
#41 against the current production integration in `D:\go-website`.

The goal is to answer five questions:

1. Which production routes actually invoke shadow judging.
2. What event schema production currently emits.
3. How that schema differs from the canonical contract.
4. Whether production data is ready for an S3/dashboard pipeline.
5. What the next production implementation batch should contain.

Current verdict: PARTIAL.

## Evidence Base

Production evidence:

- `app.py:10907`
- `app.py:10952`
- `app.py:14337`
- `app.py:14396`
- `app.py:20434`
- `app.py:20496`
- `app.py:20499`
- `shadow_judging.py:5`
- `shadow_judging.py:26`
- `shadow_judging.py:45`
- `shadow_judging.py:171`
- `shadow_judging.py:192`
- `docker-compose.prod.yml:60`
- `docker-compose.prod.yml:61`
- `docker-compose.prod.yml:122`
- `docker-compose.prod.yml:123`

Canonical contract references:

- `docs/planning/ADR-021-canonical-puzzle-identity.md`
- `tests/sgf_engine/_phase19_shadow_judging_readiness_spike.py`

## Entry-Point Inventory

### Production routes

| Route | File | Function | Hook function | Feature flag | Execution condition | User-facing judgement can change? | Event sink |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/daily-challenge/submit` | `app.py` | `dc_submit` | `shadow_judging.observe_answer_route()` | `SHADOW_JUDGING_ENABLED` | After request validation and database commit, inside `if shadow_judging.is_enabled()` | No. The hook is wrapped in `try/except` and the original answer flow continues. | `/app/data/shadow_events.jsonl` |
| `/api/challenges/friend/<int:cid>/answer` | `app.py` | `friend_challenge_answer` | `shadow_judging.observe_answer_route()` | `SHADOW_JUDGING_ENABLED` | After request validation and database commit, inside `if shadow_judging.is_enabled()` | No. The hook is wrapped in `try/except` and the original answer flow continues. | `/app/data/shadow_events.jsonl` |
| `/api/rating_test/answer` | `app.py` | `rt_answer` | `shadow_judging.observe_rating_test()` -> `observe_answer_route()` | `SHADOW_JUDGING_ENABLED` | After request validation, after session locking, inside `if shadow_judging.is_enabled()` | No. The call is wrapped in `try/except` and the original answer flow continues. | `/app/data/shadow_events.jsonl` |

### Route answer

Production currently observes shadow judging in all three answer routes:

- `/api/rating_test/answer`
- `/api/daily-challenge/submit`
- `/api/challenges/friend/<int:cid>/answer`

### Call flow verification

Verified current flow:

1. HTTP request is validated.
2. Legacy judgement is computed first.
3. `shadow_judging.is_enabled()` gates the observation call.
4. `shadow_judging.observe_answer_route()` or `shadow_judging.observe_rating_test()` is invoked.
5. Any shadow failure is caught and ignored.
6. The legacy answer path continues.

## Production Schema

### Emitted fields

| Name | Type | Always present | Nullable | Source | Meaning |
| --- | --- | --- | --- | --- | --- |
| `schema_version` | string | yes | no | hard-coded `shadow-v3` | Envelope version for the shadow event stream |
| `event_id` | string | yes | no | `uuid.uuid4()` | Unique shadow event identifier |
| `created_at` | ISO-8601 string | yes | no | `datetime.datetime.now(datetime.timezone.utc).isoformat()` | Event timestamp |
| `route` | string | yes | no | Flask request path | Literal route that emitted the event |
| `request_id` | string | yes | no | request header or generated UUID | Request correlation id |
| `latency_ms` | integer | yes | no | `time.perf_counter()` delta | Shadow processing latency |
| `entry_point` | string | yes | no | hard-coded route family label | Route-family label for aggregation |
| `legacy_question_id` | integer | yes | no | route payload / legacy ids | Legacy question or challenge identifier |
| `canonical_puzzle_id` | null | yes | yes | hard-coded `None` | Canonical puzzle identity not yet stamped |
| `session_id` | string | yes | no | route payload or synthetic route key | Route correlation key |
| `transform_idx` | integer | yes | no | route payload or `0` | Rating-test transform index or `0` sentinel |
| `source_judgement` | string | yes | no | legacy verdict | Legacy production judgement |
| `client_judgement` | string | yes | no | derived from request body | Client-reported judgement |
| `shadow_judgement` | string | yes | no | `_shadow_verdict()` or unsupported route fallback | Shadow SGF judgement |
| `shadow_reason` | string | yes | no | `_shadow_verdict()` or route fallback | Human-readable shadow diagnostic reason |
| `parser_status` | string | yes | no | parser outcome | `ok` or `failed` |
| `parser_failure_reason` | string | yes | yes | parser / route fallback | Machine-readable parser failure reason |
| `exception_class` | string | yes | yes | exception capture | Shadow-path exception class |
| `exception_message` | string | yes | yes | sanitized exception text | Sanitized shadow-path exception message |
| `classification` | string | yes | no | `_classify()` result | Legacy-vs-shadow comparison class |
| `review_recommended` | boolean | yes | no | classification membership check | Whether review is suggested |
| `owner_decision_required` | boolean | yes | no | classification equality check | Whether owner escalation is required |
| `moves_count` | integer | yes | no | request payload | Number of moves observed |
| `katago_best_move` | string | yes | no | question data | KataGo hint if present |
| `katago_best_move_present` | boolean | yes | no | `bool(katago_best_move)` | Whether a KataGo hint exists |
| `user_facing_judgement_changed` | boolean | yes | no | hard-coded `False` | Guarantees no user-facing mutation in this hook |

### Schema notes

- `shadow-v3` is append-only JSONL.
- `canonical_puzzle_id` is still emitted but remains `null`.
- Production now includes route, request correlation, latency, parser
  diagnostics, and exception envelopes.
- The three answer routes share the same envelope contract, but only
  `/api/rating_test/answer` produces a real SGF replay comparison.

## Canonical Comparison

Canonical field | Production field | Status | Evidence / notes
--- | --- | --- | ---
`event_id` | `event_id` | MATCH | Same unique event identifier.
`legacy_question_id` | `legacy_question_id` | MATCH | Production carries the legacy route question id.
`canonical_puzzle_id` | `canonical_puzzle_id` | SEMANTIC_MISMATCH | Canonical contract expects a future canonical UUID join key; production emits `None` only.
`source_judgement` | `source_judgement` | MATCH | Same legacy-vs-shadow anchor field.
`shadow_judgement` | `shadow_judgement` | MATCH | Same shadow verdict field.
`classification` | `classification` | MATCH | Same comparison label.
`player_color` | None | MISSING | Production does not carry player color.
`player_move_sgf` | None | MISSING | Production does not carry the SGF move string.
`player_move_board_coordinate` | None | MISSING | Production does not carry the board coordinate string.
`legacy_reason` | None | MISSING | Production does not emit a legacy reason string.
`shadow_reason` | `shadow_reason` | MATCH | Same shadow diagnostic field.
`review_recommended` | `review_recommended` | MATCH | Same review flag.
`owner_decision_required` | `owner_decision_required` | MATCH | Same owner escalation flag.
`candidate_only_detected` | None | MISSING | Production does not emit the candidate-only flag.
`gf003_related` | None | MISSING | Production does not emit the GF-003 safety flag.
`invalid_identity` | None | MISSING | Production does not emit identity validity diagnostics.
`legacy_unknown` | None | MISSING | Production does not emit legacy-unknown diagnostics.
`user_facing_judgement_changed` | `user_facing_judgement_changed` | MATCH | Production hard-codes `False`.
`created_at` | `created_at` | MATCH | Same timestamp concept.
`route` | `route` | PRODUCTION_ONLY | Route path added for dashboard aggregation.
`request_id` | `request_id` | PRODUCTION_ONLY | Correlation id added for event tracing.
`latency_ms` | `latency_ms` | PRODUCTION_ONLY | Shadow-only latency added for dashboard metrics.
`schema_version` | `schema_version` | PRODUCTION_ONLY | Envelope version tag added for compatibility.
`parser_status` | `parser_status` | PRODUCTION_ONLY | Parser outcome added for diagnostics.
`parser_failure_reason` | `parser_failure_reason` | PRODUCTION_ONLY | Machine-readable parser failure reason.
`exception_class` | `exception_class` | PRODUCTION_ONLY | Exception capture added for diagnostics.
`exception_message` | `exception_message` | PRODUCTION_ONLY | Sanitized exception message.
`entry_point` | `entry_point` | PRODUCTION_ONLY | Route-family label for aggregation.
`session_id` | `session_id` | PRODUCTION_ONLY | Route-level logical session key.
`transform_idx` | `transform_idx` | PRODUCTION_ONLY | Rating-test transform context or sentinel value.
`client_judgement` | `client_judgement` | PRODUCTION_ONLY | Client-reported answer result.
`moves_count` | `moves_count` | PRODUCTION_ONLY | Move count derived from submitted moves.
`katago_best_move` | `katago_best_move` | PRODUCTION_ONLY | KataGo hint from question data.
`katago_best_move_present` | `katago_best_move_present` | PRODUCTION_ONLY | Presence bit for KataGo hint.

### Comparison summary

- MATCH: 10
- MISSING: 8
- PRODUCTION_ONLY: 14
- RENAMED: 0
- TYPE_MISMATCH: 0
- SEMANTIC_MISMATCH: 1

## Pipeline

### Verified flow

`HTTP route`
-> `validation`
-> `legacy judgement`
-> `shadow judgement`
-> `comparison`
-> `event creation`
-> `persistence/JSONL sink`

### Step status

| Step | Status | Notes |
| --- | --- | --- |
| HTTP route | READY | All three answer routes are wired. |
| Validation | READY | Request/session validation occurs before the hook. |
| Legacy judgement | READY | The legacy correctness result is computed first. |
| Shadow judgement | READY | `shadow_judging.observe_answer_route()` executes when the feature flag is on. |
| Comparison | READY | `shadow_judging._classify()` builds the comparison class. |
| Event creation | READY | `shadow_judging.observe_answer_route()` constructs the JSON event. |
| Persistence / JSONL sink | READY | The event is appended to `/app/data/shadow_events.jsonl`. |

### Absent or unverified steps

- There is still no read-only aggregation layer in production.
- There is still no dashboard API/UI in production.
- JSONL retention and rotation are not documented in production code.

## Dashboard Readiness

PARTIAL

### Metric evaluation

| Metric | Status | Why |
| --- | --- | --- |
| total events | READY | Every emitted event has `event_id` and `created_at`. |
| successful comparisons | READY | `classification` identifies comparison outcomes. |
| matches | READY | Agreement classes are present in `classification`. |
| mismatches | READY | Mismatch classes are present in `classification`. |
| daily count | READY | `created_at` plus the route stream support daily grouping. |
| top mismatch puzzles | PARTIAL | `legacy_question_id` exists, but aggregation logic is still missing. |
| top parser failures | PARTIAL | `parser_failure_reason` exists, but aggregation logic is still missing. |
| parser failures | READY | `parser_status` and `parser_failure_reason` are emitted. |
| exceptions | READY | `exception_class` and `exception_message` are emitted. |
| latency average | READY | `latency_ms` is emitted. |
| latency p50 | READY | `latency_ms` is emitted. |
| latency p95 | READY | `latency_ms` is emitted. |
| request correlation | READY | `request_id` is emitted. |
| schema versioning | READY | `schema_version` is emitted. |

### Readiness conclusion

Production is not yet dashboard-complete because the raw event stream still
lacks the read-only aggregation layer and dashboard surface. The telemetry
envelope itself is now stable enough for that next batch.

## Next Implementation Batch

### Recommended batch

Objective: build the read-only aggregation layer that turns `shadow_events.jsonl`
into daily dashboard metrics without changing production behaviour.

Exact production files likely involved:

- `docs/planning/shadow_integration_gap_audit.md`
- `docs/planning/shadow_event_envelope_v1.md`
- `tests/test_shadow_integration_gap_contract.py`
- `tests/test_shadow_envelope_v1.py`
- a new aggregation module under `docs/` or `tests/` if the implementation is still documentation-first

Fields to add:

- none for the production envelope

Routes covered:

- `/api/rating_test/answer`
- `/api/daily-challenge/submit`
- `/api/challenges/friend/<int:cid>/answer`

Risk level: medium

Required tests:

- route-level contract test for each shadow hook entry point
- schema contract test for `shadow-v3`
- no-user-impact regression test for answer submission
- feature-flag off test
- event-stream aggregation contract test

Deployment required: yes

DB backup required: no

## Summary

Production now has shadow coverage on all three answer routes and emits a
stable `shadow-v3` envelope. The remaining gap is the aggregation layer that
will power an S3/dashboard pipeline.
