# A043 legacy equip fallback fail-closed and recovery closure

## Identity and authority

```text
TASK=A043_LEGACY_EQUIP_FALLBACK_FAIL_CLOSED_AND_RECOVERY_CLOSURE_001
CURRENT_ORIGIN_MASTER=6829c4c528adf4800326e90534585a32e390ebec
BASE_SHA=3348796c135ec23b2e2015623419e7806a4bc3ac
A042_HEAD=d7e2fb1a90d5fd0c5a17d6a5b864c6f0374210e8
C049_HEAD=3348796c135ec23b2e2015623419e7806a4bc3ac
BRANCH=codex/a043-legacy-equip-fallback-fail-closed-and-recovery-closure-001
APP_PY_WRITER=A043
```

`origin/master` was freshly fetched before the isolated worktree was created.
The worktree starts from the accepted C049 app.py lineage, so the C049 commerce
and appearance-commerce authority is retained. A043 does not merge or alter
that lineage.

## Route inventory

The only reachable legacy functional-equipment mutation route found is:

| Route | Method | Entrypoint | Function | Disabled flag behavior |
| --- | --- | --- | --- | --- |
| `/api/player/inventory/equip` | POST | Flask route, `@login_required` | `equip_item` | `action=equip` returns `409 LOADOUT_DISABLED`; `action=unequip` retains the approved legacy recovery path |

The route resolves the inventory row with `id AND user_id` before any mutation.
With the canonical flag on it continues to call the existing B034
`equip_owned_item` / `unequip_owned_item` service. With the flag off, no new
functional equip or replacement reaches the legacy mutation code.

```text
UNKNOWN_LEGACY_FUNCTIONAL_EQUIP_ROUTES=0
LEGACY_NEW_FUNCTIONAL_EQUIP_WHILE_DISABLED=FAIL_CLOSED
LEGACY_FUNCTIONAL_REPLACEMENT_WHILE_DISABLED=FAIL_CLOSED
LEGACY_EQUIPPED_ITEM_UNEQUIP_RECOVERY=PASS
UNEQUIP_AUTO_REPLACEMENT=NO
FAILED_REPLACEMENT_MUTATES_STATE=NO
```

## Owner policy preserved

```text
LOADOUT_ENABLED=NO
GO_ENABLE_CONSUMED=NO
XP_AMULET_NEW_EQUIP=NO
XP_AMULET_LEGACY_UNEQUIP=YES
EXISTING_EQUIPPED_STATE_AUTO_MUTATION=NO
AUTO_UNEQUIP_EXISTING_PLAYERS=NO
COSMETIC_APPEARANCE_ROUTES_CHANGED=NO
COMBAT_COMPATIBILITY_FIELDS_REMOVED=NO
COMBAT_COMPATIBILITY_FIELDS_NEW_FUNCTIONAL_AUTHORITY=NO
```

The guard is server-side and does not consult localStorage, appearance fields,
client slot state, or client combat state. The existing legacy branch is now a
recovery-only path while Loadout is disabled; it does not auto-select a
replacement or rewrite existing players on startup.

## Security and authority contract

All requests remain authenticated and ownership-scoped. Missing or foreign
inventory rows fail closed; invalid actions, unknown items, invalid slots, and
malformed requests do not mutate state. `player_inventory` remains the
equipment authority. `hero_combat_gear_v1`, `player_appearance.combat_*`, and
`APPEARANCE_EFFECTS` are not restored as functional authority.

```text
SERVER_EQUIPMENT_AUTHORITY=YES
CLIENT_EQUIPMENT_AUTHORITY=NO
LOCAL_CACHE_EQUIP_AUTHORITY=NO
SERVER_DAMAGE_AUTHORITY=YES
CLIENT_DAMAGE_AUTHORITY=NO
COSMETIC_COMBAT_POWER=0
GO_STONE_BLACK_COMBAT_POWER=0
BASELINE_DAMAGE=80
WOODEN_SWORD_DAMAGE=84
IRON_SWORD_DAMAGE=90
```

## Implementation scope

The only production source change is the narrow disabled-flag guard in
`app.py`. Test updates reconcile old flag-off equip expectations with the
owner-approved fail-closed policy while keeping flag-on canonical Loadout
coverage. A043 does not change commerce, cosmetic routes, static packaging,
Docker, service worker, schema, migration, payment, or other active lanes.

```text
APP_PY_CHANGED=YES
APP_PY_THIN_AUTHORITY_CLOSURE_ONLY=YES
RUNTIME_SOURCE_CHANGED=NO
STATIC_PACKAGING_CHANGED=NO
DOCKERFILE_CHANGED=NO
SW_JS_CHANGED=NO
SCHEMA_CHANGED=NO
MIGRATION_CHANGED=NO
SHOP_COMMERCE_CHANGED=NO
PAYMENT_CHANGED=NO
```

## Evidence

The A043 focused suite covers disabled new equip, replacement no-op, allowed
unequip recovery and replay, XP amulet locks, cross-user/malformed requests,
unknown inventory items, and flag-on canonical behavior. It also runs the
same recovery/replacement contract against a disposable PostgreSQL instance.

```text
SQLITE_LEGACY_FALLBACK_CONTRACT=PASS
POSTGRES_LEGACY_FALLBACK_CONTRACT=PASS
UNEQUIP_RECOVERY_ATOMIC=PASS
FAILED_MUTATION_PARTIAL_STATE=NO
CANONICAL_FLAG_ON_LOADOUT_BEHAVIOR_REGRESSION=PASS
```

The broader focused matrix includes A034/A038, B034/B036/B041/B042/B050,
Hero/Backpack, damage authority, A039/A040-compatible contracts, and C048/C049
commerce safety. Production was not queried or mutated. B057, C050, E046,
F034-R1, LC015, and ART003 scope was not touched.

## Remaining gate

A043 hardens the disabled compatibility route; it does not enable Loadout.
Future enablement still requires the separately governed B033 production
schema/migration readiness decision, later compatibility-field retirement or
boundedness decision, browser/physical-device and release evidence as required,
and explicit Owner GO_ENABLE authorization.
