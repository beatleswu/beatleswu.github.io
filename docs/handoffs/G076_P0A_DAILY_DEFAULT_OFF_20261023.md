# G076 P0-A Daily default-OFF compatibility — 2026-10-23

Status: IMPLEMENTED_UNCOMMITTED / BLOCKED_ENVIRONMENT for Python, real HTTP and Chrome acceptance. This is an exact dirty-overlay handoff for G MASTER review, not release clearance.

## Authority and identity

- Owner directive: 2026-10-23 P0-A, sole writer in `D:\go-odyssey-g076-p0-daily-20261023` for the named product paths, standalone additions and tests.
- Branch: `g076-p0-daily-default-off-20261023`.
- Actual and expected HEAD: `f414db82b5c1aa45f8b7086c1defb1bfe0f307eb`.
- HEAD tree: `13252e1c55aa0fda9b9766bc50afc3838f68f336`. This identifies the base commit, **not the modified overlay**.
- Initial `git status --short`: empty. Final index diff is empty (`git diff --cached --quiet`, exit 0); working files remain unstaged.
- `artifacts/g076-p0a/validation-01.json` records exact argv, exit/start errors, UTC timestamp and SHA256 of all 15 modified/new product and test files. Review those hashes with this diff; no new commit/Source identity is claimed.
- Historical f414 R3 671 PASS / 18 SKIP, ARM64 422 required PASS, and separate R4 `78d2534ef` / 106 PASS are owner-supplied context, not rerun results. None of those stages was reimplemented or adopted here.
- No index.html, shared judge/reward module, C/R4 worktree, flag configuration, production data, migration, merge, push or deployment was changed. No Oracle/live DB connection was made. G MASTER alone adopts into the Product candidate.

## Baseline evidence and environment blocker

`artifacts/g076-p0a/baseline-f414.json` was written before product edits. Static inspection on unmodified f414 shows `dailySteps.load()` GETs `/api/g076/daily/today`, whose existing dispatcher returns 503 `daily_steps_disabled_or_unconfigured` with all flags OFF. The existing Chrome test explicitly expected that blocked OFF state.

Baseline real HTTP/Chrome reproduction is **NOT_EXECUTED**. `python` is absent from PATH. Direct Python312 execution is access denied; the OCI venv cannot launch its protected Python312 base. A bounded attempt to copy that runtime also failed with access denied. Docker engine access is denied. No approval bypass or remote runtime was used.

The final exact targeted pytest launch via Node `spawnSync` reports **EPERM**, process exit `null` (process never started), not a failed pytest assertion. Shell launch diagnostics and Docker exit 1 are retained in the baseline description. The formal launch error and exact full test argv are in `validation-01.json` and `targeted-python.stderr.log`.

## Change and route assertions

1. New `g076_daily_capability.py` owns protocol selection from server environment only. All three flags OFF selects `legacy`; all ON selects `steps`; partial/unrecognized values select `hold`. Recognized false values are absent/empty, `0`, `false`, `off`; true values are `1`, `true`, `on` (case/whitespace normalized).
2. GET `/api/g076/daily/capability` requires a positive integer session user ID, returns 401 without it, 409 with `mode=hold` on partial configuration, or 200 with `mode=legacy|steps`. Every response has `Cache-Control: private, no-store` and `Vary: Cookie`. Query/body enable hints are unused. No schema or reward write occurs here.
3. The current page awaits this endpoint as the first operation in `window.onload`. It uses same-origin credentials, no-store, rejects redirects, and has an 8-second abort deadline. Valid `legacy` performs exactly one `location.replace('/daily_challenge_legacy.html')`; the restored file has no reverse redirect. Valid `steps` runs the original G076 initialization. HTTP/network/JSON/timeout/unknown-mode errors display an explicit blocked view before history, board loading or either Daily protocol starts. The initial board region is already hidden and has no initialized board.
4. New `daily_challenge_legacy.html` is byte-identical to commit `b39b35481de43ee5de6f3dc70e215d2cf291c56b`, blob `ad3773d4f1023415ec3c6bcb5a8f0b68ad1cdf4f`. SHA256: `f18b2024391dba99ddaf71412cd7971289b8876cc1d45cbdba256e8a95df26dd`. Its full SGF parser, actual move collection, signed attempt and legacy submit flow are preserved.
5. Existing POST `/api/daily-challenge/submit` still loads persisted D5B exact replay **before** new-admission checks. Changed payloads retain idempotency conflict behavior. New legacy submissions now require `daily_mode == legacy`; steps and partial modes return 409 before judging or effects. The original canonical SGF judge, token/user/date/revision checks, durable D5B receipt, daily uniqueness, XP and badge writers remain unchanged. Client `correct` stays diagnostic only.
6. Existing legacy GET `/api/daily-challenge/today` delegates to the secure board-only route in steps mode. Existing privacy-enforced today/history projection remains intact. A directly loaded legacy page cannot create a new reward in steps or partial mode; exact existing legacy receipts remain readable by their owner. Both settlement paths keep the existing shared per-user/date uniqueness boundary.
7. Explicit login-protected `/daily_challenge_legacy.html` serves through `_serve_live_static_or_baked`. The new HTML is in the live-static allowlist, Docker COPY, tracked build inputs and post-build verification list. The capability module is also in Docker and both manifest lists. No image build was executed.

## Executed checks

All logs below are in `artifacts/g076-p0a/`; the machine-readable receipt is `validation-01.json`.

| Exact command | Exit | Observed result |
| --- | --- | --- |
| `node tests/e2e/g076_daily_capability.mjs` | 0 | 48 checks PASS: actual inline capability/onload in Node VM, delayed response ordering, HTTP 401/409/503, malformed JSON, unknown mode, network error, timeout, fixed redirect, original steps init, inline script compilation, legacy byte parity, replay/admission ordering and packaging assertions |
| `node tests/e2e/g076_daily_client.mjs` | 0 | Existing 15 checks PASS: Daily transport, CSRF, server replies and frozen response-loss retry |
| `node --check tests/e2e/g076_daily_legacy_chrome.mjs` | 0 | Syntax only PASS |
| `node --check tests/e2e/g076_daily_chrome.mjs` | 0 | Syntax only PASS |
| `git diff --check` | 0 | PASS |
| Python312 targeted pytest command below | null | NOT_EXECUTED; spawn EPERM |

Node VM and source assertions are not real Chrome, HTTP, SQLite or PostgreSQL acceptance. No Python collection, fixture creation, SGF judge execution, XP/badge transaction or browser assertion was executed in this sandbox. Real Chrome original DOM was therefore **not captured**; no synthetic DOM is presented as browser evidence.

## Prepared runtime tests and exact pending commands

Run from this isolated worktree using an accessible local Python with Flask/pytest and existing repository dependencies. Do not import normal app startup or connect to a live database. Preserve existing receipts before any rerun.

```powershell
& 'C:\Users\beatl\AppData\Local\Programs\Python\Python312\python.exe' -B -m pytest -q tests/test_g076_daily_p0a.py tests/test_g076_daily_integration.py tests/test_g076_r3b_exposure.py tests/test_g076_nonmap_steps.py tests/deployment/test_g076_r3_image_closure.py tests/deployment/test_build_manifest.py --basetemp=artifacts/g076-p0a/pytest-tmp --junitxml=artifacts/g076-p0a/pytest.xml
& 'C:\Users\beatl\AppData\Local\Programs\Python\Python312\python.exe' -B tests/e2e/run_g076_daily_p0a.py
```

The first command is the exact blocked launch. The second remains NOT_EXECUTED because it depends on that interpreter. The runner refuses occupied fixture ports and an existing `browser-run.json`, starts/stops only loopback fixture servers, and runs:

```text
Python -B tests/e2e/g076_daily_fixture_server.py        # 127.0.0.1:5079
node tests/e2e/g076_daily_chrome.mjs
Python -B tests/e2e/g076_daily_p0a_fixture_server.py    # 127.0.0.1:5081
node tests/e2e/g076_daily_legacy_chrome.mjs
```

Prepared Python coverage includes all eight gate combinations, authenticated/no-store capability, unrecognized flags, direct legacy URLs and new-POST blocking, exact replay after every gate transition, changed payload conflict, same-day duplicate, cross-user attempt rejection, real SGF verdict overriding forged `correct`, XP/badges, history and privacy projection, and the actual extracted live-static/baked resolvers. Existing Daily transaction rollback and concurrent winner tests remain in the targeted suite. The legacy-first transition test now explicitly turns flags OFF for its legacy settlement; the fixture's legacy guards and step routes read the same injected environment instead of mismatching process environment and fixture flags.

Prepared Chrome coverage uses actual restored HTML/WGo canvas and HTTP, not a synthetic page: two users, actual moves aa/cc with forced bb reply, real signed attempts and server judge, durable SQLite XP/badges/review rows, result DOM, history, reload, same-day receipt replay, terminal response lost after commit/retry, partial modes and failed capability network. Historical history row is explicitly fixture-seeded, not claimed as a prior real award. Chrome uses a fresh profile, no proxy, disabled background services, and host resolution restricted to loopback. The original ON scenario is preserved; its obsolete OFF-blocked expectation now requires the restored legacy page.

If run successfully, the runners capture real DOM to `.g076-daily-tmp/steps-completed-dom.html` and `artifacts/g076-p0a/chrome-local/legacy-completed-dom.html`, plus blocked DOM, actual fixture effect rows and browser JSON receipts. Those files do not exist as acceptance evidence yet.

## Outstanding decision

P0-A shipping blocker is **not declared closed** until accessible local Python, disposable SQLite/HTTP and actual Chrome tests pass on the SHA256-pinned overlay, followed by G MASTER review/adoption. PostgreSQL semantics, a baked Docker image, ARM64, Safari/iPad and new Source qualification are NOT_EXECUTED. No existing historical receipt was promoted into a fresh pass.

No local commit was attempted: Python and real HTTP/browser acceptance are not sufficiently green. This is a verification environment blocker, not a demonstrated Git-index blocker. After successful verification, stage only the explicit reviewed product/test/handoff/evidence paths; never `git add .`. No push/merge/deploy/Production action is authorized.

## G MASTER Chrome finding — supplemental, overrides byte-identical legacy claim

Real Chrome OFF first trial returned canonical 50 XP and two badge awards HTTP 200, but displayed misleading failure due an exception in legacy showResultPanel on missing optional header. To resolve, G MASTER introduced only a bounded null guard around hdr-participants-wrap/hdr-participants; the restored page therefore is **not byte-identical** to b39. The Node check now proves it equals the b39 Git blob *after reversing exactly that one null guard*. Award formula, token, SGF/CSRF or submission transport were not changed. Earlier FAIL receipts preserved under artifacts/g076-p0a/*.FIRST_FAIL, *.SECOND_FAIL, *.THIRD_FAIL, *.FOURTH_FAIL, *.FIFTH_FAIL as applicable; await fresh Chrome verdict.
