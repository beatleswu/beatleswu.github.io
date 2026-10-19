# Go Odyssey G MASTER — REAL 3D 360-degree Character and Spirit Viewer Candidate

**Date:** 2026-10-19
**Scope:** Isolated Product G candidate. **Not** GitHub master, formal Build, release, or Owner UAT.
**Base:** `31c84ef0140ff19fb44d6d2af982e8dc14d37f9e` (already includes `02f5f700` and the month reward `00e9120d`).
**GO / NO_GO:** Isolated engineering and Chrome WebGL E2E **PASS**; production/Test02/real iPad/release **NO_GO**.

## Actual user-visible defect
- C005/G008 Character Hero already loaded authentic WebGL/GLB meshes, but
  `.g008-future30-hero-stage` explicitly had `pointer-events:none`,
  and the renderer had **no** scene rotation controls.
- The G009 Companion pane displayed static WebP card art despite existing
  SHA-256 authenticated 6 Spirits × 3 stage **18 real GLB assets**.
  There was no separate true-3D orbit/view control.

## Actual code remediation
1. `js/g008_future30_hero_renderer.js`: true Group-based turntable around
   the ground-centred character. The original renderer, authentic GLB bytes,
   equipment, and authorized companion child remain in the same 3D scene.
   Drag/touch Pointer Events (360 unrestricted yaw), accessible keyboard
   arrows/Home, rotate +/-45 and reset buttons. Pointer capture failures
   degrade safely; teardown releases handlers. No CSS rotation of a bitmap.
2. `hero.html`, `css/g009_hero_hub_batch_a.css`: visible 360 controls for
   the loaded 3D Hero only; an independent Companion 3D viewport with its
   own rotate/reset controls. Buttons are hidden/disabled unless genuine
   canvas/verified-model runtime reports ready. Touch action applies only
   to interactive canvas, preserving page scroll elsewhere.
3. `js/g009_companion_360_viewer.mjs`: lazy single EXTRA WebGL viewport
   **only on the visible Spirit tab**. It uses actual server
   `/api/pet/status.pet_key+level`, the existing Owner-approved Formal18
   manifest hash, 18-stage mapping and exact GLB byte counts/SHA-256.
   Shows genuine Three.js mesh, not an image. Changes tab, page visibility,
   or unload dispose GPU/GLB resources and pointer controls; remount is
   bounded (max two visible canvases counting G008 Hero).
   If model/manifest fails validation, show honest unavailable status and
   keep existing static-art fallback. No new Companion or entitlement state.
4. `app.py` narrow static JS allowlist, `Dockerfile` baked copy,
   `deploy/build-manifest.json` exact source/verification membership,
   `deploy/live-static-asset-inventory.json` explicit eligibility,
   `tests/deployment/test_g009_recursive_runtime_closure.py` dependency
   closure. This was essential: actual Flask initially returned **404**
   for the new .mjs; now the exact bounded route returns **200**.
   NO blanket `/js` route was enabled. No production Build performed.

## Evidence — saved and real
- Final create-only receipt:
  `docs/handoffs/GO_ODYSSEY_REAL_3D_360_BROWSER_20261019_R2.json`.
  `node tests/e2e/run_20261019_real_glb_360_browser.mjs`:
  **7/7 PASS**, Chrome headless actual WebGL + real unmodified C005 Hero GLB
  and Formal18 Companion assets, verifies model meshes and rendered canvas
  pixel differences after drag, keyboard arrows/Home, touch PointerEvent,
  GUI buttons/reset, tab-hide GPU release/remount, **all 18 approved
  Companion growth-stage meshes** each changing genuine pixels on rotation,
  and corrupted GLB fail-closed with no fake 3D.
  Test harness is a localhost, synthetic identity/REST projection with
  original authenticated *asset integrity validators*, not production Test02.
- Flask actual `/hero?tab=pet` from disposable D037 server:
  newly wired `/js/g009_companion_360_viewer.mjs` HTTP **200**,
  original Hero HTML + app CSS, real vetted `ink_drop_kelpie` stage-I GLB
  rendered in one canvas, manual synthetic touch pointer drag reached
  **83 degrees**. G008 Hero itself intentionally cannot complete under
  D037's minimal synthetic character catalog (HTTP 500); its real C005
  asset + turntable was proven separately in the Chrome WebGL fixture.
- Packaging/static/companion Python regression:
  **146 passed, 0 failed** (includes recursive HTTP reachable source,
  Dockerfile and build-manifest source closure checks).
- Previous Companion switch/pat/feed/browser idempotency E2E:
  **8/8 PASS** after this change against the disposable Flask/SQLite
  fixture. Existing G008 shared-host 18/18 and 30 logical projections,
  33 visuals, 9 fail-closed cases PASS controlled Node tests.
- No changes to original owner-approved GLB models, mapping manifest,
  SHA authority, monthly reward logic, GitHub master, player DB, or Oracle.

## Next Owner Gate
- Owner/Reviewer: inspect and formally admit trusted GitHub source and
  governed Build manifest. Perform formal isolated Build, required Docker
  tests, rollback attestation, and independent diff/receipt review.
- Owner authentic **Test02** on candidate/authorized site: on Hero tab drag
  a true 3D character **front → side → back → front**; on Spirit tab view
  and rotate selected canonical Spirit, change Spirit and verify model
  follows server account state; confirm switching/patting/feeding and
  relogin persistence. No touching real live Test02 data without approval.
- Owner **real iPad Safari** UAT: touch-drag both real 3D canvases, buttons,
  tab switch, low-memory/visibility restore, map & Adventure continuation.
  Desktop touch emulation and synthetic PointerEvents **cannot** satisfy
  the genuine iPad acceptance.
- **NO RELEASE / NO DEPLOY** until source, Build, rollback and Owner GO.

**V4 R15 Autonomous Goal Loop:** Separate and still **NO_GO**; these
product changes were directly supervised, not V4 self-executed E2E.
