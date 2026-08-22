"""B_013 source-contract evidence for server-result authority readiness.

The current routes intentionally remain blocked: their live callers do not
send canonical answer/move evidence. These tests prevent a future change from
mistaking strict boolean validation, Shadow observation, or replay markers for
server result truth.
"""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
DAILY_SOURCE = (ROOT / "daily_challenge.html").read_text(encoding="utf-8")
INDEX_SOURCE = (ROOT / "index.html").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    tree = ast.parse(APP_SOURCE)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            lines = APP_SOURCE.splitlines()
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    raise AssertionError(f"missing function: {name}")


def test_endpoints_and_current_payloads_are_explicitly_audited():
    public = _function_source("srs_review")
    daily = _function_source("dc_submit")
    friend = _function_source("friend_challenge_answer")

    assert "@app.route('/api/srs/review', methods=['POST'])" in APP_SOURCE
    assert "@app.route('/api/daily-challenge/submit', methods=['POST'])" in APP_SOURCE
    assert "@app.route('/api/challenges/friend/<int:cid>/answer', methods=['POST'])" in APP_SOURCE
    assert 'grade=data.get(\'grade\')' in public
    assert "data['correct']" in daily
    assert "data['correct']" in friend


def test_current_live_callers_do_not_supply_canonical_answer_evidence():
    assert "body: JSON.stringify({correct: !!correct})" in DAILY_SOURCE
    assert "body: JSON.stringify({ question_id: qid, correct })" in INDEX_SOURCE
    public = _function_source("srs_review")
    assert "moves" not in public


def test_server_verifier_requires_evidence_not_client_result():
    verifier = _function_source("_rt_server_verify")
    assert "moves" in verifier
    assert "_rt_replay(tree, moves)" in verifier
    assert "data.get('correct')" not in verifier
    assert "data.get('grade')" not in verifier


def test_b013_routes_do_not_claim_shadow_as_authority():
    for name in ("dc_submit", "friend_challenge_answer"):
        source = _function_source(name)
        assert "shadow_judging.observe_answer_route" in source
        assert "_observe_xp_shadow" in source or name == "friend_challenge_answer"
    public = _function_source("srs_review")
    assert "_review_service.review" in public
    assert "shadow_judging" not in public


def test_existing_replay_guards_are_server_side_but_not_result_truth():
    daily = _function_source("dc_submit")
    friend = _function_source("friend_challenge_answer")
    assert "datetime.date.today().isoformat()" in daily
    assert "UPDATE users SET id=id WHERE id=?" in daily
    assert "UNIQUE(user_id, challenge_date)" in APP_SOURCE
    assert "UPDATE users SET id=id WHERE id=?" in friend
    assert "friend_challenge_answers" in friend
    assert "already_submitted" in daily
    assert "已經作答過此題" in friend


def test_potion_and_forbidden_scope_are_untouched():
    shop_use = _function_source("shop_use")
    assert "operation_id" not in shop_use
    assert "XPSettlement.settle" not in APP_SOURCE
    assert "small_xp_potion" in APP_SOURCE
    assert "xp_amulet" in APP_SOURCE
    assert "go_stone_black" in APP_SOURCE
