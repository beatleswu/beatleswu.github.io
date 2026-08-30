# LC020-R4 — Genesis Repair Owner Merge Gate Packet

**RESULT: `PASS_LC020_R4_GENESIS_REPAIR_OWNER_MERGE_GATE_PACKET`.**
**`CANONICAL_ADMISSION_READY = YES`.**
**`OWNER_MERGE_GATE_RECOMMENDATION = GO_MERGE`.**

Packet only. No canonical merge, no master push, no Production touch, no gate
consumed. `MASTER_MERGE = NO`, `MASTER_PUSHED = NO`, `SOURCE_BEHAVIOR_CHANGED = NO`.

---

## 1. Heads & fresh master

| field | value |
|---|---|
| `LC020_R1_HEAD` | `363f76e566e1c939c6dde0ec610cd9a34bb3993f` — `LC020_R1_HEAD_EXACT = YES` |
| `LC020_R2_HEAD` | `30be85b708a6ee264600927a6524a7888a8307a2` — `LC020_R2_HEAD_EXACT = YES` |
| `LC020_R3_HEAD` | `6be5bff939f68e337cc346a1a8d7a5da97a3d624` — `LC020_R3_HEAD_EXACT = YES` |
| `FRESH_ORIGIN_MASTER_HEAD` | `38d12af38d8e5e667d3b7891853837f32139fd8a` |
| `FRESH_ORIGIN_MASTER_TREE` | `86194f9d1a2eafdd6a17ea21fb0270559e45766f` |
| `MASTER_ADVANCED_SINCE_R3` | **YES** — `c1a55daeb → 38d12af38`, 2 commits: `9998eb9eb` "admit ART003 B09 canonical assets and reconcile scope tests" + merge `38d12af38` |
| `GENESIS_RELEVANT_MASTER_DELTA` | **NONE** — the B09 advance changes only `art/`, `tests/`, `docs/planning/` files. `puzzle_identity_store.py` / `puzzle_identity_genesis_bootstrap.py` / `migrations/puzzle_identity_registry_v1.py` / `identity_read_adapter.py` / `puzzle_identity_read_window.py` / `grimoire_api.py` are byte-identical between R1's parent `8b34994b5` and fresh master `38d12af38`; `app.py` is unchanged `c1a55daeb → 38d12af38` (E055 preserved); `merge-base(363f76e56, 38d12af38) == 8b34994b5` (R1's own parent). |
| `SEMANTIC_CONFLICT` | **NO** (`SEMANTIC_CONFLICT_COUNT = 0`) |

## 2. Exact source admission payload

`git diff 8b34994b5 363f76e56` — `SOURCE_REPAIR_FILE_COUNT = 2`,
`TEST_FILE_COUNT = 1`, `LC020_R1_SOURCE_DELTA_EXACT = YES`:

| path | git blob | sha256 | kind |
|---|---|---|---|
| `puzzle_identity_store.py` | `336937f48c4022daddbc46e43a4619e1b7d9f5a7` | `e54734ab23e24eaff65725d2f3af0a5de9c263bb3e8b40d0e27ae3e18514b1e1` | M |
| `puzzle_identity_genesis_bootstrap.py` | `2756a87aa0e113228649e0c9f44a11bac54a99cc` | `1a341fcef481f50398489e19b3a90cfc5690f66cb5aa6c484668062168c60b83` | M |
| `tests/test_lc020_r1_genesis_legacy_id_collision.py` | `759e806974fdd909b7155530682ec0543c8f7030` | `1aadf6e9ec1b4ecbb4043efc0922325b51f79332ca135f0a36a1279315f4d7cb` | A |

No `app.py`. No `grimoire_api.py`. No `community_leaderboard_rewards.py`. No
migration-file modification.

## 3. Canonical planning / runbook doc payload (exact)

No `docs/planning/lc020*` file exists on fresh master. Approved additive set:

| path | origin head | blob | sha256 | purpose | req. for operator runbook | req. for canonical admission | class |
|---|---|---|---|---|---|---|---|
| `docs/planning/lc020_r2_genesis_bootstrap_execution_preflight_and_runbook_revalidation.md` | `30be85b70` | `9927539f65f1dff51917c3deca0ad1255a8d1f91` | `3cc78735ed233e56d6d123364605c3f84db6cdab2902fe68d11c471394a025de` | the two-phase Owner runbook (`GO_PRODUCTION_DB_MIGRATION` → `GO_GENESIS_BOOTSTRAP`) + Owner decision packet, against the repaired impl | **YES** | YES | **REQUIRED** |
| `docs/planning/lc020_r2_genesis_preflight_revalidation_report.json` | `30be85b70` | `067b60dd02cdce74b48fbca978e1dd5733348296` | `c8342d1315867bee192fe9564ef812c9bb77f8f7fe1d2a6ba55202a620ef4dc6` | machine-readable revalidation evidence (full disposable SQLite + PostgreSQL 16.14 genesis) | NO | YES | **REQUIRED** |
| `docs/planning/lc020_r3_genesis_repair_canonical_merge_preflight.md` | `6be5bff93` | `9f4f02a6fdceaeee5aa25091c4ee10cc180e7ea3` | `ecf60ae7522424af827c29b1409a19098674f0a07aa208fd1ff6e0f10ba2b3be` | the canonical-admission proof (synthetic merge, E055/B08 preservation, regression) | NO | YES | **RECOMMENDED** |
| `docs/planning/lc020_r3_genesis_repair_canonical_merge_preflight_report.json` | `6be5bff93` | `1d148bdc51205b426065c77e70d64f1525d21301` | `c7455b16be8002ba87abc7d967515a36c675070058c3110261448601ada1ba57` | machine report for the admission preflight | NO | YES | **RECOMMENDED** |

**EXCLUDE** (superseded by the R2 runbook, which reflects the repaired impl):
`docs/planning/lc020_genesis_bootstrap_execution_preflight_and_runbook.md`
(@ `2e6dfa4cb`) and `docs/planning/lc020_genesis_preflight_report.json`
(@ `2e6dfa4cb`) — the original LC020 *blocked* report; its runbook and
`GENESIS_EXECUTION_READY = NO` conclusion are obsolete. The blocker it describes
is summarised in the R3 doc §1 for provenance; the standalone files would be
stale and misleading on master.

`CANONICAL_DOC_PATH_COUNT = 4`
`CANONICAL_DOC_PATHS =`
- `docs/planning/lc020_r2_genesis_bootstrap_execution_preflight_and_runbook_revalidation.md`
- `docs/planning/lc020_r2_genesis_preflight_revalidation_report.json`
- `docs/planning/lc020_r3_genesis_repair_canonical_merge_preflight.md`
- `docs/planning/lc020_r3_genesis_repair_canonical_merge_preflight_report.json`

**Total canonical admission payload = 7 files** (3 source/test + 4 docs).

## 4. Frozen artifact hash lock

| artifact | authoritative sha256 | on the synthetic admission tree |
|---|---|---|
| `migrations/puzzle_identity_registry_v1.py` | `ad5bd5bc4c3d501df694e5b05835bb0426964ddb4e98bc64d291960823d6f766` | match |
| `docs/planning/lc012_p2_genesis_receipt.json` | `834eb17fb3bedfa303bf510d24a2734348ddda1204c4811ce80d4c9c89c6f54c` | match |
| regenerated `genesis_record_manifest_sha256` | `ee7b1bc4a5f8bb339904a957f236c742a48ea68f6ab4285083e089e0267e4828` | match (R2/R3 regen) |
| `proposed_uuid_list_sha256` | `cb47e9d63d2e44f06b24772436380a8e1ce4f199ae64455bfc3891da446da2f2` | match (R2/R3 regen) |
| `docs/planning/lc012_p2_historical_rename_map.json` | `473a80a3664517f7c23db9071948d17cc89053f321ae5ace58ae27e94de7923d` | match |
| frozen `questions.json` | `88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff` | match |

`FROZEN_ARTIFACT_HASH_MATCH_COUNT = 6` · `FROZEN_ARTIFACT_HASH_DRIFT_COUNT = 0`.
`RECEIPT_CHANGED = NO`, `MANIFEST_IDENTITY_ASSIGNMENTS_CHANGED = NO`,
`RENAME_MAP_CHANGED = NO`.

## 5. Collision contract (locked)

`LEGACY_ID_COLLISION_GROUP_COUNT = 11` · `LEGACY_ID_COLLISION_RECORD_COUNT = 22` ·
`LEGACY_ID_UNIQUE_VALUE_COUNT = 42793`. Collided ids
`{40479, 40511, 40512, 40513, 62011, 63382, 70450, 70752, 71238, 71240, 71244}`.
Post-genesis: `CURRENT_LEGACY_ALIAS_COUNT = 42782`,
`NONCURRENT_COLLISION_ALIAS_COUNT = 22`. Policy **`FAIL_CLOSED_AMBIGUOUS`**.
`PER_RECORD_ALIAS_CONTEXT_DISAMBIGUATION = NO` (all collision-member
`LEGACY_QUESTION_ID` aliases carry `DEFAULT_ALIAS_CONTEXT` `genesis-v1`,
`is_current = False`). Every collision legacy lookup →
`AMBIGUOUS`; `BootstrapGatedIdentityReader.key_for` → `UNRESOLVED`,
`group_key = ("unresolved", legacy_id)`. **No arbitrary `source_record_uuid`
selection.**

## 6. Canonical identity contract (preserved)

`SOURCE_RECORD_UUID_CANONICAL_IDENTITY = YES` · `LEGACY_INTEGER_ALIAS = YES` ·
`REQUEST_TIME_UUID_GENERATION = NO` · `AMBIGUITY_FAIL_CLOSED = YES`.
`LC019_W1_PRESENT = YES` · `LC019_W2_PRESENT = YES` · `HOT_READER_GROUP_COUNT = 8`.
`REWARDS_SYNC_RAW_ID_SEMANTICS_PRESERVED = YES` ·
`REWARDS_SYNC_FOLD_IDENTITY_FALSE = YES`.

## 7. Out-of-scope firewall

`LC019_W1B_IMPLEMENTED = NO` · `POST_GENESIS_NATIVE_UUID_CREATION_IMPLEMENTED =
NO` · `MARKER_POLICY_CHANGED = NO` · `VOCABULARY_BOUNDARY_CHANGED = NO` ·
`APP_PY_CHANGED = NO`. No identity-schema redesign, no grimoire behaviour change,
no per-record collision disambiguation, no request-time UUID generation, no
Production Genesis execution.

## 8. Synthetic admission reconfirmation (onto fresh master `38d12af38`)

Constructed by plumbing: `git read-tree 38d12af38` + `update-index` of the 7
payload blobs + `write-tree` →

`SYNTHETIC_MERGE_CONFLICTS = 0`
`SYNTHETIC_POST_MERGE_TREE = 0cc9c5344c4b6240014cdb23cd0c9caf3adf1319`

`git diff 38d12af38 <tree>` = exactly `M puzzle_identity_genesis_bootstrap.py` +
`M puzzle_identity_store.py` + `A tests/test_lc020_r1_genesis_legacy_id_collision.py`
+ `A` the 4 planning docs. `UNEXPECTED_FILES = 0`.

**Delta vs the R3 source-only synthetic tree** `cb8ca8524cb2eb7c4c2075527348338f1cb4a1f0`:
(a) base is `38d12af38` (F043-R2 B09 ART003 assets + scope-test reconciliation)
rather than `c1a55daeb`; (b) + the 4 LC020 planning docs from §3 (R3's synthetic
tree was source-only). No source-blob difference — the two
`puzzle_identity_*.py` blobs are byte-identical to R1's (`336937f48…`,
`2756a87aa…`), the test blob is R1's (`759e8069…`).

## 9. Full Genesis evidence (LC020-R3, authoritative — no fresh-master semantic change requires rerun)

`SQLITE_FULL_GENESIS = PASS` (9.3 s) · `POSTGRES_FULL_GENESIS = PASS` (real
disposable PostgreSQL 16.14, full 42,804-row apply, 379.1 s).

`IDENTITY_COUNT = 42804` · `CURRENT_LEGACY_ALIAS_COUNT = 42782` ·
`NONCURRENT_COLLISION_ALIAS_COUNT = 22` · `GENESIS_LINEAGE_COUNT = 42804` ·
`ACTIVE_IDENTITY_COUNT = 42804` · `BOOTSTRAP_RECEIPT_APPLIED_COUNT = 1`.
`BOOTSTRAP_HOT_BEFORE = FALSE → BOOTSTRAP_HOT_AFTER = TRUE`.
`PARTIAL_APPLY_VISIBLE = NO`. `SECOND_APPLY = ALREADY_APPLIED` (deterministic
no-op, 0 duplicate rows; a different / tampered receipt fails closed).
`COLLISION_LEGACY_LOOKUP_FAIL_CLOSED = PASS` ·
`COLLISION_READER_FAIL_CLOSED = PASS` ·
`NON_COLLISION_LEGACY_ALIAS_COMPATIBILITY = PASS` (1,000-row SQLite + 600-row PG
sample all EXACT with the manifest `source_record_uuid`; unknown → MISSING).

Identity/reader regression on the R3 synthetic merged tree = **130 passed / 46
skipped**, `ALL_IDENTITY_TESTS = PASS`, `TASK_INTRODUCED_FAILURES = 0`.

## 10. Unique-constraint protection

`UNIQUE_CURRENT_ALIAS_CONSTRAINT_PRESERVED = YES`. `uq_pia_current_alias` +
`uq_pia_one_current_path` unchanged by the repair. Post-genesis
`DUPLICATE_CURRENT_LEGACY_ALIAS_COUNT = 0` on SQLite and PostgreSQL; a manual
second *current* `LEGACY_QUESTION_ID` insert for the same `(value, context)` is
still rejected on both backends.

## 11. Master protection

`E055_ZONE3_PRESENT = YES` (`adventure_zone3_monster_authority.py` present on
`38d12af38`; `app.py` imports it and calls `_settle_monster_defeat_in_tx` with
the `adventure_authority` path). `E055_APP_PY_PRESERVED = YES` (the synthetic
admission tree's `app.py` blob == fresh-master `app.py` blob; the repair never
touches `app.py`). `E055_RUNTIME_SOURCE_PRESERVED = YES`.
`B08_CANONICAL_ART_PRESERVED = YES` (90 `art/monsters/M0*` assets on
`38d12af38` — B08 + B09; `art_003_batch_008` and `art_003_batch_009` manifests
present). No ART003 source mutation, no MonsterCatalog authority mutation.

## 12. secret_key.txt / hygiene classification

`LC020_CAUSED_SECRET_KEY_TEST_FAILURE = NO`. The three ART003 B07/B08
scope-guard tests that fail with `AssertionError: assert not {'secret_key.txt'}`
were reproduced **identically on plain fresh master `c1a55daeb` with the entire
LC020-R1 delta reverted** (LC020-R3 §8). The failure is an untracked
`secret_key.txt` auto-generated by the app's own boot code during `import app`,
tripping a worktree-hygiene assertion. `PREEXISTING_TEST_HYGIENE_DEBT = YES`.
`SECRET_KEY_CONTENT_READ = NO` · `SECRET_KEY_HASHED = NO` · `SECRET_KEY_MOVED =
NO` · `SECRET_KEY_DELETED = NO` · `SECRET_KEY_STAGED = NO` · `SECRET_KEY_TOUCHED
= NO`. Not fixed in LC020.

## 13. Proposed Owner merge gate

```
GO_MERGE LC020_GENESIS_COLLISION_SAFE_CANONICAL_ADMISSION
```

**Authorized scope — only:**
1. the exact LC020-R1 3-file functional/test delta (§2 blobs)
2. the exact 4 LC020 operator/reference docs enumerated in §3
3. the merge mechanics necessary to admit them onto fresh canonical master
   `38d12af38` (a `--no-ff` merge commit per repo governance, or an equivalent
   review-preserving mechanism)

**NOT authorized:** Production DB migration · Genesis apply · `app.py` changes ·
LC019-W1B · native UUID writer · marker / vocabulary work · deployment ·
schema / data mutation · any other branch history.

## 14. Production gate separation (mandatory)

`CANONICAL_MERGE_IMPLIES_PRODUCTION_DB_MIGRATION = NO`.
`CANONICAL_MERGE_IMPLIES_GENESIS_BOOTSTRAP = NO`.
After canonical merge, both remain separate and `NOT_GRANTED`:
`GO_PRODUCTION_DB_MIGRATION`, `GO_GENESIS_BOOTSTRAP`. The sequence stays:
canonical admission → verify canonical provenance → final Production DB
migration gate packet → Owner `GO_PRODUCTION_DB_MIGRATION` → migration
verification → Owner `GO_GENESIS_BOOTSTRAP` → Genesis apply → Production
acceptance. These gates are not collapsed.

## 15. Owner decision

| field | value |
|---|---|
| `CANONICAL_ADMISSION_READY` | **YES** |
| `REAL_DEFECT_BLOCKER_COUNT` | 0 |
| `SEMANTIC_CONFLICT_COUNT` | 0 |
| `FROZEN_ARTIFACT_DRIFT_COUNT` | 0 |
| `UNEXPECTED_FILE_COUNT` | 0 |
| `OWNER_MERGE_GATE_RECOMMENDATION` | **GO_MERGE** |
| exact authorization string | `GO_MERGE LC020_GENESIS_COLLISION_SAFE_CANONICAL_ADMISSION` |

`GO_PRODUCTION_DB_MIGRATION = NOT_GRANTED` · `GO_GENESIS_BOOTSTRAP = NOT_GRANTED`.

`NEXT_TASK` (if the Owner grants the gate):
`LC020_R5_OWNER_APPROVED_GENESIS_REPAIR_CANONICAL_MASTER_MERGE_001`.
(If the Owner holds: `PAUSE_PENDING_OWNER_DECISION`. If a new fresh-master
semantic conflict appears before R5: `LC020_R4A_FRESH_MASTER_CONFLICT_RECONCILIATION_001`.)
