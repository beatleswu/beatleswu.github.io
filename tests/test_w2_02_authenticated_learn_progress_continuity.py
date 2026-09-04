"""Focused contracts for authenticated curriculum -> Learn continuity."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_curriculum_targets_the_existing_server_backed_learn_surface() -> None:
    curriculum = _read("curriculum.html")
    index = _read("index.html")

    assert "fetch('/api/quest-board/accept'" in curriculum
    assert "href: q.href || `/?discipline=${encodeURIComponent(discipline)}&stage=${encodeURIComponent(stage)}&quest=${encodeURIComponent(key)}&resume=1`" in curriculum
    assert "href: `/?discipline=${encodeURIComponent(discipline)}&stage=${encodeURIComponent(stage)}&resume=1`" in curriculum
    assert "`/api/quest-board/progress?quest_key=${encodeURIComponent(_guildQuestMode.key)}`" in index
    assert "returnBtn.onclick = () => { window.location.href = '/curriculum#quest-board'; };" in index


def test_curriculum_next_action_is_derived_from_server_state() -> None:
    curriculum = _read("curriculum.html")

    assert "banner.dataset.w2LearnState = state;" in curriculum
    assert "banner.dataset.w2ReturnState = returnedFromLearn ? 'server-synced' : 'initial';" in curriculum
    assert "action.dataset.w2NextAction = claimable ? 'claim-reward'" in curriculum
    assert ": accepted ? 'continue-learning-quest'" in curriculum
    assert ": 'open-quest-board';" in curriculum
    assert "returnStatus" in curriculum
    assert "Back from Learn; progress was refreshed from your account." in curriculum
    assert "已從學習頁回來；進度以帳號資料重新同步。" in curriculum


def test_bfcache_return_rehydrates_without_creating_client_completion() -> None:
    curriculum = _read("curriculum.html")

    assert "if (!event.persisted || location.protocol === 'file:') return;" in curriculum
    assert "if (new URLSearchParams(location.search).has('preview')) return;" in curriculum
    assert "init();" in curriculum
    assert "completed = true" not in curriculum
    assert "app.py" not in curriculum


def test_continuity_change_does_not_expand_into_protected_authority() -> None:
    curriculum = _read("curriculum.html")

    for forbidden in (
        "/api/paypal",
        "/api/newebpay",
        "zone_unlock",
        "loadout",
        "Shop",
    ):
        assert forbidden not in curriculum
