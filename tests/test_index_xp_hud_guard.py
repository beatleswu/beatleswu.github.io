from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "index.html"


def test_update_xp_hud_bails_out_when_xp_hud_is_missing() -> None:
    text = INDEX_HTML.read_text(encoding="utf-8")

    assert "function updateXpHud(" in text
    assert "const hud = document.getElementById('xp-hud');" in text
    assert "if (!hud) return;" in text
    assert "const badge = document.getElementById('xp-rank-badge');" in text
    assert "if (!b) return;" in text
