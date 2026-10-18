#!/usr/bin/env python3
"""G009 release-only Dockerfile layer compaction, from validated 2026-10-18 handoff.

Operate ONLY on immutable Product commit 69dbe57aa535112b1759e3f3bdcf9ecbe1680efb.
This creates a DERIVED Dockerfile and never changes the original Product Dockerfile.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

PRODUCT_SHA = "69dbe57aa535112b1759e3f3bdcf9ecbe1680efb"

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def compact(root: Path, batch: int = 48) -> dict:
    root = root.resolve(strict=True)
    original = root / "Dockerfile"
    raw = original.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=True)
    copies = []
    i = 0
    while i < len(lines):
        text = lines[i].strip()
        if text.startswith("COPY "):
            start = i
            while text.endswith("\\"):
                i += 1
                if i >= len(lines):
                    raise ValueError("unterminated COPY continuation")
                text = text[:-1].strip() + " " + lines[i].strip()
            copies.append((start, i, text))
        i += 1
    if (len(copies) != 249 or copies[0][2] != "COPY requirements.txt ."
            or copies[-1][2] != "COPY entrypoint.sh ."):
        raise ValueError("Original curated Dockerfile shape changed; fail closed")
    start, end = copies[1][0], copies[-1][1]
    occupied = {i for left, right, _ in copies[1:] for i in range(left, right+1)}
    for i in range(start, end+1):
        if (i not in occupied and lines[i].strip()
                and not lines[i].lstrip().startswith("#")):
            raise ValueError(f"Unexpected non-COPY Dockerfile instruction at line {i+1}")
    sources = []
    for _, _, statement in copies[1:]:
        parts = statement.split()
        inputs, destination = parts[1:-1], parts[-1]
        if not inputs:
            raise ValueError("COPY without source")
        for source in inputs:
            if ("*" in source or "?" in source or "$" in source
                    or ".." in Path(source).parts or source.startswith("/")
                    or source.startswith("-") or "\\" in source):
                raise ValueError(f"Unsupported COPY source: {source}")
            src = root / source
            if not src.exists() or src.is_symlink():
                raise ValueError(f"Missing/linked source: {source}")
            name = Path(source).name
            if destination in (".", "./"):
                mapped = name
            elif destination.endswith("/"):
                mapped = destination.removeprefix("/app/").removeprefix("./") + name
            else:
                mapped = destination.removeprefix("/app/").removeprefix("./")
            if mapped != source:
                # Exact original Dockerfile directory-to-same-directory COPY
                # entries copy CONTENTS into the existing target directory.
                # Dockerfile 1.20 COPY --parents recreates that same parent.
                # Restrict this exception to the three verified exact inputs.
                existing_directory_copies = {
                    "assets/3d_shop/p048/future30/c005/",
                    "assets/3d_shop/p048/companion/formal_18/",
                    "assets/world-map-identity/",
                }
                if not (source in existing_directory_copies
                        and destination == "./" + source
                        and src.is_dir()):
                    raise ValueError(f"Changed mapping: {source} -> {mapped}")
            sources.append(source)
    if len(sources) != 313 or len(set(sources)) != 313:
        raise ValueError("Original curated input set does not match")
    groups = [sources[j:j+batch] for j in range(0,len(sources),batch)]
    optimized = ("# syntax=docker/dockerfile:1.20\n"
                 + "".join(lines[:start])
                 + "".join("COPY --parents " + " ".join(g) + " ./\n" for g in groups)
                 + "".join(lines[end+1:]))
    target = root / "Dockerfile.g009-compact"
    target.write_text(optimized, encoding="utf-8")
    if optimized.count("COPY ") != len(groups)+1:
        target.unlink(missing_ok=True)
        raise ValueError("Unexpected derived COPY count")
    result = {
        "schema":"g009-curated-dockerfile-compaction-v1",
        "approved_product_sha":PRODUCT_SHA,
        "original_dockerfile_sha256":sha(original),
        "optimized_dockerfile_sha256":sha(target),
        "original_copy_instructions":len(copies),
        "optimized_copy_instructions":len(groups)+1,
        "curated_source_count_excluding_requirements":len(sources),
        "source_paths":sources,
        "source_content_mutated":False,
        "independent_build_app_signature_issued":False,
        "deployed":False
    }
    (root / "Dockerfile.g009-compact.receipt.json").write_text(
        json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--product",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps({k:v for k,v in compact(args.product).items()
                      if k!="source_paths"},indent=2))
