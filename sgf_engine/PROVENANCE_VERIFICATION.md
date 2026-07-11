# SGF Engine Provenance — Verified and Vendored

Status: **RESOLVED**. This file supersedes and replaces the prior
`sgf_engine/PROVENANCE_MISMATCH.md`, which incorrectly concluded that
Production, Graph A, and the canonical development source contained
different engine logic. That conclusion was wrong; the correction and
evidence are recorded below.

## What the original mismatch actually was

DEPLOY-GOV-2's original comparison (SGF-PROV-1 read-only audit, 2026-07-11)
found that raw SHA-256 hashes for `sgf_engine`'s Python files differed
across three trees: the production container/host, the Graph A recovery
branch (`recovered-production-tip-20260711`), and the recorded source commit
on `testing-baseline-test-isolation`. That raw-hash mismatch was caused
entirely by **inconsistent line-ending representation (CRLF vs LF)** across
the three trees — not by any difference in code logic.

## Verified finding: the 16 shared files are semantically identical

After normalizing line endings (CRLF → LF) on all three trees, every one of
the 16 Python files present in all three trees is **byte-identical**:

- Production container tree == Production host build context (byte-identical
  even without normalization — confirmed via direct `sha256sum` inside the
  running container and on the host filesystem).
- Production (normalized) == Graph A (normalized) == source commit
  `d729645c0ae267be6d89a5b49c007bc64284bbcc` (normalized) for all 16 shared
  files. Composite normalized fingerprint: `03d46ab3a1908cc443db4c2af9ceef1edc043ba45cb27097f0a310aedb31f611`
  — identical across all three trees.

No content/logic divergence exists anywhere in the 16 shared files.

## Verified finding: identical behavior under test

The same 109-test engine corpus (`test_tree.py`, `test_matcher.py`,
`test_autoreply.py`, `test_coord_utils.py`, `test_parser_errors.py`,
`test_engine.py`, `test_gold_fixtures.py`, drawn from the source commit,
including the SGF gold fixtures) was run against isolated copies of all
three trees, with no production state or database touched:

| Tree | Result |
|---|---|
| Source commit | 109/109 passed |
| Graph A | 109/109 passed |
| Production | 109/109 passed |

## `sgf_engine/inventory/` is source-only offline tooling

The recorded source commit contains an `inventory/` subpackage
(`inventory/__init__.py`, `inventory/sgf_inventory.py`, a "read-only SGF
inventory and known quality issue detection" tool) that is absent from both
the production and Graph A trees. This is **not part of the production
verdict/judging path**: `app.py` and `shadow_judging.py` import only
`sgf_engine.parser.sgf_parser`, `sgf_engine.core.tree`,
`sgf_engine.core.matcher`, `sgf_engine.core.autoreply`, and
`sgf_engine.core.coord_utils` — confirmed both by direct source inspection
and by `tests/test_shadow_fail_observable_e24a.py`'s fake-package stub,
which independently declares this same 5-module surface as the canonical
runtime interface. `inventory/` is consumed only by
`tests/sgf_engine/test_sgf_inventory_known_quality_issues.py` and
`tools/corpus_quality_audit.py` (an offline analysis tool), neither of which
is part of the deployed application.

## Canonical vendored source

This repository now vendors `sgf_engine/` directly from:

```
source_repo:   https://github.com/beatleswu/beatleswu.github.io
source_branch: testing-baseline-test-isolation
source_commit: d729645c0ae267be6d89a5b49c007bc64284bbcc
```

See `sgf_engine/VENDORED_FROM.txt` for the full provenance record. The
vendored tree was extracted directly from the Git object at this commit (not
copied from Production or Graph A) and includes the complete tracked source
tree, including `inventory/`. All text files are normalized to **LF** line
endings (enforced going forward by `.gitattributes`); this is a
line-ending-representation choice only — the vendored content is
byte-identical (post-normalization) to the source commit, to Production, and
to Graph A, as established above.

## Commit provenance for the two files that appeared "special"

`sgf_engine/core/tree.py` and `sgf_engine/parser/sgf_parser.py` were the two
files whose raw hashes diverged from Graph A's copy specifically (both
matched Production's raw hash instead, before normalization). This traces to
a real, reviewed commit: `d729645c0` itself — *"feat: sgf pass decoding and
parse diagnostics (parser-only) (#40)"* — which touches exactly these two
engine files (plus four test files) and nothing else in `sgf_engine/`. Graph
A re-vendored these two files in its own commit `acd047398` ("chore:
re-vendor engine d729645 + tolerant corpus audit", 2026-07-05), which is
reachable only from Graph A branches. No unpushed or unreviewed logic exists
in Production or Graph A relative to this source commit — every difference
found was cosmetic.
