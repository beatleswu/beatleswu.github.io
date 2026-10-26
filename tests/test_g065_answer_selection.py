"""Offline fixtures: no app bootstrap, network, corpus or player DB access."""
import ast
import datetime
import os
import re
from pathlib import Path
import sqlite3
import subprocess
import sys
import types
from contextlib import nullcontext

import pytest

import map_battle_runtime as runtime
from question_selection_policy import recent_correct_ids, prefer_not_recent
from sgf_engine.parser.sgf_parser import parse_sgf

BASELINE = os.environ.get('G065_BASELINE') == '1'
ROOT = Path(__file__).resolve().parents[1]
if BASELINE:
    source = subprocess.check_output(['git', 'show', 'd0f16e6:map_battle_runtime.py'], cwd=ROOT).decode('utf-8')
    runtime = types.ModuleType('g065_baseline_runtime')
    sys.modules[runtime.__name__] = runtime
    exec(compile(source, 'd0:map_battle_runtime.py', 'exec'), runtime.__dict__)


def judge(sgf, coords, **metadata):
    question = dict(id=1, content=sgf, **metadata)
    context = dict(board_size=5, player_color='B', transform_id='identity')
    payload = dict(battle_id='offline', attempt_id='a', submission_nonce='n',
                   battle_revision=0, question_revision='r', player_color='B',
                   transform_id='identity', transform_version='v',
                   moves=[dict(x=x, y=y) for x, y in coords])
    return runtime.judge_map_battle_answer_v1(question, context,
                                            runtime.canonicalize_answer(payload, context))


EXPLICIT = '(;SZ[5]PL[B](;B[aa]C[G065:CORRECT])(;B[bb]C[G065:INCORRECT]))'


def test_explicit_success_and_failure_control():
    assert judge(EXPLICIT, [(0, 0)], answer_policy='g065-explicit-v1').result == 'CORRECT'
    assert judge(EXPLICIT, [(1, 1)], answer_policy='g065-explicit-v1').result == 'INCORRECT'


def test_unmarked_branch_is_unavailable_without_wrong_grade():
    with pytest.raises(runtime.JudgeUnavailable):
        judge('(;SZ[5](;B[aa])(;B[bb]))', [(1, 1)])


def test_legacy_linear_compatible_and_off_tree_wrong():
    assert judge('(;SZ[5];B[aa];W[cc])', [(0, 0)]).result == 'CORRECT'
    assert judge('(;SZ[5];B[aa])', [(1, 1)]).result == 'INCORRECT'


def test_no_early_leaf_acceptance_of_extra_moves():
    assert judge('(;SZ[5];B[aa])', [(0, 0), (1, 1)]).result == 'INCORRECT'


def test_reviewed_alternative_is_authority_katago_is_not():
    assert judge('(;SZ[5];B[aa])', [(1, 1)], accepted_moves=[dict(x=1, y=1)]).result == 'CORRECT'
    assert judge('(;SZ[5];B[aa])', [(1, 1)], katago_best_move='B4').result == 'INCORRECT'


@pytest.mark.parametrize('annotation', ['C[失敗]', 'C[RIGHT]', 'TE[1]', 'BM[1]'])
def test_annotations_without_dialect_require_curation(annotation):
    with pytest.raises(runtime.JudgeUnavailable):
        judge(f'(;SZ[5];B[aa]{annotation})', [(0, 0)])


def test_failure_ancestor_dominates_and_unmarked_explicit_unavailable():
    sgf = '(;SZ[5];B[aa]C[G065:INCORRECT];W[cc]C[G065:CORRECT])'
    assert judge(sgf, [(0, 0)], answer_policy='g065-explicit-v1').result == 'INCORRECT'
    with pytest.raises(runtime.JudgeUnavailable):
        judge('(;SZ[5];B[aa])', [(0, 0)], answer_policy='g065-explicit-v1')


def test_parser_preserves_comments_properties_and_parentage():
    root = parse_sgf(EXPLICIT)
    assert root.children[1].metadata['properties']['C'] == ['G065:INCORRECT']
    assert root.children[1].parent is root


@pytest.fixture
def db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE review_log(user_id INTEGER, question_id INTEGER, grade INTEGER, reviewed_at TEXT, source TEXT DEFAULT '', source_context TEXT DEFAULT 'practice:v1:offline')")
    conn.executemany('INSERT INTO review_log(user_id, question_id, grade, reviewed_at) VALUES (?,?,?,?)', [
        (1, 1, 5, '2026-10-22T23:30:00'), (1, 2, 5, '2026-10-22T12:01:00Z'),
        (1, 3, 0, '2026-10-23T11:00:00'), (2, 4, 5, '2026-10-23T11:00:00'),
        (1, 5, 5, '2026-10-22T12:00:00'), (1, 6, 5, '2026-10-24T12:00:00'),
    ])
    yield conn
    conn.close()


def test_untrusted_public_grade_does_not_suppress(db):
    db.execute("INSERT INTO review_log VALUES (1,99,5,'2026-10-23T11:00:00','','public')")
    assert 99 not in recent_correct_ids(db, 1, now=datetime.datetime(2026, 10, 23, 12))


def test_multiple_sessions_players_anonymous_due_and_fallback(db):
    now = datetime.datetime(2026, 10, 23, 12, tzinfo=datetime.timezone.utc)
    recent = recent_correct_ids(db, 1, now=now)
    assert recent == {1, 2}
    assert recent_correct_ids(db, None, now=now) == set()
    assert recent_correct_ids(db, 2, now=now) == {4}
    pool = [dict(id=n) for n in [1, 2, 3, 4]]
    for _session in range(3):
        assert [q['id'] for q in prefer_not_recent(pool, recent, due={2})] == [2, 3, 4, 1]
    assert [q['id'] for q in prefer_not_recent(pool[:2], recent)] == [1, 2]


def test_deterministic_session_repeat_rate_evidence(db):
    recent = recent_correct_ids(db, 1, now=datetime.datetime(2026, 10, 23, 12))
    pool = [dict(id=n) for n in [1, 2, 3, 4]]
    original = sum(q['id'] in recent for q in pool[:2]) / 2
    candidate = sum(q['id'] in recent for q in prefer_not_recent(pool, recent)[:2]) / 2
    assert (original, candidate) == (1.0, 0.0)  # synthetic 100% -> 0%; not production 12.8%


def load_app_function(name, namespace):
    source = (subprocess.check_output(['git', 'show', 'd0f16e6:app.py'], cwd=ROOT).decode('utf-8')
              if BASELINE else (ROOT / 'app.py').read_text(encoding='utf-8'))
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'isolated-app-function', 'exec'), namespace)
    return namespace[name]


def test_rating_practice_same_authority_all_transforms():
    # Execute real app function body, without starting app or reading its DB config.
    for t in range(8):
        namespace = dict(parse_sgf=parse_sgf, _rt_transform_idx=lambda *args: t, _re_mod=re)
        if BASELINE:
            for name in ('_transform_sgf', '_question_accepted_moves', '_normalize_question_move',
                         '_rt_find_closing', '_rt_parse_seq', '_rt_parse_answer_tree',
                         '_rt_replay', '_gtp_to_xy', '_transform_point'):
                load_app_function(name, namespace)
        verify = load_app_function('_rt_server_verify', namespace)
        q = dict(id=1, content=EXPLICIT, answer_policy='g065-explicit-v1', katago_best_move='E1')
        good = runtime._transform_point(0, 0, 5, t)
        bad = runtime._transform_point(1, 1, 5, t)
        assert verify(q, 's', [dict(x=good[0], y=good[1])]) is True
        assert verify(q, 's', [dict(x=bad[0], y=bad[1])]) is False


def test_opt_in_policy_changes_invalidate_issued_revision():
    question = dict(content=EXPLICIT, answer_policy='g065-explicit-v1')
    revision = runtime.question_revision_for(question)
    assert runtime.question_revision_for(dict(question, answer_policy='other')) != revision


def test_real_due_route_body_preserves_future_cards_and_permissions(db):
    from flask import Flask, jsonify
    today = datetime.date.today()
    db.execute('CREATE TABLE srs_cards(user_id INTEGER, question_id INTEGER, interval INTEGER, ease_factor REAL, due_date TEXT)')
    db.executemany('INSERT INTO srs_cards VALUES (?,?,?,?,?)', [
        (1, 1, 3, 2.5, (today + datetime.timedelta(days=2)).isoformat()),
        (1, 2, 1, 2.5, today.isoformat()),
        (2, 3, 3, 2.5, (today + datetime.timedelta(days=2)).isoformat()),
    ])
    namespace = dict(datetime=datetime, session={'user_id': 1},
        get_db=lambda: nullcontext(db), _load_questions=lambda: [dict(id=n) for n in (1, 2, 3, 4)],
        _IdentityKeyedSet=lambda ids, keys: set(ids), _identity_group_key_map=lambda *args: {},
        is_premium=lambda: False, question_is_free=lambda q: q['id'] != 4, jsonify=jsonify)
    due = load_app_function('srs_due', namespace)
    app = Flask(__name__)
    with app.test_request_context('/api/srs/due'):
        assert {q['question_id'] for q in due().get_json()['due']} == {2, 3}


def test_real_catalog_body_masks_locked_answers_and_is_player_scoped(db):
    from flask import Flask, jsonify, request
    db.execute('DELETE FROM review_log')
    db.execute('CREATE TABLE srs_cards(user_id INTEGER, question_id INTEGER, due_date TEXT)')
    db.execute("INSERT INTO review_log VALUES (1,1,5,?,'','practice:v1:new')",
               (datetime.datetime.now(datetime.timezone.utc).isoformat(),))
    questions = [dict(id=n, katago_best_move='A5') for n in (1, 2, 3)]
    namespace = dict(datetime=datetime, session={'user_id': 1}, request=request, jsonify=jsonify,
        get_db=lambda: nullcontext(db), _load_questions=lambda: questions,
        is_premium=lambda: False, question_is_free=lambda q: q['id'] != 3,
        _identity_group_key_map=lambda *args: {}, _identity_group_key=lambda keys, qid: ('legacy', str(qid)))
    for name in ('_i18n_topic_en', '_i18n_level_en', '_question_display_name', '_question_monster_avatar',
                 '_client_question_revision', '_session_question_fingerprint'):
        namespace[name] = lambda *args: ''
    load_app_function('_prefer_player_questions', namespace)
    catalog = load_app_function('get_questions', namespace)
    app = Flask(__name__)
    with app.test_request_context('/api/questions'):
        payload = catalog().get_json()
        assert [q['id'] for q in payload] == [2, 3, 1]
        assert next(q for q in payload if q['id'] == 3)['katago_best_move'] == ''
        namespace['session']['user_id'] = 2
        assert [q['id'] for q in catalog().get_json()] == [1, 2, 3]
    # Permission decorator remains on the actual registered route.
    source = (ROOT / 'app.py').read_text(encoding='utf-8')
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'get_questions')
    assert any(isinstance(d, ast.Name) and d.id == 'login_required' for d in node.decorator_list)


@pytest.mark.skip(reason='Owner Gate: no production corpus or real-player DB access; no fresh 152-player/12.8% claim')
def test_production_repeat_rate_and_8223_owner_adjudication():
    pass
