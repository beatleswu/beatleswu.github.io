# W2-03 Hand-held wooden sword promotion and replacement-art preparation

## Decision applied

`OWNER_SELECT_B_HAND_HELD` is now the single canonical presentation for
`wooden_sword`. The existing R3 Variant B transform is promoted from its
review-only fixture into the shared wearable renderer:

```text
WOODEN_SWORD_PRESENTATION=HAND_HELD
WOODEN_SWORD_ATTACHMENT=RIGHT_PALM
WOODEN_SWORD_LAYER=FRONT_WEAPON
MODE=FRONT_WEAPON_HAND_ALIGNED
OFFSET_PERCENT=(5,3)
ROTATION_DEG=0
SCALE=0.95
```

The existing `wooden_sword.png` is reused unchanged. The renderer consumes the
per-item attachment/layer/transform metadata and does not contain a
wooden-sword-specific transform or a client-side equipment authority.

The R3 A/B HTML and captured images remain historical Owner evidence only. They
are not loaded by the product route. The runtime no longer exposes the
`review_presentation_variants` or `presentationVariant` path, so there is one
production presentation path for `wooden_sword`.

## Replacement-art specifications

The two C-class source images remain fail-closed in the renderer. No pixels
were generated or altered in this task. The machine-readable specifications
are in
`w2_03_hero_wearable_weapon_hand_held_promotion_and_replacement_art_prep_002r4.json`.

| Item | Slot | Target layer | Required result |
| --- | --- | --- | --- |
| `cloth_robe` | armor | `TORSO_ARMOR` | Transparent open-neck torso garment aligned to the shared Hero frame; face, hands, legs, and body silhouette remain readable. |
| `fox_pelt` | armor | `BACK_BODY` | Transparent shoulder/back fur mantle behind the Hero base; central neck opening and face-safe region remain clear. |

Both specifications require a transparent 1056x1408
`PLAYER_FRAME_A_STANDARD_CHIBI` canvas, frame-relative alignment, declared
occlusion, and no product-image field. Stretching, cropping, masking, blur, or
background matching the current opaque source is explicitly rejected.

## Preserved policy and authority

- `dragon_scale` and `lucky_stone` keep their accepted compositing paths.
- `xp_amulet` remains `HOLD_FOR_AUTHORITY` and is not used as proof equipment.
- `go_stone_black` remains `INVENTORY_ONLY` and is not rendered as a wearable.
- Ownership and equipped state remain server projections from
  `player_inventory`; wearable rendering remains presentation-only.
- `app.py`, database/schema/data, payment, Shop/Loadout authority, Zone3, and
  Production are outside this task.

## Evidence and validation

The final browser harness uses the actual `/hero?tab=equipment` product route
with isolated server fixtures for no equipment, wooden sword, and
wooden-sword + `dragon_scale` + `lucky_stone` states. It checks the server
projection, layer order, right-palm attachment metadata, no-gap transform,
the preserved armor/accessory layers, and page errors at desktop, iPad
landscape, iPad portrait, and mobile portrait sizes.

Owner-visible close-ups are written to the task evidence directory after the
harness passes:

```text
tests/e2e/evidence/w2_03_hero_wearable_weapon_hand_held_promotion_and_replacement_art_prep_002r4/
```

`NEW_ART_CREATED=NO`.
