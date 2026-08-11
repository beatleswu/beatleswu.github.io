"""E10_MAP_BATTLE_V1_RESUME_MASTERY_GUARD_CORRECTION.

Root cause (confirmed live in production -- see the PR #287 acceptance
audit): _resolveMapBattleV1Resume() rejected an otherwise-valid resume
candidate whenever _adventureQuestionSeen(target.id) &&
_adventureQuestionDefeated(target.id) -- i.e. whenever the underlying
question had ANY historical SRS record with last_grade >= 3, no matter
how old.

That predicate is a NEW-target *selection* preference (still correctly
used by _pickAdventureTarget()/_pickNextAdventureTarget(): prefer
unseen, then seen-but-unmastered, over already-mastered content when
picking what to offer next). It is not a validity gate on an attempt the
server has already issued. Two routine, unmodified flows already create
legitimate active attempts for historically-mastered questions:

  - manual 下一題 (nextQuestion() with no args) selects via a plain
    `_adventureActiveQuestions[(idx+1) % length]` index wrap with NO
    seen/defeated filtering at all;
  - replenish_stars zones exist specifically to let players revisit
    already-answered content.

Server-side, map_battle_v1_prepare_attempt validates only that the
question exists; the attempt lifecycle (map_battle_persistence.py) is
driven solely by ISSUED -> SETTLED/REJECTED via submission/expiry, never
by srs_cards.last_grade. So a same-zone, still-ISSUED, unsettled attempt
for a historically-mastered question was being silently discarded by the
client alone, reverting the player to an earlier question -- reproduced
live in production on question 50376 (last_grade: 5, graded two days
before the reproducing session).

Fix: remove the seen+defeated rejection from _resolveMapBattleV1Resume()
only. The identical predicate stays untouched in
_pickAdventureTarget()/_pickNextAdventureTarget().
"""
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")


def _extract_function(name):
    marker = f"function {name}("
    start = INDEX.index(marker)
    if INDEX[max(0, start - 6):start] == "async ":
        start -= 6
    brace_start = INDEX.index("{", start)
    depth = 1
    i = brace_start + 1
    while depth:
        ch = INDEX[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    return INDEX[start:i]


REQUIRED_FUNCTIONS = [
    "_resolveMapBattleV1Resume",
    "_readMapBattleV1Resume",
    "_clearMapBattleV1Resume",
    "_adventureQuestionSeen",
    "_adventureQuestionDefeated",
]


def _run_harness(cases):
    functions_js = "\n\n".join(_extract_function(name) for name in REQUIRED_FUNCTIONS)
    harness = f"""
let _mapBattleV1ServerProgress = new Map();
const _MAP_BATTLE_V1_RESUME_STORAGE_KEY = 'go:e10:map-battle:v1:resume';

{functions_js}

    async function runCase(caseSpec) {{
    _mapBattleV1ServerProgress = new Map();
    const store = {{}};
    global.sessionStorage = {{
        getItem: (k) => (k in store ? store[k] : null),
        setItem: (k, v) => {{ store[k] = String(v); }},
        removeItem: (k) => {{ delete store[k]; }},
    }};
    if (caseSpec.resumeCandidate !== null) {{
        store['go:e10:map-battle:v1:resume'] = JSON.stringify(caseSpec.resumeCandidate);
    }}
    const seenIds = new Set(caseSpec.seenIds || []);
    const defeatedIds = new Set(caseSpec.defeatedIds || []);
        global.SRS = {{
        getCard: (qid) => (defeatedIds.has(Number(qid)) ? {{ last_grade: 5 }} : (seenIds.has(Number(qid)) ? {{ last_grade: 0 }} : null)),
        isSeen: (qid) => seenIds.has(Number(qid)),
        }};
        global.window = {{ MapBattleV1: {{ legacy: {{
            validateResume: async (candidate) => {{
                if (caseSpec.resumeValidationOk === false) throw new Error('not resumable');
                candidate.attemptState = 'ISSUED';
                return candidate;
            }},
        }} }} }};
    const fetchCalls = [];
    global.fetch = async (url) => {{
        fetchCalls.push(url);
        if (String(url).startsWith('/api/adventure/bootstrap')) {{
            return {{ ok: true, json: async () => caseSpec.bootstrapResponse }};
        }}
        if (String(url).startsWith('/api/srs/all')) {{
            return {{ ok: true, json: async () => (caseSpec.srsAllResponse || []) }};
        }}
        if (String(url).startsWith('/api/question/')) {{
            const qid = String(url).split('/').pop();
            const hit = (caseSpec.hydratableQuestions || []).find(q => String(q.id) === qid);
            if (!hit) return {{ ok: false, status: 404, json: async () => ({{}}) }};
            return {{ ok: true, json: async () => hit }};
        }}
        throw new Error('unexpected fetch url: ' + url);
    }};
    const result = await _resolveMapBattleV1Resume(caseSpec.zoneKey, caseSpec.qs || []);
    return {{
        result,
        hydrationFetched: fetchCalls.some(u => String(u).startsWith('/api/question/')),
        resumeClearedAfter: global.sessionStorage.getItem('go:e10:map-battle:v1:resume') === null,
    }};
}}

(async () => {{
    const cases = {json.dumps(cases)};
    const out = [];
    for (const c of cases) {{
        out.push(await runCase(c));
    }}
    process.stdout.write(JSON.stringify(out));
}})();
"""
    result = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"harness failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    return json.loads(result.stdout)


BASE_BOOTSTRAP = {"zones": [{"key": "d3_4"}, {"key": "k16_20"}]}
QUESTION_A = {"id": 50175, "topic": "life-and-death-a"}
QUESTION_B = {"id": 50376, "topic": "life-and-death-b"}


def _candidate(question_id, zone_key="d3_4"):
    return {
        "zoneKey": zone_key,
        "questionId": question_id,
        "battleId": "battle-1",
        "attemptId": "attempt-1",
        "submissionNonce": "nonce-1",
    }


# ---------------------------------------------------------------------------
# Matrix 1: mastered + active ISSUED -> resume succeeds (the actual production bug)
# ---------------------------------------------------------------------------

def test_matrix1_mastered_active_attempt_resumes():
    [out] = _run_harness([{
        "zoneKey": "d3_4",
        "qs": [QUESTION_A, QUESTION_B],
        "resumeCandidate": _candidate(50376),
        "bootstrapResponse": BASE_BOOTSTRAP,
        "seenIds": [50376],
        "defeatedIds": [50376],
    }])
    assert out["result"] is not None, "an active, unsettled, same-zone attempt must resume regardless of historical mastery"
    assert out["result"]["target"]["id"] == 50376
    assert out["result"]["resumeState"]["attemptId"] == "attempt-1"


# ---------------------------------------------------------------------------
# Matrix 2: mastered + settled (no persisted candidate, matching how the
# existing submission flow already clears resume on settlement) -> rejected
# ---------------------------------------------------------------------------

def test_matrix2_no_candidate_is_rejected_regardless_of_mastery():
    [out] = _run_harness([{
        "zoneKey": "d3_4",
        "qs": [QUESTION_A, QUESTION_B],
        "resumeCandidate": None,
        "bootstrapResponse": BASE_BOOTSTRAP,
        "seenIds": [50376],
        "defeatedIds": [50376],
    }])
    assert out["result"] is None


# ---------------------------------------------------------------------------
# Matrix 3: mastered + wrong zone -> rejected
# ---------------------------------------------------------------------------

def test_matrix3_mastered_wrong_zone_is_rejected():
    [out] = _run_harness([{
        "zoneKey": "d3_4",
        "qs": [QUESTION_A],
        "resumeCandidate": _candidate(50376, zone_key="k16_20"),
        "bootstrapResponse": BASE_BOOTSTRAP,
        "seenIds": [50376],
        "defeatedIds": [50376],
    }])
    assert out["result"] is None
    assert out["hydrationFetched"] is False, "zone mismatch must short-circuit before any hydration attempt"


# ---------------------------------------------------------------------------
# Matrix 4: mastered + invalid/unhydratable question -> rejected, fails closed
# ---------------------------------------------------------------------------

def test_matrix4_mastered_invalid_question_fails_closed():
    [out] = _run_harness([{
        "zoneKey": "d3_4",
        "qs": [QUESTION_A],
        "resumeCandidate": _candidate(999999),
        "bootstrapResponse": BASE_BOOTSTRAP,
        "hydratableQuestions": [],
        "seenIds": [999999],
        "defeatedIds": [999999],
    }])
    assert out["result"] is None
    assert out["resumeClearedAfter"] is True


# ---------------------------------------------------------------------------
# Matrix 5: unmastered + active -> existing resume behavior unchanged
# ---------------------------------------------------------------------------

def test_matrix5_unmastered_active_attempt_still_resumes():
    [out] = _run_harness([{
        "zoneKey": "d3_4",
        "qs": [QUESTION_A, QUESTION_B],
        "resumeCandidate": _candidate(50175),
        "bootstrapResponse": BASE_BOOTSTRAP,
    }])
    assert out["result"] is not None
    assert out["result"]["target"]["id"] == 50175


# ---------------------------------------------------------------------------
# Matrix 6: cross-pool (PR #287) + mastered + active -> hydrate and resume the
# SAME attempt. Proves the two fixes compose correctly.
# ---------------------------------------------------------------------------

def test_matrix6_cross_pool_and_mastered_together_still_resume_same_attempt():
    [out] = _run_harness([{
        "zoneKey": "d3_4",
        "qs": [QUESTION_A],  # B absent from local unitQs
        "resumeCandidate": _candidate(50376),
        "bootstrapResponse": BASE_BOOTSTRAP,
        "hydratableQuestions": [QUESTION_B],
        "seenIds": [50376],
        "defeatedIds": [50376],
    }])
    assert out["result"] is not None
    assert out["result"]["target"]["id"] == 50376
    assert out["hydrationFetched"] is True
    assert out["result"]["resumeState"]["attemptId"] == "attempt-1"


# ---------------------------------------------------------------------------
# Matrix 7: new-target SELECTION heuristics are untouched -- the mastery
# predicate must still prefer unseen, then seen-but-unmastered, over mastered.
# ---------------------------------------------------------------------------

def test_matrix7_pick_adventure_target_still_prefers_unmastered():
    pick_js = _extract_function("_pickAdventureTarget")
    assert "_adventureQuestionSeen" in pick_js
    assert "_adventureQuestionDefeated" in pick_js

    harness = f"""
let _mapBattleV1ServerProgress = new Map();
function _adventureQuestionSeen(qid) {{ return new Set([1, 2]).has(qid); }}
function _adventureQuestionDefeated(qid) {{ return qid === 2; }}
{pick_js}
const result = _pickAdventureTarget([{{id: 2}}, {{id: 3}}]);
process.stdout.write(JSON.stringify(result));
"""
    result = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    picked = json.loads(result.stdout)
    assert picked["id"] == 3, "an unseen question must still be preferred over an already-mastered one"


def test_matrix7_pick_next_adventure_target_still_prefers_unmastered():
    pick_js = _extract_function("_pickNextAdventureTarget")
    assert "_adventureQuestionSeen" in pick_js
    assert "_adventureQuestionDefeated" in pick_js

    harness = f"""
function _adventureQuestionSeen(qid) {{ return new Set([1, 2]).has(qid); }}
function _adventureQuestionDefeated(qid) {{ return qid === 2; }}
{pick_js}
const result = _pickNextAdventureTarget([{{id: 1}}, {{id: 2}}, {{id: 3}}], 1);
process.stdout.write(JSON.stringify(result));
"""
    result = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    picked = json.loads(result.stdout)
    assert picked["id"] == 3, "the mastered question (2) must still be skipped in favor of the unseen one (3)"


def test_mastery_guard_removed_only_from_resolver_not_from_selectors():
    resolver_js = _extract_function("_resolveMapBattleV1Resume")
    assert "_adventureQuestionSeen(" not in resolver_js
    assert "_adventureQuestionDefeated(" not in resolver_js

    assert "_adventureQuestionSeen" in _extract_function("_pickAdventureTarget")
    assert "_adventureQuestionDefeated" in _extract_function("_pickAdventureTarget")
    assert "_adventureQuestionSeen" in _extract_function("_pickNextAdventureTarget")
    assert "_adventureQuestionDefeated" in _extract_function("_pickNextAdventureTarget")


# ---------------------------------------------------------------------------
# Matrix 8/9: manual Next side effects and normal settlement are unrelated,
# unmodified code -- already covered by
# tests/test_e10_battle_explanation_and_return_actions.py and
# tests/test_e10_battle_reentry_i18n_ipad_cta_closure.py. Not duplicated here.
# ---------------------------------------------------------------------------
