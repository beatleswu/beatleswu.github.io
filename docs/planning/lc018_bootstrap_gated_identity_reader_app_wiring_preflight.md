# LC018 — Bootstrap-Gated Identity Reader: App-Wiring Preflight

Status: **READ-ONLY preflight. No wiring, no runtime change, no Genesis, no
master merge.** Produces the exact implementation contract + call-site matrix
for LC019.

Mode: `READ_ONLY_CALLSITE_AND_INTEGRATION_PREFLIGHT_NO_WIRING_NO_GENESIS`.

---

## 0. Canonical state (verified fresh-fetch)

| field | value |
|---|---|
| `CURRENT_ORIGIN_MASTER` | `3f98c204a2b249763ad3d8d0730e5d3a0764622b` (== LC017 merge; unchanged since) |
| identity foundation on master | `puzzle_identity_read_window.py`, `identity_read_adapter.py`, `puzzle_identity_store.py`, `puzzle_identity_genesis_bootstrap.py`, `migrations/puzzle_identity_registry_v1.py`, `tools/lc011_*` / `tools/lc012_*` — all present |
| `IDENTITY_AUTHORITY` | `source_record_uuid` |
| `LEGACY_INTEGER_ID` | compatibility alias only (`question_id`) |
| `BOOTSTRAP_HOT` | `FALSE` (no APPLIED receipt, no identities) |
| `GENESIS_AUTHORIZED` | `NO` |
| `REQUEST_TIME_UUID_GENERATION` | **not present** — `identity_read_adapter.py` and `puzzle_identity_read_window.py` contain **0** `uuid4()` / `uuid5(` / `create_*` / `mint_*` / `GenesisBootstrap` / `INSERT` occurrences (the only matches are docstring prose); AST-checked by the LC014/LC015 test suites |

## 1. Call-site inventory — Learning Core reads keyed by legacy `question_id`

Scanned: `app.py`, `grimoire_api.py`, `community_leaderboard_rewards.py`,
`daily_challenge_d5b.py`, `question_idempotency.py`, `daily_challenge_authority.py`,
`map_battle_runtime.py`, `map_battle_persistence.py`, `map_battle_legacy_adapter.py`,
`review_service.py`, `legacy_review_serializer.py`, `shadow_dashboard.py`.

Learning-Core tables in play: `review_log`, `srs_cards`, `mistake_log`
(+ `user_stats`). `review_log` alone has **61** references in `app.py`;
`srs_cards` **22**; `mistake_log` **~15**.

### 1.1 `TOTAL_CALLSITES` (read sites in scope)

| surface | module | read sites keyed by / returning `question_id` |
|---|---:|---|
| review_log aggregates | `app.py` | ~13 (`app.py:4208`+`4211`, `8886`, `10806`, `10877`, `11083`, `11457`, `11578`, `12804`, `15620`, `27561`, `27570`, `28892`) |
| SRS reads | `app.py` | ~10 (`10674`, `10844`, `10855`, `11092`, `11592`, `12801`, `15230`, `15431`, `15521`, `15616`) |
| mistake_log rollups | `app.py` | ~3 (`10678`, `10865`, `16634`) |
| Learning display | `grimoire_api.py` | 3 (`148` srs due-set, `163` review DISTINCT question_id, `670` weakness aggregate) |
| Leaderboard scoring | `community_leaderboard_rewards.py` | 1 (`364` `GROUP BY user_id, question_id`) |
| review_log non-question-id reads (count / submission_id / date-range) | `app.py` + `daily_challenge_d5b.py` + `question_idempotency.py` | ~25 (`app.py:6910`, `9640`, `14119`, `14379`, `14381`, `15715`, `16472`–`16573`, `17609`, `18159`, `18544`, `18787`, `18832`; `daily_challenge_d5b.py:84`; `question_idempotency.py:135`) |
| Adventure attempt correlation | `map_battle_runtime.py` | ~4 (`726`, `744`, `835`, `1243`) |

**`TOTAL_CALLSITES` (read, in scope) ≈ 59.**

## 2. `CALLER_MATRIX`

| class | count | which | why |
|---|---:|---|---|
| **`ALREADY_GATED`** | **0** | — | LC015 shipped `BootstrapGatedIdentityReader` + `admin_identity_lookup` but wired **zero** runtime call sites. No production/runtime read currently routes through `DualIdReadWindow`. |
| **`NEEDS_BOOTSTRAP_GATED_READER`** | **≈ 30** | `app.py` aggregate/rollup readers (~26): review_log `GROUP BY question_id` / `DISTINCT question_id` / `question_id, COUNT` / `question_id, grade` / difficulty-inference `HAVING COUNT` (`4208-4211`, `8886`, `10806`, `10877`, `11083`, `11457`, `11578`, `12804`, `15620`, `27561`, `27570`, `28892`); SRS `question_id` set/rollup reads (`10674`, `10844`, `10855`, `11092`, `11592`, `12801`, `15230`, `15431`, `15521`, `15616`); mistake_log `question_id, wrong_count` rollups (`10678`, `10865`, `16634`). **Plus non-app.py (~4)**: `grimoire_api.py:148/163/670`, `community_leaderboard_rewards.py:364`. | Each builds a **per-question rollup** or a **set of legacy ids** consumed downstream. Wiring = the LC015 recipe: fetch rows keyed by int `question_id`, call `BootstrapGatedIdentityReader.group_keys_for(...)`, re-bucket the Python-side aggregation on `group_key`. DB stays keyed by int `question_id` — **no schema change**. |
| **`LEGACY_COMPATIBILITY_ONLY`** | **≈ 25** | review_log reads where `question_id` is a **returned payload column, not the aggregation axis** (`app.py:9640`, `15715`, `16472`–`16573`, `18159`, `18787`, `18832` — all `DATE(reviewed_at)`-grouped activity rollups); `submission_id`-keyed reads (`app.py:14379/14381`, `daily_challenge_d5b.py:84`); count-only (`app.py:6910`, `17609`, `18544`); the idempotency-guard read (`question_idempotency.py:135`); `map_battle_runtime.py` attempt-correlation (`726/744/835/1243` — the int id correlates a request to its issued attempt; the judge stays keyed by the SGF the client sends). | No wiring. Legacy alias behavior is **unchanged**: the int `question_id` remains the key. Documented so LC019 does not touch them. |
| **`AMBIGUOUS_BLOCKED`** | **0** | — | No read site is *blocked*. `AMBIGUOUS` is a **runtime outcome** the wired sites handle (fail closed → keep the `("unresolved", qid)` bucket, never merge, never fabricate), not a structural blocker for the preflight. |
| **`WRITE_PATH_OUT_OF_SCOPE`** | **≈ 20** | `app.py` `CREATE TABLE` / `INSERT` / `UPDATE` / `DELETE` on `review_log` / `srs_cards` / `mistake_log` (`4471`, `4578`, `9475`, `9477`, `9479`, `14505-14516` `insert_review_log_with_identity`, `14576` srs UPSERT, `14781/14784/14788` mistake_log UPSERT, `29156` skill-tree review INSERT); `map_battle_persistence.py` battle-progress INSERT (`401/431/441`); `question_idempotency.py:101` review INSERT; `review_service.py` (the review **command** boundary). Also the point reads `WHERE user_id=? AND question_id=?` that immediately precede an UPSERT (`app.py:13527`, `14547`, `14635`). | LC018/LC019 is **read-only**. Write-side identity adoption (a `source_record_uuid` column on `srs_cards` / `review_log` / `mistake_log`, backfill, dual-write) is a **separate future migration task**, gated on Genesis. |

`review_log`'s existing `submission_id` "identity" (`migrations/review_log_submission_idempotency_v1.py`) is a **per-submission write-idempotency key**, unrelated to `source_record_uuid` — it does **not** make any review_log site `ALREADY_GATED`.

## 3. Exact files / functions / lineage for LC019

| # | site | function / route | wire target |
|---|---|---|---|
| W1 | `grimoire_api.py:163` | review-history `DISTINCT question_id` for the weakness/training feed | `group_keys_for` re-bucket; **non-app.py** |
| W2 | `grimoire_api.py:670` | `/api/player/weakness-report` review_log aggregate | `group_keys_for` re-bucket; **non-app.py** |
| W3 | `grimoire_api.py:148` | `/api/grimoire/training/daily` SRS due-cards set | `keys_for` on the returned set; **non-app.py** |
| W4 | `community_leaderboard_rewards.py:364` | `fetch_leaderboard_participant_rows` `GROUP BY user_id, question_id` scoring | `group_keys_for` re-bucket; **non-app.py, reward-scoring — requires the leaderboard-reward owner's sign-off** |
| W5–W30 | `app.py` (~26 sites listed in §2) | discipline map (`4208`), weakness analysis (`28892`), difficulty inference (`27561/27570`), SRS due/recommend/progress readers, mistake-log rollups, the `DISTINCT question_id` set builders | `group_keys_for` / `keys_for` re-bucket; **app.py — needs the app.py-writer slot** |

Lineage: all wire through `identity_read_adapter.BootstrapGatedIdentityReader`
(`key_for` / `keys_for` / `group_keys_for` / `assert_attachable`) →
`puzzle_identity_read_window.DualIdReadWindow` →
`puzzle_identity_store.PuzzleIdentityStore` (read-only surface).

## 4. Implementation contract (deterministic behavior LC019 must implement)

### 4.1 `bootstrap_state().hot == False` (every real environment today)

`BootstrapGatedIdentityReader.key_for(qid)` returns
`IdentityKey(LEGACY, str(qid))` **without querying the resolver** (one cached
`bootstrap_state()` probe). `group_key == ("legacy", qid)`. The re-bucketed
aggregation is **byte-for-byte identical** to the current int-`question_id`
aggregation. `HOT_FALSE_LEGACY_BEHAVIOR` = every wired site is a **no-op** until
Genesis runs. LC019 lands a change that is inert in production.

### 4.2 `bootstrap_state().hot == True` (after the future Owner-gated Genesis)

| resolution | `group_key` | wired-site behavior |
|---|---|---|
| `EXACT` | `("uuid", u)` | rows for `qid` fold into the canonical uuid bucket; `attachable = True` |
| `RETIRED` | `("uuid", u)` | historical rows still resolve to the uuid; `attachable = False` — **no new SRS/review/mistake/adventure state attaches** (`assert_attachable` raises `IdentityNotAttachable`) |
| `AMBIGUOUS` | `("unresolved", qid)` | **fail closed** — the rows stay in their own per-legacy-id bucket, never merged into a uuid bucket, never auto-picked; `AMBIGUOUS_ALIAS_AUTO_MERGE = NO` |
| `MISSING` | `("legacy", qid)` | compatibility — the int id stays the key |
| `UNAVAILABLE` | `("unavailable", qid)` | explicit — the int id stays the key |

### 4.3 Legacy integer alias behavior

`question_id` is **never removed**, **never rewritten**, **never backfilled**.
Every table stays keyed by `question_id INTEGER`. The reader is a *view* over
the alias table; it adds a grouping key, it does not change storage.

### 4.4 Fail-closed / no-fabrication

The reader has **no** create/mint/INSERT path (§0). `MISSING` / `UNAVAILABLE` /
`AMBIGUOUS` are typed results; a wired site treats them as "keep the legacy
key" and continues — it never raises into a user request, never invents an
identity. `assert_attachable` is the only raise, and only a would-be *writer*
calls it on purpose.

## 5. Adjacent-lane audit

| lane | branch | Learning-Core read overlap | interaction |
|---|---|---|---|
| **E051** battlefield monster catalog fail-closed cutover | `origin/codex/e051-…` (not in master) | touches `app.py` + `battlefield_monster_catalog_*` / `monster_catalog_*`; **does NOT touch** `review_log` / `srs_cards` / `mistake_log` / `question_id` / `map_battle_*` | **no functional interaction.** Only overlap: both LC019 and E051 edit `app.py` → LC019's app.py portion must serialize through the app.py-writer slot after E051 lands (or take its ~4 non-app.py sites first). |
| **E052** battlefield catalog cutover merge readiness | `origin/codex/e052-…` | none | none |
| **A046** player appearance legacy-authority retirement | `origin/codex/a046-…` | none (appearance authority only) | none |
| **A047** | no branch found | — | not started / out of scope |

## 6. app.py-writer requirement

**`FUTURE_APP_PY_WRITER_REQUIRED = YES`** — ~26 of the ~30 `NEEDS_BOOTSTRAP_GATED_READER`
sites are inline SQL + aggregation in `app.py`. LC019's app.py portion must be
executed by the app.py-writer slot and serialized against any concurrent app.py
lane (E051). The ~4 non-app.py sites (`grimoire_api.py` ×3,
`community_leaderboard_rewards.py` ×1) can be wired **without** the app.py
writer and are LC019's safe first wave (the leaderboard one pending reward-owner
sign-off).

## 7. Genesis dependency

**`GENESIS_REQUIRED_BEFORE_LC019 = NO`.** The wiring is *safe* at `hot == False`
(inert — §4.1). Genesis is required only for the wiring to have *effect*, not to
be landed. LC019 lands a no-op-until-hot change; the Owner-gated
`GenesisBootstrap.apply()` remains a fully separate task and is the sole action
that flips `hot`.

## 8. Preflight outputs

```
TOTAL_CALLSITES             = ~59 read sites in scope (app.py ~50 + grimoire_api.py 3 + community_leaderboard_rewards.py 1 + daily_challenge_d5b.py 1 + question_idempotency.py 1 + map_battle_runtime.py ~4)
ALREADY_GATED_COUNT         = 0
NEEDS_WIRING_COUNT          = ~30   (app.py ~26 + grimoire_api.py 3 + community_leaderboard_rewards.py 1)
LEGACY_COMPATIBILITY_COUNT  = ~25
AMBIGUOUS_BLOCKED_COUNT     = 0
WRITE_PATH_OUT_OF_SCOPE     = ~20   (listed §2, not a read class)

FUTURE_APP_PY_WRITER_REQUIRED       = YES   (~26 of ~30 NEEDS_WIRING sites are in app.py)
LC019_SAFE_TO_ISSUE_AFTER_PREFLIGHT = YES   (all wiring is no-op-until-hot; safe at hot=false)
GENESIS_REQUIRED_BEFORE_LC019       = NO    (Genesis needed for effect, not for safety)

REAL_GENESIS_BOOTSTRAP = NO   IDENTITY_REGISTRY_POPULATION = NO   UUID_BACKFILL = NO
BOOTSTRAP_HOT = FALSE   APP_PY_CHANGED = NO   RUNTIME_CHANGED = NO
DB/SCHEMA/DATA_MUTATED = NO   PRODUCTION_QUERY = NO   PRODUCTION_MUTATION = NO
MASTER_MERGE = NO   DEPLOY = NO   SECRET_KEY_TOUCHED = NO
```

## 9. LC019 implementation scope (proposed)

**`LC019_BOOTSTRAP_GATED_IDENTITY_READER_APP_WIRING_IMPLEMENTATION_001`** —
wire `BootstrapGatedIdentityReader` into the `NEEDS_BOOTSTRAP_GATED_READER`
sites, no-op-until-`hot`, no schema change, no Genesis:

1. **Wave 1 (no app.py writer)**: `grimoire_api.py:148/163/670` — the
   `/api/grimoire/training/daily` and `/api/player/weakness-report` reads. One
   `BootstrapGatedIdentityReader` per request + a `group_keys_for` re-bucket.
   SQLite + real-PostgreSQL parity tests proving `hot == False` output is
   byte-identical to today and `hot == True` folds/fails-closed per §4.2.
2. **Wave 1b (needs reward-owner sign-off)**: `community_leaderboard_rewards.py:364`
   leaderboard scoring re-bucket — only with the leaderboard-reward owner's
   explicit approval (it feeds XP/rank).
3. **Wave 2 (app.py-writer slot, serialized after E051)**: the ~26 `app.py`
   aggregate readers (discipline map, weakness analysis, difficulty inference,
   SRS due/recommend/progress, mistake-log rollups, `DISTINCT question_id` set
   builders).
4. **Explicitly NOT in LC019**: any write path, any `source_record_uuid` column
   on `srs_cards` / `review_log` / `mistake_log`, any backfill, the
   `map_battle` attempt-correlation path, `review_service` — those are later
   migration/write tasks gated on Genesis.

`RESULT = PASS_LC_BOOTSTRAP_GATED_IDENTITY_READER_APP_WIRING_PREFLIGHT`.
`NEXT_TASK = LC019_BOOTSTRAP_GATED_IDENTITY_READER_APP_WIRING_IMPLEMENTATION_001`.
