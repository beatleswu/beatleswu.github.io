"""Single-authority contract for the canonical Loadout capability.

Forensic GO_ODYSSEY_PLAYER_EQUIPMENT_ENTITLEMENT_LOCK_REGRESSION_FORENSIC_001
found the UI keeping its own hard-coded copy of the Loadout gate
(``FUNCTIONAL_EQUIPMENT_LOADOUT_ENABLED = false``) while the server owned the
real one. Two independent authorities means enabling the server flag alone
would not restore player access, and the two can silently drift.

These tests pin the replacement contract: the server projects a read-only
capability, the client reads only that, and the capability tracks exactly the
same flag the write path enforces. The client must fail closed when the
capability is absent, unreadable, or falsy.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("SECRET_KEY", "canonical-loadout-capability-test-secret")
import app as app_module  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_HTML = ROOT / "inventory.html"
CAPABILITY_KEY = "equipment_loadout_enabled"


# ── server capability tracks the enforced flag ───────────────────────────────

@pytest.mark.parametrize(
    "raw,expected",
    [(None, False), ("", False), ("0", False), ("false", False), ("1", True)],
)
def test_capability_tracks_the_enforced_server_flag(monkeypatch, raw, expected):
    """The projected capability must equal the flag the write path enforces."""
    if raw is None:
        monkeypatch.delenv(app_module.EQUIPMENT_CANONICAL_LOADOUT_FLAG, raising=False)
    else:
        monkeypatch.setenv(app_module.EQUIPMENT_CANONICAL_LOADOUT_FLAG, raw)
    assert app_module._equipment_canonical_loadout_enabled() is expected


def test_capability_defaults_closed_with_no_environment(monkeypatch):
    monkeypatch.delenv(app_module.EQUIPMENT_CANONICAL_LOADOUT_FLAG, raising=False)
    assert app_module._equipment_canonical_loadout_enabled() is False


def test_auth_me_projects_the_capability_from_the_enforced_flag():
    """/api/auth/me must publish the capability, bound to the same function."""
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    match = re.search(
        r"'%s':\s*(.+?),\s*\n" % CAPABILITY_KEY, source
    )
    assert match, "/api/auth/me does not project the Loadout capability"
    assert "_equipment_canonical_loadout_enabled()" in match.group(1), (
        "capability must be derived from the enforced flag, not a literal"
    )


# ── the client keeps no second authority ─────────────────────────────────────

def test_client_no_longer_hardcodes_a_second_gate():
    html = INVENTORY_HTML.read_text(encoding="utf-8")
    assert "FUNCTIONAL_EQUIPMENT_LOADOUT_ENABLED" not in html, (
        "inventory.html still carries its own hard-coded Loadout gate"
    )


def test_client_reads_only_the_server_capability():
    html = INVENTORY_HTML.read_text(encoding="utf-8")
    assert "me.%s === true" % CAPABILITY_KEY in html, (
        "client must read the server capability strictly"
    )
    assert "applyFunctionalEquipmentLoadoutCapability(me)" in html


def test_client_capability_starts_closed():
    """First paint, a failed /api/auth/me, or a missing field must stay closed."""
    html = INVENTORY_HTML.read_text(encoding="utf-8")
    assert "let functionalEquipmentLoadoutCapability = false;" in html
    # Strict equality means undefined/null/'true'-as-string all fail closed.
    assert "!!(me && me.%s === true)" % CAPABILITY_KEY in html


def test_client_equip_control_consults_the_capability_function():
    html = INVENTORY_HTML.read_text(encoding="utf-8")
    assert html.count("functionalEquipmentLoadoutEnabled()") >= 2, (
        "both the render gate and the action guard must consult the capability"
    )


def test_client_does_not_grant_ownership_from_the_capability():
    """The capability may only gate the control, never imply ownership."""
    html = INVENTORY_HTML.read_text(encoding="utf-8")
    window = html[html.index("function applyFunctionalEquipmentLoadoutCapability"):][:900]
    for forbidden in ("owned", "item_id", "inventory", "grant"):
        assert forbidden not in window, (
            f"capability handler must not touch ownership state ({forbidden})"
        )


# ── the write path stays server-enforced regardless of the capability ────────

def test_capability_is_presentation_only_and_not_the_write_authority():
    """The equip route must enforce the flag itself, not trust the client."""
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    guard = "if act == 'equip' and not _equipment_canonical_loadout_enabled():"
    assert guard in source, (
        "the 1862ce65d legacy-fallback closure must remain intact"
    )
    assert "LOADOUT_DISABLED" in source


def test_legacy_bypass_is_not_reachable_when_disabled():
    """No branch may equip a functional item while the canonical gate is off."""
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index("def equip_item():")
    body = source[start:start + 4000]
    guard_at = body.index("not _equipment_canonical_loadout_enabled()")
    canonical_at = body.index("_equipment_canonical_loadout_enabled():", guard_at + 1)
    # The unconditional 409 guard must precede any canonical/legacy branching,
    # so a disabled gate can never fall through to an equip writer.
    assert guard_at < canonical_at


# ── equippability is projected from the canonical writer's own authority ─────

@pytest.mark.parametrize(
    "equip_id,expected_slot",
    [("wooden_sword", "weapon"), ("leather_armor", "armor"), ("lucky_stone", "accessory")],
)
def test_equippable_items_project_their_canonical_slot(equip_id, expected_slot):
    projection = app_module._canonical_equippability_projection(equip_id)
    assert projection["canonical_equippable"] is True
    assert projection["canonical_slot"] == expected_slot
    assert projection["not_equippable_reason"] is None


@pytest.mark.parametrize(
    "equip_id,reason",
    [
        ("go_stone_black", "GO_STONE_BLACK_NOT_EQUIPPABLE"),
        ("xp_amulet", "XP_AMULET_HOLD_FOR_AUTHORITY"),
    ],
)
def test_non_equippable_items_project_the_servers_own_reason_code(equip_id, reason):
    """The projected reason must be the exact code a real attempt returns."""
    projection = app_module._canonical_equippability_projection(equip_id)
    assert projection["canonical_equippable"] is False
    assert projection["canonical_slot"] is None
    assert projection["not_equippable_reason"] == reason


def test_non_equippable_ids_match_the_loadout_writers_guard_exactly():
    """The projection may not drift from the writer it mirrors."""
    from migrations.equipment_canonical_slot_v1 import (
        NON_FUNCTIONAL_EQUIPMENT_IDS,
        build_slot_projection,
    )
    equippable = set(build_slot_projection(app_module.EQUIPMENT_DEFS))
    for definition in app_module.EQUIPMENT_DEFS:
        equip_id = definition["id"]
        projected = app_module._canonical_equippability_projection(equip_id)
        assert projected["canonical_equippable"] is (equip_id in equippable)
        if equip_id in NON_FUNCTIONAL_EQUIPMENT_IDS:
            assert projected["canonical_equippable"] is False


def test_unknown_equipment_id_fails_closed():
    projection = app_module._canonical_equippability_projection("not_a_real_item")
    assert projection["canonical_equippable"] is False
    assert projection["not_equippable_reason"] == "NON_FUNCTIONAL_EQUIPMENT"


def test_inventory_payload_carries_the_equippability_projection():
    equip = app_module._EQUIP_MAP["go_stone_black"]
    payload = app_module._functional_equipment_payload(equip, inv_id=1)
    assert payload["canonical_equippable"] is False
    assert payload["not_equippable_reason"] == "GO_STONE_BLACK_NOT_EQUIPPABLE"
    sword = app_module._functional_equipment_payload(
        app_module._EQUIP_MAP["wooden_sword"], inv_id=2)
    assert sword["canonical_equippable"] is True
    assert sword["canonical_slot"] == "weapon"


# ── the client no longer keeps its own non-equippable id list ────────────────

def test_client_has_no_local_non_equippable_id_authority():
    html = INVENTORY_HTML.read_text(encoding="utf-8")
    assert "FUNCTIONAL_INVENTORY_ONLY_IDS" not in html
    assert "'go_stone_black'" not in html and '"go_stone_black"' not in html
    assert "item?.canonical_equippable === true" in html


def test_client_disables_the_equip_control_for_non_equippable_items():
    html = INVENTORY_HTML.read_text(encoding="utf-8")
    assert "const notEquippable = !functionalItemEquippable(item) && !item.equipped;" in html
    assert "const blocked = notEquippable || blockedNewEquip;" in html
    assert "action.disabled = blocked;" in html
    assert "action.onclick = blocked ? null :" in html


def test_client_has_no_silent_failed_equip_path():
    """Every refused click must surface a reason, never return silently."""
    html = INVENTORY_HTML.read_text(encoding="utf-8")
    start = html.index("async function performFunctionalEquipmentAction")
    body = html[start:start + 1400]
    assert "showBackpackToast(functionalItemBlockLabel(item));" in body
    # Every refusal a player can actually trigger must announce itself. The
    # only permitted bare return is the null-argument programming guard.
    lines = body.splitlines()
    silent = []
    for i, line in enumerate(lines):
        if not line.strip().endswith("return;"):
            continue
        if line.strip() == "if (!item || item.inv_id == null) return;":
            continue  # null-argument programming guard, not a player path
        announced = any(
            "showBackpackToast" in lines[j] for j in range(max(0, i - 3), i)
        )
        if not announced:
            silent.append(line.strip())
    assert silent == [], f"refusals that fail silently: {silent}"


def test_client_keeps_ownership_visible_for_non_equippable_items():
    html = INVENTORY_HTML.read_text(encoding="utf-8")
    assert "Collection / Trophy" in html
    assert "functionalItemIsTrophy(item)" in html


# ── true cross-player ownership isolation ────────────────────────────────────

import sqlite3  # noqa: E402

from migrations.equipment_canonical_slot_v1 import upgrade as _upgrade_b033  # noqa: E402


class _DbContext:
    def __init__(self, path):
        self.path = path
        self.conn = None

    def __enter__(self):
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()


def _two_player_inventory(path):
    """PLAYER_A owns a sword; PLAYER_B owns a real, separate sword row."""
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE player_inventory("
            "id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,equip_id TEXT NOT NULL,"
            "equipped INTEGER NOT NULL DEFAULT 0,obtained_at TEXT NOT NULL,"
            "source TEXT NOT NULL DEFAULT 'drop')"
        )
        _upgrade_b033(conn, equipment_defs=app_module.EQUIPMENT_DEFS)
        conn.execute(
            "INSERT INTO player_inventory(id,user_id,equip_id,equipped,canonical_slot,"
            "obtained_at,source) VALUES(1,1,'wooden_sword',0,NULL,'2026-09-04','drop')")
        # PLAYER_B's row is real and already equipped, so a successful cross-user
        # write would be visible as both a steal and a state change.
        conn.execute(
            "INSERT INTO player_inventory(id,user_id,equip_id,equipped,canonical_slot,"
            "obtained_at,source) VALUES(2,2,'iron_sword',1,'weapon','2026-09-04','drop')")


def _snapshot(path):
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in conn.execute(
                "SELECT id,user_id,equip_id,equipped,canonical_slot FROM player_inventory"
                " ORDER BY id")
        ]


def _client_as(path, monkeypatch, user_id):
    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(path))
    monkeypatch.setenv(app_module.EQUIPMENT_CANONICAL_LOADOUT_FLAG, "1")
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["username"] = f"loadout-isolation-user-{user_id}"
    return client


@pytest.mark.parametrize("action", ["equip", "unequip"])
def test_player_a_cannot_touch_player_b_real_inventory_row(tmp_path, monkeypatch, action):
    """A real row owned by PLAYER_B must be unreachable by PLAYER_A.

    This is deliberately not a nonexistent inv_id: row 2 exists, is valid, is
    equippable and is currently equipped by PLAYER_B.
    """
    path = str(tmp_path / "isolation.db")
    _two_player_inventory(path)
    before = _snapshot(path)

    client_a = _client_as(path, monkeypatch, user_id=1)
    response = client_a.post(
        "/api/player/inventory/equip", json={"inv_id": 2, "action": action}
    )

    assert response.status_code == 404
    assert response.get_json() == {"error": "找不到物品"}
    # Nothing moved: not PLAYER_A's row, not PLAYER_B's row, not the equipped bit.
    assert _snapshot(path) == before


def test_player_b_can_still_use_their_own_row(tmp_path, monkeypatch):
    """The isolation guard must not lock the legitimate owner out."""
    path = str(tmp_path / "isolation-owner.db")
    _two_player_inventory(path)

    client_b = _client_as(path, monkeypatch, user_id=2)
    response = client_b.post(
        "/api/player/inventory/equip", json={"inv_id": 2, "action": "unequip"}
    )
    assert response.status_code == 200
    assert response.get_json()["equipped"] is False
    rows = {row["id"]: row for row in _snapshot(path)}
    assert rows[2]["equipped"] == 0
    assert rows[1]["user_id"] == 1 and rows[1]["equipped"] == 0
