from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def font(size: int) -> ImageFont.ImageFont:
    candidates = (
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/msjh.ttc"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def contact_sheet(output: Path, title: str, panels: list[tuple[str, Image.Image]], columns: int = 2) -> None:
    if output.exists():
        raise FileExistsError(f"evidence output already exists: {output}")
    label_height = 42
    title_height = 58
    target_width = 720
    prepared: list[tuple[str, Image.Image]] = []
    for label, source in panels:
        image = source.convert("RGB")
        ratio = target_width / image.width
        prepared.append((label, image.resize((target_width, round(image.height * ratio)), Image.Resampling.LANCZOS)))
    rows = (len(prepared) + columns - 1) // columns
    row_heights = []
    for row in range(rows):
        row_heights.append(max(image.height for _, image in prepared[row * columns:(row + 1) * columns]) + label_height)
    canvas = Image.new("RGB", (target_width * columns, title_height + sum(row_heights)), "#23150d")
    draw = ImageDraw.Draw(canvas)
    draw.text((18, 12), title, fill="#fff0c2", font=font(28))
    y = title_height
    for index, (label, image) in enumerate(prepared):
        row = index // columns
        column = index % columns
        panel_y = title_height + sum(row_heights[:row])
        x = column * target_width
        canvas.paste(image, (x, panel_y))
        draw.rectangle((x, panel_y, x + target_width - 1, panel_y + image.height - 1), outline="#d9a72d", width=3)
        draw.text((x + 14, panel_y + image.height + 6), label, fill="#fff0c2", font=font(20))
        y = max(y, panel_y + row_heights[row])
    canvas.save(output, "PNG", optimize=True)


def copy_new(source: Path, target: Path) -> None:
    if target.exists():
        raise FileExistsError(f"evidence output already exists: {target}")
    shutil.copyfile(source, target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--owner-target", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--adapter-result", required=True)
    parser.add_argument("--focused-result", required=True)
    parser.add_argument("--acceptance-result", required=True)
    parser.add_argument("--full-suite-result", required=True)
    args = parser.parse_args()

    evidence = args.evidence.resolve()
    owner_target = args.owner_target.resolve()
    repo = args.repo.resolve()
    if not evidence.is_dir():
        raise FileNotFoundError(f"visual evidence directory missing: {evidence}")

    visual_contract_path = evidence / "e10-vs1f-visual-contract.json"
    geometry_path = evidence / "bottom-dock-geometry.json"
    visual_contract = json.loads(visual_contract_path.read_text(encoding="utf-8"))
    geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
    if not visual_contract.get("ok") or not geometry.get("ok"):
        raise RuntimeError("visual or geometry contract is not passing")

    owner_copy = evidence / "owner-approved-alignment-target.jpg"
    copy_new(owner_target, owner_copy)
    owner_identity = {
        "classification": "OWNER_APPROVED_ALIGNMENT_TARGET",
        "source_path": str(owner_target),
        "evidence_copy": owner_copy.name,
        "bytes": owner_target.stat().st_size,
        "sha256": sha256(owner_target),
        "geometry_contract": [
            "five badges centered on five carved slots",
            "five badge centers share one horizontal centerline",
            "each label plaque shares its badge and slot vertical axis",
            "five slot centers use equal spacing",
            "the complete dock is centered on the stage",
        ],
    }
    (evidence / "owner-approved-alignment-target-identity.json").write_text(
        json.dumps(owner_identity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    aliases = {
        "desktop-1920x1080-closed-zh.png": "desktop-1920-closed-zh.png",
        "desktop-1920x1080-closed-en.png": "desktop-1920-closed-en.png",
        "desktop-1440x900-closed-zh.png": "desktop-1440-closed-zh.png",
        "desktop-1440x900-closed-en.png": "desktop-1440-closed-en.png",
        "tablet-1180x820-closed-zh.png": "ipad-landscape-1180x820.png",
        "tablet-1024x768-closed-zh.png": "ipad-landscape-1024x768.png",
    }
    for source, target in aliases.items():
        copy_new(evidence / source, evidence / target)

    contact_sheet(evidence / "panel-closed-open-contact-sheet.png", "Dock stability: panel closed / open", [
        ("1440 closed", Image.open(evidence / "desktop-1440x900-closed-en.png")),
        ("1440 panel open", Image.open(evidence / "desktop-1440x900-panel-open-en.png")),
    ])
    state_names = ("default", "hover", "focus", "pressed", "active", "disabled")
    contact_sheet(evidence / "bottom-dock-interaction-states-contact-sheet.png", "Bottom Dock interaction geometry", [
        (state.title(), Image.open(evidence / f"bottom-dock-state-{state}.png")) for state in state_names
    ], columns=3)

    desktop_result = next(result for result in visual_contract["results"] if result["specName"] == "desktop-1920-closed")
    screenshot = Image.open(evidence / "desktop-1920x1080-closed-zh.png").convert("RGB")
    dock = desktop_result["snapshot"]["bottomDock"]
    margin = 28
    crop_box = (
        max(0, round(dock["left"] - margin)),
        max(0, round(dock["top"] - margin)),
        min(screenshot.width, round(dock["right"] + margin)),
        min(screenshot.height, round(dock["bottom"] + margin)),
    )
    measured = screenshot.crop(crop_box)
    draw = ImageDraw.Draw(measured)
    viewport_geometry = next(item for item in geometry["viewports"] if item["spec_name"] == "desktop-1920-closed")
    slot_y = viewport_geometry["geometry"]["items"][0]["slot_center_y"] - crop_box[1]
    draw.line((0, slot_y, measured.width, slot_y), fill="#4fffe0", width=2)
    for index, item in enumerate(viewport_geometry["geometry"]["items"], start=1):
        slot_x = item["slot_center_x"] - crop_box[0]
        badge_x = item["badge_center_x"] - crop_box[0]
        label_x = item["label_center_x"] - crop_box[0]
        draw.line((slot_x, 0, slot_x, measured.height), fill="#ffd74f", width=2)
        draw.ellipse((badge_x - 5, slot_y - 5, badge_x + 5, slot_y + 5), outline="#4fffe0", width=3)
        draw.line((label_x, measured.height - 24, label_x, measured.height), fill="#ff6f91", width=3)
        draw.text((slot_x + 5, 5), str(index), fill="#fff7d0", font=font(18))
    measured.save(evidence / "bottom-dock-centerline-measurement.png", "PNG", optimize=True)

    status_lines = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    changed_files = sorted(
        line[3:] for line in status_lines
        if line[3:] != "secret_key.txt"
    )
    (evidence / "changed-file-inventory.json").write_text(json.dumps({
        "starting_head": "d47c8ea772a2527afffb0411a9f917578d39ce2a",
        "files": changed_files,
        "count": len(changed_files),
    }, indent=2) + "\n", encoding="utf-8")
    (evidence / "test-results.json").write_text(json.dumps({
        "adapter": args.adapter_result,
        "focused": args.focused_result,
        "acceptance": args.acceptance_result,
        "full_suite": args.full_suite_result,
        "owner_accepted_provenance_baseline_exceptions": [
            "tests/deployment/test_runtime_dependency_provenance.py::test_working_tree_matches_recorded_content_sha256",
            "tests/deployment/test_runtime_dependency_provenance.py::test_working_tree_matches_recorded_source_commit_blob",
        ],
    }, indent=2) + "\n", encoding="utf-8")

    sums_path = evidence / "SHA256SUMS.txt"
    if sums_path.exists():
        raise FileExistsError(f"evidence output already exists: {sums_path}")
    files = sorted(path for path in evidence.iterdir() if path.is_file())
    (evidence / "evidence-index.json").write_text(json.dumps({
        "contract": "e10-bottom-dock-badge-slot-alignment-evidence-v1",
        "owner_target": owner_identity,
        "geometry_summary": {
            key: geometry[key] for key in (
                "ok", "max_badge_slot_delta_x", "max_badge_slot_delta_y",
                "max_badge_center_y_spread", "max_slot_spacing_variance",
                "max_label_badge_delta_x", "max_dock_stage_center_delta_x", "failures",
            )
        },
        "files_before_index_and_sums": [path.name for path in files],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    files = sorted(path for path in evidence.iterdir() if path.is_file() and path.name != "SHA256SUMS.txt")
    sums_path.write_text("".join(f"{sha256(path)}  {path.name}\n" for path in files), encoding="utf-8")


if __name__ == "__main__":
    main()
