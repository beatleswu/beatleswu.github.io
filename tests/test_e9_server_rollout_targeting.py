import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
INDEX = (ROOT / 'index.html').read_text(encoding='utf-8')
FLAGS = (ROOT / 'js/e9/feature_flags.js').read_text(encoding='utf-8')


def test_server_decision_contract_is_fail_closed_and_authenticated():
    assert "'global_disabled'" in APP
    assert "'admin_entitled'" in APP
    assert "'named_allowlist'" in APP
    assert "'unauthenticated'" in APP
    assert "'invalid_config'" in APP
    assert "if not user_id or not username" in APP
    assert "if not config['global_enabled']" in APP
    assert "if not flags['e9Shell']" in APP


def test_rollout_config_normalizes_and_rejects_duplicate_or_invalid_entries():
    assert "casefold()" in APP
    assert "len(entries) != len(set(entries))" in APP
    assert "re.fullmatch(r'[a-z0-9_@.+-]{1,160}', x)" in APP


def test_auth_me_is_the_server_decision_boundary():
    assert "'e9_rollout': decision" in APP
    assert "_e9_rollout_decision(" in APP
    assert "_e9_rollout_telemetry(decision, uid)" in APP
    assert "user_digest" in APP
    assert "E9_ROLLOUT_ALLOWLIST" in APP


def test_client_consumes_server_flags_and_keeps_production_defaults_false():
    assert "__GO_E9_SERVER_FLAGS__" in INDEX
    assert "me.e9_rollout.effective_flags || {}" in INDEX
    assert "__GO_E9_SERVER_FLAGS__" in FLAGS
    for name in ('e9Shell', 'e9TopHud', 'e9LeftNav', 'e9RightCards', 'e9BottomDock', 'e9WorldStage'):
        assert re.search(rf'{name}: false', FLAGS)


def test_rollout_config_is_environment_only_and_no_client_identity_heuristic():
    assert "E9_ROLLOUT_GLOBAL_ENABLED" in APP
    assert "E9_ROLLOUT_ADMIN_ENABLED" in APP
    assert "email" not in APP[APP.index('def _e9_rollout_decision'):APP.index('def _e9_rollout_telemetry')]
