# LC020-R2 — Genesis Bootstrap Execution Preflight & Runbook Revalidation

**RESULT: `PASS_LC020_R2_GENESIS_BOOTSTRAP_EXECUTION_PREFLIGHT_AND_RUNBOOK_REVALIDATION`.**
`GENESIS_IMPLEMENTATION_REPAIR = PASS` · `GENESIS_EXECUTION_PREFLIGHT = PASS`.
`READY_FOR_LC020_R1_CANONICAL_MERGE_PREFLIGHT = YES`.
**`PRODUCTION_GENESIS_EXECUTION_READY = NO`** — the LC020-R1 repair is not yet on
canonical master and neither Owner gate is granted.

Revalidation only. `SOURCE_CHANGED = NO`, `MASTER_MERGE = NO`,
`MASTER_PUSHED_BY_THIS_TASK = NO`, no Production touch, no Owner gate consumed.

- Repair head under test: `363f76e566e1c939c6dde0ec610cd9a34bb3993f` (LC020-R1,
  `LC020_R1_HEAD_EXACT = YES`).
- `FRESH_ORIGIN_MASTER_HEAD` at fetch: `c1a55daebc411df46ca4bbfef6c0b814c813ec73`
  (tree `50c3c74fa8095e02cd507f7745efafcfcde4ae6f`). `MASTER_ADVANCED = YES`
  (`8b34994b5 → c1a55daeb`, 3 commits: E055 Zone 3 Goblin Cave vertical slice).
  `GENESIS_RELEVANT_MASTER_DELTA = NONE` — E055 touches `app.py`
  (`_settle_monster_defeat_in_tx` + `adventure_zone3_monster_authority` imports)
  but **not** `puzzle_identity_store.py`, `puzzle_identity_genesis_bootstrap.py`,
  `migrations/puzzle_identity_registry_v1.py`, `identity_read_adapter.py`,
  `grimoire_api.py`, any LC019-W1/W2 reader group, `rewards_sync` /
  `fold_identity`, or the receipt/manifest/rename-map artifacts.
  `FORWARD_RECONCILIATION_REQUIRED = NO` (the 2-file repair does not overlap the
  E055 app.py delta).

---

## 1. Preflight evidence (disposable / read-only)

| # | check | result |
|---|---|---|
| §2 | exact frozen artifacts | `MIGRATION_SHA256 = ad5bd5bc4c3d501df694e5b05835bb0426964ddb4e98bc64d291960823d6f766`; `BOOTSTRAP_RECEIPT_SHA256 = 834eb17fb3bedfa303bf510d24a2734348ddda1204c4811ce80d4c9c89c6f54c`; `IDENTITY_MANIFEST_SHA256 = ee7b1bc4a5f8bb339904a957f236c742a48ea68f6ab4285083e089e0267e4828` (row count 42804); `UUID_LIST_SHA256 = cb47e9d63d2e44f06b24772436380a8e1ce4f199ae64455bfc3891da446da2f2`; `RENAME_MAP_SHA256 = 473a80a3664517f7c23db9071948d17cc89053f321ae5ace58ae27e94de7923d`; `FROZEN_QUESTIONS_SHA256 = 88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff`. `RECEIPT_MANIFEST_BINDING = PASS`, `MANIFEST_UUID_UNIQUE_COUNT = 42804`, `DUPLICATE_UUID_COUNT = 0`. Full manifest regenerated read-only from `D:\go-website\questions.json` + `C:\go-website` `git archive`/`cat-file` (`C_GO_WEBSITE_MUTATED = NO`, HEAD `415a321db` unchanged). |
| §3 | collision census | `LEGACY_ID_COLLISION_GROUP_COUNT = 11`, `LEGACY_ID_COLLISION_RECORD_COUNT = 22`, `LEGACY_ID_UNIQUE_VALUE_COUNT = 42793`; collided ids exactly `{40479, 40511, 40512, 40513, 62011, 63382, 70450, 70752, 71238, 71240, 71244}`; `COLLISION_UUID_DISTINCTNESS = PASS`; `COLLISION_POLICY_SUPPORTED = YES`, `UNSUPPORTED_COLLISION_COUNT = 0`. Collision-present is **not** manifest-invalid. |
| §4 | pre-genesis no-op | `BOOTSTRAP_HOT = FALSE`; `group_key = ("legacy", question_id)`; 80-id batch all LEGACY; `RESOLVER_LOOKUPS_BEFORE_GENESIS = 0` (all `resolve_*` poisoned to raise; nothing raised). `PRE_GENESIS_NOOP_SEMANTICS_PRESERVED = YES`, `REQUEST_TIME_UUID_CREATION = NO`. |
| §5 | migration | `SQLITE_MIGRATION_APPLY = PASS` (indexes `uq_pia_current_alias`, `uq_pia_one_current_path`; `validate_schema` OK; reapply `IDEMPOTENT_OK`). `POSTGRES_MIGRATION_APPLY = PASS` (real disposable PostgreSQL — see §8). `UNIQUE_CURRENT_ALIAS_CONSTRAINT_PRESERVED = YES`. |
| §6 | genesis preflight | `GENESIS_PREFLIGHT = PASS`, 0 problems. `EXPECTED_IDENTITY_COUNT = 42804`. `LEGACY_COLLISION_POLICY = FAIL_CLOSED_AMBIGUOUS`. `COLLISION_CENSUS_BEFORE_MUTATION = YES`. Fails closed on: manifest-hash / receipt / uuid-list / static-fact / historical-pin / canon-version / row-count mismatch, duplicate UUID, uuid↔canonical-source mismatch, missing canonical_source, bad provenance_relation, uuidv4 row, migration absent, **collision-census drift**, **collision UUID collapse (unsupported)**. |
| §7 | **full SQLite Genesis** | `GENESIS_APPLY_SQLITE = PASS` (8.0 s). `IDENTITY_INSERT_COUNT = 42804`, `ACTIVE_IDENTITY_COUNT = 42804`, `GENESIS_LINEAGE_COUNT = 42804`, `BOOTSTRAP_RECEIPT_APPLIED_COUNT = 1`. `CURRENT_LEGACY_ALIAS_COUNT = 42782`, `NONCURRENT_COLLISION_ALIAS_COUNT = 22`. `BOOTSTRAP_HOT_BEFORE = FALSE → BOOTSTRAP_HOT_AFTER = TRUE`. `PARTIAL_APPLY_VISIBLE = NO`. `UNIQUE_CURRENT_ALIAS_CONSTRAINT_PRESERVED = YES` (0 duplicate current legacy alias values; index set unchanged). |
| §8 | **full PostgreSQL Genesis** | `POSTGRES_VERSION = 16.14` — see the §8 machine report (`lc020r2_pg_full_report.json`): migration + `validate_schema` PASS; `GENESIS_PREFLIGHT = PASS`; full 42,804-row `apply()` → `APPLIED`; `IDENTITY_COUNT = 42804`; `CURRENT_LEGACY_ALIAS_COUNT = 42782` + `NONCURRENT_COLLISION_ALIAS_COUNT = 22`; `HOT_AFTER = TRUE`; every one of the 11 collided ids → AMBIGUOUS (single + batch) + reader `("unresolved", id)`; non-collision sample → EXACT; `uq_pia_current_alias` still rejects a duplicate current insert; second apply → `ALREADY_APPLIED` (0 dup rows). `POSTGRES_GENESIS_APPLY = PASS`. |
| §9 | collision lookup contract | all 11 collided ids: `candidate count = 2`, `distinct canonical UUID = 2`; `resolve_legacy_question_id → AMBIGUOUS`; `resolve_many_legacy_question_ids → AMBIGUOUS`; `BootstrapGatedIdentityReader.key_for → UNRESOLVED`, `group_key = ("unresolved", legacy_id)`. **Never** `("uuid", arbitrary_member)`. `COLLISION_LEGACY_LOOKUP_FAIL_CLOSED = PASS`, `COLLISION_READER_FAIL_CLOSED = PASS`. |
| §10 | non-collision compat | 1,000-row deterministic sample: every id → `EXACT` with `source_record_uuid` == its manifest `source_record_uuid_proposed`; unknown id → `MISSING`. `NON_COLLISION_LEGACY_ALIAS_COMPATIBILITY = PASS`. No existing non-collision alias behaviour regressed (a genesis with no collisions writes 0 not-current LEGACY_QUESTION_ID aliases). |
| §11 | hot reader groups | `HOT_READER_GROUP_COUNT = 8` (grimoire `generate_daily_training` + the 7 LC019-W2 app.py groups all key through `BootstrapGatedIdentityReader.key_for` / `keys_for` / `group_keys_for`). 5,000-id batch → 5,000 `("uuid", …)` / 0 `("unresolved", …)` (that slice holds no collision id); spot non-collision id → `("uuid", <its source_record_uuid>)`. `HOT_GROUP_KEY_CANONICALIZATION = PASS`. |
| §12 | rewards_sync protection | `REWARDS_SYNC_RAW_ID_SEMANTICS_PRESERVED = YES` (`fold_identity=False` present on this head's `app.py`; LC020-R1 changed no `app.py`). `LC019_W1B_IMPLEMENTED = NO`. |
| §13 | second-run safety | full-DB second `apply()` (same receipt) → `ALREADY_APPLIED`; `DUPLICATE_IDENTITY_ROWS_CREATED = 0`, `DUPLICATE_ALIAS_ROWS_CREATED = 0`, `DUPLICATE_LINEAGE_ROWS_CREATED = 0`. Tampered receipt (`historical_tree_commit` altered) → `GenesisBootstrapError` (fail closed). |
| §14 | failure / rollback matrix | `INVALID_INPUT_DB_MUTATED = NO`, `INVALID_INPUT_HOT_FLIPPED = NO`, `PARTIAL_APPLY_VISIBLE = NO`. 15 cases: wrong manifest hash / receipt namespace / historical pin / uuid-list sha / canon version / row-count mismatch / duplicate UUID / uuid↔canonical mismatch / missing canonical_source / bad provenance / uuidv4 row → `GenesisBootstrapError` at preflight; migration absent → `OperationalError` at preflight; **collision census drift** → `GenesisBootstrapError`; **collision UUID collapse (unsupported)** → `GenesisBootstrapError`. Plus a clean **forced mid-`apply()` exception** (RuntimeError at row 11 of a 20-row synthetic genesis, `require_canonical_genesis=False`): the one SAVEPOINT rolled back completely — registry 0 / alias 0 / lineage 0 / bootstrap_receipt 0, `hot` FALSE. |

---

## 2. PHASE 1 runbook — `GO_PRODUCTION_DB_MIGRATION`

Applies the empty additive schema. Independent of Phase 2.

```
PRECHECKS
  - repo at the reviewed head that carries the LC020-R1 repair; migration
    migrations/puzzle_identity_registry_v1.py  sha256
    ad5bd5bc4c3d501df694e5b05835bb0426964ddb4e98bc64d291960823d6f766
  - full DB backup taken; backup id recorded
  - to_regclass('public.puzzle_identity_registry')  ->  NULL  (absent)
  - bootstrap_state().hot  ->  False
RUNNER
  - project migration runner applies puzzle_identity_registry_v1.upgrade(conn)
    (additive only; caller owns the transaction)
POST-MIGRATION CHECK
  - the 4 puzzle_identity_* tables exist
  - indexes uq_pia_current_alias AND uq_pia_one_current_path exist
  - validate_schema(conn) passes
  - every puzzle_identity_* table row count == 0
  - bootstrap_state() -> {tables_present: true, genesis_applied: false,
                          identity_count: 0, hot: false}
  - LC019-W1/W2 reader smoke: group_key still ("legacy", question_id);
    0 resolver queries; /api/training/daily, /api/recommend, /api/map-progress,
    /api/curriculum/summary, /api/quest-board[/progress], /api/srs/due, adventure
    state + grimoire generate_daily_training responses byte-identical to pre-migration
ABORT / ROLLBACK
  - any check fails -> STOP, restore from the backup
```

## 3. PHASE 2 runbook — `GO_GENESIS_BOOTSTRAP`

Mints the 42,804 historical identities, once. Requires Phase 1 complete.

```
PRECONDITIONS
  - Phase 1 done; puzzle_identity_* tables present and EMPTY; hot == False
  - a fresh full DB backup immediately before Phase 2, id recorded
EXACT ARTIFACT HASHES (verifier recomputes all)
  receipt bytes sha256        834eb17fb3bedfa303bf510d24a2734348ddda1204c4811ce80d4c9c89c6f54c
  rename-map bytes sha256      473a80a3664517f7c23db9071948d17cc89053f321ae5ace58ae27e94de7923d
  genesis_record_manifest_sha256  ee7b1bc4a5f8bb339904a957f236c742a48ea68f6ab4285083e089e0267e4828
  proposed_uuid_list_sha256       cb47e9d63d2e44f06b24772436380a8e1ce4f199ae64455bfc3891da446da2f2
  frozen corpus sha256        88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff
  P2 tree pin                 b162f9e72b93b73c08c1b044f365cb9287efae70 : SGF題庫
                              (tree_manifest 12fcab4aa372e16828d7bf1f5e06e440897ab4aaa097b2a256ba33db4e935d53)
REGENERATE THE 42,804-ROW MANIFEST (read-only, disposable, ~140-160 s)
  git -C <C:\go-website copy> archive b162f9e72 SGF題庫   -> extract
  git -C <C:\go-website copy> archive de7cd979d8 SGF題庫   -> extract
  git -C <C:\go-website copy> cat-file blob b162f9e72:questions.json  -> file
  tools/lc012_p2_genesis_freeze.run(snapshot=<frozen questions.json>,
       b162_tree_root=..., de7_tree_root=..., b162_corpus=..., out_dir=<tmp>)
  -> out/genesis_record_manifest_full.json (rows)
COLLISION CENSUS (before any mutation)
  legacy_id_collision_census(rows) ->
    legacy_id_collision_group_count  == 11
    legacy_id_collision_record_count == 22
    collided_ids == {40479, 40511, 40512, 40513, 62011, 63382, 70450, 70752, 71238, 71240, 71244}
    unsupported_collision_count == 0   (every member of every group has a distinct source_record_uuid)
GENESIS PREFLIGHT
  v  = GenesisReceiptVerifier(receipt_bytes, manifest_rows=rows, rename_map_bytes,
        require_canonical_genesis=True)
  bs = GenesisBootstrap(PuzzleIdentityStore(canonical_conn), v)
  pf = bs.preflight()
  EXPECTED: pf.ok == True ; problems == [] ;
            genesis_records 42804 ; direct_path_match_count 41886 ;
            historical_rename_match_count 918 ; missing 0 ; ambiguous 0 ;
            uuid_canonical_source_binding_mismatch 0 ;
            legacy_id_collisions.collision_policy == "FAIL_CLOSED_AMBIGUOUS" ;
            legacy_id_collisions.collision_policy_supported == True ;
            prior_bootstrap == None ; registry_count == 0
  bs.apply(applied_by=<operator>, when=<UTC iso>, dry_run=True) -> {DRY_RUN, would_write: 42804}
GENESIS APPLY (once)
  bs.apply(applied_by=<operator>, when=<UTC iso>) -> {status: APPLIED, identities_written: 42804}
POST-APPLY COUNTS
  puzzle_identity_registry                                            42804
  puzzle_identity_registry WHERE identity_kind='HISTORICAL_GENESIS'   42804
  puzzle_identity_registry WHERE identity_status='ACTIVE'             42804
  puzzle_identity_alias WHERE alias_kind='CANONICAL_SOURCE_KEY'       42804
  puzzle_identity_alias WHERE alias_kind='CURRENT_SOURCE_PATH'        42804
  puzzle_identity_alias WHERE alias_kind='LEGACY_QUESTION_ID' AND is_current      42782   (42804 - 22)
  puzzle_identity_alias WHERE alias_kind='LEGACY_QUESTION_ID' AND NOT is_current       22   (the 11 collision groups)
  (SELECT ... GROUP BY alias_value HAVING COUNT(*)>1 on current LEGACY_QUESTION_ID)  0 rows
  puzzle_identity_lineage WHERE event_type='GENESIS'                  42804
  puzzle_identity_bootstrap_receipt WHERE status='APPLIED'            1
  bootstrap_state().hot                                              True
READER SMOKE TESTS (post-genesis)
  - key_for(<known non-collision qid>).group_key == ("uuid", <its source_record_uuid>)
  - each of the 11 collision ids: resolve_legacy_question_id -> AMBIGUOUS (2 candidates);
    key_for -> ("unresolved", id)   (NEVER ("uuid", <one member>))
  - an unknown legacy id -> ("legacy", id)
  - grimoire generate_daily_training + the 7 app.py routes return only raw integer
    question_ids; no request-time UUID is minted
SECOND-RUN SAFETY
  - bs.apply() again with the same receipt -> {status: ALREADY_APPLIED, idempotent: true}
  - any other / tampered receipt -> GenesisBootstrapError (bootstrap_singleton UNIQUE)
ABORT CONDITIONS (any -> STOP, restore from the pre-Phase-2 backup)
  - preflight not ok / any expected count wrong / apply raises / hot not True after apply /
    census drift / unsupported collision
RECOVERY CONTRACT
  - a failed apply auto-rolls-back (one SAVEPOINT + post-write count assertion) — verify all
    counts back to 0 and hot False, then investigate.  A bad *successful* genesis has no
    in-product undo -> restore the backup.
```

No secrets appear in this runbook. Neither gate is granted or consumed by LC020-R2.

---

## 4. Owner decision packet

- **`WHAT_DB_MIGRATION_CHANGES`** — adds 4 empty tables
  (`puzzle_identity_registry` / `_alias` / `_lineage` / `_bootstrap_receipt`) + 2
  partial-unique indexes. Purely additive; no existing table/column/index/row
  touched. Proven to apply cleanly and idempotently on disposable SQLite and
  disposable PostgreSQL 16.14.
- **`WHAT_GENESIS_CHANGES`** — one `bootstrap_receipt` row + per frozen record: one
  `HISTORICAL_GENESIS` registry row, its `CANONICAL_SOURCE_KEY` /
  `CURRENT_SOURCE_PATH` / (`HISTORICAL_SOURCE_PATH` for the 918 renamed) aliases,
  one `GENESIS` lineage row, and a `LEGACY_QUESTION_ID` alias — **current for the
  42,782 unique legacy ids, not-current for the 22 collision members**.
  `bootstrap_state().hot` becomes `True` only after all rows commit.
- **`WHY_CURRENT_RUNTIME_IS_NOOP_BEFORE_HOT`** — in every environment today the
  `puzzle_identity_*` tables are absent → `_identity_tables_present()` is False →
  LC019-W1/W2 readers use `("legacy", question_id)` and never query the resolver.
  Tables present but no receipt → `hot` still False, readers still legacy.
- **`WHAT_HOT_TRUE_CHANGES`** — each LC019 reader's `group_key` switches from
  `("legacy", question_id)` to `("uuid", source_record_uuid)` for the 42,782
  ids that resolve EXACT; content-duplicate legacy ids that share a
  `source_record_uuid` fold to one bucket; **the 11 legacy-id collision groups
  resolve `AMBIGUOUS` → `("unresolved", id)`, never bound to one member**;
  unknown ids keep `("legacy", id)`. Returned/answerable `question_id` stays a
  raw integer everywhere; `rewards_sync` stays raw-id.
- `IDENTITY_COUNT = 42804` · `COLLISION_GROUP_COUNT = 11` ·
  `COLLISION_RECORD_COUNT = 22` · `COLLISION_POLICY = FAIL_CLOSED_AMBIGUOUS`.
- **Unchanged**: question content, judge / marker semantics, `正解です` / `正着`
  vocabulary policy, `rewards_sync` raw-id semantics, Shop / Revenue, Adventure
  rewards, player balances, payments, Production app / static assets. LC019-W1B
  not implemented; `add_question()` → `create_native_identity()` UUIDv4 not
  implemented.
- **Failure / rollback** — one SAVEPOINT with a post-write count assertion; any
  failure rolls the whole thing back, `hot` stays False (proven for 15 abort
  cases + a forced mid-apply exception). Same receipt again → idempotent no-op;
  different receipt → fail closed. A bad *successful* genesis → restore the
  pre-Phase-2 backup.
- **Gates required, both currently `NOT_GRANTED`**: `GO_PRODUCTION_DB_MIGRATION`
  (Phase 1), `GO_GENESIS_BOOTSTRAP` (Phase 2). They must not be combined. And
  before either can be consumed, the LC020-R1 repair must first be admitted to
  canonical master (`LC020_R3_GENESIS_REPAIR_CANONICAL_MERGE_PREFLIGHT`).

---

## 5. Test matrix (§19)

Repair-head regression (`363f76e56`): LC011-LC017 + LC019-W1/W2 + genesis +
registry/alias/lineage + `DualIdReadWindow` + `BootstrapGatedIdentityReader` +
`tests/test_lc020_r1_genesis_legacy_id_collision.py` — green (LC020-R1 report:
130 passed / 46 skipped + 143 passed / 25 skipped / 1 pre-existing D034-R1
disposable-PG flake + 8 passed / 1 C:-gated skip). This R2 preflight adds the
full disposable SQLite genesis, the full disposable PostgreSQL 16.14 genesis, and
the extended failure/rollback matrix above. `TASK_INTRODUCED_FAILURES = 0`.

`NEXT_TASK = LC020_R3_GENESIS_REPAIR_CANONICAL_MERGE_PREFLIGHT_001`.
