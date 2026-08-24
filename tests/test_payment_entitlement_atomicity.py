"""Durable SQLite regression coverage for payment entitlement atomicity."""
import importlib
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_SECRET = "test-only-payment-atomicity-secret"


def _app_module():
    os.environ.setdefault("GO_ODYSSEY_LIVE_STATIC_ROOT", str(REPO_ROOT))
    os.environ.setdefault("SECRET_KEY", TEST_SECRET)
    sys.modules.pop("app", None)
    return importlib.import_module("app")


class _DbContext:
    def __init__(self, path, events):
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self.events = events
        self.connection_id = id(self)
        self.commits = 0
        self.rollbacks = 0

    def execute(self, sql, params=()):
        self.events.append(("execute", self.connection_id, sql))
        return self._conn.execute(sql, params)

    def commit(self):
        self.commits += 1
        self.events.append(("commit", self.connection_id, ""))
        self._conn.commit()

    def rollback(self):
        self.rollbacks += 1
        self.events.append(("rollback", self.connection_id, ""))
        self._conn.rollback()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self._conn.close()


class _DbFactory:
    def __init__(self, path):
        self.path = path
        self.events = []
        self.contexts = []

    def __call__(self):
        context = _DbContext(self.path, self.events)
        self.contexts.append(context)
        return context


def _query(path, sql, params=()):
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(sql, params).fetchall()


@pytest.fixture()
def payment_db(tmp_path):
    path = tmp_path / "payment-atomicity.sqlite"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE users (id INTEGER PRIMARY KEY, plan TEXT NOT NULL,
                premium_until TEXT, is_admin INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE subscriptions (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
                provider TEXT, mer_order_no TEXT UNIQUE, plan_key TEXT, amount INTEGER,
                status TEXT, period_no TEXT, charged_times INTEGER, total_times INTEGER,
                updated_at TEXT, cancelled_at TEXT);
            CREATE TABLE payment_notify_log (id INTEGER PRIMARY KEY, provider TEXT,
                event_key TEXT UNIQUE, payload TEXT, created_at TEXT);
            CREATE TABLE payment_orders (id INTEGER PRIMARY KEY, mer_order_no TEXT UNIQUE,
                user_id INTEGER, provider TEXT, plan_key TEXT, amount REAL, currency TEXT,
                status TEXT, raw_payload TEXT, created_at TEXT, paid_at TEXT);
            CREATE TABLE player_wardrobe (user_id INTEGER, item_id TEXT, obtained_at TEXT,
                source TEXT, UNIQUE(user_id, item_id));
            CREATE TABLE badges_earned (user_id INTEGER, badge_id TEXT, earned_at TEXT,
                seen INTEGER, UNIQUE(user_id, badge_id));
            CREATE TABLE player_appearance (user_id INTEGER PRIMARY KEY, outfit_id TEXT,
                hat_id TEXT, aura_id TEXT, pet_id TEXT, title_id TEXT, accessory_id TEXT);
        """)
    return path


@pytest.fixture()
def app_with_db(monkeypatch, payment_db):
    app = _app_module()
    factory = _DbFactory(payment_db)
    monkeypatch.setattr(app, "get_db", factory)
    return app, factory, payment_db


def _seed(path, provider, order_no, uid=701, plan="monthly", amount=299):
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO users(id, plan, premium_until) VALUES(?,?,?)",
                     (uid, "free", None))
        conn.execute("""INSERT INTO subscriptions
            (id,user_id,provider,mer_order_no,plan_key,amount,status,period_no,charged_times,total_times)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
                     (uid, uid, provider, order_no, plan, amount, "pending", "", 0, 99))


def _newebpay_event(order_no):
    return {"Status": "SUCCESS", "Result": {"MerchantOrderNo": order_no,
            "PeriodNo": "period-701", "AlreadyTimes": "1", "TotalTimes": 99,
            "AuthAmt": 299}}


class _Paypal:
    def __init__(self, data):
        self.data = data

    def get_subscription(self, sub_id):
        assert sub_id == self.data["id"]
        return self.data


def _paypal_data(sub_id):
    return {"id": sub_id, "status": "ACTIVE", "billing_info": {
        "cycle_executions": [{"cycles_completed": 1}],
        "next_billing_time": "2030-01-01T00:00:00Z"}}


def _assert_success(path, uid, event_key, order_no):
    user = _query(path, "SELECT plan,premium_until FROM users WHERE id=?", (uid,))[0]
    assert user["plan"] == "premium" and user["premium_until"]
    assert len(_query(path, "SELECT * FROM payment_notify_log WHERE event_key=?", (event_key,))) == 1
    assert len(_query(path, "SELECT * FROM payment_orders WHERE mer_order_no=?", (order_no,))) == 1
    assert len(_query(path, "SELECT * FROM player_wardrobe WHERE user_id=?", (uid,))) == len(_app_module().PREMIUM_ITEMS)
    assert len(_query(path, "SELECT * FROM badges_earned WHERE user_id=?", (uid,))) == len(_app_module().PREMIUM_BADGES)
    assert len(_query(path, "SELECT * FROM player_appearance WHERE user_id=?", (uid,))) == 1


@pytest.mark.parametrize("provider", ["newebpay", "paypal"])
def test_atomic_success_duplicate_and_single_final_commit(app_with_db, monkeypatch, provider):
    app, factory, path = app_with_db
    uid, order_no = (701, f"{provider}-sub-701")
    _seed(path, provider, order_no, uid, amount=299 if provider == "newebpay" else 9.9)
    if provider == "newebpay":
        result = app._handle_period_notify(_newebpay_event(order_no), "{}")
        event_key, paid_order = "newebpay:period-701:1", f"{order_no}-1"
        duplicate = app._handle_period_notify(_newebpay_event(order_no), "{}")
    else:
        monkeypatch.setattr(app, "_paypal", lambda: _Paypal(_paypal_data(order_no)))
        result = app._paypal_sync_subscription(order_no, event_key="paypal:event-701")
        event_key, paid_order = "paypal:event-701", f"{order_no}-1"
        duplicate = app._paypal_sync_subscription(order_no, event_key="paypal:event-701")
    assert result == (True, "ok")
    assert duplicate == (True, "duplicate_ignored")
    _assert_success(path, uid, event_key, paid_order)
    first_until = _query(path, "SELECT premium_until FROM users WHERE id=?", (uid,))[0][0]
    assert _query(path, "SELECT premium_until FROM users WHERE id=?", (uid,))[0][0] == first_until
    if provider == "paypal":
        assert first_until == "2030-01-04T00:00:00"
    success_context = factory.contexts[0]
    assert success_context.commits == 1
    assert success_context.rollbacks == 0
    assert {connection_id for _, connection_id, _ in factory.events} == {success_context.connection_id, factory.contexts[1].connection_id}


@pytest.mark.parametrize("provider", ["newebpay", "paypal"])
def test_failure_rolls_back_then_same_event_retries_once(app_with_db, monkeypatch, provider):
    app, factory, path = app_with_db
    uid, order_no = (702, f"{provider}-sub-702")
    _seed(path, provider, order_no, uid, amount=299 if provider == "newebpay" else 9.9)
    original = app._grant_premium_rewards_in_tx

    def fail_after_entitlement(*args, **kwargs):
        raise RuntimeError("controlled reward failure")

    monkeypatch.setattr(app, "_grant_premium_rewards_in_tx", fail_after_entitlement)
    if provider == "newebpay":
        with pytest.raises(RuntimeError, match="controlled reward failure"):
            app._handle_period_notify(_newebpay_event(order_no), "{}")
        event_key, paid_order = "newebpay:period-701:1", f"{order_no}-1"
    else:
        monkeypatch.setattr(app, "_paypal", lambda: _Paypal(_paypal_data(order_no)))
        with pytest.raises(RuntimeError, match="controlled reward failure"):
            app._paypal_sync_subscription(order_no, event_key="paypal:event-702")
        event_key, paid_order = "paypal:event-702", f"{order_no}-1"
    user_after_failure = _query(path, "SELECT plan,premium_until FROM users WHERE id=?", (uid,))[0]
    assert (user_after_failure["plan"], user_after_failure["premium_until"]) == ("free", None)
    assert _query(path, "SELECT status,charged_times FROM subscriptions WHERE id=?", (uid,))[0]["status"] == "pending"
    for table in ("payment_notify_log", "payment_orders", "player_wardrobe", "badges_earned", "player_appearance"):
        assert _query(path, f"SELECT * FROM {table}") == []
    assert factory.contexts[0].commits == 0 and factory.contexts[0].rollbacks == 1
    monkeypatch.setattr(app, "_grant_premium_rewards_in_tx", original)
    if provider == "newebpay":
        assert app._handle_period_notify(_newebpay_event(order_no), "{}") == (True, "ok")
    else:
        assert app._paypal_sync_subscription(order_no, event_key="paypal:event-702") == (True, "ok")
    _assert_success(path, uid, event_key, paid_order)


def test_import_with_synthetic_secret_never_creates_key_file(tmp_path):
    isolated_app = tmp_path / "app.py"
    shutil.copy2(REPO_ROOT / "app.py", isolated_app)
    code = """import importlib.util, os, sys
os.environ['SECRET_KEY'] = 'test-only-payment-atomicity-secret'
sys.path.insert(0, r'%s')
spec = importlib.util.spec_from_file_location('isolated_payment_app', r'%s')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert not os.path.exists(r'%s')
""" % (REPO_ROOT, isolated_app, tmp_path / "secret_key.txt")
    subprocess.run([sys.executable, "-c", code], check=True, cwd=tmp_path,
                   env={**os.environ, "SECRET_KEY": TEST_SECRET}, capture_output=True, text=True)


def test_transaction_neutral_cores_and_standalone_wrappers(app_with_db):
    app, factory, path = app_with_db
    _seed(path, "newebpay", "standalone-703", uid=703)
    core = factory()
    app._extend_premium_in_tx(core, 703, 31, "test")
    assert core.commits == 0 and core.rollbacks == 0
    core.rollback()

    set_core = factory()
    app._set_premium_until_in_tx(set_core, 703, "2030-01-01T00:00:00", "test")
    assert set_core.commits == 0 and set_core.rollbacks == 0
    set_core.rollback()

    standalone = factory()
    app._extend_premium(standalone, 703, 31, "test")
    assert standalone.commits == 1 and standalone.rollbacks == 0
    standalone.rollback()

    rewards = factory()
    app._grant_premium_rewards_in_tx(703, rewards)
    assert rewards.commits == 0 and rewards.rollbacks == 0
    rewards.rollback()
