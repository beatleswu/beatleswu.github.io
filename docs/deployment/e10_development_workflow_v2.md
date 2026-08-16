# E10 Development Workflow V2 Foundation

This foundation is a local evidence and handoff layer for daily E10
architecture and bug-fix work. It does not change Product runtime behavior,
execute a merge, deploy, roll back, contact Production, or infer an Owner
gate.

The runner is:

```text
scripts/release/e10_development_workflow_v2.py
```

## Identity contract

Every packet carries these identities separately:

| Field | Meaning |
| --- | --- |
| `BASE_SHA` | Exact expected starting commit for the implementation worktree. |
| `IMPLEMENTATION_SHA` | Exact implementation/candidate commit under review. |
| `PRODUCT_SOURCE_SHA` | Exact Product source identity to use for a later release. It is never inferred from tooling. |
| `TOOLING_SHA` | Exact workflow/release tooling identity. It must not collapse to Product source. |
| `MERGE_SHA` | Exact Owner-executed merge identity; `NOT_YET_MERGED` is explicit only in a PR-ready packet. |

Missing identities, invalid ancestry, or `PRODUCT_SOURCE_SHA == TOOLING_SHA`
fail closed.

## Stage A: PR ready

`pr-ready` requires a clean implementation worktree, explicit identity input,
valid ancestry, exact changed-file enumeration, Lane W scope, no forbidden
R2A ancestor, no conflict markers, and a non-empty list of existing test
commands. Test commands are argv arrays and are executed locally with no shell.

The output contains both a JSON packet and a human-readable summary when
`--output` and `--human-output` are supplied. A successful packet has:

```text
PR_READY=YES
PRODUCT_RUNTIME_CHANGED=NO
R2A_INCLUDED=NO
OWNER_GATE_INFERENCE=FORBIDDEN
```

Lane W accepts only these changed-file roots:

```text
scripts/release/*
tests/deployment/*
docs/deployment/*
```

Product runtime paths, Product Dockerfile behavior, database/schema paths,
the SGF corpus, and `secret_key.txt` are protected. The latter is never read
by this runner.

## Stage B: post merge

`post-merge` validates a merge that an Owner already executed. It requires the
expected implementation to be in the actual merge lineage, exact expected
changed-file scope, a clean canonical worktree, no forbidden R2A ancestor, and
explicit provenance identities for all five fields. The provenance input must
also contain passing `source_separation`, `canonical_ancestry`,
`runtime_provenance`, and `repository_status` gates, with
`runtime_source_sha == PRODUCT_SOURCE_SHA`.

The command does not call `git merge` and reports:

```text
MERGE_EXECUTED=NO
OWNER_MERGE_OBSERVED=YES
```

## Stage C: release-prep handoff

`release-prep` accepts a successful post-merge packet plus explicit local
handoff evidence. `REQUIRED_TEST_GATES`, `STATIC_BUILD_REQUIRED`,
`OCI_BUILD_REQUIRED`, `ROLLBACK_PREFLIGHT_REQUIRED`, and `NEXT_OWNER_GATE`
are required inputs; the runner never guesses them. An Owner gate must be
provided as `{ "explicit": true, "name": "GO_DEPLOY", "evidence": "..." }`.

The handoff references the existing canonical tooling:

```text
scripts/release/package-static-release.ps1
scripts/release/deploy-static-release.ps1
scripts/release/build-release-image.ps1
scripts/release/package-release-image.ps1
scripts/release/preflight-production.ps1
```

No builder or deployer is rewritten or invoked by this stage.

## Rollback authority

Rollback authority is always:

```text
EXPLICIT_PRE_DEPLOY_CURRENT_PAIR
```

The handoff must carry the app image identity and live static identity
captured by `preflight-production.ps1` before the proposed deployment. A
deterministic pair ID binds both identities and their shared source commit.
A legacy `previous` symlink, by itself, is rejected and is not rollback
authority.

## Local invocation shape

The command line is intentionally file-based so the packet can be archived and
reviewed:

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
