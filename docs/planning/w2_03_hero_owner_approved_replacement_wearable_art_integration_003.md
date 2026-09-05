# W2-03 Owner-approved replacement wearable integration

This handoff integrates the exact Owner-approved `cloth_robe` and `fox_pelt`
PNG inputs into the existing `PLAYER_FRAME_A_STANDARD_CHIBI` wearable frame.
The raw approved inputs are preserved under
`w2_03_hero_owner_approved_replacement_wearable_sources/`; the normalized
runtime overlays are the only files served by the presentation renderer.

## Binding results

| item | output | anchor | layer | frame | acceptance |
| --- | --- | --- | --- | --- | --- |
| `cloth_robe` | `/assets/hero/equipment/wearables/overlays/cloth_robe.png` | `torso` `(0.50, 0.35)` | `TORSO_ARMOR` | `1056x1408` | Owner review pending |
| `fox_pelt` | `/assets/hero/equipment/wearables/overlays/fox_pelt.png` | `shoulder_or_torso` `(0.50, 0.31)` | `BACK_BODY` | `1056x1408` | Owner review pending |

`fox_pelt` deliberately uses the corrected `BACK_BODY` binding rather than the
old `TORSO_ARMOR` binding. Its shoulder alignment follows the locked
`[0.16, 0.22, 0.84, 0.52]` core box while the approved artwork's long side/tail
fur remains aspect-preserving instead of being squashed or cropped. That tail
extension is explicitly recorded in the machine-readable manifest and remains
part of Owner visual review.

Both files are RGBA, have transparent frame corners, and were normalized with
uniform scaling only. No motif, recolor, silhouette redesign, Hero repaint, or
new artwork was introduced. The renderer's replacement-art fail-closed list is
empty because both previously blocked IDs now have approved replacement input;
the list remains the future seam for any later unapproved item.

## Owner-visible evidence

The complete four-viewport evidence set is in
`docs/evidence/w2_03_owner_approved_replacement_wearables_003/`.
It contains the no-armor baseline, each replacement independently, and both
`wooden_sword + armor + lucky_stone` combinations. The closeups isolate the
robe neck/shoulders/sleeves/waist and the fox neck opening/shoulders/side fur.
The browser harness exercised 120 cases across the six registry characters;
the captured screenshots use the canonical `apprentice` server projection so
the evidence camera never widens character-selection authority.

Representative closeups:

- [cloth_robe desktop closeup](../evidence/w2_03_owner_approved_replacement_wearables_003/desktop-cloth-closeup.png)
- [cloth_robe iPad portrait closeup](../evidence/w2_03_owner_approved_replacement_wearables_003/ipad-portrait-cloth-closeup.png)
- [fox_pelt desktop closeup](../evidence/w2_03_owner_approved_replacement_wearables_003/desktop-fox-closeup.png)
- [fox_pelt iPad portrait closeup](../evidence/w2_03_owner_approved_replacement_wearables_003/ipad-portrait-fox-closeup.png)

## Preserved policy

The presentation remains a read-only projection of server-owned equipped state.
`wooden_sword` remains `HAND_HELD / RIGHT_PALM / FRONT_WEAPON`;
`dragon_scale` and `lucky_stone` remain on their accepted bindings;
`xp_amulet` remains `HOLD_FOR_AUTHORITY`; and `go_stone_black` remains
`INVENTORY_ONLY`. No Shop, Loadout, gameplay, database, payment, or Production
authority changed.

Automated shared-frame and browser checks are evidence only. Final visual
acceptance is intentionally still:

```text
CLOTH_ROBE_OWNER_VISUAL_ACCEPTANCE=PENDING
FOX_PELT_OWNER_VISUAL_ACCEPTANCE=PENDING
```
