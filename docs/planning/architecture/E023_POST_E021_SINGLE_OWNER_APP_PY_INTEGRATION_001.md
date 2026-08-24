# E023 — Post-E021 Single-Owner app.py Integration

Task: E023_POST_E021_SINGLE_OWNER_APP_PY_INTEGRATION_001

Status: current-master integration candidate; unmerged; Owner review required.

## Control gates

CANONICAL_REPOSITORY=D:\go-website
START_ORIGIN_MASTER=58d9b7047f285751a048fc551c955909c87984ac
MASTER_MATCHED_EXPECTED=YES
INTEGRATION_WORKTREE=D:\go-website-e023-post-e021-integration
INTEGRATION_BRANCH=codex/e023-post-e021-single-owner-integration
INTEGRATION_BASE=58d9b7047f285751a048fc551c955909c87984ac
APP_PY_SINGLE_OWNER=YES
PRODUCTION_MIGRATION_RUN=NO
PRODUCTION_MUTATION=NO
MASTER_MERGE=NO
DEPLOY=NO
FEATURE_ENABLE=NO

Implementation was performed in the isolated worktree. The canonical
checkout's pre-existing staged planning state was not changed. Protected
files, including secret_key.txt, were not inspected or touched.

## Exact candidate strategies

| Candidate | Exact SHA | E022 strategy | E023 result |
|---|---|---|---|
| C017-R1 Premium | 9cd6db3ec1ce78f10bcc9d51a4e522c1a04fa9b6 | REIMPLEMENT_ON_CURRENT_MASTER | PASS |
| F009 + F010 Monster selector | a7a6c121d63327fb65970e866aa12e9f2cb7d1e7 + 377738dc31adc8de179d7848cf00b3c2076504c8 | SELECTIVE_IMPORT | PASS |
| B027-R2 Spirit Combat | fc3441808a53fdd222d060bef0cace00b62b45bb | SELECTIVE_IMPORT | PASS |
| D017 Quest V2 | 53fa679d77f0a0c5ab2e938e749a3b19914b826b | SELECTIVE_IMPORT | PASS |

F009 and the F003–F008 Monster foundations, and D012–D016 Quest ancestors,
were imported because the exact target candidates depend on them and current
master did not contain those modules. F007 was not imported or activated.
The historical candidate SHAs were not rewritten.

## Integration commits

| Commit | Boundary |
|---|---|
| 5bc2da89f245f436a15e053c34575513872386f2 | C017 live Premium projection |
| 499b1a6fcf66a7fb06d2e6ab9c7532b60830a353 | F003–F010 Monster selector/settlement lineage |
| 884418e9328445527939b978fe9c6cebf06db253 | B027 locked Spirit combat settlement |
| e0e096d1d9d999cea2fc0c60bdf980d7ded7dbeb | D012–D017 Quest V2 runtime bridge |
| a509c8c1b431f1efdd2a36f1c4e78b51d72cfb09 | combined settlement compatibility/test closure |

Boundary file evidence:

* C017: admin.html, app.py, C017 projection test, and payment entitlement
  atomicity test.
* Monster: app.py, event_outbox.py, map_battle_runtime.py, Monster
  identity/profile/drop/reward/settlement/selector modules,
  migrations/monster_encounter_selector_state_v1.py, review adapters, and
  the F003–F010/Map Battle tests (28 files).
* B027: app.py, map_battle_runtime.py, the two Spirit runtime/policy
  modules, and the B027/equipment tests (7 files).
* Quest: app.py, Quest catalog/identity/period/progress/claim/reward/runtime/
  API/config modules, login_journey_authority.py, the three Quest migrations,
  and D013–D017/Quest tests (28 files).
* Final compatibility boundary: app.py,
  tests/test_b027_r2_spirit_runtime.py, and
  tests/test_rpg_wave2_gate2_equipment_backpack.py.

## Final authority map and semantic reconciliation

The integrated app.py has one Lane E writer and preserves these authorities:

| Domain | Authority |
|---|---|
| Question correctness | SGF/server judge; client correct/grade claims are ignored |
| Premium live projection | one _evaluate_premium_entitlement; _premium_live_from_fields delegates to it |
| Monster identity/profile | F003–F008 registries; F010 durable binding when enabled |
| Combat settlement | map_battle_runtime.settle_answer and one settle_map_battle_submission |
| Spirit effect | B022 active projection plus locked B027 policy/runtime |
| Monster defeat acquisition | F006 settle_monster_defeat with D5A lineage |
| Quest progress/claim | D017 quest_runtime.apply_quest_runtime_event and Quest V2 APIs |

The live Premium evaluator count is 1. The helper used by auth/admin/
subscription projections is not a second entitlement authority.

The combined Map Battle order is:

server question/judge
→ F010 server Monster identity/profile when selector binding is active
→ B021 Equipment / Armor
→ B027 Spirit effect
→ one map_battle_runtime settlement
→ F006 Monster reward/lineage settlement only on defeat
→ Quest V2 event projection/application

The locked damage order remains:

outgoing: base → Equipment → Spirit → settlement
incoming: Monster ATK → Armor → Spirit → settlement

The F006 step after a Map Battle defeat is acquisition/lineage settlement,
not a second HP/combat settlement. Retry cannot reapply Spirit or HP.
Exactly one active Spirit is supported; the B027 balance lock and Lord Trial
Spirit exclusion remain intact.

The Quest order is:

server answer judgement
→ authoritative Combat/Monster result
→ committed Monster settlement/event where applicable
→ Quest V2 event application
→ existing XP/Coin/item authorities

Quest V2 is default-off. When enabled, D017 suppresses the legacy Daily
writer for that path. Quest does not own correctness, Combat, Monster
settlement, Spirit, World progression, Premium, Inventory, or XP authority.
Internal Monster/Quest bridge fields are removed before the legacy public
review response is serialized.

## Feature matrix

| Monster selector | Quest V2 | Contract |
|---|---|---|
| OFF | OFF | legacy Map Battle and legacy Daily behavior preserved |
| ON | OFF | durable server Monster selection; legacy Quest behavior |
| OFF | ON | Quest V2 consumes existing Monster path; legacy Daily suppressed |
| ON | ON | selected Monster → canonical Combat/Spirit settlement → Quest event |

All four combinations were covered by the relevant integration suite. F007's
unapproved 100-row roster is not activated by any combination. F010 cannot
grant Zone clear, Stars, Lord readiness, Lord clear, or next-zone unlock.

## Migration graph

Current master already contains the D5 foundations used here:

domain_event_outbox_v1
review_log_submission_idempotency_v1
question_capacity_lineage_v1
item_use_operations_v1
premium_claim_lineage_v1
premium_reward_bundle_v1

Candidate-only migration order:

current D5 foundations
→ monster_encounter_selector_state_v1
→ quest_progress_v2
→ quest_claim_v1
→ login_journey_v1
→ runtime cutover only after schema validation

The Monster selector migration is independent of the Quest migrations. No
migration was executed and no Production schema was changed. No migration ID
overlap was found.

## Validation

PostgreSQL-specific tests were skipped because no explicitly disposable
PostgreSQL target was supplied. No shared or Production database was used.

| Boundary | Result |
|---|---|
| Current-master baseline selected safe RPG/E10 suite | 164 passed, 3 deselected |
| C017 integrated | 38 passed, 2 deselected |
| F009/F010 Monster boundary | 156 passed, 3 deselected |
| B027/F010/Map Battle/Equipment boundary | 228 passed, 4 deselected |
| D017 Quest boundary | 97 passed |
| Final combined suite, including Wave2 drop fixture | 322 passed, 4 deselected |
| Python compile/import checks | PASS |
| git diff --check | PASS |

The broad non-PostgreSQL repository run ended:

48 failed, 1 error, 5 deselected

Those failures were classified as pre-existing/stale or infrastructure-only:

* deployment/static tooling lacked Get-FileHash in the test PowerShell
  environment; temporary worktree tests also hit Windows filename-length and
  registered-worktree limits;
* protected-file harness tests correctly refused synthetic secret_key.txt
  access;
* old E10/SW/cache/version/source-shape expectations and Lane A scope tests
  do not match current master or intentionally reject E023 app.py integration;
* existing asset-closure failures concern missing/unmanifested Wave2 assets;
* old armor-authority expectations and the missing go_stone_black image
  fixture are known pre-existing limitations.

The one relevant Wave2 drop fixture was adapted to the canonical F005/D5A
interfaces and is green in the final combined suite.

TASK_INTRODUCED_FAILURES=0
RELEASE_CLOSURE_FAILURES=0
UNCLASSIFIED_FAILURES=0
POSTGRES_TEST=SKIPPED_ENVIRONMENT_GAP

## Remaining gaps and next gate

Out of scope remains: Production migration/schema change, feature enable,
deployment, F007 full roster activation, World progression consolidation,
Battlefield Boss eligibility, Coin purchase, Backpack/Wardrobe/Shop UI,
Revenue enable, Spirit rebalance, and final PostgreSQL concurrency evidence.

The branch is not merged. A new Owner GO_MERGE is required; later GO_DEPLOY
and any feature-enable decision remain separate.

PR_NUMBER=NONE
PR_STATE=NOT_OPENED
PR_MERGED=NO
INTEGRATION_HEAD_BEFORE_EVIDENCE_COMMIT=a509c8c1b431f1efdd2a36f1c4e78b51d72cfb09

