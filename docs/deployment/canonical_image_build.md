# Canonical Production Image Build

Status: build-source reconstruction complete for tracked application code and
SGF Engine; large binary/data assets remain open (see Limitations).
Sprint: DEPLOY-GOV-2. This document does not claim deployment has been
validated — see [canonical_production_deployment_audit.md](canonical_production_deployment_audit.md)
for deployment-mechanism status, which this Sprint does not change.

> **DEPLOY-GOV-2A status note (2026-07-11):** The SGF Engine "provenance
> mismatch" described in Phase C below and in the original
> `sgf_engine/PROVENANCE_MISMATCH.md` has been resolved — it was caused
> entirely by CRLF/LF line-ending inconsistency across trees, not by any
> logic divergence. A follow-up read-only audit (SGF-PROV-1) found all 16
> shared engine files byte-identical across Production, Graph A, and the
> source commit after normalization, and all three passed the same 109-test
> corpus. `sgf_engine/` is now vendored from the verified source commit
> `d729645c0ae267be6d89a5b49c007bc64284bbcc` with LF line endings; see
> `sgf_engine/PROVENANCE_VERIFICATION.md` and `sgf_engine/VENDORED_FROM.txt`.
> The rest of this document (Phase C section, Limitations item 1) reflects
> the original, now-superseded finding and is retained for historical
> record of what DEPLOY-GOV-2 actually found at the time.

## Objective

Reconstruct, inside canonical `origin/master`, enough tracked material to (1)
build the application image, (2) identify the exact Git commit and SGF Engine
provenance inside the image, (3) validate Compose configuration without
secrets, (4) produce an immutable image tag, (5) retain a rollback identity,
(6) avoid depending on Graph A working-tree clutter or production-host
residue.

## Phase A — Build Input Inventory

Classification method: every candidate path was checked against direct
production evidence — the running container's file tree (`docker exec
go-odyssey-app find ...`), the production host's build context
(`/opt/go-odyssey`), SHA-256 file hashes, and (for Python modules) a live
import-graph trace from `app.py`.

| Path | Required at runtime | Current source | Canonical treatment |
|---|---|---|---|
| `app.py` | Yes | Already tracked, hash-verified identical to production | Track (no change) |
| `shadow_judging.py` | Yes | Already tracked; production runs the **pre-E2.4A** hash (PR #49 not deployed) | Track (no change; deployment gap documented separately) |
| `shadow_dashboard.py` | Yes | Already tracked, hash-verified identical | Track (no change) |
| `scheduler.py` | Yes | Production host, hash captured, imports only `app` | Track (this Sprint) |
| `katago_explain.py` | Yes | Production host; imported unconditionally by `app.py:29` | Track (this Sprint) |
| `explain_overrides.py` | Yes | Production host; imported by `app.py:30` | Track (this Sprint) |
| `grimoire_api.py` | Yes | Production host; imported by `app.py:31` | Track (this Sprint) |
| `question_taxonomy.py` | Yes | Production host; imported by `app.py:32` | Track (this Sprint) |
| `monster_taxonomy.py` | Yes | Production host; imported by `app.py:33` | Track (this Sprint) |
| `chapter_i18n.py` | Yes | Production host; imported by `app.py:34` | Track (this Sprint) |
| `backend_i18n.py` | Yes | Production host; imported by `app.py:35` | Track (this Sprint) |
| `sgf_engine/` (parser/engine/override/core) | Yes | Three-way mismatch: production, Graph A, and the recorded source commit are all different from each other | **BLOCKED — do not vendor** (see `sgf_engine/PROVENANCE_MISMATCH.md`) |
| `tools/community_leaderboard_rewards_*.py` (4 files) | Yes (Dockerfile `COPY`s them explicitly) | Production host, secret-screened | Track (this Sprint) |
| `requirements.txt` | Yes | Production host, differs from stale Graph A copy; used production version | Track (this Sprint) |
| `entrypoint.sh` | Yes | Production host; hash-identical to Graph A | Track (this Sprint) |
| `Dockerfile` | Yes | Production host; hash-identical to Graph A (LF-normalized) | Track (this Sprint), with build-arg/label additions |
| `docker-compose.prod.yml` | Yes | Production host, secret-screened; one literal (`POSTGRES_PASSWORD=go`) redacted to an env var | Track (this Sprint), secrets removed |
| `nginx/default.conf` | Yes | Production host | Track (this Sprint) |
| `assets/` (757MB) | Yes (build-time COPY) | Production host only | **PENDING** — out of scope this Sprint, see Limitations |
| `questions.json` (58MB) | Yes (build-time COPY) | Production host only | **PENDING** — out of scope this Sprint |
| `srs.db` (1.5MB), `go_learning.db` (124KB) | Yes (build-time seed, then persisted via `entrypoint.sh`) | Production host only | **PENDING** — out of scope this Sprint |
| `wgo/`, `blog/`, `docs/testing/` (13MB), `shorts/` | Yes (build-time COPY) | Production host only | **PENDING** — out of scope this Sprint |
| `robots.txt`, `sitemap.xml`, `og-image.jpg` | Yes (build-time COPY) | Production host only | **PENDING** — out of scope this Sprint |
| Remaining ~137 root `*.py` files | **No** (not in `app.py`'s or `scheduler.py`'s import graph, verified by trace) | Production host | Excluded — flagged as a wildcard-COPY reproducibility risk, not vendored |
| Remaining root `*.html/*.js/*.json/*.png` (68 files, 169MB) | Unverified — likely a mix of real static assets and debug artifacts | Production host | **PENDING** — needs curation before vendoring, not vendored this Sprint |
| `katago_cache.db` | No (bind-mounted read-only by Compose, never `COPY`'d) | Production host | Not a build input — excluded correctly |
| `/opt/go-odyssey-static` | No (bind-mounted, separate static-release flow) | Production host | Not a build input — see Phase E below |

## Phase B — Dockerfile

The production Dockerfile was recovered directly from `/opt/go-odyssey/Dockerfile`
on the production host via SSH. It is byte-identical (after LF normalization)
to the copy on the Graph A recovery branch (`recovered-production-tip-20260711:Dockerfile`),
giving two independent sources agreeing on content.

Added, without changing existing `COPY`/`RUN` behavior:

- `ARG APP_GIT_SHA`, `ARG APP_BUILD_DATE`, `ARG SGF_ENGINE_SOURCE_COMMIT`
- `LABEL org.opencontainers.image.revision`, `.created`, `.source`, and a
  custom `com.godokoro.sgf-engine.source-commit` label
- The same three values are also exported as container `ENV` vars, closing
  the gap the prior audit found (*"No `APP_VERSION`, `GIT_SHA`... is present
  in the container"*) with the smallest possible runtime-behavior change.

## Phase C — SGF Engine Vendoring: BLOCKED

See `sgf_engine/PROVENANCE_MISMATCH.md` for full evidence. Summary: the
recorded source commit (`d729645c0ae267be6d89a5b49c007bc64284bbcc` on
`testing-baseline-test-isolation`) contains an `inventory/` subpackage that
neither production nor the Graph A vendored copy have at all, and of the 16
files present in all three trees, production matches the source commit on 2,
Graph A matches on the other 14 (and mismatches on precisely the same 2),
and production and Graph A never match each other. No exact match exists
anywhere. Per this Sprint's instructions, the vendoring portion stops here;
no `sgf_engine/` implementation code is tracked by this Sprint.

## Phase D — Compose Configuration

`docker-compose.prod.yml` was recovered directly from the production host and
secret-screened before being read. The only literal (non-`${VAR}`) secret
found was `POSTGRES_PASSWORD=go` — every other secret was already correctly
deferred to `${VAR:-}`. The canonical version:

- replaces the literal `POSTGRES_PASSWORD=go` with `${POSTGRES_PASSWORD:?...}`
  (fails fast if unset, rather than silently defaulting to a weak value)
- replaces `image: go-odyssey-app` implicit `build:` context with
  `image: ${GO_ODYSSEY_IMAGE:-go-odyssey-app:latest}` for `app`/`scheduler`,
  so a real deployment sets `GO_ODYSSEY_IMAGE=go-odyssey-app:<git-sha>` and
  `latest` is never the deployment record
- preserves every volume, health check, restart policy, and dependency
  relationship byte-for-byte otherwise

`docker-compose.build.yml` is new: a minimal build-only overlay so
`scripts/build-production-image.ps1` can build with explicit `ARG`s without
requiring the full production runtime environment (Postgres, nginx, real
secrets) to exist locally.

`.env.production.example` documents every required variable name with a
fake placeholder value; it is not consumed by anything, it exists purely as
operator documentation.

## Phase E — Nginx and Static Assets

`nginx/default.conf` was recovered directly from the production host and is
tracked as-is (no secrets, no certificate material — it references
`/etc/letsencrypt` by path only, mounted read-only at runtime). No TLS
private keys or certificates are tracked.

Static asset publishing (`sw.js`/`i18n.js` under `/opt/go-odyssey-static`,
atomically repointed via a `current` symlink) is a **separate system from the
app image build** — the Compose file bind-mounts it read-only, and the
Dockerfile's own `*.html/*.js/*.json/*.png` wildcard COPY is a distinct,
overlapping mechanism whose exact intended scope is unverified (see Phase A).

```
PENDING — STATIC RELEASE TOOLING
```

This Sprint does not attempt to reconstruct the static-release script or
determine whether it should be merged with or kept separate from the app
image build. That decision needs its own Sprint.

## Phase F — Build Manifest

See `deploy/build-manifest.json`. It records: the Dockerfile/Compose paths,
required build args, the immutable tag format (`go-odyssey-app:<short-git-sha>`,
never bare `latest`), required service list, required secret **variable
names** (no values), the full tracked-vs-pending build-input classification
from Phase A, and post-build verification file paths. No secret values are
present anywhere in this file (verified by `tests/deployment/test_build_manifest.py`).

## Phase G — Build Tooling

`scripts/build-production-image.ps1`:

- requires a clean `git status` (or explicit `-SkipCleanCheck` for local
  iteration only)
- resolves and verifies the target commit has a merge-base with
  `origin/master`
- verifies every required tracked build input listed in this document is
  present in the checkout, and separately reports (without failing) which
  Phase-A "PENDING — not yet vendored" inputs are absent, so a build failure
  at a specific `COPY` line is expected and diagnosable rather than
  mysterious
- derives an immutable tag from the resolved Git SHA
  (`go-odyssey-app:<short-sha>`)
- passes `APP_GIT_SHA`, `APP_BUILD_DATE`, `SGF_ENGINE_SOURCE_COMMIT` as build
  args
- never runs `docker compose up`, `docker push`, `docker restart`,
  `docker exec`, `ssh`, `scp`, or any remote/interactive command
- reports `BUILD NOT EXECUTED — LOCAL DOCKER ENGINE UNAVAILABLE` and exits 0
  (not a failure) if no local Docker engine is reachable

## Phase H — Validation Performed This Sprint

| Check | Result |
|---|---|
| `python -X utf8 -m pytest -q tests/deployment/` | 52 passed |
| `python -m py_compile app.py shadow_judging.py` | success |
| `python -m py_compile` on all 7 newly-vendored local modules + `scheduler.py` | success |
| Existing Shadow test suite (`tests/test_shadow_*.py`) | 24 passed; 3 errors in `test_shadow_dashboard_backend.py` and 2 full collection failures in `test_shadow_envelope_v1.py`/`test_shadow_runtime_e24.py` — **all five failures trace to the single documented `sgf_engine.parser` BLOCKED gap** (`app.py:36`), not to any other missing dependency. This is a clean confirmation that Phase A's import-graph tracing was complete: once the sgf_engine gap is closed, nothing else is missing. |
| Local Docker build | **BUILD NOT EXECUTED** — no local Docker engine reachable (`docker version` fails to connect to the daemon); even if the daemon were started, the build would fail immediately at `COPY assets/boards` (and similar) since those Phase-A "PENDING" paths are intentionally not vendored this Sprint. Starting Docker Desktop was not requested since it would not change this outcome. |

## Limitations — What Remains Outside This Image Build

1. **SGF Engine is not vendored.** BLOCKED on an unresolved three-way
   provenance mismatch. A Docker build from this branch will fail at
   `COPY sgf_engine ./sgf_engine`.
2. **Large binary/data assets are not vendored**: `assets/` (757MB),
   `questions.json` (58MB), `wgo/`, `blog/`, `docs/testing/` (13MB),
   `shorts/`, `srs.db`, `go_learning.db`, `robots.txt`/`sitemap.xml`/`og-image.jpg`.
   A Docker build from this branch will fail at the corresponding `COPY`
   lines. These require a dedicated Sprint to decide a vendoring strategy
   (tracked in Git, Git LFS, or a separate object-storage fetch step) — this
   Sprint deliberately does not invent one, per "use the smallest
   evidence-supported set."
3. **The root wildcard `COPY *.py ./` and `COPY *.html *.js *.json *.png ./`
   lines remain unnarrowed.** They are preserved as-is (existing production
   behavior), but Phase A's import-graph trace shows only 11 of ~148 root
   `.py` files are actually required at runtime — the rest ride along as
   host residue purely because of the wildcard. Narrowing this is a
   reproducibility improvement for a future Sprint, not attempted here to
   avoid changing production behavior.
4. **Static asset publishing** (`/opt/go-odyssey-static`, the `sw.js`/`i18n.js`
   atomic-release flow) is out of scope — marked `PENDING — STATIC RELEASE
   TOOLING`.
5. **No local Docker build was executed or verified.**

## Why This Replaces Reliance on the Mixed Local Deployment Directory

Before this Sprint, `origin/master` contained none of `Dockerfile`,
`docker-compose.prod.yml`, `nginx/`, `requirements.txt`, `entrypoint.sh`, or
any of the local Python modules `app.py` actually imports beyond the three
Shadow-judging files. Every one of those either lived only in the manually-
synced `/opt/go-odyssey` directory (per the prior audit, itself a disconnected,
un-versioned git checkout) or on the historical, non-canonical Graph A
branches. A clean `git clone` of `origin/master` could not answer "what would
this build into" at all. It now can, for every file this Sprint tracked —
and for every file it deliberately didn't, `deploy/build-manifest.json` says
exactly why, sourced from direct production evidence rather than inference.
