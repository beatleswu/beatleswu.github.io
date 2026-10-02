#!/usr/bin/env python3
"""Generate the canonical image-pack manifest from candidate-owned authority.

The committed image-pack manifest is intentionally an input to this command.
Callers choose the output path, so a release correction can be generated into a
disposable path first and reviewed before any tracked release artifact is
replaced.

Functional-equipment SVG membership comes from the current wearable registry's
explicit ``equipment[*].canonical_icon`` fields.  The generator never scans a
directory or carries a list of equipment ids.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


DEFAULT_REGISTRY = Path("assets/hero/equipment/wearables/wearable_registry.json")
DEFAULT_MANIFEST = Path("deploy/canonical-image-pack-manifest.json")
FUNCTIONAL_PREFIX = "assets/hero/equipment/functional/"
SVG_MIME = "image/svg+xml"


def _normalise_repo_path(value: object) -> str:
    path = str(value or "").replace("\\", "/").lstrip("/")
    if not path or path.startswith("../") or "/../" in path or path == "..":
        raise ValueError(f"unsafe governed path: {value!r}")
    return path


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _parse_dimension(value: str | None, path: str, attribute: str) -> int:
    if value is None:
        raise ValueError(f"SVG {path} has no root {attribute} attribute")
    match = re.fullmatch(r"\s*([0-9]+)(?:\.0+)?(?:px)?\s*", value)
    if not match:
        raise ValueError(f"SVG {path} has non-integer root {attribute}: {value!r}")
    return int(match.group(1))


def _svg_dimensions(raw: bytes, path: str) -> tuple[int, int]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"invalid SVG XML: {path}") from exc
    if root.tag.rsplit("}", 1)[-1] != "svg":
        raise ValueError(f"SVG root is not <svg>: {path}")
    return (
        _parse_dimension(root.attrib.get("width"), path, "width"),
        _parse_dimension(root.attrib.get("height"), path, "height"),
    )


def _registry_icons(registry: dict) -> list[tuple[str, str, dict]]:
    equipment = registry.get("equipment")
    if not isinstance(equipment, dict):
        raise ValueError("wearable registry has no equipment object")

    result: list[tuple[str, str, dict]] = []
    seen: dict[str, str] = {}
    for registry_id, record in equipment.items():
        if not isinstance(record, dict) or not record.get("canonical_icon"):
            continue
        path = _normalise_repo_path(record["canonical_icon"])
        if not path.startswith(FUNCTIONAL_PREFIX) or not path.endswith(".svg"):
            raise ValueError(
                f"equipment[{registry_id}] canonical_icon is outside the governed "
                f"functional SVG namespace: {path}"
            )
        previous = seen.get(path)
        if previous is not None and previous != registry_id:
            raise ValueError(
                f"duplicate canonical_icon {path!r}: {previous!r}, {registry_id!r}"
            )
        seen[path] = str(registry_id)
        result.append((str(registry_id), path, record))
    if not result:
        raise ValueError("wearable registry contains no governed canonical icons")
    return result


def _entry_metadata(
    path: str,
    registry_id: str,
    record: dict,
    repo_root: Path,
    provenance: str,
) -> dict:
    source = repo_root / path
    if not source.is_file():
        raise FileNotFoundError(f"governed SVG does not exist: {path}")
    raw = source.read_bytes()
    width, height = _svg_dimensions(raw, path)
    production_status = str(record.get("production_status") or "")
    source_reference = str(record.get("source") or "")
    evidence = (
        "wearable_registry.json equipment["
        f"{registry_id}] canonical_icon={path}; "
        f"production_status={production_status}; source={source_reference}"
    )
    return {
        "path": path,
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "mime": SVG_MIME,
        "width": width,
        "height": height,
        "provenance": provenance,
        "source_evidence": evidence,
    }


def generate_manifest(
    repo_root: Path,
    registry_path: Path,
    manifest_path: Path,
    output_path: Path,
) -> dict:
    registry = _load_json(registry_path)
    base = _load_json(manifest_path)
    base_entries = base.get("files")
    if not isinstance(base_entries, list):
        raise ValueError("canonical image manifest has no files list")

    base_by_path: dict[str, dict] = {}
    for entry in base_entries:
        if not isinstance(entry, dict) or not entry.get("path"):
            raise ValueError("canonical image manifest contains a malformed entry")
        path = _normalise_repo_path(entry["path"])
        if path in base_by_path:
            raise ValueError(f"duplicate manifest path: {path}")
        base_by_path[path] = entry

    # Preserve every committed entry object exactly.  Verify its byte identity
    # while it is in scope so the generator cannot hide an existing defect.
    for path, entry in base_by_path.items():
        source = repo_root / path
        if not source.is_file():
            raise FileNotFoundError(f"existing manifest file does not exist: {path}")
        raw = source.read_bytes()
        if entry.get("size") != len(raw):
            raise ValueError(f"existing manifest size mismatch: {path}")
        if entry.get("sha256") != hashlib.sha256(raw).hexdigest():
            raise ValueError(f"existing manifest SHA-256 mismatch: {path}")

    registry_icons = _registry_icons(registry)
    registry_by_path = {path: (registry_id, record) for registry_id, path, record in registry_icons}
    missing_paths = sorted(set(registry_by_path) - set(base_by_path))

    existing_svg_entries = [
        entry
        for path, entry in base_by_path.items()
        if path.startswith(FUNCTIONAL_PREFIX) and path.endswith(".svg")
    ]
    provenance_values = {
        entry.get("provenance") for entry in existing_svg_entries if entry.get("provenance")
    }
    if len(provenance_values) != 1:
        raise ValueError(
            "functional SVG provenance contract is not uniquely established by "
            f"the committed image manifest: {sorted(provenance_values, key=str)}"
        )
    svg_provenance = next(iter(provenance_values))

    additions = []
    for path in missing_paths:
        registry_id, record = registry_by_path[path]
        additions.append(
            _entry_metadata(path, registry_id, record, repo_root, svg_provenance)
        )

    all_entries_by_path = dict(base_by_path)
    for entry in additions:
        all_entries_by_path[entry["path"]] = entry
    all_entries = [all_entries_by_path[path] for path in sorted(all_entries_by_path)]

    original_summary = base.get("provenance_summary")
    if not isinstance(original_summary, dict):
        raise ValueError("canonical image manifest has no provenance_summary object")
    actual_original_summary: dict[str, int] = {
        str(category): 0 for category in original_summary
    }
    for entry in base_entries:
        category = entry.get("provenance")
        if not isinstance(category, str) or not category:
            raise ValueError(f"manifest entry has no provenance: {entry.get('path')}")
        if category not in actual_original_summary:
            raise ValueError(f"manifest entry uses an undeclared provenance: {category}")
        actual_original_summary[category] = actual_original_summary.get(category, 0) + 1
    if actual_original_summary != original_summary:
        raise ValueError(
            "committed provenance_summary does not match committed entries: "
            f"declared={original_summary!r} actual={actual_original_summary!r}"
        )
    generated_summary = dict(original_summary)
    for entry in additions:
        category = entry["provenance"]
        generated_summary[category] = generated_summary.get(category, 0) + 1

    output = dict(base)
    output["total_files"] = len(all_entries)
    output["total_bytes"] = sum(entry["size"] for entry in all_entries)
    output["provenance_summary"] = generated_summary
    output["files"] = all_entries
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    return {
        "registry_icon_count": len(registry_icons),
        "existing_entry_count": len(base_entries),
        "added_entry_count": len(additions),
        "added_entries": additions,
        "output_entry_count": len(all_entries),
        "output_total_bytes": output["total_bytes"],
        "output_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "existing_entry_retention": all(
            all_entries_by_path[path] == entry for path, entry in base_by_path.items()
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    registry_path = args.registry if args.registry.is_absolute() else repo_root / args.registry
    manifest_path = args.manifest if args.manifest.is_absolute() else repo_root / args.manifest
    output_path = args.output if args.output.is_absolute() else repo_root / args.output
    summary = generate_manifest(repo_root, registry_path, manifest_path, output_path)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
