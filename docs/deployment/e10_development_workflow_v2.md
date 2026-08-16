# E10 Development Workflow V2

This workflow is a local evidence and release-preparation layer for daily E10
architecture and bug-fix work. It never changes Product runtime by itself,
performs a merge, deploys, rolls back, contacts Production, or infers an
Owner gate.

The runner is:

```text
scripts/release/e10_development_workflow_v2.py
```

## Explicit scope modes

Every packet declares exactly one `SCOPE_MODE`:

| Mode | Use | Product source identity | Runtime scope |
| --- | --- | --- | --- |
| `CONTROL_PLANE_ONLY` | Workflow, release tooling, deployment tests, and workflow docs | `PRODUCT_SOURCE_SHA` identifies the unchanged Product source and must differ from `IMPLEMENTATION_SHA` and `TOOLING_SHA` | Must be empty |
| `PRODUCT_CHANGE` | A bounded E10 Product bug fix or Product integration | `PRODUCT_SOURCE_SHA == IMPLEMENTATION_SHA`; `TOOLING_SHA` remains distinct and must be in the candidate lineage | Exact deterministic classification from the supplied file set |

`PRODUCT_CHANGE` requires an explicit non-empty `expected_changed_files`
input. The actual candidate diff must equal that set exactly. The workflow
does not invent a Product allowlist. Files under `tests/`, `docs/`, and
canonical control-plane paths are not counted as Product runtime files; every
other changed path is conservatively classified as Product/runtime. Product
and control-plane files cannot be combined in one candidate. Mixed scope fails
closed and must be split into separate changes.

The following local or secret artifacts are always protected, including in
`PRODUCT_CHANGE`, and an expected-file entry cannot override that protection:

```text
secret_key.txt  .env*  *.db  *.sqlite*  *.pem  *.key  *.p12  *.pfx
*.exe  *.dll  node_modules/  venv*/  backups/  katago/  ngrok/  cygwin/
```

`secret_key.txt` is never read by the runner.

## Identity contract

Every packet keeps these identities separate:

| Field | Meaning |
| --- | --- |
| `BASE_SHA` | Exact expected starting commit for the implementation worktree. |
| `IMPLEMENTATION_SHA` | Exact implementation/candidate commit under review. |
| `PRODUCT_SOURCE_SHA` | Exact Product source identity that may later be released. In `PRODUCT_CHANGE` it is the implementation; in `CONTROL_PLANE_ONLY` it may remain the unchanged Product source. |
| `TOOLING_SHA` | Exact workflow/release tooling identity. It is never silently substituted for Product source. |
| `MERGE_SHA` | Exact Owner-executed merge identity; `NOT_YET_MERGED` is explicit only in a PR-ready packet. |

Missing identities, invalid ancestry, collapsed gate/Product identities, or a
scope-mode identity mismatch fail closed. `PRODUCT_SOURCE_SHA` may equal
`IMPLEMENTATION_SHA` only in `PRODUCT_CHANGE`; it must not equal
`TOOLING_SHA`.

## Historical R2A governance

`R2A_HISTORY_PRESENT=YES_EXPECTED` is the current governance invariant.
Historical R2A commits may be ancestors of canonical master and do not, by
themselves, block Workflow V2. The retired generic “R2A ancestor is
forbidden” rule is not used. Active-tree or runtime effects, if required by a
separate Product/governance review, must be validated independently rather
than inferred from ancestry.

Packets report:

```text
R2A_HISTORY_PRESENT=YES_EXPECTED
R2A_HISTORY_ANCESTRY_CAUSES_WORKFLOW_FAILURE=NO
```

## Stage A: PR ready

`pr-ready` requires a clean implementation worktree, explicit scope mode and
identity input, valid ancestry, exact changed-file enumeration, the relevant
scope contract, no protected/local artifacts, no conflict markers, and a
non-empty list of existing test commands. Test commands are argv arrays and
are executed locally with no shell.

For `CONTROL_PLANE_ONLY`, only these roots are allowed:

```text
scripts/release/*
scripts/build-production-image.ps1
tests/deployment/*
tests/release/*
docs/deployment/*
```

This is the Python equivalent of the canonical #357 ReleaseTooling
control-plane contract. The exact `scripts/build-production-image.ps1` path,
including `tests/release/**`, is control-plane; it is not a Product runtime
classification.

For `PRODUCT_CHANGE`, the supplied exact file set is the authority. The
packet reports `PRODUCT_RUNTIME_CHANGED_FILES` deterministically and can
therefore represent a normal Product candidate such as `app.py` plus its
associated test.

Successful packets contain `PR_READY=YES`, `OWNER_GATE_INFERENCE=FORBIDDEN`,
and `MERGE_SHA=NOT_YET_MERGED`.

## Stage B: post merge

`post-merge` validates a merge that an Owner already executed. It never calls
`git merge`. The expected implementation must be in the actual merge
lineage, the exact expected changed-file set must remain unchanged, the
scope-mode identity contract must still hold, the canonical worktree must be
clean, and the explicit provenance gates must pass.

`PRODUCT_CHANGE` preserves its non-empty runtime classification when present;
`CONTROL_PLANE_ONLY` must preserve an empty runtime list. In both modes,
`runtime_source_sha` must equal `PRODUCT_SOURCE_SHA`, while `MERGE_SHA` remains
a distinct merge identity.

The command reports:

```text
MERGE_EXECUTED=NO
OWNER_MERGE_OBSERVED=YES
```

## Stage C: release-prep handoff

`release-prep` accepts a successful post-merge packet and explicit local
handoff evidence. It propagates `SCOPE_MODE`, `PRODUCT_SOURCE_SHA`,
`TOOLING_SHA`, `MERGE_SHA`, and `PRODUCT_RUNTIME_CHANGED_FILES`.
`REQUIRED_TEST_GATES`, `STATIC_BUILD_REQUIRED`, `OCI_BUILD_REQUIRED`, and
`ROLLBACK_PREFLIGHT_REQUIRED` are explicit inputs; the workflow never guesses
whether a build is needed. An Owner gate must be supplied explicitly as a
recognized gate with evidence.

The handoff references existing canonical tooling and does not rewrite or
invoke builders or deployers:

```text
scripts/release/package-static-release.ps1
scripts/release/deploy-static-release.ps1
scripts/release/build-release-image.ps1
scripts/release/package-release-image.ps1
scripts/release/preflight-production.ps1
```

## Owner authority and rollback

`OWNER_GATE_INFERENCE=FORBIDDEN`. The workflow never creates or infers
`GO_MERGE`, `GO_DEPLOY`, `GO_ROLLBACK`, `GO_ENABLE`, or `GO_GRANT`.

Rollback authority is always:

```text
EXPLICIT_PRE_DEPLOY_CURRENT_PAIR
```

The handoff must carry the app image identity and live static identity
captured by `preflight-production.ps1` before a proposed deployment. A
deterministic pair ID binds both identities and their shared source commit. A
legacy `previous` symlink alone is rejected and is not rollback authority.

## Local invocation shape

The command line is file-based so packets can be archived and reviewed:

```powershell
python scripts/release/e10_development_workflow_v2.py pr-ready `
  --input .\workflow-v2-pr-ready-input.json `
  --output .\workflow-v2-pr-ready.json `
  --human-output .\workflow-v2-pr-ready.txt

python scripts/release/e10_development_workflow_v2.py post-merge `
  --input .\workflow-v2-post-merge-input.json `
  --output .\workflow-v2-post-merge.json `
  --human-output .\workflow-v2-post-merge.txt

python scripts/release/e10_development_workflow_v2.py release-prep `
  --input .\workflow-v2-release-prep-input.json `
  --output .\workflow-v2-release-prep.json `
  --human-output .\workflow-v2-release-prep.txt
```

The handoff is local release preparation only. It does not authorize or
perform `GO_MERGE`, `GO_DEPLOY`, `GO_ROLLBACK`, `GO_ENABLE`, or `GO_GRANT`.
