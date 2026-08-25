# A030-R2 — Bright Adventure Canonical Palette Lock

Status: Owner-selected design-token closure; ready for final A030 review
Source structure: `b20ed61f5ca3bce5d6a98b5ce046bdfe5b0d4e51`
A030-R1 comparison: `71150b2f067af3b017b995bbc98c351edb0bda9d`
Current canonical master at branch start: `7c30a44867501ef936f84a41f2b25032c186f367`

## Decision

`BRIGHT_ADVENTURE` is the only canonical palette for RPG Art System V1.

| Candidate | Status |
| --- | --- |
| A — Bright Adventure | OWNER_SELECTED / CANONICAL |
| B — Colorful Fantasy | NOT_SELECTED / historical evidence only |
| C — Warm Storybook | NOT_SELECTED / historical evidence only |

No new palette exploration is part of R2. The accepted A030 layout,
information hierarchy, Go-board prominence, responsive order, rarity meaning
and authority boundaries remain unchanged.

## Canonical color roles

| Role | Token |
| --- | --- |
| Adventure Blue | `#1E6FC7` |
| Go Odyssey Teal | `#39C9B6` |
| Sun Yellow | `#F6C957` |
| Adventure Orange | `#F29B52` |
| Cream | `#FFF4D8` |
| Sky | `#DDF2FF` |
| Growth Green | `#72C96B` |
| Magic Purple | `#8968D8` |
| Deep Navy | `#173653` |

Target balance is approximately 65–75% light/world/colorful surfaces and
25–35% dark structural chrome. Deep Navy is reserved for navigation, headers,
HUD rails, contrast and high-stakes moments. Gold/Sun Yellow is special:
Legendary, milestone, special reward, Boss accent and important high-value
selection—not the default outline for every panel.

## Game-world contract

`GAME_WORLD_FIRST=YES`. Bright Adventure is not a white dashboard direction.
Existing E10 world art, Zone/environment color, Hero, Spirit, Monster art and
material/FX remain visible; light surfaces frame the game world rather than
replacing it. `WHITE_DASHBOARD_DIRECTION=REJECTED`.

## Surface lock

- Equipment/Backpack: light/sky Hero surface, blue selection, teal primary CTA,
  yellow `NEW`, cream selected detail and clear functional-vs-cosmetic states.
- Combat: warm wood Go board remains dominant; Hero framing is bright/friendly;
  Monster/Battlefield Boss may use environment color and heavier contrast;
  Battlefield Boss remains distinct from Lord Trial.
- Reward: bright positive success state; Coins/XP are secondary; Equipment
  rarity receives focal weight; reveal is deterministic and non-gacha.
- Shop: merchant/world environment remains visible; utility, cosmetic, Premium
  and unavailable offers remain semantically distinct; real item art is a
  later production dependency.

## Final art production boundary

R2 does not create final item icons. Weapon, armor, accessory, consumable,
Trophy, cosmetic, Coins and XP glyphs remain placeholders until a separate Art
Production task supplies one coherent Go Odyssey icon family. Placeholder
replacement must preserve slot, rarity, capability and authority semantics.

## Evidence

The final A-only contact sheet is generated outside the repository:

`D:\go-odyssey-evidence\a030-r2-bright-adventure-canonical-20260825-001\A030_R2_BRIGHT_ADVENTURE_CANONICAL.png`

Mobile color checks:

- `07_candidate_a_equipment_mobile.png`
- `08_candidate_a_combat_mobile.png`

Historical A/B/C comparison evidence remains in the A030-R1 packet, now
explicitly labeled A selected and B/C not selected.

## Hard boundary

This closure changes docs/design tokens and review evidence only. It does not
change `app.py`, runtime HTML/JS, service worker, schema, database, assets,
commerce, payment, gameplay, World authority, Spirit mechanics, Boss/Lord
authority or Production.
