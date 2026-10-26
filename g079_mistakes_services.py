"""G079 B1: Product services for the server-step Mistakes (錯題本) mode.

Every port borrows ONE caller-owned transaction and reuses the existing app.py
authorities through ``runtime`` (app.py's late-bound module namespace):

* question / identity / context: the canonical enabled record, the existing
  attachable canonical UUID (never minted or repaired) and the content-derived
  revision context used by Practice and Map Battle.
* admit: the existing Premium/free entitlement on the borrowed connection.
* settle: G077 terminal writer + the extracted learning core
  (``_review_learning_in_transaction``) + the existing daily-quest, quest-XP,
  pet-food, capped-coin and Quest V2 writers. No new reward formula, no flat
  per-answer coin, no battle kill/drop/star is fabricated.

Nothing here commits, rolls back, opens a second connection or swallows a
writer failure: any exception rolls back SRS, rewards, review_log and the step
receipt together. Daily free quota and the daily coin cap are serialized by
the existing users-row lock (``_lock_user_for_daily_quota``) taken before any
reward write. No runtime DDL; the schema comes from
``migrations/g079_mistakes_steps_v1.py`` (explicitly invoked).
"""
from contextlib import contextmanager
import datetime

from g076_mistakes_product import MistakesServices
from g076_nonmap_steps import NonMapRejected
from g077_mistakes_settlement import ReviewFacts, build_learning_progression, build_settlement
from srs_scheduling_core import SrsAdvancePolicy

RIGHTS_VERSION = 'g079-mistakes-rights-v1'
REQUIRED_SCHEMA = (
    ('g076_mistakes_attempts', 'user_id,question_id,slot_date,content_hash,rights_hash,attempt_token'),
    ('g076_nonmap_sessions', 'id,user_id,flow,binding,step_index,history_json,state'),
    ('g076_nonmap_events', 'session_id,step_index,request_hash,response_json'),
)


def _is_sqlite(conn):
    raw = getattr(conn, '_conn', conn)
    return raw.__class__.__module__.startswith('sqlite3')


def build_mistakes_services(runtime, *, secret):
    """Return the complete MistakesServices bound to app.py's namespace."""
    R = runtime

    @contextmanager
    def transaction():
        conn = R['get_db']()
        try:
            conn.execute('BEGIN IMMEDIATE' if _is_sqlite(conn) else 'BEGIN')
            # Read-only schema preflight: an unmigrated database is HOLD, never
            # a silent legacy fallback or runtime DDL.
            try:
                for table, columns in REQUIRED_SCHEMA:
                    conn.execute('SELECT ' + columns + ' FROM ' + table + ' WHERE 1=0')
            except Exception as error:
                raise NonMapRejected('mistakes_schema_unavailable', 503) from error
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def question(conn, qid):
        matches = [q for q in R['_load_questions']()
                   if isinstance(q, dict) and type(q.get('id')) is int and q['id'] == qid]
        if len(matches) != 1 or matches[0].get('enabled', True) is False:
            return None
        return matches[0]

    def identity(conn, qid):
        # Existing strict write gate: cold/missing/retired/ambiguous -> 503.
        return R['_practice_identity_for_write'](conn, qid)

    def context(q):
        return R['_map_battle_question_context'](q)

    def entitlement(conn, uid, q):
        premium = bool(R['_practice_premium_in_transaction'](conn, uid))
        free = bool(R['question_is_free'](q))
        if not premium and not free:
            raise NonMapRejected('premium_required', 403)
        return premium, free

    def admit(conn, uid, q):
        # Rights fingerprint bound into the day's attempt row. A free question
        # stays admitted regardless of plan; a Premium-only question is bound
        # to the live Premium entitlement and re-checked on every request.
        _, free = entitlement(conn, uid, q)
        return RIGHTS_VERSION + ':' + ('free-question' if free else 'premium')

    def review_facts(conn, uid, q):
        """Terminal admission: user lock, entitlement, free quota, snapshots."""
        R['_lock_user_for_daily_quota'](conn, uid)
        premium, _ = entitlement(conn, uid, q)
        if not premium:
            snapshot = R['_daily_quota_snapshot_in_transaction'](conn, uid)
            if R['_daily_quota_rejection'](snapshot):
                raise NonMapRejected('daily_limit', 429)
        item_rating_version, _, rank_to_rating = R['_load_premium_weekly_rating_helpers']()
        player = conn.execute('SELECT elo_rating FROM users WHERE id=?', (uid,)).fetchone()
        return ReviewFacts(
            player_rating_snapshot=float(player['elo_rating'] or 1400) if player else 1400.0,
            question_rating_snapshot=rank_to_rating(q.get('rank') or q.get('difficulty')),
            item_rating_version=item_rating_version,
            question_version=str(q.get('source') or q['id']),
        )

    def xp_of(conn, uid):
        row = conn.execute('SELECT xp FROM user_stats WHERE user_id=?', (uid,)).fetchone()
        return int((row['xp'] if row else 0) or 0)

    def remaining_policy(conn, ctx, verdict, event_id, srs, prior, now, learning):
        """Non-combat review tail, same writers and order as the Map Battle
        handoff (_map_battle_noncombat_progression + Quest V2), on this conn."""
        uid = ctx.uid
        before = xp_of(conn, uid)
        quest_v2 = bool(R['quest_v2_runtime_enabled']())
        legacy_flag = R['_QUEST_LEGACY_DAILY_ENABLED']
        token = legacy_flag.set(not quest_v2)
        try:
            R['_update_daily_quests'](
                conn, uid, datetime.date.today().isoformat(),
                grade=verdict.authoritative_grade,
                monster_defeated=False,      # Mistakes never defeats a monster
                monster_type=None,
                combo_streak=learning['combo_streak'],
                progress_eligible=srs.progress_credit_granted,
                shadow_events=None,
            )
        finally:
            legacy_flag.reset(token)
        if quest_v2:
            R['_apply_quest_v2_review_events'](
                conn, uid=uid, submission_id=event_id,
                authoritative_answer_correct=(verdict.result == 'CORRECT'),
                correctness_source=R['QUEST_CORRECTNESS_SOURCE_AUTHORITATIVE_MISTAKES'],
                monster_data={}, occurred_at=R['_quest_v2_server_now'](),
                should_grant_progress=srs.progress_credit_granted,
            )
        gained = xp_of(conn, uid) - before
        if gained < 0:
            raise NonMapRejected('mistakes_progression_receipt_invalid', 503)
        return gained

    progression = build_learning_progression(
        learning=lambda *a, **kw: R['_review_learning_in_transaction'](*a, **kw),
        remaining_policy=remaining_policy)
    settle = build_settlement(
        secret=secret, admit=review_facts, progression=progression,
        # Server-judged review modes (Map Battle, Lord, Guild) always advance;
        # anti-farming is the sticky FIRST_PASS_ONLY progress credit.
        advance_policy=SrsAdvancePolicy.ALWAYS)
    return MistakesServices(transaction=transaction, question=question, identity=identity,
                            context=context, admit=admit, settle=settle)
