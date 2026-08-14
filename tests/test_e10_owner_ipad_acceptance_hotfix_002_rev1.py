"""REV1 evidence for the Owner-acceptance hotfix.

This file deliberately calls the real Flask ``/api/adventure/boss/start``
route and the real ``_load_questions``/``_questions_for_adventure_zone``
selection path.  The disposable dataset is a bounded test fixture (not the
Production question volume), but its records use the canonical question
schema and full SGF/content fields so queue identity can be audited beyond
integer IDs.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import types
from pathlib import Path

import pytest


def _install_app_import_stubs():
    if "katago_explain" not in sys.modules:
        module = types.ModuleType("katago_explain")
        module.KataGoExplainer = type("KataGoExplainer", (), {})
        sys.modules["katago_explain"] = module
    if "explain_overrides" not in sys.modules:
        module = types.ModuleType("explain_overrides")
        module.get_override = lambda *args, **kwargs: None
        sys.modules["explain_overrides"] = module
    if "grimoire_api" not in sys.modules:
        from flask import Blueprint

        module = types.ModuleType("grimoire_api")
        module.grimoire_bp = Blueprint("rev1_grimoire_stub", __name__)
        sys.modules["grimoire_api"] = module
    if "question_taxonomy" not in sys.modules:
        module = types.ModuleType("question_taxonomy")
        module.get_taxonomy = lambda *args, **kwargs: {}
        sys.modules["question_taxonomy"] = module
    if "monster_taxonomy" not in sys.modules:
        module = types.ModuleType("monster_taxonomy")
        module.get_monster_taxonomy = lambda *args, **kwargs: {}
        module.mark_encounters = lambda *args, **kwargs: None
        sys.modules["monster_taxonomy"] = module
    if "chapter_i18n" not in sys.modules:
        module = types.ModuleType("chapter_i18n")
        module.localize_topic = lambda *args, **kwargs: ""
        module.localize_level = lambda *args, **kwargs: ""
        sys.modules["chapter_i18n"] = module
    if "backend_i18n" not in sys.modules:
        module = types.ModuleType("backend_i18n")
        module.badge_en = lambda *args, **kwargs: ""
        module.skill_node_en = lambda *args, **kwargs: ""
        module.title_en = lambda *args, **kwargs: ""
        sys.modules["backend_i18n"] = module


@pytest.fixture(scope="module")
def app_module():
    _install_app_import_stubs()
    import app as app_module

    app_module.app.config["TESTING"] = True
    return app_module


@pytest.fixture()
def real_server_question_dataset(app_module, tmp_path, monkeypatch):
    """Install a canonical-schema disposable dataset behind the real loader."""
    zone = app_module._zone_by_key("k26_30")
    assert zone and zone.get("books"), "the canonical Boss zone must have book filters"
    topic = zone["books"][0]
    records = []
    for index in range(40):
        qid = 970001 + index
        letters = "abcdefghi"
        move = f"{letters[index % 9]}{letters[index // 9]}"
        move_xy = [{"x": index % 9, "y": index // 9}]
        records.append(
            {
                "id": qid,
                "content": f"(;GM[1]FF[4]CA[UTF-8]SZ[9]PL[B](;B[{move}]))",
                "source": f"rev1-disposable/q{qid}.sgf",
                "display_name": f"REV1 disposable question {qid}",
                "topic": topic,
                "discipline": "life_death",
                "stage": "LV1",
                "rank": "30k",
                "difficulty": "30k",
                "enabled": True,
                "is_free": True,
                "free": True,
                "accepted_moves": move_xy,
                "solution_state": "open",
            }
        )
    dataset_path = tmp_path / "questions-rev1.json"
    dataset_path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(app_module, "DATA_FILE", str(dataset_path))
    monkeypatch.setattr(app_module, "_questions_cache", None)
    monkeypatch.setattr(app_module, "_questions_mtime", None)
    monkeypatch.setattr(app_module, "mark_encounters", lambda questions: None)
    monkeypatch.setattr(app_module, "is_premium", lambda *args, **kwargs: True)
    return records


@pytest.fixture()
def real_server_state(app_module, monkeypatch):
    state = {
        "key": "k26_30",
        "seen": 50,
        "pct": 100,
        "unlocked": True,
        "cleared": False,
        "cooldown_left": 0,
    }
    monkeypatch.setattr(app_module, "_adventure_state", lambda uid: [dict(state)])
    return state


def _login(client, uid=7001):
    with client.session_transaction() as session:
        session["user_id"] = uid


def _content_fingerprint(question):
    content = str(question.get("content") or "")
    player_match = re.search(r"PL\[([BW])\]", content)
    canonical = {
        "content": content,
        "player_to_move": question.get("player_to_move") or (player_match.group(1) if player_match else None),
        "accepted_moves": question.get("accepted_moves") or [],
    }
    return hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def test_real_server_boss_start_builds_and_audits_twenty_question_queues(
    app_module, real_server_question_dataset, real_server_state, monkeypatch
):
    """Exercise the real route/loader/filter/shuffle path across fixed seeds."""
    original_random = app_module.random.Random
    attempt_number = {"value": 0}

    class DeterministicRandom:
        def __init__(self, _route_seed):
            seed = f"owner-acceptance-rev1-attempt-{attempt_number['value']}"
            attempt_number["value"] += 1
            self._random = original_random(seed)

        def shuffle(self, values):
            self._random.shuffle(values)

    monkeypatch.setattr(app_module.random, "Random", DeterministicRandom)
    loader_calls = []
    original_loader = app_module._load_questions

    def traced_loader():
        loader_calls.append(True)
        return original_loader()

    monkeypatch.setattr(app_module, "_load_questions", traced_loader)
    client = app_module.app.test_client()
    _login(client)
    by_id = {int(question["id"]): question for question in real_server_question_dataset}
    all_attempts = []

    for _ in range(8):
        response = client.post("/api/adventure/boss/start", json={"zone_key": "k26_30"})
        assert response.status_code == 200, response.get_json()
        body = response.get_json()
        qids = body["question_ids"]
        assert body["total"] == 20
        assert len(qids) == 20
        assert all(isinstance(qid, int) for qid in qids)
        assert len(set(qids)) == 20
        fingerprints = [_content_fingerprint(by_id[qid]) for qid in qids]
        assert all(qid in by_id for qid in qids)
        all_attempts.append({"qids": qids, "fingerprints": fingerprints})
        # The route created the signed exam; clear only this disposable test
        # session slot so the next call exercises a fresh selection.
        with client.session_transaction() as session:
            session.pop("adventure_boss_exam", None)

    consecutive_qid_duplicates = sum(
        qids[index] == qids[index - 1]
        for attempt in all_attempts
        for qids in [attempt["qids"]]
        for index in range(1, len(qids))
    )
    consecutive_content_duplicates = sum(
        fingerprints[i] == fingerprints[i - 1]
        for attempt in all_attempts
        for fingerprints in [attempt["fingerprints"]]
        for i in range(1, len(fingerprints))
    )
    unique_content = {
        fingerprint
        for attempt in all_attempts
        for fingerprint in attempt["fingerprints"]
    }
    assert loader_calls, "the real canonical question loader was not exercised"
    assert consecutive_qid_duplicates == 0
    assert consecutive_content_duplicates == 0
    assert len(unique_content) == len(real_server_question_dataset) == 40


def test_real_server_queue_items_have_distinct_effective_board_content(
    app_module, real_server_question_dataset, real_server_state
):
    """One real route-generated queue must not hide duplicate boards behind IDs."""
    client = app_module.app.test_client()
    _login(client, uid=7002)
    response = client.post("/api/adventure/boss/start", json={"zone_key": "k26_30"})
    assert response.status_code == 200
    qids = response.get_json()["question_ids"]
    questions = {int(question["id"]): question for question in app_module._load_questions()}
    fingerprints = [_content_fingerprint(questions[qid]) for qid in qids]
    assert len(qids) == 20
    assert len(set(qids)) == 20
    assert len(set(fingerprints)) == 20
    assert all(fingerprints[index] != fingerprints[index - 1] for index in range(1, len(fingerprints)))
