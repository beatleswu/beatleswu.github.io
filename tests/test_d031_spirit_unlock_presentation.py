"""D031 presentation-only contract and boundary checks."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "js" / "e9" / "adventure_spirit_unlock_presentation.js"
STYLES = ROOT / "css" / "e9" / "adventure_spirit_unlock.css"
INDEX = ROOT / "index.html"
FIXTURE = ROOT / "tests" / "e2e" / "fixtures" / "d031_spirit_unlock_presentation.html"
DOC = ROOT / "docs" / "planning" / "architecture" / "D031_SPIRIT_ADVENTURE_MILESTONE_UNLOCK_PRESENTATION_001.md"


def test_locked_milestone_mapping_and_states_are_explicit():
    source = MODULE.read_text(encoding="utf-8")
    for value in (
        "k11_15",
        "starpath_antlerling",
        "k1_5",
        "fatty",
        "d3_4",
        "obsidian_bastion",
        "NEW_SPIRIT_UNLOCK",
        "ALREADY_OWNED_NO_OP",
        "NO_MILESTONE_UNLOCK",
    ):
        assert value in source


def test_only_optional_server_result_field_can_reach_runtime_presentation():
    source = INDEX.read_text(encoding="utf-8")
    assert "Array.isArray(data.adventure_spirit_unlock_results)" in source
    assert "AdventureSpiritUnlockPresentation.present" in source
    assert "selectedZone" not in source[source.index("Array.isArray(data.adventure_spirit_unlock_results)") :]


def test_presentation_module_has_no_state_mutation_or_api_authority():
    source = MODULE.read_text(encoding="utf-8")
    assert "fetch(" not in source
    assert "XMLHttpRequest" not in source
    assert "localStorage" not in source
    assert "window.location" not in source
    assert "INSERT" not in source.upper()
    assert "UPDATE" not in source.upper()
    assert "DELETE" not in source.upper()


def test_presentation_does_not_render_compensation_or_combat_effects():
    source = MODULE.read_text(encoding="utf-8")
    assert "Coins" not in source
    assert "drop chance" not in source.lower()
    assert "rarity" not in source.lower()
    assert "combat power" not in source.lower()
    assert "effect" not in source.lower()


def test_responsive_contract_has_desktop_tablet_and_mobile_breakpoints():
    source = STYLES.read_text(encoding="utf-8")
    assert "@media (max-width: 900px)" in source
    assert "@media (max-width: 600px)" in source
    assert "prefers-reduced-motion" in source
    assert "100dvh" in source


def test_fixture_is_presentation_only_and_covers_requested_cases():
    source = FIXTURE.read_text(encoding="utf-8")
    for case in ("zone4", "zone6", "zone8", "already-owned", "no-unlock"):
        assert case in source
    assert "server-authored-result-only" in source
    assert "/api/" not in source


def test_docs_record_transport_gap_and_authority_boundary():
    source = DOC.read_text(encoding="utf-8")
    assert "adventure_spirit_unlock_results" in source
    assert "does not yet" in source
    assert "`app.py`, schema/migrations" in source
    assert "B023 authority" in source
