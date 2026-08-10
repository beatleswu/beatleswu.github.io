# GitHub private content Release governance

Status: design and local implementation only. No repository or Release was
created and no corpus bytes were uploaded.

## Repository decision

Proposed repository: `beatleswu/go-odyssey-content-backup`.

Required visibility: **PRIVATE**. The tooling refuses a non-private repository
before upload or verification. Repository creation and visibility changes are
deliberately absent from the tool; the Owner must first authorize
`GO_CREATE_PRIVATE_GITHUB_CONTENT_REPO`.

The small Git repository may track a policy README, manifest schemas, and a
standalone verifier. Large or repeated `questions.json` and SGF snapshots
belong only in immutable Release assets, never normal Git history.

Suggested tags:

- baseline: `content-baseline-YYYYMMDD-<unique-UTC-suffix>`;
- candidate: `content-release-YYYYMMDD-NNN`.

Tags are an index, not identity. Machine-readable manifests and exact hashes
are authoritative. A tag mismatch fails closed.

## Authentication and minimum permission

Recommended automation identity: a GitHub App installation token installed on
only the private content repository. Grant repository **Contents: write** for
Release creation/upload. Re-download verification requires **Contents: read**;
the write grant includes the needed read operation. Repository metadata access
is implicit for an installation and no Workflows, Administration, Issues,
Pull requests, organization, or account-wide grant is needed.

For an occasional manual path, a fine-grained personal access token limited to
that one repository with Contents read/write is an acceptable fallback. A
classic broad `repo` token is not recommended.

Credential values must stay in an existing secure mechanism: the GitHub CLI
credential store for interactive use or an approved CI secret store for
automation. The tools accept no token argument, print no token, and write no
credential to manifests. Credential creation and rotation remain separate
Owner gates.

## Governed Release workflow

1. Verify the intended repository exists and reports `PRIVATE`.
2. Verify the exact source hash and record count.
3. Create deterministic gzip plus manifest and `SHA256SUMS.txt` locally.
4. Verify the local gzip by decompressing and rehashing exact bytes.
5. Under a separate upload authorization, create the exact tag and upload
   without clobbering an existing asset.
6. Confirm the exact asset name exists.
7. Download it into a new local directory.
8. Verify compressed hash, decompressed hash, and record count.
9. Write an off-site verification receipt only after all three hashes match.
10. Permit a later Production publisher gate to consume that receipt.

The `gh` adapter can create/upload a Release only with both `--execute-remote`
and `GO_GITHUB_CONTENT_BACKUP_RELEASE`. It never creates repositories. Phase 2H
uses only `LocalReleaseRegistry` to exercise the complete upload/list/download
contract against disposable directories.

## Independent Owner gates

- Gate 1: `GO_CREATE_PRIVATE_GITHUB_CONTENT_REPO` creates/configures the
  private registry and its least-privilege credential.
- A later backup-upload gate creates and re-verifies the immutable baseline
  Release.
- Gate 2: `GO_PRODUCTION_CONTENT_RELEASE_54` permits the exact 54-record
  candidate publication only after local and off-site backup verification.
- Rollback remains independently gated by
  `GO_PRODUCTION_CONTENT_ROLLBACK_54`.

These decisions must never be collapsed into repository creation, PR merge,
application deployment, or corpus publication as one implicit action.

## PR boundary

This infrastructure should use a separate PR from #302. Its intended scope is
only the four content CLIs, shared governance module, schemas, documentation,
and fail-closed tests. The locked corpus, candidate, and large generated local
evidence remain outside Git. Phase 2H prepares a local branch for Owner review;
it does not push or create a PR.
