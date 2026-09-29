# G009 Formal9 rights-cleared replacement provenance

Self-contained rights and provenance record for the four formal9 main-hand visuals
selected by the Owner on 2026-09-28 (E_G009_FORMAL9_SELECTED_WEAPON_FINALIZATION_001). A future reviewer can verify
everything here without any chat history.

- Where did each model come from? `final_asset_manifest.json` lists provider, pack,
  official URL, the original archive (in `sources/`) and the exact archive member.
- What license shipped with it? `licenses/` holds the License.txt copied byte-for-byte
  from each original archive; both are CC0-1.0. The recorded SHA-256 also matches the
  file inside the zip.
- Are these the same bytes? `SHA256SUMS.txt` covers every file here and the four
  runtime GLBs in `assets/3d_shop/formal9_rights_cleared_v1/weapons/`. `conversion/` holds the deterministic Blender script;
  an independent rerun reproduced every GLB byte-for-byte.

Old D007 visuals retired by this change are listed in `old_asset_retirement_map.json`.
Rights clearance is not product admission: shop, purchase, drop, player selection and
release stay closed until separate Owner decisions.

KayKit's store page adds: "please don't resell unmodified copies or claim them as your
own." It is recorded verbatim in `page_snapshots/`. It is a store-page request, not a
term of the retained License.txt.

This directory is evidence only. It is not copied into the app image (Dockerfile uses an
explicit COPY list) and is not part of any static release manifest.
