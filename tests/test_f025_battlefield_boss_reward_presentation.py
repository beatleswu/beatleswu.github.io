"""Static F025 presentation integration and authority-boundary tests."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "js" / "game" / "battlefield_boss_reward_presentation_v1.js"
STYLE = ROOT / "css" / "e10" / "battlefield_boss_reward_presentation_v1.css"
INDEX = ROOT / "index.html"
FIXTURE = ROOT / "tests" / "e2e" / "fixtures" / "f025_battlefield_boss_reward_presentation.html"


def test_f025_assets_and_index_hook_exist_without_app_wiring():
    script = SCRIPT.read_text(encoding="utf-8")
    style = STYLE.read_text(encoding="utf-8")
    index = INDEX.read_text(encoding="utf-8")
    assert "battlefield-boss-reward-result" in index
    assert "battlefield_boss_reward_presentation_v1.css" in index
    assert "battlefield_boss_reward_presentation_v1.js" in index
    assert "app.py" not in script.lower()
    assert "flask" not in script.lower()
    assert "commit(" not in script.lower()
    assert "rollback(" not in script.lower()
    assert "zone_clear" not in script
    assert "lord_ready" not in script
    assert "next_zone" not in script
    assert "coins" not in script.lower()
    assert "combat power" in script.lower()
    assert ".battlefield-boss-reward-card" in style


def test_fixture_uses_only_synthetic_f024_transport_facts():
    fixture = FIXTURE.read_text(encoding="utf-8")
    assert "synthetic server-authored F024 transport payloads" in fixture
    assert "FIRST_CLEAR_NEW_COSMETIC" in fixture
    assert "FIRST_CLEAR_ALREADY_OWNED_NO_OP" in fixture
    assert "NOT_FIRST_CLEAR" in fixture
    assert "back_pack" not in fixture
    assert "zone_clear" not in fixture
    assert "star_granted" not in fixture
    assert "next_zone" not in fixture


def test_f025_does_not_call_runtime_or_browser_mutation_authorities():
    script = SCRIPT.read_text(encoding="utf-8").lower()
    for forbidden in (
        "fetch(",
        "xmlhttprequest",
        "document.cookie",
        "localstorage",
        "sessionstorage",
        "player_wardrobe",
        "event_outbox",
        "commit(",
        "rollback(",
    ):
        assert forbidden not in script
