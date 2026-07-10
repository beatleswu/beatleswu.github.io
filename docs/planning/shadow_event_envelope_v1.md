# Production Shadow Event Envelope v3

Status: Production-ready metadata envelope upgrade
Scope: Shadow Judging JSONL metadata only
Runtime impact: None to user-facing judgement

## Purpose

This document defines the production shadow event envelope emitted by
`shadow_judging.observe_answer_route()` and its compatibility wrapper
`shadow_judging.observe_rating_test()`.

The envelope is append-only JSONL and keeps the legacy judgement path unchanged.

## Envelope Version

- `schema_version`: fixed string `shadow-v3`

## Supported Routes

| Route | Entry point | Notes |
| --- | --- | --- |
| `/api/rating_test/answer` | `rating_test` | Full SGF replay comparison. Matches and mismatches are meaningful here. |
| `/api/daily-challenge/submit` | `daily_challenge` | Observation-only coverage. The shadow path is unsupported for SGF replay, so the event records a parser failure reason instead of a replay verdict. |
| `/api/challenges/friend/<int:cid>/answer` | `friend_challenge` | Observation-only coverage. The shadow path is unsupported for SGF replay, so the event records a parser failure reason instead of a replay verdict. |

## Event Schema

| Field | Type | Nullable | Example | Meaning |
| --- | --- | --- | --- | --- |
| `schema_version` | string | no | `shadow-v3` | Stable envelope version identifier. |
| `event_id` | string | no | `0b7f5f35-3af0-4dfe-9f8f-7cfe1d4d4fd0` | Unique event id for dedupe and traceability. |
| `created_at` | ISO-8601 string | no | `2026-07-11T00:00:00.000000+00:00` | UTC event timestamp. |
| `route` | string | no | `/api/rating_test/answer` | Literal production route that emitted the event. |
| `request_id` | string | no | `b5a4a2f0-0d2d-4b9d-b4c6-1f9d8f6c1d61` | Request correlation id from infrastructure or generated safely when absent. |
| `latency_ms` | integer | no | `12` | Shadow processing latency in milliseconds. |
| `entry_point` | string | no | `rating_test` | Shadow family label used for route-level aggregation. |
| `legacy_question_id` | integer | no | `29830` | Legacy route question or challenge identifier. |
| `canonical_puzzle_id` | null | yes | `null` | Canonical puzzle id is not stamped in this production phase. |
| `session_id` | string | no | `sess_123` | Route correlation key. For daily/friend routes, this is a synthetic per-request logical key. |
| `transform_idx` | integer | no | `4` | Rating-test transform index. For non-rating routes this is `0`. |
| `source_judgement` | string | no | `accept` | Legacy production judgement. |
| `client_judgement` | string | no | `reject` | Client-reported judgement from the request body. |
| `shadow_judgement` | string | no | `accept` | Shadow SGF judgement or `unsupported` for routes without replay support. |
| `shadow_reason` | string | no | `reached leaf (legacy leaf semantics)` | Human-readable shadow-path reason. |
| `parser_status` | string | no | `ok` | Parser outcome for the shadow path. `failed` is emitted for unsupported routes or parser/import failures. |
| `parser_failure_reason` | string | yes | `route unsupported: daily_challenge` | Machine-readable failure reason, empty on success. |
| `exception_class` | string | yes | `ValueError` | Shadow-path exception class, empty when none occurs. |
| `exception_message` | string | yes | `bad move format at index 0` | Sanitized exception message, empty when none occurs. |
| `classification` | string | no | `agreement_accept` | Legacy-vs-shadow comparison class. |
| `review_recommended` | boolean | no | `false` | Whether the event should be reviewed later. |
| `owner_decision_required` | boolean | no | `false` | Whether owner escalation is required. |
| `moves_count` | integer | no | `2` | Count of submitted moves. |
| `katago_best_move` | string | no | `Q16` | Question-level KataGo hint, if any. |
| `katago_best_move_present` | boolean | no | `true` | Presence bit for the KataGo hint. |
| `user_facing_judgement_changed` | boolean | no | `false` | Must remain false; shadow judging is observation only. |

## Field Notes

### `route`

- Always populated from the active Flask request when available.
- Falls back to `/api/rating_test/answer` outside a request context.

### `request_id`

- Reuses a request header when the infrastructure provides one.
- Otherwise generates a safe UUID v4 string.
- Never left blank.

### `latency_ms`

- Measured inside the shadow hook.
- Captures shadow processing only, not the user-facing response time.
- Always non-negative.

### `parser_status`

- `ok` when the SGF replay path succeeds.
- `failed` when the route is unsupported for SGF replay or when parsing/importing fails.

### `parser_failure_reason`

- Empty string when `parser_status=ok`.
- Short machine-readable reason when `parser_status=failed`.

### `exception_class`

- Empty string when no shadow-path exception occurs.
- Python exception class name when the shadow path raises.

### `exception_message`

- Empty string when no shadow-path exception occurs.
- Sanitized and truncated to avoid tokens, headers, cookies, or stack traces.

## Event Flow

`HTTP route`
-> `validation`
-> `legacy judgement`
-> `shadow judgement`
-> `comparison`
-> `event creation`
-> `persistence/JSONL sink`

The JSONL sink remains `/app/data/shadow_events.jsonl`.

## Dashboard Readiness

PARTIAL

The emitted stream now supports the raw inputs needed for:

- total events
- daily event count
- route breakdown
- matches
- mismatches
- latency
- parser failures
- exception count

What is still missing is the read-only aggregation layer and dashboard API/UI.

