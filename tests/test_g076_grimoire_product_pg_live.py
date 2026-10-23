"""NEW Product adapter Flask+native PG integration, not prior PG regression.

Uses the existing explicit disposable PG config safeguards, creates a unique
schema, never touches official DB. Source/identity/rights here are TEST ONLY.
Run only with the existing authorized isolated fixture available; no startup,
container creation or credentials are provided by this test.
"""
import hashlib
import json
import pytest
from flask import Flask
from psycopg2 import extensions

from test_g076_grimoire_pg_live import case
from g076_grimoire_product import (CanonicalCorpus, Lesson, ProductGrimoire,
                                    install_product_grimoire, question_sha)


@pytest.fixture
def product(case):
    old, _, tables, state, connect, schema = case
    q = {k:v for k,v in state['q'].items() if k != 'g076_catalog_revision'}
    raw = json.dumps([q]).encode()
    sha = hashlib.sha256(raw).hexdigest()
    proof = dict(source_record_uuid='018ffa01-0bb0-4123-8123-0123456789ab',
                 corpus_sha256=sha, question_sha256=question_sha(q),
                 catalog_revision=state['q']['g076_catalog_revision'])
    observations = []
    def canonical(conn, qid):
        assert isinstance(conn, extensions.connection)
        assert conn.get_transaction_status() == extensions.TRANSACTION_STATUS_INTRANS
        observations.append(('canonical',id(conn)))
        return proof
    def rights(conn, uid, question):
        assert conn.get_transaction_status() == extensions.TRANSACTION_STATUS_INTRANS
        observations.append(('rights',id(conn)))
        return uid in (101,202) and not state['deny']
    service = ProductGrimoire(corpus=CanonicalCorpus(raw,sha,canonical), entitlements=rights,
        lesson=lambda conn,uid:Lesson(701,'test-product-lesson','隔離法典課題'),
        connect=connect,schema=schema,secret=b'product-fixture-secret-more-than-32-bytes',
        environ=dict(old.environ),clock=lambda:state['now'])
    app = Flask(__name__);app.secret_key='disposable-product-test-session'
    legacy = []
    def answer():
        legacy.append(True)
        return 'unsafe legacy'
    app.add_url_rule('/api/training/answer','grimoire.api_training_answer',answer,methods=['POST'])
    install_product_grimoire(app,service)
    client = app.test_client()
    with client.session_transaction() as s:s['user_id']=101
    def post(action, body):
        return client.post('/api/g076/grimoire/product/'+action,json=body,
                           headers={'X-Grimoire-Request':'1'})
    return service, post, client, tables, state, proof, observations, legacy


def test_new_product_admission_step_receipt_resume_pg(product):
    service,post,client,tables,state,proof,seen,legacy = product
    token = post('admission',{}).json['attempt_token']
    row = post('steps',{'attempt_token':token}).json
    assert row['board_only'] and ';B[aa]' not in row['content']
    payload = dict(attempt_token=token,step_index=0,step_nonce=row['step_nonce'],move={'x':0,'y':0})
    seen.clear()
    result = post('steps',payload)
    assert result.status_code == 200 and result.json['status'] == 'CORRECT'
    assert len({identity for _,identity in seen}) == 1  # providers on ONE PG transaction
    assert post('steps',payload).json['duplicate'] is True
    assert len(tables()['g076_grimoire_events']) == 1
    assert post('admission',{}).json['attempt_token'] == token
    assert post('steps',{'attempt_token':token}).json['status'] == 'CORRECT'
    assert client.post('/api/training/answer',json={'correct':True}).status_code == 409
    assert not legacy


def test_new_product_pg_revokes_proof_and_membership_before_step(product):
    service,post,client,tables,state,proof,seen,legacy = product
    token = post('admission',{}).json['attempt_token']
    row = post('steps',{'attempt_token':token}).json
    payload = dict(attempt_token=token,step_index=0,step_nonce=row['step_nonce'],move={'x':0,'y':0})
    before = tables()
    proof['corpus_sha256'] = '0'*64
    assert post('steps',payload).status_code == 503
    assert tables() == before
    proof['corpus_sha256'] = service.corpus.sha256
    state['deny'] = True
    assert post('steps',payload).status_code == 403
    assert tables() == before


def test_new_product_pg_user_cannot_select_scope_or_claim_verdict(product):
    service,post,client,tables,state,proof,seen,legacy = product
    before = tables()
    assert post('admission',{'question_id':701,'scope':'extra-attempt'}).status_code == 400
    token = post('admission',{}).json['attempt_token']
    assert post('steps',{'attempt_token':token,'correct':True}).status_code == 400
    with client.session_transaction() as s:s['user_id']=202
    assert post('steps',{'attempt_token':token}).status_code == 409
    assert tables() == before
