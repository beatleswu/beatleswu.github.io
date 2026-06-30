from __future__ import annotations

import pytest

pytestmark = pytest.mark.backend


def test_puzzle_list_requires_login(client):
    response = client.get("/api/questions")

    assert response.status_code == 401


def test_puzzle_list_uses_lightweight_fixture(
    authenticated_client, lightweight_questions
):
    response = authenticated_client.get("/api/questions")

    assert response.status_code == 200
    payload = response.get_json()
    assert [question["id"] for question in payload] == [101]
    assert payload[0]["display_name"] == "corner-capture"
    assert "content" not in payload[0]


def test_puzzle_detail_returns_sgf_and_accepted_moves(
    authenticated_client, lightweight_questions
):
    response = authenticated_client.get("/api/question/101")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["content"] == lightweight_questions[0]["content"]
    assert payload["accepted_moves"] == [{"x": 3, "y": 3}]
    assert payload["locked"] is False


def test_unknown_puzzle_returns_not_found(authenticated_client):
    response = authenticated_client.get("/api/question/999999")

    assert response.status_code == 404


def test_answer_submission_requires_login(client):
    response = client.post(
        "/api/srs/review",
        json={"question_id": 101, "grade": 3},
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {"question_id": 101, "grade": 2},
        {"question_id": 101, "grade": "3"},
        {"grade": 3},
    ],
)
def test_answer_submission_rejects_invalid_payload(authenticated_client, payload):
    response = authenticated_client.post("/api/srs/review", json=payload)

    assert response.status_code == 400


@pytest.mark.pending
@pytest.mark.skip(
    reason=(
        "Successful /api/srs/review fans out across the full progression, "
        "equipment, pet, monster, quest, badge, and reward schema. The server "
        "also receives only a client-computed grade, not the move sequence."
    )
)
def test_answer_submission_success_path_pending_production_faithful_fixture():
    """Placeholder documents deliberately deferred Tier 1 success coverage."""
