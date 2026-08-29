# LC019-W1 — Bootstrap-Gated Identity Reader: Non-App Reader Wiring

Status: **implemented. One non-app.py Learning Core reader (`grimoire_api.py`
`generate_daily_training`) wired through `BootstrapGatedIdentityReader`.
No-op-until-`hot`. No app.py, no `community_leaderboard_rewards.py`, no schema,
no Genesis, no write path, no master merge.**

Mode: `NON_APP_RUNTIME_READER_WIRING_HOT_FALSE_SAFE_LANDING`.

---

## 1. Fresh-master reconciliation

| field | value |
|---|---|
| `CURRENT_ORIGIN_MASTER` | `c4568d5664f632d1cfa1e77ba39b00efa437f8a5` |
| LC018 base was | `3f98c204a` — **advanced** by the E049/E051 Battlefield MonsterCatalog cutover (`3f98c204a..c4568d5` = 8 commits: `app.py`, `battlefield_monster_catalog_*`, `monster_catalog_*`, E045–E051 docs + tests) |
| `FRESH_MASTER_RECONCILIATION` | **re-anchored to `c4568d5`** — `git diff 3f98c204a..c4568d5 -- grimoire_api.py puzzle_identity_read_window.py identity_read_adapter.py puzzle_identity_store.py` is **EMPTY**; the E051 advance does not touch `grimoire_api.py`, `review_log`, `srs_cards`, `mistake_log`, `map_battle_*`, or any identity module. LC019-W1 scope is non-conflicting. `LC018_CONTRACT_RECONCILED = YES` (LC018 predicted exactly this: "E051 touches app.py but not any Learning-Core read path → no functional interaction"). |
| `BASE_SHA` | `c4568d5664f632d1cfa1e77ba39b00efa437f8a5` |
| branch | `claude/lc019-w1-bootstrap-gated-non-app-reader-wiring` |

### 1.1 R1 — post-A049 fresh-master re-anchor

`LC019_W1_R1_POST_A049_FRESH_MASTER_RECONCILIATION_AND_MERGE_CANDIDATE_001`.
After the LC019-W1 source landed on its own branch, `origin/master` advanced
again: `c4568d5` → **`3ace7c748b5f2b5b8b4d4ebb65827b6987ad1e6a`** (tree
`377afa276cc09a8c5786bdc5eecf4bf7d3201814`) via A049-R1 — two commits
(`1862ce65d` "close disabled legacy equipment equip fallback", `3ace7c748`
"retire legacy appearance combat authority"). Those touch `app.py` and the
hero-equipment / legacy-appearance-combat authority path only.

| field | value |
|---|---|
| `INTEGRATION_BASE_SHA` | `3ace7c748b5f2b5b8b4d4ebb65827b6987ad1e6a` (fresh `origin/master`) |
| `INTEGRATION_METHOD` | `git cherry-pick` of LC019-W1 head `401f14dc9` onto fresh master — 0 conflicts |
| `LC019_W1_PATCH_EQUIVALENCE` | `EXACT` — the cherry-pick commit `git range-diff 401f14dc9~1..401f14dc9  <cherry-pick>~1..<cherry-pick>` reports `=`; the runtime + test payload (`grimoire_api.py`, `tests/test_lc019_w1_grimoire_bootstrap_gated_reader.py`) is byte-identical to `401f14dc9`. Only this doc carries an extra commit (this §1.1 R1 note) on top — no code delta. |
| `GRIMOIRE_API_MASTER_ADVANCE_CHANGED` | `NO` — `git diff c4568d5..3ace7c748 -- grimoire_api.py` is EMPTY |
| `IDENTITY_READER_FOUNDATION_CHANGED` | `NO` — `puzzle_identity_read_window.py` / `identity_read_adapter.py` / `puzzle_identity_store.py` / `puzzle_identity_genesis_bootstrap.py` / `migrations/puzzle_identity_registry_v1.py` byte-identical fresh-master ↔ `401f14dc9` (LC017 merge `3f98c204a` is an ancestor of `3ace7c748`, so the whole LC011–LC016 foundation is already on master) |
| branch | `claude/lc019-w1-r1-post-a049-fresh-master-reconciliation` |

W1 semantics are unchanged by R1. `MASTER_MERGE = NO`, `GO_MERGE_GRANTED = NO`.

## 2. Wired

`WIRED_FILE_COUNT = 1` — `grimoire_api.py` only (71 insertions / 11 deletions).

`WIRED_CALLSITE_COUNT = 2`:

| LC018 site | function | what was wired |
|---|---|---|
| `grimoire_api.py:~148` — `SELECT question_id FROM srs_cards WHERE user_id=? AND due_date<=?` | `generate_daily_training` (`due_ids`) | the SRS-due set now feeds an identity-keyed exclusion |
| `grimoire_api.py:~163` — `SELECT DISTINCT question_id FROM review_log WHERE user_id=? AND reviewed_at>=?` | `generate_daily_training` (`recent_ids`) | the recently-answered set now feeds an identity-keyed exclusion |

`generate_daily_training` builds the 5-3-2 daily recommendation. Its
dedup/exclusion (`due_ids`, `cont_ids` [node_mastery], `recent_ids`, and the
running `used` set) now compares puzzles by **`BootstrapGatedIdentityReader`
group key** instead of raw integer `question_id`. The picked lists it returns
are still raw integer `question_id`s (the UI needs an answerable question) —
`LEGACY_QUESTION_ID_REMOVED = NO`, `LEGACY_QUESTION_ID_REWRITTEN = NO`,
`STORAGE_KEY_CHANGED = NO`.

### Reconciled OUT of scope (LC018 "approximately 670")

`grimoire_api.py:api_weakness_report` (`SELECT rl.topic, rl.level, COUNT(*),
SUM(...) FROM review_log rl … GROUP BY rl.topic, rl.level`) — the aggregation
axis is `(topic, level)`, **`question_id` is neither selected nor grouped**.
Per LC018 §1 ("cover the exact semantic call sites rather than stale line
numbers") this is `LEGACY_COMPATIBILITY_ONLY` and was **not wired** — re-keying
a topic/level accuracy rollup on `source_record_uuid` would be meaningless.

## 3. `hot == False` contract (mandatory) — how it is guaranteed

1. **Table guard.** `generate_daily_training` calls the new
   `_identity_tables_present(conn)` first — a `sqlite_master` /
   `information_schema.tables` catalog lookup that returns 0 rows (no error, **no
   transaction abort**) when the candidate `puzzle_identity_*` tables are absent,
   which is the case in **every environment today** (the identity migration is a
   candidate, not applied to the runtime DB). When absent: no
   `BootstrapGatedIdentityReader` is constructed, `_gk_map` stays `{}`, and
   `_gk(qid)` returns `("legacy", str(qid))` — the recommendation logic is
   **byte-identical** to before, and the resolver is never touched.
2. **Gated reader.** When the tables *are* present but genesis is cold
   (`bootstrap_state().hot == False`), `reader.keys_for(...)` short-circuits
   before any `resolve_*` call and returns `("legacy", str(id))` keys.
   `HOT_FALSE_RESOLVER_QUERY_COUNT = 0` — a test poisons
   `DualIdReadWindow.resolve_legacy_question_id` /
   `resolve_many_legacy_question_ids` to raise and asserts
   `generate_daily_training` still completes.
3. **Parity.** A test runs `generate_daily_training` with the same seeded data
   (a) with the identity tables **absent** and (b) with them **present but
   cold**, and asserts the output lists are **identical**.
   `HOT_FALSE_OUTPUT_BYTE_IDENTICAL = PASS`.

**Landing LC019-W1 has no effective production behaviour change while bootstrap
remains cold.**

## 4. `hot == True` contract (tested with synthetic identities, no real Genesis)

| resolution | reader result | `generate_daily_training` effect |
|---|---|---|
| `EXACT` | `("uuid", u)` | two legacy `question_id`s that resolve to the same `source_record_uuid` share a `group_key` → excluding one excludes the other (test: legacy 500 and 777 → same uuid; answering 500 suppresses 777) |
| `RETIRED` | `("uuid", u)`, `retired=True`, `attachable=False` | still resolves for history; `assert_attachable("600")` raises `IdentityNotAttachable` |
| `AMBIGUOUS` | `("unresolved", qid)`, `.candidates` | **never `("uuid", …)`**, never merged into a uuid bucket, never auto-picked. `AMBIGUOUS_ALIAS_AUTO_MERGE = NO` |
| `MISSING` | `("legacy", qid)` | compatibility — the int id stays the key |
| `UNAVAILABLE` | `("unavailable", qid)` | grimoire's `_identity_tables_present` guard keeps it on the raw-int path before this is ever reached in the wired function; the reader-level `UNAVAILABLE` is still asserted |

## 5. Firewalls honoured

- `APP_PY_CHANGED = NO` · `APP_PY_WRITER_ACQUIRED = NO` — the ~26 `app.py`
  aggregate readers remain deferred to LC019-W2.
- `COMMUNITY_LEADERBOARD_REWARDS_CHANGED = NO` · `LEADERBOARD_REWARD_WIRING_CHANGED = NO`
  · `XP_AUTHORITY_CHANGED = NO` · `RANK_AUTHORITY_CHANGED = NO` — Wave 1b needs a
  separate Owner decision.
- `WRITE_PATH_CHANGED = NO` — no `review_log` / `srs_cards` / `mistake_log` /
  `map_battle_progress` / `insert_review_log_with_identity` / `review_service` /
  question-idempotency write touched. A test AST-scans the new `grimoire_api.py`
  code for `create_*` / `mint_*` / `GenesisBootstrap` / `INSERT INTO
  puzzle_identity` / `UPDATE puzzle_identity` — none present.
- `SCHEMA_CHANGED = NO` · `MIGRATION_CHANGED = NO` · `DATA_CHANGED = NO` ·
  `UUID_BACKFILL = NO`.
- `REAL_GENESIS_BOOTSTRAP = NO` · `IDENTITY_REGISTRY_POPULATION = NO` ·
  `BOOTSTRAP_HOT_CHANGED = NO` — `GenesisBootstrap.apply()` was not executed;
  `bootstrap_state().hot` stays `False`.
- `BATTLEFIELD_AUTHORITY_CHANGED = NO` · `PLAYER_APPEARANCE_AUTHORITY_CHANGED = NO`
  — E051/E052/E053 and A043/A046/A047 untouched.
- `B063_SCOPE_TOUCHED = NO` · `B064_SCOPE_TOUCHED = NO` ·
  `CURRENT_RPG_V1_RELEASE_SCOPE_CHANGED = NO`.
- `PRODUCTION_QUERY = NO` · `PRODUCTION_MUTATION = NO` · `DEPLOY = NO` ·
  `MASTER_MERGE = NO` · `SECRET_KEY_TOUCHED = NO`.

## 6. Tests

`tests/test_lc019_w1_grimoire_bootstrap_gated_reader.py`:

- `hot == False` parity (tables absent vs present-cold identical output) + resolver-query-count 0
- reader `group_key == ("legacy", str(id))` at hot False
- `hot == True` EXACT folds two legacy ids
- `hot == True` RETIRED uuid history-only / not attachable / `assert_attachable` raises
- `hot == True` AMBIGUOUS → `("unresolved", id)`, never merged, `assert_attachable` raises
- `hot == True` MISSING → legacy; UNAVAILABLE (tables dropped) → reader `UNAVAILABLE` + grimoire guard falls back to legacy
- scope firewall AST scan
- **real disposable PostgreSQL 16.14 parity**: `_identity_tables_present` returns
  `False` before / `True` after `upgrade()` **without aborting the transaction**;
  the full reader classification matrix (EXACT fold, RETIRED, AMBIGUOUS,
  MISSING) identical to SQLite

`SQLITE_PARITY = PASS` (7 SQLite tests). `POSTGRES_PARITY` — see final report.
LC011 + LC013 + LC014 + LC015 + LC019-W1 SQLite regression = **102 passed**.
`PY_COMPILE = PASS`. `APP_IMPORT = PASS`. `TASK_INTRODUCED_FAILURES = 0`.

## 7. Next

- `LC019_W2_BOOTSTRAP_GATED_IDENTITY_READER_APP_AGGREGATE_WIRING_IMPLEMENTATION_001`
  — the ~26 `app.py` aggregate readers, via the app.py-writer slot, serialized
  after E051's app.py changes land cleanly. **Do not auto-start** if app.py
  canonical integration ordering is not yet clean.
- `LC019_W1B_COMMUNITY_LEADERBOARD_REWARD_IDENTITY_REBUCKET_OWNER_DECISION_001`
  — separately gated (feeds XP/rank).
- The Owner-gated `GenesisBootstrap.apply()` remains the sole action that flips
  `hot`.
