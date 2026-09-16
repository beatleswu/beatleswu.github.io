"""ZONE3_FINAL_AUDIO_PRONUNCIATION_OVERRIDE_PRESERVATION_002R.

Corrective for the latent production-generator defect discovered during
GO_ODYSSEY_TECHNICAL_DEBT_RELIABILITY_BATCH_001 (TD-002): a real Zone3
final-production manifest rebuild
(``_generate_final_production`` -> ``_write_final_audio_manifest`` ->
``_production_entry``) used to unconditionally set every entry's
``PRONUNCIATION_OVERRIDE`` to ``None``, discarding any Owner-approved
pronunciation repair already on disk.

TD-002 already fixed the *test* that exercised this (redirecting its write
target off the real, tracked manifest onto an isolated tmp_path copy). This
file is about the *generator itself*: proving the real rebuild path now
preserves existing overrides for the exact same canonical entry identity,
never invents or copies one across identities, and never touches approved
audio content or the real tracked manifest while doing it.

Identity is the generator's own already-deterministic fields: BEAT_ID (the
existing-entries lookup key), TEXT_HASH, CHARACTER, VOICE_ID - all four
must match exactly. No fuzzy matching, no inference.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
REAL_MANIFEST = ROOT / "assets" / "e10" / "audio" / "zone3" / "zone3-cinematic-audio-manifest.json"
SUBTITLE_PATH = ROOT / "assets" / "e10" / "i18n" / "zone3" / "zone3-cinematic-subtitles.json"


@pytest.fixture()
def generator(monkeypatch):
    tool_dir = ROOT / "tools" / "e10_zone3_audio"
    sys.path.insert(0, str(tool_dir))
    try:
        import generate_zone3_audio as module  # noqa: PLC0415
        yield module
    finally:
        sys.path.remove(str(tool_dir))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _real_manifest_entries() -> dict[str, dict]:
    document = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
    return {e["BEAT_ID"]: e for e in document["entries"]}


# --------------------------------------------------------------- 5. unit-level: new entry

def test_new_entry_without_prior_manifest_has_no_override(generator):
    beat = {
        "BEAT_ID": "Z3_UNIT_NEW_BEAT",
        "SHOT_ID": "SHOT99",
        "CHARACTER": "HERO",
        "I18N_KEY": "zone3.unit.new",
        "VISIBLE_TEXT": "a brand new line never seen before",
    }
    entry = generator._production_entry(beat, existing_entries={})
    assert entry["PRONUNCIATION_OVERRIDE"] is None


def test_new_entry_does_not_pick_up_a_different_identitys_override(generator):
    """The preservation fix must not accidentally copy an override from
    another dialogue/audio identity - existing_entries here holds overrides
    for OTHER beat ids only; this beat has none of its own."""
    beat = {
        "BEAT_ID": "Z3_UNIT_NEW_BEAT_2",
        "SHOT_ID": "SHOT99",
        "CHARACTER": "HERO",
        "I18N_KEY": "zone3.unit.new2",
        "VISIBLE_TEXT": "another brand new line",
    }
    existing_entries = _real_manifest_entries()  # has 4 real overrides, none for this BEAT_ID
    assert existing_entries  # sanity: the real manifest actually has entries
    entry = generator._production_entry(beat, existing_entries)
    assert entry["PRONUNCIATION_OVERRIDE"] is None


# --------------------------------------------------------- 6. unit-level: fail-closed identity

@pytest.mark.parametrize("mutate_field,new_value", [
    ("TEXT_HASH", "0" * 64),
    ("CHARACTER", "GRIK"),
    ("VOICE_ID", "some-other-voice-id"),
])
def test_mismatched_identity_field_fails_closed_no_override_copied(generator, mutate_field, new_value):
    """Same BEAT_ID (the lookup key) but one identity field differs - the
    override must NOT be copied. This is the ambiguous/nonmatching prior
    entry scenario: fail closed, never invent a fallback match."""
    existing_entries = _real_manifest_entries()
    beat_id = "Z3_S01_B001"  # a real BEAT_ID with a real override
    prior = existing_entries[beat_id]
    assert prior.get("PRONUNCIATION_OVERRIDE") is not None  # sanity

    beat = {
        "BEAT_ID": beat_id,
        "SHOT_ID": prior["SHOT_ID"],
        "CHARACTER": prior["CHARACTER"],
        "I18N_KEY": "zone3.unit.mismatch",
        "VISIBLE_TEXT": "text irrelevant here - TEXT_HASH is computed from it below",
    }
    entry = generator._production_entry(beat, existing_entries)
    # force exactly one identity field to mismatch on the REBUILT entry side
    entry[mutate_field] = new_value
    override = generator._preserved_pronunciation_override(existing_entries, entry)
    assert override is None


def test_matching_identity_preserves_the_override_exactly(generator):
    """The positive case for the same fail-closed check: when all four
    identity fields genuinely match, the override IS carried forward,
    byte/text identical to the source."""
    existing_entries = _real_manifest_entries()
    beat_id = "Z3_S01_B001"
    prior = existing_entries[beat_id]
    rebuilt_entry = {
        "BEAT_ID": prior["BEAT_ID"],
        "TEXT_HASH": prior["TEXT_HASH"],
        "CHARACTER": prior["CHARACTER"],
        "VOICE_ID": prior["VOICE_ID"],
    }
    override = generator._preserved_pronunciation_override(existing_entries, rebuilt_entry)
    assert override == prior["PRONUNCIATION_OVERRIDE"]


def test_prior_entry_absent_for_this_beat_id_fails_closed(generator):
    entry = {"BEAT_ID": "Z3_DOES_NOT_EXIST", "TEXT_HASH": "x", "CHARACTER": "HERO", "VOICE_ID": "v"}
    assert generator._preserved_pronunciation_override({}, entry) is None


# ------------------------------------------------- 4. end-to-end manifest preservation test

def test_final_production_rebuild_preserves_all_four_overrides_exactly(generator, monkeypatch, tmp_path, capsys):
    """Runs the actual production manifest rebuild path
    (_generate_final_production, same call the real --final-production CLI
    mode makes) against an isolated temp copy of the real manifest, proving
    all four existing PRONUNCIATION_OVERRIDE values survive exactly, no
    extra override appears, and the real tracked manifest is never touched.
    """
    real_hash_before = _sha256(REAL_MANIFEST)

    fixture_manifest = tmp_path / REAL_MANIFEST.name
    fixture_manifest.write_text(REAL_MANIFEST.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(generator, "AUDIO_MANIFEST_PATH", fixture_manifest)

    before_entries = {
        e["BEAT_ID"]: e for e in json.loads(fixture_manifest.read_text(encoding="utf-8"))["entries"]
    }
    before_overrides = {
        beat_id: copy.deepcopy(e["PRONUNCIATION_OVERRIDE"])
        for beat_id, e in before_entries.items()
        if e.get("PRONUNCIATION_OVERRIDE") is not None
    }
    assert len(before_overrides) == 4  # EXISTING_OVERRIDE_COUNT_BEFORE

    class NoNetworkTts:
        def _text_to_speech(self, *args, **kwargs):
            raise AssertionError("this corrective must never regenerate audio")

    monkeypatch.setenv("ELEVENLABS_API_KEY", "dummy_test_value_not_real")

    result = generator._generate_final_production(generator._load_subtitles(), NoNetworkTts())
    assert result == 0
    output = capsys.readouterr().out
    assert "FINAL_PRODUCTION_GENERATED=0" in output  # AUDIO_REGENERATION=NO, proven not assumed

    after_document = json.loads(fixture_manifest.read_text(encoding="utf-8"))
    after_entries = {e["BEAT_ID"]: e for e in after_document["entries"]}
    after_overrides = {
        beat_id: e["PRONUNCIATION_OVERRIDE"]
        for beat_id, e in after_entries.items()
        if e.get("PRONUNCIATION_OVERRIDE") is not None
    }

    assert set(after_overrides) == set(before_overrides)  # EXISTING_OVERRIDE_COUNT_AFTER == 4, no extra
    for beat_id, value in before_overrides.items():
        assert after_overrides[beat_id] == value  # byte/text identical

    # the real, tracked manifest was never opened for writing
    assert _sha256(REAL_MANIFEST) == real_hash_before


def test_final_production_rebuild_preservation_is_stable_across_repeated_runs(
    generator, monkeypatch, tmp_path, capsys
):
    """REPEAT_COUNT>=3: the same rebuild run three times against fresh
    isolated copies each time, confirming preservation and source-hash
    stability hold on every run, not just the first."""
    real_hash_before = _sha256(REAL_MANIFEST)

    class NoNetworkTts:
        def _text_to_speech(self, *args, **kwargs):
            raise AssertionError("this corrective must never regenerate audio")

    monkeypatch.setenv("ELEVENLABS_API_KEY", "dummy_test_value_not_real")

    for run in range(3):
        fixture_manifest = tmp_path / f"run_{run}_{REAL_MANIFEST.name}"
        fixture_manifest.write_text(REAL_MANIFEST.read_text(encoding="utf-8"), encoding="utf-8")
        monkeypatch.setattr(generator, "AUDIO_MANIFEST_PATH", fixture_manifest)

        result = generator._generate_final_production(generator._load_subtitles(), NoNetworkTts())
        assert result == 0, f"run {run} failed"

        after = json.loads(fixture_manifest.read_text(encoding="utf-8"))
        overrides = [e for e in after["entries"] if e.get("PRONUNCIATION_OVERRIDE") is not None]
        assert len(overrides) == 4, f"run {run}: override count drifted"

        assert _sha256(REAL_MANIFEST) == real_hash_before, f"run {run}: source manifest hash moved"
