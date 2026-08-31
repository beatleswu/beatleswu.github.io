# LC020 R10 Post-Genesis Production Acceptance and Baseline Lock

## Result

`LC020_PRODUCTION_ACCEPTANCE = FAIL`

The Production database independently verifies the Genesis result and HOT derivation, but the
live application image is an older runtime that does not contain the LC020 identity read adapter
stack or either required live consumer reference. The required Production read-window acceptance
therefore cannot pass. This is a real post-Genesis runtime-image defect, not a Genesis count or
schema defect.

Audit timestamp: `2026-08-31T07:09:15.3853177Z`.

## Fresh repository identity

| Field | Value |
|---|---|
| Canonical remote | `https://github.com/beatleswu/beatleswu.github.io.git` |
| Fresh `origin/master` HEAD | `b3d37e22e7471d0429d882c43c3ee16049c68ea1` |
| Fresh `origin/master` tree | `39392e8c0df272fb3b0d3df2ec0c1f4f21ab7a93` |
| Task base | Fresh `origin/master` |
| Production query mode | Read-only SSH, Docker inspection, read-only PostgreSQL transaction, read-only filesystem/hash inspection |
| Production mutation | `NO` |
| Secret key touched | `NO` |

The original `D:\go-website` checkout was dirty and contained protected/unrelated artifacts. The
audit artifacts were prepared in isolated worktree `D:\go-website-lc020-r10`.

## Locked source hashes

| Canonical file | SHA-256 | Match |
|---|---|---|
| `migrations/puzzle_identity_registry_v1.py` | `ad5bd5bc4c3d501df694e5b05835bb0426964ddb4e98bc64d291960823d6f766` | `YES` |
| `puzzle_identity_genesis_bootstrap.py` | `1a341fcef481f50398489e19b3a90cfc5690f66cb5aa6c484668062168c60b83` | `YES` |
| `puzzle_identity_store.py` | `e54734ab23e24eaff65725d2f3af0a5de9c263bb3e8b40d0e27ae3e18514b1e1` | `YES` |

`LOCKED_HASH_MATCH = YES`.

## Production runtime identity

Production target `oracle_godoyssey` resolved to host `instance-20260609-0051`.

The live app is `go-odyssey-app:cc6b7915`, image digest
`sha256:0805b6914c67330e596b84fd4992394124d882baae695104b5433efde0ebf422`, with image revision
label `cc6b7915e4a70677ac7e1bafacff69fc70e33b84`. It was created at
`2026-08-30T00:40:24.460042354Z` and started at `2026-08-30T00:40:34.899322205Z`, before the
Genesis receipt was applied at `2026-08-31T05:46:28.900799Z`.

The live `/app/app.py` and `/app/grimoire_api.py` hashes are respectively
`737462f0c96d319c8e458ec546d6741469d21f37cb9d4bf7899ea4ca8e357256` and
`f9a57262c0add4805a0c3bbce41abaf329dafe9849d2f6f47ffc5d811490e4d3`, not the fresh canonical
source bytes. The live container is missing:

- `/app/identity_read_adapter.py`
- `/app/puzzle_identity_read_window.py`
- `/app/puzzle_identity_store.py`
- `/app/migrations/puzzle_identity_registry_v1.py`
- `/app/puzzle_identity_genesis_bootstrap.py`

No LC020 identity references were found in the live `app.py`, `grimoire_api.py`, or `db.py`.
Unauthenticated route probes returned `401` for both daily-training routes and `200` for
`/healthz`; route reachability does not substitute for authenticated read-adapter execution.

## Production database evidence

Read-only PostgreSQL transaction: PostgreSQL `16.14`, database `go_odyssey`.

| Check | Observed |
|---|---:|
| Identity tables | `4` |
| `puzzle_identity_registry` | `42804` |
| `puzzle_identity_alias` | `129330` |
| `puzzle_identity_lineage` | `42804` |
| Bootstrap receipts | `1` |
| Receipt status | `APPLIED` |
| Genesis identity rows | `42804` `HISTORICAL_GENESIS` + `ACTIVE` |
| Genesis lineage rows | `42804` |
| Legacy collision groups | `11` |
| Current legacy collision groups | `0` |

The receipt is `834eb17fb3bedfa303bf510d24a2734348ddda1204c4811ce80d4c9c89c6f54c`, with
`record_count=42804`, `identities_written=42804`, frozen corpus hash
`88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff`, canonicalisation
`canon-source-v1`, and Genesis key version `genesis-key-v1`.

`GENESIS_APPLIED = YES` and `IDENTITY_COUNT_GT_ZERO = YES`; therefore, from the canonical
semantic contract `genesis_applied AND identity_count > 0`, `HOT_MODE = TRUE`.

## Exact object inventory

Expected LC020-owned inventory passed:

- Tables (4): `puzzle_identity_alias`, `puzzle_identity_bootstrap_receipt`,
  `puzzle_identity_lineage`, `puzzle_identity_registry`.
- Sequences (2): `puzzle_identity_alias_id_seq`, `puzzle_identity_lineage_id_seq`.
- Explicit indexes (8): `idx_pia_uuid`, `idx_pil_event_type`, `idx_pil_related_uuid`,
  `idx_pil_uuid_seq`, `idx_pir_receipt_ref`, `idx_pir_status_kind`, `uq_pia_current_alias`,
  `uq_pia_one_current_path`.
- Triggers (5): `trg_pia_binding_immutable`, `trg_pibr_append_only`, `trg_pil_append_only`,
  `trg_pir_creation_facts_immutable`, `trg_pir_uuid_immutable`.
- Functions (4): `puzzle_identity_reject_alias_binding_change`,
  `puzzle_identity_reject_creation_fact_change`, `puzzle_identity_reject_uuid_change`,
  `puzzle_identity_reject_write`.

The seven PostgreSQL constraint-backed indexes were separately observed as generated support
objects, not unexpected LC020-owned indexes. Their names are recorded in the JSON artifact.
The exact expected columns, foreign keys, and object counts matched the canonical migration;
no unexpected LC020-owned objects were found.

`OBJECT_INVENTORY = PASS`.

## Read-adapter acceptance

The fresh canonical source contains both required consumer paths:

1. `app.py` uses `_identity_group_key_map` for its aggregate/group-key readers.
2. `grimoire_api.py` uses `BootstrapGatedIdentityReader` in `generate_daily_training`.

Those bytes are not present in the live image: the adapter modules are missing and no live
identity references were found. Consequently:

```text
IDENTITY_READ_ADAPTER_ACCEPTANCE = FAIL
UNKNOWN_OR_UNMAPPED_FAIL_OPEN = FAIL_UNVERIFIED_RUNTIME
PROCESS_RESTART_REQUIRED = NO (for database state)
CACHE_INVALIDATION_REQUIRED = NO
```

The database-side fail-closed state was also checked independently: legacy collision sample
`40479` has two distinct identities and zero current bindings; sentinel unknown alias
`__lc020_r10_unknown__` has zero rows. That DB state does not prove the missing live adapter
behavior, so it cannot override the runtime-image failure.

## Runtime corpus firewall

The live runtime corpus is the mounted `/app/data/questions.json` from volume
`go-odyssey_go-data`:

```text
PRODUCTION_RUNTIME_CORPUS_PATH=/app/data/questions.json
PRODUCTION_RUNTIME_CORPUS_RECORD_COUNT=41591
PRODUCTION_RUNTIME_CORPUS_ENABLED_COUNT=41591
PRODUCTION_RUNTIME_CORPUS_BYTES=71534621
PRODUCTION_RUNTIME_CORPUS_SHA256=b7b4eedf72a87ab8fbc82ff51b658cd4dc0f08cb33426aee013e97814edae232
PRODUCTION_RUNTIME_CORPUS_MUTATED_BY_GENESIS=NO
FROZEN_GENESIS_CORPUS_SUBSTITUTED=NO
```

The runtime corpus is distinct from the frozen Genesis corpus (`42804` records,
`88da3e43...`). No `questions.json` replacement or modification was performed by this task.

## Backup retention

```text
BACKUP_EXISTS=YES
BACKUP_PATH=/opt/go-odyssey/ops/backup/lc020_pre_genesis_20260831T050307Z.dump
BACKUP_BYTES_ACTUAL=12430028
BACKUP_BYTES_MATCH=YES
BACKUP_SHA256_ACTUAL=a3f68c89a726619982e449bb99bba6b13a7fdce115dd877ce6cf7d2c74493352
BACKUP_SHA256_MATCH=YES
BACKUP_ARCHIVE_READABLE=YES
BACKUP_RESTORED=NO
BACKUP_DELETED=NO
```

The custom-format archive listed successfully through the PostgreSQL container (`823` archive
entries). It was not restored or deleted.

## Feature and deployment firewall

Live container environment and gate evaluation showed:

```text
SHOP_STATE=DISABLED (CANONICAL_COIN_SHOP_PURCHASE_ENABLED unset; evaluated false)
LOADOUT_STATE=DISABLED (EQUIPMENT_CANONICAL_LOADOUT_ENABLED unset; evaluated false)
PAYMENTS_STATE=LIVE_CONFIGURED (NEWEBPAY_TEST=0; PAYPAL_TEST=0; both configured)
REVENUE_LIVE_STATE=DISABLED (GO_REVENUE_V1_PREMIUM_CLAIM_ENABLED unset; evaluated false)
NO_UNRELATED_FEATURE_ENABLEMENT=PASS
```

The existing live payment configuration is reported as state only; no payment or feature write
was performed. No deploy command, restart, migration, Genesis retry, rollback, or feature
enablement was issued. The live app container predates the receipt and remained the pre-existing
runtime image.

`NO_DEPLOY = PASS` for this task’s Genesis boundary.

## Final contract

```text
TASK=LC020_R10_POST_GENESIS_PRODUCTION_ACCEPTANCE_AND_BASELINE_LOCK_001
STATUS=FAIL
FRESH_ORIGIN_MASTER_HEAD=b3d37e22e7471d0429d882c43c3ee16049c68ea1
FRESH_ORIGIN_MASTER_TREE=39392e8c0df272fb3b0d3df2ec0c1f4f21ab7a93
MIGRATION_SHA256=ad5bd5bc4c3d501df694e5b05835bb0426964ddb4e98bc64d291960823d6f766
RUNNER_SHA256=1a341fcef481f50398489e19b3a90cfc5690f66cb5aa6c484668062168c60b83
STORE_SHA256=e54734ab23e24eaff65725d2f3af0a5de9c263bb3e8b40d0e27ae3e18514b1e1
LOCKED_HASH_MATCH=YES
IDENTITY_TABLE_COUNT=4
IDENTITY_REGISTRY_COUNT=42804
IDENTITY_ALIAS_COUNT=129330
IDENTITY_LINEAGE_COUNT=42804
BOOTSTRAP_RECEIPT_COUNT=1
BOOTSTRAP_RECEIPT_STATUS=APPLIED
GENESIS_APPLIED=YES
IDENTITY_COUNT_GT_ZERO=YES
HOT_MODE=TRUE
HOT_MODE_DERIVATION_PASS=YES
IDENTITY_READ_ADAPTER_ACCEPTANCE=FAIL
UNKNOWN_OR_UNMAPPED_FAIL_OPEN=FAIL_UNVERIFIED_RUNTIME
OBJECT_INVENTORY_PASS=YES
PRODUCTION_RUNTIME_CORPUS_MUTATED_BY_GENESIS=NO
PRE_GENESIS_BACKUP_RETAINED=YES
NO_UNRELATED_FEATURE_ENABLEMENT=PASS
NO_DEPLOY=PASS
PRODUCTION_QUERY=YES
PRODUCTION_MUTATION=NO
SOURCE_CHANGED=NO
MASTER_MERGE=NO
MASTER_PUSH=NO
DEPLOY=NO
ROLLBACK=NO
SECRET_KEY_TOUCHED=NO
```

Artifacts:

- `docs/planning/lc020_r10_post_genesis_production_acceptance.md`
- `docs/planning/lc020_r10_post_genesis_production_baseline.json`

`BASELINE_ARTIFACT_JSON_SHA256=ce47ed9ff1a3cd99e59c4af4082a96b8c5eae7c90702ce2a62ee1a86e263fddc`.
The JSON intentionally does not self-embed its own digest; final Git publication identities are
reported below and in the task result.

Next task: `LC020_R10_RUNTIME_IMAGE_MISSING_LC020_READ_ADAPTER_REVIEW_001`.
