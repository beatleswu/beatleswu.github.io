"""Phase 1: lock rights evidence for the four Owner-selected candidates.

Every hash is recomputed here from the retained original archives (zip members
read directly), the extracted copies, and the page snapshots. Any mismatch stops
with STOP_SELECTED_ASSET_RIGHTS_EVIDENCE_MISMATCH. CPU only.
"""
import hashlib, json, os, re, sys, zipfile

ROOT = r"D:\go-website-g009-formal9-weapon-candidates-002"
EV = os.path.join(ROOT, "evidence")
SNAP = os.path.join(EV, "page_snapshots")


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha(p):
    return sha_bytes(open(p, "rb").read())


PACKS = {
    "KENNEY_MINI_DUNGEON": dict(provider="Kenney", creator="Kenney (www.kenney.nl)", pack="Mini Dungeon (2.0)",
        zip=r"sources\kenney\kenney_mini-dungeon.zip", lic="License.txt", ex=r"extracted\kenney_mini-dungeon",
        url="https://kenney.nl/assets/mini-dungeon", snap="kenney_mini-dungeon.html"),
    "KAYKIT": dict(provider="KayKit", creator="Kay Lousberg (www.kaylousberg.com)", pack="KayKit : Fantasy Weapons Bits (1.0) FREE",
        zip=r"sources\kaykit\KayKit_FantasyWeaponsBits_1.0_FREE.zip", lic="KayKit_FantasyWeaponsBits_1.0_FREE/License.txt",
        ex=r"extracted\kaykit_fantasy_weapons_bits", url="https://kaylousberg.itch.io/fantasy-weapons-bits", snap="kaykit_fantasy-weapons-bits.html"),
}

SELECTED = [
    ("iron_sword", "IRON_SWORD", "TMP_IRON_SWORD_A", "KN_MINIDUNGEON_SWORD", "KENNEY_MINI_DUNGEON", ["Models/GLB format/weapon-sword.glb"]),
    ("fox_fang", "FOX_FANG", "TMP_FOX_FANG_A", "KK_DAGGER_A", "KAYKIT",
     ["KayKit_FantasyWeaponsBits_1.0_FREE/Assets/gltf/dagger_A.gltf", "KayKit_FantasyWeaponsBits_1.0_FREE/Assets/gltf/dagger_A.bin"]),
    ("riverstone_sabre", "RIVERSTONE_SABRE", "TMP_RIVERSTONE_SABRE_B", "KK_SWORD_D", "KAYKIT",
     ["KayKit_FantasyWeaponsBits_1.0_FREE/Assets/gltf/sword_D.gltf", "KayKit_FantasyWeaponsBits_1.0_FREE/Assets/gltf/sword_D.bin"]),
    ("bamboo_shadow_blade", "BAMBOO_SHADOW_BLADE", "TMP_BAMBOO_SHADOW_BLADE_A", "KK_SWORD_E", "KAYKIT",
     ["KayKit_FantasyWeaponsBits_1.0_FREE/Assets/gltf/sword_E.gltf", "KayKit_FantasyWeaponsBits_1.0_FREE/Assets/gltf/sword_E.bin"]),
]
KAYKIT_TEXTURE = "KayKit_FantasyWeaponsBits_1.0_FREE/Textures/weapons_bits_texture.png"

REQ_TEXT = {
    "KENNEY_MINI_DUNGEON": ["Creative Commons Zero, CC0", "http://creativecommons.org/publicdomain/zero/1.0/", "commercial purposes"],
    "KAYKIT": ["Creative Commons Zero, CC0", "http://creativecommons.org/publicdomain/zero/1.0/", "commercial projects"],
}

conv = json.load(open(os.path.join(EV, "conversion_manifest.json"), encoding="utf-8"))
snap_sums = {}
for l in open(os.path.join(SNAP, "SHA256SUMS.txt")).read().split("\n"):
    if l.strip():
        h, f = l.split(None, 1)
        snap_sums[os.path.basename(f.strip().lstrip("*"))] = h

failures, locks = [], []
for item, key, tmp, cid, pk, members in SELECTED:
    p = PACKS[pk]
    zp = os.path.join(ROOT, p["zip"])
    z = zipfile.ZipFile(zp)
    names = set(z.namelist())
    lic_bytes = z.read(p["lic"]) if p["lic"] in names else None
    lic_ex = os.path.join(ROOT, p["ex"], p["lic"].replace("/", os.sep))
    lic_text = lic_bytes.decode("utf-8", "replace") if lic_bytes else ""
    ok_text = all(t in lic_text for t in REQ_TEXT[pk])
    model_files = []
    for m in members + ([KAYKIT_TEXTURE] if pk == "KAYKIT" else []):
        zb = z.read(m)
        exf = os.path.join(ROOT, p["ex"], m.replace("/", os.sep))
        model_files.append({"archive_member": m, "sha256": sha_bytes(zb), "extracted_path": exf, "extracted_matches_archive": sha(exf) == sha_bytes(zb)})
    snap_path = os.path.join(SNAP, p["snap"])
    snap_sha = sha(snap_path)
    inter = os.path.join(ROOT, "candidates", cid + ".glb")
    lock = {
        "GAME_ITEM_KEY": item, "TMP_CANDIDATE_ID": tmp, "SOURCE_CANDIDATE_ID": cid,
        "SOURCE_PROVIDER": p["provider"], "SOURCE_CREATOR": p["creator"], "SOURCE_PACK": p["pack"],
        "SOURCE_ARCHIVE": zp, "SOURCE_ARCHIVE_SHA256": sha(zp),
        "SOURCE_MODEL_FILE": model_files[0]["extracted_path"], "SOURCE_MODEL_SHA256": model_files[0]["sha256"],
        "SOURCE_MODEL_ALL_FILES": model_files,
        "PRIMARY_LICENSE_FILE": lic_ex, "PRIMARY_LICENSE_SHA256": sha_bytes(lic_bytes) if lic_bytes else None,
        "PRIMARY_LICENSE_EXTRACTED_MATCHES_ARCHIVE": bool(lic_bytes) and sha(lic_ex) == sha_bytes(lic_bytes),
        "LICENSE_TYPE": "CC0-1.0", "LICENSE_TEXT_REFERENCE": "http://creativecommons.org/publicdomain/zero/1.0/",
        "LICENSE_REQUIRED_PHRASES_PRESENT": ok_text,
        "OFFICIAL_SOURCE_URL": p["url"], "OFFICIAL_PAGE_SNAPSHOT": snap_path, "PAGE_SNAPSHOT_SHA256": snap_sha,
        "PAGE_SNAPSHOT_MATCHES_RECORDED": snap_sums.get(p["snap"]) == snap_sha,
        "CONVERSION_MANIFEST": os.path.join(EV, "conversion_manifest.json"), "CONVERSION_MANIFEST_SHA256": sha(os.path.join(EV, "conversion_manifest.json")),
        "CONVERSION_SETTINGS": conv["settings"], "CONVERSION_SCRIPT_SHA256": conv["script_sha256"],
        "INTERMEDIATE_GLB": inter, "INTERMEDIATE_GLB_SHA256": sha(inter),
        "OWNER_SELECTED": "YES",
        "PRIMARY_LICENSE_FILE_PRESENT": "YES" if lic_bytes else "NO",
        "PRIMARY_LICENSE_RETAINED": "YES" if (lic_bytes and os.path.isfile(lic_ex)) else "NO",
        "COMMERCIAL_USE_ALLOWED": "YES" if ok_text else "UNSUPPORTED",
        "MODIFICATION_ALLOWED": "YES" if ok_text else "UNSUPPORTED",
        "GAME_DISTRIBUTION_ALLOWED": "YES" if ok_text else "UNSUPPORTED",
    }
    if not (lock["PRIMARY_LICENSE_FILE_PRESENT"] == "YES" and lock["PRIMARY_LICENSE_RETAINED"] == "YES"
            and lock["PRIMARY_LICENSE_EXTRACTED_MATCHES_ARCHIVE"] and ok_text and lock["PAGE_SNAPSHOT_MATCHES_RECORDED"]
            and all(f["extracted_matches_archive"] for f in model_files)):
        failures.append(tmp)
    locks.append(lock)

out = {"task_id": "E_G009_FORMAL9_SELECTED_WEAPON_FINALIZATION_001", "phase": "1_EVIDENCE_LOCK",
       "status": "STOP_SELECTED_ASSET_RIGHTS_EVIDENCE_MISMATCH" if failures else "PASS",
       "failures": failures, "locks": locks}
json.dump(out, open(os.path.join(EV, "final_selection_evidence_lock.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print(out["status"], failures)
for l in locks:
    print(l["TMP_CANDIDATE_ID"], l["SOURCE_MODEL_SHA256"][:12], l["PRIMARY_LICENSE_SHA256"][:12], l["INTERMEDIATE_GLB_SHA256"][:12])
sys.exit(1 if failures else 0)
