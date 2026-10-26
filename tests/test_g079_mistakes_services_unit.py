"""G079 B1 unit tests for the Mistakes Product service ports.

Fake runtime namespace with recording writers: proves call order, admission,
fail-closed propagation and receipt arithmetic. Real writers/DB are proven in
tests/test_g079_mistakes_product_pg.py (disposable PostgreSQL 16).
"""
import ast
from contextvars import ContextVar
from pathlib import Path
from types import SimpleNamespace

import pytest

from g076_nonmap_steps import NonMapRejected
from g079_mistakes_services import build_mistakes_services
from srs_scheduling_core import SrsAdvancePolicy

ROOT = Path(__file__).resolve().parents[1]
Q = {'id': 701, 'rank': '20k', 'difficulty': '20k', 'source': 'fixture/701.sgf',
     'content': '(;GM[1]SZ[5]PL[B];B[aa])'}


class Conn:
    def __init__(self, xp=0):
        self.xp, self.calls = xp, []

    def execute(self, sql, params=()):
        self.calls.append(sql)
        row = {'xp': self.xp, 'elo_rating': 1500}
        return SimpleNamespace(fetchone=lambda: row)


def runtime(**over):
    log = []
    flag = ContextVar('flag', default=True)

    def update_daily_quests(conn, uid, today, **kw):
        log.append(('daily', flag.get(), kw))
        conn.xp += 40  # a quest completion granted by the real writer in Product

    rt = {
        'get_db': None,
        '_load_questions': lambda: [Q, {'id': 702, 'enabled': False}],
        '_practice_identity_for_write': lambda conn, qid: 'uuid-%d' % qid,
        '_map_battle_question_context': lambda q: {'question_revision': 'r'},
        '_practice_premium_in_transaction': lambda conn, uid: False,
        'question_is_free': lambda q: True,
        '_lock_user_for_daily_quota': lambda conn, uid: log.append(('lock', uid)),
        '_daily_quota_snapshot_in_transaction': lambda conn, uid: log.append(('quota', uid)) or {'n': 1},
        '_daily_quota_rejection': lambda snap: None,
        '_load_premium_weekly_rating_helpers': lambda: ('irv-1', None, lambda r: 1234.0),
        'quest_v2_runtime_enabled': lambda: False,
        '_QUEST_LEGACY_DAILY_ENABLED': flag,
        '_update_daily_quests': update_daily_quests,
        '_apply_quest_v2_review_events': lambda conn, **kw: log.append(('v2', kw)),
        'QUEST_CORRECTNESS_SOURCE_AUTHORITATIVE_MISTAKES': 'AUTHORITATIVE_MISTAKES_STEP_SETTLEMENT',
        '_quest_v2_server_now': lambda: 'now',
        '_review_learning_in_transaction': None,
    }
    rt.update(over)
    return rt, log


def test_question_identity_context_ports():
    rt, _ = runtime()
    s = build_mistakes_services(rt, secret='unit')
    assert s.question(None, 701) is Q
    assert s.question(None, 702) is None      # disabled
    assert s.question(None, 999) is None      # unknown
    assert s.identity(None, 701) == 'uuid-701'
    assert s.context(Q) == {'question_revision': 'r'}


@pytest.mark.parametrize('premium,free,expected', [
    (False, True, 'g079-mistakes-rights-v1:free-question'),
    (True, True, 'g079-mistakes-rights-v1:free-question'),
    (True, False, 'g079-mistakes-rights-v1:premium'),
    (False, False, None)])
def test_rights_fingerprint_and_premium_lock(premium, free, expected):
    rt, _ = runtime(_practice_premium_in_transaction=lambda c, u: premium,
                    question_is_free=lambda q: free)
    s = build_mistakes_services(rt, secret='unit')
    if expected is None:
        with pytest.raises(NonMapRejected, match='premium_required'):
            s.admit(Conn(), 101, Q)
    else:
        assert s.admit(Conn(), 101, Q) == expected


def _settle_parts(rt):
    """Return (review_facts, progression) by rebuilding with the same runtime."""
    import g079_mistakes_services as module
    seen = {}
    real_build = module.build_settlement

    def spy(**kw):
        seen.update(kw)
        return real_build(**kw)
    module.build_settlement = spy
    try:
        build_mistakes_services(rt, secret='unit')
    finally:
        module.build_settlement = real_build
    return seen


def test_settlement_uses_always_policy_and_real_bridge():
    rt, _ = runtime()
    seen = _settle_parts(rt)
    assert seen['advance_policy'] is SrsAdvancePolicy.ALWAYS
    assert callable(seen['admit']) and callable(seen['progression'])


@pytest.mark.parametrize('premium', [False, True])
def test_review_facts_locks_user_before_quota(premium):
    rt, log = runtime(_practice_premium_in_transaction=lambda c, u: premium)
    facts = _settle_parts(rt)['admit'](Conn(), 101, Q)
    assert log[0] == ('lock', 101)
    assert (('quota', 101) in log) is (not premium)
    assert (facts.player_rating_snapshot, facts.question_rating_snapshot,
            facts.item_rating_version, facts.question_version) == (1500.0, 1234.0, 'irv-1', 'fixture/701.sgf')


def test_review_facts_daily_limit_rejects():
    rt, _ = runtime(_daily_quota_rejection=lambda s: {'error': 'daily_limit'})
    with pytest.raises(NonMapRejected, match='daily_limit') as info:
        _settle_parts(rt)['admit'](Conn(), 101, Q)
    assert info.value.status == 429


def _progress(rt, conn, *, result='CORRECT', grade=5, credited=True):
    def learning(conn, **kw):
        assert kw['strict'] is True and kw['update_mistakes'] is False and kw['internal'] is True
        conn.xp += 37
        return {'xp_gain': 37, 'combo_streak': 2}
    rt['_review_learning_in_transaction'] = learning
    progression = _settle_parts(rt)['progression']
    ctx = SimpleNamespace(flow='mistakes', uid=101, question=Q)
    verdict = SimpleNamespace(result=result, authoritative_grade=grade)
    srs = SimpleNamespace(progress_credit_granted=credited, existed=False)
    return progression(conn, ctx, verdict, 'g076-nm:abc', srs, {}, 'now')


def test_progression_sums_core_and_actual_quest_xp_legacy_daily():
    rt, log = runtime()
    conn = Conn(xp=100)
    assert _progress(rt, conn) == 37 + 40
    kind, flag_value, kw = log[0]
    assert kind == 'daily' and flag_value is True
    assert kw == {'grade': 5, 'monster_defeated': False, 'monster_type': None,
                  'combo_streak': 2, 'progress_eligible': True, 'shadow_events': None}
    assert not any(entry[0] == 'v2' for entry in log)
    assert rt['_QUEST_LEGACY_DAILY_ENABLED'].get() is True   # token reset


def test_progression_quest_v2_mode_uses_mistakes_source():
    rt, log = runtime(quest_v2_runtime_enabled=lambda: True)
    _progress(rt, Conn(), result='INCORRECT', grade=0, credited=False)
    assert log[0][1] is False     # legacy daily disabled under V2
    v2 = [entry[1] for entry in log if entry[0] == 'v2'][0]
    assert v2['correctness_source'] == 'AUTHORITATIVE_MISTAKES_STEP_SETTLEMENT'
    assert v2['authoritative_answer_correct'] is False
    assert v2['monster_data'] == {} and v2['submission_id'] == 'g076-nm:abc'


def test_writer_failure_propagates_and_flag_resets():
    def broken(conn, uid, today, **kw):
        raise RuntimeError('coin ledger failure')
    rt, _ = runtime(_update_daily_quests=broken)
    with pytest.raises(RuntimeError, match='coin ledger'):
        _progress(rt, Conn())
    assert rt['_QUEST_LEGACY_DAILY_ENABLED'].get() is True


def test_negative_xp_delta_is_invalid_receipt():
    def drain(conn, uid, today, **kw):
        conn.xp -= 1000
    rt, _ = runtime(_update_daily_quests=drain)
    with pytest.raises(NonMapRejected, match='receipt_invalid'):
        _progress(rt, Conn(xp=5000))


def test_services_module_has_no_transaction_lifecycle_outside_owner():
    tree = ast.parse((ROOT / 'g079_mistakes_services.py').read_text(encoding='utf-8'))
    owner = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'transaction')
    owner_calls = {id(n) for n in ast.walk(owner)}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in {'commit', 'rollback', 'close'}):
            assert id(node) in owner_calls, ast.unparse(node)
    # No new reward formula: the module never writes reward tables directly.
    source = (ROOT / 'g079_mistakes_services.py').read_text(encoding='utf-8')
    for sql in ('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP'):
        assert sql + ' ' not in source


def test_app_registers_complete_services_and_quest_source():
    source = (ROOT / 'app.py').read_text(encoding='utf-8-sig')
    assert 'services=_g079_mistakes_services(globals(), secret=app.secret_key)' in source
    assert "QUEST_CORRECTNESS_SOURCE_AUTHORITATIVE_MISTAKES = (\n    'AUTHORITATIVE_MISTAKES_STEP_SETTLEMENT'" in source
