"""Write the durable provenance records for E_G009_FORMAL9_SELECTED_WEAPON_FINALIZATION_001."""
import hashlib, json, os

W = r"D:\go-website-g009-formal9-finalization-001"
S = r"D:\go-website-g009-formal9-weapon-candidates-002"
P = os.path.join(W, "provenance", "g009_formal9_rights_cleared_v1")
TASK = "E_G009_FORMAL9_SELECTED_WEAPON_FINALIZATION_001"
ASSET_DIR = "assets/3d_shop/formal9_rights_cleared_v1/weapons"


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def rel(p):
    return os.path.relpath(p, W).replace("\\", "/")


lock = {l["TMP_CANDIDATE_ID"]: l for l in json.load(open(os.path.join(S, "evidence", "final_selection_evidence_lock.json"), encoding="utf-8"))["locks"]}

ID_RULE = ("asset_id = 'WEAPON_' + UPPER(SHA256(final runtime GLB bytes)[0:12]). Same content-derived rule "
           "as the D007 formal catalog, where 7 of 12 WEAPON_ IDs equal the runtime GLB SHA-256 prefix "
           "(the other 5 used a pre-conversion source hash). The runtime GLB is used here because this task "
           "requires each ID to bind to the final accepted GLB.")

SEL = [
    ("iron_sword", "IRON_SWORD", "TMP_IRON_SWORD_A", "ONE_HAND"),
    ("fox_fang", "FOX_FANG", "TMP_FOX_FANG_A", "KNIFE_SMALL"),
    ("riverstone_sabre", "RIVERSTONE_SABRE", "TMP_RIVERSTONE_SABRE_B", "ONE_HAND"),
    ("bamboo_shadow_blade", "BAMBOO_SHADOW_BLADE", "TMP_BAMBOO_SHADOW_BLADE_A", "ONE_HAND"),
]
OLD = {"iron_sword": ("WEAPON_A7C05D43F943", "assets/3d_shop/formal_character_equipment_v1/weapons/21_adventure_sword.glb", "a7c05d43f9434a6cfd0304908c68ac2a97975c6bc641516c55e1380c5f81d2fc", "CONFLICTING_EVIDENCE"),
       "fox_fang": ("WEAPON_A70FD7AB666C", "assets/3d_shop/formal_character_equipment_v1/weapons/15_hunting_knife.glb", "a70fd7ab666cd2551520146b0a8cff7fe24c67f0cebde8d685fb273d3540f8f8", "CONFLICTING_EVIDENCE"),
       "riverstone_sabre": ("WEAPON_9CD401DADF4C", "assets/3d_shop/formal_character_equipment_v1/weapons/12_katana.glb", "9cd401dadf4cf49fc404eb30e1715a898eb6895dc32dba7c56dd8a7fd0b190c4", "INSUFFICIENT_EVIDENCE"),
       "bamboo_shadow_blade": ("WEAPON_2F4CB085CE4A", "assets/3d_shop/formal_character_equipment_v1/weapons/14_army_sword.glb", "20979ea75b6bdcaade2187de81274136d56bbad31a3860ca12373ff24dde89b8", "NOT_CLEARED")}

lic_files = {"Kenney": os.path.join(P, "licenses", "kenney_mini-dungeon__License.txt"),
             "KayKit": os.path.join(P, "licenses", "kaykit_fantasy_weapons_bits__License.txt")}
zips = {"Kenney": os.path.join(P, "sources", "kenney_mini-dungeon.zip"),
        "KayKit": os.path.join(P, "sources", "KayKit_FantasyWeaponsBits_1.0_FREE.zip")}
snaps = {"Kenney": os.path.join(P, "page_snapshots", "kenney_mini-dungeon.html"),
         "KayKit": os.path.join(P, "page_snapshots", "kaykit_fantasy-weapons-bits.html")}

assets, retire = [], []
for item, key, tmp, pclass in SEL:
    l = lock[tmp]
    glb_sha = l["INTERMEDIATE_GLB_SHA256"]
    aid = "WEAPON_" + glb_sha[:12].upper()
    path = f"{ASSET_DIR}/weapon_{glb_sha[:12]}.glb"
    assert sha(os.path.join(W, path)) == glb_sha, "final GLB bytes drifted: " + item
    prov = l["SOURCE_PROVIDER"]
    assert sha(lic_files[prov]) == l["PRIMARY_LICENSE_SHA256"]
    assert sha(zips[prov]) == l["SOURCE_ARCHIVE_SHA256"]
    assert sha(snaps[prov]) == l["PAGE_SNAPSHOT_SHA256"]
    assets.append({
        "GAME_ITEM_KEY": item, "TMP_CANDIDATE_ID": tmp, "OWNER_SELECTED": "YES",
        "NEW_ASSET_ID": aid, "asset_id_rule": ID_RULE,
        "FINAL_GLB": path, "FINAL_GLB_SHA256": glb_sha, "FINAL_GLB_BYTES": os.path.getsize(os.path.join(W, path)),
        "INTERMEDIATE_GLB_SHA256": glb_sha, "FINAL_EQUALS_OWNER_BOARD_BYTES": True,
        "presentation_class": pclass, "slot": "MAIN_HAND", "socket": "hand.R",
        "SOURCE_PROVIDER": prov, "SOURCE_CREATOR": l["SOURCE_CREATOR"], "SOURCE_PACK": l["SOURCE_PACK"],
        "SOURCE_ARCHIVE": rel(zips[prov]), "SOURCE_ARCHIVE_SHA256": l["SOURCE_ARCHIVE_SHA256"],
        "SOURCE_MODEL_ARCHIVE_MEMBERS": [{"member": f["archive_member"], "sha256": f["sha256"]} for f in l["SOURCE_MODEL_ALL_FILES"]],
        "SOURCE_MODEL_SHA256": l["SOURCE_MODEL_SHA256"],
        "PRIMARY_LICENSE_FILE": rel(lic_files[prov]), "PRIMARY_LICENSE_SHA256": l["PRIMARY_LICENSE_SHA256"],
        "LICENSE_TYPE": "CC0-1.0", "LICENSE_TEXT_REFERENCE": l["LICENSE_TEXT_REFERENCE"],
        "OFFICIAL_SOURCE_URL": l["OFFICIAL_SOURCE_URL"], "OFFICIAL_PAGE_SNAPSHOT": rel(snaps[prov]), "PAGE_SNAPSHOT_SHA256": l["PAGE_SNAPSHOT_SHA256"],
        "CONVERSION_MANIFEST": "provenance/g009_formal9_rights_cleared_v1/conversion/conversion_manifest.json",
        "CONVERSION_SCRIPT": "provenance/g009_formal9_rights_cleared_v1/conversion/normalize_candidates.py",
        "CONVERSION_SCRIPT_SHA256": sha(os.path.join(P, "conversion", "normalize_candidates.py")),
        "CONVERSION_DETERMINISM": "PASS: independent Blender 5.2 rerun reproduced byte-identical GLB",
        "PRIMARY_LICENSE_FILE_PRESENT": "YES", "PRIMARY_LICENSE_RETAINED": "YES", "COMMERCIAL_USE_ALLOWED": "YES",
        "MODIFICATION_ALLOWED": "YES", "GAME_DISTRIBUTION_ALLOWED": "YES", "RIGHTS_STATUS": "RIGHTS_CLEARED",
        "ATTRIBUTION_REQUIRED": "NO",
        "product_policy": {"EQUIP_ENABLED": "UNCHANGED_NOT_GRANTED_BY_THIS_TASK", "SHOP_ENABLED": False, "PURCHASE_ENABLED": False,
                           "DROP_ENABLED": False, "PLAYER_SELECTABLE": False, "RELEASE_ENABLED": False, "PRODUCTION_ASSET_ADMISSION": False,
                           "note": "RIGHTS_CLEARED is a rights fact only. Acquisition, shop, drop and release remain product/Owner policy."},
        "lineage": [item, aid, glb_sha],
    })
    o = OLD[item]
    retire.append({"old_asset_id": o[0], "old_runtime_asset": o[1], "old_runtime_sha256": o[2], "old_rights_review_status": o[3],
                   "former_formal9_item": item, "replaced_by_asset_id": aid, "replaced_by_sha256": glb_sha,
                   "status": "RETIRED_HISTORICAL_ONLY", "alias_to_new_bytes": False,
                   "active_mapping": False, "runtime_reachable": False, "release_included": False, "production_admission": False,
                   "rights_review_reference": "G009_FORMAL9_RIGHTS_EVIDENCE_RECOVERY_001"})

notes = {"FUTURE_VISUAL_COLLISION_NOTE": "moonstar_rapier future visual should avoid near-duplicate silhouette (riverstone_sabre uses the rapier-like KayKit sword_D). Documentation only; not a blocker."}

json.dump({"task_id": TASK, "assets": assets, "notes": notes}, open(os.path.join(P, "final_asset_manifest.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
json.dump({"task_id": TASK, "retired": retire,
           "rule": "Old IDs stay historically traceable here and in the D007 prerequisite schema; they are refused by every active resolver and never alias to the new bytes."},
          open(os.path.join(P, "old_asset_retirement_map.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
board = os.path.join(S, "board", "owner_comparison_board.html")
json.dump({"task_id": TASK, "OWNER_VISUAL_SELECTION_GATE": "CLOSED", "OWNER_SELECTION_4_OF_4": "YES",
           "selection_source": "Owner instruction in task E_G009_FORMAL9_SELECTED_WEAPON_FINALIZATION_001 (2026-09-28)",
           "board_task": "E_G009_FORMAL9_RIGHTS_CLEARED_WEAPON_REPLACEMENT_002",
           "board_artifact": "https://claude.ai/artifact/2Cpvw1expcUdq1f91VWT3o", "board_html_sha256": sha(board),
           "selections": {"IRON_SWORD_SELECTED": "TMP_IRON_SWORD_A", "FOX_FANG_SELECTED": "TMP_FOX_FANG_A",
                          "RIVERSTONE_SABRE_SELECTED": "TMP_RIVERSTONE_SABRE_B", "BAMBOO_SHADOW_BLADE_SELECTED": "TMP_BAMBOO_SHADOW_BLADE_A"},
           "resolved": {a["TMP_CANDIDATE_ID"]: {"source": lock[a["TMP_CANDIDATE_ID"]]["SOURCE_CANDIDATE_ID"], "glb_sha256": a["FINAL_GLB_SHA256"]} for a in assets},
           "substitution": "NONE", **notes},
          open(os.path.join(P, "owner_selection_receipt.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)

readme = f"""# G009 Formal9 rights-cleared replacement provenance

Self-contained rights and provenance record for the four formal9 main-hand visuals
selected by the Owner on 2026-09-28 ({TASK}). A future reviewer can verify
everything here without any chat history.

- Where did each model come from? `final_asset_manifest.json` lists provider, pack,
  official URL, the original archive (in `sources/`) and the exact archive member.
- What license shipped with it? `licenses/` holds the License.txt copied byte-for-byte
  from each original archive; both are CC0-1.0. The recorded SHA-256 also matches the
  file inside the zip.
- Are these the same bytes? `SHA256SUMS.txt` covers every file here and the four
  runtime GLBs in `{ASSET_DIR}/`. `conversion/` holds the deterministic Blender script;
  an independent rerun reproduced every GLB byte-for-byte.

Old D007 visuals retired by this change are listed in `old_asset_retirement_map.json`.
Rights clearance is not product admission: shop, purchase, drop, player selection and
release stay closed until separate Owner decisions.

KayKit's store page adds: "please don't resell unmodified copies or claim them as your
own." It is recorded verbatim in `page_snapshots/`. It is a store-page request, not a
term of the retained License.txt.

This directory is evidence only. It is not copied into the app image (Dockerfile uses an
explicit COPY list) and is not part of any static release manifest.
"""
open(os.path.join(P, "README.md"), "w", encoding="utf-8", newline="\n").write(readme)

lines = []
for base in (P, os.path.join(W, *ASSET_DIR.split("/"))):
    for dp, _, fns in os.walk(base):
        for f in sorted(fns):
            if f == "SHA256SUMS.txt":
                continue
            q = os.path.join(dp, f)
            lines.append(sha(q) + "  " + rel(q))
open(os.path.join(P, "SHA256SUMS.txt"), "w", encoding="utf-8", newline="\n").write("\n".join(sorted(lines, key=lambda s: s[66:])) + "\n")
for a in assets:
    print(a["GAME_ITEM_KEY"], a["NEW_ASSET_ID"], a["FINAL_GLB_SHA256"])
print("files hashed", len(lines))
