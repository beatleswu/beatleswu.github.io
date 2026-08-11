# SGF Answer Repair Batch 001 — Phase 2G Production Content Release Preflight

Status: `READY_FOR_OWNER_PRODUCTION_CONTENT_RELEASE_DECISION`

Authorization: `GO_PRODUCTION_PREFLIGHT`. This was a read-only Production
inspection. No corpus, volume, database, Review Queue state, container, image,
or application process was changed or restarted.

## Result

The live Production corpus still matches the locked Phase 2F baseline exactly:

```text
PROD_QUESTIONS_PATH=/app/data/questions.json
PROD_RECORD_COUNT=41591
PROD_SIZE_BYTES=71534726
PROD_SHA256=4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28
PROD_BASELINE_HASH_MATCH=YES
```

The hash was checked again at the end of the Production session. It remained
unchanged. The app container remained running and healthy with restart count
zero.

The approved 54-record package also revalidated locally without regenerating or
changing any package artifact. The candidate, release manifest, and rollback
manifest still have their locked identities.

No content publish is authorized by this preflight.

## Production content boundary

- live app container: `go-odyssey-app`
- live image: `go-odyssey-app:d77dc1c0`
- live image ID:
  `sha256:48ea582e27706388856f85a9d6b1a074a5c996a572aac512d68d460e24811a63`
- app status: `running`, `healthy`
- app restart count: `0`
- mount type: `volume`
- volume: `go-odyssey_go-data`
- driver: `local`
- Docker mountpoint:
  `/var/lib/docker/volumes/go-odyssey_go-data/_data`
- container destination: `/app/data`
- backing filesystem: `/dev/sda1`, `ext4`
- `/app/data` and `/app/data/questions.json` device ID: `2049`
- available space at preflight: `9275180` KiB

The live file is mode `0600`, owner `0:0`; the app container runs with Docker's
default root user. The actual boundary can therefore preserve the current
mode/ownership while staging and atomically replacing the file inside
`/app/data`.

## Locked package identity

```text
RELEASE_GROUPS=43
RELEASE_RECORDS=54
RELEASE_CANDIDATE_SHA256=b7b4eedf72a87ab8fbc82ff51b658cd4dc0f08cb33426aee013e97814edae232
RELEASE_CANDIDATE_RECORD_COUNT=41591
RELEASE_MANIFEST_SHA256=c337c68804bf346fea80e3facbf9edbe0651075cb9464761c87209c1bbd81745
ROLLBACK_MANIFEST_SHA256=f1e970d91546f27cc65ba503c39fab2cd27adaef29a3bfbcdd38ee238a87fc23
TARGET_RECORDS_CHANGED=54
NON_TARGET_RECORDS_CHANGED=0
EXCLUDED_11_PRESENT_IN_RELEASE=NO
```

The deterministic package build was rerun against the exact baseline and
immutable Phase 2F batch. It returned the same candidate and manifest hashes,
strict all-surface verdict match, 54 target changes, and zero non-target
changes. Dedicated content-release tests passed `12/12`.

## Pre-mutation backup readiness

The currently verified content-only backup is the byte-identical local baseline
artifact captured by read-only SSH stdout streaming in Phase 2D:

`D:\go-website-sgf-answer-repair-batch-001-artifacts\production-provenance-20260809T203042Z-4d13fa98\questions.production-pre-mutation.4d13fa98af8c.json`

It remains SHA-256
`4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28`,
which is still byte-identical to the live file. The locked rollback manifest
references this exact baseline and the exact candidate.

For a future authorized publish, the pre-write sequence must stream the live
file once more through SSH stdout to a new, uniquely named local artifact,
without creating any Production temporary file; then verify remote SHA, local
SHA, local record count, and byte identity before any stage/upload begins. It
must never overwrite the existing Phase 2D artifact.

```text
PRE_MUTATION_BACKUP_METHOD=SSH_STDOUT_BYTE_STREAM_TO_UNIQUE_LOCAL_ARTIFACT_THEN_REMOTE_LOCAL_SHA_AND_COUNT_VERIFICATION
PRE_MUTATION_BACKUP_TARGET=REPO_EXTERNAL_LOCAL_ARTIFACT_DIRECTORY_WITH_UNIQUE_TIMESTAMP_AND_HASH
PRE_MUTATION_BACKUP_READY=YES_CONTENT_ONLY_BYTE_EXACT
BACKUP_BYTE_EXACT_CAPABLE=YES
BACKUP_VERIFY_SHA256_METHOD=REMOTE_SHA256SUM_EQUALS_LOCAL_SHA256_EQUALS_LOCKED_BASELINE_SHA256
```

Important operational distinction: the managed daily and weekly backup
services are still failed with `203/EXEC`; the backup script remains mode
`0664`. Therefore `MANAGED_PRODUCTION_BACKUP_SERVICE_READY=NO`. The readiness
above is for the bounded content-only rollback artifact, not for the broader
Production backup system.

## Publisher gates

The reviewed local primitive enforces:

1. target and candidate must both exist;
2. live SHA must equal the expected baseline SHA immediately before staging;
3. candidate SHA must equal the locked candidate SHA;
4. candidate record count must equal `41591`;
5. a temporary file is created inside the target directory;
6. copied bytes are flushed and `fsync`ed;
7. staged SHA and record count are rechecked;
8. mode and ownership are preserved;
9. `os.replace` performs the same-filesystem atomic switch;
10. the target directory is `fsync`ed;
11. final live SHA and record count are re-read and verified.

Wrong-current-hash refusal and byte-exact rollback passed using the real 54
record package. Missing candidate, wrong candidate hash, and wrong record count
are explicit fail-closed branches before replacement.

The release-manifest lock is enforced at the workflow level before invoking the
atomic primitive: the deterministic package build and direct file hash must
both reproduce
`c337c68804bf346fea80e3facbf9edbe0651075cb9464761c87209c1bbd81745`.
Any existing output byte mismatch is rejected by the package builder. The
atomic primitive does not independently parse the release manifest.

```text
PUBLISHER_HASH_GATE=PASS
PUBLISHER_RECORD_COUNT_GATE=PASS
PUBLISHER_CANDIDATE_HASH_GATE=PASS
PUBLISHER_MISSING_CANDIDATE_GATE=PASS
PUBLISHER_RELEASE_MANIFEST_GATE=PASS_AT_MANDATORY_PRE_WRITE_WORKFLOW_LEVEL
PUBLISHER_WRONG_HASH_FAIL_CLOSED=PASS
```

## Atomicity and runtime reload behavior

The Production boundary supports the same atomic model used by the local
simulation: stage inside `/app/data`, verify the staged bytes, and use
same-device `os.replace`. The 71.5 MB candidate is far below the observed free
space.

The application question loader caches by file mtime. Atomic replacement
changes the file mtime, so the next normal `_load_questions()` call reloads the
new corpus. A container restart is not required for content visibility.

The atomic primitive is tracked in PR #302 but is not included in the current
Production image's narrow Docker `tools/` allowlist. Consequently, a future
publish still needs an explicitly reviewed, Owner-authorized Production runner
that stages the artifact and invokes the exact primitive inside the existing
content boundary. This preflight did not copy or improvise such a runner on
Production.

```text
PUBLISH_ATOMICITY=SAME_DIRECTORY_STAGE_FSYNC_VERIFY_OS_REPLACE_DIRECTORY_FSYNC_REVERIFY_SUPPORTED
PRODUCTION_PUBLISH_RUNNER=NOT_YET_GOVERNED_OR_PRESENT_IN_LIVE_IMAGE
```

## Rollback readiness

The rollback manifest requires candidate SHA
`b7b4eedf72a87ab8fbc82ff51b658cd4dc0f08cb33426aee013e97814edae232`
as its live precondition and restores baseline SHA
`4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28`.
The baseline is a valid 41,591-record corpus and is compatible with the same
ext4 volume, permissions, and same-directory atomic replace model.

```text
PROD_ROLLBACK_COMPATIBLE=YES_AT_ARTIFACT_AND_FILESYSTEM_BOUNDARY
EXPECTED_ROLLBACK_SHA256=4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28
ROLLBACK_ATOMICITY=SAME_DIRECTORY_STAGE_FSYNC_VERIFY_OS_REPLACE_DIRECTORY_FSYNC_REVERIFY
ROLLBACK_EXECUTION_RUNNER=NOT_YET_GOVERNED_OR_PRESENT_IN_LIVE_IMAGE
```

## Owner decision boundary

The corpus and package identities are ready for an Owner decision, but this
preflight does **not** recommend an immediate `GO_PRODUCTION_CONTENT_RELEASE`
until the exact remote publish/rollback runner is separately reviewed and
locked. The managed backup-service `203/EXEC` failure also remains unresolved;
the available recovery guarantee is currently content-only via the exact local
artifact.

No Map Battle excluded record was reintroduced, and no third mutation type was
added.

## Production session audit

Production operations were limited to read-only `docker ps`, selected
`docker inspect` fields, `docker volume inspect`, `stat`, `sha256sum`, bounded
JSON record counting, `df`, and `systemctl show`/`stat` for the existing backup
services. No command wrote to the host, container, named volume, database, or
application API.

```text
PRODUCTION_READ=YES
PRODUCTION_MUTATION=NO
PRODUCTION_FILES_CREATED=0
PRODUCTION_FILES_MODIFIED=0
PRODUCTION_FILES_DELETED=0
PRODUCTION_VOLUME_MUTATED=NO
PRODUCTION_DB_MUTATED=NO
CONTAINER_RESTART=NO
MERGE=NO
DEPLOY=NO
```

Stop: `SGF_ANSWER_REPAIR_BATCH_001: READY_FOR_OWNER_PRODUCTION_CONTENT_RELEASE_DECISION`
