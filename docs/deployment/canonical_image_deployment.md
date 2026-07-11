# Canonical Image Deployment

This PR adds release tooling for the image-based deployment path.

Important boundary:

- PR/tooling merge does not deploy Production.
- Production mutations remain gated behind explicit owner approval and a separate run.

## Release Flow

The intended deployment sequence is:

1. build from merged `master`
2. package and checksum the image
3. run read-only Production preflight
4. record the rollback image identity
5. verify external content mounts
6. require the `GO_DEPLOY` owner gate
7. switch app
8. verify app
9. switch scheduler
10. verify scheduler
11. verify E2.4A safety checks
12. record the release result
13. rollback if any mandatory gate fails

## Tooling

- `scripts/release/build-release-image.ps1`
- `scripts/release/package-release-image.ps1`
- `scripts/release/preflight-production.ps1`
- `scripts/release/deploy-release-image.ps1`
- `scripts/release/verify-production-release.ps1`
- `scripts/release/rollback-release.ps1`

## Safety

- The compose release file references an immutable image tag.
- The scheduler defaults to `PREMIUM_WEEKLY_SCHEDULER_ENABLED=0`.
- The release scripts keep deployment commands behind dry-run or owner-gated execution.
- Generated release artifacts live under `release-artifacts/`, which is ignored by Git.
