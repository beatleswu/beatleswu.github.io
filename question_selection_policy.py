"""Read-only, player-scoped 24h preference; due reviews bypass suppression."""
from datetime import datetime, timedelta, timezone


def _server_correct(row):
    from srs_review_authority import is_authoritative_review_source_context, is_authoritative_review_source
    from guild_quest_answer_service import decode_guild_quest_verdict
    from lord_trial_answer_service import decode_lord_trial_verdict
    context = row['source_context']
    for decode in (decode_guild_quest_verdict, decode_lord_trial_verdict):
        verdict = decode(context)
        if verdict:
            return verdict['verdict'] == 'AUTHORITATIVE_PASS'
    return (row['grade'] is not None and row['grade'] >= 3 and (
        is_authoritative_review_source_context(context) or is_authoritative_review_source(row['source'])))


def recent_correct_ids(conn, user_id, *, now=None):
    if not user_id:
        return set()
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is not None:
        now = now.astimezone(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(hours=24)
    rows = conn.execute(
        'SELECT question_id, grade, source, source_context, reviewed_at FROM review_log '
        'WHERE user_id=? AND reviewed_at>=?',
        (user_id, cutoff.date().isoformat()),
    ).fetchall()
    result = set()
    for row in rows:
        if not _server_correct(row):
            continue
        try:
            occurred = datetime.fromisoformat(str(row['reviewed_at']).replace('Z', '+00:00'))
            if occurred.tzinfo is not None:
                occurred = occurred.astimezone(timezone.utc).replace(tzinfo=None)
            if cutoff < occurred <= now:
                result.add(row['question_id'])
        except (ValueError, TypeError):
            continue
    return result


def prefer_not_recent(candidates, recent, *, due=(), key=lambda item: item['id']):
    """Stable partition retains the full permission-filtered fallback pool."""
    due = set(due)
    return sorted(candidates, key=lambda item: key(item) in recent and key(item) not in due)
