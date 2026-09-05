"""Static contracts for the W1-03 Zone 3 Owner visual-repair gate."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
RUNNER = ROOT / "tests" / "e2e" / "run_w1_03_journey_zone3_owner_human_acceptance_visual_repair_013.mjs"
LORD_ART = "/assets/e10/art/zone3/lord_trial/zone3_lord_02_challenge_backplate.webp"


def test_replay_is_explicitly_presentation_only_and_hides_first_clear_fields() -> None:
    index = INDEX.read_text(encoding="utf-8")
    assert 'data-zone3-presentation-only="true"' in index
    assert "overlay.dataset.zone3PresentationOnly = presentationOnly ? 'true' : 'false';" in index
    assert "overlay.dataset.zone3PresentationOnly = mode === 'manual_replay' ? 'true' : 'false';" in index
    assert "overlay.classList.remove('ready');" in index
    for selector in (
        ".boss-cinematic-kicker",
        ".boss-cinematic-title",
        ".boss-cinematic-books",
        ".boss-cinematic-progress",
        ".boss-cinematic-rules",
        ".boss-reward-presentation",
    ):
        assert f'#boss-cinematic[data-zone3-presentation-only="true"] {selector}' in index


def test_lord_rechallenge_uses_the_existing_canonical_backplate_and_cta() -> None:
    index = INDEX.read_text(encoding="utf-8")
    lord_start = index.index("function showZone3LordChallengeCard")
    lord_end = index.index("function hideBossCinematic", lord_start)
    lord = index[lord_start:lord_end]
    assert LORD_ART in lord
    assert "overlay.dataset.zone3LordAsset = LORD_CHALLENGE" not in lord
    assert "overlay.dataset.zone3PresentationOnly = 'false';" in lord
    assert "btn.onclick = confirmBossBattle;" in lord


def test_first_clear_result_branch_remains_distinct_from_replay() -> None:
    index = INDEX.read_text(encoding="utf-8")
    result_start = index.index("function showZone3LordResultCard")
    result_end = index.index("document.addEventListener('journey:zone3-command'", result_start)
    result = index[result_start:result_end]
    assert "const replay = result?.replay === true;" in result
    assert "I18n.t('e9.zone3.clear_reward.title')" in result
    assert "I18n.t('e9.zone3.return.body')" in result
    assert "overlay.dataset.zone3PresentationOnly = 'false';" in result


def test_owner_runner_is_bounded_across_four_viewports_and_two_locales() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    for viewport, width, height in (
        ("desktop", 1920, 1080),
        ("ipad_landscape", 1180, 820),
        ("ipad_portrait", 820, 1180),
        ("mobile_portrait", 390, 844),
    ):
        assert f"{viewport}: Object.freeze({{ width: {width}, height: {height} }})" in runner
    assert "zh-TW" in runner and "en-US" in runner
    assert "E2E_PRESENTATION_FAILURE_ONLY" in runner
    assert "page.waitForTimeout" not in runner
    assert "test.skip" not in runner
    assert "xfail" not in runner.lower()
    assert "intentional owner-acceptance presentation negative control" in runner
