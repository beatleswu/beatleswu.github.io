"""New Product seam tests. Flask is real; the PG core is explicitly stubbed.

No PG fixture, official app import, real entitlement or production mutation.
Prior native PG receipts remain separate evidence, not rerun by this file.
"""
from contextlib import contextmanager
import hashlib
import json
from unittest.mock import Mock

import pytest
from flask import Flask

from g076_grimoire_adapter import GrimoireRejected
from g076_grimoire_product import (CanonicalCorpus, Lesson, ProductGrimoire,
    install_product_grimoire, question_sha)


Q = {'id': 701, 'grimoire_id': 5, 'content': '(;SZ[9]PL[W]AB[aa];W[bb])'}
UUID = '018ffa01-0bb0-4123-8123-0123456789ab'


def corpus_case(rows=None):
    rows = [Q, {'id': 702, 'content': '(;SZ[9];B[aa])'}] if rows is None else rows
    raw = json.dumps(rows).encode()
    sha = hashlib.sha256(raw).hexdigest()
    receipt = dict(source_record_uuid=UUID, corpus_sha256=sha,
                   question_sha256=question_sha(rows[0]), catalog_revision='a'*64)
    provider = Mock(return_value=receipt)
    return CanonicalCorpus(raw, sha, provider), receipt, provider


@pytest.fixture
def seam():
    corpus, receipt, canonical = corpus_case()
    service = ProductGrimoire(corpus=corpus, entitlements=Mock(return_value=True),
        lesson=Mock(return_value=Lesson(701, 'server-day-slot-1', '今日法典')),
        connect=Mock(side_effect=AssertionError('unit test must not connect PG')),
        schema='grimoire_candidate', secret=b'x'*32,
        environ={'G076_GRIMOIRE_STEPS_ENABLED':'on', 'G076_ANSWER_PRIVACY_ENFORCED':'on'})
    conn = object()
    @contextmanager
    def transaction(uid):
        yield conn
    service._transaction = transaction
    service._question = Mock()
    service.issue = Mock(return_value='server-token')
    service.run = Mock(return_value={'status':'OPEN','step_index':0,'step_nonce':'nonce',
        'content':'(;SZ[9]PL[W]AB[aa])','board_only':True,'previous_steps':[]})
    app = Flask(__name__)
    app.secret_key = 'test-only'
    touched = []
    def legacy():
        touched.append(True)
        return 'legacy'
    app.add_url_rule('/api/training/answer', 'grimoire.api_training_answer', legacy, methods=['POST'])
    app.add_url_rule('/alias/answer', 'grimoire.api_training_answer', legacy, methods=['POST'])
    app.add_url_rule('/api/grimoire/training/daily', 'grimoire.api_training_daily', legacy)
    app.add_url_rule('/api/training/contaminated', 'grimoire.api_training_contaminated', legacy)
    app.add_url_rule('/api/srs/review', 'srs_review', legacy, methods=['POST'])
    app.add_url_rule('/alias/review', 'srs_review', legacy, methods=['POST'])
    app.add_url_rule('/api/srs/practice/attempt', 'srs_practice_attempt', legacy, methods=['POST'])
    app.add_url_rule('/api/srs/practice/answer', 'srs_practice_answer', legacy, methods=['POST'])
    app.add_url_rule('/api/g076/nonmap/steps', 'g076_nonmap_steps.submit', legacy, methods=['POST'])
    install_product_grimoire(app, service)
    client = app.test_client()
    with client.session_transaction() as s:
        s['user_id'] = 101
    return service, app, client, touched, conn


HEADERS = {'X-Grimoire-Request':'1'}
BASE = '/api/g076/grimoire/product/'


def test_admission_is_server_owned(seam):
    service, app, client, touched, conn = seam
    r = client.post(BASE+'admission', json={}, headers=HEADERS)
    assert r.json == {'attempt_token':'server-token','title':'今日法典'}
    service.lesson.assert_called_once_with(conn, 101)
    service._question.assert_called_once_with(conn, 101, 701)
    service.issue.assert_called_once_with(101, question_id=701, scope='server-day-slot-1')
    assert r.headers['Cache-Control'] == 'private, no-store'


@pytest.mark.parametrize('body', [{'question_id':701}, {'scope':'new-round'},
    {'enabled':True}, {'user_id':202}, [], None])
def test_cannot_select_admission_or_gate(seam, body):
    service, _, client, _, _ = seam
    assert client.post(BASE+'admission', json=body, headers=HEADERS).status_code == 400
    service.issue.assert_not_called()


def test_bad_lesson_fail_closed(seam):
    service, _, client, _, _ = seam
    service.lesson.return_value = {'question_id':701, 'scope':'fake'}
    assert client.post(BASE+'admission', json={}, headers=HEADERS).status_code == 503
    service.issue.assert_not_called()


def test_trusted_identity_and_fresh_copy():
    corpus, _, provider = corpus_case()
    conn = object()
    assert corpus.identity(conn, 701) == UUID
    assert corpus.load(conn, 701)['g076_catalog_revision'] == 'a'*64
    provider.assert_called_with(conn, 701)
    q = corpus.lookup(701)
    q['content'] = 'mutated'
    assert corpus.lookup(701) == Q


@pytest.mark.parametrize('key,value', [('source_record_uuid','legacy:701'),
    ('source_record_uuid','00000000-0000-0000-0000-000000000000'),
    ('source_record_uuid',None), ('corpus_sha256','b'*64),
    ('question_sha256','b'*64), ('catalog_revision',None), ('catalog_revision','legacy')])
def test_missing_or_changed_proof_fails_closed(key, value):
    corpus, receipt, _ = corpus_case()
    receipt[key] = value
    with pytest.raises(GrimoireRejected, match='canonical_provenance'):
        corpus.load(object(), 701)


def test_no_catalog_substitution():
    corpus, receipt, _ = corpus_case([{'id':701,'content':Q['content']}])
    with pytest.raises(GrimoireRejected, match='canonical_grimoire_membership_missing'):
        corpus.load(object(), 701)


@pytest.mark.parametrize('raw', [b'[]', b'{}', b'[{"id":1,"x":NaN}]', b'[{"id":1,"id":2}]',
    b'[{"id":1},{"id":1}]', b'[{"id":true}]', b'[{"id":1,"g076_catalog_revision":"fake"}]'])
def test_invalid_corpus(raw):
    with pytest.raises(ValueError):
        CanonicalCorpus(raw, hashlib.sha256(raw).hexdigest(), lambda c,q:None)


def test_sha_mismatch():
    with pytest.raises(ValueError, match='canonical_corpus_proof_required'):
        CanonicalCorpus(b'[]', '0'*64, lambda c,q:None)


@pytest.mark.parametrize('path,method', [('/api/training/answer','post'),
    ('/alias/answer','post'), ('/api/grimoire/training/daily','get'),
    ('/api/grimoire/training/daily','head'), ('/api/training/contaminated','get'),
    ('/api/training/answer','options')])
def test_legacy_containment_independent_of_global_gate(seam, path, method):
    service, _, client, touched, _ = seam
    service.environ['G076_ANSWER_PRIVACY_ENFORCED'] = 'off'
    assert getattr(client,method)(path).status_code == 409
    assert touched == []


# G079: shared Practice/SRS/nonmap writers are governed by their own mode
# gates. Grimoire ON must neither contain nor classify them (the production
# corpus tags 41,473/41,591 questions with grimoire_id; G078 XFAIL B4).
@pytest.mark.parametrize('path', ['/api/srs/review', '/alias/review',
    '/api/srs/practice/attempt', '/api/srs/practice/answer', '/api/g076/nonmap/steps'])
def test_shared_writers_not_contained_by_grimoire(seam, path):
    _, _, client, touched, _ = seam
    assert client.post(path, json={'question_id':701,'attempt_token':'t',
        'flow':'practice'}).status_code == 200
    assert touched == [True]


def test_non_grimoire_common_writer_untouched(seam):
    _, _, client, touched, _ = seam
    assert client.post('/api/srs/review',json={'question_id':702}).status_code == 200
    assert touched == [True]


def test_off_keeps_legacy_paths(seam):
    service, _, client, touched, _ = seam
    service.environ['G076_GRIMOIRE_STEPS_ENABLED'] = 'off'
    assert client.post('/api/training/answer',json={'correct':True}).status_code == 200
    assert client.post('/api/srs/review',json={'question_id':701}).status_code == 200
    assert client.post(BASE+'admission',json={},headers=HEADERS).status_code == 503
    assert len(touched) == 2


def test_auth_and_csrf(seam):
    service, _, client, _, _ = seam
    for headers in [{}, {**HEADERS,'Origin':'https://evil.test'},
                    {**HEADERS,'Sec-Fetch-Site':'cross-site'}]:
        assert client.post(BASE+'admission',json={},headers=headers).status_code == 403
    with client.session_transaction() as s:
        s.clear()
    assert client.post(BASE+'admission',json={},headers=HEADERS).status_code == 401
    service.issue.assert_not_called()


def test_transport_step_shape_owner_and_rejected_claims(seam):
    service, _, client, _, _ = seam
    move = dict(attempt_token='token',step_index=0,step_nonce='nonce',move={'x':1,'y':1})
    assert client.post(BASE+'steps',json=move,headers=HEADERS).status_code == 200
    service.run.assert_called_once_with(101,'token',{k:v for k,v in move.items() if k!='attempt_token'})
    for key in ['user_id','correct','grade','scope','enabled']:
        assert client.post(BASE+'steps',json={**move,key:True},headers=HEADERS).status_code == 400


def test_dependency_failure_and_rights_error(seam):
    service, _, client, _, _ = seam
    service.run.side_effect = GrimoireRejected('rights_required',403)
    assert client.post(BASE+'steps',json={'attempt_token':'token'},headers=HEADERS).status_code == 403
    service.run.side_effect = RuntimeError('private secret')
    r = client.post(BASE+'steps',json={'attempt_token':'token'},headers=HEADERS)
    assert r.status_code == 503 and 'private secret' not in r.text


def test_large_body_is_rejected(seam):
    _, _, client, _, _ = seam
    assert client.post(BASE+'admission',json={'x':'a'*17000},headers=HEADERS).status_code == 413


def test_page_uses_real_product_client(seam):
    _, _, client, _, _ = seam
    r = client.get('/grimoire/player')
    assert r.status_code == 200
    assert '/grimoire/player.js' in r.text and '/wgo/wgo.player.min.js' in r.text
    assert client.get('/grimoire/player.js').status_code == 200


def test_cannot_register_behind_writer_hook(seam):
    service = seam[0]
    app = Flask('bad-order')
    @app.before_request
    def writer():
        pass
    with pytest.raises(RuntimeError, match='precede_writers'):
        install_product_grimoire(app,service)


def test_registration_with_existing_guard(seam):
    from g076_othermode_authority import install_othermode_guard
    app = Flask('known-containment')
    install_othermode_guard(app)
    install_product_grimoire(app,seam[0])
    assert 'g076_grimoire_product' in app.extensions




def test_signed_non_grimoire_practice_keeps_existing_handler(seam,monkeypatch):
    _,_,client,touched,_ = seam
    monkeypatch.setattr('g076_grimoire_product.verify_practice_attempt',Mock(return_value={'question_id':702}))
    assert client.post('/api/srs/practice/answer',json={'attempt_token':'owned'}).status_code == 200
    assert touched == [True]
