# C019 Atomic Coin Purchase Transaction Core V1

Status: implementation candidate, not live. This change adds a server-side
transaction core and its additive operation schema. It does not connect a
route, enable a Shop surface, mutate Production Coins, run a Production
migration, deploy, or merge to master.

## Provenance and boundary

TASK=C019_ATOMIC_COIN_PURCHASE_TRANSACTION_CORE_V1_001
START_ORIGIN_MASTER=58d9b7047f285751a048fc551c955909c87984ac
WORKTREE=D:\go-website-c019-atomic-coin-purchase
BRANCH=codex/c019-atomic-coin-purchase-core-v1

C019 owns the Coin purchase transaction boundary only. It does not absorb
Player/Hero progression, World progression, Combat, Spirit, Monster, or Quest
authority. Shop remains an acquisition source; it is not an ownership
authority.

## Existing authorities reconciled

| Concern | Existing authority | C019 treatment |
| --- | --- | --- |
| Coin balance | user_stats.coins, read by _coin_balance | Reused directly |
| Coin grants | _grant_coins | Untouched |
| Coin spend | _spend_coins conditional update plus currency_log | Mirrored by spend_coins_in_transaction as a transaction-safe adapter over the same row/log; no second balance is created |
| Stackable inventory | shop_inventory(user_id,item_key,qty) | C019 adapter writes this table for explicit STACK offers |
| Functional equipment ownership | player_inventory(user_id,equip_id,equipped,...) | C019 adapter writes an unequipped row; it never equips or consumes it |
| Cosmetic ownership | player_wardrobe(user_id,item_id) | C019 adapter writes pure cosmetics here; it never writes appearance/effect state |
| Acquisition evidence | D5A domain_event_outbox, event_outbox.append_event | One ITEM_ACQUISITION event is appended in the same transaction |
| Item use | D5C item_use_operations and item-use services | Not imported and not used; acquire is not consume |
| Existing Shop route | app.py:shop_buy and app.py:shop_buy_appearance | Untouched; those paths remain pre-C019 and do not gain C019 idempotency yet |

The current Shop catalog mixes legacy bundles, Pet grants, daily rotation
prices, gacha metadata, and cosmetic mappings. It does not yet expose one
uniform offer_id -> resolved reward/destination/version authority. C019
therefore uses StaticShopOfferAuthority as a narrow normalized adapter and
records SHOP_OFFER_NORMALIZATION_REQUIRED=YES for later integration.

## Offer authority

shop_offer_authority.CoinShopOffer is a server-owned internal contract:

offer_id
item_id
quantity
currency_type=COINS
price
destination
acquisition_class
offer_type
offer_version
status
duplicate_policy
eligibility_metadata
presentation_metadata

The client may identify an offer, but cannot authoritatively select price,
quantity, destination, reward class, effect, or ownership policy. The
client_price compatibility/test argument in purchase_with_coins is deliberately
ignored. Cash offers, Coin packs, paid equipment, paid consumables, boosts,
gacha, and loot boxes are outside this module.

## Durable exactly-once operation

The additive migration migrations/coin_purchase_operations_v1.py creates
coin_purchase_operations with primary key (user_id, purchase_operation_id).
The row binds:

user_id
purchase_operation_id
offer_id
request_fingerprint
offer_version
currency_type
resolved_price
reward_id
reward_quantity
destination
acquisition_class
operation_status
result_payload
lineage_event_id
created_at / updated_at / committed_at

The only durable states are IN_PROGRESS and COMMITTED. The reservation, Coin
mutation, destination mutation, D5A event, and terminal result update are one
caller-owned transaction. A failed transaction rolls back the temporary
IN_PROGRESS row with every business mutation; a process cannot commit an
ambiguous operation row independently of the purchase. A pre-existing
IN_PROGRESS row is fail-closed rather than executed again.

The migration is additive, SQLite-testable, PostgreSQL-aware, protected by a
transaction advisory lock on PostgreSQL, and never auto-runs at request time.
It has not been run against Production.

## Transaction sequence

coin_purchase_authority.purchase_with_coins performs:

1. Validate the authenticated user and operation identity.
2. Recover a committed operation before resolving a possibly changed catalog.
   A different offer_id on the same operation identity is a conflict.
3. Resolve the active server offer and eligibility.
4. Reserve (user_id,purchase_operation_id) with ON CONFLICT DO NOTHING.
5. Debit user_stats.coins with the existing conditional non-negative update and
   append the existing currency_log evidence.
6. Route the reward to its explicit ownership destination.
7. Append one D5A ITEM_ACQUISITION event with a stable purchase idempotency key.
8. Persist the authoritative result and mark the operation COMMITTED.
9. Let the caller commit the surrounding transaction.

The service never calls commit, rollback, or begin. This matches the
repository's D5 caller-owned transaction convention and lets a future route
compose all mutations under one database transaction. The caller must roll
back when the service raises.

## Acquisition routing in this slice

| Destination | Supported C019 class | Ownership result | Capability projection |
| --- | --- | --- | --- |
| shop_inventory | CONSUMABLE, SPIRIT_CONSUMABLE, XP_CONSUMABLE, MATERIAL | quantity stack | can_use only for consumable classes |
| player_inventory | WEAPON, ARMOR, ACCESSORY, TROPHY | unequipped row | functional classes can equip; trophy cannot |
| player_wardrobe | COSMETIC only | unique ownership row | can_wear=true, no combat capability |
| entitlement, capacity, credit | not implemented in this scoped adapter | fail closed | no fabricated capability |

The adapter does not calculate combat effects, equip an item, use an item, or
create a cosmetic combat effect. xp_amulet remains HOLD_FOR_AUTHORITY.
go_stone_black remains inventory-only/trophy-only and is not a Coin Shop
sale. No automatic duplicate-to-Coins conversion exists. Stackable offers
must declare STACK; cosmetics must declare REJECT_IF_OWNED; equipment must
declare an explicit duplicate policy.

## Replay and conflict contract

same user + same operation + same purchase
  -> original committed result, replayed=true
  -> no second debit, acquisition, or D5A event

same user + same operation + different offer/semantic request
  -> PURCHASE_OPERATION_CONFLICT
  -> no mutation

unknown/disabled offer
  -> UNKNOWN_OFFER
  -> no mutation

insufficient Coins
  -> INSUFFICIENT_COINS
  -> no negative balance, ownership, operation, or lineage mutation

acquisition/lineage/debit failure
  -> explicit failure
  -> caller rollback restores all earlier mutations

replayed is delivery metadata only. The stored canonical result is the same
authoritative payload returned by the original commit.

## Concurrency evidence

SQLite disposable shared-memory tests cover:

- two concurrent attempts with the same operation identity: one committed
  debit/acquisition and one deterministic replay;
- two operation identities competing for a balance sufficient for only one:
  one succeeds, one gets INSUFFICIENT_COINS, and the balance never becomes
  negative.

The test caller retries the whole SQLite transaction after a transient writer
lock, which is the correct boundary for this caller-owned service. No
PostgreSQL target was explicitly configured for this task, so PostgreSQL
transaction/concurrency execution remains SKIPPED_ENVIRONMENT_GAP; the
PostgreSQL DDL and placeholder path were kept consistent with repository
migrations but are not claimed as live execution evidence.

## Test evidence

The focused C019 suite covers schema validation, successful debit and
acquisition, authoritative server price, replay, conflicting replay,
insufficient balance, unknown/disabled offers, acquisition rollback, debit
failure, equipment, cosmetic, trophy/authority locks, unsupported
destinations, duplicate cosmetic policy, D5A lineage, D5C separation, and
both concurrency cases.

Regression suites are run separately and reported with exact pytest counts in
the task handoff. No application route or UI test is treated as C019 live
integration evidence.

## Remaining Commerce gaps

1. A later integration task must bind the normalized offer authority to the
   real server Shop catalog and route, including daily rotation price
   resolution, bundles, and eligibility. C019 does not import app.py.
2. A later integration task must choose the governed binding between the
   existing _spend_coins helper and this transaction-safe adapter, while
   keeping user_stats.coins and currency_log as the only Coin authorities.
3. Capacity, credit, entitlement, and any non-inventory acquisition targets
   need their own existing authority adapters before they can be offered.
4. Player-facing Shop, Backpack, Wardrobe, equip/use actions, confirmation,
   read projections, and error mapping remain out of scope.
5. Production migration, Production Coins, Revenue enablement, Premium
   payment/claim integration, sell, dismantle, crafting, enhancement, trading,
   gacha, and loot boxes remain out of scope.

## Explicit non-goals and safety result

APP_PY_CHANGED=NO
PLAYER_UI_CHANGED=NO
RUNTIME_ROUTE_CHANGED=NO
PRODUCTION_SCHEMA_MUTATION=NO
PRODUCTION_MUTATION=NO
DEPLOY=NO
MASTER_MERGE=NO
NEW_COIN_BALANCE_AUTHORITY=NO
D5C_USED_FOR_ACQUISITION=NO

The result is a reviewable transaction foundation, not a live purchase
endpoint. It is ready for Owner review and for a separately authorized
integration wave.
