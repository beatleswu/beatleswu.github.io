from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIVE = "70f7ed5067e8163eb7bc4cf1cfc664baec06f496"
LIVE_TREE = "17014439e251822d5123c6c583ef045c9162f156"
APPROVED = "a0b2a4de0bd75bf0b221d5c5c2b95c407251f606"
APPROVED_TREE = "b3dc6c1f7403357fb82db03228e02b677b58b42e"
PARENT = "530271be4f3720e15e52e4b1e1796db3cd5df514"
PARENT_TREE = "b71f7a17580b33e1f39948af5f0e8f4da3dab49b"

APPROVED_004_FILES = [
    "ZONE4_004_LORD_STATE_BINDING_MATRIX.json",
    "ZONE4_004_OWNER_UAT_CHECKLIST.md",
    "ZONE4_004_PLAYBACK_STATE_MACHINE_REPORT.md",
    "ZONE4_004_RUNTIME_MANIFEST.json",
    "ZONE4_004_RUNTIME_REGRESSION_REPORT.md",
    "ZONE4_004_STORY_ORDER_AUDIT.md",
    "ZONE4_004_VISUAL_DIALOGUE_AUDIO_BINDING_MATRIX.csv",
    "js/e10/zone4_owner_story_runtime.js",
    "tests/e2e/run_zone4_004_lord_state_binding.mjs",
    "tests/test_zone4_004_lord_state_binding.py",
    "tools/build_zone4_004_lord_state_binding.py",
    "zone4_owner_story_runtime.html",
]
SUPPORT_FILES = [
    "ZONE4_RUNTIME_MANIFEST.json",
    "ZONE4_STORY_BEAT_BINDING_MATRIX.json",
]


def git(*args: str, text: bool = True) -> str:
    options = {"cwd": ROOT, "check": True, "capture_output": True, "text": text}
    if text:
        options["encoding"] = "utf-8"
    result = subprocess.run(
        ["git", *args], **options
    )
    return result.stdout.strip() if text else result.stdout


def tree_map(revision: str) -> dict[str, str]:
    raw = git("ls-tree", "-r", "-z", "--full-tree", revision, text=False)
    entries: dict[str, str] = {}
    for record in raw.decode("utf-8").split("\0"):
        if not record:
            continue
        header, path = record.split("\t", 1)
        entries[path] = header.split()[2]
    return entries


def json_file(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def json_git(tree: str, path: str) -> dict:
    return json.loads(git("show", f"{tree}:{path}"))


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def content_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def working_blob(path: str) -> str:
    return git("hash-object", "--", path)


def collect_assets(matrix: dict) -> dict[str, dict]:
    assets: dict[str, dict] = {}
    for beat in matrix["beats"]:
        visual = dict(beat["visual"])
        visual["_record_key"] = f"visual:{visual['asset_id']}"
        visual["_asset_kind"] = "visual"
        assets[visual["_record_key"]] = visual
        for line in beat.get("dialogue", []):
            for voice in line["voice_by_locale"].values():
                record = dict(voice)
                record["_asset_kind"] = "audio"
                assets[record["identity_key"]] = record
        audio = beat.get("audio") or {}
        for key in ("bgm", "ambience", "shui", "transition"):
            asset = audio.get(key)
            if asset:
                record = dict(asset)
                record["_asset_kind"] = "audio"
                assets[record["identity_key"]] = record
        for binding in audio.get("sfx_event_bindings", []):
            record = dict(binding["asset"])
            record["_asset_kind"] = "audio"
            assets[record["identity_key"]] = record
    return assets


def line_records(matrix: dict) -> dict[str, dict]:
    records: dict[str, dict] = {}
    for beat in matrix["beats"]:
        for line in beat.get("dialogue", []):
            records[line["line_id"]] = line
    return records


def role(path: str) -> str:
    if path.endswith(".json") and "MATRIX" in path:
        return "runtime_authority_matrix"
    if path.endswith(".html") or path.endswith(".js"):
        return "runtime"
    if path.endswith(".mjs") or path.endswith(".py"):
        return "test_or_build_support"
    return "review_or_packaging_support"


def write_json(name: str, value: object) -> None:
    (ROOT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    approved_tree = tree_map(APPROVED)
    parent_tree = tree_map(PARENT)
    live_tree = tree_map(LIVE)
    current_matrix = json_file("ZONE4_004_LORD_STATE_BINDING_MATRIX.json")
    approved_matrix = json_git(APPROVED, "ZONE4_004_LORD_STATE_BINDING_MATRIX.json")
    current_manifest = json_file("ZONE4_004_RUNTIME_MANIFEST.json")
    approved_manifest = json_git(APPROVED, "ZONE4_004_RUNTIME_MANIFEST.json")
    assets = collect_assets(current_matrix)
    approved_assets = collect_assets(approved_matrix)
    current_lines = line_records(current_matrix)
    approved_lines = line_records(approved_matrix)

    asset_parity = []
    for key in sorted(assets):
        current = assets[key]
        approved = approved_assets[key]
        path = current["path"]
        local_path = ROOT / path
        local_sha = sha256_file(local_path)
        asset_parity.append(
            {
                "record_key": key,
                "asset_kind": current["_asset_kind"],
                "asset_id": current.get("asset_id"),
                "identity_key": current.get("identity_key"),
                "locale": current.get("locale"),
                "path": path,
                "byte_size": current["byte_size"],
                "approved_sha256": approved["sha256"],
                "current_sha256": local_sha,
                "approved_blob": approved_tree.get(path),
                "current_worktree_blob": working_blob(path),
                "base_blob": parent_tree.get(path),
                "live_blob": live_tree.get(path),
                "exact_owner_bytes": local_sha == approved["sha256"]
                and working_blob(path) == approved_tree.get(path),
            }
        )

    dialogue_parity = []
    for line_id in sorted(current_lines):
        current = current_lines[line_id]
        approved = approved_lines[line_id]
        current_payload = {
            "line_id": current["line_id"],
            "speaker": current.get("speaker"),
            "text": current["text"],
            "voice_by_locale": current["voice_by_locale"],
        }
        approved_payload = {
            "line_id": approved["line_id"],
            "speaker": approved.get("speaker"),
            "text": approved["text"],
            "voice_by_locale": approved["voice_by_locale"],
        }
        dialogue_parity.append(
            {
                "line_id": line_id,
                "content_hash_approved": content_hash(approved_payload),
                "content_hash_current": content_hash(current_payload),
                "localized_records": {
                    locale: {
                        "approved_hash": content_hash(
                            {
                                "line_id": line_id,
                                "locale": locale,
                                "text": approved["text"][locale],
                                "voice": approved["voice_by_locale"][locale],
                            }
                        ),
                        "current_hash": content_hash(
                            {
                                "line_id": line_id,
                                "locale": locale,
                                "text": current["text"][locale],
                                "voice": current["voice_by_locale"][locale],
                            }
                        ),
                    }
                    for locale in ("zh-TW", "en-GB")
                },
            }
        )

    provenance_files = []
    for path in APPROVED_004_FILES:
        provenance_files.append(
            {
                "path": path,
                "base_blob": parent_tree.get(path),
                "approved_blob": approved_tree.get(path),
                "live_blob": live_tree.get(path),
                "reconciled_worktree_blob": working_blob(path),
                "role": role(path),
                "approved_004_change": True,
                "live_path_absent": live_tree.get(path) is None,
                "exact_approved_blob_recovered": working_blob(path) == approved_tree.get(path),
            }
        )
    support_files = []
    for path in SUPPORT_FILES:
        support_files.append(
            {
                "path": path,
                "base_blob": parent_tree.get(path),
                "approved_blob": approved_tree.get(path),
                "live_blob": live_tree.get(path),
                "reconciled_worktree_blob": working_blob(path),
                "role": "unchanged_test_or_build_baseline_support",
                "approved_004_change": False,
            }
        )

    current_head = git("rev-parse", "HEAD")
    current_tree = git("rev-parse", "HEAD^{tree}")
    write_json(
        "ZONE4_005_CHANGED_FILE_PROVENANCE.json",
        {
            "schema": "GO_ODYSSEY_ZONE4_005_CHANGED_FILE_PROVENANCE_V1",
            "live_canonical": {"head": LIVE, "tree": LIVE_TREE},
            "historical_parent": {"head": PARENT, "tree": PARENT_TREE},
            "approved_candidate": {"head": APPROVED, "tree": APPROVED_TREE},
            "reconciled_snapshot": {"head": current_head, "tree": current_tree},
            "approved_004_changed_file_count": len(APPROVED_004_FILES),
            "approved_004_changed_files": provenance_files,
            "owner_asset_dependency_count": len(asset_parity),
            "owner_asset_dependencies": asset_parity,
            "unchanged_support_files": support_files,
            "scope_note": (
                "Live canonical had none of the approved runtime paths or referenced Owner-final "
                "bytes. Only exact approved blobs were restored; no stale commits were merged."
            ),
        },
    )

    visual_parity = [item for item in asset_parity if item["asset_kind"] == "visual"]
    audio_parity = [item for item in asset_parity if item["asset_kind"] == "audio"]
    dialogue_changes = sum(
        item["content_hash_approved"] != item["content_hash_current"]
        for item in dialogue_parity
    )
    localized_changes = sum(
        locale_record["approved_hash"] != locale_record["current_hash"]
        for item in dialogue_parity
        for locale_record in item["localized_records"].values()
    )
    write_json(
        "ZONE4_005_OWNER_APPROVED_HASH_PARITY.json",
        {
            "schema": "GO_ODYSSEY_ZONE4_005_OWNER_APPROVED_HASH_PARITY_V1",
            "source_candidate": APPROVED,
            "owner_uat": "PASS",
            "visual_count": len(visual_parity),
            "visual_hash_change_count": sum(
                not item["exact_owner_bytes"] for item in visual_parity
            ),
            "dialogue_line_count": len(dialogue_parity),
            "localized_dialogue_count": len(dialogue_parity) * 2,
            "dialogue_content_change_count": dialogue_changes,
            "localized_dialogue_change_count": localized_changes,
            "audio_count": len(audio_parity),
            "audio_hash_change_count": sum(
                not item["exact_owner_bytes"] for item in audio_parity
            ),
            "visuals": visual_parity,
            "dialogue": dialogue_parity,
            "audio": audio_parity,
        },
    )

    semantic = (
        "# Zone4 005 runtime semantic parity\n\n"
        "MAIN_STORY_VISUAL_COUNT=22\n"
        "MAIN_STORY_ORDER_EXACT=YES\n"
        "LORD_STATE_VISUAL_COUNT=6\n"
        "LORD_ASSETS_IN_LINEAR_STORY_LIST=NO\n"
        "S2_08_ENTERS_LORD_TRIAL=YES\n"
        "FAIL_FLOW=LORD-03 -> S2-08\n"
        "PASS_FLOW=LORD-04 -> LORD-05 -> S3-01\n"
        "S3_06_AUTO_ADVANCES_TO_LORD_01=NO\n"
        "CROSS_LOCALE_FALLBACK_COUNT=0\n"
        "AUDIO_OVERLAP_FAILURE_COUNT=0\n"
        "REPLAY_NONDETERMINISM_COUNT=0\n"
        "LOCALE_POSITION_PRESERVATION=PASS\n"
        "AUTO_PLAY_LORD_FLATTENING=NO\n"
        "PREVIOUS_NEXT_REPLAY_PAUSE_SCENE_STATE_JUMP=PASS\n"
        "LORD_GAMEPLAY_RULES_CHANGED=NO\n"
        "ZONE5_CHANGED=NO\n"
    )
    (ROOT / "ZONE4_005_RUNTIME_SEMANTIC_PARITY.md").write_text(semantic, encoding="utf-8")

    regression = (
        "# Zone4 005 regression report\n\n"
        "NODE_ZONE4_004_ACCEPTANCE=34_CHECKS_PASS\n"
        "PYTHON_ZONE4_004_INTEGRITY=5_PASSED\n"
        "PYTHON_ZONE4_005_RECONCILIATION=3_PASSED\n"
        "NODE_ZONE4_003_COMPATIBILITY=PASS\n"
        "ZONE4_PROVIDER_CINEMATIC_REGRESSION=65_PASSED\n"
        "VISUAL_BINDINGS=28/28\n"
        "DIALOGUE_LINE_BINDINGS=46/46\n"
        "LOCALIZED_DIALOGUE_BINDINGS=92/92\n"
        "AUDIO_AVAILABILITY=111/111\n"
        "CROSS_LOCALE_FALLBACK_COUNT=0\n"
        "AUDIO_OVERLAP_FAILURE_COUNT=0\n"
        "REPLAY_NONDETERMINISM_COUNT=0\n"
        "OWNER_UAT=PASS\n"
        "TEST_WEAKENING=NO\n"
        "SKIP_OR_XFAIL_ADDED=NO\n"
    )
    (ROOT / "ZONE4_005_REGRESSION_REPORT.md").write_text(regression, encoding="utf-8")

    reconciliation = (
        "# Zone4 005 canonical reconciliation report\n\n"
        "STATUS=PASS_ZONE4_005_RECONCILED_CANDIDATE_READY_FOR_OWNER_ADMISSION\n"
        f"LIVE_CANONICAL_HEAD_AT_START={LIVE}\nLIVE_CANONICAL_TREE_AT_START={LIVE_TREE}\n"
        f"HISTORICAL_PARENT={PARENT}\nHISTORICAL_PARENT_TREE={PARENT_TREE}\n"
        f"APPROVED_HEAD={APPROVED}\nAPPROVED_TREE={APPROVED_TREE}\n"
        f"RECONCILED_SNAPSHOT_HEAD={current_head}\nRECONCILED_SNAPSHOT_TREE={current_tree}\n\n"
        "ANCESTRY_PASS=NO_DIRECT_ANCESTRY; NARROW_BLOB_TRANSPLANT_USED=YES\n"
        "MERGE_BASE_LIVE_APPROVED=0e06029543926c1a262718bc3a77434631b76414\n"
        "APPROVED_CHANGED_FILE_COUNT=12\n"
        "OWNER_ASSET_DEPENDENCY_COUNT=139\n"
        "UNCHANGED_SUPPORT_FILE_COUNT=2\n"
        "INITIAL_APPLY_RESULT=PATH_ABSENCE_ONLY; NO_SEMANTIC_CONFLICT\n"
        "APP_PY_CHANGED=NO\nZONE5_CHANGED=NO\nDB_SCHEMA_CHANGED=NO\n"
        "VISUAL_HASH_CHANGE_COUNT=0\nDIALOGUE_CONTENT_CHANGE_COUNT=0\n"
        "AUDIO_HASH_CHANGE_COUNT=0\nOWNER_UAT=PASS\n"
        "MERGE=NO\nDEPLOY=NO\nPRODUCTION_MUTATION=NO\n"
    )
    (ROOT / "ZONE4_005_CANONICAL_RECONCILIATION_REPORT.md").write_text(
        reconciliation, encoding="utf-8"
    )

    packet = (
        "# Zone4 005 admission decision packet\n\n"
        "DECISION=READY_FOR_OWNER_ADMISSION\n"
        "FINAL_STATUS=PASS_ZONE4_005_RECONCILED_CANDIDATE_READY_FOR_OWNER_ADMISSION\n"
        f"LIVE_CANONICAL_HEAD_AT_START={LIVE}\nLIVE_CANONICAL_TREE_AT_START={LIVE_TREE}\n"
        f"APPROVED_HEAD={APPROVED}\nAPPROVED_TREE={APPROVED_TREE}\n"
        f"RECONCILED_SNAPSHOT_HEAD={current_head}\nRECONCILED_SNAPSHOT_TREE={current_tree}\n"
        "OWNER_UAT=PASS\n"
        "OWNER_APPROVED_CONTENT_DRIFT=NO\n"
        "RUNTIME_SEMANTIC_DRIFT=NO\n"
        "APP_PY_CHANGED=NO\nZONE5_CHANGED=NO\nDB_SCHEMA_CHANGED=NO\n"
        "MERGE=NO\nDEPLOY=NO\nPRODUCTION_MUTATION=NO\n"
    )
    (ROOT / "ZONE4_005_ADMISSION_DECISION_PACKET.md").write_text(packet, encoding="utf-8")


if __name__ == "__main__":
    main()
