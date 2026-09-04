"""Bounded contract checks for the Wave 2 first-play entry slice."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_landing_exposes_one_real_first_play_path() -> None:
    landing = _read("landing.html")

    assert 'data-w2-surface="learn-onboarding-first-play"' in landing
    assert 'id="first-play-title"' in landing
    assert landing.count('data-w2-cta="first-play-start"') == 2
    assert landing.count('href="/try"') >= 2
    assert 'data-entry="learn-first-play"' in landing
    assert 'data-i18n="rt.plBadge"' in landing
    assert 'data-i18n-html="rt.plTitle"' in landing
    assert 'data-i18n="rt.plSub"' in landing
    assert 'data-i18n="rt.plStart"' in landing
    assert 'data-i18n-aria-label="ld.path.h2"' in landing


def test_landing_first_play_copy_uses_existing_bilingual_authority() -> None:
    landing = _read("landing.html")
    i18n = _read("i18n.js")

    for key in (
        "rt.plBadge",
        "rt.plTitle",
        "rt.plSub",
        "rt.plStart",
        "ld.path.h2",
        "ld.s1.h3",
        "ld.s1.p",
        "ld.s2.h3",
        "ld.s2.p",
        "ld.s3.h3",
        "ld.s3.p",
    ):
        assert f"'{key}'" in i18n
        assert f'data-i18n="{key}"' in landing or f'data-i18n-html="{key}"' in landing or f'data-i18n-aria-label="{key}"' in landing


def test_rating_page_orients_the_first_go_interaction_without_new_authority() -> None:
    rating = _read("rating_test.html")

    assert 'data-w2-cta="begin-first-go-interaction"' in rating
    assert 'data-w2-surface="learn-onboarding-orientation"' in rating
    assert 'role="region" aria-labelledby="first-play-orientation-title"' in rating
    assert 'data-w2-interaction="first-go-board"' in rating
    assert 'data-w2-next-action="save-and-continue-learning"' in rating
    assert "function _renderFirstPlayOrientation()" in rating
    assert "_renderFirstPlayOrientation();" in rating
    assert "Your first Go step" in rating
    assert "你的第一步圍棋練習" in rating
    assert "Look for the move that feels right." in rating
    assert "先找出你覺得對的下一手。" in rating
    assert "Sign up to save your rank and start learning →" in rating
    assert "註冊保存棋力，開始學習 →" in rating


def test_first_play_stays_on_existing_public_trial_and_server_judged_board_flow() -> None:
    rating = _read("rating_test.html")

    assert "const TRIAL = location.pathname.replace(/\\/+$/,'') === '/try';" in rating
    assert "fetch('/api/rating_test/start'" in rating
    assert "fetch('/api/rating_test/answer'" in rating
    assert "function onBoardClick(bx, by)" in rating
    assert "if (!_isPlacement)" in rating
    assert "window.location.href = '/?after_placement=1';" in rating
    assert "showGoogleSignupModal();" in rating
