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


def test_quiz_pet_has_its_own_slot_below_the_board_on_phones():
    media = re.search(r"@media \(max-width: 768px\) \{\s*(#quiz-pet \{[^}]*\})(.*?)
    \}", INDEX, re.S)
    assert media, "phone block for #quiz-pet is missing"
    rule, rest = media.group(1), media.group(2)
    assert "bottom: auto" in rule
    assert "top: calc(100% - 14px)" in rule
    assert "bottom: -4px" not in rule
    # the slot is only reserved while the companion is actually shown
    assert ".quiz-board-anchor:has(> #quiz-pet:not([style*=\"display:none\"]))" in rest
    assert "margin-bottom: 50px" in rest
