"""Verify local G010 RC2 ARM64 image byte-for-byte against tested Product source.

Safe read-only offline image inspect. Independent-of-build verification tool,
but NOT an independent *trusted signature* verifier or Owner release grant.
"""
from pathlib import Path
import json
import subprocess
import _verify_g010_rc_image_source_integrity as base

ROOT=Path(__file__).resolve().parents[1]
base.EVIDENCE=ROOT/"docs/handoffs/G010_RC2_ARM64_LOCAL_BUILD_EVIDENCE_20261020.json"
base.RC=ROOT/"docs/handoffs/GO_ODYSSEY_G010_RC2_ARM64_IMAGE_SOURCE_INTEGRITY_20261020.json"

def main():
 record=json.loads(base.EVIDENCE.read_text(encoding="utf-8"))
 assert record.get("image_platform")=="linux/arm64"
 assert record.get("required_image_platform")=="linux/arm64"
 identity=subprocess.run(
  ["docker","image","inspect",record["docker_tag"],
   "--format","{{.Os}}/{{.Architecture}} {{.Id}}"],
  capture_output=True,text=True,encoding="utf-8",check=True,timeout=40,
 ).stdout.strip().split()
 assert identity==["linux/arm64",record["image_id"]]
 base.main()
 result=json.loads(base.RC.read_text(encoding="utf-8"))
 assert len(result["file_sha256"])==7
 assert result["sensitive_app_files"]=="ABSENT"
 assert result["shipped_shop_backpack_default"]=="OFF"
 result.update({
  "verdict":"RC2_LOCAL_ARM64_IMAGE_BINARY_SOURCE_INTEGRITY_PASS",
  "image_platform":"linux/arm64",
  "official_release_owner_grant":"NOT_VERIFIED",
  "independent_attestation":"NOT_VERIFIED",
  "release_admission":"NO_GO",
 })
 base.RC.write_text(
  json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
 print("G010_RC2_ARM64_IMAGE_SOURCE_MATCH=PASS")
 print("ARM64_IMAGE_ID="+record["image_id"])
 print("SOURCE_FILE_SHA256_MATCHED=7/7")
 print("RELEASE_ADMISSION=NO_GO")
if __name__=="__main__":main()
