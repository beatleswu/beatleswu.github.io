# External governance Build blocker: current integration report (2026-10-18)

**Implementation complete within the authorized worktree; operational Build remains
BLOCKED / NO_GO.** No production, other existing worktree, GitHub workflow,
permissions, issuer or signing key was modified. No push, merge or deployment.
The pre-existing uncommitted bridge overlay was preserved and extended.

Worktree: `D:\g9-release-gate-bridge`, detached HEAD
`69dbe57aa535112b1759e3f3bdcf9ecbe1680efb`, tree
`4e14800b5e064c6ec95127de8917bb3e34314cad`. The final source receipt identifies
uncommitted bytes separately from HEAD; the candidate is not integrated/accepted.

## Delivered in this continuation

- Real `gh attestation verify` integration with an absolute SHA256-pinned gh
  executable, exact GitHub OIDC issuer and certificate SAN, approved source/signer
  repository/workflow/ref/commit/run/attempt, GitHub-hosted runner restriction,
  exact in-toto subject digest/name and predicate.
- A strict host-profile loader with a fixed external installation path and
  independent compiled SHA256 pin. Unknown/duplicate fields, missing pins,
  changed bytes and relative paths reject. There is no policy-path, environment,
  local-key or CLI trust bootstrap. Missing distribution pins stay empty.
- A separately SHA256-pinned Sigstore root JSONL, supplied explicitly to gh,
  snapshotted in protected host scratch along with the decision. Caller TEMP,
  working directory, proxies, CA/Sigstore/Python/GH overrides cannot select gh's
  trust configuration or scratch. The root must have its final JSONL newline.
- Short-lived exact Gate/Product/common-directory/challenge decisions, validity
  rechecked after network verification, strict bounded decision/profile parsing,
  checked verification output size and existing atomic durable replay storage.
- Native Build preflight now requires one JSON object with explicit affirmative
  BUILD_APP authorization and exact invocation bindings, even after exit code 0.
  It also requires explicit false evidence/release permissions. Empty, malformed,
  array-shaped, mismatched or string-boolean reports reject.
- Read-only `--requirements` diagnostics and an
  [operator runbook](EXTERNAL_GOVERNANCE_OPERATOR_RUNBOOK.md) with exact inspection,
  TUF root acquisition, independent pin provisioning, challenge generation,
  real verification and eventual Build invocation commands. Operator-only
  commands are documentation; no host provisioning was executed.

## Exact issuer/activation blocker

The supported OIDC issuer is exactly
`https://token.actions.githubusercontent.com`.
The missing governance signer is **UNKNOWN_NOT_SUPPLIED**: no independent
Owner-authorized repository/workflow/protected ref/full commit/run ID/attempt
was supplied or identified in the inspected repository configuration. A precise
identity cannot be invented. The candidate remote is not signing authority.
`g009-candidate-independent-324.yml` explicitly has
`formal_release_attestation=NOT_PRESENT`; R27 evidence admission also cannot issue
BUILD_APP decisions.

Independent operator action is still required for the issuer authorization,
authenticated verifier installation/profile/root pins, protected host identity
and replay storage, and a signed unexpired decision. The runtime interpreter and
all distribution dependencies must be independently reviewed/protected too.
Candidate script hashes are not self-authentication. The trusted host must
verify its Gate entrypoint before execution and enforce identity/ACL isolation.

Both `$governanceVerifierSha256` and `HOST_PROFILE_SHA256` intentionally remain
unprovisioned. The new loader is usable by an independently provisioned reviewed
distribution; it does not establish trust in its own candidate bytes. Local tests
cannot supply the missing administrative authority.

## Real backend probe and limits

Installed GitHub CLI: **2.95.0**. The real native command
`gh attestation trusted-root` was executed with worktree-local isolated home,
config and scratch. It exited **1**, failing TUF refresh at
`https://tuf-repo-cdn.sigstore.dev/15.root.json` with socket access denied.
Raw command/exit/stderr: `artifacts/governance-r2-network-probe.json`.
A direct read-only GitHub API request was likewise denied by socket permissions.
No network permissions were changed and no alternate trust root was fabricated.

**Live cryptographic positive: NOT_EXECUTED / BLOCKED_ENVIRONMENT_AND_AUTHORITY.**
No authorized issuer/signed decision was available. Synthetic verified-output
shapes exercise policy only. Real `run_gh` success and production replay
consumption were not asserted or simulated as an authorization. All injected
runners always return `MOCK_VERIFIED_NOT_AUTHORIZED` and never consume decisions.
Native PowerShell report doubles stop before any worktree/test/Docker operation.
Build and release remain separate from execution/reviewer admission; those
independent gates are unchanged.

## Current validation

Final run: **407 passed, 0 failed, 0 errors, 0 skipped**, in **186.05 seconds**.
JUnit: `artifacts/governance-r2-final.xml`. All six implementation/test source
hashes matched before and after execution. `git diff --check` passed.

Final validation results and source/artifact SHA256 receipts are recorded in
`artifacts/governance-r2-validation.json` (generated after final tests).
The original 324 release regression cases are included, plus 68 bridge cases and
15 native PowerShell report-boundary cases. Tests use disposable repositories
inside this worktree and mocked Docker interactions; no formal admission is
claimed. Source hashes are compared before/after final test execution.

Historical failure from this continuation: the first native report run produced
**14 passed / 1 failed** (`artifacts/governance-r2-report.xml`). Windows PowerShell
unwrapped a one-element JSON array. Requiring a top-level object corrected it;
the subsequent native run produced **15 passed**
(`artifacts/governance-r2-report-final.xml`). The failure artifact is preserved.
The earlier bridge-only runs produced **51 passed**, then **68 passed** as coverage
was expanded. Prior continuation/regression runs are intermediate evidence, not
claims about the final bytes.

Reproduction in the existing local test environment:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PSExecutionPolicyPreference = 'Bypass' # process and children only
$env:PATH = 'D:\g9-release-gate-bridge\.test-venv\Scripts;' + $env:PATH
& .\.test-venv\Scripts\python.exe -m pytest -q -p no:cacheprovider `
  tests/deployment/test_external_governance_bridge.py `
  tests/deployment/test_external_governance_build_report.py `
  tests/deployment/test_g009_release_candidate_tooling.py `
  tests/deployment/test_build_app_known_failure_baseline.py `
  tests/deployment/test_g009_zone4_owner_b_contract_conflict_policy.py `
  tests/deployment/test_runtime_dependency_provenance.py `
  --basetemp=D:/g9-release-gate-bridge/.test-governance-operator-reproduction `
  --junitxml=artifacts/governance-operator-reproduction.xml --tb=short
```

The executable verification semantics were checked against the
[official CLI manual](https://cli.github.com/manual/gh_attestation_verify) and
[versioned Sigstore integration source](https://github.com/cli/cli/blob/v2.95.0/pkg/cmd/attestation/verification/sigstore.go).

---

# Historical report from the pre-existing overlay (superseded for current bytes)

The following records the previous implementation and validation. Its counts and
hashes identify that earlier overlay, not this continuation.

# Independent external governance bridge

Status: implemented verification core and build preflight; **NO_GO / production
activation blocked**. No deployment, push, merge, production mutation, release
permission change, issuer creation or signing-key creation was performed.

Worktree: `D:\g9-release-gate-bridge`, initially clean, detached HEAD
`69dbe57aa535112b1759e3f3bdcf9ecbe1680efb`, tree
`4e14800b5e064c6ec95127de8917bb3e34314cad`. Changes are an uncommitted overlay;
HEAD alone does not identify these new bytes.

## Inspected authority

* `scripts/release/build-release-image.ps1`: previously unconditional governance
  attestation rejection, despite caller-supplied authority strings.
* `scripts/release/verify_release_candidate_binding.py`: local binding checks;
  imported-module identity must still reject without external runner attestation.
* R27 reference (read only):
  `D:/go-odyssey-g009-storage-recovery/G009_MC_TAKEOVER_20261016_R2/R27_CLAUDE_TRUSTED_RELEASE_GATE_20261017/implementation/trusted_release_gate.py`,
  SHA256 `99ac278f67fc44b1b62f6bb79b585a80984244ac181a537d8a6d41eb89e28746`.
  Its maximum admission is `EVIDENCE_ADMITTED_ATTESTED`, while release stays
  `NO_GO_PENDING_OWNER`. It is not a release-decision issuer and was not modified
  or imported as a governance trust anchor.
* `.github/workflows/g009-candidate-independent-324.yml`: uploads test evidence,
  explicitly says `formal_release_attestation = NOT_PRESENT`; it is not an
  independently authorized governance signer. Workflow/permissions unchanged.

No authenticated governance issuer, authorized signed BUILD_APP decision, or
protected verifier installation receipt was supplied or identified in these
inspected inputs. This does not assert that none exists elsewhere.

## Changed files and behavior

* `scripts/release/verify_external_governance.py`: strict decision parser,
  bounded immutable decision snapshot, exact source/common-directory/challenge
  binding, UTC validity window of at most ten minutes, pinned GitHub-hosted
  issuer/repository/workflow/ref/commit/run/attempt, exact attestation subject
  and custom predicate, subprocess timeout, and durable atomic replay consumption.
  Runs `gh attestation verify` with issuer, signer workflow and digest, source
  ref and digest, predicate type and deny-self-hosted restrictions. Its profile
  pins the absolute gh executable and bytes, host home/config, and replay storage.
  Caller GH/Sigstore/Python environment overrides cannot choose those roots.
  JSON, flags, a digest or a locally signed receipt cannot provision a profile.
* `scripts/release/build-release-image.ps1`: checks governance before creating
  a detached worktree, tests or Docker, including DryRun. Decision and challenge
  are untrusted inputs. The authority entrypoint is a fixed protected external
  executable, never candidate Python or a PATH-resolved verifier. The externally
  authenticated installation hash is deliberately absent; build remains closed
  with `EXTERNAL_GOVERNANCE_TRUST_ANCHOR_UNPROVISIONED`. No caller override exists.
* `scripts/release/verify_release_candidate_binding.py`: includes the bridge in
  recorded control-plane byte identity and documents governance/evidence
  separation. The external runner-attestation rejection remains intact.
* `tests/deployment/test_external_governance_bridge.py`: synthetic positive
  verification and rigorous rejection cases. An injected runner always returns
  `MOCK_VERIFIED_NOT_AUTHORIZED`, never consumes a production decision and never
  authorizes build/release or admits evidence.
* `tests/deployment/test_g009_release_candidate_tooling.py`: gives the disposable
  plugin-test project its own pytest configuration so worktree-local scratch
  directories cannot inherit the real repository's collection/import boundary.
  Assertions and production behavior are unchanged.

The decision schema requires exactly: `schema`, `decision_id`, `action`,
`gate_sha`, `product_sha`, `git_common_dir`, `challenge`, `issued_at`,
`expires_at`, `evidence_sha256`. The only supported action is
`AUTHORIZE_BUILD_APP`. The predicate URI is currently an inert protocol identifier
under reserved `.invalid`; it neither identifies nor provisions an issuer.

A signed decision's evidence digest is an authorization's reference to evidence,
not proof that tests ran. This verifier **always** reports `evidence_admitted=false`
and `release_authorized=false`. Runner execution attestation, independent reviewer
admission and subsequent release/deploy approvals remain separate requirements.

## Exact prerequisites for activation

1. Independently authorized governance issuer and protected workflow source,
   externally pinned repository/workflow/ref/full commit/run/attempt, with an
   Owner/governance decision that this workflow may issue BUILD_APP authorization.
   Candidate tests or an Actions provenance certificate alone do not grant this.
2. Administrator-controlled external installation of the reviewed verifier,
   interpreter/runtime, gh binary, trust configuration and profile, outside both
   candidate checkouts. Its distribution/install hash must be independently
   authenticated, then pinned by the governing host. The proposed fixed Windows
   entrypoint is `C:\Program Files\Go Odyssey Governance\verify-governance.exe`;
   **no such installation was created or asserted here**. Candidate edits to this
   reference implementation cannot establish the host's trust in themselves.
3. A real signed, unexpired BUILD_APP decision over the exact Gate/Product,
   repository identity, evidence reference and host invocation challenge, plus
   GitHub/Sigstore attestation retrievable by the pinned verifier. No fake decision
   or self-signed trust root was generated. Challenge exchange with an issuer is
   not provisioned because no issuer was supplied.
4. A pre-created, administrator-protected local SQLite replay ledger with the
   exact `DDL` in the verifier. No CLI reset/init facility exists. Protect the
   database, parent directory and backups against candidate writes/rollback;
   retain them across invocations. SQLite concurrency is single-host only.
5. Trusted host clock/network/GitHub authentication and protected home/config.
   Offline, missing/failed attestation or timeout never falls back to local JSON.
6. Independently admit test execution and reviewer evidence through their own
   trusted hosts. This change does not wire those missing R27/runner/reviewer
   authorities and cannot make the full build or release pipeline pass.

Until these exist, both the Python CLI and PowerShell build reject. There is no
claim of live cryptographic success, operational production activation, signed
release authorization, or Owner acceptance.

## Validation

Test execution uses workspace-local `.test-venv` and `.test-deps`. The supplied
Python lacked pytest; network pip installation failed with WinError 10013.
Available pytest 9.1.1 / Flask 3.0.3 and dependencies were read from local pip cache
and extracted only into this worktree. `PYTHONDONTWRITEBYTECODE=1` prevents writes
to external Python libraries. PowerShell test execution uses process-only
`PSExecutionPolicyPreference=Bypass`; no persistent execution/release policy changes.
Automatic approval review rejected recursive temporary-directory cleanup with
`blocked by policy` and supplied no more specific reason. Generated test/runtime
directories remain inside this worktree with local ignore files; no external
directory was deleted or modified.

Initial combined run: **182 passed, 22 failed**, saved in
`artifacts/governance-bridge-tests-initial.xml`. Failures exposed an unclosed SQLite
handle and native execution-policy test setup, plus existing subprocess dependency
and collection-boundary problems. They are historical failures, not passes.
After explicit connection closing and test environment corrections, the
intermediate run was **325 passed, 1 failed** (nested synthetic-project collection),
saved in `artifacts/governance-bridge-tests-final.xml`. The isolated pytest project
configuration fixes that collection failure.

Final complete run: **375 passed, 0 failed, 0 errors, 0 skipped**, in **172.00s**:
51 bridge cases plus the existing 324 regression cases across the four release
suites named in the command below. JUnit:
`artifacts/governance-bridge-exact-final.xml`. Final bridge-only run: **51 passed**;
final build-wiring checks: **3 passed**. `git diff --check` passes.

Final results and SHA256 receipts are recorded in
`artifacts/governance-bridge-validation.json`. The new suite covers wrong issuer,
repository, ref, source/signer commit, workflow, runner, run/attempt, subject digest,
subject name and predicate; forged approval flags/JSON, duplicate keys/subjects,
expired/future/overlong decisions, mismatched Gate/Product/common-dir/challenge,
missing/oversized decision, missing/malformed/failed attestation, offline/timeout,
candidate environment or executable replacement, mutable source snapshot,
missing/corrupt/schema-modified/triggered replay ledger, and eight concurrent
consumers with exactly one winner. Native PowerShell DryRun verifies the real
entrypoint fails before build setup.

Synthetic positive tests validate verification policy and ledger behavior only;
they are not evidence of real signatures or production authorization.

Reproduction command after restoring the test-only environment described above:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PSExecutionPolicyPreference = 'Bypass' # this test process and children only
$env:PATH = 'D:\g9-release-gate-bridge\.test-venv\Scripts;' + $env:PATH
& .\.test-venv\Scripts\python.exe -m pytest -q -p no:cacheprovider `
  tests/deployment/test_external_governance_bridge.py `
  tests/deployment/test_g009_release_candidate_tooling.py `
  tests/deployment/test_build_app_known_failure_baseline.py `
  tests/deployment/test_g009_zone4_owner_b_contract_conflict_policy.py `
  tests/deployment/test_runtime_dependency_provenance.py `
  --basetemp=D:/g9-release-gate-bridge/.test-exact-final `
  --junitxml=D:/g9-release-gate-bridge/artifacts/governance-bridge-exact-final.xml `
  --tb=short
```

Only disposable repositories and mocked Docker interactions are used by these
tests. They are implementation regression checks, not a formal R27 admission run
or a release permission grant. Source hashes are compared before/after the last
full run so its results identify the final implementation bytes.

GitHub CLI verification semantics were checked against the installed gh 2.95.0
help and [official verification documentation](https://cli.github.com/manual/gh_attestation_verify).
