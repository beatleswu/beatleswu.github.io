# LC015 — Dual-ID Read Caller Integration & Bootstrap-Gated Adoption

Status: **bootstrap-gated read adapter delivered + one meaningful read caller
(`admin_identity_lookup`) integrated. Every other target caller is proven
`APP_PY_DEPENDENT` with exact evidence and deferred. `bootstrap_state().hot` is
`False` in every real environment, so no runtime read path changes.**

Mode: IMPLEMENT / TEST / COMMIT / PUSH. `APP_PY_CHANGED = NO` (C048 owns the
`app.py` writer). `REAL_GENESIS_BOOTSTRAP = NO`, `UUID_BACKFILL = NO`,
`LEGACY_ID_REMOVED = NO`, no schema change, no production migration, no master
merge.

Base: `ee9f65c9e` (LC014). `origin/master` (fresh-fetch) =
`6829c4c528adf4800326e90534585a32e390ebec`. `merge-base(HEAD, origin/master)` =
`c2a1dab3125cdef0cff381815d3d995bdd340538`. **LC014 is not in master.**
`FRESH_MASTER_RECONCILIATION = LC_CANDIDATE_LINEAGE_EXTENDED` — LC015 extends the
LC014 candidate branch; no merge / rebase / PR (per §2).

---

## 1. What LC015 adds (additive only — `git diff HEAD` = 0 changed files)

| file | role |
|---|---|
| `identity_read_adapter.py` | **new** — `BootstrapGatedIdentityReader`, `IdentityKey`, `IdentityKeyKind`, `IdentityNotAttachable`, plus `identity_key_for_read` / `identity_keys_for_aggregate` / `admin_identity_lookup`. The single seam that encodes the §6 bootstrap gate so no caller re-implements it. |
| `tests/test_lc015_dual_id_read_caller_integration.py` | **new** — 15 SQLite + 1 real-PostgreSQL parity test. |

No existing module is edited. `app.py`, `review_service.py`, `sgf_admin_workbench.py`,
`canonical_learning_judge.py`, `map_battle_*` — untouched.

## 2. `CALLER_MATRIX` (exact evidence)

| target caller | every read/aggregate site | classification | reason |
|---|---|---|---|
| **review_log read / aggregation** | `app.py:4044` (`SELECT question_id, COUNT(*) … GROUP BY question_id`), `app.py:8715` / `10628` / `10699` / `10905` / `11405` (`SELECT DISTINCT question_id FROM review_log …`), `app.py:12160` (`SELECT question_id, grade … question_id IN (…)`) | **APP_PY_DEPENDENT** — deferred | all sites are inline SQL in `app.py`; no non-`app.py` review_log aggregate surface exists (`review_service.py` is the *write* command boundary; `legacy_review_serializer.py` serialises a single outcome, not an aggregate). `APP_PY_CALLER_INTEGRATION_REQUIRED_LATER = YES`. |
| **SRS read / aggregation** | `app.py:10496` / `10666` / `10677` / `10914` / `11426` / `12592` / `14917` (`SELECT question_id … FROM srs_cards …`), `app.py:13312` / `14256` (`SELECT * FROM srs_cards WHERE user_id=? AND question_id=?`) | **APP_PY_DEPENDENT** — deferred | all SRS reads are inline in `app.py`. `SRS_CORRECTNESS_AUTHORITY_CHANGED = NO`, `SRS_WRITE_PATH_CHANGED = NO`. |
| **admin lookup** | no dedicated puzzle-identity lookup surface exists today | **READY_FOR_NON_APP_PY_INTEGRATION → integrated** | `admin_identity_lookup(conn, …)` in the new adapter implements all four selectors (legacy id / uuid / current path / historical path), AMBIGUOUS → fail closed with candidates, never auto-picks. The admin HTTP *route* that calls it is `app.py` (C048) — deferred; the lookup itself ships now, tested. |
| **Learning Core reads** | judge = `canonical_learning_judge.py` (keyed by the SGF the client sends, **not** a `question_id` lookup); display/analytics reads = `app.py` | **NOT_SAFE_YET** (judge — correctness authority, out of scope) / **APP_PY_DEPENDENT** (display) — deferred | §10: do not change correctness authority. |
| **Adventure identity consumers** | `map_battle_runtime.py` / `map_battle_persistence.py` touch `question_id`; the identity consumers are `app.py` routes | **APP_PY_DEPENDENT** — deferred | §5: defer Adventure if `app.py` mutation would be required. It would. |

`FIRST_WAVE_CALLERS = admin identity lookup (integrated as a non-app.py read
surface)`.
`DEFERRED_CALLERS = review_log aggregation, SRS reads, Learning Core display
reads, Adventure identity consumers — all APP_PY_DEPENDENT, to be wired by C048
behind bootstrap_state().hot`.

## 3. The bootstrap gate (`BootstrapGatedIdentityReader`, §6)

`hot = bootstrap_state()["hot"]` — `True` only when the genesis bootstrap
receipt is `APPLIED` **and** identities exist. `hot` and the tables-present
probe are computed once per reader.

| state | `key_for(question_id)` → | `attachable` | `group_key` |
|---|---|---|---|
| `hot == False` (**always today**) | `IdentityKey(LEGACY, str(qid))` | `False` | `("legacy", qid)` |
| `hot` + `EXACT` | `IdentityKey(UUID, source_record_uuid)` | **`True`** | `("uuid", uuid)` |
| `hot` + `RETIRED` | `IdentityKey(UUID, source_record_uuid, retired=True)` | `False` | `("uuid", uuid)` — resolvable for history |
| `hot` + `AMBIGUOUS` | `IdentityKey(UNRESOLVED, str(qid), candidates=…)` | `False` | `("unresolved", qid)` — **never merged into a uuid bucket** |
| `hot` + `MISSING` | `IdentityKey(LEGACY, str(qid))` | `False` | `("legacy", qid)` — compatibility |
| `hot` + `UNAVAILABLE` | `IdentityKey(UNAVAILABLE, str(qid))` | `False` | `("unavailable", qid)` |

`HOT_FALSE_LEGACY_BEHAVIOR = PASS` — on `hot == False` the reader never queries
the resolver beyond the single cheap `bootstrap_state()` probe, returns a
`LEGACY` key for every id, and a test proves registry / alias / lineage row
counts are byte-for-byte unchanged after any number of calls.

`assert_attachable(question_id)` — a would-be **writer** of new SRS / review /
adventure state calls this on purpose: returns the canonical uuid iff `EXACT`,
else raises `IdentityNotAttachable`. It **never fabricates** an identity.
`RETIRED_NEW_ATTACHMENT = REJECTED`.

## 4. Dual-ID aggregate keying (§7)

`keys_for(question_ids)` / `group_keys_for(question_ids)` — one batch resolve,
each id classified independently. `AGGREGATE_COLLISION_FAIL_CLOSED = YES`,
`AMBIGUOUS_ALIAS_AUTO_MERGE = NO`:

- a legacy id current in >1 alias context to different identities → its own
  `("unresolved", qid)` bucket, never folded into any `("uuid", …)` bucket;
- two distinct ambiguous ids stay in two distinct buckets;
- a caller re-buckets its `review_log` / `srs_cards` rows on `group_key` and can
  never merge two historically distinct records because their legacy integers
  coincide.

## 5. Admin lookup (§11)

`admin_identity_lookup(conn, <one selector>)`:

| selector | resolves via | evidence |
|---|---|---|
| `legacy_question_id` | `resolve_legacy_question_id` (context-agnostic) | `ADMIN_LOOKUP_LEGACY_ID = PASS` |
| `source_record_uuid` | `get_identity` | `ADMIN_LOOKUP_UUID = PASS` |
| `current_source_path` | `resolve_current_source_path` | `ADMIN_LOOKUP_CURRENT_PATH = PASS` |
| `historical_source_path` | `resolve_historical_source_path` | `ADMIN_LOOKUP_HISTORICAL_PATH = PASS` |

`AMBIGUOUS` → `{"status": "AMBIGUOUS", "candidates": [...]}` — **no
`source_record_uuid` field, the operator picks**. Unknown → `{"status":
"MISSING"}`. Zero or ≥2 selectors → `{"status": "BAD_REQUEST"}`.
`AMBIGUOUS_ADMIN_LOOKUP_FAIL_CLOSED = YES`.

## 6. No write authority (§14)

`identity_read_adapter.py` imports **only** `DualIdReadWindow`,
`ResolutionStatus` from `puzzle_identity_read_window` — no
`create_historical_genesis_identity`, `create_native_identity`,
`mint_genesis_uuid`, `GenesisBootstrap`, `PuzzleIdentityStore`, `INSERT`,
`UPDATE`, or `DELETE`. A test parses the module AST and asserts this. Thousands
of adapter calls against a seeded DB leave every table's row count unchanged.
`PRODUCTION_IDENTITY_WRITES_ADDED = NO`, `NO_FABRICATED_IDENTITY = PASS`,
`SILENT_IDENTITY_CREATION = NO`.

## 7. Recipe for the future `app.py` wire (C048 / LC016)

For each deferred aggregate caller, the change is one call + a re-bucket:

```python
from identity_read_adapter import BootstrapGatedIdentityReader

reader = BootstrapGatedIdentityReader(conn)          # once per request
rows = conn.execute("SELECT question_id, COUNT(*) AS cnt FROM review_log "
                    "WHERE user_id=? AND grade>=3 GROUP BY question_id", (uid,)).fetchall()
gk = reader.group_keys_for(r["question_id"] for r in rows)
merged = collections.Counter()
for r in rows:
    merged[gk[str(r["question_id"])]] += r["cnt"]     # ("uuid", …) rows fold; ("legacy"/"unresolved", …) stay separate
```

On `hot == False` this is byte-for-byte the current behaviour (every key is
`("legacy", qid)`). For a would-be *writer* of a new `srs_cards` row:
`uuid = reader.assert_attachable(question_id)` — raises rather than attach to a
retired / ambiguous / missing identity.

## 8. Tests (§17 / §18)

`tests/test_lc015_dual_id_read_caller_integration.py`:

- **HOT_FALSE**: pure legacy, zero mutation; also `hot == False` when the
  receipt exists but is not `APPLIED`.
- **HOT_TRUE matrix**: EXACT → UUID + attachable; RETIRED → UUID + history only
  + `assert_attachable` raises; AMBIGUOUS → UNRESOLVED + `("unresolved", qid)` +
  candidates + `assert_attachable` raises; MISSING → LEGACY (compat);
  UNAVAILABLE (tables dropped) → UNAVAILABLE key.
- **aggregate**: mixed EXACT/RETIRED/AMBIGUOUS/MISSING → correct per-id keys, 4
  distinct group keys, ambiguous never merged into the uuid bucket; batch
  dedupes duplicate inputs.
- **admin lookup**: all four selectors; AMBIGUOUS fail-closed (no auto-pick);
  unknown → MISSING; retired by uuid; BAD_REQUEST on 0 / ≥2 selectors.
- **renamed path**: old path MISSING, new path EXACT, legacy id keying
  unchanged.
- **NO_FABRICATED_IDENTITY**: row counts unchanged after thousands of calls;
  AST import check.
- **real PostgreSQL parity**: the full gate matrix (cold → legacy; hot →
  EXACT/RETIRED/MISSING/AMBIGUOUS; aggregate; admin lookup) on a disposable
  `postgres:16.14-alpine` container — identical classification to SQLite.

`SQLITE_PARITY = PASS` (15). `POSTGRES_PARITY` — see the final report (the test
is committed and ready; on this run it depends on the local Docker daemon being
up).

## 9. What LC015 does NOT do

- No `app.py` / `review_service.py` / SRS / Adventure / Learning-UI code change;
  no HTTP route wiring.
- No genesis bootstrap, no UUID backfill, no registry population; `bootstrap_state().hot`
  stays `False` in every real candidate/runtime state.
- No `question_id` removal, no historical row rewrite, no schema change, no
  production migration, no corpus / SGF / LC012-R2 artifact change.
- No RPG / other-lane change (B055, C048, A039, D040, E044, F032, ART002/003).
- No merge / rebase / PR onto master.

## 10. What LC016 should do

1. **C048-owned `app.py` wire** of the deferred aggregate callers using §7's
   recipe, behind `bootstrap_state().hot` (still `False` until genesis).
2. **Admin route** that calls `admin_identity_lookup`.
3. Independently: the **owner-gated genesis bootstrap** (`GenesisBootstrap.apply()`
   with the real LC012-R2 receipt + 42,804-row manifest) — the only thing that
   flips `hot` to `True`.
4. A fresh-master integration candidate for the whole LC011–LC015 identity
   lineage (Coordinator-directed).
