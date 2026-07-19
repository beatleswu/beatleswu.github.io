# E9-ADMIN-GATE1A governed admin-only rollout

Final status: `E9_ADMIN_ONLY_ACCEPTED_WITH_NON_ADMIN_EVIDENCE_GAP`
Date: 2026-07-19

## Governed operation

- Canonical tool: `scripts/release/set-e9-rollout.ps1`
- Exact command: `powershell -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\release\\set-e9-rollout.ps1 -Operation enable-admin-only -LayoutFile .\\deploy\\release-layout.production.json -Execute -OwnerGate GO_DEPLOY`
- Owner gate: `GO_DEPLOY`, bounded to this admin-only rollout
- Mutation executed: exactly once
- New governed backup: `20260719-052125-752f92b05649`
- Backup SHA-256: `752f92b0564974e91a1cf26c3f9245a53333dddd37535519810f10474e4bbd6e`
- Config SHA after mutation: `530613e4fa8e2c500516f45c5ac2abcb00cc995f9083fa65a7602e2d54c63259`

## Configuration

The canonical helper requires its global gate to be true as the master switch;
the `admin_only` scope keeps public rollout disabled. Named allowlist and cohort
rollout are not supported by this helper and remained inactive.

| Field | Before | After |
| --- | --- | --- |
| Global gate | false | true |
| Admin gate | false | true |
| Scope | admin_only | admin_only |
| Component flags | six-flag preset | same six-flag preset |
| Public rollout | disabled by scope | disabled by scope |
| Named allowlist/cohort | inactive | inactive |

Runtime status after mutation reported `state=admin_only`, `admin=true`,
`global=true`, and the complete six-component preset. App, scheduler, and nginx
recreation completed; the helper reported `running|healthy`, `running`,
`running`, and healthz `200` on attempt 2. Container IDs were not emitted by the
setter result and are therefore not reproduced here.

## Endpoint and browser acceptance

Three separated public samples after mutation returned:

| Sample | `/healthz` | `/` | `/login` |
| --- | --- | --- | --- |
| 1 | 200 | 200 | 200 |
| 2 | 200 | 200 | 200 |
| 3 | 200 | 200 | 200 |

### Admin (`beatles`)

The existing approved authenticated session reported `is_admin=true`,
`eligible=true`, `reason=admin_entitled`, `kill_switch=false`, and all six
effective flags true. The E9 page rendered five component roots (`top_hud`,
`left_nav`, `world_stage`, `right_cards`, `bottom_dock`) with non-zero bounds;
the Legacy adventure map had a zero-sized root. Navigation away/back and a
full refresh retained the same E9 ownership and root count. A clean browser tab
reported no console errors. Logout returned to `/login?from=logout`.

Re-login was not attempted because credentials were not entered or exposed in
this acceptance run.

Result: positive admin enablement, handoff, navigation, refresh, exclusivity,
and logout PASS; re-login NOT TESTED.

### Unauthenticated

After logout, a clean public tab showed no E9 component root and no E9 visible
content. The public landing/login flow remained available. No feature flags were
overridden client-side.

Result: PASS.

### Non-admin

No approved non-admin account was available. No account was created or changed.

Result: `NON_ADMIN_ACCEPTANCE_ACCOUNT_UNAVAILABLE`.

## Safety and rollback

- Image/source: unchanged from the approved baseline
- Application deployment/rebuild: none
- Shadow: unchanged
- Database/SGF/questions/player state: unchanged
- Event-store injection or mutation: none
- Rollback target: exact governed backup above, available for canonical rollback
- Health/endpoint failure: none observed
- Public/global rollout: not enabled; scope remains `admin_only`

## Decision

The admin-only gate is Production-enabled and positively accepted for the
available admin session. Full acceptance is withheld solely because the
non-admin account and re-login evidence are unavailable. Continue with the
remaining E9-ADMIN-GATE1A evidence gap before starting lifecycle hardening or
any broader rollout.
