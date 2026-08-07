"""E10_MAP_BATTLE_V1_CROSS_POOL_RESUME_CLOSURE.

Root cause (confirmed via live production testing, see PR #285's own
follow-up acceptance report): _resolveMapBattleV1Resume() validated its
resume candidate's question_id ONLY against the zone's book-filtered
`qs` (unitQs) selection pool. "下一題" can hand out a question that a
later, freshly-recomputed unitQs no longer contains (server-side practice
queue rotation) -- when that happens, the authoritative, still-valid V1
attempt was being thrown away and _pickAdventureTarget() silently
reverted the player to an earlier question, on BOTH the reload path and
the same-page re-entry path (they share this one resolver).

The fix: qs is a *selection* pool, not an *existence* check for an
attempt that already exists. When the candidate's question_id isn't a
local qs member, hydrate it through the same canonical /api/question/:id
path _loadBossQuestion() already uses for an identical local-miss case,
instead of invalidating the resume.

These tests extract the REAL function bodies from index.html and execute
them in a Node vm context against a mocked fetch/sessionStorage/SRS --
not a source-text regex check -- so they actually exercise the resolver's
branching.
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
    # Walk back to include a leading `async ` keyword if present.
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


def test_all_required_functions_extract_cleanly():
    for name in REQUIRED_FUNCTIONS:
        block = _extract_function(name)
        assert block.strip().startswith(("function ", "async function ")), name
        assert block.rstrip().endswith("}"), name


def _run_harness(cases):
    """cases: list of dicts, each describing one scenario to run through
    the real, extracted _resolveMapBattleV1Resume(). Returns parsed JSON
    results, one entry per case, in the same order."""
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
        getCard: (qid) => (defeatedIds.has(Number(qid)) ? {{ last_grade: 3 }} : (seenIds.has(Number(qid)) ? {{ last_grade: 0 }} : null)),
        isSeen: (qid) => seenIds.has(Number(qid)),
    }};
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


def test_case1_local_pool_resume_unchanged_no_hydration_fetch():
    [out] = _run_harness([{
        "zoneKey": "d3_4",
        "qs": [QUESTION_A, QUESTION_B],
        "resumeCandidate": _candidate(50376),
        "bootstrapResponse": BASE_BOOTSTRAP,
    }])
    assert out["result"]["target"]["id"] == 50376
    assert out["hydrationFetched"] is False, "must not hit the network when the target is already a local qs member"


def test_case2_cross_pool_resume_hydrates_and_resolves_target():
    [out] = _run_harness([{
        "zoneKey": "d3_4",
        "qs": [QUESTION_A],  # B intentionally absent -- the observed production failure shape
        "resumeCandidate": _candidate(50376),
        "bootstrapResponse": BASE_BOOTSTRAP,
        "hydratableQuestions": [QUESTION_B],
    }])
    assert out["result"] is not None, "a valid attempt for a cross-pool question must still resume"
    assert out["result"]["target"]["id"] == 50376
    assert out["hydrationFetched"] is True
    assert out["result"]["resumeState"]["attemptId"] == "attempt-1", "the ORIGINAL attempt identity must be preserved/reused, not replaced"


def test_case6_invalid_question_fails_closed_to_fallback():
    [out] = _run_harness([{
        "zoneKey": "d3_4",
        "qs": [QUESTION_A],
        "resumeCandidate": _candidate(999999),
        "bootstrapResponse": BASE_BOOTSTRAP,
        "hydratableQuestions": [],  # canonical loader cannot resolve it either
    }])
    assert out["result"] is None
    assert out["hydrationFetched"] is True
    assert out["resumeClearedAfter"] is True, "an unresolvable resume must be cleared, not left to dangle"


def test_case7_wrong_zone_does_not_consume_resume():
    [out] = _run_harness([{
        "zoneKey": "d3_4",
        "qs": [QUESTION_A],
        "resumeCandidate": _candidate(50376, zone_key="k16_20"),
        "bootstrapResponse": BASE_BOOTSTRAP,
        "hydratableQuestions": [QUESTION_B],
    }])
    assert out["result"] is None
    assert out["hydrationFetched"] is False, "a zone mismatch must short-circuit before any hydration attempt"


def test_case8_settled_question_falls_back_even_when_hydrated():
    [out] = _run_harness([{
        "zoneKey": "d3_4",
        "qs": [QUESTION_A],
        "resumeCandidate": _candidate(50376),
        "bootstrapResponse": BASE_BOOTSTRAP,
        "hydratableQuestions": [QUESTION_B],
        "seenIds": [50376],
        "defeatedIds": [50376],
    }])
    assert out["result"] is None, "seen+defeated must still fall back, whether the target came from qs or hydration"


def test_bootstrap_failure_still_fails_closed():
    functions_js = "\n\n".join(_extract_function(name) for name in REQUIRED_FUNCTIONS)
    harness = f"""
let _mapBattleV1ServerProgress = new Map();
const _MAP_BATTLE_V1_RESUME_STORAGE_KEY = 'go:e10:map-battle:v1:resume';
{functions_js}
global.sessionStorage = {{ getItem: () => null, setItem: () => {{}}, removeItem: () => {{}} }};
global.SRS = {{ getCard: () => null, isSeen: () => false }};
global.fetch = async () => ({{ ok: false, status: 500, json: async () => ({{}}) }});
_resolveMapBattleV1Resume('d3_4', []).then(r => process.stdout.write(JSON.stringify(r)));
"""
    result = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "null"


def test_reload_path_shares_the_same_resolver_call_as_in_page_reentry():
    # Both paths must delegate to the SAME resolver -- no separate reload-only
    # or in-page-only resume logic, matching the task's explicit "reload and
    # in-page must share contract" requirement.
    entry = INDEX[INDEX.index("async function enterAdventureZoneInPage("):]
    entry = entry[:entry.index("\n}\n")]
    assert "await _resolveMapBattleV1Resume(zone.key, unitQs)" in entry

    reload_marker = "const resume = await _resolveMapBattleV1Resume(zoneParam, unitQs);"
    assert INDEX.count(reload_marker) == 1
    assert "await _resolveMapBattleV1Resume(zone.key, unitQs)" in INDEX
