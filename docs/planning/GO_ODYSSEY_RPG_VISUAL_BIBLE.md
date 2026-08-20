# GO ODYSSEY RPG VISUAL BIBLE

## Character System Section v1

Status: PROPOSAL_FOR_OWNER_GATE1
Scope: Wave 2 Lane A character production foundation
Base: origin/master a82b0d99e0b413d9cd55dac4e86ef5c5140351e6

This section establishes the shared character-art contract for player appearances and world
characters. It is a specification only. It does not change runtime assets, renderers, APIs, combat,
ownership, Premium, database schema, or Production.

## 1. Precedence and relationship to existing bibles

1. The E10 Newbie Village Art Direction Bible remains authoritative for Zone 1-specific Hero,
   Village Elder, Water Spirit Horse, village, and scene decisions.
2. Any separately approved E10 cross-zone visual identity document remains authoritative for shared
   cross-zone Go visual language and energy behavior.
3. This section owns the Wave 2 character production contract: player appearance identity, world NPC
   identity, base-art export, character anchors, and collection presentation.
4. The screenplay owns story canon. A production concept cannot rewrite a story role.
5. Lane B owns functional equipment and Backpack. Lane C owns item, collection, and shop economy
   presentation. Character artwork cannot cross those authority boundaries.

## 2. Character categories

The following categories are separate:

| Category | Meaning | Selectable by player | Gameplay authority |
|---|---|---:|---|
| PLAYER_CHARACTER_APPEARANCE | Player-selected body, face, hair, and base visual identity | Yes | None |
| WORLD_CHARACTER_NPC | Elder, messenger, guide, merchant, companion, or Zone story character | No | Story/presentation only |
| MONSTER_ENEMY | Battlefield enemy or boss encounter entity | No | Server encounter authority, never character collection authority |
| OUTFIT_COSMETIC | Visual layer worn by a player appearance | No, equipped visually | No attack/defense authority |
| FUNCTIONAL_EQUIPMENT | Weapon, armor, accessory, or other gameplay item | Equipped separately | Server-owned functional authority |

Names such as Warrior, Mage, Knight, and Sage are collection families or visual roles. They are
not combat classes unless a future product decision explicitly authorizes a separate class system.

## 3. Master canvas and export contract

~~~
MASTER_CANVAS=1056x1408
SOURCE_FORMAT=PNG master
RUNTIME_FORMAT=WebP
COLOR_MODE=RGBA
ALPHA_POLICY=true alpha; no chroma-key matte
~~~

- The visible body uses a shared target frame of x=.20–.80 and y=.02–.98.
- The visible foot contact is aligned to y=.975; a soft shadow may extend to y=.99.
- Transparent pixels must use neutral RGB values. Green-key RGB residue is rejected even when alpha
  is zero.
- Runtime WebP is derived from the accepted PNG master. No hand-edited runtime-only variant becomes
  the source of truth.
- Profile/card derivatives are generated from the accepted master and retain the same identity key.

## 4. Camera, pose, and body system

- Camera: frontal or near-frontal, eye-level, orthographic-feeling, with no perspective stretch.
- Default pose: stable standing pose with relaxed/open hands and clear feet.
- Base body: full-body image, consistent baseline, readable shoulder and head placement.
- Allowed variation: age, body width, height impression, skin tone, hair, and facial expression may
  vary intentionally, but not through accidental crop or scale drift.
- The artist must record any intentional silhouette exception, especially for older bodies, broader
  guardian silhouettes, or flowing robe shapes.

## 5. Face grid

- Use a shared eye, brow, nose, mouth, ear, and chin alignment guide.
- Face scale may vary for age and body identity, but eye placement and expression direction must
  remain readable at card size.
- Avoid oversized generic anime eyes, photorealistic pores, and tiny facial detail that disappears
  on mobile.
- Preserve the existing ten characters' identities during polish. A face-grid correction is not a
  license to replace a character.

## 6. Outline, shading, and lighting

### Outline

- Use a consistent dark blue-brown outline family rather than pure black.
- The contour should remain readable on both light and dark UI surfaces.
- Avoid green, white, or saturated colored edge halos.

### Shading

- Use a shared three-value cel/soft-render structure: base, controlled shadow, restrained highlight.
- Large material planes are preferred over many sub-pixel folds.
- Hair, robe, armor, skin, and cloth should remain distinguishable at mobile card size.

### Lighting

- Default key light is soft upper-left with a restrained fill.
- Face readability takes priority over costume sparkle.
- Gold, white, and magical highlights are accents, not full-image bloom.
- The Go Odyssey world can use warm village light, cool forest light, or zone-specific ambience, but
  the character's face and silhouette must remain in the common lighting family.

## 7. Palette logic

The palette is role-coded but not power-coded:

- Beginner: teal, off-white, clay beige, leather brown, muted brass.
- Warrior: slate, blue, rust, charcoal, leather brown.
- Knight/Guardian: blue-charcoal, stone grey, ivory, restrained gold.
- Ranger: forest green, bark brown, mist violet, ivory.
- Rogue: charcoal, muted violet/teal, warm grey.
- Mage: deep navy, lavender, ivory, muted brass.
- Scholar/Sage: umber, slate, parchment ivory, muted teal.

Color must not imply attack strength, defense strength, rarity, Premium entitlement, or item
ownership.

## 8. Mobile and card safe area

- Keep the face, torso, primary silhouette cue, and feet inside the default card safe area.
- Use at least 10% outer margin on the master unless a recorded silhouette exception is approved.
- At approximately 72–96px card height, the character must remain identifiable by silhouette and one
  primary palette block.
- Do not rely on tiny text, tiny weapons, tiny jewelry, or micro-patterns to identify a character.
- Selected and locked state belong to the UI layer, not inside the artwork.

## 9. Base art and visual layer contract

The canonical visual stack is:

~~~
Base Character
  → Outfit Cosmetic
  → Functional Equipment projection if supported
  → Cosmetic Style Gear
  → Aura / FX
~~~

### Base Character

Contains body, face, hair, hands, base clothing, and identity silhouette. Preferred policy is
empty/open hands. No authoritative functional weapon, armor, accessory, stat, or combat effect is
embedded in the base artwork.

### Outfit Cosmetic

Changes appearance only. Outfit art may be layered over a compatible base character and must declare
its frame/anchor compatibility. It does not grant attack or defense.

### Functional Equipment projection

May show the visual projection of an owned/equipped functional item. Its identity and effect come
from the server-owned functional equipment path, not from pixels or client-submitted display data.

### Cosmetic Style Gear

Includes visual hats, capes, accessories, pets, and other style layers. Visual presence is not
ownership or gameplay authority.

### Aura / FX

Presentation-only effects. They must not look like hidden weapon damage, defense, XP, loot, coin, or
Premium mechanics.

## 10. Weapon and prop policy

- Functional weapons are separate from player-character base art.
- Empty/open hands are the default.
- A decorative prop may appear only when it is clearly non-authoritative, documented in the asset
  record, and approved as a visual prop.
- A decorative sword, staff, shield, or book must never silently map to player_inventory.
- A functional-equipment projection must use a separate item identity and a compatible anchor.

## 11. Player character art direction

The current ten remain:

~~~
apprentice
apprentice_girl
swordsman
rogue
ranger
berserker
guardian
paladin
mage
sage
~~~

Their concepts are preserved and polished, not replaced. The first expansion adds ten candidate
identities:

~~~
trail_apprentice
river_wayfinder
stone_caretaker
duelist_scout
bastion_warden
forest_pathfinder
night_runner
constellation_apprentice
archive_scholar
worldkeeper
~~~

These IDs are candidates pending Owner display-name approval. None is a combat class.

## 12. NPC, companion, and monster relationship

### World NPCs

NPCs share the same world materials, lighting discipline, alpha cleanliness, and line-family logic,
but may use more age, body, pose, and personality variation than the player roster. They are not
registered as player character appearances.

### Water Spirit Horse

Water Spirit Horse / 小水 remains a story companion and pet-system entity, not a player body
appearance, mount, weapon, or combat class. Its canonical identity is governed by the existing
Newbie Village bible.

### Monsters and enemy bosses

Monsters may use stronger scale, motion, asymmetry, gloss, or environmental effects. They remain in
the monster/enemy asset namespace and are excluded from the character collection. A boss portrait
must not become an NPC registry entry merely because it is a humanoid or story-relevant encounter.

## 13. Shared character anchors

All coordinates are normalized to the master canvas unless marked body-relative:

| Anchor | Contract |
|---|---|
| BODY_FRAME | x=.20–.80, y=.02–.98 target visible body box |
| FOOT_BASELINE | y=.975 visible contact; shadow may reach y=.99 |
| HAND_ANCHOR | primary body-relative point x=.82,y=.58; secondary x=.18,y=.58; safe boxes ±.12 x and ±.15 y |
| HEAD_ANCHOR | center x=.50,y=.16; safe box x=.28–.72,y=.02–.32 |
| BACK_ANCHOR | behind-body safe box x=.05–.95,y=.20–.86 |
| ACCESSORY_ANCHOR | chest/waist center x=.50,y=.55; safe box x=.36–.64,y=.40–.68 |
| AURA_SAFE_AREA | x=.04–.96,y=.02–.98, with face and labels clear |

The anchors are a shared production contract. Adopting them in runtime is a separate Lane B/C
implementation decision.

## 14. Collection presentation

The future Hero → 外觀 → 角色造型 surface is a Character Collection:

- show 10 / 20 progress;
- show large preview, selected state, locked state, unlock requirement, family, short lore, Zone,
  and acquisition source;
- provide All, Beginner, Warrior, Knight, Ranger, Rogue, Mage, and Scholar filters;
- provide desktop two-panel and mobile single-preview/two-column-card layouts;
- never show Attack, Defense, Power, class stats, equipment effects, or functional weapon claims;
- do not add rarity at Gate 1 because family and acquisition information better serve a non-power
  appearance collection.

## 15. Acceptance gates

Every accepted character asset must pass:

1. identity continuity;
2. canvas, alpha, and transparent-pixel checks;
3. shared body and footline checks;
4. face, outline, lighting, and palette checks;
5. desktop, tablet, and mobile crop checks;
6. empty/open-hands and no-authoritative-weapon check;
7. player/NPC/monster category check;
8. Owner approval before runtime connection.

~~~
CHARACTER_COMBAT_AUTHORITY=NO
FUNCTIONAL_WEAPON_BAKED_IN_BASE_ART=NO
OUTFIT_COMBAT_AUTHORITY=NO
MONSTER_AS_PLAYER_APPEARANCE=NO
~~~
