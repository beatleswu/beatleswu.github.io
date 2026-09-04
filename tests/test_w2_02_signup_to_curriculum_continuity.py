"""Bounded contracts for the W2 signup-to-curriculum continuation slice."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_trial_signup_preserves_the_authenticated_curriculum_target() -> None:
    rating = _read("rating_test.html")
    login = _read("login.html")

    assert "const _trialContinueTarget = '/curriculum';" in rating
    assert "function _trialSignupHref()" in rating
    assert "encodeURIComponent(_trialContinueTarget)" in rating
    assert "if (a) a.href = _trialSignupHref();" in rating
    assert "window.location.href = _trialContinueTarget;" in rating
    assert "_trialSignupHref(); return;" in rating
    assert "return (r&&r.ok)?(_safeLoginReturn()||'/?after_placement=1'):null;" in login
    assert "fetch('/api/rating_test/claim_anon'" in login


def test_curriculum_exposes_one_existing_first_learning_action() -> None:
    curriculum = _read("curriculum.html")

    assert "const CURRICULUM_CONTINUE_T =" in curriculum
    assert "function buildLearnContinuation(unitStats)" in curriculum
    assert "data-w2-surface = 'learn-onboarding-curriculum-continuity'" not in curriculum
    assert "banner.dataset.w2Surface = 'learn-onboarding-curriculum-continuity';" in curriculum
    assert "action.dataset.w2Cta = 'curriculum-first-action';" in curriculum
    assert "board.appendChild(buildLearnContinuation(unitStats));" in curriculum
    assert "action.href = target;" in curriculum
    assert "fetch('/api/quest-board/accept'" in curriculum
    assert "location.href = href;" in curriculum


def test_onboarding_continuity_keeps_locale_and_accessibility_contracts_bounded() -> None:
    landing = _read("landing.html")
    curriculum = _read("curriculum.html")

    # Keep the parent first-play test contract while making the HTML-bearing copy render as HTML.
    assert 'data-i18n="rt.plSub"' in landing
    assert 'data-i18n-html="rt.plSub"' in landing
    assert "role=\'region\'" not in curriculum
    assert "banner.setAttribute('role', 'region');" in curriculum
    assert "banner.setAttribute('aria-labelledby', 'learn-continuation-title');" in curriculum
    assert ".w2-learn-continuation .cb-action:focus-visible" in curriculum
    assert "_isEnCur() ? entry.en : entry.zh" in curriculum


def test_slice_does_not_introduce_server_or_commerce_authority() -> None:
    for name in ("rating_test.html", "login.html", "curriculum.html"):
        source = _read(name)
        assert "app.py" not in source
        assert "/api/paypal" not in source
        assert "/api/newebpay" not in source
