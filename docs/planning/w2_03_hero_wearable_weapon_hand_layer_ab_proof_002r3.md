# W2-03 Wooden Sword Hand-Layer A/B Proof

## Decision boundary

This is a review-only visual proof. Variant A remains the accepted R2
`CARRIED_AT_HIP / BACK_WEAPON` presentation. Variant B uses the existing
`wooden_sword` art in a review-only `FRONT_WEAPON` layer with its handle aligned
to the Hero's visible right palm. No Owner selection has been made.

`OWNER_SELECTION_REQUIRED=YES`

Possible decisions:

- `OWNER_SELECT_A_HIP_CARRY`
- `OWNER_SELECT_B_HAND_HELD`
- `OWNER_REJECT_BOTH`

## Evidence

| Viewport | Full A/B comparison | Right-hand close-up |
| --- | --- | --- |
| Desktop | [desktop-ab.png](../../tests/e2e/evidence/w2_03_hero_wearable_weapon_hand_layer_ab_proof_002r3/desktop-ab.png) | [desktop-right-hand-closeup.png](../../tests/e2e/evidence/w2_03_hero_wearable_weapon_hand_layer_ab_proof_002r3/desktop-right-hand-closeup.png) |
| iPad portrait | [ipad-portrait-ab.png](../../tests/e2e/evidence/w2_03_hero_wearable_weapon_hand_layer_ab_proof_002r3/ipad-portrait-ab.png) | [ipad-portrait-right-hand-closeup.png](../../tests/e2e/evidence/w2_03_hero_wearable_weapon_hand_layer_ab_proof_002r3/ipad-portrait-right-hand-closeup.png) |
| Mobile portrait | [mobile-portrait-ab.png](../../tests/e2e/evidence/w2_03_hero_wearable_weapon_hand_layer_ab_proof_002r3/mobile-portrait-ab.png) | [mobile-portrait-right-hand-closeup.png](../../tests/e2e/evidence/w2_03_hero_wearable_weapon_hand_layer_ab_proof_002r3/mobile-portrait-right-hand-closeup.png) |

The machine-readable browser observations are in
[browser-results.json](../../tests/e2e/evidence/w2_03_hero_wearable_weapon_hand_layer_ab_proof_002r3/browser-results.json).

## Observed implementation

- Existing source art only: `apprentice_p1.png` and `wooden_sword.png`.
- Variant A keeps the R2 default registry transform and `BACK_WEAPON` order.
- Variant B is opt-in through `presentationVariant` and requires the registry
  entry to be `review_only=true`; it is not selected by the normal Hero page.
- Variant B renders after the base Hero, with the handle crossing the visible
  right palm in the captured proof.
- Armor/accessory layer behavior is unchanged.
- The renderer does not write inventory, loadout, combat, progression, or
  server state.

## Validation

```text
python -m pytest -q tests/test_w2_03_hero_wearable_weapon_hand_layer_ab_proof_002r3.py tests/test_w2_03_hero_wearable_weapon_attachment_correction_002r2.py tests/test_rpg_wave2_wearable_renderer_delivery.py
12 passed

node tests/e2e/run_w2_03_hero_wearable_weapon_hand_layer_ab_proof_002r3.mjs
W2_03_WEAPON_HAND_LAYER_AB_PROOF=PASS
W2_03_WEAPON_HAND_LAYER_AB_VIEWPORT_COUNT=3

node tests/e2e/run_w2_03_hero_wearable_weapon_attachment_correction_browser_qa.mjs
W2_03_WEAPON_ATTACHMENT_QA=PASS
W2_03_WEAPON_ATTACHMENT_CASE_COUNT=9
```

## Scope

`HERO_ART_CHANGED=NO`  
`WOODEN_SWORD_ART_CHANGED=NO`  
`NEW_ART_CREATED=NO`  
`DRAGON_SCALE_CHANGED=NO`  
`LUCKY_STONE_CHANGED=NO`  
`APP_PY_CHANGED=NO`  
`PRODUCTION_MUTATED=NO`  
`MERGED=NO`  
`DEPLOYED=NO`
