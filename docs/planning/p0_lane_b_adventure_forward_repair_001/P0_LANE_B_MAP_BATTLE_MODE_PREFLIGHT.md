# P0 Lane B — Map Battle Mode Preflight

Task: `GO_ODYSSEY_P0_LANE_B_ADVENTURE_FORWARD_REPAIR_001`

## Mode authority

| Field | Result |
|---|---|
| `CURRENT_PRODUCTION_MODE` | `admin` (Owner-provided Production observation) |
| `SUPPORTED_VALUES` | `off`, `dark`, `admin`, `allowlist`, `percentage`, `global` |
| `TARGET_MODE` | `global` |
| `TARGET_MODE_SEMANTICS` | Any authenticated user admitted; anonymous requests remain blocked at `login_required`; no admin privilege is granted |

The source default remains `off`. The observed Production value `admin` is not
inferred from that default; it is the incident baseline supplied for this task.

## Admission proof

`global` is handled by `map_battle_runtime.mode_eligible()` and returns true
without an admin claim. The attempt/answer routes still require an authenticated
session and the server owns question, battle, nonce, correctness, and
progression facts.

Permanent tests:

- authenticated non-admin with `global`: accepted and can create an attempt;
- authenticated admin with `global`: accepted even when the session admin flag
  is false, proving session privilege claims are not the authority;
- `admin` with DB non-admin: rejected with `map_battle_mode_not_eligible`;
- `admin` with DB admin: accepted;
- anonymous attempt: `401` with canonical `未登入`, and no battle row is created;
- `off` and invalid values: `503 map_battle_v1_disabled`.

The synthetic end-to-end case also exercises `global` with a non-admin:

```text
authenticated request
 -> /api/adventure/map-battles/v1/attempts
 -> server-issued attempt and nonce
 -> /api/adventure/map-battles/v1/answers
 -> server CORRECT verdict
 -> mbv1:<submission_id> review evidence
 -> FIRST_PASS_ONLY progression applied
 -> exact replay returns duplicate
```

World Map same-page entry and refresh/re-entry both route through the client
Adventure entry functions recorded in `P0_LANE_B_ADVENTURE_CONTEXT_FIX.md`;
the server handshake tested above is the progression-bearing boundary used by
Continue Adventure.

## Configuration path

```text
/opt/go-odyssey/.env
  E10_MAP_BATTLE_V1_MODE=global
      ↓ --env-file
docker-compose.release.yml app.environment
  E10_MAP_BATTLE_V1_MODE: ${E10_MAP_BATTLE_V1_MODE:-off}
      ↓ container process environment
map_battle_persistence.get_map_battle_v1_mode(os.environ)
      ↓ each Map Battle V1 request
app._map_battle_require_enabled()
```

Evidence:

- `deploy/release-layout.production.json:17` identifies the governed
  Production env path `/opt/go-odyssey/.env`.
- `docker-compose.release.yml:70` injects the key into the `app` service.
- `map_battle_persistence.py:72-77` reads and validates it.
- `scripts/release/deploy-release-image.ps1:1538` uses the Production env file;
  its app recreation command at `:1641` uses
  `up -d --no-build --no-deps --force-recreate`.

There is no dedicated Map Battle setter in this lane and no Production command
was executed. An Owner-approved config operation must update the governed env
file, validate Compose interpolation, recreate the app container, and verify
the runtime environment and health before exposure.

## Exact preflight answers

```text
CONFIG_AUTHORITY=/opt/go-odyssey/.env:E10_MAP_BATTLE_V1_MODE -> docker-compose.release.yml app.environment -> get_map_battle_v1_mode(os.environ)
CURRENT_VALUE=admin
TARGET_VALUE=global

PROCESS_ENV_RELOAD_REQUIRED=YES
SERVICE_RESTART_REQUIRED=YES
CONTAINER_RESTART_REQUIRED=YES
CONTAINER_RECREATE_REQUIRED=YES
APP_IMAGE_REBUILD_REQUIRED=NO
STATIC_PROMOTION_REQUIRED=NO
FULL_COORDINATED_DEPLOY_REQUIRED=NO

CAN_D1_BE_CHANGED_WITHOUT_APP_IMAGE_REBUILD=YES
CAN_D1_BE_CHANGED_WITHOUT_FULL_COORDINATED_DEPLOY=YES
```

`restart` alone cannot change an already-created container's injected
environment; the governed `--force-recreate` is the required safe operation.
No image rebuild is needed because the application already supports `global`.

## D1/D2 classification

```text
D1_CONFIG_FIX=config-only + process reload/container recreate
D2_CODE_HOTFIX=static-only
CAN_A_AND_B_SHARE_ONE_STATIC_PROMOTION=YES, if Coordinator chooses one governed static window; D1 remains an independent env/recreate action
```

The D2 code is in `index.html` and has no `app.py` or DB dependency. A static
promotion can carry it without changing Commerce, Map Battle server authority,
or historical data. This report does not authorize either promotion or config
change.
