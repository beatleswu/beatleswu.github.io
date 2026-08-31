"""Shared ART003 admission-scope resolution for candidate and master tests.

ART003 scope checks run in two different repository states:

* on a candidate line, ``candidate_base..HEAD`` is the proposed admission;
* after admission, ``canonical_tip^1..canonical_tip`` is the immutable
  historical admission, even when ``HEAD`` is already ``origin/master``.

The second form is deliberately commit-specific.  Comparing a canonical
checkout with ``origin/master`` would produce an empty diff and would turn an
exact-path assertion into a vacuous check.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# These are the commits whose trees contain the exact admitted scope used by
# the current B02-B11 contracts.  B02-B09 share the B09 reconciliation commit
# because it is the last cumulative ART003 scope update for those tests.
ART003_B09_SCOPE_TIP = "9998eb9eb5fac02e1cfd17ada4cbdf6d4d6249c1"
ART003_B10_SCOPE_TIP = "6228de020dea513fe33b974a37444537738c0baa"
ART003_B11_SCOPE_TIP = "b3d37e22e7471d0429d882c43c3ee16049c68ea1"


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _resolve(ref: str) -> str:
    return _git("rev-parse", ref)


def _is_ancestor(ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def is_canonical_line(
    *, canonical_tip: str, canonical_master: str = "origin/master", head_ref: str = "HEAD"
) -> bool:
    """Return whether ``head_ref`` is on the fetched canonical line.

    ``canonical_tip`` must itself already be reachable from the canonical
    master ref.  This prevents a stale or unrelated commit from being treated
    as the canonical admission window.
    """

    return _is_ancestor(canonical_tip, canonical_master) and _is_ancestor(
        canonical_master, head_ref
    )


def admission_base(
    *,
    canonical_tip: str,
    candidate_base: str,
    canonical_master: str = "origin/master",
    head_ref: str = "HEAD",
) -> str:
    """Resolve the non-empty base for the current admission scope.

    On canonical history, the base is the first parent of the recorded
    admission commit.  On a candidate line, the caller-provided base is used.
    A candidate base equal to its tip is rejected so a scope test cannot pass
    merely because the comparison is empty.
    """

    if is_canonical_line(
        canonical_tip=canonical_tip, canonical_master=canonical_master, head_ref=head_ref
    ):
        return _git("rev-parse", f"{canonical_tip}^1")

    if not _is_ancestor(candidate_base, head_ref):
        raise AssertionError(
            f"candidate base {candidate_base} is not an ancestor of {head_ref}"
        )
    if _resolve(candidate_base) == _resolve(head_ref):
        raise AssertionError("candidate admission base equals HEAD; refusing an empty scope")
    return candidate_base


def admission_tip(
    *,
    canonical_tip: str,
    candidate_base: str,
    canonical_master: str = "origin/master",
    head_ref: str = "HEAD",
) -> str:
    """Resolve the endpoint paired with :func:`admission_base`."""

    if is_canonical_line(
        canonical_tip=canonical_tip, canonical_master=canonical_master, head_ref=head_ref
    ):
        return canonical_tip
    # Resolve the ref before returning it so malformed candidate refs fail at
    # the boundary rather than silently producing an incomplete diff.
    _resolve(head_ref)
    return head_ref


def _paths(*args: str) -> set[str]:
    return {line.replace("\\", "/") for line in _git(*args).splitlines() if line}


def changed_paths(
    *,
    canonical_tip: str,
    candidate_base: str,
    canonical_master: str = "origin/master",
    head_ref: str = "HEAD",
    include_worktree: bool = True,
) -> set[str]:
    """Return committed plus pending paths in the resolved admission scope."""

    base = admission_base(
        canonical_tip=canonical_tip,
        candidate_base=candidate_base,
        canonical_master=canonical_master,
        head_ref=head_ref,
    )
    tip = admission_tip(
        canonical_tip=canonical_tip,
        candidate_base=candidate_base,
        canonical_master=canonical_master,
        head_ref=head_ref,
    )
    changed = _paths("diff", "--name-only", base, tip)

    # Pending changes belong to the candidate checkout only.  Canonical tests
    # still see them when they run in a dirty checkout, preserving the exact
    # firewall instead of hiding local mutations behind historical scope.
    if include_worktree and head_ref == "HEAD":
        changed.update(_paths("diff", "--name-only"))
        changed.update(_paths("diff", "--cached", "--name-only"))
        changed.update(_paths("ls-files", "--others", "--exclude-standard"))
    return changed
