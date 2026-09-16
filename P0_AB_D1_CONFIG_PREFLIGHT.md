# P0 A+B D1 configuration preflight

This is a reviewed, non-executing Production configuration plan. No
Production environment, container, or service was read or changed by this
task.

~~~text
CONFIG_AUTHORITY=/opt/go-odyssey/.env:E10_MAP_BATTLE_V1_MODE
CURRENT_PRODUCTION_VALUE=admin
TARGET_VALUE=global
PROCESS_ENV_RELOAD_REQUIRED=YES
SERVICE_RESTART_REQUIRED=YES
CONTAINER_RESTART_REQUIRED=YES
CONTAINER_RECREATE_REQUIRED=YES
APP_IMAGE_REBUILD_REQUIRED=NO
STATIC_PROMOTION_REQUIRED_FOR_D1=NO
FULL_COORDINATED_DEPLOY_REQUIRED=NO
~~~

The future governed sequence is:

1. capture a secret-free Production config fingerprint;
2. change only E10_MAP_BATTLE_V1_MODE from admin to global under the Owner
   enable gate;
3. validate Compose interpolation with the Production env file;
4. recreate only the app service using --no-build --no-deps --force-recreate;
5. verify global is in the new process environment and health is green;
6. verify anonymous, authenticated admin, and authenticated non-admin
   reachability;
7. retain the one-key rollback and restore/recreate if any gate fails.

A plain restart without Compose environment recreation is insufficient. D1 is
orthogonal to the static A+B promotion: it does not rebuild the image and is
not evidence of a successful static promotion.

~~~text
D1_ACTION_EXECUTED=NO
PRODUCTION_CONFIG_MUTATION=NO
CONFIG_ROLLBACK_READY=YES
CONFIG_ROLLBACK=global -> admin, then governed app force-recreate and health/access checks
~~~
