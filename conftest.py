"""Canonical pytest collection boundary for the Go Odyssey repository.

The repository root may contain retained registered worktrees and other
development checkouts.  They are preservation material, not test roots.  The
canonical test universe is the repository's own ``tests`` directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


_REPOSITORY_ROOT = Path(__file__).resolve().parent
_CANONICAL_TEST_ROOT = _REPOSITORY_ROOT / "tests"


def pytest_ignore_collect(collection_path: Path, config: Any) -> bool | None:
    """Keep collection inside this checkout's canonical ``tests`` root.

    ``pytest.ini:testpaths`` handles the normal no-argument invocation.  This
    hook is the defensive boundary for explicit ``pytest .`` or other broad
    invocations: root-level retained worktrees and unrelated nested checkouts
    are ignored without being deleted, moved, or pruned.
    """

    path = Path(collection_path).resolve()
    if path == _REPOSITORY_ROOT:
        return False
    try:
        path.relative_to(_CANONICAL_TEST_ROOT)
    except ValueError:
        return True
    return False
