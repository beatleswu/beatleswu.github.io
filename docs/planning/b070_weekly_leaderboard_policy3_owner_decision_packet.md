# B070 Policy 3 historical leaderboard restoration decision packet

This packet is read-only and does not authorize or execute a Production backfill. It is bound to B069 manifest `11c9984562f5bf2ac2938183f6cf4891f2f6276008760ae65f79801323ac82c4` and report `c7ff573d21b3fb018d7aca490899e7862f1ca6ae61f06f0f7d00adff5bb61316`.

## Owner gate payload

```text
GO_PRODUCTION_LEADERBOARD_HISTORICAL_RESTORATION
BOUND_POLICY=POLICY_3_PLAYER_PRESERVATION
BOUND_LEDGER_SHA256=03b0001c5d41cb4cdbd49b6c4b7c506d0f8716f6d17d114b8b09eddfea5264e5
BOUND_RESTORED_SCORE_TOTAL=7436
BOUND_EXCLUDED_DUPLICATE_SCORE_TOTAL=160
DATA_MUTATION=YES
SCHEMA_MUTATION=NO
SELF_GRANTED=NO
```

## Exact scope and totals

Window: `2026-08-24 00:00 Asia/Taipei` through `2026-08-31 00:00 Asia/Taipei` exclusive. The canonical score unit is one distinct `(user_id, question_id)` with legacy `grade >= 3`, after excluding existing trusted keys and duplicate-suspect keys.

```text
POLICY_3_LEDGER_SCORE_TOTAL=7436
POLICY_3_EXCLUDED_SCORE_TOTAL=160
POLICY_3_RESTORED_USER_COUNT=27
POLICY_3_RESTORED_EVENT_COUNT=7436
INSERT_ROW_COUNT=7436
INSERT_SCORE_TOTAL=7436
EXPECTED_AFFECTED_USERS=28
DUPLICATE_SUSPECT_RAW_EXCESS_EVENTS=270
IMPOSSIBLE_EVENT_COUNT=0
```

The ledger contains 7,596 canonical affected score-unit entries and all 8,803 qualifying raw legacy rows. Each raw row has a stable `review_log:id`, decision, score-unit identity, and idempotency key. Cross-source rows are assigned to one deterministic canonical representative; source-bucket membership is reported separately and is intentionally non-additive.

## Source-by-source Policy 3 totals

| Source | Canonical restored events | Restored score | Excluded duplicate raw events | Excluded duplicate score units | Clean source-bucket keys |
|---|---:|---:|---:|---:|---:|
| Practice | 1009 | 1009 | 257 | 148 | 1049 |
| Guild Quest | 6031 | 6031 | 13 | 12 | 6031 |
| Boss Trial | 396 | 396 | 0 | 0 | 458 |

Canonical restored events sum to 7,436. Clean source-bucket keys are Practice 1,049, Guild Quest 6,031, and Boss Trial 458; the sum is 7,538 because the same question can carry multiple legacy source flags. Duplicate score-unit membership is Practice 148, Guild Quest 12, Boss Trial 1; canonical excluded score-unit allocation is Practice 148, Guild Quest 12, Boss Trial 0, summing to 160.

## Final effect for all 28 affected users

| User ID | Display name | Current trusted | Policy 3 restored | Projected score | Excluded score units | Excluded raw duplicate events |
|---:|---|---:|---:|---:|---:|---:|
| 7 | 元元 | 0 | 634 | 634 | 6 | 6 |
| 8 | 晴晴 | 0 | 303 | 303 | 0 | 0 |
| 991012 | KeysPie | 0 | 53 | 53 | 0 | 0 |
| 991013 | 吳老 | 0 | 7 | 7 | 0 | 0 |
| 991062 | 庫巴魔王 | 0 | 79 | 79 | 0 | 0 |
| 991073 | 藍文 | 0 | 18 | 18 | 1 | 1 |
| 991080 | Alia | 0 | 186 | 186 | 0 | 0 |
| 991081 | Jared | 42 | 626 | 668 | 0 | 0 |
| 991084 | 誰比我強 | 0 | 0 | 0 | 19 | 19 |
| 991087 | 三色糰子 | 0 | 15 | 15 | 0 | 0 |
| 991119 | Test | 8 | 617 | 625 | 0 | 0 |
| 991136 | Slingshotbawi | 0 | 83 | 83 | 0 | 0 |
| 991145 | 林豐 | 209 | 13 | 222 | 0 | 0 |
| 991146 | 林盛 | 165 | 62 | 227 | 0 | 0 |
| 991147 | 林茹 | 92 | 23 | 115 | 4 | 5 |
| 991151 | 玫瑰言 | 0 | 1 | 1 | 0 | 0 |
| 991234 | Chioy | 0 | 73 | 73 | 0 | 0 |
| 991260 | 圍棋之神 | 0 | 1281 | 1281 | 4 | 5 |
| 991264 | 新手小宇 | 0 | 11 | 11 | 0 | 0 |
| 991269 | 露露 | 0 | 17 | 17 | 0 | 0 |
| 991282 | Ray Hsieh | 0 | 448 | 448 | 123 | 230 |
| 991283 | 林承叡Jerry | 12 | 2817 | 2829 | 0 | 0 |
| 991284 | 燁燁 | 0 | 9 | 9 | 0 | 0 |
| 991285 | joachim | 0 | 19 | 19 | 0 | 0 |
| 991287 | Test11 | 0 | 20 | 20 | 0 | 0 |
| 991288 | keorys | 0 | 7 | 7 | 0 | 0 |
| 991289 | TylerKy | 0 | 1 | 1 | 0 | 0 |
| 991290 | Alva | 0 | 13 | 13 | 3 | 4 |

## Owner-critical reconciliation

"Unresolved" in B069 was an overloaded “lost score not restored” value. This packet partitions it into restored score, duplicate-excluded score, and other unresolved score.

* **林承叡Jerry (991283)**: fresh pre-B050 2829; trusted 12; restored 2817; projected 2829; duplicate excluded 0; other unresolved 0. B069 unresolved 2817 means all lost score not restored under Policy 3, not an additional bucket.
* **圍棋之神 (991260)**: fresh pre-B050 1285; trusted 0; restored 1281; projected 1281; duplicate excluded 4; other unresolved 0. B069 unresolved 1285 means all lost score not restored under Policy 3, not an additional bucket.

For `991260 / 圍棋之神`, the exact reconciliation is `1281 restored + 4 duplicate-excluded + 0 other-unresolved = 1285`. Therefore `PLAYER_991260_SCORE_SEMANTICS_RECONCILED=YES`.

## Projected leaderboard

Ranking uses the current server rule: score descending, final counted time ascending, user ID ascending. No historical rank is forced.

```text
PROJECTED_VISIBLE_USER_COUNT=28
PROJECTED_TOTAL_SCORE=7969
RANK_1=林承叡Jerry
RANK_1_SCORE=2829
RANK_2=圍棋之神
RANK_2_SCORE=1281
```

| Rank | User ID | Display name | Score |
|---:|---:|---|---:|
| 1 | 991283 | 林承叡Jerry | 2829 |
| 2 | 991260 | 圍棋之神 | 1281 |
| 3 | 991081 | Jared | 668 |
| 4 | 7 | 元元 | 634 |
| 5 | 991119 | Test | 625 |
| 6 | 991282 | Ray Hsieh | 448 |
| 7 | 8 | 晴晴 | 303 |
| 8 | 991146 | 林盛 | 227 |
| 9 | 991145 | 林豐 | 222 |
| 10 | 991080 | Alia | 186 |
| 11 | 991147 | 林茹 | 115 |
| 12 | 991136 | Slingshotbawi | 83 |
| 13 | 991062 | 庫巴魔王 | 79 |
| 14 | 991234 | Chioy | 73 |
| 15 | 991012 | KeysPie | 53 |
| 16 | 991287 | Test11 | 20 |
| 17 | 991285 | joachim | 19 |
| 18 | 991073 | 藍文 | 18 |
| 19 | 991269 | 露露 | 17 |
| 20 | 991087 | 三色糰子 | 15 |
| 21 | 991290 | Alva | 13 |
| 22 | 991264 | 新手小宇 | 11 |
| 23 | 991284 | 燁燁 | 9 |
| 24 | 991288 | keorys | 7 |
| 25 | 991013 | 吳老 | 7 |
| 26 | 991261 | 沐真 | 5 |
| 27 | 991151 | 玫瑰言 | 1 |
| 28 | 991289 | TylerKy | 1 |

## Canonical migration model

```text
legacy review_log row
  -> B069 Policy 3 score-unit classification
  -> immutable historical_leaderboard_reconciliation:v1 event
  -> idempotent canonical evidence insert
  -> dedicated reviewed historical-evidence leaderboard projection
```

`historical_leaderboard_reconciliation:v1:` is new provenance, not a native `mbv1`, `rt`, or `daily_d5b` source. B050 remains unchanged. The proposed idempotency key is `b069:weekly:2026-W35:user:{user_id}:question:{question_id}`.

Execution must use an Owner-gated transaction, reject hash/count/manifest mismatches, never rewrite `review_log`, and make a same-batch rerun produce zero additional score. Rollback, if separately authorized, removes only the generated migration batch/projection and never deletes legacy evidence.

Historical `<unattributed>` rows remain firewalled: 16,553 events, 35 users, 13,095 score, restored 0. `premium_weekly` restored score is 0.

## Required future authority work

Practice, Guild Quest, and canonical Lord/Boss Trial future scoring require server-owned evidence. Raw `boss_trial:*` rows must never be promoted by this packet. `lord_trial:v1:*` remains server-authoritative but outside the current B050 whitelist; `LORD_TRIAL_B050_POLICY_GAP=YES` and no B050 change is made.

## Safety and decision

```text
B050_FILTER_CHANGED=NO
LEADERBOARD_AUTHORITY_CHANGED=NO
XP_CHANGED=NO
RANK_AUTHORITY_CHANGED=NO
COINS_CHANGED=NO
QUEST_AUTHORITY_CHANGED=NO
COMBAT_CHANGED=NO
APP_PY_CHANGED=NO
PRODUCTION_QUERY=READ_ONLY_ONLY
PRODUCTION_MUTATION=NO
BACKFILL_EXECUTED=NO
DEPLOY=NO
ROLLBACK=NO
```

`READY_FOR_OWNER_GO_PRODUCTION_LEADERBOARD_HISTORICAL_RESTORATION_DECISION=YES`.
Next task: `OWNER_GO_PRODUCTION_LEADERBOARD_HISTORICAL_RESTORATION_DECISION`.
