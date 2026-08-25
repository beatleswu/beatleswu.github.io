# E029 Post-PR400 Multi-Lane Current-Master Reconciliation

Status: Owner review required

## Scope and source gate

This is a read-only topology and integration-order reconciliation. It does not merge a
candidate, change runtime code, execute a migration, enable a flag, query Production, or deploy.

The exact source verified for this task is:

- current origin/master: e2669bfa8582239dd001dbb41b2cd134923e9e27
- previous canonical master: b75308d44806bb7c2e2b131a73ba06a71c188b3
- PR400 accepted head: 709d052cc773036468908f41c963c0d46d64c2ab
- PR400 merge: e2669bfa8582239dd001dbb41b2cd134923e9e27
- PR400 merge tree: 89cc56e209b8a787881b1304aa6c2eb27e015ea6

origin/master was fetched immediately before the audit and matched the expected current
master. All candidate comparisons below are recomputed against e266, not copied from an
older ahead/behind report.

## Executive result

The seven accepted/reference foundation SHAs are all exact local Git objects and are reachable
from named local and remote candidate refs. None is an ancestor of e266, and e266 is not an
ancestor of any of the seven accepted SHAs. Their common merge-base is the previous master
b75308d44806bb7c2e2b131a73ba06a71c188b3.

Therefore:

- accepted candidates directly forward-integratable by Git fast-forward: 0;
- accepted candidates that can be used as behavioral/provenance inputs: 7;
- accepted runtime candidates that require a new current-master reconciliation candidate: B034,
  C023, D020, and F014;
- accepted documentation candidates that remain useful after explicit source reconciliation:
  A027 and D021;
- B034 is a true Git child of B033;
- C023 is a commerce stack that contains an equipment-slot commit distinct from B033, but its
  equipment migration and test blobs are byte-identical to the B033 blobs;
- no audited accepted foundation directly changes a PR400 Player Presentation file;
- future route/event wiring still requires one serial Lane E app.py integration owner.

The exact topology and machine-readable wave plan are in:

- e029_post_pr400_candidate_topology_matrix.json
- e029_post_pr400_merge_wave_matrix.json

## PR400 change domain

PR400 introduced the current Player Presentation read foundation:

| Surface | Current-master evidence |
| --- | --- |
| app.py imports | player_presentation_read_service and player_presentation_api_contract |
| app.py route | GET /api/player/presentation at the get_player_presentation handler |
| canonical read model | player_state_read_model.py |
| read service | player_presentation_read_service.py |
| transport narrowing | player_presentation_api_contract.py |
| focused tests | A025, B028, B030, E026, and E027 tests |

The PR400 merge changed ten tracked paths: app.py, the three Player Presentation Python
modules, one A025 planning matrix, and the A025/B028/B030/E026/E027 focused tests.

The seven accepted E029 foundation diffs have zero exact-path intersection with that ten-path
PR400 set. No accepted B/C/D/F foundation imports a Player Presentation module. The collision
that remains is prospective: adding equipment, commerce, acquisition, or World/Boss public
routes to app.py must be done serially, without altering the Player Presentation route's
session identity and read-only contract.

## Accepted candidate topology matrix

| Candidate | Parent | Merge-base with e266 | Ahead / behind e266 | Current-master ancestor status | Exact commit files | Strategy |
| --- | --- | --- | --- | --- | --- | --- |
| A027 605ada21d2e179a8b2c7292da40a8333d00738d2 | b75308d44806bb7c2e2b131a73ba06a71c188b3c | b75308d44806bb7c2e2b131a73ba06a71c188b3c | 1 / 4 | neither direction | 3 documentation files | reconcile docs on current master |
| B033 15f665f656418ab189d32aa809c163f3e27fa92c | b75308d44806bb7c2e2b131a73ba06a71c188b3c | b75308d44806bb7c2e2b131a73ba06a71c188b3c | 1 / 4 | neither direction | equipment migration and test | current-master schema reconciliation |
| B034 e7235ef74bcf2a31c190e3a6ce320bc8ee6c3e74 | B033 exact SHA | b75308d44806bb7c2e2b131a73ba06a71c188b3c | 2 / 4 | neither direction | equipment_loadout_service.py and test | selective import on current master |
| C023 ab588aa28cbae92a8c29bffe575b67b1f3207793 | f3ee9a6f13f69bbc2add0b709109048e2ef22036 | b75308d44806bb7c2e2b131a73ba06a71c188b3c | 8 / 4 | neither direction | coin purchase authority, docs, and tests | selective import on current master |
| D020 d251ed92c46ebf6e7806ba4258ba6ba6b032e4a6 | 200fe5411cb0ea7772ee1784de6f7edcabbfe03c | b75308d44806bb7c2e2b131a73ba06a71c188b3c | 3 / 4 | neither direction | acquisition adapter, docs, and tests | selective import on current master |
| D021 3e764df5dbc1aefb487f770d7f2ac673362978b3 | b75308d44806bb7c2e2b131a73ba06a71c188b3c | b75308d44806bb7c2e2b131a73ba06a71c188b3c | 1 / 4 | neither direction | 3 documentation files | reconcile docs on current master |
| F014 9dda188a7a52b02d680cd6ff7aedaf891169bb12 | b75308d44806bb7c2e2b131a73ba06a71c188b3c | b75308d44806bb7c2e2b131a73ba06a71c188b3c | 1 / 4 | neither direction | World/Boss boundary modules, docs, and tests | selective import on current master |

The complete file-level classification, branch refs, exact parent/tree data, candidate
dependencies, and collision sets are in the JSON artifact. All seven accepted SHAs are
remote-visible on dedicated candidate refs before E029 publication.

### B033 / B034 topology

B034 is a true Git child of B033:

B033 15f665f656418ab189d32aa809c163f3e27fa92c
→ B034 e7235ef74bcf2a31c190e3a6ce320bc8ee6c3e74

B034 does not change app.py. It adds the loadout service and tests, and its runtime contract
requires the B033 canonical_slot schema. A future app.py equipment route remains a separate
serial cutover.

### C023 duplicated-equivalent schema

C023 follows its own commerce chain:

C019 365a601e1f29b33e0b028f5efb9f9b7a7538d0d6
→ C019 concurrency correction 16d86b006e8a87c897edaedcecd1a9b77fcd2742
→ C020 reconciliation a8c8c41b4d95b0534573b68f911d973a37c59658
→ C021 adapter 2aab903f3edcdb1262fa089f8d1e5263673d4c19
→ C021 zero-price correction 711da28f1a3da44e87b1097e9e5a43e5c792b843
→ C022 reconciliation c61d928a121da01b6b209b34a3d96ddd04514b2b
→ equipment-slot commit f3ee9a6f13f69bbc2add0b709109048e2ef22036
→ C023 ab588aa28cbae92a8c29bffe575b67b1f3207793

The f3ee equipment-slot commit is not the B033 SHA. However, the migration blob
c4ff93bdb6ac98494691dc91a03a2dcd8e2d38c4 and test blob
7ea3196e1a0e257e48fd6d008c6699a8ee6d1506 exactly match the corresponding B033 blobs.
The future integration must select one canonical schema owner and must not import both
schema histories as separate runtime changes.

### D020 topology

D020 is a true child of the D018/D019 acquisition chain:

D018 0571ec05e1acdb13595d46a00404e11fddb58292
→ D019 200fe5411cb0ea7772ee1784de6f7edcabbfe03c
→ D020 d251ed92c46ebf6e7806ba4258ba6ba6b032e4a6

The exact D020 commit changes acquisition adapter evidence semantics and tests. It introduces
no new migration file in its own commit and does not modify app.py.

### F014 / F015 relationship

F014 is accepted as a thin World/Battlefield Boss boundary adapter. F015 is active and
remote-visible, but is not a Git child of F014: it starts from b753 and re-adds byte-identical
F014 module/test blobs together with new World milestone runtime, migration, and tests. F015
therefore needs its own Owner review and current-master reconciliation; it must not be treated
as a clean F014 descendant.

## Active-task overlay

| Task | Audited ref | Task-start master | Current master changed after start | Current implementation visible | Docs-only | Final reconciliation |
| --- | --- | --- | --- | --- | --- | --- |
| A028 | local branch at e266 | e266 | no | no A028-specific delta visible | no | no for current ref; yes for any new runtime commit |
| B035 | remote branch 9361f7de31c0f1a189b19202ce20dd21c6cd690b | b753 | yes | no | yes | yes |
| C024 | local-only branch 0c166440a9894bcd07bcea6b0dbeea8372bdb32b | b753 | yes | no | yes | yes |
| D022 | remote branch 7ab57ee78c74aa4526bfa29b6a8a0aa998604882 | b753 | yes | no | yes | yes; D022 already records the e266 publication drift |
| F015 | remote branch e0a28dedcac1b4cfddfde32e0474de26a1be4b02 | b753 | yes | yes | no | yes; new current-master candidate required |

A028 was created from origin/master after PR400 and is the only active frontend line intended
to adopt /api/player/presentation. Its audited head is currently exactly e266, so no
A028-specific frontend implementation is visible at this ref yet. The route in that branch
is inherited from PR400.

B035, C024, and D022 are documentation-only overlays. Their findings can remain useful when
the source facts are unchanged, but each final task report must explicitly reconcile against
e266. D022 already recorded that origin/master advanced to e266 at publication and that the
Player Presentation paths did not overlap its three docs; its original baseline fields still
identify b753 and are not current-master ancestry.

F015 is runtime/schema work. It cannot be declared current-master-ready from its b753 base;
it needs a new e266-based candidate or an equivalent explicit current-master reconciliation
before any merge gate.

## B lane: Equipment

B033 is a candidate-only additive schema for canonical equipment slots. B034 is the dependent
loadout command service. Neither touches the PR400 file set, imports Player Presentation
modules, or changes app.py.

The actual integration risk is not PR400 core collision. It is future route wiring and the
duplicate-equivalent B033 schema embedded in C023. B033/B034 should be reconciled once on
current master. A later C023 import must consume that canonical slot schema instead of adding
a second schema owner.

No statement here means the schema is merged, Production-ready, or Production-migrated.

## C lane: Commerce

C023's runtime modules are:

- coin_purchase_authority.py
- shop_offer_authority.py
- shop_offer_adapter.py

They do not touch or import the PR400 Player Presentation files. C023 does not change app.py;
the future Shop route is a separate same-file, non-overlapping app.py seam. The commerce
runtime should be selectively imported after the equipment slot authority and canonical
acquisition boundary are resolved. The coin purchase migration remains candidate-only.

The Player Presentation endpoint must not be used as Shop/economy authority, and Shop wiring
must not add commerce fields to the Player Presentation transport contract.

## D lane: Acquisition

D020's canonical_acquisition_result.py and acquisition_result_adapters.py are structurally
independent of PR400. D020 does not change app.py or schema files in its exact commit. Its
future app.py producer/event bridge can still collide with Shop and other producer wiring,
so it belongs under the same serial Lane E integration owner.

D021 is documentation-only. It must not be used to claim that D020 is merged or that any
producer has reached Production.

## F lane: World / Monster / Battlefield Boss

F014 adds a World/Battlefield Boss boundary contract and adapter. It explicitly keeps:

- Battlefield Boss separate from Lord;
- Monster defeat separate from World progression;
- boundary evidence separate from a generic encounter selector;
- future persistence/consumer decisions separate from the pure contract.

F014 has no PR400 file overlap and no direct Player Presentation import. A future app.py
World/Boss binding is a separate non-overlapping seam that must be integrated serially.
F015's milestone storage must remain pending until its own runtime/schema review is complete.

## app.py collision map

The audited accepted commits all have app_py_changed = false. PR400 currently owns:

- the Player Presentation imports near the top of app.py;
- the authenticated GET /api/player/presentation handler;
- the session-derived identity and read-only response boundary.

Future seams are classified as follows:

| Future work | Current evidence | PR400 collision | Integration rule |
| --- | --- | --- | --- |
| B034 Equipment route cutover | B034 has no route | SAME_FILE_NON_OVERLAPPING_SEAM plus import-section collision only | one Lane E app.py writer; preserve Player Presentation route |
| C023 Shop route cutover | C023 has no route | SAME_FILE_NON_OVERLAPPING_SEAM plus import-section collision only | wire only after commerce/acquisition boundaries are settled |
| D020 acquisition producer bridge | D020 has no route | SAME_FILE_NON_OVERLAPPING_SEAM | consume canonical acquisition results; no second producer authority |
| F014 World/Boss binding | F014 has no route | SAME_FILE_NON_OVERLAPPING_SEAM | preserve Boss/Lord and World progression boundaries |
| A028 frontend adoption | current branch has no A028-specific delta | NONE in app.py | only hero/frontend owner changes frontend files; no backend route rewrite |

No evidence shows a same-function collision with get_player_presentation. The required policy
is nevertheless APP_PY_SERIAL_INTEGRATION_REQUIRED = YES because the future route cutovers
share one app.py file and may share imports, error handling, session boundaries, or transaction
helpers.

## Schema and migration readiness

| Candidate/work | Schema designed | Schema code exists | Schema merged | Production migrated | Feature enabled |
| --- | --- | --- | --- | --- | --- |
| PR400 Player Presentation | not required | not required | yes as part of e266 | no migration | read route exists; no new feature enable |
| B033 canonical slot | yes | yes in candidate | no | no | no |
| B034 loadout service | requires B033 | no new schema | no | no | no |
| C023 coin purchase | yes, coin_purchase_operations_v1 | yes in candidate | no | no | no |
| C023 equipment slot copy | duplicate-equivalent B033 blobs | yes in candidate | no | no | no |
| D020 acquisition | no new schema in exact D020 commit | no new migration in exact commit | no | no | no |
| F014 boundary adapter | no schema | no | no | no | no |
| F015 milestone projection | pending candidate schema | yes on active branch | no | no | no |

Schema code existence, merge, Production migration, and feature enable are independent gates.
E029 executes none of them.

## Stale-master policy

The following rule applies consistently after PR400:

1. A docs-only recon may remain reviewable when its findings are source-stable and no changed
   current-master file affects the finding. Its final report must name e266 and explicitly
   reconcile any changed-domain overlap.
2. A runtime implementation must prove that e266 is an ancestor, or produce a new
   current-master-based candidate. A behind candidate is not automatically invalid, but it
   cannot be called merge-ready without reconciliation.
3. A schema candidate must separately report schema code, schema merge, Production migration,
   and enablement.
4. A frontend candidate must use the current Player Presentation API and must not compete for
   hero.html ownership.

## Recommended remaining merge waves

The merged Wave 0 foundation is PR400. The recommended remaining sequence has six waves:

1. Equipment schema and B034 loadout service, with one canonical slot-schema owner.
2. D020 acquisition result and producer adapter foundation, with D021 docs reconciled.
3. C023 commerce core selectively imported, excluding its duplicate B033 schema owner.
4. F014 World/Battlefield Boss boundary adapter. Keep F015 milestone storage separate until
   reviewed.
5. A028 Player Presentation frontend adoption from the e266-created branch.
6. One serial Lane E app.py cutover/combined-acceptance wave for any public equipment, Shop,
   acquisition, and World/Boss routes or event bindings.

Each runtime wave needs a fresh current-master integration candidate, focused tests, a
current-master provenance check, and a new Owner GO_MERGE decision. GO_DEPLOY and feature
enable remain separate and are not granted here.

The next integration owner is LANE_E. Other lanes may prepare pure modules, tests, migrations,
contracts, and docs, but SAME_FILE_MULTIWRITER_FORBIDDEN remains in force for app.py and any
overlapping route-wiring seam.

## E029 boundaries and validation

E029 changed no application runtime, frontend, schema, or Production surface. It performed:

- exact Git object and ancestry inspection;
- exact changed-file and PR400-overlap inspection;
- active branch/ref visibility inspection;
- JSON syntax validation;
- docs-only artifact creation.

No runtime tests or Production queries were required. The two JSON artifacts validate with
Python's JSON parser. Final publication must use an explicit three-file stage and a normal
non-force push; no merge or deploy is implied.

## Owner review conclusion

E029 is ready for Owner review. It is not a GO_MERGE authorization.

The key decision for the next implementation wave is not whether PR400 conflicts with the
accepted B/C/D/F foundation modules: the exact-path audit found no direct core collision.
The key control is to reconcile those old-base inputs onto e266 selectively, choose one
equipment schema owner, preserve one acquisition/commerce authority, and serialize all
future app.py route/event cutovers under Lane E.
