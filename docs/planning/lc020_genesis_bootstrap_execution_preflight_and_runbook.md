# LC020 — Genesis Bootstrap Execution Preflight & Owner Runbook

**RESULT: `BLOCKED_LC020_GENESIS_BOOTSTRAP_EXECUTION_PREFLIGHT_AND_RUNBOOK`.**
**`GENESIS_EXECUTION_READY = NO`.** A real implementation gap was found and, per
task §19, is reported — not fixed here. `NEXT_TASK = LC020_GENESIS_IMPLEMENTATION_REPAIR`.

Everything that could be proven in a disposable / non-Production environment was
proven green **except the one-shot `GenesisBootstrap.apply()` against the exact
authorized 42,804-row manifest**, which cannot complete because the frozen corpus
carries 11 `legacy_question_id` collision groups (22 records) and
`create_historical_genesis_identity()` writes an unconditional *current*
`LEGACY_QUESTION_ID` alias per identity.

- Base: `origin/master` `62cd841a3af78a66c4c5aba16cdfebb7814513da`
  (tree `dc2dcaaad74a29afc3c7da909d84298ea303d0c0`). `LC019_W1_PRESENT = YES`,
  `LC019_W2_PRESENT = YES`.
- Mode: READ-ONLY preflight. `DISPOSABLE_DB_ONLY = YES`, `PRODUCTION_DB_USED = NO`,
  `PRODUCTION_GENESIS_APPLY = NO`, `GENESIS_GATE_CONSUMED = NO`,
  `PRODUCTION_DB_MIGRATION_GATE_CONSUMED = NO`, `MASTER_MERGE = NO`,
  `APP_PY_CHANGED = NO`, `GRIMOIRE_API_CHANGED = NO`,
  `COMMUNITY_LEADERBOARD_REWARDS_CHANGED = NO`, `SECRET_KEY_TOUCHED = NO`.

---

## 1. THE BLOCKER — legacy_question_id collision in the frozen corpus

| field | value |
|---|---|
| where | `GenesisBootstrap.apply()` → `PuzzleIdentityStore.create_historical_genesis_identity()` → `_insert_alias("LEGACY_QUESTION_ID", str(legacy_question_id), context=DEFAULT_ALIAS_CONTEXT, is_current=True)` |
| constraint hit | `uq_pia_current_alias  ON (alias_kind, alias_value, alias_context) WHERE is_current` |
| surfaces as | raw `sqlite3.IntegrityError` / `psycopg2.errors.UniqueViolation` **mid-apply()** |
| colliding groups | **11** `legacy_question_id`s, **22** manifest rows: `40479, 40511, 40512, 40513, 62011, 63382, 70450, 70752, 71238, 71240, 71244` |
| each group | has a **distinct** `source_record_uuid` (genesis correctly separates them) but the same integer `legacy_question_id` |
| verifier catches it? | **NO** — `GenesisReceiptVerifier.verify()` does not check legacy-id uniqueness |
| preflight catches it? | **NO** — `GenesisBootstrap.preflight()` does not check it |
| fail-closed intact? | **YES** — the one SAVEPOINT rolls back: registry 0 / alias 0 / lineage 0 / bootstrap_receipt 0, `bootstrap_state().hot == False`, `PARTIAL_APPLY_VISIBLE = NO` |

These 11 groups are the corpus's known legacy-`id` collisions (LC008/LC010:
`id` collides in 11 groups). The genesis manifest is *correct* — every record gets
its own `source_record_uuid`. The gap is that `create_historical_genesis_identity`
records a **current** `LEGACY_QUESTION_ID` alias for every identity, and two
identities cannot both own the same current legacy alias.

### Repair is a design decision (LC020_GENESIS_IMPLEMENTATION_REPAIR)

The Owner / coordinator must choose how the 22 collision-member legacy aliases are
recorded. Candidate designs (not implemented here):

1. **Ambiguity-fail-closed (matches LC011 design).** For a `legacy_question_id`
   shared by >1 genesis identity, write each `LEGACY_QUESTION_ID` alias with
   `is_current = False` (or omit it). Then `resolve_legacy_question_id(40479)`
   returns `AMBIGUOUS`, LC019 readers keep those ids on the `("unresolved", id)`
   bucket, and the operator later promotes the correct binding per record. This is
   exactly the "legacy-`id` disambiguation" the identity foundation was built to
   enable.
2. **Distinguishing `alias_context`.** Give each collision member a per-record
   `alias_context` (e.g. the `record_index` or `canonical_source`). Keeps both
   current but forces every legacy read to supply context — larger blast radius on
   the LC014/LC015/LC019 read surface.
3. **Manifest-driven.** Add a `legacy_id_ambiguous` flag to the 22 rows in the
   LC012-R2 manifest generator and have `apply()` honour it. Changes an
   Owner-ratified immutable artifact shape → needs its own ratification.

Whichever is chosen, `GenesisReceiptVerifier` and/or `GenesisBootstrap.preflight()`
must also be extended to **detect the collision set up front** so it never again
surfaces as a raw DB error mid-apply.

---

## 2. What PASSED (disposable / read-only evidence)

| # | check | result |
|---|---|---|
| §3 | artifact discovery | migration `migrations/puzzle_identity_registry_v1.py` sha256 `ad5bd5bc4c3d501df694e5b05835bb0426964ddb4e98bc64d291960823d6f766`; receipt `docs/planning/lc012_p2_genesis_receipt.json` sha256 `834eb17fb3bedfa303bf510d24a2734348ddda1204c4811ce80d4c9c89c6f54c` (== KNOWN_RECEIPT_SHA256); rename map `docs/planning/lc012_p2_historical_rename_map.json` sha256 `473a80a3664517f7c23db9071948d17cc89053f321ae5ace58ae27e94de7923d` (== KNOWN); `GenesisBootstrap` impl `puzzle_identity_genesis_bootstrap.py`; frozen corpus `D:\go-website\questions.json` sha256 `88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff` (exact) |
| — | manifest regeneration | full 42,804-row manifest regenerated read-only in 157 s via `tools/lc012_p2_genesis_freeze.run()` from `D:\go-website\questions.json` + `git archive`/`git cat-file` of `b162f9e72` and `de7cd979d8` `SGF題庫` in `C:\go-website` (HEAD `415a321db` unchanged before/after → `C_GO_WEBSITE_MUTATED = NO`). `IDENTITY_MANIFEST_ROW_COUNT = 42804`. |
| §4 | receipt ↔ manifest binding | `RECEIPT_MANIFEST_BINDING = PASS`. recomputed `genesis_record_manifest_sha256 = ee7b1bc4a5f8bb339904a957f236c742a48ea68f6ab4285083e089e0267e4828` (== receipt); recomputed `proposed_uuid_list_sha256 = cb47e9d63d2e44f06b24772436380a8e1ce4f199ae64455bfc3891da446da2f2` (== receipt); `MANIFEST_ROW_COUNT = 42804`; `MANIFEST_UUID_UNIQUE_COUNT = 42804`; `DUPLICATE_UUID_COUNT = 0`; `DIRECT_PATH_MATCH_COUNT = 41886`; `HISTORICAL_RENAME_MATCH_COUNT = 918`; per-row `mint_genesis_uuid(canonical_source) == source_record_uuid_proposed` mismatch **0**; `MISSING_REQUIRED_IDENTITY_COUNT = 0`; `AMBIGUOUS_ALIAS_COUNT = 0` (alias-collision on the *legacy id*, not the alias value used by the verifier, is the separate §1 blocker). |
| §5 | disposable migration | `MIGRATION_APPLY = PASS` (SQLite `:memory:`). Tables: `puzzle_identity_registry`, `puzzle_identity_alias`, `puzzle_identity_lineage`, `puzzle_identity_bootstrap_receipt`. Partial-unique indexes: `uq_pia_current_alias`, `uq_pia_one_current_path`. `validate_schema()` → OK. `MIGRATION_REAPPLY_BEHAVIOR = IDEMPOTENT_OK`. `UNEXPECTED_SCHEMA_OBJECTS = NONE`. |
| §6 | pre-genesis no-op | `BOOTSTRAP_HOT_BEFORE = FALSE` (`{tables_present: true, genesis_applied: false, identity_count: 0, hot: false}`). `GROUP_KEY_BEFORE_GENESIS = ("legacy", question_id)`; 50-id batch all `LEGACY`. `RESOLVER_LOOKUPS_BEFORE_GENESIS = 0` (all `DualIdReadWindow.resolve_*` poisoned to raise; nothing raised). `PRE_GENESIS_NOOP_SEMANTICS_PRESERVED = YES`. |
| §7 | genesis preflight / dry-run | `GENESIS_PREFLIGHT = PASS` (verifier checks only). `EXPECTED_INSERT_COUNT = 42804`, `EXPECTED_DIRECT_PATH_MATCH = 41886`, `EXPECTED_HISTORICAL_RENAME_MATCH = 918`, `EXPECTED_CONFLICT_COUNT = 0`, `EXPECTED_MISSING = 0`, `EXPECTED_AMBIGUOUS = 0`, `safe_to_run_trusted_without_recompute = false`. `apply(dry_run=True)` → `{status: DRY_RUN, would_write: 42804}`. |
| §8 | disposable apply (real manifest) | **`GENESIS_APPLY_DISPOSABLE = FAIL`** — `IntegrityError` on `uq_pia_current_alias` (see §1). `BOOTSTRAP_HOT_AFTER = FALSE`. registry/alias/lineage/bootstrap_receipt all `0`. `PARTIAL_APPLY_VISIBLE = NO`. |
| §9 | hot-state readers (clean synthetic genesis) | `HOT_READER_GROUP_COUNT = 8` (grimoire `generate_daily_training` + the 7 LC019-W2 app.py groups). After a *clean* 3-identity synthetic genesis: `reader.hot = True`; EXACT id → `("uuid", <genesis source_record_uuid>)`, `attachable = True`; a post-genesis second current alias for one legacy id → `("unresolved", id)`, **never** `("uuid", …)` (`AMBIGUITY_FAIL_CLOSED = PASS`); unknown legacy id → `("legacy", id)` (`LEGACY_ALIAS_READ_COMPATIBILITY = PASS`). `HOT_GROUP_KEY_CANONICALIZATION = PASS`. `REQUEST_TIME_UUID_CREATION = NO`. |
| §11 | apply-once / idempotency | first `apply()` → `APPLIED`; second `apply()` same receipt → `ALREADY_APPLIED` (`idempotent = true`); different-receipt `apply()` → `GenesisBootstrapError` (fail-closed). `DUPLICATE_IDENTITY_ROWS_CREATED = 0`, `DUPLICATE_ALIAS_ROWS_CREATED = 0`, `DUPLICATE_LINEAGE_ROWS_CREATED = 0`. |
| §12 | fail-closed abort matrix | `FAILURE_MATRIX = PASS`. 11/11 invalid-input cases leave `HOT_FLIPPED = false` **and** `DB_MUTATED = false`: wrong manifest sha in receipt, wrong receipt static fact (namespace), wrong historical tree pin, row-count mismatch, duplicate uuid, uuidv4 row, tampered canonical_source (same uuid), missing canonical_source, bad provenance_relation, migration absent (`OperationalError` at preflight), **and the legacy-id-collision full-corpus case (`PRECHECK = PASS`, `apply() → IntegrityError`, `DB_MUTATED = false`, `HOT_FLIPPED = false`)**. |

`REWARDS_SYNC_RAW_ID_SEMANTICS_PRESERVED = YES` (LC020 changed no source;
`rewards_sync` still calls `_stage_completion_state(..., fold_identity=False)` on
`62cd841a3`). `COMMUNITY_LEADERBOARD_REWARD_REBUCKET_CHANGED = NO`.
`LC019_W1B_IMPLEMENTED = NO`. `POST_GENESIS_NATIVE_UUID_CREATION_IMPLEMENTED = NO`.
`MARKER_POLICY_CHANGED = NO`. `VOCABULARY_BOUNDARY_CHANGED = NO`.

---

## 3. Owner decision packet

**A. What the Production migration changes.** `migrations/puzzle_identity_registry_v1.py`
adds 4 empty tables (`puzzle_identity_registry` / `_alias` / `_lineage` /
`_bootstrap_receipt`) plus 2 partial-unique indexes. Purely additive; no existing
table, column, index, or row is touched. Proven to apply cleanly and idempotently
on a disposable DB.

**B. What Genesis changes.** `GenesisBootstrap.apply()` inserts one
`puzzle_identity_bootstrap_receipt` row and, in the same SAVEPOINT, one
`HISTORICAL_GENESIS` `puzzle_identity_registry` row + its `CANONICAL_SOURCE_KEY` /
`CURRENT_SOURCE_PATH` / (`HISTORICAL_SOURCE_PATH`) / `LEGACY_QUESTION_ID` aliases +
one `GENESIS` lineage row **per frozen record**. `bootstrap_state().hot` becomes
`True` only after all rows commit.

**C. Why current behaviour is no-op.** In every environment today the
`puzzle_identity_*` tables are absent → `_identity_tables_present()` is `False` →
LC019-W1/W2 readers use `("legacy", question_id)` and never query the resolver.
Even with the tables present but no receipt, `bootstrap_state().hot` is `False`
and the readers stay on the legacy path.

**D. What flips when `hot` becomes `True`.** Every LC019 reader's `group_key`
switches from `("legacy", question_id)` to `("uuid", source_record_uuid)` for the
41,886+918 records whose identity resolves EXACT; content-duplicate legacy ids
that resolve to one `source_record_uuid` fold to one bucket (dedup / exclusion /
progress counting collapse them); AMBIGUOUS ids stay `("unresolved", id)` and are
never merged; MISSING ids keep `("legacy", id)`. Returned/answerable `question_id`
stays a raw integer everywhere. `rewards_sync` stays raw-id.

**E. Identities affected.** Exactly **42,804** (`41,886` DIRECT + `918`
HISTORICAL_RENAME). `42,804` distinct `source_record_uuid`. **11** legacy-id
collision groups (`22` records) currently **block** the apply — see §1.

**F. Failure / rollback guarantees.** `apply()` runs in one bounded SAVEPOINT with
a post-write `COUNT(*)` assertion; any failure rolls the whole thing back — no
partial identities, `hot` stays `False` (proven for 11 abort cases). A second run
with the same receipt is an idempotent no-op; a different receipt fails closed on
the `bootstrap_singleton='GENESIS'` UNIQUE. There is **no** in-product rollback of
a *successful* genesis (the receipt + immutability triggers are permanent by
design); recovery from a bad successful genesis = restore the DB from the
pre-Phase-B backup (Phase B precondition below).

**G. What stays unchanged.** `rewards_sync` raw-id semantics; LC019-W1B not
implemented; `add_question()` → `create_native_identity()` UUIDv4 not implemented;
marker policy for the 41,831 MANUAL records unchanged; `正解です` / `正着`
vocabulary boundary unchanged.

**H. Gates required (still NOT granted).**
`GO_PRODUCTION_DB_MIGRATION = NOT_GRANTED`, `GO_GENESIS_BOOTSTRAP = NOT_GRANTED`.
**Blocked on `LC020_GENESIS_IMPLEMENTATION_REPAIR` first** (§1).

---

## 4. Operator runbook (for the *future* authorized run, AFTER the §1 repair)

Two independent gates. They need not be consumed in one transaction — Phase A can
land days before Phase B.

### PHASE A — `GO_PRODUCTION_DB_MIGRATION`  (apply the empty schema)

```
PRECHECKS
  - repo at the reviewed master; migrations/puzzle_identity_registry_v1.py
    sha256 == ad5bd5bc4c3d501df694e5b05835bb0426964ddb4e98bc64d291960823d6f766
  - canonical DB reachable; take a full backup and record its id
  - SELECT to_regclass('public.puzzle_identity_registry')  ->  NULL  (absent)
  - bootstrap_state().hot  ->  False
MIGRATION RUNNER
  - the project migration runner applies migrations/puzzle_identity_registry_v1.py
    (upgrade(conn); caller owns the transaction)  -- additive only
POST-MIGRATION SCHEMA CHECK
  - the 4 puzzle_identity_* tables + uq_pia_current_alias + uq_pia_one_current_path exist
  - validate_schema(conn) passes
  - every table row count == 0
  - bootstrap_state()  ->  {tables_present: true, genesis_applied: false,
                            identity_count: 0, hot: false}
  - LC019-W1/W2 reader smoke: group_key still ("legacy", question_id); 0 resolver
    queries; /api/training/daily, /api/map-progress, /api/srs/due, /api/curriculum/summary,
    /api/quest-board[/progress], /api/recommend + grimoire generate_daily_training
    responses byte-identical to pre-migration
ABORT / ROLLBACK
  - any precheck fails, or any post-check fails  ->  STOP, restore from the backup
```

### PHASE B — `GO_GENESIS_BOOTSTRAP`  (mint the 42,804 historical identities, once)

```
PRECONDITIONS
  - §1 repair merged; GenesisBootstrap.preflight() rejects a legacy-id-collision
    manifest up front (no longer surfaces mid-apply)
  - Phase A complete; puzzle_identity_* tables present and EMPTY; hot == False
  - a fresh full DB backup taken immediately before Phase B, id recorded
EXACT ARTIFACT HASHES  (verifier recomputes all of these)
  - receipt bytes sha256      834eb17fb3bedfa303bf510d24a2734348ddda1204c4811ce80d4c9c89c6f54c
  - rename-map bytes sha256    473a80a3664517f7c23db9071948d17cc89053f321ae5ace58ae27e94de7923d
  - genesis_record_manifest_sha256   ee7b1bc4a5f8bb339904a957f236c742a48ea68f6ab4285083e089e0267e4828
  - proposed_uuid_list_sha256        cb47e9d63d2e44f06b24772436380a8e1ce4f199ae64455bfc3891da446da2f2
  - frozen corpus sha256      88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff
  - P2 tree pin               b162f9e72b93b73c08c1b044f365cb9287efae70 : SGF題庫
                             (tree_manifest 12fcab4aa372e16828d7bf1f5e06e440897ab4aaa097b2a256ba33db4e935d53)
REGENERATE THE 42,804-ROW MANIFEST  (read-only, disposable, ~160 s)
  git -C <C:\go-website copy> archive b162f9e72 SGF題庫  -> extract
  git -C <C:\go-website copy> archive de7cd979d8 SGF題庫  -> extract
  git -C <C:\go-website copy> cat-file blob b162f9e72:questions.json  -> file
  tools/lc012_p2_genesis_freeze.run(snapshot=<frozen questions.json>,
       b162_tree_root=..., de7_tree_root=..., b162_corpus=..., out_dir=<tmp>)
  -> out/genesis_record_manifest_full.json  (rows)
GENESIS PREFLIGHT
  v = GenesisReceiptVerifier(receipt_bytes, manifest_rows=rows,
        rename_map_bytes, require_canonical_genesis=True)
  bs = GenesisBootstrap(PuzzleIdentityStore(canonical_conn), v)
  pf = bs.preflight()
  EXPECTED:  pf.ok == True ; problems == [] ;
             genesis_records 42804 ; direct_path_match_count 41886 ;
             historical_rename_match_count 918 ; missing 0 ; ambiguous 0 ;
             uuid_canonical_source_binding_mismatch 0 ;
             prior_bootstrap == None ; registry_count == 0
  bs.apply(applied_by=<operator>, when=<UTC iso>, dry_run=True)  -> {DRY_RUN, would_write: 42804}
GENESIS APPLY  (once)
  bs.apply(applied_by=<operator>, when=<UTC iso>)  -> {status: APPLIED, identities_written: 42804}
POST-APPLY COUNTS
  puzzle_identity_registry                                  42804
  puzzle_identity_registry WHERE identity_kind='HISTORICAL_GENESIS'  42804
  puzzle_identity_registry WHERE identity_status='ACTIVE'   42804
  puzzle_identity_alias WHERE alias_kind='CANONICAL_SOURCE_KEY'  42804
  puzzle_identity_alias WHERE alias_kind='CURRENT_SOURCE_PATH'   42804
  puzzle_identity_alias WHERE alias_kind='LEGACY_QUESTION_ID' is_current   42804 - <collision demotions from the §1 repair>
  puzzle_identity_lineage WHERE event_type='GENESIS'        42804
  puzzle_identity_bootstrap_receipt WHERE status='APPLIED'  1
  bootstrap_state().hot                                     True
READER SMOKE TESTS  (post-genesis)
  - BootstrapGatedIdentityReader.key_for(<known qid>).group_key == ("uuid", <its source_record_uuid>)
  - a legacy-id-collision id (e.g. 40479) -> ("unresolved", "40479")  [after the §1 repair]
  - an unknown legacy id -> ("legacy", <id>)
  - grimoire generate_daily_training + the 7 app.py routes return only raw integer
    question_ids and no request-time UUID is minted
SECOND-RUN SAFETY
  - re-running bs.apply() with the same receipt -> {status: ALREADY_APPLIED, idempotent: true}
  - any other receipt -> GenesisBootstrapError (bootstrap_singleton UNIQUE)
ABORT CONDITIONS  (any -> STOP, restore from the pre-Phase-B backup)
  - preflight not ok / any expected count wrong / apply raises / hot not True after apply
RECOVERY CONTRACT
  - a failed apply auto-rolls-back (SAVEPOINT); verify all counts back to 0 and hot False,
    then investigate.  A bad *successful* genesis has no in-product undo -> restore backup.
```

No secrets appear in this runbook. Neither gate is granted or consumed by LC020.

---

## 5. Test matrix (§18)

`LC011-LC017 + LC019-W1 + LC019-W2 + genesis + identity-registry + alias/lineage +
dual-id + bootstrap-gated-reader` suites on `62cd841a3`: **150 passed, 45 skipped**
(`test_lc013_r1_genesis_binding.py` C:-path cases skip under this scratch worktree's
path layout — the equivalent full-manifest regen + digest binding is re-proven by
this preflight's own §4). `TASK_INTRODUCED_FAILURES = 0` (LC020 changed no
product source). `PRE_EXISTING_FAILURES = 0` in scope. `POSTGRES_PARITY` — the
disposable-PostgreSQL genesis path is covered by
`tests/test_lc013_r1_postgres_and_genesis.py` (part of the 45 skipped here for the
same path reason; the SQLite disposable apply in this preflight exercised the
identical code path and surfaced the §1 blocker).

`GENESIS_EXECUTION_READY = NO` · `RESULT = BLOCKED_LC020_GENESIS_BOOTSTRAP_EXECUTION_PREFLIGHT_AND_RUNBOOK` ·
`NEXT_TASK = LC020_GENESIS_IMPLEMENTATION_REPAIR`.
