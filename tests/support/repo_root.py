"""Semantic checkout-root discovery for tests that need repository data."""

from __future__ import annotations

import subprocess
from pathlib import Path


def find_repo_root(start: Path | str | None = None) -> Path:
    """Return the Git checkout root containing ``start``.

    Git is the source of truth, so this works for ordinary checkouts and
    registered worktrees whose ``.git`` entry is a file.  The ancestor-marker
    fallback keeps the helper useful in a partially materialised test
    environment without introducing a fixed ``parents[N]`` assumption.
    """

    probe = Path(start or __file__).expanduser().resolve()
    if probe.is_file():
        probe = probe.parent

    try:
        result = subprocess.run(
            ["git", "-C", str(probe), "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        result = None

    if result is not None and result.returncode == 0:
        reported = result.stdout.strip()
        if reported:
            root = Path(reported).expanduser().resolve()
            if root.is_dir():
                return root

    for candidate in (probe, *probe.parents):
        if (candidate / ".git").exists():
            return candidate

    raise RuntimeError(f"Unable to discover a Git checkout root from {probe}")
