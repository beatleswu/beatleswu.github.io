# P0 non-admin review toolbar static hotfix plan

## Classification

- `STATIC_ONLY_HOTFIX=YES`
- `APP_IMAGE_REBUILD_REQUIRED=NO`
- `APP_FORCE_RECREATE_REQUIRED=NO`
- `D1_CHANGE=NO`
- `DB_MUTATION=NO`
- `SCHEMA_MUTATION=NO`
- `FULL_COORDINATED_DEPLOY_REQUIRED=NO`

The only shipped Product byte is `sgf_report_widget.js`. The governed static
release must be generated from the exact admitted canonical SHA using
`scripts/release/package-static-release.ps1`, then promoted only with
`scripts/release/deploy-static-release.ps1 -Execute -OwnerGate GO_DEPLOY`.
No manual copy, ad-hoc SSH patch, service-worker edit, image rebuild, or app
recreate is allowed.

The static tool creates a new generation and atomically switches `current`;
the governed verifier checks the public HTTPS bytes and worker identity. On a
public verification failure, use the explicit prior verified generation with
`scripts/release/rollback-static-release.ps1`.

Pre-hotfix Production read-only identity was:

- static generation: `20260916-233517-ba31e884-v241-p0-srs-static-closure-hotfix`
- static source: `ba31e8840eb6f90e2d000a41ceca570da944b815`
- app image remained `go-odyssey-app:8b21c2f6`
- D1 remained `global`

Promotion fields are intentionally recorded by the coordinator after
canonical admission and public verification; this candidate report does not
claim a live promotion.
