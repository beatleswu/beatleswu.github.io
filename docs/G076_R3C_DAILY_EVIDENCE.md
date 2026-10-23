# G076 R3-C Daily isolated evidence — 2026-10-23

Scope: `D:\go-odyssey-g076-r3-daily-codex-20261023`, branch
`g076-r3c-daily-codex`; starting HEAD
`0b358cc7e5987ffc335dd1b7088b4299b1585518`.

Status: **isolated Daily candidate tested; coordinator integration HOLD**.
No complete R3 or Production claim. Zero production writes. No push, PR, merge,
deploy, remote Git operation or other worktree mutation was performed.

## Changes and authority

- The actual standalone `daily_challenge.html` loads the Daily-only safe endpoint
  and unmodified shared client through a small namespaced adapter. It no longer
  fetches a solution-bearing today payload or performs local tree verdicts.
- The server owns the persistent user/date cursor, nonce, history, verdict and
  forced opponent replies. Only committed replies appear on the board. Retry
  freezes the same uncertain move; reload reconstructs committed history.
- `g076_daily_step_integration.py` extracts the actual base `dc_submit` D5B,
  XP, badge/streak and appearance effects. The terminal event, D5B envelope and
  every effect share one transaction. The cross-route date-unique row is acquired
  before effects. Failures roll back reservation, awards and terminal event.
- The current Daily route has no debit/refund or explicit quest-runtime event.
  No extra award is invented. One canonical review row remains available to
  existing review-log consumers. Additional quest event admission remains HOLD.
- Three flags default OFF; missing configuration/schema, unsupported questions,
  revoked rights, bad binding or unavailable authority fail closed. Preflight
  validates every reachable branch before the first move.
- Exact coordinator additions, old-route gate, safe today alias, assets,
  transaction/provider contracts and migration prerequisites are in
  `docs/G076_R3C_DAILY_APP_INTEGRATION.md`; they are NOT applied to app.py.

## Tests actually executed

```text
python -m pytest -q -p no:cacheprovider \
  tests/test_g076_daily_integration.py \
  tests/test_g076_nonmap_steps.py \
  tests/test_g076_nonmap_live_http.py
95 passed, 1 skipped in 24.29s

node tests/e2e/g076_daily_client.mjs
PASS, 15 checks

node tests/e2e/g076_daily_chrome.mjs
PASS, 21 checks
```

The pytest suite ran in a disposable cached image
`go-odyssey-app:g076r3a-local-smoke`, with its entrypoint replaced by Python/sh,
working directory `/workspace`, only THIS worktree mounted, and no application
startup. pytest 9.1.1 was installed into the workspace's temporary test directory;
Node 20.19.2 was installed only inside the disposable test container to run the
existing syntax test. Host Node was 24.16.0. Windows Chrome was 155.0.8059.39.

The one skip is the existing Windows-Chrome test inside the Linux container,
whose Windows executable path is unavailable. It is not relabelled PASS. The
separate namespaced native Chrome test executes the actual Daily page, its real
WGo Canvas, real authenticated HTTP, shared client and extracted production
Daily adapter against disposable SQLite. It includes black and white multistep,
forced opponent replies, reload, response loss after nonterminal and terminal
commits, exact retry, CSRF rejection, flag-OFF UI and actual XP/badge persistence.
No mocked browser transport supplies successful verdicts in this live test.
Its response-loss wrapper throws only AFTER the real HTTP response is received.

The Daily SQLite tests include real current `dc_submit` cross-route races,
exactly-once D5B/XP/badges, real seven-day streak appearance, concurrent terminal
retries, wrong-answer finality, effect/commit rollback and recovery, uid/date/token
and nonce/content binding, explicit correct/incorrect branches, terminal opponent
reply, unsupported trees, missing schema and existing admin date selection.
The fixture AST-loads only the named existing functions/constants from THIS
app.py, stripping route decorators and supplying fixture-only DB/auth boundaries;
it does not import application startup, read secrets, or contact any database.
The blueprint itself performs authentication, CSRF, origin and rights checks.
This is Flask integration evidence, not Production middleware qualification.

Earlier iterations are not final PASS evidence: one shared syntax test initially
failed because the container lacked Node; adding the test dependency resolved it.
An unsupported-root SGF fixture exposed a 503 instead of the intended 422; the
adapter now rejects that projection before context issuance, with no writes.
The initial physical-click browser harness needed the real board scrolled into
its viewport; the final harness uses actual mouse events on visible WGo points.

## Reproduction

On this Windows workspace, with Docker and Chrome available, create
`.g076-daily-tmp/docker-config` (empty, so Docker does not read account config).
Use this explicit mount only:

```powershell
$mount = 'type=bind,source=D:\go-odyssey-g076-r3-daily-codex-20261023,target=/workspace'
docker --config .g076-daily-tmp/docker-config run --rm --mount $mount --workdir /workspace --entrypoint python go-odyssey-app:g076r3a-local-smoke -m pip install --target /workspace/.g076-daily-tmp/python pytest==9.1.1
docker --config .g076-daily-tmp/docker-config run --rm --mount $mount --workdir /workspace --env PYTHONPATH=/workspace/.g076-daily-tmp/python:/workspace:/workspace/tests --env PYTHONDONTWRITEBYTECODE=1 --entrypoint sh go-odyssey-app:g076r3a-local-smoke -c 'apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends nodejs > /tmp/g076-daily-node-install.log && python -m pytest -q -p no:cacheprovider tests/test_g076_daily_integration.py tests/test_g076_nonmap_steps.py tests/test_g076_nonmap_live_http.py'
docker --config .g076-daily-tmp/docker-config run --rm --detach --name g076-r3c-daily-check --publish 127.0.0.1:5079:5079 --mount ($mount+',readonly') --workdir /workspace --env PYTHONPATH=/workspace/.g076-daily-tmp/python:/workspace:/workspace/tests --env PYTHONDONTWRITEBYTECODE=1 --entrypoint python go-odyssey-app:g076r3a-local-smoke tests/e2e/g076_daily_fixture_server.py
try {
    node tests/e2e/g076_daily_chrome.mjs
    if ($LASTEXITCODE -ne 0) { throw 'Daily Chrome failure' }
    node tests/e2e/g076_daily_client.mjs
    if ($LASTEXITCODE -ne 0) { throw 'Daily JS failure' }
} finally {
    docker --config .g076-daily-tmp/docker-config stop g076-r3c-daily-check
}
```

These containers contain only synthetic users, a disposable SQLite database and
fixture-only login/control endpoints. Never register fixture routes in app.py.
No Dockerfile or image manifest is changed. HTTP binds only 127.0.0.1:5079;
Chrome disables background network activity and resolves only loopback. Container
SQLite state disappears when each `--rm` fixture container stops.

## Explicit remaining limits

- app.py integration/asset registration and packaging: NOT_APPLIED / HOLD.
- PostgreSQL 16 run: NOT_EXECUTED (optional). PostgreSQL uses the existing qmark
  wrapper and user/session row locks, but SQLite tests do not qualify PG locking.
- Production schema/migrations, full middleware/rights requalification,
  all legacy exposure paths, deployment and Owner acceptance: NOT_EXECUTED.
- No new quest-runtime event authority was supplied. Its completion is not claimed.
- Unsupported questions remain unavailable; no substitute puzzle or fake award.
- Answer reveal / abandonment is unavailable until a server contract exists.
  Badge/appearance metadata is stored in the D5B envelope; the step receipt's
  existing allowlist exposes XP/id only. This page does not claim those effects
  from a client-side animation.

## Protected source verification

Before committing, `git diff --exit-code 0b358cc7e5987ffc335dd1b7088b4299b1585518 -- app.py index.html Dockerfile deploy/build-manifest.json g076_nonmap_steps.py js/game/g076_nonmap_step_client.js`
returned 0. `git diff --check` returned 0. Owner-provided untracked
`G076_R3_DAILY_CODEX_TASK.md` is preserved and excluded from this lane's commit.
Temporary dependencies, browser profiles and screenshots are excluded from Git.

## SHA256 source receipt

| File | SHA256 |
| --- | --- |
| daily_challenge.html | 68fb2a82989260264104ff88125d14e2bef9ef9f1b75c1d3d71e62e1998aca19 |
| g076_daily_step_integration.py | 7c62b9e5e48192f1e3a22dfcba7d060c7afdc234c3dde3d8ecb7ac084d41e970 |
| js/game/g076_daily_step_client.js | 7c1a51e90a8cb2fee3a887939a07780c14be10c112e60730e6ab648a2aa67fc4 |
| tests/g076_daily_fixture.py | 7f95047408d1fc5b6090fe186e10ad496ab2cad1a5ac59e5fbf5adb977aa0e0e |
| tests/test_g076_daily_integration.py | 12ee770731d89ea02c91aa0d3c92e14fabefde6f798b924b5fb3d5e15cb517fd |
| tests/e2e/g076_daily_chrome.mjs | cba8feb3e8e6de881362e44723f9bdca7e43f438fbe27fdd5f685b8ee7b4ddaa |
| tests/e2e/g076_daily_client.mjs | b3e1663503157cffe934739840b2bc0b849e75247e16e59972bfa729349176c5 |
| tests/e2e/g076_daily_fixture_server.py | fc58b002545c9fa118999a21570ece9c2667f2533d82c49caa1aa867c9b2775f |
| docs/G076_R3C_DAILY_APP_INTEGRATION.md | cadc9573322a1e91149656770c42d71de3affc9704dbe073a47d0343eaa62353 |
