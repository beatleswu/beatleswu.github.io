# LC013 — Immutable Puzzle Identity: Registry & Lineage Storage Candidate

Status: **empty storage foundation implemented — additive migration + repository
+ gated bootstrap interface + tests. No genesis population. No app.py. No
production migration.**

Mode: RECON / IMPLEMENT / TEST / COMMIT / PUSH. `APP_PY_CHANGED = NO` ·
`USER_VISIBLE_RUNTIME_CHANGED = NO` · `GENESIS_BOOTSTRAP_EXECUTED = NO` ·
`UUID_BACKFILL = NO` · `PRODUCTION_DB_MIGRATION = NO`.

Base: `9d4d5a91470167f71aa5df19ef591a71390053ec` (LC012-R2, `LC012_R2_DEPENDENCY_EXACT = YES`).
`origin/master` (fresh-fetch): `4585bd1a12d179d0810300f047357f2e36c3e851`.
`git diff origin/master…HEAD -- db.py migrations/ schemas/` is **empty** — the
schema/persistence infrastructure on the accepted Learning Core lineage is
byte-identical to fresh canonical master, so this candidate is built against
current conventions. `FRESH_MASTER_SCHEMA_RECON = PASS`.

---

## 1. Storage recon (actual, not assumed)

| question | finding |
|---|---|
| where Puzzle identity currently lives | **Not in the DB.** Puzzles are corpus records in `questions.json` (`DATA_FILE = os.environ.get('QUESTIONS_JSON_PATH', 'questions.json')`, `_load_questions()` in `app.py`). Runtime identity = the record's `id` field (legacy integer). |
| DB rows / corpus records / projections? | Corpus records / in-memory projections of `questions.json`. There is no `questions` table. |
| existing numeric / legacy identifiers | `q['id']` (int). Persisted as `review_log.question_id INTEGER` (SRS/analytics), `migrations/sgf_admin_workbench_v1.py` `question_id bigint` + `record_index`, `migrations/sgf_human_review_v2a.py` **`legacy_question_id TEXT` + `record_index BIGINT` + `reviewed_record_sha256`** (already an LC011-shaped locator: legacy id = alias, record_index = audit locator, content sha ≠ identity). |
| SRS / analytics FK references | `review_log.question_id` (no real FK — questions aren't a table), the `sgf_admin_workbench_*` and `sgf_human_review_*` tables. **None removed or altered by LC013.** |
| migrations framework | Custom, module-per-file under `migrations/`. Each module: `SCHEMA_VERSION`, `upgrade(conn, *, dry_run=False) -> dict`, `validate_schema(conn) -> dict`, `downgrade_for_isolated_test(conn)`, a `*SchemaError(RuntimeError)`. Caller owns the transaction; the module **never commits**. Not imported at app startup. |
| PostgreSQL / SQLite | Both required. `_is_sqlite(conn)` = `getattr(conn,'_conn',conn).__class__.__module__.startswith('sqlite3')`. `?` paramstyle everywhere (`db.PostgresCursorWrapper.translate_placeholders` → `%s`). Helpers: `_id_type` (`INTEGER PRIMARY KEY AUTOINCREMENT` \| `BIGSERIAL PRIMARY KEY`), `_stamp` (`TEXT` \| `TIMESTAMPTZ`), `_json_type` (`TEXT` \| `JSONB`). Tests use `sqlite3.connect(":memory:")`; PG paths covered by `*_postgres.py` suites. |
| existing UUID support anywhere | **None.** `grep -rn "uuid" migrations/` → nothing. `source_record_uuid` is a new concept in persistence. |
| existing lineage / audit table pattern | `migrations/domain_event_outbox_v1.py` (D5A outbox, `event_id TEXT PRIMARY KEY`, CHECK-enum `event_type`/`outcome`, append-oriented), `migrations/premium_claim_lineage_v1.py` (`premium_entitlement_events` with `parent_entitlement_event_id`), `migrations/equipment_canonical_slot_v1.py` (SQLite `CREATE TRIGGER … BEFORE UPDATE OF … RAISE(ABORT,…)` + PG `CHECK`/trigger). LC013 follows exactly these idioms. |

## 2. Tables (additive — `migrations/puzzle_identity_registry_v1.py`, `SCHEMA_VERSION = puzzle_identity_registry_v1`)

`MIGRATION_ADDITIVE_ONLY = YES` — four new tables, six indexes, one partial
unique index, seven SQLite triggers (five PG triggers + four PG functions). No
existing column removed, no table rewritten.

### 2.1 `puzzle_identity_registry` — one durable row per Puzzle identity

| column | notes |
|---|---|
| `source_record_uuid` **TEXT PRIMARY KEY** | the permanent identity. `CHECK` on 8-4-4-4-12 shape; full `uuid.UUID()` + version check in the repository. **Immutable** (trigger). |
| `identity_kind` | `CHECK IN ('HISTORICAL_GENESIS','NATIVE_UUIDV4')`. Immutable (trigger). |
| `identity_version` | `puzzle-identity-schema-v1`. Immutable. |
| `origin_class` | `CHECK IN ('GENESIS','NATIVE')`; cross-checked against `identity_kind`. Immutable. |
| `identity_status` | `CHECK IN ('ACTIVE','RETIRED')`, default `ACTIVE`. **Mutable** (retire/restore only). |
| `created_at`, `created_by_process`, `creation_reason` | creation provenance. Immutable. |
| `genesis_receipt_ref` | `→ puzzle_identity_bootstrap_receipt(receipt_sha256)`. `CHECK (identity_kind <> 'HISTORICAL_GENESIS' OR genesis_receipt_ref IS NOT NULL)`. Immutable. |
| `retired_at`, `retire_reason` | set on retire; `CHECK (identity_status <> 'RETIRED' OR retired_at IS NOT NULL)`. |
| `provenance_note` | **generic nullable** field, **no assigned semantics** — reserved so a future MANUAL-marker policy (§23, still undecided) has somewhere to land without LC013 inventing meaning. |

The **live/current source path is not here** — it is an alias (§2.2).
`SOURCE_PATH_AS_LIVE_IDENTITY = NO`, `CONTENT_HASH_AS_IDENTITY = NO`,
`RECORD_INDEX_AS_IDENTITY = NO`, `LEGACY_NUMERIC_ID_AS_PRIMARY_IDENTITY = NO`.

### 2.2 `puzzle_identity_alias` — legacy id / source path / resolver aliases

`id` PK; `source_record_uuid → registry`; `alias_kind CHECK IN
('LEGACY_QUESTION_ID','HISTORICAL_SOURCE_PATH','CURRENT_SOURCE_PATH','CANONICAL_SOURCE_KEY','RESOLVER_ALIAS')`;
`alias_value`; `alias_context` (default `genesis-v1`, e.g. `post-genesis` after a
rename) — **paths are not assumed globally unique forever**, the context scopes
them; `confidence CHECK IN ('EXACT','HIGH_CONFIDENCE','RECORDED')`; `is_current`
(0/1).

- `UNIQUE (source_record_uuid, alias_kind, alias_value, alias_context)` — an
  identity never has duplicate alias rows.
- **`uq_pia_current_alias` — partial `UNIQUE (alias_kind, alias_value,
  alias_context) WHERE is_current = 1`.** This is the storage-level guarantee
  behind `AMBIGUOUS_ALIAS_FAILS_CLOSED`: two different identities can never both
  *currently* claim the same legacy id / path / context. A rename supersedes the
  old current alias (`is_current 1→0`) and inserts a new one; superseded rows
  stay for history.
- The identity binding columns (`source_record_uuid, alias_kind, alias_value,
  alias_context`) are **immutable** (trigger) — you supersede, you don't rewrite.

### 2.3 `puzzle_identity_lineage` — append-only LC011 events

`id` PK; `source_record_uuid → registry`; `seq BIGINT` with `UNIQUE
(source_record_uuid, seq)` (per-identity monotonic); `event_type CHECK IN` the
**13 LC011 mutation events** (`RENAME, MOVE, COLLECTION_CHANGE, CASE_CORRECTION,
CANONICALIZATION_CORRECTION, CONTENT_CORRECTION, METADATA_CORRECTION, DELETE,
RESTORE, SPLIT, MERGE, REPLACED, MANUAL`) **plus two creation anchors**
(`GENESIS`, `NATIVE_CREATE`); `occurred_at`, `actor`, `from_value`, `to_value`,
`related_source_record_uuid` (shape-checked UUID, for split/merge/replaced),
`relationship_role CHECK IN ('PARENT','CHILD','SURVIVOR','NON_SURVIVOR','SUPERSEDES','SUPERSEDED_BY')`,
`reason` (NOT NULL), `evidence_ref`, `recorded_at`.

`LINEAGE_UPDATE_ALLOWED = NO`, `LINEAGE_DELETE_ALLOWED = NO` — enforced by
`trg_pil_no_update` / `trg_pil_no_delete` (SQLite) and `trg_pil_append_only`
(PG `BEFORE UPDATE OR DELETE`). The repository also rejects unknown
`event_type` before touching the DB. The only documented exception is
`downgrade_for_isolated_test()` (drops the whole candidate for a disposable
fixture) — no normal-code update/delete path exists.

### 2.4 `puzzle_identity_bootstrap_receipt` — once-only genesis guard

`receipt_sha256` PK; **`bootstrap_singleton TEXT NOT NULL DEFAULT 'GENESIS'
UNIQUE CHECK (bootstrap_singleton = 'GENESIS')`** — at most one row can ever
exist, so a second genesis bootstrap `INSERT` fails with a UNIQUE violation
(`SECOND_GENESIS_BOOTSTRAP_FAILS_CLOSED = YES`). Carries the full LC012-R2
immutable tuple (`frozen_corpus_sha256`, `record_count`, `namespace_uuid`,
`canonicalisation_rules_version`, `genesis_key_spec_version`,
`historical_tree_commit`, `historical_tree_manifest_sha256`,
`historical_rename_map_sha256`, `genesis_record_manifest_sha256`,
`proposed_uuid_list_sha256`), `status CHECK IN ('APPLIED','ABORTED')`,
`identities_written`, `applied_at`, `applied_by`. Immutable (trigger).

`GENESIS_RECEIPT_REFERENCE_SUPPORTED = YES` — genesis registry rows carry
`genesis_receipt_ref` (a reference), the receipt facts live in one row, **not
duplicated per identity**.

## 3. Indexes

`idx_pir_status_kind`, `idx_pir_receipt_ref`, `idx_pia_uuid`, `idx_pil_uuid_seq`,
`idx_pil_event_type`, `idx_pil_related_uuid`, and the partial
`uq_pia_current_alias` (§2.2). All `CREATE … IF NOT EXISTS`.

## 4. Immutability enforcement (DB-level, both dialects)

| invariant | SQLite | PostgreSQL |
|---|---|---|
| `source_record_uuid` immutable | `trg_pir_uuid_immutable` `BEFORE UPDATE OF source_record_uuid … WHEN NEW IS NOT OLD … RAISE(ABORT)` | `trg_pir_uuid_immutable` → `puzzle_identity_reject_uuid_change()` (`RAISE EXCEPTION` on `IS DISTINCT FROM`) |
| creation facts immutable | `trg_pir_creation_facts_immutable` `BEFORE UPDATE OF identity_kind, identity_version, origin_class, created_at, created_by_process, creation_reason, genesis_receipt_ref` | `puzzle_identity_reject_creation_fact_change()` |
| alias binding immutable | `trg_pia_binding_immutable` | `puzzle_identity_reject_alias_binding_change()` |
| lineage append-only | `trg_pil_no_update` + `trg_pil_no_delete` | `trg_pil_append_only` `BEFORE UPDATE OR DELETE` → `puzzle_identity_reject_write()` |
| bootstrap receipt immutable | `trg_pibr_no_update` + `trg_pibr_no_delete` | `trg_pibr_append_only` |

`SOURCE_RECORD_UUID_UNIQUE = YES` (PK), `SOURCE_RECORD_UUID_MUTABLE = NO` (trigger
+ no repository update path). There is **no** application code path that
UPDATEs `source_record_uuid`.

## 5. Repository — `puzzle_identity_store.py` (`PuzzleIdentityStore`)

Every mutating method runs inside a `SAVEPOINT` (`_unit(tag)` — RELEASE on
success, `ROLLBACK TO` + `RELEASE` + re-raise on error), independent of the
caller's outer transaction. `IDENTITY_CREATE_TRANSACTION_BOUNDARY = PASS`:
`create_historical_genesis_identity` / `create_native_identity` write the
registry row **+ all initial aliases + the creation lineage row** atomically —
a mid-way constraint violation leaves **zero** partial rows (test Q).

| operation | UUID behaviour |
|---|---|
| `create_historical_genesis_identity` | caller-supplied **UUIDv5** (version-checked), `genesis_receipt_ref` required, aliases `CANONICAL_SOURCE_KEY` + `CURRENT_SOURCE_PATH` (+ `HISTORICAL_SOURCE_PATH`, `LEGACY_QUESTION_ID` when given), lineage `GENESIS`. |
| `create_native_identity` | **UUIDv4** minted once (or caller-supplied, version-checked), no receipt ref, lineage `NATIVE_CREATE`. `source=''` authoring is supported by simply omitting `current_source_path`. |
| `record_rename` / `record_move` | **same `source_record_uuid`**; supersede current `CURRENT_SOURCE_PATH` alias, insert new one, append `RENAME`/`MOVE`. `RENAME_MINTS_NEW_UUID = NO`, `MOVE_MINTS_NEW_UUID = NO`. |
| `record_content_correction` | **fails closed** unless `reviewed=True` — `SAME_PATH_CHANGED_CONTENT_AUTO_PRESERVE = NO`. On review, appends `CONTENT_CORRECTION` only (no UUID change). |
| `record_replacement` | target identity must already exist and differ; old retired; lineage `REPLACED` on both (`SUPERSEDED_BY` / `SUPERSEDES`). `REPLACEMENT_REUSES_OLD_UUID = NO`. |
| `record_split` | children must be pre-existing distinct identities ≠ parent; parent retired; lineage `SPLIT` (`PARENT`/`CHILD`). `SPLIT_CHILD_REUSES_PARENT_UUID = NO`. |
| `record_merge` | explicit `survivor`; non-survivors retired; lineage `MERGE` (`SURVIVOR`/`NON_SURVIVOR`). No silent UUID collapse. |
| `retire_identity` / `restore_identity` | `identity_status` ACTIVE↔RETIRED + lineage `DELETE`/`RESTORE`. **Deletion is never identity loss** — retired identities stay in the registry and stay resolvable (test N). |
| `resolve(alias_kind, alias_value, alias_context)` | `EXACT` (one current binding) / `MISSING` (none) / raises `AmbiguousAliasError` (>1 current — impossible under `uq_pia_current_alias`, still checked). Retired identities resolve with `status='RETIRED'` and the UUID still returned. No fuzzy/automatic merges. |

## 6. Dual-ID window

`DUAL_ID_WINDOW_SUPPORTED = YES`, `LEGACY_ID_REMOVED = NO`. The legacy integer
`question_id` keeps working in existing runtime unchanged; `source_record_uuid`
lives **alongside** it as `LEGACY_QUESTION_ID` aliases in the new table. LC013
wires **no** call sites — `review_log`, SRS, analytics, admin, Adventure, and
the Learning UI are untouched. A later task maps them over the alias table at
its own pace.

## 7. Bootstrap interface — `puzzle_identity_genesis_bootstrap.py` (`GenesisBootstrap`)

`BOOTSTRAP_INTERFACE_DEFINED = YES`, `REAL_BOOTSTRAP_RUN = NO`.

1. `preflight()` — validates the LC012-R2 receipt **first**: in canonical mode
   every immutable field must equal the frozen constant (imported from
   `tools/lc012_p2_genesis_freeze.py`, `tools/lc012_sgf_source_tree_freeze.py`,
   `tools/lc011_identity_registry_prototype.py` — never redefined here); the
   receipt's own once-only gate must be `safe_to_run`; every manifest row must
   carry a distinct **UUIDv5** and a valid `provenance_relation`
   (`DIRECT_PATH_MATCH` / `HISTORICAL_RENAME_MATCH`); the target registry must be
   empty with no prior bootstrap row.
2. `apply(applied_by, when, dry_run=False)` — one `SAVEPOINT`: INSERT the
   `bootstrap_receipt` row (singleton guard) then create every genesis identity;
   any failure rolls the whole thing back.
3. **Idempotency-safe**: re-running the *same* receipt returns `ALREADY_APPLIED`
   (no-op); a *different* receipt raises (`SECOND_GENESIS_BOOTSTRAP_FAILS_CLOSED`).

Tested only with a **3-row synthetic manifest / synthetic UUIDs**
(`require_canonical_genesis=False`) and with canonical-mode preflight rejecting a
non-frozen receipt. The real 42,804-row bootstrap is **not** invoked anywhere in
LC013.

## 8. Drift / fail-closed coverage (`tests/test_lc013_puzzle_identity_registry.py`, 24 tests)

A create-genesis · B create-native-v4 (+ v5-rejected) · C duplicate UUID ·
D UUID + creation-fact mutation rejected · E legacy alias resolve · F historical
path alias · G rename keeps UUID · H move keeps UUID · I append lineage ·
J lineage UPDATE **and** DELETE rejected · K replacement → new UUID ·
L split children → new UUIDs · M merge explicit survivor · N retired identity
still resolvable (+ restore) · O ambiguous alias fails closed (partial-unique +
resolver guard) · P unsupported lineage event rejected (repository + CHECK) ·
Q transaction rollback leaves zero partial rows · content-correction fail-closed
without review · migration additive+reversible+idempotent · PG DDL shape ·
bootstrap synthetic apply + idempotency · bootstrap non-empty registry fail ·
bootstrap canonical-mode rejects non-frozen receipt · bootstrap rejects non-v5
rows.

## 9. What LC013 intentionally does NOT do

- **No genesis population.** The 42,804 frozen identities are not written to any
  canonical/Production persistence. `GENESIS_BOOTSTRAP_EXECUTED = NO`,
  `IDENTITY_REGISTRY_PRODUCTION_POPULATION = NO`. The LC012-R2 bootstrap gate
  stays unconsumed.
- **No `app.py` change** (`APP_PY_CHANGED = NO`; D038 owns the `app.py` writer),
  **no `add_question()` runtime change** (`ADD_QUESTION_RUNTIME_CHANGED = NO`),
  **no resolver call-site wiring**, no SRS / `review_log` / Adventure / Learning
  UI change (`USER_VISIBLE_RUNTIME_CHANGED = NO`).
- **No production DB migration.** `PRODUCTION_DB_MIGRATION = NO`,
  `GO_PRODUCTION_DB_MIGRATION` not granted. The migration is a *candidate* — a
  governed local/test runner decides when to apply it.
- **No MANUAL-marker policy.** `MANUAL_MARKER_POLICY_DECIDED = NO` — the generic
  nullable `provenance_note` is reserved without semantics.
- **No corpus / SGF / genesis-artifact mutation** (`CORPUS_MUTATION = NO`,
  `SGF_MUTATION = NO`, `GENESIS_ARTIFACT_MUTATION = NO`), no master merge, no
  deploy.

## 10. What comes after LC013

1. **Owner-gated genesis bootstrap** — feed the real LC012-R2 receipt +
   42,804-row manifest to `GenesisBootstrap.apply()` in a governed offline run
   against the canonical DB, once, behind an explicit `GO` gate.
2. **Resolver wiring** — map `review_log.question_id` / admin / SRS reads to
   `source_record_uuid` via the alias table, exact/high-confidence only.
3. **`add_question()` integration** — new native puzzles call
   `create_native_identity()` (UUIDv4, persisted once) instead of leaving
   `source=''` identity-less. Owned by the authoring/`app.py` line, not here.
4. **MANUAL-marker policy** — a separate owner decision; then attach semantics to
   the reserved field.
