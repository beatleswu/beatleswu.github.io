# P0 A+B future Production hotfix plan

This document is a future Owner-gated order only. It is not a deployment
authorization and no step below was executed.

## Required order

1. Verify the exact canonical and Production baseline.
2. Promote the one governed A+B static package atomically.
3. Verify public static bytes and release provenance.
4. Change E10_MAP_BATTLE_V1_MODE=admin to global.
5. Force-recreate the app container through the governed mechanism.
6. Verify health, anonymous boundary, authenticated admin, and authenticated
   non-admin reachability.
7. Verify real non-admin Adventure: Continue Adventure -> correct answer ->
   progression increments.
8. Owner device UAT verifies the Zone4 cinematic visibly renders.
9. Only after future progression is fixed may Lane C historical population
   recovery be considered under its own separate gate.

The static step must use the exact package and manifest from
package-static-release.ps1 and deploy-static-release.ps1; no ad-hoc SSH or
live-static file copy is acceptable.

## Rollback

~~~text
STATIC_ROLLBACK=scripts/release/rollback-static-release.ps1 to an explicit prior verified generation
CONFIG_ROLLBACK=global -> admin, then governed app force-recreate
DB_ROLLBACK=not applicable to A+B; no A+B DB write exists
~~~

Static rollback must verify the target generation's manifest and public bytes.
Config rollback must repeat health and anonymous/admin/non-admin reachability
checks. No historical row, reward, SRS, or progression repair is part of this
hotfix.

## Owner gates

Required approvals remain separate: canonical/source gate, static promotion
gate, D1 configuration enable gate, Production health/access gate, and Owner
device UAT. Passing this candidate preflight does not merge or deploy it.

~~~text
MERGE=NO
DEPLOY=NO
PRODUCTION_CONFIG_MUTATION=NO
PRODUCTION_DB_MUTATION=NO
PRODUCTION_MUTATION=NO
~~~
