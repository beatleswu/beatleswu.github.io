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
    assert "casefold()" in APP  # still used for E9_ROLLOUT_SCOPE, not identity
    assert "len(entries) != len(set(entries))" in APP
    assert "_E9_CANONICAL_USER_ID_PATTERN = re.compile(r'[1-9][0-9]*')" in APP
    assert "if x.strip()" in APP


def test_allowlist_matches_canonical_user_id_not_username_with_no_fallback():
    # E9 Phase 1 identity correction: the allowlist must match users.id (a
    # stable, canonical primary key), never username -- and there must be no
    # dual-track "user_id OR username" compatibility path. A fallback would
    # let the incorrect identity model persist indefinitely alongside the
    # correct one and make the allowlist's true coverage impossible to audit.
    decision_fn = APP[APP.index('def _e9_rollout_decision'):APP.index('def _e9_rollout_telemetry')]
    assert "str(user_id) in config['allowlist']" in decision_fn
    assert "_e9_normalize_identity" not in APP  # dead helper from the old username-matching design, removed entirely
    assert "username) in config['allowlist']" not in decision_fn
    assert " or " not in re.search(r"elif config\['scope'\] == 'named_allowlist'.*", decision_fn).group()


def test_admin_only_scope_is_default_and_allowlist_cannot_expand_it():
    assert "os.environ.get('E9_ROLLOUT_SCOPE', 'admin_only')" in APP
    assert "raw_scope not in {'admin_only', 'named_allowlist'}" in APP
    assert "if raw_scope == 'admin_only' and entries" in APP
    assert "config['scope'] == 'named_allowlist'" in APP


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


def test_allowlist_contents_never_reach_client_response_or_logs():
    # The decision dict is exactly what /api/auth/me serializes and what
    # _e9_rollout_telemetry logs -- confirm neither ever includes the
    # configured allowlist itself, only the (already-hashed, in
    # _e9_rollout_telemetry) per-user outcome.
    decision_fn = APP[APP.index('def _e9_rollout_decision'):APP.index('def _e9_rollout_telemetry')]
    telemetry_fn = APP[APP.index('def _e9_rollout_telemetry'):APP.index('QUESTION_PROBLEM_REPORT_REASON_CODES')]
    assert "return {'eligible': eligible, 'reason': reason, 'effective_flags': flags, **base}" in decision_fn
    assert "'allowlist'" not in decision_fn.split("return {'eligible'")[-1]  # not present in the returned dict literal
    assert "config['allowlist']" not in telemetry_fn
    assert "hashlib.sha256(str(user_id)" in telemetry_fn  # only a hashed digest is logged, never the raw identity
