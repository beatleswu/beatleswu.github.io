# E9-ADMIN-ACCEPT2 closure addendum

Final status: `E9_ADMIN_ONLY_PRODUCTION_ACCEPTED`
Date: 2026-07-19

## Owner manual acceptance addendum

The project owner completed the remaining authenticated acceptance checks using
approved accounts. This document records only sanitized outcomes; no password,
cookie, token, session ID, CSRF value, or full API payload is retained.

### Admin (`beatles`)

- Initial login: PASS
- Refresh: PASS
- Logout: PASS
- Re-login: PASS
- E9 remained available after re-login
- Legacy Adventure remained hidden

### Non-admin (`test01`)

- Ordinary non-admin account confirmed
- Legacy Adventure displayed
- E9 not visible
- Admin-only boundary confirmed

## Final acceptance matrix

| State | Eligible | E9 visible | Legacy visible | Result |
| --- | --- | --- | --- | --- |
| Unauthenticated | false | no | login/Legacy | PASS |
| Admin first login | true | yes | no | PASS |
| Admin after refresh | true | yes | no | PASS |
| Admin after logout | false | no | login | PASS |
| Admin re-login | true | yes | no | PASS |
| Non-admin login | false | no | yes | PASS |

No E9/Legacy overlap, player mutation, database mutation, SGF/questions
mutation, flag drift, deployment, image rebuild, or Shadow change occurred.

## Closure decision

`E9_ADMIN_ONLY_PRODUCTION_ACCEPTED` is now the canonical status. The next
approved Sprint is `E9-BETA-LIFECYCLE1`, covering unmount, cleanup, stale async,
remount, and duplicate listener/timer/observer behavior. Named allowlist and
cohort rollout remain out of scope.
