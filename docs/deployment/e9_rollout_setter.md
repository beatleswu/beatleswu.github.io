# Governed E9 rollout configuration

`scripts/release/set-e9-rollout.ps1` is the only supported operator for E9
rollout settings in Production. It uses the reviewed SSH stdin path from
`ReleaseTooling.psm1`; it never downloads or prints the protected
`/opt/go-odyssey/.env`. The host's existing non-interactive `sudo` policy is
used only to run this fixed helper as the file owner; no shell command or
arbitrary environment editor is accepted.

```powershell
# Read-only inspection
./scripts/release/set-e9-rollout.ps1 status -LayoutFile ./deploy/release-layout.production.json
./scripts/release/set-e9-rollout.ps1 dry-run -LayoutFile ./deploy/release-layout.production.json
# Preview all-authenticated E10 access specifically (still read-only):
./scripts/release/set-e9-rollout.ps1 dry-run -LayoutFile ./deploy/release-layout.production.json -Authenticated
# Preview an allowlist enablement specifically (still read-only):
./scripts/release/set-e9-rollout.ps1 dry-run -LayoutFile ./deploy/release-layout.production.json -AllowlistIds "7,42,100"

# Owner-gated mutations
./scripts/release/set-e9-rollout.ps1 enable-admin-only -LayoutFile ./deploy/release-layout.production.json -Execute -OwnerGate GO_DEPLOY
./scripts/release/set-e9-rollout.ps1 disable -LayoutFile ./deploy/release-layout.production.json -Execute -OwnerGate GO_DEPLOY
./scripts/release/set-e9-rollout.ps1 rollback -LayoutFile ./deploy/release-layout.production.json -Execute -OwnerGate GO_DEPLOY
# Enable a named allowlist -- separate gate, see below:
./scripts/release/set-e9-rollout.ps1 enable-allowlist -LayoutFile ./deploy/release-layout.production.json -AllowlistIds "7,42,100" -Execute -OwnerGate GO_ENABLE_E9_ALLOWLIST
# Enable E10 for every authenticated player -- separate gate:
./scripts/release/set-e9-rollout.ps1 enable-authenticated -LayoutFile ./deploy/release-layout.production.json -Execute -OwnerGate GO_ENABLE_E10_GLOBAL_ACCESS
```

The helper accepts no arbitrary key/value input. It locks the protected file,
creates a governed checksum-recorded backup, changes only the five managed E9
keys (the four fixed enum/boolean keys plus `E9_ROLLOUT_ALLOWLIST`), writes a
same-filesystem temporary file, atomically replaces the original, preserves
owner/group/mode, and appends a sanitized audit record under the release
staging directory. Mutations recreate only `app` and `scheduler` through the
canonical release Compose file and restart nginx so the persisted settings
reach both runtime services.

On failure, `enable-admin-only` attempts the disabled state before returning
failure (unchanged, pre-existing behavior). `enable-allowlist` and
`enable-authenticated` instead restore the **exact pre-operation rollout
state** from that operation's own
governed backup (via the helper's `rollback` operation) — never a
hard-coded target — because the pre-Phase-2 state is `admin_only`, and
silently dropping to fully disabled on a failed allowlist enablement would be
an unrelated service regression for existing admins.

## Allowlist identity format

`E9_ROLLOUT_ALLOWLIST` entries are **canonical user IDs** (`users.id`, the
database primary key) — decimal positive integers matching `^[1-9][0-9]*$`
only: no leading zero, no sign, no decimal point, and **not** usernames or
email addresses. `-AllowlistIds` takes a comma-separated list of these IDs;
it is validated locally (format, non-empty, no duplicates) before any remote
connection is opened, and the remote helper re-validates independently as
defense in depth. There is no username-matching fallback and none should be
added — resolve any intended usernames to their canonical IDs before calling
this tool.

## Owner gates

- `GO_DEPLOY` — `enable-admin-only`, `disable`, `rollback`. Authorizes
  re-affirming or disabling the existing admin-only rollout.
- `GO_ENABLE_E9_ALLOWLIST` — `enable-allowlist` only. A deliberately separate
  gate: enabling the allowlist changes which real, non-admin end users are
  exposed to E9 on the *same* running image, which is a materially different
  action from deploying a version. Never treat `GO_DEPLOY` as authorizing
  this operation, and never treat `GO_ENABLE_E9_ALLOWLIST` as authorizing a
  deploy.

- `GO_ENABLE_E10_GLOBAL_ACCESS` — `enable-authenticated` only. This exposes
  E10 to every player whose server-side session resolves both canonical user
  ID and username. It does not make Adventure anonymous, and implementation
  authorization alone does not authorize this Production operation.

Public-anonymous, percentage-based, and arbitrary flag-set configurations
remain unsupported by this tool. The only scopes are `admin_only`,
`named_allowlist`, and `authenticated`; unknown values fail closed.
