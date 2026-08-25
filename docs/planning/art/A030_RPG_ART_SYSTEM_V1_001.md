# A030 — RPG Art System V1 Preproduction

Status: canonical design system locked by A030-R2 Owner palette decision
Scope: art direction, reusable visual tokens, surface contracts, renderable mockups and evidence only  
Runtime boundary: no production gameplay, authority, route, schema, asset-package or service-worker change

## Canonical palette lock — A030-R2

`BRIGHT_ADVENTURE` is the single canonical palette for RPG Art System V1.
Candidate B (`COLORFUL_FANTASY`) and Candidate C (`WARM_STORYBOOK`) remain
historical comparison evidence only; they are not implementation choices.

The canonical roles are Adventure Blue `#1E6FC7`, Go Odyssey Teal
`#39C9B6`, Sun Yellow `#F6C957`, Adventure Orange `#F29B52`, Cream
`#FFF4D8`, Sky `#DDF2FF`, Growth Green `#72C96B`, Magic Purple `#8968D8`
and Deep Navy `#173653`. Light, world and colorful surfaces target roughly
65–75%; dark structural chrome targets roughly 25–35%.

`GAME_WORLD_FIRST=YES`: light UI frames the existing E10 world, Zone art,
Hero, Spirit, Monster art and material/FX. It does not replace them with
plain white panels. `WHITE_DASHBOARD_DIRECTION=REJECTED`.

Gold is special rather than default chrome: reserve it for Legendary,
milestones, special rewards, Boss accents and important high-value selected
moments. Blue selection, teal action and yellow `NEW` states carry ordinary
interaction meaning.

## Product visual thesis

Go Odyssey should read as a colorful Go adventure game before it reads as a learning website. The player loop is visible and emotionally ordered:

**Adventure → Encounter → Solve the Go problem → Attack/defeat → Reward → Backpack → Equip → Hero visibly improves → Return to a harder adventure.**

The Art System does not own any of those facts. It gives the facts a consistent visual language. The Go problem remains the largest interactive object in combat; fantasy framing, Hero, Spirit, Monster and feedback make the result feel consequential without obscuring the board.

The target child should be able to answer at a glance:

- Where am I?
- What am I solving?
- Who is beside me?
- What did I earn?
- Can I use or equip it?
- What is my next action?

## Audience and emotional target

Primary players are approximately 6–12 years old, with kyu-level learners as a secondary audience. The system uses large touch targets, compact metadata, obvious selected/locked states and friendly fantasy contrast. It avoids corporate dashboards, spreadsheet density, grimdark surfaces, casino/gacha framing and adult MMORPG inventory complexity.

Visual excitement comes from illustration, material, silhouette, short reveal motion and clear progression—not from constant particles, unreadable fantasy fonts or neon bloom.

## Existing E10 continuity

This proposal extends the current E10 direction; it does not replace it.

The read-only master inspection found:

- `assets/maps/e10_world_stage_v2_clean.webp` is the canonical current-world map asset. A030 treats the map as the broad fantasy layer and does not redraw it.
- The Adventure world component keeps map, zone nodes, player marker and selected-zone details as separate presentation surfaces. A030 keeps World progression authority outside the art system.
- `hero.html` already provides deep wood, readable content surfaces, Hero identity, XP, functional Equipment and Spirit projections in distinct areas. A030 keeps that structure while the canonical future color balance is Bright Adventure.
- `inventory.html` already distinguishes functional Equipment from general Backpack items, uses rarity states, equipped state and server-backed item detail. A030 makes that distinction the cross-surface contract rather than creating a second inventory model.
- `shop.html` already has a merchant/world presentation. A030 keeps the environment visible, makes offer type visible and prevents pure cosmetics from implying power.
- A023 provides a reusable Common/Rare/Elite/Battlefield Boss encounter hierarchy, a one-framework HP presentation and explicit separation from Lord Trial. A030 consumes that direction; it does not redesign the encounter authority.
- A021A provides the canonical six-Spirit runtime asset package. A030 uses one Spirit frame language and does not create another pet system.

The canonical A030 visual family is therefore: **Bright Adventure light/world
surfaces + Deep Navy structural chrome + Adventure Blue selection + Go Odyssey
Teal actions + Sun Yellow `NEW`/milestone accents + strong character/item
silhouettes**. Existing E10 art, materials and environment color remain part
of the world layer.

## Core visual principles

### 1. Game world first

World art should remain visible around major actions. A panel can be rich, but should not become an opaque document over the map. Bright Adventure surfaces frame the world; Deep Navy is reserved for navigation, headers, HUD rails, contrast and high-stakes moments.

### 2. Hero is repeatedly present

Hero identity, level/rank, equipped loadout, Spirit and progression are recurring anchors. The Hero is not a fake combat-stat sheet: only evidence-backed server projections are shown.

### 3. Items are objects

Every item presentation has a primary silhouette, slot marker, rarity treatment and state. Names and metadata support the image; they do not replace it. A weapon looks like a weapon, armor like armor, accessory like an accessory, Trophy like a collectible and Consumable like an object that can be used.

### 4. Go is native to the world

Black/white stones, wood, ink, board-grid geometry, territory paths and stone rings are used as accents. A literal 19×19 grid is reserved for the actual Go problem or intentional framing; it does not cover every card.

### 5. Child-readable hierarchy

One dominant action, one selected state, short labels, 44px minimum targets and no more than three meaningful metadata lines per item card. Secondary details can appear in a detail sheet or lower-priority region.

### 6. Power and appearance remain honest

Functional Equipment uses server-projected ownership/equipped state and may show real supported effects. Pure cosmetics use collection/appearance language only. Trophy, Consumable and cosmetic states never receive a fake “Attack +” row.

### 7. Reward moments are short events

Rewards reveal as a clear result, not a slot machine. The reveal order is result → Coins/XP → item cards → destination/status → one next action.

### 8. Boss moments are distinct

Battlefield Boss uses stronger generic-Monster geometry, scale, HP rail and warning beat. Lord Trial remains a separate ritual/progression authority and must not inherit the generic Boss frame merely because both are boss-like.

## Visual token proposal

The machine-readable source is `a030_rpg_visual_tokens.json`. The central roles are:

| Role | Proposal |
| --- | --- |
| World/background layer | Existing E10 world art plus Sky `#DDF2FF` and environment color; do not replace the map with a white dashboard |
| Primary chrome | Deep Navy `#173653` |
| Selection/action | Adventure Blue `#1E6FC7`; Go Odyssey Teal `#39C9B6` |
| Positive/new | Growth Green `#72C96B`; Sun Yellow `#F6C957` |
| Content | Cream `#FFF4D8` and light Sky `#DDF2FF` |
| Magic/rare accents | Magic Purple `#8968D8`; Adventure Orange `#F29B52` |
| Special gold | Sun Yellow/gold treatment reserved for Legendary and high-value moments |
| Positive | `#7BD37A`, always paired with icon/label |
| Warning | `#F0A84A`, always paired with warning geometry |
| Failure | `#D65B4B`, never the only correctness signal |

Corners are purposeful: 10px controls, 12px insets, 16px major panels, 10px Boss frames and pill-shaped badges only for compact status. Shadows lift a surface from the world; they do not create a separate web page.

Typography uses a restrained display face only for titles. Body, helper, buttons and Traditional Chinese use a highly readable sans-serif. Numbers and short technical labels can use a monospace accent. Body text is never set in a decorative fantasy face.

## Reusable visual roles

The same roles must be reused across Hero, Backpack, Combat, Reward, Shop, Spirit and Quest.

| Role | Behavior |
| --- | --- |
| `BACKGROUND` | Existing E10 world art, environment color or a light/sky scene; low contrast behind interaction |
| `SURFACE_PANEL` | Light Sky/Cream or illustrated world surface; dark chrome is not the default card fill |
| `INSET_PANEL` | One step lighter/darker than parent; carries detail and comparison without becoming a web table |
| `PRIMARY_FRAME` | Blue/teal structural edge; gold only for special/high-value moments |
| `SECONDARY_FRAME` | Quiet Sky/Teal edge for supporting content |
| `HERO_FRAME` | Character focal area, identity plate and progression rail |
| `MONSTER_FRAME` | Base creature/tier frame, HP and nameplate |
| `ITEM_CARD` | One object silhouette, name, rarity/type and state |
| `ITEM_SLOT` | Empty/selected/locked/equipped geometry, never just a blank rectangle |
| `EQUIPMENT_SLOT` | Weapon/armor/accessory marker; only supported functional slots are equipable |
| `REWARD_CARD` | New/rarity/destination/action-aware reward object |
| `SHOP_CARD` | Offer-type first: utility, cosmetic, collection or subscription |
| `QUEST_CARD` | One objective, one primary next action, short context |
| `BOSS_FRAME` | Heavy generic Boss material and warning geometry; not Lord chrome |
| `SPIRIT_FRAME` | Companion material with portrait, role, stage and active state |
| `PRIMARY_CTA` | The next action; 48px minimum and verb-first |
| `SECONDARY_CTA` | View, compare, continue or return |
| `UTILITY_CTA` | Back, close, filter or settings; icon plus accessible label |
| `DISABLED_CTA` | Muted/dashed with reason; never a dead-looking mystery button |
| state roles | Selected, Locked, New, Equipped, Owned and Unavailable each have geometry plus text/icon |
| feedback roles | XP, HP, Coins, damage, defense, success, failure and warning use a stable icon/text pairing |

## Rarity language

Common, Uncommon, Rare, Epic and Legendary differ through frame geometry, material, badge symbol, spacing and restrained glow. Color is supportive only. A Common card should be visually quiet; Legendary is special because it gets a short reveal and crest, not because every surface is saturated.

The A023 encounter hierarchy follows the same principle: visible labels and geometry make Common, Rare, Elite and Battlefield Boss distinguishable without color alone.

## Equipment and Backpack — priority P1

The first implementation target is a three-part decision surface:

1. **Hero/loadout** — the player sees the current character and three canonical functional slots: Weapon, Armor, Accessory.
2. **Selected item detail** — one large object, rarity/type, ownership/equipped state, supported server-projected values and a single action.
3. **Backpack grid** — item cards with image, quantity, rarity/type, New state and selected state.

Equipment is not a spreadsheet. Child-readable comparison uses only real supported values and a small delta treatment such as `+ server value`, `− server value` or `same`; it must not invent unsupported combat semantics. The source of ownership remains `player_inventory`; equipped state remains `player_inventory.equipped`; equip is not consume.

Functional Equipment is visibly different from pure cosmetics: a functional card carries a `FUNCTIONAL / 戰鬥裝備` mark and a supported slot; a cosmetic card carries `COSMETIC / 純外觀` and collection/appearance language. `go_stone_black` remains a Trophy/inventory-only object, and `xp_amulet` remains on authority hold. The Art System must not normalize either into an equipable slot.

Mobile order is intentionally different from Desktop: Hero/loadout strip → selected detail sheet → Backpack grid. The player does not have to scan a desktop table or a tiny side drawer.

## Combat — priority P2

The Go board is the main interaction. The recommended Desktop composition is Monster/HP and Hero/Spirit framing around a large center board; the recommended Mobile composition is top identity rail → full-width Go board → compact feedback/action rail. The fantasy layer reacts to the answer; it does not claim correctness or damage.

Reusable states:

- Correct: short teal-gold edge pulse and readable success label.
- Incorrect: bounded warm-red shake plus coaching copy; no shame language.
- Damage: a server-settled number near the Monster.
- Defense: a shield cue near the Hero only when the committed result provides it.
- Spirit trigger: a companion orbit/reaction cue, with no implied effect calculation.
- Defeat: compact silhouette transition, then Reward surface.

The current A023 framework already defines one HP presentation framework and Common/Rare/Elite/Battlefield Boss presentation timing. A030 keeps that contract and gives it a broader visual system. Suggested maximums remain quick for ordinary play: Common entrance 420ms / defeat 700ms; Rare 620/820; Elite 780/980; Battlefield Boss 1200/1400. Reduced-motion mode converts those to immediate state changes with persistent labels/icons.

## Regular Monster, Battlefield Boss and Lord

Regular Monsters use a standard nameplate, standard HP, minimal effect and quick entrance. Rare and Elite add visible badges, reinforced frame geometry and bounded aura. Battlefield Boss adds the heaviest generic frame, larger portrait/HP treatment and a warning beat.

Lord Trial is not a fourth tier of the same identity ladder. It owns its ritual, progression and ceremonial presentation. The Boss frame must never label itself Lord or borrow Lord Trial progression cues.

The production model is **Base Creature Family → Variant Identity → Presentation Tier**. A base creature can become a scout, thrower, miner or heavy guard through a meaningful combination of silhouette, gear, pose, markings, prop, texture or proportion. Hue-only swaps are rejected. Final Monster count is deliberately undecided and never encoded by this system.

## Reward / Drop — priority P3

The reward surface is a readable event after committed settlement:

1. Result header: “Monster defeated / 遭遇完成”.
2. Coins and XP, with icons and numbers.
3. Reward cards for Equipment, Consumable, Material, Cosmetic, Spirit-related item or Trophy.
4. `NEW` / Owned / destination state.
5. One primary action: Equip, Use or Continue. At most one secondary action: View in Backpack.

Actions are capability-driven. A cosmetic can open Collection; a Trophy cannot show Equip; a Consumable shows Use only when the server says it is usable. No roulette, spin, paid reveal or fake guarantee is part of the design.

## Shop — priority P4

The Shop groups offers by what the player receives:

- **Coin utility** — useful item, quantity and coin price.
- **Coin cosmetic** — appearance/collection, no fake Attack/Defense/XP rows.
- **Premium/subscription** — access/benefit copy, separate from item ownership.
- **Unavailable/blocked** — muted art and reason, no misleading CTA.

The merchant/world backdrop remains part of the scene, while cards use the same item/rareness/status tokens as Backpack and Reward. Shop catalog, pricing, payment, Premium entitlement and ownership remain their own authorities.

## Hero, Spirit, World and Quest extension

### Hero Overview

Hero is the identity anchor: portrait/full body, player name, level/rank, XP rail and short equipment/Spirit summary. Do not introduce Hero class power, STR/DEF, passives, skills or a separate combat authority.

### Spirit Companion

There is one six-Spirit system: `ink_drop_kelpie`, `whispering_void_kit`, `star_shell_hatchling`, `starpath_antlerling`, `fatty`, `obsidian_bastion`. A Spirit frame shows portrait, name, role, stage/level and Active/Owned/Locked state. It uses companion material, not Equipment slot treatment. The current A021A assets remain canonical.

### World / Adventure

The E10 map stays broad and visible. Current Zones remain the established ten-zone progression: 新手村, 史萊姆平原, 哥布林洞穴, 迷霧森林, 獸人部落, 龍之谷, 賢者之塔, 魔王城前線, 諸神黃昏, 上古終焉神殿. A030 provides edge framing, HUD, CTA and panel roles; it does not repaint the map or move zone authority.

### Quest

Quest cards are short direction cards attached to world context. They show one objective, one next action and compact reward preview only where the Quest authority supplies it. Quest correctness, periods and rewards remain separate.

## Motion and audio choreography

Motion is short and purposeful:

| Event | Visual timing role |
| --- | --- |
| Item acquired | 280–520ms card reveal, `NEW` persists |
| Equip | 220–360ms slot-to-Hero link pulse |
| Correct answer | ≤340ms board-edge pulse |
| Damage/defense | 300–520ms result cue after committed settlement |
| Spirit trigger | 360–650ms companion reaction |
| Monster defeat | 700–1400ms by tier, then reward |
| Boss entrance | one bounded warning beat, no long gate on ordinary answers |
| Zone unlock | short path/crest pulse; existing audio contract supplies sound |

Existing Zone 1 audio/SFX remains untouched. The visual system only names timing roles compatible with card reveal, challenge confirm, energy, Go-stone impact, success/failure and zone unlock. Reduced-motion mode removes movement and preserves labels, state geometry and timing completion.

## Typography and accessibility

Traditional Chinese and English must remain readable at Desktop, iPad and Mobile widths. Body/helper text is never below 14/12px respectively in the proposed system. Critical controls are at least 44px, with 48px preferred for primary CTA. Focus uses a visible high-contrast blue/navy outline and offset; gold remains available for important selected moments. Selected, rarity, locked and success/failure states are not color-only; each has icon, label or geometry.

The board and future runtime UI should be tested at 1440×900, iPad landscape, 390px, 375px and 360px. Mobile changes order instead of just scaling down. No horizontal scroll is allowed for primary decisions.

## Asset taxonomy and naming

`a030_rpg_asset_taxonomy.json` defines future categories: `hero/`, `equipment/weapon|armor|accessory/`, `items/consumable|material|trophy/`, `cosmetics/`, `spirits/`, `monsters/`, `bosses/`, `world/`, `ui/frames|icons|buttons|status/`, `fx/combat|reward|unlock/`, `shop/` and `quest/`.

Machine IDs use lower snake case. Spirit runtime forms use `spirit_<machine_id>_stage<1|2|3>.<ext>`. Monster variants use base family plus meaningful variant/tier tokens. Text should not be baked into art where a locale-neutral asset is possible. A030 does not move or promote any assets.

### Final art production note

A030-R2 locks color direction only; it does not create final item icons. The
current weapon, armor, accessory, consumable, Trophy, cosmetic, Coins and XP
glyph placeholders are temporary presentation stand-ins. Future Art
Production must replace them with one coherent Go Odyssey icon family while
preserving the locked slot, rarity and authority semantics.

## Renderable mockup board

`a030_core_loop_visual_board.html` is a self-contained board with local repository asset references only and CSS/SVG neutral shapes where final illustration is not required. It contains:

- Equipment + Backpack Desktop and responsive Mobile composition.
- Combat Desktop and responsive Mobile composition, with the Go board as the dominant object.
- Reward/Drop Desktop and responsive Mobile composition.
- Shop Desktop and responsive Mobile composition.
- Tablet landscape reference.
- Seven-step core loop storyboard.
- Visual-system contact sheet for frames, rarity, slots, state and CTA language.

The board is a composition lock, not a final art production package. It intentionally uses the existing E10 map and available character/Monster/merchant assets where useful, but does not make those evidence images runtime dependencies.

## Implementation priorities

The recommended order is:

1. **P1 — Equipment / Backpack**: highest daily decision value; establish item/slot/state language.
2. **P2 — Combat**: make the Go problem dominant and connect A023 framework states.
3. **P3 — Reward / Drop**: make acquisition readable and non-gacha.
4. **P4 — Shop**: align offer type and item language without changing commerce authority.
5. **P5 — Spirit Companion**: apply the single six-Spirit frame and active state.
6. **P6 — Battlefield Boss**: extend A023 tier language while preserving Lord separation.
7. **P7 — Hero Overview polish**: unify identity, progression and loadout summary.
8. **P8 — World presentation polish**: keep E10 map dominant and refine edge framing.
9. **P9 — Quest presentation**: compact objective/next-action cards.
10. **P10 — Global RPG polish**: shared motion, accessibility and final asset pass.

This order follows the current product dependencies: item/state language is reused by Reward, Shop and Hero; Combat must consume but not redefine the Go and settlement authorities; World and Quest are later because their authorities are intentionally separate.

## Known unresolved questions

1. Final Monster roster cardinality and base-family inventory remain undecided pending the F-lane pace/recon work.
2. Final combat stat vocabulary must be limited to fields that are proven and server-projected; this board does not lock new stats.
3. Final art production dimensions and compression targets require the release/static delivery contract before runtime promotion.
4. The exact cross-surface Reward-to-Backpack destination copy needs product/i18n approval.
5. Premium and Shop visual copy must continue to follow Revenue authority decisions; A030 only defines offer-type slots.
6. Lord Trial visual refresh, if any, must be reviewed separately from the Battlefield Boss framework.

## Explicit non-goals

A030 does not redesign the ten Zones, replace Zone 1 art, create a Monster roster, produce all final Equipment/Spirit illustrations, rewrite Hero/Backpack/Combat/Shop runtime, wire C019/C023/C026/B034, change progression/combat/economy/Premium/Quest/Spirit mechanics, change prices, modify app.py, update service worker/cache, touch schema/DB/Production or enable/deploy/merge anything.

## Review questions and pre-production conclusion

- Does the system look like a game? **Yes in the renderable proposal**: world chrome, focal characters, object-based item cards, short actions and clear reward/combat moments are coherent.
- Does the Go board remain primary in combat? **Yes**: the combat composition reserves the largest central surface for the board on Desktop and Mobile.
- Is functional Equipment distinct from cosmetic? **Yes**: slot/equip/value treatment versus collection/appearance treatment.
- Is Trophy distinct from Equipment? **Yes**: Trophy slot mark and no Equip action.
- Is Regular Monster distinct from Battlefield Boss? **Yes**: tier label, geometry, scale, HP treatment and bounded entrance.
- Is Battlefield Boss distinct from Lord? **Yes**: generic Boss frame explicitly excludes Lord ritual/progression.
- Is reward presentation non-gacha? **Yes**: deterministic result cards and explicit next actions, no roulette.
- Is Mobile first-class? **Yes**: intentional reorder and single-column decision flow at 390/375/360px.
- Can the system extend to all ten RPG systems? **Yes**, because it is role/token based and presentation-cardinality agnostic.

`READY_FOR_OWNER_A030_VISUAL_REVIEW` remains a review handoff, not an Owner PASS claim.
