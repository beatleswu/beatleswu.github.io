"""R5 disposable SQLite settlement candidate. No runtime registration or DDL.

Catalog membership MUST be a trusted, frozen projection of questions.json in
main.g076_grimoire_catalog_members, installed with the fixture before issuance.
This is an explicit integration dependency, NOT a runtime catalog migration.
All catalog/state reads and writes use the caller's single transaction. Missing
local catalog fails closed: no fallback to get_ldb(), files, or another DB.
Never call directly as an HTTP answer handler: exactly-once is owned by R4.
"""
import hashlib
import json
import sqlite3

from g076_grimoire_adapter import GrimoireRejected, _settle_node_mastery


def catalog_revision(conn):
    """Trusted loader must include this digest in q['g076_catalog_revision'].

    R4 already binds every question field. A changed projection therefore
    invalidates old attempts without changing token/nonce/once-only logic.
    Digest provides binding, not authority to install a catalog projection.
    """
    for name in ('grimoires', 'g076_grimoire_catalog_members'):
        if not conn.execute("SELECT 1 FROM main.sqlite_master WHERE type='table' AND name=?",
                            (name,)).fetchone():
            raise GrimoireRejected('same_database_catalog_required', 503)
    catalogs = [list(r) for r in conn.execute('SELECT id,node_count FROM main.grimoires ORDER BY id')]
    members = [list(r) for r in conn.execute('SELECT question_id,grimoire_id '
                'FROM main.g076_grimoire_catalog_members ORDER BY question_id,grimoire_id')]
    return hashlib.sha256(json.dumps([catalogs,members], separators=(',', ':')).encode()).hexdigest()


def _ids(raw):
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        raise GrimoireRejected('invalid_daily_cache', 503) from None
    if not isinstance(value, list) or any(type(i) is not int or i < 1 for i in value):
        raise GrimoireRejected('invalid_daily_cache', 503)
    return value


def settle_catalog_and_cache(conn, *, uid, question, correct, event_id, now):
    """Supply as R4 settle callback. No commit, new connection, XP or reward.

    Rank advances at most ONE level per new attempt, never falls, exactly like
    legacy. Denominator is max(1, node_count), NOT answered-node count. Cache
    completion includes incorrect answers and is independent of mastery rank.
    """
    if type(conn) is not sqlite3.Connection or not conn.in_transaction:
        raise GrimoireRejected('same_transaction_sqlite_required', 503)
    # Avoid temporary-table shadowing or attached-DB catalog ambiguity.
    for name in ('node_mastery', 'player_grimoire_progress', 'daily_training_cache'):
        if not conn.execute("SELECT 1 FROM main.sqlite_master WHERE type='table' AND name=?",
                            (name,)).fetchone():
            raise GrimoireRejected('local_settlement_schema_required', 503)
    if conn.execute("SELECT 1 FROM sqlite_temp_master WHERE type IN ('table','view')").fetchone():
        raise GrimoireRejected('temporary_schema_hold', 503)
    gid = question.get('grimoire_id')
    members, denominator = [], None
    if gid:
        if type(gid) is not int or gid < 1:
            raise GrimoireRejected('invalid_catalog_id', 503)
        if question.get('g076_catalog_revision') != catalog_revision(conn):
            raise GrimoireRejected('catalog_projection_revision_changed', 503)
        row = conn.execute('SELECT node_count FROM main.grimoires WHERE id=?', (gid,)).fetchone()
        # Missing legacy row uses 1, but an incomplete local projection must HOLD.
        if not row or type(row['node_count']) is not int:
            raise GrimoireRejected('catalog_projection_incomplete', 503)
        denominator = max(1, row['node_count'])
        members = [r['question_id'] for r in conn.execute(
            'SELECT question_id FROM main.g076_grimoire_catalog_members WHERE grimoire_id=?', (gid,))]
        if (question['id'] not in members or len(members) != len(set(members)) or
                any(type(i) is not int or i < 1 for i in members)):
            raise GrimoireRejected('catalog_projection_incomplete', 503)

    cache = conn.execute('SELECT question_ids,completed_ids FROM main.daily_training_cache '
                         'WHERE user_id=? AND date=?', (uid, now[:10])).fetchone()
    qids, done = (_ids(cache['question_ids']), _ids(cache['completed_ids'])) if cache else ([], [])
    receipt = _settle_node_mastery(conn, uid=uid, question=question, correct=correct,
                                   event_id=event_id, now=now)
    if gid:
        # Join rather than a parameter-per-member IN clause: no SQLite bind limit.
        purity = conn.execute('''SELECT COALESCE(SUM(n.purity),0) FROM main.node_mastery n
            JOIN main.g076_grimoire_catalog_members m ON m.question_id=n.question_id
            WHERE n.user_id=? AND m.grimoire_id=?''', (uid, gid)).fetchone()[0] / denominator
        old = conn.execute('SELECT * FROM main.player_grimoire_progress '
                           'WHERE user_id=? AND grimoire_id=?', (uid, gid)).fetchone()
        rank = old['rank'] if old else 0
        thresholds = {0: .3, 1: .6, 2: .8, 3: 1.0}
        if rank in thresholds and purity >= thresholds[rank]:
            rank += 1
        conn.execute('''INSERT INTO main.player_grimoire_progress
            (user_id,grimoire_id,rank,purity,total_attempts,correct_count,last_studied_at)
            VALUES (?,?,?,?,?,?,?) ON CONFLICT(user_id,grimoire_id) DO UPDATE SET
            rank=excluded.rank,purity=excluded.purity,total_attempts=excluded.total_attempts,
            correct_count=excluded.correct_count,last_studied_at=excluded.last_studied_at''',
            (uid, gid, rank, purity, (old['total_attempts'] if old else 0) + 1,
             (old['correct_count'] if old else 0) + int(correct), now))
    if question['id'] in qids and question['id'] not in done:
        conn.execute('UPDATE main.daily_training_cache SET completed_ids=? WHERE user_id=? AND date=?',
                     (json.dumps(done + [question['id']]), uid, now[:10]))
    return receipt
