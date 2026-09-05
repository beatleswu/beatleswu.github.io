# W2-03 Hero Wearable Visual Refresh 002R1

## Bounded outcome

This package audits the 14 functional wearable overlays in the canonical
`PLAYER_FRAME_A_STANDARD_CHIBI` frame and hardens presentation-only rendering.
Twelve existing transparent overlays are retained in the normalized-frame
renderer. `cloth_robe` and `fox_pelt` are explicitly held out because their
source pixels contain a baked opaque checkerboard/product field. No CSS crop,
background-colored mask, blur, or substitute art is used to disguise them.

The machine-readable classification is in
`w2_03_hero_wearable_visual_refresh_002r1_manifest.json`.

## Classification

| Class | Meaning | Items | Count |
| --- | --- | --- | ---: |
| A | `READY_TRANSPARENT_WEARABLE` | `wooden_sword`, `iron_sword`, `fox_fang`, `dragon_claw`, `celestial_blade`, `leather_armor`, `dragon_scale`, `void_mantle`, `lucky_stone`, `xp_amulet`, `fox_mask`, `dragon_eye` | 12 |
| B | `COMPOSITING_FIX_REQUIRED` | none | 0 |
| C | `ART_REPLACEMENT_REQUIRED` | `cloth_robe`, `fox_pelt` | 2 |

The 14-item count excludes `go_stone_black`, which remains the canonical
inventory-only item and is not a wearable overlay.

## Runtime behavior

`js/rpg_wave2_wearable_renderer.js` now applies an explicit presentation
quality gate. C-class source art is omitted before DOM layer creation, while
the server-owned equipped projection is preserved. The renderer records the
held-out IDs in `data-replacement-ids`, keeps
`data-authority="server_equipped_projection"`, and keeps
`data-gameplay-authority="none"`.

`hero.html` keeps the held-out item visible in the read-only equipment
projection and labels it `已裝備 · 穿戴圖待替換` / `Equipped · wearable art pending
replacement`. This makes the fallback explicit rather than silently making
the item appear unequipped.

## Representative proof contract

The owner-visible proof uses server-backed fixture projections for:

- no functional equipment;
- `wooden_sword` as the weapon;
- `cloth_robe` as the held-out failed-art case;
- `lucky_stone` as the accessory;
- `wooden_sword + dragon_scale + lucky_stone` as the full wearable proof.

The proof is captured as before/after Hero crops at desktop, iPad portrait,
and mobile portrait. The crop is enlarged for review; it does not change the
production CSS dimensions.

## Authority and scope

- ownership/equipped state remains `player_inventory` and
  `player_inventory.equipped`;
- character identity remains `player_appearance.character_key`;
- effects remain server `EQUIPMENT_DEFS`;
- rendering is read-only and has no POST, inventory, combat, payment, or
  gameplay authority;
- no new art was created;
- `app.py`, DB/schema/data, payment, Shop authority, Loadout authority,
  Zone3, and Production were not changed.

## Current status

`PASS_W2_03_COMPOSITING_COMPLETE_WITH_TARGETED_ART_REPLACEMENTS_IDENTIFIED`

The two C-class assets need separately approved replacement art before they
can be promoted to wearable presentation. The remaining 12 overlays are
reused without bespoke item/character redraws.
