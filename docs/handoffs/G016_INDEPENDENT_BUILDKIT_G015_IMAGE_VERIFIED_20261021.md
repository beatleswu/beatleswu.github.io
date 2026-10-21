# G016｜Independent BuildKit G015 image integrity and offline container smoke

Date: 2026-10-21, authorized beatles host. This is evidence for the isolated Go Odyssey Product 3D candidate, NOT a GO_MERGE, GO_DEPLOY, rights admission, formal product release or physical Safari UAT.

## Provenance and previously blocked state

Target source, still the unchanged G015 tested code: 4db8bfac69cb29aca58e97ed00e3deac1c345dc9. Parent G014 bdb342475951b5ef30e3c50bd3a8014efe7e03ff. Protected latest Product candidate 21a2c84aeb44674e5ff8b3cb958fbc2d38865822 remains unchanged. G015 native PG + original /hero Chrome WebGL: 4 dual-hand render states, 2 independently signed logins, default-off guard PASS; 157 regression PASS, 8 skipped, 0 FAIL.

Prior standard Docker builder failures were real:
- 261 build steps completed but export/unpack failed with unpigz crc32 mismatch.
- Alternate OCI exporter reported an unexpected digest; the 245 MB tar was independently proven incomplete (missing index.json and one sha256 blob mismatch).
Do not use those failed artifacts.

## G016 new independent builder (not global cache prune)

Create isolated builder named g016-clean-only with Docker's already locally present moby/buildkit:buildx-stable-1 and docker-container driver. Build with a separate BuildKit data container, without deleting / pruning any Docker caches, prior images, volumes or Go Odyssey QA containers.

Run a complete 261-step Dockerfile build from EXACT G015 source SHA. Docker BuildKit finished and exported a clean OCI file with exit code 0 (independent from previous Docker Desktop built-in builder):
D:\go-odyssey-g010-3d-activation-evidence-20261021\G016_CLEAN_BUILDKIT_G015_4DB8BFA_20261021.tar

- 289,699,840 bytes, OCI tar SHA-256 eb091fa1d3dc2968492eedc62d480dd7549451a2dad39cbd1870bcc5b36a4d92.
- OCI manifest digest sha256:dc4472d2513cc61a43419b04fa2c56c3363c259085cd45bc1d419dce2846a369.
- Image config digest sha256:5582c5d697245b300174c9f027436e10b318ff6c333acdafe098a05a78fdd2c9.
- Independent tar verifier: validates OCI index, 264 blob SHA-256 digests, image manifest and config, revision label/APP_GIT_SHA, 264 layer references, and extracts runtime source from OCI layer streams to verify exact byte equality for original hero.html, G009 equipment bootstrap, G009 shared attachment host and offhand migration.
- Explicitly scans all OCI layer paths to reject test-only G015 QA bridge, G011 private GLB material, secret_key.txt and stage.env. WARNING: Ten previously tracked P038 GLB bytes may already be present in official image; binary presence does not imply P038 legal admission or gameplay entitlement.
- Verifier output PASS, 0 missing source files, 0 unwanted QA/private files, 0 SHA mismatch:
D:\go-odyssey-g010-3d-activation-evidence-20261021\G016_CLEAN_BUILDKIT_FULL_OCI_VERIFICATION_20261021.json

The same full hash-verified OCI was actually imported into Docker (docker load exit code 0) as image sha256:dc4472d2513cc61a43419b04fa2c56c3363c259085cd45bc1d419dce2846a369, locally tagged go-odyssey:g016-4db8bfa-verified-local; tag never pushed.
A read-only, network-disconnected, auto-removed Docker container then successfully executed its real image-bundled Python and checked the offhand canonical slots, original Hero HTML, actual G009 bootstrap and hand scale runtime, original G015 Git SHA, and verified the QA bridge and private GLB paths are absent. Exit code 0; printed G016_RUNTIME_SOURCE_SMOKE_PASS.

## Distinct gates

**G016 image build, OCI digest, loaded Docker image, offline smoke: PASS.** Old G015 HOLD_UNTRUSTED_DOCKER_LAYER_OR_EXPORT is resolved for this specifically inspected independently built candidate, not magically for every Docker Desktop build/cache.

**Formal game economy/asset release remains NO-GO**: P038 12 derived/historical weapon-shield models are still NOT_ADMITTED, G014 synthetic SKU definitions do not exist in formal server item catalog, original public Hero route still suppresses those unadmitted assets, and Shop remains browse-only/default-off. P022 extra 16 assets remain nonrelease QA. Owner physical iPad Safari validation unperformed. No formal player data, GitHub master, Oracle deploy or production P038 model licensing status changed.

**G016 handoff/version caveat**: The image revision is G015 code SHA 4db8bfa; any later G016 documentation-only Git commit does not change the accepted OCI source revision. When reporting latest Git HEAD, distinguish evidence handoff commit from the image-source commit.

All evidence is on the authorized beatles host and this handoff is a description, not a release signature.
