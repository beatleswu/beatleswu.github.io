import datetime as _dt
import json
import math
import os
from collections import Counter, defaultdict


DEFAULT_SHADOW_EVENTS_PATH = os.environ.get(
    'SHADOW_EVENTS_PATH',
    '/app/data/shadow_events.jsonl',
)

EXPECTED_ROUTES = (
    '/api/rating_test/answer',
    '/api/daily-challenge/submit',
    '/api/challenges/friend/<int:cid>/answer',
)

_PUZZLE_ID_KEYS = (
    'puzzle_id',
    'question_id',
    'canonical_id',
    'legacy_id',
    'q_id',
    'id',
)

_TIMESTAMP_KEYS = (
    'timestamp',
    'observed_at',
    'created_at',
    'finished_at',
)

_MATCH_KEYS = (
    'match',
    'is_match',
)

_LATENCY_KEYS = (
    'latency_ms',
    'shadow_latency_ms',
)


def _utc_now():
    return _dt.datetime.now(_dt.timezone.utc)


def _default_result(path, now):
    routes = {
        route: {
            'total': 0,
            'matches': 0,
            'mismatches': 0,
            'parser_failures': 0,
            'exceptions': 0,
        }
        for route in EXPECTED_ROUTES
    }
    return {
        'generated_at': now.isoformat(),
        'source_path': path,
        'summary': {
            'total_events': 0,
            'today_events': 0,
            'last_7_days': 0,
            'last_30_days': 0,
            'invalid_lines': 0,
            'partial_events': 0,
            'unknown_schema_versions': 0,
        },
        'routes': routes,
        'latency': {
            'count': 0,
            'average_ms': 0.0,
            'minimum_ms': 0.0,
            'maximum_ms': 0.0,
            'p50_ms': 0.0,
            'p95_ms': 0.0,
        },
        'parser': {
            'failures': 0,
            'by_reason': [],
        },
        'exceptions': {
            'total': 0,
            'by_class': [],
        },
        'top_mismatches': [],
        'top_parser_failures': [],
        'schema_versions': [],
    }


def _parse_timestamp(raw):
    if not raw or not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value:
        return None
    if value.endswith('Z'):
        value = value[:-1] + '+00:00'
    try:
        parsed = _dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.astimezone(_dt.timezone.utc)


def _normalize_route(route):
    if not isinstance(route, str):
        return None
    value = route.strip()
    if not value:
        return None
    if value.startswith('/api/challenges/friend/') and value.endswith('/answer'):
        return '/api/challenges/friend/<int:cid>/answer'
    return value


def _get_first(event, keys):
    for key in keys:
        if key in event:
            return event.get(key)
    return None


def _coerce_latency(event):
    raw = _get_first(event, _LATENCY_KEYS)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    return value


def _coerce_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ('true', '1', 'yes'):
            return True
        if lowered in ('false', '0', 'no'):
            return False
    return None


def _derive_match(event):
    for key in _MATCH_KEYS:
        coerced = _coerce_bool(event.get(key))
        if coerced is not None:
            return coerced
    legacy = event.get('legacy_verdict') or event.get('legacy_judgement')
    shadow = event.get('shadow_verdict') or event.get('shadow_judgement')
    if isinstance(legacy, str) and isinstance(shadow, str):
        legacy = legacy.strip()
        shadow = shadow.strip()
        if legacy and shadow:
            return legacy == shadow
    return None


def _event_is_partial(event):
    required = ('route',)
    for key in required:
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            continue
        return True
    return False


def _puzzle_key(event):
    raw = _get_first(event, _PUZZLE_ID_KEYS)
    if raw is None:
        return 'unknown'
    text = str(raw).strip()
    return text or 'unknown'


def _counter_rows(counter, key_name):
    rows = []
    for key, count in counter.most_common():
        rows.append({key_name: key, 'count': count})
    return rows


def _puzzle_rows(counter, route_map):
    rows = []
    for puzzle_id, count in counter.most_common(10):
        rows.append({
            'puzzle_id': puzzle_id,
            'count': count,
            'routes': sorted(route_map.get(puzzle_id, set())),
        })
    return rows


def _percentile(values, percentile):
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = math.ceil((percentile / 100.0) * len(ordered)) - 1
    index = max(0, min(rank, len(ordered) - 1))
    return float(ordered[index])


def aggregate_shadow_events(path=None, now=None):
    now = now or _utc_now()
    path = path or DEFAULT_SHADOW_EVENTS_PATH
    result = _default_result(path, now)
    latency_values = []
    parser_reasons = Counter()
    exception_classes = Counter()
    mismatch_puzzles = Counter()
    mismatch_routes = defaultdict(set)
    parser_failure_puzzles = Counter()
    parser_failure_routes = defaultdict(set)
    schema_versions = Counter()

    if not os.path.exists(path):
        return result

    with open(path, 'r', encoding='utf-8') as handle:
        for line in handle:
            raw_line = line.strip()
            if not raw_line:
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                result['summary']['invalid_lines'] += 1
                continue
            if not isinstance(event, dict):
                result['summary']['invalid_lines'] += 1
                continue

            result['summary']['total_events'] += 1

            if _event_is_partial(event):
                result['summary']['partial_events'] += 1

            schema_version = event.get('schema_version')
            if schema_version:
                schema_versions[str(schema_version)] += 1
                if str(schema_version) not in ('shadow-v2', 'shadow-v3'):
                    result['summary']['unknown_schema_versions'] += 1

            event_dt = _parse_timestamp(_get_first(event, _TIMESTAMP_KEYS))
            if event_dt is not None:
                event_date = event_dt.date()
                if event_date == now.date():
                    result['summary']['today_events'] += 1
                delta_days = (now.date() - event_date).days
                if 0 <= delta_days < 7:
                    result['summary']['last_7_days'] += 1
                if 0 <= delta_days < 30:
                    result['summary']['last_30_days'] += 1

            route = _normalize_route(event.get('route'))
            if route and route not in result['routes']:
                result['routes'][route] = {
                    'total': 0,
                    'matches': 0,
                    'mismatches': 0,
                    'parser_failures': 0,
                    'exceptions': 0,
                }

            route_bucket = result['routes'].get(route)
            if route_bucket is not None:
                route_bucket['total'] += 1

            match_value = _derive_match(event)
            if match_value is True and route_bucket is not None:
                route_bucket['matches'] += 1
            elif match_value is False:
                if route_bucket is not None:
                    route_bucket['mismatches'] += 1
                puzzle_id = _puzzle_key(event)
                mismatch_puzzles[puzzle_id] += 1
                if route:
                    mismatch_routes[puzzle_id].add(route)

            parser_status = str(event.get('parser_status') or '').strip().lower()
            parser_failure_reason = str(event.get('parser_failure_reason') or '').strip()
            parser_failed = parser_status == 'failed' or bool(parser_failure_reason)
            if parser_failed:
                result['parser']['failures'] += 1
                if route_bucket is not None:
                    route_bucket['parser_failures'] += 1
                parser_reasons[parser_failure_reason or 'unknown'] += 1
                puzzle_id = _puzzle_key(event)
                parser_failure_puzzles[puzzle_id] += 1
                if route:
                    parser_failure_routes[puzzle_id].add(route)

            exception_class = str(event.get('exception_class') or '').strip()
            if exception_class:
                result['exceptions']['total'] += 1
                exception_classes[exception_class] += 1
                if route_bucket is not None:
                    route_bucket['exceptions'] += 1

            latency_ms = _coerce_latency(event)
            if latency_ms is not None:
                latency_values.append(latency_ms)

    if latency_values:
        total_latency = sum(latency_values)
        result['latency'] = {
            'count': len(latency_values),
            'average_ms': round(total_latency / len(latency_values), 3),
            'minimum_ms': round(min(latency_values), 3),
            'maximum_ms': round(max(latency_values), 3),
            'p50_ms': round(_percentile(latency_values, 50), 3),
            'p95_ms': round(_percentile(latency_values, 95), 3),
        }

    result['parser']['by_reason'] = _counter_rows(parser_reasons, 'reason')
    result['exceptions']['by_class'] = _counter_rows(exception_classes, 'exception_class')
    result['top_mismatches'] = _puzzle_rows(mismatch_puzzles, mismatch_routes)
    result['top_parser_failures'] = _puzzle_rows(parser_failure_puzzles, parser_failure_routes)
    result['schema_versions'] = _counter_rows(schema_versions, 'schema_version')
    return result
