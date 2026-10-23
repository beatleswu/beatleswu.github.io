"""G077 native PG tests. Label verification MUST precede fixture/schema setup.

G077_DISPOSABLE_PG_EXPECTED_LABELS is the externally reviewed complete label
object from this exact container, never a guessed value or a wildcard.
"""
import json
import os
import subprocess

import pytest
from test_g076_grimoire_product_pg_live import product
from test_g076_grimoire_pg_live import case


@pytest.fixture
def verified_product(request):
    expected = json.loads(os.environ['G077_DISPOSABLE_PG_EXPECTED_LABELS'])
    assert isinstance(expected, dict) and expected
    result = subprocess.run(['docker','inspect','g076-r5-isolated-pg-20261023'],
                            check=True, capture_output=True, text=True)
    container, = json.loads(result.stdout)
    assert container['Name'] == '/g076-r5-isolated-pg-20261023'
    assert container['Config']['Labels'] == expected
    assert container['Config']['Image'] == 'postgres:16-alpine'
    assert container['State']['Running'] is True
    assert '/var/lib/postgresql/data' in container['HostConfig']['Tmpfs']
    assert container['NetworkSettings']['Ports']['5432/tcp'] == [
        {'HostIp':'127.0.0.1','HostPort':'55476'}]
    # Only now may the inherited fixture connect/create its random schema.
    result = request.getfixturevalue('product')
    result[0].environ['G076_ANSWER_PRIVACY_ENFORCED'] = 'off'
    return result


def start(post):
    token = post('admission', {}).json['attempt_token']
    row = post('steps', {'attempt_token':token}).json
    assert row['board_only'] is True and ';B[aa]' not in row['content']
    return dict(attempt_token=token, step_index=0, step_nonce=row['step_nonce'], move={'x':0,'y':0})


def test_independent_product_pg_commit_retry_rights_and_proof(verified_product):
    service, post, client, tables, state, proof, seen, legacy = verified_product
    payload = start(post)
    seen.clear()
    assert post('steps', payload).json['status'] == 'CORRECT'
    assert len({identity for _,identity in seen}) == 1
    assert post('steps', payload).json['duplicate'] is True
    assert len(tables()['g076_grimoire_events']) == 1
    before = tables()
    state['deny'] = True
    assert post('steps', payload).status_code == 403
    assert tables() == before
    state['deny'] = False
    proof['corpus_sha256'] = '0'*64
    assert post('steps', payload).status_code == 503
    assert tables() == before
    assert client.post('/api/training/answer', json={'correct':True}).status_code == 409
    assert legacy == []


@pytest.mark.parametrize('failure', ['insert', 'commit'])
def test_independent_product_pg_real_rollback_and_retry(verified_product, failure):
    service, post, client, tables, state, proof, seen, legacy = verified_product
    payload = start(post)
    before = tables()
    schema = service.schema  # inherited fixture's validated random identifier
    conn = service.connect()
    try:
        with conn.cursor() as cursor:
            if failure == 'insert':
                cursor.execute('CREATE FUNCTION '+schema+".g077_fail() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'G077 isolated insert fault'; END $$")
                cursor.execute('CREATE TRIGGER g077_fault AFTER INSERT ON '+schema+'.g076_grimoire_events FOR EACH ROW EXECUTE FUNCTION '+schema+'.g077_fail()')
            else:
                cursor.execute('CREATE TABLE '+schema+'.g077_parent(id integer PRIMARY KEY)')
                cursor.execute('ALTER TABLE '+schema+'.g076_grimoire_events ADD COLUMN g077_fk integer DEFAULT 1 REFERENCES '+schema+'.g077_parent(id) DEFERRABLE INITIALLY DEFERRED')
        conn.commit()
    finally:
        conn.close()
    # Added test-only FK column changes row shape, so snapshot after DDL.
    before = tables()
    assert post('steps', payload).status_code == 503
    assert tables() == before
    conn = service.connect()
    try:
        with conn.cursor() as cursor:
            if failure == 'insert':
                cursor.execute('DROP TRIGGER g077_fault ON '+schema+'.g076_grimoire_events')
            else:
                cursor.execute('INSERT INTO '+schema+'.g077_parent VALUES(1)')
        conn.commit()
    finally:
        conn.close()
    assert post('steps', payload).json['status'] == 'CORRECT'
    assert post('steps', payload).json['duplicate'] is True
    assert len(tables()['g076_grimoire_events']) == 1
