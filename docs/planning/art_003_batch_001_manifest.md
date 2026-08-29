# ART003 B01 R2 Owner-PASS Freeze and Canonical Art Publication Manifest

Task: `ART003_B01_R2_OWNER_PASS_FREEZE_AND_CANONICAL_ART_PUBLICATION_001`

B01-R1 HEAD: `2c25f2f423f672023a919abaf35f6c975bcf3d65`

Status: `PASS_ART003_B01_OWNER_PASS_FREEZE_AND_CANONICAL_ART_PUBLICATION`

The Owner explicitly accepted both R1 revisions in the ART003 B01-R2 task: `M008_OWNER_VISUAL_REVIEW=PASS` and `M010_OWNER_VISUAL_REVIEW=PASS`. Together with the eight previously accepted assets, all ten B01 images are now frozen as Owner-approved canonical production art. The ART002 roster, Zone distribution, runtime IDs, runtime mapping and gameplay authority remain unchanged.

## Scope and status

- Batch target: 10 normal Monsters: `M002-M010` and `M012`.
- Owner-PASS freeze: 10/10.
- R1 revision candidates remaining: 0/2; M008 and M010 are accepted.
- Owner-approved new art: 10/10.
- Canonical B01 production art: 10/10.
- Runtime-mapped new art: 0/10; canonical art publication does not grant runtime authority.
- Technical QA: 10/10; all sources are readable PNG RGBA with transparent alpha and unique SHA-256 values.
- Final visual QA status: 10/10 `PASS` under the Owner-approved B01 asset gate.
- Artwork pixels, filenames and IDs were not changed in R2: `ART_PIXEL_MUTATIONS=0`, `ART_REGENERATION=0`, `ART_ID_RENAMES=0`.
- `app.py`, runtime source, static runtime wiring, roster, Zone mapping, gameplay numbers, Boss, Lord and Spirit identities: unchanged.

For this manifest, `CANONICAL` means Owner-approved production-art identity. It does not mean runtime-mapped, gameplay-authoritative, merged to `master` or deployed. The explicit Owner decision is the acceptance evidence for M008 and M010 in the R2 task; the eight earlier PASS decisions remain frozen and byte-identical.

The ten supplied JPGs remain style references only. Their card text, statistics, skill panels, names and UI are not roster or gameplay authority.

## Frozen B01 production-art set

| M-ID | Asset | Owner visual status | Final visual QA | Canonical | SHA-256 |
|---|---|---|---|---|---|
| M002 | `art/monsters/M002_gate_sprout.png` | PASS | PASS | YES | `49B8F04D137EC101ED4B9BFE1ADB2B4E47139D43C96C5629038D874D0DCB8E89` |
| M003 | `art/monsters/M003_barrel_bouncer.png` | PASS | PASS | YES | `9F7C63F0B0B8A12DE117E7AB4D270B8ABB9D95A4725A2DE719CA766CAAB55706` |
| M004 | `art/monsters/M004_strawhat_mole.png` | PASS | PASS | YES | `C5E3B33416E9B4AD4CA039A02F293856718EA996E78B4158CAE1FEC67333D2D3` |
| M005 | `art/monsters/M005_chime_chick.png` | PASS | PASS | YES | `F243D7B6CBB926379C9B44305C49AFA31CCF1E1FF9545A0A9DB06752C41B3B16` |
| M006 | `art/monsters/M006_pebble_beetle.png` | PASS | PASS | YES | `4C72B3B2D5ED3022B3E352FE453A19D395511C91B0A73187257E7ED7C86AF2B9` |
| M007 | `art/monsters/M007_well_bubble.png` | PASS | PASS | YES | `06D217B0156F93144244ED93CD50872CA959450B14CF861E19DF67B0E1C78B44` |
| M008 | `art/monsters/M008_paddy_hopper.png` | PASS | PASS | YES | `12463A8C63C99E92C35E1CCEEE6E145C55079DBB7570C2C6EFBD7EBA56AC4C85` |
| M009 | `art/monsters/M009_signpost_fox.png` | PASS | PASS | YES | `49BE99FC1823D6C7E1EAB110A47BB26A14716B077AF61C37BE8EA68BCEF49038` |
| M010 | `art/monsters/M010_dumpling_gnome.png` | PASS | PASS | YES | `3F65FAFD0FC9DCDF7EF12DFE6C9299829F0585D91B7922429C205859AE63D342` |
| M012 | `art/monsters/M012_mudball_otter.png` | PASS | PASS | YES | `8CB0DE9AC6075552EE8075A8A5EB04AE494B49134D205C1E9BB982C4C3FAC473` |

## R2 boundaries

`OWNER_PASSSET_FREEZE_COUNT=10`; `ART_PIXEL_MUTATIONS=0`; `ART_REGENERATION=0`; `ART_ID_RENAMES=0`; `RUNTIME_MAPPED_NEW_ART=0`.

`F033_SCOPE_TOUCHED=NO`; `F034_SCOPE_TOUCHED=NO`; `M_ID_ZONE_MAPPING_CHANGED=NO`; `E045_SCOPE_TOUCHED=NO`; `COMBAT_PROFILE_MAPPING_CHANGED=NO`; `GAMEPLAY_AUTHORITY_CHANGED=NO`.

No B02 work starts automatically. The next art step is `READY_FOR_ART003_B02=YES` after this publication is reviewed by the coordinator; no runtime wiring is implied.
