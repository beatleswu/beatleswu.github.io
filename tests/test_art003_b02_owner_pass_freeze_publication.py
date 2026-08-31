"""Focused ART003 B02 Owner-pass freeze and canonical-art publication checks."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image

from tests.art003_admission_scope import ART003_B09_SCOPE_TIP, changed_paths as admission_changed_paths


ROOT = Path(__file__).resolve().parents[1]
B01_HEAD = "0b2f4c7ec65f845918bd96a2daec21551d27ff34"
B02_HEAD = "d3ccac1565b6c5bbe3f357164777f256136d2dc2"
BASE_SHA = "574b3eeb9641c48676e95d3744d204dffca1e1fa"
F039_BASE_HEAD = "c1a55daebc411df46ca4bbfef6c0b814c813ec73"
F039_R1_TEST_FILES = {
    "tests/test_art003_b02_owner_pass_freeze_publication.py",
    "tests/test_art003_b03_production.py",
    "tests/test_art003_b04_production.py",
    "tests/test_art003_b05_production.py",
    "tests/test_art003_b05_r1_publication.py",
    "tests/test_art003_b06_production.py",
    "tests/test_art003_b06_r1_publication.py",
    "tests/test_art003_b07_production.py",
}
F041_B08_ADMISSION_FILES = {
    "art/monsters/M078_potion_gob.png",
    "art/monsters/M079_prism_gecko.png",
    "art/monsters/M080_gravity_crab.png",
    "art/monsters/M081_scrollback_turtle.png",
    "art/monsters/M082_astrolabe_beetle.png",
    "art/monsters/M083_cloudstep_ram.png",
    "art/monsters/M085_blackgate_hound.png",
    "art/monsters/M086_breakshield_beetle.png",
    "art/monsters/M087_bannerbreak_stonebeast.png",
    "art/monsters/M088_stringwing_bat.png",
    "docs/planning/art_003_batch_008_manifest.json",
    "docs/planning/art_003_batch_008_owner_visual_review_pack.md",
    "tests/test_art003_b08_production.py",
}
F043_B09_ADMISSION_FILES = {
    "art/monsters/M089_steelfang_hyena.png",
    "art/monsters/M090_battlement_lizard.png",
    "art/monsters/M091_smokescreen_weasel.png",
    "art/monsters/M092_ironwheel_rhino.png",
    "art/monsters/M093_beacon_scorpion.png",
    "art/monsters/M094_shieldshell_crab.png",
    "art/monsters/M095_obsidian_automaton.png",
    "art/monsters/M096_wallbreak_bear.png",
    "art/monsters/M097_scout_hawkbeast.png",
    "art/monsters/M099_aurora_serpent.png",
    "docs/planning/art_003_batch_009_manifest.json",
    "docs/planning/art_003_batch_009_owner_visual_review_pack.md",
    "tests/test_art003_b09_r1_publication.py",
}
B02_IDS = ("M013", "M014", "M015", "M016", "M017", "M018", "M019", "M020", "M021", "M023")
B01_IDS = ("M002", "M003", "M004", "M005", "M006", "M007", "M008", "M009", "M010", "M012")
B02_HASHES = {
    "M013": "05B1B68AFDC2194E8C556C8A4591F3E4A152FD0159655CCBEC667D2CDD7E163E",
    "M014": "4D0C86CB682CF5BB3B5CE245136AAB3FCE681264B25E214F0368571BB576A327",
    "M015": "AAA618C8688AB2DF06429F5493F890CC768796C8503DB4A1A33BAE8A9272A1D0",
    "M016": "E5807B0EB27426105EE05F4EABCEA8DC0EC394A2393863111179CFCB823D1200",
    "M017": "45133093DA514F9407454FF44095C3DF13BDD1E976D2A9EEAFA1C36F224B9BDC",
    "M018": "BC1C334FE21F2F557FA86EBA5A6FE0B221F1248409A464658D5F6AB39BA7F83F",
    "M019": "B0355111163C595EE47CB71101B6E60E288E72943F5C1CD7C2C710F864DDCAE6",
    "M020": "5501608A189629265D048715003C5AED965D673D6689D45F4461D77A99476BA3",
    "M021": "9309E1E3451477481FBDFEEC55DD7F07B30C0CE5290449743031E2D6E02B745B",
    "M023": "59A3F4BE1B948B30267D3D5311694285CED6F228BDE1CB97435A60748CD89C67",
}
M022_SHA256 = "91F788F87EE4621F85BE7FDC5751134D52BC925FE629776DCC2E27188DE288F8"


def _load_json_without_duplicate_keys(path: Path) -> dict:
    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise AssertionError(f"duplicate JSON key {key!r} in {path}")
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)


def _git_blob(ref: str, path: str) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", f"{ref}:{path}"], cwd=ROOT, text=True
    ).strip()


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _worktree_blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def test_b02_manifest_has_exact_owner_pass_freeze_records():
    manifest = _load_json_without_duplicate_keys(ROOT / "docs/planning/art_003_batch_002_manifest.json")
    assets = manifest["assets"]

    assert manifest["task"] == "ART003_B02_R1_OWNER_PASS_FREEZE_AND_CANONICAL_ART_PUBLICATION_001"
    assert manifest["current_origin_master"] == BASE_SHA
    assert manifest["base_sha"] == BASE_SHA
    assert manifest["b02_source_head"] == B02_HEAD
    assert manifest["fresh_art_reconciliation"] == "PASS"
    assert [asset["monster_id"] for asset in assets] == list(B02_IDS)
    assert len(assets) == 10

    for asset in assets:
        monster_id = asset["monster_id"]
        path = asset["production_asset_path"]
        assert monster_id in B02_HASHES
        assert asset["art_monster_id"] == monster_id
        assert asset["asset_path"] == path
        assert asset["sha256"] == B02_HASHES[monster_id]
        assert asset["file"]["sha256"] == B02_HASHES[monster_id]
        assert asset["owner_visual_status"] == "PASS"
        assert asset["freeze_status"] == "FROZEN"
        assert asset["runtime_mapping_status"] == "NOT_MAPPED"
        assert asset["owner_approved"] == "YES"
        assert asset["canonical_asset"] == "YES"
        assert asset["runtime_mapped"] == "NO"
        assert asset["final_visual_qa_status"] == "PASS"
        assert asset["visual_qa"]["status"] == "PASS"
        assert all(value == "YES" for value in asset["technical_qa"].values())
        assert _sha256(ROOT / path) == B02_HASHES[monster_id]

    assert manifest["owner_review"]["owner_pass_count"] == 10
    assert manifest["owner_review"]["owner_review_pending_count"] == 0
    assert manifest["owner_review"]["b02_owner_acceptance"] == "PASS"
    assert manifest["owner_review"]["canonical_b02_art_count"] == 10
    assert manifest["qa_summary"]["b02_owner_passset_freeze_count"] == 10
    assert manifest["qa_summary"]["art003_canonical_new_art_count"] == 20
    assert manifest["runtime_firewall"]["runtime_mapped_new_art"] == 0


def test_b02_png_qa_and_exact_source_blob_identity():
    manifest = _load_json_without_duplicate_keys(ROOT / "docs/planning/art_003_batch_002_manifest.json")
    for asset in manifest["assets"]:
        path = asset["production_asset_path"]
        with Image.open(ROOT / path) as image:
            image.load()
            assert image.format == "PNG"
            assert image.mode == "RGBA"
            alpha = image.getchannel("A")
            assert any(value > 0 for value in alpha.getextrema())
            assert [alpha.getpixel(point) for point in ((0, 0), (image.width - 1, 0), (0, image.height - 1), (image.width - 1, image.height - 1))] == [0, 0, 0, 0]
            bbox_gt16 = alpha.point(lambda value: 255 if value > 16 else 0).getbbox()
            assert bbox_gt16
            assert bbox_gt16[0] > 0 and bbox_gt16[1] > 0
            assert bbox_gt16[2] < image.width and bbox_gt16[3] < image.height
        assert _worktree_blob(path) == _git_blob(B02_HEAD, path)

    for monster_id in B01_IDS:
        path = next(
            asset["asset_path"]
            for asset in _load_json_without_duplicate_keys(ROOT / "docs/planning/art_003_batch_001_manifest.json")["assets"]
            if asset["art_monster_id"] == monster_id
        )
        assert _worktree_blob(path) == _git_blob(B01_HEAD, path)


def test_board_counts_and_authority_firewall():
    board = _load_json_without_duplicate_keys(ROOT / "docs/planning/art_production_master_board.json")
    gates = board["acceptance_gates"]
    assert board["task"] == "ART003_B02_R1_OWNER_PASS_FREEZE_AND_CANONICAL_ART_PUBLICATION_001"
    assert board["audit_reference"]["current_origin_master"] == BASE_SHA
    assert board["audit_reference"]["reconciliation_base_sha"] == BASE_SHA
    assert board["audit_reference"]["b02_source_head"] == B02_HEAD
    assert gates["B01_STATUS"] == "OWNER_APPROVED_CANONICAL_ART_COMPLETE"
    assert gates["B01_COUNT"] == 10
    assert gates["B01_OWNER_PASS"] == 10
    assert gates["B01_PENDING"] == 0
    assert gates["B01_STATUS_CHANGED"] == "NO"
    assert gates["B02_STATUS"] == "OWNER_APPROVED_CANONICAL_ART_COMPLETE"
    assert gates["B02_GENERATED_COUNT"] == 10
    assert gates["B02_OWNER_PASSSET_FREEZE_COUNT"] == 10
    assert gates["B02_OWNER_PASS"] == 10
    assert gates["B02_PENDING"] == 0
    assert gates["B02_REVISE"] == 0
    assert gates["B02_REJECT"] == 0
    assert gates["B02_CANONICAL_ART_COUNT"] == 10
    assert gates["B02_HASH_COUNT"] == 10
    assert gates["B02_HASH_UNIQUE_COUNT"] == 10
    assert gates["ART003_CANONICAL_NEW_ART_COUNT"] == 20
    assert gates["ART003_RUNTIME_MAPPED_NEW_ART_COUNT"] == 0
    assert gates["RUNTIME_MAPPED_NEW_ART"] == 0
    assert gates["ART_PIXEL_MUTATIONS"] == 0
    assert gates["ART_REGENERATION"] == 0
    assert gates["ART_REENCODING"] == 0
    assert gates["M022_CHANGED"] == "NO"
    assert gates["M022_REDRAWN"] == "NO"
    assert gates["M022_RUNTIME_REFERENCE_CHANGED"] == "NO"
    assert gates["APP_PY_CHANGED"] == "NO"
    assert gates["RUNTIME_SOURCE_CHANGED"] == "NO"
    assert gates["RUNTIME_MAPPING_CHANGED"] == "NO"
    for lane in ("A044_SCOPE_TOUCHED", "B058_SCOPE_TOUCHED", "E047_SCOPE_TOUCHED", "F035_SCOPE_TOUCHED", "LC015_SCOPE_TOUCHED"):
        assert gates[lane] == "NO"
    assert gates["B02_INCLUDED_IN_B058"] == "NO"
    assert gates["ART003_PRODUCTION_STATUS"] == "B01_B02_COMPLETE_READY_FOR_B03"

    b02_board_assets = board["art003_b02"]["assets"]
    assert [asset["M_ID"] for asset in b02_board_assets] == list(B02_IDS)
    assert all(asset["VISUAL_QA"] == "PASS" for asset in b02_board_assets)
    assert all(asset["OWNER_VISUAL_STATUS"] == "PASS" for asset in b02_board_assets)
    assert all(asset["FREEZE_STATUS"] == "FROZEN" for asset in b02_board_assets)
    assert all(asset["RUNTIME_MAPPING_STATUS"] == "NOT_MAPPED" for asset in b02_board_assets)


def test_m022_is_unchanged_and_no_runtime_scope_is_in_diff():
    assert _sha256(ROOT / "assets/monsters/orc_grunt_chibi.png") == M022_SHA256
    changed = admission_changed_paths(canonical_tip=ART003_B09_SCOPE_TIP, candidate_base=F039_BASE_HEAD)
    changed -= F041_B08_ADMISSION_FILES
    changed -= F043_B09_ADMISSION_FILES
    assert changed <= F039_R1_TEST_FILES
    assert "app.py" not in changed
    assert "assets/monsters/orc_grunt_chibi.png" not in changed
