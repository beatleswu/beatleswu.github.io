# LC020-R3 — Genesis Repair Canonical Merge Preflight

**RESULT: `PASS_LC020_R3_GENESIS_REPAIR_CANONICAL_MERGE_PREFLIGHT`.**
`LC020_R1_CANONICAL_ADMISSION_READY = YES`.
`NEXT_TASK = LC020_R4_GENESIS_REPAIR_OWNER_MERGE_GATE_PACKET_001`.

Canonical merge preflight only. **No master merge, no master push, no Production
touch, no Owner gate consumed.** `MASTER_MERGE = NO`, `MASTER_PUSHED = NO`.

---

## 1. Inputs & fresh master

| field | value |
|---|---|
| `LC020_R1_HEAD` | `363f76e566e1c939c6dde0ec610cd9a34bb3993f` — `LC020_R1_HEAD_EXACT = YES` |
| `LC020_R2_HEAD` | `30be85b708a6ee264600927a6524a7888a8307a2` — `LC020_R2_HEAD_EXACT = YES` (docs-only on R1) |
| `FRESH_ORIGIN_MASTER_HEAD` | `c1a55daebc411df46ca4bbfef6c0b814c813ec73` |
| `FRESH_ORIGIN_MASTER_TREE` | `50c3c74fa8095e02cd507f7745efafcfcde4ae6f` |
| `MASTER_ADVANCED` | **NO** (unchanged since LC020-R2 completion) |
| `GENESIS_RELEVANT_MASTER_DELTA` | **NONE** — `puzzle_identity_store.py` / `puzzle_identity_genesis_bootstrap.py` / `migrations/puzzle_identity_registry_v1.py` / `identity_read_adapter.py` / `puzzle_identity_read_window.py` / `grimoire_api.py` are byte-identical between the R1 parent `8b34994b5` and fresh master `c1a55daeb`; `merge-base(363f76e56, c1a55daeb) == 8b34994b5` (R1's own parent). |
| `SEMANTIC_CONFLICT` | **NO** |

## 2. Exact source delta to admit

`git diff 8b34994b5 363f76e56`:

- `SOURCE_REPAIR_FILE_COUNT = 2` — `puzzle_identity_store.py`,
  `puzzle_identity_genesis_bootstrap.py`
- `TEST_FILE_COUNT = 1` — `tests/test_lc020_r1_genesis_legacy_id_collision.py`

`APP_PY_CHANGED = NO` · `GRIMOIRE_API_CHANGED = NO` ·
`COMMUNITY_LEADERBOARD_REWARDS_CHANGED = NO` · `MIGRATION_CHANGED = NO`.
No unrelated branch file is imported.

### `R2_DOCS_CANONICAL_ADMISSION_RECOMMENDED = YES`

The repo's LC011–LC019 convention is that each identity task's planning doc is
committed to canonical master alongside its code. The LC020-R1 repair should
therefore be admitted together with the operator-facing planning provenance:

- `docs/planning/lc020_genesis_bootstrap_execution_preflight_and_runbook_revalidation.md`
  … *(the earlier LC020 STOP/blocker doc is already provenance; not required)*
- `docs/planning/lc020_r2_genesis_bootstrap_execution_preflight_and_runbook_revalidation.md`
  — the two-phase Owner runbook (`GO_PRODUCTION_DB_MIGRATION` → `GO_GENESIS_BOOTSTRAP`)
  + Owner decision packet, rebuilt against the repaired implementation.
- `docs/planning/lc020_r2_genesis_preflight_revalidation_report.json`
  — the machine-readable revalidation evidence.
- `docs/planning/lc020_r3_genesis_repair_canonical_merge_preflight.md` + its
  report JSON (this document).

These are the operator's reference for the still-gated Genesis and explain why
the collision-safe alias shape is what it is. Total canonical-merge footprint =
3 source/test files + 4–5 planning files, all additive; no runtime behaviour
changes until a future Owner-gated Genesis.

## 3. Collision contract (unchanged)

| field | value |
|---|---|
| `LEGACY_ID_COLLISION_GROUP_COUNT` | 11 |
| `LEGACY_ID_COLLISION_RECORD_COUNT` | 22 |
| `LEGACY_ID_UNIQUE_VALUE_COUNT` | 42793 |
| `LEGACY_COLLISION_POLICY` | `FAIL_CLOSED_AMBIGUOUS` |
| non-collision legacy alias | `is_current = True` |
| collision-member legacy alias | `is_current = False` |
| `PER_RECORD_ALIAS_CONTEXT_DISAMBIGUATION` | NO (all use `DEFAULT_ALIAS_CONTEXT` `genesis-v1`) |
| `UNIQUE_CURRENT_ALIAS_CONSTRAINT_PRESERVED` | YES (`uq_pia_current_alias` + `uq_pia_one_current_path` unchanged; 0 duplicate current `LEGACY_QUESTION_ID` values post-genesis; a manual 2nd current insert is still rejected on SQLite and PG) |

## 4. Frozen artifact protection (byte-identical on the synthetic tree)

`migrations/puzzle_identity_registry_v1.py` sha256
`ad5bd5bc4c3d501df694e5b05835bb0426964ddb4e98bc64d291960823d6f766`;
`docs/planning/lc012_p2_genesis_receipt.json`
`834eb17fb3bedfa303bf510d24a2734348ddda1204c4811ce80d4c9c89c6f54c`;
regenerated `genesis_record_manifest_sha256`
`ee7b1bc4a5f8bb339904a957f236c742a48ea68f6ab4285083e089e0267e4828`;
`proposed_uuid_list_sha256`
`cb47e9d63d2e44f06b24772436380a8e1ce4f199ae64455bfc3891da446da2f2`;
`docs/planning/lc012_p2_historical_rename_map.json`
`473a80a3664517f7c23db9071948d17cc89053f321ae5ace58ae27e94de7923d`;
frozen `questions.json` `88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff`.
`RECEIPT_CHANGED = NO`, `MANIFEST_IDENTITY_ASSIGNMENTS_CHANGED = NO`,
`RENAME_MAP_CHANGED = NO`.

## 5. Synthetic canonical admission

`git merge-tree --write-tree c1a55daeb 363f76e56` →
**`SYNTHETIC_POST_MERGE_TREE = cb8ca8524cb2eb7c4c2075527348338f1cb4a1f0`**,
`SYNTHETIC_MERGE_CONFLICTS = 0`. Materialised locally as commit
`4d93aceaa236170debca1e298763a99694f0e9e3` (parents `c1a55daeb` + `363f76e56`,
**never pushed, not a branch**) for disposable revalidation.

`git diff c1a55daeb <synthetic-tree>` = exactly `M puzzle_identity_genesis_bootstrap.py`
+ `M puzzle_identity_store.py` + `A tests/test_lc020_r1_genesis_legacy_id_collision.py`.
`UNEXPECTED_FILES = 0`. Synthetic-tree `app.py` blob == fresh-master `app.py`
blob (`abc350916…`) → the E055 app.py change is preserved byte-for-byte; the
two `puzzle_identity_*.py` blobs == R1's blobs (`336937f48…`, `2756a87aa…`).

## 6. Full Genesis revalidation from the synthetic canonical state

| # | check | result |
|---|---|---|
| §8 | `GENESIS_PREFLIGHT_SYNTHETIC` | **PASS** (0 problems; census before mutation; fail-closed on manifest/receipt/uuid/static-fact/pin/canon-version/row-count mismatch, dup UUID, uuid↔canonical mismatch, missing canonical_source, bad provenance, uuidv4 row, migration absent, **collision-census drift**, **collision-UUID collapse**) |
| §8 | `SQLITE_FULL_GENESIS_SYNTHETIC` | **PASS** (9.3 s). `IDENTITY_COUNT = 42804`, `ACTIVE = 42804`, `GENESIS_LINEAGE_COUNT = 42804`, `bootstrap_receipt APPLIED = 1`. `CURRENT_LEGACY_ALIAS_COUNT = 42782`, `NONCURRENT_COLLISION_ALIAS_COUNT = 22`. `BOOTSTRAP_HOT_BEFORE = FALSE → BOOTSTRAP_HOT_AFTER = TRUE`. `PARTIAL_APPLY_VISIBLE = NO`. 0 duplicate current legacy alias values. |
| §8 | `POSTGRES_FULL_GENESIS_SYNTHETIC` | see the §8 machine report (`lc020r3_pg_full_report.json`) — real disposable PostgreSQL 16.14: migration + `validate_schema` PASS; preflight PASS; full 42,804-row `apply()` → `APPLIED`; `IDENTITY_COUNT = 42804` / `42782` current + `22` not-current / `hot AFTER = TRUE`; all 11 collided ids AMBIGUOUS (single + batch) + reader `("unresolved", id)`; non-collision sample EXACT; `uq_pia_current_alias` still rejects a duplicate current insert; second apply → `ALREADY_APPLIED` (0 dup rows). |
| §9 | `COLLISION_LEGACY_LOOKUP_FAIL_CLOSED` | **PASS** — all 11 collided ids: 2 members, 2 distinct canonical UUIDs, `resolve_legacy_question_id` and `resolve_many_legacy_question_ids` → `AMBIGUOUS`. Never an arbitrary canonical UUID. |
| §9 | `COLLISION_READER_FAIL_CLOSED` | **PASS** — `BootstrapGatedIdentityReader.key_for` → `UNRESOLVED`, `group_key = ("unresolved", legacy_id)`. |
| §9 | `NON_COLLISION_LEGACY_ALIAS_COMPATIBILITY` | **PASS** — 1,000-row deterministic sample all `EXACT` with the manifest `source_record_uuid`; unknown id → `MISSING`. |
| §11 | hot readers | `HOT_READER_GROUP_COUNT = 8` (grimoire `generate_daily_training` + the 7 LC019-W2 app.py groups); 5,000-id batch → 5,000 `("uuid", …)` / 0 `("unresolved", …)`; `HOT_GROUP_KEY_CANONICALIZATION = PASS`. |
| §13 out-of-scope | `SOURCE_RECORD_UUID_CANONICAL_IDENTITY = YES`, `LEGACY_INTEGER_ALIAS = YES`, `REQUEST_TIME_UUID_GENERATION = NO`, `AMBIGUITY_FAIL_CLOSED = YES`; `MARKER_POLICY_CHANGED = NO`, `VOCABULARY_BOUNDARY_CHANGED = NO`, `LC019_W1B_IMPLEMENTED = NO`, `POST_GENESIS_NATIVE_UUID_CREATION_IMPLEMENTED = NO`. `REWARDS_SYNC_RAW_ID_SEMANTICS_PRESERVED = YES` (`fold_identity=False` on the synthetic tree). |
| §14 | failure/rollback matrix | 15 tampered-input cases → `DB_MUTATED = NO` / `HOT_FLIPPED = NO`; a clean forced mid-`apply()` RuntimeError → full SAVEPOINT rollback (registry/alias/lineage/bootstrap_receipt all 0, `hot` FALSE). |

`C_GO_WEBSITE_MUTATED = NO` (HEAD `415a321db` unchanged; `git archive` /
`cat-file` only).

## 7. Identity / reader regression (§10) — on the synthetic merged tree

`PY_COMPILE = PASS`, `APP_IMPORT = PASS`. LC011-LC017 + LC019-W1 + LC019-W2 +
genesis bootstrap + registry + aliases + lineage + `DualIdReadWindow` +
`BootstrapGatedIdentityReader` + `tests/test_lc020_r1_genesis_legacy_id_collision.py`
= **130 passed, 46 skipped** (C:-path-gated + PG-container-gated cases).
`ALL_IDENTITY_TESTS = PASS`, `TASK_INTRODUCED_FAILURES = 0`.

## 8. E055 / B08 protection (§11 / §12)

`E055_ZONE3_PRESENT = YES` (`adventure_zone3_monster_authority.py` present;
`app.py` still imports it and calls `_settle_monster_defeat_in_tx` with the
`adventure_authority` path). `E055_APP_PY_PRESERVED = YES` (synthetic-tree
`app.py` blob == fresh-master `app.py` blob). `E055_RUNTIME_SOURCE_PRESERVED =
YES`. `B08_CANONICAL_ART_PRESERVED = YES` (80 `art/monsters/M0*` assets present;
ART003 payload / M-ID / Zone-3 authority tests pass — 23 passed).

**Pre-existing, not LC020-caused:** `test_art003_b07_production.py::test_only_b07_scope_changed_and_no_secret`
and two `test_art003_b08_production.py` scope-guard tests fail with
`AssertionError: assert not {'secret_key.txt'}` — a worktree-hygiene assertion
tripped by the app-boot-generated untracked `secret_key.txt`. Reproduced
identically on plain fresh master `c1a55daeb` with the entire LC020-R1 delta
reverted. `SECRET_KEY_TOUCHED = NO`.

## 9. Gates (all still `NOT_GRANTED`, none consumed)

`LC020_R1_OWNER_MERGE_GATE = NOT_GRANTED` · `LC020_R1_OWNER_MERGE_GATE_CONSUMED = NO`.
`GO_PRODUCTION_DB_MIGRATION = NOT_GRANTED` · `GO_GENESIS_BOOTSTRAP = NOT_GRANTED`.
Canonical admission and Production execution remain separate governance steps.

`LC020_R1_CANONICAL_ADMISSION_READY = YES` ·
`NEXT_TASK = LC020_R4_GENESIS_REPAIR_OWNER_MERGE_GATE_PACKET_001`.
