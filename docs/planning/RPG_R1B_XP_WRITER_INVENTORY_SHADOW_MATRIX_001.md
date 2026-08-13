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

## R1C shadow coverage expansion

This section is the current R1C implementation evidence for
`RPG_R1C_XP_SHADOW_EXPANSION_001`. It extends observation only; the legacy
writers remain authoritative.

```text
TOTAL_RUNTIME_XP_WRITERS=8
CLASSIFIED_RUNTIME_XP_WRITERS=8
UNCLASSIFIED_RUNTIME_XP_WRITERS=0
R1B_EXISTING_SHADOW_WRITERS=QUEST_BOARD_STAGE,DAILY_CHALLENGE
R1C_IMPLEMENTED_SHADOW_WRITERS=REVIEW_SUBMISSION,DAILY_QUEST,DAILY_QUEST_ALL_COMPLETE,FRIEND_CHALLENGE_REWARD
ADMIN_XP_STATUS=DEFERRED_SPECIAL_SEMANTICS
LEGACY_RANK_MIGRATION_STATUS=DEFERRED_MIGRATION_SEMANTICS
WEAK_SYNTHETIC_EVENT_IDENTITY_CREATED=NO
```

### R1C provenance matrix

| Writer | Legacy authority / event identity | Premium handling | R1C shadow status | Cutover status |
|---|---|---|---|---|
| `REVIEW_SUBMISSION` | Public credited progress is the server-owned `srs_cards.progress_credited` identity for `(user_id, question_id)`. Internal Map Battle progression uses the settled server `submission_id` and `source_context`. Shadow is created only when `should_grant_review_progress()` authorizes the first credited progression. | No explicit Premium 18% stage in this writer. Appearance, companion, and potion values remain support-stage inputs; Premium is `PREMIUM_INELIGIBLE`. | `SHADOW_NOW` | `NO_CUTOVER` |
| `DAILY_QUEST` | `daily_quests(user_id, quest_key, quest_date)` plus the committed `xp_awarded` state. Event identity is date/key-specific and is emitted only when the quest transitions to completed with XP. | Per-definition quest XP; no Premium factor. | `SHADOW_NOW` | `NO_CUTOVER` |
| `DAILY_QUEST_ALL_COMPLETE` | Separate `quest_key=all_complete` completion state on the same daily date. Its event identity and idempotency key are distinct from every ordinary daily quest key. | Definition bonus XP; no Premium factor. | `SHADOW_NOW` | `NO_CUTOVER` |
| `FRIEND_CHALLENGE_REWARD` | The answer primary key `(challenge_id, user_id, question_id)` prevents replay. Completion reward identity is per `(challenge_id, reward recipient user_id)`, so each participant has an independent event. | Per-answer XP plus the existing win/draw bonus; no Premium factor. | `SHADOW_NOW` | `NO_CUTOVER` |
| `ADMIN_XP` | Admin-authorized signed adjustment / SET semantics. | Premium and gameplay modifiers are ineligible. | `DEFERRED_SPECIAL_SEMANTICS` | `NO_CUTOVER` |
| `LEGACY_RANK_MIGRATION` | Startup compatibility migration, not an earned reward event. | Not applicable. | `DEFERRED_MIGRATION_SEMANTICS` | `NO_CUTOVER` |

The R1C event identities are server-generated and stable across retries:

```text
REVIEW_SUBMISSION_PUBLIC_EVENT=
srs_cards.progress_credited:user:{user_id}:question:{question_id}
REVIEW_SUBMISSION_MAP_BATTLE_EVENT=
review_log:map_battle:submission:{submission_id}:user:{user_id}
DAILY_QUEST_EVENT=
daily_quests:user:{user_id}:date:{quest_date}:key:{quest_key}:completion
DAILY_QUEST_ALL_COMPLETE_EVENT=
daily_quests:user:{user_id}:date:{quest_date}:key:all_complete:completion
FRIEND_CHALLENGE_EVENT=
friend_challenge_reward:challenge:{challenge_id}:user:{reward_recipient_id}
```

`DAILY_QUEST_AND_ALL_COMPLETE_COLLISION=NO`: the ordinary quest key and the
`all_complete` key produce different event identities and different shadow
idempotency keys. A friend challenge retry reuses the same challenge/recipient
identity; the existing answer marker rejects the repeated answer before the
legacy reward path can run again.

### R1C calculation contract

The side-effect-free shadow path preserves the established fixed-point order:

```text
BASE
→ additive first_correct / mistake_correction
→ combo
→ support appearance / companion / potion
→ Premium
→ one final ROUND_HALF_UP
```

```text
FACTOR_SCALE=1000000
PREMIUM_FACTOR_PPM=1180000
PREMIUM_DOUBLE_STACK=NO
ROUNDING_MODE=ROUND_HALF_UP
FINAL_ROUNDING_ONLY=YES
SHADOW_CALCULATION_SIDE_EFFECT_FREE=YES
SHADOW_PLAYER_MUTATION=NO
SHADOW_LEDGER_INSERT=NO
SHADOW_IDEMPOTENCY_CONSUMPTION=NO
SHADOW_RESPONSE_CHANGE=NO
SHADOW_FAILURE_BLOCKS_LEGACY_REWARD=NO
```

Legacy review behavior can round between its existing modifier stages. R1C
records any resulting difference under the existing mismatch categories; it
does not silently rebalance the legacy reward. Legacy Premium state is
classified per writer and no caller adds a second 18% factor.

The R1C implementation extends the evidence payload with canonical integer
`support_factors_ppm` when multiple support factors are present. Decimal legacy
effect values are converted at the boundary with no floating-point authority;
the calculation itself remains integer/fixed-point only.

### Future writer-cutover evidence contract

This is a planning gate, not an R1C authorization to cut over any writer.
Before a writer can be considered for authoritative settlement, its observed
evidence must satisfy:

```text
EVENT_IDENTITY_MISMATCH=0
PREMIUM_MISMATCH=0
ROUNDING_MISMATCH=0
BASE_XP_MISMATCH=0
MODIFIER_MISMATCH=0
DUPLICATE_REWARD_OR_SETTLEMENT=0
PLAYER_IMPACT_DURING_SHADOW=0
SHADOW_FAILURE_AFFECTS_LEGACY_REWARD=0
LEGACY_SEMANTIC_DIFFERENCES=INDIVIDUALLY_CLASSIFIED_AND_OWNER_APPROVED
```

`ERROR_FAIL_CLOSED` is an observation failure only. It cannot deny or alter a
legacy reward. No arbitrary Production event-count threshold is locked here.
The following are `PROPOSED_FOR_OWNER_REVIEW` minimum observation samples,
chosen to cover both frequency and semantic diversity:

```text
REVIEW_SUBMISSION=
500 credited events, 50 users, with first-correct/mistake/combo/support
dimensions represented where the product produces them
DAILY_QUEST=
100 completion events, 30 users, with each ordinary quest key represented
DAILY_QUEST_ALL_COMPLETE=
50 completion events, 20 users, including the transition from all three
ordinary quests to the bonus completion
FRIEND_CHALLENGE_REWARD=
100 participant completion events, 20 challenges, with win/draw/loss and
retry paths represented where available
```

These sample sizes remain Owner-review proposals. They do not enable shadow,
writer cutover, Production configuration, migration, Opening Balance, or the
Level 51–100 curve.

### R1C safety status

```text
CURRENT_WRITER_CUTOVER_COUNT=0
R1C_WRITER_CUTOVER_EXECUTED=NO
XP_SHADOW_DEFAULT_ENABLED=NO
XP_WRITER_CUTOVER_DEFAULT_ENABLED=NO
LV51_100_DEFAULT_ENABLED=NO
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
TRACK_B_CHANGED_BY_R1C=NO
PRODUCTION_DB_MUTATION=NO
PRODUCTION_APP_DEPLOY=NO
PRODUCTION_STATIC_DEPLOY=NO
PRODUCTION_XP_SHADOW_ENABLED=NO
PRODUCTION_XP_WRITER_CUTOVER=NO
```
