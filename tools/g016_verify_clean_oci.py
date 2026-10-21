"""G016 immutable OCI verification: every tar/blob digest, index -> manifest
-> config/layers, image commit, exact source files, release exclusions.
Never accept an export without clean exit status and complete OCI graph.
"""
from pathlib import Path
import hashlib,json,tarfile,sys,datetime
e=Path(r"D:\go-odyssey-g010-3d-activation-evidence-20261021")
root=Path(r"D:\go-odyssey-g010-3d-activation-20261021")
tarpath=e/"G016_CLEAN_BUILDKIT_G015_4DB8BFA_20261021.tar"
sha="4db8bfac69cb29aca58e97ed00e3deac1c345dc9"
proof={"schema":"G016_CLEAN_INDEPENDENT_OCI_CONTENT_V1",
  "archive_path":str(tarpath),"source_commit":sha,"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "phase":"VERIFYING","full_production_admission":False,"no_master_merge_or_deploy":True,
  "asset_qa_content_is_not_licensed_for_release":True}
wanted={
 "app/js/g009_d_r2_shared_host_bootstrap.js":root/"js/g009_d_r2_shared_host_bootstrap.js",
 "app/js/g009_shared_hero_attachment_host.js":root/"js/g009_shared_hero_attachment_host.js",
 "app/migrations/equipment_canonical_slot_v1.py":root/"migrations/equipment_canonical_slot_v1.py",
 "app/hero.html":root/"hero.html"
}
got={}
fail=[]
try:
 with tarfile.open(tarpath,"r:") as tar:
  entries={m.name.lstrip("./"):m for m in tar.getmembers() if m.isfile()}
  assert "oci-layout" in entries and "index.json" in entries, "oci_index_or_layout_missing"
  layout=json.load(tar.extractfile(entries["oci-layout"]))
  assert layout["imageLayoutVersion"]=="1.0.0"
  index=json.load(tar.extractfile(entries["index.json"]))
  assert index["schemaVersion"]==2
  manifests=index["manifests"]
  assert len(manifests)==1
  def inspect_blob(digest):
   assert digest.startswith("sha256:")
   sub=digest.split(":")[1]
   name="blobs/sha256/"+sub
   assert name in entries, "MISSING_BLOB:"+name
   return tar.extractfile(entries[name])
  blobs=[name for name in entries if name.startswith("blobs/sha256/")]
  for i,name in enumerate(blobs):
   with tar.extractfile(entries[name]) as f:
    h=hashlib.sha256()
    while True:
     chunk=f.read(1024*1024)
     if not chunk:break
     h.update(chunk)
    assert h.hexdigest()==name.split("/")[-1], "BLOB_DIGEST_MISMATCH:"+name
  manifest=json.load(inspect_blob(manifests[0]["digest"]))
  assert manifest["schemaVersion"]==2
  config=json.load(inspect_blob(manifest["config"]["digest"]))
  assert config["config"]["Env"] and "APP_GIT_SHA="+sha in config["config"]["Env"]
  assert config["config"].get("Labels",{}).get("org.opencontainers.image.revision")==sha
  layers=manifest["layers"]
  assert len(layers)>=20
  proof["manifest_digest"]=manifests[0]["digest"]
  proof["config_digest"]=manifest["config"]["digest"]
  proof["layer_count"]=len(layers)
  proof["blob_count"]=len(blobs)
  proof["layer_media_types"]=sorted(set(x["mediaType"] for x in layers))
  proof["archive_sha256"]=hashlib.sha256(tarpath.read_bytes()).hexdigest()
  proof["archive_bytes"]=tarpath.stat().st_size
  # Walk every OCI layer payload and verify exact runtime source state.
  seenPaths=set()
  for i,layer in enumerate(layers):
   media=layer["mediaType"]
   mode="r|gz" if ("gzip" in media or "+gzip" in media) else "r|"
   handle=inspect_blob(layer["digest"])
   with tarfile.open(fileobj=handle,mode=mode) as contents:
    for f in contents:
     path=f.name.lstrip("./")
     if path:
      seenPaths.add(path)
     if path in wanted:
      stream=contents.extractfile(f) if f.isfile() else None
      if stream is None:fail.append("runtime_source_not_regular:"+path);continue
      got[path]=hashlib.sha256(stream.read()).hexdigest()
     if path.startswith("app/tests/e2e") or "g015_p038_original_hero_qa.mjs" in path or "g011_private_qa_assets" in path:
      fail.append("forbidden_test_or_private_asset_in_image:"+path)
  for path,source in wanted.items():
   if path not in got:fail.append("missing_runtime_source:"+path)
   else:
    h=hashlib.sha256(source.read_bytes()).hexdigest()
    if got[path]!=h:fail.append("runtime_source_sha_mismatch:"+path)
  proof["verified_runtime_sources"]=got
  proof["wanted_runtime_source_count"]=len(wanted)
  proof["no_secret_exposure"]=not any("secret_key.txt" in p or "stage.env" in p for p in seenPaths)
  assert proof["no_secret_exposure"],"SECRET_INCLUDED"
  proof["index_digest_verified"]=True
  proof["all_blob_digests_verified"]=True
  proof["forbidden_paths_found"]=[s for s in fail if s.startswith("forbidden")]
  if fail:raise AssertionError(";".join(fail))
  proof["phase"]="OCI_CONTENT_FULL_SHA256_AND_SOURCE_PASS"
except Exception as ex:
 proof["phase"]="OCI_INTEGRITY_HOLD"
 proof["reason"]=str(ex)[:2500]
proof["errors"]=fail[:35]
out=e/"G016_CLEAN_BUILDKIT_FULL_OCI_VERIFICATION_20261021.json"
out.write_text(json.dumps(proof,indent=2,ensure_ascii=False),encoding="utf8")
print(json.dumps({k:proof.get(k) for k in ("phase","reason","archive_bytes","layer_count","blob_count","wanted_runtime_source_count","forbidden_paths_found","errors")},ensure_ascii=False))
if proof["phase"]!="OCI_CONTENT_FULL_SHA256_AND_SOURCE_PASS":sys.exit(1)
