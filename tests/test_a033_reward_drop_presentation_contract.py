from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
MODULE = ROOT / "js" / "game" / "reward_drop_presentation_v1.js"
STYLES = ROOT / "css" / "e10" / "reward_drop_presentation_v1.css"
FIXTURE = ROOT / "tests" / "e2e" / "fixtures" / "a033_reward_drop_presentation_showcase.html"


def test_a033_files_and_mount_are_present():
    assert MODULE.is_file()
    assert STYLES.is_file()
    assert FIXTURE.is_file()
    source = INDEX.read_text(encoding="utf-8")
    assert "/js/game/reward_drop_presentation_v1.js?v=a033r3" in source
    assert "/css/e10/reward_drop_presentation_v1.css?v=a033r3" in source
    assert 'id="reward-drop-v1"' in source
    assert 'id="reward-drop-v1-brand"' in source


def test_a033_presentation_contract_is_fail_closed_and_authority_free():
    source = MODULE.read_text(encoding="utf-8")
    assert "GENERIC_MONSTER_REWARD_PRESENTATION_V1" in source
    assert "FUNCTIONAL_EQUIPMENT" in source
    assert "PURE_COSMETIC" in source
    assert "NO_DROP" in source
    assert "ALREADY_OWNED" in source
    assert "NOT_FIRST_CLEAR" in source
    assert "unsupported_reward_type" in source
    assert "malformed_or_missing_reward" in source
    assert "VIEW_BACKPACK" in source
    assert "RARITIES" not in source
    assert "model.rarity" not in source
    assert "rarity.toUpperCase" not in source
    assert "drop_rate" not in source
    assert "probability" not in source
    assert "coins_granted" not in source
    assert "fallback_emoji" not in source
    assert "conflicting_reward_status" in source


def test_a033_adapter_has_no_writer_or_browser_state_authority():
    source = MODULE.read_text(encoding="utf-8")
    assert "fetch(" not in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source
    assert "window.location" not in source


def test_a033_rarity_is_not_a_public_reward_presentation_field():
    source = MODULE.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")
    index_source = INDEX.read_text(encoding="utf-8")
    assert "item.rarity" not in source
    assert "showMonsterRewardLegacyToast(toastId, icon, name)" in index_source
    assert "showMonsterRewardLegacyToast('loot-toast', loot.icon, loot.name)" in index_source
    assert "showMonsterRewardLegacyToast('appear-toast', item.emoji, item.name)" in index_source
    assert "reward-drop-v1__state.common" not in styles
    assert "reward-drop-v1__state.rare" not in styles
    assert "reward-drop-v1__state.epic" not in styles
    assert "reward-drop-v1__state.legendary" not in styles


def test_a033_r2_uses_rpg_result_layer_without_fixture_copy_in_evidence():
    styles = STYLES.read_text(encoding="utf-8")
    fixture = FIXTURE.read_text(encoding="utf-8")
    assert "--reward-navy: #071526" in styles
    assert "reward-drop-v1__brand" in styles
    assert "reward-drop-v1__neutral-art" in styles
    assert "@media (max-width: 720px)" in styles
    assert ".reward-drop-v1__state {\n    display: block;" in styles
    assert '<main class="showcase" id="fixture-debug" hidden>' in fixture
    assert "/js/game/reward_drop_presentation_v1.js?v=a033r3" in fixture
    assert "/css/e10/reward_drop_presentation_v1.css?v=a033r3" in fixture
    assert 'id="reward-drop-v1-brand"' in fixture
    assert "already_owned" in fixture
    assert "not_first_clear" in fixture
