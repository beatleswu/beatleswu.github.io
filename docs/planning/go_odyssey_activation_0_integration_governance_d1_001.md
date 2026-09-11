# GO Odyssey Activation_0 Integration Governance — D1

**Task:** `GO_ODYSSEY_ACT_F_ACTIVATION_INTEGRATION_GOVERNANCE_D1_001`
**Lane:** `ACT-F`
**Class:** `INTEGRATION_GOVERNANCE`
**Priority:** `P0`
**Branch:** `codex/act-f-integration-governance-d1-001`
**Recorded:** `2026-09-11`

This is the durable Activation_0 authority and cross-lane review contract.
ACT-F owns the cross-lane guard, transaction-boundary review, writer
assignment, Puzzle Identity protection, migration coordination, and integration
evidence. ACT-F is not an implementation owner for ACT-A, ACT-B, ACT-C, ACT-D,
or ACT-E.

## Reconciliation anchor

The requested base was rechecked in a clean isolated worktree before this
document was written:

| Fact | Value |
| --- | --- |
| `BASE_HEAD` | `da531c6da0edabab3c025823ec1157e604d56498` |
| `BASE_TREE` | `e942e346854ba8397900ee5fa1d824cd2a38967a` |
| ACT-A branch | `codex/act-a-app-wiring-d1-001`, at `BASE_HEAD` |
| ACT-B branch | `codex/act-b-provider-boundary-d1-001`, at `BASE_HEAD` |
| ACT-C branch | `codex/act-c-reward-authority-d1-001`, at `BASE_HEAD` |
| ACT-E branch observed | `codex/act-e-onboarding-v2-d1-001`, at `BASE_HEAD` |
| ACT-D branch observed | no returned branch/worktree at reconciliation time |
| canonical checkout safety | dirty unrelated checkout preserved; no reset, clean, stash, secret inspection, merge, deploy, migration, or Production mutation |

`BASE_HEAD`/`BASE_TREE` is the repository coherence anchor for this
review. The accepted Production facts below are Coordinator-provided
Activation_0 live facts. Repository source presence, a historical planning
document, or a migration candidate does not replace the live-fact authority.

## Activation_0 accepted live truth

`ACTIVATION_0_LIVE_TRUTH_RECONCILED=YES`

| Accepted fact | Current authority | Reconciliation classification |
| --- | --- | --- |
| Production/canonical coherence | `da531c6da0edabab3c025823ec1157e604d56498` / `e942e346854ba8397900ee5fa1d824cd2a38967a` | exact object and tree recheck in this lane |
| Puzzle Identity | `42,804 ACTIVE`; Genesis bootstrap `APPLIED`; resolver `HOT` in Production | accepted Activation_0 live fact; protected below; no live mutation here |
| E9 | authenticated | accepted Activation_0 rollout fact; source defaults are not treated as Production proof |
| E10 Map Battle | admin | accepted Activation_0 access fact; runtime mode and route source remain separately reviewable |
| `canonical_slot` | schema live | accepted Activation_0 schema fact; source migration remains separately reviewable and is not applied here |
| canonical Loadout | `EQUIPMENT_CANONICAL_LOADOUT_ENABLED=OFF` | accepted Activation_0 flag fact; disabled behavior remains fail-closed |
| Onboarding V2 | schema absent | accepted Activation_0 live schema fact; `migrations/w2_a1_onboarding_v1.py` is a candidate, not proof of live schema |
| Friend Challenge | current durable claim/settlement persistence gap | accepted Activation_0 gap; legacy tables/routes do not authorize a new canonical ledger |
| inventory | four-store model: `player_inventory`, `player_wardrobe`, `shop_inventory`, `pet_inventory` | accepted model reconciled to base schema; `player_appearance` is a presentation projection |

Historical source comments that describe Puzzle Identity or another schema as
candidate, cold, or not applied are retained historical/source evidence; they
do not override the accepted Activation_0 Production fact. Conversely, an
accepted live fact does not authorize source mutation, a migration, a merge, or
a deploy.

### Repository evidence index

These paths are the bounded source evidence used for the governance review.
They do not independently prove live Production state:

| Boundary | Base-tree evidence |
| --- | --- |
| E9 scope and authenticated decision | `app.py:719-769` |
| E10 Map Battle mode/admin boundary | `map_battle_persistence.py:19-29`, `app.py:5861-5870`, `app.py:15226-15507` |
| four stores and projections | `app.py:5150-5196`, `app.py:5586-5591` |
| Friend Challenge current path | `app.py:5519-5537`, `app.py:22646-23050`; no tracked `migrations/*friend*` file |
| Loadout flag and server boundary | `app.py:24192-24209`, `equipment_loadout_service.py:1-11,370-382` |
| canonical-slot schema candidate | `migrations/equipment_canonical_slot_v1.py:1-20` |
| Onboarding V2 schema candidate | `migrations/w2_a1_onboarding_v1.py:1-7,185-190` |
| caller-owned Battle settlement | `map_battle_persistence.py:1-7,686-705` |
| caller-owned Coin purchase | `coin_purchase_authority.py:1-6,931-1065` |
| server-fact onboarding | `wave2_onboarding_authority.py:3-6,277-289,1117-1120` |
| Puzzle Identity review surface | `identity_read_adapter.py`, `puzzle_identity_read_window.py`, `puzzle_identity_store.py`, `puzzle_identity_genesis_bootstrap.py` |

### Four-store inventory model

| Store | Authority | Boundary |
| --- | --- | --- |
| `player_inventory` | functional equipment ownership and equipped state; effects come from server `EQUIPMENT_DEFS` | acquire is not equip; acquisition creates `equipped=0`; preserve exact ownership row identity |
| `player_wardrobe` | cosmetic item ownership | presentation-only; cannot authorize functional equipment or combat effects |
| `shop_inventory` | shop quantity/state compatibility store | not proof of player ownership or purchase authorization |
| `pet_inventory` | pet consumable quantity | not functional equipment or Puzzle Identity authority |

`player_appearance` remains a presentation projection. No lane may create a
parallel equipment truth, infer ownership from a visual registry, or collapse
these stores into one generic ledger.

## Current development scalability governance

`GO_ODYSSEY_DEVELOPMENT_SCALABILITY_DECOMPOSITION` is the current governing
concept.

**Purpose:** increase safe development throughput, not architectural aesthetics.

**Core rule:** freeze boundaries early; mutate structure only when real work
requires it.

| Rule | Current authority |
| --- | --- |
| `DECOMPOSITION_REQUIRES_EVIDENCE` | `YES` |
| `DECOMPOSITION_SCOPE_MUST_BE_NARROW` | `YES` |
| evidence in one domain | does not authorize repository-wide refactoring |
| `ACTIVE_MUTATION_AUTHORITY_DUPLICATION` | `0` for Activation-touched canonical paths |
| `CANONICAL_TRANSACTION_OWNER_UNIQUE` | `YES` |
| `LEGACY_PARALLEL_PATH` | isolated, read-only, or bounded compatibility only |
| new feature dependency on legacy | `NO_UNLESS_EXPLICITLY_AUTHORIZED` |
| parallelism | parallelize independent work; serialize only for real authority, transaction, or dependency reasons |
| decomposition as a release gate | `NO` |
| `FULL_ARCHITECTURE_DECOMPOSITION` | `SUPERSEDED_CONCEPT` |

`FULL_ARCHITECTURE_DECOMPOSITION=SUPERSEDED_CONCEPT`

The D tracks are not mandatory sequential refactor epochs:

* `D1` — activation-coupled decomposition;
* `D2` — boundary freeze; structural mutation only when a runtime bottleneck is
  evidenced;
* `D3` — World Expansion frontend/presentation hotspot track, trigger-based;
* `D4` — long-term compatibility/maintenance track, trigger-based.

No D2, D3, or D4 completion is required for this D1 review. Zone4 may later
act as an architecture pressure test. If Zone4 demonstrates that World,
Cinematic, Audio, Battle, and Reward can proceed without unnecessary shared
authority contention, decomposition is sufficient and product work continues
to Z5–6.

## Puzzle Identity HOT-state contract

`PUZZLE_IDENTITY_HOT_CONTRACT=PASS`

The cross-lane invariant is:

```text
ACTIVE_IDENTITIES=42804
GENESIS_BOOTSTRAP=APPLIED
PRODUCTION_RESOLVER=HOT
```

ACT-A, ACT-B, ACT-C, and ACT-E must not independently write any
`puzzle_identity_*` table. ACT-F owns review of:

* `identity_read_adapter.py`;
* `puzzle_identity_read_window.py`;
* `puzzle_identity_store.py`;
* `puzzle_identity_genesis_bootstrap.py`.

Ownership is review authority, not permission to edit. A mutation requires a
specific evidence packet showing the runtime defect, exact affected operation,
why a read-only/bounded compatibility path cannot solve it, and the smallest
safe change. No such mutation is authorized by this artifact.

Targeted identity guards are limited to material Activation protection:

* preserve exact, ambiguous, and missing resolver behavior, including
  fail-closed ambiguity;
* never use client Puzzle Identity, a legacy alias, or a presentation registry
  as a new canonical writer;
* never rewrite the 42,804-row Genesis set, receipt, lineage, or aliases as part
  of an Activation lane;
* keep identity/db/migration review in ACT-F.

## APP.PY single-writer process gate

`APP_PY_SINGLE_WRITER_GOVERNANCE=PASS`

ACT-A is the sole Activation writer for `app.py`, `index.html`, and
`sw.js`. The gate is process-based and does not pin a fixed base SHA or
prohibit future authorized ACT-A work.

Every ACT-B, ACT-C, ACT-D, or ACT-E handoff must carry these exact fields,
even when the requested wiring is none:

```text
APP_PY_CHANGED=NO
ACT_A_EXACT_WIRING_REQUEST=<exact route/symbol/consumer request, or NONE>
```

The current no-handoff records are explicit:

| Lane | `APP_PY_CHANGED` | `ACT_A_EXACT_WIRING_REQUEST` |
| --- | --- | --- |
| ACT-B | `NO` | `NONE_PENDING_CANDIDATE_RETURN` |
| ACT-C | `NO` | `NONE_PENDING_CANDIDATE_RETURN` |
| ACT-D | `NO` | `NONE_PENDING_CANDIDATE_RETURN` |
| ACT-E | `NO` | `NONE_PENDING_CANDIDATE_RETURN` |

If an implementation lane later needs an `app.py` symbol, it stops writing
the file and submits the exact request to ACT-A. A single-writer assignment
never authorizes cleanup or unrelated refactoring.

## Transaction ordering contract

`TRANSACTION_ORDERING_CONTRACT=PASS`

| Owner | Mutation authority |
| --- | --- |
| ACT-A | HTTP/request transaction commit and rollback coordinator |
| ACT-B | Battle mutation authority |
| ACT-C | Reward and Coin mutation authority |
| ACT-D | Inventory mutation authority |
| ACT-E | Onboarding mutation authority |
| ACT-F | contract review only; not orchestration or domain mutation |

Domain functions must be caller-transaction APIs for a cross-domain flow: they
validate server facts, perform only their owned mutation, and do not silently
commit or roll back the caller transaction. The request coordinator owns the
final commit or rollback. Existing schema-install/bootstrap work is separate
migration/setup concern and is not a cross-domain settlement shortcut.

Expected Activation order:

```text
authoritative battle settle
  -> immutable reward fact
  -> Coin settlement, when applicable
  -> inventory/drop ownership
  -> onboarding server fact
  -> one ACT-A commit
```

Contract:

1. Battle results are server-derived and bound to durable battle/attempt
   identity. Client grades, damage, Monster identity, reward, Coin, item, and
   onboarding claims are never authority.
2. Each downstream owner receives the preceding server-owned fact and
   contributes to the same caller-owned transaction when stores share a
   connection.
3. If any phase fails before commit, ACT-A rolls back all uncommitted phases;
   the response is typed/retryable and no partial success is implied.
4. A bounded legacy path that already committed an earlier phase must expose a
   durable phase/idempotency identity and return explicit pending/retry state.
   Retries must not duplicate a reward, Coin debit, inventory row, or onboarding
   fact. This exception does not authorize a new split transaction.
5. A domain owner may not move all orchestration into ACT-F. ACT-F reviews
   sequence, rollback, idempotency, and ownership direction.

## Migration governance

`MIGRATION_GOVERNANCE=PASS`
`GO_PRODUCTION_DB_MIGRATION=NOT_GRANTED`

Production has no generic migration ledger. Any new Activation DDL must be:

* additive and idempotent;
* guarded by catalog presence/schema-shape checks before mutation;
* separately reviewable with an exact file, schema version, and ownership
  record;
* executed through a separately named migration operation, never silently as
  normal application startup or code deploy;
* covered by fresh-schema, already-present, malformed/partial, and relevant
  concurrency/failure tests;
* accompanied by read-only Production catalog evidence, backup/rollback
  evidence, exact artifact identity, and separate Owner authorization.

Possible candidates are limited to evidence-backed requests:

* ACT-C Friend Challenge durable claim/settlement schema, only if the current
  persistence gap is proven to require new DDL;
* ACT-E Onboarding V2 schema.

Neither candidate is applied or authorized here. When a candidate exists, its
gate requires an exact schema contract, additive/idempotent/catalog-guard
proof, isolated validation, read-only Production preflight, retained rollback
evidence, and explicit Owner `GO_PRODUCTION_DB_MIGRATION` authorization for
that exact candidate.

`migrations/**` and `db.py` are ACT-F's sole D1
writer/reviewer-coordinator surface. A candidate owner may propose a migration
but may not apply it or edit this surface without ACT-F assignment.

## Current file ownership matrix

| Surface | D1 writer | Review boundary |
| --- | --- | --- |
| `app.py`, `index.html`, `sw.js` | ACT-A | writer ownership, exact wiring, transaction direction, no unrelated edits |
| `map_battle_runtime.py`, `map_battle_persistence.py` | ACT-B | battle authority, server facts, idempotency, transaction behavior, Puzzle Identity safety |
| canonical reward/Coin modules, including `coin_purchase_authority.py` | ACT-C | reward/Coin mutation uniqueness, ledger/idempotency, cross-domain ordering |
| inventory/loadout service files, including `equipment_loadout_service.py` | ACT-D | store selection, exact ownership, no auto-equip, no presentation leakage |
| onboarding-specific E9 presentation and onboarding authority | ACT-E | server-fact consumption, E9 boundary, transaction behavior, schema gate |
| identity modules, `db.py`, and `migrations/**` | ACT-F | writer/reviewer coordination; identity mutation remains separately gated |
| any unlisted shared file | no lane may write until ACT-F assigns one writer | stop writing first; assignment is explicit and path-scoped |

The matrix does not authorize cleanup, extraction, renaming, or repo-wide
refactoring outside the requested path.

## Candidate review state

No ACT-A–E candidate contains a diff from `BASE_HEAD` at this reconciliation.
Every returned candidate still requires independent exact base/head/tree,
scope, ownership, transaction-owner, authority-duplication, Puzzle Identity,
migration, rollout/Production, and decomposition review.

### `ACT_A_REVIEW_STATE`

`NOT_RETURNED_FOR_REVIEW` — `codex/act-a-app-wiring-d1-001` is at
`BASE_HEAD`; no candidate diff was present. ACT-A remains the only future
writer of `app.py`, `index.html`, and `sw.js`.

### `ACT_B_REVIEW_STATE`

`NOT_RETURNED_FOR_REVIEW` — `codex/act-b-provider-boundary-d1-001` is at
`BASE_HEAD`; no candidate diff was present. `APP_PY_CHANGED=NO` and
`ACT_A_EXACT_WIRING_REQUEST=NONE_PENDING_CANDIDATE_RETURN`.

### `ACT_C_REVIEW_STATE`

`NOT_RETURNED_FOR_REVIEW` — `codex/act-c-reward-authority-d1-001` is at
`BASE_HEAD`; no candidate diff was present. `APP_PY_CHANGED=NO` and
`ACT_A_EXACT_WIRING_REQUEST=NONE_PENDING_CANDIDATE_RETURN`.

### `ACT_D_REVIEW_STATE`

`NOT_RETURNED_FOR_REVIEW` — no
`codex/act-d-inventory-authority-d1-001` branch/worktree was returned.
`APP_PY_CHANGED=NO` and
`ACT_A_EXACT_WIRING_REQUEST=NONE_PENDING_CANDIDATE_RETURN` are the required
handoff values when ACT-D returns.

### `ACT_E_REVIEW_STATE`

`NOT_RETURNED_FOR_REVIEW` — `codex/act-e-onboarding-v2-d1-001` is at
`BASE_HEAD`; no candidate diff was present. `APP_PY_CHANGED=NO` and
`ACT_A_EXACT_WIRING_REQUEST=NONE_PENDING_CANDIDATE_RETURN`.

## Decomposition trigger review

No structural split proposal was present in the base or returned candidate
diffs. Therefore:

| Trigger | Evidence at this review |
| --- | --- |
| `SHARED_FILE_CONTENTION` | not evidenced; returned ACT-A–E refs have no diff |
| `DUPLICATE_ACTIVE_MUTATION_AUTHORITY` | not evidenced; ownership is assigned uniquely |
| `AMBIGUOUS_TRANSACTION_OWNER` | no new proposal; ACT-A is coordinator and one domain owner is assigned per mutation |
| `LEGACY_CANONICAL_INTERFERENCE` | known compatibility boundary only; new features cannot depend on it without authorization |
| `REPEATED_CROSS_DOMAIN_REGRESSION` | not evidenced in returned candidate refs |

`DECOMPOSE=NO` for the current review. If a later proposal supplies one
listed trigger, authorize only the smallest boundary that removes that
specific contention. Line count is not a success metric.

`UNNECESSARY_DECOMPOSITION_FOUND=NO`

## Development-scalability exit test

This is a tracked health check, not a mandatory D2/D3/D4 program:

| Exit condition | D1 state |
| --- | --- |
| `ACTIVE_MUTATION_AUTHORITY_DUPLICATION=0_FOR_TOUCHED_CANONICAL_PATHS` | YES by current matrix; recheck each handoff |
| `CANONICAL_TRANSACTION_OWNER_UNIQUE=YES` | YES by this contract; recheck returned implementations |
| `SHARED_HOT_FILE_WRITERS=LOW_OR_CONTROLLED` | YES — app/shell surfaces are ACT-A-only |
| `CROSS_DOMAIN_AUTHORITY_DIRECTION=CLEAR` | YES — battle → reward → Coin → inventory → onboarding |
| `LEGACY_CANONICAL_BOUNDARY=EXPLICIT` | YES — bounded compatibility only |
| `NEXT_3_TO_5_PLANNED_FEATURES_HAVE_SAFE_OWNERSHIP=YES` | YES for assigned Zone4/world/cinematic/audio/battle/reward/onboarding ownership; implementation review pending |
| D2/D3/D4 complete | not required; `NOT_A_D1_EXIT_GATE` |

Closing this check does not grant merge, deployment, migration, or Production
authority.

## Prohibitions and gates

This artifact grants no authority for routine feature ownership by ACT-F,
`app.py` feature implementation by ACT-F, Provider/Reward/Inventory/Onboarding
implementation by ACT-F, repo-wide refactoring, mandatory D2/D3/D4 work,
Production mutation, migration application, merge, deploy, baseline masking,
Puzzle Identity rewriting, or a new Owner decision without a genuine product
policy question.

```text
PRODUCTION_MUTATION=NO
GO_PRODUCTION_DB_MIGRATION=NOT_GRANTED
GO_MERGE=NOT_GRANTED
GO_DEPLOY=NOT_GRANTED
OWNER_DECISIONS_REQUIRED=NONE
```

## Final D1 status

```text
STATUS=PASS_ACT_F_ACTIVATION_INTEGRATION_GOVERNANCE_D1_READY_FOR_CROSS_LANE_REVIEW
BRANCH=codex/act-f-integration-governance-d1-001
BASE_HEAD=da531c6da0edabab3c025823ec1157e604d56498
TREE=REPORT_EXACT_COMMIT_TREE_IN_FINAL_HANDOFF
ACTIVATION_0_LIVE_TRUTH_RECONCILED=YES
FULL_ARCHITECTURE_DECOMPOSITION_MARKED_SUPERSEDED=YES
DEVELOPMENT_SCALABILITY_GOVERNANCE_LANDED=YES
PUZZLE_IDENTITY_HOT_CONTRACT=PASS
APP_PY_SINGLE_WRITER_GOVERNANCE=PASS
TRANSACTION_ORDERING_CONTRACT=PASS
MIGRATION_GOVERNANCE=PASS
UNNECESSARY_DECOMPOSITION_FOUND=NO
PRODUCTION_MUTATION=NO
GO_MERGE=NOT_GRANTED
GO_DEPLOY=NOT_GRANTED
```
