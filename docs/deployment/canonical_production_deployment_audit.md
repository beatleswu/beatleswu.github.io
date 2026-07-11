# Canonical Production Deployment Audit

Status: Findings recorded, no procedure enacted
Audit Date: 2026-07-11
Canonical Git Commit: `4ea3f63e62d8db9ec50815f99e9ccf0ac6780caf` (`origin/master`)
Production Host: SSH alias `oracle_godoyssey` (instance `instance-20260609-0051`)

## Executive Summary

Production is **not** deployed from `origin/master` (`beatleswu.github.io`) directly, and it is **not**
deployed via any GitHub Actions workflow. The only GitHub Actions workflow on this repository is the
platform's automatic static-site publisher (`pages-build-deployment`), which has nothing to do with
the running application on the Oracle host.

The real mechanism, reconstructed entirely from direct evidence (a `deploy.ps1` found on the
production host, screened for secrets before reading), is: a Windows-local PowerShell script that
(1) runs `git ls-files`/`git rev-parse` against **whatever local repository it is executed from**,
(2) archives those tracked files into a tarball, (3) `scp`s the tarball to the host's `/tmp`,
(4) SSHes in, extracts it directly over `/opt/go-odyssey`, and runs `docker compose build && up -d`,
(5) restarts nginx, (6) publishes a separately-versioned static-asset release for `sw.js`/`i18n.js`,
(7) verifies the public `sw.js` version.

**Critical finding: `deploy.ps1` does not exist anywhere in `origin/master`'s tracked history.** It
only exists on the preserved Graph A branches. This means the actual deployment source has, at least
historically, been a Graph-A-shaped local working directory (with `nginx/`, `assets/`, `sgf_engine/`,
`questions.json`, `wgo/`, `blog/` — none of which are tracked in `origin/master`) — not a clean
checkout of the canonical repository this ADR-0001 designates. Direct file hashing confirms
`app.py`/`shadow_dashboard.py` on production match `origin/master` exactly, but this appears to be
the result of manual file-level synchronization into that local deploy tree, not a git-based
integration.

**Confirmed via direct hash comparison: PR #49 (E2.4A) is NOT deployed.** Production's
`shadow_judging.py` matches the pre-E2.4A hash (`4214820d1`/`554c7c01d`) exactly, not
`origin/master`'s current hash. The silent-fallback risk E2.4A was written to close is still live in
the running system today.

## Evidence Collected

### Canonical Repository

`git ls-tree -r --name-only origin/master` returns 67 files total. There is **no Dockerfile, no
docker-compose file, no nginx configuration, no GitHub Actions workflow, no systemd unit, no
Makefile, no `templates/` or `static/` directory, no puzzle/question data, and no `sgf_engine/`**
anywhere in the canonical repository's tracked tree. The tracked content is: `app.py`,
`shadow_judging.py`, `shadow_dashboard.py`, a small set of shadow-judging test files, a handful of
`docs/planning/*.md` files, `CLAUDE.md`, the ADR, and a generic personal-site template
(`index.html`, jQuery/Magnific-Popup/fliplightbox assets, stock fonts/images) that appears unrelated
to the Go Odyssey application itself.

**Conclusion: the canonical repository alone cannot reproduce the running deployment.** It carries
the shadow-judging Python modules and this governance documentation, but not the application's
templates, static assets, puzzle data, SGF engine, or any build/deploy tooling.

### GitHub Automation

```
gh workflow list
pages-build-deployment  active  263834377
```

10 recent runs, all `pages build and deployment` on `master`, triggered `dynamic` (GitHub's
standard Pages trigger), each completing 3 jobs: `build`, `deploy`, `report-build-status`, producing
a `github-pages` artifact. This is GitHub's built-in static-site publisher — **it is not a custom
workflow and does not deploy to the Oracle production host.**

**No workflow performs production deployment.** No SSH-based deploy step, no Docker build/push step,
no reference to `oracle_godoyssey` or the production host exists in any workflow run inspected.

### Production Filesystem

Host identity: user `ubuntu`, host `instance-20260609-0051`.

Deployment-related search under `/home/ubuntu`, `/opt`, `/srv` (bounded, depth 4) found:

- `/opt/go-odyssey/` — the real deployment directory: `Dockerfile`, `docker-compose.prod.yml`,
  `deploy.ps1`, `deploy-quick.ps1`, `deploy-static.ps1`, a `.git` directory, plus many
  `_backup_*` snapshot directories and `SGF題庫*` directories.
- `/opt/colorfulgo/` — a separate, unrelated project (`Dockerfile`, `docker-compose.prod.yml`,
  `deploy-a1.ps1`) — the `colorfulgo` container seen in `docker ps` belongs to this, not Go Odyssey.

**`/opt/go-odyssey`'s own git state is unreliable and must not be trusted as deployment-identity
evidence by itself:**

```
git rev-parse HEAD        -> cedcb0f1477c31f414d4976ab80256bcfe34c286
git log -1 --oneline       -> fatal: bad object HEAD
git status --short         -> fatal: bad object HEAD
git remote -v               -> (empty — no remote configured at all)
git branch --show-current  -> optimize-pets-map-images
```

The `HEAD` ref points at a commit SHA whose object does not exist in this checkout's local object
database, and no remote is configured. This directly validates ADR-0001's evidence-priority rule:
git refs on this host cannot be trusted; only direct file hashes can establish deployment identity.

`Dockerfile` owned by `ubuntu`, mtime `2026-07-10 07:36:35 UTC`. `docker-compose.prod.yml` mtime
`2026-07-09 12:23:46 UTC`. `deploy.ps1` mtime `2026-07-05 05:24:15 UTC`.

**Deployment model at the filesystem level: a plain directory, populated by file overwrite (tar
extraction), not a git clone/pull.** The Dockerfile's `COPY sgf_engine ./sgf_engine`,
`COPY questions.json srs.db go_learning.db ./`, and similar lines confirm the Docker build context
draws directly from whatever files happen to be present in `/opt/go-odyssey` on disk — files that
are not tracked in `origin/master` and whose provenance is therefore whatever the last `deploy.ps1`
run happened to package from its local source machine.

### Docker Compose

`docker-compose.prod.yml` (secrets redacted where literal values, not variable references, were
present):

- Services: `postgres` (image `postgres:16-alpine`), `app` (build from local `Dockerfile`),
  `scheduler` (build from the same `Dockerfile`, `command: python scheduler.py`), `nginx` (image
  `nginx:alpine`).
- `app`/`scheduler` use **`build:` with local context**, not a pinned/pulled image — confirming a
  host-built model, not registry-pull.
- Most secrets are deferred via `${VAR:-}` (populated from `/opt/go-odyssey/.env`, per comments in
  the file — not inspected). **One exception: `POSTGRES_PASSWORD` is set as a literal value directly
  in the compose file, not deferred to `.env`.** This value has been redacted from this report and
  from all command output; it is flagged here as a security/governance gap, not reproduced.
- `app` mounts: `go-data:/app/data` (named volume), `/opt/go-odyssey-static:/opt/go-odyssey-static:ro`
  (bind mount — matches `GO_ODYSSEY_LIVE_STATIC_ROOT=/opt/go-odyssey-static/current`, an atomic
  "current" symlink pattern for static asset releases), `./katago_cache.db:/app/katago_cache.db:ro`.
- `SHADOW_EVENTS_PATH=/app/data/shadow_events.jsonl` and `SHADOW_JUDGING_ENABLED=1` are set directly
  in the compose file (not behind a flag toggle) — Shadow Judging is unconditionally enabled in this
  configuration.
- `nginx` depends on `app` being `service_healthy`; mounts `./nginx/default.conf` and
  `/etc/letsencrypt` read-only.
- Health checks: `postgres` via `pg_isready`; `app` via the same `/healthz` endpoint used externally;
  `scheduler` explicitly disables health checking.

### Container and Image Identity

```
docker ps --no-trunc
go-odyssey-app         go-odyssey-app         created 2026-07-10 22:45:11 UTC, healthy
go-odyssey-scheduler   go-odyssey-scheduler   created 2026-07-10 22:45:11 UTC
go-odyssey-nginx       nginx:alpine           created 2026-06-25 12:11:49 UTC
go-odyssey-postgres    postgres:16-alpine     created 2026-06-09 07:36:03 UTC
colorfulgo             colorfulgo-colorfulgo  (unrelated project)
```

`go-odyssey-app`: image `sha256:3bf7b88a206e7421701f6dc003ac79a6b0e16f8a47f13d99db7791aeb69afbdd`,
created `2026-07-10T22:45:11Z`, started `2026-07-10T22:45:49Z`, restart policy `unless-stopped`,
Compose labels confirm `project=go-odyssey`, `working_dir=/opt/go-odyssey`,
`config_files=/opt/go-odyssey/docker-compose.prod.yml`, `service=app`.

**The container's creation timestamp (2026-07-10T22:45:11Z) predates both PR #49's merge
(2026-07-11T00:32:29Z) and PR #50's merge (2026-07-11T00:54:24Z).** This is independent, direct
timing evidence — consistent with the file-hash finding below — that neither has been deployed.

No `APP_VERSION`, `GIT_SHA`, `COMMIT_SHA`, or `BUILD_SHA` environment variable is present in the
container. **The build process does not stamp any commit or version identifier into the running
system.** Only `SHADOW_JUDGING_ENABLED=1` was found among the requested identity-relevant variable
names.

### Source and Image Matching

Production file hashes (via `docker exec go-odyssey-app sh -lc sha256sum ...`):

| File | Production hash | Matches |
|---|---|---|
| `app.py` | `bad670834e88...` | `4214820d1`, `554c7c01d`, `8c077244e`, `4ea3f63e6`, `origin/master` — identical everywhere (file untouched by PR #49/#50) |
| `shadow_judging.py` | `890071a5e1bf...` | `4214820d1`, `554c7c01d` **only** — does **not** match `8c077244e`, `4ea3f63e6`, or `origin/master` (all of which have hash `19439c4e29b9...`) |
| `shadow_dashboard.py` | `dee8528eea84...` | identical everywhere (file untouched by PR #49) |
| `CLAUDE.md` | MISSING | Dockerfile does not `COPY` this file — would remain absent even after a rebuild from current `origin/master`, by design (not a runtime file) |
| `docs/architecture/ADR-0001-...md` | MISSING | same reason as above |

**Currently deployed application commit-equivalent: `4214820d1` / `554c7c01d` (PR #47 state, pre-E2.4A).**

- **PR #49 is NOT deployed.** The exact silent-fallback code path E2.4A removed is still running in
  production today.
- **PR #50 is moot for runtime purposes** — it only ever touched `CLAUDE.md` and a docs file that
  the Dockerfile never copies into the image, so "is it deployed" doesn't apply to the running
  container the way it does for `shadow_judging.py`.
- Runtime identity is reproducible from tracked Git content **only for the specific files the
  Dockerfile copies from a source tree that includes them** — but that source tree itself is not
  `origin/master` (which lacks `sgf_engine/`, `questions.json`, `nginx/`, etc. entirely), so full
  reproducibility from `origin/master` alone is **not currently possible**.

### Service Startup

`docker.service` is `enabled` (starts on boot). No dedicated systemd unit exists for the Go Odyssey
Compose stack itself — containers rely on Docker's own `restart: unless-stopped` policy plus
`docker.service` starting at boot. No custom deployment/pull timer or cron job was found. Two
relevant scheduled units exist: `godokro-backup-daily.timer` / `godokro-backup-weekly.timer`,
running `/opt/go-odyssey/ops/backup/linux/backup.sh {daily|weekly}` (uses `gcloud` config — likely
uploads to Google Cloud Storage; script contents and backup contents were not inspected, per the
"do not open backup contents" rule). This appears to be a **database/data backup mechanism, not an
application code or image backup** — it does not by itself provide an application rollback path.

### Health Verification

| Endpoint | Result |
|---|---|
| `GET /healthz` | 200 |
| `GET /` | 200 |
| `GET /login` | 200 |
| `GET /api/admin/shadow/dashboard` | 401 (confirmed real route — two unrelated nonexistent `/api/admin/*` paths return 404 in a separate control check, not shown here since that check was performed in an earlier audit this session) |

These four checks confirm the app, static assets, and Shadow dashboard's auth gate are all
responding as expected. They are **not sufficient** as a full post-deploy verification — they don't
confirm scheduler health, Postgres connectivity from the app's perspective, or Shadow Judging's
actual event-writing behavior.

### Rollback Capability

- `docker images --no-trunc --digests` shows **exactly one** `go-odyssey-app` image, tagged
  `latest`. **No prior/rollback image is retained** — each build overwrites the `latest` tag with no
  history kept locally.
- No registry digest is associated with the image (`RepoDigests` empty) — it was built locally, not
  pulled.
- The active Compose file uses `build:` context, not `image:` with a pinned tag — there is currently
  no mechanism to "pin" a previous image even if one existed.
- Database backup automation exists (daily/weekly timers) but is separate from any application-code
  rollback mechanism.
- **No evidence was found that application rollback has ever been tested or documented.**

## Current Deployment Model

```
MIXED / MANUAL DEPLOYMENT
```

Grounded in direct evidence: the Docker image is host-built from a local Compose file (not
GitHub-Actions-built, not registry-pulled), but the source that reaches the host arrives via a
manual, Windows-local PowerShell script (`deploy.ps1`) that packages `git ls-files` output from
**whatever local repository happens to be checked out when the script is run** — not a clone or pull
of `origin/master`, and not reproducible from `origin/master` alone since that repository lacks the
majority of the application's tracked files (`sgf_engine/`, `questions.json`, `nginx/`, `assets/`,
`wgo/`, `blog/`, the Dockerfile itself, and the compose file). The host-side git checkout at
`/opt/go-odyssey` is itself disconnected (no remote, corrupted object store) and cannot be used to
verify what was deployed — only direct file hashing can.

## Confirmed Current Procedure

1. **Source**: a local Windows working directory (historically Graph-A-shaped, given `deploy.ps1`,
   `nginx/`, `assets/`, `sgf_engine/`, `questions.json` only exist there) is manually kept
   file-level-synchronized, at least for `app.py`/`shadow_judging.py`/`shadow_dashboard.py`, with
   whatever was last pushed to `origin/master`.
2. **Build (local, pre-transfer)**: `deploy.ps1` runs `git ls-files`/`git rev-parse --short HEAD` in
   that local repo, builds a tar archive of tracked files (excluding some patterns), verifies an
   expected `sw.js` version in the archive.
3. **Transfer**: `scp` uploads the archive to `/tmp` on the Oracle host; the script verifies the
   remote file size.
4. **Extract + build + up**: SSH runs
   `tar xzf ... in /opt/go-odyssey && cp nginx/default-ssl.conf nginx/default.conf && docker compose -f docker-compose.prod.yml build && docker compose -f docker-compose.prod.yml up -d`
   — this overwrites `/opt/go-odyssey` in place and rebuilds/recreates the `app`/`scheduler`
   containers.
5. **Nginx**: explicitly `docker restart go-odyssey-nginx` afterward, to refresh its upstream
   resolution to the recreated `app` container.
6. **Static release**: a separate step publishes a new dated release under
   `/opt/go-odyssey-static/` and atomically repoints a `current` symlink, specifically for
   `sw.js`/`i18n.js`.
7. **Verification**: an official-domain health check, then a check that the publicly-served
   `sw.js` VERSION string matches what was expected from the local source.

No step in this process records a commit SHA, build identifier, or version string anywhere
retrievable from the running container after the fact (confirmed by Audit D — no such env var
exists). The `$shortHead` value `deploy.ps1` captures appears to be used only for local console
output during the deploy run itself, not persisted.

## Security and Secret Boundaries

- `.env` was not read. Private key material was not read or printed. No complete container
  environment dump was performed — only specific, named variables were checked, and only for
  presence, not value, except where a value was itself just a variable-reference placeholder
  (`${VAR:-}`) rather than a secret.
- One literal secret-adjacent value (`POSTGRES_PASSWORD`) was encountered inside
  `docker-compose.prod.yml` during a pre-read grep screen. It has been redacted in this document and
  was not printed to any log this audit produced beyond the single grep match used to detect and
  redact it. This is flagged under Risks and Gaps below, not treated as a finding to fix in this
  Sprint.

## Risks and Gaps

1. **No deterministic, single-source build.** The canonical git repository (`origin/master`) cannot
   by itself reproduce the production deployment — it is missing the Dockerfile, compose file,
   nginx config, `sgf_engine/`, and application data/assets entirely.
2. **The deployment source of truth is an unmanaged local working directory**, not a reviewable git
   ref. Whoever runs `deploy.ps1` next determines what actually ships, based on whatever state their
   local machine happens to be in.
3. **No commit/version identity is stamped into the built image or running container.** Post-hoc
   verification is only possible via direct file hashing, and only for the files the Dockerfile
   happens to `COPY` — this audit's Audit G approach is the *only* current way to answer "what's
   deployed," and it required this Sprint's own SSH access to perform.
4. **No rollback image is retained.** A bad deploy cannot be reverted to a previous image; the only
   recovery path would be re-running the entire manual process against an older local source tree,
   if one still exists and can be identified.
5. **`/opt/go-odyssey`'s own git checkout is corrupted and disconnected from any remote** — it cannot
   itself answer "what commit is this," which is precisely why file-hash verification had to be used
   instead.
6. **A literal (non-`.env`) secret value exists directly in `docker-compose.prod.yml`**
   (`POSTGRES_PASSWORD`) — inconsistent with every other secret in the same file, which is properly
   deferred to `.env`.
7. **PR #49's fix is not yet deployed** — the silent shadow-verdict fallback this Sprint's prior work
   removed from the codebase is still active in the running system.

## Recommended Canonical Procedure

The following is a **proposed target design**, explicitly not yet validated end-to-end and not to be
executed without further verification and owner sign-off:

1. Verified canonical commit — `git rev-parse origin/master` before any build. **PROPOSED — NOT YET
   VALIDATED**: requires first resolving gap #1/#2 (the canonical repo doesn't yet contain everything
   needed to build).
2. A clean, isolated checkout — `git clone` (not a manually-synced working directory) of a single
   repository that contains **all** files the current Dockerfile needs (`Dockerfile`,
   `docker-compose.prod.yml`, `nginx/`, `assets/`, `sgf_engine/`, `questions.json`, etc.), or a
   documented, deterministic assembly step that combines multiple known-good sources. **PROPOSED —
   NOT YET VALIDATED**.
3. Explicit `sgf_engine` inclusion — either vendor it into the same repository as tracked content
   (reversing today's untracked-directory-copy model), or a documented, reproducible fetch step
   pinned to a specific `testing-baseline-test-isolation` commit. **PROPOSED — NOT YET VALIDATED**.
4. Image build — `docker compose -f docker-compose.prod.yml build`, from the clean checkout above,
   not from an ad hoc archive extraction. **PROPOSED — NOT YET VALIDATED**.
5. Immutable image identity — tag the built image with the source commit SHA (e.g.
   `go-odyssey-app:<short-sha>`) instead of only `latest`, and retain at least the previous tag.
   **PROPOSED — NOT YET VALIDATED**.
6. Configuration validation without printing secrets — e.g. `docker compose config --services`
   /`--images` only, never a full `config` dump. **Already demonstrated safe in this audit.**
7. Database migration gate — explicit, reviewed step before `up -d`, run only when schema changes are
   part of the release. **PROPOSED — NOT YET VALIDATED** (no migration tooling was located this
   audit).
8. Container recreation — `docker compose up -d` for `app`/`scheduler`, matching today's behavior.
9. Nginx handling — explicit restart after app recreation, matching today's behavior (`deploy.ps1`
   step 4b), since Compose alone doesn't guarantee nginx re-resolves the new container.
10. Health verification — `/healthz` plus the expanded checks below.
11. Runtime file-hash verification — the exact technique used in this audit (Audit G), run as a
    standard post-deploy step rather than an ad hoc investigation.
12. Rollback target recording — the previous image tag/SHA, recorded *before* the new build starts.
13. Deployment report — a short, standard artifact recording: source commit, image tag, hash
    verification result, health check result, timestamp.
14. Explicit owner `GO DEPLOY` approval, per ADR-0001 — required before step 4 (container recreation)
    in any environment, always.

## Proposed Owner Gates

- `GO DEPLOY` required before any container recreation on the production host.
- A separate, explicit approval required before any change to the deployment source-of-truth model
  itself (e.g., deciding to vendor `sgf_engine` into the app repo, or to make `origin/master` the
  sole deployment source).
- Database migration steps, if introduced, require their own explicit gate, separate from `GO DEPLOY`.

## Proposed Post-Deploy Verification

- `GET /healthz` (existing)
- `GET /` and `GET /login` (existing, already checked this audit)
- `GET /api/admin/shadow/dashboard` → expect 401 unauthenticated (existing, already checked)
- File-hash verification of `app.py`, `shadow_judging.py`, `shadow_dashboard.py` against the source
  commit (this audit's Audit G method)
- `docker ps` confirming all 4 Go-Odyssey containers healthy/running with a fresh creation timestamp
- A single real shadow-judging event observed in `shadow_events.jsonl` after a live rating-test
  answer, confirming the feature is actually emitting events, not just present in code
- Scheduler container log check for a clean startup (no crash-loop)
- Postgres `pg_isready` (already part of its own healthcheck, but worth an explicit post-deploy read)

## Proposed Rollback Procedure

**PROPOSED — NOT YET VALIDATED**, blocked on gap #4 (no retained rollback image today):

1. Before any deploy, tag and retain the current running image under a dated/SHA tag.
2. On rollback need: re-tag the retained previous image as the active one and `docker compose up -d`
   without rebuilding.
3. Database rollback, if ever needed, is a separate, explicitly gated procedure using the existing
   daily/weekly backup mechanism — not covered by this Sprint, and not something application-code
   rollback should assume it can trigger automatically.
4. Until step 1 is actually implemented and exercised at least once, **rollback should be considered
   unavailable**, not merely undocumented.

## Pending Decisions

- Should `origin/master` become the sole deployment source (requiring `sgf_engine/`, `nginx/`,
  `assets/`, `questions.json`, `Dockerfile`, and `docker-compose.prod.yml` to all be vendored into
  it), or should a different, explicitly-designated repository/directory become canonical for
  deployment while `origin/master` remains the canonical *application code* review target?
- How should `sgf_engine` be sourced deterministically — vendored as tracked content, or fetched from
  `testing-baseline-test-isolation` at build time with a pinned commit?
- Should the literal `POSTGRES_PASSWORD` in `docker-compose.prod.yml` be moved to `.env` like every
  other secret in the same file? (Flagged here; not a decision this Sprint makes.)
- Who owns running `deploy.ps1`, and from which machine/checkout, going forward?
- Is the `/opt/go-odyssey` host git checkout worth repairing (re-adding a remote, fixing the object
  store), or should it be abandoned in favor of a clean, reproducible source model?

## References

- `docker-compose.prod.yml`, `Dockerfile`, `deploy.ps1` — read directly from `/opt/go-odyssey` on the
  production host via SSH, screened for secrets before any content was recorded
- PR #47 (`4214820d1`) — last commit whose `shadow_judging.py` matches what's currently deployed
- PR #49 (`8c077244e`) — merged, confirmed **not** deployed
- PR #50 (`4ea3f63e6`) — merged, docs-only, not applicable to the running container by Dockerfile
  design
- ADR-0001 — canonical repository and deployment governance (this Sprint's predecessor)
