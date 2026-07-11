# ADR-0001: Canonical Repository and Deployment Governance

Status: Accepted
Date: 2026-07-11
Decision Owners: beatleswu (owner), with Claude/Codex/ChatGPT operating under the boundaries defined below

## Context

In early July 2026, a single local working directory (`D:\go-website`) was found to contain two
git-history lineages with no common ancestor:

- **Graph A** — a large family of local-only branches (`optimize-pets-map-images` at the time,
  `phase-22-shadow-judging`, `merge-reunify-20260702`, `production-recovered-20260702`,
  `rq-hotfix1/2/3`, `sgf-fe-hotfix1a-node-property-parser`, `batch-22a-corpus-audit`, and others)
  carrying a long, richly-documented incident history, a full `sgf_engine/` tree, `deploy.ps1`, and
  a `CLAUDE.md` describing a 41-spec governance framework. None of these branches were ever pushed
  to `origin`.
- **Graph B** — `origin/master` on `https://github.com/beatleswu/beatleswu.github.io.git`, with a
  continuous, PR-reviewed history (PRs #1 through #49 at time of writing) including the same
  feature intent (shadow envelope, shadow dashboard, shadow runtime completion) implemented and
  merged independently.

A local branch-recreation event on 2026-07-11 (`optimize-pets-map-images` reset to an old `master`
tip) stranded several Graph A commits, including work done in this session. Two preservation
branches were created (`recovered-optimize-20260711`, `recovered-production-tip-20260711`) before
any cleanup. A multi-step audit — culminating in direct SHA-256 comparison of live production
container files against both lineages — established that **production runs Graph B**, not Graph A.

This ADR exists so that no future session (human or AI) has to re-derive that conclusion from
branch names, commit subjects, or the presence of local tooling files — all of which pointed the
wrong way at various points during the incident.

## Decision

### Canonical Repository

```
https://github.com/beatleswu/beatleswu.github.io.git
```

This is the canonical remote for `D:\go-website`, referenced locally as `origin`. Despite the
GitHub-Pages-sounding name, this repository's `master` branch carries the real, continuously
PR-reviewed history of this application — including the full Phase 19+ SGF Engine roadmap
(GF-001/GF-002/GF-003 fixtures, override-key-strategy ADR, SGF quality triage packets) and the
shadow-judging feature line through PR #49.

### Canonical Branch

```
master
```

Direct production file hashes (`app.py`, `shadow_judging.py`, `shadow_dashboard.py`) were verified
identical to `origin/master` at commit `4214820d1` (PR #47) before PR #49 merged. PR #49 merged
into `master` as commit `8c077244e05c0a844c66539a6e1e079cee688c6e`.

**Graph A is not canonical production.** It contains real, valuable, non-duplicated local work
(see "Recovery and Archive Branches" below), but it must never be described as the production
lineage in any future audit or report.

### Production Runtime Identity

Determining what code is actually deployed follows this strict priority order:

1. **Production container file hashes** (`docker exec <container> sha256sum <file>`), compared
   directly against `git show <ref>:<path> | sha256sum`.
2. **Image/build metadata** where available (image digest, build labels).
3. **Comparison with Git objects** — confirming the hash matches a real, identifiable commit.
4. **Git branch and commit labels** — supporting evidence only, never sufficient alone.

Branch names, the presence or absence of local tooling files (e.g. `deploy.ps1`), and commit
subject lines are **not proof** of production identity. This was demonstrated directly during the
2026-07 incident: `deploy.ps1`'s presence on Graph A and absence from Graph B was initially
(incorrectly) read as evidence Graph A was canonical — the opposite was true.

### Feature and PR Workflow

```
origin/master
  → isolated feature branch
  → focused tests
  → PR targeting master
  → review and explicit owner approval
  → merge
  → separate deployment approval
  → production verification
```

One Sprint should normally produce one focused branch, one PR, and one final report. Sprints that
attempt to bundle implementation, verification, and deployment together make it harder to isolate
what actually changed and why — this is the direct lesson of the E2.4A → E2.4A-fix → Release Gate
sequence, which stayed trustworthy specifically because each step re-verified from a clean state
rather than trusting the prior step's self-report.

### Deployment Governance

**Merge is not deployment.** No agent may treat a merged PR as deployed, and no agent may deploy
without explicit, separate owner authorization for that specific action. Use these gates verbatim,
or an equivalently unambiguous instruction naming the PR/action:

```
GO MERGE
GO DEPLOY
```

**`deploy.ps1` is not, and never was, the deployment mechanism.** It does not exist anywhere in
Graph B's tracked history (confirmed: `git log --oneline origin/master -- deploy.ps1` returns
nothing) and does not exist on the production host's container filesystem either (confirmed via
`docker exec go-odyssey-app sh -lc "test -f /app/deploy.ps1"` → not found). Its presence on Graph A
and absence from Graph B was, at one point during the 2026-07 incident, misread as evidence Graph A
was canonical — see "Production Runtime Identity" above. It must not be restored, invented, or
guessed at under any circumstance.

**DEPLOY-GOV-1 audit result: the deployment mechanism is `scripts/release/*.ps1`, and it is
reviewed.** A separate, independently-built pipeline — `scripts/release/deploy-release-image.ps1`,
`rollback-release.ps1`, `preflight-production.ps1`, `verify-production-release.ps1`, and the shared
`ReleaseTooling.psm1` — has 36+ commits of PR-reviewed history on `origin/master` culminating in
PR #75, backed by `tests/deployment/*.py` (9 test files, 28+ commits: build-manifest, compose
secret boundaries, image content boundary, runtime dependency provenance, SGF engine vendor
provenance, and release-tooling behavior itself). This is the canonical deployment mechanism. It is
owner-gated at execution time via `-OwnerGate GO_DEPLOY` and requires `-Execute` to mutate anything;
without `-Execute` it dry-runs and only reports identity/readiness.

**Known gap closed by this audit, then fixed:** the scripts were reviewed, but the
production-specific input that drives them — `deploy/release-layout.production.json` (the
`-LayoutFile` argument: compose paths, service names, health-check URLs) — was found to be
untracked, with zero git history, alongside two related planning docs
(`docs/deployment/pr55_deploy_day_verification_checklist.md`,
`docs/deployment/TECH_DEBT_BACKLOG.md`). All three were brought under review in the same change
that added this section (see PR history for this file). Any future edit to the production layout
file must go through a reviewed PR before a deploy run may reference it — a layout file with no
review trail is exactly the kind of unaudited artifact this ADR exists to prevent.

**Remaining, explicitly out of scope for DEPLOY-GOV-1 closure:** TECH-DEBT-001 (duplicated
readiness/DB/compose-env/questions-probe helpers across `scripts/release/*.ps1` instead of living
once in `ReleaseTooling.psm1`) is tracked and deliberately deferred — it does not block deploy-day
execution, per the backlog's own priority note. Consolidating it later must not be pulled into any
production release's main line.

### SGF Engine Governance

`sgf_engine` is **not currently tracked in `origin/master`'s git history at all**
(`git ls-tree origin/master -- sgf_engine` returns empty). The only place this ADR could find the
vendoring rule documented is on the preserved Graph A branch, at
`sgf_engine/VENDORED_FROM.txt` (verified directly before writing this section):

```
source_repo: https://github.com/beatleswu/beatleswu.github.io
source_branch: testing-baseline-test-isolation
source_commit: d729645
vendored_date: 2026-07-05
rule: never edit engine code here; re-vendor from the testing repo.
```

`testing-baseline-test-isolation` is confirmed to exist as a real branch on `origin`
(`origin/testing-baseline-test-isolation`). The governance rule this ADR adopts, pending a full
audit of how sgf_engine actually reaches the production container:

- The production application line (`master` and its feature branches) treats `sgf_engine` as
  **vendored and read-only**. Direct edits to SGF Engine code from within the application line are
  prohibited.
- Changes to SGF Engine behavior must originate on the SGF Engine development line
  (`testing-baseline-test-isolation` or its successor), be tested there, and then be deliberately
  re-vendored into the application line with an updated `VENDORED_FROM.txt`.
- **Open question, explicitly flagged, not resolved by this ADR**: since `sgf_engine/` is not
  tracked in `origin/master` at all, the actual mechanism by which it reaches the production
  container (submodule, build-time fetch, manual COPY from elsewhere) is unknown and must be
  established by a dedicated audit before anyone touches SGF Engine vendoring again.

### Shadow Judging Governance

Shadow Judging is an **observation and comparison system**. It is not, and must never become, a
fallback production judging authority. `sgf_engine` is the sole correctness authority for Shadow
verdict generation.

When SGF Engine is unavailable or fails during Shadow evaluation:

- record an explicit, observable error event;
- preserve legacy API behavior byte-for-byte;
- never silently substitute a hand-written parser or alternate verdict implementation.

This is not aspirational — it is the specific governance correction made in **E2.4A / PR #49**
(merged as `8c077244e05c0a844c66539a6e1e079cee688c6e`), which removed a silent fallback from
`sgf_engine` to a hand-rolled `_shadow_verdict_simple()` that had existed in `shadow_judging.py`.
Any future change to `shadow_judging.py` must preserve this property, and any code review of that
file should treat a reintroduced silent fallback as a governance regression, not just a bug.

### Recovery and Archive Branches

```
recovered-optimize-20260711
recovered-production-tip-20260711
```

These branches exist **only** to preserve local historical work that was stranded by the 2026-07-11
branch-recreation incident. They are:

- **recovery/archive references** — not live development branches;
- **not canonical production branches** under any circumstance;
- **not direct merge sources** — nothing merges from them into `master` in bulk;
- **candidates for selective, reviewed transplantation of unique work only**.

Graph A (reachable from these branches) contains real, non-duplicated work worth preserving,
including the SGF-DATA-AUDIT1/1B tooling (`tools/audit_tree_null_records.py` and its tests),
SGF-FE-HOTFIX1A, and the RQ-hotfix series. None of this exists on `origin/master` today. Porting
any of it forward must happen via normal reviewed cherry-picks of specific, identified commits —
never a bulk merge of Graph A into `master`.

### AI-Agent and Owner Responsibilities

AI roles below are workflow defaults describing where each tool tends to add the most value — they
are not security principals, and they do not themselves carry any permission. Actual authorization
is controlled entirely by the owner gates in the next section.

**Claude** — repository and production audit; code/architecture review; recovery analysis;
controlled implementation when explicitly assigned a scoped Sprint.

**Codex** — focused implementation; tests; branch/commit/PR workflow; deployment only after
explicit authorization and independently verified tooling.

**ChatGPT** — architecture and Sprint design; task documents; risk analysis; interpreting audit and
implementation reports.

**Owner** — the owner alone authorizes: merge to `master`; production deploy; database migration;
force push; destructive cleanup; canonical branch or remote changes; production secrets or
credentials.

### High-Risk Operation Gates

Explicit owner approval is required before any of the following, regardless of which agent is
operating:

- merging to `master`
- deploying
- database migrations or schema changes
- changing remotes
- moving or deleting canonical/recovery branches
- force push
- `git reset --hard`
- `git clean`
- production file changes
- restarting or rebuilding production containers
- deleting unknown untracked files
- modifying `.env`
- exposing credentials or secrets

## Consequences

### Positive

- Future sessions have a single, dated, evidence-backed reference for "what is canonical" instead
  of re-deriving it from branch archaeology every time.
- The Shadow Judging silent-fallback risk is now documented as a governance property to defend, not
  just a one-off bug fix.
- Recovery branches have an explicit, bounded purpose, reducing the temptation to either delete them
  prematurely or treat them as a second production lineage.

### Trade-offs

- **DEPLOY-GOV-1 is closed.** The deployment mechanism is `scripts/release/*.ps1`, reviewed via
  PR history through PR #75 and backed by `tests/deployment/*.py`. The production layout input
  (`deploy/release-layout.production.json`) and deploy-day checklist docs were found untracked and
  have been brought under review (see "Deployment Governance" above). What remains deferred is
  TECH-DEBT-001 (helper duplication across the release scripts), which is explicitly non-blocking.
- The SGF Engine vendoring path (how `sgf_engine/` reaches the production container despite not
  being tracked in `origin/master`) remains an open question this ADR flags but does not resolve.

### Remaining Unknowns

- The exact mechanism that gets `sgf_engine/` into the running production container.
- Whether `go-odyssey-production` (referenced only in prior session memory, not in any currently
  reachable Git ref or remote) still exists as a private backup mirror — **historically referenced,
  not currently verified**.

## Lessons Learned — 2026-07 Repository Lineage Incident

Recorded neutrally, without attributing fault to any person or model — the point is the pattern,
not who ran into it.

1. Two unrelated Git histories (no common ancestor) existed in the same local repository at the
   same time, under branch names that looked like they described the same project.
2. A local branch name (`optimize-pets-map-images`) suggested production lineage but was not, by
   itself, authoritative — the branch was silently recreated from a different, shallower base
   partway through the incident.
3. The presence of `deploy.ps1` on one lineage and its absence on the other was initially treated
   as strong evidence of which lineage was canonical. It pointed the wrong way.
4. Recovery branches (`recovered-optimize-20260711`, `recovered-production-tip-20260711`) were
   correctly created to preserve local-only work *before* any cleanup or reconciliation decision was
   made — this is the right default when lineage is uncertain.
5. Direct production container file hashes ultimately proved that production matched Graph B /
   `origin/master`, not Graph A — settling the question that branch names and local files could not.
6. Graph A contained valuable but non-canonical local work (SGF-DATA-AUDIT1/1B, HOTFIX1A,
   RQ-hotfixes) that is worth selectively preserving, not discarding wholesale and not bulk-merging.
7. The same investigation also exposed the Shadow Judging silent-fallback risk (E2.4A/PR #49),
   an unrelated but real correctness-governance issue found only because the audit went deep enough
   to read actual code paths instead of trusting file/branch labels.
8. Future identity audits must verify production hashes *before* making any recovery, migration, or
   cleanup decision — not after.

Explicit rules going forward:

- Do not infer canonical status from branch names.
- Do not infer canonical status from commit subjects.
- Do not infer deployment status from merge status.
- Do not infer production identity from local tooling files.
- Prefer direct runtime evidence over any of the above.
- Preserve uncertain histories before cleanup.
- Reconcile unique work selectively, never through blind bulk merges.

## Operational Checklist

Before any Git, branch, PR, recovery, or deployment work in this repository:

1. Read this ADR.
2. Confirm `origin/master` is the branch you mean when you say "canonical" or "production line".
3. If you need to know what's actually running in production, get a runtime hash — do not infer it
   from git state alone.
4. If you're touching a recovery branch (`recovered-*`), treat it as read-only archive unless a
   specific, reviewed transplant is explicitly requested.
5. Never treat "merged" as "deployed". Deployment requires its own explicit owner authorization.
6. `deploy.ps1` does not exist and must never be restored, invented, or guessed at. The reviewed
   deployment mechanism is `scripts/release/*.ps1` (see "Deployment Governance" above,
   DEPLOY-GOV-1). Any edit to `deploy/release-layout.production.json` or the deploy-day docs must
   go through a reviewed PR before a deploy run references it.

## References

- PR #47 — E2.4 shadow runtime coverage merge (`4214820d1`)
- PR #48 — E2.5 read-only shadow dashboard UI (open at time of writing)
- PR #49 — E2.4A: remove silent shadow fallback (merged as `8c077244e05c0a844c66539a6e1e079cee688c6e`)
- `recovered-optimize-20260711`, `recovered-production-tip-20260711` — Graph A preservation branches
- `sgf_engine/VENDORED_FROM.txt` (as read from `recovered-production-tip-20260711`)
- PR #75 — `fix/release: preserve questions volume and parse nested PowerShell JSON`, latest of
  36+ reviewed commits building `scripts/release/*.ps1` (merged as `efd37caf6013aa3504178371e12ddb4c77b8280c`)
- DEPLOY-GOV-1 closure — `deploy/release-layout.production.json`,
  `docs/deployment/pr55_deploy_day_verification_checklist.md`,
  `docs/deployment/TECH_DEBT_BACKLOG.md` brought under PR review
