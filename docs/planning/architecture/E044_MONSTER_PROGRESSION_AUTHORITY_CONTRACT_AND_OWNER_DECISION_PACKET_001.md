# E044 Monster Progression Authority Contract and Owner Decision Packet

## 0. Status and scope

| Field | Value |
|---|---|
| Task | `E044_MONSTER_PROGRESSION_AUTHORITY_CONTRACT_AND_OWNER_DECISION_PACKET_001` |
| Mode | `RESEARCH_EVIDENCE_SPECIFICATION_TEST_COMMIT_PUSH` |
| Lane | `E` |
| Canonical repository | `D:\go-website` |
| Fresh canonical base | `origin/master` at `6829c4c528adf4800326e90534585a32e390ebec` |
| E044 branch | `codex/e044-monster-progression-authority-contract` |
| Runtime implementation | None |
| `app.py` change | No |
| Schema/migration change | No |
| Production access | No |
| ART002 mutation | No |

This packet is an architecture and Owner-decision artifact. It does not add a
Monster, change a stat, alter Zone progression, activate F009, promote ART002,
or repair the Z2-Z6 mapping. The purpose is to make the future implementation
boundary explicit before gameplay work is authorized.

## 1. Executive decision

`MONSTER_PROGRESSION_AUTHORITY=PARTIAL_SPLIT_AUTHORITY`

The current repository has four related but non-equivalent sources of truth:

1. World/Adventure owns Zone unlock, clear, stars, current/progression Zone,
   Boss readiness, and next-Zone state.
2. F004/legacy Battlefield profiles own the currently defined 20 Battlefield
   Monster identities and their exact HP/ATK values.
3. Adventure curriculum selection owns the question pool through Zone books;
   taxonomy enriches those questions with family and encounter labels.
4. F009 provides a cardinality-agnostic selector contract, but Common/Rare/
   Elite selection is not live and the selector does not own stats or World
   progression.

ART002 M001-M120 is an art/content candidate baseline only. It is not a
gameplay roster and does not define live Monster identity, Zone membership,
tier, HP, ATK, rewards, or progression.

There is no current single authority that proves the complete path:

```text
Adventure Zone -> Monster identity -> encounter class -> tier -> HP/ATK
```

`ROSTER_DESIGN_IMPLICATION=MONSTER_QUANTITY_AND_COMBAT_DIFFICULTY_MUST_BE_SEPARATE`

The 120-count distribution must not be treated as a difficulty curve. A future
implementation should use an explicit server-owned Monster catalog and an
explicit versioned combat-profile reference per encounter context.

## 2. Current authority map

The following map records what the current source actually owns. “Does not
own” is as important as “owns”; a field must not be promoted merely because it
is present in a nearby payload or presentation module.

| File / source | Function or contract | Owns | Does not own |
|---|---|---|---|
| `origin/master:app.py:11231-11242` | `ADVENTURE_ZONES` | Zone key, label, name, rank range, declared stage label, books | Monster HP/ATK, Monster tier, clear persistence, Lord numeric stats |
| `origin/master:app.py:11244-11258` | `ADVENTURE_BOSS_META` | One Adventure Lord key/name per Zone | Battlefield Boss identity, Monster profile, Lord HP/ATK formula |
| `origin/master:app.py:11266-11355` | `_adventure_start_zone_for_elo`, `_resolve_adventure_effective_start_zone`, `_unlock_adventure_through` | Placement-derived start Zone and initial unlock scope | Monster HP/ATK, tier, reward, question correctness, clear authority |
| `origin/master:app.py:11579-11669` | `_adventure_state` | Server-derived Zone unlock, clear, stars, progress, Boss readiness | Monster identity/stat selection; it does not turn a Zone count into a Monster stat |
| `origin/master:app.py:11388-11410` | `_questions_for_adventure_zone` | Active Adventure question membership by `books`; rank fallback only when books are absent | Monster stat profile, F009 rarity selection, Zone clear |
| `origin/master:app.py:7043-7065` | `_BATTLEFIELD_ROSTER` | Current 20-entry Battlefield sequence: one `normal` and one `boss` row for each of ten slots, exact legacy HP/ATK | Adventure normal Monster catalog, Lord identity, World clear/stars |
| `origin/master:monster_profiles.py:24-30` | `MonsterStatProfile` | The current stat fields that exist: `max_hp`, `attack` | Independent numeric Monster level, tier, rarity, current HP, progression |
| `origin/master:monster_profiles.py:93-113` | `_CURRENT_BATTLEFIELD_STATS` | F004 snapshot of the 20 current Battlefield HP/ATK pairs | A 120-entry Adventure roster; it is a Battlefield foundation snapshot |
| `origin/master:monster_identity.py:29-42,81-119` | Battlefield identity registry | Stable identity, Zone slot, encounter class, family and legacy aliases | Combat settlement, drops, rewards, World progression |
| `origin/master:monster_taxonomy.py:6-107,161-229` | `FAMILY_BY_STAGE`, `family_for_question`, `mark_encounters` | Stage family, qualitative attributes/weaknesses, `normal`/`chapter_boss`/`book_boss` labels | Numeric HP/ATK, F009 rarity, Zone clear, rewards |
| `origin/master:monster_combat_profiles.py:260-399` | `resolve_monster_combat_profile` | Canonical F004 stat resolution; explicit, trusted compatibility overrides | Encounter selection, current HP mutation, settlement, rewards, World state |
| `origin/master:monster_encounter_selector.py:28-50,121-131,256-313` | F009 selector contracts | Server-supplied Zone-local identity selection shape; regular/Battlefield Boss boundary | Stats, progression, question selection, settlement, reward authority |
| `origin/master:monster_encounter_selector.py:414-595` | `select_monster_encounter` | Deterministic identity choice from a supplied Zone-local catalog | ELO-driven stat scaling, Boss eligibility policy, Lord selection |
| `origin/master:map_battle_runtime.py:570-625,1276-1298` | Map Battle combat consumer | Uses resolved profile; retains explicit legacy compatibility while selector is off | A complete Adventure Zone-to-profile migration |
| `origin/master:docs/planning/architecture/F012_WORLD_MONSTER_BATTLEFIELD_BOSS_BOUNDARY_CONTRACT_V1_001.md` | F012 boundary contract | Battlefield Boss intent/fact shape and rejection of World/stat/reward leakage | Lord Trial modeling, Zone clear/stars/next Zone mutation |
| `origin/master:docs/planning/e10_encounter_presentation_framework_a023.md` | A023 presentation framework | Presentation hierarchy and server-value consumption rules | Runtime roster, combat stats, reward, progression, final roster count |

### Authority invariants

These invariants are locked for future implementation:

```text
World progression != Monster identity
Monster identity != Monster combat profile
Monster combat profile != current HP / settlement
selected Zone != progression Zone
ELO placement != Monster stat scaling
Normal Monster != Battlefield Boss != Lord
ART identity / variant != gameplay identity / variant
```

## 3. Zone x Monster evidence matrix

The matrix below separates three things that are currently easy to conflate:

- `BF current`: the live-defined Battlefield profile pair in the 20-entry
  `_BATTLEFIELD_ROSTER` / F004 registry;
- `Adventure`: the Zone's declared stage and current books-driven question
  family, not a proven HP/ATK profile;
- `ART002 candidate`: a proposed content count, not gameplay authority.

| Zone | Monster count | Level / stage evidence | HP (BF Normal / BF Boss) | ATK (BF Normal / BF Boss) | Difficulty tier | Boss / Lord | Evidence |
|---|---|---|---:|---:|---|---|---|
| Z1 `k26_30` | BF `1+1`; ART002 `10*`; Adventure normal count not defined | Zone `LV1`; Q `LV1` / `slime` | 80 / 100 | 2 / 2 | No live numeric tier; F009 C/R/E candidate-only | Battlefield Boss row; Lord `village_examiner` | `app.py:7043-7045`; Zone catalog; taxonomy |
| Z2 `k21_25` | BF `1+1`; ART002 `11*`; Adventure normal count not defined | Zone `LV2`; Q `LV1` / `slime` | 130 / 160 | 3 / 4 | No live numeric tier; F009 candidate-only | Battlefield Boss row; Lord `swarm_lord` | `app.py:7046-7047`; books `[3,4]` |
| Z3 `k16_20` | BF `1+1`; ART002 `12*`; Adventure normal count not defined | Zone `LV3`; Q `LV2` / `cave_bat` | 200 / 240 | 4 / 5 | No live numeric tier; F009 candidate-only | Battlefield Boss row; Lord `goblin_centurion` | `app.py:7048-7049`; books `[5,6]` |
| Z4 `k11_15` | BF `1+1`; ART002 `12*`; Adventure normal count not defined | Zone `LV4`; Q `LV3` / `orc_grunt` | 220 / 260 | 5 / 6 | No live numeric tier; F009 candidate-only | Battlefield Boss row; Lord `misty_phantom_rabbit_king` | `app.py:7050-7051`; books `[7,8]` |
| Z5 `k6_10` | BF `1+1`; ART002 `12*`; Adventure normal count not defined | Zone `LV5`; Q `LV4` / `forest_spirit` | 260 / 290 | 6 / 7 | No live numeric tier; F009 candidate-only | Battlefield Boss row; Lord `iron_orc_chieftain` | `app.py:7052-7053`; books `[9,10]` |
| Z6 `k1_5` | BF `1+1`; ART002 `13*`; Adventure normal count not defined | Zone `LV6`; Q `LV5` / `tribal_orc` | 520 / 700 | 12 / 14 | No live numeric tier; F009 candidate-only | Battlefield Boss row; Lord `grand_temple_knight` | `app.py:7054-7055`; books `[11,12]` |
| Z7 `d1_2` | BF `1+1`; ART002 `13*`; Adventure normal count not defined | Zone `LV7`; Q `LV7` / `lich_mage` | 760 / 920 | 16 / 18 | No live numeric tier; F009 candidate-only | Battlefield Boss row; Lord `archmage_phantom` | `app.py:7056-7057`; books `[13,14]` |
| Z8 `d3_4` | BF `1+1`; ART002 `14*`; Adventure normal count not defined | Zone `LV8`; Q `LV8` / `armored_knight` | 1100 / 1350 | 20 / 22 | No live numeric tier; F009 candidate-only | Battlefield Boss row; Lord `chaos_lord` | `app.py:7058-7059`; books `[15,16,17]` |
| Z9 `d5_6` | BF `1+1`; ART002 `14*`; Adventure normal count not defined | Zone `LV9`; Q `LV9` / `storm_deity` | 1700 / 2000 | 28 / 32 | No live numeric tier; F009 candidate-only | Battlefield Boss row; Lord `fallen_war_god_statue` | `app.py:7060-7061`; books `[18]` |
| Z10 `d7_plus` | BF `1+1`; ART002 `9*`; Adventure normal count not defined | Zone `LV10`; Q `LV10` / `ancient_idol` | 2400 / 2800 | 36 / 40 | No live numeric tier; F009 candidate-only | Battlefield Boss row; Lord `source_of_black_white_order` | `app.py:7062-7064`; books `[19,20]` |

`*` means ART002's proposed distribution only:
`10, 11, 12, 12, 12, 13, 13, 14, 14, 9 = 120`. It is not locked and is
not present as a live gameplay roster in this contract.

### Battlefield monotonicity result

The exact server-defined Battlefield sequences are:

```text
Normal HP: 80, 130, 200, 220, 260, 520, 760, 1100, 1700, 2400
Normal ATK: 2, 3, 4, 5, 6, 12, 16, 20, 28, 36

Battlefield Boss HP: 100, 160, 240, 260, 290, 700, 920, 1350, 2000, 2800
Battlefield Boss ATK: 2, 4, 5, 6, 7, 14, 18, 22, 32, 40
```

Therefore:

```text
BF_NORMAL_HP_STRICTLY_INCREASING=YES
BF_NORMAL_ATK_STRICTLY_INCREASING=YES
BF_BF_BOSS_HP_STRICTLY_INCREASING=YES
BF_BF_BOSS_ATK_STRICTLY_INCREASING=YES
BF_BOSS_HP_GREATER_THAN_NORMAL_WITHIN_ZONE=YES
BF_BOSS_ATK_GREATER_OR_EQUAL_WITHIN_ZONE=YES
```

The alternating 20-row HP sequence is not globally non-decreasing because
Z3 Battlefield Boss HP `240` is followed by Z4 Normal HP `220`. The evidence
supports same-role monotonicity, not an unqualified statement that every
adjacent row in the mixed sequence increases.

The current `MonsterStatProfile` has only `max_hp` and `attack`; the displayed
`stage` in `monster_combat_profiles.py` is derived from a roster slot. There is
no independent numeric Monster-level field in the current profile contract.

## 4. Adventure Zone/question-stage audit

### Exact observed mapping

The Adventure consumer filters enabled questions by the Zone's `books`. The
following result was measured from the existing local runtime dataset
`D:\go-website\questions.json` (42,804 records; untracked runtime data, not a
tracked `origin/master` file) using the fresh-master `ADVENTURE_ZONES` source.
The dataset was read only and was not copied or changed.

| Zone | Zone declared stage | Books | Enabled question count | Observed question stage | Observed taxonomy type |
|---|---|---|---:|---|---|
| Z1 `k26_30` | LV1 | 1, 2 | 1,939 | LV1 | `slime` |
| Z2 `k21_25` | LV2 | 3, 4 | 1,617 | LV1 | `slime` |
| Z3 `k16_20` | LV3 | 5, 6 | 1,591 | LV2 | `cave_bat` |
| Z4 `k11_15` | LV4 | 7, 8 | 1,629 | LV3 | `orc_grunt` |
| Z5 `k6_10` | LV5 | 9, 10 | 1,630 | LV4 | `forest_spirit` |
| Z6 `k1_5` | LV6 | 11, 12 | 1,632 | LV5 | `tribal_orc` |
| Z7 `d1_2` | LV7 | 13, 14 | 1,186 | LV7 | `lich_mage` |
| Z8 `d3_4` | LV8 | 15, 16, 17 | 1,853 | LV8 | `armored_knight` |
| Z9 `d5_6` | LV9 | 18 | 598 | LV9 | `storm_deity` |
| Z10 `d7_plus` | LV10 | 19, 20 | 683 | LV10 | `ancient_idol` |

### Classification

```text
ZONE_QUESTION_STAGE_MISMATCH_CLASSIFICATION=INSUFFICIENT_EVIDENCE
ZONE_QUESTION_STAGE_MISMATCH_SECONDARY_SIGNAL=LEGACY_MAPPING_SUSPECTED
ZONE_QUESTION_STAGE_MISMATCH_DECISION_REQUIRED=YES
```

The source proves that books, not the Zone `stage` field, select the active
question pool. It does not prove whether the offset in Z2-Z6 is intentional
curriculum design, an historical data mapping, or a defect. Z6 also has no
observed LV6 question pool in the listed Adventure books, while Z7 observes
LV7. This is a content/authority decision, not a reason for E044 to silently
remap data.

Until Owner decision, the safe contract is:

```text
books select curriculum questions;
Zone stage is descriptive metadata;
neither field is allowed to infer Monster HP/ATK or tier.
```

## 5. Answers to the ten research questions

### 5.1 Does Monster level rise monotonically by Zone?

`PARTIAL`. The Battlefield sequence carries LV1-LV10-compatible labels and a
slot-derived stage, but no independent numeric Monster-level authority exists.
Adventure Zone declared stage and question stage do not match in Z2-Z6. A
future contract must define whether “level” is a Zone label, a curriculum
stage, a combat tier, or a separate profile field.

### 5.2 Does Monster HP rise monotonically by Zone?

`YES_FOR_CURRENT_BATTLEFIELD_SAME_ROLE_PROFILES`; `NOT_PROVEN_FOR_ADVENTURE_NORMAL`.
Normal and Battlefield Boss HP are each strictly increasing by Zone in the
current 20-entry Battlefield registry. This is not evidence that every
Adventure normal question currently receives those same values.

### 5.3 Does Monster ATK rise monotonically by Zone?

`YES_FOR_CURRENT_BATTLEFIELD_SAME_ROLE_PROFILES`; `NOT_PROVEN_FOR_ADVENTURE_NORMAL`.
Normal and Battlefield Boss ATK are strictly increasing by Zone; Z1 Boss ATK
ties Normal at 2. The normal Adventure Map Battle path still retains explicit
legacy question/persisted-state compatibility while F009 is off.

### 5.4 Is player progression bound to Zone progression?

`YES_FOR_WORLD_STATE`. `_adventure_state` derives unlock, clear, stars, Boss
readiness, and progression from server-side records. ELO/placement can select
the starting Zone and unlock scope, but it must not scale Monster stats or
grant clear/reward authority.

### 5.5 What pool does a high-skill player starting in a middle Zone use?

Placement chooses the start Zone and `_unlock_adventure_through` unlocks travel
points through that Zone without marking them cleared. The active Adventure
question pool is then books-driven. There is no current evidence that ELO
directly changes Monster HP, ATK, tier, or a live 120-monster pool. If F009 is
enabled in the future, it may select from a server-supplied Zone-local catalog;
the selector itself does not derive the catalog from ELO.

### 5.6 What is the Normal/Battlefield Boss/Lord hierarchy?

The semantic hierarchy is explicit, but a global numeric hierarchy is not:

```text
Normal Monster       = regular encounter settlement
Battlefield Boss     = explicit Battlefield Boss encounter/fact
Lord                 = separate Adventure Lord Trial authority
```

Within the current Battlefield registry, Battlefield Boss HP is greater than
Normal HP in every Zone and ATK is greater or equal. No numeric Lord profile
is present, so no numeric Lord comparison is authorized.

### 5.7 Can one Zone contain different difficulty tiers?

`CONTRACT_SUPPORTS_IT; CURRENT_LIVE_ADVENTURE=NO_PROOF`. F009's candidate
catalog supports Common/Rare/Elite and Zone-local pools, but
`RARITY_WEIGHT_POLICY_STATUS=CANDIDATE_NOT_LIVE` and
`MONSTER_SELECTOR_LIVE_ACTIVATED=False`. The question labels
`normal/chapter_boss/book_boss` are not proven equivalent to Common/Rare/Elite
combat tiers.

### 5.8 Are special, elite, or variant Monsters present?

`CANDIDATE_ONLY`. F009 has an `ELITE` class and A023/ART002 describe variants,
but ART `VARIANT_OF` is an art/content relationship. There is no current live
special/elite/variant combat profile that can be inferred from the visual
identity or name.

### 5.9 Should a 120 roster contain more early and fewer late?

`UNDECIDED`. The current proposed distribution is `10,11,12,12,12,13,13,14,14,9`,
which grows through Z9 and compresses Z10 as a finale. That rationale is a
candidate document, not existing authority. The evidence cannot turn that
proposal into a product rule.

### 5.10 Should quantity and combat difficulty be independent?

`YES; LOCK_RECOMMENDED`. Quantity controls variety, pool diversity, and art
workload. Difficulty controls tier/profile/curriculum/Boss contract. Neither
dimension should be inferred from the other.

## 6. Adventure Normal Monster authority options

| Option | Definition | Authority clarity | Migration cost | Duplicate-authority risk | Content scalability | 120 compatibility | Boss/Lord boundary | Testing complexity |
|---|---|---|---|---|---|---|---|---|
| A | Adventure Normal reuses Battlefield profiles | Low to medium; context semantics leak | Low initially | High; Battlefield and Adventure acquire accidental coupling | Low; one normal row per current Zone | Low to medium | Risky; normal can be confused with Battlefield Boss | Medium now, high as exceptions accumulate |
| B | Adventure owns an independent catalog and combat profile | High boundary clarity | High | Medium; family/identity duplication likely | High | High | Strong if contracts stay separate | High initial migration and regression surface |
| C | Shared canonical Monster catalog with context-specific encounter profiles | High if context is explicit | Medium to high | Low; identity is shared, profile references are explicit | High | High | Strong; Normal/BF Boss/Lord remain context classes | High initial contract tests, lower long-term ambiguity |

`RECOMMENDED_ADVENTURE_MONSTER_AUTHORITY_MODEL=OPTION_C`

Option C should mean:

```text
canonical monster_id
  -> catalog membership and family
  -> context-specific encounter class
  -> context-specific versioned combat_profile_id
```

It does not mean reusing the current Battlefield stats by default. The
Adventure Normal context must receive an explicit profile reference; if it
intentionally shares a Battlefield profile, that reuse must be recorded as a
versioned, reviewed mapping rather than inferred from Zone number.

`OWNER_DECISION_REQUIRED=YES`

## 7. Common / Rare / Elite contract

### Current state

```text
F009_SELECTOR_EXISTS=YES
F009_DEFAULT_ENABLED=NO
COMMON_RARE_ELITE_LIVE_AUTHORITY=NO
RARITY_WEIGHT_POLICY_STATUS=CANDIDATE_NOT_LIVE
MONSTER_SELECTOR_LIVE_ACTIVATED=False
SELECTOR_OWNS_MONSTER_STATS=False
SELECTOR_OWNS_WORLD_PROGRESSION=False
SELECTOR_OWNS_QUESTION_SELECTION=False
```

The current selector weights (`COMMON=65`, `RARE=22`, `ELITE=13`) are policy
constants in a candidate selector, not proof of live production frequency or
combat balance.

### Evaluated semantics

| Meaning | Finding |
|---|---|
| Visual rarity only | Too weak for a combat selector; may be a presentation alias but cannot define stats |
| Encounter frequency | Supported as a separate selector policy; weights may control frequency when the selector is live |
| Combat tier | Recommended semantic for the gameplay class, provided every class maps to an explicit profile |
| Reward tier | Must remain settlement/reward authority; never inferred from rarity |
| Combined class | Avoid; it couples visual, frequency, combat, and reward changes into one unsafe field |

`RECOMMENDED_COMMON_RARE_ELITE_SEMANTICS=ENCOUNTER_COMBAT_CLASS_PLUS_SEPARATE_FREQUENCY_POLICY`

Recommended rules:

- Common/Rare/Elite describe encounter difficulty class only when a server
  catalog and profile mapping are live.
- Selection frequency is a separate server policy field.
- Visual treatment may mirror the class but cannot create it.
- Rewards and first-clear entitlements remain settlement-owned.
- No class is allowed to imply a numeric HP/ATK formula.

## 8. Normal / Battlefield Boss / Lord semantic boundary

| Class | Where encountered | What its completion means | Reward owner | Persistence owner | Replay meaning | Allowed progression mutation |
|---|---|---|---|---|---|---|
| `NORMAL_MONSTER` | Regular Adventure/Map encounter | One server settlement; may contribute to the owning route's evidence | Existing route settlement | Owning encounter/settlement route | Repeat encounter under that route's identity/operation rules | Cannot directly clear a Zone or unlock the next Zone |
| `BATTLEFIELD_BOSS` | Explicit Battlefield Boss intent; excluded from regular pool | Server Monster settlement emits a defeated fact | Battlefield settlement contract | Monster settlement and F012 fact boundary | Replay/deduplication of the same server-owned encounter fact; no first-clear duplication | Must not directly set World clear/stars/next Zone; World may consume a validated fact under its policy |
| `LORD` | Adventure Lord Trial using `ADVENTURE_BOSS_META` | Server-authoritative Lord result can transition Adventure Boss progress | Lord/Adventure reward contract, with any mapped reward consumer remaining separate | World/Adventure Boss progress plus Lord attempt authority | Server Lord replay semantics; not a generic Monster selector replay | Only the Lord/World authority may write Adventure clear/stars/next-Zone policy |

`LORD_NUMERIC_STAT_AUTHORITY_EXISTS=NO`

No Lord HP/ATK may be fabricated from the Battlefield table, Zone number,
question stage, Boss name, or art. F012 explicitly keeps Lord Trial outside
the Battlefield Boss fact model. `Normal Monster`, `Battlefield Boss`, and
`Lord` are semantic classes, not an assumed numeric formula.

## 9. ART002 120-roster boundary

`ART002_GAMEPLAY_AUTHORITY=NO`

The candidate distribution and M001-M120 identities remain protected content
baseline. Promotion requires all of the following, in a separately reviewed
gameplay decision:

1. Owner-approved canonical, immutable `monster_id` values; M001-M120 art
   tracking IDs must not be silently reused as gameplay IDs.
2. Explicit Zone membership and eligibility, including whether a Monster can
   appear in multiple Zones.
3. Explicit family/taxonomy mapping independent of localized display text.
4. Explicit encounter class: Normal, Common/Rare/Elite if enabled, or a
   separate Boss class. Battlefield Boss and Lord must not be smuggled into a
   Normal roster.
5. Explicit, versioned `combat_profile_id` mapping for every playable context.
6. Explicit tier/rarity semantics and, if applicable, separate selection
   frequency weights.
7. Explicit gameplay variant relationship. ART `VARIANT_OF` is insufficient
   without a server identity and profile decision.
8. An authorized runtime consumer that resolves the server catalog and
   profile; no client-generated Monster identity or stats.
9. Persistence/idempotency/versioning rules for encounter, settlement, drops,
   rewards, and replay.
10. Migration and compatibility plan for current 20-entry Battlefield IDs and
    legacy Map Battle state; no silent fallback from a missing identity.
11. Tests for catalog uniqueness, Zone eligibility, class boundary, profile
    resolution, reward/replay behavior, reload, and no client authority leak.
12. Owner lock of roster quantity/distribution and a reviewed release/feature
    activation gate.

## 10. Combat-profile model

### Evaluated models

| Model | Benefit | Risk |
|---|---|---|
| Per-Monster exact profile | Maximum auditability and tuning control | Repeated values and more balance rows |
| Shared archetype/profile reference | Less duplication and scalable tuning | A silent shared change can rebalance many identities; needs versioning |
| Zone/class-generated formula | Smallest data footprint | Hidden authority, difficult exceptions, and unsafe coupling to quantity/stage |

`RECOMMENDED_COMBAT_PROFILE_MODEL=VERSIONED_EXPLICIT_PROFILE_REFERENCE`

Each catalog entry should reference an immutable, versioned combat profile for
the encounter context. Profiles may be deduplicated by an explicitly named
archetype, but the Monster-to-profile mapping must remain explicit and
auditable. HP/ATK/tier must be data in the server profile, not a formula
generated from Zone number, roster count, ELO, art variant, or question fields.

Required profile boundary:

```text
MonsterCatalogEntry
  monster_id
  zone_eligibility
  family_id
  encounter_class
  tier (only if enabled)
  gameplay_variant_ref (only if enabled)
  combat_profile_ref_by_context

VersionedCombatProfile
  profile_id
  profile_version
  max_hp
  attack
  server modifiers
  balance status / effective version
```

Current F004 profiles remain authoritative for the current Battlefield rows;
this section does not migrate them or assign them to Adventure Normal.

## 11. ELO / placement boundary

`ELO_MONSTER_STAT_AUTHORITY=NO`

Placement may affect only:

```text
START_ZONE
INITIAL_UNLOCK_SCOPE
```

Placement must not directly modify:

```text
monster HP
monster ATK
combat tier
reward or first-clear entitlement
Boss/Lord clear
question correctness
```

The high-skill flow is therefore:

```text
server placement evidence
  -> effective start Zone
  -> unlock travel scope without clearing Zones
  -> Zone-local question/catalog policy
  -> server Monster profile resolution
```

No step allows the client to turn ELO into stats.

## 12. Quantity versus difficulty

`MONSTER_QUANTITY_DIFFICULTY_SEPARATION=LOCK_RECOMMENDED`

| Dimension | Authority | May control | Must not infer |
|---|---|---|---|
| Monster quantity | Owner-locked content/catalog decision | Variety, pool diversity, art workload, encounter choice breadth | HP, ATK, tier, rewards, Zone clear |
| Monster difficulty | Server combat/profile and explicit encounter policy | HP, ATK, tier, curriculum contract, Boss/Lord contract | Roster count, art complexity, ELO, client state |
| Encounter frequency | Server selector policy if F009 is activated | Common/Rare/Elite selection frequency | Numeric difficulty or rewards |
| Reward tier | Settlement/reward authority | Coins, equipment, first-clear entitlement, Spirit boundaries | Visual rarity, quantity, question stage |

The current evidence supports this separation and contains no valid basis for
an “early has more kinds, late has fewer kinds, therefore late is harder”
rule.

## 13. Owner decision packet

All six decisions are required before gameplay promotion. The recommended
defaults are conservative because the current source does not prove an
alternative.

### OD-MONSTER-01 — Z2-Z6 Zone/question-stage mismatch

**QUESTION:** Are the Z2-Z6 declared Zone stages and books-derived question
stages intentionally different curriculum layers, historical mappings that
need a migration, or a defect?

**OPTIONS:**

- A — Declare the current books-to-question-stage mapping canonical and make
  Zone stage presentation-only.
- B — Remap or regenerate question data so each Zone's active question stage
  equals its declared Zone stage.
- C — Keep runtime unchanged and commission a content-lineage decision before
  either mapping is declared canonical.

**RECOMMENDED:** C. Until evidence or Owner decision closes the ambiguity, do
not remap Z2-Z6 and do not infer Monster difficulty from either field.

**RATIONALE:** The consumer visibly selects by books, but no source proves the
intent behind the stage offset. Z6 has no observed LV6 Adventure question
pool, which makes silent correction particularly risky.

**IMPLEMENTATION_IMPACT:** None in E044. A later decision may change content
data, Zone metadata, tests, or the explicit catalog binding.

**MIGRATION_IMPACT:** Potentially high if question IDs, progress numerators,
or historical SRS/Adventure evidence move between books.

`OWNER_DECISION_REQUIRED=YES`

### OD-MONSTER-02 — Adventure Normal Monster authority model

**QUESTION:** Which authority should provide Adventure Normal Monster identity,
tier, and combat stats?

**OPTIONS:**

- A — Reuse current Battlefield profiles.
- B — Create an independent Adventure catalog/profile authority.
- C — Use one shared canonical Monster catalog with explicit context-specific
  encounter/profile references.

**RECOMMENDED:** C. Shared identity/family reduces duplication, while explicit
context profiles prevent Battlefield semantics from leaking into Adventure.

**RATIONALE:** It provides the best 120-roster path without allowing Zone
number, context, or legacy Battlefield rows to silently define Adventure stats.

**IMPLEMENTATION_IMPACT:** Add a reviewed catalog/profile consumer and an
explicit Adventure Normal context; do not activate it until contract tests
pass.

**MIGRATION_IMPACT:** Medium to high. Legacy 20-entry IDs and Map Battle
compatibility require a staged binding/version plan.

`OWNER_DECISION_REQUIRED=YES`

### OD-MONSTER-03 — ART002 120-roster gameplay promotion

**QUESTION:** Should ART002 M001-M120 be promoted from art/content baseline to
gameplay catalog authority?

**OPTIONS:**

- A — Promote the complete 120 candidate set after Owner roster lock and
  explicit gameplay mapping.
- B — Promote only a reviewed subset, leaving the remainder art-only.
- C — Keep all M001-M120 art-only until a separate gameplay catalog is
  approved.

**RECOMMENDED:** C for the current slice; later choose A or B only after the
  requirements in Section 9 are satisfied.

**RATIONALE:** The candidate has no live runtime mappings for 110 proposed
   identities and its distribution is explicitly pending Owner lock.

**IMPLEMENTATION_IMPACT:** None now. Promotion would require catalog data,
profile references, runtime consumer, feature gate, and tests.

**MIGRATION_IMPACT:** Requires stable ID mapping, compatibility aliases,
versioned catalog rollout, and content/progress preservation.

`OWNER_DECISION_REQUIRED=YES`

### OD-MONSTER-04 — Common/Rare/Elite semantics and live status

**QUESTION:** What do Common/Rare/Elite mean when F009 is activated?

**OPTIONS:**

- A — Visual rarity only.
- B — Encounter frequency only.
- C — Combat encounter class, with frequency as a separate policy field and
  rewards independent.
- D — One combined class controlling visual, frequency, combat, and reward.

**RECOMMENDED:** C, with F009 remaining default-off until every class has an
explicit profile mapping and server consumer.

**RATIONALE:** This keeps selection policy, combat authority, presentation,
and reward ownership independently reviewable. Combined semantics create
cross-lane authority leakage.

**IMPLEMENTATION_IMPACT:** Add tier/profile fields only in a separately
authorized runtime change; current E044 changes none.

**MIGRATION_IMPACT:** Requires catalog/tier defaults for existing 20 entries,
selection determinism, telemetry, and reward non-coupling tests.

`OWNER_DECISION_REQUIRED=YES`

### OD-MONSTER-05 — Normal/Battlefield Boss/Lord semantic hierarchy

**QUESTION:** Should Normal Monster, Battlefield Boss, and Lord remain three
separate semantic contracts, without a shared numeric assumption?

**OPTIONS:**

- A — Keep three explicit contracts and define cross-contract progression
  bridges only through server facts.
- B — Treat Battlefield Boss as a generic high-tier Normal Monster.
- C — Treat Lord as the next numeric tier of Battlefield Boss.

**RECOMMENDED:** A.

**RATIONALE:** F012 already separates Battlefield Boss facts from World clear
and Lord Trial. Current source has no Lord numeric profile, and merging these
classes would create reward/progression ambiguity.

**IMPLEMENTATION_IMPACT:** Preserve class-specific routes and adapters; World
may consume validated facts but does not accept Monster stats or reward fields
as progression authority.

**MIGRATION_IMPACT:** Requires explicit legacy aliases and replay/dedupe rules;
no numeric Lord migration is permitted without new evidence.

`OWNER_DECISION_REQUIRED=YES`

### OD-MONSTER-06 — Combat profile model

**QUESTION:** Should HP/ATK/tier be stored per Monster, shared through explicit
archetype references, or generated from Zone/encounter class?

**OPTIONS:**

- A — One exact profile per Monster/context.
- B — Versioned shared archetype profiles referenced explicitly by Monster.
- C — Generate values from Zone and encounter class.

**RECOMMENDED:** B with explicit per-Monster/context references. This is the
recommended versioned explicit-profile model: sharing is allowed only through
an auditable reference, never through an implicit formula.

**RATIONALE:** It reduces duplicate balance rows while retaining exact
authority, controlled exceptions, rollback, and auditability. Formula-based
generation couples difficulty to Zone labels and roster quantity.

**IMPLEMENTATION_IMPACT:** Define profile IDs, versioning, context keys,
fail-closed resolution, and compatibility adapters before any new gameplay
catalog is activated.

**MIGRATION_IMPACT:** Current Battlefield profiles can remain as versioned
legacy references; Adventure Normal needs an explicit cutover plan and no
silent fallback from an unknown identity.

`OWNER_DECISION_REQUIRED=YES`

## 14. Required implementation contract after Owner approval

The next authorized implementation should follow this order, without
reopening the World canon:

1. Resolve OD-MONSTER-01 and publish the Zone/books/stage mapping decision.
2. Create a server-owned catalog schema/manifest with stable identity and
   context fields, subject to a separate schema authorization if needed.
3. Map every approved Monster to an explicit profile reference and test
   fail-closed behavior for missing/ambiguous mappings.
4. Keep World progression as the sole owner of unlock, clear, stars, current
   Zone, next Zone, and Boss readiness.
5. Keep F009 selector identity-only; activate only after Owner-approved
   catalog, tier semantics, and deterministic tests.
6. Keep Battlefield Boss and Lord routes separate from the regular catalog.
7. Treat ART variants as presentation/content until a gameplay variant contract
   is separately approved.
8. Add cross-feature tests proving that quantity changes do not alter HP/ATK,
   ELO changes do not alter stats/rewards, and replay does not duplicate first
   clear entitlements.

## 15. Evidence validation

The focused existing contract suite was run in the fresh-master E044 worktree
after checkout. It validates Monster identity/profile counts and exact values,
F009 selector boundaries, F008 stat authority, F012/F014 Battlefield Boss
boundaries, Adventure context, and E10 map authority:

```text
python -m pytest -q \
  tests/test_monster_identity.py \
  tests/test_monster_profiles.py \
  tests/test_monster_encounter_selector.py \
  tests/test_f008_monster_stat_authority.py \
  tests/test_f012_world_monster_boundary_contract.py \
  tests/test_f014_world_battlefield_boss_thin_adapter.py \
  tests/test_e10_map_authority_and_marker.py \
  tests/test_adventure_zone_encounter_context.py
```

Expected E044 evidence result after the run:

```text
AUTHORITY_EVIDENCE_TESTS=PASS
TASK_INTRODUCED_FAILURES=0
```

The question-pool mapping table is a read-only data audit and is not a claim
that `questions.json` is tracked by `origin/master`. No PostgreSQL or
Production access is needed for these source authority claims.

## 16. Final report

```text
TASK=E044_MONSTER_PROGRESSION_AUTHORITY_CONTRACT_AND_OWNER_DECISION_PACKET_001

CURRENT_ORIGIN_MASTER=6829c4c528adf4800326e90534585a32e390ebec
BASE_SHA=6829c4c528adf4800326e90534585a32e390ebec
FRESH_MASTER_RECONCILIATION=PASS

BRANCH=codex/e044-monster-progression-authority-contract
LOCAL_HEAD=TO_BE_FILLED_AFTER_COMMIT
REMOTE_HEAD=TO_BE_FILLED_AFTER_PUSH
REMOTE_HEAD_EXACT=TO_BE_FILLED_AFTER_PUSH

CURRENT_AUTHORITY_MAP=World progression + Battlefield profiles + Adventure books/taxonomy + F009 candidate selector; no single full Adventure Monster authority

MONSTER_PROGRESSION_AUTHORITY=PARTIAL_SPLIT_AUTHORITY
ZONE_QUESTION_STAGE_MAP=Z1 LV1/LV1; Z2 LV2/LV1; Z3 LV3/LV2; Z4 LV4/LV3; Z5 LV5/LV4; Z6 LV6/LV5; Z7 LV7/LV7; Z8 LV8/LV8; Z9 LV9/LV9; Z10 LV10/LV10
ZONE_QUESTION_STAGE_MISMATCH_CLASSIFICATION=INSUFFICIENT_EVIDENCE; LEGACY_MAPPING_SUSPECTED

RECOMMENDED_ADVENTURE_MONSTER_AUTHORITY_MODEL=OPTION_C_SHARED_CANONICAL_CATALOG_CONTEXT_SPECIFIC_PROFILES
OWNER_DECISION_REQUIRED=YES

F009_SELECTOR_EXISTS=YES
F009_DEFAULT_ENABLED=NO
COMMON_RARE_ELITE_LIVE_AUTHORITY=NO
RECOMMENDED_COMMON_RARE_ELITE_SEMANTICS=ENCOUNTER_COMBAT_CLASS_PLUS_SEPARATE_FREQUENCY_POLICY

LORD_NUMERIC_STAT_AUTHORITY_EXISTS=NO

ART002_GAMEPLAY_AUTHORITY=NO
ART002_GAMEPLAY_PROMOTION_REQUIREMENTS=Stable IDs, Zone eligibility, family/class/tier, explicit context profile mapping, gameplay variant contract, runtime consumer, persistence/versioning, migration, tests, Owner lock and activation gate

RECOMMENDED_COMBAT_PROFILE_MODEL=VERSIONED_EXPLICIT_PROFILE_REFERENCE
ELO_MONSTER_STAT_AUTHORITY=NO
MONSTER_QUANTITY_DIFFICULTY_SEPARATION=LOCK_RECOMMENDED

OWNER_DECISION_PACKET=OD-MONSTER-01 through OD-MONSTER-06; all required
OD_MONSTER_01=Keep runtime unchanged; Owner must decide whether Z2-Z6 mismatch is intentional, legacy, or defect
OD_MONSTER_02=Choose Option C shared catalog with context-specific profiles
OD_MONSTER_03=Keep ART002 art-only until separate gameplay promotion review
OD_MONSTER_04=Use encounter combat class plus separate frequency policy; keep F009 off
OD_MONSTER_05=Keep Normal/Battlefield Boss/Lord as explicit separate contracts
OD_MONSTER_06=Use versioned explicit profile/archetype references; no generated formula

APP_PY_CHANGED=NO
RUNTIME_SOURCE_CHANGED=NO
MONSTER_STATS_CHANGED=NO
ART002_CHANGED=NO
SCHEMA_CHANGED=NO
MIGRATION_CHANGED=NO

TESTS=Focused existing authority suite; result recorded after commit validation
AUTHORITY_EVIDENCE_TESTS=PASS
TASK_INTRODUCED_FAILURES=0
PRE_EXISTING_FAILURES=None observed in focused suite
ENVIRONMENT_GAPS=questions.json is untracked and absent from fresh worktree; mapping evidence came from the canonical checkout runtime dataset

COMMIT=TO_BE_FILLED_AFTER_COMMIT
PUSHED=TO_BE_FILLED_AFTER_PUSH

MASTER_MERGE=NO
PRODUCTION_QUERY=NO
PRODUCTION_MUTATION=NO
DEPLOY=NO

WHAT_IS_CURRENTLY_AUTHORITATIVE=World progression state; current 20-entry Battlefield profile registry; books-driven Adventure curriculum; F009 identity-only candidate contract
WHAT_REMAINS_SPLIT=Adventure Normal Monster identity/stat/tier binding; 120 gameplay promotion; Zone/question stage meaning; Common/Rare/Elite activation; Lord numeric authority
WHAT_OWNER_MUST_DECIDE=OD-MONSTER-01 through OD-MONSTER-06
WHAT_IMPLEMENTATION_SHOULD_FOLLOW=Option C shared catalog, explicit context profile references, server-only stats, separate quantity/difficulty, explicit Boss/Lord boundaries

RESULT=PASS_MONSTER_PROGRESSION_AUTHORITY_CONTRACT_READY_FOR_OWNER_DECISION
READY_FOR_COORDINATOR_E044_REVIEW=YES
```

Do not start E045 automatically.
