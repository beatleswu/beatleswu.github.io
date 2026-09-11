# GO_ODYSSEY_ACT_F_ACTIVATION_FINAL_INTEGRATION_PREPARATION_001

Status: `READY_FOR_FINAL_INDEPENDENT_INTEGRATION_REVIEW`

This is a durable ACT-F integration-preparation record. It does not grant a
merge, deploy, Production database change, schema application, feature
enablement, or cutover.

## Authority and candidate

```text
TARGET_BRANCH=codex/act-f-activation-final-integration-prep-001
CODE_CANDIDATE_HEAD=837a0c266d1a4a0356fee00e1b54643403801276
CANONICAL_BASE_HEAD=da531c6da0edabab3c025823ec1157e604d56498
CANONICAL_BASE_TREE=e942e346854ba8397900ee5fa1d824cd2a38967a
CODE_CANDIDATE_TREE=b06a322e36f1c333d9bb64c0980f7ed2bd573b36
ACTIVATION_APP_PY_DECOMPOSITION=COMPLETE
```

The candidate was constructed from the canonical base by applying the accepted
ACT-A R1 net diff, then mechanically verifying the carried ACT-B/C/D/E blobs.
No intermediate pre-R1 ACT-A or ACT-C content was reintroduced.

## Activation_0 reconciliation and governance

`docs/planning/go_odyssey_activation_0_integration_governance_d1_001.md` is
carried as the accepted ACT-F D1 authority artifact. It records:

- canonical/Production `da531c6d` coherence;
- Puzzle Identity HOT state: 42,804 active identities, Genesis bootstrap
  applied, Production resolver HOT;
- authenticated E9 and E10 Map Battle admin state;
- live `canonical_slot` schema, Loadout flag off, and absent V2 onboarding
  schema at the accepted baseline;
- the current Friend Challenge persistence gap and four-store inventory model;
- the final D1 ownership matrix and transaction rules;
- current development-scalability governance.

The old mandatory `FULL_ARCHITECTURE_DECOMPOSITION` program is explicitly
marked `SUPERSEDED_CONCEPT`. D1 is activation-coupled decomposition; D2 is
boundary freeze; D3 and D4 are trigger-based tracks, not mandatory sequential
release epochs. Decomposition remains evidence-driven and narrow.

```text
ACTIVATION_0_LIVE_TRUTH_RECONCILED=YES
FULL_ARCHITECTURE_DECOMPOSITION_MARKED_SUPERSEDED=YES
DEVELOPMENT_SCALABILITY_GOVERNANCE_LANDED=YES
```

## Domain blob provenance

Every B/C/D/E-owned file carried by ACT-A was compared to its accepted owner
head with `git rev-parse HEAD:path`. All comparisons are byte-equal.

| PATH | OWNER | SOURCE_HEAD | SOURCE_BLOB | FINAL_BLOB | BYTE_EQUAL |
|---|---|---|---|---|---|
| `map_battle_runtime.py` | ACT-B | `abce846a3edd202849b2e2dc6dc6cd9200d26bf1` | `c4e8941a15a5488d70440b25e47f37afea094f0c` | `c4e8941a15a5488d70440b25e47f37afea094f0c` | YES |
| `tests/test_act_b_provider_boundary_d1.py` | ACT-B | `abce846a3edd202849b2e2dc6dc6cd9200d26bf1` | `78c7eafb5c55ee9b48e93d8a24a7605671198877` | `78c7eafb5c55ee9b48e93d8a24a7605671198877` | YES |
| `coin_reward_authority.py` | ACT-C | `c7f4b7b3b389f5769671dc3de7a8effe0174597a` | `19be7e99d9f4ec9ccaaded36c3b87e6552723cd4` | `19be7e99d9f4ec9ccaaded36c3b87e6552723cd4` | YES |
| `tests/test_act_c_reward_coin_authority_d1.py` | ACT-C | `c7f4b7b3b389f5769671dc3de7a8effe0174597a` | `57eb1b7281f93858a28212ec162b06ef8258f7b6` | `57eb1b7281f93858a28212ec162b06ef8258f7b6` | YES |
| `tests/test_act_c_reward_coin_authority_d1_postgres.py` | ACT-C | `c7f4b7b3b389f5769671dc3de7a8effe0174597a` | `40f303873b1825ee1d5953c4f386d2d1fdf7736a` | `40f303873b1825ee1d5953c4f386d2d1fdf7736a` | YES |
| `shop_inventory_authority.py` | ACT-D | `b02281a77b164cab2af9c957fdd050b0267086bd` | `9ad3ba99965752fd833edd3fca1291088cc045d1` | `9ad3ba99965752fd833edd3fca1291088cc045d1` | YES |
| `tests/test_act_d_inventory_authority_d1.py` | ACT-D | `b02281a77b164cab2af9c957fdd050b0267086bd` | `dbd97a14b653358097af6b98cf09ed4c6b67d758` | `dbd97a14b653358097af6b98cf09ed4c6b67d758` | YES |
| `docs/planning/act_e_onboarding_v2_d1_implementation_001.md` | ACT-E | `b34c9617021fa27b70afe7ab1fb52fca9daf783d` | `b4055d8224d4a16e8601fa792f2c313a113399b0` | `b4055d8224d4a16e8601fa792f2c313a113399b0` | YES |
| `js/e9/journey_onboarding_view.js` | ACT-E | `b34c9617021fa27b70afe7ab1fb52fca9daf783d` | `efd5fa3f10d3aace45b6494fa4aa2480498269da` | `efd5fa3f10d3aace45b6494fa4aa2480498269da` | YES |
| `onboarding_v2_transition.py` | ACT-E | `b34c9617021fa27b70afe7ab1fb52fca9daf783d` | `2ff1ddb177e8b1df4dc16f13c2f19942b862a454` | `2ff1ddb177e8b1df4dc16f13c2f19942b862a454` | YES |
| `tests/e2e/run_act_e_onboarding_v2_bridge.mjs` | ACT-E | `b34c9617021fa27b70afe7ab1fb52fca9daf783d` | `ca1e3abee849c21512b0d644e116797018179a60` | `ca1e3abee849c21512b0d644e116797018179a60` | YES |
| `tests/test_act_e_onboarding_v2_d1.py` | ACT-E | `b34c9617021fa27b70afe7ab1fb52fca9daf783d` | `c2420b8a711ffdb9e135200d8e9bcb24681860d6` | `c2420b8a711ffdb9e135200d8e9bcb24681860d6` | YES |

```text
ALL_DOMAIN_BLOBS_BYTE_EQUAL=YES
```

## Friend Challenge migration review

ACT-F is the sole writer/reviewer for `migrations/**` and `db.py`.

```text
FRIEND_CHALLENGE_MIGRATION_FILE=migrations/friend_challenge_reward_settlements_v1.py
FRIEND_CHALLENGE_MIGRATION_REVIEW=PASS
FRIEND_CHALLENGE_PENDING_ROLLBACK_SEMANTICS=PASS
FRIEND_CHALLENGE_WIRING=HOLD_FOR_SCHEMA
GO_PRODUCTION_DB_MIGRATION=NOT_GRANTED
```

The candidate migration is additive, idempotent, catalog-presence guarded,
PostgreSQL-safe, dry-run capable, and exact-schema validating. It defines only
`challenge_id`, `user_id`, `settlement_status`, `created_at`, and `settled_at`,
with primary key `(challenge_id,user_id)`, status check `PENDING|SETTLED`, and
index `(user_id,settled_at)`. It has no reward payload columns, does not alter
`reward_claimed`, performs no data rewrite, and contains no commit/rollback.

The migration takes an advisory transaction lock on PostgreSQL and leaves the
caller-owned transaction boundary intact. The ACT-F test proves that a failed
settlement rolls back the temporary PENDING reservation and reward mutation;
the same legitimate settlement can then retry and commit SETTLED. The test
does not apply the schema to Production.

## Onboarding migration review

```text
ONBOARDING_MIGRATION_ALREADY_PRESENT=YES
ONBOARDING_MIGRATION_CHANGE_REQUIRED=NO
ONBOARDING_V2_STATE=IMPLEMENTED_DARK
```

Canonical already contains the accepted `migrations/w2_a1_onboarding_v1.py`
for `wave2_onboarding_state_v1` with exactly the six authority columns:
`user_id`, `state_version`, `status`, `current_step`,
`first_context_attempt_id`, and `updated_at`. It is additive, idempotent,
catalog guarded, and advisory-lock protected. It was not rewritten. The 24
graduated users remain deterministically mappable and 164 in-flight users
remain grandfathered compatibility; no snapshot was changed.

## Packaging reconciliation

| MODULE | ALREADY_PACKAGED | ACTION |
|---|---|---|
| `activation_http_contract.py` | NO | Added one explicit Docker/build-manifest entry |
| `coin_reward_authority.py` | NO | Added one explicit Docker/build-manifest entry |
| `shop_inventory_authority.py` | NO | Added one explicit Docker/build-manifest entry |
| `wave2_onboarding_authority.py` | NO | Added one explicit Docker/build-manifest entry |
| `adventure_zone4_10_monster_runtime_provider.py` | NO | Added exact transitive closure entry |
| `adventure_zone4_10_monster_reward_policy.py` | NO | Added exact transitive closure entry |
| `adventure_zone4_10_monster_identity_authority.py` | NO | Added exact transitive closure entry |
| `adventure_zone1_2_monster_runtime_provider.py` | NO | Added exact transitive closure entry |
| `onboarding_v2_transition.py` | N/A | Test/integration-only; intentionally not runtime packaged |
| `migrations/**` | N/A | Not packaged wholesale; Friend migration is separately reviewable |

No duplicate entries were added. The focused dependency-closure, build-manifest,
and canonical-input suite passed `55` tests after the four transitive entries
were added.

## Evaluator governance reconciliation

- The SRS guard was tied to the obsolete three-commit baseline. Exact base and
  candidate both contain four `_srs_review_operation` commits and identical
  function bytes. The guard now asserts four while retaining the exception and
  rollback assertions; it was not removed.
- The presentation-only guards retain their strict component/view/style
  checks. Their changed-path gate is skipped only when the exact cumulative
  Activation marker set is present (`app.py`,
  `activation_http_contract.py`, and the D1 authority artifact); it is not a
  permanent allow-all rule.
- The F010 selector evaluator expects a 503 even when the accepted ACT-B
  canonical Z1 provider is available. Exact replay: canonical base returns
  `503 monster_selector_unavailable`; the cumulative candidate returns `200`
  through the accepted provider binding. This is a stale evaluator premise,
  not a new selector mutation or a reason to weaken the ACT-B provider path.
- Remaining broad failures were compared against the exact canonical base and
  retained only as `BASELINE_IDENTICAL`, `STALE_EVALUATOR_PROVEN`, or
  `ENVIRONMENT_BLOCKED`. The authenticated E2E error signature is the same
  PostgreSQL harness `UnicodeDecodeError` at byte `0xb5`; the static closure
  signature is the test-generated audio manifest size mismatch (`expected
  73656, got 73680`). The protected untracked `secret_key.txt` was preserved,
  never inspected, and never staged.

## Transaction and identity checks

| AUTHORITY | COMMIT/ROLLBACK OWNER |
|---|---|
| HTTP transaction coordinator | ACT-A |
| Battle mutation | ACT-B; no independent runtime commit/rollback |
| Reward/Coin mutation | ACT-C; no independent runtime commit/rollback |
| Inventory mutation | ACT-D; no independent runtime commit/rollback |
| Onboarding mutation | ACT-E; no independent outer-flow commit/rollback |
| ACT-F runtime transaction ownership | NO |

Focused coverage passed Map Battle provider persistence, Rewards Sync,
shop-inventory consume, V2 onboarding dark path, and Friend Challenge rollback
semantics. Migration/bootstrap setup helpers are separate setup concerns and do
not become cross-domain settlement owners.

```text
HTTP_TRANSACTION_COORDINATOR=ACT-A
ACT-B_COMMIT_ROLLBACK=NO
ACT-C_COMMIT_ROLLBACK=NO
ACT-D_COMMIT_ROLLBACK=NO
ACT-E_COMMIT_ROLLBACK=NO
ACT-F_RUNTIME_TRANSACTION_OWNERSHIP=NO
PUZZLE_IDENTITY_MUTATION=NO
PUZZLE_IDENTITY_SCHEMA_MUTATION=NO
PUZZLE_IDENTITY_AUTHORITY_DUPLICATION=NO
PUZZLE_IDENTITY_HOT_CONTRACT=PASS
```

No identity, puzzle-identity, QuestionsCorpus, or identity-schema file changed.
The 42,804 active-identity HOT state remains the authority; it is not confused
with the 41,591 live QuestionsCorpus content records.

## Feature and ownership state

```text
FEATURE_FLAGS_CHANGED=NO
E10_MAP_BATTLE_ROLLOUT=UNCHANGED
ONBOARDING_V2_CUTOVER=UNCHANGED_IMPLEMENTED_DARK
FRIEND_CHALLENGE_CUTOVER=HOLD_FOR_SCHEMA
EQUIPMENT_CANONICAL_LOADOUT=UNCHANGED_OFF
CANONICAL_COIN_SHOP=UNCHANGED
ZONE4_10_ROLLOUT=UNCHANGED
```

```text
ACT_A_REVIEW_STATE=PASS_COORDINATOR_REVIEW_ACCEPTED
ACT_B_REVIEW_STATE=PASS_COORDINATOR_REVIEW_ACCEPTED
ACT_C_REVIEW_STATE=PASS_COORDINATOR_REVIEW_ACCEPTED
ACT_D_REVIEW_STATE=PASS_COORDINATOR_REVIEW_ACCEPTED
ACT_E_REVIEW_STATE=PASS_COORDINATOR_REVIEW_ACCEPTED
ACT_F_REVIEW_STATE=PASS_INTEGRATION_PREPARATION
```

## Test evidence

Focused ACT-A/B/C/D/E/F, governance, migration, onboarding, and atomicity
coverage passed. The nine new ACT test files collected 74 tests and passed
`74 passed` in isolation. ACT-C PostgreSQL concurrency passed `2 passed`.
The ACT-E Node bridge passed `18` checks. Map Battle regression passed
`89 passed, 1 skipped`; Puzzle Identity regression passed `66 passed, 49
skipped`; packaging/build-manifest passed `55 passed`.

Required full-directory runs from clean cache/output configuration:

```text
FULL_GATE_RUN_1=FAIL_RAW: 5715 passed, 278 skipped, 118 failed, 9 errors, 53 warnings
FULL_GATE_RUN_2=FAIL_RAW: 5715 passed, 278 skipped, 117 failed, 10 errors, 52 warnings
FULL_GATE_DIAGNOSTIC_RUN=FAIL_RAW: 5715 passed, 278 skipped, 117 failed, 10 errors, 54 warnings
EXACT_BASE_COMPARISON=5670 passed, 265 skipped, 102 failed, 9 errors, 54 warnings
NEW_CANDIDATE_INTRODUCED_UNBASELINED_FAILURES=0
```

The raw full-directory gate is not represented as green. The accepted
Activation-focused gates are green, and every remaining full-directory
failure/error has an exact base, stale-evaluator, or environment signature
recorded above for independent review.

## Containment and final gates

The tracked candidate changes relative to `da531c6d` are limited to accepted
ACT-A R1 integration content, exact B/C/D/E carried blobs, ACT-F D1 artifacts,
the Friend Challenge migration candidate, explicit runtime packaging entries,
focused tests/evidence, and the two narrow evaluator-governance corrections.
There is no Zone 4 implementation, unrelated cleanup, schema application,
feature enablement, merge, deploy, or Production mutation.

```text
PRODUCTION_MUTATION=NO
WORKTREE_CLEAN=NO_PROTECTED_UNTRACKED_SECRET_ONLY
OWNER_DECISIONS_REQUIRED=NONE
GO_PRODUCTION_DB_MIGRATION=NOT_GRANTED
GO_MERGE=NOT_GRANTED
GO_DEPLOY=NOT_GRANTED
SUCCESS_STATUS=PASS_ACT_F_ACTIVATION_FINAL_INTEGRATION_PREPARATION_READY_FOR_INDEPENDENT_REVIEW
```
