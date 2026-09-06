from __future__ import annotations


def _application(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "w1-d3-rate-limit-test-only")
    import app as application

    application.app.secret_key = "w1-d3-rate-limit-test-only"
    with application._auth_fail_lock:
        application._auth_fail_log.clear()
    return application


class _NoopDb:
    def __init__(self, entered=None):
        self.entered = entered

    def __enter__(self):
        if self.entered is not None:
            self.entered.append(True)
        return object()

    def __exit__(self, exc_type, _exc, _tb):
        return False


def _admin_headers(application, client, user_id=7):
    token = "t" * 32
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["is_admin"] = True
        session["sgf_answer_review_csrf"] = token
    return {application._REVIEW_CSRF_HEADER: token}


def test_authentication_and_csrf_are_checked_before_workbench_throttle(monkeypatch):
    application = _application(monkeypatch)

    anonymous = application.app.test_client()
    response = anonymous.post(
        "/api/admin/sgf-workbench/items/1/status",
        json={"status": "NEEDS_RESEARCH"},
    )
    assert response.status_code == 401

    client = application.app.test_client()
    _admin_headers(application, client)
    response = client.post(
        "/api/admin/sgf-workbench/items/1/status",
        json={"status": "NEEDS_RESEARCH"},
        headers={application._REVIEW_CSRF_HEADER: "invalid"},
    )
    assert response.status_code == 403
    assert response.get_json()["error"] == "review_csrf_failed"


def test_authenticated_mutation_is_allowed_then_throttled_without_partial_stage(monkeypatch):
    application = _application(monkeypatch)
    calls = []
    db_enters = []
    monkeypatch.setattr(application, "get_db", lambda: _NoopDb(db_enters))
    monkeypatch.setattr(
        application,
        "resolve_workbench_item",
        lambda *_args, **_kwargs: calls.append(True) or {"status": "NEEDS_RESEARCH"},
    )

    client = application.app.test_client()
    headers = _admin_headers(application, client)
    limit = application.WORKBENCH_MUTATION_RATE_MAX

    for _ in range(limit):
        response = client.post(
            "/api/admin/sgf-workbench/items/1/status",
            json={"status": "NEEDS_RESEARCH"},
            headers=headers,
        )
        assert response.status_code == 200
    assert len(calls) == limit

    stage_db_enters = []
    monkeypatch.setattr(application, "get_db", lambda: _NoopDb(stage_db_enters))
    throttled = client.post(
        "/api/admin/sgf-workbench/items/1/stage",
        json={"action": "DISABLE_BROKEN_QUESTION"},
        headers=headers,
    )
    assert throttled.status_code == 429
    assert throttled.get_json() == {"error": "rate_limited"}
    assert stage_db_enters == []
    assert len(calls) == limit


def test_workbench_throttle_isolated_by_authenticated_identity(monkeypatch):
    application = _application(monkeypatch)
    monkeypatch.setattr(application, "get_db", lambda: _NoopDb())
    monkeypatch.setattr(
        application,
        "resolve_workbench_item",
        lambda *_args, **_kwargs: {"status": "NEEDS_RESEARCH"},
    )
    limit = application.WORKBENCH_MUTATION_RATE_MAX

    first = application.app.test_client()
    first_headers = _admin_headers(application, first, user_id=7)
    for _ in range(limit):
        assert first.post(
            "/api/admin/sgf-workbench/items/1/status",
            json={"status": "NEEDS_RESEARCH"},
            headers=first_headers,
        ).status_code == 200
    assert first.post(
        "/api/admin/sgf-workbench/items/1/status",
        json={"status": "NEEDS_RESEARCH"},
        headers=first_headers,
    ).status_code == 429

    second = application.app.test_client()
    second_headers = _admin_headers(application, second, user_id=8)
    assert second.post(
        "/api/admin/sgf-workbench/items/1/status",
        json={"status": "NEEDS_RESEARCH"},
        headers=second_headers,
    ).status_code == 200


def test_normal_sequential_review_actions_stay_below_existing_limit(monkeypatch):
    application = _application(monkeypatch)
    monkeypatch.setattr(application, "get_db", lambda: _NoopDb())
    monkeypatch.setattr(
        application,
        "resolve_workbench_item",
        lambda *_args, **_kwargs: {"status": "NEEDS_RESEARCH"},
    )
    client = application.app.test_client()
    headers = _admin_headers(application, client)

    # Four deliberate taps represent a normal short review sequence and stay
    # below the existing five-hit/ten-second authenticated mutation policy.
    for _ in range(application.WORKBENCH_MUTATION_RATE_MAX - 1):
        response = client.post(
            "/api/admin/sgf-workbench/items/1/status",
            json={"status": "NEEDS_RESEARCH"},
            headers=headers,
        )
        assert response.status_code == 200
