# Go Odyssey G010 RC Stage 1 — Local candidate source/image integrity
Date: 2026-10-20 | G MASTER | Stage decision: RC_STAGE1_LOCAL_INTEGRITY_PASS

## Goal
Take the M1–M5 accepted local Product candidate without any master changes, production database writes or deploy. Prove that the already built isolated Docker runtime files match the tested candidate source BY CONTENT HASH, preserve release gates, and package reproducible owner-review evidence. This stage is NOT independent signed-source admission or full RC release authorization.

## Immutable source, image and results
- Branch candidate/go-product-integrated-20261019, baseline SHA efd4524c3a3b5669b693ee0be50acf586c73ad90, changes remain UNCOMMITTED.
- Local Docker candidate image ID sha256:ad3baf13342d5f9e23acaf2770cc6b8e0f937222b7678c24a166afb64877644e.
- New checker: tests/_verify_g010_rc_image_source_integrity.py reads M5 build-evidence hashes; verifies all nine workstation overlay sources exactly match recorded hashes, Docker tag ID matches, and the seven app runtime files INSIDE a network-disabled, read-only Docker container have exact byte-for-byte SHA-256 equality. Also checks mandatory M4 UI assets in Dockerfile and Build manifest inputs/post-build file list.
- Checker result: G010_RC_LOCAL_IMAGE_BINARY_SOURCE_INTEGRITY=PASS. FILES_MATCHED=7; RELEASE_FEATURE_GATES=OFF. Real Product shop.html G009 browse preview and inventory.html G009 read-only constants remain TRUE; no known /app/.env, /app/.env.production or /app/secret_key.txt inside the inspected image.
- Image verification artifact: docs/handoffs/GO_ODYSSEY_G010_RC_IMAGE_SOURCE_INTEGRITY_20261020.json.
- Prior M5 integrated tests 65/65 PASS, policy regressions 192/192 PASS, one-identity full native PG and real Chrome test 1/1 PASS, 258 unique tests; not rerun by this RC stage. Building was local, not attested.
- `git diff --check` was PASS at M5 handoff, no new Product runtime source files were changed by RC Stage 1.

## Release readiness limits — NO_GO for Owner-gated or independent steps
- Real physical iPad Safari UAT remains PENDING; Chrome tablet touch emulation is not physical iPad Owner acceptance. Do not mark M5 CLOSED until passed.
- Formal signed source/Build attestation and independently verifiable one-time release consent remain UNVERIFIED. V4 trusted Guest OAuth, WORM/Owner gate and Goal Loop remain NO_GO. The local build digest and local hash comparisons are NOT a substitute.
- Legacy D5C retired cosmetic purchase test still expects 200 for a correctly gated 409; D017 exact PG16.14 preflight cannot be proven on installed PG17.10. These are explicitly outstanding compatibility/external acceptance cases, not silently counted as PASS.
- 13 prior Zone1 second-star Oracle correction still BLOCKED by formal maintenance gate.
- GitHub master Commit/Merge/Push, Oracle production DB and godokoro.com deployment NOT performed; origin PUSH disabled. No temporary/test feature flag persisted to a public environment.
- Source review ZIP is owner review evidence, not a release signature; do not stage secret_key.txt, `.env` or use `git add .`.

## Work that can proceed without Owner
1. Independent source/diff and known-red audit after required test versions are available; integrate only with separately authorized isolated branch and verify hash evidence before any merge.
2. Owner-run physical iPad on a deliberately admitted staging URL; verify WGo touch 20Q, Quest ledger, Shop preview default-off, Backpack, leaderboard and cross-session state. Do not invent Owner PASS.
3. External trusted signed source and formal build gate; final Merge, Oracle Build/Deploy and rollback remain separate Owner-authorized operations.

Conclusion: RC_STAGE1_LOCAL_INTEGRITY_PASS; G010_M5_FORMAL_RELEASE_READY=FALSE.
