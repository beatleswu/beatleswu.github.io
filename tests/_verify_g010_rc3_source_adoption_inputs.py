"""G010 RC3: read-only adoption input verifier and adversarial source tests.

Independent from the ZIP packager and Docker build scripts, but NOT an
externally trusted reviewer. This only checks byte integrity and prepares
a bounded handoff for such a reviewer. Zero Git writes, network, passwords,
private keys, source commit, master merge or release authorization.
"""
from __future__ import annotations
from collections import Counter
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
from tempfile import TemporaryDirectory
import zipfile

ROOT=Path(__file__).resolve().parents[1]
BASE_SHA="efd4524c3a3b5669b693ee0be50acf586c73ad90"
BUNDLE=ROOT/"docs/handoffs/G010_M5_OWNER_SOURCE_REVIEW_BUNDLE_20261020.zip"
IMAGE=ROOT/"docs/handoffs/GO_ODYSSEY_G010_RC2_ARM64_IMAGE_SOURCE_INTEGRITY_20261020.json"
EVID=ROOT/"docs/handoffs/G010_RC2_ARM64_LOCAL_BUILD_EVIDENCE_20261020.json"
OUTPUT=ROOT/"docs/handoffs/GO_ODYSSEY_G010_RC3_SOURCE_ADOPTION_INPUT_AUDIT_20261020.json"
SRC_ROOT="candidate_files/"
BAD_BASENAMES={"secret_key.txt","credentials.json",".env",".env.production",
               "id_rsa","users.db","users.sqlite","katago_cache.db"}
REQUIRED={
 "Dockerfile","deploy/build-manifest.json","app.py","community.html",
 "index.html","map_battle_runtime.py","shop.html",
 "g010_m4_quest_leaderboard.js","g010_m4_quest_leaderboard.css",
 "tests/test_20261020_g010_m1_zone2_monster_lord_native_pg.py",
 "tests/test_20261020_g010_m2_reward_closed_loop_native_pg.py",
 "tests/test_20261020_g010_m3_shop_player_native_pg.py",
 "tests/test_20261020_g010_m4_quest_rank_native_pg.py",
 "tests/test_20261020_g010_m5_unified_one_player_pg.py",
}
PRODUCTION_RUNTIME={
 "app.py","community.html","index.html","map_battle_runtime.py",
 "shop.html","g010_m4_quest_leaderboard.js",
 "g010_m4_quest_leaderboard.css",
}
def digest(raw:bytes)->str:
 return hashlib.sha256(raw).hexdigest()
def valid_rel(name:str)->bool:
 if not name or "\\" in name or any(ord(c)<32 for c in name):
  return False
 if name.startswith(("/",".",":")) or re.match(r"^[a-zA-Z]:",name):
  return False
 p=PurePosixPath(name)
 return all(part not in (".","..","") for part in p.parts)
def verify_zip(raw:bytes, *, strict_inventory:bool=True) -> dict:
 """Verify even adversarial ZIP metadata without extracting any file."""
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  infos=z.infolist()
  # A review ZIP is not a place for unbounded decompression.
  if len(infos)>128 or any(i.file_size>24_000_000 for i in infos) or sum(
      i.file_size for i in infos)>60_000_000:
   raise ValueError("UNBOUNDED_REVIEW_ARCHIVE")
  names=[i.filename for i in infos]
  if len(names)!=len(set(names)):
   raise ValueError("DUPLICATE_ZIP_MEMBER")
  for i in infos:
   if i.is_dir() or not valid_rel(i.filename):
    raise ValueError("UNSAFE_MEMBER_PATH")
   if (i.external_attr>>16)&0o170000==stat.S_IFLNK:
    raise ValueError("ZIP_SYMLINK_NOT_ALLOWED")
   if PurePosixPath(i.filename).name.lower() in BAD_BASENAMES:
    raise ValueError("SECRET_OR_DATABASE_NAME_IN_REVIEW")
  if "SOURCE_REVIEW_MANIFEST.json" not in names or "tracked_changes.patch" not in names:
   raise ValueError("REQUIRED_MANIFEST_MISSING")
  metadata=json.loads(z.read("SOURCE_REVIEW_MANIFEST.json"))
  if metadata.get("bundle_kind")!="OWNER_REVIEW_ONLY_NOT_BUILD_ATTESTATION":
   raise ValueError("CLAIMED_TRUSTED_ATTESTATION")
  if metadata.get("baseline_commit")!=BASE_SHA:
   raise ValueError("UNEXPECTED_BASELINE")
  if metadata.get("product_deployed") is not False:
   raise ValueError("IMPROPER_DEPLOYMENT_CLAIM")
  if (metadata.get("independent_source_signature")!="NOT_VERIFIED"
      or metadata.get("formal_owner_approval")!="NOT_GIVEN"
      or metadata.get("true_iPad_owner_uat")!="NOT_PERFORMED"):
   raise ValueError("FORGED_TRUST_OR_OWNER_ATTESTATION")
  files=metadata.get("included_files")
  if not isinstance(files,dict) or not REQUIRED<=set(files):
   raise ValueError("REVIEW_FILES_MISSING")
  expected={SRC_ROOT+n for n in files}
  if set(names)!=(expected|{"SOURCE_REVIEW_MANIFEST.json","tracked_changes.patch"}):
   raise ValueError("ARCHIVE_MEMBERS_DO_NOT_MATCH_MANIFEST")
  for name,pinned in files.items():
   if not valid_rel(name) or PurePosixPath(name).name.lower() in BAD_BASENAMES:
    raise ValueError("INVALID_INVENTORY_ENTRY")
   if not re.fullmatch(r"[0-9a-f]{64}",pinned):
    raise ValueError("NON_SHA256_DIGEST")
   if digest(z.read(SRC_ROOT+name))!=pinned:
    raise ValueError("TAMPERED_MEMBER:"+name)
  if digest(z.read("tracked_changes.patch"))!=metadata["source_patch_sha256"]:
   raise ValueError("TAMPERED_TRACKED_PATCH")
  if strict_inventory:
   if set(files)!={p for p in files if (ROOT/p).is_file()}:
    raise ValueError("FILE_NOT_ON_REVIEW_WORKTREE")
   for name,pinned in files.items():
    if digest((ROOT/name).read_bytes())!=pinned:
     raise ValueError("WORKTREE_DRIFT:"+name)
  return {
   "members":len(files),
   "manifest":metadata,
   "patch_digest":metadata["source_patch_sha256"],
  }

def git(*args:str):
 p=subprocess.run(["git",*args],cwd=ROOT,check=True,capture_output=True,
  encoding="utf-8",errors="replace",timeout=35)
 return p.stdout.strip()
def check_tracked_patch(manifest:dict):
 paths=[
  "Dockerfile","deploy/build-manifest.json","app.py","community.html",
  "index.html","map_battle_runtime.py","shop.html",
  "tests/e2e/run_20261019_real_lord_20_wgo_browser.mjs",
 ]
 p=subprocess.run(["git","diff","--binary","--",*paths],
  cwd=ROOT,check=True,capture_output=True,timeout=45)
 if digest(p.stdout)!=manifest["source_patch_sha256"]:
  raise ValueError("PATCH_DRIFT_FROM_WORKTREE")

def evaluate_custody(*,bundle_override:bytes|None=None,
                     run_docker:bool=True)->dict:
 raw=BUNDLE.read_bytes() if bundle_override is None else bundle_override
 details=verify_zip(raw,strict_inventory=bundle_override is None)
 manifest=details["manifest"]
 if git("rev-parse","HEAD")!=BASE_SHA:
  raise ValueError("GIT_HEAD_DRIFT")
 check_tracked_patch(manifest)
 m5=json.loads(EVID.read_text(encoding="utf-8"))
 img=json.loads(IMAGE.read_text(encoding="utf-8"))
 if m5.get("image_platform")!="linux/arm64" or img.get("image_platform")!="linux/arm64":
  raise ValueError("PRODUCTION_ARCHITECTURE_MISMATCH")
 if m5.get("image_id")!=img.get("image_id"):
  raise ValueError("IMAGE_EVIDENCE_DIGEST_MISMATCH")
 for f in PRODUCTION_RUNTIME:
  if manifest["included_files"].get(f)!=img["file_sha256"].get(f):
   raise ValueError("RUNTIME_IMAGE_SOURCE_BUNDLE_DRIFT:"+f)
 if run_docker:
  inspected=subprocess.run(
   ["docker","image","inspect",m5["docker_tag"],
    "--format","{{.Os}}/{{.Architecture}} {{.Id}}"],
   check=True,capture_output=True,text=True,timeout=35,
  ).stdout.strip()
  if inspected!="linux/arm64 "+m5["image_id"]:
   raise ValueError("LOCAL_DOCKER_IMAGE_CHANGED")
 cached_origin_sha=git("rev-parse","refs/remotes/origin/master")
 merge_base=git("merge-base","HEAD","refs/remotes/origin/master")
 if cached_origin_sha!=merge_base:
  raise ValueError("CACHED_MASTER_NOT_ANCESTOR")
 ahead=git("rev-list","--left-right","--count","origin/master...HEAD")
 dirty=git("status","--porcelain=v1")
 if not dirty:
  raise ValueError("SOURCE_MUST_STILL_BE_UNADOPTED_PENDING_OWNER")
 control=(ROOT/"scripts/release/build-release-image.ps1").read_text(
  encoding="utf-8")
 if "EXTERNAL_GOVERNANCE_ATTESTATION_REQUIRED" not in control:
  raise ValueError("FORMAL_GATE_PREMATURELY_WIRED")
 return {
  "candidate_baseline":BASE_SHA,
  "cached_origin_master":cached_origin_sha,
  "cached_master_freshness":"NOT_VERIFIED_NETWORK",
  "git_ahead_of_cached_master":ahead,
  "working_tree_has_uncommitted_candidate":True,
  "review_bundle_sha256":digest(raw),
  "review_source_files":details["members"],
  "tracked_patch_sha256":details["patch_digest"],
  "release_image_id":m5["image_id"],
  "release_image_platform":"linux/arm64",
  "runtime_files_in_bundle_equal_to_arm64_image_sha256":len(PRODUCTION_RUNTIME),
  "formal_external_owner_reviewer_gate":"NOT_WIRED",
  "independent_reviewer":"NOT_OBTAINED",
  "actual_ipad_owner_uat":"NOT_PERFORMED",
  "formal_signed_source_admission":"NO_GO",
  "github_master_merged":False,
  "oracle_production_modified":False,
 }

def main():
 result=evaluate_custody()
 result["status"]="RC3_LOCAL_SOURCE_CUSTODY_INPUTS_PASS"
 OUTPUT.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
 print("RC3_LOCAL_SOURCE_CUSTODY_INPUTS=PASS")
 print("REVIEW_SOURCE_FILES="+str(result["review_source_files"]))
 print("ARM64_IMAGE_RUNTIME_HASH_BINDING=7/7")
 print("FORMAL_SOURCE_ADMISSION=NO_GO")
 print("EVIDENCE="+str(OUTPUT))
if __name__=="__main__":main()
