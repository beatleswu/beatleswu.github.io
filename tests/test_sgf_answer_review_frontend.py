import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "sgf_answer_review.js"
PAGE = ROOT / "sgf_answer_review.html"


def _run_node_assertions(source):
    result = subprocess.run(
        ["node", "-e", source],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_board_coordinate_conversion_is_deterministic_for_taps():
    harness = f"""
const assert = require('assert');
const queue = require({json.dumps(str(SCRIPT))});
const geometry = queue.boardGeometry(19, 760, 760);
const topLeft = queue.intersectionToCanvas(0, 0, geometry);
const center = queue.intersectionToCanvas(9, 9, geometry);
const bottomRight = queue.intersectionToCanvas(18, 18, geometry);
const rect = {{left: 20, top: 40, width: 760, height: 760}};
assert.deepStrictEqual(queue.clientPointToIntersection(rect.left + topLeft.x, rect.top + topLeft.y, rect, 19), {{x: 0, y: 0}});
assert.deepStrictEqual(queue.clientPointToIntersection(rect.left + center.x, rect.top + center.y, rect, 19), {{x: 9, y: 9}});
assert.deepStrictEqual(queue.clientPointToIntersection(rect.left + bottomRight.x, rect.top + bottomRight.y, rect, 19), {{x: 18, y: 18}});
assert.strictEqual(queue.clientPointToIntersection(rect.left - 100, rect.top - 100, rect, 19), null);
assert.strictEqual(queue.gtpCoordinate(0, 18, 19), 'A1');
assert.strictEqual(queue.gtpCoordinate(8, 9, 19), 'J10');
assert.strictEqual(queue.gtpCoordinate(18, 0, 19), 'T19');
console.log('coordinate-contract-ok');
"""
    assert "coordinate-contract-ok" in _run_node_assertions(harness)


def test_failed_save_never_advances_and_pending_retry_deduplicates():
    harness = f"""
const assert = require('assert');
const queue = require({json.dumps(str(SCRIPT))});
assert.strictEqual(queue.indexAfterSave(4, 20, false), 4);
assert.strictEqual(queue.indexAfterSave(4, 20, true), 5);
assert.strictEqual(queue.indexAfterSave(19, 20, true), 19);
const operations = [
  {{body: {{mutation_id: 'save:one'}}}},
  {{body: {{mutation_id: 'save:one'}}}},
  {{body: {{mutation_id: 'save:two'}}}},
  {{body: {{}}}},
];
assert.deepStrictEqual(queue.dedupePendingMutations(operations).map(op => op.body.mutation_id), ['save:one', 'save:two']);
assert.strictEqual(queue.pendingStorageKey('abc', 7), 'sgf-owner-review-pending:abc:7');
console.log('retry-contract-ok');
"""
    assert "retry-contract-ok" in _run_node_assertions(harness)


def test_group_filters_preserve_input_order_and_summary_counts_groups_once():
    harness = f"""
const assert = require('assert');
const queue = require({json.dumps(str(SCRIPT))});
const groups = [
  {{review_group_key:'a', priority_tier:'P0', reason_codes:['STRUCTURAL_SGF_ISSUE'], group_size:1, side_to_move:null, current_first_solution_moves:[]}},
  {{review_group_key:'b', priority_tier:'P1', reason_codes:['HIGH_CONFIDENCE_GLOBAL_TENUKI_SUSPECT'], group_size:3, side_to_move:'B', current_first_solution_moves:[{{x:1,y:1}}]}},
  {{review_group_key:'c', priority_tier:'P2', reason_codes:['MULTIPLE_SOLUTION_REVIEW'], group_size:1, side_to_move:'W', current_first_solution_moves:[{{x:1,y:1}}]}},
];
const states = {{
  b: {{review_status:'CONFIRMED_ISSUE', proposals:[{{type:'REJECT_HISTORICAL_PRECOMPUTED_FALLBACK'}}]}},
  c: {{review_status:'POSSIBLE_MULTIPLE_SOLUTION', proposals:[]}},
}};
assert.deepStrictEqual(groups.filter(g => queue.groupMatchesFilters(g, states[g.review_group_key], {{status:'pending',priority:'all',focus:'all'}})).map(g => g.review_group_key), ['a']);
assert.deepStrictEqual(groups.filter(g => queue.groupMatchesFilters(g, states[g.review_group_key], {{status:'all',priority:'all',focus:'tenuki'}})).map(g => g.review_group_key), ['b']);
assert.deepStrictEqual(groups.filter(g => queue.groupMatchesFilters(g, states[g.review_group_key], {{status:'all',priority:'all',focus:'duplicate'}})).map(g => g.review_group_key), ['b']);
const summary = queue.computeSummary(groups, states);
assert.deepStrictEqual(summary, {{total_groups:3,pending:1,reviewed:2,confirmed_issue:1,possible_multiple_solution:1,uncertain:0,no_issue:0,staged_repair_groups:1,staged_proposals:1}});
console.log('filter-contract-ok');
"""
    assert "filter-contract-ok" in _run_node_assertions(harness)


def test_owner_page_has_all_five_viewport_contracts_and_touch_safe_controls():
    html = PAGE.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")

    for viewport in (
        "desktop-1440x900",
        "ipad-768x1024",
        "ipad-820x1180",
        "ipad-1024x768",
        "ipad-1180x820",
    ):
        assert viewport in html
    assert "touch-44px" in html
    assert re.search(r"button,select\{min-height:48px\}", html)
    assert re.search(r"\.staged-actions button\{min-height:44px\}", html)
    assert "touch-action:none" in html
    assert ":hover" not in html
    assert "position:fixed" in html and 'id="sticky-nav"' in html
    assert 'id="go-board"' in html
    assert html.index('id="go-board"') < html.index('id="sticky-nav"')
    assert ".mobile-fast-bar{display:none}" in html
    assert "@media(max-width:899px) and (orientation:portrait)" in html
    assert "mobile-fast-a-correct" in script
    assert "mobile-fast-both" in script
    assert "mobile-fast-a-wrong" in script
    assert "mobile-fast-later" in script
    assert "hasComparableAnswers" in script


def test_board_first_actions_require_no_coordinate_or_sgf_text_entry():
    html = PAGE.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")

    assert "直接點棋盤交叉點；不需輸入座標" in script
    assert 'id="replace-answer-btn"' in html
    assert 'id="add-answer-btn"' in html
    assert 'data-side="B"' in html and 'data-side="W"' in html
    assert 'id="source-includes-answer" type="checkbox"' in html
    assert "<textarea" not in html.lower()
    assert 'type="text"' not in html.lower()
    assert "/questions" not in script
    assert "accepted_moves" not in script
    assert "OWNER_APPROVED_REPAIR_PROPOSAL" in script
    assert "STAGED_NOT_APPLIED" in script


def test_local_storage_is_scoped_to_retry_queue_not_review_truth():
    script = SCRIPT.read_text(encoding="utf-8")

    assert "sgf-owner-review-pending" in script
    assert "localStorage.setItem(storageKey(), JSON.stringify(cleaned))" in script
    assert "runtime.states = payload.states" in script
    assert "server-side staging" in script
    assert "localStorage.setItem('review" not in script
