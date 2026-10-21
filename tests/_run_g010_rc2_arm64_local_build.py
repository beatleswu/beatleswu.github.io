"""RC2 local arm64 candidate build, derived from the accepted clean context builder.

Copies M5's uncommitted candidate only from frozen git archive + 9 hash-checked
allowlisted files; builds a NEW platform-correct ARM64 image locally. Does NOT
sign, push, merge, deploy, provide release approval or read secrets.
"""
from __future__ import annotations
import ast
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"tests"/"_run_g010_m5_sanitized_docker_candidate.py"
TARGET=ROOT/"tests"/"_g010_rc2_arm64_builder_generated.py"
raw=SOURCE.read_text(encoding="utf-8")
replacements=[
 ('G010_M5_LOCAL_CANDIDATE_BUILD_EVIDENCE_20261020.json',
  'G010_RC2_ARM64_LOCAL_BUILD_EVIDENCE_20261020.json'),
 ('go-odyssey:g010-m5-local-candidate-20261020',
  'go-odyssey:g010-rc2-arm64-local-candidate-20261020'),
 ('"docker","build","--pull=false","--progress=plain",',
  '"docker","buildx","build","--platform","linux/arm64",'
  '"--load","--pull=false","--progress=plain",'),
 ('"docker","run","--rm","--network","none",',
  '"docker","run","--platform","linux/arm64","--rm","--network","none",'),
]
for old,new in replacements:
 assert raw.count(old)==1,(old,raw.count(old))
 raw=raw.replace(old,new)
marker='  evidence["image_id"]=inspect.stdout.strip()'
assert raw.count(marker)==1
raw=raw.replace(marker,marker+'''
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
''')
ast.parse(raw)
TARGET.write_text(raw,encoding="utf-8")
print("G010_RC2_ARM64_BUILD_FROM_CLEAN_SOURCE=START",flush=True)
proc=subprocess.run([sys.executable,"-B",str(TARGET)],cwd=ROOT)
raise SystemExit(proc.returncode)
