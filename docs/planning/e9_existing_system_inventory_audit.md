# E9-PREFLIGHT-01: Existing Economy, Avatar, Equipment & Monster Inventory Audit

```
Project: Go Odyssey / godokoro.com
Repository: D:\go-website
Branch: audit/e9-existing-system-inventory
Base HEAD: a7e56324306070686dcf91e378c7fbc525641740 (origin/master)
Work type: read-only audit + documentation
Production mutation: NONE performed
Runtime behavior changes: NONE performed
Deployment: NONE performed
```

## Methodology

Five independent read-only research passes were run in parallel over the working tree, each restricted to
Read/Grep/Glob/read-only Bash:

1. Economy & player progression (`app.py`, `db.py`, `grimoire_api.py`, `community_leaderboard_rewards.py`, templates)
2. Avatar/Hero system (`hero.html`, `index.html`, rendering + ownership code)
3. Equipment/cosmetics catalog (`APPEARANCE_DEFS`, `BADGE_DEFS`, `COMBAT_GEAR`, `EQUIPMENT_DEFS`, `SKILL_DEFS`, skins, shop consumables)
4. Monster/Boss/Zone system (`monster_taxonomy.py`, battlefield roster, adventure zones)
5. Quests/Rewards/Shop/Community (`community_leaderboard_rewards.py`, daily challenge, SRS, mistakes, leaderboard, guild)

Every claim below is backed by a `file:line` citation gathered by those passes. Where evidence was insufficient,
findings are marked `UNKNOWN` rather than guessed. No concept-diagram assumption (coins/gems/energy/passes) was
treated as real without code/DB evidence.

`app.py` is a ~21,290-line monolithic Flask app; there is no separate `templates/`, `models/`, or `migrations/`
directory — schema lives inline in `app.py` (`CREATE TABLE`/`add_column_if_not_exists` calls) and root-level
`.html` files serve as templates directly.

---

## Phase A — Canonical source map

| System | Canonical source of truth |
|---|---|
| Player progression / stats | `app.py` `user_stats` table (inline schema, ~app.py:2618-2629, 3563-3611) |
| Currency (coins) | `app.py` `user_stats.coins` + `currency_log` ledger (app.py:3081-3088, 15704-15732) |
| Premium/subscription | `app.py` `users.plan`/`users.premium_until` + `subscriptions` table (app.py:3117-3146) |
| Avatar/Hero cosmetics | `app.py` `APPEARANCE_DEFS` (784-1390) + `hero.html` `COMBAT_GEAR` (hero.html:3368-3424) — **two parallel systems**, see Phase C |
| Equipment ownership/equipped | `app.py` `player_wardrobe` / `player_appearance` tables (app.py:3034, 3049) |
| Monsters (combat) | `app.py` `_BATTLEFIELD_ROSTER` (app.py:4415-4437) |
| Monster flavor names | `monster_taxonomy.py` (name pools only, no combat data) |
| Adventure zones/bosses | `app.py` `ADVENTURE_ZONES` / `ADVENTURE_BOSS_META` (app.py:7824-7848) |
| Quests | `app.py` `DAILY_QUEST_DEFS` + `daily_quests` table (app.py:1580, 2932) |
| Community rewards | `community_leaderboard_rewards.py` (2036 lines) + `leaderboard_snapshots`/`leaderboard_reward_claims` tables |
| SRS | `app.py` `srs_cards` table (app.py:2601) |

---

## Phase B — Player values & economy

### B.1 Progression fields (selected — full detail in agent transcript, condensed here)

| Field | Storage | Gameplay Effect | Status |
|---|---|---|---|
| `xp` | `user_stats.xp` column | Drives `rank_level` via `xp_to_lv()` | ACTIVE_RUNTIME |
| `rank_level` (LV1–LV50) | `user_stats.rank_level` | Gates HP cap, appearance rewards | ACTIVE_RUNTIME |
| `rank_xp` | `user_stats.rank_xp` | Still written, no longer drives level derivation | LEGACY_ACTIVE |
| `go_rank` (kyu/dan) | `user_stats.go_rank` | Promotion/demotion at 70%/30% win rate | ACTIVE_RUNTIME |
| `elo_rating`/`elo_provisional` | `users.elo_rating`/`elo_provisional` | Drives placement rank + adventure zone unlock | ACTIVE_RUNTIME |
| `current_streak`/`max_streak` | `user_stats` columns | Badge gating only | ACTIVE_UI |
| `combo_streak`/`max_combo` | `user_stats` columns | Multiplies XP gain (`combo_mult`) | ACTIVE_RUNTIME |
| `total_correct`, `mistake_corrected` | `user_stats` columns | Achievement/title gating | ACTIVE_UI |
| Win rate (online play) | Computed from `game_results` | Directly promotes/demotes `go_rank` | ACTIVE_RUNTIME |
| `player_hp`/`player_max_hp` | `user_stats` columns | Core adventure-boss combat resource | ACTIVE_RUNTIME |
| `adventure_boss_progress` | Table (cleared/stars/attempts/best_score/cooldown) | Gates zone completion & star rating | ACTIVE_RUNTIME |
| `adventure_zone_unlocks` | Table | Gates which zones are enterable | ACTIVE_RUNTIME |
| Node mastery (purity/attempt_count/contaminated) | `grimoire_api.py` table | Drives spaced-repetition question resurfacing | ACTIVE_RUNTIME (no direct UI %) |
| `attr_atk/def/vis/prec` + `free_pts` | `user_stats` columns | Drives auto-title + adventure combat calc | ACTIVE_RUNTIME |
| `reset_tickets`, `tutorial_step`, `tour_done`, SP (`player_sp` table) | Columns/table exist | Consuming route not traced this pass | **UNKNOWN — flag for follow-up** |
| `user_stats.title` (legacy free-text) | Column | Superseded by `player_appearance.title_id` | LEGACY_UNUSED (unconfirmed) |

### B.2 Currencies / resources

| Resource | Exists | Status |
|---|---|---|
| **Coins** | YES — `user_stats.coins` + full `currency_log` audit ledger, daily-cap anti-farm | ACTIVE_RUNTIME |
| **Shop item quantities** (hint tickets, XP potions, streak shields, etc.) | YES — `shop_inventory` table | ACTIVE_RUNTIME |
| **SP (skill points)** | Schema exists (`player_sp` table), earn/spend routes not confirmed this pass | DATA_ONLY (follow-up needed) |
| Gold | NO — only a badge-rarity string literal, not a resource | CONCEPT_ONLY (name collision) |
| Gems / Diamonds | NO | Does not exist |
| Energy / Stamina | NO | Does not exist |
| Stars (as spendable currency) | NO — `adventure_boss_progress.stars` is a 0–3 rating, not spendable | Does not exist as currency |
| Scrolls / Tokens / Guild currency / Event currency / Premium credit / Reward points | NO | Does not exist |
| Premium Quest Tokens | YES, but narrow — scoped only to the Premium Weekly feature | ACTIVE_RUNTIME (not general currency) |

**Real currency count: 2** (coins + shop item stock as a resource ledger). Everything else on the reference
concept diagrams (gems, energy, passes as a currency) **does not exist in code**.

### B.3 Premium/Subscription

- `users.plan` (`'free'`/`'premium'`) + `users.premium_until`, centralized expiry check `check_premium_expiry()`.
- Two fully separate payment providers, both writing into the same `subscriptions` table via a `provider` column:
  **NewebPay** (TWD, local) and **PayPal** (USD, overseas). Confirmed: no code path credits coins from a payment —
  premium purchase only sets `plan`/`premium_until`.
- Premium-only content found: 6 stat-bonus cosmetic items (`robe_premium`, `hat_premium`, `aura_premium`,
  `pet_premium`, `title_premium`, `acc_premium`) + 2 premium badges + `radiant` stone/board skins + `sage` character.
- No premium-gated adventure zones or exclusive bosses found — adventure progression is keyed purely on Elo/placement.
- Separate one-time trial-code redemption system (`trial_codes` table) also grants premium status, independent of payment.

---

## Phase C — Avatar/Hero system

- **10 base characters** (`hero.html:3405-3416`, duplicated in `index.html:6762-6774` — already drifted, i18n
  names present in one copy but missing in the other).
- **No body-type/skin-tone/face/hair customization exists at all.** Gender presentation is baked into character
  choice, not a separate slot.
- **Renderer**: layered static `<img>` CSS z-index stacking onto a fixed 1056×1408 "mannequin" — **not** Canvas,
  SVG, or a true sprite-sheet system. Positioning lookup tables (`GEAR_BBOX`, `GEAR_ANCHOR`, `CHAR_BODY`) are
  computed in code but never applied — dead code. The only true frame-based sprite animation is the separate
  pet/companion system (hero.html:2490-2716).
- **Pet slot** is declared in the data model but hard-disabled (forced to `'none'` — see also `combat_pet` dead field
  in Phase D).
- **Ownership**: `player_wardrobe` (Postgres, insert-only — no trade/sell/delete route exists anywhere).
- **Equipped state**: `player_appearance` — one scalar column per slot, no multi-item stacking per slot.
- Items are **not purely cosmetic**: gear grants real stat bonuses (xp/drop bonus) that can lapse server-side if a
  player is later found under-qualified, even while still visually equipped.
- **Hero vs. Adventure Map**: there is no separate Adventure Map template — the map is embedded in `index.html`,
  and map nodes show zone emoji, **not** the player avatar. `play.html` (actual gameplay) has no full-body avatar
  at all.
- **Three divergent avatar-rendering generations coexist**: (a) a dead 6-key legacy character/armor overlay scheme
  (CSS remnants in `index.html`), (b) the current 10-key combat-gear system, independently duplicated between
  `hero.html` and `index.html` and already out of sync, (c) an older color+emoji nav-badge scheme still live on
  `play.html`. `inventory.html`/`badges.html` are orphaned pages with zero inbound links, superseded by `/hero` tabs.

**E9 reuse classification:**

| Subsystem | Classification |
|---|---|
| Character choice + wardrobe ownership/equip data model (`player_wardrobe`/`player_appearance`) | REUSE AS-IS |
| `COMBAT_GEAR` tier progression logic (gates, stat bonuses) | REUSE DATA, REDRAW ART |
| Layered `<img>` CSS renderer itself | LEGACY ONLY (replace renderer, keep data) |
| Dead positioning lookup tables (`GEAR_BBOX`/`GEAR_ANCHOR`/`CHAR_BODY`) | REMOVE LATER |
| Legacy 6-key character/armor overlay scheme in `index.html` | REMOVE LATER |
| `inventory.html`/`badges.html` static pages | REMOVE LATER (superseded) |
| `combat_pet` field | REMOVE LATER (always `'none'`, no catalog) |

---

## Phase D — Equipment & cosmetics

Full per-item table: [e9_existing_equipment_catalog.csv](e9_existing_equipment_catalog.csv) (282 rows, all 8
source catalogs, deduplicated by `item_id` within each catalog namespace).

### Catalog map

| Catalog | Items | Rendered today? |
|---|---|---|
| `APPEARANCE_DEFS` | 64 | Yes — drop/streak/rank/premium cosmetics (outfit/hat/back/accessory/pet/aura/title) |
| `BADGE_DEFS` | 84 | Yes — achievement badges, emoji-only |
| `COMBAT_GEAR` (hero.html) | 78 | Yes — 10 characters + 7 tiered slots × up to 10 tiers |
| `STONE_SKINS` | 5 | Yes |
| `BOARD_SKINS` | 5 | Yes |
| `EQUIPMENT_DEFS` | 15 | **No — dead code.** Real stat-affecting weapon/armor/accessory items served by `/api/player/inventory*`, but no template/JS calls those endpoints |
| `SKILL_DEFS` | 10 | **No — dead code.** Same non-use pattern as EQUIPMENT_DEFS |
| Shop consumables | 21 | Yes (not cosmetic/equipment, listed for completeness) |

**Total distinct catalog-backed items: 261** (excl. consumables) / **282** (incl. consumables).
**Currently rendered: 251. Dead/orphaned backend-only: 25** (EQUIPMENT_DEFS + SKILL_DEFS).

### Asset existence — systemic finding

`git ls-files assets/` returns **zero tracked files**. Every asset path referenced by `COMBAT_GEAR`
(`/assets/hero/gear_v2/*.webp`, `/assets/hero/characters/*.webp`, `/assets/hero/accessories/*.webp`) and shop
consumables (`/assets/shop/*.webp`) is **unverifiable from this repository** — the entire `assets/` directory is
untracked by git. Per ADR-0001, production identity/asset provenance cannot be inferred from local tooling files,
so this is marked **UNKNOWN**, not confirmed-missing. `APPEARANCE_DEFS` and `BADGE_DEFS` render via inline emoji
and have no binary asset dependency (unaffected by this gap).

### Known defects (real bugs, not design choices)

1. `aura_moon` (unlock_rank 2d) and `aura_celestial` (unlock_rank 5d) declare rank-based unlocks that
   `RANK_APPEARANCE_UNLOCKS` never actually grants — **structurally unobtainable items**.
2. `combat_pet` DB column/payload field always hardcoded `'none'` — dead weight, no catalog, no UI.
3. `frame`, `stone`-as-item, `board`-as-item slots are reserved in the profile API's `slot_map` but **zero**
   `APPEARANCE_DEFS` items use those slot values — always empty arrays.
4. Rarity vocabulary is inconsistent: `common/uncommon/rare/epic/legendary` (appearance/equipment/skins) vs.
   `bronze/silver/gold/legendary` (badges) — two unreconciled scales.
5. `badge_lb_weekly_1` is explicitly commented in source as "Phase 3B, not yet actually granted" — vaporware.

---

## Phase E — Monsters, Bosses, Zones

Full 10-zone matrix: [e9_zone_monster_matrix.csv](e9_zone_monster_matrix.csv)

Three separate, only loosely connected systems share monster/boss vocabulary — **do not conflate them**:

| System | Persistence | Purpose |
|---|---|---|
| `monster_taxonomy.py` name pools | None (computed at question-enrich time) | Flavor-text names attached to questions by `stage`; "boss" here just means "last question in a chapter/book" |
| Battlefield roster (`_BATTLEFIELD_ROSTER`) | Real: `battlefield_monster`, `monster_kill_log`, `monster_kill_history` | The actual daily HP/ATK combat loop; advances on a global `kill_count % 20` index, **not zone-scoped** |
| Adventure zone bosses (`ADVENTURE_ZONES`/`ADVENTURE_BOSS_META`) | Real: `adventure_boss_progress`, `adventure_zone_unlocks` | The pass/fail zone-unlock exam (20 Qs, pass ≥16); gates progression, no HP/damage/loot |

- **20 stable battle monsters** with real HP/ATK (80HP/2ATK up to 2800HP/40ATK), reward = flat coins + loot roll +
  appearance-item roll on kill. Kill logs/history are real persisted DB rows, not computed.
- **10 stable, DB-persisted adventure bosses**, one per canonical zone. **No confirmed direct coin/XP reward** on
  boss defeat — the handler (`adventure_boss_finish`) only writes `cleared/stars/attempts/best_score`.
- **10/10 canonical zones already have both a monster and a boss mapping** — no zone requires new monster design.
- Monster/boss art asset existence is **UNKNOWN** (same untracked `assets/` gap as Phase D) — flag for the deploy
  governance track, not a confirmed defect.

---

## Phase F — Quests, Rewards, Shop, Community

| System | Status |
|---|---|
| Daily Challenge | ACTIVE_RUNTIME — real tables, real reward path, real UI |
| Daily quests | ACTIVE_RUNTIME |
| **Weekly quests** | **Does not exist** — only hit is an unrelated premium-weekly-report email-token mechanism |
| **Login streak** | **Does not exist** as its own feature — closest analog is the daily-challenge *submission* streak |
| Adventure missions | ACTIVE_RUNTIME |
| Boss rewards | **PARTIAL** — progress/star tracking only, no confirmed coin/XP payout |
| Achievements | ACTIVE_RUNTIME |
| Shop | ACTIVE_RUNTIME |
| Inventory/Backpack | **DATA_ONLY** — real backend (`/api/player/inventory`, `/api/player/wardrobe`) fully implemented, but the mounted `/inventory` page is a static "COMING SOON" stub that never calls it |
| Leaderboard | ACTIVE_RUNTIME |
| **Guild** | **Does not exist** — no table, no membership route; "guild" is purely decorative flavor text/asset naming reused from the quest-board/adventure-map skin |
| Community rewards | Read-side ACTIVE_RUNTIME; **grant pipeline is manual-only** (CLI tools under `tools/`); an automatic scheduler exists only on unmerged feature branches, not on `master` |
| Battle log | ACTIVE_RUNTIME under a different name (`game_records`) |
| Soul records / question records | Does not exist as a user feature — only internal admin-only ID-matching helpers |
| SRS | ACTIVE_RUNTIME |
| Mistakes/weakness | ACTIVE_RUNTIME |

Notable surprise: the Inventory page is backwards from the usual pattern — a fully live backend sits behind a
dead stub UI, rather than the more common "UI ahead of backend."

---

## Phase G — New small-card UI data matrix

| UI Card | Verified real data available | Recommendation |
|---|---|---|
| Player card (name/avatar/level/rank/premium/streak) | display name, `rank_level`, `go_rank`, `is_premium()`, `current_streak`, equipped title (`player_appearance.title_id`) | REUSE AS-IS |
| Resource row | `coins` only as a real spendable currency; XP/streak/rank as status, not currency | Show coins + XP/streak as **status chips**, not a 4-currency row — gems/energy/passes are **PLACEHOLDER — DO NOT IMPLEMENT** |
| Left nav: Adventure Map | `index.html` embedded map, real `adventure_zone_unlocks`/`adventure_boss_progress` | REUSE AS-IS |
| Left nav: Character/Hero | `/hero` route, real wardrobe data | REUSE AS-IS (redraw renderer per Phase C) |
| Left nav: Equipment | Same wardrobe/appearance tables as Hero — no separate system | REUSE AS-IS |
| Left nav: Backpack/Inventory | Real backend exists (`/api/player/inventory`, `/api/player/wardrobe`) but current page is a stub — this is the one card that's *more* ready than its own UI suggests | REUSE DATA, build real UI |
| Left nav: Missions | Daily quest/daily challenge routes are real | REUSE AS-IS |
| Left nav: Shop | `shop.html`, real catalog/buy/gacha | REUSE AS-IS |
| Left nav: Guild | Does not exist | **PLACEHOLDER — DO NOT IMPLEMENT** (or relabel as Community/Leaderboard, which is real) |
| Right card: Daily Challenge / Daily quests | Real | REUSE AS-IS |
| Right card: Boss progress | Real (`adventure_boss_progress`) | REUSE AS-IS |
| Right card: Weekly reward | Does not exist | **PLACEHOLDER — DO NOT IMPLEMENT** |
| Right card: Login streak | Does not exist (use daily-challenge submit streak instead) | Relabel to existing streak field |
| Right card: SRS due count | Real (`/api/srs/due`) | REUSE AS-IS |
| Right card: Weakness summary | Real (`/api/mistakes/stats`) | REUSE AS-IS |
| Bottom dock: Leaderboard | Real | REUSE AS-IS |
| Bottom dock: Achievements | Real (`badges.html`/`/api/badges/*`) | REUSE AS-IS |
| Bottom dock: Question records | No "soul records" user feature; game history exists under `game_records` | Relabel, don't invent |
| Bottom dock: Friends | `friendships` table exists (per Phase F guild/community findings) | REUSE AS-IS (verify scope if used further) |
| Bottom dock: Guild | Does not exist | **PLACEHOLDER — DO NOT IMPLEMENT** |
| Start Challenge CTA | Zone/node selection, rank range, locked/cleared/boss-ready state all real via `adventure_boss_progress`/`adventure_zone_unlocks` | REUSE AS-IS |

---

## Final classification (Section XI)

**A. REUSE AS-IS**: coins + ledger, XP/rank/streak/combo stats, `player_wardrobe`/`player_appearance` ownership
model, `APPEARANCE_DEFS` cosmetics, `COMBAT_GEAR` unlock-gate logic (not its renderer), Badges, Daily
Challenge/Quests, Shop, Leaderboard, SRS, Mistakes, all 10 adventure zones + bosses + battlefield monsters,
Premium/subscription plumbing.

**B. REUSE DATA, REDRAW ART**: the 10 base characters and 7 tiered gear slots (keep item_id/ownership/progress/API,
replace the layered-`<img>` renderer and the two divergent `hero.html`/`index.html` copies with one canonical
data-driven renderer); monster art (data/HP/rewards real, art asset pipeline unverified).

**C. REQUIRES NEW SYSTEM**: Weekly quests, Guild, Gems/Energy/any second currency, automated community-reward
scheduling on `master`, boss-defeat direct reward (currently absent), body/face/hair avatar customization.

**D. DO NOT INCLUDE IN E9 MVP**: `EQUIPMENT_DEFS`/`SKILL_DEFS` (dead combat-stat system), legacy 6-key
character/armor overlay in `index.html`, dead positioning lookup tables, `combat_pet` field, `inventory.html`/
`badges.html` static stub pages (superseded), `frame`/`stone`/`board`-as-collectible empty slots.

---

## Executive Summary — direct answers

1. **Real currencies today: 2** — coins (with full ledger) and shop-item stock as a spendable resource. (SP is
   schema-only/unconfirmed.)
2. **Real non-currency player values: 13** — xp, rank_level, rank_xp(legacy), go_rank, elo_rating/provisional,
   streak/max_streak, combo_streak/max_combo, total_correct, mistake_corrected, player_hp/max_hp, adventure boss
   progress, adventure zone unlocks, node mastery, attribute points.
3. **Concept-diagram resources that do not exist**: gems, diamonds, energy, stamina, scrolls, tokens-as-currency,
   guild currency, event currency, premium credit, reward points, "gold" (name collision only with badge rarity).
4. **Base Avatars: 10** chibi characters.
5. **Avatar renderer**: layered static `<img>` CSS z-index stacking on a fixed mannequin — not Canvas/SVG/sprite
   sheet; positioning lookup tables exist but are dead code.
6. **Total distinct equipment/cosmetic items: 261** (excl. consumables) / **282** incl. shop consumables.
7. **Per-category counts**: Outfit 12, Head/Hat 10, Back 8, Accessory(appearance) 8, Accessory(combat,dead) 5,
   Weapon(dead) 5, Armor(dead) 5, Pet 7, Aura 6, Title 13, Badge 84, Combat-gear tiers+characters 78, Stone Skin 5,
   Board Skin 5.
8. **Missing/orphaned assets**: 0 items have a *confirmed-present* binary asset (`asset_exists=true`); 148 items
   need none (emoji/CSS); 99+ items reference `/assets/...` paths that are unverifiable because the entire
   `assets/` directory is untracked by git in this repo.
9. **Do equipment items affect stats?** Yes for ~148 of them (COMBAT_GEAR tiers, some APPEARANCE_DEFS auras/robes/
   pets/accessories, plus the 25 dead EQUIPMENT_DEFS/SKILL_DEFS items) — equipment is **not** purely cosmetic.
10. **Monsters/Bosses today**: 20 stable battlefield monsters (real HP/ATK/rewards) + 10 stable adventure-zone
    bosses (real, DB-persisted progress).
11. **10-zone mapping**: **10/10 zones already have a real monster and a real boss** — no zone requires new
    monster design.
12. **Cards that can plug directly into production data today**: Player card, Adventure Map, Hero/Character,
    Equipment, Backpack/Inventory (data ready, UI is the gap), Missions, Shop, Daily Challenge, Boss progress, SRS
    due count, Weakness summary, Leaderboard, Achievements, Start Challenge CTA.
13. **Cards that must be removed/placeholder-only for E9 MVP**: any multi-currency resource row beyond coins,
    Guild, Weekly reward card, Login-streak-as-a-distinct-feature (relabel to daily-submit streak instead), "Soul
    records" naming (relabel to game history).
14. **Legacy Hero ownership reusable into E9**: the entire `player_wardrobe`/`player_appearance` data model, all
    261 catalog items and their unlock conditions, and the `COMBAT_GEAR` tier-gate logic — only the visual
    renderer needs replacing.
15. **Hard constraints the E9.0 Design Bible must respect**: exactly 2 real currencies (not 4); 10 base characters
    with no face/hair/body customization layer; 261 real catalog items across 3 overlapping-but-distinct item
    systems that need reconciling before new art is commissioned; all 10 adventure zones already have canonical
    monster/boss identities that should not be redesigned from scratch; the binary asset pipeline for hero/monster
    art is unverifiable from this repo and must be confirmed via the (separately gated) deployment/asset
    provenance audit before assuming any asset exists in production.

---

## Verification

```
git status --short   -> see below (only new audit docs added; no tracked files modified)
git diff --stat       -> no diff against tracked files (new files only, no existing file modified)
git diff --check      -> clean
```

Tests run (closest existing coverage to the audited systems; no dedicated Hero/Avatar/Equipment/Adventure/
Monster/Boss test suite exists in this repository at time of audit):

```
tests/test_premium_weekly_compat.py
tests/test_premium_weekly_scheduler_default_safety.py
tests/test_index_xp_hud_guard.py
-> 6 passed, 0 failed
```

No full production test suite was run (docs-only audit; per governance instructions, only directly related
existing tests were selected).

## Tracked working-tree status

This repository has substantial pre-existing untracked content (backup folders, log files, KataGo binaries, DB
files, node_modules, etc.) unrelated to this audit — none of it was touched, created, or removed by this work.
The only files added by this audit are the four listed below, all under `docs/planning/`.

## Changed files (this audit)

- `docs/planning/e9_existing_system_inventory_audit.md` (this file)
- `docs/planning/e9_existing_system_inventory_snapshot.json`
- `docs/planning/e9_existing_equipment_catalog.csv`
- `docs/planning/e9_zone_monster_matrix.csv`

---

```
E9-PREFLIGHT-01: READY FOR OWNER REVIEW
```

Do not deploy. Do not modify runtime. Do not merge. Do not begin E9.1 until this audit is reviewed by the owner.
Next steps after review: E9.0 Avatar Design Bible v1.1, E9.0 Map Layout Contract, E9.0 RWD & Monster Placement
Contract — each of which must respect the real counts and constraints established here.
