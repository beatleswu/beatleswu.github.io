# G009 uncleared 3D asset release exclusion (2026-09-28)

This is a release STOP policy, not an asset-rights clearance or a deployment receipt.
Owner mapping approval is identity authority only. D007 R1's 12 GLBs remain
`release_eligibility=NOT_CLEARED`; its candidate admission expressly does not
verify license, provenance, CC0 status, or production rights. Four Formal9
identity rows carry explicit `RIGHTS_STATUS=NOT_CLEARED` and false equip, shop,
purchase, drop, player-select, release, and Production-admission flags in
`js/g009_owner_approved_formal_equipment_mapping.js`. The other D007 assets
have no affirmative rights grant. Wooden Sword's existing identity is unchanged.

`node tests/e9_node_tests/run_g009_uncleared_release_exclusion.mjs` is the
deterministic source-release boundary gate. It enumerates all 12 exact D007
asset paths, verifies repository presence, and fails if any is included in a
static closure manifest, Docker COPY source, or build manifest. The source
`/assets/<path>` route can serve those files from a local source checkout;
repository presence and local HTTP reachability are **not** Production
admission. At this review, 12/12 public read-only HEAD requests to the exact
asset URLs on `https://godokoro.com` returned HTTP 404. That is a point-in-time
observation, not a persistent guarantee or authenticated browser acceptance.

The historical `js/formal_3d_character_equipment_runtime.js` creates its own
renderer but has zero Hero/adapter bootstrap references, no explicit Flask
route, no static inventory membership, and no Docker COPY. It is retained as
D007 historical source/test evidence, not an executable deployable route.
Do not add it to a release or import it from the shared Hero host.

Current combined Hero release must STOP independently of the asset exclusion:
`hero.html` references D007 and R2 bootstraps, and the F renderer imports the
shared host, but `app.py` has no explicit routes for these modules and the
Dockerfile does not copy their dependency graph. No build was run. A future
release candidate needs a separate, exact route/COPY/static dependency closure
and tests before any release claim; this task does not admit those modules or
the GLBs to Production.

Release decision for every NOT_CLEARED GLB: keep excluded from **both** app
image and static generation. A future change may (1) continue exclusion,
(2) replace the asset under new exact identity and authority, or (3) present
independent authoritative `RIGHTS_CLEARED` evidence and an Owner-approved
admission. In all cases re-run the 12-path manifest/COPY gate, inspect the
actual combined release artifact, and verify public serving after authorized
deployment. `equip_capability=false` alone is not a release gate.
