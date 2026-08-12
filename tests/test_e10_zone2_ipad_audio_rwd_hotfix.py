"""Regression contracts for the Zone 2 iPad portrait/audio hotfix.

These checks are intentionally deterministic source contracts.  They do not
pretend to prove real Safari playback; the Owner's real-device acceptance
remains the authority for audible output and portrait presentation.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")


def test_zone2_portrait_uses_same_shot_as_blurred_fill_not_flat_green_bars():
    assert ".film-shot::before" in INDEX
    assert "--film-backdrop-image" in INDEX
    assert "background-size: cover" in INDEX
    assert "filter: blur(24px)" in INDEX
    assert "object-fit: contain" in INDEX
    assert "background: #5f8f75" not in INDEX
    assert "shotEl.style.setProperty('--film-backdrop-image'" in INDEX


def test_explicit_play_animation_unlocks_reusable_safari_media_elements():
    assert "function _unlockIntroAudioFromGesture()" in INDEX
    assert "function _primeIntroMediaElement" in INDEX
    assert "await _unlockIntroAudioFromGesture()" in INDEX
    assert "audio.playsInline = true" in INDEX
    assert "_introAudioUnlockPromise" in INDEX
    assert "_introAudio = null" not in INDEX[INDEX.index("function _stopIntroFilm"):INDEX.index("function getCinematicNarratorVoices")]


def test_playback_failures_are_observable_without_cross_locale_fallback():
    assert "AUDIO_PLAY_ATTEMPT" in INDEX
    assert "AUDIO_PLAY_RESOLVED" in INDEX
    assert "AUDIO_PLAY_REJECTED" in INDEX
    assert "CURRENT_SHOT" in INDEX
    assert "LOCALE" in INDEX
    assert "VOICE_FILE" in INDEX
    assert "voice_reuse_after_gesture_unlock" in INDEX


def test_orientation_has_no_cinematic_restart_or_duplicate_audio_hook():
    # Orientation must be layout-only.  There is deliberately no listener
    # that calls replay/start/stop or increments the cinematic run id.
    assert "addEventListener('orientationchange'" not in INDEX
    assert "addEventListener(\"orientationchange\"" not in INDEX
    assert "replayIntroFilm()" in INDEX
