"""WGo DPR/canvas size can differ from DOM offsetHeight; source must use true backing dimensions."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
RUNNER=ROOT/"tests"/"e2e"/"run_20261019_real_lord_20_wgo_browser.mjs"

def test_real_touch_coordinates_project_backing_board_into_visible_bounding_rect():
    s=RUNNER.read_text(encoding="utf-8")
    block=s[s.index("function point(){"):s.index("\ntry{",s.index("function point(){"))]
    assert "board.getX(dx)/board.width*r.width" in block
    assert "board.getY(dy)/board.height*r.height" in block
    assert "el.offsetWidth" not in block.replace("cssBoardWidth:el.offsetWidth","")
    assert "el.offsetHeight" not in block
    assert "INVALID_WGO_BOARD_GEOMETRY" in block
    # Real G082 failure evidence: old runner sent y=316 for SGF coordinate y=4.
    # WGo backing height=1455.5, getY(4)=372.75, DOM rect top=164.90625,
    # visible rect height=727.75. The real intersection is y=351.
    top=164.90625
    rect_height=727.75
    backing_height=1455.5
    get_y_for_four=372.75
    correct=round(top+get_y_for_four/backing_height*rect_height)
    assert correct==351
    assert correct!=316
    assert "async function waitForStableWGoBoard()" in s
    assert "waitForStableWGoBoard()" in s
