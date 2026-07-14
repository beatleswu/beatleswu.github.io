## Canonical Repository Rules

Read [ADR-0001](docs/architecture/ADR-0001-canonical-repository-and-deployment.md) before doing
any Git, branch, PR, recovery, or deployment work in this repository.

- The canonical integration branch is `origin/master`.
- Use isolated feature branches for implementation work — do not commit directly to `master`.
- Recovery branches (`recovered-*`) are preservation-only — never a merge source, never canonical.
- Production identity requires runtime/hash evidence — never infer it from branch names, commit
  subjects, or the presence of local tooling files.
- Merge and deployment are separate, owner-gated operations. A merged PR is not a deployed PR.
- DEPLOY-GOV-1 is closed (ADR-0001, `01af7c2f5`). The reviewed production deployment mechanism is
  `scripts/release/*.ps1` — `deploy-release-image.ps1` (full image deploy) and
  `deploy-static-release.ps1` (static-only deploy) — backed by `tests/deployment/*.py`. See
  [docs/deployment/production_deployment_governance.md](docs/deployment/production_deployment_governance.md)
  for the operational contract. `deploy.ps1` does not exist in this repository and must never be
  invented, restored, or guessed at. Every deployment script run still requires an explicit,
  separate owner `GO_DEPLOY` (or `GO_ROLLBACK`) gate at execution time, passed via `-OwnerGate` with
  `-Execute` — a merged PR, or the mere existence of these scripts, never implies authorization to
  run them.
- Do not modify `.env` or unknown untracked artifacts, and do not inspect secrets.
- Do not directly edit vendored SGF Engine code — changes originate on the SGF Engine development
  line and are deliberately re-vendored.
- Puzzle/judging correctness comes from `sgf_engine` — AI explains, the Engine judges.
- No destructive Git operations (`git reset --hard`, `git clean`, force-deleting branches) without
  explicit owner approval.
