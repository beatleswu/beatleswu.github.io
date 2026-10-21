"""Run the curriculum's actual display code in Node with synthetic API data.

No app import, database, live players, Quest V2, or third-party JS dependencies.
Also runnable directly with Python's standard unittest runner.
"""

from pathlib import Path
import json
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class QuestProgressUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if not cls.node:
            raise RuntimeError("Node is required to execute the curriculum UI tests")
        html = (ROOT / "curriculum.html").read_text(encoding="utf-8")
        # Execute production functions, not a Python copy of their calculations.
        cls.source = (
            "const assert = require('node:assert/strict'); let english = false;"
            "const _isEnCur = () => english;"
            "const document = {createElement: () => ({querySelector: () => null})};"
            "const STAGE_RANK = {}, STAGE_IS_DAN = {};"
            "const dLabel = x => x, dOrig = x => x, stageLabelOf = x => x;\n"
            + html[html.index("let _questBoard ="):html.index("// 領賞後長老")]
            + html[html.index("function stageReward("):html.index("function dailyQuestCard(")]
            + html[html.index("function questTrackerHtml("):html.index("function rerenderBoard(")]
        )

    def run_js(self, assertions):
        result = subprocess.run(
            [self.node, "-"], input=self.source + "\n" + assertions,
            text=True, encoding="utf-8", capture_output=True, timeout=15,
            cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_checkpoint_boundaries_and_partial_final_segment(self):
        self.run_js("""
            english = true;
            for (const total of [30, 35, 40, 50]) {
              for (let practiced = 0; practiced <= total; practiced++) {
                const input = Object.freeze({practiced, total});
                const p = questPracticeProgress(input);
                assert.equal(p.label, `Practiced ${practiced} / ${total}`);
                assert.equal(p.pct, practiced / total * 100);
                if (practiced === total) {
                  assert.match(p.milestone, /All problems practiced/);
                  assert.match(p.milestone, /determined by the server/);
                } else {
                  const done = Math.floor(practiced / 10) * 10;
                  const next = Math.min(done + 10, total);
                  assert.equal(p.milestone,
                    `Practice milestone ${done} / ${total}; next: ${next}, ${next - practiced} to go`);
                }
              }
            }
            assert.match(questPracticeProgress({practiced: 29, total: 30}).milestone, /1 to go/);
            assert.ok(questPracticeProgress({practiced: 29, total: 30}).pct < 100);
        """)

    def test_invalid_or_missing_counts_do_not_become_zero_or_completion(self):
        cases = [None, True, False, "10", -1, 1.5, 51, {}, []]
        self.run_js("""
            english = true;
            const invalid = """ + json.dumps(cases) + """;
            for (const practiced of [...invalid, undefined, NaN, Infinity]) {
              const p = questPracticeProgress(questUnitFromApi({practiced, total: 50}));
              assert.equal(p.label, 'Practice progress unavailable');
              assert.equal(p.milestone, '');
              assert.equal(p.pct, 0);
            }
            for (const total of [undefined, null, true, '30', 0, -1, 30.5, Infinity]) {
              assert.equal(questPracticeProgress({practiced: 0, total}).label,
                'Practice progress unavailable');
            }
            assert.equal(questPracticeProgress({practiced: 0, total: 30}).label, 'Practiced 0 / 30');
        """)

    def test_checkpoints_are_limited_to_existing_30_to_50_problem_commissions(self):
        self.run_js("""
            for (const total of [1, 10, 29, 51, 300]) {
              assert.equal(questPracticeProgress({practiced: 1, total}).milestone, '');
            }
        """)

    def test_cards_distinguish_practice_from_mastery_in_both_languages(self):
        self.run_js("""
            const unit = questUnitFromApi({discipline: 'life_death', stage: 'LV2',
              practiced: 20, total: 35, coins: 17, xp: 23});
            for (const en of [false, true]) {
              english = en;
              for (const mode of ['open', 'accepted', 'claim']) {
                const html = questCard(unit, mode).innerHTML;
                assert.ok(html.includes(en ? 'Practiced 20 / 35' : '已練習 20 / 35'));
                assert.ok(html.includes(qbT('mastery_note')));
                assert.ok(html.includes(questPracticeProgress(unit).milestone));
                assert.ok(html.includes('width:57.14285714285714%'));
              }
            }
        """)

    def test_practice_completion_does_not_unlock_claim_or_change_rewards(self):
        self.run_js("""
            english = true;
            const unit = Object.freeze(questUnitFromApi({discipline: 'life_death',
              stage: 'LV2', practiced: 35, total: 35, coins: 17, xp: 23}));
            for (const mode of ['open', 'accepted', 'claim']) {
              const html = questCard(unit, mode).innerHTML;
              assert.equal(html.includes('class="qc-btn claim"'), mode === 'claim');
              assert.ok(html.includes('All problems practiced'));
              assert.ok(html.includes('>17</span>'));
              assert.ok(html.includes('>23</span>'));
              assert.equal(_questBoard.claimable.length, 0);
            }
        """)

    def test_tracker_uses_segment_api_progress_over_whole_stage_summary(self):
        self.run_js("""
            english = true;
            const key = 'life_death::LV2::1';
            const meta = {quest_key: key, stage_key: key, discipline: 'life_death',
              stage: 'LV2', practiced: 12, total: 35, href: '/?quest=synthetic'};
            _questBoard.accepted = [key];
            _questBoard.quest_meta = [meta];
            const summary = [{...meta, practiced: 200, total: 300}];
            let html = questTrackerHtml(summary);
            assert.ok(html.includes('Practiced 12 / 35'));
            assert.ok(html.includes('next: 20, 8 to go'));
            assert.ok(html.includes('href="/?quest=synthetic"'));
            assert.ok(!html.includes('200 / 300'));
            _questBoard.claimable = [{...meta, practiced: 35}];
            html = questTrackerHtml(summary);
            assert.ok(html.includes('Practiced 35 / 35'));
            assert.ok(html.includes('Ready to Claim'));
            assert.ok(html.includes('href="#quest-board"'));
        """)


if __name__ == "__main__":
    unittest.main()
