# A031 Equipment + Backpack Reference-Faithful Art Production

## Status and authority

This package applies the Owner-approved `GO_ODYSSEY_OWNER_VISUAL_REFERENCE_V1` direction to the existing E10 `/inventory?e10=1` presentation surface. The standalone Equipment + Backpack reference is the page-specific visual authority; the full contact sheet is the cross-surface authority. Both are visual references only. Current-master server contracts remain the gameplay and data authority.

The implementation is intentionally presentation-only:

- Functional Equipment ownership and equipped state remain `player_inventory` and `player_inventory.equipped`.
- Effects and comparison values remain server-provided `EQUIPMENT_DEFS` projections.
- The only mutation remains the existing `/api/player/inventory/equip` route with its existing `inv_id`/`action` contract.
- Backpack ownership/use remains the existing `/api/shop/catalog`, `/api/pet/status`, and `/api/shop/use` domain contract.
- Appearance ownership remains separate in `player_wardrobe` and `/api/player/appearance`.
- `xp_amulet` remains equip-blocked and `go_stone_black` remains inventory-only.

No reference-only item, price, currency, stat, level, rarity, or action was promoted into product authority.

## Current-master recon

| Surface | Current implementation | Authority preserved |
| --- | --- | --- |
| E10 Equipment + Backpack | `inventory.html?e10=1` | E10 shell, existing controller |
| Functional Equipment | `loadFunctionalEquipment()`, `renderFunctionalEquipmentGrid()`, `renderFunctionalEquipmentDetail()` in `inventory.html` | `/api/player/inventory`, `/api/skills/profile` |
| Equip / Unequip | `performFunctionalEquipmentAction()` | `/api/player/inventory/equip` |
| Backpack | `loadBackpack()`, `renderBackpackGrid()` in `inventory.html` | `/api/shop/catalog`, `/api/auth/me`, `/api/pet/status` |
| Wearable Hero projection | `GoOdysseyWearableRenderer` from `js/rpg_wave2_wearable_renderer.js` | `player_appearance.character_key` plus server-equipped projection |
| Visual rules | `css/e10/backpack.css` scoped by `html[data-e10-backpack-shell="true"]` | presentation only |

The new composition keeps the existing DOM IDs and controller functions. It adds a three-column Hero / Loadout / Selected Detail board, then a real-art Equipment collection and the existing Backpack inventory. This is a visual re-composition, not a second inventory or equipment authority.

## Reference-faithful composition

The E10 view now reads in this order:

1. Hero scene with existing fantasy environment art and transparent wearable projection.
2. Exactly three server-backed loadout slots: Weapon, Armor, Accessory.
3. Selected functional item detail with existing truthful effects, comparison and action.
4. Functional Equipment collection using the existing SVG item art.
5. Backpack inventory grid using the existing approved shop/item art mapped by canonical item key.

Bright Adventure tokens are applied to the E10 surface: light sky/cream/world surfaces, Adventure Blue selection, Go Odyssey Teal action, Sun Yellow for the small state badge, and Deep Navy structural contrast. Gold is not used as a default card border. Existing E10 fantasy art remains visible behind the surface; the light treatment is not a white-dashboard replacement.

## Asset intake and coverage

`A031_EQUIPMENT_BACKPACK_ASSET_MANIFEST_001.json` inventories 15 functional Equipment records and 24 current catalog / Spirit-inventory records. Every listed current item resolves to an existing repository asset:

- Functional Equipment: `/assets/hero/equipment/functional/*.svg`.
- Wearable projection: `/assets/hero/equipment/wearables/overlays/*.png` plus the existing transparent character bases.
- Backpack catalog and Spirit items: existing `/assets/shop/*.webp` and `/assets/items/*.svg`.

Current coverage is 39/39 existing approved item-art records. If an unexpected future key has no approved asset, the E10 card fails closed to an explicit `MISSING_FINAL_ART` placeholder; it never falls back to emoji or a generic glyph.

The existing `cloth_robe.png` and `fox_pelt.png` Hero overlays received alpha-only cleanup: baked checkerboard/background pixels were removed and fully transparent pixels were normalized to `(0, 0, 0, 0)`. Visible character/item pixels, dimensions and wearable identity were not redrawn or regenerated.

The Owner reference examples `Spirit Badge`, `Starweave Cloak`, and `Supply Potion` are not current product identities and remain reference-only. No product rows were created for them.

## Functional / non-functional visual language

- Functional Equipment uses slot, equipped, effect and equip/unequip language.
- Trophy / inventory-only `go_stone_black` is shown as collection-only and has no functional Hero overlay.
- `xp_amulet` can use the existing presentation art but remains blocked by its current equip contract.
- Consumables and materials use the existing Backpack capability labels and only expose the existing manual-use action where the server says it is valid.
- Pure cosmetics are not merged into Functional Equipment and do not receive combat-effect language.

The page copy remains DOM/i18n-driven: Chinese mode uses Chinese labels and English mode uses English labels; item names and effects still come from the existing server payload.

No unsupported Combat Power, DPS, Crit, Gear Score, or invented comparison number was added.

## Responsive contract

| Target | Composition |
| --- | --- |
| Desktop | Hero / Loadout / Selected Detail in one board; Equipment and Backpack grids below |
| Tablet landscape | Hero + Loadout; Selected Detail spans below; four-column item grids |
| Tablet portrait | Same bounded two-column board with detail below; no horizontal overflow |
| Mobile | Hero → three-slot Loadout → Selected Detail → two-column real-art collections; touch targets remain at least 44px |

The design does not shrink the desktop into unreadable columns. Hero art, item art and selected state remain visible at mobile card scale. Existing reduced-motion rules remain active.

## Evidence and remaining art boundary

The required evidence set is generated outside the repository under `D:\go-odyssey-evidence\a031-equipment-backpack-reference-faithful-*`. It distinguishes Owner reference material from runtime pixels and labels any unexpected asset gap explicitly. The current manifest reports no missing final art for the 39 real current records. Future final illustration production can replace the approved current SVG/WebP item art without changing the authority contract.

## Non-goals

This task does not change `app.py`, routes, database/schema, Equipment slot semantics, item definitions, Shop or Premium authority, Spirit mechanics, World authority, combat math, prices, rewards, feature flags, Service Worker code, or Production. No final new item illustration catalog is invented from the reference sheet.
