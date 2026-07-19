# E9-ADMIN-ACCEPT1 Production acceptance

Status: `E9_ADMIN_ACCEPTANCE_PARTIAL`  
Date: 2026-07-19  
Repository baseline: `74bfc72f6f0ba72ec570c8556b69422fc6b731fe`

## Scope and safety

This was a read-only browser acceptance. The existing `beatles` session was
used only for GET inspection and then logged out. No answer, battle, reward,
profile, progress, XP, coin, quota, SRS, Adventure, database, SGF, question,
feature-flag, container, or deployment mutation was performed. Passwords,
cookies, tokens, session identifiers, and full API payloads are not recorded.

## Production baseline

| Check | Result | Evidence |
| --- | --- | --- |
| `/healthz` | PASS | Public response body `{"ok":true}` |
| `/` | PASS | Public page rendered |
| `/login` | PASS | Logged-out login page rendered after logout |
| App/scheduler/nginx/Postgres | NOT TESTED in this browser-only pass | Existing canonical read-only baseline remains owner-provided |
| Source/image | NOT TESTED independently | Owner-provided baseline: source `0951c9a33ec287c57f21906c2dbcd9d7fd5ff314`, image `sha256:f719687bd0bd2269ac22dacf68dcfdbe85d9d56dc8314826c867e6b2445814d8` |
| Public versions | PASS | SW `v196-e9-adventure-cta-activation-fix`; i18n `20260710a`; E9 asset identity `e9-c3-navigation` |

## Account evidence

| Role | Result | Evidence |
| --- | --- | --- |
| Admin (`beatles`) | PASS for identity, BLOCKED for E9 enablement | `/api/auth/me` reported `is_admin=true`, but `eligible=false`, `reason=global_disabled`, and all effective E9 flags false |
| Non-admin | BLOCKED | No existing approved non-admin account was available; no role change or account creation was attempted |

## Acceptance matrix

| Journey | Unauthenticated | Admin | Non-admin |
| --- | --- | --- | --- |
| Initial load | PASS | PASS (Legacy while gates disabled) | BLOCKED |
| Adventure entry | PASS (redirects to login; no E9 mount) | PASS (Legacy shell observed) | BLOCKED |
| Auth handoff | N/A | FAIL for required E9 enablement; gate is globally disabled | BLOCKED |
| E9 enabled | NO | NO (`global_disabled`) | NOT TESTED |
| Legacy visible | PASS | PASS | NOT TESTED |
| Refresh | PASS on logged-out path | NOT TESTED after authenticated E9 handoff | NOT TESTED |
| Back/forward | NOT TESTED | NOT TESTED | NOT TESTED |
| Logout | N/A | PASS: existing session ended and login page rendered | NOT TESTED |
| Re-login | N/A | NOT TESTED; would require credentials re-entry | NOT TESTED |
| Fatal console error | PASS: no console errors observed in bounded logs | PASS: no errors observed before logout | NOT TESTED |
| Duplicate Shell | PASS: E9 root count 0 | PASS: E9 root count 0 while globally disabled | NOT TESTED |
| Player mutation | PASS | PASS | PASS (no account/session used) |

## Unauthenticated journey

The logged-out page rendered the Guild Reception login shell. `/curriculum`
redirected to `/login`; no E9 root was present (`e9Count=0`, `e9Visible=false`).
No fatal console errors were observed in the bounded browser log sample.

Result: `UNAUTHENTICATED_LEGACY_ACCEPTED`.

## Admin journey

The pre-logout authenticated `beatles` session reported `is_admin=true`, but
the server decision was fail-closed because the global rollout gate was off:
`eligible=false`, `reason=global_disabled`, and all six effective flags were
false. The home page therefore showed the Legacy Adventure shell and no visible
E9 root. This proves the gate is not accidentally granting E9, but it does not
prove the positive admin journey because this Sprint is not authorized to turn
the gate on.

Logout completed normally and returned to the login page. Same-browser re-login
and positive E9 handoff remain untested because no credential entry was
authorized or available in the existing session.

Result: `ADMIN_E9_ACCEPTED` is **not claimed**; positive admin acceptance is
`BLOCKED` by the disabled server gate.

## Non-admin journey

No approved non-admin account was available. No account was created, promoted,
or modified. The required non-admin acceptance is therefore `BLOCKED` with
classification `NON_ADMIN_ACCEPTANCE_ACCOUNT_UNAVAILABLE`.

## Version, cache, network, and console evidence

Public SW, i18n, and E9 asset identities matched the canonical baseline. The
bounded console sample contained no errors; only counts and endpoint-level
observations are retained. No headers, cookies, tokens, profile payloads, or
personal data were stored. A complete authenticated cache-convergence matrix
was not possible without the missing positive admin and non-admin journeys.

## Gaps and next Sprint

The admin-only gate exists and fails closed, but positive admin enablement and
non-admin protection are not both Production-accepted. Update the gap register
and continue with **`E9-ADMIN-ACCEPT1`** using an owner-approved environment in
which the already-governed admin gate is enabled and an approved non-admin
account is available. Do not proceed to lifecycle hardening or rollout
expansion. No runtime fix is indicated by this acceptance pass.
