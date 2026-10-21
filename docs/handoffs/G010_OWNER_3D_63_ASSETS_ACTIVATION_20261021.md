# G010 Owner 3D Assets — 2026-10-21 Separate Product Candidate

**Scope:** Real player-accessible 3D catalog integration in an isolated, detached worktree, based strictly on `21a2c84aeb44674e5ff8b3cb958fbc2d38865822`. **No GitHub merge, no formal Oracle deploy, no production player mutation, no payment/equip authority change.**

## Direct functional outcome
- Real `/hero?tab=equipment` equipment panel now contains a lazy-loaded, genuine WebGL 3D asset gallery (not 2D stand-in). Browser verifies SHA-256 of the original unchanged GLB bytes before parsing; missing, corrupted or unapproved entries fail closed.
- The gallery exposes the **63 admitted/presentation-cleared GLB identities** from canonical manifests: Future30 **33** character visual variants (30 logical), **18** formally approved pet development-stage models, P048 **5** head cosmetics + **1** backpack, P048 **2** preview-only companions, and **4** copyright-cleared replacement weapons.
- Navigational links from `/shop` and `/inventory` take the player to `/hero?tab=equipment#g010-3d-gallery`. The existing Hero live-equipped WebGL renderer and server-owned inventory/appearance authority are preserved. The gallery shows model previews only; viewing a model never claims it, equips it, charges coins, changes a loadout, or elevates Premium.
- Only create WebGL context when equipment panel visible; dispose GPU resources on tab switch and visibility/page exit; touch drag, mouse drag and reset support; accessible selects/labels/status.
- **Existing** 3D Hero true-360 and formally approved Companion 360 viewers, shared Hero equipment host, and Shop purchase engine remain as-is. This delta does not re-implement any of those approved subsystems.
- Asset legal limit: 12 historic D007 GLBs remain **NOT_CLEARED** and are not admitted by this task; old replacement IDs are retired. The **4 CC0 replacement weapon models are RIGHTS_CLEARED but remain RELEASE_NOT_ADMITTED** pending separate authorized release admission. No authorization of player ownership or Production release is implied. Earlier P048 HOLD art (H01/B01/B19/H09/A10/T01/V05) is not silently promoted.

## Exact engineering delta
`hero.html`, `shop.html`, `inventory.html`, `js/g010_hero_3d_gallery.mjs`, `app.py` narrow static module allowlist, `Dockerfile` exact COPY, `deploy/build-manifest.json` exact source and installed module, `deploy/live-static-asset-inventory.json` eligible module. The gallery consumes already tracked, SHA-authorized GLBs; it creates **no** new model bytes and **no** new database tables, purchase route, source of player truth or static carte-blanche rule.

## Real evidence, machine-verifiable
- `G010_3D_ALL_63_SHA256_AUDIT_20261021.json`: **63/63 bytes SHA-256 PASS**, aggregate **270885952 bytes**; per-path original SHA, size and authority record. Cross-check count in `tests/g010_3d_all_models_integrity.py`.
- `tests/e2e/G010_3D_ASSET_GALLERY_BROWSER_20261021.json`: **23 PASS**, 10 selected real GLB WebGL models including all 4 selected weapons, changing actual pixels on pointer rotation, reset, tab-hide teardown/remount, 0 JS errors/HTTP failures.
- `tests/e2e/G010_3D_ALL_63_REAL_WEBGL_BROWSER_20261021.json`: **76 PASS**, **63/63** all models actually loaded, verified and rendered in Chrome/SW WebGL, real pixel change on rotation, one renderer, cleanup/remount, 0 errors and HTTP failures.
- `tests/e2e/G010_3D_REAL_HERO_BROWSER_20261021.json`: **6 PASS**, source `hero.html?tab=equipment` itself loads the real 3D weapon model and visible canvas, not just synthetic DOM.
- Focused source and closure regression from the isolated candidate: `python -m pytest -q tests/test_g010_3d_gallery_activation_contract.py tests/test_3d_shop_p048_runtime.py tests/test_3d_shop_presentation_foundation.py tests/deployment/test_g009_recursive_runtime_closure.py tests/test_c053_option_b_shop_ui_containment.py` = **56 PASS / 0 FAIL**.
- Browser tests were on an HTTP localhost static-source server, not an authenticated live Flask deployment. This proves genuine browser WebGL, exact asset serving and source-page wiring, but **NOT** full final image Docker Build/UAT or live entitlement/equip transactions.

## Owner gates not bypassed
- `G009_SHOP_BROWSE_PREVIEW_ONLY=true` and `CANONICAL_COIN_SHOP_PURCHASE_ENABLED=false` remain unchanged in Product policy. No coins, payment methods, purchases or gameplay-level equip were silently enabled.
- Owner-approved Future30 character acquisition and server-owned Pet/Companion stage remain controlled by existing backend. A model being viewable is not a purchase or unlock.
- Before formal release: explicit treatment of the 4 RIGHTS_CLEARED_RELEASE_NOT_ADMITTED models in the release authority; exact isolated Docker image Build + file closure and authenticated Hero/equipment/Shop/Backpack E2E; actual iPad Safari UAT; outstanding history 3+5 UI regression verdict; separate Owner GO_MERGE and GO_DEPLOY.
- No additional independent signing-host prerequisite reintroduced.
