# Go Odyssey Evidence Artifact Authority Pipeline V1

This document is the implementation contract for Evidence-002. It governs
durable evidence intended to survive a task or executor session. Ordinary
executor stdout and task-local scratch files are not authority until the
artifact is finalized into the durable evidence root.

## Authority and storage

The canonical non-tracked evidence root is:

    D:\go-odyssey-release-evidence

The central index is:

    D:\go-odyssey-release-evidence\evidence-index.json

Each governed artifact is stored below:

    <root>\<program>\<task>\<artifact-class>\<artifact-id>\<filename>

and has a sibling artifact.manifest.json. The artifact bytes are the content
authority, the sidecar is the metadata authority, and the central index is the
discoverability and relationship registry. None of these layers may disagree.

The Evidence-001 bootstrap artifact is an existing immutable fixture:

    GOE1-W2-INFRA-EVIDENCE-001-MASTERPLAN-267025b0fcf49bb3

Its bootstrap sidecar predates this implementation and remains unchanged. The
first index build backfills it by verifying its existing bytes, SHA256, stable
path, sidecar, and canonical binding.

## Governed classes

The supported classes are:

    CENSUS
    MASTERPLAN
    TASK_SCOPE_LOCK
    INDEPENDENT_REVIEW
    ADMISSION_RECONCILIATION
    OWNER_GATE_EVIDENCE
    RELEASE_ARTIFACT
    STATIC_RELEASE_MANIFEST
    DATA_PROMOTION_ARTIFACT
    DB_MIGRATION_PREFLIGHT
    DB_MIGRATION_POSTCHECK
    PRODUCTION_ACCEPTANCE
    INCIDENT_EVIDENCE
    PRESERVATION_MANIFEST
    RECOVERY_MANIFEST
    FINAL_CLOSEOUT_LEDGER

All governed classes require SHA256, byte count, provenance, and immutable
artifact identity. Canonical/source and Production bindings are recorded when
the class has them; they are not invented for artifacts that do not have such
a binding.

## Identity contract

The universal sidecar fields are:

    artifact_id, schema_version, task, artifact_class, filename,
    stable_path, content_type, bytes, hash_algorithm, sha256,
    created_at_utc, producer, provenance, authority_state,
    lifecycle_state, retention_class, immutable

The content-bound ID is:

    GOE1-<task>-<artifact-class>-<first-16-hex-of-sha256>

The sidecar may also bind canonical_head, canonical_tree,
source_authority_ref, source_head, source_tree, production_identity,
owner_gate_ref, supersedes, superseded_by, recovered_from,
reconstruction_of, verification, notes, and program.

canonical_head, canonical_tree, source_head, and source_tree are Git object
identities and therefore use lowercase 40-hex Git SHA values. Artifact content
and manifest/index digests use lowercase 64-hex SHA256 values.

immutable must be true. A duplicate ID with identical bytes and identity is an
idempotent no-op. A duplicate ID with different bytes or identity is a hard
failure; accepted artifacts are never silently overwritten.

Authority states are:

    ORIGINAL
    RECOVERED_ORIGINAL
    RECONSTRUCTED
    DERIVED
    HISTORICAL
    PRODUCTION_ACCEPTANCE
    PRESERVATION_ONLY

Lifecycle states are CURRENT_ACTIONABLE and SUPERSEDED. Authority precedence
is scoped to one logical claim:

1. ORIGINAL or byte-identical RECOVERED_ORIGINAL
2. current actionable review or derived evidence
3. PRODUCTION_ACCEPTANCE
4. DERIVED
5. RECONSTRUCTED
6. HISTORICAL
7. PRESERVATION_ONLY
8. SUPERSEDED

A recovered byte-identical original keeps its original content-bound identity
and outranks a reconstruction. A reconstruction receives a new identity and
must link to the missing original; it never impersonates the original.

## Finalization sequence

The core implementation performs this bounded sequence:

1. Treat the input as task-local working material.
2. Reject protected source paths and scan only the candidate bytes and metadata
   for prohibited credential material.
3. Validate artifact class, path components, metadata, and identity inputs.
4. Compute source byte count and SHA256.
5. Acquire the root index lock and create a temporary artifact in the target
   directory.
6. Flush and fsync the temporary artifact, then independently verify bytes and
   SHA256.
7. Atomically move the verified artifact to its immutable path.
8. Write the sidecar through a temporary file, flush/fsync it, and verify the
   artifact/sidecar pair.
9. Atomically update the central index only after both files verify.
10. Re-verify the index entry and return the closeout identity.

The closeout identity is not authoritative until step 10 succeeds. An index
failure retains already-written artifact material without creating a valid
index entry and returns INDEX_UPDATE_FAILED.

Index writes use a lock, temporary JSON, flush/fsync, and atomic replace.
Missing or malformed indexes fail closed except that the first finalize or
explicit bounded backfill may create a new V1 index.

## Commands

The Windows entry point is:

    scripts/evidence/evidence.ps1

It forwards to scripts/evidence/evidence_core.py. The supported commands are:

- register: validate a source and return a proposed content-bound identity; it
  does not persist anything.
- finalize: persist an artifact, sidecar, and index entry atomically.
- verify: verify artifact bytes, sidecar, and index agreement.
- lookup: query the index by task, class, SHA256, or Owner-gate reference.
- supersede: add explicit old/new relationship edges in the index without
  overwriting either artifact.
- recover: finalize a byte-identical recovered original or a linked
  reconstruction.
- audit: verify the index or rebuild it from verified sidecars. Use
  audit --rebuild-index --path <artifact-or-manifest> for bounded bootstrap
  backfill; an unscoped rebuild is an explicit full audit operation.

Example:

    scripts\evidence\evidence.ps1 --root D:\go-odyssey-release-evidence finalize --source D:\task\review.md --program W2-INFRASTRUCTURE --task W2-INFRA-EVIDENCE-002 --artifact-class INDEPENDENT_REVIEW --filename review.md --content-type "text/markdown; charset=utf-8" --producer "Codex"

The JSON result includes artifact_id, durable_path, manifest_path, bytes,
sha256, manifest_sha256, index_entry_id, and verified=YES.

## Recovery and supersession

Recovery requires authority_state=RECOVERED_ORIGINAL and a recovered_from
link. If the bytes and content-bound identity match the original, recovery is
idempotent and preserves the original identity.

Reconstruction requires authority_state=RECONSTRUCTED and reconstruction_of.
It must use a new content-bound identity, normally by using a new task/artifact
scope, and remains secondary until the original is recovered or otherwise
resolved.

Supersession is an explicit index relationship. The old entry becomes
SUPERSEDED, its superseded_by list names the new artifact, and the new entry's
supersedes list names the old artifact. Old artifact bytes and sidecars are
retained.

## Secret boundary

The core rejects private-key blocks, bearer credentials, known token prefixes,
credential-bearing database URLs, credential assignments, and protected
source filenames such as secret_key.txt and .env. Error output contains only a
stable failure code and never echoes matched content.

The implementation never reads or persists secret material. Production
evidence may record metadata-only facts such as
protected_material_touched=NO, but may not include credentials, cookies,
authorization headers, passwords, tokens, or raw sensitive database data.

## Failure codes

Important fail-closed outcomes include:

    ARTIFACT_MISSING
    ARTIFACT_READ_FAILED
    PROHIBITED_SECRET_CONTENT
    PROTECTED_SOURCE_PATH_REJECTED
    STABLE_ROOT_UNAVAILABLE
    INVALID_MANIFEST
    ARTIFACT_HASH_MISMATCH
    ARTIFACT_BYTE_COUNT_MISMATCH
    DUPLICATE_ARTIFACT_ID
    PARTIAL_PUBLICATION
    ATOMIC_WRITE_FAILED
    INDEX_CORRUPT
    INDEX_UPDATE_FAILED
    INDEX_ENTRY_MISSING
    SUPERSESSION_ARTIFACT_MISSING

An optional non-governed report may remain a working artifact when persistence
fails. A masterplan, acceptance package, release proof, or other governed
deliverable may not claim EVIDENCE_LOCKED=YES unless finalization and index
verification complete.

## Ownership boundaries

Evidence-002 owns only the isolated contract, core, CLI wrapper, schema, and
filesystem-only tests. It does not modify app.py, runtime behavior,
Production, database state, deployment state, or the existing Evidence-001
artifact/sidecar.

EVIDENCE-C remains deferred: taskbook closeout integration and bounded
migration of active legacy evidence are separate work. Future L5 and
DB/schema systems consume the core operations and artifact classes without
acquiring app.py ownership.

Owner gates remain external. The evidence pipeline can bind a task, candidate
SHA/tree, artifact ID/SHA, canonical identity, release identity, Production
target, and Owner-gate reference, but it cannot grant or consume an Owner
gate.
