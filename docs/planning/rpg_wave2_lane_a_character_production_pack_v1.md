# RPG Wave 2 Lane A — Character Production Pack v1

Status: PROPOSAL_FOR_OWNER_GATE1
Lane: Wave 2 Lane A — Character Production Foundation
Base: origin/master a82b0d99e0b413d9cd55dac4e86ef5c5140351e6
Scope: specification, registry preparation, concept design, and art-production contracts

This pack does not generate final art, change runtime rendering, change combat, add a database
table, change Premium, or alter Production. Candidate concepts become canonical only after Owner
approval.

## 1. Product invariants

- The ten current player character IDs remain unchanged.
- All ten existing concepts are KEEP_CONCEPT and POLISH.
- The target player-character roster is twenty appearances: ten current plus ten concept slots.
- A player character appearance is visual identity only. It is not an RPG class and has no attack,
  defense, XP, loot, coin, or functional-equipment authority.
- Base character art must not bake in an authoritative weapon, armor, accessory, or combat effect.
- The Village Elder reuses the canonical Elder identity in
  docs/planning/e10_newbie_village_art_direction_bible.md.
- World NPCs, monsters, outfits, and functional equipment remain separate categories.

## 2. Existing ten polish pack

Current runtime character assets are normalized 1056x1408 RGBA WebP files under
assets/hero/characters. The existing renderer already measures per-character body boxes through
CHAR_BODY. The polish pass preserves identity and improves export cleanliness, common face/outline
rules, lighting, costume legibility, and card-size readability.

| ID | CURRENT_ASSET | CURRENT_VISUAL_STRENGTH | CURRENT_VISUAL_WEAKNESS | BODY_FRAME_ADJUSTMENT | FACE_STYLE_ADJUSTMENT | OUTLINE_ADJUSTMENT | LIGHTING_ADJUSTMENT | ALPHA_CLEANUP | COSTUME_SIMPLIFICATION_IF_NEEDED | MOBILE_READABILITY_FIX | COLOR_NORMALIZATION | EFFORT |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| apprentice | assets/hero/characters/chibi_apprentice_normalized.webp | Clean baseline novice silhouette; readable teal block | Green-key RGB residue and small trim detail | Preserve slim baseline; target body box x .21-.78, y .02-.98 | Common face/eye/brow grid; retain novice age | Uniform dark blue-brown contour; remove halo | Shared soft upper-left key; reduce flat highlights | Decontaminate transparent RGB and semi-transparent edge pixels | Keep tunic and strap; remove sub-card-size trim | Increase face, pendant, and teal/off-white contrast | Teal, off-white, leather brown, muted brass | LIGHT |
| apprentice_girl | assets/hero/characters/chibi_apprentice_girl_normalized.webp | Clear alternate beginner identity and open silhouette | Visible bounds and edge treatment differ from roster average | Re-center body and restore common footline; reduce edge spread | Align eye scale and brow weight without erasing identity | Match contour weight to apprentice | Match warm/cool balance to apprentice | Clean edge spill, especially at wide silhouette | Keep beginner costume; simplify tiny hem decoration | Preserve hair/face read at two-column card width | Teal family with a distinct but restrained accent | MEDIUM |
| swordsman | assets/hero/characters/chibi_swordsman_normalized.webp | Strong blue warrior read and compact silhouette | Small headband/trim details compete at card size | Align shoulder width and feet to shared body frame | Common face grid; keep focused expression | Reduce variable dark edge thickness | Add shared face key and controlled shoulder fill | Remove blue/green fringe at contour | Consolidate headband and chest trim into larger shapes | Make blue upper-body block and hair silhouette dominant | Blue, slate, warm brown, brass | LIGHT |
| rogue | assets/hero/characters/chibi_rogue_normalized.webp | High-contrast dark silhouette reads immediately | Hood, hands, and dark costume can merge on dark UI | Preserve narrow profile; maintain visible hand separation | Brighten eye/face plane within common grid | Keep dark outline but avoid black-on-black interior | Add cool fill to separate hood, face, and torso | Clean dark edge matte and transparent pixels | Reduce micro-folds; retain hood identity | Add a light face window and one accent block | Charcoal, muted violet/teal, brown, ivory | LIGHT |
| ranger | assets/hero/characters/chibi_ranger_normalized.webp | Green/brown travel palette gives immediate world role | Low contrast between hair, hood, and costume at small size | Preserve lean stance; normalize shoulder and hand spacing | Common eye/brow grid; keep alert expression | Match contour weight and join line caps | Shared warm key with restrained green fill | Remove green-key contamination without flattening green costume | Keep mantle and satchel; simplify tiny leaf/strap marks | Use one large green mantle shape and warm face window | Forest green, umber, ivory, muted brass | LIGHT |
| berserker | assets/hero/characters/chibi_berserker_normalized.webp | Red hair and broad energy give a distinct silhouette | Hair and costume detail make face/card hierarchy noisy | Keep broad identity; align torso width to body-frame maximum | Increase face plane and reduce competing hair highlights | Consistent outline around hair spikes and shoulders | Control red hair highlight; shared neutral face fill | Clean fine hair edge and partial alpha | Group fur/leather shapes into three readable masses | Keep red hair as one high-value silhouette cue | Ox-blood red, charcoal, leather brown, brass | MEDIUM |
| guardian | assets/hero/characters/chibi_guardian_normalized.webp | Sturdy protective silhouette and dark armor blocks | Broad torso can dominate card; armor trim is dense | Preserve broad frame but keep footline and face proportion common | Common face grid; retain grounded expression | Slightly lighter interior contour for armor separation | Shared key on face and upper armor; softer shadow | Clean broad armor edge and matte | Merge small plate seams into large armor planes | Keep shoulder/torso block; reduce low-value plate detail | Blue-charcoal, iron grey, brown, muted brass | MEDIUM |
| paladin | assets/hero/characters/chibi_paladin_normalized.webp | White/gold contrast is readable and aspirational | Gold filigree and bright areas can become visual noise | Preserve upright body; align cape/shoulder bounds | Common face grid; retain calm expression | Use warm dark outline around white costume | Keep warm key but lower gold bloom | Clean pale fringe against light backgrounds | Reduce gold filigree to a few large motifs | Keep white torso and one gold focal shape | Ivory, navy, muted gold, brown | MEDIUM |
| mage | assets/hero/characters/chibi_mage_normalized.webp | Strong navy/lavender palette and instantly readable magic family | Highest detail density; broad alpha/bounding behavior differs; small details collapse | Re-center body and stabilize robe/hair bounds within shared frame | Reduce eye/hair detail to common face grid | Normalize long-hair and robe contour weight | Shared key plus restrained cool fill; no neon aura | Heavy edge decontamination and alpha review on dark/light test cards | Collapse star/trim marks into large robe motifs | Preserve lavender hair and navy robe as two large blocks | Navy, lavender, ivory, muted gold | HEAVY |
| sage | assets/hero/characters/chibi_sage_normalized.webp | Age diversity and scholar identity expand roster meaningfully | Face, beard/glasses/detail density do not yet share the common card grid | Preserve older, upright body; align head and feet without making youthful | Establish common facial landmarks while retaining age lines | Normalize beard, glasses, and robe contour hierarchy | Warm face key, cooler robe fill, restrained highlights | Heavy beard/glasses edge and transparent-pixel cleanup | Keep scholar robe and one focal accessory; remove tiny trim | Make face, hair, and robe silhouette readable before accessories | Earth brown, slate, ivory, muted brass | HEAVY |

### 2.1 Polish counts

~~~
LIGHT_POLISH_COUNT=4
MEDIUM_POLISH_COUNT=4
HEAVY_POLISH_COUNT=2
KEEP_CONCEPT=10
POLISH=10
RETIRE=0
REDRAW=0
REPLACE=0
~~~

### 2.2 Shared polish acceptance

Each polished asset must pass:

1. 1056x1408 RGBA canvas and clean alpha on both light and dark test backgrounds.
2. Neutral RGB values in fully transparent pixels; no green-key fringe or matte halo.
3. Common foot baseline, body box, face landmarks, contour weight, and soft upper-left lighting.
4. Empty/open hands by default. Any prop requires a separate non-authoritative art note.
5. Identification at desktop card size and approximately 72–96px mobile card height.
6. No change to current internal ID, unlock behavior, or combat authority.

## 3. New player-character concept pack

All names below are candidates, not final canonical display names. They are visual identities only.

| CHARACTER_ID_CANDIDATE | DISPLAY_NAME_CANDIDATE | FAMILY | WORLD_ASSOCIATION | VISUAL_ROLE | AGE/BODY_PRESENTATION | SILHOUETTE | PRIMARY_PALETTE | SECONDARY_PALETTE | CLOTHING_LANGUAGE | DISTINCTIVE_FEATURE | UNLOCK_SOURCE | PLAYER_LORE | ART_PRIORITY |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| trail_apprentice | Trail Apprentice | Beginner / Adventurer | Newbie Village departure road | A novice who has begun travelling | Adolescent-to-young-adult; neutral presentation | Short coat, scarf, compact travel pack, open hands | Teal-blue | Clay beige, brown, brass | Practical linen, repaired hems, light straps | A route-marked scarf or small waystone charm | Early story milestone | You left the village before you felt ready, carrying curiosity rather than status. | HIGH |
| river_wayfinder | River Wayfinder | Adventurer | Slime Plains waterways | Quiet field guide and route reader | Young adult; broad presentation options | Hooded rain cape, tall boots, side satchel | Water blue | Reed green, warm grey, brass | Weatherproof cloth, rolled map, simple belt | One asymmetrical water-ripple hem | Zone 2 story completion | You learned to read unsafe ground by watching what the water refuses to carry. | MEDIUM |
| stone_caretaker | Stone Caretaker | Scholar / Village | Elder court and Go waystones | Keeper of local practice and memory | Adult or older adult; age-diverse | Broad sash, grounded stance, layered short robe | Stone grey | Cedar brown, ivory, muted gold | Dojo workwear with durable apron layer | A visible stone-counting cord | Village collection milestone | You maintain the stones so other players can make their first move. | MEDIUM |
| duelist_scout | Duelist Scout | Warrior | Frontier roads and training grounds | Alert traveller who values observation | Teen or young adult; any presentation | Narrow shoulder line, asymmetric short coat, long leg line | Slate blue | Rust red, ivory, leather brown | Light travel cloth, reinforced cuffs, no battle weapon baked in | One split shoulder panel | Mid-game practice milestone | You look for the shape of a fight before deciding whether to enter it. | HIGH |
| bastion_warden | Bastion Warden | Knight / Guardian | Village defense and Demon Castle front | Protective, calm, non-aggressive defender | Adult; varied body widths encouraged | Rounded shoulder mantle, stable vertical torso | Blue-charcoal | Stone grey, muted gold, brown | Layered guard cloth and padded mantle | Large back/shoulder arc readable without equipment | Zone 5 or defense story | You protect a path by staying where others can still see it. | HIGH |
| forest_pathfinder | Forest Pathfinder | Ranger | Misty Forest | Patient guide through uncertain terrain | Teen or adult; neutral/androgynous options | Leaf-like mantle, long hood, tall boots | Forest green | Mist violet, bark brown, ivory | Weathered cloak, quiet layered travel cloth | One leaf-shaped hood profile | Zone 4 completion | You learned that the safest path is often the one that leaves room for someone else. | MEDIUM |
| night_runner | Night Runner | Rogue / Adventurer | Goblin Cave and forest edge | Fast courier and careful listener | Teen or young adult; any presentation | Low-profile split coat and diagonal hem | Charcoal | Muted violet, teal, warm grey | Soft hood, close-fitting travel layers, no weapon authority | Light-catching face opening | Zone 3 story milestone | You carry messages through places where certainty is more dangerous than silence. | HIGH |
| constellation_apprentice | Constellation Apprentice | Mage | Sage Tower approach | Beginner scholar of sky and stone | Adolescent or young adult; broad presentation | Asymmetric sleeves, tall hair/hood line, open hands | Deep navy | Lavender, ivory, muted brass | Star-map cloth with large simple motifs | One incomplete constellation band | Sage Tower story milestone | You know only a few stars, but you know which ones to keep looking for. | HIGH |
| archive_scholar | Archive Scholar | Scholar / Sage | Sage Tower and ancient records | Researcher who turns memory into a path | Adult or older adult; age-diverse | Tall collar, layered archive satchel, straight robe line | Warm umber | Slate, parchment ivory, muted teal | Archive layers, cloth tabs, practical sleeves | One oversized index tag or folio clasp | Long-term learning milestone | You keep records because a forgotten choice can still shape a living world. | MEDIUM |
| worldkeeper | Worldkeeper | Sage / Guardian | Endgame world stage | Quiet steward of shared routes and people | Broad age/body presentation; no fixed gender cue | Long stable mantle and strong vertical center | Deep indigo | Ivory, cedar brown, restrained gold | Civic mantle over travel base; no royal costume | Paired black/white waystone motif | Final collection/story milestone | You are not the strongest person in the world; you are someone who keeps it open to others. | HIGH |

No concept above defines a class, combat role, attack value, defense value, or functional item
ownership.

## 4. World NPC production pack

The following seven entries are the first high-priority reusable world-character production pack.
They are not player-selectable appearances.

| CANONICAL_ID | DISPLAY_NAME | ZONE | STORY_ROLE | GAMEPLAY_ROLE | CURRENT_ART | MISSING_ART | PORTRAIT_REQUIRED | FULL_BODY_REQUIRED | CINEMATIC_VARIANT_REQUIRED | UI_VARIANT_REQUIRED | ART_PRIORITY |
|---|---|---|---|---|---|---|---|---|---|---|---|
| world.village_elder | 村長 / Village Elder | Zone 1 Newbie Village | Living teacher and keeper of the first Go trial | Narrative guide and first-trial presenter; no combat authority | assets/e10/art/zone1/lord_trial/zone1_village_elder_reference.png and .webp | Reusable transparent 1056x1408 body set, neutral portrait crop, expression variants | YES | YES | YES | YES | HIGH |
| world.messenger | 信使 / Messenger | Zone 1, Shot 10 | Brings the missing-caravan hook after the Elder trial | Story handoff and route hook; no combat authority | None | Full canonical design: satchel/sash, village courier silhouette, running and stop poses | YES | YES | YES | YES | HIGH |
| world.herder | 牧人 / Herder | Zone 2 Slime Plains | Witness to the slimes' suffering and corrupted hive | Zone context and testimony; no combat authority | Zone 2 audio/story references only; no reusable character art | Mud-safe field clothing, cart interaction, close dialogue pose, background silhouette | YES | YES | YES | YES | HIGH |
| world.smith_elder | 鐵匠長老 / Smith-Elder | Zone 5 Orc Tribe | Explains the corrupted ore and Chieftain's axe history | Lore clue and emotional context; no combat authority | Generic assets/hero/npc_blacksmith_* exist but are not this canon identity | Specific elder smith identity, ore-handling pose, quiet close-up, age distinction from Jason | YES | YES | YES | YES | HIGH |
| world.archmage | 大法師 / Archmage | Zone 7 Sage Tower | Mentor who reframes the Hero's search for a correct answer | Heartstone story handoff; no combat authority | No standalone production character asset found | Tower-scale full body, intimate face close-up, sleeve gesture, Heartstone handoff variant | YES | YES | YES | YES | HIGH |
| world.serel | Serel / 瑟瑞爾 (candidate localization) | Zone 8 Demon Castle Front | Working frontline officer responsible for real soldiers | Narrative military context; never player army authority | No standalone production character asset found | Command-flag pose, face-to-face Hero variant, withdrawal/protection pose | YES | YES | YES | YES | HIGH |
| world.eastern_guardian | 東方守護者 / Eastern Guardian | Zone 10 Ancient Doom Temple | Silent guardian who communicates by look and gesture | Non-verbal cinematic gate; no combat authority | No standalone production character asset found | Silent silhouette, archway gesture, wide and close cinematic variants | YES | YES | YES | YES | HIGH |

### 4.1 Village Elder continuity lock

The Elder must reuse the identity already defined in the Newbie Village bible:

- late-60s to early-70s lean upright frame;
- white-grey hair in a low half-knot, not a new high-topknot identity;
- long white moustache and medium-long forked beard;
- deep indigo/blue-charcoal robe, warm-brown sash, restrained brass/wood Go detail;
- calm living teacher, not an ancient projection or boss monster.

The existing Elder reference is accepted as identity evidence and production key art. It is not a
reason to invent a second Elder.

## 5. NPC identity registry cleanup

Physical files are not renamed in this task.

| CANONICAL_CHARACTER_ID | DISPLAY_NAME | CURRENT_RUNTIME_ASSET | LEGACY_FILENAME | FUTURE_ASSET_KEY |
|---|---|---|---|---|
| world.guild_mentor.claire | 克萊兒 / Claire | assets/go_rpg_assets/npc_elina.webp and .png | npc_elina | npc_guild_mentor_claire |
| world.cleansing_mentor.elina | 艾莉娜 / Elina | assets/guild_ui/npc_vera.png | npc_vera | npc_cleansing_mentor_elina |
| world.arena_referee.oberon | 奧伯隆 / Oberon | assets/play_page_assets/home/ubuntu/play_assets/npc_aiden.webp and .png | npc_aiden | npc_arena_referee_oberon |

The registry key becomes the stable identity. Runtime aliases may continue to resolve old physical
filenames until a separately approved asset migration exists.

## 6. Character Collection UX specification

Surface: Hero → 外觀 → 角色造型
Future product name: Character Collection

### 6.1 Collection data contract

Each card/detail view should expose:

- collection count, for example 10 / 20;
- canonical or candidate character ID;
- display name;
- family;
- world or Zone association;
- one-sentence player lore;
- acquisition source;
- unlock requirement and progress;
- selected state;
- locked state;
- preview asset key.

The card must not expose Attack, Defense, Power, class stats, equipment effects, or a functional
weapon implication.

### 6.2 Filters

~~~
All
Beginner
Warrior
Knight
Ranger
Rogue
Mage
Scholar
~~~

Families are collection labels only. They do not affect combat.

### 6.3 Desktop interaction

- Use a two-panel layout: large preview/detail panel on the left, collection grid on the right.
- Preview keeps the 1056x1408 character safe area and shows name, family, Zone association, lore, and
  acquisition source.
- The grid shows selected, owned/unlocked, and locked states without changing the base art.
- Selecting an unlocked card updates the preview and selected marker.
- A single Apply/Select action persists the visual selection through the existing appearance path.
- A failed server validation restores the previous selected state; client optimism is visual only.

### 6.4 Mobile interaction

- Use a single-column preview followed by a two-column card grid.
- Keep the selected action sticky below the preview, not inside a tiny card.
- Locked cards remain readable and announce the requirement; they cannot submit selection.
- Tapping a card opens a compact detail sheet with lore, Zone, family, and acquisition source.
- Keep face, torso, and primary silhouette inside the card safe area; do not crop feet or head on
  the default card.
- Preserve accessible text for selected and locked state; do not use color alone.

### 6.5 Rarity decision

Do not introduce character rarity at Gate 1. Family, story association, collection progress, and
unlock source provide more product value and do not imply gameplay power. A future non-power
collection tier would require a separate Owner decision.

## 7. Character / outfit / equipment layer contract

The visual stack is:

~~~
Base Character
  → Outfit Cosmetic
  → Functional Equipment projection if supported
  → Cosmetic Style Gear
  → Aura / FX
~~~

Layer responsibilities:

1. Base Character: body, face, hair, hands, base clothing identity, and silhouette. No authoritative
   weapon or combat effect.
2. Outfit Cosmetic: visual wardrobe overlay. It can change appearance only. Existing supported
   non-combat cosmetic effects remain separate server rules and must not be inferred from art.
3. Functional Equipment projection: visual representation of an owned/equipped functional item.
   Authority remains player_inventory and server-side definitions.
4. Cosmetic Style Gear: non-authoritative hat, cape, accessory, pet, or style layer.
5. Aura / FX: presentation-only layer with no ownership or combat implication by itself.

No renderer change is authorized by this document.

## 8. Shared character anchor specification

Coordinates are normalized against the 1056x1408 master canvas unless marked body-relative. They
are production anchors for Lane B/C to consume later; they are not a runtime migration.

| ANCHOR | PROPOSED CONTRACT |
|---|---|
| BODY_FRAME | Visible body target x=.20–.80, y=.02–.98; per-character measured override permitted; preserve common footline |
| FOOT_BASELINE | y=.975 visible foot contact; shadow may extend to y=.99 |
| HAND_ANCHOR | Primary hand point body-relative x=.82, y=.58; secondary hand point x=.18, y=.58; safe boxes ±.12 x and ±.15 y |
| HEAD_ANCHOR | Center x=.50, y=.16; safe box x=.28–.72, y=.02–.32 |
| BACK_ANCHOR | Behind-body safe box x=.05–.95, y=.20–.86; must not cover face or selected-state label |
| ACCESSORY_ANCHOR | Chest/waist point x=.50, y=.55; safe box x=.36–.64, y=.40–.68 |
| AURA_SAFE_AREA | Outer effect area x=.04–.96, y=.02–.98; face and card text remain clear |

Artists may use intentional silhouette exceptions, but the exception must be recorded with the
asset and must not silently change equipment attachment semantics.

## 9. Cross-lane requirements

### Lane B — functional equipment and Backpack

- Consume BODY_FRAME, HAND_ANCHOR, HEAD_ANCHOR, BACK_ANCHOR, ACCESSORY_ANCHOR, and AURA_SAFE_AREA.
- Keep functional item identity in a separate item/equipment registry and player_inventory.
- A weapon projection may attach near HAND_ANCHOR, but base art remains empty/open-handed by default.
- No character ID, family, display name, or decorative prop may grant a functional item.
- Any functional-equipment artwork must declare its supported base-frame compatibility.

### Lane C — Items, Collections, and Shop presentation

- Reuse the same preview safe area and selected/locked presentation semantics.
- Keep character collection metadata separate from item economy metadata.
- A cosmetic outfit can be shown over a character only through the cosmetic layer contract.
- Shop/merchant presentation must not rename or re-key the Lane A character identity registry.
- No rarity, price, Premium flag, or purchase source is implied by character art alone.

## 10. Gate 1 acceptance

Owner review should confirm:

- all ten existing concepts remain intact;
- the ten candidate slots are useful and non-class-based;
- the Elder continuity lock is accepted;
- the six missing NPC concepts are correctly prioritized;
- alias cleanup is registry-only;
- collection UX excludes combat values and rarity;
- anchor coordinates are suitable for Lane B/C;
- no base artwork contains authoritative functional weapons.

~~~
CHARACTER_COMBAT_AUTHORITY=NO
FUNCTIONAL_WEAPON_BAKED_IN_BASE_ART=NO
DB_MIGRATION=NO
RUNTIME_IMPLEMENTATION=NO
PRODUCTION_MUTATION=NO
~~~
