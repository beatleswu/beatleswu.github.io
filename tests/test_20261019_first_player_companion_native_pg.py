"""First-player Companion choice: real Flask, PostgreSQL and governed schema.

Proves the fail-closed 503 on the disposable pre-migration environment, then
explicitly applies *only there* the reviewed B023 operations/evolution additive
migrations. No production migration or app.init_db() policy change.
"""
from __future__ import annotations

import pytest
from test_20261019_adventure_answer_level_e2e import journey, UID
from test_20261019_monthly_postgres import local_postgres, runtime as native_runtime
from migrations.companion_operations_v1 import (
    upgrade as upgrade_companion_operations,
    validate_schema as validate_companion_operations,
)
from migrations.spirit_evolution_events_v1 import (
    upgrade as upgrade_evolution_events,
    validate_schema as validate_evolution_events,
)


def _row(conn, sql, args=()):
    return conn.execute(sql, args).fetchone()


def test_new_player_spirit_schema_missing_fails_closed_then_governed_migration_allows_choice(journey):
    app, client = journey
    with app.get_db() as conn:
        observed = validate_companion_operations(conn)
        assert observed["present"] is False
        assert observed["missing"] == ["companion_operations"]
        assert _row(conn, "SELECT COUNT(*) AS n FROM user_pets WHERE user_id=?", (UID,))["n"] == 0

    # The original first-player flow failed in the earlier browser E2E exactly
    # here. This is a legitimate refusal, not a reason to bypass the guard.
    denied = client.post(
        "/api/pet/choose",
        json={"pet_key": app.PET_STARTER_KEY, "operation_id": "p1-before-migration"},
    )
    assert denied.status_code == 503, denied.get_json()
    assert denied.get_json()["code"] == "COMPANION_OPERATION_SCHEMA_UNAVAILABLE"
    with app.get_db() as conn:
        assert _row(conn, "SELECT COUNT(*) AS n FROM user_pets WHERE user_id=?", (UID,))["n"] == 0
        assert validate_companion_operations(conn)["present"] is False

    # Controlled operation in the disposable PG cluster only. These migrations
    # intentionally are not part of generic init_db() and should not be added
    # there without an independent production release decision.
    with app.get_db() as conn:
        first = upgrade_companion_operations(conn)
        evolution = upgrade_evolution_events(conn)
        second = upgrade_companion_operations(conn)
        assert first["created"] == ["companion_operations"]
        assert second["created"] == []
        assert evolution["present"] is True
        assert validate_companion_operations(conn)["missing"] == []
        assert validate_evolution_events(conn)["missing"] == []

    payload = {"pet_key": app.PET_STARTER_KEY, "operation_id": "p1-governed-spirit-choice"}
    chosen = client.post("/api/pet/choose", json=payload)
    assert chosen.status_code == 200, chosen.get_json()
    body = chosen.get_json()
    assert body["ok"] is True and body["pet"]["pet_key"] == app.PET_STARTER_KEY
    assert body["operation_id"] == payload["operation_id"]

    replay = client.post("/api/pet/choose", json=payload)
    assert replay.status_code == 200, replay.get_json()
    assert replay.get_json() == body
    conflicted = client.post("/api/pet/choose", json={
        "pet_key": next(key for key in app.PET_CATALOG if key != app.PET_STARTER_KEY),
        "operation_id": payload["operation_id"],
    })
    assert conflicted.status_code == 409, conflicted.get_json()
    assert conflicted.get_json()["code"] == "COMPANION_OPERATION_CONFLICT"
    different_id = client.post("/api/pet/choose", json={
        "pet_key": app.PET_STARTER_KEY, "operation_id": "p1-second-unlock-forbidden",
    })
    assert different_id.status_code == 409, different_id.get_json()

    displayed = client.get("/api/pet/status")
    assert displayed.status_code == 200
    assert displayed.get_json()["pet"]["pet_key"] == app.PET_STARTER_KEY

    with app.get_db() as conn:
        pets = _row(conn, "SELECT COUNT(*) AS n FROM user_pets WHERE user_id=?", (UID,))["n"]
        operations = conn.execute(
            "SELECT operation_id,status FROM companion_operations WHERE user_id=? ORDER BY operation_id",
            (UID,),
        ).fetchall()
        candy = _row(conn, "SELECT qty FROM pet_inventory WHERE user_id=? AND item_key=?",
                     (UID, "go_spirit_candy"))
        fruit = _row(conn, "SELECT qty FROM pet_inventory WHERE user_id=? AND item_key=?",
                     (UID, "starfruit"))
        lineage = conn.execute(
            "SELECT idempotency_key FROM domain_event_outbox "
            "WHERE idempotency_key LIKE ?",
            ("spirit-reward:p1-governed-spirit-choice:%",),
        ).fetchall()
    assert pets == 1
    assert candy and candy["qty"] == 6
    assert fruit and fruit["qty"] == 1
    assert len(lineage) == 2
    assert len(operations) == 2, operations  # completed + expected business rejection
    assert {row["status"] for row in operations} == {"COMPLETED", "FAILED"}
    print("P1_COMPANION_MIGRATION_DIAGNOSTIC", {
        "before": "503_COMPANION_OPERATION_SCHEMA_UNAVAILABLE",
        "after": "200_REAL_SPIRIT_SELECTED_PERSISTED",
        "replay": "200_SAME_RESULT",
        "alternate_request": "409_DENIED",
        "source": "explicit_isolated_governed_migration",
        "production_mutated": False,
    })
