"""G010 M5 isolated, CLEAN Docker image build of the exact working candidate.

No trusted Build attestation is claimed. This script does NOT use the dirty
checkout as Docker context; it archives immutable Git HEAD and overlays only
an allowlisted set of already reviewed changed Product files. Explicitly
refuses secret files and verifies new web assets exist inside the image.
No master mutation, deploy, push or Oracle access.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/"docs"/"handoffs"/"G010_RC2_ARM64_LOCAL_BUILD_EVIDENCE_20261020.json"
OVERLAY=[
  "app.py","community.html","index.html","map_battle_runtime.py",
  "shop.html","Dockerfile","deploy/build-manifest.json",
  "g010_m4_quest_leaderboard.js","g010_m4_quest_leaderboard.css",
]
WEB_ASSETS=[
 "community.html","g010_m4_quest_leaderboard.js",
 "g010_m4_quest_leaderboard.css",
]
FORBIDDEN=["secret_key.txt",".env",".env.production","id_rsa",
           ".git/config","credentials.json"]
TAG="go-odyssey:g010-rc2-arm64-local-candidate-20261020"
def sha256(path):
 h=hashlib.sha256()
 with open(path,"rb") as file:
  for b in iter(lambda:file.read(2**20),b""):
   h.update(b)
 return h.hexdigest()
def main():
 assert os.environ.get("PRODUCTION","").lower() != "true"
 assert subprocess.check_output(
  ["git","rev-parse","--abbrev-ref","HEAD"],cwd=ROOT,text=True).strip() == (
   "candidate/go-product-integrated-20261019"
  ),"Unexpected candidate branch, refusing to build"
 head=subprocess.check_output(
  ["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
 assert head == "efd4524c3a3b5669b693ee0be50acf586c73ad90"
 for path in OVERLAY:
  assert (ROOT/path).is_file(),f"Missing reviewed file {path}"
 assert "g010_m4_quest_leaderboard.js" in (ROOT/"Dockerfile").read_text(
  encoding="utf-8")
 assert "g010_m4_quest_leaderboard.css" in (ROOT/"Dockerfile").read_text(
  encoding="utf-8")
 with tempfile.TemporaryDirectory(prefix="g010-m5-clean-build-") as temporary:
  temp=Path(temporary)
  context=temp/"context"
  context.mkdir()
  archive=temp/"source.tar"
  subprocess.run(["git","archive","--format=tar","-o",str(archive),"HEAD"],
                 cwd=ROOT,check=True,timeout=90)
  with tarfile.open(archive,"r") as tar:
   # No checkout-controlled tar symlinks or traversal into build context.
   for member in tar.getmembers():
    name=member.name.replace("\\","/")
    assert not name.startswith("/") and ".." not in Path(name).parts
   tar.extractall(context,filter="data")
  checksums={}
  for name in OVERLAY:
   target=context/name
   target.parent.mkdir(parents=True,exist_ok=True)
   shutil.copy2(ROOT/name,target)
   assert sha256(ROOT/name)==sha256(target)
   checksums[name]=sha256(target)
  for forbidden in FORBIDDEN:
   assert not (context/forbidden).exists(),f"unsafe build: {forbidden} present"
  for name in WEB_ASSETS:
   assert (context/name).is_file() and (context/name).stat().st_size>0
  print("M5_CLEAN_ARCHIVE_PLUS_EXPLICIT_OVERLAY=PASS",flush=True)
  evidence={
   "schema":"G010_M5_LOCAL_BUILD_EVIDENCE_V1",
   "source_branch":"candidate/go-product-integrated-20261019",
   "immutable_baseline_head":head,
   "working_tree_overlay_hashes":checksums,
   "secret_files_excluded":FORBIDDEN,
   "docker_tag":TAG,
   "trusted_source_admission":"NOT_VERIFIED",
   "independent_release_attestation":"NOT_VERIFIED",
   "formal_deployment":"NOT_AUTHORIZED",
   "actual_ipad_owner_uat":"NOT_VERIFIED",
  }
  # docker build can inspect local-only image but cannot publish it.
  command=[
   "docker","buildx","build","--platform","linux/arm64","--load","--pull=false","--progress=plain",
   "-t",TAG,
   "--build-arg","APP_GIT_SHA=G010-M5-UNCOMMITTED-LOCAL-CANDIDATE",
   "--build-arg","APP_BUILD_DATE=2026-10-20-local-candidate",
   "--build-arg","SGF_ENGINE_SOURCE_COMMIT=unverified-local",
   str(context),
  ]
  proc=subprocess.run(command,capture_output=True,text=True,
                      encoding="utf-8",errors="replace",timeout=900)
  evidence["docker_build_returncode"]=proc.returncode
  evidence["docker_build_log_tail"]=(proc.stdout+"\n"+proc.stderr)[-9000:]
  print("M5_BUILD_EXIT="+str(proc.returncode),flush=True)
  print(evidence["docker_build_log_tail"][-4900:],flush=True)
  if proc.returncode:
   evidence["verdict"]="BUILD_FAILED"
   MANIFEST.write_text(json.dumps(evidence,indent=2,ensure_ascii=False),encoding="utf-8")
   return proc.returncode
  inspect=subprocess.run(["docker","image","inspect",TAG,
   "--format","{{.Id}}"],capture_output=True,text=True,
   encoding="utf-8",timeout=30,check=True)
  evidence["image_id"]=inspect.stdout.strip()
  observed_platform=subprocess.run(
   ["docker","image","inspect",TAG,"--format","{{.Os}}/{{.Architecture}}"],
   capture_output=True,text=True,check=True,timeout=30).stdout.strip()
  evidence["image_platform"]=observed_platform
  evidence["required_image_platform"]="linux/arm64"
  if observed_platform!="linux/arm64":
   evidence["verdict"]="RC2_WRONG_IMAGE_ARCHITECTURE"
   MANIFEST.write_text(json.dumps(evidence,indent=2,ensure_ascii=False),
                       encoding="utf-8")
   print("RC2_BUILD_ARCHITECTURE_REJECT="+observed_platform,flush=True)
   return 81

  verify=subprocess.run(["docker","run","--platform","linux/arm64","--rm","--network","none",
   "--read-only","--entrypoint","/bin/sh",TAG,
   "-c"," && ".join("test -s /app/"+name for name in WEB_ASSETS)],
   capture_output=True,text=True,timeout=70)
  evidence["assets_present_inside_image"]=verify.returncode==0
  print("M5_IMAGE_ASSETS_PRESENT="+str(verify.returncode==0),flush=True)
  if verify.returncode:
   evidence["verdict"]="IMAGE_ASSETS_MISSING"
  else:
   evidence["verdict"]="LOCAL_CANDIDATE_DOCKER_BUILD_PASS_RELEASE_UNATTESTED"
  MANIFEST.write_text(json.dumps(evidence,indent=2,ensure_ascii=False),encoding="utf-8")
  print("M5_BUILD_EVIDENCE="+str(MANIFEST),flush=True)
  return verify.returncode

if __name__=="__main__":
 raise SystemExit(main())
