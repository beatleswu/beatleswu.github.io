# Canonical pytest collection procedure

This is the authoritative broad Python test procedure for the L6 quality
signal.

## Working root

Run from the active Go Odyssey checkout root, for example:

```text
D:\go-website
C:\go-website
```

The checkout may also be a deeper registered Git worktree. The tests discover
their repository root with `git rev-parse --show-toplevel`; they do not use a
fixed `parents[N]` path assumption.

For a canonical L6 review, verify the release baseline before collecting:

```powershell
git ls-remote origin refs/heads/master
git rev-parse HEAD
```

The current canonical baseline is
`3dc517bfbf789da378f971b092980fb53e7a5e2f`.

## Canonical command

Use:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONPATH = (Get-Location).Path
python -B -m pytest --collect-only -q -p no:cacheprovider
python -B -m pytest -q -p no:cacheprovider
```

The first command is the collection gate. The second is the broad test gate.
Run both from the checkout root and preserve the complete output for the
review record.

## Collection boundary

`pytest.ini` sets `testpaths = tests`, so the no-argument command collects only
the active checkout's `tests/` directory. The root `conftest.py` provides a
defensive boundary for explicit broad invocations and ignores paths outside
that canonical test root. Common virtual environments, build outputs, and
worktree-named directories are also listed in `norecursedirs`.

This is an exclusion boundary, not cleanup authority: retained worktrees are
not deleted, moved, pruned, or otherwise modified.

## Environment assumptions

- The command is run at the checkout root.
- Repository imports resolve through `PYTHONPATH`.
- `PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider` keep this read-only
  collection check from creating Python bytecode or a pytest cache.
- Tests that require the preserved `C:\go-website` historical repository or
  its frozen corpus skip with an explicit reason when those inputs are absent.

## Genuine failure triage

1. Confirm the reported path is under the active checkout's `tests/` root.
2. If the path is under a retained or nested checkout, it is collection
   contamination and must be fixed at the boundary; do not delete the tree.
3. For paths under the canonical `tests/` root, reproduce with the individual
   file and classify the error as a real collection or test failure.
4. Report every remaining error; skips are not passes and must retain their
   explicit reason.
