# E049 Battlefield MonsterCatalog bounded shadow migration

## Scope and authority

E049 implements the Owner-approved bounded shadow window only. The existing
F003/F004/F008 Battlefield identity, profile, combat, and settlement paths
remain authoritative. The E045 catalog and the E046/E047 adapter are observed
beside those paths; their output cannot select a monster, set HP or ATK,
change a combat result, mutate player state, settle a reward, or change
progression.

The implementation is request-local and deterministic. It does not persist
records, emit telemetry, add a response field, log player identifiers, or
consult presentation/art planning data.

## Reconciled lineage

The candidate is based on the fresh `origin/master` fetched for E049:

`3f98c204a2b249763ad3d8d0730e5d3a0764622b`

Accepted E045 through E048 artifacts were replayed onto that base. A046 was
audited at `bd80ede8b9d9ba0a680ad20fd17b2d48e8542e27`; its appearance-authority
retirement semantics are not present on this base, but they do not overlap
E049's Battlefield shadow call sites and were not imported or overwritten.

## Shadow caller order

| Phase | Caller | Active source | Shadow action | Mutation capability |
| --- | --- | --- | --- | --- |
| `STATUS_READ_ONLY_PROJECTION` | `monster_status` | F003/F004/F008 | Compare the server-resolved current profile | None |
| `NORMAL_BATTLEFIELD_CONSUMERS` | `_lane_b_monster_update_with_authoritative_profile` for normal encounters | F003/F004/F008 | Compare the same profile before the legacy operation | None |
| `BOSS_BATTLEFIELD_CONSUMERS` | `_lane_b_monster_update_with_authoritative_profile` for boss encounters | F003/F004/F008 | Compare the same profile before the legacy operation | None |
| `MUTATION_AND_SETTLEMENT_PATH_SHADOW_COMPARISON` | `_update_monster_and_quests` and its settlement branch | F003/F004/F008 and existing settlement service | Record what the catalog would resolve beside mutation and settlement | None |

The sink is created by the review operation, is passed through the existing
call chain, and is exposed only as a request-local Flask `g` tuple after the
operation. It is never included in the JSON response or persistence writes.

## Diagnostic contract

The runtime adapter emits deterministic JSON-compatible records containing the
run id, consumer, phase, path role, zone, encounter class, current and shadow
identity/profile/stat fields, status, and drift type. The complete drift set
is:

`MATCH`, `IDENTITY_DRIFT`, `CONTEXT_MISMATCH`, `PROFILE_REF_DRIFT`,
`PROFILE_VERSION_DRIFT`, `HP_DRIFT`, `ATK_DRIFT`, `UNKNOWN_MONSTER`,
`UNKNOWN_PROFILE`, and `MISSING_PROFILE`.

Unknown identity/profile, missing profile, invalid context, and invalid phase
or path role fail closed for the shadow record only. The active legacy result
is unchanged. No generated formula, presentation fallback, permanent legacy
fallback, or time-boxed compatibility bridge is introduced.

The only explicit profile-version compatibility pair is
`f008.v1 -> e045.profile.v1`, representing the two named registries used by
the current and foundation sources. Any other version pair is reported as
`PROFILE_VERSION_DRIFT`.

## Evidence

- Normal Battlefield coverage: all 10 zones, zero drift.
- Boss Battlefield coverage: all 10 zones, zero drift.
- Mutation and settlement roles: both exercised in focused tests and remain
  non-mutating shadow observations.
- F009 remains disabled; Adventure, Lord, ART002, F034/F035 planning, reward
  authority, world progression, and app.py-owned domains outside E049 remain
  outside the caller integration.
- Focused E045-E049 plus F003/F004/F008/F009/Adventure authority suite:
  `173 passed`.
- Map Battle collection: 27 cases. The 26-case bounded non-Postgres subset
  passed. The full run reproduced the pre-existing harness stall after 25
  completed cases in the Postgres/Docker lifecycle case; Map Battle runtime
  was not changed.

## Cutover status

No authority cutover is performed by E049. The evidence is sufficient for a
separate Owner gate for a future fail-closed cutover only when all covered
normal and boss callers continue to report zero drift and no unknown callers.
The future policy is strict: any identity, context, profile reference,
profile version, HP, or ATK mismatch blocks cutover or requires rollback.
