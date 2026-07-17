import datetime as _dt
import json
import math
import os
import time
from collections import Counter, defaultdict

from shadow_event_storage import discover_event_files


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
    'canonical_puzzle_id',
    'legacy_question_id',
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
_AGGREGATE_DEFAULT_MAX_BYTES = 8 * 1024 * 1024
_AGGREGATE_DEFAULT_MAX_EVENTS = 50_000
_AGGREGATE_DEFAULT_LATENCY_MS = 250
_AGGREGATE_MAX_BYTES = 64 * 1024 * 1024
_AGGREGATE_MAX_EVENTS = 250_000
_AGGREGATE_MAX_LATENCY_MS = 5_000
_AGGREGATE_READ_CHUNK_BYTES = 64 * 1024
_AGGREGATE_MEMORY_BUDGET_BYTES = 64 * 1024 * 1024
_AGGREGATE_MAX_GROUP_KEYS = 4_096

_AGGREGATE_MAX_BYTES_ENV = 'SHADOW_DASHBOARD_MAX_BYTES'
_AGGREGATE_MAX_EVENTS_ENV = 'SHADOW_DASHBOARD_MAX_EVENTS'
_AGGREGATE_LATENCY_MS_ENV = 'SHADOW_DASHBOARD_LATENCY_BUDGET_MS'


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


def _iter_reverse_lines_with_budget(path, max_bytes, state):
    """Yield newest JSONL records first without loading the byte window at once.

    ``state`` receives the exact bytes read and whether the selected file was
    consumed completely. The largest raw buffer is one read chunk plus one
    record crossing a chunk boundary; write-side records are capped at 64 KiB.
    Historical oversized records remain bounded by the total byte budget.
    """
    size = os.path.getsize(path)
    lower_bound = max(0, size - max_bytes)
    position = size
    carry = b''
    state['complete'] = lower_bound == 0

    with open(path, 'rb') as handle:
        while position > lower_bound:
            read_size = min(
                _AGGREGATE_READ_CHUNK_BYTES,
                position - lower_bound,
            )
            position -= read_size
            handle.seek(position)
            block = handle.read(read_size)
            state['bytes_read'] += len(block)
            if len(block) != read_size:
                state['complete'] = False

            parts = (block + carry).split(b'\n')
            carry = parts[0]
            for raw_line in reversed(parts[1:]):
                if raw_line.strip():
                    yield raw_line

        if lower_bound == 0 and carry.strip():
            yield carry


def _bounded_int(value, default, *, minimum, maximum):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if not minimum <= parsed <= maximum:
        return default
    return parsed


def _bounded_counter_increment(counter, key, *, fallback='other'):
    if key in counter or len(counter) < _AGGREGATE_MAX_GROUP_KEYS:
        counter[key] += 1
    else:
        counter[fallback] += 1


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


def _default_result(
    path,
    now,
    *,
    max_bytes=_AGGREGATE_DEFAULT_MAX_BYTES,
    max_events=_AGGREGATE_DEFAULT_MAX_EVENTS,
    latency_budget_ms=_AGGREGATE_DEFAULT_LATENCY_MS,
):
    routes = {route: _default_route_bucket() for route in EXPECTED_ROUTES}
    return {
        'generated_at': now.isoformat(),
        'source_path': path,
        'window_complete': True,
        'files_considered': 0,
        'files_scanned': 0,
        'events_scanned': 0,
        'bytes_scanned': 0,
        'scan_truncated': False,
        'duplicate_events_skipped': 0,
        'scan_errors': 0,
        'read_budget': {
            'max_bytes': max_bytes,
            'max_events': max_events,
            'latency_budget_ms': latency_budget_ms,
            'memory_budget_bytes': _AGGREGATE_MEMORY_BUDGET_BYTES,
            'read_chunk_bytes': _AGGREGATE_READ_CHUNK_BYTES,
        },
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
        'candidate_diagnostics': {
            'candidate_only_detected': 0,
            'by_source': [],
            'classes': [],
            'known_legacy_bug': 0,
        },
        'agreement_window': {
            'matches': 0,
            'mismatches': 0,
            'rate': None,
            'window_complete': True,
        },
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
    classification = _coerce_text(event.get('classification'), max_len=80)
    if classification == 'legacy_accepts_shadow_candidate_match':
        # Explained candidate-only difference: neither ordinary agreement nor
        # unexplained disagreement.
        return None
    if classification == 'legacy_rejects_transform_candidate':
        return False
    for key in _MATCH_KEYS:
        coerced = _coerce_bool(event.get(key))
        if coerced is not None:
            return coerced
    legacy = (
        event.get('source_judgement')
        or event.get('legacy_verdict')
        or event.get('legacy_judgement')
    )
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
    classification = _coerce_text(event.get('classification'), max_len=80)
    canonical_puzzle_id = _coerce_text(event.get('canonical_puzzle_id'), max_len=80) or None
    candidate_source = _coerce_text(event.get('candidate_source'), max_len=40) or None
    if candidate_source not in (None, 'accepted_moves', 'katago_best_move'):
        candidate_source = None
    candidate_only_detected = _coerce_bool(event.get('candidate_only_detected'))
    invalid_identity = _coerce_bool(event.get('invalid_identity'))
    gf003_related = _coerce_bool(event.get('gf003_related'))
    legacy_unknown = _coerce_bool(event.get('legacy_unknown'))
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
        'classification': classification,
        'canonical_puzzle_id': canonical_puzzle_id,
        'candidate_only_detected': candidate_only_detected,
        'candidate_source': candidate_source,
        'invalid_identity': invalid_identity,
        'gf003_related': gf003_related,
        'legacy_unknown': legacy_unknown,
        'player_color': _coerce_text(event.get('player_color'), max_len=4) or None,
        'player_move_sgf': _coerce_text(event.get('player_move_sgf'), max_len=24) or None,
        'player_move_board_coordinate': _coerce_text(
            event.get('player_move_board_coordinate'), max_len=16
        ) or None,
        'reason': reason,
        'parser_failure_reason': parser_failure_reason,
        'exception_message': exception_message,
        'details': {
            'schema_version': schema_version or '-',
            'entry_point': entry_point or '-',
            'classification': classification or '-',
            'canonical_puzzle_id': canonical_puzzle_id or '-',
            'candidate_only_detected': candidate_only_detected,
            'candidate_source': candidate_source or '-',
            'invalid_identity': invalid_identity,
            'gf003_related': gf003_related,
            'legacy_unknown': legacy_unknown,
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


def aggregate_shadow_events(
    path=None,
    now=None,
    *,
    max_bytes=None,
    max_events=None,
    latency_budget_ms=None,
    monotonic=None,
):
    """Aggregate the newest bounded window across active and rotated JSONL files.

    Storage discovery defines file precedence (active, then rotations newest
    first). Records are scanned tail-first, so the first copy of an ``event_id``
    wins. Aggregates are commutative; timestamps are normalized for time-window
    metrics without retaining whole event dictionaries in memory.
    """
    now = now or _utc_now()
    path = path or DEFAULT_SHADOW_EVENTS_PATH
    max_bytes = _bounded_int(
        os.environ.get(_AGGREGATE_MAX_BYTES_ENV) if max_bytes is None else max_bytes,
        _AGGREGATE_DEFAULT_MAX_BYTES,
        minimum=1,
        maximum=_AGGREGATE_MAX_BYTES,
    )
    max_events = _bounded_int(
        os.environ.get(_AGGREGATE_MAX_EVENTS_ENV) if max_events is None else max_events,
        _AGGREGATE_DEFAULT_MAX_EVENTS,
        minimum=1,
        maximum=_AGGREGATE_MAX_EVENTS,
    )
    latency_budget_ms = _bounded_int(
        (
            os.environ.get(_AGGREGATE_LATENCY_MS_ENV)
            if latency_budget_ms is None
            else latency_budget_ms
        ),
        _AGGREGATE_DEFAULT_LATENCY_MS,
        minimum=1,
        maximum=_AGGREGATE_MAX_LATENCY_MS,
    )
    result = _default_result(
        path,
        now,
        max_bytes=max_bytes,
        max_events=max_events,
        latency_budget_ms=latency_budget_ms,
    )
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
    candidate_sources = Counter()
    candidate_classes = Counter()
    seen_event_ids = set()

    event_files = discover_event_files(path)
    result['files_considered'] = len(event_files)
    if not event_files:
        return result

    clock = monotonic or time.monotonic
    deadline = clock() + (latency_budget_ms / 1000.0)
    stop_scan = False

    for file_index, event_path in enumerate(event_files):
        if result['events_scanned'] >= max_events:
            result['scan_truncated'] = True
            break
        remaining_bytes = max_bytes - result['bytes_scanned']
        if remaining_bytes <= 0 or clock() >= deadline:
            result['scan_truncated'] = True
            break

        state = {'bytes_read': 0, 'complete': False}
        result['files_scanned'] += 1
        try:
            raw_lines = _iter_reverse_lines_with_budget(
                event_path,
                remaining_bytes,
                state,
            )
            for raw_bytes in raw_lines:
                if clock() >= deadline:
                    result['scan_truncated'] = True
                    stop_scan = True
                    break
                if result['events_scanned'] >= max_events:
                    result['scan_truncated'] = True
                    stop_scan = True
                    break

                raw_line = raw_bytes.decode('utf-8', errors='replace').strip()
                if not raw_line:
                    continue
                try:
                    event = json.loads(raw_line)
                except (json.JSONDecodeError, ValueError):
                    result['summary']['invalid_lines'] += 1
                    continue
                if not isinstance(event, dict):
                    result['summary']['invalid_lines'] += 1
                    continue

                result['events_scanned'] += 1
                event_id = _coerce_text(event.get('event_id'), max_len=120)
                if event_id:
                    if event_id in seen_event_ids:
                        result['duplicate_events_skipped'] += 1
                        continue
                    seen_event_ids.add(event_id)

                result['summary']['total_events'] += 1
                if _event_is_partial(event):
                    result['summary']['partial_events'] += 1

                schema_version = _coerce_text(event.get('schema_version'), max_len=40)
                if schema_version:
                    _bounded_counter_increment(schema_versions, schema_version)
                    if schema_version not in ('shadow-v2', 'shadow-v3', 'shadow-v4'):
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

                raw_route = _coerce_text(event.get('route'), max_len=120)
                route = _normalize_route(raw_route)
                if (
                    route
                    and route not in result['routes']
                    and len(result['routes']) < _AGGREGATE_MAX_GROUP_KEYS
                ):
                    result['routes'][route] = _default_route_bucket()

                route_bucket = result['routes'].get(route)
                if route_bucket is not None:
                    route_bucket['total'] += 1

                classification = _coerce_text(event.get('classification'), max_len=80)
                candidate_only = _coerce_bool(event.get('candidate_only_detected'))
                candidate_source = _coerce_text(event.get('candidate_source'), max_len=40)
                if candidate_only is True:
                    result['candidate_diagnostics']['candidate_only_detected'] += 1
                    if candidate_source not in ('accepted_moves', 'katago_best_move'):
                        candidate_source = 'unknown'
                    _bounded_counter_increment(candidate_sources, candidate_source)
                if classification in (
                    'legacy_accepts_shadow_candidate_match',
                    'legacy_rejects_transform_candidate',
                ):
                    _bounded_counter_increment(candidate_classes, classification)
                if classification == 'legacy_rejects_transform_candidate':
                    result['candidate_diagnostics']['known_legacy_bug'] += 1

                match_value = _derive_match(event)
                if match_value is True:
                    result['agreement_window']['matches'] += 1
                    if route_bucket is not None:
                        route_bucket['matches'] += 1
                elif match_value is False:
                    result['agreement_window']['mismatches'] += 1
                    if route_bucket is not None:
                        route_bucket['mismatches'] += 1
                    puzzle_id = _puzzle_key(event)
                    _bounded_counter_increment(mismatch_puzzles, puzzle_id)
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
                    _bounded_counter_increment(
                        parser_reasons,
                        parser_failure_reason or 'unknown',
                    )
                    puzzle_id = _puzzle_key(event)
                    _bounded_counter_increment(parser_failure_puzzles, puzzle_id)
                    if route:
                        parser_failure_routes[puzzle_id].add(route)

                if judgement == 'error':
                    result['summary']['judgement_errors'] += 1
                    result['judgement']['errors'] += 1
                    if route_bucket is not None:
                        route_bucket['judgement_errors'] += 1
                    puzzle_id = _puzzle_key(event)
                    _bounded_counter_increment(judgement_error_puzzles, puzzle_id)
                    if route:
                        judgement_error_routes[puzzle_id].add(route)
                if judgement:
                    _bounded_counter_increment(judgement_counts, judgement)

                if exception_class:
                    result['exceptions']['total'] += 1
                    _bounded_counter_increment(exception_classes, exception_class)
                    if route_bucket is not None:
                        route_bucket['exceptions'] += 1

                latency_ms = _coerce_float(_get_first(event, _LATENCY_KEYS))
                if latency_ms is not None:
                    latency_values.append(latency_ms)
        except (OSError, ValueError):
            result['scan_errors'] += 1
            result['scan_truncated'] = True
        finally:
            result['bytes_scanned'] += state['bytes_read']

        if not state['complete']:
            result['scan_truncated'] = True
            stop_scan = True
        if stop_scan:
            break
        if file_index + 1 < len(event_files) and result['bytes_scanned'] >= max_bytes:
            result['scan_truncated'] = True
            break

    if result['files_scanned'] < result['files_considered']:
        result['scan_truncated'] = True
    result['window_complete'] = not result['scan_truncated'] and result['scan_errors'] == 0
    result['agreement_window']['window_complete'] = result['window_complete']

    agreement_total = (
        result['agreement_window']['matches']
        + result['agreement_window']['mismatches']
    )
    if result['window_complete'] and agreement_total:
        result['agreement_window']['rate'] = round(
            result['agreement_window']['matches'] / agreement_total,
            6,
        )

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
    result['candidate_diagnostics']['by_source'] = _counter_rows(
        candidate_sources,
        'candidate_source',
    )
    result['candidate_diagnostics']['classes'] = _counter_rows(
        candidate_classes,
        'classification',
    )
    return result
