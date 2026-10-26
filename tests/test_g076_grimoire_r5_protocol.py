"""Full imported R4+R5 Flask/SQLite regression; requires pytest and Flask.

No app.py registration or external DB. Stdlib AST tests are separate evidence.
"""
import concurrent.futures
from datetime import datetime
import json

import pytest

from test_g076_grimoire_adapter import fx, client, issue, send, rows
from g076_grimoire_catalog import catalog_revision, settle_catalog_and_cache


@pytest.fixture
def catalog(fx):
    fx[2]['q']['grimoire_id'] = 5
    with fx[3]() as c:
        c.executescript('''
            CREATE TABLE grimoires(id INTEGER PRIMARY KEY,node_count INTEGER);
            CREATE TABLE g076_grimoire_catalog_members(
                question_id INTEGER PRIMARY KEY,grimoire_id INTEGER NOT NULL);
            CREATE TABLE player_grimoire_progress(user_id INTEGER,grimoire_id INTEGER,
                rank INTEGER,purity REAL,total_attempts INTEGER,correct_count INTEGER,
                last_studied_at TEXT,PRIMARY KEY(user_id,grimoire_id));
            INSERT INTO grimoires VALUES(5,1);
            INSERT INTO g076_grimoire_catalog_members VALUES(701,5);
        ''')
        c.execute('INSERT INTO daily_training_cache VALUES(?,?,?,?,?)',
                  (101,datetime.fromtimestamp(fx[2]['now']).date().isoformat(),'[701]','[]','fixture'))
        fx[2]['q']['g076_catalog_revision'] = catalog_revision(c)
    fx[0].settle = settle_catalog_and_cache
    return fx


def terminal(fx):
    token = issue(fx)
    cursor = send(fx,token).json
    response = send(fx,token,cursor,(3,3))
    assert response.status_code == 200
    return token,cursor,response


def counts(fx):
    return [rows(fx,t) for t in ('node_mastery','player_grimoire_progress',
                                'daily_training_cache','g076_grimoire_attempts','g076_grimoire_events')]


def test_terminal_replay_all_states_once(catalog):
    fx = catalog
    token,cursor,response = terminal(fx)
    before = counts(fx)
    for _ in range(3):
        assert send(fx,token,cursor,(3,3)).json == {**response.json,'duplicate':True}
    assert counts(fx) == before
    assert rows(fx,'player_grimoire_progress')[0]['total_attempts'] == 1
    assert json.loads(rows(fx,'daily_training_cache')[0]['completed_ids']) == [701]


@pytest.mark.parametrize('field', ['correct','grade','reward','user_id','question_id'])
def test_malicious_fields_cannot_write_catalog_or_cache(catalog,field):
    fx = catalog
    token = issue(fx)
    cursor = send(fx,token).json
    before = counts(fx)
    assert send(fx,token,cursor,(3,3),extras={field:True}).status_code == 400
    assert counts(fx) == before


@pytest.mark.parametrize('change', ['owner','revision','expiry','rights','catalog'])
def test_terminal_replay_authority_rechecked(catalog,change):
    fx = catalog
    token,cursor,_ = terminal(fx)
    before = counts(fx)
    uid = 101
    if change == 'owner':
        uid = 202
    elif change == 'revision':
        fx[2]['q']['question_revision'] = 'changed'
    elif change == 'expiry':
        fx[2]['now'] += 3600
    elif change == 'catalog':
        with fx[3]() as c:
            c.execute('UPDATE grimoires SET node_count=2')
            fx[2]['q']['g076_catalog_revision'] = catalog_revision(c)
    else:
        fx[2]['deny'] = True
    assert send(fx,token,cursor,(3,3),uid=uid).status_code >= 400
    assert counts(fx) == before


def test_nonce_conflict_and_wrong_move_conflict(catalog):
    fx = catalog
    token,cursor,_ = terminal(fx)
    before = counts(fx)
    assert send(fx,token,{**cursor,'step_nonce':'forged'},(3,3)).status_code == 403
    assert send(fx,token,cursor,(0,0)).status_code == 409
    assert counts(fx) == before


@pytest.mark.parametrize('failure', ['after_catalog','after_cache','event_insert','commit'])
def test_failure_after_writes_rolls_back_attempt_event_and_all_states(catalog,failure):
    fx = catalog
    token = issue(fx)
    cursor = send(fx,token).json
    with fx[3]() as c:
        if failure in ('after_catalog','after_cache'):
            table,operation = ('player_grimoire_progress','INSERT') if failure == 'after_catalog' else ('daily_training_cache','UPDATE')
            c.execute('CREATE TRIGGER failure AFTER ' + operation + ' ON ' + table +
                      " BEGIN SELECT RAISE(ABORT,'after state write'); END")
        elif failure == 'event_insert':
            c.execute("CREATE TRIGGER failure BEFORE INSERT ON g076_grimoire_events BEGIN SELECT RAISE(ABORT,'event'); END")
        else:
            c.execute('CREATE TRIGGER failure AFTER UPDATE ON daily_training_cache '
                      'BEGIN INSERT INTO deferred_failure VALUES(99); END')
    before = counts(fx)
    response = send(fx,token,cursor,(3,3))
    assert response.status_code == 503
    assert counts(fx) == before
    with fx[3]() as c:
        c.execute('DROP TRIGGER failure')
    assert send(fx,token,cursor,(3,3)).status_code == 200
    assert rows(fx,'player_grimoire_progress')[0]['total_attempts'] == 1


def test_concurrent_duplicate_terminals(catalog):
    fx = catalog
    token = issue(fx)
    cursor = send(fx,token).json
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _:send(fx,token,cursor,(3,3)),range(8)))
    assert all(r.status_code == 200 for r in responses)
    assert sum(not r.json['duplicate'] for r in responses) == 1
    assert rows(fx,'node_mastery')[0]['attempt_count'] == 1
    assert rows(fx,'player_grimoire_progress')[0]['total_attempts'] == 1
    assert json.loads(rows(fx,'daily_training_cache')[0]['completed_ids']) == [701]


def test_concurrent_conflicting_terminal_moves(catalog):
    fx = catalog
    # One-step canonical question makes BOTH moves terminal.
    fx[2]['q']['content'] = '(;SZ[5]PL[B];B[aa])'
    token = issue(fx)
    cursor = send(fx,token).json
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda xy:send(fx,token,cursor,xy),[(0,0),(3,3)]))
    assert sorted(r.status_code for r in responses) == [200,409]
    assert rows(fx,'node_mastery')[0]['attempt_count'] == 1
    assert rows(fx,'player_grimoire_progress')[0]['total_attempts'] == 1


def test_catalog_in_other_database_refused(catalog,tmp_path):
    fx = catalog
    with fx[3]() as c:
        c.execute('ALTER TABLE grimoires RENAME TO hidden')
        c.execute('ATTACH DATABASE ? AS catalog', (str(tmp_path/'other.sqlite'),))
        c.execute('CREATE TABLE catalog.grimoires(id INTEGER PRIMARY KEY,node_count INTEGER)')
        c.execute('INSERT INTO catalog.grimoires VALUES(5,1)')
    token = issue(fx)
    before = counts(fx)
    response = send(fx,token,send(fx,token).json,(3,3))
    assert response.json == {'error':'same_database_catalog_required'}
    assert counts(fx) == before
