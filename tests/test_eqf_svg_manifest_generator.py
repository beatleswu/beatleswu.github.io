"""Parity and scope tests for the canonical functional-equipment SVG generator."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts/release/generate_canonical_image_pack_manifest.py"
REGISTRY = ROOT / "assets/hero/equipment/wearables/wearable_registry.json"
MANIFEST = ROOT / "deploy/canonical-image-pack-manifest.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalise(value: str) -> str:
    return value.replace("\\", "/").lstrip("/")


def _registry_icons() -> dict[str, tuple[str, dict]]:
    equipment = _load(REGISTRY)["equipment"]
    return {
        _normalise(record["canonical_icon"]): (registry_id, record)
        for registry_id, record in equipment.items()
        if record.get("canonical_icon")
    }


def _run_generator(output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GENERATOR), "--repo-root", str(ROOT), "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_generator_is_tracked_and_invocable():
    assert GENERATOR.is_file()
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(GENERATOR.relative_to(ROOT))],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert tracked.returncode == 0, tracked.stderr


def test_generator_is_authority_derived_deterministic_and_preserves_manifest():
    base = _load(MANIFEST)
    base_by_path = {entry["path"]: entry for entry in base["files"]}
    registry_icons = _registry_icons()
    registry_paths = set(registry_icons)
    missing_paths = sorted(registry_paths - set(base_by_path))
    eqf_missing_paths = sorted(
        path
        for path, (_, record) in registry_icons.items()
        if record.get("production_status") == "EQ_E_ACCEPTED_ASSET"
        and path not in base_by_path
    )
    # The corrective has materialized the generator output into the committed
    # manifest.  Keep the authority-derived membership assertion dynamic, and
    # require the current release artifact to cover every governed icon.
    assert missing_paths == eqf_missing_paths == []

    committed_manifest_sha = _sha(MANIFEST)
    asset_shas_before = {
        path: _sha(ROOT / path) for path in registry_paths
    }

    with tempfile.TemporaryDirectory(prefix="eqf-generator-") as temp_dir:
        temp = Path(temp_dir)
        output_one = temp / "one.json"
        output_two = temp / "two.json"
        first = _run_generator(output_one)
        second = _run_generator(output_two)
        assert first.returncode == 0, first.stderr
        assert second.returncode == 0, second.stderr
        assert output_one.read_bytes() == output_two.read_bytes()
        assert output_one.read_bytes() == MANIFEST.read_bytes()

        generated = _load(output_one)
        generated_by_path = {entry["path"]: entry for entry in generated["files"]}
        assert set(generated_by_path) - set(base_by_path) == set()
        assert set(base_by_path) - set(generated_by_path) == set()
        for path, entry in base_by_path.items():
            assert generated_by_path[path] == entry

        assert set(registry_paths) <= set(generated_by_path)
        assert generated["total_files"] == len(generated["files"])
        assert generated["total_bytes"] == sum(
            entry["size"] for entry in generated["files"]
        )
        assert generated["files"] == sorted(
            generated["files"], key=lambda entry: entry["path"]
        )

        for path in missing_paths:
            entry = generated_by_path[path]
            raw = (ROOT / path).read_bytes()
            assert entry["size"] == len(raw)
            assert entry["sha256"] == hashlib.sha256(raw).hexdigest()
            assert entry["mime"] == "image/svg+xml"
            assert entry["width"] == 256
            assert entry["height"] == 256
            assert entry["source_evidence"]
            assert registry_icons[path][0] in entry["source_evidence"]

        # The same filesystem-byte assertion applies to the retained legacy
        # icons; the generator must not only verify the newly added rows.
        for path in registry_paths - set(missing_paths):
            entry = generated_by_path[path]
            raw = (ROOT / path).read_bytes()
            assert entry["size"] == len(raw)
            assert entry["sha256"] == hashlib.sha256(raw).hexdigest()

    stone = registry_icons["assets/hero/equipment/functional/go_stone_black.svg"][1]
    assert stone["wearable_visibility"] == "INVENTORY_ONLY"
    assert stone["mask_policy"] == "NO_RUNTIME_OVERLAY"
    assert not (ROOT / "assets/hero/equipment/wearables/overlays/go_stone_black.png").exists()

    assert _sha(MANIFEST) == committed_manifest_sha
    assert {path: _sha(ROOT / path) for path in registry_paths} == asset_shas_before
