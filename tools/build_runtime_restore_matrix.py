from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


GENERATED_RUNTIME_PATHS = {
    "chapter_overrides.json",
    "daily_final.png",
    "daily_q.png",
    "daily_q_data.json",
    "fb_cover.jpg",
    "fb_post_open_pets.jpg",
    "go_odyssey_storyboard_4.png",
    "katago_answer_overrides.json",
    "katago_checkpoint.json",
    "questions.json",
    "uni_stats.png",
    "youtube_banner_final.jpg",
}

STATIC_CURRENT_PATHS = {
    "assets/hero/chibi_rpg_fullbody_pixel_avatar.html",
    "i18n.js",
    "sw.js",
}


@dataclass(frozen=True)
class RestoreRow:
    path: str
    classification: str
    current_production_hash: str
    canonical_commit: str
    canonical_blob: str
    owner: str
    restore_action: str


def classify_row(path: str, audit_classification: str) -> tuple[str, str, str]:
    if audit_classification == "CLEAN":
        if path.startswith("assets/") or path in STATIC_CURRENT_PATHS:
            return "KEEP", "Static Current", "No change"
        if path in GENERATED_RUNTIME_PATHS:
            return "KEEP", "Generated Runtime", "No change"
        return "KEEP", "Git Runtime", "No change"

    if audit_classification == "REGRESSED_TO_OLD_GIT_VERSION":
        if path.startswith("blog/") or path.endswith((".html", ".js", ".css")):
            return "RESTORE", "Git Runtime", "Sync canonical git source"
        if path in {"manifest.json", "robots.txt", "sitemap.xml", "pwa.js"}:
            return "RESTORE", "Git Runtime", "Sync canonical git source"
        return "RESTORE", "Git Runtime", "Sync canonical git source"

    if audit_classification == "STATIC_OVERRIDE":
        return "RESTORE", "Static Current", "Sync static-current from canonical git source"

    if audit_classification == "SERVED_HASH_MISMATCH":
        if path in GENERATED_RUNTIME_PATHS:
            return "GENERATED", "Generated Runtime", "Regenerate from source script or data"
        if path == "login.html":
            return "RESTORE", "Git Runtime", "Restore canonical login page"
        return "IGNORE", "Generated Runtime", "Out of runtime surface"

    return "IGNORE", "Git Runtime", "Needs manual review"


def load_inventory(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def build_matrix(rows: Iterable[dict[str, str]]) -> list[RestoreRow]:
    matrix: list[RestoreRow] = []
    for row in rows:
        path = row["path"]
        classification, owner, restore_action = classify_row(path, row["classification"])
        current_production_hash = (
            row["production_sha256"]
            or row["served_sha256"]
            or row["static_current_sha256"]
            or row["container_sha256"]
            or row["release_sha256"]
        )
        matrix.append(
            RestoreRow(
                path=path,
                classification=classification,
                current_production_hash=current_production_hash,
                canonical_commit=row["last_modified_commit"],
                canonical_blob=row["git_blob"],
                owner=owner,
                restore_action=restore_action,
            )
        )
    return sorted(matrix, key=lambda r: r.path)


def write_csv(path: Path, rows: list[RestoreRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(
            [
                "Path",
                "Classification",
                "Current Production Hash",
                "Canonical Commit",
                "Canonical Blob",
                "Owner",
                "Restore Action",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.path,
                    row.classification,
                    row.current_production_hash,
                    row.canonical_commit,
                    row.canonical_blob,
                    row.owner,
                    row.restore_action,
                ]
            )


def write_md(path: Path, rows: list[RestoreRow], inventory_path: Path) -> None:
    counts = Counter(row.classification for row in rows)
    owners = Counter(row.owner for row in rows)
    action_counts = Counter(row.restore_action for row in rows)
    samples = defaultdict(list)
    for row in rows:
        if row.classification != "KEEP" and len(samples[row.classification]) < 20:
            samples[row.classification].append(row.path)

    lines = [
        "# Runtime Restore Matrix",
        "",
        f"- Inventory source: `{inventory_path.as_posix()}`",
        f"- Rows: `{len(rows)}`",
        f"- KEEP: `{counts.get('KEEP', 0)}`",
        f"- RESTORE: `{counts.get('RESTORE', 0)}`",
        f"- GENERATED: `{counts.get('GENERATED', 0)}`",
        f"- IGNORE: `{counts.get('IGNORE', 0)}`",
        "",
        "## Owner Split",
    ]
    for owner, count in owners.most_common():
        lines.append(f"- {owner}: `{count}`")

    lines.extend(
        [
            "",
            "## Restore Actions",
        ]
    )
    for action, count in action_counts.most_common():
        lines.append(f"- {action}: `{count}`")

    for classification in ["RESTORE", "GENERATED", "IGNORE"]:
        lines.extend(["", f"## {classification}",])
        for item in samples.get(classification, []):
            lines.append(f"- {item}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a runtime restore matrix from the audit inventory.")
    parser.add_argument(
        "--inventory",
        default="docs/testing/runtime_integrity_inventory_2026-07-12.csv",
        help="Path to the runtime inventory CSV.",
    )
    parser.add_argument(
        "--matrix-csv",
        default="docs/testing/runtime_restore_matrix_2026-07-12.csv",
        help="Output restore matrix CSV path.",
    )
    parser.add_argument(
        "--matrix-md",
        default="docs/testing/runtime_restore_matrix_2026-07-12.md",
        help="Output restore matrix markdown path.",
    )
    args = parser.parse_args()

    inventory_path = Path(args.inventory)
    matrix_csv_path = Path(args.matrix_csv)
    matrix_md_path = Path(args.matrix_md)

    inventory = load_inventory(inventory_path)
    matrix = build_matrix(inventory)
    write_csv(matrix_csv_path, matrix)
    write_md(matrix_md_path, matrix, inventory_path)

    print(f"Wrote {len(matrix)} rows to {matrix_csv_path}")
    print(f"Wrote summary to {matrix_md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
