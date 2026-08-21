# Master Lane A — Sword Pose × Dragon Scale Compatibility Closeout

This packet is a Lane A presentation-only continuation of the verified
`2b20bae77` compatibility prototype. It does not change ownership, equip
state, combat, inventory, runtime registration, or database authority.

## Scope

The proof covers the minimum required prototype characters:

- `apprentice`
- `mage`
- `paladin`

For each character, the existing package contains:

- default pose + `dragon_scale`;
- full-body `one_hand_sword_pose` + the same universal pose-aware
  `dragon_scale` overlay;
- desktop comparison and sword-pose matrices;
- mobile-scale matrix;
- static asset-contract validation.

The full-body weapon pose is the complete character variant. No local hand,
forearm, or bespoke item-character redraw is used.

## Review results

| Check | Result | Evidence |
| --- | --- | --- |
| Torso masking | `PASS_REVIEW_READY` | six default/sword composites |
| Arm occlusion | `PASS_REVIEW_READY` | sword-pose composites and overlay manifest |
| Weapon-hand alignment | `PASS_REVIEW_READY` | full-body sword variants |
| Shoulder layering | `PASS_REVIEW_READY` | default vs sword comparison |
| Cape/mantle interaction | `PASS_REVIEW_READY` | mage composite and pose-aware overlay |
| Mobile readability | `PASS_REVIEW_READY` | `SWORD_POSE_DRAGON_SCALE_MOBILE_MATRIX.png` |
| Default pose remains unchanged | `PASS_REVIEW_READY` | default/sword comparison |

## Gate status

`WEAPON_POSE_ARMOR_COMPATIBILITY=READY_FOR_OWNER_PASS_3_OF_6`

`OWNER_PASS=NOT_PRESENT`

The artifact labels in the source manifest are review-candidate evidence,
not Owner acceptance. The remaining 14 Sword Pose characters must not enter
mass production until the Owner explicitly passes this gate.

## Authority invariants

```text
FUNCTIONAL_EQUIPMENT_AUTHORITY=player_inventory
FUNCTIONAL_EFFECT_AUTHORITY=server EQUIPMENT_DEFS
POSE_SELECTION=PRESENTATION_ONLY
CLIENT_COMBAT_AUTHORITY=NO
RUNTIME_AUTHORITY_CHANGED=NO
DB_MIGRATION=NO
```

## Review artifacts

- `matrices/DEFAULT_VS_SWORD_POSE_ARMOR_COMPARISON.png`
- `matrices/SWORD_POSE_DRAGON_SCALE_3_CHARACTER_MATRIX.png`
- `matrices/SWORD_POSE_DRAGON_SCALE_MOBILE_MATRIX.png`
- `manifest.json`
- `tests/test_rpg_wave2_weapon_pose_armor_compatibility.py`
