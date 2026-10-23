"""New G077 wiring evidence only. No official app import or database writes."""
from pathlib import Path
import ast

import pytest
from flask import Flask

from test_g076_grimoire_product import seam, HEADERS, BASE
from g076_grimoire_product import install_product_grimoire


def test_product_flag_does_not_require_global_privacy(seam):
    service, _, client, _, _ = seam
    service.environ['G076_ANSWER_PRIVACY_ENFORCED'] = 'off'
    assert service._steps_enabled() is True
    assert client.post(BASE+'admission', json={}, headers=HEADERS).status_code == 200
    service.environ['G076_GRIMOIRE_STEPS_ENABLED'] = 'off'
    service.environ['G076_ANSWER_PRIVACY_ENFORCED'] = 'on'
    assert service._steps_enabled() is False
    assert client.post(BASE+'admission', json={}, headers=HEADERS).status_code == 503


def test_missing_official_providers_are_installed_but_not_ready():
    app = Flask('g077-no-provider'); app.secret_key = 'test-only'
    gate = {'G076_GRIMOIRE_STEPS_ENABLED':'on', 'G076_ANSWER_PRIVACY_ENFORCED':'off'}
    install_product_grimoire(app, environ=gate)
    client = app.test_client()
    with client.session_transaction() as session: session['user_id'] = 101
    manifest = client.get(BASE+'manifest')
    assert manifest.status_code == 200
    assert manifest.json['providers_configured'] is False
    assert manifest.json['corpus_verified'] is False
    assert manifest.json['entitlements_verified'] is False
    assert manifest.json['global_privacy_required'] is False
    assert manifest.json['product_readiness'] == 'HOLD'
    assert client.post(BASE+'admission', json={}, headers=HEADERS).status_code == 503
    assert client.get('/grimoire/player').status_code == 200


@pytest.mark.parametrize('endpoint', ['training_daily', 'dc_today', 'dc_submit', 'dc_history',
    'dc_history_detail', 'get_mistakes', 'friend_challenge_detail',
    'friend_challenge_answer', 'rt_start', 'rt_resume', 'rt_answer',
    'map_battle_v1_prepare_attempt', 'map_battle_v1_resume_validation',
    'map_battle_v1_battle_state', 'map_battle_v1_submission_nonce',
    'map_battle_v1_answers', 'g076_map_battle_step_start',
    'g076_map_battle_step_submit', 'g076_daily_steps.start'])
def test_aggregate_alias_cannot_bypass_independent_flag(endpoint):
    app = Flask('g077-alias'); app.secret_key = 'test-only'
    touched = []
    app.add_url_rule('/alias', endpoint, lambda: touched.append(True) or 'unsafe', methods=['GET','POST'])
    gate = {'G076_GRIMOIRE_STEPS_ENABLED':'on', 'G076_ANSWER_PRIVACY_ENFORCED':'off'}
    install_product_grimoire(app, environ=gate)
    client = app.test_client()
    assert client.post('/alias').status_code == 409
    assert touched == []
    gate['G076_GRIMOIRE_STEPS_ENABLED'] = 'off'
    assert client.post('/alias').status_code == 200


@pytest.mark.parametrize('path', ['/', '/index.html'])
def test_existing_player_navigation_is_gated(path):
    app = Flask('g077-navigation'); app.secret_key = 'test-only'
    app.add_url_rule(path, 'old_player', lambda: 'old player')
    gate = {'G076_GRIMOIRE_STEPS_ENABLED':'on'}
    install_product_grimoire(app, environ=gate)
    client = app.test_client()
    result = client.get(path+'?grimoire=5')
    assert result.status_code == 302 and result.location == '/grimoire/player'
    assert 'no-store' in result.headers['Cache-Control']
    gate['G076_GRIMOIRE_STEPS_ENABLED'] = 'off'
    assert client.get(path+'?grimoire=5').text == 'old player'


@pytest.mark.parametrize('qid,status', [(701,409), (702,200), (999,409)])
def test_direct_question_alias_cannot_reveal_grimoire_solution(seam, qid, status):
    service = seam[0]
    app = Flask('g077-read'); app.secret_key = 'test-only'
    app.add_url_rule('/q/<int:qid>', 'get_question', lambda qid: 'legacy SGF')
    install_product_grimoire(app, service)
    assert app.test_client().get('/q/'+str(qid)).status_code == status


def test_daily_relabel_is_contained(seam):
    _, _, client, touched, _ = seam
    assert client.post('/api/g076/nonmap/steps', json={
        'flow':'daily','attempt_token':'old-practice-token'}).status_code == 409
    assert touched == []


def test_bound_snapshot_cannot_be_overridden_by_raw_classifier(seam):
    from unittest.mock import Mock
    service = seam[0]
    app = Flask('g077-pinned'); app.secret_key = 'test-only'
    touched = []
    app.add_url_rule('/review', 'srs_review', lambda: touched.append(True) or 'unsafe', methods=['POST'])
    raw_classifier = Mock(return_value={'id':701})
    install_product_grimoire(app, service, lookup=raw_classifier)
    assert app.test_client().post('/review', json={'question_id':701}).status_code == 409
    raw_classifier.assert_not_called()
    assert touched == []


def test_official_app_installs_before_other_hooks():
    tree = ast.parse(Path('app.py').read_text(encoding='utf-8-sig'))
    calls = [n.value.func.id for n in tree.body if isinstance(n, ast.Expr)
             and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name)]
    assert calls.index('install_othermode_guard') < calls.index('install_product_grimoire')


def test_docker_packages_explicit_new_runtime_closure():
    docker = Path('Dockerfile').read_text(encoding='utf-8')
    for name in ('g076_grimoire_adapter.py', 'g076_grimoire_catalog.py',
                 'g076_grimoire_pg_service.py', 'g076_grimoire_product.py',
                 'js/game/g076_grimoire_product_client.js'):
        assert 'COPY '+name+' ' in docker
    # G077-F packages the player in its approved explicit curated root-HTML
    # multi-source COPY, not a duplicate standalone COPY instruction.
    assert docker.count('grimoire_player.html') == 1
    assert 'rating_test.html grimoire_player.html shop.html' in docker


def test_official_provider_uses_configured_path_and_never_defaults_to_fixture(tmp_path, monkeypatch):
    import grimoire_api
    from g076_grimoire_adapter import GrimoireRejected
    path = tmp_path/'official-classification-only.json'
    monkeypatch.setattr(grimoire_api, 'DATA_FILE', str(path))
    with pytest.raises(GrimoireRejected): grimoire_api.official_grimoire_lookup(701)
    path.write_text('[{"id":701,"grimoire_id":5},{"id":702}]', encoding='utf-8')
    assert grimoire_api.official_grimoire_lookup(701)['grimoire_id'] == 5
    assert grimoire_api.official_grimoire_lookup(702).get('grimoire_id') is None
    path.write_text('[{"id":701},{"id":701}]', encoding='utf-8')
    with pytest.raises(GrimoireRejected): grimoire_api.official_grimoire_lookup(701)
