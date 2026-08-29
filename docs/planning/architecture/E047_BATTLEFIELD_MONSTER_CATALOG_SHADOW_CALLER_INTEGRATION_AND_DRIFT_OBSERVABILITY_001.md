# E047 Battlefield Monster Catalog Shadow Caller and Drift Observability

Status: bounded, non-authoritative diagnostic candidate.  E047 observes the
current Battlefield authority beside the accepted E045/E046 foundation.  It
does not authorize a gameplay migration.

## Provenance

- Fresh base: `origin/master` at the E047 reconciliation point.  The fresh
  master moved to `574b3eeb9641c48676e95d3744d204dffca1e1fa` while the branch
  was prepared.
- E046 accepted source head: `70c41bd2639837556779af63be3632ee5e4d0eac`.
- E046's foundation, adapter, and consumer-matrix commits are carried into
  this branch in order.
- B058/B057 RC work is upstream context only.  E047 does not modify its branch,
  tree, manifest, merge, or release identity.

## Shadow caller matrix

| Caller | Active gameplay authority | Shadow invocation | Player visible | Mutation capable | Safe |
| --- | --- | --- | --- | --- | --- |
| Battlefield parity matrix | Current F003/F008 resolver | `observe_battlefield_shadow_matrix()` | No | No | Yes |
| Developer diagnostic artifact | Current F003/F008 resolver | `build_shadow_diagnostic_artifact()` / `render_shadow_diagnostic_json()` | No | No | Yes |
| Bounded drift classifier | None; classification only | `classify_shadow_drift()` | No | No | Yes |
| E045/E046 adapter contract tests | Test fixture only | `compare_runtime_encounter()` through caller | No | No | Yes |
| F009 active selector | Not integrated | None | No | No | No caller added |
| Adventure active resolver | Not integrated | None; Adventure remains no-profile in E046 | No | No | No caller added |
| Lord active runtime | Not integrated | None; no numeric Lord profile | No | No | No caller added |
| World/reward/combat mutation paths | Not integrated | None | No | No | No caller added |

The four integrated rows are diagnostic/test callers, not live player
consumers.  No `app.py` import, route hook, UI output, persistence, DB write,
or external telemetry was added.

## Caller contract

`battlefield_monster_catalog_shadow_caller.py` resolves the current side with
the active F008 `resolve_monster_combat_profile()` using an explicit F003
Monster ID.  It then passes the resulting tuple to the E046 shadow adapter.
The caller accepts an explicit F003 `roster_slot` through the adapter path but
never turns `monster_idx`, presentation labels, art paths, roster count, ELO,
or array order into authority.

The caller returns immutable `BattlefieldShadowDiagnostic` records with:

`timestamp_or_run_id`, `consumer`, `zone`, `encounter_class`,
`current_monster_id`, `shadow_monster_id`, `current_profile`, `shadow_profile`,
`current_hp`, `shadow_hp`, `current_atk`, `shadow_atk`, `status`, and
`drift_type`.

`SHADOW_RUN_ID=e047.battlefield-shadow.v1` is intentionally stable.  The JSON
artifact is returned in memory and rendered with sorted keys; no timestamp or
random seed is introduced.

## Drift taxonomy

The first explicit difference is classified as one of:

- `MATCH`
- `IDENTITY_DRIFT`
- `PROFILE_REF_DRIFT`
- `HP_DRIFT`
- `ATK_DRIFT`
- `MISSING_PROFILE`
- `UNKNOWN_MONSTER`
- `UNKNOWN_PROFILE`
- `CONTEXT_MISMATCH`

Unknown identity, unknown profile, missing profile, and invalid context become
typed `FAIL` diagnostic records.  They never replace the current runtime
result.  A normal-versus-Boss context mismatch is reported separately from a
missing Adventure/Lord profile.  The two source profile versions are retained
in output; their version labels are intentionally not treated as drift when
the explicit profile identity and values match.

## Battlefield parity evidence

The matrix invokes 10 normal and 10 Boss Zones.  For every row:

- current identity equals shadow identity;
- F008 current profile ID equals the E045 referenced profile ID;
- current HP equals shadow HP;
- current ATK equals shadow ATK; and
- status is `PASS`, drift type is `MATCH`.

The current values remain the accepted Battlefield snapshot:

| Context | Zones | HP | ATK | Shadow drift |
| --- | ---: | --- | --- | ---: |
| Battlefield normal | 10 | 80, 130, 200, 220, 260, 520, 760, 1100, 1700, 2400 | 2, 3, 4, 5, 6, 12, 16, 20, 28, 36 | 0 |
| Battlefield Boss | 10 | 100, 160, 240, 260, 290, 700, 920, 1350, 2000, 2800 | 2, 4, 5, 6, 7, 14, 18, 22, 32, 40 | 0 |

## Authority firewalls

- Shadow output cannot mutate gameplay, select a Monster, or set HP/ATK.
- F003/F004/F008 and existing Battlefield settlement remain active authority.
- F009 stays default-off and is not a shadow caller.
- Adventure and Lord are not integrated as active callers; Adventure does not
  inherit Battlefield profiles and Lord receives no numeric profile.
- World progression, rewards, Boss behavior, and combat mutation paths are not
  called by E047.
- Common/Rare/Elite remains disabled and is not coupled to frequency.
- ART002 remains art-only; F034 planning Zones are not gameplay input.
- B058 scope, A044, F034-R2, LC015, and ART003 are untouched.

## Readiness and next step

`MONSTER_FOUNDATION_NEXT_ADOPTION_READINESS=`
`READY_FOR_BATTLEFIELD_READONLY_RUNTIME_SHADOW`.

The next E task should be an explicit Battlefield consumer migration decision
packet, backed by this shadow artifact and a separately approved owner gate.
That decision must preserve F008 compatibility behavior and continue to keep
Adventure, Lord, F009, World progression, reward settlement, and combat
mutation outside the migration.  E047 itself does not activate that caller.
