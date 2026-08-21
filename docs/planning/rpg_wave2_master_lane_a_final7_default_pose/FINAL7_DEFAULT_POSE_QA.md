# Final7 Default Pose — Master Lane A QA

## Production candidate

The seven identities were converted from the Owner-approved Final7 identity
directions into a single player-character presentation family. The pack keeps
the canonical IDs unchanged and leaves runtime registration untouched.

| Character | Identity retained | Silhouette | Mobile read | Status |
| --- | --- | --- | --- | --- |
| `river_wayfinder` | Option B river/travel identity | hood + water-trim cape + satchel | pass | owner review |
| `stone_caretaker` | Option A stone/village identity | broad wrap tunic + bead strand | pass | owner review |
| `duelist_scout` | Option B agile scout identity | high collar + asymmetric rust panel | pass | owner review |
| `bastion_warden` | Option A calm defensive identity | blue cape + cream panels | pass | owner review |
| `forest_pathfinder` | Option B forest identity | hood + layered leaf shoulders | pass | owner review |
| `archive_scholar` | Option A scholar identity | glasses + archive layers | pass | owner review |
| `worldkeeper` | Option A civic steward identity | blue/gold cape panels | pass | owner review |

## Frame contract

```text
MASTER_CANVAS=1056x1408 RGBA
SOURCE_MASTER=PNG
RUNTIME_DERIVATIVE=WebP
FOOT_BASELINE=y=.975 (pixel y=1373)
VISIBLE_TOP=pixel y=49
TRUE_ALPHA=YES
FUNCTIONAL_WEAPON_BAKED_IN_BASE_ART=NO
CHARACTER_COMBAT_AUTHORITY=NO
RUNTIME_REGISTRATION=UNCHANGED
```

The generated RGB provenance inputs contained a checkerboard matte. The
packaging helper removes only edge-connected checkerboard pixels, attenuates
bright neutral boundary pixels, and then normalizes the visible body to the
same baseline and height used by the approved P1 masters. The PNG and WebP
derivatives were re-opened after writing and measured as RGBA.

## Owner gate

`FINAL7_DEFAULT_POSE_OWNER_PASS=NOT_PRESENT`

This package is a production candidate and review artifact. It does not
register the seven characters or claim runtime/gameplay availability before
Owner visual acceptance.
