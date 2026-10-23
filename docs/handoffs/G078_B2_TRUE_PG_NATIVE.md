# G078 Lane B2 native PostgreSQL continuation

Date: 2026-10-23 (Asia/Taipei)
Workspace: `D:\go-odyssey-g076-p0b-rating-20261023`
Verified starting HEAD: `282f4ead69a6daff59e87466f6871a7fbfd94ca6`

**IMPLEMENTED; NATIVE PG NOT_EXECUTED. No TRUE PG PASS claim.**
G MASTER must execute all 16 cases against the authorized disposable container
and retain its native result before asserting native parity. Historical SQLite
results, collection, static checks, and opt-in skips do not establish PG PASS.

## Owned changes and authority

Added only `tests/test_g078_rating_pg_live.py` and this handoff. No edits to
`app.py`, `g076_rating_steps.py`, `g078_rating_integration.py`, the original
fixture, or the existing integration tests. Existing dirty/untracked work was
retained. No git commit, push, merge, deployment, Oracle or production operation.
No credential file was read, copied, printed or committed. No PG connection or
DDL was executed during this implementation turn.

User reports G MASTER independently verified the exact online container label
and loopback binding in the preceding round. The suite additionally requires
fresh matching Docker metadata before opening any connection. It does not start,
restart, reconfigure, or delete containers.

## Execution gate

G MASTER supplies `PG_DSN` securely in the test process environment. The suite
never reads the protected disposable JSON or falls back to `DATABASE_URL`, the
application pool, a service DSN, or another database. Do not paste credentials
into commands, transcripts, artifacts or this document.

Required non-secret environment markers:

```powershell
$env:G078_PG_CONTAINER = 'g076-r5-isolated-pg-20261023'
$env:G078_PG_ISOLATION_MARKER = 'go-odyssey.g076.r5=isolated-disposable'
```

After G MASTER has securely supplied `PG_DSN`, execute from the workspace above:
Use a Python environment with Flask, the repository fixture dependencies and
`psycopg2` (typically supplied by `psycopg2-binary`) installed. The cached runtime
below can perform the no-DSN checks, but currently lacks psycopg2; use G MASTER's
prepared PG environment for the native run, or prepare that dependency first.

```powershell
& 'C:/Users/beatl/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -B tests/test_g078_rating_pg_live.py
```

The DSN must explicitly name `host=127.0.0.1`, `port=55476`, and a database.
`service` and `hostaddr` are rejected. Docker must report the exact container
running, label `go-odyssey.g076.r5=isolated-disposable`, and only
`127.0.0.1:55476` for `5432/tcp`. Docker unavailability or any mismatch is an
error, never a skip or a fallback. Docker inspection selects only running state,
the one label and port mappings; it does not request container environment.

Missing/empty `PG_DSN` produces an explicit class-level SKIP with zero executed
tests. A zero exit status from this skip is **NOT PASS**. An accepted native
receipt requires `Ran 16 tests`, no errors/failures/skips, and the exact source
identity. Do not use `--locals` or environment dumps when recording receipts.

Each test creates its own `g078_b2_<random UUID hex>` schema, sets search_path
to that schema (without public), and removes only that schema in cleanup.
Original tables receive PostgreSQL INTEGER/TEXT/DOUBLE PRECISION fixture types.
No schema migration or DDL is installed by the application adapter. Interruption
or connection loss can prevent cleanup; report leftover schema names rather
than running broad cleanup. Native statements have 10-second statement and
5-second lock timeouts; connection attempts have a 5-second timeout.

## What the fixture executes

The real `db.PostgresConnectionWrapper`, including its actual placeholder
translator, sits over psycopg2 connections with `DictCursor`. The observation
subclass records calls and delegates native SQL/commit/rollback/close unchanged.
No SQL lock removal, SQLite connection, or PostgreSQL emulation exists here.

The existing `g076_rating_fixture.original_functions()` supplies the original
app judge/math/writer/finalization AST. The existing namespace factory and pool
literal are also extracted from that fixture, avoiding its SQLite constructor.
Its existing RemoveCommit transformation remains part of the fixture seam;
legacy route bodies and the SharedConnection callback are not invoked by these
tests. The adapter invokes the extracted writer on the real PG connection.
The two-question corpus, selection/history/rank stubs and shortened two-round
configuration remain explicit fixture limitations. This is native PG evidence
for that bounded seam, not real corpus, full app startup, legacy HTTP, account
claim/SP, security admission or production qualification evidence.

Deferred commit failure uses a native `DEFERRABLE INITIALLY DEFERRED` foreign
key and inserts an invalid reference immediately before delegating to the real
wrapper commit. PostgreSQL must raise ForeignKeyViolation at commit; the adapter
must roll back all second-round effects and allow the exact nonce retry.
There is no monkeypatched commit exception. Concurrent replay uses two worker
threads and separate PG connections, retaining original account/session locks.

## Sixteen native cases

| Case | Required behavior |
| --- | --- |
| 01 | Native server version, real wrapper, retained account/session FOR UPDATE and one transaction commit |
| 02 | Authenticated account's original 2100 Elo / 160 SE prior |
| 03 | Anonymous 1500 / 400 prior, sid capability, no account/mistake mutation |
| 04 | Two accounts; cross-owner rejection without effects and independent progression |
| 05 | Missing account rejected without fabrication or writes |
| 06 | settle_forfeit writes incorrect round using original Elo/SE estimate |
| 07 | Early timeout rejected; deadline timeout uses original trusted forfeit with no fabricated moves |
| 08 | Original transformed question, CONTINUE without settlement, original judge and correct Elo/SE |
| 09 | Unverifiable original judge blocks writer with unchanged snapshot |
| 10 | Changed original question blocks forfeit writer with unchanged snapshot |
| 11 | Exact response and request-hash receipt once; conflicting replay rejected |
| 12 | Concurrent same-body replay yields identical replies, one response/event/mistake increment |
| 13 | Native deferred-FK commit failure rolls back account/queue/unlock/session/nonce/ledger; retry succeeds |
| 14 | Placement account update, queue deletion, unlock, two responses and second-account isolation |
| 15 | Missing ledger returns readiness false and HTTP HOLD; readiness creates no DDL |
| 16 | Rating ON works with global privacy OFF and ON; authenticated HTTP board-only projection |

## Fresh local verification and outstanding receipt

Executed with the cached CPython runtime and `-B`: AST parse, count of 16 test
methods, original AST namespace construction, and PostgreSQL fixture type
adaptation checks. All completed successfully without a database connection.
The no-DSN branch was explicitly exercised after removing `PG_DSN` from only
that verification process: `Ran 0 tests`, `OK (skipped=1)`, reason
`PG_DSN missing: native PG NOT_EXECUTED (not PASS)`.

The ordinary `python` command was unavailable on PATH; the documented cached
runtime worked for collection/namespace/skip checks. A negative gate check
confirmed missing isolation markers are rejected before any connection. The
next non-isolated-endpoint negative check stopped at `ModuleNotFoundError:
No module named 'psycopg2'`; that endpoint guard was not dynamically verified.
No dependency was installed and no DSN was obtained. Native server checks and all 16 test bodies remain
**NOT_EXECUTED pending G MASTER**. Capture fresh HEAD, dirty-overlay file SHA256s
(especially app/steps/adapter/original fixture/new test), container identity,
command and complete sanitized unittest output in G MASTER's authorized receipt
location. Do not upgrade any historical failure or this local skip to PG PASS.
