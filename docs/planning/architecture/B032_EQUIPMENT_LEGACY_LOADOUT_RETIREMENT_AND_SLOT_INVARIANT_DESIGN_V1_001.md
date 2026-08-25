# B032 Equipment Legacy Loadout Retirement and Slot Invariant Design

Task: B032_EQUIPMENT_LEGACY_LOADOUT_RETIREMENT_AND_SLOT_INVARIANT_DESIGN_V1_001

Canonical master: b75308d44806bb7c2e2b131a73ba06a71c188b3c

Authoritative B031 reference: 9f2f86f4478c243c04c344e16805e5f17f99774e

Scope: read, analyze, data-invariant design, legacy-retirement design, docs
only.

No runtime, app.py, frontend, schema, migration, Production, deployment, or
merge change was made.

## Executive decision

The canonical functional Equipment path is:

player_inventory ownership
→ POST /api/player/inventory/equip
→ app.py:equip_item
→ player_inventory.equipped
→ _get_authoritative_combat_stats
→ server EQUIPMENT_DEFS

The eight player_appearance.combat_* columns are not B021 functional combat
authority. They are a legacy persisted loadout-like projection. They still
matter because:

1. app.py:skills_character is a live writer;
2. _get_appearance_effects reads them and turns legacy _tN keys into XP/drop
   bonuses during review/profile flows;
3. social and visual surfaces transport or render several of the fields;
4. hero.html keeps a localStorage copy and posts the fields back to the legacy
   route.

The player_inventory table also lacks a database-enforced effective-slot
invariant. The normal PostgreSQL equip route serializes and replaces a slot
correctly, but malformed/direct state can still be stored. Accepted B028-R1
fails closed when reading such state; it does not prevent creation.

### Recommended decisions

RECOMMENDED_LEGACY_DISPOSITION=COMPATIBILITY_READ_ONLY

Freeze new legacy combat_* writes and retire their gameplay-adjacent XP/drop
effect before a new Loadout Command Service is exposed. Keep compatibility
reads only while the visual/social bridge is active. Do not automatically
translate legacy visual keys into functional Equipment IDs.

SLOT_INVARIANT_STRATEGY=A

Use an additive nullable canonical_slot projection plus both database gates:

1. a partial unique constraint for equipped rows:
   UNIQUE(user_id, canonical_slot) WHERE equipped=true AND
   canonical_slot IS NOT NULL;
2. an equipped-row validity constraint equivalent to:
   equipped=false OR canonical_slot IS NOT NULL.

The projection is not a second definition authority; EQUIPMENT_DEFS remains
the server definition authority. The validity constraint is required because
the partial unique constraint alone does not reject an equipped row whose
canonical_slot is NULL.

EQUIPPED_TRUE_REQUIRES_CANONICAL_SLOT=YES

## Exact current source map

| Concern | Current source | Actual behavior |
| --- | --- | --- |
| Equipment ownership | app.py player_inventory | Acquisition and admin grant insert rows; ownership is tied to user_id |
| Functional equipped state | player_inventory.equipped | Canonical player equip route mutates it |
| Functional slot | EQUIPMENT_DEFS[equip_id].slot | Server-resolved; no database slot column exists |
| Functional combat | app.py:_get_authoritative_combat_stats | Reads active player_inventory rows and server definitions; deliberately ignores player_appearance.combat_* |
| Legacy combat-field writer | app.py:skills_character | Updates only supplied combat_* columns after _gear_unlocked checks |
| Legacy gameplay-adjacent reader | app.py:_get_appearance_effects | Converts legacy _tN suffixes into XP/drop bonuses |
| Appearance API | app.py:get_appearance | Returns combat_armor, combat_cape, combat_weapon, combat_offhand; raw combat_hat/pet/aura/acc are not returned there |
| Social projection | app.py:_row_loadout and social routes | Leaderboard, friends, and DM projections include most legacy combat fields |
| Browser cache | hero.html, bot.html, index.html, curriculum.html | localStorage and API callers are presentation/cache surfaces, not functional Equipment authority |
| Read conflict policy | accepted B028-R1 | Conflicted canonical slot is unresolved; no arbitrary winner |

Current schema and route anchors:

- app.py:4720 creates player_inventory with id, user_id, equip_id,
  equipped, obtained_at, source.
- app.py:4728 creates only idx_inv_user(user_id).
- app.py:5281-5288 adds the eight legacy combat_* columns to
  player_appearance.
- app.py:16888-16929 contains equip_item and its PostgreSQL row lock,
  slot-wide clear, target set, and commit.
- app.py:7050-7149 contains the canonical functional combat resolver.
- app.py:2756-2800 contains the legacy appearance effect reader.
- app.py:17507-17558 contains the legacy combat-field route writer.

The complete field and consumer matrix is in:

docs/planning/architecture/b032_equipment_legacy_consumer_matrix.json

## Legacy field-by-field disposition

All eight fields currently receive the same interim disposition:

COMPATIBILITY_READ_ONLY

That does not mean they are safe gameplay authority. It means:

- stop adding new writes in a later implementation;
- preserve read compatibility for existing social/visual consumers while a
  bridge is prepared;
- remove the legacy XP/drop effect rather than silently carrying it into the
  new command service;
- retire the columns only after all consumers are bridged and an owner has
  approved the data lifecycle.

### combat_weapon

Written by skills_character and hero.html. Read by _get_appearance_effects,
get_appearance, social loadout projections, and bot.html. It contributes legacy
XP and visual weapon layers. It has no player_inventory ownership binding and
no EQUIPMENT_DEFS slot validation. Do not map weapon_tN to a functional weapon
automatically.

### combat_armor

Written by skills_character and hero.html. Read by _get_appearance_effects,
get_appearance, social projections, and bot.html. It contributes legacy drop
bonus and visual armor layers. B021 armor mitigation does not use it.

### combat_cape

Written by skills_character and hero.html. Read by _get_appearance_effects,
get_appearance, social projections, and bot.html. It contributes legacy XP
bonus and is not a canonical functional Equipment slot.

### combat_offhand

Written by skills_character and hero.html. Read by _get_appearance_effects,
get_appearance, social projections, and bot.html. It contributes legacy drop
bonus and is not a canonical functional Equipment slot.

### combat_hat

Written by skills_character. It is read by _get_appearance_effects and social
loadout projections. It contributes legacy XP bonus. It is distinct from the
cosmetic hat_id field and is not returned as a raw field by get_appearance.

### combat_pet

Written by skills_character, although the current hero save path sends pet as
none. It is read by _get_appearance_effects and social projections. It
contributes legacy drop bonus. It is distinct from user_pets, Spirit, and
cosmetic pet_id.

### combat_aura

Written by skills_character. It is read by _get_appearance_effects and social
projections. It contributes legacy XP bonus. It is distinct from cosmetic
aura_id.

### combat_acc

Written by skills_character and sent by hero.html. It is read by
_get_appearance_effects and contributes legacy drop bonus. It is not currently
included in get_appearance or _row_loadout, making its persisted state
especially unsuitable as a stable public contract.

## Legacy retirement design

### Phase 1: freeze and measure

No existing field is mutated by B032. A later implementation should:

1. stop accepting combat_* as a gameplay mutation in skills_character, or
   explicitly ignore those fields while preserving character_key behavior;
2. record how many non-empty legacy rows exist per field;
3. run the malformed-data detector below;
4. identify social/visual consumers that still need compatibility reads;
5. make the legacy XP/drop effect disposition an explicit owner decision.

The current _gear_unlocked check is not an ownership check. It confirms
rank/total_correct eligibility only. It must not be presented as functional
Equipment ownership validation.

### Phase 2: separate visual compatibility from gameplay

The desired bridge is:

legacy player_appearance.combat_* read
→ presentation-only compatibility adapter
→ social/visual renderer

The legacy fields must not flow into:

- B021 damage or mitigation;
- Equipment ownership;
- player_inventory.equipped;
- D5C item-use;
- new command-service result authority.

The legacy XP/drop bonuses should be retired or replaced by an explicitly
server-owned rule before the new Loadout Command Service is cut over. B032
does not choose a replacement balance rule.

### Phase 3: retire

After all callers are bridged:

1. make the legacy fields read-only or return a deprecation marker;
2. stop writing them from hero.html and skills_character;
3. remove raw-field social projections;
4. verify no gameplay helper reads them;
5. only then schedule column removal in a separate owner-approved migration.

No data backfill into player_inventory is recommended by default. The legacy
keys represent visual tier assets such as armor_tN and cape_tN, not necessarily
the functional Equipment IDs in EQUIPMENT_DEFS. Automatic translation would
create false ownership or combat power.

## Slot invariant options

### Option A: normalized canonical_slot plus partial unique constraint

Add a nullable canonical_slot projection to player_inventory. The migration
backfills it from the server-controlled EQUIPMENT_DEFS mapping. Non-equippable
or unknown IDs remain outside the effective equipped set and are detected
separately.

canonical_slot may remain NULL for an unequipped non-functional ownership row,
an unknown historical row awaiting repair, or another non-equippable item.
It must never remain NULL when equipped=true. In particular,
go_stone_black is canonical_slot=NULL and inventory-only, so equipped=true is
forbidden. xp_amulet remains HOLD_FOR_AUTHORITY; until an effect authority is
approved it is not functionally equippable, and equipped=true is malformed and
must fail closed.

Strategy A has two independent storage gates. First, add an equipped-row
validity constraint equivalent to:

equipped = false OR canonical_slot IS NOT NULL;

The second gate is the effective-slot uniqueness constraint. Add the
equivalent of:

CREATE UNIQUE INDEX player_inventory_one_equipped_slot
ON player_inventory(user_id, canonical_slot)
WHERE equipped = 1 AND canonical_slot IS NOT NULL;

The exact migration must use repository dialect conventions and must not run
until the duplicate detector is clean or every exception has an explicit
owner-approved repair record.

Advantages:

- the database enforces the target invariant;
- an equipped row cannot silently persist without a canonical slot;
- the user/slot lookup is indexable;
- all known app writers can populate the projection;
- B028-R1 remains a read-time fail-closed safety net.

Risks:

- canonical_slot must stay synchronized with EQUIPMENT_DEFS;
- every insert/update writer must be audited;
- malformed historical rows must be handled before index creation;
- the validity constraint and unique index must be added only after the
  equipped-null detector and explicit repair/quarantine gate pass;
- SQLite test support needs an explicit compatibility path.

This is the recommended design.

### Option B: generated or derived database slot

A generated expression or functional index could map equip_id to slot. The
problem is that the current definition authority is Python EQUIPMENT_DEFS, not
a database catalog. PostgreSQL cannot have a generated expression consult that
Python registry. A CASE expression would duplicate the catalog in the schema,
and every new Equipment definition would require synchronized database work.

This creates a second slot-definition representation and is rejected for the
current architecture.

### Option C: command writer and reconciliation only

Centralize equip, unequip, and replacement in one command service, retain the
current user row lock, and reject malformed rows. This is useful as an
application safety layer but does not provide a hard invariant while direct
admin/acquisition/import writers or manual database writes remain possible.

It is insufficient as the only invariant for the current topology.

## Malformed data detection and repair

B032 defines read-only detection only. It does not run these queries against
Production and does not repair local or remote data.

The detector should materialize a deterministic equip_id-to-slot mapping from
EQUIPMENT_DEFS and run these classes:

1. Duplicate equipped weapon: join equipped player_inventory rows to the
   mapping, group by user_id and slot=weapon, and select HAVING COUNT(*) > 1.
2. Duplicate equipped armor: same query with slot=armor.
3. Duplicate equipped accessory: same query with slot=accessory.
4. Unknown equip_id: equipped player_inventory LEFT JOIN mapping where the
   mapping is null.
5. EQUIPPED_WITH_NULL_CANONICAL_SLOT: equipped rows whose server-derived
   canonical_slot projection is NULL. This is a migration preflight blocker
   for the equipped-row validity constraint and is classified as FAIL_CLOSED
   + EXPLICIT_REPAIR.
6. go_stone_black equipped: equipped rows with equip_id=go_stone_black.
7. xp_amulet equipped: equipped rows with equip_id=xp_amulet, classified as
   HOLD_FOR_AUTHORITY review state rather than activated effect.

Default remediation:

FAIL_CLOSED + EXPLICIT_REPAIR

Do not use latest-wins, lowest-id-wins, highest-rarity-wins, or an arbitrary
first row. Do not auto-unequip or delete ownership rows in B032. An owner-
approved maintenance command may later choose a winner or clear a slot in one
audited transaction, but that is a separate implementation and authorization
gate.

The detector is a preflight gate for both constraints. A migration must stop
before constraint creation when unresolved duplicate effective slots,
EQUIPPED_WITH_NULL_CANONICAL_SLOT rows, unknown equipped IDs, or the locked
go_stone_black/xp_amulet states remain. No repair may auto-select a winner.

## Command-service ordering

SHOULD_LOADOUT_COMMAND_SERVICE_BE_BUILT_BEFORE_INVARIANT=NO

The command service should not be treated as a substitute for a database
invariant. It can be implemented as part of the staged rollout, but the
invariant design, historical detector, and writer inventory must be accepted
first.

SHOULD_LEGACY_COMBAT_FIELDS_BE_RETIRED_BEFORE_SERVICE=YES for writes and
gameplay-adjacent effects. Compatibility reads may remain temporarily while
visual/social consumers are bridged.

SHOULD_SCHEMA_MIGRATION_PRECEDE_ROUTE_CENTRALIZATION=CONDITIONAL

Safe order:

1. freeze legacy gameplay writes/effects and decide legacy bonus retirement;
2. detect malformed player_inventory state;
3. add a nullable canonical_slot projection;
4. backfill known functional Equipment from EQUIPMENT_DEFS;
5. update all app writers and the future command boundary;
6. explicitly repair or quarantine duplicate same-slot equipped rows, unknown
   equip_id rows, equipped rows with NULL canonical_slot, go_stone_black
   equipped rows, and xp_amulet equipped rows;
7. prove that no equipped row has canonical_slot NULL;
8. add the equipped-row validity constraint;
9. add the partial unique user plus canonical-slot constraint;
10. centralize the command service and continue the rollout; keep read
    compatibility until visual migration is complete, then retire legacy
    columns in a later migration.

An additive projection can precede route centralization only while the
constraints are not yet enforcing. Both final constraints must follow writer
coverage, malformed-state repair/quarantine, and clean-data proof.

## Locked boundaries

The following remain unchanged:

- Equip is not consume.
- Equip is not acquisition.
- D5A is not D5C.
- xp_amulet remains HOLD_FOR_AUTHORITY.
- go_stone_black remains TROPHY, inventory-only, no combat power, and not
  equippable.
- equipped=true requires canonical_slot IS NOT NULL; an equipped NULL-slot
  row is invalid storage and must fail closed.
- B021 combat continues to use player_inventory.equipped and EQUIPMENT_DEFS.
- B028-R1 conflict reads continue to fail closed.
- No second functional combat Equipment authority is created.

## Validation evidence

Static/source validation on b75308d44806bb7c2e2b131a73ba06a71c188b3c found:

- 8 legacy combat fields.
- 1 production server writer: skills_character.
- 1 frontend field writer: hero.html saveLoadoutToServer.
- 10 grouped server/read surfaces, with bot/community/messages as visual
  consumers.
- 3 player_inventory mutation families: monster settlement acquisition,
  admin grant/remove, and canonical equip/unequip.
- No normal equip reference to D5C item_use_operations or ITEM_USE.
- No player_inventory slot column or effective-slot unique constraint.
- _get_authoritative_combat_stats does not consult player_appearance.combat_*.

Existing Equipment-focused tests may be rerun as regression evidence. B032
adds no tests and makes no runtime change.

## Final report

CURRENT_ORIGIN_MASTER=b75308d44806bb7c2e2b131a73ba06a71c188b3c

LEGACY_COMBAT_FIELDS_COUNT=8

LEGACY_WRITERS_COUNT=1 production server writer

LEGACY_READERS_COUNT=10 grouped server/read surfaces

SECOND_FUNCTIONAL_COMBAT_AUTHORITY=NO

RECOMMENDED_LEGACY_DISPOSITION=COMPATIBILITY_READ_ONLY

SLOT_INVARIANT_STRATEGY=A

EQUIPPED_TRUE_REQUIRES_CANONICAL_SLOT=YES

PARTIAL_UNIQUE_SLOT_CONSTRAINT=YES

EQUIPPED_SLOT_VALIDITY_CONSTRAINT=YES

EQUIPPED_NULL_SLOT_DETECTOR=YES

AUTO_DESTRUCTIVE_REPAIR=NO

SCHEMA_MIGRATION_RECOMMENDED=YES

BACKFILL_REQUIRED=YES

AUTO_DESTRUCTIVE_REPAIR=NO

LOADOUT_COMMAND_SERVICE_BEFORE_INVARIANT=NO

LEGACY_COMBAT_FIELDS_RETIRED_BEFORE_SERVICE=YES for writes/effects

SCHEMA_MIGRATION_BEFORE_ROUTE_CENTRALIZATION=CONDITIONAL

XP_AMULET_HOLD_PRESERVED=YES

GO_STONE_BLACK_TROPHY_PRESERVED=YES

APP_PY_CHANGED=NO

SCHEMA_CHANGED=NO

PRODUCTION_MUTATION=NO

DEPLOY=NO

MASTER_MERGE=NO
