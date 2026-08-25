# A026 Player Presentation Consumer Adapter Core V1

Status: pure presentation adapter candidate; no route or screen wiring.

## Provenance

```
CURRENT_CANONICAL_MASTER=b75308d44806bb7c2e2b131a73ba06a71c188b3c
OWNER_ACCEPTED_INPUT=A025-R1
OWNER_ACCEPTED_INPUT_HEAD=d1401925952181b02da75a60e87c6bb851909125
CONTRACT_VERSION=PLAYER_PRESENTATION_API_V1
VIEW_MODEL_VERSION=PLAYER_PRESENTATION_VIEW_MODEL_V1
```

A025-R1 remains the accepted input contract reference. A026 does not merge
or recreate B028/B030 state and does not claim that accepted candidates are
part of `origin/master`.

## Purpose and topology

A026 prevents each future presentation surface from independently decoding
the Player Presentation transport. It narrows the transport once into an
immutable, deterministic view model that Hero, Adventure, Backpack, and
future presentation adapters can consume later.

```
B028 canonical read model
    -> B030 read service
    -> A025 PLAYER_PRESENTATION_API_V1
    -> A026 PLAYER_PRESENTATION_VIEW_MODEL_V1
    -> future surface-specific rendering
```

`player_presentation_consumer_adapter.py` is presentation-only. It has no
route decorator, API call, SQL, storage write, localStorage access, mutation,
ownership writer, or gameplay calculation.

## Input contract

`build_player_presentation_view_model` accepts either the immutable
`PlayerPresentationApiV1` object or a detached mapping with the exact A025
transport shape:

```
contract_version
player_id
projection_status
display_identity (optional)
hero
progression
persistent_hp
equipment
spirit
cosmetics
provenance
```

Unknown top-level fields fail closed. The adapter never treats a client
mapping as an authority and never reconstructs missing backend state.

## Output contract

The immutable `PlayerPresentationViewModelV1` exposes only:

```
view_model_version
contract_version
projection_status
player_id
display_identity (optional)
hero
progression
persistent_hp
equipment
spirit
cosmetics
```

The output intentionally omits A025 provenance and all excluded authorities;
the consumer is not a second authority-discovery layer. `to_dict()` returns
a detached plain object and the deterministic serializer uses sorted compact
JSON.

## Presentation-safe narrowing

### Hero

Only identity/presentation fields are returned: Hero ID, identity status,
presentation fallback, and stored-value diagnostics where supplied. The
adapter requires `player_appearance.character_key` and
`authority_scope=presentation_only` in the input. It does not create a
functional Hero model or expose combat attributes, class power, skills, or
passives.

### Progression

The view model may contain only XP/Level/Rank presentation facts and narrow
projection diagnostics:

```
xp
rank_level
level
rank_xp
go_rank
projection_status
invalid_fields
reason
```

The following are rejected and never appear in output:

```
total_correct
current_streak
max_streak
learning_stats
engagement_streak
correct_count
```

This adapter is not a Learning stats API, SRS API, Quest progress API,
engagement/streak API, or analytics API.

### Persistent HP

Only `persistent_player_hp`, `persistent_player_max_hp`, and the
`persistent_player_state` scope are returned. `encounter_hp`, encounter
state, and equivalent aliases are rejected. The adapter never aliases
persistent HP into an encounter value:

```
persistent_player_hp != encounter_hp
```

### Equipment

Equipment output is read-only presentation state: owned/equipped slots,
quantities, functional display status, display metadata, and invalid/conflict
diagnostics. Input authority must remain `player_inventory`.

Combat stats, combat power, damage, defense, bonuses, and combat modifiers
are rejected. The adapter does not calculate or settle any effect and does
not equip, unequip, consume, or resolve conflicted slots.

### Spirit

The output contains one active Spirit presentation with identity, enabled /
ownership-validated flags, evolution stage, and presentation progression
level where supplied. Input authority must be the server active-Spirit
projection and `single_active_spirit=true`.

Spirit combat effects and effect flags are rejected. `LORD_TRIAL_SPIRIT_EFFECTS`
remain `OFF`; no Lord Trial or second Spirit authority is created.

### Pure cosmetics

Selected and owned cosmetic display records are accepted only when explicitly
marked `presentation_only=true` and not marked with combat power. Gameplay
effect flags are not forwarded. Effect-bearing or legacy appearances cannot
silently become pure cosmetics and fail closed instead.

## Excluded authorities

The adapter rejects or omits all of the following:

```
World progression
selected/progression Zone
Quest state or reward authority
Shop catalog, purchase, Coins, Gacha, or Premium entitlement
encounter HP or Monster battle state
combat stats and equipment effects
Spirit combat effects
Learning correctness and streak state
```

The view model is therefore suitable for presentation fragments only. A
surface must continue to consume its own separate authority for World,
Quest, encounter, Shop, Premium, reward, and mutation behavior.

## Surface readiness

No existing screen is wired in A026. The intended future use is:

| Surface | Safe A026 use | Must remain separate |
| --- | --- | --- |
| Hero overview | identity, XP/level/rank, persistent HP, equipment/Spirit/cosmetic summary | mutations, badges, effects, World context |
| Adventure identity | player marker, Hero identity, level, active Spirit | zones, selected location, progression, encounter state |
| Backpack | owned/equipped functional equipment presentation | consumables, materials, item use, Shop inventory |
| Wardrobe | selected/owned pure cosmetic presentation | wardrobe mutation and release policy |

This is a consumer-core contract, not a route migration or frontend
implementation.

## Validation

`tests/test_a026_player_presentation_consumer_adapter.py` covers:

- valid full A025 snapshot;
- missing optional presentation fields;
- invalid authority payloads;
- Learning/streak fields and equivalent aliases;
- World, Quest, Shop, Premium, and encounter fields;
- persistent-vs-encounter HP separation;
- equipment combat stats and Spirit effects;
- pure cosmetic acceptance and effect-bearing cosmetic rejection;
- immutable and detached output;
- deterministic serialization;
- absence of route/API/storage/mutation wiring.

The A026 candidate is limited to this module, its focused test, and this
document. It does not change `app.py`, frontend screens, schemas, runtime
routes, payment, Production, or deployment.
