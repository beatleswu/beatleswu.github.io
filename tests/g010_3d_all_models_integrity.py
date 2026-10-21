"""Audit every GLB that the Hero 3D gallery can display; no source/model modifications."""
from pathlib import Path
import json,hashlib,collections,datetime
root=Path(__file__).resolve().parents[1]
def load(s):return json.loads((root/s).read_text(encoding="utf-8"))
future=load("schemas/future30_c005_real_asset_runtime_mapping_manifest.json")
companions=load("assets/3d_shop/p048/companion/formal_18/mapping_manifest.json")
p048=load("assets/3d_shop/p048/runtime_manifest.json")
weapons=load("schemas/g009_formal9_rights_cleared_replacement_v1.json")
records=[]
def add(category,name,path,sha,bytes_expected=None,rights=""):
 path=str(path).lstrip("/")
 assert path.startswith("assets/3d_shop/") and ".." not in path and "\\" not in path,path
 assert len(sha)==64 and all(c in "0123456789abcdefABCDEF" for c in sha)
 f=root/path
 assert f.is_file(),path
 h=hashlib.sha256()
 with f.open("rb") as reader:
  while chunk:=reader.read(2*1024*1024):h.update(chunk)
 actual=h.hexdigest()
 assert actual==sha.lower(),(category,name,path,actual,sha)
 size=f.stat().st_size
 if bytes_expected is not None:assert size==bytes_expected,(name,size,bytes_expected)
 records.append({"category":category,"id":name,"path":path,"sha256":actual,"bytes":size,"rights":rights})
assert future["authority"]["authority_status"]=="FINAL_V1_PRODUCT"
for x in future["visual_models"]:
 assert x["admission_state"]=="ENABLED" and x["legal_provenance"]["license_status"]=="ADMITTED"
 assert x["legal_provenance"]["provenance_status"]=="VERIFIED" and x["asset_status"]=="PRESENT"
 add("character",x["visual_model_id"],x["runtime_glb"],x["runtime_sha256"],rights="Owner admitted")
assert companions["owner_approved_18_18"] and companions["mapping_count"]==18
for x in companions["mappings"]:
 add("spirit",x["pet_key"]+"."+x["stage"],x["runtime_glb"],x["asset_sha256"],x["asset_bytes"],"Owner approved")
for x in p048["entries"]:
 if x["authority_domain"] not in ("HEAD_PRESENTATION","BACK_PRESENTATION","COMPANION_PRESENTATION"):continue
 assert x["source_provenance"]["commercial_use_allowed"] is True
 c="bonus" if x["authority_domain"]=="COMPANION_PRESENTATION" else "accessory"
 add(c,x["presentation_id"],x["runtime_asset"],x["runtime_sha256"],rights="commercial use approved, preview only")
assert weapons["rights"]["RIGHTS_STATUS"]=="RIGHTS_CLEARED"
assert weapons["release_eligibility_value"]=="RIGHTS_CLEARED_RELEASE_NOT_ADMITTED"
for x in weapons["items"]:
 assert x["server_item_id"] in {s["server_item_id"] for s in weapons["mapping"]}
 add("weapon",x["server_item_id"],x["runtime_asset"],x["runtime_sha256"],
    rights="rights-cleared; not production release admitted")
count=dict(collections.Counter(x["category"] for x in records))
assert count=={"character":33,"spirit":18,"accessory":6,"bonus":2,"weapon":4},count
assert len(records)==63
assert len({x["path"] for x in records})==63
assert len({x["sha256"] for x in records})==63
output={"schema":"G010_3D_ALL_63_ASSETS_SHA_AUDIT_V1","timestamp_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "verdict":"63_OF_63_SHA256_BYTES_VERIFIED","count_by_category":count,"total_assets":63,
 "total_bytes":sum(x["bytes"] for x in records),"no_ownership_change":True,"production_admission":False,
 "weapons_not_admitted_for_production":4,"models":records}
dest=root/"G010_3D_ALL_63_SHA256_AUDIT_20261021.json"
dest.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf8")
print(json.dumps({"verdict":output["verdict"],"count":count,"total_bytes":output["total_bytes"],
 "receipt":str(dest),"receipt_sha256":hashlib.sha256(dest.read_bytes()).hexdigest()},ensure_ascii=False))
