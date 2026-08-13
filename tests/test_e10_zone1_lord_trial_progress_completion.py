"""Focused server-side contract for the Zone 1 Lord Trial hotfix.

The Lord Trial is an explicitly unlocked exam.  Its question reviews must be
allowed to create the review_log evidence consumed by the authoritative
boss/finish route even when the player has exhausted the ordinary free
practice quota.  The bypass is scoped to the live, server-created exam and
expires with the same evidence window as boss/finish.
"""
from __future__ import annotations

import datetime as dt
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


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
        module.grimoire_bp = Blueprint("grimoire_stub_zone1_trial", __name__)
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
    import app as module

    module.app.config["TESTING"] = True
    return module


def _started_at(minutes_ago: int = 0) -> str:
    return (dt.datetime.now() - dt.timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")


def test_active_boss_exam_question_is_scoped_and_live(app_module):
    with app_module.app.test_request_context("/"):
        from flask import session

        session["adventure_boss_exam"] = {
            "zone_key": "k26_30",
            "question_ids": [101, 102],
            "started_at": _started_at(),
        }
        assert app_module._adventure_boss_question_is_active(101) is True
        assert app_module._adventure_boss_question_is_active("102") is True
        assert app_module._adventure_boss_question_is_active(999) is False


def test_active_replay_exam_uses_the_same_question_scoped_limit_bypass(app_module):
    with app_module.app.test_request_context("/"):
        from flask import session

        session["adventure_boss_exam"] = {
            "zone_key": "k26_30",
            "question_ids": [201, 202],
            "started_at": _started_at(),
            "attempt_mode": "replay",
        }
        assert app_module._adventure_boss_question_is_active(201) is True
        assert app_module._adventure_boss_question_is_active(999) is False


def test_expired_or_malformed_boss_exam_cannot_bypass_practice_limit(app_module):
    with app_module.app.test_request_context("/"):
        from flask import session

        session["adventure_boss_exam"] = {
            "zone_key": "k26_30",
            "question_ids": [101],
            "started_at": _started_at(app_module.BOSS_ATTEMPT_MAX_MINUTES + 1),
        }
        assert app_module._adventure_boss_question_is_active(101) is False
        session["adventure_boss_exam"] = {"question_ids": [101], "started_at": "not-a-date"}
        assert app_module._adventure_boss_question_is_active(101) is False


def test_srs_review_limit_guard_exempts_only_active_boss_questions():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    guard_start = source.index("active_boss_question = (not internal and _adventure_boss_question_is_active(qid))")
    guard = source[guard_start:guard_start + 1400]
    assert "if today_count >= _eff_limit and not active_boss_question:" in guard
    assert "if today_count >= _eff_limit:" not in guard
