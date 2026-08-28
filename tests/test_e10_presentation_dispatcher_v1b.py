"""Independent B1B contracts for the future PresentationDispatcher.

This file intentionally runs against the pre-implementation canonical base.
The expected red is limited to missing future asset/delegation/packaging
requirements.  It never imports app.py or contacts a backend.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = "f9554b871eec580746b840e5d9df4278a695b464"
PRESENTATION_PATH = ROOT / "js" / "game" / "presentation_dispatcher.js"
NODE_CONTRACT = ROOT / "tests" / "e2e" / "run_e10_presentation_dispatcher_contract.mjs"
SRS_PATH = ROOT / "srs.js"
REVIEW_TRANSPORT_PATH = ROOT / "js" / "game" / "review_transport.js"
INDEX_PATH = ROOT / "index.html"
LORD_CONTROLLER_PATH = ROOT / "js" / "game" / "lord_trial_controller.js"
APP_PATH = ROOT / "app.py"
DOCKERFILE_PATH = ROOT / "Dockerfile"
BUILD_MANIFEST_PATH = ROOT / "deploy" / "build-manifest.json"
STATIC_INVENTORY_PATH = ROOT / "deploy" / "live-static-asset-inventory.json"
SW_PATH = ROOT / "sw.js"
DISPATCHER_ASSET = "js/game/presentation_dispatcher.js"
AUTHORIZED_DISPATCHER_SCRIPT_SRC = "/js/game/presentation_dispatcher.js?v=20260816e10v1bb1"
AUTHORIZED_EFFECTS_SCRIPT_SRC = "/js/game/presentation_effects_b2.js?v=20260817e10v1bb2"
AUTHORIZED_REVIEW_TRANSPORT_SCRIPT_SRC = "/js/game/review_transport.js?v=20260817e10v1bb3"
AUTHORIZED_GAME_SESSION_SCRIPT_SRC = "/js/game/game_session.js"
BASE_SRS_SCRIPT_SRC = "/srs.js?v=20260622i18n1"
B1_SRS_SCRIPT_SRC = "/srs.js?v=20260816e10v1bb1"
# E10_LORD_REPLAY_ISOLATED_RELEASE_001: world_stage.js's own content changed
# (generic replay eligibility, see js/e9/world_stage.js), and its stale
# 20260801 cache-busting tag was left unbumped -- a returning user's cached
# copy would never receive the new logic. This release corrects it to the
# same release tag as the new cinematic_replay.js module it now cooperates
# with (RELEASE-CACHE-FIX-01).
BASE_WORLD_STAGE_SCRIPT_SRC = "/js/e9/world_stage.js?v=20260801e10art1"
E042_WORLD_STAGE_SCRIPT_SRC = "/js/e9/world_stage.js?v=20260828e042s1"
# E10_REPLAY_STORY_CROSS_SURFACE_IPAD_HOTFIX_002: right_cards.js's own content
# changed too (the landscape Replay Story surface stopped deciding visibility
# from a hardcoded zone-key allowlist and now asks the shared availability
# authority). It therefore needs its own new cache identity for exactly the
# same reason world_stage.js did above -- a returning iPad user's cached copy
# would otherwise keep the dead/absent button.
BASE_RIGHT_CARDS_SCRIPT_SRC = "/js/e9/right_cards.js?v=20260801e10art1"
E040_S1_RIGHT_CARDS_SCRIPT_SRC = "/js/e9/right_cards.js?v=20260828e040s1"
SYNTHETIC_SECRET = "e10-v1b-b1b-contract-test-secret"
B2_DISPATCH_INSERTION = """\
    const b2Dispatcher = window.PresentationDispatcher;
    const b2Effects = window.GoOdysseyPresentationEffectsB2;
    if (b2Dispatcher && typeof b2Dispatcher.dispatchEffects === 'function' && b2Effects) {
        const scope = _createB2PresentationScope(data, lordController);
        b2Dispatcher.dispatchEffects(data, {
            adapter: b2Effects,
            dependencies: _createB2PresentationDependencies(scope),
            grade,
            scope,
            onError: failure => reportFailure(failure.stage, failure),
        });
        return;
    }
"""
B2_SUBMIT_SRS_CONTEXT = """\
        presentation_context: {
            mode: _bossMode ? 'lord' : 'normal',
            questionId: Number(bossAnswerContext?.questionId || currentQ.id),
            attemptId: _bossMode ? _bossAttemptId : null,
            lordIndex: _bossMode ? bossAnswerContext?.index : null,
            lifecycleGeneration: _mapBattleV1LifecycleGeneration,
        },
"""
B2_INDEX_FUNCTION_DELTAS = {
    "_dispatchCommittedReviewPresentation": B2_DISPATCH_INSERTION,
    "submitSRS": B2_SUBMIT_SRS_CONTEXT,
}
B2_INDEX_HELPER_FUNCTIONS = (
    "_createB2PresentationScope",
    "_createB2PresentationDependencies",
)

B3_SUBMIT_SRS_CHALLENGE_REJECTION = """\
                // Challenge mode stays unlocked, but a rejected review never advances.
                setMsg(I18n.t('index.srs.save_fail'), 'err');
"""
B3_BASE_SUBMIT_SRS_CHALLENGE_REJECTION = """\
                // 挑戰模式：不鎖定，直接進下一題
                if(grade>0){ srsDoneCount++; nextQuestion(); }
"""
B3_WRONG_ANSWER_REVIEW = """\
        if(currentQ&&!_dailyLimitReached&&window.ReviewTransport&&typeof window.ReviewTransport.review==='function'){
            const observerCommand={
                question_id:currentQ.id,
                grade:0,
                unit_name:null,
                unit_done:false,
                ..._currentReviewMetadata()
            };
            window.ReviewTransport.review(observerCommand).then(({payload:d})=>{if(d.error==='daily_limit'){_dailyLimitMax=d.limit||_dailyLimitMax;_applyDailyLimit();return;}if(d.error)return;_syncGuildQuestProgress();if(d.monster&&!_isAdventureZonePractice()){updateMonsterUI(d.monster);if(!d.monster.defeated)monsterSpeakTaunt(d.monster.type||_lastMonsterType);}if(d.player)updatePlayerHPUI(d.player);if(d.quest_updates)updateQuestPanel(d.quest_updates);}).catch(error=>{if(error?.kind==='REJECTED'&&error.code==='daily_limit'){const d=error.payload||{};_dailyLimitMax=d.limit||_dailyLimitMax;_applyDailyLimit();}});
        }
"""
B3_BASE_WRONG_ANSWER_REVIEW = """\
        if(currentQ&&!_dailyLimitReached)fetch('/api/srs/review',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify({question_id:currentQ.id,grade:0,unit_name:null,unit_done:false,..._currentReviewMetadata()})}).then(r=>r.json()).then(d=>{if(d.error==='daily_limit'){_dailyLimitMax=d.limit||_dailyLimitMax;_applyDailyLimit();return;}if(d.error)return;_syncGuildQuestProgress();if(d.monster&&!_isAdventureZonePractice()){updateMonsterUI(d.monster);if(!d.monster.defeated)monsterSpeakTaunt(d.monster.type||_lastMonsterType);}if(d.player)updatePlayerHPUI(d.player);if(d.quest_updates)updateQuestPanel(d.quest_updates);}).catch(()=>{});
"""
B3_INDEX_REPLACEMENTS = {
    "submitSRS": (
        B3_SUBMIT_SRS_CHALLENGE_REJECTION,
        B3_BASE_SUBMIT_SRS_CHALLENGE_REJECTION,
    ),
    "onBoardClick": (B3_WRONG_ANSWER_REVIEW, B3_BASE_WRONG_ANSWER_REVIEW),
}

B4_SUBMIT_SRS_REVIEW_GUARD = """\
    const reviewMetadata = _currentReviewMetadata();
    const identity = _gameSession.adoptQuestion(currentQ, {
        mode: _bossMode ? 'lord' : 'normal',
        attemptId: _bossMode ? _bossAttemptId : null,
        index: _bossMode ? _bossIndex : null,
        lifecycleGeneration: _mapBattleV1LifecycleGeneration,
        reviewMetadata,
    });
    if (!_gameSession.beginReview(identity)) return;
"""
B6_SUBMIT_SRS_REVIEW_GUARD = """\
    const reviewMetadata = _currentReviewMetadata();
    const identity = _gameSession.adoptQuestion(currentQ, {
        ..._modeContext.identityOptions(currentQ),
        lifecycleGeneration: _mapBattleV1LifecycleGeneration,
        reviewMetadata,
    });
    if (!_gameSession.beginReview(identity)) return;
"""
B1_SUBMIT_SRS_REVIEW_GUARD = """\
    const reviewRequestKey = `${_bossMode ? (_bossAttemptId || 'active') + ':' + _bossIndex : 'practice'}:${Number(currentQ.id)}`;
    if (_reviewRequestInFlightKey === reviewRequestKey) return;
    _reviewRequestInFlightKey = reviewRequestKey;
"""
B4_SUBMIT_SRS_REVIEW_CALL = """\
        data = await SRS.review(currentQ.id,grade,unit,unitDone,reviewMetadata);
"""
B1_SUBMIT_SRS_REVIEW_CALL = """\
        data = await SRS.review(currentQ.id,grade,unit,unitDone,_currentReviewMetadata());
"""
B4_SUBMIT_SRS_PRESENTATION_CONTEXT = """\
        presentation_context: _gameSession.presentationContext(identity),
"""
B6_SUBMIT_SRS_PRESENTATION_CONTEXT = """\
        presentation_mode: _modeContext.presentationMode(),
"""
B4_SUBMIT_SRS_FINALLY = """\
    })().finally(() => _gameSession.endReview(identity));
"""
B1_SUBMIT_SRS_FINALLY = """\
    })().finally(() => {
        if (_reviewRequestInFlightKey === reviewRequestKey) _reviewRequestInFlightKey = null;
    });
"""
B4_GAME_SESSION_INITIALIZATION = """\
const _gameSession = window.GoOdysseyGameSession.create({
    getCurrentQuestion: () => currentQ,
    getLifecycleGeneration: () => _mapBattleV1LifecycleGeneration,
});
"""
B4_CURRENT_REVIEW_STATE = """\
let _bossTransitionInFlightKey = null;
let _bossLastSettledKey = null;
let _lordTrialController = null;
"""
B1_REVIEW_STATE = """\
let _bossTransitionInFlightKey = null;
let _bossLastSettledKey = null;
let _reviewRequestInFlightKey = null;
let _lordTrialController = null;
"""

B051_SUBMIT_SRS_BOSS_ARGUMENT = """\
    const bossAnswer = arguments.length > 1 ? arguments[1] : null;
"""
B051_SUBMIT_SRS_BOSS_METADATA = """\
    if (_bossMode && bossAnswer) reviewMetadata.boss_answer = bossAnswer;
"""
B051_LORD_VERDICT_GUARD = """\
            const authoritativeVerdict = reviewResult.boss_verdict;
            if (!authoritativeVerdict
                || (authoritativeVerdict.verdict !== 'AUTHORITATIVE_PASS'
                    && authoritativeVerdict.verdict !== 'AUTHORITATIVE_FAIL')) {
                return { advanced: false, reason: 'server_verdict_missing' };
            }

"""


def _normalize_b051_submit_srs(current_function: str) -> str:
    for fragment in (B051_SUBMIT_SRS_BOSS_ARGUMENT, B051_SUBMIT_SRS_BOSS_METADATA):
        assert current_function.count(fragment) == 1
        current_function = current_function.replace(fragment, "", 1)
    assert current_function.count("if(!_bossMode&&grade>=3&&unit){") == 1
    current_function = current_function.replace(
        "if(!_bossMode&&grade>=3&&unit){", "if(grade>=3&&unit){", 1
    )
    b051_correct_tally = """\
        _todayTotal++;
        if (data.boss_verdict?.verdict === 'AUTHORITATIVE_PASS') _todayCorrect++;
"""
    assert current_function.count(b051_correct_tally) == 1
    current_function = current_function.replace(
        b051_correct_tally, "        _todayTotal++; if(grade>=3) _todayCorrect++;\n", 1
    )
    return current_function


def _normalize_b051_lord_controller(current_source: str) -> str:
    assert current_source.count(B051_LORD_VERDICT_GUARD) == 1
    current_source = current_source.replace(B051_LORD_VERDICT_GUARD, "", 1)
    assert current_source.count("index: submittedIndex, qid: submittedQuestionId,\n") == 2
    current_source = current_source.replace(
        "index: submittedIndex, qid: submittedQuestionId,\n",
        "index: submittedIndex, qid: submittedQuestionId, grade: submission.grade,\n",
        2,
    )
    b051_next_correct = """\
            const nextCorrect = Number(context.correct || 0)
                + (authoritativeVerdict.verdict === 'AUTHORITATIVE_PASS' ? 1 : 0);
"""
    assert current_source.count(b051_next_correct) == 1
    return current_source.replace(
        b051_next_correct,
        "            const nextCorrect = Number(context.correct || 0)\n"
        "                + (Number(submission.grade) >= 3 ? 1 : 0);\n",
        1,
    )

FROZEN_INDEX_FUNCTIONS = (
    "_dispatchCommittedReviewPresentation",
    "submitSRS",
    "_handleBossAnswer",
    "_loadBossQuestion",
    "_finishBossBattle",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _git_show(path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{BASE_SHA}:{path}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, f"HARNESS_FAILURE: git show failed for {path}"
    return result.stdout


def _extract_function(source: str, name: str) -> str:
    match = re.search(
        rf"(?:async\s+)?function\s+{re.escape(name)}\s*\([^)]*\)\s*\{{",
        source,
    )
    assert match, f"HARNESS_FAILURE: function {name} not found"
    # The regex above always ends its match on the function body's own
    # opening brace (`\)\s*\{` after the parameter list), so that brace is
    # necessarily the LAST "{" in the matched span. find() instead of
    # rfind() previously locked onto an earlier "{" belonging to a
    # destructured/default parameter (e.g. `function f(data, { onError } =
    # {}) {`), truncating the extracted body at that parameter's own closing
    # brace instead of the real function body.
    opening = source.rfind("{", match.start(), match.end())
    depth = 0
    quote = None
    escaped = False
    line_comment = False
    block_comment = False
    index = opening
    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""
        if line_comment:
            if char in "\r\n":
                line_comment = False
            index += 1
            continue
        if block_comment:
            if char == "*" and next_char == "/":
                block_comment = False
                index += 2
            else:
                index += 1
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char == "/" and next_char == "/":
            line_comment = True
            index += 2
            continue
        if char == "/" and next_char == "*":
            block_comment = True
            index += 2
            continue
        if char in "'\"`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[match.start() : index + 1]
        index += 1
    raise AssertionError(f"HARNESS_FAILURE: unterminated function {name}")


def _stable_js(source: str) -> str:
    return re.sub(r"\s+", " ", source).strip()


def _remove_function(source: str, name: str) -> str:
    function_source = _extract_function(source, name)
    assert source.count(function_source) == 1, (
        f"HARNESS_FAILURE: expected one function source for {name}"
    )
    function_line = function_source + "\n\n"
    assert source.count(function_line) == 1, (
        f"HARNESS_FAILURE: expected one newline after {name}"
    )
    return source.replace(function_line, "", 1)


def _normalize_b4_submit_srs(current_function: str, base_function: str) -> str:
    assert current_function.count(B6_SUBMIT_SRS_REVIEW_GUARD) == 1, (
        "HARNESS_FAILURE: expected one exact B6 ModeContext identity handoff"
    )
    current_function = current_function.replace(
        B6_SUBMIT_SRS_REVIEW_GUARD,
        B4_SUBMIT_SRS_REVIEW_GUARD,
        1,
    )
    assert current_function.count(B6_SUBMIT_SRS_PRESENTATION_CONTEXT) == 1, (
        "HARNESS_FAILURE: expected one exact B6 presentation context extension"
    )
    current_function = current_function.replace(B6_SUBMIT_SRS_PRESENTATION_CONTEXT, "", 1)
    for label, current_delta, base_delta in (
        (
            "review guard",
            B4_SUBMIT_SRS_REVIEW_GUARD,
            B1_SUBMIT_SRS_REVIEW_GUARD,
        ),
        (
            "SRS.review reviewMetadata argument",
            B4_SUBMIT_SRS_REVIEW_CALL,
            B1_SUBMIT_SRS_REVIEW_CALL,
        ),
        (
            "review finalizer",
            B4_SUBMIT_SRS_FINALLY,
            B1_SUBMIT_SRS_FINALLY,
        ),
    ):
        assert current_function.count(current_delta) == 1, (
            f"HARNESS_FAILURE: expected one exact B4 {label} delta in submitSRS"
        )
        assert base_function.count(base_delta) == 1, (
            f"HARNESS_FAILURE: expected one exact B1 {label} baseline in submitSRS"
        )
        current_function = current_function.replace(current_delta, base_delta, 1)

    assert current_function.count(B4_SUBMIT_SRS_PRESENTATION_CONTEXT) == 1, (
        "HARNESS_FAILURE: expected one exact B4 presentation context delta in submitSRS"
    )
    assert current_function.count(B2_SUBMIT_SRS_CONTEXT) == 0, (
        "HARNESS_FAILURE: B4 presentation context already normalized unexpectedly"
    )
    current_function = current_function.replace(
        B4_SUBMIT_SRS_PRESENTATION_CONTEXT,
        B2_SUBMIT_SRS_CONTEXT,
        1,
    )
    return current_function


_EXTERNAL_SCRIPT_TAG_RE = re.compile(
    r"<script\b(?=[^>]*\bsrc\s*=)[^>]*>.*?</script\s*>",
    re.IGNORECASE | re.DOTALL,
)
_SCRIPT_SRC_ATTRIBUTE_RE = re.compile(
    r"\bsrc\s*=\s*(['\"])(?P<src>.*?)\1",
    re.IGNORECASE | re.DOTALL,
)
_JS_IDENTIFIER = r"[A-Za-z_$][A-Za-z0-9_$]*"
_PRESENTATION_ALIAS_DECLARATION_RE = re.compile(
    rf"\b(?:const|let|var)\s+(?P<alias>{_JS_IDENTIFIER})\s*=\s*(?P<initializer>[^;]+);",
    re.DOTALL,
)


def _external_script_tags(source: str) -> list[tuple[str, str]]:
    entries = []
    for match in _EXTERNAL_SCRIPT_TAG_RE.finditer(source):
        tag = match.group(0)
        src_match = _SCRIPT_SRC_ATTRIBUTE_RE.search(tag)
        assert src_match, "HARNESS_FAILURE: external script tag has no src value"
        entries.append((tag, src_match.group("src")))
    return entries


def _replace_script_src(tag: str, old_src: str, new_src: str) -> str:
    match = _SCRIPT_SRC_ATTRIBUTE_RE.search(tag)
    assert match and match.group("src") == old_src, "HARNESS_FAILURE: unexpected script src"
    return tag[: match.start("src")] + new_src + tag[match.end("src") :]


def _remove_external_script_tag(source: str, tag: str) -> str:
    assert source.count(tag) == 1, "HARNESS_FAILURE: expected one authorized script tag"
    whole_line = re.compile(rf"(?m)^[ \t]*{re.escape(tag)}[ \t]*(?:\r?\n|$)")
    match = whole_line.search(source)
    if match:
        return source[: match.start()] + source[match.end() :]
    return source.replace(tag, "", 1)


def _verified_presentation_dispatcher_aliases(source: str) -> set[str]:
    aliases = set()
    for match in _PRESENTATION_ALIAS_DECLARATION_RE.finditer(source):
        initializer = re.sub(r"\s+", "", match.group("initializer"))
        if initializer in {
            "window.PresentationDispatcher",
            "window.PresentationDispatcher||null",
            "typeofwindow!=='undefined'?window.PresentationDispatcher:null",
            "typeofwindow===\"undefined\"?null:window.PresentationDispatcher",
        }:
            aliases.add(match.group("alias"))
    return aliases


def _contains_exact_json_value(value, expected: str) -> bool:
    if isinstance(value, str):
        return value == expected
    if isinstance(value, dict):
        return any(_contains_exact_json_value(item, expected) for item in value.values())
    if isinstance(value, list):
        return any(_contains_exact_json_value(item, expected) for item in value)
    return False


def _sw_identity(source: str) -> tuple[str, str]:
    version = re.search(r"const\s+VERSION\s*=\s*['\"]([^'\"]+)", source)
    asset = re.search(r"const\s+ASSET_IDENTITY\s*=\s*['\"]([^'\"]+)", source)
    assert version and asset, "HARNESS_FAILURE: SW identity constants not found"
    return version.group(1), asset.group(1)


def _run_node_contract() -> dict:
    node = shutil.which("node")
    if not node:
        pytest.fail("HARNESS_FAILURE: node executable is unavailable")
    environment = os.environ.copy()
    environment["SECRET_KEY"] = SYNTHETIC_SECRET
    result = subprocess.run(
        [node, str(NODE_CONTRACT)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode in {0, 2}, (
        "HARNESS_FAILURE: Node contract crashed\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines, f"HARNESS_FAILURE: Node contract emitted no JSON: {result.stderr!r}"
    report = json.loads(lines[-1])
    report["process_returncode"] = result.returncode
    return report


def test_node_contract_runner_reports_expected_base_state_or_validates_module():
    report = _run_node_contract()

    assert report["contract"] == "E10_FRONTEND_V1B_PRESENTATION_DISPATCHER_B1B"
    assert set(report["cases"]) == {
        "missing_data",
        "data_not_ok",
        "all_effects_succeed",
        "badge_callback_throws",
        "badge_state_dependency_throws",
        "badge_seen_sync_throws",
        "badge_seen_promise_rejects",
        "monster_callback_throws",
        "quest_callback_throws",
        "on_error_throws",
        "deterministic_result",
        "never_calls_review_transport",
        "never_calls_progression",
    }
    if report["status"] == "missing_asset":
        pytest.fail("EXPECTED_RED:PRESENTATION_DISPATCHER_ASSET_MISSING")
    assert report["status"] == "ready", report
    assert report["process_returncode"] == 0, report
    assert report["failures"] == [], report


def test_srs_review_is_the_only_review_transport_and_private_state_stays_in_srs():
    source = _read(SRS_PATH)
    transport_source = _read(REVIEW_TRANSPORT_PATH)
    assert source.count("/api/srs/review") == 0
    assert transport_source.count("/api/srs/review") == 2
    assert "requester('/api/srs/review'" in transport_source
    assert source.count("_reviewTransport.legacyReview(") == 1
    assert _read(INDEX_PATH).count("SRS.review(") == 1
    for private_name in (
        "_earned",
        "_badgeDefs",
        "_lsMerge",
        "_onBadge",
        "_onMonster",
        "_onQuest",
    ):
        assert private_name in source

    dispatch_body = _extract_function(source, "dispatchReviewPresentation")
    direct_calls = re.findall(
        r"(?:\bwindow\s*\.\s*)?\bPresentationDispatcher\s*\.\s*dispatch\s*\(",
        dispatch_body,
    )
    verified_aliases = _verified_presentation_dispatcher_aliases(source)
    alias_call_count = sum(
        len(
            re.findall(
                rf"\b{re.escape(alias)}\s*\.\s*dispatch\s*\(", dispatch_body
            )
        )
        for alias in verified_aliases
    )
    if len(direct_calls) + alias_call_count != 1:
        pytest.fail("EXPECTED_RED:SRS_NOT_YET_DELEGATING_TO_PRESENTATION_DISPATCHER")
    assert "/api/srs/review" not in dispatch_body


def test_presentation_dispatcher_has_no_transport_or_progression_authority():
    if not PRESENTATION_PATH.is_file():
        pytest.fail("EXPECTED_RED:PRESENTATION_DISPATCHER_ASSET_MISSING")
    source = _read(PRESENTATION_PATH)
    forbidden = (
        "/api/srs/review",
        "SRS.review",
        "nextQuestion",
        "_handleBossAnswer",
        "_loadBossQuestion",
        "_finishBossBattle",
        "LordReviewController",
        "GoOdysseyLordTrialController",
        "MapBattleV1",
        "settle",
    )
    for token in forbidden:
        assert token not in source, f"PresentationDispatcher contains forbidden authority: {token}"


def test_index_html_effect_bodies_and_lord_controller_are_frozen():
    current_index = _read(INDEX_PATH)
    base_index = _git_show("index.html")
    for name in FROZEN_INDEX_FUNCTIONS:
        current_function = _extract_function(current_index, name)
        base_function = _extract_function(base_index, name)
        if name == "submitSRS":
            current_function = _normalize_b051_submit_srs(current_function)
            current_function = _normalize_b4_submit_srs(current_function, base_function)
        b2_delta = B2_INDEX_FUNCTION_DELTAS.get(name)
        if b2_delta:
            assert current_function.count(b2_delta) == 1, (
                f"HARNESS_FAILURE: expected one exact B2 delta in {name}"
            )
            current_function = current_function.replace(b2_delta, "", 1)
        b3_replacement = B3_INDEX_REPLACEMENTS.get(name)
        if b3_replacement:
            b3_delta, base_b3_delta = b3_replacement
            assert current_function.count(b3_delta) == 1, (
                f"HARNESS_FAILURE: expected one exact B3 delta in {name}"
            )
            assert base_function.count(base_b3_delta) == 1, (
                f"HARNESS_FAILURE: expected one exact B3 base delta in {name}"
            )
            current_function = current_function.replace(b3_delta, base_b3_delta, 1)
        assert _stable_js(current_function) == _stable_js(
            base_function
        ), f"B1 changed frozen index function body: {name}"

    controller_source = _normalize_b051_lord_controller(_read(LORD_CONTROLLER_PATH))
    assert _stable_js(controller_source) == _stable_js(
        _git_show("js/game/lord_trial_controller.js")
    )


def test_b1_index_html_changes_are_script_loading_only():
    current_index = _read(INDEX_PATH)
    base_index = _git_show("index.html")
    current_scripts = _external_script_tags(current_index)
    base_scripts = _external_script_tags(base_index)
    current_srcs = [src for _, src in current_scripts]
    base_srcs = [src for _, src in base_scripts]

    assert AUTHORIZED_DISPATCHER_SCRIPT_SRC not in base_srcs
    assert current_srcs.count(AUTHORIZED_DISPATCHER_SCRIPT_SRC) == 1
    assert AUTHORIZED_EFFECTS_SCRIPT_SRC not in base_srcs
    assert current_srcs.count(AUTHORIZED_EFFECTS_SCRIPT_SRC) == 1
    assert AUTHORIZED_REVIEW_TRANSPORT_SCRIPT_SRC not in base_srcs
    assert current_srcs.count(AUTHORIZED_REVIEW_TRANSPORT_SCRIPT_SRC) == 1
    assert AUTHORIZED_GAME_SESSION_SCRIPT_SRC not in base_srcs
    assert current_srcs.count(AUTHORIZED_GAME_SESSION_SCRIPT_SRC) == 1
    assert current_srcs.index(AUTHORIZED_REVIEW_TRANSPORT_SCRIPT_SRC) < current_srcs.index(
        B1_SRS_SCRIPT_SRC
    )
    assert current_srcs.index(AUTHORIZED_GAME_SESSION_SCRIPT_SRC) < current_srcs.index(
        B1_SRS_SCRIPT_SRC
    )
    # B5 adds QuestionLoader/BoardRenderer and B6 adds ModeContext/GameBootstrap
    # after the four already-governed B1-B4 modules;
    # E10_ZONE_GENERIC_CINEMATIC_REPLAY_001 adds the generic cinematic replay
    # model as the ninth governed browser module.
    assert len(current_srcs) == len(base_srcs) + 9
    assert any(src.startswith("/js/game/question_loader.js") for src in current_srcs)
    assert any(src.startswith("/js/game/board_renderer.js") for src in current_srcs)
    assert any(src.startswith("/js/game/mode_context.js") for src in current_srcs)
    assert any(src.startswith("/js/game/game_bootstrap.js") for src in current_srcs)
    assert any(src.startswith("/js/game/cinematic_replay.js") for src in current_srcs)
    assert base_srcs.count(BASE_SRS_SCRIPT_SRC) == 1
    assert current_srcs.count(B1_SRS_SCRIPT_SRC) == 1
    assert current_srcs.count(BASE_SRS_SCRIPT_SRC) == 0

    current_without_dispatcher = [
        src
        for src in current_srcs
        if src
        not in {
            AUTHORIZED_DISPATCHER_SCRIPT_SRC,
            AUTHORIZED_EFFECTS_SCRIPT_SRC,
            AUTHORIZED_REVIEW_TRANSPORT_SCRIPT_SRC,
            AUTHORIZED_GAME_SESSION_SCRIPT_SRC,
        }
        and not src.startswith("/js/game/question_loader.js")
        and not src.startswith("/js/game/board_renderer.js")
        and not src.startswith("/js/game/mode_context.js")
        and not src.startswith("/js/game/game_bootstrap.js")
        and not src.startswith("/js/game/cinematic_replay.js")
    ]
    assert E042_WORLD_STAGE_SCRIPT_SRC in current_srcs
    assert BASE_WORLD_STAGE_SCRIPT_SRC not in current_srcs
    assert E040_S1_RIGHT_CARDS_SCRIPT_SRC in current_srcs
    assert BASE_RIGHT_CARDS_SCRIPT_SRC not in current_srcs
    normalized_current_srcs = [
        BASE_SRS_SCRIPT_SRC if src == B1_SRS_SCRIPT_SRC
        else BASE_WORLD_STAGE_SCRIPT_SRC if src == E042_WORLD_STAGE_SCRIPT_SRC
        else BASE_RIGHT_CARDS_SCRIPT_SRC if src == E040_S1_RIGHT_CARDS_SCRIPT_SRC
        else src
        for src in current_without_dispatcher
    ]
    assert normalized_current_srcs == base_srcs

    # B5 legitimately adds the QuestionLoader/BoardRenderer integration
    # surface to the inline application script.  The protected B1/B2/B3
    # function bodies are checked above; this assertion is intentionally
    # limited to the B1 script-loading contract rather than comparing the
    # entire post-B5 document to the pre-B5 base.
    assert current_srcs.index(AUTHORIZED_DISPATCHER_SCRIPT_SRC) < current_srcs.index(
        AUTHORIZED_EFFECTS_SCRIPT_SRC
    )


def test_b0_exact_route_remains_narrow_and_app_py_is_not_a_generic_static_bridge():
    app_source = _read(APP_PATH)
    assert "@app.route('/js/game/presentation_dispatcher.js')" in app_source
    assert "@app.route('/js/game/<path:" not in app_source
    assert "@app.route('/js/<path:" not in app_source


def test_future_dispatcher_is_explicitly_packaged_and_versioned():
    missing = []
    index_source = _read(INDEX_PATH)
    if not re.search(
        r"<script\b[^>]*\bsrc\s*=\s*['\"][^'\"]*js/game/presentation_dispatcher\.js(?:\?[^'\"]*)?['\"]",
        index_source,
        re.IGNORECASE,
    ):
        missing.append("PRESENTATION_DISPATCHER_NOT_SCRIPT_LOADED")

    dockerfile = _read(DOCKERFILE_PATH)
    if "COPY js/game/presentation_dispatcher.js ./js/game/presentation_dispatcher.js" not in dockerfile:
        missing.append("PRESENTATION_DISPATCHER_NOT_PACKAGED")

    build_manifest = json.loads(_read(BUILD_MANIFEST_PATH))
    if not _contains_exact_json_value(build_manifest, DISPATCHER_ASSET):
        missing.append("PRESENTATION_DISPATCHER_NOT_IN_BUILD_MANIFEST")

    inventory = json.loads(_read(STATIC_INVENTORY_PATH))
    eligible = set(inventory["eligible_files"]["entries"])
    required = set(inventory["required_in_generation"]["entries"])
    if DISPATCHER_ASSET not in eligible:
        missing.append("PRESENTATION_DISPATCHER_NOT_IN_STATIC_INVENTORY")
    if DISPATCHER_ASSET not in required:
        missing.append("PRESENTATION_DISPATCHER_NOT_REQUIRED_IN_GENERATION")

    if _sw_identity(_read(SW_PATH)) == _sw_identity(_git_show("sw.js")):
        missing.append("SW_IDENTITY_NOT_YET_BUMPED_FOR_B1")

    if missing:
        pytest.fail("EXPECTED_RED:" + ",".join(missing))
