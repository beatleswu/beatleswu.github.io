'''R9 D-only replay identity characterization against the REAL Product B050 in-memory fixture.

Run this same file twice; it never opens a production DB:
  G009_REPLAY_EXPECT=defect G009_PRODUCT_ROOT=<unpatched R8 product copy>
  G009_REPLAY_EXPECT=fixed  G009_PRODUCT_ROOT=<scratch copy with replay_api_diff applied>
Supplements, never waives, the original 21 FAIL or the R8 52-test suite.
'''
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(os.environ['G009_PRODUCT_ROOT'])
assert (ROOT / 'app.py').is_file()
EXPECT = os.environ.get('G009_REPLAY_EXPECT')
assert EXPECT in ('defect', 'fixed'), 'set G009_REPLAY_EXPECT=defect or fixed'
sys.path.insert(0, str(ROOT / 'tests'))
from test_b050_public_srs_review_authority import api_env, app_module, _post  # noqa: E402,F401

OLD_LINE = "submission_id=data.get('submission_id') or request.headers.get('Idempotency-Key')"
NEW_GUARD = "if data.get('submission_id') not in (None, '')"
GENERATED = re.compile(r'srv-[0-9a-f]{32}')
_ABSENT = object()


class _ShapedClient:
    '''Delegate to the real Flask test client; only reshape the identity inputs.'''

    def __init__(self, inner, body_id=_ABSENT, header=None):
        self._inner = inner
        self._body_id = body_id
        self._header = header
        self.calls = 0

    def post(self, *args, **kwargs):
        body = kwargs.get('json')
        assert isinstance(body, dict), '_post must send a JSON object via json='
        body = dict(body)
        body.pop('submission_id', None)
        if self._body_id is not _ABSENT:
            body['submission_id'] = self._body_id
        kwargs['json'] = body
        headers = {
            k: v for k, v in dict(kwargs.get('headers') or {}).items()
            if k.lower() != 'idempotency-key'
        }
        if self._header is not None:
            headers['Idempotency-Key'] = self._header
        kwargs['headers'] = headers
        self.calls += 1
        return self._inner.post(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _send(client, body_id=_ABSENT, header=None, grade=5):
    shaped = _ShapedClient(client, body_id=body_id, header=header)
    response = _post(shaped, grade=grade, submission_id='r9-placeholder')
    assert shaped.calls == 1, '_post bypassed client.post; identity shaping not applied'
    return response


def _env(api_env):
    client, conn = api_env
    files = [r[2] for r in conn.execute('PRAGMA database_list').fetchall()]
    assert files and not any(files), files
    return client, conn


def _ids(conn):
    return [r['submission_id'] for r in conn.execute(
        'SELECT submission_id FROM review_log ORDER BY rowid').fetchall()]


def _assert_rejected(response):
    assert response.status_code == 400, response.get_json()
    assert response.get_json()['error'] == 'invalid_submission_identity'


def test_phase_matches_imported_product_source(app_module, api_env):
    _env(api_env)
    assert Path(app_module.__file__).resolve() == (ROOT / 'app.py').resolve()
    source = (ROOT / 'app.py').read_text(encoding='utf-8')
    if EXPECT == 'defect':
        assert OLD_LINE in source and NEW_GUARD not in source
    else:
        assert OLD_LINE not in source and NEW_GUARD in source


@pytest.mark.parametrize('empty_id', [[], {}], ids=['list', 'dict'])
def test_empty_container_identity_retry(api_env, empty_id):
    client, conn = _env(api_env)
    first = _send(client, body_id=empty_id)
    retry = _send(client, body_id=empty_id)
    ids = _ids(conn)
    if EXPECT == 'defect':
        # Characterizes the defect: each retry silently becomes a new review.
        assert first.status_code == 200, first.get_json()
        assert retry.status_code == 200, retry.get_json()
        assert not retry.get_json().get('submission_duplicate')
        assert len(ids) == 2 and ids[0] != ids[1], ids
        assert all(GENERATED.fullmatch(i) for i in ids), ids
    else:
        _assert_rejected(first)
        _assert_rejected(retry)
        assert ids == []


@pytest.mark.parametrize('empty_id', [[], {}], ids=['list', 'dict'])
def test_present_empty_container_does_not_defer_to_header(api_env, empty_id):
    client, conn = _env(api_env)
    result = _send(client, body_id=empty_id, header='r9-hdr-shadow')
    if EXPECT == 'defect':
        assert result.status_code == 200, result.get_json()
        assert _ids(conn) == ['r9-hdr-shadow']
    else:
        _assert_rejected(result)
        assert _ids(conn) == []


@pytest.mark.parametrize('falsy_id', [0, False], ids=['zero', 'false'])
def test_falsy_scalar_identity(api_env, falsy_id):
    client, conn = _env(api_env)
    result = _send(client, body_id=falsy_id)
    if EXPECT == 'defect':
        assert result.status_code == 200, result.get_json()
        ids = _ids(conn)
        assert len(ids) == 1 and GENERATED.fullmatch(ids[0]), ids
    else:
        _assert_rejected(result)
        assert _ids(conn) == []


@pytest.mark.parametrize('bad_id', [['r9'], {'id': 'r9'}, 17], ids=['list', 'dict', 'int'])
def test_other_malformed_identity_rejected_even_with_valid_header(api_env, bad_id):
    client, conn = _env(api_env)
    _assert_rejected(_send(client, body_id=bad_id, header='r9-hdr-valid'))
    assert _ids(conn) == []


def test_valid_body_identity_has_priority_over_header(api_env):
    client, conn = _env(api_env)
    first = _send(client, body_id='r9-body-1', header='r9-hdr-a')
    retry = _send(client, body_id='r9-body-1', header='r9-hdr-b')
    assert first.status_code == 200, first.get_json()
    assert retry.status_code == 200, retry.get_json()
    assert retry.get_json().get('submission_duplicate') is True
    assert _ids(conn) == ['r9-body-1']


@pytest.mark.parametrize('blank', [_ABSENT, None, ''], ids=['absent', 'null', 'empty-string'])
def test_absent_or_blank_body_defers_to_stable_header(api_env, blank):
    client, conn = _env(api_env)
    first = _send(client, body_id=blank, header='r9-hdr-stable')
    retry = _send(client, body_id=blank, header='r9-hdr-stable')
    assert first.status_code == 200, first.get_json()
    assert retry.status_code == 200, retry.get_json()
    assert retry.get_json().get('submission_duplicate') is True
    assert _ids(conn) == ['r9-hdr-stable']


def test_missing_identity_generates_fresh_ids_and_cannot_deduplicate(api_env):
    client, conn = _env(api_env)
    first = _send(client)
    retry = _send(client)
    assert first.status_code == 200, first.get_json()
    assert retry.status_code == 200, retry.get_json()
    assert not retry.get_json().get('submission_duplicate')
    ids = _ids(conn)
    assert len(ids) == 2 and ids[0] != ids[1], ids
    assert all(GENERATED.fullmatch(i) for i in ids), ids
