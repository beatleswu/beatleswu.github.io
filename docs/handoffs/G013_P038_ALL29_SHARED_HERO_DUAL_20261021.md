# G013｜P038 8 mainhand + 4 shields on CURRENT G009 shared Hero rig (all 29 active characters)

## Phase acceptance: PASS — real Chrome/WebGL QA; **not** formal Player Equip/Shop admission

Source branch `g010-3d-activation-20261021`, pre-G013 baseline `5ba112bdb7682c5e6e13e43e834240b55c37e1c3`.

### What was actually integrated/tested (NEW evidence, not claiming historical P038 was rerun)

- Reused the **unchanged** `js/g009_shared_hero_attachment_host.js` and `js/hero_equipment_attachment_adapter.js` from current G008/G009 Hero, rather than creating another competing renderer or altering formal Product. New dedicated QA fixture `tests/e2e/fixtures/g013_p038_dual_hand_qa.html` leverages the actual current host, one renderer, hand.R + hand.L bone anchors, async resource disposal.
- Strict QA gate: only `http://127.0.0.1/?g013_qa=1`. The fixture validates unchanged `G011_P022_P038_QA_MODEL_RECOVERY_20261021.json`, `NOT_ADMITTED`, never permits a real client grant/equip/purchase route, and uses only **8 exact MAIN_HAND + 4 OFF_HAND** P038 QA asset IDs. Its 12 models are SHA-256 verified against the original bytes, including the two QA-only archive binaries omitted from Docker.
- For each weapon/shield, calculates world-space scale compensation from the real hand bone inherited scale, pivots sword to mesh min-Y hand grip and shield to the geometric center, normalizes model size relative to actual 3D character height, and follows both hand-bone matrices through the G009 shared host. All transforms live only inside the isolated QA fixture. The historic raw GLBs, Product rights manifest, owned items and production renderer were NOT rewritten.
- Uses real Future30 **29 P038 active Hero models** (A1/A3/V1..E3, excludes archived A2/R2). Real byte SHA validation for all 12 equipment GLBs and every character under test. Uses A1 Default/Correct action pose, A3 Default/Raised Arm action pose, 27 others in Default = **31 character+pose states**.
- Full cross product: **31 states × 8 MAIN_HAND × 4 OFF_HAND = 992 dual-handed combinations**. **1,984 independently evaluated attached hand states**; all attach status `attached`, real nonempty GLB mesh bounds, single child in MAIN_HAND and OFF_HAND, exact loaded SHA, actual bound-to-hand source, and two bone-attachment matrix deltas **0.0** across all runs. Normalized object dimension/hero height range **0.225..0.342**; center-to-hand/hero-height maximum **0.1422**; false expanded-hero intersections **0**. Runtime created only one WebGLRenderer (maximum=1), disposed it cleanly after QA. 0 JS uncaught exceptions.
- Separate smoke check **4 combinations PASS** on A1, targeted 3 Hero representative check **160 combinations PASS**, and fresh wider all-29 check **992 combinations PASS**; the final test was re-executed after correcting receipt pose-count metadata (a reporting defect, not a geometry fix).
- Four targeted real Chrome screenshots (A1 Default, A3 Default/Raised Arm, K1 Default) are retained on beatles, outside Product, and do **not** substitute for 29-character Owner visual sign-off.

### Exact reproducible sources and evidence
- QA fixture: `tests/e2e/fixtures/g013_p038_dual_hand_qa.html`.
- Browser real WebGL runner: `tests/e2e/g013_p038_12_dual_hero_real_webgl.mjs`. Run `$env:G013_ALL29='1'; node tests/e2e/g013_p038_12_dual_hero_real_webgl.mjs` on authorized beatles. `G013_SMOKE=1` limits to 4 quick combinations.
- Original full 992 case raw receipt: `D:\go-odyssey-g010-3d-activation-evidence-20261021\G013_P038_ALL29_DUAL_HAND_20261021.json` SHA-256 `c7ad0fc77607f801f5c4f78a5b0601f22d73723d68a4280c400694800e310393`.
- Tracked compact derived metrics and hash pointer: `docs/handoffs/G013_P038_ALL29_DUAL_HAND_AGGREGATE_20261021.json`.
- Standalone regression contract `tests/test_g013_p038_shared_rig_all29_qa.py`. Source archive generator under `D:\go-odyssey-g010-3d-activation-evidence-20261021\g013_generate_p038_dual_hand_fixture.py` and metric verifier `g013_aggregate_p038_29.py`.

### Nonrelease / continuation boundaries
- This exercise is an **isolated QA fixture** with synthetically validated appearance context, not a native PG player `/api/player/inventory/equip` plus Shop purchase and relogin. That separately passed only for the G012 four Formal9 CC0-but-not-admitted items (and G011 wooden sword). Do not count 12 P038 assets as saleable, owned by player or approved for formal release.
- Historic P038 source library provenance and intellectual-property restrictions remain; DO NOT transplant unadmitted or unrelated character records into Oracle. Formal Player exact inventory IDs and canonical OFF_HAND shield rights/capability have **not** been created, authorized or deployed.
- The older P038 29-character rig test ran a different source renderer; this test newly proves compatibility with the **current G009 shared-host primitives**, not completion of new production in-page server-authoritative shield equip. Owner iPad Safari signoff, production rights/admission, approved exact 3D item identities, independent GO_MERGE and GO_DEPLOY remain distinct gates.
- G013 files are all QA fixture/runner/tests and a documentation receipt; no change to `app.py`, `Dockerfile`, `hero.html`, `shop.html`, `inventory.html`, official JS renderer or asset manifests, and no production write or master merge.
