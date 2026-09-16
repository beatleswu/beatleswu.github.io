# P0 A+B static package preflight

## Classification

~~~text
STATIC_ONLY_CODE_HOTFIX=YES
APP_IMAGE_REBUILD_REQUIRED=NO
FULL_COORDINATED_DEPLOY_REQUIRED=NO
FUTURE_STATIC_PROMOTION_REQUIRED=YES
DEPLOY_EXECUTED=NO
~~~

The changed runtime files are index.html and js/e9/world_stage.js. The
governed inventory already includes index.html and the E9 runtime boundary,
including js/e9/world_stage.js; the generated package necessarily contains
the complete governed closure, not an ad-hoc two-file copy.

## Governed packager result

The first direct invocation against the integration worktree failed closed on
the repository's protected ignored secret_key.txt. That file was not deleted,
moved, exposed, or overwritten. A tracked-only local checkout of the same
exact integration HEAD (with no untracked secret) was used solely so the
governed packager could run its own clean-source guard.

scripts/release/package-static-release.ps1 then completed successfully with
the exact candidate SHA:

~~~text
release_git_sha=883e0e540fe4bee3998d368db1e472c347b5e892
static_generation_id=20260916-211348-883e0e54-v241-p0-srs-static-closure-hotfix
service_worker_version=v241-p0-srs-static-closure-hotfix
service_worker_asset_identity=release-883e0e540fe4bee3998d368db1e472c347b5e892
generated_worker_identity=release-883e0e540fe4bee3998d368db1e472c347b5e892
manifest_file_count=2157
bundle_file_count=2157
archive_entry_count=2157
archive_size=963952640
archive_sha256=507b980803f6440e6355e963499ab264713856ecc499f9f36cec8892c535ec80
manifest_sha256=a058bc8280c0d7a9f984e965b712f976d6a9bf23e8720b05c7019aca3d045113
gnu_tar=GNU tar 1.35
~~~

The manifest entries for the changed Product files were verified against the
candidate bytes:

~~~text
index.html
  sha256=8f2b6cf8daa8584dcc35511837a6ff2a1c46b1ca52483d7798891cd239971710
  size=1126472
js/e9/world_stage.js
  sha256=bfebe07c7eb71c661a5cdbed62b71e8899b295fd90242cadffee83c19e072f3d
  size=94886
~~~

## Cache and deploy boundary

The checked-in sw.js was not changed. The packager rewrites only the staged
worker's executable asset identity to the full release SHA. The existing
worker activation logic removes older cg-shell-/cg-img- namespaces while
retaining the current pair. No manual cache edit, live-static copy, SSH copy,
or individual-file switch was performed.

deploy-static-release.ps1 was not run in normal or -Execute mode. Its governed
contract was covered by the static tooling tests; any future promotion must
pass the exact manifest/archive to that script, which performs remote staging,
atomic current.next -> current, app/scheduler restart as required by the mount
topology, and public byte/provenance verification. This task performed
package/preflight only.

## Rollback readiness

~~~text
STATIC_ROLLBACK_READY=YES
ROLLBACK_TOOL=scripts/release/rollback-static-release.ps1
ROLLBACK_TARGET=explicit prior verified generation's release-manifest.json
RAW_FILE_COPY_ROLLBACK=FORBIDDEN
~~~
