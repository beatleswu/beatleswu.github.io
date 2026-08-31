"""Controlled Incident 019B compatibility baseline runner and census.

Default mode is read-only preview.  ``--capture-baseline`` is intentionally
explicit and requires the exact version confirmation; it is the future
Owner-gated migration/backfill entrypoint and is not run by this task.

The output contains only aggregate counts and short deterministic player
pseudonyms.  It never prints connection details or account identifiers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

# Allow the runner to be invoked directly as ``python tools/<runner>.py`` from
# the repository root, as well as imported by a test or another tool.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from adventure_progress_compatibility import (
    BASELINE_VERSION,
    build_compatibility_census,
    populate_frozen_historical_baseline,
)


def _zone_question_ids(app_module: Any) -> dict[str, set[int]]:
    questions = app_module._load_questions()
    return {
        zone["key"]: {
            int(question["id"])
            for question in app_module._questions_for_adventure_zone(
                questions, zone, premium=True
            )
        }
        for zone in app_module.ADVENTURE_ZONES
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Incident 019B Adventure mastery compatibility census"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="preview the one-time baseline and print a set-aware census (default)",
    )
    mode.add_argument(
        "--capture-baseline",
        action="store_true",
        help="capture the frozen baseline in the caller-selected database",
    )
    parser.add_argument(
        "--historical-mode",
        choices=("preview", "frozen"),
        default="preview",
        help="use live source preview or the already frozen table for the census",
    )
    parser.add_argument(
        "--confirm-baseline-version",
        default=None,
        help="required with --capture-baseline; must equal the locked version",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.capture_baseline and args.confirm_baseline_version != BASELINE_VERSION:
        raise SystemExit(
            "--capture-baseline requires --confirm-baseline-version "
            f"{BASELINE_VERSION}"
        )

    # Importing app is deliberately deferred so importing this tool remains a
    # pure helper operation and no database connection is opened accidentally.
    import app as app_module

    zone_question_ids = _zone_question_ids(app_module)
    all_question_ids = set().union(*zone_question_ids.values())
    if args.capture_baseline:
        with app_module.get_db() as conn:
            result = populate_frozen_historical_baseline(
                conn,
                question_ids=all_question_ids,
            )
            conn.commit()
            result["census"] = build_compatibility_census(
                conn,
                zone_question_ids,
                historical_mode="frozen",
            )
    else:
        with app_module.get_db() as conn:
            result = build_compatibility_census(
                conn,
                zone_question_ids,
                historical_mode=args.historical_mode,
            )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
