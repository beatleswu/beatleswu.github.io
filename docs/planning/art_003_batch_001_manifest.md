# ART003 B01 R1 Targeted Visual Revision Manifest

Task: `ART003_B01_R1_TARGETED_VISUAL_REVISION_AND_PASSSET_FREEZE_001`

Parent ART003 B01 head: `fb59e554a5daf2849a7f15f9467ff572d6138397`

Status: `PASS_ART003_B01_R1_TARGETED_REVISION_READY_FOR_OWNER_REVIEW`

The Owner-locked Monster Style System remains unchanged. ART003 B01 R1 freezes the eight explicit Owner-PASS assets and revises only M008 and M010. The ART002 candidate roster, Zone distribution, runtime IDs and gameplay authority remain unchanged.

## Scope and status

- Batch target: 10 normal Monsters.
- Owner-PASS frozen: 8/8 (`M002-M007`, `M009`, `M012`).
- Targeted R1 revision candidates: 2/2 (`M008`, `M010`).
- Owner-approved new art: 8/10.
- Canonical assets promoted in this task: 0/10.
- Runtime-mapped new art: 0/10.
- Technical QA: 10/10; M008 and M010 are `R1_TECH_PASS` and remain Owner-review pending.
- Authorized asset replacements: 2 (`M008`, `M010`); frozen pass-set pixel mutations: 0.
- Runtime, `app.py`, roster, Zone distribution, gameplay numbers, Boss, Lord and Spirit identities: unchanged.

`OWNER_VISUAL_STATUS=PASS` is an explicit Owner decision for the eight frozen items. `R1_TECH_PASS` means the revised candidate passed file-level and visual-brief checks; it is not Owner approval, canonical promotion, runtime integration or final cross-surface QA.

The ten supplied JPGs were used only as style references. Their card text, statistics, skill panels, names and UI were not copied or treated as roster authority.

## Pass-set freeze

| M-ID | Asset | Owner status | SHA-256 |
|---|---|---|---|
| M002 | `art/monsters/M002_gate_sprout.png` | PASS / FROZEN | `49B8F04D137EC101ED4B9BFE1ADB2B4E47139D43C96C5629038D874D0DCB8E89` |
| M003 | `art/monsters/M003_barrel_bouncer.png` | PASS / FROZEN | `9F7C63F0B0B8A12DE117E7AB4D270B8ABB9D95A4725A2DE719CA766CAAB55706` |
| M004 | `art/monsters/M004_strawhat_mole.png` | PASS / FROZEN | `C5E3B33416E9B4AD4CA039A02F293856718EA996E78B4158CAE1FEC67333D2D3` |
| M005 | `art/monsters/M005_chime_chick.png` | PASS / FROZEN | `F243D7B6CBB926379C9B44305C49AFA31CCF1E1FF9545A0A9DB06752C41B3B16` |
| M006 | `art/monsters/M006_pebble_beetle.png` | PASS / FROZEN | `4C72B3B2D5ED3022B3E352FE453A19D395511C91B0A73187257E7ED7C86AF2B9` |
| M007 | `art/monsters/M007_well_bubble.png` | PASS / FROZEN | `06D217B0156F93144244ED93CD50872CA959450B14CF861E19DF67B0E1C78B44` |
| M009 | `art/monsters/M009_signpost_fox.png` | PASS / FROZEN | `49BE99FC1823D6C7E1EAB110A47BB26A14716B077AF61C37BE8EA68BCEF49038` |
| M012 | `art/monsters/M012_mudball_otter.png` | PASS / FROZEN | `8CB0DE9AC6075552EE8075A8A5EB04AE494B49134D205C1E9BB982C4C3FAC473` |

`OWNER_PASSSET_FREEZE_COUNT=8`; `PASSSET_PIXEL_MUTATIONS=0`; `PASSSET_ID_RENAMES=0`; `PASSSET_REGENERATION=0`; `PASSSET_MAPPING_CHANGE=0`.

## R1 revision candidates

| M-ID | ZH / EN | Zone | Asset | Revision scope | File QA | Owner review |
|---|---|---|---|---|---|---|
| M008 | 稻田蹦蹦 / Paddy Hopper | Z1 新手村 | `art/monsters/M008_paddy_hopper.png` | STRUCTURAL_VISUAL_CLARITY_ONLY; clear biological hind legs; no spring/rope joints | PNG RGBA; 1122×1402; alpha corners 0; complete bbox | PENDING |
| M010 | 糰子地精 / Dumpling Gnome | Z1 新手村 | `art/monsters/M010_dumpling_gnome.png` | NPC_TO_MONSTER_VISUAL_LANGUAGE_CORRECTION; integrated dumpling body; no chef cues | PNG RGBA; 1024×1536; alpha corners 0; complete bbox | PENDING |

## Owner gate

Owner must review only M008 and M010 for the targeted revisions. Do not self-approve either image. Neither revised image is canonical or runtime-wired by this task. No ART003 B02 work starts automatically.
