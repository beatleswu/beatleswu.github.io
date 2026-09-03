# W1-05 Zone 3 Owner-approved ten-shot asset acceptance

Task: `W1_05_QUALITY_ZONE3_OWNER_APPROVED_10SHOT_ASSET_ACCEPTANCE_004`

This is source-art acceptance only. No art was edited, copied into the
runtime, regenerated, redrawn, or replaced. Final runtime integration and
physical-device acceptance remain separate later gates.

## Identity and WORLD cross-check

- Package: `ZONE3_FINAL_10SHOT_OWNER_APPROVED.zip`
- Package SHA-256: `b3aa7e3e4d0d06c294d8f30eb3a05f5e9c5375721bbf4a4e16ccd6a1134ed1b8`
- Package size: `9,907,226` bytes
- Source entries: exactly 10, `SHOT01` through `SHOT10`, each once
- Rejected asset paths: none
- WORLD candidate: `39c587a216f6cc13efe572066d9d8f0299960f1b`
- WORLD tree: `676da3ddd4456b83aaa591e830a7adf4dab5c161`
- Cross-check: every package source byte stream, byte count, SHA-256, and
  dimension matches the corresponding WORLD `CINEMATIC_SHOT` source entry.

SHOT07 and SHOT08 are the package's final revised versions. The ZIP contains
no earlier rejected variants.

## Source inventory and technical acceptance

All ten images independently decoded and loaded successfully. No material
corruption, unusable resolution, severe compression defect, broken major
object, unreadable face, duplicate major body part, or baked text was found at
normal gameplay presentation size.

| Shot | Filename | Bytes | SHA-256 | Dimensions | Aspect | Decode |
|---|---|---:|---|---|---:|---|
| SHOT01 | `zone3_shot01_moving_refugees_owner_approved.jpeg` | 545655 | `381d94c09d1d37d921c461e3f6c80b9a37ba92ed0d63581e9015ac53440e470f` | 1536x864 | 1.777778 | PASS |
| SHOT02 | `zone3_shot02_household_belongings_owner_approved.jpeg` | 663920 | `f2af78399c1603ba1df453f5efb9df22f344999d9fe6721ebeb418527155bbc0` | 1536x1024 | 1.500000 | PASS |
| SHOT03 | `zone3_shot03_meet_grik_owner_approved.jpeg` | 621107 | `e7c08c827f213b3adc9db24ce419282d747cbfd7ee2ca08fbf2c4cfd32dad1a2` | 1536x1024 | 1.500000 | PASS |
| SHOT04 | `zone3_shot04_shrinking_living_space_owner_approved.jpeg` | 591629 | `bd4f1b818e49aa976a20cd82c5d48fef77c569c70ba23e4407942b50adb85a67` | 1536x1024 | 1.500000 | PASS |
| SHOT05 | `zone3_shot05_blocked_water_route_owner_approved.jpeg` | 711516 | `f7261e5f42545327bb5960aec2d38f049ffba0cb94c11d405e2f2ac81d2d4f4f` | 1536x864 | 1.777778 | PASS |
| SHOT06 | `zone3_shot06_last_door_centurion_owner_approved.jpeg` | 619999 | `9309ba5bd565007a30666a018c904321df43d64baeeee3ac0286016dd4a8ab15` | 1536x1024 | 1.500000 | PASS |
| SHOT07 | `zone3_shot07_lord_trial_challenge_owner_approved.png` | 2545852 | `e861ef571c3b46ba7e8b93839da472a390ee8a9a25784cf860564a1c1627950f` | 1672x941 | 1.776833 | PASS |
| SHOT08 | `zone3_shot08_fragile_truce_owner_approved.png` | 2527541 | `ffecac99714b6f936df6e95aaccd4287f64bda73eeedf224bdcb7e93641edab2` | 1536x1024 | 1.500000 | PASS |
| SHOT09 | `zone3_shot09_stone_shard_handoff_owner_approved.jpeg` | 557654 | `573e29b1176182705847dfbf89dc1cceff686567187a6514f6e8fe213b861344` | 1536x1024 | 1.500000 | PASS |
| SHOT10 | `zone3_shot10_mist_forest_hook_owner_approved.jpeg` | 569654 | `06b276012e83971631a8ac352ba07325938bb06f61be3a49f6050314084e6646` | 1536x1024 | 1.500000 | PASS |

## Story, child readability, and continuity review

The primary action, relationship, cause/effect focus, and story focus are
clear for an elementary-school audience in every frame. Dialogue remains the
source for detailed motivation and emotional nuance; no required text is
inside the art.

Across SHOT01–SHOT10: `PRIMARY_ACTION_CLEAR=PASS`,
`CHARACTER_RELATION_CLEAR=PASS`, `CAUSE_EFFECT_CLEAR=PASS`,
`STORY_FOCUS_CLEAR=PASS`, and `TEXT_REQUIRED_TO_UNDERSTAND_BASIC_ACTION=NO`.

| Shot | Story function | Child readability | Hero | Shui | Grik | Centurion |
|---|---|---|---|---|---|---|
| SHOT01 | PASS — families move deeper into the cave | PASS | PASS | PASS | N/A | N/A |
| SHOT02 | PASS — blankets, pots, toys, and household bundles read as belongings | PASS | PASS | PASS | N/A | N/A |
| SHOT03 | PASS — open hands and distance read as peaceful first contact | PASS | PASS | PASS | PASS | N/A |
| SHOT04 | PASS — Grik points while the occupied cave visibly narrows around the group | PASS | PASS | PASS | PASS | N/A |
| SHOT05 | PASS — rockfall blocks the visible water route and the bucket reinforces the need | PASS | PASS | PASS | PASS | N/A |
| SHOT06 | PASS — Centurion forms the last protective door with families behind him | PASS | PASS | PASS | N/A | PASS |
| SHOT07 | PASS — Centurion's armed challenge clearly precedes the Lord Trial | PASS | PASS | PASS | N/A | PASS |
| SHOT08 | PASS — belongings are down, children rest, and the Centurion remains guarded | PASS | PASS | PASS | PASS | PASS |
| SHOT09 | PASS — Grik hands Hero a small ordinary shard | PASS | PASS | PASS | PASS | N/A |
| SHOT10 | PASS — Grik points from the cave toward the mist-covered forest | PASS | PASS | PASS | PASS | N/A |

## Final ten-row acceptance matrix

`IPAD` and `MOBILE` are asset-presentation passes: the manifest supplies
full-frame contain where a portrait cover crop is not safe, and reviewed
custom positioning for SHOT09–SHOT10. They are not physical-device passes.

| SHOT | STORY | CHILD_READABILITY | HERO_CONTINUITY | SHUI_CONTINUITY | GRIK_CONTINUITY | CENTURION_CONTINUITY | TECHNICAL | DESKTOP | IPAD_LANDSCAPE | IPAD_PORTRAIT | MOBILE | OVERALL |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SHOT01 | PASS | PASS | PASS | PASS | N/A | N/A | PASS | PASS | PASS | PASS | PASS | PASS |
| SHOT02 | PASS | PASS | PASS | PASS | N/A | N/A | PASS | PASS | PASS | PASS | PASS | PASS |
| SHOT03 | PASS | PASS | PASS | PASS | PASS | N/A | PASS | PASS | PASS | PASS | PASS | PASS |
| SHOT04 | PASS | PASS | PASS | PASS | PASS | N/A | PASS | PASS | PASS | PASS | PASS | PASS |
| SHOT05 | PASS | PASS | PASS | PASS | PASS | N/A | PASS | PASS | PASS | PASS | PASS | PASS |
| SHOT06 | PASS | PASS | PASS | PASS | N/A | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| SHOT07 | PASS | PASS | PASS | PASS | N/A | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| SHOT08 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| SHOT09 | PASS | PASS | PASS | PASS | PASS | N/A | PASS | PASS | PASS | PASS | PASS | PASS |
| SHOT10 | PASS | PASS | PASS | PASS | PASS | N/A | PASS | PASS | PASS | PASS | PASS | PASS |

Global continuity: HERO `PASS`; SHUI `PASS`; GRIK `PASS`; CENTURION `PASS`.
Hero retains the dark tousled hair, blue tunic, brown strap, and pendant.
Shui remains a small translucent blue juvenile spirit with no horn and a
circular yin-yang-like chest core. Grik remains a young, slim, tired/guarded
goblin rather than an elder or Centurion. The Centurion remains seasoned,
weathered, protective, dignified, larger than Grik, and non-demonic across
SHOT06–SHOT08.

SHOT08 passes `FRAGILE_TRUCE`: the group is settled and children can rest, but
the Centurion remains watchful and the image does not present a celebratory
reconciliation.

## Stone Shard and text/UI separation

`STONE_SHARD_VISUAL_CONTRACT=PASS`. In SHOT09 the shard is small, irregular,
ordinary, non-glowing, and marked naturally; it is not a map, rune artifact,
or legendary item.

`CENTURION_VISUAL_CONTRACT=PASS`. SHOT06–SHOT08 preserve the same seasoned,
weathered, protective, dignified, larger-than-Grik Centurion. He is not
demonic or presented as berserker spectacle.

`TEXT_BAKED_INTO_ART_COUNT=0`
`RUNTIME_BUTTON_BAKED_INTO_ART_COUNT=0`
`REWARD_BAKED_INTO_ART_COUNT=0`
`ZONE_STATE_BAKED_INTO_ART_COUNT=0`

The markings on the SHOT04 prop map are environmental story-prop marks, not
runtime text/UI. Runtime state, route, reward, and CTA remain outside the
source frames.

## Responsive acceptance contract

The committed WORLD/JOURNEY binding provides a classified row for all 10
shots. This is a presentation contract, not physical-device evidence.

| Shot | Desktop | iPad landscape | iPad portrait | Mobile portrait | Focal subject safe | Subtitle safe area |
|---|---|---|---|---|---|---|
| SHOT01 | cover 50% 50% | cover 50% 50% | contain 50% 50% | contain 50% 50% | full frame retains Hero, Shui, route, and moving families | shared runtime shell bottom safe-area inset |
| SHOT02 | cover 50% 54% | cover 50% 54% | contain 50% 54% | contain 52% 56% | full frame retains Hero, belongings, Shui, and family; optional mobile focus is down | shared runtime shell bottom safe-area inset |
| SHOT03 | cover 50% 50% | cover 50% 50% | contain 50% 50% | contain 58% 50% | full frame retains Hero/Shui, route, and Grik; optional Grik focus only | shared runtime shell bottom safe-area inset |
| SHOT04 | cover 50% 50% | cover 50% 50% | contain 50% 50% | contain 58% 50% | full frame retains speakers, occupied space, and explanation gesture | shared runtime shell bottom safe-area inset |
| SHOT05 | cover 50% 50% | cover 50% 50% | contain 50% 50% | contain 67% 50% | full frame retains people, rockfall, and unreachable water | shared runtime shell bottom safe-area inset |
| SHOT06 | cover 50% 50% | cover 50% 50% | contain 50% 50% | contain 58% 50% | full frame retains Hero/Shui, doorway, Centurion, and families | shared runtime shell bottom safe-area inset |
| SHOT07 | cover 50% 50% | cover 50% 50% | contain 50% 50% | contain 55% 50% | full frame retains the confrontation, trial space, and families | shared runtime shell bottom safe-area inset |
| SHOT08 | cover 50% 50% | cover 50% 50% | contain 50% 50% | contain 60% 52% | full frame retains truce group, resting families, and belongings | shared runtime shell bottom safe-area inset |
| SHOT09 | cover 50% 50% | cover 50% 50% | cover 58% 50% | cover 58% 50% | custom position retains Hero, Grik, and ordinary shard; Shui is optional context | shared runtime shell bottom safe-area inset |
| SHOT10 | cover 50% 50% | cover 50% 50% | cover 58% 50% | cover 58% 50% | custom position retains Hero, pointing Grik, and mist hook | shared runtime shell bottom safe-area inset |

Coverage and counts:

- `RESPONSIVE_CLASSIFICATION_COVERAGE=10/10`
- Desktop safe: `10/10`
- iPad landscape safe: `10/10`
- iPad portrait acceptable: `10/10` (`8` contain, `2` custom position)
- Mobile portrait acceptable: `10/10` (`8` contain, `2` custom position)
- Portrait generic crop safe: `2/10` for both iPad and mobile; the other eight
  are deliberately supported with full-frame contain, not falsely called
  generic crop-safe.

The Journey binding's portrait subtitle container uses the runtime shell's
left/right and bottom safe-area insets and a bounded scrollable height. That
is a shell presentation contract, not text baked into any source image.

## Bounded validation

Targeted command, with the supplied attachment path in
`W1_05_OWNER_PACKAGE_PATH`:

```text
pytest -q tests/test_w1_05_quality_zone3_owner_approved_10shot_asset_acceptance.py
```

The gate covers package identity, exact sequence/no duplicates, all ten
source metadata/decode checks, byte-for-byte WORLD source identity, the full
responsive row count, and manifest text/UI/Stone Shard guards. Manual visual
review covers story function, elementary-school readability, character
continuity, and material image defects.

## Boundary

`PHYSICAL_DEVICE_ACCEPTANCE=NOT_PERFORMED`.

This closes source-art acceptance only. It does not claim final runtime
integration, real iPad/mobile hardware acceptance, animation/audio playback,
or Production readiness.
