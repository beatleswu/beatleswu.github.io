#!/usr/bin/env python3
"""Generate the exact Zone 3 runtime static-asset closure.

The release inventory stages this manifest as an explicit, hash-verified
subtree. Source artwork is deliberately excluded; only committed runtime
derivatives, locale manifests, and audio assets are included.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ZONE3_ROOTS = (
    Path("assets/e10/art/zone3"),
    Path("assets/e10/audio/zone3"),
    Path("assets/e10/i18n/zone3"),
)
OUTPUT = Path("deploy/canonical-e10-zone3-static-pack-manifest.json")
BASE_HEAD = "65dd8c00f217fc04942456d5b1dd02f52fc8f265"
BASE_TREE = "e227201cd0e12eeb0c82a15f5d46d45bf66397e9"

CURATED_MISSING_RESOURCES = tuple(
    f"assets/e10/art/zone3/cinematic/zone3_shot{i:02d}.webp"
    for i in range(1, 6)
)


def mime_for(path: Path) -> str:
    return {
        ".json": "application/json",
        ".mp3": "audio/mpeg",
        ".webp": "image/webp",
    }[path.suffix.lower()]


def runtime_paths(repo_root: Path) -> list[Path]:
    paths = []
    for relative_root in ZONE3_ROOTS:
        root = repo_root / relative_root
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(repo_root).as_posix()
            if "/source/" in relative:
                continue
            if path.suffix.lower() not in {".json", ".mp3", ".webp"}:
                continue
            paths.append(path)
    return sorted(paths, key=lambda path: path.relative_to(repo_root).as_posix())


def file_entry(path: Path, repo_root: Path) -> dict[str, object]:
    raw = path.read_bytes()
    relative = path.relative_to(repo_root).as_posix()
    return {
        "path": relative,
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "mime": mime_for(path),
        "provenance": "owner-approved-zone3-runtime-closure",
        "source_evidence": (
            "Committed Zone 3 runtime derivative or locale/audio manifest; "
            "source authority remains in the Zone 3 content manifests."
        ),
    }


def main(repo_root: Path) -> None:
    paths = runtime_paths(repo_root)
    entries = [file_entry(path, repo_root) for path in paths]
    expected_prefix = "assets/e10/"
    assert all(entry["path"].startswith(expected_prefix) for entry in entries)
    assert len({entry["path"] for entry in entries}) == len(entries)
    assert all("/source/" not in entry["path"] for entry in entries)

    by_path = {entry["path"]: entry for entry in entries}
    missing = [path for path in CURATED_MISSING_RESOURCES if path not in by_path]
    if missing:
        raise SystemExit(f"curated Zone 3 resource missing from closure: {missing}")

    manifest = {
        "$schema_note": (
            "Canonical governed Zone 3 runtime static closure for QA blocker "
            "repair 011. The five first-entry cinematic WebP resources were "
            "present in the source checkout but absent from the failed image "
            "package; this closure also stages the complete Zone 3 runtime "
            "media/data set. Source JPEG/PNG masters are never staged."
        ),
        "manifest_version": "1.0.0",
        "generated_for": "W1_03_JOURNEY_ZONE3_FINAL_QA_BLOCKER_REPAIR_011",
        "source_head": BASE_HEAD,
        "source_tree": BASE_TREE,
        "prefix": expected_prefix,
        "total_files": len(entries),
        "total_bytes": sum(int(entry["size"]) for entry in entries),
        "curated_missing_resources": [
            {
                "resource_path": path,
                "source_present": True,
                "candidate_manifest_present": False,
                "image_present": False,
                "static_package_present": True,
                "runtime_requested": True,
                "omission_origin": "PACKAGE_MANIFEST",
            }
            for path in CURATED_MISSING_RESOURCES
        ],
        "source_exclusion": {
            "excluded_path_segment": "/source/",
            "excluded_extensions": [".jpeg", ".jpg", ".png"],
            "reason": "source masters are evidence, not runtime delivery bytes",
        },
        "files": entries,
    }
    output = repo_root / OUTPUT
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"path": OUTPUT.as_posix(), "files": len(entries), "bytes": manifest["total_bytes"]}))


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd())
