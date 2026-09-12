# EQ-F Post-Merge Release Runbook Preflight — Shop / Equipment Flag Propagation

Status: **R3 corrective implemented and tested, 2026-09-13.** Sections 1-8
below are the original R2 read-only forensic record and are preserved
unedited as history. Section 9 records what R3 built on top of that
forensic evidence. This document is a runbook correction, not an
authorization. It grants none of GO_MERGE, GO_DEPLOY, GO_EQUIPMENT_ENABLE,
or GO_PRODUCTION_DB_MIGRATION — none of those gates were consumed by
building or testing the R3 corrective, and none is consumed by this update.

## 1. Actual flag consumers (source-verified, not assumed)

| Flag | Read by | Evidence |
|---|---|---|
| `CANONICAL_COIN_SHOP_PURCHASE_ENABLED` | **app only** | `app.py:23601-23602` — `_canonical_coin_shop_purchase_enabled()` calls `_env_flag_enabled(CANONICAL_COIN_SHOP_PURCHASE_FLAG, default=False)`. `scheduler.py` has zero references to this name. |
| `EQUIPMENT_CANONICAL_LOADOUT_ENABLED` | **app only** | `app.py:23614-23615` — `_equipment_canonical_loadout_enabled()`, same helper. `scheduler.py` has zero references to this name. |

**Correction to any prior assumption:** neither flag is consumed by
`scheduler.py`. The scheduler process does not need either variable at
runtime. `_env_flag_enabled()` (`app.py:30686`) reads `os.environ.get(name)`
fresh on each call — there is no cached config object and no separate
startup-vs-request-time distinction beyond that.

## 2. Production effective values (read-only, freshly verified 2026-09-13)

| Process/container | Shop effective | Equipment effective | Evidence method |
|---|---|---|---|
| `go-odyssey-app` | `true` | `false` | `docker exec go-odyssey-app env \| grep -E '^CANONICAL_COIN_SHOP_PURCHASE_ENABLED=\|^EQUIPMENT_CANONICAL_LOADOUT_ENABLED='` |
| `go-odyssey-scheduler` | `true` | `false` | same, against the scheduler container (value present in the container's environment even though the scheduler process never reads it — see §1) |

Both containers are running image `sha256:` for source commit
`657d5b368541f593b7bfb16008512de552b5caa2` (`APP_GIT_SHA`, confirmed live).

## 3. Exact source of each value

Checked, in order, every plausible source named in the forensic task:

- `docker-compose.prod.yml` (repo-tracked): **does not reference either flag**
  in the `app` or `scheduler` service `environment:` blocks (both fully read
  and grepped). No `env_file:` directive exists in this file at all.
- `docker-compose.release.yml` (the file `deploy-release-image.ps1` actually
  uses): **does not reference either flag** (grepped directly on the
  production host's copy).
- `docker-compose.release.healthcheck.override.yml`: **does not reference
  either flag**.
- Production `.env` (`/opt/go-odyssey/.env`): **zero matches** for either
  flag name (narrow, count-only check; file otherwise untouched and
  uninspected).
- `docker-compose.shop-reopen.override.yml` — **found on the production host
  only**, at `/opt/go-odyssey/docker-compose.shop-reopen.override.yml`. This
  file is the sole, positive, explicit source of both values:

  ```
  services:
    app:
      environment:
        CANONICAL_COIN_SHOP_PURCHASE_ENABLED: "true"
        EQUIPMENT_CANONICAL_LOADOUT_ENABLED: "false"
    scheduler:
      environment:
        CANONICAL_COIN_SHOP_PURCHASE_ENABLED: "true"
        EQUIPMENT_CANONICAL_LOADOUT_ENABLED: "false"
  ```

  **This file is not tracked in git.** It does not exist in the working
  tree, in `origin/master`, or in the exact deployed commit
  (`657d5b368541f593b7bfb16008512de552b5caa2`)'s tree. `docker compose ls`
  on the host confirms it as one of the four active config files for the
  running `go-odyssey` project
  (`docker-compose.release.yml`,
  `docker-compose.release.healthcheck.override.yml`,
  `docker-compose.shop-reopen.override.yml`,
  `docker-compose.prod.yml`) — meaning someone ran a `docker compose -f ...`
  invocation that explicitly included it when these containers were last
  created, outside of the reviewed automation below.

| Flag | Source of value | Location | Injection step | Target process | Timing | Default if absent |
|---|---|---|---|---|---|---|
| `CANONICAL_COIN_SHOP_PURCHASE_ENABLED` | **Explicit host-side compose override, untracked** | `/opt/go-odyssey/docker-compose.shop-reopen.override.yml` | Applied at container creation via an ad hoc `docker compose -f ... -f docker-compose.shop-reopen.override.yml up -d` (not part of `deploy-release-image.ps1`) | app (consumed); scheduler (present, unused) | startup (container env, read per-request by the app) | `false` (code default in `_env_flag_enabled`) |
| `EQUIPMENT_CANONICAL_LOADOUT_ENABLED` | Same file, same mechanism | Same | Same | app (consumed); scheduler (present, unused) | startup | `false` (code default — identical to the required value) |

## 4. Default vs. explicit propagation — hard requirement

- `CANONICAL_COIN_SHOP_PURCHASE_ENABLED=true` is **EXPLICITLY_INJECTED**, with
  positive provenance: the untracked host override file, confirmed present
  and confirmed to be part of the live compose project's active config-file
  set. It is **not** an application default — the code default is `false`,
  the opposite of the required state. This satisfies "SHOP=true must have
  positive provenance" for the *current* running containers only.
- `EQUIPMENT_CANONICAL_LOADOUT_ENABLED=false` is also **EXPLICITLY_INJECTED**
  by the same file today, but happens to equal `_env_flag_enabled`'s
  **APPLICATION_DEFAULT** as well. Both sources agree, so no ambiguity for
  Equipment specifically.

## 5. Recreate / deploy preservation — proven, not merely unproven

Traced `scripts/release/deploy-coordinated-release.ps1` →
`scripts/release/deploy-release-image.ps1` (the coordinated script's own
`$deployAppScript` child call) → its actual `docker compose` invocations
(lines 1589 and 1625, the `--force-recreate` steps for `app` and
`scheduler`):

```
docker compose -p <project> --env-file <production_env_path> \
  -f docker-compose.release.yml \
  -f <per-release healthcheck override> \
  up -d --no-build --no-deps --force-recreate <service>
```

This is the **exact, complete `-f` file list** the standard, reviewed release
path uses. It does **not** include `docker-compose.shop-reopen.override.yml`,
and it does not include `docker-compose.prod.yml` either. `--env-file` only
drives `${VAR}` substitution inside the compose YAML text — it does not
forward arbitrary host/`.env` variables into a container unless the compose
file references them by name, and neither `docker-compose.release.yml` nor
its healthcheck override references either flag.

**Conclusion: the next `--force-recreate` run of `deploy-release-image.ps1`
(directly, or via `deploy-coordinated-release.ps1`) will silently drop
`docker-compose.shop-reopen.override.yml` and both flags will fall through to
their code defaults.**

  SHOP_VALUE_AFTER_RECREATE_PROVABLE = **NO** — proven, not merely unproven:
    the exact command line was read, and it demonstrably omits the only file
    that sets Shop to `true`. The value would revert to `false`
    (`SHOP_PURCHASE_DISABLED`), silently, with no error and no owner action.
  EQUIPMENT_VALUE_AFTER_RECREATE_PROVABLE = YES — for the narrower, safe
    reason that Equipment's required value (`false`) equals its code default;
    dropping the override cannot accidentally enable it.

## 6. Future Equipment-enable control path

`EQUIPMENT_ENABLE_CONTROL_PATH_STATUS = CONTROL_PATH_NOT_FOUND`

No script in `scripts/release/` references either flag name. The only
existing mechanism that sets `EQUIPMENT_CANONICAL_LOADOUT_ENABLED` at all is
the same untracked `docker-compose.shop-reopen.override.yml` that also
controls Shop — editing that single file to flip Equipment to `true` would
necessarily go through the identical unreviewed, unversioned path already
shown to not survive a coordinated recreate, and offers no isolation from the
Shop value (they live in the same file, same services, same override). There
is no existing, approved, isolated control surface for a future
`GO_EQUIPMENT_ENABLE` gate. This is a real gap, not merely an unexercised
feature — no `.env`, ssh, sed, or compose mutation was performed to test or
work around it.

`scripts/release/commerce_production_readiness_preflight.py` was checked and
is **not** a control path: it is a read-only, non-mutating source/schema
*auditor* (its own docstring: "It never creates a table, changes a row,
commits, rolls back, enables a feature..."). It statically scans source for
gate-name references; it does not read or set the Production runtime value.

## 7. Release safety classification

`BLOCKED_EQ_F_SHOP_FLAG_RECREATE_PRESERVATION_UNPROVEN`

Criterion-by-criterion:
  1. Actual consumers known — yes (§1).
  2. Shop=true has an explicit authoritative source — yes, but only via an
     untracked, unreviewed host file (§3-4).
  3. Equipment=false has an explicit/proven source — yes (§3-4).
  4. Coordinated deploy/recreate preserves required values — **no, proven
     false for Shop** (§5).
  5. Shop cannot silently fall back false on recreate — **false; it can and,
     on the current script path, will** (§5).
  6. Future Equipment enablement isolated from Shop, or the precise missing
     control identified — the precise gap is identified (§6): no isolated
     control exists; both flags share one unreviewed override file.

This is a genuine, evidenced blocker on the *release automation*, not on any
application code, and not something this task is authorized to fix (no
script edit, no compose edit, no container recreate was performed or is
proposed here).

## 8. Smallest corrective (for a future, separate, explicitly authorized task)

Not executed here — recorded only as the shape of the fix this evidence
points to, for whoever receives the next explicit gate:
  - Track `docker-compose.shop-reopen.override.yml` (or fold its two lines
    into `docker-compose.release.yml` directly) in git, so it has review
    history and a canonical source.
  - Add it to `deploy-release-image.ps1`'s `-f` file list (both the `config`
    calls and the two `--force-recreate` calls) so a coordinated release
    preserves it automatically.
  - Consider splitting Shop's override from Equipment's into two named files
    (or two independently toggleable keys under one reviewed file) so a
    future `GO_EQUIPMENT_ENABLE` gate can flip Equipment without touching the
    Shop line at all.
  - Remove the `scheduler` block from the override (or confirm it is
    harmless dead weight) since `scheduler.py` never reads either flag.

None of the above was implemented by the R2 task. GO_MERGE, GO_DEPLOY,
GO_EQUIPMENT_ENABLE, and GO_PRODUCTION_DB_MIGRATION remained ungranted at
the end of R2.

## 9. R3 corrective — implemented mechanism (2026-09-13)

R3 built exactly the shape recorded in §8, on top of the EQ-F product
candidate at `e3df397cee89ac5446d5b84eee8aac9b151ed600`, and nowhere else:
no equipment domain service, registry, asset, renderer, Shop pricing logic,
first-clear/backfill logic, `app.py` product logic, or i18n content was
touched (`EQ_F_PRODUCT_BYTES_CHANGED=NO`, verified by diff against that
exact commit for every such path).

### 9.1 Tracked Shop-preservation authority

`docker-compose.release.product-flags.yml` (repo root, tracked, no secrets)
is now the sole, versioned authority for both flags' normal-deploy values:

```
services:
  app:
    environment:
      CANONICAL_COIN_SHOP_PURCHASE_ENABLED: "true"
      EQUIPMENT_CANONICAL_LOADOUT_ENABLED: "false"
  scheduler:
    environment:
      CANONICAL_COIN_SHOP_PURCHASE_ENABLED: "true"
      EQUIPMENT_CANONICAL_LOADOUT_ENABLED: "false"
```

`SHOP_CONSUMERS = app` and `EQUIPMENT_CONSUMERS = app` remain the correct,
source-verified consumer classification from §1 — this file's `scheduler:`
block is intentional harmless parity with the historical override it
replaces, not a claim that the scheduler reads either key.

### 9.2 Governed deploy path now mechanically includes it

`scripts/release/deploy-release-image.ps1` was edited (the only script
touched) to resolve, upload, and reference
`docker-compose.release.product-flags.yml` unconditionally in all four of
its governed compose invocations: both pre-flight `config --services` /
`config --images` checks and both `--force-recreate` calls (`app` and
`scheduler`). `scripts/release/deploy-coordinated-release.ps1` calls this
script as its own app-deployment child step, so the fix applies transitively
through the full coordinated path with no separate edit there.
`docs/deployment` and the two pinned tests that asserted the previous exact
command text / upload count
(`tests/deployment/test_release_tooling.py`,
`tests/deployment/test_release_upload_bounded_scp.py`) were updated to the
new, longer, intentional command text and count — not loosened or skipped.

`GOVERNED_DEPLOY_INCLUDES_SHOP_AUTHORITY = YES`, and it is a **mechanical**
property (source-verified: every `--force-recreate` and `config` line in the
script contains the new `-f` argument, unconditionally) rather than a
documentation promise. A future operator cannot omit it by forgetting a
manual flag.

### 9.3 Isolated, Owner-gated Equipment-enable control

`docker-compose.release.equipment-enable.override.yml` (repo root, tracked)
changes exactly one key, for exactly one service:

```
services:
  app:
    environment:
      EQUIPMENT_CANONICAL_LOADOUT_ENABLED: "true"
```

It never mentions `CANONICAL_COIN_SHOP_PURCHASE_ENABLED` and has no
`scheduler:` block (both source-verified by
`tests/deployment/test_eq_f_r3_release_flag_propagation.py`). Because
Compose merges the `environment` map per key, layering this file on top of
`docker-compose.release.product-flags.yml` changes only Equipment; Shop's
`true` value from the earlier file is untouched — proven with a real local
`docker compose config` resolution, not just YAML-merge reasoning by hand.

`scripts/release/set-equipment-enable-state.ps1` (new script) is the sole
operator entry point:

- `-State Enable -OwnerGate GO_EQUIPMENT_ENABLE -Execute` uploads and layers
  the enable override, force-recreates **only** the `app` service (the only
  real consumer), reads back exactly
  `CANONICAL_COIN_SHOP_PURCHASE_ENABLED` and
  `EQUIPMENT_CANONICAL_LOADOUT_ENABLED` from the app container (never a full
  `env`/`printenv` dump), and runs one bounded health check against the
  release layout's `health_url`.
- `-State Disable -OwnerGate GO_ROLLBACK -Execute` (Equipment-only rollback)
  simply omits the enable override from the same recreate, so the baseline
  file's `false` applies again — Shop is never touched by either direction.
- Without `-Execute`, both states are a pure, read-only dry run: it resolves
  the release layout and prints the exact plan and literal `docker compose`
  command as JSON, then returns — before any SSH, Docker, or host contact.
  Wrong or missing `-OwnerGate` (for either state, including passing the
  *other* state's gate) fails closed via the same `Assert-OwnerGate` every
  other canonical release script uses, before anything is touched.
- It reuses the repository's existing bounded SSH/SCP primitives
  (`Invoke-BoundedSshCommand`, `Invoke-BoundedScpUpload`,
  `Assert-OwnerGate`) from `ReleaseTooling.psm1` rather than inventing a new
  ad hoc ssh/sed/compose-editing mechanism.

`TRACKED_SHOP_AUTHORITY_PATH = docker-compose.release.product-flags.yml`
`TRACKED_EQUIPMENT_ENABLE_AUTHORITY_PATH = docker-compose.release.equipment-enable.override.yml`
`EQUIPMENT_CONTROL_SCRIPT_PATH = scripts/release/set-equipment-enable-state.ps1`

### 9.4 The historical host-only override is untouched

Per the R3 task's explicit scope boundary, R3 did not read, edit, or delete
`/opt/go-odyssey/docker-compose.shop-reopen.override.yml`, did not SSH to
Production, and did not recreate any container. `HOST_OVERRIDE_MUTATION =
NO`. Reconciling the live host (removing its reliance on the untracked file
now that a tracked replacement exists) is a separate, later, explicitly
authorized deploy-time procedure — not part of this corrective.

### 9.5 Effective states (all proven via real local `docker compose config`
resolution and/or the control script's dry-run, never by touching Production)

| State | Shop (app) | Equipment (app) | Equipment (scheduler) |
|---|---|---|---|
| NORMAL_DEPLOY (product-flags file only) | `true` | `false` | `false` |
| AFTER_GO_EQUIPMENT_ENABLE (+ enable override) | `true` | `true` | `false` |
| EQUIPMENT_ROLLBACK (enable override removed) | `true` | `false` | `false` |

### 9.6 Updated release safety classification

`PASS_EQ_F_RELEASE_FLAG_PROPAGATION_AND_ISOLATED_EQUIPMENT_CONTROL_CORRECTIVE_READY_FOR_INDEPENDENT_REVIEW`

Re-scoring §7's six criteria against the R3 mechanism:
  1. Actual consumers known — yes, unchanged (§1).
  2. Shop=true has an explicit authoritative source — yes, now a **tracked,
     reviewed** file (§9.1), not an untracked host file.
  3. Equipment=false has an explicit/proven source — yes, same tracked file.
  4. Coordinated deploy/recreate preserves required values — **yes**, proven
     by source-verifying every compose invocation in the governed script
     (§9.2), not merely asserted.
  5. Shop cannot silently fall back false on recreate — **true now**: the
     file that sets it is uploaded and referenced unconditionally by the
     same script that used to omit it.
  6. Future Equipment enablement is isolated from Shop — **yes**: a
     separate tracked file, a separate script, a separate Owner gate
     (`GO_EQUIPMENT_ENABLE` to turn on, `GO_ROLLBACK` to turn off), proven
     by real Compose resolution to never alter Shop's value.

This status is a readiness statement for independent review, not a
Production authorization. `GO_MERGE`, `GO_DEPLOY`, `GO_EQUIPMENT_ENABLE`,
and `GO_PRODUCTION_DB_MIGRATION` remain ungranted; nothing in R3 was ever
executed with `-Execute` against a real host, and Production's live
containers and the historical host-only override are exactly as R2 left
them.
