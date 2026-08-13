# RPG R1B XP Writer Inventory / Shadow Matrix

Status: implementation evidence for `RPG_R1B_XP_SHADOW_SETTLEMENT_001`.

This artifact records the current repository search and the deliberately
bounded R1B shadow scope. It does not authorize writer cutover, migration,
Opening Balance execution, Level 51–100 activation, or Production activity.

## Inventory coverage

The current Python runtime search covered direct SQL mutations of
`user_stats.xp`, `user_stats.rank_xp`, and `user_stats.rank_level`, together
with their reward/source markers and helper calculations.

```text
DIRECT_XP_MUTATION_CALLSITES_FOUND=8
DIRECT_XP_MUTATION_CALLSITES_CLASSIFIED=8
UNCLASSIFIED_RUNTIME_XP_WRITERS=0
```

Read-only references, test fixtures, pet XP, Coins, HP, Go rank, and the R1A
`XPSettlement` foundation were not counted as current player XP writers.

## Current writer matrix

| Writer | Source / callsite | Current authority and provenance | Premium / modifiers | Shadow status | R1B action |
|---|---|---|---|---|---|
| `REVIEW_SUBMISSION` | `app.py` `/api/srs/review` | Existing review transaction; sticky `srs_cards.progress_credited` gates the first credited `(user_id, question_id)` progression. Map Battle also enters this surface with `source_context` / settled submission identity. | `XP_BY_DIFF` + first-correct + mistake-correction + combo + appearance + companion + XP potion; legacy integer conversions; no explicit 18% Premium factor in this writer. | Deferred: identity and legacy modifier normalization require R1C review. | `DEFER_WITH_REASON` |
| `DAILY_QUEST` | `app.py` `_update_daily_quests` per quest | `daily_quests(user_id, quest_key, quest_date)` and `completed/xp_awarded`; called from optional monster/quest progression. | Per-definition `q['xp']`; no Premium factor; direct `rank_xp` increment. | Deferred: source-marker transaction and optional progression boundary require later cutover mapping. | `DEFER_WITH_REASON` |
| `DAILY_QUEST_ALL_COMPLETE` | `app.py` `_update_daily_quests` `all_complete` branch | Same daily quest row, keyed by `daily_quest:all_complete` reward state. | Definition XP; no Premium factor; direct `rank_xp` increment. | Deferred with the daily quest writer family. | `DEFER_WITH_REASON` |
| `QUEST_BOARD_STAGE` | `app.py` `/api/rewards/sync` `rewards_sync` | `reward_claimed(user_id, stage_key)` primary key wins the claim before aggregate XP/Coins mutation. | `seg['xp']` is already the legacy stage amount; Premium can affect accessible segment shape, not an additional 18% factor. | Selected. Stable server marker, deterministic amount, and shadow runs after committed claim with no DB access. | `SHADOW_NOW` |
| `DAILY_CHALLENGE` | `app.py` `/api/daily-challenge/submit` `dc_submit` | `daily_challenge_log(user_id, challenge_date)` unique marker; only first submission can award. | Fixed `DAILY_CHALLENGE_XP_REWARD`; no Premium factor or additional modifier. | Selected. Stable server marker and deterministic fixed award; shadow runs after commit. | `SHADOW_NOW` |
| `FRIEND_CHALLENGE_REWARD` | `app.py` `_award_challenge_reward` via `friend_challenge_answer` | `friend_challenge_answers(challenge_id,user_id,question_id)` prevents repeated answers; completion/result reward is derived from both participants. | Per-answer XP plus win/draw result bonus; no Premium factor; per-answer and final-result identity still need separate settlement mapping. | Deferred. | `DEFER_WITH_REASON` |
| `ADMIN_XP` | `app.py` `/api/admin/users/<uid>/assets/xp` `admin_set_xp` | Admin-authorized direct SET/DELTA updates XP and rank fields; audit is separate from XP settlement. | No Premium or support modifiers; signed adjustment semantics are foundation-only. | Inventory only; no shadow/cutover. | `ADMIN_SPECIAL_CASE` |
| `LEGACY_RANK_MIGRATION` | `app.py` `_migrate_ranks`, invoked from startup schema initialization | Existing `user_stats.xp` plus legacy rank format can be normalized during initialization. This is migration behavior, not a player reward. | No Premium; derives rank fields and may rewrite legacy XP floor. | Must not be shadowed as a reward writer. | `LEGACY_DEAD_PATH` |

The R1A schema/foundation itself is not a current writer. Its mutation flag
remains disabled and no R1B path calls `XPSettlement.settle()`.

## Shadow contract

R1B adds a side-effect-free `compare_xp_shadow()` calculation and an
observational helper in `app.py`. It emits bounded structured application-log
evidence only when `XP_SHADOW_ENABLED=1`.

```text
XP_SHADOW_DEFAULT_ENABLED=NO
XP_WRITER_CUTOVER_DEFAULT_ENABLED=NO  (XP_SETTLEMENT_ENABLED)
LV51_100_DEFAULT_ENABLED=NO
NEW_DB_TABLE=NO
NEW_MIGRATION=NO
```

The selected writers continue to perform the legacy award and commit. Only
after commit does the shadow helper calculate and log the comparison. It has
no database connection and therefore cannot insert a ledger row, consume an
idempotency key, mutate `user_stats`, mutate rank fields, change a response,
or change a reward. Shadow failures are logged as `ERROR_FAIL_CLOSED` and are
ignored by the legacy reward path.

The canonical calculation remains:

```text
BASE
→ additive learning bonuses
→ combo factor
→ support factor
→ Premium factor once
→ one final ROUND_HALF_UP
```

Factors are integer PPM (`FACTOR_SCALE=1000000`; Premium `1180000`). The
selected legacy sources pass a non-Premium base amount because neither writer
has a separate 18% Premium XP factor.

Event provenance is retained in evidence:

```text
QUEST_BOARD_STAGE:
  source_marker=reward_claimed(user_id,stage_key)
  event_identity=server-derived user/stage identity
  idempotency_key=server-derived bounded ASCII-safe shadow key

DAILY_CHALLENGE:
  source_marker=daily_challenge_log(user_id,challenge_date)
  event_identity=server-derived user/date identity
  idempotency_key=server-derived bounded ASCII-safe shadow key
```

Defined mismatch categories are:

```text
MATCH
ROUNDING_MISMATCH
PREMIUM_MISMATCH
BASE_XP_MISMATCH
MODIFIER_MISMATCH
EVENT_IDENTITY_MISMATCH
UNSUPPORTED_WRITER
LEGACY_SEMANTIC_DIFFERENCE
ERROR_FAIL_CLOSED
```

No mismatch is silently normalized and no legacy reward behavior is changed
by this Sprint.

## Safety status

```text
CURRENT_WRITER_CUTOVER_COUNT=0
OPENING_BALANCE_EXECUTED=NO
OPENING_BALANCE_ROWS_CREATED=0
PLAYER_XP_ROWS_MUTATED_BY_TASK=0
PLAYER_MIGRATION=NO
ORPHAN_ROWS_CHANGED=0
LEVEL_CURVE_RUNTIME_CHANGED=NO
LV51_100_VISIBLE=NO
PLAYER_VISIBLE_XP_RESULT_CHANGED=NO
PLAYER_VISIBLE_LEVEL_CHANGED=NO
PLAYER_VISIBLE_REWARD_CHANGED=NO
PLAYER_VISIBLE_UI_CHANGED=NO
TRACK_A_CHANGED=NO
TRACK_B_CHANGED_BY_R1B=NO
PRODUCTION_DB_MUTATION=NO
PRODUCTION_APP_DEPLOY=NO
```
