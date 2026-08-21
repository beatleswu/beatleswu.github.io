# Go Odyssey Lane B — XP Consume Idempotency and Trust Boundary Closure

Status: implementation candidate / Owner review required

Base: `9c5380fde9d4cdff4168040d32997c960374c726`

This note records the bounded B_012 runtime hardening and the blockers that
must not be hidden behind a green active-effect check.

## Scope and safety

```text
XP_PRODUCT_COUNT=3
XP_CONSUMABLES=small_xp_potion,xp_potion,grand_xp_potion
XP_BALANCE_CHANGED=NO
XP_POTION_DURATION_CHANGED=NO
XP_POTION_MULTIPLIER_CHANGED=NO
XP_SETTLEMENT_CUTOVER=NO
XP_AMULET=HOLD_FOR_AUTHORITY
GO_STONE_BLACK=INVENTORY_ONLY_BOSS_TROPHY
QUESTION_CAPACITY_RUNTIME_CHANGED=NO
SHOP_PRICE_CHANGED=NO
PAYMENT_FILES_CHANGED=0
UI_CHANGED=NO
ASSET_FILES_CHANGED=0
DB_MIGRATION_EXECUTED=NO
```

## Consume idempotency audit

The existing potion transaction is atomic for the inventory decrement and
`active_effects` insert. B_011 also serializes the shared `xp_potion` active
effect on the authenticated user's row. That proves concurrent active-effect
exclusion, but it does not identify a retried logical request after the first
response is lost.

The current persistence surfaces are:

* `shop_inventory(user_id,item_key,qty)` — quantity only;
* `active_effects(user_id,effect_key,value,expires_at,effect_date,created_at)` —
  effect state only;
* `currency_log` / `gacha_log` — acquisition records, not item-use records.

None stores a server-validated operation identity, request hash, item binding,
or the original response. `XPSettlement` has an idempotency key for future XP
settlement, but it is disabled/calculation-only here and is not an item-use
authority. No shared D outbox or lineage foundation is present on this base.

```text
XP_CONSUME_REQUEST_IDEMPOTENCY=NOT_PRESENT
IDEMPOTENCY_DURABLE_ACROSS_RETRY=NO
IDEMPOTENCY_SCHEMA_DEPENDENCY=YES
XP_CONSUME_IDEMPOTENCY=BLOCKED_ON_D_FOUNDATION
```

The correct future primitive is a canonical item-use persistence extension or
D-owned transactional outbox with a unique identity scoped to
`(authenticated_user, mutation_family, operation_id)`, a request hash, exact
item binding, committed effect identity, and a replayable response projection.
The inventory decrement and effect insert must remain in the same transaction.
The server must validate or generate the identity; a client-generated string
must never become authority. Reusing `active_effects` as an implicit ledger
would lose result identity and create a second, ad-hoc ledger, so it was not
implemented.

## XP trust-path matrix

```text
XP_AWARD_WRITER_COUNT=8
XP_CLIENT_TRUST_PATH_COUNT=3
XP_CLIENT_TRUST_PATHS_REMAINING_UNSAFE_COUNT=3
CLIENT_XP_AUTHORITY=PARTIAL_REMAINING_UNSAFE
```

| Path | Endpoint / writer | Client-controlled | Server-derived / validated | B_012 result |
|---|---|---|---|---|
| Public review | `POST /api/srs/review` → `_srs_review_operation` → `user_stats` | `question_id`, `grade`, context and timing fields | question catalog, difficulty/base XP, SRS marker, modifiers, final XP arithmetic | `CLIENT_ASSERTED_RESULT_UNSAFE` remains: the client grade still decides correctness and can earn the server-computed reward without a server-verifiable answer proof |
| Daily Challenge | `POST /api/daily-challenge/submit` → `daily_challenge_log` → `user_stats` | `correct` | server date, canonical daily question, fixed reward, unique `(user_id,challenge_date)` marker | `CLIENT_ASSERTED_RESULT_UNSAFE` remains: a strict boolean is now required, but `true` is still client asserted |
| Friend Challenge | `POST /api/challenges/friend/<cid>/answer` → `friend_challenge_answers` → `_award_challenge_reward` | `question_id`, `correct` | participant/challenge membership, question membership, answer primary key, completion counts, result and reward formula | `CLIENT_ASSERTED_RESULT_UNSAFE` remains: a strict boolean is now required, but the answer truth is still client asserted |

Safe local hardening in this candidate:

1. Daily Challenge and Friend Challenge require a JSON boolean for `correct`;
   truthy strings/objects cannot be normalized into a rewarded result.
2. Same-user daily submission and friend-answer mutations use the existing
   authenticated `users` row as a transaction serialization point. Public
   review retains the existing `srs_cards.progress_credited` replay marker;
   its unknown-question/default-XP fall-through and separate concurrent-review
   race remain part of the server-verifiable settlement hardening dependency.
   Existing server markers remain authoritative for normal replay prevention.

The remaining closure dependency for all three paths is a server-verifiable
answer/result contract. The existing Shadow judging hook is observational and
cannot be promoted to authority in B_012. The current Daily/Friend clients do
not submit canonical move evidence, and the public SRS route submits a grade,
not a server-judged answer. Therefore this candidate does not claim
`CLIENT_XP_AUTHORITY=NO` or `XP_TRUST_BOUNDARY_READY=YES`.

## Replay and identity model

These are the existing server-derived replay identities, not a universal XP
key:

```text
PUBLIC_REVIEW_FIRST_CREDIT=
  srs_cards.progress_credited:user:{user_id}:question:{question_id}
PUBLIC_REVIEW_MAP_BATTLE=
  review_log:map_battle:submission:{submission_id}:user:{user_id}
DAILY_CHALLENGE=
  daily_challenge_log:user:{user_id}:date:{challenge_date}
FRIEND_ANSWER=
  friend_challenge_answers:{challenge_id}:{user_id}:{question_id}
FRIEND_COMPLETION_REWARD=
  friend_challenge_reward:challenge:{challenge_id}:user:{reward_recipient_id}
```

These identities protect current XP replay semantics, but they are not a
generic request-response idempotency primitive for potion consumption.

## D handoff points

```text
D_OUTBOX_INTEGRATION_POINT_COUNT=2
1=ITEM_CONSUME_EFFECT — commit evidence for decrement + effect creation and replay response
2=XP_SETTLEMENT_EVIDENCE — base/modifier/final XP lineage after a future authority cutover
D_LINEAGE_INTEGRATION_DEFERRED=YES
XP_SUPPORT_TRACEABILITY=PARTIAL
```

No outbox, lineage ledger, XP cutover, payment, Premium package, shop, or
Production state was changed by this candidate.
