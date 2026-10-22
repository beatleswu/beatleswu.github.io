"""G060 regression: exact public assets, never anonymous player APIs."""
import hashlib
from pathlib import Path

import pytest
import app as application

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('suffix,mime', [('js', 'javascript'), ('css', 'text/css')])
@pytest.mark.parametrize('authenticated', [False, True])
def test_leaderboard_asset_raw_bytes(suffix, mime, authenticated):
    application.app.config.update(TESTING=True)
    client = application.app.test_client()
    if authenticated:
        with client.session_transaction() as session:
            session['user_id'] = 880062
    name = f'g010_m4_quest_leaderboard.{suffix}'
    response = client.get('/' + name, follow_redirects=False)
    assert response.status_code == 200, (response.status_code, response.headers.get('Location'))
    assert 'Location' not in response.headers
    assert mime in response.content_type
    assert hashlib.sha256(response.data).digest() == hashlib.sha256((ROOT / name).read_bytes()).digest()


@pytest.mark.parametrize('route', ['/api/quests/v2', '/api/community/leaderboard', '/api/quest-board/progress'])
def test_player_api_still_requires_login(route):
    response = application.app.test_client().get(route, follow_redirects=False)
    assert response.status_code == 401


def test_unlisted_asset_stays_unrouted():
    assert application.app.test_client().get('/g010_m4_quest_leaderboard.secret').status_code == 404
