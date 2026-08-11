# Governed Production content-only publish runner

This document records the reviewed transport contract added by
`scripts/release/publish-content-release.ps1`. It is a content release path,
not an application or static deployment path.

## Target model

The runner reads the Production layout for the application service and the
`/app/data` mount destination. Immediately before a future mutation, its
host-side helper runs Docker inspection and requires exactly one `volume`
mount at that destination. It then resolves the named volume's actual
`Mountpoint` and addresses only its `questions.json` child. A guessed host
path, bind mount, non-local volume driver, symlink, missing mount, or any
other filename fails closed.

The current layout describes the application service and mount destination;
the volume name and host mountpoint are runtime facts and are recorded in the
receipt after Docker inspection. `questions_content_source_path` is not used
as a substitute for that runtime proof.

## Release flow

The runner consumes an already-built PR318 bundle and verifies the exact
candidate, predecessor, record count, package identity (the SHA-256 of the
bundle's `SHA256SUMS.txt`), release manifest, rollback manifest, source
provenance, mutation audit, acceptance evidence, and allowlisted asset set.
It never regenerates repair decisions.

The default is read-only preflight. It validates the bundle locally and sends
the helper over the existing bounded SSH primitive to inspect the live named
volume and predecessor. It also checks that the configured release staging
root is the governed writable location, the derived release directory is
inside that root and unused, and the release id can be used for an immutable
rollback capture. Dry-run creates no remote staging directory, lock, backup,
receipt, or content file.

An explicitly gated execution is serialized by the existing release-operation
lock and uses the existing bounded SCP transport. The exact bundle is staged
under the configured release staging root. The host helper then:

1. revalidates the bundle and resolves the actual volume mount;
2. verifies the live predecessor immediately before mutation;
3. captures and verifies an exact predecessor backup;
4. writes an immutable rollback receipt before promotion;
5. decompresses and verifies the candidate inside the volume's parent
   directory, then atomically replaces `questions.json` with `os.replace`;
6. verifies the live candidate bytes/count and writes an immutable publish
   receipt; or
7. on an objective integrity failure, restores the captured predecessor via a
   second verified atomic replacement and reports `OLD_VERIFIED_CONTENT`.

The helper never restarts services, switches static assets, builds an image,
publishes a Release, or contacts the SGF Engine. Subjective content
disagreement is not an automatic rollback trigger.

## Receipt identity

`schemas/content_remote_publish_receipt.schema.json` describes the durable
rollback/publish receipt. It records the release id, actual container/mount/
volume target, predecessor and stored backup identity, candidate identity,
bundle/package identity, rollback-manifest identity, and final verified
state. The predecessor backup and receipts remain in the immutable remote
release staging directory for a later governed rollback operation.

The owner gate for a real promotion is `GO_PRODUCTION_CONTENT_RELEASE`.
This PR does not authorize that gate and does not contain any SGF repair
bytes.
