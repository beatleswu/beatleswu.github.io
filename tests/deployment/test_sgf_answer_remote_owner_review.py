"""Deployment-preflight contracts for remote SGF Owner Review access."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
ROUTES = (ROOT / "sgf_answer_review_routes.py").read_text(encoding="utf-8")
QUEUE = (ROOT / "sgf_answer_review_queue.py").read_text(encoding="utf-8")
CLIENT = (ROOT / "sgf_answer_review.js").read_text(encoding="utf-8")
HARNESS = (ROOT / "tools" / "run_sgf_answer_review_queue_qa.py").read_text(encoding="utf-8")
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
COMPOSE = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
NGINX = (ROOT / "nginx" / "default.conf").read_text(encoding="utf-8")
SERVICE_WORKER = (ROOT / "sw.js").read_text(encoding="utf-8")


def test_remote_route_reuses_normal_admin_authorization_without_qa_bypass():
    assert "create_sgf_answer_review_blueprint" in APP
    assert "admin_required=admin_required" in APP
    assert ROUTES.count("@admin_required") == 6
    assert "/admin/sgf-answer-review" in ROUTES
    assert "/__local_qa__/owner-login" not in APP
    assert "/__local_qa__/owner-login" not in ROUTES


def test_local_qa_bootstrap_is_loopback_only_and_absent_from_image():
    assert 'host="127.0.0.1"' in HARNESS
    assert "NETWORK_SCOPE=127.0.0.1_ONLY" in HARNESS
    assert "run_sgf_answer_review_queue_qa.py" not in DOCKERFILE


def test_remote_transport_requires_https_and_secure_session_cookie():
    assert "return 301 https://$host$request_uri" in NGINX
    assert "listen 443 ssl" in NGINX
    assert "Strict-Transport-Security" in NGINX
    assert "SESSION_COOKIE_HTTPONLY=True" in APP
    assert "SESSION_COOKIE_SAMESITE='Lax'" in APP
    assert "SESSION_COOKIE_SECURE=_site_url_for_cookie.startswith('https://')" in APP
    assert "SITE_URL=${SITE_URL:-https://godokoro.com}" in COMPOSE
    assert "SECRET_KEY=${SECRET_KEY:-}" in COMPOSE


def test_review_writes_are_same_origin_csrf_protected():
    assert "review_origin_denied" in ROUTES
    assert "review_csrf_failed" in ROUTES
    assert "secrets.compare_digest" in ROUTES
    assert "X-SGF-Answer-Review-CSRF" in ROUTES
    assert "headers[runtime.csrfHeader] = runtime.csrfToken" in CLIENT
    assert 'credentials: "same-origin"' in CLIENT


def test_review_state_schema_is_additive_and_account_scoped():
    assert "ensure_review_queue_tables(conn)" in APP
    for table in (
        "sgf_answer_review_states",
        "sgf_answer_review_progress",
        "sgf_answer_review_mutations",
        "sgf_answer_review_audit",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in QUEUE
    assert "owner_user_id" in QUEUE
    assert "UPDATE questions" not in QUEUE
    assert "accepted_moves" not in QUEUE


def test_review_api_is_network_only_under_service_worker():
    api_guard = "if (url.pathname.startsWith('/api/'))"
    assert api_guard in SERVICE_WORKER
    api_offset = SERVICE_WORKER.index(api_guard)
    cache_first_offset = SERVICE_WORKER.index("url.pathname.endsWith('.js')")
    assert api_offset < cache_first_offset
    assert "event.respondWith(fetch(request))" in SERVICE_WORKER[api_offset:cache_first_offset]
