"""Focused contract checks for GO_ODYSSEY_ACT_A_APP_WIRING_D1."""

import ast
from contextlib import contextmanager
from pathlib import Path

import pytest

from activation_http_contract import ActivationDomainError, ActivationDomainResult


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (REPO_ROOT / 'app.py').read_text(encoding='utf-8')
APP_TREE = ast.parse(APP_SOURCE, filename=str(REPO_ROOT / 'app.py'))


def _function(name):
    return next(
        node for node in APP_TREE.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )


def _calls_attribute(node, attribute):
    return [
        child for child in ast.walk(node)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr == attribute
    ]


class _FakeConnection:
    def __init__(self, *, commit_error=None):
        self.begin_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self.close_count = 0
        self.commit_error = commit_error

    def execute(self, statement):
        assert statement == 'BEGIN'
        self.begin_count += 1

    def commit(self):
        self.commit_count += 1
        if self.commit_error:
            raise self.commit_error

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.close_count += 1


def _activation_transaction_for(fake_connection):
    node = _function('_activation_transaction')
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        'contextmanager': contextmanager,
        'get_db': lambda: fake_connection,
    }
    exec(compile(module, '<activation-transaction-test>', 'exec'), namespace)  # noqa: S102
    return namespace['_activation_transaction']


def test_activation_transaction_commits_once_and_closes_on_success():
    connection = _FakeConnection()
    transaction = _activation_transaction_for(connection)

    with transaction() as yielded:
        assert yielded is connection

    assert connection.commit_count == 1
    assert connection.rollback_count == 0
    assert connection.close_count == 1
    assert connection.begin_count == 1


def test_activation_transaction_rolls_back_domain_failure_and_closes():
    connection = _FakeConnection()
    transaction = _activation_transaction_for(connection)

    with pytest.raises(RuntimeError, match='domain failure'):
        with transaction():
            raise RuntimeError('domain failure')

    assert connection.commit_count == 0
    assert connection.rollback_count == 1
    assert connection.close_count == 1
    assert connection.begin_count == 1


def test_activation_transaction_rolls_back_commit_failure_and_closes():
    connection = _FakeConnection(commit_error=OSError('commit failure'))
    transaction = _activation_transaction_for(connection)

    with pytest.raises(OSError, match='commit failure'):
        with transaction():
            pass

    assert connection.commit_count == 1
    assert connection.rollback_count == 1
    assert connection.close_count == 1
    assert connection.begin_count == 1


def test_activation_map_battle_mutation_routes_use_the_explicit_coordinator():
    for name in (
        'map_battle_v1_prepare_attempt',
        'map_battle_v1_resume_validation',
        'map_battle_v1_submission_nonce',
        'map_battle_v1_answers',
    ):
        route = _function(name)
        assert any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == '_activation_transaction'
            for child in ast.walk(route)
        ), name
        assert not _calls_attribute(route, 'commit'), name
        assert not _calls_attribute(route, 'rollback'), name


def test_activation_http_types_are_flask_and_transaction_free():
    contract_source = (REPO_ROOT / 'activation_http_contract.py').read_text(encoding='utf-8')
    assert 'from flask' not in contract_source
    assert 'get_db' not in contract_source
    assert '.commit(' not in contract_source
    assert '.rollback(' not in contract_source


def test_result_and_error_snapshot_payload_and_preserve_stable_error_fields():
    source_body = {'ok': True}
    result = ActivationDomainResult(source_body, status_code=201)
    source_body['ok'] = False
    assert result.body['ok'] is True
    assert result.status_code == 201

    error = ActivationDomainError(
        'provider_unavailable',
        status_code=503,
        retryable=True,
        message='try again later',
        body={'error': 'caller-cannot-override', 'detail': 'safe detail'},
    )
    payload = error.to_http_body()
    assert payload == {
        'error': 'provider_unavailable',
        'code': 'provider_unavailable',
        'retryable': True,
        'message': 'try again later',
        'detail': 'safe detail',
    }
    assert error.status_code == 503


def test_activation_http_types_validate_status_and_code():
    with pytest.raises(ValueError):
        ActivationDomainResult({}, status_code=700)
    with pytest.raises(ValueError):
        ActivationDomainError('bad code')
    with pytest.raises(TypeError):
        ActivationDomainError('bad_retryable', retryable=1)


def test_identity_hot_reader_contract_and_truthful_comments_remain_intact():
    assert 'reader = BootstrapGatedIdentityReader(conn)' in APP_SOURCE
    assert 'if not reader.hot:' in APP_SOURCE
    assert 'return reader.group_keys_for(ids)' in APP_SOURCE
    assert 'def _identity_group_key(gk_map, qid):' in APP_SOURCE
    assert 'every environment today' not in APP_SOURCE
    assert 'Cold (today)' not in APP_SOURCE


def test_app_contains_only_boundary_adapters_not_activation_domain_authority():
    assert 'def _activation_domain_result_response(result):' in APP_SOURCE
    assert 'def _activation_domain_error_response(error):' in APP_SOURCE
    assert 'ActivationDomainResult' in APP_SOURCE
    assert 'ActivationDomainError' in APP_SOURCE
    # The app may adapt reviewed domain ports, but it must not introduce
    # parallel provider/reward/inventory/onboarding implementations.
    assert 'class ActivationProvider' not in APP_SOURCE
    assert 'class ActivationReward' not in APP_SOURCE
    assert 'class ActivationInventory' not in APP_SOURCE
    assert 'class ActivationOnboarding' not in APP_SOURCE


def test_reviewed_provider_and_inventory_handoffs_are_called_at_narrow_seams():
    provider_new = _function('_map_battle_provider_for_new')
    provider_restore = _function('_map_battle_provider_for_restore')
    inventory = _function('_inv_consume')

    assert any(
        isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id == 'resolve_map_battle_provider_for_new'
        for child in ast.walk(provider_new)
    )
    assert any(
        isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id == 'resolve_map_battle_provider_for_restore'
        for child in ast.walk(provider_restore)
    )
    assert any(
        isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id == 'consume_shop_inventory'
        for child in ast.walk(inventory)
    )
    assert not _calls_attribute(inventory, 'commit')
    assert not _calls_attribute(inventory, 'rollback')
    assert 'runtime_provider=MAP_BATTLE_RUNTIME_PROVIDER_REGISTRY' in APP_SOURCE


def test_rewards_sync_uses_accepted_coin_authority_inside_act_a_transaction():
    route = _function('rewards_sync')

    assert any(
        isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id == 'settle_rewards_sync_claim_in_transaction'
        for child in ast.walk(route)
    )
    assert any(
        isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id == '_activation_transaction'
        for child in ast.walk(route)
    )
    assert not _calls_attribute(route, 'commit')
    assert not _calls_attribute(route, 'rollback')
    assert '_activation_coin_reward_error_response' in APP_SOURCE


def test_onboarding_v2_routes_are_dark_gated_and_use_the_app_transaction():
    mutation = _function('_onboarding_v2_mutation')
    projection = _function('onboarding_v2_projection')

    assert "GO_ODYSSEY_ONBOARDING_V2_ENABLED" in APP_SOURCE
    assert 'w2_a1_onboarding_v1' not in APP_SOURCE
    assert "@app.route('/api/onboarding/v2', methods=['GET'])" in APP_SOURCE
    for name in (
        'onboarding_v2_start',
        'onboarding_v2_resume',
        'onboarding_v2_skip',
        'onboarding_v2_finish',
    ):
        assert f'def {name}():' in APP_SOURCE
    assert any(
        isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id == '_activation_transaction'
        for child in ast.walk(mutation)
    )
    assert any(
        isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id == 'get_onboarding_v2_state'
        for child in ast.walk(projection)
    )
    assert not _calls_attribute(mutation, 'commit')
    assert not _calls_attribute(mutation, 'rollback')
