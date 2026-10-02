"""Guard the committed Zone 3 static manifest against generator drift."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "release" / "generate_zone3_static_pack_manifest.py"
COMMITTED_MANIFEST = ROOT / "deploy" / "canonical-e10-zone3-static-pack-manifest.json"
RUNTIME_ROOTS = (
    Path("assets/e10/art/zone3"),
    Path("assets/e10/audio/zone3"),
    Path("assets/e10/i18n/zone3"),
)


def test_committed_zone3_static_manifest_matches_canonical_generator() -> None:
    """A fresh canonical generation must reproduce every committed byte."""

    with tempfile.TemporaryDirectory(prefix="g009-h048-zone3-generator-") as temp:
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
