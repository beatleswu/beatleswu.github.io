import ast
import importlib
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _app_module():
    os.environ.setdefault("GO_ODYSSEY_LIVE_STATIC_ROOT", str(REPO_ROOT))
    sys.modules.pop("app", None)
    return importlib.import_module("app")


class _Cursor:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self, user, fail_on=None):
        self.user = user
        self.fail_on = fail_on
        self.statements = []
        self.commits = 0

    def execute(self, statement, params=()):
        self.statements.append(statement)
        if self.fail_on and self.fail_on in statement:
            raise RuntimeError("injected reward write failure")
        if "SELECT plan, premium_until FROM users" in statement:
            return _Cursor(self.user)
        if "SELECT * FROM player_appearance" in statement:
            return _Cursor(None)
        return _Cursor()

    def commit(self):
        self.commits += 1


def test_transaction_neutral_helpers_never_commit_on_success_or_failure():
    app = _app_module()
    conn = _Connection({"plan": "free", "premium_until": None})

    app._extend_premium_in_tx(conn, 7, 30, "test")

    assert conn.commits == 0
    assert any("UPDATE users SET plan='premium'" in sql for sql in conn.statements)
    assert any("player_wardrobe" in sql for sql in conn.statements)

    failing = _Connection({"plan": "free", "premium_until": None},
                          fail_on="player_wardrobe")
    try:
        app._extend_premium_in_tx(failing, 7, 30, "test")
    except RuntimeError as exc:
        assert "injected reward write failure" in str(exc)
    else:
        raise AssertionError("injected reward failure must propagate to transaction owner")
    assert failing.commits == 0


def test_standalone_compatibility_wrappers_commit_once():
    app = _app_module()
    conn = _Connection({"plan": "free", "premium_until": None})

    app._extend_premium(conn, 7, 30, "test")

    assert conn.commits == 1


def test_payment_success_paths_commit_only_after_in_transaction_premium_work():
    source = (REPO_ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}

    for name, helper in (
        ("_handle_period_notify", "_extend_premium_in_tx"),
        ("_paypal_sync_subscription", "_set_premium_until_in_tx"),
    ):
        calls = [node for node in ast.walk(functions[name]) if isinstance(node, ast.Call)]
        helper_lines = [call.lineno for call in calls
                        if isinstance(call.func, ast.Name) and call.func.id == helper]
        commit_lines = [call.lineno for call in calls
                        if isinstance(call.func, ast.Attribute) and call.func.attr == "commit"]
        assert helper_lines, f"{name} must use {helper}"
        assert any(line > max(helper_lines) for line in commit_lines), (
            f"{name} must commit after {helper} completes")
