# E9 Stage C Admin-Only Rollout Package

This package defines the first Stage C rollout boundary. It is server-authoritative,
admin-only, and disabled by default. It does not enable E9 or change Production
configuration.

## Safe configuration

```text
E9_ROLLOUT_SCOPE=admin_only
E9_ROLLOUT_GLOBAL_ENABLED=false
E9_ROLLOUT_ADMIN_ENABLED=false
E9_ROLLOUT_ALLOWLIST=
E9_ROLLOUT_FLAGS=e9Shell,e9TopHud,e9LeftNav,e9RightCards,e9BottomDock,e9WorldStage
```

An eligible Stage C admin decision requires an authenticated session, an
authoritative `users.is_admin` value, `E9_ROLLOUT_GLOBAL_ENABLED=true`,
`E9_ROLLOUT_ADMIN_ENABLED=true`, valid configuration, and the `admin_only` scope.
The effective result enables all six E9 flags. Every other outcome returns all
flags false and keeps the Legacy shell.

The named-allowlist capability remains available as a separately selected
server scope, but this package rejects a non-empty allowlist in `admin_only`
scope. No named users are configured by this package.

## Kill switch and failure behavior

The global switch is authoritative and defaults off. Turning it off makes new
server decisions ineligible without a database change or frontend rebuild.
Malformed or missing configuration, failed identity lookup, unauthenticated
requests, and decision/API failures fail closed to Legacy. Client query
parameters and local storage are not eligibility inputs.

## Decision telemetry

Existing structured decision logging records only `eligible`, reason code,
effective flags, decision/config version, kill-switch state, request surface,
and a short irreversible user digest. It does not record email, username,
allowlist contents, tokens, secrets, or free-text PII. Operational counters
are derived from the existing decision/fallback logs; no second analytics
pipeline is introduced.

## Stage C operating package

Initial scope is admin-only with all six flags enabled for eligible admins.
Abort and immediately disable the global switch for critical fallback,
double-shell, duplicate-fetch/request-budget breach, identity/session leakage,
ordinary-user eligibility, provenance mismatch, or P0/P1 interaction errors.
Success requires a usable admin flow, unchanged Legacy behavior for ordinary
users, correct logout/session switching, normal request budgets, no shell
duplication or data leakage, and 24–48 hours without P0/P1 signals. Observation
is a later Owner-controlled stage; this implementation does not enable E9.
