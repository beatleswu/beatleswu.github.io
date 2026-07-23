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
    import app
    return app


def test_newbie_panel_is_owned_by_world_stage_and_uses_canonical_identity():
    assert 'id="e9-newbie-mainline"' in WORLD_MARKUP
    assert "function renderBeginnerVillageMainline(root, zone)" in WORLD_STAGE
    assert "zone.key !== 'k26_30'" in WORLD_STAGE
    assert "renderSelectedZone(root, zones, zone.key, true)" in WORLD_STAGE
    assert 'id="e9-world-stage-details"' in WORLD_MARKUP
    assert 'aria-pressed' in WORLD_STAGE
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
    assert "v202-e9-component-loader-timeout-fix" in SW
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


def test_named_allowlist_matches_canonical_user_id_not_username(monkeypatch):
    # Real runtime proof (not just a source-string check) that the E9 Phase 1
    # identity fix behaves correctly: allowlist membership is decided by
    # user_id, is independent of username, and a non-numeric/mismatched
    # username on an allowlisted ID does not block eligibility, while an
    # allowlisted username string (the old, incorrect model) does NOT grant
    # access on its own.
    app = _load_rollout_module()
    monkeypatch.setenv("E9_ROLLOUT_GLOBAL_ENABLED", "true")
    monkeypatch.setenv("E9_ROLLOUT_ADMIN_ENABLED", "false")
    monkeypatch.setenv("E9_ROLLOUT_SCOPE", "named_allowlist")
    monkeypatch.setenv("E9_ROLLOUT_ALLOWLIST", "7,42,100")

    allowlisted = app._e9_rollout_decision(user_id=42, username="totally-unrelated-display-name", is_admin=False)
    assert allowlisted["reason"] == "named_allowlist" and allowlisted["eligible"]

    not_allowlisted = app._e9_rollout_decision(user_id=999, username="also-not-on-the-list", is_admin=False)
    assert not_allowlisted["reason"] == "not_allowed" and not not_allowlisted["eligible"]

    # The literal string "42" would also happen to be a substring match if the
    # implementation still matched on username -- confirm a user whose
    # USERNAME happens to equal an allowlisted ID string, but whose user_id
    # does not, is correctly rejected (proves there is no username-based path
    # remaining, not just that a differently-named user is rejected).
    username_collision = app._e9_rollout_decision(user_id=999, username="42", is_admin=False)
    assert username_collision["reason"] == "not_allowed" and not username_collision["eligible"]

    admin_bypass_alongside_allowlist = app._e9_rollout_decision(user_id=999, username="admin-user", is_admin=True)
    assert admin_bypass_alongside_allowlist["reason"] == "not_allowed" and not admin_bypass_alongside_allowlist["eligible"]
    # admin_enabled is false above, so is_admin alone must not grant entry --
    # confirms admin_entitled and named_allowlist are independently gated, not
    # silently coupled.


def test_invalid_rollout_config_fails_closed_for_everyone_including_admins(monkeypatch):
    # Task book WI-4 eligibility matrix, row 5: a malformed rollout config
    # must fail closed to invalid_config for EVERY caller, including admins --
    # distinct from global_disabled (which is a valid config that is simply
    # turned off) and distinct from not_allowed (a valid config that just
    # doesn't cover this user). Covers all three ways _e9_rollout_config()
    # can return None: bad scope, bad allowlist format, bad flags.
    app = _load_rollout_module()
    base_env = {
        "E9_ROLLOUT_GLOBAL_ENABLED": "true",
        "E9_ROLLOUT_ADMIN_ENABLED": "true",
        "E9_ROLLOUT_SCOPE": "named_allowlist",
        "E9_ROLLOUT_ALLOWLIST": "7,42",
        "E9_ROLLOUT_FLAGS": "e9Shell,e9TopHud,e9LeftNav,e9RightCards,e9BottomDock,e9WorldStage",
    }

    def apply(overrides):
        for key, value in {**base_env, **overrides}.items():
            monkeypatch.setenv(key, value)

    malformed_configs = {
        "bad_scope": {"E9_ROLLOUT_SCOPE": "public"},
        "bad_allowlist_format": {"E9_ROLLOUT_ALLOWLIST": "007"},
        "bad_allowlist_duplicate": {"E9_ROLLOUT_ALLOWLIST": "7,7"},
        "bad_flags": {"E9_ROLLOUT_FLAGS": "e9Shell,not_a_real_flag"},
        "flags_missing_e9shell": {"E9_ROLLOUT_FLAGS": "e9TopHud,e9LeftNav"},
    }
    for label, overrides in malformed_configs.items():
        apply(overrides)
        for is_admin in (True, False):
            decision = app._e9_rollout_decision(user_id=42, username="someone", is_admin=is_admin)
            assert decision["reason"] == "invalid_config", (label, is_admin, decision)
            assert decision["eligible"] is False, (label, is_admin, decision)
            assert all(not value for value in decision["effective_flags"].values()), (label, is_admin, decision)
            # invalid_config must never be confused with a merely-off valid
            # config -- kill_switch is a separate, coarser signal, but the
            # reason code itself is the one WI-4 requires kept distinct.
            assert decision["reason"] != "global_disabled", (label, is_admin, decision)


def test_authenticated_request_with_no_resolvable_user_id_never_matches_or_admin_bypasses(monkeypatch):
    # Task book WI-4 eligibility matrix, row 6: an "authenticated" caller (a
    # session/is_admin flag may be present) but with no resolvable canonical
    # user_id must fail closed -- never named_allowlist, never admin_entitled,
    # regardless of is_admin. This is a distinct security property from row 4
    # (a genuinely logged-out visitor): here is_admin=True is passed
    # deliberately to prove a missing user_id cannot be overridden by an
    # admin flag on the same call.
    app = _load_rollout_module()
    monkeypatch.setenv("E9_ROLLOUT_GLOBAL_ENABLED", "true")
    monkeypatch.setenv("E9_ROLLOUT_ADMIN_ENABLED", "true")
    monkeypatch.setenv("E9_ROLLOUT_SCOPE", "named_allowlist")
    monkeypatch.setenv("E9_ROLLOUT_ALLOWLIST", "7,42")

    for missing_user_id in (None, 0, ""):
        decision = app._e9_rollout_decision(user_id=missing_user_id, username="admin-with-no-id", is_admin=True)
        assert decision["reason"] == "unauthenticated", (missing_user_id, decision)
        assert decision["reason"] != "named_allowlist", (missing_user_id, decision)
        assert decision["reason"] != "admin_entitled", (missing_user_id, decision)
        assert decision["eligible"] is False, (missing_user_id, decision)
        assert all(not value for value in decision["effective_flags"].values()), (missing_user_id, decision)

    # Symmetric check: a resolvable user_id but no resolvable username must
    # also fail closed the same way, not fall through to some other path.
    decision = app._e9_rollout_decision(user_id=42, username="", is_admin=True)
    assert decision["reason"] == "unauthenticated"
    assert decision["eligible"] is False
