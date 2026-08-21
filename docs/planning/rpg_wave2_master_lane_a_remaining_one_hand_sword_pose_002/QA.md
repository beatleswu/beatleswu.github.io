# Lane A remaining ONE_HAND_SWORD_POSE production candidate QA

Task: `GO_ODYSSEY_MASTER_LANE_A_REMAINING_ONE_HAND_SWORD_POSE_002`

## Scope

This pack contains exactly fourteen new full-body presentation candidates:

`apprentice_girl`, `swordsman`, `rogue`, `ranger`, `berserker`, `guardian`,
`sage`, `river_wayfinder`, `stone_caretaker`, `duelist_scout`,
`bastion_warden`, `forest_pathfinder`, `archive_scholar`, `worldkeeper`.

The six existing Owner-approved variants are review references only and were
byte-checked against the production base. No approved variant was regenerated
or changed.

## Dependency and authority evidence

- Production baseline: `c36ce33763c80de7313922ad4096331ded540c18`
- Final7 Default Pose dependency: `546fce85e27f1a6dbbdbf983e6374950f8df44a6`
- Sword Pose x Armor dependency: `1be5d9523ffd9cc874081d343efc0e4bfa69fa1d`
- Pose method: `FULL_BODY_REDRAW`
- Pose family: `ONE_HAND_SWORD_POSE`
- Functional equipment authority: `player_inventory + server EQUIPMENT_DEFS`
- Character combat authority: `NO`
- Client combat authority: `NO`
- Local hand patch: `NO`
- Local forearm patch: `NO`
- Runtime implementation: `NO`

The art depicts a generic one-handed sword presentation. It does not register
an item, grant ownership, select equipment, or change combat.

## Production asset contract

Each candidate has:

- master PNG: 1056x1408 RGBA;
- true alpha with transparent frame corners;
- foreground baseline normalized to y=1373 (`.975` of the 1408px frame);
- lossless WebP derivative at the same dimensions;
- full-body redraw provenance to the Owner-approved Default Pose identity.

## Self-QA result

- New candidates: `14/14` present.
- Source closure: `14/14`.
- PNG master closure: `14/14`.
- WebP derivative closure: `14/14`.
- Dimension/color-mode checks: `14/14`.
- Alpha integrity checks: `14/14`.
- Duplicate candidate IDs: `0`.
- Duplicate canonical asset paths: `0`.
- Existing six approved variants changed: `0`.
- Local hand/forearm patches: `0`.
- Armor architecture regressions introduced: `0`.
- Meaningful player-family drift introduced by this batch: `0`.

The full-roster lineup is intentionally included for Owner visual comparison;
the six already approved poses remain the comparison authority. Agent QA does
not grant Owner PASS. The Sword Pose gate remains `6/20` until explicit Owner
approval.

## Review artifacts

- `matrices/REMAINING14_ONE_HAND_SWORD_POSE_MATRIX.png`
- `matrices/REMAINING14_ONE_HAND_SWORD_POSE_MOBILE_MATRIX.png`
- `matrices/ALL20_ONE_HAND_SWORD_POSE_SCALE_LINEUP.png`
