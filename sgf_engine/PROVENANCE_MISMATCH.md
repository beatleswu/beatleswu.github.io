# SGF Engine Vendoring — BLOCKED — PROVENANCE MISMATCH

Status: **BLOCKED**. No `sgf_engine/` code is vendored into this repository by
this Sprint (DEPLOY-GOV-2). This file documents the evidence; it deliberately
contains no engine implementation code.

## Recorded provenance claim

Both the production host (`/opt/go-odyssey/sgf_engine/VENDORED_FROM.txt`) and
the Graph A recovery branch (`recovered-production-tip-20260711:sgf_engine/VENDORED_FROM.txt`)
record the same claim:

```
source_repo: https://github.com/beatleswu/beatleswu.github.io
source_branch: testing-baseline-test-isolation
source_commit: d729645
vendored_date: 2026-07-05
rule: never edit engine code here; re-vendor from the testing repo.
```

## Full source commit resolution

The abbreviated `d729645` resolves unambiguously to a single commit reachable
from `origin/testing-baseline-test-isolation`:

```
d729645c0ae267be6d89a5b49c007bc64284bbcc
feat: sgf pass decoding and parse diagnostics (parser-only) (#40)
```

Confirmed via `git merge-base --is-ancestor d729645c0 origin/testing-baseline-test-isolation`
(ancestor: yes).

## Three-way comparison

Three candidate trees were compared by SHA-256, file by file:

1. **Production container** (`docker exec go-odyssey-app find /app/sgf_engine -name '*.py'`)
2. **Production host build context** (`/opt/go-odyssey/sgf_engine`, matches container exactly)
3. **Graph A vendored copy** (`recovered-production-tip-20260711:sgf_engine`)
4. **Recorded source commit** (`d729645c0ae267be6d89a5b49c007bc64284bbcc:sgf_engine`)

### File inventory mismatch

The source commit contains 18 files including an `inventory/` subpackage:

```
sgf_engine/inventory/__init__.py
sgf_engine/inventory/sgf_inventory.py
```

**Neither production nor Graph A contains `sgf_engine/inventory/` at all.**
Both are missing these two files entirely relative to the recorded source
commit.

### Content hash mismatch

Of the 16 files present in both production and the source commit:

| File | Production matches source? | Graph A matches source? |
|---|---|---|
| `__init__.py` | No | Yes |
| `core/__init__.py` | No | Yes |
| `core/autoreply.py` | No | Yes |
| `core/coord_utils.py` | No | Yes |
| `core/matcher.py` | No | Yes |
| `core/tree.py` | **Yes** | No |
| `engine/__init__.py` | No | Yes |
| `engine/engine.py` | No | Yes |
| `override/__init__.py` | No | Yes |
| `override/override_identity.py` | No | Yes |
| `override/override_loader.py` | No | Yes |
| `override/override_loader_integration.py` | No | Yes |
| `override/override_runtime.py` | No | Yes |
| `override/override_schema.py` | No | Yes |
| `parser/__init__.py` | No | Yes |
| `parser/sgf_parser.py` | **Yes** | No |

Production matches the recorded source commit on exactly 2 of 16 present
files (`core/tree.py`, `parser/sgf_parser.py`). Graph A matches the recorded
source commit on the other 14, and mismatches on precisely those same 2
files. Production and Graph A also do not match each other on any of the 16
files.

**No two of the three trees (production, Graph A, recorded source commit) are
identical.** There is no exact match anywhere, and therefore no unambiguous
"correct" copy to vendor.

## Conclusion

Per this Sprint's governing instructions: *"If not exact: Stop the vendoring
portion and return: BLOCKED — SGF ENGINE PROVENANCE MISMATCH. Do not silently
choose one copy."*

This Sprint does not vendor any `sgf_engine/` implementation code. The
canonical Dockerfile continues to reference `COPY sgf_engine ./sgf_engine` as
a build input (preserving existing production build behavior), but that
directory remains **untracked** in `origin/master`, exactly as documented in
ADR-0001. `deploy/build-manifest.json` records this file's path as the
required follow-up.

## Recommended next step

A dedicated Sprint should:

1. Determine why `VENDORED_FROM.txt`'s claim doesn't match either running
   copy — most likely candidates: local edits made directly against the
   deployed/Graph-A copies after the 2026-07-05 vendor date (prohibited by
   the engine's own stated rule), or the `VENDORED_FROM.txt` metadata itself
   being stale/never updated after a later re-vendor.
2. Establish, with the owner, which tree is actually intended to be
   authoritative going forward.
3. Only then vendor a byte-for-byte copy of the agreed authoritative source
   into this repository with a corrected, verified `VENDORED_FROM.txt`.

No SGF Engine implementation code was edited, copied, or invented by this
Sprint.
