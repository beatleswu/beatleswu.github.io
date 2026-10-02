"""D005 regression coverage for canonical Derived84 pack bytes."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from scripts.release.generate_g009_derived84_static_pack_manifest import (
    TEXT_SUFFIXES,
    canonical_source_bytes,
)


ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts/release/generate_g009_derived84_static_pack_manifest.py"
RUNTIME_MANIFEST = ROOT / "assets/world-map-identity/runtime_manifest.json"
RUNTIME_LABEL = "assets/world-map-identity/runtime_manifest.json"


def _run_generator(source_manifest: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--repo-root",
            str(ROOT),
            "--source-manifest",
            str(source_manifest),
            "--source-manifest-label",
            RUNTIME_LABEL,
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_generator_for_root(
    repo_root: Path, source_manifest: Path, output: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--repo-root",
            str(repo_root),
            "--source-manifest",
            str(source_manifest),
            "--source-manifest-label",
            RUNTIME_LABEL,
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_cli_execution_path_uses_canonical_bytes_for_crlf_materialized_source(
    tmp_path: Path,
):
    canonical = RUNTIME_MANIFEST.read_bytes()
    assert b"\r\n" not in canonical
    materialized = canonical.replace(b"\n", b"\r\n")
    crlf_source = tmp_path / "runtime_manifest.json"
    crlf_source.write_bytes(materialized)
    output = tmp_path / "derived84-pack.json"

    result = _run_generator(crlf_source, output)

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_bytes().decode("utf-8"))
    source_row = payload["files"][0]
    assert source_row["path"] == RUNTIME_LABEL
    assert source_row["size"] == len(canonical)
    assert source_row["sha256"] == hashlib.sha256(canonical).hexdigest()
    assert output.read_bytes().count(b"\r\n") == 0
    assert payload["total_bytes"] == sum(row["size"] for row in payload["files"])


def test_actual_default_packaging_entrypoint_is_deterministic(tmp_path: Path):
    output = tmp_path / "derived84-pack.json"

    result = subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--repo-root",
            str(ROOT),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_bytes().decode("utf-8"))
    assert payload["source_manifest"] == RUNTIME_LABEL
    runtime = json.loads(RUNTIME_MANIFEST.read_bytes().decode("utf-8"))
    assert payload["total_files"] == 1 + len(runtime["entries"])
    assert payload["total_bytes"] == sum(row["size"] for row in payload["files"])
    assert payload["source_manifest_sha256"] == hashlib.sha256(
        RUNTIME_MANIFEST.read_bytes()
    ).hexdigest()


def test_cli_execution_path_does_not_require_git_repository(tmp_path: Path):
    fixture_root = tmp_path / "gitless-root"
    source = fixture_root / "assets/world-map-identity/runtime_manifest.json"
    assets = (
        fixture_root / "assets/world-map-identity/avatars/avatar.png",
        fixture_root / "assets/world-map-identity/standing/stand.png",
        fixture_root / "assets/world-map-identity/companion/pet_stage1.png",
    )
    for asset in assets:
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_bytes(asset.name.encode("ascii"))

    manifest = {
        "counts": {"avatar": 1, "standing": 1, "companion_stage": 1},
        "entries": [
            {
                "asset_role": "AVATAR",
                "target_runtime_path": "assets/world-map-identity/avatars/avatar.png",
            },
            {
                "asset_role": "STANDING",
                "target_runtime_path": "assets/world-map-identity/standing/stand.png",
            },
            {
                "asset_role": "COMPANION",
                "target_runtime_path": "assets/world-map-identity/companion/pet_stage1.png",
            },
        ],
    }
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(
        (json.dumps(manifest, indent=2) + "\n").replace("\n", "\r\n").encode("utf-8")
    )
    assert not (fixture_root / ".git").exists()

    output = tmp_path / "gitless-pack.json"
    result = _run_generator_for_root(fixture_root, source, output)

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_bytes().decode("utf-8"))
    assert payload["total_files"] == 4
    assert payload["files"][0]["size"] == len(
        source.read_bytes().replace(b"\r\n", b"\n")
    )


def test_git_present_guard_matches_generator_canonical_bytes_to_head_blobs():
    """The test-only Git assertion must never become generator runtime logic."""

    runtime = json.loads(RUNTIME_MANIFEST.read_bytes().decode("utf-8"))
    governed_text_paths = [RUNTIME_LABEL]
    governed_text_paths.extend(
        entry["target_runtime_path"]
        for entry in runtime["entries"]
        if Path(entry["target_runtime_path"]).suffix.lower() in TEXT_SUFFIXES
    )
    assert len(governed_text_paths) == len(set(governed_text_paths))

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    for relative_path in governed_text_paths:
        working_tree_path = ROOT / Path(*relative_path.split("/"))
        working_tree_bytes = working_tree_path.read_bytes()
        canonical_bytes = canonical_source_bytes(working_tree_path)
        git_blob_bytes = subprocess.run(
            ["git", "cat-file", "blob", f"{head}:{relative_path}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout

        assert canonical_bytes == git_blob_bytes, (
            f"{relative_path} canonical bytes differ from HEAD blob "
            f"(working_size={len(working_tree_bytes)}, "
            f"canonical_sha256={hashlib.sha256(canonical_bytes).hexdigest()}, "
            f"blob_sha256={hashlib.sha256(git_blob_bytes).hexdigest()})"
        )
