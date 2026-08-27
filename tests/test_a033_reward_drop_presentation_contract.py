from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
MODULE = ROOT / "js" / "game" / "reward_drop_presentation_v1.js"
STYLES = ROOT / "css" / "e10" / "reward_drop_presentation_v1.css"


def test_a033_files_and_mount_are_present():
    assert MODULE.is_file()
    assert STYLES.is_file()
    source = INDEX.read_text(encoding="utf-8")
    assert "/js/game/reward_drop_presentation_v1.js?v=a033v2" in source
    assert "/css/e10/reward_drop_presentation_v1.css?v=a033v2" in source
    assert 'id="reward-drop-v1"' in source


def test_a033_presentation_contract_is_fail_closed_and_authority_free():
    source = MODULE.read_text(encoding="utf-8")
    assert "GENERIC_MONSTER_REWARD_PRESENTATION_V1" in source
    assert "FUNCTIONAL_EQUIPMENT" in source
    assert "PURE_COSMETIC" in source
    assert "NO_DROP" in source
    assert "unsupported_reward_type" in source
    assert "malformed_or_missing_reward" in source
    assert "VIEW_BACKPACK" in source
    assert "drop_rate" not in source
    assert "probability" not in source
    assert "coins_granted" not in source


def test_a033_adapter_has_no_writer_or_browser_state_authority():
    source = MODULE.read_text(encoding="utf-8")
    assert "fetch(" not in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source
    assert "window.location" not in source
