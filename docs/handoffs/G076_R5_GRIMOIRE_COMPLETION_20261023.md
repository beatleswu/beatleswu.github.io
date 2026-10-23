# G076 R5 Grimoire isolated continuation — completion evidence, mode HOLD

2026-10-23, Asia/Taipei. NON-PRODUCTION ONLY. G MASTER remains sole main integration Writer. P0-A Daily OFF repair is separate. Release HOLD remains.

## Identity and permitted scope

- Workspace: `D:\go-odyssey-g076-r4-grimoire-worker-20261023`.
- Initial `git log -1 --format="%H%n%P"`: HEAD `78d2534ef763f000015eebf95f23e0d5c65408e2`, parent `f414db82b5c1aa45f8b7086c1defb1bfe0f307eb`; both match user authority. Initial `git status --short` had no entries (Git emitted a `.pytest_cache/` directory warning).
- Changed only R4-owned `g076_grimoire_adapter.py`; added `g076_grimoire_catalog.py`, `tests/test_g076_grimoire_r5_sqlite.py`, `tests/test_g076_grimoire_r5_protocol.py`, this report and adjacent proposed SQL documentation. No other worktree writes.
- No changes to app.py, index.html, Dockerfile, deploy, grimoire_api.py, g076_othermode_authority.py, shared judgement/reward, runtime flags, real content or accounts.
- No push, merge, Oracle, Production PG/schema/player mutation, CI, Build, deploy or feature-gate approval.

## Actual legacy coupling, rights and reward findings

Read `grimoire_api.py` actual `api_training_answer`, daily generation/cache handlers, purity function, table helper and login decorator; also `db.py` connection wrapper/pool. `get_ldb()` and `get_sdb()` BOTH call `db.get_db()` against the same configured PostgreSQL pool. They are **separate connections/transactions**, not the same transaction. No live DB URL, credentials or runtime catalog was inspected. Same logical configured database is established from source only; no runtime atomicity claim.

The legacy answer handler reads catalog `grimoires.node_count` through a nested `get_ldb()` connection, reads membership from cached questions.json, then writes node/progress/cache through `get_sdb()`. Its schema helper commits internally. Consequently invoking that handler/helper is NOT a safe transactional settlement integration. R5 never calls its handler or table-creation helper in the settlement path.

Legacy mastery uses the last five booleans, weighted purity, preserved prior last_correct_at on incorrect answers, attempt increment, and contamination `(not correct) and purity < .3`. Aggregate is SUM of this owner's mastery for **all questions in the catalog**, divided by `max(1,node_count)` (not answered count; no new clamp). Rank advances at most one level per attempt at .3/.6/.8/1.0 and never drops. Total/correct counters increment per attempt. Cache completion appends only an included question not already completed, including incorrect answers; other dates and missing caches are untouched. No cache generation or reset is introduced.

Legacy answer trusts browser `correct`, with a session-presence decorator and question-existence check, but no explicit premium/ownership entitlement check in that function. It writes **no XP or reward**. Daily generation reads user_stats/SRS/review_log for recommendations; that does not authorize an answer or reward. R5 preserves R4's mandatory trusted `admit(conn,uid,q) is True` on issue/resume/answer/replay. Test admission is synthetic; real rights policy remains an integration dependency, not inferred from legacy.

## Candidate implementation and exact limits

R4 service, token/step nonce, canonical judge, replay event, terminal once-only logic and Flask blueprint are unchanged. The old mastery SQL/statements were extracted verbatim into `_settle_node_mastery`; `settle_node_only` retains its original catalog/cache HOLD checks and delegates. AST comparison against HEAD verified unchanged `GrimoireSteps`, `create_blueprint`, `GrimoireRejected`, and every mastery-writer statement from `old = ...` through return. Existing R4 tests/report were not edited.

New `settle_catalog_and_cache` is an **opt-in SQLite-only callback**, explicitly supplied to the existing `GrimoireSteps(settle=...)`. It requires an active transaction, local main-DB tables and no temporary tables/views. R4 owns BEGIN IMMEDIATE, final event/attempt writes, COMMIT, rollback and connection closure. Callback performs no commits, new connections, network calls or external effects.

The disposable fixture supplies a complete trusted frozen `g076_grimoire_catalog_members` projection alongside `grimoires`. Catalog denominator, membership, node mastery, progress, daily cache and replay states are all read/written on that connection. No fallback to another DB or JSON file. Missing catalog yields `same_database_catalog_required`; missing/malformed node-count or missing question membership yields `catalog_projection_incomplete`. This intentionally HOLDs incomplete projections rather than reproducing legacy's missing-catalog fallback to 1. A separate database cannot satisfy these main-table requirements. No cross-DB atomicity is asserted.

`catalog_revision(conn)` hashes canonical JSON containing sorted `[id,node_count]` and `[question_id,grimoire_id]` rows. The trusted question loader must include `g076_catalog_revision` in its q object **before issue and on every revalidation**. Existing R4 whole-question binding then binds this digest without modifying token logic. Missing or changed digest fails terminal settlement closed. The fixture installs the projection before issuance; no production importer is supplied. The digest binds bytes but does not authorize their provenance. MASTER must establish completeness and the original questions.json SHA, and prevent catalog publication racing issuance/settlement. SQLite BEGIN IMMEDIATE serializes the disposable DB; that is not PostgreSQL locking evidence.

The existing dedicated `create_blueprint(service)` is ready for an isolated Flask app (tested in authored protocol tests); the application has no registration or token-issuance route. Server scope issuance/admission policy, real identity/rights providers, real catalog projection, PG transaction adapter and application/client wiring remain **HOLD**. New scopes still mean new attempts under the unchanged R4 policy. Settlement helper alone is not an HTTP entry point and is not independently replay-safe; R4 transaction/events supply exactly-once.

Adjacent `G076_R5_GRIMOIRE_PROPOSED_SQL_20261023.sql` is standalone documentation only, not a migration. It describes per-owner plus per-attempt SELECT FOR UPDATE, first-row races, catalog publication barrier, same-connection writes and commit-before-response. Current service deliberately rejects PostgreSQL connections; no PG implementation is implied.

## Historical and current receipts (never combined)

Historical R4 report at this base records:

1. `python -m pytest -q tests/test_g076_grimoire_adapter.py`: **61 passed, 1 failed**, 13.13s. Assertion expected a generic error instead of correctly rejected `unsafe_settlement_receipt`; historical FAIL preserved.
2. `python -m pytest -q tests/test_g076_grimoire_adapter.py tests/test_g076_othermode_authority.py tests/test_g076_server_step_authority.py`: **106 passed**, 23.16s (62 R4 + 44 existing). SHA-bound historical evidence only; NOT a fresh R5 run.

Current commands from this workspace, in execution order relevant to validation:

```powershell
python -m pytest -q -p no:cacheprovider tests/test_g076_grimoire_adapter.py tests/test_g076_othermode_authority.py tests/test_g076_server_step_authority.py
```

Failed before collection: `python` not recognized in this session PATH. Then:

```powershell
& 'C:\Users\beatl\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q -p no:cacheprovider tests/test_g076_grimoire_adapter.py tests/test_g076_othermode_authority.py tests/test_g076_server_step_authority.py
```

Exit 1: `No module named pytest`. This is a validation-environment failure, not a passing baseline.

```powershell
$r5Deps = Join-Path $env:TEMP 'g076-r5-python-deps-20261023'
& 'C:\Users\beatl\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pip install --disable-pip-version-check --target $r5Deps pytest Flask psycopg2-binary
```

Exit 1: network connection to pypi.org blocked with WinError 10013 after retries; dependencies were not installed. No environment escalation. Direct system Python at `C:\Users\beatl\AppData\Local\Programs\Python\Python312\python.exe` also failed to start with access denied; its site-packages directory was denied. No permission bypass attempted.

```powershell
& 'C:\Users\beatl\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B tests/test_g076_grimoire_r5_sqlite.py
```

- First run: exit 0, **10 tests OK**, 18.991s, before adding catalog-digest binding.
- Final-code run: exit 0, **11 tests OK**, 18.816s. Includes **2,520 exact legacy parity subcases**, not 2,520 additional pytest tests. These verify every boolean history of length 0–5, both verdicts, ranks 0–4 and node_count 0/1/2/8; owner/catalog isolation, legacy counters/history/contamination/timestamps, no rank demotion/multi-level jump, cache membership/date/absent behavior, projection absence/revision rejection, malformed cache, real AFTER-write trigger failures, deferred COMMIT failure, and eight concurrent distinct settlements without lost updates.
- All databases are real disposable SQLite, file-backed for concurrent writers and in-memory for parity pairs. Cleanup belongs to TemporaryDirectory. Legacy answer, purity and candidate functions are extracted **exactly by AST**; only transport/date/DB providers are supplied. The import hook supplies the exact legacy purity function to the exact writer without importing unavailable Flask. This is explicit settlement SQL/formula evidence, **not full module-import, HTTP, nonce or PG evidence**.
- No R5 test assertion failure occurred in these executed runs. The earlier environment failures remain listed above.

Source AST parity and `compile(..., 'exec')` on the four changed/new Python files returned `SOURCE_PARITY_OK: R4 service, transport, rejection class and mastery writer statements unchanged; 4 files compile`. This is source/syntax evidence, not Build or R4 test PASS.

Final full-suite attempt:

```powershell
$r5Python = 'C:\Users\beatl\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $r5Python -m pytest -q -p no:cacheprovider tests/test_g076_grimoire_adapter.py tests/test_g076_othermode_authority.py tests/test_g076_server_step_authority.py tests/test_g076_grimoire_r5_sqlite.py tests/test_g076_grimoire_r5_protocol.py
```

Exit 1: `No module named pytest`; **NOT_COLLECTED / NOT_EXECUTED**. Full imported protocol tests are authored for malicious correct/grade/reward/owner fields; owner/revision/expiry/rights/catalog replay; forged nonce/conflicting move; rollback after catalog/cache/event writes and deferred commit; concurrent duplicate/conflicting terminal requests and split-DB refusal. These do not contribute to current PASS counts. R4's 106 baseline has not been freshly rerun.

## PG and browser feasibility

```powershell
docker info --format '{{.ServerVersion}}'
pg_isready -h localhost -p 5432
```

Docker info failed: config access denied and permission denied connecting to `npipe:////./pipe/docker_engine`. pg_isready reported `localhost:5432 - accepting connections`; this does NOT identify a disposable fixture, version, ownership or write authority. No authenticated PG connection or DDL was attempted. No verified disposable PostgreSQL 16 fixture available; **PG / SELECT FOR UPDATE / PG concurrency = NOT_EXECUTED**.

Chrome executable exists at `C:\Program Files\Google\Chrome\Application\chrome.exe`. The existing Chrome runner exercises Map Battle and writes outside this task's scope; it is not a Grimoire actual mode runner. Grimoire product UI/transport is unregistered, and Flask dependencies cannot be imported here. Thus actual Chrome mode flow is not feasible in this session: **CHROME=NOT_EXECUTED / HOLD**. No browser automation or Safari/iPad, CI, Build, deploy or mode-compatibility PASS claim.

## Delivery and remaining gate state

**MODE_READY=NO; MODE_COMPATIBILITY=HOLD; INTEGRATION=HOLD; RELEASE=HOLD.** Separate global/mode feature-gate review is still required. P0-A Daily OFF repair remains separately owned. Production owner authorization is still separate and absent here.

**LOCAL_COMMIT=NOT_ATTEMPTED / BLOCKED_VALIDATION**: full R4+R5 green prerequisite is unmet because dependencies are unavailable. No git add or commit was attempted. This avoids presenting subset PASS as full clearance. `.git` points to `D:/go-website/.git/worktrees/go-odyssey-g076-r4-grimoire-worker-20261023`, outside the writable root; the old R4 index.lock denial is historical, not a new attempted Git operation. G MASTER can validate and stage only these exact six permitted files in an authorized environment.

No credentials, bearer tokens, real players, production data or flags were used. No new XP/reward formula, catalog importer, schema migration or release gate was invented.

## Final source receipt

Final branch `g076-r4-grimoire-worker-20261023`, HEAD unchanged `78d2534ef763f000015eebf95f23e0d5c65408e2`; base committed TREE `ce609eff98f852316ce0449f0b669c79ba99b5ea`. This tree identifies the committed base, **not the six-file overlay**. Final `git status --short` lists exactly the six files above (one modified, five untracked). `git diff --check` exited 0. The following unchanged-file check exited 0:

```powershell
git diff --exit-code HEAD -- tests/test_g076_grimoire_adapter.py docs/handoffs/G076_R4_GRIMOIRE_WORKER_20261023.md app.py index.html Dockerfile grimoire_api.py g076_othermode_authority.py
```

SHA256 of final source/test/proposed-SQL bytes (this report deliberately has no self-hash):

| File | SHA256 |
| --- | --- |
| g076_grimoire_adapter.py | `9F04909DE26DDAA14BBAFC014F9EAA1BF8C6FCB695B3191959FCE0B9BD2ECE9B` |
| g076_grimoire_catalog.py | `092530CB8FBF1A65D15955FFD893BF3C45DEA37D8A2DB00B80530B516BB5D352` |
| tests/test_g076_grimoire_r5_sqlite.py | `5D59B8DFA809287B1925E124E9B9ABBAC03590CB911A9C3A2719DDC8DFC4A288` |
| tests/test_g076_grimoire_r5_protocol.py | `A48B5C916BD4F8B740172765B0BF8883AF92DE4EFD40EE59A8FA6EA9875F5118` |
| docs/handoffs/G076_R5_GRIMOIRE_PROPOSED_SQL_20261023.sql | `F59628A6DC76D725DC73CB91618416CCED82F4FBE9920FC49C0F2B19B959572F` |

Exact executed source-comparison/syntax command (HEAD was the base SHA above):

```powershell
$r5Python = 'C:\Users\beatl\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
@'
import ast, pathlib, subprocess
old = ast.parse(subprocess.check_output(['git','show','HEAD:g076_grimoire_adapter.py'], text=True))
new = ast.parse(pathlib.Path('g076_grimoire_adapter.py').read_text())
def node(tree,name):
    return next(n for n in tree.body if getattr(n,'name',None)==name)
for name in ('GrimoireSteps','create_blueprint','GrimoireRejected'):
    assert ast.dump(node(old,name)) == ast.dump(node(new,name)), name
old_writer = node(old,'settle_node_only').body
start = next(i for i,n in enumerate(old_writer) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='old' for t in n.targets))
new_writer = node(new,'_settle_node_mastery').body[2:]
assert [ast.dump(n) for n in old_writer[start:]] == [ast.dump(n) for n in new_writer]
paths = ['g076_grimoire_adapter.py','g076_grimoire_catalog.py','tests/test_g076_grimoire_r5_sqlite.py','tests/test_g076_grimoire_r5_protocol.py']
for p in paths:
    compile(pathlib.Path(p).read_text(), p, 'exec')
print('SOURCE_PARITY_OK: R4 service, transport, rejection class and mastery writer statements unchanged; 4 files compile')
'@ | & $r5Python -B -
```
