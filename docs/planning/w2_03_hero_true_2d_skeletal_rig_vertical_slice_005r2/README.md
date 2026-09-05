# W2-03 apprentice_p1 true 2D skeletal foundation

This package is the in-flight foundation for
`W2_03_HERO_TRUE_2D_SKELETAL_EQUIPMENT_RIG_VERTICAL_SLICE_005R2`, amended by
`W2_03_HERO_TRUE_2D_SKELETAL_RIG_ART_DEPENDENCY_AMENDMENT_005R2A`.

It deliberately stops short of final visual acceptance. The runtime has a
real parent/child bone graph, slots, local attachment transforms, deterministic
draw order, a looping local-bone timeline, responsive design-space fitting,
and lifecycle cleanup. It is presentation-only and does not read or write
inventory authority.

## Foundation artifacts

| Artifact | Purpose |
| --- | --- |
| `apprentice_p1_skeletal_manifest.json` | Fixed design-space bone, slot, attachment, timeline, source provenance, and art-dependency contract. |
| `js/e9/hero_skeletal_rig.js` | Dependency-free Canvas2D runtime. Every rendered region is a slot attachment transformed by its bone world matrix plus local attachment transform. |
| `docs/evidence/w2_03_hero_true_2d_skeletal_rig_vertical_slice_005r2/foundation_probe.html` | Local animated foundation probe with base, sword, robe, pelt, and full-loadout presentation presets. It is not a production route. |
| `tests/test_w2_03_hero_true_2d_skeletal_rig_vertical_slice_005r2.py` | Bounded manifest, transform, animation, responsive, lifecycle, and authority-boundary checks. |

## Frozen source and current technical proof

Only the existing approved source PNGs are referenced. No source image is
rewritten and no derivative art is committed. The source atlas and each
wearable remain full-frame 1056×1408 transparent PNGs; the manifest uses
source rectangles and masks as technical attachment metadata.

The foundation proves the following without claiming final visual approval:

* `LUCKY_STONE` is attached to `CHEST` through `CHEST_ACCESSORY`.
* `WOODEN_SWORD` is technically attached to `HAND_R` through a reusable item
  attachment record. The approved prop is not altered.
* `CLOTH_ROBE` has torso and arm-relative sleeve attachment infrastructure.
* `FOX_PELT` has a rear `BACK` slot and torso-relative attachment infrastructure.
* The same design-space skeleton is fitted into any viewport; no viewport
  coordinate becomes attachment authority.

## Art gate

The support audit is authoritative: the current flat Hero and wearable art is
not sufficient for a professional full-body true skeletal visual proof. The
following Owner-approved art dependencies remain open:

1. `apprentice_head_hair_rig_patch`
2. `apprentice_torso_pelvis_rig_patches`
3. `apprentice_arm_hand_rig_patches` (including `right_hand_closed_grip`)
4. `cloth_robe_skeletal_segments`
5. `fox_pelt_skeletal_mantle_segments`

Accordingly, `WOODEN_SWORD_FINAL_VISUAL_PROOF`,
`CLOTH_ROBE_FINAL_VISUAL_PROOF`, and `FOX_PELT_FINAL_VISUAL_PROOF` are all
`BLOCKED_WAIT_OWNER_APPROVED_RIG_ART`. No closed grip, hidden anatomy, sleeve
underside, underarm, or pelt overlap pixels are fabricated by this package.

## Boundaries

`app.py`, shared shell files, DB/payment code, Shop/Loadout authority, Zone 3,
combat, and Production are unchanged. The legacy flat wearable renderer is
not modified or promoted as skeletal proof. `OWNER_VISUAL_ACCEPTANCE` remains
`PENDING`.
