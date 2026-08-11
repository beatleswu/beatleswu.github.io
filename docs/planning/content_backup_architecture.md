# Content backup architecture

Status: Phase 2H local candidate; no remote repository, Release, Production
write, or credential was created.

## Boundary

The application repository governs code and release tooling. It does not own
the 41,591-record `questions.json` corpus. Real corpus snapshots must never be
committed to this repository or to `beatleswu/beatleswu.github.io`.

The proposed off-site registry is a separate private repository with the
logical name `go-odyssey-content-backup`. The repository itself stays small:
policy, schemas, verifier source, and a human-readable index may be tracked.
Byte-exact corpus snapshots are immutable GitHub Release assets.

Phase 2H read-only discovery found no existing repository named
`beatleswu/go-odyssey-content-backup` and no similarly named Go Odyssey
content/backup repository. Remote creation requires the separate Owner gate
`GO_CREATE_PRIVATE_GITHUB_CONTENT_REPO`.

## Artifact model

Each pre-mutation backup Release contains:

- `questions.pre-mutation.json.gz`;
- `backup-manifest.json`;
- `SHA256SUMS.txt`.

Each governed content Release contains:

- `questions.repaired-candidate.json.gz`;
- the byte-exact approved content release manifest;
- the byte-exact approved rollback manifest;
- `content-registry-entry.json`;
- `SHA256SUMS.txt`.

Gzip is deterministic (`mtime=0` and no original filename). Compressed hashes
identify storage bytes only. Corpus authority is always the SHA-256 of the
exact uncompressed JSON bytes plus its record count.

The backup manifest schema is
`schemas/content_backup_manifest.schema.json`; the candidate registry schema
is `schemas/content_release_registry.schema.json`. Neither permits or needs
credentials, tokens, environment values, SSH key paths, or database secrets.

## Required backup proof

A backup is usable only after all three identities agree:

1. the exact source stream;
2. the locally written and decompressed gzip;
3. the remotely re-downloaded and decompressed GitHub Release asset.

Upload success or remote metadata alone is insufficient. Missing assets,
public visibility, the wrong tag, compressed-byte drift, uncompressed-byte
drift, or record-count drift fail closed. The verification receipt records
only hashes, count, tag, asset name, and visibility.

GitHub is not the only rollback dependency. A uniquely named same-host
pre-mutation copy must be created and verified before future publication. The
off-site Release and the local copy are independent mandatory gates.

## Publisher and rollback boundary

The publisher verifies the current live hash/count, local baseline backup,
off-site verification receipt, approved release-manifest hash, and candidate
hash/count before it can execute. Verification is the default mode. Execution
additionally requires `--execute` and the exact Owner gate
`GO_PRODUCTION_CONTENT_RELEASE_54`.

The replacement sequence is:

1. copy the candidate to a unique stage file in the live file's directory;
2. flush and fsync the staged file, then preserve live mode/ownership;
3. verify staged hash and record count;
4. atomically replace with `os.replace`;
5. fsync the parent directory;
6. reopen and verify the live hash and record count.

The Production execution host must expose native directory fsync semantics
(the governed target is Linux). Unsupported hosts fail closed. Windows local
simulation injects an explicit disposable-directory durability hook; it is not
used for Production execution.

Rollback is separately invokable and requires the current live corpus to equal
the expected candidate. It verifies the rollback manifest and byte-exact
baseline, then uses the same stage/fsync/replace/directory-fsync/post-verify
sequence. Its execution gate is `GO_PRODUCTION_CONTENT_ROLLBACK_54`.

## Locked Phase 2F package

Phase 2H consumes but does not regenerate these bytes:

| Artifact | SHA-256 |
| --- | --- |
| Production baseline | `4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28` |
| 54-record candidate | `b7b4eedf72a87ab8fbc82ff51b658cd4dc0f08cb33426aee013e97814edae232` |
| Release manifest | `c337c68804bf346fea80e3facbf9edbe0651075cb9464761c87209c1bbd81745` |
| Rollback manifest | `f1e970d91546f27cc65ba503c39fab2cd27adaef29a3bfbcdd38ee238a87fc23` |

The release remains 43 groups / 54 records. The 11 Map Battle multi-reply
traversal records remain excluded and no membership is recalculated here.

## Legacy managed backup

The existing managed backup status remains `203/EXEC`. Prior read-only
evidence traced this to the configured backup script having mode `0664`, so
systemd cannot execute the configured `ExecStart`. Phase 2H does not contact or
change Production.

Repair should be a separate governed operations Sprint: restore the executable
bit through the tracked ops/deployment source, verify unit path/ownership and
unit syntax, run one controlled backup, then prove the current named-volume
corpus can be restored and byte-verified before enabling timers. The target
architecture is managed/local backup plus private GitHub off-site backup.
