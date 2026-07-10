# Shadow Dashboard Backend (Sprint E2.3)

## Scope

Sprint E2.3 adds the backend needed for the first Shadow Dashboard:

- a read-only aggregation layer that reads `/app/data/shadow_events.jsonl`
- a read-only admin JSON API at `/api/admin/shadow/dashboard`

This sprint does not add frontend UI, charts, CSS, JavaScript, or any new
answer-judgement behavior.

## Aggregation Architecture

Runtime flow:

`shadow_events.jsonl` -> `shadow_dashboard.aggregate_shadow_events()` -> `/api/admin/shadow/dashboard`

Implementation notes:

- the aggregator is file-based and read-only
- missing files return an empty dataset instead of raising
- malformed JSONL lines are skipped and counted as `invalid_lines`
- partial events are tolerated and counted as `partial_events`
- unknown `schema_version` values are tolerated and counted as `unknown_schema_versions`
- friend challenge route instances are normalized to `/api/challenges/friend/<int:cid>/answer`

## Dashboard API

Route:

- `GET /api/admin/shadow/dashboard`

Authentication:

- protected by existing `@admin_required`
- unauthenticated callers receive the normal admin auth response
- non-admin callers receive the normal admin auth response

Response shape:

```json
{
  "generated_at": "2026-07-11T12:34:56+00:00",
  "source_path": "/app/data/shadow_events.jsonl",
  "summary": {},
  "routes": {},
  "latency": {},
  "parser": {},
  "exceptions": {},
  "top_mismatches": [],
  "top_parser_failures": [],
  "schema_versions": []
}
```

## Supported Metrics

Summary:

- `total_events`
- `today_events`
- `last_7_days`
- `last_30_days`
- `invalid_lines`
- `partial_events`
- `unknown_schema_versions`

Per route:

- `total`
- `matches`
- `mismatches`
- `parser_failures`
- `exceptions`

Latency:

- `count`
- `average_ms`
- `minimum_ms`
- `maximum_ms`
- `p50_ms`
- `p95_ms`

Parser diagnostics:

- total parser failures
- parser failures grouped by `parser_failure_reason`

Exception diagnostics:

- total exceptions
- exceptions grouped by `exception_class`

Puzzle groupings:

- `top_mismatches`
- `top_parser_failures`

## Event Interpretation

The aggregator accepts current production shadow envelopes and tolerates older
or partially populated lines.

Fields currently interpreted when present:

- `schema_version`
- `route`
- `timestamp`
- `observed_at`
- `created_at`
- `finished_at`
- `latency_ms`
- `shadow_latency_ms`
- `parser_status`
- `parser_failure_reason`
- `exception_class`
- `match`
- `is_match`
- `legacy_verdict`
- `legacy_judgement`
- `shadow_verdict`
- `shadow_judgement`
- `puzzle_id`
- `question_id`
- `canonical_id`
- `legacy_id`
- `q_id`

## Known Limitations

- this sprint does not add a dashboard HTML page or chart rendering
- aggregation is computed on read; no materialized cache is written
- timestamp-based windows only count events with a parseable timestamp
- top puzzle groupings fall back to `unknown` when the envelope does not carry a stable puzzle identifier
- unknown routes are returned as additional route buckets but only the three production answer routes are pre-seeded in the response
