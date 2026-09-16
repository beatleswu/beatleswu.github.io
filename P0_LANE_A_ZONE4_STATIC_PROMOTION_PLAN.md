# P0 Lane A Zone4 static promotion plan

This is a future plan only. No release, deployment, cache switch, restart, or
Production mutation was performed in this task.

STATIC_ONLY_HOTFIX=YES
APP_IMAGE_REBUILD_REQUIRED=NO
FULL_COORDINATED_DEPLOY_REQUIRED=NO
DB_MUTATION_REQUIRED=NO

The governed static inventory already includes js/e9/world_stage.js in its
eligible E9 runtime boundary. The minimum future mechanism is:

1. From an exact governed candidate checkout, run
   scripts/release/package-static-release.ps1 to stage the declared static
   inventory, verify bytes, parse the service-worker identity, and create the
   immutable bundle and release manifest.
2. Pass that exact bundle and manifest to
   scripts/release/deploy-static-release.ps1 under its normal Owner-gated
   execution path. Do not use an ad-hoc SSH copy or root deploy replacement.
3. Verify public HTTPS bytes and static-release provenance after the atomic
   activation. The script uses current.next plus atomic rename and has
   automatic recovery on post-switch verification failure.

APP_IMAGE_REBUILD_REQUIRED=NO means the existing live-static serving boundary
can deliver this static runtime correction without rebuilding the application
image. The governed static script may restart app and scheduler after a
symlink switch because their bind mount resolves the target at container
start; that operational restart is not an app-image rebuild.

## Cache and rollback behavior

SW_CACHE_ROTATION_BEHAVIOR:

- The candidate does not change sw.js.
- The existing worker derives shell/image cache names from VERSION and
  ASSET_IDENTITY.
- The existing activate handler removes older cg-shell- and cg-img- cache
  namespaces while retaining the current pair.
- The static packager and public verifier must validate the generated worker
  identity; no manual cache edit is permitted.

HTTP_CACHE_BEHAVIOR:

- Publish a new immutable generation directory.
- Switch current atomically through current.next and mv -Tf.
- Verify raw public HTTPS bytes with the governed cache-busting verification
  path and verify the public service-worker version and release provenance.
- Never copy an individual file into the live current directory.

ROLLBACK_METHOD:

Use scripts/release/rollback-static-release.ps1 with an explicit known-good
TargetGenerationPath. It reads that generation's release-manifest.json,
atomically switches current, restarts app and scheduler as required by the
mount topology, and re-verifies public bytes and provenance. Do not rely on a
bare legacy previous symlink.

