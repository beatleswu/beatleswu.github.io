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
