# LC016 — LC011–LC015 Fresh-Master Identity-Lineage Reconciliation & Integration Candidate

Status: **one fresh-master integration candidate that carries the accepted
LC011–LC015 identity contracts as 30 pure-add files. No app.py wiring, no
genesis, no registry population, no UUID backfill, no production migration, no
master merge.**

Mode: RECONCILE / INTEGRATE / TEST / DOCUMENT / COMMIT / PUSH.

---

## 1. Fresh master

| field | value |
|---|---|
| `CURRENT_ORIGIN_MASTER` | `574b3eeb9641c48676e95d3744d204dffca1e1fa` |
| `EXPECTED_CANONICAL_MASTER` | `574b3eeb9641c48676e95d3744d204dffca1e1fa` — **match** |
| `merge-base(LC015, master)` | `c2a1dab3125cdef0cff381815d3d995bdd340538` (the LC line's fork point) |
| master ahead of that merge-base | 54 commits (B057 / B058 and the accepted RPG/art lanes) |
| `FRESH_MASTER_RECONCILIATION` | **PASS** — master is at the expected `574b3eeb`; no unexpected advance |

`BASE_SHA = 574b3eeb9641c48676e95d3744d204dffca1e1fa`.
`BRANCH = claude/lc016-fresh-master-identity-lineage-integration`.

## 2. `LC_IDENTITY_LINEAGE_MATRIX`

Every identity-lineage file is **absent from fresh master** — the integration is
a pure add with zero conflict. Each file is carried at its **final** state
(taken from LC015 head `bf65b6fdc`, which already contains LC013-R1's storage,
LC014's read window + store additions, and LC015's adapter), so no parent
change is duplicated.

| TASK | HEAD | REQUIRED_FOR_INTEGRATION | SUBSUMED_BY | FILES | AUTHORITY_ROLE |
|---|---|---|---|---|---|
| **LC011** | `2406e0bd6` | YES | — | `tools/lc011_identity_registry_prototype.py`; `docs/planning/lc011_immutable_puzzle_identity_foundation_adr.md`, `lc011_identity_registry_contract.json`, `lc011_owner_identity_decision_packet.md` | Genesis key spec — ratified namespace `c70b30f4-b745-5585-b5c3-64021901ad76`, `canon-source-v1`, `genesis-key-v1`, `mint_genesis_uuid`; the identity ADR |
| **LC012** | `550d3b5da` | tools only (the D: STOP report is preserved evidence) | LC012-R2 for the pin | `tools/lc012_sgf_source_tree_freeze.py` (`GENESIS_SNAPSHOT_SHA256`, `EXPECTED_RECORD_COUNT`, corpus-side); `docs/planning/lc012_sgf_source_tree_genesis_freeze_report.md`, `lc012_sgf_source_tree_genesis_manifest_contract.md`, `lc012_sgf_source_tree_freeze_report.json`, `lc012_r1_historical_c_drive_sgf_genesis_provenance_recovery.md` | Frozen-corpus constants (sha `88da3e43…`, 42,804); D:-tree STOP + C: Rank-B provenance evidence |
| **LC012-R2** | `9d4d5a914` | YES | — | `tools/lc012_p2_genesis_freeze.py`; `docs/planning/lc012_p2_genesis_receipt.json` (sha `834eb17f…`), `lc012_p2_historical_rename_map.json` (sha `473a80a3…`, 918), `lc012_p2_genesis_record_manifest.json` (proof; full sha `ee7b1bc4…`), `lc012_p2_genesis_tree_pin_and_receipt.md` | Owner-ratified **P2 genesis tree pin** (`b162f9e72:SGF題庫`, tree manifest `12fcab4a…`) + immutable receipt + 918 rename map + the one reused manifest / uuid-list serialisation |
| **LC013** | `fb76d40b7` | NO — superseded | **LC013-R1** | — (its migration/store/bootstrap are carried at the R1 state) | — |
| **LC013-R1** | `19d797970` | YES (subsumes LC013) | — | `migrations/puzzle_identity_registry_v1.py`, `puzzle_identity_store.py`, `puzzle_identity_genesis_bootstrap.py`; `tests/test_lc013_puzzle_identity_registry.py`, `test_lc013_r1_postgres_and_genesis.py`, `test_lc013_r1_genesis_binding.py`, `test_lc012_p2_genesis_receipt.py`, `test_lc012_sgf_source_tree_genesis_freeze.py`, `test_lc011_identity_registry_contract.py` | Empty registry / alias / lineage / bootstrap-receipt storage (PG FK order, real `BOOLEAN`, plpgsql-`%`-safe DDL); `GenesisReceiptVerifier` crypto-binds the exact LC012-R2 artifact bytes; `GenesisBootstrap` (never run) |
| **LC014** | `ee9f65c9e` | YES | — | `puzzle_identity_read_window.py`; `tests/test_lc014_dual_id_resolver.py` (also the additive read helpers in `puzzle_identity_store.py`, carried at LC015 state) | `DualIdReadWindow` — `EXACT` / `RETIRED` / `AMBIGUOUS` (fail closed) / `MISSING` / `UNAVAILABLE`; batch resolve; reverse lookup; `dual_id_key`; `bootstrap_state().hot` |
| **LC015** | `bf65b6fdc` | YES | — | `identity_read_adapter.py`; `tests/test_lc015_dual_id_read_caller_integration.py` | `BootstrapGatedIdentityReader` + `IdentityKey` / `IdentityKeyKind` / `IdentityNotAttachable`; `admin_identity_lookup`, `identity_key_for_read`, `identity_keys_for_aggregate` — the §6 bootstrap gate + admin lookup |

**30 files, 10 080 insertions, 0 deletions.** Infra dependency check: `db.py`,
`migrations/__init__.py`, `pytest.ini` are byte-identical between LC015 and fresh
master; `tools/` is an implicit namespace package on both (no `__init__.py`);
`tools/lc011_*` / `tools/lc012_*` names do not collide with master's 64 `tools/`
files. No `conftest.py` anywhere — every identity test is self-contained.

## 3. Preserved contracts (verified on the integrated candidate)

| contract | evidence |
|---|---|
| `CANONICAL_QUESTION_IDENTITY = source_record_uuid` | `mint_genesis_uuid` (LC011) minted from `canon-source-v1(source)`; `record_index` / content hash / duplicate group are **not** identity; `REQUEST_TIME_UUID_GENERATION = NO` (no create/mint path outside the gated `GenesisBootstrap`) |
| `LEGACY_INTEGER_ID_COMPATIBILITY = YES` | `question_id` kept everywhere; `LEGACY_QUESTION_ID` is an alias kind; `dual_id_key` returns `("legacy", qid)` unless `EXACT` |
| `REAL_GENESIS_BOOTSTRAP = NO`, `IDENTITY_REGISTRY_POPULATION = NO`, `UUID_BACKFILL = NO` | `GenesisBootstrap.apply()` is never called; the 42,804-row manifest is only *regenerated read-only* in `test_lc013_r1_genesis_binding.py` to re-verify the digests |
| `AMBIGUOUS_FAIL_CLOSED = YES`, no silent alias merge | LC014 raises `AmbiguousAliasError` / returns `AMBIGUOUS`; LC015 maps it to an `UNRESOLVED` key with `group_key = ("unresolved", qid)` that is never folded into a uuid bucket |
| `RETIRED_HISTORY_READABLE = YES`, `RETIRED_ATTACHABLE = NO` | `RETIRED` → uuid returned, `attachable = False`; `assert_attachable` raises `IdentityNotAttachable` |
| `BOOTSTRAP_GATE_ENFORCED = YES`, `HOT_FALSE_LEGACY_BEHAVIOR = PASS` | `bootstrap_state().hot` is `False` (no APPLIED receipt, no identities); `BootstrapGatedIdentityReader.key_for` returns a `LEGACY` key for every id and never queries the resolver; a test proves registry/alias/lineage row counts unchanged after any number of calls |
| `BOOTSTRAP_HOT_AFTER_TASK = FALSE` | nothing in LC016 seeds a receipt or an identity |
| admin lookup — all four selectors | `admin_identity_lookup` by `legacy_question_id` / `source_record_uuid` / `current_source_path` / `historical_source_path`; `AMBIGUOUS` → `{status: AMBIGUOUS, candidates: […]}` with no `source_record_uuid`, operator picks |
| `NO_FABRICATED_IDENTITY = PASS`, `MISSING_RESULT_TYPED = YES`, `UNAVAILABLE_RESULT_TYPED = YES`, `SILENT_IDENTITY_CREATION = NO` | AST import checks on `puzzle_identity_read_window.py` and `identity_read_adapter.py`; typed results on every non-resolving path |
| `CORPUS_CHANGED = NO`, `SGF_CHANGED = NO`, `LC012_R2_ARTIFACT_CHANGED = NO` | the three `docs/planning/lc012_p2_*` artifacts are carried byte-identical (their shas re-verified by the tests) |
| `APP_PY_CHANGED = NO`, `CURRENT_MASTER_COMPATIBILITY = PASS`, `APP_IMPORT = PASS` | `import app` succeeds with the identity modules present; RPG loadout / ownership / shop-offer / RPG-wave1 tests unaffected (LC016 edits no master file) |

## 4. Deferred (unchanged from LC015)

`REVIEW_LOG_APP_PY_WIRING = DEFERRED`, `SRS_APP_PY_WIRING = DEFERRED`,
`LEARNING_DISPLAY_APP_PY_WIRING = DEFERRED`,
`ADVENTURE_IDENTITY_APP_PY_WIRING = DEFERRED` — every such read site is inline in
`app.py`; the wire recipe (one `BootstrapGatedIdentityReader` call + a
`group_key` re-bucket, behind `hot`) is in
`lc015_dual_id_read_caller_integration.md` §7. `REVIEW_LOG_WRITE_PATH_CHANGED = NO`,
`SRS_WRITE_PATH_CHANGED = NO`, `PRODUCTION_IDENTITY_WRITES_ADDED = NO`.

## 5. Other lanes / releases — untouched

`B057_RC_CONTENT_CHANGED = NO`, `B058_MASTER_RELEASE_CONTENT_CHANGED = NO`,
`A044_SCOPE_TOUCHED = NO`, `E047_SCOPE_TOUCHED = NO`, `F035_SCOPE_TOUCHED = NO`,
`ART003_SCOPE_TOUCHED = NO`. LC016 is a post-merge side candidate; no RPG runtime
change, no release-content change.

## 6. Tests

- `LC_IDENTITY_REGRESSION` — LC011 contract + LC013 registry + LC014 resolver +
  LC015 adapter on SQLite: **95 passed**.
- `LC013-R1 PostgreSQL` + `LC014 PG parity` + `LC015 PG parity` on a disposable
  `postgres:16.14-alpine` container — see the final report.
- `LC012 / LC012-R2 / LC013-R1 genesis-binding` — the D: frozen corpus is present
  so the corpus-side + receipt-binding tests run; the C:\go-website
  provenance-regeneration parts skip where that historical repo is unavailable.
- `CURRENT_MASTER_COMPATIBILITY` — `test_b034_equipment_loadout_service` /
  `test_b040_equipment_ownership_service` / `test_c025_shop_offer_identity_projection` /
  `test_rpg_wave1_lane_b`: **74 passed / 4 skipped**.

`TASK_INTRODUCED_FAILURES = 0`.

## 7. Result & next steps

`RESULT = READY_FOR_OWNER_REVIEW_IDENTITY_LINEAGE_INTEGRATION`.
**Not** `MERGED` / `GENESIS_APPLIED` / `UUID_BACKFILLED` / `PRODUCTION_MIGRATED`.

Report separately (do **not** combine):

- **A — merge review**: the integrated LC011–LC015 identity lineage on
  `claude/lc016-fresh-master-identity-lineage-integration` is a clean 30-file
  pure add on `574b3eeb` with the full contract test matrix green; ready for an
  Owner/Coordinator merge-review decision.
- **B — `NEXT_APP_PY_WIRING_TASK`**: a future task that wires the deferred
  `review_log` / SRS / Learning-display / Adventure read call sites in `app.py`
  through `BootstrapGatedIdentityReader` (still a no-op until `hot`), owned by
  the current app.py-writer slot. Not this lane, not now.
- **C — `NEXT_GENESIS_GATE_TASK`**: a future Owner-gated task that runs
  `GenesisBootstrap.apply()` once with the real LC012-R2 receipt + 42,804-row
  manifest against the canonical DB — the only action that flips
  `bootstrap_state().hot` to `True`. Separate, explicitly gated, irreversible.
