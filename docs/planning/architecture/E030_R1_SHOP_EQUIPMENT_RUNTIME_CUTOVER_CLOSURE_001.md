# E030-R1 Shop and Equipment Runtime Cutover Closure

Task: `E030_R1_SHOP_EQUIPMENT_RUNTIME_CUTOVER_CLOSURE_001`
Lane: `E`
Status: implementation candidate; Owner review required.

This document records the narrow repair on top of the recovered E030
implementation. It does not add products, change prices, enable a feature,
run a migration, access Production, or change any domain authority module.

## Source and boundaries

The R1 worktree was created from the exact current `origin/master` at task
start:

`e10735cf580fb5074e07811f76ab60445562760c`

The previously accepted E030 implementation was recovered by applying its
exact commits without rewriting them:

* implementation: `87d7614c537eb5eedd40e70edc387bb2cfc7a383`
* tests/docs: `d3298e85a4619270adf4573c7e8be917152de221`

B041 remains supplied by current master. The exact ownership-row APIs used
by this candidate are `equip_owned_item(..., ownership_row_id=...)` and
`unequip_owned_item(..., ownership_row_id=...)`.

## Existing runtime seams

| Concern | Entry point | R1 boundary | Authority retained |
| --- | --- | --- | --- |
| Shop item purchase | `POST /api/shop/buy` → `shop_buy` | server-fact dispatch, then canonical or unchanged legacy path | C025/C029, C019/C026, D024, or the existing legacy Shop writer |
| Shop appearance purchase | `POST /api/shop/buy_appearance` → `shop_buy_appearance` | same pre-mutation dispatch rule | C025/C029, C019/C026, D024, or existing daily-rotation writer |
| Equip/unequip | `POST /api/player/inventory/equip` → `equip_item` | authenticated row lookup and exact B041 row identity | B034/B041 loadout service when enabled; legacy path when disabled |
| Monster Equipment grant | `_settle_monster_defeat_in_tx` → `grant_functional_item` | B040 call once per quantity | Monster settlement decides drops; B040 writes ownership |
| Admin Equipment grant | `POST /api/admin/users/<uid>/assets/equipment` → `admin_set_equipment` | B040 call with `source="admin"` | existing admin auth/validation/audit |

The only application runtime file changed by the recovered E030 work is
`app.py`; R1 adds the real Shop caller change in `shop.html`, focused tests,
and this evidence.

## R1 blocker 1: pre-mutation Shop dispatch

The flags do not mean that every historical Shop product is canonical. When
`CANONICAL_COIN_SHOP_PURCHASE_ENABLED` is true, both Shop POST routes first
run `_classify_shop_request` using only current server catalog and rotation
facts. The classifier performs no Coin debit, operation reservation,
ownership write, legacy grant, or commit. Daily rotation resolution uses the
read-only `persist=False` form.

The dispatch contract is:

| Server-fact classification | Runtime path | Example covered by R1 |
| --- | --- | --- |
| `CANONICAL_READY` | C025/C029 projection → C019 → C026 → caller commit → D024 | `hint_ticket`, current pure Coin wardrobe |
| `LEGACY_ONLY` | existing legacy implementation exactly once | `premium_hint_bundle` bundle, `extra_questions_small` effect item, and a valid legacy appearance fixture |
| `INVALID` | stable 400/503 fail-closed response | unknown offer, conflicting selectors, malformed/unavailable dispatch facts |

The classifier rejects a request that partially identifies a canonical offer
or supplies conflicting selectors. It never calls C026 and then falls back
to legacy after a mutation or an adaptation error. A canonical failure and a
post-commit D024 presentation failure both stay on the canonical recovery
path.

The current real catalog still has zero functional Equipment Shop offers.
R1 does not add or remove any `SHOP_ITEMS`, cosmetics, bundles, effects,
pets, quantities, destinations, prices, or duplicate policies. The locked
identities remain `xp_amulet` (`AUTHORITY_HOLD`) and `go_stone_black`
(`TROPHY_INVENTORY_ONLY`).

## R1 blocker 2: real client operation identity

The real callers are in `shop.html`:

* `buyItem(key)` → `POST /api/shop/buy`
* `buyAppearance(itemId)` → `POST /api/shop/buy_appearance`

Both call the shared `requestShopPurchase(route, selector, payload)` helper.
For a new intent, the helper creates one UUID using
`crypto.randomUUID()` (with a cryptographic `getRandomValues` UUID fallback)
and adds it as `purchase_operation_id`. It does not use timestamps, weak
randomness, counters, item IDs, or database IDs.

Pending intent state is scoped by exact route and selector, kept in memory
and best-effort `sessionStorage`, and expires after 30 minutes. A network
failure, canonical-result 5xx, or `PURCHASE_OPERATION_IN_PROGRESS` response
retains the identity. Success, an invalid request, a definitive insufficient
Coin response, or another terminal response clears it. A subsequent retry of
the same intent therefore addresses the same C026 operation, while a new
intent after completion receives a new identity. No sensitive data is stored.

The Node contract test executes the helper extracted from the real page and
also statically verifies that both production caller functions use it; it is
not a test-only request-body injection.

## R1 blocker 3: exact Equipment ownership row

`equip_item` authenticates the session, selects
`player_inventory.id = inv_id AND user_id = session user`, and takes the
server row's `equip_id`. In canonical mode it passes both values to B041 as:

```text
equip_owned_item(..., server_row_equip_id, ownership_row_id=row.id)
unequip_owned_item(..., server_row_equip_id, ownership_row_id=row.id)
```

The request body `equip_id`, `slot`, and `canonical_slot` cannot choose the
target row or slot. The response includes `inv_id` and
`target_ownership_row_id` as exact-row evidence. Duplicate `iron_sword`,
armor, and accessory rows are covered; unequipping an already-unequipped
duplicate is an exact-row no-op. B041 stable ownership-row errors are mapped
without exposing SQL details.

The loadout flag remains `EQUIPMENT_CANONICAL_LOADOUT_ENABLED`, default off.
When on, missing or malformed B033 schema fails closed and does not fall back
to the legacy writer. B036 locked-item behavior remains intact.

## Transaction and authority rules

Canonical Shop execution remains:

```text
authenticated session
  → server Shop facts
  → C025/C029 normalized offer
  → C019 authority
  → C026 purchase_with_coins
  → caller-owned commit
  → committed operation + D5A evidence
  → D024 adaptation
  → response
```

`app.py` does not duplicate C026 or D024 logic. The route commits only after
the C026 operation, debit, ownership mutation, exact ownership reference,
lineage, and committed result are persisted. D024 is read after commit. If
adaptation fails, the response is an honest canonical-result-unavailable
failure; the same operation ID replays the committed purchase and cannot
debit or acquire a second time.

Monster and Admin grants still use B040 with sources `drop` and `admin`.
B040 does not decide Monster drops, auto-equip anything, or accept client
slot/stat authority.

## Feature and schema boundary

Both gates are request-time environment flags using the existing
`_env_flag_enabled` convention and are absent/false by default:

* `CANONICAL_COIN_SHOP_PURCHASE_ENABLED`
* `EQUIPMENT_CANONICAL_LOADOUT_ENABLED`

Gate-off tests preserve the existing Shop and Equip/Unequip behavior. The
canonical Shop path requires `coin_purchase_operations` and accepted
acquisition dependencies; the canonical loadout path requires valid B033
schema. E030-R1 does not modify schema code or execute any migration. C030's
legacy PostgreSQL text-timestamp compatibility remains `PASS` and is not
reopened.

B039 Option C remains the only release sequence: compatible code merge,
Production read-only preflight, traffic freeze, explicit production schema
authorization, approved migrations, compatible deploy, explicit feature
enable, invariant smoke proof, and reopen. None of those Production steps is
performed here.

## Static/cache boundary

R1 changes `shop.html` only for the operation identity lifecycle. The
repository static release packager governs the `i18n.js`/`sw.js` static pack;
HTML is handled by the existing network-first service-worker path. Therefore
`sw.js` is unchanged and no version bump is required for this HTML change.

## Validation evidence

The focused Python E030 + E030-R1 suite passes: **45 passed**. It includes
pre/post-B033
B040 grants, default-off behavior, canonical stackable/wardrobe purchases,
dispatch classification, schema fail-closed behavior, D024 recovery,
locked-item preservation, and exact B041 duplicate-row targeting.

The real-client Node contract passes with **9 requests** covering success, new-intent, network retry,
canonical-result 503 retry, in-progress retry, terminal clear, and
new-intent-after-completion cases.

The broad relevant Python matrix is **383 passed, 2 failed, 8 skipped**. The
two failures reproduce on the exact current-master parent and are not
introduced by E030-R1:

* `tests/test_rpg_wave1_lane_a_combat_equipment.py::test_equipped_armor_reduces_retaliation_and_unequip_restores_baseline`
  (baseline expects retaliation 20; current parent returns 2).
* `tests/test_rpg_wave2_lane_b_functional_equipment_presentation_wiring.py::test_reload_rehydrates_each_equipped_item_and_restores_same_presentation`
  (baseline loop includes the locked `xp_amulet` and receives the existing
  400 response).

The 8 skips are the B033/B034 PostgreSQL tests requiring an explicitly marked
disposable PostgreSQL target; no such target was used. The Lane B source
regression is **15 passed** and the additional Shop/collection/commerce
presentation set is **37 passed**. The browser IA test could not start because
the isolated worktree has no `playwright-core`; this is an environment gap,
not an R1 code failure. Python compile/import, JavaScript syntax, and
`git diff --check` pass.

## Release verdict

* `APP_PY_SINGLE_WRITER=YES`
* `B034_ROUTE_CUTOVER=YES` in code structure, still default off
* `CANONICAL_COIN_SHOP_PRODUCTION_SCHEMA_READY=NO`
* `CURRENT_REAL_FUNCTIONAL_EQUIPMENT_OFFER_COUNT=0`
* `SW_JS_CHANGED=NO`
* `PRODUCTION_QUERY=NO`
* `PRODUCTION_MUTATION=NO`
* `PRODUCTION_SCHEMA_MIGRATION=NO`
* `FEATURE_ENABLED=NO`
* `DEPLOY=NO`
* `MASTER_MERGE=NO`

This is ready for Owner E030-R1 review only; it is not a merge, enablement,
migration, or deployment authorization.
