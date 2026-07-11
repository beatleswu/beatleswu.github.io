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
    'occurred_at',
)

_MATCH_KEYS = (
    'match',
    'is_match',
)

_LATENCY_KEYS = (
    'latency',
    'latency_ms',
    'shadow_latency_ms',
)

_JUDGEMENT_KEYS = (
    'shadow_judgement',
    'shadow_judgement_result',
    'shadow_verdict',
    'judgement',
    'verdict',
)

_RECENT_DEFAULT_LIMIT = 200
_RECENT_MAX_LIMIT = 500
_RECENT_MAX_BYTES = 512 * 1024


def _utc_now():
    return _dt.datetime.now(_dt.timezone.utc)


def _coerce_text(value, *, max_len=200):
    if value is None:
        return ''
    text = str(value).replace('\r', ' ').replace('\n', ' ').replace('\t', ' ').strip()
    if not text:
        return ''
    return text[:max_len]


def _sanitize_reason(value, *, max_len=240):
    reason = _coerce_text(value, max_len=max_len)
    return reason


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
        return ''
    value = route.strip()
    if not value:
        return ''
    if value.startswith('/api/challenges/friend/') and value.endswith('/answer'):
        return '/api/challenges/friend/<int:cid>/answer'
    return value


def _get_first(event, keys):
    for key in keys:
        if key in event:
            return event.get(key)
    return None


def _coerce_float(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result) or result < 0:
        return None
    return result


def _coerce_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ('true', '1', 'yes', 'y', 'ok', 'match', 'pass'):
            return True
        if lowered in ('false', '0', 'no', 'n', 'error', 'fail', 'failed', 'mismatch'):
            return False
    return None


def _tail_lines(path, limit, max_bytes=_RECENT_MAX_BYTES):
    if limit <= 0 or not os.path.exists(path):
        return []

    chunk_size = 8192
    data = bytearray()
    with open(path, 'rb') as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        newline_target = limit + 1

        while position > 0 and len(data) < max_bytes:
            read_size = min(chunk_size, position, max_bytes - len(data))
            position -= read_size
            handle.seek(position)
            block = handle.read(read_size)
            data[:0] = block
            if data.count(b'\n') >= newline_target:
                break

    return data.decode('utf-8', errors='replace').splitlines()[-limit:]


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
    text = _coerce_text(raw, max_len=80)
    return text or 'unknown'


def _counter_rows(counter, key_name):
    return [{key_name: key, 'count': count} for key, count in counter.most_common()]


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


def _default_summary():
    return {
        'total_events': 0,
        'today_events': 0,
        'last_7_days': 0,
        'last_30_days': 0,
        'invalid_lines': 0,
        'partial_events': 0,
        'unknown_schema_versions': 0,
        'judgement_errors': 0,
    }


def _default_route_bucket():
    return {
        'total': 0,
        'matches': 0,
        'mismatches': 0,
        'parser_failures': 0,
        'exceptions': 0,
        'judgement_errors': 0,
    }


def _default_result(path, now):
    routes = {route: _default_route_bucket() for route in EXPECTED_ROUTES}
    return {
        'generated_at': now.isoformat(),
        'source_path': path,
        'summary': _default_summary(),
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
        'judgement': {
            'errors': 0,
            'by_value': [],
        },
        'exceptions': {
            'total': 0,
            'by_class': [],
        },
        'top_mismatches': [],
        'top_parser_failures': [],
        'top_judgement_errors': [],
        'schema_versions': [],
    }


def _empty_recent_result(path, limit):
    return {
        'generated_at': _utc_now().isoformat(),
        'source_path': path,
        'limit': limit,
        'returned_events': 0,
        'filters': {
            'route': '',
            'parser_status': '',
            'shadow_judgement': '',
            'request_id': '',
            'schema_version': '',
        },
        'summary': {
            'total_events': 0,
            'success': 0,
            'parser_failed': 0,
            'exception': 0,
            'judgement_error': 0,
            'average_latency_ms': 0.0,
        },
        'routes': {route: {'event_count': 0, 'parser_failed': 0, 'average_latency_ms': 0.0} for route in EXPECTED_ROUTES},
        'parser_failures': [],
        'recent_events': [],
        'invalid_lines': 0,
    }


def _derive_parser_status(event):
    raw = _coerce_text(event.get('parser_status'), max_len=40).lower()
    if raw in ('ok', 'failed'):
        return raw
    parser_failure_reason = _coerce_text(event.get('parser_failure_reason'), max_len=240)
    if parser_failure_reason:
        return 'failed'
    exception_class = _coerce_text(event.get('exception_class'), max_len=80)
    if exception_class:
        return 'failed'
    return raw or 'ok'


def _derive_judgement(event, parser_status, parser_failure_reason, exception_class, match_value):
    raw = _coerce_text(_get_first(event, _JUDGEMENT_KEYS), max_len=40).lower()
    if raw:
        return raw
    if match_value is True:
        return 'match'
    if match_value is False:
        return 'mismatch'
    if parser_status == 'failed' or parser_failure_reason or exception_class:
        return 'error' if exception_class or parser_failure_reason else 'failed'
    return 'unknown'


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


def _normalize_recent_event(event, *, line_index):
    if not isinstance(event, dict):
        return None

    parsed_dt = _parse_timestamp(_get_first(event, _TIMESTAMP_KEYS))
    route = _normalize_route(event.get('route')) or _coerce_text(event.get('route'), max_len=80)
    request_id = _coerce_text(event.get('request_id'), max_len=120)
    parser_failure_reason = _sanitize_reason(event.get('parser_failure_reason'))
    exception_class = _coerce_text(event.get('exception_class'), max_len=80)
    exception_message = _sanitize_reason(event.get('exception_message'), max_len=240)
    schema_version = _coerce_text(event.get('schema_version'), max_len=40)
    entry_point = _coerce_text(event.get('entry_point'), max_len=80)
    latency_ms = _coerce_float(_get_first(event, _LATENCY_KEYS))
    parser_status = _derive_parser_status(event)
    match_value = _derive_match(event)
    judgement = _derive_judgement(event, parser_status, parser_failure_reason, exception_class, match_value)
    reason = _sanitize_reason(event.get('reason'))
    if not reason and parser_failure_reason:
        reason = parser_failure_reason
    if not reason and exception_class:
        reason = f'sgf_engine unavailable or failed: {exception_class}'
    if not reason and judgement == 'error' and exception_class:
        reason = f'sgf_engine unavailable or failed: {exception_class}'
    if not reason and judgement == 'failed':
        reason = parser_failure_reason or 'parser failed'

    parser_failed = parser_status == 'failed' or bool(parser_failure_reason)
    has_exception = bool(exception_class)
    success = not parser_failed and not has_exception and judgement not in ('error', 'failed', 'mismatch')

    return {
        'timestamp': parsed_dt.isoformat() if parsed_dt else '',
        'route': route,
        'request_id': request_id,
        'parser_status': parser_status,
        'shadow_judgement': judgement,
        'latency_ms': None if latency_ms is None else round(latency_ms, 3),
        'exception_class': exception_class,
        'schema_version': schema_version,
        'entry_point': entry_point,
        'reason': reason,
        'parser_failure_reason': parser_failure_reason,
        'exception_message': exception_message,
        'details': {
            'schema_version': schema_version or '-',
            'entry_point': entry_point or '-',
            'reason': reason or '-',
            'parser_failure_reason': parser_failure_reason or '-',
            'exception_class': exception_class or '-',
            'exception_message': exception_message or '-',
            'shadow_judgement': judgement or '-',
        },
        'success': success,
        'parser_failed': parser_failed,
        'judgement_error': judgement == 'error',
        'has_exception': has_exception,
        '_sort_key': parsed_dt.timestamp() if parsed_dt else float('-inf'),
        '_line_index': line_index,
    }


def _normalize_and_filter_recent_event(
    event,
    *,
    line_index,
    route=None,
    parser_status=None,
    shadow_judgement=None,
    request_id=None,
    schema_version=None,
):
    normalized = _normalize_recent_event(event, line_index=line_index)
    if normalized is None:
        return None

    if route and normalized['route'] != route:
        return None
    if parser_status and normalized['parser_status'] != parser_status:
        return None
    if shadow_judgement and normalized['shadow_judgement'] != shadow_judgement:
        return None
    if schema_version and normalized['schema_version'] != schema_version:
        return None
    if request_id and request_id.lower() not in normalized['request_id'].lower():
        return None
    return normalized


def _sort_recent_events(events):
    return sorted(
        events,
        key=lambda event: (event.get('_sort_key', float('-inf')), event.get('_line_index', -1)),
        reverse=True,
    )


def recent_shadow_dashboard_data(
    path=None,
    limit=_RECENT_DEFAULT_LIMIT,
    *,
    route=None,
    parser_status=None,
    shadow_judgement=None,
    request_id=None,
    schema_version=None,
):
    path = path or DEFAULT_SHADOW_EVENTS_PATH
    try:
        limit = int(limit or _RECENT_DEFAULT_LIMIT)
    except (TypeError, ValueError):
        limit = _RECENT_DEFAULT_LIMIT
    limit = max(1, min(limit, _RECENT_MAX_LIMIT))
    raw_lines = _tail_lines(path, limit=limit)
    result = _empty_recent_result(path, limit)
    normalized_events = []

    for line_index, raw_line in enumerate(raw_lines):
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            result['invalid_lines'] += 1
            continue
        normalized = _normalize_and_filter_recent_event(
            event,
            line_index=line_index,
            route=route,
            parser_status=parser_status,
            shadow_judgement=shadow_judgement,
            request_id=request_id,
            schema_version=schema_version,
        )
        if normalized is None:
            if isinstance(event, dict):
                # Count invalid JSON only; filtered-out records are expected.
                pass
            else:
                result['invalid_lines'] += 1
            continue
        normalized_events.append(normalized)

    normalized_events = _sort_recent_events(normalized_events)[:limit]
    result['returned_events'] = len(normalized_events)
    result['summary']['total_events'] = len(normalized_events)
    result['filters'] = {
        'route': route or '',
        'parser_status': parser_status or '',
        'shadow_judgement': shadow_judgement or '',
        'request_id': request_id or '',
        'schema_version': schema_version or '',
    }

    latencies = []
    route_latency = defaultdict(list)
    for event in normalized_events:
        normalized_route = event['route']
        if normalized_route and normalized_route not in result['routes']:
            result['routes'][normalized_route] = {
                'event_count': 0,
                'parser_failed': 0,
                'average_latency_ms': 0.0,
            }
        route_bucket = result['routes'].get(normalized_route)
        if route_bucket is not None:
            route_bucket['event_count'] += 1

        if event['success']:
            result['summary']['success'] += 1
        if event['parser_failed']:
            result['summary']['parser_failed'] += 1
            if route_bucket is not None:
                route_bucket['parser_failed'] += 1
            result['parser_failures'].append(event)
        if event['has_exception']:
            result['summary']['exception'] += 1
        if event['judgement_error']:
            result['summary']['judgement_error'] += 1

        latency_ms = event['latency_ms']
        if latency_ms is not None:
            latencies.append(latency_ms)
            if route_bucket is not None:
                route_latency[normalized_route].append(latency_ms)

    if latencies:
        result['summary']['average_latency_ms'] = round(sum(latencies) / len(latencies), 3)
    for route_name, bucket in result['routes'].items():
        values = route_latency.get(route_name, [])
        if values:
            bucket['average_latency_ms'] = round(sum(values) / len(values), 3)

    for event in normalized_events:
        event.pop('_sort_key', None)
        event.pop('_line_index', None)
    for event in result['parser_failures']:
        event.pop('_sort_key', None)
        event.pop('_line_index', None)

    result['recent_events'] = normalized_events
    return result


def aggregate_shadow_events(path=None, now=None):
    now = now or _utc_now()
    path = path or DEFAULT_SHADOW_EVENTS_PATH
    result = _default_result(path, now)
    latency_values = []
    parser_reasons = Counter()
    judgement_counts = Counter()
    exception_classes = Counter()
    mismatch_puzzles = Counter()
    mismatch_routes = defaultdict(set)
    parser_failure_puzzles = Counter()
    parser_failure_routes = defaultdict(set)
    judgement_error_puzzles = Counter()
    judgement_error_routes = defaultdict(set)
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

            schema_version = _coerce_text(event.get('schema_version'), max_len=40)
            if schema_version:
                schema_versions[schema_version] += 1
                if schema_version not in ('shadow-v2', 'shadow-v3'):
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
                result['routes'][route] = _default_route_bucket()

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

            parser_status = _derive_parser_status(event)
            parser_failure_reason = _sanitize_reason(event.get('parser_failure_reason'))
            exception_class = _coerce_text(event.get('exception_class'), max_len=80)
            judgement = _derive_judgement(
                event,
                parser_status,
                parser_failure_reason,
                exception_class,
                match_value,
            )
            if parser_status == 'failed' or parser_failure_reason:
                result['parser']['failures'] += 1
                if route_bucket is not None:
                    route_bucket['parser_failures'] += 1
                parser_reasons[parser_failure_reason or 'unknown'] += 1
                puzzle_id = _puzzle_key(event)
                parser_failure_puzzles[puzzle_id] += 1
                if route:
                    parser_failure_routes[puzzle_id].add(route)

            if judgement == 'error':
                result['summary']['judgement_errors'] += 1
                result['judgement']['errors'] += 1
                if route_bucket is not None:
                    route_bucket['judgement_errors'] += 1
                puzzle_id = _puzzle_key(event)
                judgement_error_puzzles[puzzle_id] += 1
                if route:
                    judgement_error_routes[puzzle_id].add(route)
                judgement_counts[judgement] += 1
            elif judgement:
                judgement_counts[judgement] += 1

            if exception_class:
                result['exceptions']['total'] += 1
                exception_classes[exception_class] += 1
                if route_bucket is not None:
                    route_bucket['exceptions'] += 1

            latency_ms = _coerce_float(_get_first(event, _LATENCY_KEYS))
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
    result['judgement']['by_value'] = _counter_rows(judgement_counts, 'shadow_judgement')
    result['exceptions']['by_class'] = _counter_rows(exception_classes, 'exception_class')
    result['top_mismatches'] = _puzzle_rows(mismatch_puzzles, mismatch_routes)
    result['top_parser_failures'] = _puzzle_rows(parser_failure_puzzles, parser_failure_routes)
    result['top_judgement_errors'] = _puzzle_rows(judgement_error_puzzles, judgement_error_routes)
    result['schema_versions'] = _counter_rows(schema_versions, 'schema_version')
    return result
