# Governed E9 rollout configuration

`scripts/release/set-e9-rollout.ps1` is the only supported operator for the
four E9 rollout settings in Production. It uses the reviewed SSH stdin path
from `ReleaseTooling.psm1`; it never downloads or prints the protected
`/opt/go-odyssey/.env`.

```powershell
# Read-only inspection
./scripts/release/set-e9-rollout.ps1 status -LayoutFile ./deploy/release-layout.production.json
./scripts/release/set-e9-rollout.ps1 dry-run -LayoutFile ./deploy/release-layout.production.json

# Owner-gated mutations
./scripts/release/set-e9-rollout.ps1 enable-admin-only -LayoutFile ./deploy/release-layout.production.json -Execute -OwnerGate GO_DEPLOY
./scripts/release/set-e9-rollout.ps1 disable -LayoutFile ./deploy/release-layout.production.json -Execute -OwnerGate GO_DEPLOY
./scripts/release/set-e9-rollout.ps1 rollback -LayoutFile ./deploy/release-layout.production.json -Execute -OwnerGate GO_DEPLOY
```

The helper accepts no arbitrary key/value input. It locks the protected file,
creates a governed checksum-recorded backup, changes only the four E9 keys,
writes a same-filesystem temporary file, atomically replaces the original,
preserves owner/group/mode, and appends a sanitized audit record under the
release staging directory. Mutations recreate only `app` and `scheduler`
through the canonical release Compose file and restart nginx so the persisted
settings reach both runtime services. Any service or health failure attempts
the disabled state before returning failure.

The supported admin-only values are `true`, `true`, `admin_only`, and the six
Stage C component flags defined by the application. Public, percentage, named
allowlist, and arbitrary flag configurations are not supported by this tool.
