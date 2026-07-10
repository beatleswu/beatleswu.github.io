# Shadow Runtime Completion (Sprint E2.4)

## Goal

Sprint E2.4 completes the production Shadow Judging runtime for all production
answer routes without changing user-visible judgement.

Supported routes:

- `/api/rating_test/answer`
- `/api/daily-challenge/submit`
- `/api/challenges/friend/<int:cid>/answer`

## Canonical Input Pipeline

All routes now feed one shared shadow observer:

`route payload -> canonical input adapter -> shadow compare -> shadow event`

Canonical input fields:

- `legacy_question_id`
- `session_id`
- `transform_idx`
- `sgf_transformed`
- `moves`
- `client_correct`
- `final_correct`
- `katago_best_move`

Adapter behavior:

- if request `moves` are present, the observer uses them directly
- if request `moves` are absent, the observer derives a canonical move list from the SGF and the final legacy route result
- the fallback adapter is shared across routes; there is no route-specific compare branch

## Shared Compare Flow

All three routes use the same runtime entry points:

- `shadow_judging.observe_rating_test()`
- `shadow_judging.observe_answer_route()`

Shared compare semantics:

- shadow runtime is observation-only
- shadow runtime never changes legacy responses
- parser failures represent SGF/runtime issues
- unsupported-route placeholders are no longer emitted for daily challenge or friend challenge

## Event Consistency

Every route emits the same envelope family:

- `schema_version`
- `route`
- `request_id`
- `latency_ms`
- `entry_point`
- `legacy_question_id`
- `session_id`
- `source_judgement`
- `client_judgement`
- `shadow_judgement`
- `shadow_reason`
- `parser_status`
- `parser_failure_reason`
- `exception_class`
- `exception_message`
- `classification`

## Current Limitation

Daily challenge and friend challenge currently post final correctness without a
full move list. To keep runtime coverage complete without frontend changes, the
shared adapter synthesizes canonical shadow input from SGF plus the final legacy
route result when raw moves are absent.
