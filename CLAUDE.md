## Canonical Repository Rules

Read [ADR-0001](docs/architecture/ADR-0001-canonical-repository-and-deployment.md) before doing
any Git, branch, PR, recovery, or deployment work in this repository.

- The canonical integration branch is `origin/master`.
- Use isolated feature branches for implementation work — do not commit directly to `master`.
- Recovery branches (`recovered-*`) are preservation-only — never a merge source, never canonical.
- Production identity requires runtime/hash evidence — never infer it from branch names, commit
  subjects, or the presence of local tooling files.
- Merge and deployment are separate, owner-gated operations. A merged PR is not a deployed PR.
- The production deployment mechanism is currently PENDING GOVERNANCE AUDIT — do not invent,
  guess, or restore deployment commands (e.g. `deploy.ps1`) without that audit.
- Do not modify `.env` or unknown untracked artifacts, and do not inspect secrets.
- Do not directly edit vendored SGF Engine code — changes originate on the SGF Engine development
  line and are deliberately re-vendored.
- Puzzle/judging correctness comes from `sgf_engine` — AI explains, the Engine judges.
- No destructive Git operations (`git reset --hard`, `git clean`, force-deleting branches) without
  explicit owner approval.
