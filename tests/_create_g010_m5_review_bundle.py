"""Prepare G010 M5 explicit-source review ZIP; never include secrets or data.

This is a review bundle, NOT a signed Build provenance receipt or release.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/"docs/handoffs/G010_M5_OWNER_SOURCE_REVIEW_BUNDLE_20261020.zip"
TRACKED=[
 "Dockerfile","deploy/build-manifest.json",
 "app.py","community.html","index.html","map_battle_runtime.py",
 "shop.html","tests/e2e/run_20261019_real_lord_20_wgo_browser.mjs",
]
NEW=[
 "g010_m4_quest_leaderboard.js",
 "g010_m4_quest_leaderboard.css",
 "tests/e2e/run_20261020_g010_m2_reward_readback_browser.mjs",
 "tests/e2e/run_20261020_g010_m3_shop_purchase_equip_real_browser.mjs",
 "tests/e2e/run_20261020_g010_m4_quest_off_real_browser.mjs",
 "tests/e2e/run_20261020_g010_m4_quest_rank_real_browser.mjs",
 "tests/e2e/run_20261020_g010_zone2_lord_20_wgo_browser.mjs",
 "tests/e2e/run_20261020_zone2_first_entry_browser.mjs",
 "tests/e2e/run_20261020_shop_backpack_governed_browser.mjs",
 "tests/e2e/test_20261020_adventure_map_node_route.cjs",
 "tests/e2e/test_20261020_g010_m3_expanded_offer_admission.cjs",
 "tests/test_20261020_g010_m1_zone2_monster_lord_native_pg.py",
 "tests/test_20261020_g010_m2_reward_closed_loop_native_pg.py",
 "tests/test_20261020_g010_m3_shop_player_native_pg.py",
 "tests/test_20261020_g010_m4_quest_rank_native_pg.py",
 "tests/test_20261020_g010_m5_unified_one_player_pg.py",
 "tests/test_20261020_g010_zone2_quest_claim_native_pg.py",
 "tests/test_20261020_shop_native_pg_relogin.py",
 "tests/test_20261020_zone2_first_play_native_pg.py",
 "tests/_run_g010_m2_disposable_pg_claim_concurrency.py",
 "tests/_run_g010_m3_disposable_pg_item_use.py",
 "tests/_run_g010_m5_sanitized_docker_candidate.py",
 "tests/_verify_g010_rc_image_source_integrity.py",
 "tests/_run_g010_rc2_arm64_local_build.py",
 "tests/_g010_rc2_arm64_builder_generated.py",
 "tests/_verify_g010_rc2_arm64_image_integrity.py",
 "tests/_verify_g010_rc2_release_admission_no_go.py",
 "tests/_verify_g010_rc3_source_adoption_inputs.py",
 "tests/test_20261020_g010_rc3_reviewer_adversarial.py",
 "tests/_create_g010_m5_review_bundle.py",
 "docs/handoffs/GO_ODYSSEY_G010_RC_IMAGE_SOURCE_INTEGRITY_20261020.json",
 "docs/handoffs/GO_ODYSSEY_G010_RC_STAGE1_LOCAL_SOURCE_IMAGE_PASS_20261020.md",
 "docs/handoffs/G010_RC2_ARM64_LOCAL_BUILD_EVIDENCE_20261020.json",
 "docs/handoffs/GO_ODYSSEY_G010_RC2_ARM64_IMAGE_SOURCE_INTEGRITY_20261020.json",
 "docs/handoffs/GO_ODYSSEY_G010_RC2_RELEASE_ADMISSION_NO_GO_MATRIX_20261020.json",
 "docs/handoffs/GO_ODYSSEY_G010_RC2_ARM64_AND_RELEASE_GATE_LOCAL_PASS_20261020.md",
 "docs/handoffs/GO_ODYSSEY_G010_RC3_REMOTE_MASTER_READ_ONLY_20261020.json",
 "docs/handoffs/GO_ODYSSEY_G010_RC3_INDEPENDENT_REVIEW_INPUT_HANDOFF_20261020.md",
 "docs/handoffs/GO_ODYSSEY_G010_M1_ZONE2_MONSTER_QUEST_LORD_COMPLETE_20261020.md",
 "docs/handoffs/GO_ODYSSEY_G010_M2_REWARD_CLOSED_LOOP_CANDIDATE_PASS_20261020.md",
 "docs/handoffs/GO_ODYSSEY_G010_M3_REAL_SHOP_BACKPACK_PLAYER_STAGE_PASS_20261020.md",
 "docs/handoffs/GO_ODYSSEY_G010_M4_QUEST_LEADERBOARD_REAL_PLAYER_PASS_20261020.md",
 "docs/handoffs/GO_ODYSSEY_G010_M5_LOCAL_ENGINEERING_PASS_FORMAL_RELEASE_NO_GO_20261020.md",
 "docs/handoffs/G010_M5_LOCAL_CANDIDATE_BUILD_EVIDENCE_20261020.json",
]
DENIED={"secret_key.txt",".env",".env.production","id_rsa",
        "credentials.json","users.db","users.sqlite","katago_cache.db"}
def digest(blob):
 return hashlib.sha256(blob).hexdigest()
def main():
 assert subprocess.check_output(
  ["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip() == (
    "efd4524c3a3b5669b693ee0be50acf586c73ad90")
 files=TRACKED+NEW
 assert len(set(files))==len(files)
 assert all("/../" not in f and not f.startswith(("/","."))
            and ".." not in Path(f).parts for f in files)
 assert not any(Path(f).name in DENIED for f in files)
 patch=subprocess.run(["git","diff","--binary","--",*TRACKED],
   capture_output=True,check=True,cwd=ROOT).stdout
 assert len(patch)>0
 rec={
   "bundle_kind":"OWNER_REVIEW_ONLY_NOT_BUILD_ATTESTATION",
   "baseline_commit":"efd4524c3a3b5669b693ee0be50acf586c73ad90",
   "formal_owner_approval":"NOT_GIVEN",
   "true_iPad_owner_uat":"NOT_PERFORMED",
   "independent_source_signature":"NOT_VERIFIED",
   "product_deployed":False,
   "included_files":{},
   "source_patch_sha256":digest(patch),
 }
 DEST.parent.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(DEST,"w",zipfile.ZIP_DEFLATED,compresslevel=7) as z:
  z.writestr("tracked_changes.patch",patch)
  for relative in files:
   full=ROOT/relative
   assert full.is_file(),f"source review file absent {relative}"
   raw=full.read_bytes()
   assert len(raw)>0
   rec["included_files"][relative]=digest(raw)
   z.writestr("candidate_files/"+relative.replace("\\","/"),raw)
  z.writestr("SOURCE_REVIEW_MANIFEST.json",
    json.dumps(rec,indent=2,ensure_ascii=False).encode("utf-8"))
 with zipfile.ZipFile(DEST) as z:
  assert "candidate_files/app.py" in z.namelist()
  assert "candidate_files/g010_m4_quest_leaderboard.js" in z.namelist()
  assert not any(Path(x).name in DENIED for x in z.namelist())
  assert z.testzip() is None
 print("G010_M5_OWNER_REVIEW_BUNDLE_PASS=TRUE")
 print("BUNDLE="+str(DEST))
 print("BUNDLE_SHA256="+digest(DEST.read_bytes()))
 print("BUNDLE_BYTES="+str(DEST.stat().st_size))
 print("FILES="+str(len(files)))
 print("TRUSTED_RELEASE_ATTESTATION=NOT_VERIFIED")
if __name__=="__main__":main()
