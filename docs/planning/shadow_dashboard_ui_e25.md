# Shadow Dashboard UI E2.5

## Scope

This sprint adds a read-only admin UI for Shadow Judging observability.

Included:

- `GET /admin/shadow-dashboard`
- `GET /api/admin/shadow/dashboard/recent`
- recent events table
- summary cards
- route statistics
- parser failure table
- request-id search
- route filter
- status filter

Excluded:

- Shadow runtime changes
- parser changes
- SGF engine changes
- event schema changes
- database changes
- write endpoints

## Architecture

The existing backend aggregation endpoint remains unchanged:

- `GET /api/admin/shadow/dashboard`

The UI uses a bounded recent-events reader:

- `GET /api/admin/shadow/dashboard/recent`

Flow:

`shadow_events.jsonl` -> bounded tail reader -> normalized recent event payload -> admin-only HTML + vanilla JS

## Recent Event Payload

The recent dashboard API returns:

- `summary`
- `routes`
- `parser_failures`
- `recent_events`
- `limit`
- `returned_events`

Recent events are returned newest-first.

## Performance

The UI does not scan the full JSONL file.

It reads only a bounded tail window from `shadow_events.jsonl`, capped by:

- line limit
- byte limit

This keeps the dashboard read-only and safe for production use without adding cache or background jobs.

## Security

Both the HTML page and recent dashboard API are protected by existing `@admin_required`.

Expected behavior:

- unauthenticated API access: `401`
- non-admin API access: `403`
- unauthenticated HTML access: redirect to `/login`

## UI Sections

The page includes:

- `Recent Events`
- `Summary Cards`
- `Route Statistics`
- `Parser Failure Table`
- `Event Detail`

Event detail exposes only existing read-only fields:

- `schema_version`
- `entry_point`
- `parser_failure_reason`
- `exception_message`
