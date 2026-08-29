# LC019-W2 — Canonical-Master App Integration & Writer-Governance Preflight

Status: **READ-ONLY preflight. No implementation, no app.py write, no schema/data
change, no Genesis, no production. Deliverable = this document.**

Mode: `READ_ONLY_PREFLIGHT`.

---

## 1. Canonical base

| field | value |
|---|---|
| `CURRENT_ORIGIN_MASTER` | `dc5728304a21249c38cd0c234ec4791247ca7fe9` |
| `CURRENT_ORIGIN_MASTER_TREE` | `36b2062cd6b8eea68a1e88421a4b56685d9560de` |
| matches expected | YES (HEAD + TREE exact) |
| master advanced since LC019-W1-R2 | NO — `dc5728304` is the LC019-W1 merge commit itself |
| `LC019_W1_CANONICAL_PRESENT` | **YES** — `grimoire_api.py` on master imports `BootstrapGatedIdentityReader`, has `_identity_tables_present`, and `generate_daily_training` compares its dedup/exclusion sets by `_gk()` group key |

## 2. W1 canonical contract (verified on `dc5728304`)

- `WIRED_FILE_COUNT = 1` (`grimoire_api.py`), `WIRED_CALLSITE_COUNT = 2`
  (`generate_daily_training`: SRS-due set L181, review_log DISTINCT recent set L196).
- `HOT_FALSE_OUTPUT_BYTE_IDENTICAL = PASS`, `HOT_FALSE_RESOLVER_QUERY_COUNT = 0`
  — `_identity_tables_present` guard → tables absent in every env today →
  `_gk_map = {}` → `_gk(qid) = ("legacy", str(qid))`.
- `api_weakness_report` (`grimoire_api.py` L714, `GROUP BY rl.topic, rl.level`) —
  no `question_id` key → **LEGACY_COMPATIBILITY_ONLY**, correctly left unwired.

Identity foundation invariants on master (unchanged from LC015/LC016):
`hot=False → ("legacy", question_id)` always today; `EXACT→("uuid",u)` attachable;
`RETIRED→("uuid",u)` history-only not-attachable; `AMBIGUOUS→("unresolved",qid)`
fail-closed **never merged**; `MISSING→("legacy",qid)`; `UNAVAILABLE→("unavailable",qid)`.
Adapter imports only the read window — no create / mint / uuid4 / uuid5 / bootstrap.

## 3. W2 target callsite inventory (canonical master `app.py`, 29,390 lines)

Every Learning-Core reader that keys / dedups / excludes / counts by legacy
`question_id`. Two sub-patterns:

- **Pattern A** — `question_id` is a **dedup / exclusion / membership / set key**
  (`seen_ids`, `done_today`, `mastered_ids`, `practiced_ids`, `defeated_ids`,
  `wrong_ids - mastered_ids`, `qid not in X`, `all(qid in practiced_ids …)`,
  `queue & answered`). Identity fold **changes the result** → **W2**.
- **Pattern B** — `question_id` is a **metadata-lookup key** (`qdisc.get(qid)`,
  `qs_map.get(qid)`) or a `GROUP BY question_id` whose groups are summed straight
  back up (attempt totals). Identity fold **does not change the result** →
  **LEGACY_COMPATIBILITY_ONLY**.

### 3.1 W2_REQUIRED — Pattern A, player-facing (app.py)

| # | file:line | function / route | current identity input | legacy alias use | req-time UUID | ambiguity behavior today | player-facing effect | app.py? |
|--|--|--|--|--|--|--|--|--|
| 1 | app.py:10935/10973/10984/10994/11006 (+`add()` dedup) | `training_daily` — `GET /api/training/daily` | `done_today` / `due_ids` / `mastered_ids` / `mistake_ids` / `seen_ids` — all `SELECT [DISTINCT] question_id FROM review_log\|srs_cards\|mistake_log`, compared as raw-int sets; `selected_set` + `qid not in done_today` | raw int `question_id` everywhere | none | none — raw-int set membership | **daily 5-3-2 training queue** (the app.py twin of grimoire W1's `generate_daily_training`) | YES |
| 2 | app.py:10803/10807 | `recommend_questions` — `POST /api/recommend` | `srs_map` / `mistake_map` keyed by `question_id`; `is_mastered(qid)` / `mistake_map.get(qid)` / `srs_map.get(qid)` per candidate | raw int | none | none | next-question recommendations | YES |
| 3 | app.py:11707/11721 | `_adventure_correct_question_ids` / `_adventure_state` | `correct_ids` = `DISTINCT question_id` (grade≥3, map-battle marker); matched against `q['id']` per zone/boss | raw int set | none | none | **Adventure Lord zone/boss progression** | YES |
| 4 | app.py:12930/12933 | `curriculum_summary` — `GET /api/curriculum/summary` | `srs` rows + `defeated_ids` (`DISTINCT question_id`, marker); `qid_meta.get(qid)`, `if qid in defeated_ids` | raw int | none | none | curriculum 學科×階段 practiced / boss-defeated counts | YES |
| 5 | app.py:15766/15770 | `map_progress` — `GET /api/map-progress` | `seen_ids` (srs) + `defeated_ids` (marker); per question `if qid in seen_ids` / `in defeated_ids`, boss status | raw int | none | none | **map / chapter progress bars + book-boss status** | YES |
| 6 | app.py:15581 + 15671 | `_stage_completion_state` / `quest_board_progress` — `GET /api/quest-board[/progress]` | `practiced_ids` = all `srs_cards.question_id`; `all(qid in practiced_ids for qid in seg['question_ids'])`; `next(qid … if qid not in practiced_ids)` | raw int | none | none | **guild-quest completion + claimable state** (gates reward claim; the claim *write* is separate/out-of-scope) | YES |
| 7 | app.py:15380 | `srs_due` — `GET /api/srs/due` | `seen = {r['question_id'] …}`; `due += [… for q in qs if q['id'] not in seen]` | raw int; returns `question_id` as data | none | none | SRS due list (client renders raw ids; only the `seen` dedup is identity-relevant) | YES |

### 3.2 W2_OPTIONAL — Pattern A, low player-facing / semantics-question (app.py)

| # | file:line | function | note |
|--|--|--|--|
| 8 | app.py:9015 | `_newbie_daily_completed_count` | `queue_ids & answered` (`DISTINCT question_id` today). Fold could match queue-id vs answered-dup. Newbie daily counter only. |
| 9 | app.py:11212/11221 | `_training_contaminated_total` | `len(wrong_ids - mastered_ids)` — set difference by `question_id`. A training-UI count. |
| 10 | app.py:27703/27715 | `_load_rt_calibration` | `GROUP BY question_id HAVING COUNT(*)>=N` — cross-user difficulty calibration `{qid:{n,acc,avg_elo}}`. Fold would **merge attempt samples** for content-dups (arguably better); global (no `user_id`), rating-test weighting only. |

### 3.3 LEGACY_COMPATIBILITY_ONLY (Pattern B / no `question_id` axis / single-id / submission-id) — **not wired**

| file:line | function | why |
|--|--|--|
| app.py:4218 | `get_discipline_counts` | `GROUP BY question_id` then `SUM(cnt)` per discipline = attempt total; `q_disc.get(qid)` metadata lookup. Fold-neutral. |
| app.py:11584 | `_home_report_weakness_summary` | `GROUP BY rl.question_id, rl.discipline` then summed to discipline totals (attempt totals). Fold-neutral. Already `question_id`-keyed for rename-immunity. |
| app.py:29039 | `rt_result` radar merge | `question_id → qdisc` lookup, per-attempt sample counting (deliberately not deduped). |
| app.py:9769 | `_admin_retention_event_union_sql` | `user_id`/date rollup, no `question_id`. |
| app.py:15863 | `stats_daily` | `GROUP BY DATE(reviewed_at)`. |
| app.py:16618-16725 | `stats_dashboard` (heatmap / weekly / `week_stats` / topic / difficulty / today) | date-range + `topic`/`difficulty` snapshot rollups; no `question_id`. |
| app.py:18306 | `leaderboard` | `GROUP BY u.id` — user rollup. |
| app.py:18691 | `public_profile` | `COUNT(*)` user totals. |
| app.py:18934 / 18979 | `friend_list` | `MAX(DATE(reviewed_at))` per user; `GROUP BY r.user_id, DATE(...)`. |
| app.py:6920 | `get_today_free_count` | `COUNT(*)` daily quota, no `question_id`. |
| app.py:17765 | `_compute_title_metrics` | `COUNT(*)` answered total. |
| app.py:14248 | `_map_battle_progression_already_applied` | `source_context` idempotency probe. |
| app.py:14510 | review submission retry check | `WHERE submission_id=?`. |
| app.py:29289 | `rt` claim guard | `WHERE source='rt:sid'` COUNT. |
| app.py:13656 | `srs_card(qid)` — `GET /api/srs/card/<int:qid>` | single exact-id card fetch. |
| app.py:16756 / 16783 | `get_mistakes` / `mistake_stats` | `mistake_log` rows 1:1 to output; `question_id` returned as data + `qs_map` decorate; `worst5` LIMIT 5. |

### 3.4 WRITE_PATH_OUT_OF_SCOPE

`app.py:9604-9608` (account wipe DELETEs), `app.py:14676` / `14764` (review-submit
card/mistake single-id reads on the write path), `app.py:16798` (`/api/mistakes/remove`
DELETE), `app.py:28939` (rt-session mistake_log read+UPDATE). Review/SRS/mistake
**writes** are not in any LC019 wave.

### 3.5 Adjacent (not app.py, not this task)

`grimoire_api.py` `node_mastery` reads (L550/595/606/685) — `question_id`-keyed
purity membership + metadata lookup, in the already-wired W1 file. A **W1 addendum**
candidate, not W2. `community_leaderboard_rewards.py:364` — **LC019-W1B**, separate
Owner decision (feeds XP / rank).

## 4. app.py-writer governance

`LC019_W2_APP_PY_REQUIRED` = **YES**. Every W2_REQUIRED reader in §3.1 is an inline
function/route body in `app.py`; there is no non-app.py seam. W2 needs:

- **one import** — `from identity_read_adapter import BootstrapGatedIdentityReader`
  in the app.py import cluster (~L162);
- **one shared helper** — an app.py-local `_identity_tables_present(conn)` +
  per-unit `BootstrapGatedIdentityReader` construction (mirroring grimoire W1);
- **7 reader bodies** re-keyed to compare by `group_key` (§3.1 rows 1-7), raw-int
  `question_id` preserved as returned/answerable data.

`APP_PY_EXACT_CALLSITES` (canonical `dc5728304`): import ~L162; `recommend_questions`
~L10803/10807; `training_daily` ~L10935/10973/10984/10994/11006; `_adventure_*`
~L11707/11721; `curriculum_summary` ~L12930/12933; `srs_due` ~L15380;
`_stage_completion_state`/`quest_board_progress` ~L15581/15671; `map_progress`
~L15766/15770. (`_newbie_daily_completed_count` L9015, `_training_contaminated_total`
L11212, `_load_rt_calibration` L27703/27715 if W2_OPTIONAL rows 8-10 are pulled in.)

`APP_PY_EXPECTED_CHANGE_SCOPE` = additive-only, ~+120/-40 lines across ~9 hunks;
no route signature change, no response-shape change, no write path, no import
removed.

### 4.1 B071C overlap

`B071C_APP_PY_OVERLAP` = **YES**.

`refs/heads/codex/b071c-historical-leaderboard-evidence-fresh-master-merge-candidate`
(`7e686b58a`, merge-base `3ace7c748`) is an **unmerged fresh-master merge candidate**
that modifies `app.py` (+10): a migration import at ~L162 (**same import cluster
W2 needs**) and an `init_db()` block (~L5600) calling
`upgrade_historical_leaderboard_evidence_schema`. It also touches
`community_leaderboard_rewards.py` (+87) and adds
`migrations/historical_leaderboard_evidence_v1.py` +
`tools/historical_leaderboard_restoration.py`. Sibling `b071a` (`4e4693a2a`)
carries the same +10 app.py change.

The two app.py footprints do not share a logic region (B071C = import + `init_db`;
W2 = import + ~9 reader bodies), so the only literal collision is one adjacent
import line. But per the standing rule — **two lanes must not both hold the app.py
writer slot** — and B071C's change is startup/`init_db` wiring queued for a master
merge:

`LC019_W2_SAFE_TO_START_WHILE_B071C_ACTIVE` = **NO**.

## 5. Identity authority (preserved, no redesign)

`SOURCE_RECORD_UUID_CANONICAL_IDENTITY = YES` · `LEGACY_INTEGER_ALIAS_SUPPORTED = YES`
· `REQUEST_TIME_UUID_GENERATION = NO` · `AMBIGUITY_FAIL_CLOSED = YES` ·
`AMBIGUOUS_ALIAS_AUTO_MERGE = NO`. W2 consumes only `BootstrapGatedIdentityReader`
group keys; no new identity surface.

## 6. Genesis / DB / Production firewalls

`OWNER_GATE_FOR_GENESIS = NOT_GRANTED`. `REAL_GENESIS_BOOTSTRAP = NO` ·
`IDENTITY_REGISTRY_POPULATION = NO` · `BOOTSTRAP_HOT_CHANGED = NO`. W2 is a no-op
until `bootstrap_state().hot` (the `_identity_tables_present` guard + the adapter's
`hot=False` short-circuit both hold on the runtime DB).

`W2_FUTURE_SCHEMA_CHANGE_REQUIRED` = **NO** — the registry/alias/lineage schema
(`migrations/puzzle_identity_registry_v1.py`) already exists on master; W2 reads it.
`W2_FUTURE_DATA_CHANGE_REQUIRED` = **NO for W2 itself** — W2 never populates. (The
separate Owner-gated `GenesisBootstrap.apply()` is the only thing that ever writes
identity rows, and it is not part of W2.)

`SCHEMA_CHANGED = NO` · `MIGRATION_CHANGED = NO` · `DATA_CHANGED = NO` ·
`UUID_BACKFILL = NO` · `WRITE_PATH_CHANGED = NO` · `PRODUCTION_QUERY = NO` ·
`PRODUCTION_MUTATION = NO` · `DEPLOY = NO` · `ROLLBACK = NO`.

## 7. Cross-lane

`B071_SCOPE_TOUCHED = NO` · `B071A_SCOPE_TOUCHED = NO` · `B071C_SCOPE_TOUCHED = NO`
(read-only inspection of the b071c ref only) · `MONSTER_CATALOG_CHANGED = NO` ·
`E053_SCOPE_TOUCHED = NO` · `A049_AUTHORITY_CHANGED = NO` · `SHOP_ENABLED = NO` ·
`LOADOUT_ENABLED = NO` · `PAYMENTS_CHANGED = NO`.

## 8. W2 implementation test matrix (design only)

| id | coverage | how |
|--|--|--|
| `HOT_FALSE_BYTE_IDENTITY` | each wired route/function returns byte-identical output vs pre-W2, tables absent **and** tables-present-cold, same seeded `review_log`/`srs_cards`/`mistake_log`/`node_mastery` | golden-output capture on canonical `app.py` per route (`/api/training/daily`, `/api/recommend`, `/api/map-progress`, `/api/curriculum/summary`, `/api/quest-board/progress`, `/api/srs/due`, adventure state) |
| `HOT_FALSE_ZERO_RESOLVER_QUERY` | resolver never touched while cold | poison `DualIdReadWindow.resolve_legacy_question_id` / `resolve_many_legacy_question_ids` to raise; every wired path still completes |
| `EXACT_UUID` | two legacy ids → one `source_record_uuid` fold: excluding/counting one affects the other | synthetic identities (no real Genesis); assert `training_daily` drops the dup, `map_progress` counts it once per identity, quest `practiced` credits the fold |
| `LEGACY_ALIAS_EXACT` | `LEGACY_QUESTION_ID` alias present, ACTIVE → same fold as EXACT | synthetic `_insert_alias(u, "LEGACY_QUESTION_ID", …)` |
| `RETIRED` | retired identity still resolves for history, `attachable=False`, never picked as "new" | synthetic retire; assert `assert_attachable` raises, `seen`/`defeated` still recognizes history |
| `AMBIGUOUS` | `("unresolved", qid)` — never merged into a uuid bucket, never auto-picked, `AMBIGUOUS_ALIAS_AUTO_MERGE=NO` | two current identities for one legacy id across contexts |
| `MISSING` | `("legacy", qid)` — behaves exactly as today | id with no alias row |
| `UNAVAILABLE` | tables dropped mid-request → `("unavailable", qid)`; the `_identity_tables_present` guard keeps the wired body on the raw-int path | drop `puzzle_identity_alias` |
| `SQLITE_PARITY` | full matrix on SQLite | in-memory learning DB fixtures |
| `POSTGRES_PARITY` | full matrix on real disposable PostgreSQL 16.14 | `postgres:16.14-alpine` container, in-container `SELECT 1` readiness gate |
| `CURRENT_MASTER_REGRESSION` | no regression to A049 authority / battlefield / equipment | re-run `test_a034/a043/a046/b036/rpg_b021/wave1/wave2` + the existing route smoke tests unchanged |
| route-level smallest set | `test_training_daily`, `test_recommend`, `test_map_progress`, `test_curriculum_summary`, `test_quest_board_progress`, `test_srs_due`, `test_adventure_state` — one golden-output test each, hot=False | Flask test client against canonical `app.py` |

## 9. W2 scope decision

| field | value |
|---|---|
| `W2_REQUIRED_FILE_COUNT` | **1** |
| `W2_REQUIRED_FILES` | `app.py` |
| `W2_REQUIRED_CALLSITE_COUNT` | **7 semantic sites** (§3.1) — `training_daily`, `recommend_questions`, `_adventure_correct_question_ids`/`_adventure_state`, `curriculum_summary`, `map_progress`, `_stage_completion_state`/`quest_board_progress`, `srs_due` — plus 1 shared import + 1 shared helper. (+3 `W2_OPTIONAL`, §3.2, Coordinator's call.) |
| `LC019_W2_APP_PY_REQUIRED` | **YES** |
| `APP_PY_WRITER_REQUIRED_FOR_IMPLEMENTATION` | **YES** |
| `W2_CAN_RUN_CONCURRENTLY_WITH_B071C` | **NO** |
| `W2_START_GATE` | **`WAIT_FOR_B071C_APP_PY_WRITER_RELEASE`** — resume once B071A/B071C's app.py change has landed on canonical master (or its lane has explicitly released the writer slot); then re-anchor W2 to the new master head and re-verify §3 line numbers before wiring. |

## 10. Firewalls honoured by this task

`APP_PY_CHANGED = NO` · `SCHEMA_CHANGED = NO` · `DATA_CHANGED = NO` ·
`REAL_GENESIS_BOOTSTRAP = NO` · `IDENTITY_REGISTRY_POPULATION = NO` ·
`BOOTSTRAP_HOT_CHANGED = NO` · `PRODUCTION_QUERY = NO` · `PRODUCTION_MUTATION = NO`
· `DEPLOY = NO` · `SECRET_KEY_TOUCHED = NO` · `MASTER_MERGE = NO`. Deliverable is
this planning doc on an isolated branch; no runtime/source file touched.
