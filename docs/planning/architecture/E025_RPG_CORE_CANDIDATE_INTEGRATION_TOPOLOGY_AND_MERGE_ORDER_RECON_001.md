# E025 RPG Core Candidate Integration Topology and Merge Order Recon

Task: `E025_RPG_CORE_CANDIDATE_INTEGRATION_TOPOLOGY_AND_MERGE_ORDER_RECON_001`
Master lane: E
Mode: read/analyze, Git ancestry recon, integration topology, docs only
Owner gate: none granted by E025

## Executive result

The verified canonical remote is still:

`origin/master = b75308d44806bb7c2e2b131a73ba06a71c188b3c`

Fourteen requested candidate inputs were reconciled: nine task-book
accepted/reference candidates and five remote-visible candidates still marked
pending Owner review. All fourteen exact commit objects and their dedicated
remote refs are available. None of the fourteen candidate tips is an ancestor
of current `origin/master`, so none is merged into the current master.

The important topology facts are:

* `B028 -> B030` is a real Git stack.
* `D018 -> D019-R1` is a real Git stack through an unlisted intermediate
  D019 base.
* `F012-R1`, `A025-R1`, `B032-R1`, and `C021-R1` are current-master-based
  pending stacks, but their R1 tips are not self-contained relative to the
  listed parent candidate.
* No listed candidate directly changes `app.py`; the collision risk is in the
  future route/writer wiring, not in the candidate commit file sets.
* C019 requires a candidate-only `coin_purchase_operations_v1` migration
  before a real Shop route cutover. B032's `canonical_slot` constraints are
  design-only. F012 leaves World milestone storage as an explicit later
  decision.

The recommended next app.py integration is `PLAYER_PRESENTATION`: the B028 /
B030 read-only chain has no schema prerequisite and has lower collision risk
than Equipment, Shop, Acquisition, or World/Monster mutation wiring. A025-R1
must remain pending until its Owner review passes; the eventual route must not
be invented from the contract branch.

The machine-readable evidence is in:

* `e025_candidate_dependency_graph.json`
* `e025_app_py_collision_matrix.json`
* `e025_recommended_merge_waves.json`

## Evidence boundary and verification method

The repository identity was verified from the isolated exact-master worktree:

| Field | Value |
| --- | --- |
| Canonical repository | `D:\go-website` |
| Remote | `https://github.com/beatleswu/beatleswu.github.io.git` |
| Recon worktree | `D:\go-website-e025-topology-recon` |
| Recon base | `b75308d44806bb7c2e2b131a73ba06a71c188b3c` |
| Branch for this docs candidate | `codex/e025-rpg-core-topology-recon` |
| Production access | not used |
| Runtime/schema mutation | none |

`origin/master` was fetched before the recon and remained the expected SHA.
The dirty canonical checkout was not used for edits. Its pre-existing staged
file, untracked artifacts, and protected files were not changed or inspected.

The candidate facts below come from exact Git objects, `git merge-base`,
`git rev-list --left-right --count`, commit parents, exact parent-to-tip file
diffs, branch/ref containment, and the remote refs fetched from `origin`.
`ahead_by` and `behind_by` mean candidate-only and master-only commit counts
respectively.

## Candidate provenance matrix

`Owner status` reflects the E025 task book. `ACCEPTED_REFERENCE` means the
candidate is an allowed accepted/reference input, not that it is merged.
`PENDING_OWNER_REVIEW` is deliberately not treated as accepted.

| Candidate | SHA | Owner status | Parent | Merge base | Ahead / behind | Master ancestor of candidate | Candidate ancestor of master | Merged | Direct changed files | app.py | schema | runtime | tests | docs | Strategy |
| --- | --- | --- | --- | --- | ---: | --- | --- | --- | ---: | --- | --- | --- | --- | --- | --- |
| A024 | `4c99bd3` | accepted/reference | `58d9b70` | `58d9b70` | 1 / 10 | NO | NO | NO | 2 | NO | NO | NO | NO | YES | EXACT_IMPORT |
| B028 | `2c8b879` | accepted/reference | `ca97580` | `58d9b70` | 2 / 10 | NO | NO | NO | 2 | NO | NO | YES | YES | NO | SELECTIVE_IMPORT |
| B029 | `e02ef16` | accepted/reference | `58d9b70` | `58d9b70` | 1 / 10 | NO | NO | NO | 2 | NO | NO | NO | NO | YES | EXACT_IMPORT |
| B030 | `ade769b` | accepted/reference | `2c8b879` | `58d9b70` | 3 / 10 | NO | NO | NO | 3 | NO | NO | YES | YES | YES | SELECTIVE_IMPORT |
| B031 | `9f2f86f` | accepted/reference | `58d9b70` | `58d9b70` | 1 / 10 | NO | NO | NO | 2 | NO | NO | NO | NO | YES | EXACT_IMPORT |
| C019 | `cb8f7e0` | accepted/reference | `8016d7a` | `58d9b70` | 2 / 10 | NO | NO | NO | 3 | NO | NO | YES | YES | YES | SELECTIVE_IMPORT |
| C020 | `2d2d20a` | accepted/reference | `58d9b70` | `58d9b70` | 1 / 10 | NO | NO | NO | 2 | NO | NO | NO | NO | YES | EXACT_IMPORT |
| D018 | `4f0546d` | accepted/reference | `58d9b70` | `58d9b70` | 1 / 10 | NO | NO | NO | 4 | NO | NO | YES | YES | YES | SELECTIVE_IMPORT |
| F012-R1 | `9170132` | accepted/reference | `0fa0646` | `b75308d` | 2 / 0 | YES | NO | NO | 4 | NO | NO | YES | YES | YES | SELECTIVE_IMPORT |
| A025-R1 | `d140192` | pending Owner review | `0d3d639` | `b75308d` | 2 / 0 | YES | NO | NO | 4 | NO | NO | YES | YES | YES | SELECTIVE_IMPORT |
| B032-R1 | `ab260bd` | pending Owner review | `0f1fcaa` | `b75308d` | 2 / 0 | YES | NO | NO | 2 | NO | NO | NO | NO | YES | EXACT_IMPORT |
| C021-R1 | `8af8e69` | pending Owner review | `f8124b4` | `b75308d` | 2 / 0 | YES | NO | NO | 3 | NO | NO | YES | YES | YES | SELECTIVE_IMPORT |
| D019-R1 | `9d01f8b` | pending Owner review | `89bd0f4` | `58d9b70` | 3 / 10 | NO | NO | NO | 4 | NO | NO | YES | YES | YES | SELECTIVE_IMPORT |
| F013 | `becea9e` | pending Owner review | `b75308d` | `b75308d` | 1 / 0 | YES | NO | NO | 3 | NO | NO | NO | NO | YES | EXACT_IMPORT |

The abbreviated SHA values in this table are only for readability; the JSON
artifact contains every full SHA. Every candidate also has an exact local
branch/ref, an exact `origin/` remote ref, and an identifiable worktree. The
full branch and worktree mapping is in the JSON artifact.

### Exact direct changed-file classification

The candidate tips have no direct `app.py` changes and no direct schema-file
changes. Direct file classes are:

* A024, B029, B031, C020, and F013: documentation/matrix only.
* B028, B030, C019, D018, F012-R1, A025-R1, C021-R1, and D019-R1: pure or
  route-independent runtime modules plus tests and/or evidence docs.
* B032-R1: design documentation only; its proposed schema is not code.

The absence of direct `app.py` changes is not a runtime integration claim.
These modules are not wired into the current application routes by their
candidate commits. Future wiring is therefore a new integration boundary.

## Exact Git dependency graph

### Verified Git edges

Only two edges among the named candidate tips are direct ancestry:

```text
B028 2c8b879a...
  └── B030 ade769b9...

D018 4f0546d4...
  └── unlisted D019 base 89bd0f4...
        └── D019-R1 9d01f8b7...
```

The other R1 candidates are based on unlisted candidate-base commits:

| R1 candidate | Exact parent | Meaning |
| --- | --- | --- |
| F012-R1 | `0fa0646541e0147778d502639f49145f050aa0e1` | unlisted F012 boundary base |
| A025-R1 | `0d3d63919ebaac17f08fb4df10385c38c67e6d13` | unlisted A025 API contract base |
| B032-R1 | `0f1fcaab373913948dc8d98a0b9d3632156943fe` | unlisted B032 invariant-design base |
| C021-R1 | `f8124b4d77cf04f2b9fb09fd5e8a5f14faeb93fe` | unlisted C021 adapter base |
| D019-R1 | `89bd0f4ffd27684598c194f32432310e131226a1` | unlisted D019 adapter base after D018 |

This is why `current master is ancestor of candidate = YES` does not mean an
R1 tip is a self-contained one-commit import. The complete stack or a clean
current-master transplant must be used.

### Architectural dependencies, separated from Git ancestry

```text
B028 -> B030 -> A025-R1
                 ^
                 |
               A024/B029 presentation evidence

B031 -> B032-R1 -> equipment schema/runtime decision

C019 + C020 -> C021-R1 -> future Shop route wiring

D018 -> D019-R1 -> producer-specific acquisition adapters

F010 + F012-R1 + F013 -> future World/Monster adapter
```

These arrows are architectural dependencies, not claims that the commits are
Git ancestors. In particular:

* A025-R1 consumes the B028/B030 shape, but its current Git parent is the
  unlisted A025 contract commit.
* C021-R1 normalizes server-resolved offers for C019; it does not contain the
  C019 operation schema.
* D019-R1 adapts committed producer facts into D018; it does not perform
  acquisition or item use.
* F012 is a boundary contract only. It does not select a Monster, settle
  combat, persist World milestones, or grant progress.

## Current app.py collision result

### Direct candidate collision

`CURRENT_CANDIDATE_DIRECT_APP_PY_TOUCH_COUNT=0`
`DIRECT_CHANGED_FILE_OVERLAP_COUNT=0`

There is no exact same-file candidate collision to resolve in the listed
candidate commits. This is a useful topology fact, not permission to wire
multiple routes in parallel.

### Prospective integration collision groups

E025 identifies six future app.py collision groups. They are semantic
integration targets and are intentionally not changed here.

| Group | Existing app.py seam | Candidate inputs | Collision class | Schema prerequisite | Risk | Owner |
| --- | --- | --- | --- | --- | --- | --- |
| Player Presentation route | new authenticated read route and session identity handoff | A024, B028, B030, A025-R1 | SHARED_ROUTE | no | medium | E |
| Equipment legacy retirement | `skills_character`, `_get_appearance_effects`, `/api/skills/character` | B031, B032-R1 | SHARED_HELPER | conditional | high | E |
| Equipment slot writer | `equip_item`, `/api/player/inventory/equip`, admin/drop writers | B028, B031, B032-R1 | SHARED_TRANSACTION | yes for hard invariant | high | E |
| Shop catalog adapter | `shop_catalog`, `shop_buy`, `shop_buy_appearance`, Coin debit | C019, C020, C021-R1 | SHARED_TRANSACTION | C019 operation schema | high | E |
| Acquisition producer wiring | Monster, Quest, Premium, Shop result boundaries | D018, D019-R1 | SHARED_HELPER | no new D018/D019 schema | medium | E |
| World/Battlefield Boss wiring | adventure Boss start/finish and Map Battle settlement handoff | F012-R1, F013 | SEMANTIC_ORDERING_CONFLICT | milestone storage decision | high | E |

The exact route/function inventory, guards, and required predecessors is in
`e025_app_py_collision_matrix.json`. The most important boundary rules are:

* the Player route must remain a read projection and must not become World,
  Quest, Shop, Premium, or combat authority;
* `player_inventory.equipped` and server `EQUIPMENT_DEFS` remain functional
  Equipment authority; `player_appearance.combat_*` is a legacy split to
  retire or quarantine, not a second combat authority;
* Shop must preserve `user_stats.coins` and `currency_log` as the only Coin
  authority and must not feed C019 gacha, cash, Premium, or free grants;
* D018/D019 can translate only committed producer facts; they cannot grant or
  retry a producer;
* World may authorize a Battlefield Boss intent, while Monster settlement
  emits the committed defeated fact. Neither path may directly set Zone clear,
  Star, Lord readiness, or next-zone unlock.

## Schema dependency map

E025 did not modify schema and did not query Production. The statuses below
are deliberately separated:

| Group | Schema designed | Schema code exists | Schema merged into current master | Production migrated | Feature enabled | Evidence / gate |
| --- | --- | --- | --- | --- | --- | --- |
| C019 `coin_purchase_operations_v1` | YES | YES in C019 lineage | NO | NOT_ASSESSED_NO_PRODUCTION_ACCESS | NO | C019 imports `migrations.coin_purchase_operations_v1`; current master does not contain that migration. Route cutover requires separate migration review. |
| B032 Strategy A `canonical_slot` | YES | NO | NO | NOT_ASSESSED_NO_PRODUCTION_ACCESS | NO | B032-R1 is docs-only. It proposes nullable projection, backfill, equipped-row validity, and partial unique constraint. |
| D018/D019 acquisition result | NO new schema | NO | NO | NOT_ASSESSED_NO_PRODUCTION_ACCESS | NO | Pure result/adapter contracts; D5A/D5C existing authorities remain separate. |
| F012 World milestone storage | OWNER DECISION REQUIRED | NO | NO | NOT_ASSESSED_NO_PRODUCTION_ACCESS | NO | F012 explicitly says future adapter/storage sufficiency is unresolved. |
| A024/B028/B030/A025 presentation read | NO | NO | NO | NOT_ASSESSED_NO_PRODUCTION_ACCESS | NO | Read-only projection/transport; no new persistence is authorized. |

`migrations/coin_purchase_operations_v1.py` is present in the C019 candidate
lineage and absent from current master. C019 also relies on existing event
outbox/D5A foundations. It is therefore incorrect to describe C019 as a
runtime-only route import, even though the direct C019 commit itself did not
change a migration file.

B032's recommended Strategy A is not ready for implementation merely because
the design is clear. It still requires a current-master migration task,
backfill/preflight detection, all-writer coverage, and an Owner gate. F012's
World milestone storage is not a missing filename to be guessed; it is a
product/authority decision.

## Recommended merge waves

The complete machine-readable wave plan is in
`e025_recommended_merge_waves.json`. The safe dependency-aware sequence is:

### Wave 1 — Player read foundation

Inputs: A024, B028, B029, B030.
Hold: A025-R1 until Owner PASS.

Import the B028 read model before B030. Keep A024/B029 as evidence docs. Use
selective import for the runtime modules because the old-base stack is not a
current-master branch, even though neither module changes `app.py`. No schema
is required. The acceptance boundary is a read-only Player/Hero projection,
not a new Player state writer.

### Wave 2 — Canonical acquisition foundation

Input: D018.
Hold: D019-R1 until Owner PASS.

D018 is a pure committed-result envelope and should precede producer adapters.
D019-R1 must be imported with its D018 lineage, not alone. D5A remains
acquisition evidence and D5C remains item-use authority.

### Wave 3 — Equipment invariant preparation

Input: B031.
Hold: B032-R1 until Owner PASS and a schema implementation task exists.

B031 evidence should be available before any loadout writer centralization.
The hard invariant is not complete until malformed rows are detected,
`canonical_slot` is backfilled, all writers are covered, and the two database
gates are added in a separately authorized migration. Do not retire the legacy
writer by naming alone.

### Wave 4 — Commerce operation and offer foundation

Inputs: C019 and C020.
Hold: C021-R1 until Owner PASS.

C019 provides the exactly-once operation boundary but is not a live route.
C020 supplies offer/catalog reconciliation. C021-R1 can be transplanted only
after its pending review and only into the current C019/C020 contract. The
operation schema must be reviewed before Shop route cutover; E025 does not run
it.

### Wave 5 — World/Monster boundary

Input: F012-R1.
Hold: F013 until Owner PASS.

Import the complete F012 contract series, not only the R1 commit. It is
current-master-based and pure, but it deliberately does not implement World
milestone storage or runtime selection. F013 remains a pending evidence input.

### Wave 6 — Single-owner app.py wiring and combined acceptance

No candidate SHA is merged by this wave. After the preceding contracts and
pending reviews are resolved, Lane E uses one fresh current-master integration
worktree and one executor. The internal sequence is:

1. Player Presentation read route;
2. D018/D019 producer adapters at committed result boundaries;
3. Equipment writer/invariant cutover;
4. Shop offer/C019 purchase route;
5. World/Battlefield Boss adapter.

Each boundary gets its own focused tests and provenance checkpoint. This wave
requires new explicit Owner GO_MERGE authorization; it does not grant deploy,
feature enable, or Production migration.

## Stacked-candidate policy

The correct rule is not “cherry-pick the newest SHA.” The recommended policy
for each stack is:

| Stack | Recommendation | Reason |
| --- | --- | --- |
| B028 -> B030 | integrate B028 first, then transplant B030 | B030 directly imports B028 and the B030 tip is not self-contained without it |
| A025 -> A025-R1 | keep pending; rebuild/forward-transplant after Owner PASS | R1 parent is unlisted and the route contract must be checked against current B028/B030 |
| D018 -> D019-R1 | integrate D018 first, then import D019 | D019 adapters produce D018 results and must not invent producer authority |
| F012 -> F012-R1 | import the complete pure-contract series as one controlled unit | R1's direct parent is the unlisted F012 base; R1 alone is not a self-contained contract |
| B032 -> B032-R1 | preserve design evidence, implement schema later on current master | both commits are documentation/design; no schema exists yet |
| C021 -> C021-R1 | transplant onto current C019/C020 after Owner PASS | adapter semantics are tied to Shop offer policy and C019 mapping |
| D019 -> D019-R1 | include D018 and the producer-adapter base | D019-R1 is three commits ahead of the old master merge-base |

No candidate history should be rewritten. A future integration branch may
selectively import the exact behavior or reimplement it forward on current
master, but the choice must be recorded with tests and must preserve the Owner
locks.

## Next app.py integration recommendation

`NEXT_APP_PY_INTEGRATION=PLAYER_PRESENTATION`

Why:

* B028 and B030 are accepted read-only foundations with clear authority
  boundaries;
* A024 supplies the surface/readiness evidence and does not require runtime
  changes;
* the route has no schema prerequisite;
* the route can be added without touching combat settlement, acquisition,
  Shop transactions, or World milestones;
* it provides the shortest visible coherence gain for an authenticated player;
* it has lower collision risk than the Equipment legacy split, the C019
  transaction schema, producer wiring, or Battlefield Boss/World wiring.

The recommendation is conditional, not an implementation authorization. Before
route code is written, A025-R1 must either receive Owner PASS or be replaced by
an explicitly approved current-master contract. The route must authenticate
first, call the B030 service once, serialize the A025-compatible read envelope,
and never become a state writer.

## Candidate status summary

| Metric | Result |
| --- | ---: |
| Total candidates reconciled | 14 |
| Owner-accepted/reference and unmerged | 9 |
| Pending Owner review | 5 |
| Stacked candidates | 8 |
| Direct candidate app.py writers | 0 |
| Prospective app.py collision groups | 6 |
| Concrete schema prerequisite groups | 3 |
| Recommended merge waves | 6 |
| RPG Core systems | 10 |

The eight stacked candidates are B028, B030, C019, F012-R1, A025-R1,
B032-R1, C021-R1, and D019-R1. A candidate may be current-master-based and
still be stacked on an unlisted task-base commit; those are separate facts.

## E025 scope closure

E025 changed no runtime, app.py, schema, migration, Production, feature flag,
or deployment surface. It did not merge any candidate and did not grant
GO_MERGE. The four documentation artifacts are the only intended output and
are marked Owner-review-required by this task.

The next task may use this package to create a single-owner integration
worktree. It must re-fetch current `origin/master` immediately before any
authorized merge or implementation mutation and stop on drift.
