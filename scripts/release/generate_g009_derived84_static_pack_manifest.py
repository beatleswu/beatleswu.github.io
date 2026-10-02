#!/usr/bin/env python3
"""Generate the G009 Derived84 static pack manifest.

The runtime manifest is a governed UTF-8 text asset.  Git checkout filters
are not a runtime dependency of release generation, so canonical text bytes
are obtained by normalizing only CRLF line endings to LF.  Binary assets are
read byte-for-byte.

The generator deliberately does not contain expected sizes, hashes, or Git
object IDs.  It derives all values from the source manifest and runtime files
at execution time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_SOURCE_MANIFEST = Path("assets/world-map-identity/runtime_manifest.json")
DEFAULT_OUTPUT = Path("deploy/g009-derived84-static-pack-manifest.json")
TEXT_SUFFIXES = frozenset({".css", ".html", ".js", ".json", ".md", ".txt"})


def canonical_source_bytes(path: Path) -> bytes:
    """Return the governed source bytes independent of checkout EOL mode."""

    raw = path.read_bytes()
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return raw

    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"governed text asset is not UTF-8: {path}") from exc

    bare_cr = raw.replace(b"\r\n", b"")
    if b"\r" in bare_cr:
        raise ValueError(f"governed text asset contains a bare CR: {path}")
    return raw.replace(b"\r\n", b"\n")


def _repo_file(repo_root: Path, relative: str) -> Path:
    if not relative or relative.startswith(("/", "\\")):
        raise ValueError(f"asset path must be relative: {relative!r}")
    candidate = (repo_root / Path(*relative.split("/"))).resolve()
    root = repo_root.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"asset path escapes repository root: {relative!r}")
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate


def _mime_for(path: str) -> str:
    return {
        ".json": "application/json",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(Path(path).suffix.lower(), "application/octet-stream")


def _file_entry(path: str, data: bytes) -> dict[str, Any]:
    return {
        "path": path,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "mime": _mime_for(path),
    }


def _read_runtime_manifest(source_path: Path) -> tuple[dict[str, Any], bytes]:
    raw = canonical_source_bytes(source_path)
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid runtime manifest: {source_path}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("runtime manifest root must be an object")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("runtime manifest must contain non-empty entries")
    return manifest, raw


def build_pack(
    *,
    repo_root: Path,
    source_manifest_path: Path,
    source_manifest_label: str,
) -> dict[str, Any]:
    manifest, source_raw = _read_runtime_manifest(source_manifest_path)
    entries = manifest["entries"]
    role_counts = Counter(entry.get("asset_role") for entry in entries)
    expected_roles = {"AVATAR", "STANDING", "COMPANION"}
    if set(role_counts) != expected_roles:
        raise ValueError(f"unexpected runtime asset roles: {dict(role_counts)!r}")

    files = [
        _file_entry(source_manifest_label, source_raw),
    ]
    for entry in entries:
        target_path = entry.get("target_runtime_path")
        if not isinstance(target_path, str):
            raise ValueError("runtime entry has no target_runtime_path")
        target = _repo_file(repo_root, target_path)
        files.append(_file_entry(target_path, canonical_source_bytes(target)))

    paths = [row["path"] for row in files]
    if len(paths) != len(set(paths)):
        raise ValueError("duplicate path in generated pack")

    counts = manifest.get("counts")
    if not isinstance(counts, dict):
        raise ValueError("runtime manifest must contain counts")
    declared_counts = {
        "AVATAR": int(counts["avatar"]),
        "STANDING": int(counts["standing"]),
        "COMPANION": int(counts["companion_stage"]),
    }
    if declared_counts != dict(role_counts):
        raise ValueError(
            f"runtime manifest counts disagree with entries: "
            f"declared={declared_counts!r} actual={dict(role_counts)!r}"
        )

    return {
        "$schema_note": (
            "Exact public closure for the Owner-accepted G009 Derived84 "
            f"identity assets ({role_counts['AVATAR']} avatar, "
            f"{role_counts['STANDING']} standing, "
            f"{role_counts['COMPANION']} Companion stage) "
            "plus the runtime manifest the client reads. Owner delivery "
            "authority: DUAL_DELIVERY_LIVE_STATIC_FIRST_WITH_BAKED_FALLBACK. "
            "The same bytes are baked into the application image as the "
            "fallback. Inclusion grants no ownership, entitlement, "
            "acquisition or Shop availability."
        ),
        "manifest_version": "1.0.0",
        "generated_for": "G_G009_DELIVERY_RUNTIME_PROVENANCE_CLOSURE_CORRECTIVE_RESUME_001",
        "prefix": "assets/world-map-identity/",
        "total_files": len(files),
        "total_bytes": sum(row["size"] for row in files),
        "source_manifest": source_manifest_label,
        "source_manifest_sha256": files[0]["sha256"],
        "accepted_asset_counts": {
            "AVATAR": role_counts["AVATAR"],
            "STANDING": role_counts["STANDING"],
            "COMPANION": role_counts["COMPANION"],
        },
        "files": files,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="repository root containing runtime asset paths",
    )
    parser.add_argument(
        "--source-manifest",
        type=Path,
        default=DEFAULT_SOURCE_MANIFEST,
        help="runtime manifest to read; defaults to the governed repository path",
    )
    parser.add_argument(
        "--source-manifest-label",
        default=DEFAULT_SOURCE_MANIFEST.as_posix(),
        help="manifest path recorded in the generated pack",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="output pack path; D005 callers must use a non-committed path",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = args.repo_root.resolve()
    source_manifest = args.source_manifest
    if not source_manifest.is_absolute():
        source_manifest = (repo_root / source_manifest).resolve()
    output = args.output
    if not output.is_absolute():
        output = (repo_root / output).resolve()

    payload = build_pack(
        repo_root=repo_root,
        source_manifest_path=source_manifest,
        source_manifest_label=args.source_manifest_label,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(
        (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
