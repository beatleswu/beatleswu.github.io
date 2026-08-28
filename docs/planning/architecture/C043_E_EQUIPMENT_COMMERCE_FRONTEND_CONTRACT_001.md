# C043-E Equipment Shop Frontend Contract

Task: `C043-E` — bounded frontend implementation at
`c2a1dab3125cdef0cff381815d3d995bdd340538`.

## Scope and boundary

This change is frontend-only. `shop.html` can render an optional equipment
panel and report a server-confirmed purchase, but it does not create catalog
entries, choose prices/currency/rarity/scarcity, mutate ownership, equip an
item, or change feature defaults. No `app.py`, backend, schema/migration,
payment, `.env`, secret, or Production file is changed.

The panel is hidden when the catalog has no `equipment_offers`. The current
base catalog has no such field and the existing C43/E030 runtime contract has
no real functional-equipment catalog entries, so the default rendering stays
unchanged while the server remains default-off.

## Optional catalog projection

When separately authorized, `/api/shop/catalog` may add an
`equipment_offers` array. Each entry must be the existing server-owned
`CoinShopOffer.as_dict()` shape, with these facts already resolved by the
server:

```json
{
  "offer_id": "server-owned-offer-id",
  "item_id": "server-owned-item-id",
  "quantity": 1,
  "currency_type": "COINS",
  "price": "<positive server-owned integer>",
  "destination": "player_inventory",
  "acquisition_class": "WEAPON",
  "status": "ACTIVE"
}
```

`price` is a positive server value; the placeholder above is not a proposed
price. `acquisition_class` is limited to the existing
functional equipment classes. Optional `presentation_metadata` may provide
server-owned `name`, `name_en`, `description`, `description_en`, `icon`, or
`icon_path` values. The frontend discards malformed entries and has no local
product, price, currency, rarity, or scarcity defaults.

## Purchase and feedback loop

The equipment button posts to the existing `POST /api/shop/buy` route with
`offer_id`. The established `requestShopPurchase` helper adds a stable
`purchase_operation_id`; network, post-commit canonical-result, and
in-progress failures keep that identity for a same-purchase retry. Client
price, quantity, destination, slot, and equip fields are not sent.

A success message is shown only when the response contains `ok: true` and a
verifiable `canonical_acquisition_result` whose server facts match the offer:

```json
{
  "source_type": "SHOP_COIN_PURCHASE",
  "source_operation_id": "server-owned-operation-id",
  "source_reference": "server-owned-offer-id",
  "destination": "PLAYER_INVENTORY",
  "ownership_authority": "player_inventory",
  "ownership_reference": "player_inventory:<exact-inserted-row-id>",
  "item_id": "server-owned-item-id",
  "quantity": 1,
  "can_equip": true,
  "can_wear": true,
  "is_new": true,
  "replayed": false
}
```

The Backpack link is derived only from that exact validated ownership
reference. No row ID is reconstructed from current inventory state. The
message explicitly says that equipment is added to the Backpack and that no
automatic equip occurs. A missing or inconsistent canonical result is shown
as an error and never as purchase success.

## Exact `app.py` patch still needed

No `app.py` patch is included in this commit. To expose the optional panel,
the separately authorized server owner should add this projection inside
`shop_catalog()`, after `slots = _daily_shop_slots(conn)` and before leaving
the database context:

```python
equipment_offers = []
if _canonical_coin_shop_purchase_enabled():
    for server_facts in _canonical_shop_offer_facts(conn):
        if server_facts.destination != 'player_inventory':
            continue
        try:
            equipment_offers.append(normalize_shop_offer(server_facts).as_dict())
        except (OfferNotReady, ShopOfferIdentityError):
            continue
```

Then add the already-resolved list to the existing `jsonify` mapping:

```python
'equipment_offers': equipment_offers,
```

This is a route projection only. It must not add a product to `SHOP_ITEMS`,
invent a price or currency, or enable `SHOP_ENABLED`/`LOADOUT_ENABLED` (or
their current canonical server flag names). The existing server-owned offer
authority and purchase route remain the source of truth.
