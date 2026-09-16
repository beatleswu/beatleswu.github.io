# P0 Lane B — Production Enable Plan (Preflight Only)

This is a non-executing plan. It contains no Production credentials, no live
command result, and no authorization to mutate Production.

## D1 configuration change

Owner-approved desired change:

```text
/opt/go-odyssey/.env
E10_MAP_BATTLE_V1_MODE=admin
        ->
E10_MAP_BATTLE_V1_MODE=global
```

The governed release Compose file passes the value only to the `app` service.
The application reads the process environment through
`get_map_battle_v1_mode()` and validates unsupported values to `off`.

Required future sequence:

1. capture the current Production env/config fingerprint without exposing
   secrets;
2. update only `E10_MAP_BATTLE_V1_MODE` under the Owner enable gate;
3. run Compose interpolation/preflight with the Production env file;
4. recreate the app container with `--no-build --no-deps --force-recreate`;
5. verify the container environment resolves to `global` and health is green;
6. run authenticated admin, authenticated non-admin, and anonymous reachability
   checks;
7. retain a rollback copy of the one config key and restore/recreate if any
   health or access gate fails.

The release layout identifies `/opt/go-odyssey/.env` as
`production_env_path`. The release tooling's app recreation operation is the
governed mechanism; this task did not invoke it.

## Exact D1 preflight classification

```text
CONFIG_AUTHORITY=/opt/go-odyssey/.env:E10_MAP_BATTLE_V1_MODE
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

A plain restart of an existing container without recreating its Compose
environment is insufficient. `--force-recreate` is the exact safe boundary.

## D2 static corrective promotion

The D2 implementation is limited to `index.html`; no `app.py`, DB schema,
payment, reward, or server authority changes are present. Therefore:

```text
D2_CODE_HOTFIX=static-only
STATIC_PROMOTION_REQUIRED_FOR_D2=YES
APP_IMAGE_REBUILD_REQUIRED_FOR_D2=NO
```

The existing static release tooling should be used to package and verify the
new `index.html`; no `sw.js` change is needed for this corrective. The D1 env
change is orthogonal and may be executed in the same release window, but it is
not evidence of a successful static promotion.

## Rollback

- D1 rollback: restore `E10_MAP_BATTLE_V1_MODE=admin` in the governed env,
  recreate the app container, and re-run reachability checks. This returns the
  pre-hotfix admin-only exposure; it does not rewrite player data.
- D2 rollback: switch the governed static release back to the prior verified
  static generation. Commerce, ownership, SRS rows, Map Battle rows, and any
  server progression evidence remain untouched.

## Explicit non-actions

```text
PRODUCTION_CONFIG_MUTATION=NO
PRODUCTION_DB_WRITE=NO
HISTORICAL_DATA_TOUCHED=NO
DEPLOY=NO
MERGE=NO
```

No broad MBV1 retirement or Adventure progression-authority migration is part
of this plan.
