"""Read-only syllabus import. Run explicitly; never publish or mint identities."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

BASE_SHA = "d0f16e6ed1f7283ea39a1826d52a464a8a981cba"
PRIMARY = {"示範": "demo", "練習": "practice", "單元測驗": "quiz", "結業考": "graduation"}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(syllabus: Path, videos: Path):
    csv_path = syllabus / "啟蒙班_題目分配.csv"
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig", newline="")))
    lessons, media = [], []
    for n in range(1, 21):
        selected = [r for r in rows if int(r["課"]) == n]
        title = selected[0]["課名"]
        groups = {k: [] for k in (*PRIMARY.values(), "reserve", "challenge")}
        for row in selected:
            role = PRIMARY.get(row["用途"], {"備用": "reserve", "挑戰": "challenge"}.get(row["用途"]))
            if role is None:
                raise ValueError("unknown syllabus role")
            # Legacy aliases are reference data only, NOT canonical identifiers.
            groups[role].append({"legacy_question_id": int(row["題號"]), "order": int(row["順序"]),
                                 "canonical_id": None, "revision": None, "katago_status": "UNKNOWN"})
        if len(groups["practice"]) != 8 or len({q["legacy_question_id"] for q in groups["practice"]}) != 8:
            raise ValueError(f"lesson {n}: eight distinct practices required")
        lesson_id = f"v1-init-{n:02}"
        video = videos / f"啟蒙班_第{n}課_{title}.mp4"
        script = videos / f"啟蒙班_第{n}課_{title}_腳本.txt"
        media.append({"lesson_id": lesson_id, "source_file": video.name, "sha256": digest(video),
                      "bytes": video.stat().st_size, "script_sha256": digest(script),
                      "external_url": None, "owner_review": "PENDING", "packaged": False})
        lessons.append({"id": lesson_id, "number": n, "week": (n - 1) // 5 + 1,
                        "title": title, "questions": groups})
    primary_count = sum(len(l["questions"][role]) for l in lessons for role in PRIMARY.values())
    if primary_count != 240:
        raise ValueError("primary syllabus must have 240 assignments")
    catalog = {"schema": "g066-course-catalog-v1", "version": "initiation-20261022-v1",
               "source_base_sha": BASE_SHA, "runtime_enabled": False,
               "source_receipts": [{"name": p.name, "sha256": digest(p)} for p in
                                   (csv_path, syllabus / "啟蒙班_課表.html", syllabus / "啟蒙班_課表.pdf")],
               "assignment_counts": {"csv_rows": len(rows), "primary": primary_count,
                                     "auxiliary": len(rows) - primary_count},
               "candidate_rules": {"owner_approved": False, "enabled": False, "new_lessons_per_day": 2,
                                   "retries_per_day": 3, "separate_from_free_daily_20": True},
               "lessons": lessons}
    return catalog, {"schema": "g066-external-media-v1", "assets": media}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--syllabus", type=Path, required=True)
    parser.add_argument("--videos", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in zip(("catalog.json", "media-manifest.json"), build(args.syllabus, args.videos)):
        (args.output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
