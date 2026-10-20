"""RC2 read-only, fail-closed candidate readiness and adversarial checks.

This is local diagnostics, NOT the independent Owner/Reviewer signature
verifier and NOT authorization for Build/Merge/Deploy. No write to Product,
Docker engine or Oracle. Output only a JSON report in handoffs.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
M5=ROOT/"docs/handoffs/G010_M5_LOCAL_CANDIDATE_BUILD_EVIDENCE_20261020.json"
ARM=ROOT/"docs/handoffs/G010_RC2_ARM64_LOCAL_BUILD_EVIDENCE_20261020.json"
OUTPUT=ROOT/"docs/handoffs/GO_ODYSSEY_G010_RC2_RELEASE_ADMISSION_NO_GO_MATRIX_20261020.json"
PRODUCTION_PLATFORM="linux/arm64"
EXPECTED_HEAD="efd4524c3a3b5669b693ee0be50acf586c73ad90"
RUNTIME=[
 "app.py","community.html","index.html","map_battle_runtime.py",
 "shop.html","g010_m4_quest_leaderboard.js","g010_m4_quest_leaderboard.css",
]
def _run(*args):
 p=subprocess.run(list(args),cwd=ROOT,capture_output=True,
                  text=True,encoding="utf-8",errors="replace",timeout=30)
 return p.returncode,p.stdout.strip()

def _hash(p:Path):
 return hashlib.sha256(p.read_bytes()).hexdigest()

def local_source_check(record:dict,root:Path=ROOT):
 hashes=record.get("working_tree_overlay_hashes")
 if not isinstance(hashes,dict) or not hashes:return False
 return all((root/name).is_file() and _hash(root/name)==digest
            for name,digest in hashes.items())

def local_platform_check(observed:str):
 return observed==PRODUCTION_PLATFORM

def admission_decision(source_ok:bool, platform_ok:bool,
                       clean_commit:bool, reviewer_signature:bool=False,
                       owner_grant:bool=False, ipad_owner_uat:bool=False,
                       outside_verified:bool=False):
 """Diagnostics-only and incapable of granting official authority.

 Any flags resembling authority MUST be external-verified by a separately
 installed independently trusted checker. This local function never treats
 caller flags/self-issued JSON as proof, even if all flags say 'true'.
 """
 flags={
   "local_source_hashes":bool(source_ok),
   "local_target_platform":bool(platform_ok),
   "clean_exact_committed_source":bool(clean_commit),
   "external_reviewer_signature_supplied":bool(reviewer_signature),
   "owner_release_grant_claimed":bool(owner_grant),
   "physical_ipad_uat_claimed":bool(ipad_owner_uat),
   "external_verifier_claimed":bool(outside_verified),
 }
 reasons=[]
 for name in ("local_source_hashes","local_target_platform",
              "clean_exact_committed_source"):
  if not flags[name]:reasons.append(name.upper()+"_NOT_SATISFIED")
 reasons.extend([
   "INDEPENDENT_TRUST_ROOT_SIGNATURE_NOT_VERIFIED",
   "EXTERNAL_OWNER_SINGLE_USE_GRANT_NOT_VERIFIED",
   "PHYSICAL_IPAD_OWNER_UAT_NOT_VERIFIED",
   "SEPARATE_SIGNED_RELEASE_ADMISSION_REQUIRED",
 ])
 return {"formal_release_admission":"NO_GO",
         "local_diagnostics":flags,"blocking_reasons":reasons}

def adversarial_matrix():
 checks={}
 base=dict(source_ok=True,platform_ok=True,clean_commit=True)
 samples=[
  ("wrong_architecture",{**base,"platform_ok":False},"NO_GO"),
  ("tampered_source",{**base,"source_ok":False},"NO_GO"),
  ("dirty_uncommitted_tree",{**base,"clean_commit":False},"NO_GO"),
  ("missing_independent_signer",base,"NO_GO"),
  ("fake_all_authority_flags",{**base,"reviewer_signature":True,
   "owner_grant":True,"ipad_owner_uat":True,
   "outside_verified":True},"NO_GO"),
  ("all_missing",dict(source_ok=False,platform_ok=False,
                      clean_commit=False),"NO_GO"),
 ]
 for name,arg,expected in samples:
  decision=admission_decision(**arg)
  assert decision["formal_release_admission"]==expected,name
  checks[name]="DENIED_AS_REQUIRED"
 return checks

def main():
 assert os.environ.get("PRODUCTION","").lower()!="true"
 baseline=json.loads(M5.read_text(encoding="utf-8"))
 assert baseline["docker_build_returncode"]==0
 head_rc,head=_run("git","rev-parse","HEAD")
 assert head_rc==0 and head==EXPECTED_HEAD
 dirty_rc,dirty=_run("git","status","--porcelain=v1")
 assert dirty_rc==0
 source_ok=local_source_check(baseline)
 assert source_ok,"M5 source digest changed; stop. Rebuild is required."
 existing_rc,existing_platform=_run("docker","image","inspect",
   baseline["docker_tag"],"--format","{{.Os}}/{{.Architecture}}")
 assert existing_rc==0 and existing_platform=="linux/amd64"
 arm_record=None
 arm_platform="NOT_BUILT"
 arm_image=None
 if ARM.is_file():
  arm_record=json.loads(ARM.read_text(encoding="utf-8"))
  if arm_record.get("docker_build_returncode")==0:
   image_rc,actual=_run("docker","image","inspect",
      arm_record["docker_tag"],"--format","{{.Os}}/{{.Architecture}}")
   id_rc,actual_id=_run("docker","image","inspect",
      arm_record["docker_tag"],"--format","{{.Id}}")
   if image_rc==0 and id_rc==0 and actual_id==arm_record.get("image_id"):
    arm_platform=actual
    arm_image=actual_id
 checks=adversarial_matrix()
 result={
   "schema":"G010_RC2_LOCAL_GOVERNANCE_V1",
   "baseline_head":head,"candidate_branch":"candidate/go-product-integrated-20261019",
   "working_tree_clean":not bool(dirty),
   "original_local_build_platform":existing_platform,
   "formal_platform_required":PRODUCTION_PLATFORM,
   "arm_local_image_platform":arm_platform,
   "arm_local_image_id":arm_image,
   "source_overlay_hashes_match":source_ok,
   "tamper_and_authentication_negative_controls":checks,
   "formal_governance":admission_decision(
      source_ok,local_platform_check(arm_platform),not bool(dirty)),
   "signed_independent_review":"NOT_OBTAINED",
   "owner_physical_ipad_uat":"NOT_PERFORMED",
   "independent_build_provenance":"NOT_OBTAINED",
   "master_merge_push":"NOT_AUTHORIZED",
   "oracle_production_deploy":"NOT_AUTHORIZED",
   "stage_rc2_local_safety_checks":"PASS",
 }
 OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
 print("G010_RC2_ADVERSARIAL_DENIAL_TESTS="+str(len(checks))+"/6 PASS")
 print("G010_RC2_SOURCE_DIGEST=PASS")
 print("G010_RC2_ARM64_LOCAL_IMAGE="+arm_platform)
 print("G010_RC2_FORMAL_RELEASE_ADMISSION=NO_GO")
 print("EVIDENCE="+str(OUTPUT))
if __name__=="__main__":main()
