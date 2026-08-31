# RPG V1 Full Canonical Catch-Up RC Dependency and Provenance Reconciliation

`TASK=RPG_V1_FULL_CANONICAL_CATCH_UP_RC_DEPENDENCY_AND_PROVENANCE_RECONCILIATION_001`

`ROLE=RELEASE_GOVERNANCE`  
`MODE=READ_ONLY_RELEASE_RECONCILIATION`  
`ASSIGNEE=CODEX`  
`OBSERVATION_DATE=2026-08-31`  
`PREFERRED_PATH=FULL_CANONICAL_CATCH_UP_RC`  
`FALLBACK=INCIDENT018_ONLY_HOTFIX`  
`DEPLOY=NO`

## Decision

`STATUS=RECONCILIATION_COMPLETE_FULL_RC_BLOCKED`

The evidence record is complete and publishable, but the full RC cannot be locked. Fresh `origin/master` is `b3d37e22e7471d0429d882c43c3ee16049c68ea1`; Incident019B R3 is remote and mechanically mergeable but is not canonical; CODEX-1 has published a partial before-state snapshot but the required R1 safe-account mapping is unresolved, so `INCIDENT019B_BEFORE_SNAPSHOT_STATUS=MISSING`; and the live database is LC020 `HOT_APPLIED` while the live app image lacks the LC020 read adapter and remains on the legacy question-id path. No deployment, restart, rollback, database mutation, migration/backfill, feature enablement, or source-code change was performed.

## Authority and no-mutation boundary

- `origin/master` is the canonical integration line. The shared canonical checkout was preserved and was not used for artifact edits.
- The release layout identifies the production SSH alias as `oracle_godoyssey`, but this task used only bounded read-only SSH, Docker inspection, public HTTP checks, and read-only database transactions.
- Owner gates remain separate: `GO_MERGE`, `GO_DEPLOY`, `GO_ROLLBACK`, database migration/backfill, and feature enablement are not implied by this evidence.
- `.env`, `secret_key.txt`, unknown untracked artifacts, and secrets were not inspected or modified.
- `APP_PY_CHANGED=NO`, `SOURCE_CHANGED=NO`, `PRODUCTION_MUTATION=NO`, `DEPLOY=NO`, and `ROLLBACK=NO`.

## Canonical source and checkout identity

Fresh verification immediately before reconciliation:

| Field | Value |
|---|---|
| `FRESH_ORIGIN_MASTER_HEAD` | `b3d37e22e7471d0429d882c43c3ee16049c68ea1` |
| `FRESH_ORIGIN_MASTER_TREE` | `39392e8c0df272fb3b0d3df2ec0c1f4f21ab7a93` |
| `git ls-remote origin refs/heads/master` | matches `b3d37e22e7471d0429d882c43c3ee16049c68ea1` |
| current shared checkout | `D:\go-website`, branch `codex/art003-b01-r1-targeted-visual-revision` |
| current shared checkout HEAD/tree | `2c25f2f423f672023a919abaf35f6c975bcf3d65` / `ca84eac422997d87645a92363559ab71d6494e23` |
| shared checkout mutation | none; its existing state was preserved |

The current master head includes canonical B11, the Incident018 merged lineage, D044 final RC source admission lineage, LC020 source admission lineage, and the identity read-adapter source. The canonical source hashes relevant to the live comparison are:

| Canonical file | SHA-256 |
|---|---|
| `app.py` | `d3d9183abd5cd7c8f94b2600ea13899b2c0335dae24dd1fe86451828243b76bf` |
| `sw.js` | `1e15bf565450b0f3bd78ac0837773e17662cab0be8467b3a0f11b2b04e85d9a8` |
| `index.html` | `6a8fd37fabfdb0d0accc4c66d4be3fe9ecb6f29187a2f7eb5b2c01fc6154bec4` |
| `identity_read_adapter.py` | `5302c1f4a1530ec20e3bca52d51877d859b9af82986960c79a0c778f56e05158` |
| `puzzle_identity_read_window.py` | `569890d3eece212445c00d1b59e6328b4a00135b0a9090600b3199e8abb78bec` |
| `puzzle_identity_store.py` | `e54734ab23e24eaff65725d2f3af0a5de9c263bb3e8b40d0e27ae3e18514b1e1` |
| `puzzle_identity_genesis_bootstrap.py` | `1a341fcef481f50398489e19b3a90cfc5690f66cb5aa6c484668062168c60b83` |
| `migrations/puzzle_identity_registry_v1.py` | `ad5bd5bc4c3d501df694e5b05835bb0426964ddb4e98bc64d291960823d6f766` |

## Production source, image, static, and service identity

All values below are read-only observations from the live production host on `2026-08-31`.

| Field | Verified value |
|---|---|
| production source SHA | `cc6b7915e4a70677ac7e1bafacff69fc70e33b84` |
| source provenance | OCI revision label and static manifest both report the same SHA; the Git object is unavailable in this repository, so no local object comparison is claimed |
| production image | `go-odyssey-app:cc6b7915` |
| production image ID/digest | `sha256:0805b6914c67330e596b84fd4992394124d882baae695104b5433efde0ebf422` |
| app and scheduler | healthy, both on `go-odyssey-app:cc6b7915`, zero observed restarts |
| static generation | `20260830-000006-cc6b7915-v240-a028-hero-player-presentation-readonly` |
| static release SHA | `cc6b7915e4a70677ac7e1bafacff69fc70e33b84` |
| static service-worker version | `v240-a028-hero-player-presentation-readonly` |
| public/static `sw.js` SHA-256 | `d468dfb90891b7fdfc4882ec4c9825552b7f847968392ccc4245e602f0f6a64e` |
| baked `/app/sw.js` SHA-256 | `1e15bf565450b0f3bd78ac0837773e17662cab0be8467b3a0f11b2b04e85d9a8` |
| public checks | `/healthz`, `/login`, `/`, and `/sw.js` returned HTTP 200 |

The live app hash is `737462f0c96d319c8e458ec546d6741469d21f37cb9d4bf7899ea4ca8e357256`, which differs from the current canonical `app.py`. The live app does not contain `incident_018_observability.py`, `adventure_progress_compatibility.py`, `migrations/adventure_historical_mastery_v1.py`, or `tools/incident_019b_progression_continuity.py`. Supporting live hashes from the bounded production probe include `/app/db.py` `194d969e79f850a7ed74a2b8d3bebfda050dbc159f126e0af6b231b861d5251d` and `/app/grimoire_api.py` `f9a57262c0add4805a0c3bbce41abaf329dafe9849d2f6f47ffc5d811490e4d3`; the live image also lacks the LC020 identity adapter/read-window/store/genesis files.

The static manifest and direct file hashes agree for `i18n.js`, `sw.js`, and `index.html`. The live static generation and image source SHA are internally consistent with each other, but are not current `origin/master` identity and are not candidate acceptance evidence for a future RC.

## Incident018, Incident019B, LC020, and B11 status

### Incident018

`INCIDENT018_CANONICAL=YES`. The merged Incident018 source lineage is reachable from current `origin/master` (including observability and the later attempt-lease fix). `INCIDENT018_PRODUCTION_FIXED=NO`: the live image has no Incident018 observability module. `INCIDENT018_PRODUCTION_ACCEPTED=NO`: the required full 20-question Lord trial, including resume before expiry and resume after expiry, was not executed. `NOT_RUN` is not `PASS`.

Historical Incident018 source/build evidence remains useful for lineage only. The historical build preflight was blocked before Docker (`17 failed`, `909 passed`, `108 skipped`); it does not authorize an image or deployment.

### Incident019B

| Field | Result |
|---|---|
| `INCIDENT019B_R3_REMOTE_HEAD` | `d24062467100790ce681d926da15e70ab304a2ad` |
| remote verification | fresh `git ls-remote` matches the local remote-tracking ref |
| canonical | `NO`; current master contains none of the four new R3 paths |
| merge relationship | current master descends from common base `6228de020dea513fe33b974a37444537738c0baa` |
| synthetic merge | clean synthetic tree `f2d3d046c94670c040c24e932a8a36c6d9b41da2` |
| before-state snapshot | `MISSING`; CODEX-1 published `codex/incident-019b-r5a-production-before-state` at `e589bcebaa12d3e08da335805097eab6c0047248` with artifact SHA `20ccc76b4b4c5b4dfd68ad0fabb4c92a6249b83b8897a111438189ff9bea7a01`, but R1 safe-account `7167b6214d65` remains unresolved and all R1 state fields are `UNRESOLVED_SAFE_ID_NOT_PRESENT` |
| production compatibility executed | `NO`; migration/backfill is explicitly forbidden in this task |

The R3 diff is six paths: `adventure_progress_compatibility.py`, `app.py`, `migrations/adventure_historical_mastery_v1.py`, the adapted E10 foundation test, the Incident019B test, and its continuity tool. The app change is additive and keeps restored historical mastery separate from defeated/Boss/stars state, which is consistent with server-authoritative progression, but source correctness does not grant `GO_MERGE`.

### LC020

`LC020_DB_STATE=HOT_APPLIED`. A read-only transaction verified the `go_odyssey` database, identity registry/alias/lineage/receipt schema, `42804` registry rows, `129330` aliases (`129308` current and `22` non-current), `42804` lineage rows, one applied receipt, and a `HISTORICAL_GENESIS` `ACTIVE/GENESIS` identity group. The applied receipt reports `42804` identities and the frozen corpus SHA `88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff`.

The live app does not contain the LC020 read adapter. Therefore `LC020_CURRENT_PRODUCTION_COMPATIBILITY=ADDITIVE_LEGACY_COEXISTENCE_ONLY`: the hot schema can coexist with the old app while the legacy question-id path remains authoritative, but current Production is not hot/full-RC compatible. `LC020_RELEASE_BLOCKER=YES` for the full RC. No production migration, backfill, or database mutation was performed.

### B11

`B11_CANONICAL=YES`. Current master contains the ten B11 monster asset bytes and the canonical adapted manifest/review/test material; the owner-frozen manifest records the ten admitted IDs `M110`, `M111`, and `M113`–`M120`. The asset bytes match the B11 source branch, while canonical docs/tests were adapted on master. Asset identity can be reused as unchanged source evidence, but final candidate package closure still requires rerun.

## Production feature/configuration precheck

No secrets or environment files were inspected. Bounded runtime state shows:

| Field | Result |
|---|---|
| `PRODUCTION_SHOP_ENABLED` | `NO`; canonical coin shop flag false |
| `PRODUCTION_LOADOUT_ENABLED` | `NO`; canonical loadout flag false |
| `PRODUCTION_PAYMENTS_ENABLED` | `YES` as provider configuration: NewEBPay and PayPal are configured in live mode; canonical Shop/Loadout purchase flags remain off |
| `PRODUCTION_REVENUE_ENABLED` | `NO` for the C013/canonical claim route; it is default-off |
| community leaderboard rewards | `COMMUNITY_LEADERBOARD_REWARDS_ENABLED=true`; existing production reward execution is an owner-governed hazard and was not changed |
| premium weekly scheduler | `0` |
| shadow judging | `true` |

Payments are therefore an owner-gated production configuration concern even though Shop, Loadout, and the canonical revenue claim route are off. This task did not enable, disable, or mutate any of them.

## Global freeze and active slots

| Slot | Current lane | Classification | Safe to continue after RC lock? |
|---|---|---|---|
| CODEX-1 | Incident019B R5A before-state snapshot | `PRODUCTION_READONLY` | yes; evidence is a prerequisite before lock and must not mutate Production |
| CODEX-2 | LC020 post-Genesis Production acceptance baseline | `PRODUCTION_READONLY` | yes; candidate acceptance must rerun after candidate lock |
| CODEX-3 | A057 R2 one-hand sword planning/admission preflight | `NON_SOURCE_PLANNING` | yes |
| CODEX-4 | post-B11 monster roster gap planning | `NON_SOURCE_PLANNING` | yes |
| CODEX-5 | this reconciliation artifact | `PRODUCTION_READONLY` | yes |

`GLOBAL_FREEZE_REQUIRED_LANES=INCIDENT019B_APP_PY_WRITER_PRIORITY_AT_RC_LOCK`. Incident019B is the sole current app.py source-admission lane and has writer priority. CODEX-3 and CODEX-4 are docs-only planning lanes; CODEX-1, CODEX-2, and CODEX-5 are read-only lanes. No other active slot currently requires a source freeze, but no competing app.py writer may enter the lock window.

## Historical evidence classification

| Evidence | Classification | Reuse boundary |
|---|---|---|
| Current master ancestry and committed Incident018, D044, LC020, and B11 source lineage | `REUSABLE_UNCHANGED_IDENTITY` | reusable as source-lineage proof after fresh SHA/tree verification; not runtime acceptance |
| B11 ten asset bytes and owner-frozen IDs | `REUSABLE_UNCHANGED_IDENTITY` | reuse asset hashes; rerun final candidate package closure |
| D044-R5 eight-file exact source admission and its 338-pass/17-skip/0-fail historical validation | `REUSABLE_UNCHANGED_IDENTITY` | proves the historical admitted payload only; final candidate changed and needs re-anchor |
| Historical D041 43-check package integrity | `REQUIRES_RERUN_CANDIDATE_CHANGED` | rerun against the locked candidate; physical-device acceptance was never executed |
| A2/A3/A4 asset closure and release packaging | `REQUIRES_RERUN_CANDIDATE_CHANGED` | rerun because candidate source/package identity will change |
| E10 VS1E, hero legacy-cache guard, Lord contract, zero-Coins, and leaderboard checks | `REQUIRES_RERUN_CANDIDATE_CHANGED` | app.py/source/runtime identity changes and required current acceptance is absent |
| Incident018 full 20-question Lord trial with pre/post-expiry resume | `REQUIRES_RERUN_CANDIDATE_CHANGED` | no current PASS exists; execute on locked candidate |
| Static service-worker cache identity and public cache behavior | `REQUIRES_RERUN_CANDIDATE_CHANGED` | publish under `release-<LOCKED_FULL_SOURCE_SHA>` and verify public/static/baked hashes |
| LC020 live DB snapshot | `REUSABLE_UNCHANGED_IDENTITY` | current read-only DB fact only; compatibility and post-deploy evidence must be rerun after any owner-authorized app change |
| Old `cc6b7915` Production acceptance/static/image identity as candidate approval | `OBSOLETE` | baseline provenance only; it is not current master or full-RC acceptance |
| Incident019B production migration/backfill proof | `NOT_APPLICABLE` | explicitly not executed or authorized in this task; separate owner gate required |
| Incident018-only hotfix path | `NOT_APPLICABLE` | fallback is not the preferred full-catch-up path and does not solve LC020/full-RC reconciliation |

## Required reruns and device acceptance

After Incident019B is admitted by the owner and a fresh full-RC source SHA is locked, rerun at minimum:

- Incident019B progression compatibility and continuity tests, including the adapted E10 Zone 2 foundation contract.
- Incident018 observability/lease tests and the complete Lord-trial acceptance: all 20 questions, resume before expiry, resume after expiry, and judge/attempt identity checks.
- Hero legacy-cache guard, Lord contract matrix, zero-Coins/shop/loadout containment, E10 VS1E, A2/A3/A4, i18n fallback, leaderboard eligibility/reward safety, B11 asset/package closure, and LC020 post-Genesis application compatibility.
- D041 package integrity against the exact candidate source/image/static/SW identity, plus release build/package preflight. Any build hang, wrong checkout, missing dependency, or partial suite is `UNEXECUTED` or `BLOCKED`, never `PASS`.
- Static/SW cache verification with namespace `release-<LOCKED_FULL_SOURCE_SHA>` and direct/public hash comparison.

Required device acceptance remains unexecuted: D041 package verification on the candidate plus physical Desktop, iPad, and iPhone/browser acceptance, including the full Lord trial/resume path and cache namespace checks. Historical package integrity is not physical-device acceptance.

## Full RC lock gates

| Gate | Ready now? | Reason |
|---|---|---|
| `READY_TO_LOCK_FULL_RC_SOURCE_SHA` | `NO` | Incident019B is not canonical and CODEX-1 before-state evidence is waiting |
| `READY_FOR_FULL_RC_BUILD` | `NO` | no locked full-RC SHA; candidate reruns and build/package preflight remain required |
| `READY_FOR_GO_DEPLOY` | `NO` | deployment is explicitly prohibited; owner deployment gate and full candidate/device evidence are absent |

Do not lock a SHA until all of the following are proven: Incident019B canonical admission; verified before-state snapshot; exact source admissions; global freeze of the Incident019B app.py writer; fresh `origin/master` identity; clean focused tests; and no unresolved source blocker. Build, deployment, feature enablement, database migration/backfill, and Production acceptance remain separate owner gates.

## Exact report fields

```text
TASK=RPG_V1_FULL_CANONICAL_CATCH_UP_RC_DEPENDENCY_AND_PROVENANCE_RECONCILIATION_001
STATUS=RECONCILIATION_COMPLETE_FULL_RC_BLOCKED
FRESH_ORIGIN_MASTER_HEAD=b3d37e22e7471d0429d882c43c3ee16049c68ea1
FRESH_ORIGIN_MASTER_TREE=39392e8c0df272fb3b0d3df2ec0c1f4f21ab7a93
PRODUCTION_SOURCE_SHA=cc6b7915e4a70677ac7e1bafacff69fc70e33b84
PRODUCTION_IMAGE=go-odyssey-app:cc6b7915
PRODUCTION_IMAGE_DIGEST=sha256:0805b6914c67330e596b84fd4992394124d882baae695104b5433efde0ebf422
PRODUCTION_STATIC_GENERATION=20260830-000006-cc6b7915-v240-a028-hero-player-presentation-readonly
PRODUCTION_SW_VERSION=v240-a028-hero-player-presentation-readonly
PRODUCTION_SW_SHA256=d468dfb90891b7fdfc4882ec4c9825552b7f847968392ccc4245e602f0f6a64e
INCIDENT018_CANONICAL=YES
INCIDENT018_PRODUCTION_FIXED=NO
INCIDENT018_PRODUCTION_ACCEPTED=NO
INCIDENT019B_R3_REMOTE_HEAD=d24062467100790ce681d926da15e70ab304a2ad
INCIDENT019B_R3_REMOTE_VERIFIED=YES
INCIDENT019B_CANONICAL=NO
INCIDENT019B_BEFORE_SNAPSHOT_STATUS=WAITING
INCIDENT019B_PRODUCTION_COMPATIBILITY_EXECUTED=NO
LC020_DB_STATE=HOT_APPLIED
LC020_APP_SOURCE_CONTAINS_READ_ADAPTER=NO_LIVE_IMAGE
LC020_CURRENT_PRODUCTION_COMPATIBILITY=ADDITIVE_LEGACY_COEXISTENCE_ONLY_NOT_FULL_RC_COMPATIBLE
LC020_RELEASE_BLOCKER=YES
B11_CANONICAL=YES
PRODUCTION_SHOP_ENABLED=NO
PRODUCTION_LOADOUT_ENABLED=NO
PRODUCTION_PAYMENTS_ENABLED=YES_PROVIDER_CONFIGURED_LIVE
PRODUCTION_REVENUE_ENABLED=NO_CANONICAL_CLAIM_ROUTE_DEFAULT_OFF
APP_PY_CHANGED=NO
SOURCE_CHANGED=NO
PRODUCTION_MUTATION=NO
DEPLOY=NO
ROLLBACK=NO
SECRET_KEY_TOUCHED=NO
```

## Next task

`NEXT_TASK=RESOLVE_INCIDENT019B_R1_SAFE_IDENTIFIER_MAPPING_OR_OWNER_CONFIRM_ACCOUNT_REPLACEMENT_THEN_GO_MERGE_AND_FRESH_FULL_RC_REANCHOR`

CODEX-1’s evidence branch/artifact was inspected without duplication or mutation. Its R1 safe identifier remains unresolved, so the before-state gate is `MISSING`. Resolve the R1 mapping or obtain the owner’s explicit account-replacement decision, then the owner must decide `GO_MERGE` for Incident019B. Only after that admission should a fresh full-RC source re-anchor, focused rerun matrix, build/package gate, device acceptance, and separately authorized deployment review proceed.

`RESULT=EVIDENCE_PUBLISHED_FULL_RC_SOURCE_LOCK_BUILD_AND_DEPLOY_NOT_READY`
