"""D007 read-only contract checks for Future30 admission and formal Hero wiring."""

import json
import os
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def source(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def test_canonical_future30_registry_is_exactly_30_logical_and_33_visual():
    manifest = load_json("schemas/future30_c005_real_asset_runtime_mapping_manifest.json")
    roster = manifest["roster"]
    visuals = manifest["visual_models"]
    keys = [entry["character_id"] for entry in roster]
    visual_ids = [entry["visual_model_id"] for entry in visuals]

    assert manifest["counts"] == {
        "logical_character_count": 30,
        "visual_model_count": 33,
        "variant_model_counts": {"RED": 30, "BLUE": 3},
    }
    assert len(keys) == len(set(keys)) == 30
    assert len(visual_ids) == len(set(visual_ids)) == 33
    assert all(entry["admission_state"] == "ENABLED" for entry in roster)
    assert all(entry["asset_status"] == "PRESENT" for entry in visuals)
    assert all(entry["placeholder_mapping"] is False for entry in visuals)
    for entry in visuals:
        assert (ROOT / entry["runtime_glb"].lstrip("/")).is_file()


def test_server_admission_uses_manifest_and_preserves_legacy_fallback():
    app = source("app.py")
    registry = source("future30_character_registry.py")

    assert "from future30_character_registry import" in app
    assert "FUTURE30_CHARACTER_KEYS" in app
    assert "is_future30_character_key" in app
    assert "VALID_CHARACTER_KEYS" in app
    assert "ACTIVE_CHARACTER_KEYS" in app
    assert "PRESERVE_KEY_WITH_EXISTING_2D_FALLBACK" in app
    assert "no legacy key is guessed into A1...E3" in app
    assert "asset_id" not in app[app.index("def _presentation_character_key"):app.index("@app.route('/api/skills/character'")]
    assert "FUTURE30_EXPECTED_LOGICAL_COUNT = 30" in registry
    assert "FUTURE30_EXPECTED_VISUAL_COUNT = 33" in registry


def test_formal_host_and_f009_contract_are_explicit_and_bounded():
    runtime = source("js/formal_3d_character_equipment_runtime.js")
    adapter = source("js/player_appearance_3d_attachment_adapter.js")
    schema = load_json("schemas/formal_3d_character_equipment_v1.json")

    for slot in ("CHARACTER_ROOT", "MAIN_HAND", "OFF_HAND", "HEAD", "BACK", "AURA", "PET_COMPANION"):
        assert f'  {slot}:' in runtime
    assert "hand.R" in runtime and "hand.L" in runtime
    assert "swapCharacter" in runtime
    assert "clearAttachmentHost" in runtime
    assert "setCompanion" in runtime
    assert "PLAYER_APPEARANCE_3D_ATTACHMENT_CONTRACT" in runtime
    assert "createPlayerAppearance3DAttachmentAdapter" in runtime
    assert "TWO_HANDED" in runtime
    assert "POLEARM" in runtime
    assert schema["shared_preview_contract"]["asset_identity"] == "asset_id"
    assert schema["shared_preview_contract"]["mount_api"] == "mountShared3DPreview(container, payload)"
    assert "renderServerSnapshot" in adapter
    assert "previewAura" in adapter
    assert "cancelPreview" in adapter
    assert "preview_mutates_ownership: false" in adapter
    assert "runtime must not call fetch" not in adapter


def test_authenticated_hero_passes_server_snapshot_to_formal_runtime():
    hero = source("hero.html")
    assert 'fetch("/api/player/appearance"' in hero
    assert "...appearance" in hero
    assert "character_key: appearance?.character_key || null" in hero
    assert "mountFormal3DFromHero" in hero
    assert "player_appearance.character_key" in hero or "server-provided character_key" in hero
    assert "formal_3d_authority" in hero
    assert ".fullbody-generated-avatar[hidden]" in hero


def test_appearance_read_model_declares_existing_wardrobe_ownership():
    app = source("app.py")
    appearance_start = app.index("def get_appearance():")
    appearance_end = app.index("@app.route('/api/player/appearance/equip'")
    projection = app[appearance_start:appearance_end]
    assert "'owned':          True" in projection
    assert "player_wardrobe" in projection
    assert "player_appearance.character_key" in projection


def test_real_character_route_requires_persistent_ownership_and_rejects_unknown(tmp_path, monkeypatch):
    # Exercise real routes against a throwaway SQLite fixture only.  Catalog
    # admission does not itself grant ownership or mutate appearance.
    os.environ.setdefault("SECRET_KEY", "d007-future30-route-test-secret")
    import app as app_module
    from future30_character_service import grant_future30_character, initialize_future30_catalog

    db_path = tmp_path / "future30-admission.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT NOT NULL)")
        connection.execute("INSERT INTO users(id, username) VALUES(7, 'd007-admission')")
        connection.execute(
            "CREATE TABLE player_appearance(user_id INTEGER PRIMARY KEY, character_key TEXT, updated_at TEXT)"
        )
        initialize_future30_catalog(connection)
        connection.commit()

    class DbContext:
        def __enter__(self):
            self.connection = sqlite3.connect(db_path)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA foreign_keys=ON")
            return self.connection

        def __exit__(self, exc_type, exc, tb):
            if exc_type is None:
                self.connection.commit()
            else:
                self.connection.rollback()
            self.connection.close()

    monkeypatch.setattr(app_module, "get_db", lambda: DbContext())
    monkeypatch.setattr(app_module, "is_premium", lambda _uid: False)
    monkeypatch.setattr(
        app_module,
        "_compute_title_metrics",
        lambda *_args, **_kwargs: {"go_rank": "30k", "units_done": 0, "total_correct": 0},
    )
    app_module.app.config.update(TESTING=True)
    monkeypatch.setitem(app_module.app.config, "APP_ENV", "acceptance")
    monkeypatch.setitem(app_module.app.config, "FUTURE30_ACCEPTANCE_ENTITLEMENTS_ENABLED", False)
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7
        session["username"] = "d007-admission"

    unowned = client.post("/api/skills/character", json={"character_key": "A1"})
    assert unowned.status_code == 403
    assert unowned.get_json()["error"] == "FUTURE30_CHARACTER_NOT_ENTITLED"
    with sqlite3.connect(db_path) as connection:
        assert connection.execute(
            "SELECT character_key FROM player_appearance WHERE user_id=7"
        ).fetchone() is None

    rejected = client.post("/api/skills/character", json={"character_key": "A31"})
    assert rejected.status_code == 400

    catalog = client.get("/api/player/character-catalog")
    assert catalog.status_code == 200
    catalog_json = catalog.get_json()
    assert catalog_json["logical_count"] == 30
    assert catalog_json["visual_count"] == 33
    assert [entry["character_key"] for entry in catalog_json["entries"]] == [
        "A1", "A3", "V1", "V2", "V3", "R1", "R2", "R3", "H1", "H2",
        "H3", "K1", "K2", "K3", "W1", "W2", "W3", "M1", "M2", "S1",
        "S2", "F1", "F2", "F3", "AR1", "AR2", "AR3", "E1", "E2", "E3",
    ]
    assert all(not entry["owned"] for entry in catalog_json["entries"])
    assert all(entry["acquisition_group_status"] == "UNASSIGNED" for entry in catalog_json["entries"])

    with DbContext() as connection:
        granted = grant_future30_character(
            connection,
            7,
            "A1",
            "ACCEPTANCE_TEST",
            environment="acceptance",
            allow_acceptance_test=True,
            source_reference="isolated-test",
        )
        assert granted["created"] is True
        connection.commit()

    # ACCEPTANCE_TEST ownership is hidden/ineffective until the isolated-only
    # switch is explicitly enabled; the same frozen route then applies it.
    still_unavailable = client.post("/api/skills/character", json={"character_key": "A1"})
    assert still_unavailable.status_code == 403
    monkeypatch.setitem(app_module.app.config, "FUTURE30_ACCEPTANCE_ENTITLEMENTS_ENABLED", True)
    accepted = client.post("/api/skills/character", json={"character_key": "A1"})
    assert accepted.status_code == 200
    assert accepted.get_json()["rejected"] == []
    with sqlite3.connect(db_path) as connection:
        assert connection.execute(
            "SELECT character_key FROM player_appearance WHERE user_id=7"
        ).fetchone()[0] == "A1"

    appearance = client.get("/api/player/character-catalog").get_json()
    owned_a1 = next(entry for entry in appearance["entries"] if entry["character_key"] == "A1")
    assert owned_a1["owned"] is True
    assert owned_a1["acquisition_source"] == "ACCEPTANCE_TEST"
    assert owned_a1["permanent"] is True
    assert owned_a1["is_applied"] is True

    legacy_alias = client.post("/api/skills/character", json={"character_key": "hero_male"})
    assert legacy_alias.status_code == 200
    assert "character" in legacy_alias.get_json()["rejected"]
    with sqlite3.connect(db_path) as connection:
        assert connection.execute(
            "SELECT character_key FROM player_appearance WHERE user_id=7"
        ).fetchone()[0] == "A1"
