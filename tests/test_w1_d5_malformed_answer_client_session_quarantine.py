"""W1-D5 client-only session quarantine and transport contract tests."""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
SRS_PATH = ROOT / "srs.js"
TRANSPORT_PATH = ROOT / "js" / "game" / "review_transport.js"
INDEX_PATH = ROOT / "index.html"


def _run_node(script: str) -> dict:
    # Incident 002/003E: this test suite embeds the full current text of one
    # or more product JS files into the verification script. `node -e
    # <script>` passes that text as a single OS command-line argument, which
    # is subject to a hard platform length ceiling (observed: Windows'
    # CreateProcess rejects the whole invocation with WinError 206 once the
    # combined embedded source crosses roughly 32K characters) that ordinary,
    # legitimate product growth can cross with no change to this test's own
    # logic or to the JS it verifies. Writing the identical script to a temp
    # CommonJS file (`.cjs`, so Node never mis-treats it as an ES module
    # regardless of any ancestor package.json) and running `node <file>`
    # instead removes that ceiling entirely.
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".cjs", dir=ROOT, delete=False, encoding="utf-8",
    ) as handle:
        handle.write(script)
        script_path = pathlib.Path(handle.name)
    try:
        result = subprocess.run(
            ["node", str(script_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        script_path.unlink(missing_ok=True)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    return json.loads(result.stdout)


def test_srs_quarantine_is_revision_bound_and_wrap_safe():
    source = SRS_PATH.read_text(encoding="utf-8")
    script = f"""
const fs = require('fs');
globalThis.window = {{}};
globalThis.fetch = async () => ({{ ok: true, json: async () => ({{}}) }});
globalThis.localStorage = {{ getItem: () => null, setItem: () => {{}}, removeItem: () => {{}} }};
globalThis.__D5_SRS = undefined;
{source}
globalThis.__D5_SRS = SRS;
const q431v1 = {{ id: 431, question_revision: 'rev-1' }};
const q431v2 = {{ id: 431, question_revision: 'rev-2' }};
const q432 = {{ id: 432, question_revision: 'rev-1' }};
SRS.clearSessionQuarantine();
const attached = SRS.quarantineQuestion(431, 'rev-1');
const next = SRS.findNextAvailableQuestion([q431v1, q432], q431v1, 1);
const repeated = Array.from({{ length: 8 }}, () => SRS.findNextAvailableQuestion([q431v1, q432], q432, 1)?.id ?? null);
const revisionIsolation = SRS.findNextAvailableQuestion([q431v2, q432], q432, 1)?.id ?? null;
SRS.quarantineQuestion(432, 'rev-1');
const exhausted = SRS.findNextAvailableQuestion([q431v1, q432], q431v1, 1);
console.log(JSON.stringify({{ attached, nextId: next?.id ?? null, repeated, revisionIsolation, exhausted }}));
"""
    result = _run_node(script)
    assert result == {
        "attached": True,
        "nextId": 432,
        "repeated": [432] * 8,
        "revisionIsolation": 431,
        "exhausted": None,
    }


def test_malformed_answer_closes_the_same_session_wrap_loop():
    source = SRS_PATH.read_text(encoding="utf-8")
    script = f"""
globalThis.window = {{
  ReviewTransport: {{
    legacyReview: async () => ({{
      error: 'malformed_answer',
      failure_class: 'QUESTION_OR_CONTENT_INVALID',
      retryable: false, question_id: 431, question_revision: 'rev-1'
    }})
  }}
}};
{source}
(async () => {{
  const list = [
    {{ id: 431, question_revision: 'rev-1' }},
    {{ id: 432, question_revision: 'rev-1' }}
  ];
  const legacyNext = (questions, current) => {{
    const index = questions.findIndex(question => question.id === current.id);
    return questions[(index + 1) % questions.length];
  }};
  let legacyCurrent = list[0];
  const preFix = [legacyCurrent.id];
  legacyCurrent = legacyNext(list, legacyCurrent);
  preFix.push(legacyCurrent.id);
  legacyCurrent = legacyNext(list, legacyCurrent);
  preFix.push(legacyCurrent.id);

  SRS.clearSessionQuarantine();
  await SRS.review(431, 0, null, false, {{}});
  let current = list[0];
  const postFix = [];
  for (let index = 0; index < 4; index += 1) {{
    const next = SRS.findNextAvailableQuestion(list, current, 1);
    postFix.push(next?.id ?? null);
    if (next) current = next;
  }}
  console.log(JSON.stringify({{ preFix, postFix }}));
}})().catch(error => {{ console.error(error); process.exitCode = 1; }});
"""
    result = _run_node(script)
    assert result == {
        "preFix": [431, 432, 431],
        "postFix": [432, 432, 432, 432],
    }


def test_review_transport_preserves_structured_rejection_without_answer_payload():
    source = TRANSPORT_PATH.read_text(encoding="utf-8")
    script = f"""
globalThis.window = {{}};
globalThis.fetch = async () => ({{
  ok: false,
  status: 400,
  json: async () => ({{
    error: 'malformed_answer', code: 'malformed_answer',
    failure_class: 'CLIENT_ANSWER_INVALID', reason_code: 'malformed_move_action',
    retryable: false, question_id: 431, question_revision: 'rev-1'
  }})
}});
{source}
window.ReviewTransport.review({{ question_id: 431, grade: 5, moves: [{{ x: 1, y: 1 }}] }}, globalThis.fetch)
  .then(() => process.stdout.write(JSON.stringify({{ ok: true }})))
  .catch(error => process.stdout.write(JSON.stringify({{
    name: error.name, code: error.code, failureClass: error.failureClass,
    reasonCode: error.reasonCode, retryable: error.retryable,
    questionId: error.questionId, questionRevision: error.questionRevision,
    rawMovesLogged: false
  }})));
"""
    result = _run_node(script)
    assert result == {
        "name": "ReviewRejected",
        "code": "malformed_answer",
        "failureClass": "CLIENT_ANSWER_INVALID",
        "reasonCode": "malformed_move_action",
        "retryable": False,
        "questionId": 431,
        "questionRevision": "rev-1",
        "rawMovesLogged": False,
    }


def test_direct_review_transport_rejection_uses_the_same_session_quarantine():
    srs_source = SRS_PATH.read_text(encoding="utf-8")
    transport_source = TRANSPORT_PATH.read_text(encoding="utf-8")
    script = f"""
globalThis.window = {{}};
{srs_source}
{transport_source}
const fetchImpl = async () => ({{
  ok: false,
  status: 400,
  json: async () => ({{
    error: 'malformed_answer', failure_class: 'DETERMINISTIC_JUDGE_INPUT_INVALID',
    retryable: false, question_id: 431, question_revision: 'rev-1'
  }})
}});
(async () => {{
  SRS.clearSessionQuarantine();
  try {{
    await window.ReviewTransport.review({{ question_id: 431, grade: 0 }}, fetchImpl);
  }} catch (error) {{
    console.log(JSON.stringify({{
      rejected: error.name === 'ReviewRejected',
      quarantined: SRS.isQuestionQuarantined(431, 'rev-1')
    }}));
    return;
  }}
  console.log(JSON.stringify({{ rejected: false, quarantined: false }}));
}})().catch(error => {{ console.error(error); process.exitCode = 1; }});
"""
    result = _run_node(script)
    assert result == {"rejected": True, "quarantined": True}


def test_transient_failure_is_not_quarantined_by_client_policy():
    source = SRS_PATH.read_text(encoding="utf-8")
    script = f"""
globalThis.window = {{
  ReviewTransport: {{ legacyReview: async (_qid, _grade, _unit, _done, metadata) => metadata }}
}};
{source}
(async () => {{
  SRS.clearSessionQuarantine();
  await SRS.review(431, 5, null, false, {{
    error: 'judge_unavailable', failure_class: 'TRANSIENT_SERVER_FAILURE',
    retryable: true, question_id: 431, question_revision: 'rev-1'
  }});
  const transientServer = SRS.isQuestionQuarantined(431, 'rev-1');
  await SRS.review(431, 5, null, false, {{
    error: 'guild_verdict_unavailable', failure_class: 'TRANSIENT_PERSISTENCE_FAILURE',
    retryable: true, question_id: 431, question_revision: 'rev-1'
  }});
  const transientPersistence = SRS.isQuestionQuarantined(431, 'rev-1');
  await SRS.review(431, 5, null, false, {{
    error: 'malformed_answer', failure_class: 'CONTENT_SIDE_CANONICALIZATION_FAILURE',
    retryable: false, question_id: 431, question_revision: 'rev-1'
  }});
  const deterministicMalformed = SRS.isQuestionQuarantined(431, 'rev-1');
  SRS.clearSessionQuarantine();
  await SRS.review(431, 5, null, false, {{
    error: 'malformed_answer', failure_class: 'CLIENT_ANSWER_INVALID',
    retryable: false, question_id: 431, question_revision: 'rev-1'
  }});
  const clientInvalid = SRS.isQuestionQuarantined(431, 'rev-1');
  console.log(JSON.stringify({{ transientServer, transientPersistence, deterministicMalformed, clientInvalid }}));
}})().catch(error => {{ console.error(error); process.exitCode = 1; }});
"""
    result = _run_node(script)
    assert result == {
        "transientServer": False,
        "transientPersistence": False,
        "deterministicMalformed": True,
        "clientInvalid": False,
    }


def test_index_contract_quarantines_permanent_only_and_handles_exhaustion():
    source = INDEX_PATH.read_text(encoding="utf-8")
    srs_source = SRS_PATH.read_text(encoding="utf-8")

    assert "failureClass === 'TRANSIENT_PERSISTENCE_FAILURE'" in srs_source
    assert "failureClass === 'TRANSIENT_SERVER_FAILURE'" in srs_source
    assert "data.retryable === true" in srs_source
    assert "quarantineQuestion(questionId, revision)" in srs_source
    assert "__GO_D5_RECORD_REJECTED_ANSWER__" in srs_source
    assert "__GO_D5_RECORD_REJECTED_ANSWER__" in TRANSPORT_PATH.read_text(encoding="utf-8")
    assert "SRS.findNextAvailableQuestion" in source
    assert "_showSessionNoValidQuestion();" in source

    # The temporary key is explicitly not the canonical Learning identity.
    assert "source_record_uuid" not in source[source.index("let _guildQuestQuestions"):source.index("function _publishMapBattleV1Lifecycle")]


def test_index_does_not_report_unit_progress_before_review_acceptance():
    """SRS.reportUnitProgress (a real, server-recorded side effect) must
    stay upstream of -- and outside -- the review commit assignment: it may
    not depend on this specific review having been accepted, and it must
    not itself become the value branch of that commit.

    Incident 002/003E: the review commit line legitimately gained a
    practice-vs-legacy ternary (``data = incident002Practice ? await
    SRS.practiceAnswer(...) : await SRS.review(...)``), so the exact prior
    literal ``data = await SRS.review(...)`` no longer appears contiguously.
    This checks the same two invariants the original assertions protected --
    the call is still reachable with its exact legacy argument list, it is
    still the value assigned to ``data``, and the unit-progress report still
    precedes it in source order -- without depending on the surrounding
    expression's exact literal formatting.
    """
    source = INDEX_PATH.read_text(encoding="utf-8")
    unit_progress_match = re.search(
        r"SRS\.reportUnitProgress\(currentQ\.id,unit\)", source,
    )
    assert unit_progress_match, "SRS.reportUnitProgress call site is missing"
    review_commit_match = re.search(
        r"data\s*=\s*(?:incident002Practice\s*\?[\s\S]*?:\s*)?"
        r"await SRS\.review\(currentQ\.id,grade,unit,unitDone,reviewMetadata\);",
        source,
    )
    assert review_commit_match, (
        "the legacy SRS.review(...) commit, assigned to `data`, is missing "
        "or no longer has its exact historical argument list"
    )
    assert unit_progress_match.start() < review_commit_match.start(), (
        "SRS.reportUnitProgress must still be called upstream of the review "
        "commit that decides whether this answer was accepted"
    )
    assert "_quarantineRejectedAnswer" in SRS_PATH.read_text(encoding="utf-8")


def test_null_revision_parser_failure_uses_opaque_fingerprint_and_closes_loop():
    source = SRS_PATH.read_text(encoding="utf-8")
    script = f"""
globalThis.window = {{
  ReviewTransport: {{ legacyReview: async () => ({{
    error: 'judge_unavailable',
    failure_class: 'DETERMINISTIC_PARSER_FAILURE',
    reason_code: 'question_content_parser_failure',
    retryable: false, question_id: 431, question_revision: null,
    session_question_fingerprint: 'fp-431-v1'
  }}) }}
}};
{source}
(async () => {{
  const q431 = {{ id: 431, question_revision: null, session_question_fingerprint: 'fp-431-v1' }};
  const q432 = {{ id: 432, question_revision: 'rev-1', session_question_fingerprint: 'fp-432' }};
  SRS.clearSessionQuarantine();
  await SRS.review(431, 0, null, false, {{}});
  const quarantined = SRS.isQuestionQuarantined(431, 'fp-431-v1');
  const first = SRS.findNextAvailableQuestion([q431, q432], q431, 1)?.id ?? null;
  const second = SRS.findNextAvailableQuestion([q431, q432], q432, 1)?.id ?? null;
  console.log(JSON.stringify({{ quarantined, first, second }}));
}})().catch(error => {{ console.error(error); process.exitCode = 1; }});
"""
    result = _run_node(script)
    assert result == {"quarantined": True, "first": 432, "second": 432}


def test_client_side_invalidity_and_unclassified_legacy_error_fail_closed():
    source = SRS_PATH.read_text(encoding="utf-8")
    script = f"""
globalThis.window = {{
  ReviewTransport: {{ legacyReview: async (_qid, _grade, _unit, _done, metadata) => metadata }}
}};
{source}
(async () => {{
  const q431 = {{ id: 431, question_revision: null, session_question_fingerprint: 'fp-431' }};
  SRS.clearSessionQuarantine();
  const client = await SRS.review(431, 0, null, false, {{
    error: 'malformed_answer', failure_class: 'CLIENT_ANSWER_INVALID',
    retryable: false, question_id: 431, question_revision: null,
    session_question_fingerprint: 'fp-431'
  }});
  const clientQuarantined = SRS.isQuestionQuarantined(431, 'fp-431');
  const legacy = await SRS.review(431, 0, null, false, {{
    error: 'malformed_answer', retryable: false, question_id: 431,
    question_revision: null, session_question_fingerprint: 'fp-431'
  }});
  const legacyQuarantined = SRS.isQuestionQuarantined(431, 'fp-431');
  console.log(JSON.stringify({{
    clientOk: client.ok === undefined,
    clientQuarantined,
    legacyOk: legacy.ok === undefined,
    legacyQuarantined,
    revision: SRS.questionRevision(q431)
  }}));
}})().catch(error => {{ console.error(error); process.exitCode = 1; }});
"""
    result = _run_node(script)
    assert result == {
        "clientOk": True,
        "clientQuarantined": False,
        "legacyOk": True,
        "legacyQuarantined": False,
        "revision": "fp-431",
    }


def test_same_id_changed_payload_fingerprint_is_independent_and_session_reset_clears_it():
    source = SRS_PATH.read_text(encoding="utf-8")
    script = f"""
globalThis.window = {{}};
{source}
const oldQuestion = {{ id: 431, question_revision: null, session_question_fingerprint: 'fp-old' }};
const newQuestion = {{ id: 431, question_revision: null, session_question_fingerprint: 'fp-new' }};
SRS.clearSessionQuarantine();
const attached = SRS.quarantineQuestion(431, 'fp-old');
const oldSuppressed = SRS.isQuestionQuarantined(431, SRS.questionRevision(oldQuestion));
const newSuppressed = SRS.isQuestionQuarantined(431, SRS.questionRevision(newQuestion));
SRS.clearSessionQuarantine();
const cleared = SRS.isQuestionQuarantined(431, 'fp-old');
console.log(JSON.stringify({{ attached, oldSuppressed, newSuppressed, cleared }}));
"""
    result = _run_node(script)
    assert result == {
        "attached": True,
        "oldSuppressed": True,
        "newSuppressed": False,
        "cleared": False,
    }
