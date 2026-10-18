# External BUILD_APP governance operator runbook

Current state: **BLOCKED / NO_GO**. This is an operator handoff, not an authority
grant. Commands below were not run against production. Values enclosed in `<...>`
must come from the independent Owner/governance authority; they are not defaults.

## Exact missing issuer

The supported OIDC token issuer is exactly
`https://token.actions.githubusercontent.com`. That URL is known; it does not
authorize any particular workflow to make governance decisions.

The missing governance principal is the **Owner-authorized BUILD_APP signing
repository + workflow path + protected ref + full signer/source commit + run ID +
run attempt**. Its values are **UNKNOWN_NOT_SUPPLIED**. Also absent are an
authenticated host-verifier installation receipt, profile/root pins and a real
signed decision. No exact principal can honestly be named from the supplied
inputs. The local remote `beatleswu/beatleswu.github.io` is the candidate source,
not an authorization to trust it as issuer. Its existing
`g009-candidate-independent-324.yml` declares `formal_release_attestation=NOT_PRESENT`.
R27 evidence admission is likewise not BUILD_APP issuance authority.

Obtain an independent receipt that names the principal, the permission to issue
`AUTHORIZE_BUILD_APP`, the reviewed workflow source, evidence digest, exact
Gate/Product/common-directory binding and challenge exchange. Do not substitute
a green Actions run, local approval JSON, locally created key or candidate SHA.

## Read-only preparation

From this worktree, the following prints the missing prerequisites and exits 1
deliberately. It cannot authorize or consume a decision:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
& .\.test-venv\Scripts\python.exe -I scripts/release/verify_external_governance.py --requirements
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
git rev-parse --path-format=absolute --git-common-dir
git status --short
```

On the independent administrative host, inspect the authority-supplied signer
without changing GitHub workflows or permissions:

```powershell
$SignerRepo = '<OWNER/APPROVED_GOVERNANCE_REPOSITORY>'
$WorkflowFile = '<APPROVED_WORKFLOW_FILENAME.yml>'
$SignerCommit = '<APPROVED_FULL_40_HEX_COMMIT>'
$RunId = '<APPROVED_RUN_ID>'
$RunAttempt = '<APPROVED_RUN_ATTEMPT>'
$gh = 'C:\Program Files\GitHub CLI\gh.exe'
& $gh workflow view $WorkflowFile --repo $SignerRepo --ref $SignerCommit --yaml
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect approved workflow' }
& $gh api "repos/$SignerRepo/actions/runs/$RunId/attempts/$RunAttempt" `
  --jq '{id,run_attempt,head_sha,path,event,status,conclusion,html_url}'
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect approved signer run' }
```

Compare all identities to the independent receipt. These API results are
diagnostic; they cannot establish authorization. The workflow must actually
attest the decision artifact with the predicate URI used below, using
GitHub-hosted execution. Reusable workflows require the actual signer identity;
this implementation requires signer and source to match the one approved
repository/commit. It deliberately rejects unsupported cross-repository signing.
Issuance/dispatch commands depend on that workflow's reviewed interface, which
was not supplied; no invented dispatch inputs or issuer workflow is provided.

## Host installation and independent pins

The reference has no CLI or environment switch to provision trust. A separate
administrator must install a reviewed distribution outside all candidate trees.
The trust chain is:

1. Independently authenticated verifier executable hash pinned in the reviewed
   Gate build entrypoint (`$governanceVerifierSha256`, currently empty).
2. Independently authenticated `host-profile.json` hash compiled into that
   verifier distribution (`HOST_PROFILE_SHA256`, currently empty). Fixed path:
   `C:\Program Files\Go Odyssey Governance\host-profile.json`.
3. That exact profile pins approved signer/source/run, absolute gh executable
   and SHA256, Sigstore root JSONL path and SHA256, and protected host storage.
4. Real `gh attestation verify` checks Sigstore signatures/timestamps and the
   exact certificate identity, then the bridge checks decision bindings/expiry
   and consumes its ID atomically in the protected replay ledger.

Hashing files inside a candidate does not authenticate them. Administrators must
review the distribution, its Python/runtime/packaging dependencies, workflow
authority and root provenance independently, then provision the two distribution
pins through their controlled installation/review process. Candidate builds must
not stamp their own installation/profile pins. The protected host must also
authenticate the Gate entrypoint's bytes; a candidate-editable script is not a
host security boundary by itself.

Use separate administrator/verifier/candidate identities or an equivalent broker
and restricted process token. Protect executable, dependencies, profile, gh,
config, scratch, ledger and parent directories against candidate writes, link
replacement and rollback. A filename under Program Files alone is not ACL proof.
This reference does not provision that isolation or change host ACLs.

On a connected administrative staging host, acquire candidate roots using gh's
TUF verification and retain its exit status. This is acquisition, not governance
approval; independently authenticate and review the resulting root bytes before
pinning them. Use an administrator-approved gh binary/toolchain:

```powershell
$gh = 'C:\Program Files\GitHub CLI\gh.exe'
$Staging = '<ABSOLUTE_ADMINISTRATOR_CONTROLLED_STAGING_DIRECTORY>'
$rootLines = @(& $gh attestation trusted-root)
if ($LASTEXITCODE -ne 0 -or $rootLines.Count -eq 0) { throw 'Sigstore root acquisition failed' }
$rootFile = Join-Path $Staging 'trusted-root.jsonl'
[IO.File]::WriteAllText($rootFile, ($rootLines -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
Get-FileHash -LiteralPath $gh,$rootFile -Algorithm SHA256
```

Preserve JSONL's final newline (required by gh 2.95). The host profile has exactly
these fields; none may be omitted or added:

```json
{
  "repository": "<OWNER/APPROVED_GOVERNANCE_REPOSITORY>",
  "workflow": "<OWNER/APPROVED_GOVERNANCE_REPOSITORY>/.github/workflows/<APPROVED_WORKFLOW.yml>",
  "ref": "refs/heads/<APPROVED_PROTECTED_BRANCH>",
  "commit": "<APPROVED_FULL_40_HEX_COMMIT>",
  "run_id": "<APPROVED_RUN_ID>",
  "run_attempt": "<APPROVED_RUN_ATTEMPT>",
  "gh_path": "C:\\Program Files\\GitHub CLI\\gh.exe",
  "gh_sha256": "<INDEPENDENTLY_AUTHENTICATED_LOWERCASE_SHA256>",
  "ledger": "C:\\ProgramData\\Go Odyssey Governance\\consumed.sqlite",
  "host_home": "C:\\ProgramData\\Go Odyssey Governance\\home",
  "gh_config_dir": "C:\\ProgramData\\Go Odyssey Governance\\gh-config",
  "trusted_root": "C:\\Program Files\\Go Odyssey Governance\\trusted-root.jsonl",
  "trusted_root_sha256": "<INDEPENDENTLY_AUTHENTICATED_LOWERCASE_SHA256>"
}
```

Pre-create `host_home/tmp` and protected GH config/home. Authenticate the verifier
service using the protected config; caller GH_TOKEN, PATH, proxy, CA, Sigstore,
Python and HOME overrides are not forwarded to gh. Pin changes/run attempts
require new independent profile approval and distribution pinning.

Initialize the replay ledger **once**, under administrator control, with exactly:

```sql
CREATE TABLE consumed (decision_id TEXT PRIMARY KEY NOT NULL, digest TEXT NOT NULL)
```

Use SQLite DELETE or WAL journaling and durable local storage. Admission opens
the existing database read/write; it never creates/resets it. Protect its directory,
sidecars and backups from replacement/rollback; never delete rows to retry a
consumed decision. Multiple independent hosts need a shared authoritative replay
service rather than copies of this single-host ledger.

## Decision and real verification

The independently approved issuer must sign the exact bytes of a file named
`release-decision.json`. Required JSON fields: `schema` =
`g009-independent-build-decision-v1`, `action` = `AUTHORIZE_BUILD_APP`,
`decision_id`, `gate_sha`, `product_sha`, `git_common_dir`, `challenge`,
`issued_at`, `expires_at`, `evidence_sha256`. No extra fields are accepted.
The challenge is a fresh 32-byte host-generated random value encoded as 64
lowercase hex characters; do not reuse it. The issuer must obtain the invocation
binding from the trusted host, not accept uncontrolled candidate requests as
approval. Times must be UTC `YYYY-MM-DDTHH:MM:SSZ`, valid now, at most 600 seconds
apart. The evidence SHA256 is an authorization reference, not test admission.

Generate the challenge only on the trusted invocation host and pass it through
the approved issuer's challenge exchange:

```powershell
$challengeBytes = New-Object byte[] 32
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
try { $rng.GetBytes($challengeBytes) } finally { $rng.Dispose() }
$Challenge = ([BitConverter]::ToString($challengeBytes)).Replace('-', '').ToLowerInvariant()
```

On the protected host, this is the real cryptographic diagnostic command. It
verifies but **does not consume a decision or authorize Build**:

```powershell
$p = Get-Content -LiteralPath 'C:\Program Files\Go Odyssey Governance\host-profile.json' -Raw | ConvertFrom-Json
$Decision = '<ABSOLUTE_PATH_TO_ISSUER_SIGNED_release-decision.json>'
& $p.gh_path attestation verify $Decision --hostname github.com `
  --repo $p.repository --signer-digest $p.commit `
  --source-ref $p.ref --source-digest $p.commit `
  --cert-oidc-issuer https://token.actions.githubusercontent.com `
  --cert-identity "https://github.com/$($p.workflow)@$($p.ref)" `
  --custom-trusted-root $p.trusted_root --deny-self-hosted-runners `
  --predicate-type https://go-odyssey.invalid/attestations/build-authorization/v1 --format json
if ($LASTEXITCODE -ne 0) { throw 'Real Sigstore verification failed; no fallback' }
```

The reserved `.invalid` URI is an exact protocol type, not an issuer or network
endpoint. The bridge additionally checks certificate source/signer/run/attempt,
exact subject name/digest, invocation binding, expiry after verification and replay.
Do not call the consuming verifier as a precheck and then reuse the same decision.

After independent installation acceptance, invoke Build from the approved clean
Gate checkout using a fresh signed decision and its host challenge:

```powershell
& .\scripts\release\build-release-image.ps1 `
  -GovernanceExpectedGitCommonDirectory '<EXACT_APPROVED_ABSOLUTE_COMMON_DIR>' `
  -GovernanceGateSourceSha '<EXACT_APPROVED_GATE_40_HEX_SHA>' `
  -GovernanceProductSourceSha '<EXACT_APPROVED_PRODUCT_40_HEX_SHA>' `
  -GovernanceDecision '<ABSOLUTE_PATH_TO_SIGNED_DECISION>' `
  -GovernanceChallenge '<HOST_64_HEX_CHALLENGE>'
```

Do not run this against the current uncommitted overlay: installation pins are
absent and it is not an approved clean Gate candidate. DryRun also requires and
consumes a real valid decision once provisioned. Failures after consumption need
a new decision, not replay-ledger editing. Build authorization never admits test
execution/reviewer evidence or grants release/deploy authority; those independent
gates remain closed until their own authorities act.

## Verification references and current live limitation

Flags/output semantics were checked against installed gh 2.95.0 and the official
[CLI manual](https://cli.github.com/manual/gh_attestation_verify),
[versioned verifier implementation](https://github.com/cli/cli/blob/v2.95.0/pkg/cmd/attestation/verification/sigstore.go)
and [root acquisition manual](https://cli.github.com/manual/gh_attestation_trusted-root).
The real root-acquisition probe in this session exited 1: access to
`https://tuf-repo-cdn.sigstore.dev/15.root.json` was denied by socket permissions.
See `artifacts/governance-r2-network-probe.json`. No live cryptographic positive,
signed governance decision, host installation or production activation is claimed.
