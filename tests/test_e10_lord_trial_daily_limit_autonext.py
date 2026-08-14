"""Release-safety contracts for Lord Trial auto-advance at the daily wall.

The normal free-practice limit remains a client/server gate, while an active
server-owned Boss attempt is allowed to submit and load its signed queue.  A
failed Boss review must never be treated as a successful answer locally.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")


def _function_block(name: str, end_name: str) -> str:
    start = INDEX.index(f"function {name}")
    end = INDEX.index(f"function {end_name}", start)
    return INDEX[start:end]


def test_daily_limit_helper_is_the_single_boss_exemption_predicate():
    helper = _function_block("_dailyLimitBlocksCurrentFlow", "_dailyLimitStorageKey")
    assert "_dailyLimitReached" in helper
    assert "!_challengeId" in helper
    assert "!_bossMode" in helper

    for function_name, end_name in (
        ("submitSRS", "loadQuestion"),
        ("loadQuestion", "onBoardClick"),
        ("nextQuestion", "prevQuestion"),
    ):
        block = _function_block(function_name, end_name)
        assert "_dailyLimitBlocksCurrentFlow()" in block

    lang_start = INDEX.index("window.onLangChange = () =>")
    lang = INDEX[lang_start:INDEX.index("const E9_INLINE_DEBUG_HOSTNAMES", lang_start)]
    assert "_dailyLimitBlocksCurrentFlow()" in lang


def test_boss_daily_limit_error_fails_closed_without_local_progression():
    submit = _function_block("submitSRS", "loadQuestion")
    start = submit.index("}else if(data.error==='daily_limit')")
    end = submit.index("}else{", start)
    daily_limit_branch = submit[start:end]
    assert "if (_bossMode)" in daily_limit_branch
    assert "_handleBossAnswer" not in daily_limit_branch
    assert "no progress recorded" in daily_limit_branch
    assert "setMsg" in daily_limit_branch

    # Successful Boss reviews still have exactly one advancement authority.
    assert submit.count("await _handleBossAnswer(grade, bossAnswerContext);") == 1


def test_load_question_boss_exempts_both_daily_limit_guards():
    load = _function_block("loadQuestion", "onBoardClick")
    assert load.count("_dailyLimitBlocksCurrentFlow()") >= 2
    assert "if(_dailyLimitReached && !_challengeId)" not in load


def test_shared_next_is_not_a_boss_authority_and_is_not_misleading():
    next_block = _function_block("nextQuestion", "prevQuestion")
    boss_guard = next_block[next_block.index("if (_bossMode)"):next_block.index("if (mapBattleV1Transition)")]
    assert "_syncBossNextButton();" in boss_guard
    assert "return;" in boss_guard
    assert "loadQuestion" not in boss_guard

    sync_start = INDEX.index("function _syncBossNextButton()")
    sync = INDEX[sync_start:INDEX.index("async function _loadBossQuestion", sync_start)]
    assert "next.disabled = _bossMode;" in sync
    assert "next.hidden = _bossMode;" in sync
    assert "aria-disabled" in sync


def test_server_daily_limit_is_blocked_only_for_non_boss_questions():
    guard_start = APP.index(
        "active_boss_question = (not internal and _adventure_boss_question_is_active(qid))"
    )
    guard = APP[guard_start:guard_start + 1500]
    assert "if today_count >= _eff_limit and not active_boss_question:" in guard
    assert "if today_count >= _eff_limit:" not in guard
    assert "_validate_adventure_boss_review_context" in APP


def test_server_active_boss_scope_rejects_expired_or_out_of_queue_questions():
    start = APP.index("def _adventure_boss_question_is_active")
    end = APP.index("# 每關綁定的劇情主線書", start)
    active = APP[start:end]
    assert "session.get('adventure_boss_exam')" in active
    assert "question_id in question_ids" in active
    assert "BOSS_ATTEMPT_MAX_MINUTES" in active
    assert "attempt_id" in active
