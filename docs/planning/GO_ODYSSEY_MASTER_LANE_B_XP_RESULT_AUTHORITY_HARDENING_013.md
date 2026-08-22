# Go Odyssey Lane B B_013 — XP Result Authority Hardening

Status: blocked with exact server-truth dependency

Base: `8c2598f56595044b825040dbc82af9506d735907`

This packet audits the three XP-awarding routes named by B_012. It does not
change potion consumption, XP settlement cutover, question capacity, payment,
the D outbox, or the D5B lineage/submission identity work.

## Decision

All three routes remain `BLOCKED_CANONICAL_RESULT_SOURCE_MISSING` at this
checkout. The current browser contracts submit a legacy result boolean/grade,
not an answer or move sequence from which the server can independently derive
correctness. `_rt_server_verify` is a usable authority for routes that already
provide `moves` plus session/transform context, but it is not safely applicable
to these three payloads.

No production runtime code was changed in B_013. Adding a server-only
requirement for `moves` would fail the existing Daily/Friend clients, while
accepting the legacy boolean would leave the trust boundary unsafe. The safe
next implementation requires a reviewed client/server answer contract and,
for Public Review replay identity, D5B integration.

## Endpoint authority matrix

| Path | Current request | Server-owned state | Current result/XP authority | Replay/transaction | B_013 classification |
| --- | --- | --- | --- | --- | --- |
| Public Review | `question_id`, `grade` (0/3/5), timing/context | question metadata, SRS row, review log, user stats | difficulty/base and modifiers are server-derived, but client `grade` decides correctness and whether XP is written | `_srs_review_operation` owns the review transaction; `srs_cards.progress_credited` is partial first-credit protection | `BLOCKED_CANONICAL_RESULT_SOURCE_MISSING` |
| Daily Challenge | `correct` boolean; optional `moves` is not sent by the browser | server business date, daily challenge row, unique `(user_id, challenge_date)` log marker, fixed reward | client `correct` decides the stored result, XP, badges and appearance eligibility | same-user row serialization plus unique daily marker; transaction covers log, XP and related rewards | `BLOCKED_CANONICAL_RESULT_SOURCE_MISSING` |
| Friend Challenge | `question_id`, `correct` boolean; optional `moves` is not sent by the browser | authenticated participant, challenge/question membership, answer PK, completion counts | client `correct` is persisted; win/loss and XP are computed from those client-asserted answer rows | same-user serialization plus PK `(challenge_id,user_id,question_id)`; answer/reward transaction is local | `BLOCKED_CANONICAL_RESULT_SOURCE_MISSING` |

Authentication is the existing `login_required` session and `session['user_id']`
for all three routes. No client reward amount, base XP, or multiplier is
accepted as an independent numeric authority, but the asserted result still
controls reward eligibility.

## Client-asserted field matrix

| Path | Field | Current behavior | Safe target |
| --- | --- | --- | --- |
| Public Review | `grade` | trusted after allowlist `0,3,5`; `grade >= 3` drives correctness/XP | ignore for authority; derive grade/result from canonical submitted answer |
| Public Review | `question_id` | used to load question metadata and SRS row | validate against a server-issued question/session identity |
| Daily Challenge | `correct` | strict JSON bool after B_012, then directly drives log/XP/reward | ignore for authority; verify submitted answer against the canonical daily question |
| Friend Challenge | `correct` | strict JSON bool after B_012, then stored in answer row | ignore for authority; verify submitted answer and derive completion/result |
| All | `xp`, `reward_xp`, `score`, `won`, `completed` | not accepted as authoritative numeric/result fields | reject or ignore; derive all reward fields server-side |

`daily_challenge.html` currently submits only `{correct}`. The existing Friend
caller submits only `{question_id, correct}`. Public Review's `ReviewCommand`
contains `grade` and no answer/move field. Therefore a server-only adapter
cannot reconstruct the actual answer without inventing evidence.

## Canonical verifier boundary

`_rt_server_verify(pool_q, sid, moves)` replays the canonical SGF answer tree,
accepted moves, and the stored KataGo fallback. It requires actual `moves` and
a stable transform/session identity. The Daily and Friend hooks call
`shadow_judging.observe_answer_route` after the legacy write; Shadow is
observational and cannot become XP authority. Public Review has no call to the
canonical verifier and no answer payload.

Consequently:

```text
SERVER_RESULT_TRUTH_AUTHORITY_CLOSED=NO
CLIENT_XP_AUTHORITY_FULLY_CLOSED=NO
XP_TRUST_BOUNDARY_READY=NO
```

The safe follow-up is to add a reviewed answer/action transport to each
caller, bind it to a server-issued question/session identity, call a canonical
server verifier before any reward mutation, and fail closed when the verifier
cannot determine a result. That follow-up is outside this no-UI-change B_013
checkout.

## Replay and concurrency

B_012 protections remain valid but do not close result truth:

- Public Review has server-side first-credit state, but no durable D5B
  submission identity at this base; concurrent/replayed review semantics are
  therefore not sufficient for this task's exact replay claim.
- Daily Challenge uses the server date, a same-user row lock, and the unique
  `(user_id, challenge_date)` marker. Two concurrent identical submissions can
  award at most once, but the first result is still client asserted.
- Friend Challenge uses participant/challenge/question validation, a same-user
  row lock, and the answer primary key. Duplicate answers are guarded, but the
  stored answer truth is still client asserted.

No response-replay ledger or parallel idempotency system was added.

## D5B overlap

`D5B_FILE_OVERLAP=app.py` for the Public Review path (`srs_review`,
`_srs_review_operation`, `review_log`). The D5B semantic overlap is question
submission identity, replay-safe review evidence, and the authoritative answer
context needed before Public Review can be made server-truthful. No D5B
candidate was merged or silently consumed here. Daily/Friend have no direct
D5B file overlap at this checkout, but their future answer identity and
completion evidence must not be implemented as a second lineage ledger in
Lane B.

`PUBLIC_REVIEW_D5B_DEPENDENCY=YES`

## Exclusions preserved

```text
XP_CONSUME_IDEMPOTENCY_CHANGED=NO
XP_POTION_BALANCE_CHANGE=NO
XP_POTION_TIMER_CHANGE=NO
XP_POTION_STACKING_CHANGE=NO
XP_SETTLEMENT_CUTOVER=NO
QUESTION_CAPACITY_RUNTIME_CHANGED=NO
D_OUTBOX_IMPLEMENTATION=NO
D_LINEAGE_IMPLEMENTATION=NO
SHOP_CHANGE=NO
PREMIUM_CHANGE=NO
PAYMENT_CHANGE=NO
UI_CHANGED=NO
ASSET_FILES_CHANGED=0
DB_MIGRATION_EXECUTED=NO
PRODUCTION_MUTATION=NO
```
