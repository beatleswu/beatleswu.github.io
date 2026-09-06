"""Focused W1-C4 contracts for the Zone 3 Lord result presenter."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
I18N = ROOT / "i18n.js"
MANIFEST = ROOT / "deploy/canonical-e10-zone3-static-pack-manifest.json"

SUCCESS_BACKPLATE = (
    "/assets/e10/art/zone3/lord_trial/"
    "zone3_lord_04_first_star_success_backplate.webp"
)
SUCCESS_PORTRAIT = (
    "/assets/e10/art/zone3/lord_trial/"
    "zone3_lord_06_success_lord_portrait.webp"
)
FAILURE_BACKPLATE = (
    "/assets/e10/art/zone3/lord_trial/"
    "zone3_lord_03_failure_backplate.webp"
)

EXPECTED_FAILURE_COPY = {
    "kicker": "領主試煉",
    "title": "領主挑戰失敗",
    "body": "領主尚未被擊敗。再答對 30 題後即可再次挑戰。",
    "info": "目前進度已保留；返回修行不會重複通關或獎勵。",
    "cta": "去修行",
}

EXPECTED_ASSET_SHA256 = {
    SUCCESS_BACKPLATE: "4cd9570539bf9253da800031c78465f90f18119db85654ced2375a181a15898f",
    SUCCESS_PORTRAIT: "13b4437bd72de85d51ba377264cdb8a11bac40b8e21d3e475cb511b4f19e7827",
    FAILURE_BACKPLATE: "73e5760c120f0c3bc0a4b720b7fbc096c6c1abb3d0d1c29a64c52b2d8f4aed0c",
}


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _zone3_result_block() -> str:
    text = _text(INDEX)
    start = text.index("function showZone3LordResultCard")
    end = text.index("document.addEventListener('journey:zone3-command'", start)
    return text[start:end]


def test_zone3_success_result_binds_approved_backplate_and_portrait() -> None:
    text = _text(INDEX)
    result = _zone3_result_block()

    assert "result-zone3-win" in result
    assert SUCCESS_BACKPLATE in result
    assert "overlay.dataset.assetSlot = passed" in result
    assert "'Z3_FIRST_STAR_SUCCESS_BACKPLATE'" in result
    assert f"successPortrait.src = '{SUCCESS_PORTRAIT}'" in result
    assert "successPortrait.hidden = false" in result
    assert f"background-image: url('{SUCCESS_BACKPLATE}')" in text
    assert 'id="zone3-success-lord-portrait"' in text


def test_zone3_failure_result_uses_dedicated_state_and_exact_copy_keys() -> None:
    result = _zone3_result_block()
    i18n = _text(I18N)

    assert "result-zone3-fail" in result
    assert FAILURE_BACKPLATE in result
    assert "'Z3_LORD_FAILURE_BACKPLATE'" in result
    assert "e9.zone3.lord_failure.kicker" in result
    assert "e9.zone3.lord_failure.title" in result
    assert "e9.zone3.lord_failure.body" in result
    assert "e9.zone3.lord_failure.info" in result
    assert "e9.zone3.lord_failure.cta" in result
    assert f"background-image: url('{FAILURE_BACKPLATE}')" in _text(INDEX)
    for value in EXPECTED_FAILURE_COPY.values():
        assert value in i18n


def test_zone3_failure_never_reuses_unlock_or_battlefield_presentation() -> None:
    result = _zone3_result_block()

    assert "e9.zone3.battlefield_boss." not in result
    assert "index.boss." not in result
    assert "領主封印已解除" not in result
    assert "古老封印正在崩解，領主即將現身。" not in result
    assert "開始決戰" not in result
    assert "btn.textContent = I18n.t('e9.zone3.lord_failure.cta')" in result


def test_zone3_failure_cta_returns_to_training_without_starting_lord() -> None:
    result = _zone3_result_block()

    assert "window.location.href = firstQuestionHref(zone);" in result
    assert "confirmBossBattle" not in result
    assert "_startBossBattleNow" not in result
    assert "_zone3ReturnToMap('lord_result')" not in result


def test_zone3_result_state_owns_and_clears_result_art_metadata() -> None:
    text = _text(INDEX)
    result = _zone3_result_block()

    assert "overlay.dataset.zone3Presentation = 'result';" in result
    assert "overlay.dataset.zone3LordAsset = passed" in result
    assert "overlay.dataset.assetStatus = 'OWNER_APPROVED_PRESENT';" in result
    assert "delete overlay.dataset.zone3LordAsset;" not in result
    assert "function _hideZone3ResultPortrait()" in text
    assert "_hideZone3ResultPortrait();" in text
    assert "successPortrait.hidden = true" in result


def test_zone3_challenge_art_remains_separate_from_result_art() -> None:
    text = _text(INDEX)
    challenge_start = text.index("function showZone3LordChallengeCard")
    challenge_end = text.index("function hideBossCinematic", challenge_start)
    challenge = text[challenge_start:challenge_end]

    assert "/assets/e10/art/zone3/lord_trial/zone3_lord_02_challenge_backplate.webp" in challenge
    assert SUCCESS_BACKPLATE not in challenge
    assert FAILURE_BACKPLATE not in challenge


def test_approved_zone3_result_assets_are_unchanged_and_manifested() -> None:
    for runtime_path, expected_sha256 in EXPECTED_ASSET_SHA256.items():
        path = ROOT / runtime_path.lstrip("/")
        assert path.is_file(), runtime_path
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha256

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest_paths = {entry["path"] for entry in manifest["files"]}
    assert {path.lstrip("/") for path in EXPECTED_ASSET_SHA256} <= manifest_paths


def test_zone3_result_css_is_scoped_to_zone3_result_states() -> None:
    text = _text(INDEX)

    assert '.boss-cinematic.result-zone3-win[data-zone-key="k16_20"] .boss-cinematic-scene' in text
    assert '.boss-cinematic.result-zone3-fail[data-zone-key="k16_20"] .boss-cinematic-scene' in text
    assert '.boss-cinematic.result-zone3-win[data-zone-key="k16_20"] #zone3-success-lord-portrait' in text
    assert "GENERIC_MODAL_REFACTOR" not in text
