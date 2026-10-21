from pathlib import Path
import subprocess,json,datetime,sys
base=Path(r"D:\go-odyssey-g010-3d-activation-evidence-20261021")
tag="go-odyssey:g016-4db8bfa-verified-local"
sha="4db8bfac69cb29aca58e97ed00e3deac1c345dc9"
inspect=subprocess.run(["docker","image","inspect",tag],capture_output=True,text=True,timeout=30)
assert inspect.returncode==0,inspect.stderr
info=json.loads(inspect.stdout)[0]
assert info["Config"]["Labels"]["org.opencontainers.image.revision"]==sha
assert ("APP_GIT_SHA="+sha) in info["Config"]["Env"]
test=("import os;from pathlib import Path;"
 "from migrations.equipment_canonical_slot_v1 import CANONICAL_SLOTS;"
 "assert CANONICAL_SLOTS==('weapon','armor','accessory','offhand');"
 "root=Path('/app');"
 "assert 'g015_qa' in (root/'js/g009_d_r2_shared_host_bootstrap.js').read_text();"
 "assert 'hand_world_scale' in (root/'js/g009_shared_hero_attachment_host.js').read_text();"
 "assert '/js/g009_d_r2_shared_host_bootstrap.js' in (root/'hero.html').read_text();"
 "assert not (root/'tests/e2e/g015_p038_original_hero_qa.mjs').exists();"
 "assert not (root/'tests/e2e/g011_private_qa_assets').exists();"
 "assert not (root/'secret_key.txt').exists();"
 "assert os.getenv('APP_GIT_SHA')=='"+sha+"';"
 "print('G016_RUNTIME_SOURCE_SMOKE_PASS')")
cmd=["docker","run","--rm","--network","none","--read-only",
 "--tmpfs","/tmp:rw,size=64m","--entrypoint","python",tag,"-c",test]
p=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
report={"schema":"G016_REAL_DOCKER_OFFLINE_SMOKE_V1","utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "source_sha":sha,"local_tag":tag,"image_id":info["Id"],
 "image_revision_label":info["Config"]["Labels"]["org.opencontainers.image.revision"],
 "network_mode":"none","rootfs":"read-only","container_removed":True,
 "no_external_accounts_or_production_db":True,"exit_code":p.returncode,
 "stdout":p.stdout.strip()[-700:],"stderr":p.stderr.strip()[-1000:],
 "verdict":"G016_OFFLINE_IMPORTED_IMAGE_SMOKE_PASS" if p.returncode==0 and "G016_RUNTIME_SOURCE_SMOKE_PASS" in p.stdout else "HOLD"}
out=base/"G016_IMPORTED_IMAGE_NETWORKLESS_RUNTIME_SMOKE_20261021.json"
out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
print(json.dumps({k:report[k] for k in ("verdict","image_id","source_sha","exit_code")}))
if report["verdict"]!="G016_OFFLINE_IMPORTED_IMAGE_SMOKE_PASS":sys.exit(1)
