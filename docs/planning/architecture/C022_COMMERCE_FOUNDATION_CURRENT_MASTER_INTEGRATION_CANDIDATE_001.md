# C022 — Commerce Foundation Current-Master Integration Candidate

Status: current-master integration candidate; Owner review required.

C022 forward-integrates the accepted C019 Coin purchase core and C021 Shop
offer adapter onto the current canonical master line. It does not wire a Shop
route or promote any catalog into runtime authority.

## Provenance

| Field | Value |
|---|---|
| Repository | `D:\go-website` |
| Current canonical master at start | `b75308d44806bb7c2e2b131a73ba06a71c188b3c` |
| C022 branch | `codex/c022-commerce-foundation-current-master` |
| C019 accepted base | `8016d7a9e9f6316b8977865ee8233934d8efac28` |
| C019-R1 accepted | `cb8f7e07350edb873c6300bfae3680819b0329f6` |
| C020 accepted | `2d2d20afad69fe7b7e0b00f2c78c74f9b9d7694c` |
| C021 accepted | `f8124b4d77cf04f2b9fb09fd5e8a5f14faeb93fe` |
| C021-R1 accepted | `8af8e69cd22b1fddb2dab8e9b769067091d51d90` |
| App / route / Production behavior | unchanged |

The C022 worktree was created directly from `origin/master`. The canonical
checkout's unrelated tracked planning change was preserved and not included.

## Forward-integrated lineage

The accepted commits were selected by exact SHA and applied in dependency order;
no old branch was merged wholesale.

| Accepted source | C022 forward commit | Content |
|---|---|---|
| `8016d7a9e9f6316b8977865ee8233934d8efac28` | `ad1d38910` | C019 offer authority, purchase core, operation migration, tests, docs |
| `cb8f7e07350edb873c6300bfae3680819b0329f6` | `f4cbdb6b4` | C019-R1 truthful balance transition and equipment `is_new` fix |
| `2d2d20afad69fe7b7e0b00f2c78c74f9b9d7694c` | `8a7897e15` | C020 catalog evidence and normalization matrix docs |
| `f8124b4d77cf04f2b9fb09fd5e8a5f14faeb93fe` | `c23ab42d4` | C021 pure Shop offer adapter, tests, docs |
| `8af8e69cd22b1fddb2dab8e9b769067091d51d90` | `0606586d6` | C021-R1 positive-price-only C019 closure |

The C019 R1 source is a descendant of the accepted C019 base. The current
master commit is an ancestor of the C022 branch and also contains the
accepted C019 parent ancestry through `58d9b7047f285751a048fc551c955909c87984ac`.

## Transitive dependency proof

C019 imports:

```text
coin_purchase_authority.py
  -> event_outbox.append_event
  -> migrations.coin_purchase_operations_v1
  -> shop_offer_authority
```

C019 tests also exercise:

```text
migrations.domain_event_outbox_v1
```

Before integration, current master already contained and supplied:

- `event_outbox.py`, including `append_event` and `ITEM_ACQUISITION` support;
- `migrations/domain_event_outbox_v1.py`, including the D5A schema and
  `upgrade`/`validate_schema` APIs.

The missing C019-specific files were supplied by the accepted C019 base
commit, especially `migrations/coin_purchase_operations_v1.py`. No duplicate
outbox or second Coin ledger was created. Current master has nine changed
lines in `event_outbox.py` relative to the C019 parent, but the imported API
and D5A contract required by C019 remain available and the dependency suite
passes.

## C019 foundation preserved

The integrated C019 core retains:

- `user_stats.coins` as the only Coin balance authority;
- server-owned `CoinShopOffer` resolution;
- durable `(user_id, purchase_operation_id)` identity;
- deterministic same-operation replay;
- changed-payload/offer conflict failure;
- atomic Coin debit, destination acquisition, D5A evidence, and result
  persistence inside the caller-owned transaction;
- C019-R1 truthful `coins_before`, `coins_spent`, `coins_after` transitions;
- D5A `ITEM_ACQUISITION` evidence and no D5C purchase path.

The operation migration is code only. C022 does not run it against a live or
Production database.

## C021 foundation preserved

The integrated adapter remains caller-input-driven and does not import or copy
`app.py:SHOP_ITEMS`. Every READY offer has:

```text
currency = COINS
server_price is int and > 0
```

`FREE_OFFER`, including `server_price=0` with approval metadata, is rejected
with `NEEDS_FREE_GRANT_AUTHORITY` details and cannot produce a C019 mapping.
Premium cash, gacha, `robe_premium`, legacy-effect cosmetics, client-authored
price/offer IDs, and other C021-R1 exclusions remain fail-closed.

`pet_inventory` remains `NEEDS_DESTINATION_ADAPTER`; multi-grant products
remain `NEEDS_MULTI_GRANT_PROFILE`.

Daily offers retain a stable business `offer_id`, while `offer_version` and
eligibility reference carry the business date.

## C020 evidence boundary

The accepted C020 Markdown and JSON artifacts are included as catalog evidence
and normalization history. They were produced against an earlier accepted
source base. A static comparison shows `app.py` has since drifted from the
C020 parent (`1173` insertions and `157` deletions), so C022 does not treat
C020's product counts or matrices as a live current-master catalog authority.

No new catalog dictionary was created. A later route-wiring task must refresh
the source facts from current server code before selecting READY offers.

## No route cutover

C022 does not modify:

- `app.py`;
- `/api/shop/buy` or `/api/shop/buy_appearance`;
- Shop, Backpack, Wardrobe, or frontend code;
- payment or Premium routes;
- Production schema or database state.

The foundation is not live until a separately authorized integration task
connects current server catalog facts and a route caller to C019.

## Validation evidence

In the C022 current-master worktree:

```text
C019 + C021 focused suites:       42 passed
D5A outbox/migration suite:       14 passed, 1 skipped
```

The focused tests cover exactly-once replay, changed-payload conflict,
insufficient Coins, acquisition rollback, C019 operation schema, D5A/D5C
separation, positive-price guarantees, zero-price free-offer rejection,
daily stable IDs and date versions, Premium/gacha exclusions, pet destination
classification, and multi-grant classification.

No Production migration, Coin mutation, route wiring, deployment, or merge was
performed.
