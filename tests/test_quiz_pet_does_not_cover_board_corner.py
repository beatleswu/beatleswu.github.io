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


def test_quiz_pet_stands_above_the_board_top_left_on_phones():
    media = re.search(r"@media \(max-width: 768px\) \{\s*(#quiz-pet \{[^}]*\})\s*(#quiz-pet-status \{[^}]*\})\s*\}", INDEX)
    assert media, "phone block for #quiz-pet is missing"
    pet, badge = media.group(1), media.group(2)
    assert "bottom: calc(100% - 12px)" in pet          # sits on top of the frame, outside the grid
    assert "bottom: -4px" not in pet and "top:" not in pet
    assert "left: calc(100% - 10px)" in badge          # status badge beside the sprite, clear of the prompt pill


def test_phone_layout_reserves_no_extra_space_under_the_board():
    # An earlier attempt pushed the nav buttons down 50px; the owner rejected that.
    assert "margin-bottom: 50px" not in INDEX
    assert "#quiz-pet:not(" not in INDEX
