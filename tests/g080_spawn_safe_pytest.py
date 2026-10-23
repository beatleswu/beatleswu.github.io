"""Windows-spawn-safe G080 pytest entrypoint for isolated full-suite shards.

The real Grimoire pre-import remains, but every side effect is inside main().
Windows multiprocessing reloads this module as __mp_main__; it must never
run pytest recursively or create nested worker trees.
"""
from __future__ import annotations

import os
import sys


def main() -> int:
    sys.path.insert(0, os.getcwd())
    os.environ.setdefault("SECRET_KEY", "g080-disposable-contract-test-only")
    import grimoire_api  # noqa: F401
    import pytest
    return int(pytest.main(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
