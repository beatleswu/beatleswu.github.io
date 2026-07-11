## Canonical Repository Rules

Read [ADR-0001](docs/architecture/ADR-0001-canonical-repository-and-deployment.md) before doing
any Git, branch, PR, recovery, or deployment work in this repository.

- The canonical integration branch is `origin/master`.
- Recovery branches (`recovered-*`) are preservation-only — never a merge source, never canonical.
- Production identity requires runtime/hash evidence — never infer it from branch names, commit
  subjects, or the presence of local tooling files.
- Merge and deployment are separate, owner-gated operations. A merged PR is not a deployed PR.
- Do not modify `.env` or unknown untracked artifacts.
- Do not directly edit vendored SGF Engine code — changes originate on the SGF Engine development
  line and are deliberately re-vendored.
