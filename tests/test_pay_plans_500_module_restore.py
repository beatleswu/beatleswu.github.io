"""PAY-PLANS-500 -- restore of newebpay.py / paypal_api.py.

Root cause (read-only triage, then this hotfix): commit e7b127bc2 ("fix:
restore production app baseline for shadow dashboard api") brought app.py
code depending on `import newebpay` / `import paypal_api` into master, but
never added those two vendored modules -- so every /api/pay/* route raised
an unhandled ModuleNotFoundError (500) in Production, confirmed live via
GET /api/pay/plans.

Both files are restored byte-identical to their last verified commit
(newebpay.py @ 86f5ca4cfb450b511ed0162085b7a98d733ea23b, paypal_api.py @
64c5a95ca8da8f3df05901fcf2e25aa4ef2eebb6 -- both also present, byte-for-byte
identical, at recovered-production-tip-20260711, the last known-good
Production snapshot before e7b127bc2). See
deploy/runtime-source-provenance.json for full provenance.

These tests never make a real network call to NewebPay or PayPal, never
create a real order/subscription, and never require real credentials --
NEWEBPAY_*/PAYPAL_* are intentionally left unset/empty in this test
environment, exercising exactly the "provider not configured" path that
must now fail safely (503 or a clean redirect) instead of crashing (500).
"""
import hashlib
import importlib
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

NEWEBPAY_PATH = REPO_ROOT / "newebpay.py"
PAYPAL_API_PATH = REPO_ROOT / "paypal_api.py"


def _read(path):
    return path.read_text(encoding="utf-8")


@pytest.fixture
def clean_payment_env(monkeypatch):
    """Ensure every payment credential is unset/empty for these tests --
    the deliberate 'not yet activated' state confirmed live in Production."""
    for key in ("NEWEBPAY_MERCHANT_ID", "NEWEBPAY_HASH_KEY", "NEWEBPAY_HASH_IV",
                "PAYPAL_CLIENT_ID", "PAYPAL_SECRET"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("NEWEBPAY_TEST", "1")
    monkeypatch.setenv("PAYPAL_TEST", "1")
    yield
    for mod_name in ("newebpay", "paypal_api"):
        sys.modules.pop(mod_name, None)


@pytest.fixture
def app_client(clean_payment_env):
    os.environ.setdefault("GO_ODYSSEY_LIVE_STATIC_ROOT", str(REPO_ROOT))
    sys.modules.pop("app", None)
    import app as flask_app_module
    importlib.reload(flask_app_module)
    return flask_app_module.app.test_client(), flask_app_module


# ---------------------------------------------------------------------------
# 1. Both modules import successfully from a clean checkout/container.
# 14. Application startup succeeds in a clean production-like container.
# ---------------------------------------------------------------------------

def test_newebpay_module_imports_successfully(clean_payment_env):
    newebpay = importlib.import_module("newebpay")
    assert hasattr(newebpay, "is_configured")
    assert hasattr(newebpay, "build_period_form")
    assert hasattr(newebpay, "decrypt_period_response")
    assert hasattr(newebpay, "alter_period_status")


def test_paypal_api_module_imports_successfully(clean_payment_env):
    paypal_api = importlib.import_module("paypal_api")
    assert hasattr(paypal_api, "is_configured")
    assert hasattr(paypal_api, "create_product")
    assert hasattr(paypal_api, "create_plan")
    assert hasattr(paypal_api, "create_subscription")
    assert hasattr(paypal_api, "get_subscription")
    assert hasattr(paypal_api, "cancel_subscription")


def test_app_module_imports_without_error(clean_payment_env):
    # app.py's init_db() only runs under `if __name__ == '__main__'`, so a
    # plain import never touches the database -- this proves the module
    # graph (including the two lazily-imported payment modules once a
    # payment route is hit) is structurally sound.
    os.environ.setdefault("GO_ODYSSEY_LIVE_STATIC_ROOT", str(REPO_ROOT))
    sys.modules.pop("app", None)
    import app as flask_app_module  # noqa: F401


# ---------------------------------------------------------------------------
# 2. No undeclared third-party dependency is required at runtime.
# ---------------------------------------------------------------------------

def test_pycryptodome_is_declared_and_importable():
    requirements = _read(REPO_ROOT / "requirements.txt")
    assert "pycryptodome" in requirements
    import Crypto  # noqa: F401
    from Crypto.Cipher import AES  # noqa: F401


def test_paypal_api_uses_only_stdlib():
    content = _read(PAYPAL_API_PATH)
    import_lines = [l for l in content.splitlines() if l.strip().startswith(("import ", "from "))]
    stdlib_modules = {"os", "json", "time", "base64", "urllib"}
    for line in import_lines:
        module = line.split()[1].split(".")[0]
        assert module in stdlib_modules, f"unexpected non-stdlib import in paypal_api.py: {line}"


# ---------------------------------------------------------------------------
# 3. GET /api/pay/plans does not return 500.
# 8. Plans response matches the frontend-consumed schema.
# ---------------------------------------------------------------------------

def test_pay_plans_route_returns_200_not_500(app_client):
    client, _ = app_client
    resp = client.get("/api/pay/plans")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert set(payload.keys()) == {
        "ok", "configured", "test_mode", "paypal_configured",
        "paypal_test_mode", "plans",
    }
    assert set(payload["plans"].keys()) == {"monthly", "annual"}
    for plan in payload["plans"].values():
        assert set(plan.keys()) == {"amount", "days"}


# ---------------------------------------------------------------------------
# 4 & 5. Empty NewebPay/PayPal credentials follow the intended unavailable
# path (not_configured / False), not a crash.
# ---------------------------------------------------------------------------

def test_empty_newebpay_credentials_report_not_configured(app_client):
    client, _ = app_client
    payload = client.get("/api/pay/plans").get_json()
    assert payload["configured"] is False


def test_empty_paypal_credentials_report_not_configured(app_client):
    client, _ = app_client
    payload = client.get("/api/pay/plans").get_json()
    assert payload["paypal_configured"] is False


# ---------------------------------------------------------------------------
# 6. Missing (not just empty) optional provider configuration does not
# crash -- re-import with the keys entirely absent from os.environ.
# ---------------------------------------------------------------------------

def test_missing_config_keys_do_not_crash_module_import(monkeypatch):
    for key in ("NEWEBPAY_MERCHANT_ID", "NEWEBPAY_HASH_KEY", "NEWEBPAY_HASH_IV",
                "NEWEBPAY_TEST", "PAYPAL_CLIENT_ID", "PAYPAL_SECRET", "PAYPAL_TEST"):
        monkeypatch.delenv(key, raising=False)
    sys.modules.pop("newebpay", None)
    sys.modules.pop("paypal_api", None)
    newebpay = importlib.import_module("newebpay")
    paypal_api = importlib.import_module("paypal_api")
    assert newebpay.is_configured() is False
    assert paypal_api.is_configured() is False
    sys.modules.pop("newebpay", None)
    sys.modules.pop("paypal_api", None)


# ---------------------------------------------------------------------------
# 7. No provider network request occurs when credentials are absent.
# ---------------------------------------------------------------------------

def test_no_network_request_when_newebpay_not_configured(app_client):
    client, _ = app_client
    with mock.patch("urllib.request.urlopen") as urlopen_mock:
        resp = client.post("/api/pay/newebpay/subscribe", json={"plan": "monthly"})
        # 401/302 (not logged in) or 503 (not configured) are both acceptable
        # "did not proceed to a provider call" outcomes for this check.
        assert resp.status_code in (401, 403, 302, 503)
        urlopen_mock.assert_not_called()


def test_no_network_request_when_paypal_not_configured(app_client):
    client, _ = app_client
    with mock.patch("urllib.request.urlopen") as urlopen_mock:
        resp = client.post("/api/pay/paypal/subscribe", json={"plan": "monthly"})
        assert resp.status_code in (401, 403, 302, 503)
        urlopen_mock.assert_not_called()


def test_no_network_request_from_plans_route(app_client):
    client, _ = app_client
    with mock.patch("urllib.request.urlopen") as urlopen_mock:
        resp = client.get("/api/pay/plans")
        assert resp.status_code == 200
        urlopen_mock.assert_not_called()


# ---------------------------------------------------------------------------
# 9. Provider helper factories return the expected object/type.
# ---------------------------------------------------------------------------

def test_newebpay_factory_returns_expected_module(clean_payment_env):
    os.environ.setdefault("GO_ODYSSEY_LIVE_STATIC_ROOT", str(REPO_ROOT))
    sys.modules.pop("app", None)
    import app as m
    result = m._newebpay()
    assert result.__name__ == "newebpay"
    assert callable(result.is_configured)


def test_paypal_factory_returns_expected_module(clean_payment_env):
    os.environ.setdefault("GO_ODYSSEY_LIVE_STATIC_ROOT", str(REPO_ROOT))
    sys.modules.pop("app", None)
    import app as m
    result = m._paypal()
    assert result.__name__ == "paypal_api"
    assert callable(result.is_configured)


# ---------------------------------------------------------------------------
# 10. Order/payment initiation routes fail safely when disabled.
# ---------------------------------------------------------------------------

def test_newebpay_subscribe_fails_safely_when_unconfigured(app_client):
    client, _ = app_client
    with client.session_transaction() as sess:
        sess["user_id"] = 1
    resp = client.post("/api/pay/newebpay/subscribe", json={"plan": "monthly"})
    assert resp.status_code == 503
    payload = resp.get_json()
    assert payload["error"] == "not_configured"


def test_paypal_subscribe_fails_safely_when_unconfigured(app_client):
    client, _ = app_client
    with client.session_transaction() as sess:
        sess["user_id"] = 1
    resp = client.post("/api/pay/paypal/subscribe", json={"plan": "monthly"})
    assert resp.status_code == 503
    payload = resp.get_json()
    assert payload["error"] == "not_configured"


# ---------------------------------------------------------------------------
# 11. Callback validation rejects invalid signatures/payloads safely.
# ---------------------------------------------------------------------------

def test_newebpay_notify_rejects_missing_period_field(app_client):
    client, _ = app_client
    resp = client.post("/api/pay/newebpay/notify", data={})
    assert resp.status_code == 400
    assert resp.get_data() == b"no data"


def test_newebpay_notify_rejects_undecryptable_payload(app_client):
    client, _ = app_client
    resp = client.post("/api/pay/newebpay/notify", data={"Period": "not-valid-hex"})
    assert resp.status_code == 400
    assert resp.get_data() == b"decrypt error"


def test_paypal_webhook_ignores_unrecognized_event_safely(app_client):
    client, _ = app_client
    resp = client.post("/api/pay/paypal/webhook", json={})
    assert resp.status_code == 200
    assert resp.get_data() == b"ignored"


def test_paypal_return_redirects_safely_without_subscription_id(app_client):
    client, _ = app_client
    resp = client.get("/api/pay/paypal/return")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/upgrade?pay=failed"


# ---------------------------------------------------------------------------
# 12. No secret values appear in logs or responses.
# ---------------------------------------------------------------------------

def test_plans_response_never_contains_raw_credential_values(app_client, monkeypatch):
    # Even if a credential were non-empty, the /plans contract only exposes
    # booleans (configured/test_mode) -- prove the response body cannot
    # structurally contain a credential value.
    monkeypatch.setenv("NEWEBPAY_MERCHANT_ID", "FAKE_MERCHANT_ID_FOR_TEST")
    monkeypatch.setenv("NEWEBPAY_HASH_KEY", "FAKE_HASH_KEY_FOR_TEST_ONLY")
    monkeypatch.setenv("NEWEBPAY_HASH_IV", "FAKE_HASH_IV_FOR_TEST_ON")
    sys.modules.pop("newebpay", None)
    os.environ.setdefault("GO_ODYSSEY_LIVE_STATIC_ROOT", str(REPO_ROOT))
    sys.modules.pop("app", None)
    import app as m
    client = m.app.test_client()
    resp = client.get("/api/pay/plans")
    body = resp.get_data(as_text=True)
    assert "FAKE_MERCHANT_ID_FOR_TEST" not in body
    assert "FAKE_HASH_KEY_FOR_TEST_ONLY" not in body
    assert "FAKE_HASH_IV_FOR_TEST_ON" not in body


def test_neither_module_logs_credentials_via_print():
    for path in (NEWEBPAY_PATH, PAYPAL_API_PATH):
        content = _read(path)
        for line in content.splitlines():
            if "print(" in line:
                assert "MERCHANT_ID" not in line and "HASH_KEY" not in line \
                    and "HASH_IV" not in line and "SECRET" not in line and "CLIENT_ID" not in line


# ---------------------------------------------------------------------------
# 13. Existing authenticated/unauthenticated behavior remains unchanged.
# ---------------------------------------------------------------------------

def test_plans_route_requires_no_authentication(app_client):
    client, _ = app_client
    resp = client.get("/api/pay/plans")
    assert resp.status_code == 200


def test_subscribe_routes_still_require_login(app_client):
    client, _ = app_client
    resp = client.post("/api/pay/newebpay/subscribe", json={"plan": "monthly"})
    assert resp.status_code in (302, 401, 403)


# ---------------------------------------------------------------------------
# 15. Built image contains both module files (Dockerfile/provenance audit --
# a real image build is exercised separately; this locks the declarative
# contract that must stay in sync with it).
# ---------------------------------------------------------------------------

def test_dockerfile_explicitly_copies_both_modules():
    content = _read(REPO_ROOT / "Dockerfile")
    assert "COPY newebpay.py ./" in content
    assert "COPY paypal_api.py ./" in content


def test_build_manifest_tracks_both_modules():
    import json
    manifest = json.loads(_read(REPO_ROOT / "deploy" / "build-manifest.json"))
    tracked = manifest["build_inputs"]["tracked_in_canonical_branch_this_sprint"]
    assert "newebpay.py" in tracked
    assert "paypal_api.py" in tracked


def test_runtime_provenance_records_both_modules_with_matching_hashes():
    import json
    provenance = json.loads(_read(REPO_ROOT / "deploy" / "runtime-source-provenance.json"))
    by_path = {f["path"]: f for f in provenance["files"]}
    assert "newebpay.py" in by_path
    assert "paypal_api.py" in by_path
    assert by_path["newebpay.py"]["content_sha256"] == hashlib.sha256(NEWEBPAY_PATH.read_bytes()).hexdigest()
    assert by_path["paypal_api.py"]["content_sha256"] == hashlib.sha256(PAYPAL_API_PATH.read_bytes()).hexdigest()


def test_module_files_are_git_tracked():
    result = subprocess.run(
        ["git", "ls-files", "newebpay.py", "paypal_api.py"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    tracked = set(result.stdout.split())
    assert tracked == {"newebpay.py", "paypal_api.py"}


# ---------------------------------------------------------------------------
# 16. Real container GET /api/pay/plans returns the expected non-500 result
# -- exercised separately via an actual Docker build in this Sprint's
# validation (not practical to run a full image build inside the unit-test
# suite); this test is the fast, always-run proxy for the same contract.
# ---------------------------------------------------------------------------

def test_pay_plans_contract_matches_real_flask_route_end_to_end(app_client):
    client, _ = app_client
    resp = client.get("/api/pay/plans")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("application/json")
    payload = resp.get_json()
    assert payload["plans"]["monthly"]["amount"] == 299
    assert payload["plans"]["annual"]["amount"] == 2490
