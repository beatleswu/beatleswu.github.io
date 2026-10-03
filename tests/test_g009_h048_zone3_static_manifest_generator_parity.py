"""Guard the committed Zone 3 static manifest against generator drift."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "release"))
from generate_g009_derived84_static_pack_manifest import canonical_source_bytes

GENERATOR = ROOT / "scripts" / "release" / "generate_zone3_static_pack_manifest.py"
COMMITTED_MANIFEST = ROOT / "deploy" / "canonical-e10-zone3-static-pack-manifest.json"
RUNTIME_ROOTS = (
    Path("assets/e10/art/zone3"),
    Path("assets/e10/audio/zone3"),
    Path("assets/e10/i18n/zone3"),
)


def test_committed_zone3_static_manifest_matches_canonical_generator() -> None:
    """A fresh canonical generation must reproduce every committed byte."""

    with tempfile.TemporaryDirectory(
        prefix="g009-h048-zone3-generator-", dir=ROOT
    ) as temp:
        temp_root = Path(temp)
        (temp_root / "deploy").mkdir()
        for relative_root in RUNTIME_ROOTS:
            source = ROOT / relative_root
            destination = temp_root / relative_root
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, destination)

        result = subprocess.run(
            [sys.executable, str(GENERATOR), str(temp_root)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

        generated_manifest = (
            temp_root / "deploy" / "canonical-e10-zone3-static-pack-manifest.json"
        )
        assert generated_manifest.is_file()
        assert generated_manifest.read_bytes() == COMMITTED_MANIFEST.read_bytes()


def test_zone3_generator_canonicalizes_lf_and_crlf_text_inputs() -> None:
    """CRLF materialization must not alter governed Zone3 accounting."""

    audio_relative = Path(
        "assets/e10/audio/zone3/zone3-presentation-audio-manifest.json"
    )
    with tempfile.TemporaryDirectory(
        prefix="g009-h048-zone3-eol-equivalence-", dir=ROOT
    ) as temp:
        temp_root = Path(temp)
        roots = (temp_root / "lf", temp_root / "crlf")
        for candidate in roots:
            (candidate / "deploy").mkdir(parents=True)
            for relative_root in RUNTIME_ROOTS:
                source = ROOT / relative_root
                destination = candidate / relative_root
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source, destination)

        lf_audio = roots[0] / audio_relative
        crlf_audio = roots[1] / audio_relative
        lf_raw = lf_audio.read_bytes()
        crlf_raw = lf_raw.replace(b"\n", b"\r\n")
        crlf_audio.write_bytes(crlf_raw)

        assert len(lf_raw) != len(crlf_raw)
        canonical_lf = canonical_source_bytes(lf_audio)
        canonical_crlf = canonical_source_bytes(crlf_audio)
        assert len(canonical_lf) == len(canonical_crlf) == 25059
        assert hashlib.sha256(canonical_lf).hexdigest() == hashlib.sha256(
            canonical_crlf
        ).hexdigest()

        generated = []
        for candidate in roots:
            result = subprocess.run(
                [sys.executable, str(GENERATOR), str(candidate)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 0, result.stderr
            manifest = candidate / "deploy" / COMMITTED_MANIFEST.name
            assert manifest.is_file()
            generated.append(manifest.read_bytes())

        assert generated[0] == generated[1]
        lf_manifest = json.loads(generated[0].decode("utf-8"))
        audio_entry = next(
            entry for entry in lf_manifest["files"] if entry["path"] == audio_relative.as_posix()
        )
        assert audio_entry["size"] == 25059
        assert audio_entry["sha256"] == hashlib.sha256(canonical_lf).hexdigest()
        assert lf_manifest["total_files"] == 235
        assert lf_manifest["total_bytes"] == 28204646
