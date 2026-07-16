import re
import os
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD_STAGE = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
WORLD_MARKUP = (ROOT / "components/adventure/world_stage.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")


def _load_rollout_module():
    from flask import Blueprint

    modules = {
        "katago_explain": {"KataGoExplainer": type("KataGoExplainer", (), {})},
        "explain_overrides": {"get_override": lambda *a, **k: None},
        "question_taxonomy": {"get_taxonomy": lambda *a, **k: {}},
        "monster_taxonomy": {"get_monster_taxonomy": lambda *a, **k: {}, "mark_encounters": lambda *a, **k: None},
        "chapter_i18n": {"localize_topic": lambda *a, **k: "", "localize_level": lambda *a, **k: ""},
        "backend_i18n": {"badge_en": lambda *a, **k: "", "skill_node_en": lambda *a, **k: "", "title_en": lambda *a, **k: ""},
        "grimoire_api": {"grimoire_bp": Blueprint("e9_c1_1_grimoire_stub", __name__)},
    }
    for name, attrs in modules.items():
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module
    for name in ("sgf_engine", "sgf_engine.parser"):
        sys.modules[name] = types.ModuleType(name)
    parser = types.ModuleType("sgf_engine.parser.sgf_parser")
    parser.parse_sgf = lambda *a, **k: None
    sys.modules["sgf_engine.parser.sgf_parser"] = parser
    import app
    return app


def test_newbie_panel_is_owned_by_world_stage_and_uses_canonical_identity():
    assert 'id="e9-newbie-mainline"' in WORLD_MARKUP
    assert "function renderBeginnerVillageMainline(root, zone)" in WORLD_STAGE
    assert "zone.key !== 'k26_30'" in WORLD_STAGE
    assert "zones.filter(function (zone) { return zone.key === 'k26_30'; })" in WORLD_STAGE
    assert "localStorage" not in WORLD_STAGE
    assert "location.search" not in WORLD_STAGE


def test_newbie_panel_reuses_batch_a_copy_and_has_no_second_adventure_schema():
    for key in (
        "adventure.newbie.first_stop_title",
        "adventure.newbie.summary",
        "adventure.newbie.step_battle",
        "adventure.newbie.step_progress",
        "adventure.newbie.step_boss",
        "adventure.newbie.first_star_hint",
        "adventure.newbie.cta_begin",
        "adventure.newbie.cta_continue",
        "adventure.newbie.cta_boss",
    ):
        assert key in WORLD_STAGE
        assert re.search(re.escape("'" + key + "'") + r"\s*:\s*\{\s*en:", I18N)
    render_body = WORLD_STAGE.split("function renderBeginnerVillageMainline", 1)[1].split("function renderZones", 1)[0]
    assert "/api/adventure/bootstrap" not in render_body
    assert "startAdventureFromE9(zone.key)" in WORLD_STAGE
    assert "Daily" not in WORLD_STAGE


def test_newbie_cta_maps_existing_state_without_recomputing_progress():
    assert "zone.bossAvailable" in WORLD_STAGE
    assert "zone.cleared || zone.stars > 0" in WORLD_STAGE
    assert "cta_boss" in WORLD_STAGE
    assert "cta_continue" in WORLD_STAGE
    assert "cta_begin" in WORLD_STAGE
    assert "+1" not in WORLD_STAGE
    assert "remaining_to_challenge" not in WORLD_STAGE
    assert "boss_exam_size" not in WORLD_STAGE


def test_sw_active_version_is_bumped_for_this_runtime_change():
    assert "v192-e9-admin-shell-activation" in SW
    assert "v190-newbie-village-mainline-clarity" not in SW


def test_synthetic_rollout_matrix_uses_server_identity_and_cleans_environment():
    app = _load_rollout_module()
    names = ("E9_ROLLOUT_GLOBAL_ENABLED", "E9_ROLLOUT_ADMIN_ENABLED", "E9_ROLLOUT_SCOPE", "E9_ROLLOUT_ALLOWLIST")
    old = {name: os.environ.get(name) for name in names}
    try:
        os.environ.update({
            "E9_ROLLOUT_GLOBAL_ENABLED": "true",
            "E9_ROLLOUT_ADMIN_ENABLED": "true",
            "E9_ROLLOUT_SCOPE": "admin_only",
            "E9_ROLLOUT_ALLOWLIST": "",
        })
        admin = app._e9_rollout_decision(user_id=101, username="synthetic-admin", is_admin=True)
        ordinary = app._e9_rollout_decision(user_id=202, username="synthetic-user", is_admin=False)
        anonymous = app._e9_rollout_decision()
        assert admin["reason"] == "admin_entitled" and admin["eligible"]
        assert ordinary["reason"] == "not_allowed" and not ordinary["eligible"]
        assert anonymous["reason"] == "unauthenticated" and not anonymous["eligible"]
        assert all(not value for value in ordinary["effective_flags"].values())
        assert all(not value for value in anonymous["effective_flags"].values())
    finally:
        for name, value in old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    assert all(name not in os.environ or os.environ[name] == old[name] for name in names)
