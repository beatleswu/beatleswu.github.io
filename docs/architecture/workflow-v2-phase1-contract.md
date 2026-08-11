# Workflow V2 Phase 1 Contract

This document defines the ordinary Go Odyssey development and release
workflow. It composes the existing release tooling; it is not a deployment
architecture replacement.

## Scope and authority

The canonical source remains origin/master. Work starts from an isolated
feature branch and ends at one owner merge decision. A Production release is
separate and requires one owner deploy decision when deployment is needed.

This phase does not change deployment scripts, live-static serving, rollback
mechanics, E10 runtime behavior, SGF behavior, content, or Production.

The machine-readable artifacts are:

- docs/architecture/workflow-v2-pr-evidence.schema.json
- docs/architecture/workflow-v2-release-provenance.schema.json
- scripts/workflow_v2_evidence.py

The helper only reads Git metadata and writes evidence files supplied by the
caller. It does not merge, deploy, rollback, or contact Production.

## Operational classes

Classification is based on authority and blast radius, not file count and not
the name of a feature area.

### NORMAL

Use for ordinary application behavior, UI, bounded server logic,
documentation, tests, and static changes that stay inside an existing
manifest/serving contract.

An E10 UI change can be NORMAL when it stays inside an existing contract.
An SGF documentation or test change can be NORMAL when it does not touch
judging or parser authority.

### HOTFIX

Use for an urgent, known regression with a narrow scope and focused
validation. It retains the same safety properties as NORMAL with a shorter
path and does not permit an additional authority boundary.

HOTFIX is not a shortcut around merge, artifact identity, or the Production
deploy gate.

### HEAVY

Use when the change touches deployment tooling, database/schema authority,
SGF judging/parser/core semantics, authentication/security, rollout
architecture, infrastructure, broad cross-system behavior, or release
governance.

Not every E10 or SGF change is automatically HEAVY. The authority touched is
the deciding fact.

## PR evidence contract

The PR evidence artifact is a candidate record. It may contain:

- base ref and exact base SHA;
- PR head ref, exact commit SHA, candidate tree SHA, and parents;
- changed files and candidate blob SHAs;
- risk class and classification basis;
- relevance flags for Python, JavaScript, and browser validation;
- focused validation results;
- an optional planned release type.

It must not claim to know the future merge commit. The helper derives changed
files and blob identities from the candidate Git objects.

Required validation categories are:

- focused_tests;
- affected_regression;
- diff_check;
- scope_check.

Python changes additionally require python_syntax and compileall. JavaScript
changes require javascript_syntax. Browser-relevant changes require
browser_contract. HEAVY changes additionally require broader_validation.

All required categories must be recorded as PASS. A check can explain that a
category was not applicable only when the relevance contract does not require
it.

Example checks input:

    {
      "checks": [
        {"category": "focused_tests", "status": "PASS", "details": "..."},
        {"category": "affected_regression", "status": "PASS", "details": "..."},
        {"category": "diff_check", "status": "PASS"},
        {"category": "scope_check", "status": "PASS"}
      ]
    }

Create a candidate artifact with:

    python scripts/workflow_v2_evidence.py candidate \
      --base-ref origin/master \
      --head-ref HEAD \
      --risk-class NORMAL \
      --basis bounded_server_logic \
      --scope-statement "One bounded server behavior change" \
      --checks-json pr-checks.json \
      --output workflow-pr-evidence.json

## Post-merge release provenance

After merge, release provenance is generated from the exact merged source
commit. It binds:

- release_id;
- merged_source_sha;
- merged_tree_sha;
- merge parents;
- proof that the merged source is reachable from canonical origin/master;
- risk class and classification basis;
- the declared release type;
- app artifact identity when applicable;
- static artifact identity and Service Worker identity when applicable;
- external/content identities when applicable;
- a hash/link to the candidate PR evidence when available.

Release types are:

- APP_ONLY;
- STATIC_ONLY;
- PAIRED_APP_STATIC.

APP_ONLY and STATIC_ONLY are independently supported by the existing
artifact tooling. PAIRED_APP_STATIC is a declaration only in Phase 1.
Coherent pair switching and pair rollback remain Phase 2 requirements.

The release helper requires artifact identities to match the merged source:
the application OCI revision and static release_git_sha must equal
merged_source_sha.

## Owner gates

The ordinary lifecycle is:

    development
    -> focused PR validation
    -> owner merge decision
    -> merge
    -> release evidence and exact artifact preparation
    -> owner deploy decision, when needed
    -> deploy
    -> objective verification

Keep manual:

- merge;
- Production deploy or static-generation mutation;
- explicit destructive rollback;
- SGF/content mutation;
- security and control-plane changes;
- subjective Owner acceptance where required.

Automate evidence collection, hash generation, manifest creation, provenance
generation, ordinary preflight, deterministic artifact verification, health
checks, and smoke evidence gathering. None of these automatically authorizes
an irreversible Owner decision.

## Test layers

PR proves semantic correctness: focused behavior, affected subsystem
regression, relevant syntax/compile checks, browser contract, scope, and
diff.

Release proves source and artifact correctness: merged-source provenance,
artifact hashes and identity, static completeness, preflight, and rollback
readiness.

Production proves runtime correctness: health, readiness, exact artifact
identity, affected smoke, browser errors, and required Owner acceptance.

Do not repeat the entire deployment suite for every layer. Keep remote
identity, archive/hash, and Production health checks because they prove
different boundaries.

## Explicit non-goals

Phase 1 does not solve app/static compatibility or coherent rollback. A
paired release must currently be reported as requiring Phase 2 protection
against mixed states.

FAST_STATIC remains a complete manifest-bound live-static generation. Phase 1
does not widen it to arbitrary file promotion.

The known dragon animation manifest issue remains
OPEN_NOT_IN_SCOPE. It is not repaired or used to block unrelated Workflow V2
work when it is pre-existing, untouched, and not release-correctness
relevant.
