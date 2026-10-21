"""Independent LOCAL RC proof: immutable overlay -> exact image bytes.

Read-only Docker, no network, no app startup, no Production DB, no push.
Verifies all seven runtime candidate files inside the built image against
each workstation byte and against M5's recorded digest; verifies G009
release locks are preserved, and mandatory post-Build list is accurate.
Not a trusted external signed admission or formal deployment permission.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/"docs/handoffs/G010_M5_LOCAL_CANDIDATE_BUILD_EVIDENCE_20261020.json"
RC=ROOT/"docs/handoffs/GO_ODYSSEY_G010_RC_IMAGE_SOURCE_INTEGRITY_20261020.json"
RUNTIME=[
 "app.py","community.html","index.html","map_battle_runtime.py",
 "shop.html","g010_m4_quest_leaderboard.js","g010_m4_quest_leaderboard.css",
]
SOURCE=[
 *RUNTIME,"Dockerfile","deploy/build-manifest.json",
]
ASSETS={
 "/app/community.html", "/app/g010_m4_quest_leaderboard.js",
 "/app/g010_m4_quest_leaderboard.css",
}
def sha(blob: bytes)->str:
 return hashlib.sha256(blob).hexdigest()
def run(args:list[str], timeout:int=90):
 return subprocess.run(args,check=True,capture_output=True,text=True,
                       encoding="utf-8",errors="replace",timeout=timeout).stdout.strip()
def main():
 recorded=json.loads(EVIDENCE.read_text(encoding="utf-8"))
 assert recorded["docker_build_returncode"]==0
 assert recorded["assets_present_inside_image"] is True
 assert recorded["trusted_source_admission"]=="NOT_VERIFIED"
 assert recorded["formal_deployment"]=="NOT_AUTHORIZED"
 tag=recorded["docker_tag"]
 image_id=run(["docker","image","inspect",tag,"--format","{{.Id}}"])
 assert image_id==recorded["image_id"],"Docker tag has since drifted!"
 overlay=recorded["working_tree_overlay_hashes"]
 assert set(overlay)==set(SOURCE),(sorted(overlay),sorted(SOURCE))
 for relative in SOURCE:
  assert sha((ROOT/relative).read_bytes())==overlay[relative],(
   "Workspace has changed since M5 Build: "+relative)
 manifest=json.loads((ROOT/"deploy/build-manifest.json").read_text(encoding="utf-8"))
 required=set(manifest["post_build_verification_files"])
 assert ASSETS <= required,"M4 UI assets omitted from official verify list"
 input_list=set(manifest["build_inputs"]["tracked_in_canonical_branch_this_sprint"])
 assert {"g010_m4_quest_leaderboard.js",
         "g010_m4_quest_leaderboard.css"} <= input_list,(
   "M4 UI omitted from manifest source inputs")
 dockerfile=(ROOT/"Dockerfile").read_text(encoding="utf-8")
 assert all(n in dockerfile for n in
            ["g010_m4_quest_leaderboard.js","g010_m4_quest_leaderboard.css"])
 assert "const G009_SHOP_BROWSE_PREVIEW_ONLY = true;" in (
  ROOT/"shop.html").read_text(encoding="utf-8")
 assert "const G009_BACKPACK_READ_ONLY = true;" in (
  ROOT/"inventory.html").read_text(encoding="utf-8")
 image_script=r"""
import hashlib,json,os,sys
expected=json.loads(sys.argv[1])
result={}
for filename,digest in expected.items():
 path='/app/'+filename
 assert os.path.isfile(path),(filename,'MISSING')
 with open(path,'rb') as fp:
  computed=hashlib.sha256(fp.read()).hexdigest()
 assert computed==digest,(filename,digest,computed)
 result[filename]=computed
with open('/app/shop.html','r',encoding='utf-8') as f:
 assert 'const G009_SHOP_BROWSE_PREVIEW_ONLY = true;' in f.read()
with open('/app/inventory.html','r',encoding='utf-8') as f:
 assert 'const G009_BACKPACK_READ_ONLY = true;' in f.read()
for forbidden in ('/app/.env','/app/.env.production','/app/secret_key.txt'):
 assert not os.path.exists(forbidden),('forbidden secret inside image',forbidden)
print(json.dumps({'verdict':'IMAGE_RUNTIME_SHA256_EQUALS_SOURCE',
 'files':result,'release_gates':'OFF','secrets_in_app':'ABSENT'}))
"""
 actual=run([
  "docker","run","--rm","--network","none","--read-only",
  "--tmpfs","/tmp","--entrypoint","python",tag,"-c",image_script,
  json.dumps({n:overlay[n] for n in RUNTIME},separators=(',',':')),
 ],timeout=130)
 parsed=json.loads(actual)
 assert parsed["verdict"]=="IMAGE_RUNTIME_SHA256_EQUALS_SOURCE"
 assert parsed["release_gates"]=="OFF"
 assert len(parsed["files"])==7
 result={
  "verdict":"RC_LOCAL_IMAGE_BINARY_SOURCE_INTEGRITY_PASS",
  "image_id":image_id,"source_baseline":recorded["immutable_baseline_head"],
  "file_sha256":parsed["files"],
  "manifest_required_assets_verified":sorted(ASSETS),
  "shipped_shop_backpack_default":"OFF",
  "sensitive_app_files":"ABSENT",
  "network_used":False,
  "external_trusted_attestation":"NOT_VERIFIED",
  "physical_ipad_uat":"NOT_VERIFIED",
  "formal_deployment":"NOT_AUTHORIZED",
 }
 RC.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
 print("G010_RC_LOCAL_IMAGE_BINARY_SOURCE_INTEGRITY=PASS")
 print("IMAGE_ID="+image_id)
 print("FILES_MATCHED="+str(len(parsed["files"])))
 print("RELEASE_FEATURE_GATES=OFF")
 print("SOURCE_ADMISSION=NOT_VERIFIED")
 print("EVIDENCE="+str(RC))
if __name__=="__main__":
 main()
