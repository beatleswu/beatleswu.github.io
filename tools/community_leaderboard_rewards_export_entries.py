"""Read-only exporter: real Community Leaderboard Rewards entries file.

`finalize-preview` / `finalize-commit` (see
tools/community_leaderboard_rewards_manual.py) are pure functions of a
caller-supplied `--entries-file`; neither one queries the database for
ranking data. Until now there was no safe way to produce that file from
the *real* weekly/monthly community leaderboard, because:

  - the only route that computes those rankings,
    `@app.route('/api/community/leaderboard')`, is `@login_required` and
    is meant to stay that way -- it is not something an operator should
    log into as a real user just to export data;
  - its JSON response deliberately never exposes the internal integer
    `user_id` (see `_row_loadout`/`fmt()` in app.py) -- and it must
    continue not to, since it is a public API response.

This tool closes that gap without touching the public route or its
output shape: it reuses the same (now factored-out, byte-for-byte
identical) scoring query and period-boundary helpers that route already
calls --
`app._fetch_community_leaderboard_score_rows` /
`app._community_leaderboard_period_start_iso` -- so ranking semantics can
never drift between the public page and this exporter. It reads
`u.id` directly from those rows (safe here, because this writes a local
operator file, not a public API response) and writes an entries JSON
file matching exactly what `finalize-preview`/`finalize-commit` expect:

    [{"user_id": 123, "display_name": "Player", "avatar": null,
      "rank": 1, "score": 999}, ...]

Read-only: this tool never INSERTs, UPDATEs, or DELETEs anything, never
touches any reward snapshot/claim table, never grants coins/items/
badges/titles, and never enables the scheduler.
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import community_leaderboard_rewards as lbr


def _load_app_module():
    """Import app.py lazily -- it's a large Flask module with real DB
    pool setup, so only import it when this tool actually needs DB
    access. Keeps --help and unit tests of the pure functions below fast
    and free of any DB/network side effect."""
    import app as app_module
    return app_module


def rows_to_leaderboard_entries(rows, limit=None):
    """Pure transform: raw score-query rows (dict-like, each with
    id/display_name/score/character_key) -> (entries, skipped).

    No DB access, no I/O -- this only shapes and validates data already
    fetched by the caller, so it can be unit-tested with plain dicts.

    Rank is assigned from row order (position in `rows`, which is already
    ORDER BY score DESC from the shared scoring query) *before* any
    entry is skipped, so a skipped row (bad nickname, duplicate id,
    missing score) can never promote the next real player up a rank band
    they didn't actually earn.

    An entry is skipped (not raised) for:
      - a user_id already seen in this same row set (duplicate_user_id)
      - a null/missing score (missing_score)
      - a display_name that fails
        community_leaderboard_rewards.validate_leaderboard_display_name_snapshot
        (unsafe_display_name) -- one unsafe nickname must not abort
        export for every other eligible player.
    """
    entries = []
    skipped = []
    seen_user_ids = set()
    for i, row in enumerate(rows, start=1):
        if limit is not None and i > limit:
            break
        user_id = row["id"]
        if user_id in seen_user_ids:
            skipped.append({"user_id": user_id, "rank": i, "reason": "duplicate_user_id"})
            continue
        score = row["score"]
        if score is None:
            skipped.append({"user_id": user_id, "rank": i, "reason": "missing_score"})
            continue
        display_name = row["display_name"]
        try:
            lbr.validate_leaderboard_display_name_snapshot(display_name)
        except ValueError as exc:
            skipped.append({
                "user_id": user_id, "rank": i,
                "reason": f"unsafe_display_name: {exc}",
            })
            continue
        seen_user_ids.add(user_id)
        character_key = row["character_key"] if "character_key" in row.keys() else None
        entries.append({
            "user_id": int(user_id),
            "display_name": display_name,
            "avatar": character_key or None,
            "rank": i,
            "score": score,
        })
    return entries, skipped


def validate_entries_list(entries):
    """Structural validation of a finished entries list, right before
    it's written to disk. Pure function, no I/O. Raises ValueError on
    the first problem found -- this is a defense-in-depth check on top
    of rows_to_leaderboard_entries's own per-row validation."""
    seen_user_ids = set()
    for entry in entries:
        user_id = entry.get("user_id")
        if not isinstance(user_id, int) or isinstance(user_id, bool):
            raise ValueError(f"entry user_id must be an int, got {user_id!r}")
        if user_id in seen_user_ids:
            raise ValueError(f"duplicate user_id in entries list: {user_id}")
        seen_user_ids.add(user_id)
        rank = entry.get("rank")
        if not isinstance(rank, int) or isinstance(rank, bool) or rank <= 0:
            raise ValueError(f"entry rank must be a positive int, got {rank!r}")
        score = entry.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            raise ValueError(f"entry score must be numeric, got {score!r}")
        display_name = entry.get("display_name")
        if not isinstance(display_name, str) or not display_name.strip():
            raise ValueError(f"entry display_name must be a non-empty string, got {display_name!r}")
    return True


def fetch_real_leaderboard_rows(conn, app_module, board_type):
    """Read-only fetch of the real, current weekly/monthly community
    leaderboard rows via app.py's shared, unmodified scoring helpers."""
    period_start_iso = app_module._community_leaderboard_period_start_iso(board_type)
    return app_module._fetch_community_leaderboard_score_rows(conn, period_start_iso)


def resolve_period_metadata(board_type, period_key, period_start, period_end):
    """Fill in any of period_key/period_start/period_end left unset by
    the caller from community_leaderboard_rewards.get_leaderboard_period
    -- the same period-boundary logic finalize_leaderboard_reward_period
    itself uses. This is metadata for the output file / for the
    finalize-preview command line, not something that changes which rows
    are queried -- the scoring query itself always reflects "the current
    period as of now" (matching the live route), same as production."""
    if period_key and period_start and period_end:
        return period_key, period_start, period_end
    computed_start, computed_end = lbr.get_leaderboard_period(board_type)
    computed_key = lbr.format_leaderboard_period_key(board_type, computed_start)
    return (
        period_key or computed_key,
        period_start or computed_start.isoformat(),
        period_end or computed_end.isoformat(),
    )


def build_parser():
    parser = argparse.ArgumentParser(
        prog="community_leaderboard_rewards_export_entries",
        description=(
            "Read-only exporter: builds a real entries-file for Community "
            "Leaderboard Rewards finalize-preview/finalize-commit from the "
            "live community leaderboard scoring query. Never writes to any "
            "table, never grants anything."
        ),
    )
    parser.add_argument("--board", required=True, choices=lbr.BOARD_TYPES)
    parser.add_argument(
        "--period-key", default=None,
        help="Defaults to the current period's key (format_leaderboard_period_key).",
    )
    parser.add_argument(
        "--period-start", default=None,
        help="Defaults to the current period's start date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--period-end", default=None,
        help="Defaults to the current period's end date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Cap the number of exported entries (the underlying query "
             "already caps at 50; this can only narrow that further).",
    )
    parser.add_argument("--output", required=True, help="Path to write the entries JSON file.")
    parser.add_argument(
        "--database-url", default=None,
        help="Sets $DATABASE_URL before importing app.py, so app.py's own DB "
             "connection pool targets this database. Leave unset to use "
             "whatever DATABASE_URL is already in the environment.",
    )
    return parser


def _configure_utf8_console():
    """Best-effort: make stdout/stderr tolerate arbitrary Unicode text (real
    player display names in the skip-log lines) even on a non-UTF-8 Windows
    console, without requiring the operator to remember
    `PYTHONIOENCODING=utf-8`. No-op if a stream doesn't support reconfigure.
    Never raises -- the entries JSON file this tool writes is always UTF-8
    regardless of console encoding."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (ValueError, OSError):
                pass


def main(argv=None):
    _configure_utf8_console()
    args = build_parser().parse_args(argv)
    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url

    app_module = _load_app_module()

    period_key, period_start, period_end = resolve_period_metadata(
        args.board, args.period_key, args.period_start, args.period_end)

    with app_module.get_db() as conn:
        rows = fetch_real_leaderboard_rows(conn, app_module, args.board)

    entries, skipped = rows_to_leaderboard_entries(rows, limit=args.limit)
    validate_entries_list(entries)

    if not entries:
        print(
            f"WARNING: no eligible entries found for board={args.board} "
            f"period_key={period_key} -- writing an empty entries file.",
            file=sys.stderr,
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(f"board={args.board}")
    print(f"period_key={period_key}")
    print(f"period_start={period_start}")
    print(f"period_end={period_end}")
    print(f"entries_count={len(entries)}")
    print(f"skipped_count={len(skipped)}")
    for item in skipped:
        print(f"skipped: user_id={item['user_id']} rank={item['rank']} reason={item['reason']}",
              file=sys.stderr)
    print(f"output={output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
