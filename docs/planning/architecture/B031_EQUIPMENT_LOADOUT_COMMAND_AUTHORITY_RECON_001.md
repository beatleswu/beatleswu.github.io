# B031 Equipment Loadout Command Authority Recon

Task: B031_EQUIPMENT_LOADOUT_COMMAND_AUTHORITY_RECON_001
Repository: D:\go-website
Base: 58d9b7047f285751a048fc551c955909c87984ac
Mode: read, analyze, command/authority recon, static validation, docs only

## Outcome

The canonical functional Equipment authority is already clear for the normal
player equip path:

player_inventory ownership
→ /api/player/inventory/equip
→ server EQUIPMENT_DEFS slot/effect resolution
→ player_inventory.equipped
→ B021 _get_authoritative_combat_stats

The route performs a same-slot replacement atomically on its PostgreSQL
transaction. It does not consume the item and it does not use D5C.

The authority is not globally closed, however. The player_inventory schema has
no database-enforced one-effective-item-per-slot constraint, and a separate
legacy /api/skills/character path stores client-selected player_appearance
combat_* fields. Those legacy fields are not consumed by the B021 damage
resolver, but _get_appearance_effects can derive legacy XP/drop effects from
them. This is a separate loadout projection and an open client-authority
finding.

Recommendation:

RECOMMENDATION_C=FIX_DATA_INVARIANT_BEFORE_COMMAND_SERVICE

First close or explicitly retire the legacy loadout split and decide how the
one-slot invariant is to be enforced. Then create a route-agnostic loadout
command service if a single API boundary is still desired. That service must
reuse player_inventory and B021; it must not create another inventory or
combat authority.

## Canonical source map

| State or behavior | Current source | Authority / mutation | Legacy behavior or gap |
| --- | --- | --- | --- |
| Equipment definitions | app.py, EQUIPMENT_DEFS | Server definition registry; 15 unique IDs across weapon, armor, accessory | No client stat/value authority |
| Ownership | player_inventory | Acquisition/admin grant insert rows; user ownership is checked by user_id | Inventory rows can exist unequipped |
| Equipped state | player_inventory.equipped | app.py:equip_item | Schema does not enforce one effective slot |
| Slot | EQUIPMENT_DEFS[equip_id].slot | Server-resolved in equip_item | Client slot fields are ignored by canonical route |
| Functional effect | EQUIPMENT_DEFS plus _FUNCTIONAL_EFFECT_ACTIVE_KEYS | B021 _get_authoritative_combat_stats and active effect helpers | No frontend combat authority |
| Read conflict behavior | Accepted B028-R1 read model | Conflict slot has no effective equipped item | Detects malformed state after the fact; does not prevent every direct write |
| Persistent HP | Existing user/player state used by its owning combat paths | Not part of this Equipment command | Encounter HP remains a separate boundary |
| Legacy appearance loadout | player_appearance.character_key and combat_* | /api/skills/character | Separate client-selected projection; not canonical B021 equipment |
| Item use | item_use_operations.py / D5C | D5C ITEM_USE operation authority | Normal equip does not call it |
| Reward/acquisition lineage | Existing settlement/acquisition path; D5A where explicitly wired | Separate from equip and D5C | Functional equipment drop currently visibly inserts player_inventory directly |

The accepted B028-R1 source at
2c8b879a8667c0247c23e560475ee29fafad508d remains the read-model reference for
conflict fail-closed behavior. B031 does not modify or duplicate that reader.

## Equipment catalog locks

The current app.py EQUIPMENT_DEFS contains 15 unique definitions:

- Weapons: wooden_sword, iron_sword, fox_fang, dragon_claw, celestial_blade
- Armor: cloth_robe, leather_armor, fox_pelt, dragon_scale, void_mantle
- Accessories: lucky_stone, xp_amulet, fox_mask, dragon_eye, go_stone_black

All definitions use one of the canonical slots: weapon, armor, or accessory.

The following locks remain unchanged:

- xp_amulet: HOLD_FOR_AUTHORITY; it has no active functional effect key.
- go_stone_black: TROPHY, inventory-only, no combat power, not equippable.
- Equip is not acquisition and equip is not consumption.
- D5A reward/acquisition lineage is not D5C item-use authority.

## Current mutation topology

### Canonical player equip and unequip

The only player-facing functional writer is:

app.py:equip_item
route: POST /api/player/inventory/equip

The request accepts inv_id and action. The canonical route does not accept
client-supplied slot, item class, attack, defense, mitigation, rarity, or
effect values.

For both actions it first selects the inventory row by id and authenticated
user_id. A missing or unowned row returns an error. It then resolves the row's
equip_id through the server EQUIPMENT_DEFS map, validates the canonical slot,
and rejects go_stone_black.

For action=equip, the PostgreSQL path:

1. locks the user's inventory rows with SELECT ... FOR UPDATE;
2. resolves all definition IDs in the target slot on the server;
3. clears equipped=0 for those same-slot IDs;
4. sets equipped=1 on the requested owned inventory row;
5. commits one transaction.

For action=unequip, it sets equipped=0 on the requested owned row and commits.
The database wrapper rolls back on an exception. The route also has an explicit
commit on success.

This gives the canonical route a PASS for same-slot replacement and
transactional route behavior. It does not give the database a permanent
invariant, because the table has only a primary key and a user index:

player_inventory(id, user_id, equip_id, equipped, obtained_at, source)

There is no slot column and no unique or partial unique constraint representing
user plus effective slot.

### Acquisition and administrative writers

Monster/drop progression inserts player_inventory rows with equipped=0.
The admin equipment grant inserts an unequipped row after server definition
validation. The admin remove path deletes a user-owned inventory row. These
are ownership mutations, not player equip commands, but they are additional
direct writers outside a future loadout command service.

### Legacy loadout writer

app.py:skills_character at POST /api/skills/character accepts
character_key and combat_* fields and writes player_appearance. The route
validates character_key and unlock conditions, but does not bind the
combat_* identifiers to player_inventory ownership or EQUIPMENT_DEFS slots.

This path is not B021 functional equipment authority:

- B021 _get_authoritative_combat_stats reads player_inventory.equipped and
  server EQUIPMENT_DEFS.
- player_appearance combat_* values are not used for the canonical B021
  damage/mitigation calculation.
- _get_appearance_effects nevertheless derives legacy XP/drop effects from
  appearance and combat_* state.

Therefore this is not a second B021 damage engine, but it is a second
persisted loadout-like projection with gameplay-adjacent effects. The
client-authority boundary is not closed across the whole application.

## Command matrix

The machine-readable command matrix is in
docs/planning/architecture/b031_equipment_loadout_command_matrix.json. Its
rows cover acquisition, admin ownership mutation, canonical equip, canonical
unequip, same-slot replacement, and the legacy loadout writer.

| Command | Route/function | Ownership | Slot/effect resolution | Transaction | Idempotency | Status |
| --- | --- | --- | --- | --- | --- | --- |
| acquire_drop | _update_monster_and_quests | Server settlement context | Server drop definition | Caller transaction | Count-based duplicate suppression, no operation identity | Acquisition only |
| admin_grant | admin_set_equipment | Admin and target user | EQUIPMENT_DEFS membership; inserted unequipped | Single commit | None | Admin acquisition |
| admin_remove | admin_set_equipment | id plus target user | No slot transition | Single commit | None | Admin ownership mutation |
| equip | equip_item action=equip | id plus authenticated user_id | EQUIPMENT_DEFS slot; trophy rejection | PostgreSQL row lock, slot clear, target set, commit | Desired-state only | Canonical functional equip |
| unequip | equip_item action=unequip | id plus authenticated user_id | Server definition validation | Update and commit | Desired-state only | Canonical functional unequip |
| replace_same_slot | equip_item action=equip | Same as equip | Server clears all IDs in target slot | Same as equip | Desired-state only | No distinct route |
| legacy_loadout_save | skills_character | No player_inventory binding for combat_* | Legacy key/unlock checks | Update and commit | Last-write-wins | Secondary projection; open gap |

## Authority and forgery audit

For the canonical /api/player/inventory/equip route:

- Ownership: PASS; inventory row is selected with authenticated user_id.
- Slot validation: PASS; slot is resolved from EQUIPMENT_DEFS.
- Item class: server-resolved; no client item class is accepted.
- Attack, defense, damage reduction, crit multiplier, effect key, and effect
  value: server-resolved from EQUIPMENT_DEFS and the functional-effect
  allowlist.
- Equipped result: server-written and returned.
- Client-supplied extra fields: not used as gameplay authority.

For /api/skills/character, the client can choose combat_* keys that are
persisted into player_appearance without player_inventory ownership binding.
The route does not let the client submit raw numeric damage, but the
client-selected legacy key can affect _get_appearance_effects. This is:

LOADOUT_CLIENT_AUTHORITY_VIOLATION

It must be resolved by a later authorized task; B031 does not modify it.

## Atomic slot invariant

Target invariant:

for each user plus canonical slot, effective equipped identity count <= 1

The three layers are different:

1. DATABASE_CONSTRAINT: absent. The current schema cannot guarantee the
   invariant if a direct writer or malformed import inserts multiple equipped
   rows.
2. TRANSACTION_LOGIC: present in the canonical PostgreSQL equip route. It
   locks the user's rows, clears the target slot, sets the requested row, and
   commits as one transaction.
3. READ_MODEL_FAIL_CLOSED: present in accepted B028-R1. A slot with more
   than one equipped candidate is unresolved, and no item in that conflicted
   slot is projected as effectively equipped.

Conclusion:

SAME_SLOT_ATOMIC_REPLACEMENT=PASS for the canonical route
ONE_EFFECTIVE_ITEM_PER_SLOT_GUARANTEED=NO globally
MUTATION_CONFLICT_PREVENTION_GAP=YES

B028-R1 prevents a malformed state from becoming an arbitrary effective read
model winner. It does not prevent the malformed state from being stored.

## Equip versus D5C item use

Normal equip and unequip do not decrement quantity and do not call
item_use_operations.py. Static inspection found no D5C reference in the
canonical equip route.

D5C remains the ITEM_USE authority for consumable/resource mutation. It must
not be overloaded for ordinary loadout state. No third inventory source should
be introduced.

## Combat propagation

The exact B021 functional combat chain is:

app._get_authoritative_combat_stats
→ active player_inventory rows with equipped=1
→ server EQUIPMENT_DEFS and _FUNCTIONAL_EFFECT_ACTIVE_KEYS
→ canonical battle settlement

The resolver reads the database state at combat time. It does not consume
frontend localStorage, Hero appearance, Shop display selection, or client
submitted stat values. Equipment changes therefore propagate to the next
canonical settlement without a second combat stat authority.

The legacy _get_equip_effect and _get_appearance_effects helpers remain in
other legacy paths. They must not be mistaken for the B021 combat authority.

## UI and caller topology

### inventory.html

The functional Backpack surface fetches /api/player/inventory and stores the
result in an in-memory functionalEquipmentItems list. Its action handler posts
only inv_id and action to /api/player/inventory/equip. After a successful
server response it reloads the inventory. This local array is presentation
cache, not durable authority.

### hero.html

The Hero surface also fetches /api/player/inventory for functional equipment.
Separately it keeps hero_combat_gear_v1 in localStorage and posts the visual
loadout to /api/skills/character. The localStorage path is a second client-side
cache/projection and must not be promoted to B021 combat authority.

### wearable renderer

js/rpg_wave2_wearable_renderer.js consumes server-projected equipped data and
marks presentation authority as server_equipped_projection. It does not write
inventory state.

Conclusion:

BACKPACK_LOCAL_STATE_DUPLICATION=transient presentation duplication, not a
durable authority
HERO_VISUAL_LOADOUT_PRESENTATION_ONLY=YES for character/appearance rendering
SECOND_FUNCTIONAL_COMBAT_EQUIPMENT_AUTHORITY=NO
SECOND_PERSISTED_LOADOUT_PROJECTION=YES via player_appearance.combat_*

## Idempotency decision

Equip and unequip are set-desired-state commands, not increment operations.
Repeating equip X or unequip X converges to the same final state and does not
stack the B021 effect. The current route therefore has useful natural
idempotence.

It does not provide:

- caller-owned operation_id;
- canonical payload hash;
- durable original-result replay;
- changed-payload conflict;
- durable operation audit.

No new operations table should be added automatically. A later command-service
task should first decide whether exact response replay is required. If the
product/API contract requires it, that task needs a narrowly scoped durable
operation authority, without replacing player_inventory ownership or D5C.

## Recommendation

RECOMMENDATION_C=FIX_DATA_INVARIANT_BEFORE_COMMAND_SERVICE

Evidence:

1. The normal functional route is already a reasonable server-authoritative
   desired-state command.
2. The storage layer does not enforce one effective item per canonical slot.
3. A separate /api/skills/character writer accepts client-selected legacy
   combat_* keys without player_inventory ownership binding.
4. B028-R1 safely exposes malformed conflicts but cannot prevent their creation.

The next authorized step should close or explicitly retire the legacy
player_appearance combat_* gameplay-adjacent path and establish the intended
one-slot invariant. After that, a route-agnostic Equipment Loadout Command
Service is reasonable if multiple routes need one stable command boundary.
Such a service must call the existing authority; it must not create another
inventory, equipped-state store, D5C replacement, or combat stat calculator.

## Static validation and regression evidence

Static validation on current master:

- EQUIPMENT_DEFS: 15 definitions, 0 duplicate IDs, all slots canonical.
- Active functional effect IDs: all resolve to known definitions.
- xp_amulet active functional effect keys: none.
- go_stone_black active functional effect keys: none.
- Canonical equip ownership query: present.
- Canonical server slot resolution: present.
- Trophy rejection: present.
- PostgreSQL user-row lock: present.
- Same-slot clear and target set/unset: present.
- Canonical equip commit: present.
- D5C reference in equip route: absent.
- B028-R1 conflict policy: verified from accepted source.

Focused regression evidence:

- tests/test_rpg_wave2_gate2_equipment_backpack.py: 7 passed.
- tests/test_rpg_b021_equipment_combat_loop.py: 21 passed.
- tests/test_rpg_wave2_lane_b_functional_equipment_presentation_wiring.py:
  6 passed.
- tests/test_rpg_wave2_gate2_cross_lane_integration.py: 5 passed.
- tests/test_rpg_wave1_lane_a_combat_equipment.py: 7 passed, 1 pre-existing
  failure.
- Combined relevant run: 40 passed, 1 pre-existing failure.

The pre-existing failure is
test_equipped_armor_reduces_retaliation_and_unequip_restores_baseline. Its
legacy fixture expected player_dmg=20 and current result was 2. B031 did not
modify runtime or tests and introduced no failures.

## Explicit non-scope

B031 changes no app.py, frontend, combat, inventory mutation, D5 module,
schema, migration, production database, feature flag, deployment, or merge.

The JSON companion artifact contains the exact command matrix and machine
readable validation facts.
