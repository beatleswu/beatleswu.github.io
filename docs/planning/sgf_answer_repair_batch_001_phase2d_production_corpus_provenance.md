# SGF Answer Repair Batch 001 — Phase 2D Production Corpus Provenance

Status: `READY_FOR_OWNER_PRODUCTION_PROVENANCE_REVIEW`

Authorization: `GO_READ_ONLY_PRODUCTION_PROVENANCE`

This report records a narrowly scoped read-only Production provenance
inspection. No Production file, volume, database, container, question,
fallback, Review Queue state, or application release was mutated.

## Result

The exact current Production corpus has been proved and acquired byte-for-byte
to a dedicated local evidence directory outside the application worktree:

- runtime path: `/app/data/questions.json`
- size: `71534726` bytes
- records: `41591`
- SHA-256:
  `4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28`
- drift from the Phase 2C anchor: `NO`
- remote/local byte identity: `YES`

Production's de facto corpus authority is the external persistent Docker
volume `go-odyssey_go-data`. The current corpus is not governed by the
application image or Git repository.

The exact local pre-mutation artifact now exists, but a Production content
rollback workflow does not. The configured daily and weekly backup services
are currently failing before execution because the backup script is not
executable. Their last successful runs predate the current corpus file.
Consequently, no existing Production backup was proved to contain the exact
current corpus.

No repair batch is authorized by this finding.

## Git and scope

- branch: `codex/sgf-answer-repair-batch-001`
- PR: `#302` (Draft, open)
- start HEAD: `268cb59dfcd06a7d5d622388c9c92fddd20c603d`
- application worktree status before this report: clean
- local evidence is outside the application worktree

No credential, SSH user, server address, private-key path, environment value,
token, or secret is included in this report.

## Live application identity

- container: `go-odyssey-app`
- container created:
  `2026-08-09T10:16:19.674275025Z`
- container state: `running`, `healthy`
- container restart count after the inspection: `0`
- image tag: `go-odyssey-app:d77dc1c0`
- image ID/digest:
  `sha256:48ea582e27706388856f85a9d6b1a074a5c996a572aac512d68d460e24811a63`
- OCI revision:
  `d77dc1c02ac3264196768eda3c02f048ddcbd6a8`

The container remained running and healthy throughout the inspection.

## Runtime mount proof

Actual `docker inspect` evidence for `/app/data`:

- mount type: `volume`
- mount source:
  `/var/lib/docker/volumes/go-odyssey_go-data/_data`
- mount destination: `/app/data`
- volume name: `go-odyssey_go-data`
- volume driver: `local`
- volume mountpoint:
  `/var/lib/docker/volumes/go-odyssey_go-data/_data`
- volume created: `2026-06-09T01:54:31Z`
- volume read/write for the app: `true`
- Docker root: `/var/lib/docker`
- backing filesystem: root `/dev/sda1`, `ext4`

The governed release Compose file declares the questions volume external, and
the deploy and rollback scripts recover the existing live volume name before
recreating app or scheduler containers. Therefore:

- normal application deploy preserves the questions volume: `YES`
- image replacement preserves the questions volume: `YES`
- application rollback preserves the questions volume: `YES`
- container recreate preserves the questions volume: `YES`, unless a separate
  explicitly destructive volume operation is performed
- application image rollback rolls back corpus content: `NO`

## Exact Production corpus identity

The actual runtime file was checked before and after the bounded inspection:

- exists: `YES`
- mode: `0600`
- owner inside the app container: UID/GID `0:0`
- mtime: `2026-07-18T21:13:07.278339811Z`
- size: `71534726`
- top-level type: JSON list
- record count: `41591`
- SHA-256:
  `4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28`
- expected count/hash match: `YES`
- current corpus drift detected: `NO`

## Local exact pre-mutation evidence

Production bytes were streamed through SSH stdout directly into a new local
file. No temporary or backup file was created on Production.

- local evidence path:
  `D:\go-website-sgf-answer-repair-batch-001-artifacts\production-provenance-20260809T203042Z-4d13fa98\questions.production-pre-mutation.4d13fa98af8c.json`
- size: `71534726`
- records: `41591`
- SHA-256:
  `4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28`
- remote/local byte identity: `YES`
- local exact pre-mutation artifact available: `YES`
- artifact promoted as a long-term publishing workflow: `NO`

## Four native-repair records

All results below were read from the byte-identical local copy of the exact
Production file. No record was exported back to Production or rewritten.

Comparison normalization is exactly:

1. decode the historical local source as UTF-8;
2. convert CRLF and remaining CR line endings to LF;
3. trim only leading/trailing string whitespace;
4. make no internal SGF, property, coordinate, or variation transformation.

### Question 7998

- Production record found: `YES`
- record index: `17067`
- embedded content SHA-256:
  `73c9e4777e69d48b007ec249db78148a581fffafda76cbfaee75151a6a6bd358`
- `katago_best_move`: `C16`
- `accepted_moves`: field absent
- `solution_state`: field absent
- `enabled`: `true`
- historical source:
  `D:\go website\SGF題庫\天道殘卷：中盤妙手與鬼手全書 ｜ Go - Cosmic Fragments Encyclopedia of Divine Moves\官子部\120.sgf`
- historical source raw SHA-256:
  `50b66e6505fb7d55d2de983de4bae3950165aebe31e7336a3297376546ebf0db`
- raw byte match: `NO`
- normalized content match: `YES`

### Question 8057

- Production record found: `YES`
- record index: `16955`
- embedded content SHA-256:
  `d11bb70ad4dc559f5db834ed0ffb60da61f9f11c5ec414d1425acae3445b8386`
- `katago_best_move`: `Q16`
- `accepted_moves`: field absent
- `solution_state`: field absent
- `enabled`: `true`
- historical source:
  `D:\go website\SGF題庫\天道殘卷：中盤妙手與鬼手全書 ｜ Go - Cosmic Fragments Encyclopedia of Divine Moves\官子部\179.sgf`
- historical source raw SHA-256:
  `6489eaf4b35796087f469463322b2f6adc30af6855a542b02cd51ac05859accc`
- raw byte match: `NO`
- normalized content match: `YES`

### Question 8092

- Production record found: `YES`
- record index: `14608`
- embedded content SHA-256:
  `98480f03bdcfdea84846f15f873e10eeafc14a7a1ff10f559d5bb0547259bc27`
- `katago_best_move`: `Q17`
- `accepted_moves`: field absent
- `solution_state`: field absent
- `enabled`: `true`
- historical source:
  `D:\go website\SGF題庫\天道殘卷：中盤妙手與鬼手全書 ｜ Go - Cosmic Fragments Encyclopedia of Divine Moves\官子部\30.sgf`
- historical source raw SHA-256:
  `05b611207fcf342ece02307df140cc2d3f3c5c4d76330f101c068512249a83d0`
- raw byte match: `NO`
- normalized content match: `YES`

### Question 8100

- Production record found: `YES`
- record index: `16994`
- embedded content SHA-256:
  `7e809d745cbd120631a4495c86b10a16321a0090c0fd18f4a5de7e2993484285`
- `katago_best_move`: `Q4`
- `accepted_moves`: field absent
- `solution_state`: field absent
- `enabled`: `true`
- historical source:
  `D:\go website\SGF題庫\天道殘卷：中盤妙手與鬼手全書 ｜ Go - Cosmic Fragments Encyclopedia of Divine Moves\官子部\38.sgf`
- historical source raw SHA-256:
  `81476c4650caf8d3d8f2f8ba3fe0bbbd76ecaa1028ce96d2ba40549656b2627c`
- raw byte match: `NO`
- normalized content match: `YES`

## Fallback candidate and exclusion checks

The locked
`FALLBACK_REMEDIATION_CANDIDATE_BATCH_001` was compared against the exact
Production corpus copy without printing complete records:

- expected groups: `50`
- expected records: `61`
- Production records found: `61`
- distinct question IDs: `61`
- expected `katago_best_move` matches: `61`
- expected `katago_best_move` mismatches: `0`
- missing records: `0`
- content-precondition drift: `0`

Known excluded conflicts remain unchanged:

- question 15436 Production fallback: `Q4`
- question 15388 Production fallback: `Q4`
- question 65095 Production fallback: `D17`
- previous conflict state still valid: `YES`

No fallback value was cleared or changed.

## Backup provenance and recoverability

Two configured mechanisms were found:

1. Daily: PostgreSQL dump plus a compressed archive rooted at
   `/opt/go-odyssey`, uploaded to external object storage.
2. Weekly: OCI boot-volume snapshot.

The daily site archive does not traverse the Docker named-volume mountpoint.
It archives `/opt/go-odyssey`. A stale host-root `questions.json` exists there,
but it is not the live runtime file:

- host-root path: `/opt/go-odyssey/questions.json`
- size: `60706592`
- mtime: `2026-07-09T17:14:49.103065500Z`
- SHA-256:
  `2958aa9c55f76346bdeb21e6340fd3f2bd0394ab9ed4d5bf031103b9c78a944c`

The live volume's rolling `/app/data/questions.json.bak` has the same stale
size/hash and is also not the current exact corpus.

The weekly boot-volume mechanism covers `/var/lib/docker` at the block-device
level because Docker root resides on the root boot filesystem. It could cover
the questions volume at the time a snapshot succeeds, but no backup content
was restored and no backup object was byte-hashed in this phase.

More importantly, both timers currently fail before running:

- daily and weekly timers: enabled and scheduled
- service result: `exit-code`, status `203/EXEC`
- observed reason: permission denied executing the backup script
- backup script mode: `0664` (not executable)
- last successful daily backup: `2026-06-18T00:01:54Z`
- first daily failure in the inspected history: `2026-06-19T00:00:02Z`
- last successful weekly snapshot: `2026-06-14T21:07:00Z`
- first weekly failure in the inspected history: `2026-06-21T03:30:02Z`
- current corpus mtime: `2026-07-18T21:13:07Z`

The latest successful backup capable of covering the Docker volume predates
the current corpus. Therefore:

- questions volume included by daily archive: `NO`
- questions volume historically included by weekly boot snapshot: `YES`, at
  block-device scope
- successful backup containing current exact corpus: `NO`
- current exact corpus recoverable from existing backup: `NO`
- current exact corpus available as the new local read-only evidence copy:
  `YES`
- Production content rollback workflow available: `NO`

The backup permission failure was not fixed, the timers were not started, and
no backup was created.

## Current authority and future mutation governance

`CURRENT_PRODUCTION_CORPUS_AUTHORITY=EXTERNAL_PERSISTENT_VOLUME_IS_DE_FACTO_AUTHORITY`

`SAFE_CONTENT_MUTATION_WORKFLOW_AVAILABLE_TODAY=NO`

The minimum missing governance components are:

1. a healthy, verified pre-mutation backup that contains the exact current
   questions volume or exact corpus bytes;
2. an immutable content release manifest recording before/after corpus hash,
   record count, approved mutation set, and artifact identity;
3. an Owner-gated atomic publisher for the named-volume file that validates
   the expected precondition hash before replacement;
4. a tested content-only rollback procedure that restores an exact corpus
   artifact without rolling back application code or destroying the volume;
5. post-publication judging, hash, record-count, and application-health gates;
6. a durable audit record linking the Owner decision, repair manifests,
   published artifact, and rollback artifact;
7. repair of the separate backup-service execution failure under its own
   authorization.

A safe future sequence would be: exact capture and immutable before artifact;
locked mutation against that artifact; complete judging verification;
immutable after artifact; Owner-gated atomic publication with exact before-hash
precondition; remote after-hash verification; audit record; and a tested exact
artifact rollback path. This phase did not implement any part of that mutation
workflow.

## Production command audit

The Production allowlist used only read operations:

- `docker ps`, `docker inspect`, `docker image inspect`, `docker volume
  inspect`, `docker info`
- `docker exec` with `test`, `stat`, `sha256sum`, `cat`, and `python -B` JSON
  reads
- `systemctl list-timers`, `systemctl show`, `systemctl cat`
- `journalctl`, `stat`, `namei`, `grep`, `sed`, `findmnt`, and `df`

The exact corpus transfer used remote stdout only and created one local file.
No remote temporary file, archive, backup, migration, API mutation, restart,
or deployment command was invoked.

```text
PRODUCTION_COMMANDS_READ_ONLY=YES
PRODUCTION_FILES_CREATED=0
PRODUCTION_FILES_MODIFIED=0
PRODUCTION_FILES_DELETED=0
PRODUCTION_CONTAINERS_RESTARTED=0
PRODUCTION_VOLUMES_MUTATED=0
PRODUCTION_DB_MUTATED=NO
PRODUCTION_ADMIN_API_MUTATION=NO
```

## Required assertions

```text
START_HEAD=268cb59dfcd06a7d5d622388c9c92fddd20c603d
PR_302_STATE=OPEN_DRAFT
LIVE_APP_CONTAINER=go-odyssey-app
LIVE_APP_IMAGE=go-odyssey-app:d77dc1c0
LIVE_APP_IMAGE_ID_OR_DIGEST=sha256:48ea582e27706388856f85a9d6b1a074a5c996a572aac512d68d460e24811a63
QUESTIONS_RUNTIME_PATH=/app/data/questions.json
QUESTIONS_MOUNT_TYPE=volume
QUESTIONS_MOUNT_SOURCE=/var/lib/docker/volumes/go-odyssey_go-data/_data
QUESTIONS_MOUNT_DESTINATION=/app/data
QUESTIONS_VOLUME_NAME=go-odyssey_go-data
QUESTIONS_VOLUME_DRIVER=local
PRODUCTION_QUESTIONS_SIZE_BYTES=71534726
PRODUCTION_QUESTIONS_RECORD_COUNT=41591
PRODUCTION_QUESTIONS_SHA256=4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28
EXPECTED_CURRENT_CORPUS_MATCH=YES
LOCAL_EVIDENCE_PATH=D:\go-website-sgf-answer-repair-batch-001-artifacts\production-provenance-20260809T203042Z-4d13fa98\questions.production-pre-mutation.4d13fa98af8c.json
LOCAL_EVIDENCE_SIZE_BYTES=71534726
LOCAL_EVIDENCE_RECORD_COUNT=41591
LOCAL_EVIDENCE_SHA256=4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28
REMOTE_LOCAL_BYTE_IDENTITY=YES
Q7998_PRODUCTION_FOUND=YES
Q7998_NORMALIZED_SOURCE_MATCH=YES
Q8057_PRODUCTION_FOUND=YES
Q8057_NORMALIZED_SOURCE_MATCH=YES
Q8092_PRODUCTION_FOUND=YES
Q8092_NORMALIZED_SOURCE_MATCH=YES
Q8100_PRODUCTION_FOUND=YES
Q8100_NORMALIZED_SOURCE_MATCH=YES
FALLBACK_BATCH_RECORDS_EXPECTED=61
FALLBACK_BATCH_RECORDS_FOUND=61
FALLBACK_EXPECTATION_MATCH_COUNT=61
FALLBACK_EXPECTATION_MISMATCH_COUNT=0
MISSING_RECORD_COUNT=0
Q15436_PRODUCTION_FALLBACK=Q4
Q15388_PRODUCTION_FALLBACK=Q4
Q65095_PRODUCTION_FALLBACK=D17
KNOWN_CONFLICT_STATE_STILL_VALID=YES
BACKUP_MECHANISM_DISCOVERED=DAILY_SITE_AND_DB_ARCHIVE_PLUS_WEEKLY_OCI_BOOT_VOLUME_SNAPSHOT; BOTH_CURRENTLY_FAIL_203_EXEC
QUESTIONS_VOLUME_INCLUDED_IN_BACKUP=HISTORICAL_WEEKLY_BLOCK_SNAPSHOT_ONLY; NO_SUCCESS_AFTER_CURRENT_CORPUS_MTIME
CURRENT_EXACT_CORPUS_RECOVERABLE_FROM_EXISTING_BACKUP=NO
LOCAL_EXACT_PRE_MUTATION_ARTIFACT_AVAILABLE=YES
PRODUCTION_CONTENT_ROLLBACK_WORKFLOW_AVAILABLE=NO
NORMAL_DEPLOY_PRESERVES_QUESTIONS_VOLUME=YES
IMAGE_ROLLBACK_PRESERVES_QUESTIONS_VOLUME=YES
CONTAINER_RECREATE_PRESERVES_QUESTIONS_VOLUME=YES
CURRENT_PRODUCTION_CORPUS_AUTHORITY=EXTERNAL_PERSISTENT_VOLUME_IS_DE_FACTO_AUTHORITY
SAFE_CONTENT_MUTATION_WORKFLOW_AVAILABLE_TODAY=NO
MISSING_GOVERNANCE_COMPONENTS=HEALTHY_EXACT_BACKUP; IMMUTABLE_CONTENT_RELEASE_MANIFEST; OWNER_GATED_ATOMIC_PUBLISHER; TESTED_CONTENT_ONLY_ROLLBACK; POST_PUBLISH_GATES; DURABLE_AUDIT_LINKAGE; BACKUP_EXECUTION_REPAIR
CANONICAL_SGF_MUTATED=NO
QUESTIONS_JSON_MUTATED=NO
FALLBACK_DATA_MUTATED=NO
ACCEPTED_MOVES_MUTATED=NO
REVIEW_QUEUE_MUTATED=NO
KATAGO_RUN=NONE
MERGE=NO
DEPLOY=NO
```
