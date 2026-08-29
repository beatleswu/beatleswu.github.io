# LC019-W2 — Canonical-Identity App Reader Integration (implementation)

Status: **implemented. 7 required app.py aggregate-reader sites fold by canonical
identity `group_key`. No-op until bootstrap is hot. `app.py` is the only runtime
file changed. No schema/data/Genesis/write-path/master-merge.**

Mode: `IMPLEMENTATION` · `APP_PY_SINGLE_WRITER = LC019_W2`.

Base: `origin/master` `81ab0f263bf72614c303199707e5e42d3ae559a4`
(tree `28c81698dd883720da79517084d0781a8b551e15`) — B071A/B071C/B071D historical
leaderboard evidence merged; the B071 app.py writer slot is released.
`APP_PY_WRITER_CONFLICT = NO`.

---

## 1. Shared integration (app.py, after `get_db()`)

| symbol | role |
|---|---|
| `from identity_read_adapter import BootstrapGatedIdentityReader` | the already-canonical LC011–LC017 reader (also used by grimoire LC019-W1) |
| `_identity_tables_present(conn)` | `sqlite_master` / `information_schema` catalog probe — never aborts the caller's tx when the candidate tables are absent (every env today) |
| `_identity_group_key_map(conn, ids)` | `{str(id): group_key}`; returns `{}` when tables absent **or** `reader.hot` is False → callers fall back to `("legacy", str(id))` and the resolver is never touched |
| `_identity_group_key(gk_map, qid)` | one id → `group_key`, default `("legacy", str(qid))` |
| `_IdentityKeyedSet(ids, gk_map)` | set whose `in` / `&` / `len` / `bool` compare by `group_key`. Cold: `group_key` of `N` is `("legacy", str(N))` — a **bijection** with the raw id, so it behaves byte-identically to a plain `set` of ids. Hot: two ids sharing a `source_record_uuid` collapse to one member; an `AMBIGUOUS` id keeps its own `("unresolved", id)` bucket (never merged). Read-only — never mints or writes. |

## 2. Wired sites (7 required)

| # | site | route(s) | what folds |
|--|--|--|--|
| 1 | `training_daily` | `GET /api/training/daily` | `done_today`, `mastered_ids`, `seen_ids`, `selected_set` → `_IdentityKeyedSet`; the `done_today & stored_ids` / `& queue_set` intersections fold too. Picked ids stay raw ints. |
| 2 | `recommend_questions` | `POST /api/recommend` | `srs_map` / `mistake_map` re-keyed by `group_key`; `is_mastered` / score / `wrong_count` lookups use `_gk(qid)`. Output ids stay raw ints. |
| 3 | `_adventure_correct_question_ids` / `_adventure_state` | (state consumed by 5 adventure routes) | `correct_ids`, `attempted_ids`, `defeated_ids` → `_IdentityKeyedSet`; per-zone `seen` / `attempted` / `defeated` / star counts fold. Helper still returns raw ids; the fold is in `_adventure_state`. |
| 4 | `curriculum_summary` | `GET /api/curriculum/summary` | `qid_meta` gains a `group_key` index; `defeated_ids` folds; per-`(discipline×stage)` `practiced` / boss-defeated counters dedup on `group_key` (`_practiced_seen` / `_boss_seen`). `cardsCount` stays a raw card count. |
| 5 | `map_progress` | `GET /api/map-progress` | `seen_ids`, `defeated_ids` → `_IdentityKeyedSet`; per-map `practiced` / `defeated` / boss status / `pct` fold. |
| 6 | `_stage_completion_state` / `quest_board_progress` | `GET /api/quest-board`, `GET /api/quest-board/progress` | `practiced_ids` → `_IdentityKeyedSet`; `completed` / `practiced` / `next_question_id` fold. **`_stage_completion_state(..., fold_identity=False)`** keeps raw-id semantics unconditionally — `POST /api/rewards/sync` passes it, so the reward-grant write path is provably identical in every bootstrap state. |
| 7 | `srs_due` | `GET /api/srs/due` | `seen` → `_IdentityKeyedSet` so a question whose identity already has a real due card is not given a synthesized default card. Returned `question_id`s stay raw ints. |

`OPTIONAL_SITES_CHANGED = NO` — `_newbie_daily_completed_count`,
`_training_contaminated_total`, `_load_rt_calibration` untouched (W2_OPTIONAL,
separate Coordinator decision). Pattern-B readers
(`api_weakness_report`, `get_discipline_counts`, `_home_report_weakness_summary`,
`rt_result` radar, stats dashboards, leaderboards, profile, friend list,
`COUNT(*)` guards, idempotency reads, `srs_card`, mistake outputs) unchanged.

## 3. hot == False contract (mandatory)

- `_identity_tables_present` is False in every environment today (the identity
  migration is a candidate, not applied to the runtime DB) → `_identity_group_key_map`
  returns `{}` → every `_IdentityKeyedSet` / `_gk` is the raw-id bijection.
- If the tables were present but genesis not applied, `_identity_group_key_map`
  still returns `{}` (`reader.hot` short-circuit) — no resolver call.
- **Tests:** every wired route is called with (a) identity tables **absent** and
  (b) tables **present but cold** with all `DualIdReadWindow.resolve_*` methods
  wrapped to raise — the two JSON responses are asserted **equal** and the
  resolver call count is asserted **0**.
  `HOT_FALSE_ALL_ROUTE_OUTPUTS_IDENTICAL = PASS`,
  `HOT_FALSE_TOTAL_RESOLVER_QUERY_COUNT = 0`.

## 4. hot == True contract (synthetic identities, no real Genesis)

| state | `group_key` | effect |
|--|--|--|
| `EXACT` / `LEGACY_ALIAS_EXACT` | `("uuid", u)` | two legacy ids sharing `u` are one member — dedup / exclusion / counts fold |
| `RETIRED` | `("uuid", u)` | still a member (history); `attachable=False` |
| `AMBIGUOUS` | `("unresolved", id)` | own bucket — **never** `("uuid", …)`, two distinct ambiguous ids never collapse. `AMBIGUOUS_ALIAS_AUTO_MERGE = NO` |
| `MISSING` | `("legacy", id)` | raw-id behaviour |
| `UNAVAILABLE` | n/a | `_identity_tables_present` guard keeps the wired body on the raw-id path |

Route-level folds asserted: `map_progress` (`practiced` for a map with a
content-duplicate pair increases by one when only one has a card),
`srs_due` (the duplicate does not get a second synthetic card).

## 5. Firewalls

`APP_PY_CHANGED = YES` (the single authorised writer). `WRITE_PATH_CHANGED = NO`
(review / SRS / mistake / rating-test / account-wipe / submission-idempotency
untouched; `rewards_sync` uses `fold_identity=False`). `SCHEMA_CHANGED = NO` ·
`MIGRATION_CHANGED = NO` · `DATA_CHANGED = NO` · `UUID_BACKFILL = NO`.
`REAL_GENESIS_BOOTSTRAP = NO` · `IDENTITY_REGISTRY_POPULATION = NO` ·
`BOOTSTRAP_HOT_CHANGED = NO` (`GenesisBootstrap.apply()` not called).
`HISTORICAL_EVIDENCE_MIGRATION_CHANGED = NO` ·
`HISTORICAL_LEADERBOARD_CONSUMER_CHANGED = NO` · `RESTORATION_RUNNER_CHANGED = NO`
· `B050_POLICY_CHANGED = NO` (`community_leaderboard_rewards.py`, the B071
migration/runner, `grimoire_api.py`, identity modules — all byte-identical).
`A049_AUTHORITY_CHANGED = NO` · `MONSTER_CATALOG_AUTHORITY_CHANGED = NO` ·
`SHOP_ENABLED = NO` · `LOADOUT_ENABLED = NO` · `PAYMENTS_CHANGED = NO` ·
`ART_SCOPE_TOUCHED = NO`. `PRODUCTION_QUERY = NO` · `PRODUCTION_MUTATION = NO` ·
`DEPLOY = NO` · `MASTER_MERGE = NO` · `SECRET_KEY_TOUCHED = NO`.

## 6. Tests / validation

`tests/test_lc019_w2_app_reader_identity_folding.py` — 15 SQLite + 1 real
disposable PostgreSQL 16.14 parity:
- hot=False byte-identical + zero-resolver-query for all 7 sites (6 routes
  parametrized + `quest_board_progress` + a full-sweep resolver-count-0 test)
- `_IdentityKeyedSet` / `_identity_group_key_map` cold bijection
- hot=True EXACT / LEGACY_ALIAS / RETIRED / AMBIGUOUS / MISSING / UNAVAILABLE
- hot=True route folds (`map_progress`, `srs_due`)
- scope-firewall source scan + optional-sites-untouched scan
- PG parity: catalog guard False→True without aborting the tx; full
  classification matrix identical to SQLite

Regression on this branch: `PY_COMPILE` / `APP_IMPORT` / `grimoire_api` import
PASS · A034/A043/A046/B036/RPG-B021/Wave1/Wave2 = 72 · adventure / quest / B050 /
B071A = 218 (+2 skip) · `rewards_sync` atomic-idempotency / e9 / D5B-idempotency
= 187 (+1 skip) · LC011–LC019 identity = 141 (+45 PG-gated skip) · e9 core / D0xx
quest = 99. `TASK_INTRODUCED_FAILURES = 0`.

## 7. Next

`LC019_W2_FRESH_MASTER_RECONCILIATION_AND_MERGE_CANDIDATE_001` (Coordinator
review first; Genesis remains separately Owner-gated).
