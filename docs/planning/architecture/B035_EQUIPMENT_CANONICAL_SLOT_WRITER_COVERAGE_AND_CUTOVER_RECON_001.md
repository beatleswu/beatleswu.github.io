# B035 Equipment Canonical-Slot Writer Coverage and Cutover Recon

Status: read-only reconciliation and design packet. No runtime, schema, or
Production change is made by B035.

## Provenance

The fresh isolated worktree was created from `origin/master` after fetch.

| item | value |
| --- | --- |
| current canonical master | `b75308d44806bb7c2e2b131a73ba06a71c188b3c` |
| worktree branch | `codex/b035-equipment-canonical-slot-writer-recon` |
| B031 accepted input | `9f2f86f4478c243c04c344e16805e5f17f99774e` |
| B033 accepted input | `15f665f656418ab189d32aa809c163f3e27fa92c` |
| B034 accepted input | `e7235ef74bcf2a31c190e3a6ce320bc8ee6c3e74` |
| C022 accepted input | `b08c822573051635c92070d696ca43fcb49020f1` |
| C023 status | in progress; unaccepted and not current-master authority |

The current-master checkout was not changed. The pre-existing canonical
tracked change in `D:\go-website` was not touched.

## Authority and scope

The functional Equipment authorities remain:

* ownership: `player_inventory`;
* equipped state: `player_inventory.equipped`;
* item identity and canonical slot: server `EQUIPMENT_DEFS` / `_EQUIP_MAP`;
* combat effects: `_get_authoritative_combat_stats` and its functional
  equipment helpers, which read owned/equipped `player_inventory` rows and
  server definitions (`app.py:7050-7087`).

`player_appearance.combat_*` is not a second B021 combat-stat authority. It is
nevertheless still a live legacy presentation writer and its
`_get_appearance_effects` reader still contributes XP/drop effects. That is a
separate legacy retirement blocker, not a reason to relabel the B021
equipment-stat authority.

The current-master `player_inventory` table initializer has only
`id,user_id,equip_id,equipped,obtained_at,source` (`app.py:4720-4728`); the
accepted B033 `canonical_slot` migration is not present in this current-master
tree. Therefore B033 enforcement is a future integration/migration gate, not a
currently active constraint.

The accepted B033 invariant has two parts:

1. `equipped=true` requires a non-NULL server-derived `canonical_slot`.
2. At most one equipped row may exist for one `(user_id, canonical_slot)`.

An ownership row with `equipped=false` and `canonical_slot=NULL` is legal under
the accepted design. It is projection-incomplete when a known functional item
could have its slot derived, but it is not by itself a hard constraint blocker.

## Search and classification method

B035 searched current-master Python source for literal `INSERT`, `UPDATE`, and
`DELETE` operations against `player_inventory`, then followed the enclosing
helpers and their route/event callers. The Monster settlement callback was
followed because it is an indirect storage seam even though
`monster_settlement.py` itself does not execute the SQL. Tests and accepted
candidate worktrees were kept separate from current-master writer counts.

The classifications below use these meanings:

* `BLOCKS_B033_ENFORCEMENT`: can produce or preserve a state forbidden by the
  final hard invariant, including an equipped row without a slot or a second
  effective same-slot row.
* `SAFE_FOR_B033_CONSTRAINT_BUT_PROJECTION_INCOMPLETE`: only creates or keeps
  unequipped ownership rows with NULL slot, so the hard constraint is safe but
  a later read projection must derive more complete slot data.
* `FULLY_B033_COMPATIBLE`: writes the server-derived slot and respects the
  malformed-state guard/uniqueness contract.
* `RETIRED_OR_HISTORICAL`: not a current writer and retained only as evidence.
* `NOT_FUNCTIONAL_EQUIPMENT_WRITER`: may delete or orchestrate data but does
  not create functional equipped/owned state.
* `UNKNOWN_NEEDS_FOLLOWUP`: no current-master writer was placed here.

## Current-master writer coverage

The exact machine-readable record is in
`b035_player_inventory_writer_matrix.json`. The four current-master mutation
records are:

| writer | operation | can create functional ownership | can set `equipped=true` | current slot behavior | B033 classification |
| --- | --- | --- | --- | --- | --- |
| `current.loadout.equip_item` | UPDATE | no | yes | column-unaware; derives a legacy slot only to clear rows | `BLOCKS_B033_ENFORCEMENT` |
| `current.monster.grant_functional_item` | INSERT | yes | no (`equipped=0`) | omits `canonical_slot` | `SAFE_FOR_B033_CONSTRAINT_BUT_PROJECTION_INCOMPLETE` |
| `current.admin.grant_equipment` | INSERT | yes | no (`equipped=0`) | omits `canonical_slot` | `SAFE_FOR_B033_CONSTRAINT_BUT_PROJECTION_INCOMPLETE` |
| `current.admin.remove_equipment` | DELETE | no | no | not applicable | `NOT_FUNCTIONAL_EQUIPMENT_WRITER` |

### 1. `current.loadout.equip_item`

* Route/function: `POST /api/player/inventory/equip`,
  `app.py:equip_item` (`app.py:16888-16934`).
* Request identity: `inv_id` plus `action` (`equip` or `unequip`). The route
  proves the inventory row belongs to the authenticated session user with
  `SELECT ... WHERE id=? AND user_id=?` (`app.py:16897-16901`).
* The server resolves the row's `equip_id` through `_EQUIP_MAP` and obtains a
  slot from `EQUIPMENT_DEFS` (`app.py:16902-16905`). The client cannot provide
  the slot or a combat value.
* `go_stone_black` is rejected by `INVENTORY_ONLY_EQUIPMENT_IDS`;
  `xp_amulet` is currently defined as an accessory and is not in that reject
  set. Consequently the current route can functionally equip `xp_amulet`,
  which conflicts with the accepted HOLD_FOR_AUTHORITY lock and must be
  closed by the future command authority.
* On equip, PostgreSQL uses a user-row `FOR UPDATE` lock and then clears
  `equipped` for the other server-defined items in the same legacy slot before
  setting the target row to `equipped=1` (`app.py:16908-16925`). SQLite does not
  get the PostgreSQL row-lock branch. The code does not preflight unknown
  equipped rows, NULL canonical slots, projection disagreement, or duplicate
  effective state.
* The route never writes `canonical_slot`. With B033 enforcement active, a
  target row with NULL canonical slot would fail the validity constraint; the
  route also remains a separate mutation implementation rather than the
  accepted B034 service.
* The route commits inside `with get_db()` (`app.py:16928`). This differs from
  B034's accepted caller-owned transaction contract.
* The unequip branch only sets the selected row to `equipped=0`. It does not
  consume the item, call D5C, or write legacy appearance fields.

This is the sole current-master writer that can set `equipped=true`, so it is
the sole current-master B033 hard blocker. It must be replaced or strictly
adapted to B034 before the final B033 validity constraint can be enforced.

### 2. `current.monster.grant_functional_item`

* Function: nested `grant_functional_item` in
  `_settle_monster_defeat_in_tx` (`app.py:7207-7340`, SQL at
  `app.py:7270-7282`).
* Callers: the existing Monster defeat settlement callback through
  `monster_settlement.settle_monster_defeat`; the callback is reachable from
  legacy SRS/Battlefield progression and the Map Battle settlement handoff.
* The helper resolves the requested drop through `_EQUIP_MAP`, counts existing
  ownership, and inserts one or more rows with `equipped=0`. It omits
  `canonical_slot`. Its transaction is owned by the enclosing review/Monster
  settlement operation; this helper does not commit.
* It can grant a functional Equipment definition or a trophy as an ownership
  row, but it cannot set an equipped row. Under B033, this is safe for the hard
  constraint and incomplete for canonical projection. It must not be reported
  as an equipped-slot blocker.

`monster_settlement.settle_monster_defeat` is an indirect callback/orchestration
seam, not a second SQL writer. No second inventory authority was found.

### 3. `current.admin.grant_equipment`

* Route/function: `POST /api/admin/users/<uid>/assets/equipment`,
  `admin_set_equipment`, grant branch (`app.py:9971-9984`).
* Admin input `equip_id` is checked against server `EQUIPMENT_DEFS`; the row is
  inserted with `equipped=0`, and the route commits its own connection.
* It may create ownership for any definition accepted by the current
  definition list, including rows that later need the special-item policy,
  but it cannot set `equipped=true`. The INSERT omits `canonical_slot`, so it is
  B033-hard-constraint safe but projection-incomplete.
* The remove branch (`app.py:9985-9990`) deletes a user-owned inventory row and
  is recorded separately because it is a storage mutation, but it cannot
  produce an equipped state.

## Accepted candidate writers outside current master

These are evidence and future topology, not current-master writers:

* B033 migration backfill derives slots from the server definition registry and
  writes `canonical_slot` for known functional rows. It is a fully compatible
  migration writer, but it is not executed in B035.
* B034 `equip_owned_item` and `unequip_owned_item` are the accepted command
  writer pair at `e7235ef74bcf2a31c190e3a6ce320bc8ee6c3e74`. They require the
  B033 schema shape, use server slot authority, fail closed on malformed state,
  and do not commit independently. They are not present in current master.
* C022's accepted acquisition authority, `SqlAcquisitionAuthority` in the
  C022 candidate, inserts ownership with `equipped=0` and currently omits
  `canonical_slot`. It is therefore safe for the hard B033 constraint but
  projection-incomplete. C022 is not current-master runtime.
* C023's remote in-progress candidate (`ab588aa28cbae92a8c29bffe575b67b1f3207793`)
  proposes making the C022 acquisition writer derive and persist the slot when
  the column exists. C023 is explicitly unaccepted and is not used as current
  truth, a passed gate, or a B035 dependency.

## Legacy `player_appearance.combat_*` path

The eight legacy fields are created by the current schema initializer
(`app.py:5274-5292`) and are written by one live route:

`POST /api/skills/character` → `skills_character` (`app.py:17508-17559`).

The route accepts optional `combat_armor`, `combat_weapon`, `combat_cape`,
`combat_offhand`, `combat_hat`, `combat_pet`, `combat_aura`, and `combat_acc`.
It sanitizes/truncates values and applies `_gear_unlocked` rank/answer gates,
but it does not prove `player_inventory` ownership or resolve a slot from
`EQUIPMENT_DEFS`. The Hero page posts this loadout (`hero.html:4250-4303`);
`index.html` also calls the character endpoint for character selection.

The field-by-field result is deliberately conservative:

| field | live effect reader | presentation/read consumers | ownership/slot validation | disposition now |
| --- | --- | --- | --- | --- |
| `combat_weapon` | `_get_appearance_effects` adds tier XP | appearance API, Hero overlay, bot/community cards | no inventory ownership; no canonical slot | `COMPATIBILITY_READ_ONLY` plus retirement blocker |
| `combat_armor` | `_get_appearance_effects` adds tier drop | appearance API, Hero overlay, bot/community cards | no inventory ownership; no canonical slot | `COMPATIBILITY_READ_ONLY` plus retirement blocker |
| `combat_cape` | `_get_appearance_effects` adds tier XP | appearance API, Hero overlay, bot/community cards | no inventory ownership; no canonical slot | `COMPATIBILITY_READ_ONLY` plus retirement blocker |
| `combat_offhand` | `_get_appearance_effects` adds tier drop | appearance API, Hero overlay, bot/community cards | no inventory ownership; no canonical slot | `COMPATIBILITY_READ_ONLY` plus retirement blocker |
| `combat_hat` | `_get_appearance_effects` adds tier XP | community/leaderboard/loadout projections | no inventory ownership; no canonical slot | `COMPATIBILITY_READ_ONLY` plus retirement blocker |
| `combat_pet` | `_get_appearance_effects` adds tier drop | community/leaderboard/loadout projections | no inventory ownership; no canonical slot | `COMPATIBILITY_READ_ONLY` plus retirement blocker |
| `combat_aura` | `_get_appearance_effects` adds tier XP | community/leaderboard/loadout projections | no inventory ownership; no canonical slot | `COMPATIBILITY_READ_ONLY` plus retirement blocker |
| `combat_acc` | `_get_appearance_effects` adds tier drop | legacy loadout/appearance projections where selected | no inventory ownership; no canonical slot | `COMPATIBILITY_READ_ONLY` plus retirement blocker |

The gameplay reader is exact and live: `_get_appearance_effects`
(`app.py:2756-2801`) folds these fields into XP/drop modifiers, and the SRS
review path consumes that result at `app.py:14224`. This is not B021's
functional Equipment damage/mitigation authority, but it is gameplay-adjacent
and must be retired or explicitly governed before the legacy writer can be
removed. No automatic mapping of these values into `player_inventory` is
recommended; a compatibility read can remain temporarily while the effect
path is retired through a separately accepted decision.

The Hero visual loadout remains presentation-only for the current B032/B034
decision. The current `player_inventory` combat-stat reader explicitly rejects
these fields (`app.py:7053-7057`).

## Special-item trace

* `go_stone_black` is present in the server definition list but is explicitly
  in `INVENTORY_ONLY_EQUIPMENT_IDS` (`app.py:1264-1267`); the current equip
  route rejects it. No current functional equip writer for it exists. Monster
  ownership/drop and admin ownership may still create an `equipped=0` row.
* `xp_amulet` is an accessory definition (`app.py:1223-1230`). Current grant
  writers create ownership only, but the current equip route does not reject
  it. Thus a current functional equip path does exist for `xp_amulet`, contrary
  to the accepted HOLD_FOR_AUTHORITY rule. B034 must remain the future gate and
  reject it before mutation; B035 does not patch the route.

## Current route and cutover decision

`CURRENT_EQUIP_ROUTE_RECOMMENDATION=CUTOVER_TO_B034`.

The current route has useful server checks, but it is not a safe final writer:
it owns/commits the transaction, does not write canonical slot, has no
malformed-state preflight, can bypass B034, and accepts `xp_amulet`. A future
`app.py` adapter should retain authentication and the current `inv_id`/action
HTTP contract while translating to B034's server-owned command. The adapter
must explicitly test duplicate-owned-row identity semantics because the current
route targets an inventory row while B034's accepted core command is keyed by
server-resolved equipment identity. B035 does not silently claim that parity is
already proven.

There is no separate current unequip route. Unequip is the `action=unequip`
branch of the same endpoint. It sets `equipped=0`, does not consume an item,
and is therefore not itself a B033 hard blocker; it should still be moved with
the route so one command authority owns both states.

## Malformed-data preflight and remediation

No Production query was run. Before B033 final constraints are applied, a
read-only environment must classify at least:

1. duplicate equipped rows after joining `equip_id` to server definitions by
   `(user_id, slot)`;
2. equipped unknown `equip_id` values;
3. `equipped=true` with NULL `canonical_slot`;
4. stored canonical slot disagreeing with the server-derived slot;
5. `go_stone_black` equipped;
6. `xp_amulet` equipped while HOLD_FOR_AUTHORITY is active.

The NULL-slot detector is named `EQUIPPED_WITH_NULL_CANONICAL_SLOT`, as locked
by B032-R1. The preflight policy is `FAIL_CLOSED + EXPLICIT_REPAIR`: do not
choose latest/lowest/highest-rarity winners, do not auto-unequip in this task,
and do not add a destructive repair to a migration. A blocker prevents final
constraint activation until an owner-approved repair/quarantine process has
produced clean evidence. Unequipped NULL-slot ownership rows remain legal and
must not be misclassified as hard blockers.

## B034 cutover prerequisites

Before a future route integration can be accepted, all of the following are
needed:

1. B033 schema candidate is integrated and its migration has passed disposable
   PostgreSQL/SQLite checks; current master currently has neither the
   `canonical_slot` column nor active constraints.
2. A read-only malformed-data preflight is clean, or every blocker has an
   owner-approved explicit repair/quarantine result.
3. B034 service code is available on the integration base and remains the
   single loadout mutation authority.
4. A thin route adapter preserves authentication (`login_required` session
   identity), request validation, current error/status behavior, and the
   caller-owned transaction boundary. B034 itself must not commit.
5. Adapter parity tests cover `inv_id` selection, equip, unequip, same-slot
   replacement, cross-slot preservation, duplicate owned rows, locked items,
   malformed state, rollback, and B033 invariant proof.
6. Current and accepted ownership writers are handled per writer: equipped=true
   writers must be canonical-slot-safe before constraint enforcement; ownership-
   only INSERT writers may be migrated separately because `equipped=0` with
   NULL slot is constraint-safe, but they should become slot-aware before the
   projection-completeness target is declared.
7. C022/C023 acquisition behavior is accepted independently. C023 is not a
   B035 dependency and must not be treated as merged.
8. Legacy `combat_*` gameplay effects have a separately accepted retirement or
   compatibility policy. B034 must not inherit them or map them silently into
   functional Equipment.

## Migration and release separation

The following statuses are intentionally separate:

| gate | B035 result |
| --- | --- |
| `SCHEMA_CODE_EXISTS` | yes, accepted B033 candidate exists outside current master |
| `SCHEMA_MERGED` | no |
| `READ_ONLY_PRODUCTION_PREFLIGHT` | required, not run by B035 |
| `PRODUCTION_MIGRATION_GRANTED` | no owner grant in B035 |
| `PRODUCTION_MIGRATED` | no |
| `WRITER_CUTOVER_COMPLETE` | no |

Writer timing is `PER_WRITER_DEPENDENT`:

* the current `equipped=true` loadout route must be cut over to B034 before
  enforcement, or in the same controlled release with an atomic route/schema
  rollout. Running final B033 enforcement while the old route remains able to
  write an equipped NULL-slot row is unsafe;
* current Monster/admin ownership-only INSERTs are not hard constraint
  blockers, so their canonical-slot projection fix may be before or after the
  schema rollout, but must be tracked before projection completeness is
  declared;
* acquisition/Shop writers follow their own accepted C022/C023 gate;
* legacy `player_appearance.combat_*` retirement is a separate compatibility
  release and is not a reason to create another Equipment authority.

Recommended sequence:

`writer recon → owner-approved writer compatibility changes → read-only
malformed preflight → integrate B033 schema candidate → cut over the
equipped=true route to B034 before/at the same enforcement release → verify
ownership-only writers → owner-granted Production migration → post-cutover
regression and projection audit`.

This sequence is a recommendation only. B035 grants no merge, migration, or
Production authority.

## Validation evidence

* JSON parsing: `2/2` documents valid.
* Matrix assertions: `PASS` (four current-master storage mutation records,
  one equipped=true writer, two ownership-only INSERT writers, one B033 hard
  blocker, and locked-item results).
* Documentation/source assertions: `PASS`.
* `git diff --check`: `PASS`.
* Existing equipment/static regression selection:
  `tests/test_rpg_wave2_gate2_equipment_backpack.py` and
  `tests/test_rpg_wave1_lane_b.py` — `22 passed`.
* No Production query, mutation, migration, or runtime test database was used
  by B035.

## Final recommendation

`NEXT_EQUIPMENT_INTEGRATION`: integrate accepted B033/B034 onto a fresh
current-master branch, build only the thin `/api/player/inventory/equip`
adapter, and run the malformed/precondition/parity suite before any
Production migration. In parallel, prepare narrow server-slot writes for the
Monster/admin ownership-only producers; keep C023 unaccepted until its own
review. Retire the legacy `combat_*` gameplay effect reader through a separate
owner-approved task, while preserving temporary compatibility reads.

No current-master code, app route, migration, or Production database was
changed by B035.
