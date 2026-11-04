from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
MISTAKES = (ROOT / "mistakes.html").read_text(encoding="utf-8")


def _rule(css: str, selector: str) -> str:
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert m, selector
    return m.group(1)


def test_quiz_pet_never_intercepts_board_taps():
    # The companion image box (transparent area included) overlaps the board's
    # bottom-left corner; owners reported that points near 1-1 could not be played.
    assert "pointer-events: none" in _rule(INDEX, "#quiz-pet")
    assert "pointer-events: none" in _rule(MISTAKES, "#quiz-pet")


def test_quiz_pet_hangs_outside_board_frame_on_phones():
    media = re.search(r"@media \(max-width: 768px\) \{ (#quiz-pet \{[^}]*\}) \}", INDEX)
    assert media, "phone rule for #quiz-pet is missing"
    rule = media.group(1)
    assert "bottom: auto" in rule
    assert "top: calc(100% + 8px)" in rule
    assert "bottom: -4px" not in rule
