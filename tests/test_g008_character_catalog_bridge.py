"""Local, disposable acceptance for the G008 Future30 catalog bridge."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from future30_character_registry import (
    FUTURE30_CHARACTER_KEY_ORDER,
    FUTURE30_C005_MANIFEST_SHA256,
    FUTURE30_PRODUCT_MANIFEST_SHA256,
    future30_registry_diagnostics,
)
from future30_character_service import (
    Future30AcquisitionRejected,
    Future30CatalogUnavailable,
    Future30CharacterNotEntitled,
    Future30UnknownCharacter,
    apply_future30_character,
    catalog_payload,
    ensure_future30_catalog,
    grant_future30_character,
    initialize_future30_catalog,
    list_future30_entitlements,
    project_applied_character,
)
from migrations.future30_character_catalog_v1 import (
    ACQUISITION_SOURCES,
    CATALOG_TABLE,
    ENTITLEMENT_TABLE,
    VISUAL_TABLE,
    upgrade,
    validate_schema,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_KEYS = (
    "A1", "A3", "V1", "V2", "V3", "R1", "R2", "R3", "H1", "H2",
    "H3", "K1", "K2", "K3", "W1", "W2", "W3", "M1", "M2", "S1",
    "S2", "F1", "F2", "F3", "AR1", "AR2", "AR3", "E1", "E2", "E3",
)


@pytest.fixture
def isolated_db():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE)")
    connection.execute("INSERT INTO users(id, username) VALUES(17, 'bridge-test')")
    connection.execute(
        """CREATE TABLE player_appearance(
               user_id INTEGER PRIMARY KEY,
               character_key TEXT,
               updated_at TEXT
           )"""
    )
    yield connection
    connection.close()


def test_owner_bound_future30_has_exact_30_logical_and_33_visual_mappings():
    diagnostic = future30_registry_diagnostics()
    assert diagnostic["valid"] is True
    assert diagnostic["logical_count"] == 30
    assert diagnostic["visual_count"] == 33
    assert diagnostic["manifest_sha256"] == FUTURE30_C005_MANIFEST_SHA256
    assert diagnostic["product_manifest_sha256"] == FUTURE30_PRODUCT_MANIFEST_SHA256
    assert FUTURE30_CHARACTER_KEY_ORDER == EXPECTED_KEYS

    manifest = json.loads(
        (ROOT / "schemas/future30_c005_real_asset_runtime_mapping_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(manifest["roster"]) == 30
    assert len(manifest["visual_models"]) == 33
    assert manifest["counts"]["variant_model_counts"] == {"RED": 30, "BLUE": 3}
    blue_keys = []
    for row in manifest["visual_models"]:
        path = ROOT / row["runtime_glb"].lstrip("/")
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["runtime_sha256"]
        if row["variant"] == "BLUE":
            blue_keys.append(row["character_id"])
    assert blue_keys == ["AR1", "AR2", "AR3"]


def test_migration_is_additive_idempotent_and_validates_exact_schema(isolated_db):
    first = upgrade(isolated_db)
    second = upgrade(isolated_db)
    assert first["valid"] is True
    assert set(first["created"]) == {CATALOG_TABLE, VISUAL_TABLE, ENTITLEMENT_TABLE}
    assert second["valid"] is True
    assert second["created"] == []
    assert validate_schema(isolated_db)["acquisition_sources"] == list(ACQUISITION_SOURCES)

    seeded = initialize_future30_catalog(isolated_db)
    assert seeded["logical_count"] == 30
    assert seeded["visual_count"] == 33
    assert seeded["character_keys"] == list(EXPECTED_KEYS)
    assert ensure_future30_catalog(isolated_db)["c005_manifest_sha256"] == FUTURE30_C005_MANIFEST_SHA256
    assert isolated_db.execute(f"SELECT COUNT(*) FROM {CATALOG_TABLE}").fetchone()[0] == 30
    assert isolated_db.execute(f"SELECT COUNT(*) FROM {VISUAL_TABLE}").fetchone()[0] == 33
    assert isolated_db.execute(f"SELECT COUNT(*) FROM {ENTITLEMENT_TABLE}").fetchone()[0] == 0

    payload = catalog_payload(isolated_db)
    assert [entry["character_key"] for entry in payload["entries"]] == list(EXPECTED_KEYS)
    assert all(entry["default_variant"] == "RED" for entry in payload["entries"])
    assert all(entry["acquisition_group"] is None for entry in payload["entries"])
    assert sum(len(entry["visual_models"]) for entry in payload["entries"]) == 33
    assert all(len(entry["visual_models"]) == (2 if entry["character_key"] in {"AR1", "AR2", "AR3"} else 1) for entry in payload["entries"])
    blue_visuals = [
        visual
        for entry in payload["entries"]
        for visual in entry["visual_models"]
        if visual["variant"] == "BLUE"
    ]
    assert [visual["character_key"] for visual in blue_visuals] == ["AR1", "AR2", "AR3"]
    assert payload["acquisition_allocation"] == [
        {"source": "STARTER", "count": 5, "assignment_status": "UNASSIGNED"},
        {"source": "STAGE", "count": 10, "assignment_status": "UNASSIGNED"},
        {"source": "PREMIUM", "count": 5, "assignment_status": "UNASSIGNED"},
        {"source": "SHOP", "count": 10, "assignment_status": "UNASSIGNED"},
    ]


def test_persistent_entitlement_is_unique_idempotent_and_required_for_apply(isolated_db):
    initialize_future30_catalog(isolated_db)
    with pytest.raises(Future30CharacterNotEntitled):
        apply_future30_character(isolated_db, 17, "A1")
    with pytest.raises(Future30UnknownCharacter):
        grant_future30_character(
            isolated_db, 17, "A31", "ACCEPTANCE_TEST",
            environment="acceptance", allow_acceptance_test=True,
        )

    first = grant_future30_character(
        isolated_db, 17, "A1", "ACCEPTANCE_TEST",
        environment="acceptance", allow_acceptance_test=True,
        source_reference="isolated-event-1",
    )
    duplicate = grant_future30_character(
        isolated_db, 17, "A1", "ACCEPTANCE_TEST",
        environment="acceptance", allow_acceptance_test=True,
        source_reference="isolated-event-1",
    )
    conflicting_source = grant_future30_character(
        isolated_db, 17, "A1", "SHOP",
        environment="acceptance", source_reference="different-event",
    )
    assert first["created"] is True
    assert duplicate["created"] is False
    assert conflicting_source["created"] is False
    assert conflicting_source["acquisition_source"] == "ACCEPTANCE_TEST"
    assert isolated_db.execute(
        f"SELECT COUNT(*) FROM {ENTITLEMENT_TABLE} WHERE user_id=17 AND character_key='A1'"
    ).fetchone()[0] == 1

    assert list_future30_entitlements(isolated_db, 17) == []
    assert list_future30_entitlements(isolated_db, 17, allow_acceptance_test=True)[0][
        "acquisition_source"
    ] == "ACCEPTANCE_TEST"
    with pytest.raises(Future30CharacterNotEntitled):
        apply_future30_character(isolated_db, 17, "A1")

    applied = apply_future30_character(
        isolated_db, 17, "A1", allow_acceptance_test=True
    )
    assert applied["character_key"] == "A1"
    assert applied["character_key_source"] == "player_appearance.character_key"
    assert applied["entitlement_source"] == "ACCEPTANCE_TEST"
    assert applied["permanent"] is True
    assert isolated_db.execute(
        "SELECT character_key FROM player_appearance WHERE user_id=17"
    ).fetchone()[0] == "A1"
    projection = project_applied_character(isolated_db, 17, "A1", allow_acceptance_test=True)
    assert projection["entitled"] is True
    assert projection["runtime"]["runtime_sha256"]


def test_acceptance_source_isolation_and_premium_ownership_do_not_depend_on_membership(isolated_db):
    initialize_future30_catalog(isolated_db)
    with pytest.raises(Future30AcquisitionRejected):
        grant_future30_character(
            isolated_db, 17, "A3", "ACCEPTANCE_TEST",
            environment="production", allow_acceptance_test=True,
        )
    with pytest.raises(Future30AcquisitionRejected):
        grant_future30_character(
            isolated_db, 17, "A3", "ACCEPTANCE_TEST",
            environment="acceptance", allow_acceptance_test=False,
        )

    premium = grant_future30_character(
        isolated_db, 17, "A3", "PREMIUM", environment="acceptance"
    )
    assert premium["permanent"] is True
    # Selection checks the durable entitlement only; it does not consult
    # current subscription status, so later Premium expiry does not re-lock.
    applied_after_membership_expiry = apply_future30_character(isolated_db, 17, "A3")
    assert applied_after_membership_expiry["character_key"] == "A3"
    assert applied_after_membership_expiry["entitlement_source"] == "PREMIUM"


def test_catalog_drift_fails_closed_without_rewriting_frozen_mapping(isolated_db):
    initialize_future30_catalog(isolated_db)
    isolated_db.execute(
        f"UPDATE {CATALOG_TABLE} SET runtime_glb='assets/not-the-canonical-file.glb' "
        "WHERE character_key='A1'"
    )
    with pytest.raises(Future30CatalogUnavailable):
        ensure_future30_catalog(isolated_db)
    assert isolated_db.execute(
        f"SELECT runtime_glb FROM {CATALOG_TABLE} WHERE character_key='A1'"
    ).fetchone()[0] == "assets/not-the-canonical-file.glb"


def test_acceptance_test_grant_is_non_http_explicitly_gated_and_one_key_at_a_time(tmp_path, monkeypatch):
    import os

    os.environ.setdefault("SECRET_KEY", "g008-bridge-cli-test-secret")
    import app as app_module

    db_path = tmp_path / "future30-cli.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT NOT NULL)")
        connection.execute("INSERT INTO users(id, username) VALUES(17, 'bridge-cli-test')")
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
    monkeypatch.setitem(app_module.app.config, "APP_ENV", "acceptance")
    monkeypatch.setitem(app_module.app.config, "FUTURE30_ACCEPTANCE_ENTITLEMENTS_ENABLED", False)
    runner = app_module.app.test_cli_runner()
    args = ["grant-future30-acceptance-character", "--user-id", "17", "--character-key", "A1"]
    disabled = runner.invoke(args=args)
    assert disabled.exit_code != 0
    assert "disabled" in disabled.output
    with sqlite3.connect(db_path) as connection:
        assert connection.execute(f"SELECT COUNT(*) FROM {ENTITLEMENT_TABLE}").fetchone()[0] == 0

    monkeypatch.setitem(app_module.app.config, "FUTURE30_ACCEPTANCE_ENTITLEMENTS_ENABLED", True)
    granted = runner.invoke(args=args)
    assert granted.exit_code == 0
    assert '"created": true' in granted.output
    repeated = runner.invoke(args=args)
    assert repeated.exit_code == 0
    assert '"created": false' in repeated.output
    assert not any(
        "future30" in str(rule.rule).lower() and "grant" in str(rule.rule).lower()
        for rule in app_module.app.url_map.iter_rules()
    )
    with sqlite3.connect(db_path) as connection:
        assert connection.execute(f"SELECT COUNT(*) FROM {ENTITLEMENT_TABLE}").fetchone()[0] == 1
