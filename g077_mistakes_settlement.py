"""Borrowed-transaction Mistakes terminal writer.

G079: registered from app.py through g079_mistakes_services.py, which supplies
the Product admission (ReviewFacts) and the complete remaining policy. The
historical G077/G078 notes below describe this module's own contract.

Implemented atomic subset: canonical review identity, lifetime SRS credit and
per-attempt mistake analytics. The existing nonmap cursor/event is the durable
receipt and replay boundary. No DDL, connection ownership or Battle evidence.

Admission must lock the user and enforce current rights/quota, returning the
existing review rating snapshots. Progression must implement ALL remaining
Review effects (including wrong-answer shields, XP/rank, quests, pet, coins and
badges) on this connection without committing or swallowing failures. Missing
policy is HOLD, even for an already credited card. Fixture policies are not
Product admission. SQLite requires BEGIN IMMEDIATE; PostgreSQL requires the
normal adapter and user/session row locks.
"""
from dataclasses import dataclass
import datetime
import json

from g076_nonmap_steps import NonMapRejected, _session
from g076_server_step_authority import adjudicate_next_step
from practice_answer_authority import canonicalize_practice_answer, judge_practice_answer
from question_idempotency import canonical_payload_digest, insert_review_log_with_identity
from srs_scheduling_core import (
    apply_srs_scheduling, ProgressCreditPolicy, SrsAdvancePolicy,
)


@dataclass(frozen=True)
class ReviewFacts:
    player_rating_snapshot: float | None
    question_rating_snapshot: float | None
    item_rating_version: str
    question_version: str


def build_learning_progression(*, learning, remaining_policy=None):
    """Bridge the extracted real review core, held until ALL policy is supplied.

    learning is app._review_learning_in_transaction, never ReviewService.
    remaining_policy must implement quest modes, coin/food ledgers and any
    applicable noncombat progression on this connection, with no transaction
    lifecycle calls or swallowed failures. It returns additional XP actually
    written, including quest XP. A callable is a dependency, not certification;
    the Product policy is g079_mistakes_services.remaining_policy.
    """
    def progression(conn, ctx, verdict, event_id, srs, prior, now):
        if not callable(learning) or not callable(remaining_policy):
            raise NonMapRejected('mistakes_remaining_reward_policy_hold', 503)
        if ctx.flow != 'mistakes':
            raise NonMapRejected('mistakes_context_required', 403)
        result = learning(
            conn, uid=ctx.uid, qid=ctx.question['id'], q_info=ctx.question,
            grade=verdict.authoritative_grade, now=now, internal=True,
            submission_id=event_id,
            should_grant_progress=srs.progress_credit_granted,
            srs_row_existed=srs.existed, strict=True, update_mistakes=False,
        )
        xp = result['xp_gain']
        if type(xp) is not int or xp < 0:
            raise NonMapRejected('mistakes_progression_receipt_invalid', 503)
        extra = remaining_policy(conn, ctx, verdict, event_id, srs, prior, now, result)
        if type(extra) is not int or extra < 0:
            raise NonMapRejected('mistakes_progression_receipt_invalid', 503)
        return xp + extra

    return progression


def build_settlement(*, secret, admit, progression=None, advance_policy):
    """Return a MistakesServices.settle port. No implicit reward/SRS policy.

    progression(conn, ctx, verdict, event_id, srs, prior_mistake, now) returns
    the exact nonnegative integer XP actually written. It is called on every
    new terminal event, including wrong and repeated correct, never on replay.
    The sticky srs.progress_credit_granted gates lifetime reward effects;
    srs.existed gates the first-answer bonus. Exceptions must reach the outer
    transaction owner. Do not call this port outside the trusted step bridge.
    """
    if not isinstance(advance_policy, SrsAdvancePolicy):
        raise ValueError('explicit SrsAdvancePolicy required')

    def settle(conn, ctx, canonical, verdict, event_id):
        if not callable(admit) or not callable(progression):
            raise NonMapRejected('mistakes_progression_policy_hold', 503)
        if ctx.flow != 'mistakes':
            raise NonMapRejected('mistakes_context_required', 403)
        # SQLite serialization is a caller obligation, not an implicit BEGIN.
        raw = getattr(conn, '_conn', conn)
        if raw.__class__.__module__.startswith('sqlite3') and not raw.in_transaction:
            raise NonMapRejected('mistakes_transaction_required', 503)
        row, _ = _session(conn, ctx, secret)
        if event_id != 'g076-nm:' + row['id'] or row['state'] != 'OPEN':
            raise NonMapRejected('mistakes_terminal_identity_conflict')
        # Bind this terminal to the persisted cursor, not an arbitrary complete
        # answer for the same question. Only one new player move is admissible.
        moves = canonical.payload.get('moves', [])
        history = json.loads(row['history_json'])
        if (len(history) != row['step_index'] or len(moves) != len(history) + 1 or
                any(m.get('action') != 'play' or m.get('color') != ctx.attempt['player_color']
                    for m in moves) or
                [[m.get('x'), m.get('y')] for m in moves[:-1]] != history):
            raise NonMapRejected('mistakes_terminal_history_conflict')
        rebuilt = canonicalize_practice_answer({'moves': [
            {'x': m.get('x'), 'y': m.get('y')} for m in moves]}, ctx.attempt)
        if rebuilt.payload != canonical.payload:
            raise NonMapRejected('mistakes_canonical_binding_conflict')
        decision = adjudicate_next_step(ctx.question,
            player_color=ctx.attempt['player_color'], board_size=ctx.attempt['board_size'],
            trusted_history=history, move=(moves[-1]['x'], moves[-1]['y']))
        if decision.status not in ('CORRECT', 'INCORRECT') or decision.status != verdict.result:
            raise NonMapRejected('mistakes_terminal_verdict_conflict')
        # Rejudge canonical server evidence, never accept a supplied grade alone.
        actual = judge_practice_answer(ctx.question, ctx.attempt, canonical)
        if (actual.result, actual.authoritative_grade) != (verdict.result, verdict.authoritative_grade):
            raise NonMapRejected('mistakes_verdict_conflict')
        facts = admit(conn, ctx.uid, ctx.question)
        if not isinstance(facts, ReviewFacts):
            raise NonMapRejected('mistakes_review_policy_hold', 503)
        q, uid = ctx.question, ctx.uid
        prior = conn.execute('SELECT * FROM mistake_log WHERE user_id=? AND question_id=?',
                             (uid, q['id'])).fetchone()
        if prior is None:
            raise NonMapRejected('mistake_not_owned', 403)
        now = datetime.datetime.now().isoformat()
        digest = canonical_payload_digest({
            'flow': ctx.flow, 'user_id': uid, 'scope': ctx.scope,
            'question_id': q['id'], 'binding': row['binding'],
            'answer': canonical.payload, 'grade': actual.authoritative_grade,
        })
        inserted = insert_review_log_with_identity(
            conn, user_id=uid, question_id=q['id'], grade=actual.authoritative_grade,
            topic=q.get('topic', ''), level=q.get('level', ''),
            difficulty=q.get('difficulty', ''), reviewed_at=now, response_ms=None,
            discipline=q.get('discipline') or 'whole_board',
            player_rating_snapshot=facts.player_rating_snapshot,
            question_rating_snapshot=facts.question_rating_snapshot,
            item_rating_version=facts.item_rating_version,
            question_version=facts.question_version, source_context='mistakes',
            is_scaffolding=0, training_set_id=None, submission_id=event_id,
            submission_payload_hash=digest)
        if not inserted['inserted']:
            # A review without its terminal receipt is NOT a successful replay.
            # Normal retries return the saved nonmap event before entering here.
            code = ('mistakes_submission_conflict' if
                    inserted['existing']['submission_payload_hash'] != digest else
                    'mistakes_receipt_missing')
            raise NonMapRejected(code)
        srs = apply_srs_scheduling(
            conn, user_id=uid, question_id=q['id'], grade=actual.authoritative_grade,
            now=now, progress_credit_policy=ProgressCreditPolicy.FIRST_PASS_ONLY,
            advance_policy=advance_policy)
        if actual.authoritative_grade < 3:
            conn.execute('UPDATE mistake_log SET wrong_count=wrong_count+1,last_wrong_at=? '
                         'WHERE user_id=? AND question_id=?', (now, uid, q['id']))
        else:
            conn.execute('UPDATE mistake_log SET correct_after=correct_after+1,last_correct_at=? '
                         'WHERE user_id=? AND question_id=?', (now, uid, q['id']))
        xp = progression(conn, ctx, actual, event_id, srs, dict(prior), now)
        if type(xp) is not int or xp < 0:
            raise NonMapRejected('mistakes_progression_receipt_invalid', 503)
        return {'submission_id': event_id, 'xp_awarded': xp,
                'srs': {name: getattr(srs, name) for name in
                        ('ease_factor', 'interval', 'repetitions', 'due_date')}}

    return settle
