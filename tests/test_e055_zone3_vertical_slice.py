"""E055 contracts for the Zone 3 Goblin Cave vertical slice."""

from __future__ import annotations

import re
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adventure_zone3_monster_authority import (
    ZONE3_BINDING_SOURCE,
    ZONE3_KEY,
    ZONE3_LORD_CLASSIFICATION,
    ZONE3_LORD_ID,
    ZONE3_MONSTER_PROFILE_REGISTRY,
    ZONE3_NORMAL_IDS,
    ZONE3_PRESENTATION_ASSET_FILENAMES,
    ZONE3_PROFILE_VERSION,
    Zone3MonsterAuthorityError,
    decode_zone3_binding,
    encode_zone3_binding,
    get_zone3_binding,
    select_zone3_binding,
    zone3_combat_profile,
)

# Reuse the repository's disposable Map Battle API fixture for one bounded
# route-level proof.  The fixture is imported only for tests; it never touches
# a live database.
try:
    from test_map_battle_legacy_adapter import api_env as api_env
except ImportError:  # pragma: no cover - direct non-pytest imports
    api_env = None


def _install_app_import_stubs():
    """Keep this contract test independent of optional local integrations."""

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
        module.grimoire_bp = Blueprint("grimoire_stub_e055", __name__)
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


def test_zone3_roster_is_exact_and_lord_is_not_a_normal_entry():
    assert ZONE3_NORMAL_IDS == (
        "M022", "M023", "M024", "M025", "M026", "M027", "M028",
        "M029", "M030", "M031", "M032", "M033", "M060",
    )
    assert len(ZONE3_NORMAL_IDS) == 13
    assert len(ZONE3_MONSTER_PROFILE_REGISTRY.profiles) == 13
    assert ZONE3_LORD_ID not in ZONE3_NORMAL_IDS
    assert ZONE3_LORD_CLASSIFICATION == "LORD_ONLY"


def test_only_explicit_zone3_ids_can_resolve_or_be_selected():
    for question_id in range(1, 101):
        assert select_zone3_binding(question_id).monster_id in ZONE3_NORMAL_IDS
    assert get_zone3_binding("not-a-zone3-monster") is None
    assert get_zone3_binding("goblin_centurion") is None
    with pytest.raises(Zone3MonsterAuthorityError):
        decode_zone3_binding({
            "zone_key": ZONE3_KEY,
            "migration_source": ZONE3_BINDING_SOURCE,
            "migration_version": (
                "e055.zone3.binding.v1:forged:adventure_z3_normal_forged:"
                f"{ZONE3_PROFILE_VERSION}"
            ),
        })


def test_binding_profile_and_presentation_are_explicit_per_m_id():
    assert len(ZONE3_PRESENTATION_ASSET_FILENAMES) == 12
    for monster_id in ZONE3_NORMAL_IDS:
        binding = get_zone3_binding(monster_id)
        assert binding is not None
        assert binding.monster_id == monster_id
        assert binding.zone_key == ZONE3_KEY
        assert binding.encounter_class == "NORMAL"
        assert binding.profile_id == f"adventure_z3_normal_{monster_id}"
        assert binding.profile_version == ZONE3_PROFILE_VERSION
        assert binding.max_hp == 100
        assert binding.attack == 8
        assert binding.presentation_asset.startswith(("/assets/", "/art/monsters/"))
        profile = ZONE3_MONSTER_PROFILE_REGISTRY.by_id[monster_id]
        assert profile.monster_id == monster_id
        assert profile.zone_key == ZONE3_KEY
        assert profile.encounter_class == "NORMAL"
        assert zone3_combat_profile(binding).canonical_monster_id == monster_id


def test_m022_protected_battlefield_asset_is_not_conflated_with_legacy_id():
    binding = get_zone3_binding("M022")
    assert binding is not None
    assert binding.presentation_asset == "/assets/monsters/orc_grunt_chibi.png"
    assert binding.monster_id == "M022"
    assert binding.monster_id != "legacy_bf_03_normal"
    assert ZONE3_LORD_ID != binding.monster_id


def test_persisted_binding_round_trips_and_rejects_context_or_profile_tampering():
    binding = get_zone3_binding("M023")
    assert binding is not None
    encoded = encode_zone3_binding(binding)
    row = {
        "zone_key": ZONE3_KEY,
        "migration_source": ZONE3_BINDING_SOURCE,
        "migration_version": encoded,
    }
    assert decode_zone3_binding(row) == binding
    with pytest.raises(Zone3MonsterAuthorityError):
        decode_zone3_binding({**row, "zone_key": "k21_25"})
    with pytest.raises(Zone3MonsterAuthorityError):
        decode_zone3_binding({
            **row,
            "migration_version": encoded.replace(
                "e055.zone3.normal.v1", "e055.zone3.normal.v2"
            ),
        })
    with pytest.raises(Zone3MonsterAuthorityError):
        decode_zone3_binding({**row, "migration_source": "legacy-adventure-map"})


def test_app_uses_zone3_binding_for_combat_and_existing_settlement_writer(
    app_module, monkeypatch
):
    binding = get_zone3_binding("M022")
    assert binding is not None
    battle = {
        "id": "battle-zone3",
        "zone_key": ZONE3_KEY,
        "migration_source": ZONE3_BINDING_SOURCE,
        "migration_version": encode_zone3_binding(binding),
        "monster_hp": binding.max_hp,
        "monster_hp_max": binding.max_hp,
        "state": "OPEN",
    }
    monkeypatch.setattr(
        app_module,
        "load_authoritative_battle_state",
        lambda *args, **kwargs: battle,
    )
    profile = app_module._map_battle_monster_profile_resolver(
        object(), 101, "battle-zone3"
    )
    assert profile.canonical_monster_id == "M022"
    assert profile.profile_id == binding.profile_id
    assert profile.profile_version == ZONE3_PROFILE_VERSION

    captured = {}

    def fake_settle(conn, event, **kwargs):
        captured["event"] = event
        captured["kwargs"] = kwargs
        return "settled-by-existing-writer"

    monkeypatch.setattr(app_module, "settle_monster_defeat", fake_settle)
    result = app_module._settle_monster_defeat_in_tx(
        object(),
        101,
        battlefield={},
        settlement_id="map-battle:battle-zone3",
        hp_before=100,
        hp_after=0,
        adventure_authority=binding,
    )
    assert result == "settled-by-existing-writer"
    assert captured["event"].monster_id == "M022"
    assert captured["event"].zone_id == ZONE3_KEY
    assert captured["kwargs"]["monster_registry"] is ZONE3_MONSTER_PROFILE_REGISTRY


def test_zone3_runtime_contract_is_server_bound_and_presentation_only():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    adapter = (ROOT / "js" / "map_battle_v1_adapter.js").read_text(encoding="utf-8")
    index = (ROOT / "index.html").read_text(encoding="utf-8")

    assert "select_zone3_binding(question['id'])" in app_source
    assert "ZONE3_BINDING_SOURCE" in app_source
    assert "monster_profile_resolver=_map_battle_monster_profile_resolver" in app_source
    assert "_adventure_zone3_binding" in app_source
    assert "JOIN map_battles b" in app_source
    assert "adventure_monster" in app_source
    assert "state.adventureMonster" in adapter
    assert "state.adventureMonster" in index
    assert "^\\/art\\/monsters\\/[A-Za-z0-9._-]+\\.png$" in index
    assert "showAdventureNormalEncounterContinuation" in index
    assert "adventure.zone3.continue" in index
    assert "adventure.zone3.return_map" in index
    assert "adventure.zone3.encounter_complete" in index
    assert "'monster_id'" in app_source
    assert "forged_fields" in app_source
    assert "_map_battle_f010_profile" in app_source


def test_zone3_art_route_is_allowlisted_and_bilingual_copy_exists(app_module):
    client = app_module.app.test_client()
    allowed = client.get("/art/monsters/M023_coppercap_goblin.png")
    assert allowed.status_code == 200
    assert allowed.mimetype == "image/png"
    assert client.get("/art/monsters/not-allowlisted.png").status_code == 404

    i18n = (ROOT / "i18n.js").read_text(encoding="utf-8")
    for key in (
        "adventure.zone3.encounter_title",
        "adventure.zone3.encounter_objective",
        "adventure.zone3.continue",
        "adventure.zone3.return_map",
        "adventure.zone3.encounter_complete",
    ):
        match = re.search(rf"'{re.escape(key)}'\s*:\s*\{{[^\n]+", i18n)
        assert match, key
        assert "en:" in match.group(0) and "zh:" in match.group(0)


@pytest.mark.skipif(api_env is None, reason="shared disposable API fixture unavailable")
def test_zone3_prepare_uses_server_binding_and_rejects_forged_identity(
    api_env, monkeypatch
):
    client, conn = api_env
    import app as app_module

    question = {
        "id": 7301,
        "source": "e055/zone3-fixture.sgf",
        "content": "(;SZ[19];B[dd];W[ee])",
        "accepted_moves": [{"x": 3, "y": 3}],
        "topic": "5哥布林洞穴",
        "monster_type": "goblin",
    }
    monkeypatch.setattr(app_module, "_load_questions", lambda: [question])
    monkeypatch.setattr(
        app_module,
        "_questions_for_adventure_zone",
        lambda questions, zone, premium=True: (
            list(questions) if zone["key"] == ZONE3_KEY else []
        ),
    )

    response = client.post(
        "/api/adventure/map-battles/v1/attempts",
        json={"zone_key": ZONE3_KEY, "question_id": question["id"]},
        headers={"X-Map-Battle-Client-Protocol": "v1"},
    )
    assert response.status_code == 200, response.get_json()
    payload = response.get_json()
    presentation = payload["battle"]["adventure_monster"]
    assert presentation["monster_id"] in ZONE3_NORMAL_IDS
    assert presentation["zone_key"] == ZONE3_KEY
    assert presentation["encounter_class"] == "NORMAL"
    stored = dict(conn.execute(
        "SELECT * FROM map_battles WHERE id=?", (payload["battle_id"],)
    ).fetchone())
    assert stored["migration_source"] == ZONE3_BINDING_SOURCE
    assert stored["migration_version"].startswith("e055.zone3.binding.v1:")
    assert stored["monster_hp_max"] == 100

    forged = client.post(
        "/api/adventure/map-battles/v1/attempts",
        json={
            "zone_key": ZONE3_KEY,
            "question_id": question["id"],
            "monster_id": "M999",
        },
        headers={"X-Map-Battle-Client-Protocol": "v1"},
    )
    assert forged.status_code == 400
    assert "server-owned" in forged.get_json()["message"]

    answer = client.post(
        "/api/adventure/map-battles/v1/answers",
        json={
            "battle_id": payload["battle_id"],
            "attempt_id": payload["attempt_id"],
            "submission_nonce": payload["submission_nonce"],
            "battle_revision": payload["battle"]["battle_revision"],
            "question_revision": payload["question_revision"],
            "player_color": payload["player_color"],
            "transform_id": payload["transform_id"],
            "transform_version": payload["transform_version"],
            "moves": [{"x": 3, "y": 3}],
        },
        headers={"X-Map-Battle-Client-Protocol": "v1"},
    )
    assert answer.status_code == 200, answer.get_json()
    answer_payload = answer.get_json()
    assert answer_payload["result"] == "CORRECT"
    assert answer_payload["adventure_monster"]["monster_id"] == presentation["monster_id"]
    assert answer_payload["adventure_monster"]["hp"] < presentation["max_hp"]
