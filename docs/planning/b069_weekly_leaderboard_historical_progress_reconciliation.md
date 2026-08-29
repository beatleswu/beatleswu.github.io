# B069 weekly leaderboard historical progress reconciliation

Snapshot: 2026-08-29 16:01:02 UTC (2026-08-30 00:01:02 Asia/Taipei)

This is a read-only Production reconciliation. No rows were inserted,
updated, deleted, backfilled, migrated, or deleted, and no deployment or
rollback was attempted.

## Executive result

The source census is complete for all source prefixes and literals found in
the retained code, tests, SQL consumers, and read-only Production
`review_log` data. There are nine source/data families and five explicit
prefixes. No unknown source literal remains unclassified. The separate
`<unattributed>` null/null historical bucket is disclosed as a historical
orphan and is not silently converted into trusted activity.

The B050 security contract remains intact: only `mbv1:*`,
`daily_d5b:v1:*`, and `rt:*` are counted by the current community weekly
leaderboard. Practice, Guild Quest, and raw legacy Boss Trial rows remain
excluded because their stored grade is not independently server-judged.

`READY_FOR_OWNER_RESTORATION_DECISION=YES` does not authorize a migration.
The recommended restoration is the owner-gated, bounded `POLICY_3_PLAYER_PRESERVATION`
described below.

## Window and population

| Field | Value |
|---|---:|
| Window start | 2026-08-24 00:00 Asia/Taipei |
| Window end (exclusive) | 2026-08-31 00:00 Asia/Taipei |
| SQL window | 2026-08-23 16:00:00 UTC to 2026-08-30 16:00:00 UTC |
| Server timezone | Asia/Taipei |
| Database timezone | UTC |
| DB weekly activity users | 29 |
| DB weekly activity rows | 15,089 |
| All-source qualifying rows (`grade >= 3`) | 11,072 |
| All-source distinct users | 29 |
| All-source distinct `(user_id, question_id)` score | 8,129 |
| B050 trusted distinct users | 7 |
| B050 trusted score | 533 |
| Excluded legacy affected users | 28 |
| Excluded legacy/lost score | 7,596 |

The earlier incident values of 25 all-source users and 5 trusted users were
an earlier open-week snapshot. The fresh read-only query has 29 and 7; this
does not change the authority boundary or the identified loss mechanism.

The sum of per-source bucket scores is not a union: one user/question can
carry more than one legacy source flag. The authoritative all-source and
excluded totals above are calculated from distinct user/question identities.

## Authority and scoring contract

The current reader is `community_leaderboard_rewards.py`'s
`fetch_leaderboard_participant_rows`, whose `qualifying_distinct` CTE applies:

```text
grade >= 3 AND
(source_context LIKE 'mbv1:%'
 OR source_context LIKE 'daily_d5b:v1:%'
 OR source LIKE 'rt:%')
```

`app.py`'s `/api/community/leaderboard` calls that reader with no database
limit, ranks the returned rows, and applies only a defensive `[:50]` bound.
The frontend renders all received rows; its top-three slices are presentation
podium widgets, not the weekly dataset. Therefore the first collapse from
the broad historical activity set to the trusted set is the B050 SQL source
predicate, not a `LIMIT 5` or frontend truncation.

For every counted source, the score is fixed at one point per distinct
`(user_id, question_id)` in the period when the authoritative stored grade is
at least 3. Grade values are not weighted. There is no leaderboard multiplier,
combo, streak, explicit daily cap, or explicit weekly cap in this reader;
period boundaries and distinct identity provide the reset/deduplication rule.

Server-owned evidence requires a server-derived result or settlement, bound
question/attempt identity, an immutable source marker, and an idempotent event
identity. A client grade can remain a transport/scheduling input on the
legacy public SRS path, but it cannot become correctness or leaderboard
authority.

## Complete source census

The machine-readable version of this table is the
`leaderboard_source_census` array in
[`b069_weekly_leaderboard_historical_progress_reconciliation_manifest.json`](b069_weekly_leaderboard_historical_progress_reconciliation_manifest.json).

| Player feature | Source | Producer | Server authoritative? | B050 trusted? | Should score? | Current users | Current score | Classification | Action required |
|---|---|---|---:|---:|---:|---:|---:|---|---|
| Map Battle | `mbv1:*` | `app.py::map_battle_v1_answers` -> `settle_answer` -> `MapBattleReviewHandoff` | YES | YES | YES | 0 | 0 | `SERVER_AUTHORITATIVE_COUNTED` | None; current E10 week has no rows |
| Daily Bounty/D5B | `daily_d5b:v1:*` | `app.py::dc_submit` -> `daily_challenge_authority` -> `daily_challenge_d5b` | YES | YES | YES | 0 | 0 | `SERVER_AUTHORITATIVE_COUNTED` | None; code-defined zero-row source |
| Rating Test | `rt:*` | `app.py::rt_answer` -> `rt_claim_sp` | YES | YES | YES | 7 | 533 | `SERVER_AUTHORITATIVE_COUNTED` | None |
| Lord Trial/Boss verdict | `lord_trial:v1:*` | `lord_trial_answer_service` -> `_srs_review_operation` -> `adventure_boss_finish` | YES | NO | NO in current board | 0 | 0 | `SERVER_AUTHORITATIVE_NOT_COUNTED` | Owner/product decision before board inclusion |
| Free Practice/ordinary review | `practice` | `index.html` -> `/api/srs/review` -> `ReviewService` -> `_srs_review_operation` | NO | NO | YES for future server-evidence contract | 24 | 1,204 | `LEGACY_CLIENT_GRADE_EXCLUDED` | Add server-owned evidence before future scoring; no B050 bypass |
| Guild Quest | `guild_quest` | Guild Quest UI -> `/api/srs/review`; `quest_accepted` is only quest acceptance | NO | NO | YES for future server-evidence contract | 15 | 6,073 | `LEGACY_CLIENT_GRADE_EXCLUDED` | Add per-answer server evidence before future scoring |
| Legacy Boss Trial marker | `boss_trial:*` | Boss UI -> `/api/srs/review`; current B051 flow rewrites validated results to `lord_trial:v1:*` | NO for raw rows | NO | NO for raw rows | 6 | 459 | `LEGACY_CLIENT_GRADE_EXCLUDED` | Never promote raw legacy rows; use B051 verdicts only under a new contract |
| Premium weekly training | `premium_weekly` | `index.html::_currentReviewMetadata` -> public SRS route | NO | NO | NO | 0 | 0 | `INTENTIONALLY_NON_SCORING` | None; retained as code-defined zero-row literal |
| Historical no-source rows | `<unattributed>` (`source` and `source_context` NULL) | Historical `review_log` boundary; exact original caller is not retained | NO | NO | NO pending provenance | 0 | 0 | `DEPRECATED` | Keep disclosed as unresolved historical orphan; never silently restore |

Explicit prefixes found: `mbv1:`, `daily_d5b:v1:`, `rt:`,
`lord_trial:v1:`, and `boss_trial:`. The other two active literals are
`practice`, `guild_quest`, and `premium_weekly`; the null/null bucket is a
data-provenance bucket, not a hidden literal. Production all-history checks
found no additional concrete source literal.

### Source-by-source authority evidence

* `mbv1:*`: the Map Battle route rejects client correctness, damage, HP,
  reward, and source fields. `map_battle_runtime.settle_answer` validates the
  issued attempt, nonce, revision, canonical moves, and server judge before
  the internal review handoff writes the marker. Persistence owns settled
  submission identity and conflict handling.
* `daily_d5b:v1:*`: `dc_submit` verifies the signed user/date/question attempt,
  canonicalizes moves, delegates to the shared server judge, stores the server
  result, and makes the legacy client boolean diagnostic only. Submission
  payload hash and `(user_id, challenge_date)` protect replay/double-submit.
* `rt:*`: `rt_answer` verifies the session token, question, and moves on the
  server. `rt_claim_sp` writes only server-verified correct answers with a
  session marker and returns `already_claimed` on a repeated claim.
* `lord_trial:v1:*`: `lord_trial_answer_service.judge_lord_trial_answer`
  delegates to the shared Map Battle judge, persists a signed verdict envelope,
  and `adventure_boss_finish` consumes complete sequential verdict evidence.
  The prefix has no current community leaderboard reader and Production has
  zero rows in this window and all history queried.
* `practice`: the public route accepts only the bounded SM-2 grades 0, 3, and
  5. The grade updates scheduling state, but B050 forces
  `progress_eligible=false` because no server answer evidence exists.
* `guild_quest`: the client labels the same legacy SRS route with
  `guild_quest`. `quest_accepted` records quest acceptance, not each claimed
  correct answer, so it is not independent leaderboard evidence.
* `boss_trial:*`: current signed Boss flow treats the marker as a validated
  transport context and persists a B051 `lord_trial:v1` verdict. Existing raw
  rows are legacy data without that stored verdict envelope and remain
  untrusted.
* `premium_weekly`: this explicit client source literal is transported with a
  premium training-set ID, but the public SRS path has no server judge and it
  is not a leaderboard source.
* `<unattributed>`: 21,534 historical rows (16,553 qualifying) have both
  source fields NULL. They are fully counted in the historical census and
  left unresolved for restoration; the retained data cannot prove their
  original feature or duplicate semantics.

Orphan accounting: `ORPHAN_WRITER_COUNT=2` for code-defined
`premium_weekly` and raw `boss_trial:*` paths with no trusted current board
reader; `ORPHAN_READER_COUNT=0`; `HISTORICAL_ORPHAN_SOURCE_COUNT=1` for the
null/null bucket; `UNKNOWN_SOURCE_COUNT=0` because no additional concrete
literal or prefix was found.

## Player activity reverse mapping

| Player activity | Generated source | Should score weekly | Currently scores weekly | Authority result |
|---|---|---:|---:|---|
| Free Practice | `practice` | YES under Owner future contract | NO | Client grade is scheduling-only; authority gap |
| Guild Quest question | `guild_quest` | YES under Owner future contract | NO | Client grade is not per-answer server evidence |
| Daily Bounty/D5B | `daily_d5b:v1:*` | YES | YES | Server judge and daily settlement |
| Rating Test/placement claim | `rt:*` | YES | YES | Server verifies moves before claim |
| Map Battle | `mbv1:*` | YES | YES | Server battle settlement and review handoff |
| Lord Trial | `lord_trial:v1:*` | NO in current B050 board | NO | Server-owned Boss evidence, separate consumer |
| Legacy Boss Trial review | `boss_trial:*` | NO for raw rows | NO | Legacy client marker; never trusted |
| Premium weekly training | `premium_weekly` | NO | NO | Training source, not board activity |
| Normal Adventure review | `practice` or a server-owned adapter source | YES only when server evidence exists | `practice` branch NO | No separate normal-battle source |
| Normal/Elite/Monster defeat | None for this board; domain events are separate | NO direct score | NO | Gameplay event, not leaderboard evidence |
| Boss clear / zone progression | None directly; Boss finish consumes `lord_trial:v1` | NO direct score | NO | Progression state, not board activity |
| Quest completion/acceptance | `quest_accepted` is not a leaderboard source | NO direct score | NO | Acceptance does not prove each answer |
| Spirit milestone/selection | None | NO | NO | Reward/progression event, not board activity |
| Equipment purchase/equip | None | NO | NO | Economy/loadout state, not board activity |
| Replay | Reuses the underlying submission identity | No duplicate point | No duplicate point | Distinct user/question and route idempotency |
| Achievements/other events/challenges | No additional current source found; Daily Bounty maps to D5B | Only where an explicit server source exists | No additional source | No unmapped release-capable source |

Reverse mapping is exhaustive for the discovered families:
`UNMAPPED_PLAYER_FEATURE_COUNT=0`, `UNMAPPED_SOURCE_COUNT=0`.

## Current and historical source totals

Counts below are qualifying `grade >= 3` rows; score totals are distinct
`(user_id, question_id)` within each source bucket. The overall union is
reported separately because source flags overlap.

| Source | Current qualifying rows | Current users | Current score | Historical qualifying rows | Historical users | Historical score |
|---|---:|---:|---:|---:|---:|---:|
| `mbv1:*` | 0 | 0 | 0 | 264 (541 raw rows) | 1 | 197 |
| `daily_d5b:v1:*` | 0 | 0 | 0 | 0 | 0 | 0 |
| `rt:*` | 2,269 | 7 | 533 | 6,086 | 39 | 2,181 |
| `lord_trial:v1:*` | 0 | 0 | 0 | 0 | 0 | 0 |
| `practice` | 2,254 | 24 | 1,204 | 64,656 (94,653 raw rows) | 149 | 39,045 |
| `guild_quest` | 6,083 | 15 | 6,073 | 56,367 (85,323 raw rows) | 61 | 56,155 |
| `boss_trial:*` | 466 | 6 | 459 | 1,706 (2,062 raw rows) | 11 | 1,611 |
| `premium_weekly` | 0 | 0 | 0 | 0 | 0 | 0 |
| `<unattributed>` | 0 | 0 | 0 | 16,553 (21,534 raw rows) | 35 | 13,095 |
| **All-source union** | **11,072** | **29** | **8,129** | **104,979** | **167** | **—** |

Current trusted union is 533 points across 7 users. Current excluded legacy
union is 7,596 points across 28 users. The current `community_leaderboard`
API therefore has no `LIMIT 5` root cause; its response is the trusted result
of the B050 predicate.

## Historical affected users

The following 28 users are the complete current-week set whose pre-B050 score
exceeds their B050 trusted score. `C` is a legacy-only-but-plausible distinct
score key; `D` is a duplicate/conflicted key associated with a repeated
non-empty submission payload hash. `Unresolved` is never silently treated as
restored.

| User ID | Display name | Pre-B050 | Trusted | Lost | Practice keys | Guild keys | Boss keys | C | D | Unresolved |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 991283 | 林承叡Jerry | 2,829 | 12 | 2,817 | 327 | 2,413 | 162 | 3,293 | 0 | 2,817 |
| 991260 | 圍棋之神 | 1,285 | 0 | 1,285 | 104 | 1,169 | 17 | 1,288 | 5 | 1,285 |
| 7 | 元元 | 640 | 0 | 640 | 34 | 412 | 199 | 644 | 6 | 640 |
| 991081 | Jared | 668 | 42 | 626 | 64 | 562 | 0 | 677 | 0 | 626 |
| 991119 | Test | 625 | 8 | 617 | 21 | 596 | 0 | 619 | 0 | 617 |
| 991282 | Ray Hsieh | 571 | 0 | 571 | 436 | 128 | 14 | 833 | 230 | 571 |
| 8 | 晴晴 | 303 | 0 | 303 | 0 | 284 | 19 | 303 | 0 | 303 |
| 991080 | Alia | 186 | 0 | 186 | 4 | 182 | 0 | 186 | 0 | 186 |
| 991136 | Slingshotbawi | 83 | 0 | 83 | 36 | 0 | 48 | 138 | 0 | 83 |
| 991062 | 庫巴魔王 | 79 | 0 | 79 | 0 | 79 | 0 | 79 | 0 | 79 |
| 991234 | Chioy | 73 | 0 | 73 | 20 | 53 | 0 | 133 | 0 | 73 |
| 991146 | 林盛 | 227 | 165 | 62 | 0 | 62 | 0 | 76 | 0 | 62 |
| 991012 | KeysPie | 53 | 0 | 53 | 0 | 53 | 0 | 53 | 0 | 53 |
| 991147 | 林茹 | 119 | 92 | 27 | 0 | 27 | 0 | 44 | 5 | 27 |
| 991287 | Test11 | 20 | 0 | 20 | 20 | 0 | 0 | 20 | 0 | 20 |
| 991073 | 藍文 | 19 | 0 | 19 | 19 | 0 | 0 | 19 | 1 | 19 |
| 991084 | 誰比我強 | 19 | 0 | 19 | 19 | 0 | 0 | 0 | 19 | 19 |
| 991285 | joachim | 19 | 0 | 19 | 19 | 0 | 0 | 19 | 0 | 19 |
| 991269 | 露露 | 17 | 0 | 17 | 17 | 0 | 0 | 17 | 0 | 17 |
| 991290 | Alva | 16 | 0 | 16 | 5 | 11 | 0 | 13 | 4 | 16 |
| 991087 | 三色糰子 | 15 | 0 | 15 | 15 | 0 | 0 | 30 | 0 | 15 |
| 991145 | 林豐 | 222 | 209 | 13 | 1 | 12 | 0 | 13 | 0 | 13 |
| 991264 | 新手小宇 | 11 | 0 | 11 | 11 | 0 | 0 | 11 | 0 | 11 |
| 991284 | 燁燁 | 9 | 0 | 9 | 9 | 0 | 0 | 9 | 0 | 9 |
| 991013 | 吳老 | 7 | 0 | 7 | 7 | 0 | 0 | 7 | 0 | 7 |
| 991288 | keorys | 7 | 0 | 7 | 7 | 0 | 0 | 7 | 0 | 7 |
| 991151 | 玫瑰言 | 1 | 0 | 1 | 1 | 0 | 0 | 1 | 0 | 1 |
| 991289 | TylerKy | 1 | 0 | 1 | 1 | 0 | 0 | 1 | 0 | 1 |

### Owner-critical users

* **991283 / 林承叡Jerry:** fresh pre-B050 score 2,829, trusted 12, lost
  2,817. The source bucket keys are practice 327, guild 2,413, and Boss
  162; they overlap and are not additive. All 3,293 observed legacy rows
  are C, with no independent server-correlated A/B evidence. High-confidence
  recoverable score is 0; maximum plausible clean-lost score is 2,817;
  unresolved is 2,817. The previously supplied score 1,652 is retained as
  historical context but not forced onto this fresh open-week snapshot.
* **991260 / 圍棋之神:** fresh pre-B050 score 1,285, trusted 0, lost 1,285.
  Source keys are practice 104, guild 1,169, and Boss 17. There are 1,288 C
  rows/keys and 5 D suspect rows touching four lost keys. High-confidence
  recoverable score is 0; maximum plausible clean-lost score is 1,281;
  unresolved is 1,285. The previously supplied score 1,204 is not used to
  override the fresh evidence.

## Evidence and duplicate audit

For the 8,803 current-week legacy qualifying rows:

* Practice: 2,254 rows, 1,204 source-bucket keys, 24 users; A=0, B=0,
  C=1,997, D=257, E=0. All 2,254 rows match an `srs_cards` row, but that is
  a server echo of the same legacy operation, not independent correctness
  evidence. 2,249 last-grade values match.
* Guild Quest: 6,083 rows, 6,073 source-bucket keys, 15 users; A=0, B=0,
  C=6,070, D=13, E=0. There are 28 `quest_accepted` rows in the window,
  but acceptance does not corroborate each claimed correct question. 6,083
  rows match `srs_cards`; 6,078 last-grade values match.
* Boss Trial: 466 rows, 459 source-bucket keys, 6 users; A=0, B=0,
  C=466, D=0, E=0. There are zero `lord_trial:v1:*` rows in the window;
  raw `boss_trial:*` rows are not B051 verdict evidence.

Duplicate audit: 270 excess rows across 154 repeated payload-hash groups;
160 distinct lost user/question keys are touched by a repeated hash. Exact
submission-ID duplicate excess is 0, same-user/question/grade/timestamp
duplicate excess is 0, impossible rows are 0, invalid grades/questions/users
are 0, and negative response times are 0. The live leaderboard already
deduplicates by user/question, so these rows do not double-credit the current
score; they remain unresolved for restoration.

## Restoration policies

| Policy | Restored users | Restored score | Unresolved users | Unresolved score | Security risk | Player-trust impact |
|---|---:|---:|---:|---:|---|---|
| `POLICY_1_STRICT` A only | 0 | 0 | 28 | 7,596 | Low | High negative |
| `POLICY_2_BALANCED` A+B | 0 | 0 | 28 | 7,596 | Low | High negative |
| `POLICY_3_PLAYER_PRESERVATION` clean C only | 27 | 7,436 | 7 | 160 | Medium, Owner-gated | High positive with explicit limits |
| `POLICY_4_BLIND_LEGACY` all rows | 28 | 7,596 | 0 | 0 | Critical; not recommended | Short-term positive but untrustworthy |

`POLICY_3_PLAYER_PRESERVATION` is recommended only after an explicit Owner
decision. It restores clean C distinct score keys, excludes D suspect keys,
never grants XP/Coins/combat/quest/streak/reward state, and never labels a
legacy client row as server-judged correctness. The seven unresolved records
are:

| Player | Source | Unresolved score | Reason |
|---|---|---:|---|
| 元元 / 7 | `guild_quest` | 6 | Repeated payload-hash suspicion; no independent judge |
| 藍文 / 991073 | `practice` | 1 | Repeated payload-hash suspicion |
| 誰比我強 / 991084 | `practice` | 19 | All keys have repeated payload-hash suspicion |
| 林茹 / 991147 | `guild_quest` | 4 | Repeated payload-hash suspicion |
| 圍棋之神 / 991260 | `practice` | 4 | Four keys have repeated payload-hash suspicion |
| Ray Hsieh / 991282 | `practice`, `boss_trial` | 123 | Repeated-hash suspicion; source flags overlap |
| Alva / 991290 | `practice`, `guild_quest` | 3 | Repeated payload-hash suspicion |

## Recommended future migration model

No migration is authorized by B069. If the Owner approves the bounded policy,
the next task should use the existing `domain_event_outbox_v1` immutable
ledger and `leaderboard_snapshots` projection rather than changing B050's
reader in place:

```text
legacy row
  -> reconciliation classification
  -> immutable reviewed manifest
  -> generated canonical historical leaderboard event
  -> idempotency key
  -> leaderboard snapshot/projection
```

Recommended idempotency key:
`b069:weekly:2026-W35:user:{user_id}:question:{question_id}`.

The audit trail must record this manifest hash, report hash, migration commit,
Owner gate, source row IDs, before/after counts, and transaction outcome. A
future Practice/Guild implementation must create server-owned evidence before
those sources enter the trusted whitelist. `CLIENT_SELF_REPORTED_LEADERBOARD_SCORE=NO`.

## Test evidence

The focused B050 authority and leaderboard suites passed: 26 tests passed.
The separate PostgreSQL-shaped admin regression fixture has one pre-existing
failure because its fixture omits the current `review_log.source_context`
column required by the production-shaped query at
`community_leaderboard_rewards.py:419`; this audit did not modify that fixture
or runtime code. Therefore `TASK_INTRODUCED_FAILURES=0` and
`PRE_EXISTING_FAILURES=1`.

## Safety and next action

`B050_FILTER_CHANGED=NO`, `B050_AUTHORITY_BYPASSED=NO`,
`XP_AUTHORITY_CHANGED=NO`, `RANK_AUTHORITY_CHANGED=NO`,
`COMMUNITY_LEADERBOARD_REWARDS_CHANGED=NO`, `LC019_SCOPE_TOUCHED=NO`.

Production access was read-only (`SELECT`/read-only logs/metadata only).
`BACKFILL_EXECUTED=NO`, `PRODUCTION_MUTATION=NO`,
`PRODUCTION_DB_MIGRATION=NO`, `DEPLOY=NO`, and `ROLLBACK=NO`.

Next task: `B070_RPG_V1_WEEKLY_LEADERBOARD_HISTORICAL_PROGRESS_RESTORATION_OWNER_DECISION_PACKET_001`.

Decision status: `READY_FOR_OWNER_RESTORATION_DECISION=YES`.
