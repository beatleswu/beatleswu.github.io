"""G043: exact Bunny/Corgi supplemental Static closure without player state changes."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[2]
PACK=ROOT/"deploy/g043-bonus-companion-supplemental-static-pack-manifest.json"
OLD=ROOT/"docs/handoffs/G010_P048_C01_C04_IMAGE_CLOSURE_20261021.json"
INVENTORY=ROOT/"deploy/live-static-asset-inventory.json"
FORMAL=(
 "deploy/g009-hero-model-static-pack-manifest.json",
 "deploy/g009-companion-formal18-static-pack-manifest.json",
 "deploy/g009-formal9-replacement-static-pack-manifest.json",
)
ALLOWED={
 "assets/3d_shop/p048/companion/C01/animal-bunny.glb",
 "assets/3d_shop/p048/companion/C01/Textures/colormap.png",
 "assets/3d_shop/p048/companion/C04/Corgi.glb",
}
def load(path): return json.loads(path.read_text(encoding="utf8"))
def validate_exact_pack(info,source):
    rows=info["files"]
    if len(rows)!=3 or set(x["path"] for x in rows)!=ALLOWED:
        raise ValueError("Supplemental pack may only contain three exact authorized paths")
    if len({x["path"] for x in rows})!=3:
        raise ValueError("Duplicate path")
    evidence={e["path"]:e for e in source["files"]}
    for row in rows:
        path=row["path"]
        if ".." in Path(path).parts or path.startswith("/") or path not in evidence:
            raise ValueError("Unapproved or unsafe supplemental path")
        f=ROOT/path
        if not f.is_file() or f.stat().st_size != row["size"] or row["size"]!=evidence[path]["bytes"]:
            raise ValueError("Supplemental file size does not match approved source")
        sh=hashlib.sha256(f.read_bytes()).hexdigest()
        if sh!=row["sha256"] or sh!=evidence[path]["sha256"]:
            raise ValueError("Supplemental file SHA not previously verified")
    if info["total_files"]!=3 or info["total_bytes"]!=sum(x["size"] for x in rows):
        raise ValueError("Supplemental pack totals inconsistent")
    if info["new_pet_entitlement"] is not False or info["pet_key_runtime_authority"]!="EXISTING_PET_KEY_REQUIRED_AT_RUNTIME":
        raise ValueError("Unauthorized player ownership policy")
    if not info["canonical_formal_69_glb_unchanged"]:
        raise ValueError("Formal asset count modified")
    if not info["release_admission"] or info["admission_scope"]!="EXACT_THREE_BONUS_PRESENTATION_ASSETS_ONLY":
        raise ValueError("No exact Owner release admission")

def test_three_exact_supplemental_assets_have_existing_content_sha_and_bytes():
    info,old=load(PACK),load(OLD)
    assert old["release_admission"] is False  # never rewrite original G010 history
    assert old["ownership_authority_changes"] is False
    assert info["source_evidence_sha256"]==hashlib.sha256(OLD.read_bytes()).hexdigest()
    validate_exact_pack(info,old)

def test_only_exact_three_bonus_files_join_disjoint_69_formal_models():
    info=load(PACK)
    formal=set()
    for name in FORMAL:
        data=load(ROOT/name)
        formal|={x["path"] for x in data["files"] if x["path"].endswith(".glb")}
    assert len(formal)==69
    assert len([x for x in info["files"] if x["path"].endswith(".glb")])==2
    assert formal.isdisjoint(ALLOWED)
    assert (ROOT/"assets/3d_shop/p048/runtime_manifest.json").is_file()

def test_supplemental_pack_is_staged_by_real_static_inventory_without_wildcard():
    entries=load(INVENTORY)["required_subtrees"]["entries"]
    related=[e for e in entries if e["manifest"]==PACK.relative_to(ROOT).as_posix()]
    assert len(related)==1
    assert related[0]["prefix"]=="assets/3d_shop/p048/companion/"
    assert "exactly" in related[0]["staging_rule"].lower()
    assert len(set(x["manifest"] for x in entries))==len(entries)

@pytest.mark.parametrize("mutation",["sha","bytecount","extra","duplicate","missing","playergrant","modelcount","noapproval"])
def test_unapproved_or_corrupt_supplemental_manifest_rejected(mutation):
    info=copy.deepcopy(load(PACK))
    if mutation=="sha":info["files"][0]["sha256"]="0"*64
    if mutation=="bytecount":info["files"][0]["size"]+=1
    if mutation=="extra":info["files"].append({"path":"assets/3d_shop/p048/companion/evil.glb","size":1,"sha256":"1"*64})
    if mutation=="duplicate":info["files"][1]=info["files"][0]
    if mutation=="missing":info["files"].pop()
    if mutation=="playergrant":info["new_pet_entitlement"]=True
    if mutation=="modelcount":info["canonical_formal_69_glb_unchanged"]=False
    if mutation=="noapproval":info["release_admission"]=False
    with pytest.raises(ValueError):
        validate_exact_pack(info,load(OLD))
