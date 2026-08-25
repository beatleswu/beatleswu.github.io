# A030-R1 RPG Art System Color Direction Closure

## Decision scope

This is a color-only revision of the Owner-accepted A030 pre-production
structure at b20ed61f5ca3bce5d6a98b5ce046bdfe5b0d4e51. The current canonical
master at the start of the revision is
7c30a44867501ef936f84a41f2b25032c186f367, which is the parent of the accepted
A030 structure.

The accepted surface composition, information hierarchy, Go-board prominence,
responsive order, rarity semantics and authority boundaries remain unchanged.
The R1 package only compares three color directions and records the visual
rules needed for the next Owner decision.

## Owner review target

The current A030 deep-teal / antique-gold / parchment balance is structurally
sound but too dark and mature for a 6–12-year-old adventure RPG. R1 shifts the
visual center toward bright, colorful, open and friendly surfaces while keeping
dark chrome for hierarchy, contrast, navigation and Boss moments.

Target surface balance:

- Light, world and colorful surfaces: 65–75%
- Dark structural chrome: 25–35%

Gold is no longer the default outline. It is reserved for Legendary, major
milestones, Boss accents, special rewards and important selected moments.

## Three candidates

### A — Bright Adventure (recommended)

Open sky, adventure blue, Go Odyssey teal, sun yellow and cream create a
clear entry point for children. Deep navy remains a structural anchor rather
than a full-card default. Candidate A is the primary owner-decision evidence.

### B — Colorful Fantasy

Blue, violet, teal, coral and warm yellow emphasize Spirit/magic identity.
The palette remains light and controlled rather than neon. It is a credible
alternative if the Owner wants more overt magical flavor.

### C — Warm Storybook

Cream, sky, grass green, warm orange and soft gold create a friendly
illustrated-adventure-book mood. It is younger and warmer, but still uses
strong structural chrome and clear RPG state geometry so it does not become
preschool styling.

Machine-readable values are in
a030_r1_rpg_color_tokens.json. The renderable evidence board is
a030_r1_palette_comparison_board.html.

## Cross-surface color contract

### Equipment and Backpack

The Hero area uses a light or sky-toned surface; the selected-item detail uses
cream for reading; functional slots use slot geometry and a blue selection
edge; the primary action is teal; NEW is warm yellow. Functional Equipment
and pure cosmetics remain semantically distinct. No color change grants an
effect, ownership, equip capability or authority.

### Combat

The Go board keeps its warm wood and remains the dominant interaction. The
Hero side becomes brighter and friendlier. The Monster side may inherit the
Zone/environment color. A Battlefield Boss may be darker/heavier, creating
contrast between normal adventure and danger instead of making the whole game
feel like Boss mode.

### Reward

Light surfaces, sky color and sun yellow make success feel like victory,
discovery and progress. Rare Equipment receives more visual emphasis than
Coins/XP utility cards. The reward remains deterministic and non-gacha.

### Shop

The merchant/world environment remains visible. Offer type leads before price
and metadata. Utility, cosmetic, Premium and unavailable states remain
distinct. Pure cosmetics do not receive Attack, Defense or XP language.

## Rarity language

Rarity uses color plus label, symbol and geometry:

| Rarity | Color role | Symbol | Geometry |
| --- | --- | --- | --- |
| Common | neutral light gray-blue | ○ | single quiet frame |
| Uncommon | growth green | ◆ | green inset marker |
| Rare | adventure blue | ◇ | double blue edge |
| Epic | magic purple | ✦ | violet crest |
| Legendary | special gold | ✹ | gold crest and reveal rim |

Gold is deliberately concentrated in Legendary and milestone moments so that
it becomes meaningful again.

## Evidence packet

The board is renderable from local repository assets and keeps the accepted
A030 composition. The Owner review evidence is generated outside the repo:

- 01_equipment_palette_comparison.png
- 02_candidate_a_equipment.png
- 03_candidate_a_combat.png
- 04_candidate_a_reward.png
- 05_candidate_a_shop.png
- 06_palette_contact_sheet.png

## Boundaries

This package does not modify app.py, runtime HTML/JS, service worker,
schema, database, assets, commerce, gameplay, Spirit authority, World
authority, Boss/Lord authority or Production. It does not produce final item
icons or final art. Existing glyph placeholders remain allowed for this
palette-only decision.

## Recommendation

Use Candidate A as the default direction for the next visual pass, subject to
Owner selection. Do not promote a palette to runtime until the Owner selects
one candidate and a separate implementation task authorizes the change.
