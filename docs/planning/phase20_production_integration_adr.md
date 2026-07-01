# Phase 20: Production Integration ADR

## Status

Accepted as Phase 20 owner decision baseline. Facts verified 2026-07-02 by direct
read-only inspection of the production checkout.

## Context: Verified Facts

- The production codebase is the local folder `D:\go-website` on the owner's machine.
- It is a local-only git repository with NO remote configured. Branch
  `optimize-pets-map-images`, last commit 2026-06-17.
- The application is a single-file Flask monolith (`app.py`, ~676 KB) using
  Flask-SocketIO in threading mode.
- Deployment: `deploy.ps1` creates a tar archive (excluding `.env`, `.git`,
  `SGF*`, `docs`, local DB files, KataGo binaries), uploads it to an Oracle
  Cloud A1 VM at `/opt/go-odyssey`, and restarts via docker compose. Server
  address and credentials live only in the local `deploy.ps1` and MUST NOT be
  recorded in this repository.
- Production database is PostgreSQL. Local development uses a local postgres
  `go_odyssey` database.
- `D:\go-website` does NOT contain a `sgf_engine` directory. The engine is not
  yet integrated.
- The sgf_engine code in this testing repository has ZERO divergence from the
  copy in `C:\go-website`: all commits since `dbc07a5` touch only `tests/`.
  This testing repository holds the canonical engine source.
- Known answer-judging entry routes in production `app.py` (shadow hook
  candidates): `/api/daily-challenge/submit`, `/api/challenges/friend/<id>/answer`,
  `/api/rating_test/answer`. A complete enumeration is required in the future
  hook task.
- Stale copies exist and must not be used: `D:\go website` (folder name with a
  space; older copy) and the stale `run_preview.bat` reference in `C:\go-website`.

## Decision

1. sgf_engine enters production as a VENDORED DIRECTORY COPY: the `sgf_engine/`
   package is copied one-way from this testing repository (at a pinned commit)
   into `D:\go-website\sgf_engine\`.
2. A provenance file `sgf_engine/VENDORED_FROM.txt` in the production codebase
   must record: source repository, source branch, source commit hash, sync date.
3. Engine code is NEVER edited directly in the production codebase. All engine
   changes land in this testing repository first, pass its test suite, then
   re-vendor with an updated provenance file.
4. `puzzle_variation_overrides.json` follows the same one-way flow: this
   repository is the editing source of truth; production receives copies.

## Prerequisite Before Any Hook Work (Priority Zero)

- `D:\go-website` must get a PRIVATE remote backup (private GitHub repository
  or equivalent) before any integration work begins. It currently has no
  off-machine copy of its git history, and the machine was recently reinstalled.
- Before the first push, verify `.gitignore` excludes `.env` and all secret
  files. The `.env` file contains live third-party API tokens.

## Deployment Considerations

- The tar exclude pattern `SGF*` is uppercase; the vendored directory
  `sgf_engine` is lowercase. The future hook task MUST verify case-sensitivity
  of the tar exclude handling so the engine directory is actually shipped.
- The docker image and compose configuration must include the vendored
  `sgf_engine/` directory and the override JSON.
- No new pip dependencies are required by the engine (stdlib only).

## Minimal Shadow Hook Principle (conceptual, not implemented here)

1. Run current production judging exactly as today.
2. Preserve the current production result as the user-facing result.
3. Try to run sgf_engine shadow judgement.
4. Convert the legacy-vs-shadow comparison into a Phase 19 shadow event.
5. If shadow event creation fails for any reason, drop shadow evidence safely.
6. Return the original production result unchanged.

## Required Conditions Before Hook Implementation

- Private remote backup of the production codebase exists (Priority Zero above).
- Production judging entrypoints fully enumerated.
- Rollback plan documented (feature flag default-off; removal = delete hook call).
- No-user-impact guarantee documented (except-all around the entire shadow path).
- Phase 19 shadow contract available (merged as PR #38).
- Owner explicitly authorizes the hook implementation task.

## Blocked Conditions

- Owner authorization missing.
- Hook would change any user-facing result.
- Hook would require DB schema before shadow data is proven safe-to-drop
  (first iteration logs to JSONL file, not DB).
- Hook would enable GF-003, activate B[sd]/T16, modify SGF bytes, READY_IDS,
  puzzle_variation_overrides.json, or judging semantics.

## GF-003 / Override Safety Boundary

- GF-003 remains disabled. B[sd]/T16 remains candidate-only in GF-003 context
  only. B[sf]/T14 remains the canonical GF-003 answer. No runtime or production
  override is added. No judging semantics change.

## Rejected Alternatives

- pip package: requires index/versioning infrastructure the deployment flow
  does not have; no benefit over a provenance-pinned vendored copy.
- git submodule: the production repository has no remote, and the tar-based
  deploy does not resolve submodules.
- Reimplementing judging inside app.py: duplicates tested code and forks truth.
- Merging the repositories: this testing repository is public; the production
  codebase must not become public.

## Open Questions (to resolve in the hook task)

- Which override JSON path production will read at runtime.
- Full enumeration of judging entrypoints beyond the three known routes.
