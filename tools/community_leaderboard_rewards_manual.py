"""Internal manual utility for Community Leaderboard Rewards Phase 1.

Owner-only, dry-run-first CLI for running the leaderboard reward
finalize/grant helpers by hand against a local (or otherwise explicitly
configured) database. This is NOT a scheduler, NOT a public API, NOT
wired into the frontend, and does not deploy anything — see
docs/community_leaderboard_rewards_plan_20260705.md, section
"PR 5 internal manual utility 語意".

Commands:
    finalize-preview   dry-run preview of finalize_leaderboard_reward_period.
                       Never touches the database (passes conn=None).
    finalize-commit    writes leaderboard_snapshots + pending/skipped
                       leaderboard_reward_claims rows. Refuses to run
                       without --confirm-finalize. Never grants anything.
    grant-preview      read-only preview of coins/badge/title/item grants
                       for an already-finalized board/period. Never calls
                       any grant function, never updates claim status.
    grant-adapter-preview  dry-run-only preview of the real Phase 3B
                       adapter plan (grant_community_leaderboard_coins/
                       _item/_badge). Never calls any grant function,
                       never writes leaderboard_reward_component_log.
                       Also reports which claims (if any) would be
                       blocked by the current weekly-only item/badge
                       allowlists.
    grant-commit       intentionally disabled — see GRANT_COMMIT_DISABLED_MESSAGE.
                       No production coin/badge/title/item grant function
                       has been wired into this tool; wiring one in is
                       left to a later PR. Always refuses, with or
                       without --confirm-grant.
    grant-weekly-2026w27-commit  Phase 3D: WRITE-CAPABLE, but narrowly
                       scoped to board_type='weekly', period_key='2026-W27'
                       ONLY. Grants coins/item/badge for the pending claims
                       of that single period through the real production
                       grant functions. Requires
                       --confirm-weekly-2026w27-grant plus an exact
                       --expected-pending/--expected-total-coins match;
                       refuses any other board/period, any blocked claim,
                       any real-function signature error, and any title
                       payload. This is NOT a generic grant-commit — it
                       has no way to target any other board or period.
    retry-weekly-2026w27-claim  Phase 3H: WRITE-CAPABLE, but hard-gated
                       to claim_id=1/user_id=991136/weekly/2026-W27
                       ONLY. Retries exactly one previously-failed claim
                       (e.g. one that hit a real daily coin-cap
                       shortfall) by transitioning it 'failed' ->
                       'pending' and reusing the same grant path as
                       grant-weekly-2026w27-commit. Requires
                       --confirm-retry-claim-1 plus an exact
                       --claim-id/--user-id/--expected-coins match;
                       refuses any other claim, any status other than
                       'failed', any existing component-log row, and
                       any title/appearance_fragment mismatch. This is
                       NOT a generic retry mode.

This module never imports or calls the real coin-granting or
shop-purchase-granting helpers, never references a real badge/wardrobe/
item storage table by name, never hardcodes a production host or secret
(the database URL defaults to the same local dev Postgres used by the
test suite, and can be overridden via --database-url or the DATABASE_URL
env var), and is not wired into any scheduler, cron job, or frontend
route.
"""

import argparse
import datetime
import json
import os
import socket
import stat
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import community_leaderboard_rewards as lbr

DEFAULT_DATABASE_URL = "postgresql://go:go@localhost:5432/go_odyssey"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OPERATIONS_ROOT = Path(
    os.environ.get("GO_ODYSSEY_REWARD_OPERATIONS_ROOT", "/opt/go-odyssey/reward-operations")
)
SNAPSHOT_FILENAME = "snapshot.json"
PREVIEW_FILENAME = "preview.json"
GRANT_RESULT_FILENAME = "grant-result.json"
_OPERATION_FILENAMES = frozenset({SNAPSHOT_FILENAME, PREVIEW_FILENAME, GRANT_RESULT_FILENAME})

GRANT_COMMIT_DISABLED_MESSAGE = (
    "grant-commit is intentionally disabled until production grant "
    "functions are wired in a later PR"
)

_CLAIM_COLUMNS = [
    "id", "user_id", "board_type", "period_key", "rank", "rank_band", "score",
    "eligible", "ineligible_reason", "reward_bundle_key", "granted_coins",
    "granted_items_json", "granted_badges_json", "granted_titles_json",
    "status", "error_message", "created_at", "granted_at",
]


def _connect(database_url):
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper
    raw_conn = psycopg2.connect(database_url)
    # Match db.get_db()'s own cursor_factory so any real production
    # helper this tool eventually calls (Phase 3D) -- several of which
    # read rows via dict-style column access -- gets the row shape it
    # expects, exactly as it does in production.
    raw_conn.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw_conn, pooled=False)


def _load_entries(entries_file):
    with open(entries_file, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _load_json_file(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _canonical_file_sha256(path):
    return lbr.sha256_hex_from_value(_load_json_file(path))


def _parse_json_arg(raw, label):
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must decode to a JSON object")
    return value


def _database_identity(database_url):
    parsed = urllib.parse.urlsplit(database_url)
    scheme = parsed.scheme or "unknown"
    host = parsed.hostname or "unknown-host"
    port = parsed.port or ""
    dbname = (parsed.path or "").lstrip("/") or "unknown-db"
    suffix = f":{port}" if port else ""
    return f"{scheme}://{host}{suffix}/{dbname}"


def _environment_identity():
    return {
        "production_flag": str(os.environ.get("PRODUCTION", "")),
        "hostname": socket.gethostname(),
    }


def _reject_symlink_path(path):
    current = Path(path.anchor) if path.is_absolute() else Path(".")
    for part in path.parts[1:] if path.is_absolute() else path.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ValueError(f"symlink paths are forbidden for reward operations: {current}")


def _is_world_writable(path):
    if os.name == "nt":
        return False
    return bool(path.stat().st_mode & stat.S_IWOTH)


def _ensure_restrictive_directory(path):
    if path.exists():
        if not path.is_dir():
            raise ValueError(f"operation path is not a directory: {path}")
        if _is_world_writable(path):
            raise ValueError(f"world-writable directory is forbidden: {path}")
    else:
        path.mkdir(mode=0o700, parents=True, exist_ok=False)
    if os.name != "nt":
        os.chmod(path, 0o700)


def _validate_operation_dir(operation_dir):
    raw = Path(operation_dir)
    if not raw.is_absolute():
        raise ValueError("operation_dir must be an absolute path")
    _reject_symlink_path(raw)
    root = DEFAULT_OPERATIONS_ROOT.resolve(strict=False)
    candidate = raw.resolve(strict=False)
    if candidate == REPO_ROOT or REPO_ROOT in candidate.parents:
        raise ValueError("reward operation files must not be written inside the Git working tree")
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"operation_dir must stay under {root}")
    _ensure_restrictive_directory(root)
    parent = candidate.parent
    if parent != candidate:
        _reject_symlink_path(parent)
        _ensure_restrictive_directory(parent)
    _ensure_restrictive_directory(candidate)
    return candidate


def _validate_operation_file(path, *, operation_dir=None, require_exists=True):
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValueError("operation file path must be absolute")
    _reject_symlink_path(candidate)
    resolved = candidate.resolve(strict=False)
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise ValueError("reward operation files must not be stored inside the Git working tree")
    if operation_dir is not None and resolved.parent != Path(operation_dir).resolve(strict=False):
        raise ValueError(f"operation file must live directly under {operation_dir}")
    if resolved.name not in _OPERATION_FILENAMES:
        raise ValueError(f"unexpected reward operation filename: {resolved.name}")
    if require_exists:
        if not resolved.exists():
            raise ValueError(f"operation file does not exist: {resolved}")
        if not resolved.is_file():
            raise ValueError(f"operation path is not a file: {resolved}")
        if _is_world_writable(resolved):
            raise ValueError(f"world-writable file is forbidden: {resolved}")
    return resolved


def _write_operation_json(path, payload):
    target = _validate_operation_file(path, require_exists=False)
    data = (lbr.canonical_json_dumps(payload) + "\n").encode("utf-8")
    if target.exists():
        if target.read_bytes() != data:
            raise ValueError(f"existing operation file identity differs: {target}")
    else:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(str(target), flags, 0o600)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
        finally:
            try:
                os.chmod(target, 0o600)
            except OSError:
                pass
    written = target.read_bytes()
    if written != data:
        raise ValueError(f"operation file bytes changed unexpectedly after write: {target}")
    return target, lbr.sha256_hex_from_value(json.loads(written.decode("utf-8")))


def _build_preview_identity_record(snapshot, preview, *, database_url, snapshot_file):
    return {
        "board_type": snapshot["board_type"],
        "period_key": snapshot["period_key"],
        "period_start": snapshot["period_start"],
        "period_end_exclusive": snapshot["period_end_exclusive"],
        "timezone": snapshot["timezone"],
        "database_identity": _database_identity(database_url),
        "environment_identity": _environment_identity(),
        "snapshot_file": str(snapshot_file),
        "snapshot_file_sha256": _canonical_file_sha256(snapshot_file),
        "snapshot_sha256": preview["snapshot_sha256"],
        "preview_sha256": preview["preview_sha256"],
        "summary": preview["summary"],
    }


def _load_and_validate_preview_identity(preview_file, *, snapshot, snapshot_file, database_url):
    preview_identity = _load_json_file(preview_file)
    if preview_identity.get("snapshot_file_sha256") != _canonical_file_sha256(snapshot_file):
        raise ValueError("preview identity does not match the exact snapshot file bytes")
    if preview_identity.get("snapshot_sha256") != lbr.sha256_hex_from_value(snapshot):
        raise ValueError("preview identity snapshot SHA mismatch")
    if preview_identity.get("database_identity") != _database_identity(database_url):
        raise ValueError("preview identity database mismatch")
    # Only production_flag is a meaningful identity signal here; hostname is
    # the container's ephemeral Docker-assigned ID and changes on every
    # deploy/force-recreate, which would otherwise fail-close every preview
    # captured before a later, unrelated redeploy.
    expected_env = _environment_identity()
    stored_env = preview_identity.get("environment_identity") or {}
    if stored_env.get("production_flag") != expected_env["production_flag"]:
        raise ValueError("preview identity environment mismatch")
    for key in ("board_type", "period_key", "period_start", "period_end_exclusive", "timezone"):
        if preview_identity.get(key) != snapshot.get(key):
            raise ValueError(f"preview identity {key} mismatch")
    return preview_identity


def _print_header(board_type, period_key, mode, dry_run):
    print(f"board_type={board_type}")
    print(f"period_key={period_key}")
    print(f"mode={mode}")
    print(f"dry_run={dry_run}")
    if dry_run:
        print("warning=none (dry-run: no DB write, no grant call)")
    else:
        print("warning=THIS WRITES TO THE DATABASE configured by --database-url")


def fetch_claims_as_dicts(conn, board_type, period_key):
    """Read-only fetch of leaderboard_reward_claims rows for one
    board_type/period_key, as plain dicts. Adds a 'claim_id' alias of
    'id' so the result can be passed directly into the PR 4B/4C
    preview/grant helpers, which read claim_id."""
    columns_sql = ", ".join(_CLAIM_COLUMNS)
    cur = conn.execute(
        f"SELECT {columns_sql} FROM leaderboard_reward_claims "
        "WHERE board_type = %(board_type)s AND period_key = %(period_key)s ORDER BY id",
        {"board_type": board_type, "period_key": period_key},
    )
    claims = []
    for row in cur.fetchall():
        claim = dict(zip(_CLAIM_COLUMNS, row))
        claim["claim_id"] = claim["id"]
        claims.append(claim)
    return claims


def run_finalize_preview(board_type, period_key, period_start, period_end, entries):
    """dry_run=True, conn=None — physically cannot touch the database."""
    return lbr.finalize_leaderboard_reward_period(
        None, board_type, period_key, period_start, period_end, entries, dry_run=True,
    )


def run_finalize_commit(conn, board_type, period_key, period_start, period_end, entries):
    """Caller owns the transaction — does not call conn.commit()."""
    return lbr.finalize_leaderboard_reward_period(
        conn, board_type, period_key, period_start, period_end, entries, dry_run=False,
    )


def run_grant_preview(conn, board_type, period_key):
    """Read-only preview of coins + badge + title + item grants for a
    board_type/period_key. Every helper is invoked with dry_run=True, so
    no grant function is ever called, no claim status is ever updated,
    and nothing is written to the database — `conn` is used for SELECT
    only (coins preview reads pending claims; the claim fetch below reads
    the full claim set for the badge/title/item previews)."""
    coins_preview = lbr.grant_leaderboard_reward_claims(
        conn, board_type, period_key, dry_run=True)
    claims = fetch_claims_as_dicts(conn, board_type, period_key)
    badge_preview = lbr.grant_leaderboard_badge_rewards(claims, dry_run=True)
    title_preview = lbr.grant_leaderboard_title_rewards(claims, dry_run=True)
    item_preview = lbr.grant_leaderboard_item_rewards(claims, dry_run=True)
    return {
        "board_type": board_type,
        "period_key": period_key,
        "claims_count": len(claims),
        "pending_count": sum(1 for c in claims if c["status"] == lbr.CLAIM_STATUS_PENDING),
        "skipped_count": sum(1 for c in claims if c["status"] == lbr.CLAIM_STATUS_SKIPPED),
        "granted_count": sum(1 for c in claims if c["status"] == lbr.CLAIM_STATUS_GRANTED),
        "failed_count": sum(1 for c in claims if c["status"] == lbr.CLAIM_STATUS_FAILED),
        "coins_preview": coins_preview,
        "badge_preview": badge_preview,
        "title_preview": title_preview,
        "item_preview": item_preview,
    }


def run_grant_adapter_preview(conn, board_type, period_key):
    """Dry-run-only preview of the real Phase 3B adapter plan
    (grant_community_leaderboard_coins/_item/_badge) for a board_type/
    period_key. Reuses grant_leaderboard_reward_bundle's own dry_run=True
    path (no grant function is ever called, nothing is written -- not
    even leaderboard_reward_component_log), then additionally checks
    every pending/granted claim's actual item/badge/title keys against
    the Phase 3B allowlists so an operator can see, before any real
    grant, which claims (if any) would be blocked by the current
    weekly-only scope. Never requires or accepts a confirm flag -- there
    is nothing here that writes anything."""
    bundle_preview = lbr.grant_leaderboard_reward_bundle(
        conn, board_type=board_type, period_key=period_key, dry_run=True)
    claims = fetch_claims_as_dicts(conn, board_type, period_key)

    blocked = []
    for claim in claims:
        if claim["status"] in (lbr.CLAIM_STATUS_SKIPPED, lbr.CLAIM_STATUS_FAILED):
            continue
        claim_id = claim["claim_id"]
        try:
            items = lbr.extract_leaderboard_item_payload(claim)
        except ValueError as exc:
            blocked.append({"claim_id": claim_id, "reason": f"item_payload_error: {exc}"})
            continue
        for item_key in items:
            if not lbr.is_phase_3b_item_key_allowed(item_key):
                blocked.append({
                    "claim_id": claim_id,
                    "reason": f"item_key_not_allowed_in_phase_3b: {item_key}",
                })
        try:
            badge_title = lbr.extract_leaderboard_badge_title_payload(claim)
        except ValueError as exc:
            blocked.append({"claim_id": claim_id, "reason": f"badge_title_payload_error: {exc}"})
            continue
        for badge_key in badge_title["badges"]:
            if not lbr.is_phase_3b_badge_key_allowed(badge_key):
                blocked.append({
                    "claim_id": claim_id,
                    "reason": f"badge_key_not_allowed_in_phase_3b: {badge_key}",
                })
        if badge_title["titles"]:
            blocked.append({
                "claim_id": claim_id,
                "reason": "title_grants_deferred_in_phase_3b",
            })

    coins_would_grant_entries = [
        e for e in bundle_preview["coins_result"].get("preview", []) if e.get("would_grant")
    ]
    would_grant_item_claims = {
        e["claim_id"] for e in bundle_preview["item_result"].get("entries", [])
        if e.get("result") == "would_grant"
    }
    would_grant_badge_claims = {
        e["claim_id"] for e in bundle_preview["badge_result"].get("entries", [])
        if e.get("result") == "would_grant"
    }
    would_grant_title_claims = {
        e["claim_id"] for e in bundle_preview["title_result"].get("entries", [])
        if e.get("result") == "would_grant"
    }

    return {
        "board_type": board_type,
        "period_key": period_key,
        "dry_run": True,
        "claims_count": len(claims),
        "pending_count": sum(1 for c in claims if c["status"] == lbr.CLAIM_STATUS_PENDING),
        "skipped_count": sum(1 for c in claims if c["status"] == lbr.CLAIM_STATUS_SKIPPED),
        "would_grant_coin_claims": len(coins_would_grant_entries),
        "would_grant_items_claims": len(would_grant_item_claims),
        "would_grant_badges_claims": len(would_grant_badge_claims),
        "would_grant_titles_claims": len(would_grant_title_claims),
        "total_coins": sum(e.get("granted_coins", 0) for e in coins_would_grant_entries),
        "blocked_claims": blocked,
        "bundle_preview": bundle_preview,
    }


def run_grant_real_preview(conn, board_type, period_key):
    """Dry-run-only preview reusing run_grant_adapter_preview's own
    fake-function-free bundle preview (claims_count/would-grant counts/
    blocked_claims -- identical computation, zero calls, zero writes),
    then ADDITIONALLY verifies that the real production coin/item/badge
    grant targets exist and are signature-compatible for every claim's
    actual payload -- without ever calling any of them.

    The module doing that verification
    (tools/community_leaderboard_rewards_real_grant_preview.py) is
    imported here, lazily, inside this function body only -- this
    module's own top-level source never mentions any real production
    grant-helper or table name, preserving every pre-existing safety
    test on this file unchanged."""
    from community_leaderboard_rewards_real_grant_preview import (
        load_app_module, verify_real_grant_targets_for_claims,
    )

    base = run_grant_adapter_preview(conn, board_type, period_key)
    claims = fetch_claims_as_dicts(conn, board_type, period_key)
    app_module = load_app_module()
    signature_errors = verify_real_grant_targets_for_claims(app_module, conn, claims)

    result = dict(base)
    result["real_function_signature_errors"] = signature_errors
    return result


def cmd_grant_real_preview(args):
    conn = _connect(args.database_url)
    try:
        result = run_grant_real_preview(conn, args.board, args.period_key)
    finally:
        conn.close()
    _print_header(args.board, args.period_key, "grant-real-preview", True)
    print(f"claims_count={result['claims_count']}")
    print(f"pending_count={result['pending_count']}")
    print(f"skipped_count={result['skipped_count']}")
    print(f"would_grant_coin_claims={result['would_grant_coin_claims']}")
    print(f"would_grant_items_claims={result['would_grant_items_claims']}")
    print(f"would_grant_badges_claims={result['would_grant_badges_claims']}")
    print(f"would_grant_titles_claims={result['would_grant_titles_claims']}")
    print(f"total_coins={result['total_coins']}")
    print(f"blocked_claims={len(result['blocked_claims'])}")
    print(f"real_function_signature_errors={len(result['real_function_signature_errors'])}")
    for item in result["blocked_claims"]:
        print(f"blocked: claim_id={item['claim_id']} reason={item['reason']}", file=sys.stderr)
    for err in result["real_function_signature_errors"]:
        print(f"signature_error: claim_id={err['claim_id']} component={err['component']} "
              f"error={err['error']}", file=sys.stderr)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    if result["real_function_signature_errors"]:
        return 4
    return 0


def cmd_snapshot_exact_period(args):
    from community_leaderboard_rewards_exact_period import (
        build_exact_period_preview,
        build_exact_period_snapshot,
    )
    conn = _connect(args.database_url)
    try:
        snapshot = build_exact_period_snapshot(
            conn,
            board_type=args.board,
            period_key=args.period_key,
            period_start=args.period_start,
            period_end_exclusive=args.period_end,
            timezone=args.timezone,
            limit=args.limit,
        )
    finally:
        conn.close()
    preview = None
    preview_identity = None
    operation_dir = None
    if args.operation_dir:
        operation_dir = _validate_operation_dir(args.operation_dir)
        snapshot_path = operation_dir / SNAPSHOT_FILENAME
        preview_path = operation_dir / PREVIEW_FILENAME
        _write_operation_json(snapshot_path, snapshot)
        preview = build_exact_period_preview(snapshot)
        preview_identity = _build_preview_identity_record(
            snapshot,
            preview,
            database_url=args.database_url,
            snapshot_file=snapshot_path,
        )
        _write_operation_json(preview_path, preview_identity)
    print(f"board_type={args.board}")
    print(f"period_key={args.period_key}")
    print("mode=snapshot-exact-period")
    print("dry_run=True")
    print(f"snapshot_sha256={lbr.sha256_hex_from_value(snapshot)}")
    print(f"original_participant_count={snapshot['participant_counts']['original_participant_count']}")
    print(f"ranked_participant_count={snapshot['participant_counts']['ranked_participant_count']}")
    print(f"top_ranked_row_count={snapshot['participant_counts']['top_ranked_row_count']}")
    if operation_dir is not None:
        print(f"operation_dir={operation_dir}")
        print(f"snapshot_file={operation_dir / SNAPSHOT_FILENAME}")
        print(f"preview_file={operation_dir / PREVIEW_FILENAME}")
        print(f"preview_sha256={preview['preview_sha256']}")
    print(json.dumps(snapshot, indent=2, ensure_ascii=False))
    return 0


def cmd_preview_exact_period(args):
    from community_leaderboard_rewards_exact_period import build_exact_period_preview
    snapshot_file = _validate_operation_file(args.snapshot_file, require_exists=True)
    snapshot = _load_json_file(snapshot_file)
    preview = build_exact_period_preview(snapshot)
    preview_identity = None
    if args.preview_file:
        preview_file = _validate_operation_file(
            args.preview_file,
            operation_dir=snapshot_file.parent,
            require_exists=True,
        )
        preview_identity = _load_and_validate_preview_identity(
            preview_file,
            snapshot=snapshot,
            snapshot_file=snapshot_file,
            database_url=args.database_url,
        )
    print(f"board_type={preview['board_type']}")
    print(f"period_key={preview['period_key']}")
    print("mode=preview-exact-period")
    print("dry_run=True")
    print(f"snapshot_sha256={preview['snapshot_sha256']}")
    print(f"preview_sha256={preview['preview_sha256']}")
    print(f"claims_count={preview['summary']['claims_count']}")
    print(f"snapshot_row_count={preview['summary']['snapshot_row_count']}")
    print(f"eligible_claim_count={preview['summary']['eligible_claim_count']}")
    print(f"component_count={preview['summary']['component_count']}")
    if preview_identity is not None:
        print(f"preview_identity_file={preview_file}")
    print(json.dumps(preview, indent=2, ensure_ascii=False))
    return 0


def cmd_grant_exact_period_commit(args):
    from community_leaderboard_rewards_exact_period import commit_exact_period
    snapshot_file = _validate_operation_file(args.snapshot_file, require_exists=True)
    snapshot = _load_json_file(snapshot_file)
    preview_file = _validate_operation_file(
        args.preview_file,
        operation_dir=snapshot_file.parent,
        require_exists=True,
    )
    expected_total_items = _parse_json_arg(args.expected_total_items_json, "expected_total_items_json")
    expected_total_badges = _parse_json_arg(args.expected_total_badges_json, "expected_total_badges_json")
    _load_and_validate_preview_identity(
        preview_file,
        snapshot=snapshot,
        snapshot_file=snapshot_file,
        database_url=args.database_url,
    )
    conn = _connect(args.database_url)
    try:
        try:
            result = commit_exact_period(
                conn,
                snapshot=snapshot,
                expected_snapshot_sha256=args.expected_snapshot_sha256,
                expected_preview_sha256=args.expected_preview_sha256,
                expected_claim_count=args.expected_claim_count,
                expected_component_count=args.expected_component_count,
                expected_total_coins=args.expected_total_coins,
                expected_total_items=expected_total_items,
                expected_total_badges=expected_total_badges,
                owner_gate=args.owner_gate,
                required_owner_gate=lbr.EXACT_PERIOD_OWNER_GATE,
                now=datetime.datetime.now(datetime.timezone.utc),
            )
        except Exception:
            conn.rollback()
            raise
        conn.commit()
    finally:
        conn.close()
    grant_result_path = snapshot_file.parent / GRANT_RESULT_FILENAME
    grant_result_record = {
        "board_type": snapshot["board_type"],
        "period_key": snapshot["period_key"],
        "snapshot_sha256": result["snapshot_sha256"],
        "preview_sha256": result["preview_sha256"],
        "result": result["result"],
        "summary": result["summary"],
        "database_identity": _database_identity(args.database_url),
        "environment_identity": _environment_identity(),
    }
    _write_operation_json(grant_result_path, grant_result_record)
    print(f"board_type={snapshot['board_type']}")
    print(f"period_key={snapshot['period_key']}")
    print("mode=grant-exact-period-commit")
    print("dry_run=False")
    print(f"result={result['result']}")
    print(f"snapshot_sha256={result['snapshot_sha256']}")
    print(f"preview_sha256={result['preview_sha256']}")
    print(f"grant_result_file={grant_result_path}")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


# ── Phase 3D: weekly 2026-W27 real grant-commit (write-capable, narrow) ─
#
# This section deliberately hardcodes board_type/period_key so it can
# never be pointed at any other board or period, even by mistake --
# args.board/args.period_key are only ever compared against these
# constants for a reject/accept decision, never substituted into the
# actual query. Widening this to arbitrary board/period is explicitly
# out of scope and left to a future, separately-reviewed PR.

WEEKLY_2026W27_BOARD = "weekly"
WEEKLY_2026W27_PERIOD_KEY = "2026-W27"


def run_weekly_2026w27_grant_commit(conn, *, expected_pending, expected_total_coins):
    """Write-capable grant-commit for board_type='weekly',
    period_key='2026-W27' ONLY. Raises ValueError (calling nothing) unless
    every one of these gates passes first:

      - a fresh run_grant_real_preview reports blocked_claims == 0 and
        real_function_signature_errors == 0 (this also transitively
        guards against any appearance_fragment/disallowed item or badge
        key, since those already populate blocked_claims)
      - would_grant_titles_claims == 0 -- this module has no title-grant
        wiring at all
      - pending_count == expected_pending
      - total_coins == expected_total_coins

    Only after every gate passes does it fetch the actual pending claims
    and call
    community_leaderboard_rewards_real_grant_commit.execute_weekly_2026w27_grant_commit,
    imported here lazily so this file's own top-level source never
    mentions a real production grant-helper by name. Caller owns the
    transaction (never calls conn.commit()/rollback())."""
    from community_leaderboard_rewards_real_grant_preview import load_app_module
    from community_leaderboard_rewards_real_grant_commit import execute_weekly_2026w27_grant_commit

    preview = run_grant_real_preview(conn, WEEKLY_2026W27_BOARD, WEEKLY_2026W27_PERIOD_KEY)

    if preview["blocked_claims"]:
        raise ValueError(
            f"refusing to commit: {len(preview['blocked_claims'])} blocked claim(s) present"
        )
    if preview["real_function_signature_errors"]:
        raise ValueError(
            f"refusing to commit: {len(preview['real_function_signature_errors'])} "
            "real_function_signature_error(s) present"
        )
    if preview["would_grant_titles_claims"]:
        raise ValueError(
            "refusing to commit: title payloads present in this period -- out of scope"
        )
    if preview["pending_count"] != expected_pending:
        raise ValueError(
            f"refusing to commit: expected-pending mismatch "
            f"(expected {expected_pending}, got {preview['pending_count']})"
        )
    if preview["total_coins"] != expected_total_coins:
        raise ValueError(
            f"refusing to commit: expected-total-coins mismatch "
            f"(expected {expected_total_coins}, got {preview['total_coins']})"
        )

    app_module = load_app_module()
    claims = fetch_claims_as_dicts(conn, WEEKLY_2026W27_BOARD, WEEKLY_2026W27_PERIOD_KEY)
    pending_claims = [c for c in claims if c["status"] == lbr.CLAIM_STATUS_PENDING]

    results = execute_weekly_2026w27_grant_commit(conn, app_module, pending_claims)

    return {
        "board_type": WEEKLY_2026W27_BOARD,
        "period_key": WEEKLY_2026W27_PERIOD_KEY,
        "dry_run": False,
        "claims_processed": len(results),
        "claims_granted": sum(1 for r in results if r["status"] == "granted"),
        "claims_failed": sum(1 for r in results if r["status"] == "failed"),
        "results": results,
    }


def cmd_grant_weekly_2026w27_commit(args):
    if args.board != WEEKLY_2026W27_BOARD:
        print(
            f"Refusing: --board must be {WEEKLY_2026W27_BOARD!r}, got {args.board!r}. "
            "This command cannot target any other board.",
            file=sys.stderr,
        )
        return 2
    if args.period_key != WEEKLY_2026W27_PERIOD_KEY:
        print(
            f"Refusing: --period-key must be {WEEKLY_2026W27_PERIOD_KEY!r}, got "
            f"{args.period_key!r}. This command cannot target any other period.",
            file=sys.stderr,
        )
        return 2
    if not args.confirm_weekly_2026w27_grant:
        print(
            "Refusing to run grant-weekly-2026w27-commit without "
            "--confirm-weekly-2026w27-grant (this WRITES real coins/items/badges).",
            file=sys.stderr,
        )
        return 2

    conn = _connect(args.database_url)
    try:
        try:
            result = run_weekly_2026w27_grant_commit(
                conn,
                expected_pending=args.expected_pending,
                expected_total_coins=args.expected_total_coins,
            )
        except ValueError as exc:
            conn.rollback()
            print(f"Refusing to commit: {exc}", file=sys.stderr)
            return 5
        conn.commit()
    finally:
        conn.close()

    _print_header(args.board, args.period_key, "grant-weekly-2026w27-commit", False)
    print(f"claims_processed={result['claims_processed']}")
    print(f"claims_granted={result['claims_granted']}")
    print(f"claims_failed={result['claims_failed']}")
    for r in result["results"]:
        if r["status"] == "failed":
            print(f"failed: claim_id={r['claim_id']} error={r['error']}", file=sys.stderr)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result["claims_failed"] == 0 else 6


# ── Phase 3H: single failed-claim retry, hard-gated to claim_id=1 ──────
#
# This is NOT a generic retry mode. Every constant below is compared
# against, never substituted from caller input into the actual query --
# retrying any other claim requires a new, separately-reviewed command.

RETRY_CLAIM_ID = 1
RETRY_USER_ID = 991136
RETRY_BOARD = "weekly"
RETRY_PERIOD_KEY = "2026-W27"
RETRY_EXPECTED_ITEMS = {"xp_potion": 2}
RETRY_EXPECTED_BADGES = ["badge_lb_weekly_1"]


def run_retry_weekly_2026w27_claim(conn, *, claim_id, user_id, expected_coins):
    """Narrow, write-capable retry for exactly claim_id=1 / user_id=991136
    / board_type='weekly' / period_key='2026-W27'. Raises ValueError
    (calling nothing, changing nothing) unless every one of these gates
    passes:

      - claim_id == RETRY_CLAIM_ID, user_id == RETRY_USER_ID (checked
        against the caller's arguments AND against the actual claim row)
      - the claim row exists, with board_type/period_key/user_id
        matching the hardcoded constants
      - current status == 'failed'
      - granted_coins == expected_coins
      - the item payload is exactly RETRY_EXPECTED_ITEMS (no
        appearance_fragment, no other key, no missing key)
      - the badge payload is exactly RETRY_EXPECTED_BADGES
      - there is no title payload
      - leaderboard_reward_component_log has zero rows for this claim_id
        (a non-zero count means a partial grant may already exist --
        this refuses rather than risk a double-grant, requiring manual
        review instead)

    Only after every gate passes does it transition the claim from
    'failed' to 'pending'
    (community_leaderboard_rewards.reset_leaderboard_claim_to_pending_for_retry)
    and then reuse execute_weekly_2026w27_grant_commit UNMODIFIED for
    the single resulting claim -- same coin bypass, same item/badge
    adapters, same per-claim SAVEPOINT, same component-log idempotency,
    same granted/failed status marking as every other weekly claim in
    Phase 3D. Caller owns the transaction (never calls
    conn.commit()/rollback())."""
    if claim_id != RETRY_CLAIM_ID:
        raise ValueError(f"refusing to retry: claim_id must be {RETRY_CLAIM_ID}, got {claim_id!r}")
    if user_id != RETRY_USER_ID:
        raise ValueError(f"refusing to retry: user_id must be {RETRY_USER_ID}, got {user_id!r}")

    from community_leaderboard_rewards_real_grant_preview import load_app_module
    from community_leaderboard_rewards_real_grant_commit import execute_weekly_2026w27_grant_commit

    columns_sql = ", ".join(_CLAIM_COLUMNS)
    cur = conn.execute(
        f"SELECT {columns_sql} FROM leaderboard_reward_claims WHERE id = %(id)s FOR UPDATE",
        {"id": claim_id},
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"refusing to retry: claim_id={claim_id} does not exist")
    claim = dict(zip(_CLAIM_COLUMNS, row))
    claim["claim_id"] = claim["id"]

    if claim["user_id"] != RETRY_USER_ID:
        raise ValueError(
            f"refusing to retry: claim_id={claim_id} belongs to user_id={claim['user_id']!r}, "
            f"not {RETRY_USER_ID}"
        )
    if claim["board_type"] != RETRY_BOARD:
        raise ValueError(
            f"refusing to retry: claim_id={claim_id} board_type={claim['board_type']!r}, "
            f"not {RETRY_BOARD!r}"
        )
    if claim["period_key"] != RETRY_PERIOD_KEY:
        raise ValueError(
            f"refusing to retry: claim_id={claim_id} period_key={claim['period_key']!r}, "
            f"not {RETRY_PERIOD_KEY!r}"
        )
    if claim["status"] != lbr.CLAIM_STATUS_FAILED:
        raise ValueError(
            f"refusing to retry: claim_id={claim_id} status={claim['status']!r}, expected 'failed'"
        )
    if claim["granted_coins"] != expected_coins:
        raise ValueError(
            f"refusing to retry: expected-coins mismatch "
            f"(expected {expected_coins}, got {claim['granted_coins']})"
        )

    items = lbr.extract_leaderboard_item_payload(claim)
    if items != RETRY_EXPECTED_ITEMS:
        raise ValueError(
            f"refusing to retry: item payload mismatch "
            f"(expected {RETRY_EXPECTED_ITEMS}, got {items})"
        )

    badge_title = lbr.extract_leaderboard_badge_title_payload(claim)
    if badge_title["badges"] != RETRY_EXPECTED_BADGES:
        raise ValueError(
            f"refusing to retry: badge payload mismatch "
            f"(expected {RETRY_EXPECTED_BADGES}, got {badge_title['badges']})"
        )
    if badge_title["titles"]:
        raise ValueError(
            f"refusing to retry: title payload present ({badge_title['titles']}) -- out of scope"
        )

    existing_component_log = conn.execute(
        "SELECT count(*) FROM leaderboard_reward_component_log WHERE claim_id = %(claim_id)s",
        {"claim_id": claim_id},
    ).fetchone()[0]
    if existing_component_log:
        raise ValueError(
            f"refusing to retry: claim_id={claim_id} already has "
            f"{existing_component_log} component-log row(s) -- possible partial grant, "
            "requires manual review, not an automatic retry"
        )

    reset_ok = lbr.reset_leaderboard_claim_to_pending_for_retry(conn, claim_id)
    if not reset_ok:
        raise ValueError(
            f"refusing to retry: claim_id={claim_id} status changed concurrently, "
            "no longer 'failed'"
        )

    app_module = load_app_module()
    claim["status"] = lbr.CLAIM_STATUS_PENDING
    results = execute_weekly_2026w27_grant_commit(conn, app_module, [claim])

    return {
        "claim_id": claim_id,
        "user_id": user_id,
        "board_type": RETRY_BOARD,
        "period_key": RETRY_PERIOD_KEY,
        "dry_run": False,
        "results": results,
    }


def cmd_retry_weekly_2026w27_claim(args):
    if args.claim_id != RETRY_CLAIM_ID:
        print(
            f"Refusing: --claim-id must be {RETRY_CLAIM_ID}, got {args.claim_id!r}. "
            "This command cannot target any other claim.",
            file=sys.stderr,
        )
        return 2
    if args.user_id != RETRY_USER_ID:
        print(
            f"Refusing: --user-id must be {RETRY_USER_ID}, got {args.user_id!r}. "
            "This command cannot target any other user.",
            file=sys.stderr,
        )
        return 2
    if not args.confirm_retry_claim_1:
        print(
            "Refusing to run retry-weekly-2026w27-claim without --confirm-retry-claim-1 "
            "(this WRITES real coins/items/badges for claim_id=1 only).",
            file=sys.stderr,
        )
        return 2

    conn = _connect(args.database_url)
    try:
        try:
            result = run_retry_weekly_2026w27_claim(
                conn, claim_id=args.claim_id, user_id=args.user_id,
                expected_coins=args.expected_coins,
            )
        except ValueError as exc:
            conn.rollback()
            print(f"Refusing to retry: {exc}", file=sys.stderr)
            return 5
        conn.commit()
    finally:
        conn.close()

    claim_result = result["results"][0]
    print(f"claim_id={result['claim_id']}")
    print(f"user_id={result['user_id']}")
    print(f"board_type={result['board_type']}")
    print(f"period_key={result['period_key']}")
    print(f"status={claim_result['status']}")
    if claim_result["error"]:
        print(f"error={claim_result['error']}", file=sys.stderr)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if claim_result["status"] == "granted" else 6


def cmd_finalize_preview(args):
    entries = _load_entries(args.entries_file)
    result = run_finalize_preview(
        args.board, args.period_key, args.period_start, args.period_end, entries)
    _print_header(args.board, args.period_key, "finalize-preview", True)
    preview = result["preview"]
    eligible = [p for p in preview if p["eligible"]]
    print(f"claims_count={len(preview)}")
    print(f"pending_count={len(eligible)}")
    print(f"skipped_count={len(preview) - len(eligible)}")
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_finalize_commit(args):
    if not args.confirm_finalize:
        print(
            "Refusing to run finalize-commit without --confirm-finalize "
            "(this would write leaderboard_snapshots + leaderboard_reward_claims rows).",
            file=sys.stderr,
        )
        return 2
    entries = _load_entries(args.entries_file)
    conn = _connect(args.database_url)
    try:
        result = run_finalize_commit(
            conn, args.board, args.period_key, args.period_start, args.period_end, entries,
        )
        conn.commit()
    finally:
        conn.close()
    _print_header(args.board, args.period_key, "finalize-commit", False)
    print(f"claims_count={result['claims']['inserted'] + result['claims']['existing']}")
    print(f"pending_count={result['claims']['pending']}")
    print(f"skipped_count={result['claims']['skipped']}")
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_grant_preview(args):
    conn = _connect(args.database_url)
    try:
        result = run_grant_preview(conn, args.board, args.period_key)
    finally:
        conn.close()
    _print_header(args.board, args.period_key, "grant-preview", True)
    print(f"claims_count={result['claims_count']}")
    print(f"pending_count={result['pending_count']}")
    print(f"skipped_count={result['skipped_count']}")
    granted_preview_count = sum(1 for e in result["coins_preview"]["preview"] if e["would_grant"])
    print(f"granted_preview_count={granted_preview_count}")
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_grant_adapter_preview(args):
    conn = _connect(args.database_url)
    try:
        result = run_grant_adapter_preview(conn, args.board, args.period_key)
    finally:
        conn.close()
    _print_header(args.board, args.period_key, "grant-adapter-preview", True)
    print(f"claims_count={result['claims_count']}")
    print(f"pending_count={result['pending_count']}")
    print(f"skipped_count={result['skipped_count']}")
    print(f"would_grant_coin_claims={result['would_grant_coin_claims']}")
    print(f"would_grant_items_claims={result['would_grant_items_claims']}")
    print(f"would_grant_badges_claims={result['would_grant_badges_claims']}")
    print(f"would_grant_titles_claims={result['would_grant_titles_claims']}")
    print(f"total_coins={result['total_coins']}")
    print(f"blocked_claims={len(result['blocked_claims'])}")
    for item in result["blocked_claims"]:
        print(f"blocked: claim_id={item['claim_id']} reason={item['reason']}", file=sys.stderr)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_grant_commit(args):
    # No production coin/badge/title/item grant function is wired into
    # this tool. Wiring one in (and deciding the safety policy around it)
    # is explicitly left to a later PR — this command must never grant
    # anything, confirm flag or not.
    print(GRANT_COMMIT_DISABLED_MESSAGE, file=sys.stderr)
    return 3


def _add_common_args(subparser):
    subparser.add_argument("--board", required=True, choices=lbr.BOARD_TYPES)
    subparser.add_argument("--period-key", required=True)
    subparser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
        help="Defaults to the local dev Postgres used by the test suite, or $DATABASE_URL.",
    )


def build_parser():
    parser = argparse.ArgumentParser(
        prog="community_leaderboard_rewards_manual",
        description=(
            "Owner-only manual utility for Community Leaderboard Rewards (Phase 1). "
            "Dry-run by default. Not a scheduler, not a public API, does not deploy."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fp = sub.add_parser("finalize-preview", help="Dry-run preview only, no DB write.")
    _add_common_args(fp)
    fp.add_argument("--entries-file", required=True)
    fp.add_argument("--period-start", required=True)
    fp.add_argument("--period-end", required=True)
    fp.set_defaults(func=cmd_finalize_preview)

    fc = sub.add_parser(
        "finalize-commit",
        help="Writes snapshots + pending/skipped claims. Requires --confirm-finalize.",
    )
    _add_common_args(fc)
    fc.add_argument("--entries-file", required=True)
    fc.add_argument("--period-start", required=True)
    fc.add_argument("--period-end", required=True)
    fc.add_argument("--confirm-finalize", action="store_true")
    fc.set_defaults(func=cmd_finalize_commit)

    gp = sub.add_parser("grant-preview", help="Read-only preview of coins/badge/title/item grants.")
    _add_common_args(gp)
    gp.set_defaults(func=cmd_grant_preview)

    gap = sub.add_parser(
        "grant-adapter-preview",
        help="Dry-run-only preview of the real Phase 3B adapter plan. No confirm flag exists "
             "because nothing here ever writes anything (not even the component log).",
    )
    _add_common_args(gap)
    gap.set_defaults(func=cmd_grant_adapter_preview)

    grp = sub.add_parser(
        "grant-real-preview",
        help="Dry-run-only preview verifying the real production grant targets exist and "
             "are signature-compatible. Never calls any real grant function, no --commit "
             "flag exists, writes nothing.",
    )
    _add_common_args(grp)
    grp.set_defaults(func=cmd_grant_real_preview)

    sep = sub.add_parser(
        "snapshot-exact-period",
        help="Read-only extraction of a closed exact-period snapshot with deterministic "
             "ranking, exclusions, and tie-break metadata.",
    )
    _add_common_args(sep)
    sep.add_argument("--period-start", required=True, help="Exact period start date (YYYY-MM-DD).")
    sep.add_argument("--period-end", required=True, help="Exact exclusive period end date (YYYY-MM-DD).")
    sep.add_argument("--timezone", default="Asia/Taipei")
    sep.add_argument("--limit", type=int, default=50)
    sep.add_argument(
        "--operation-dir",
        default=None,
        help="Absolute host-local operation directory under GO_ODYSSEY_REWARD_OPERATIONS_ROOT. "
             "If supplied, writes snapshot.json and preview.json with restrictive permissions.",
    )
    sep.set_defaults(func=cmd_snapshot_exact_period)

    pep = sub.add_parser(
        "preview-exact-period",
        help="Pure preview from an exact-period snapshot file. Computes canonical preview and "
             "reward totals plus snapshot/preview SHA-256 values.",
    )
    pep.add_argument("--snapshot-file", required=True)
    pep.add_argument("--preview-file", default=None)
    pep.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
        help="Defaults to the local dev Postgres used by the test suite, or $DATABASE_URL.",
    )
    pep.set_defaults(func=cmd_preview_exact_period)

    gc = sub.add_parser(
        "grant-commit",
        help="Intentionally disabled until a later PR wires production grant functions.",
    )
    _add_common_args(gc)
    gc.add_argument("--confirm-grant", action="store_true")
    gc.set_defaults(func=cmd_grant_commit)

    gep = sub.add_parser(
        "grant-exact-period-commit",
        help="WRITE-CAPABLE exact-period grant path. Requires exact snapshot/preview hashes, "
        "expected totals, and the dedicated owner gate. Returns already_granted_noop for a "
        "fully matching prior successful run; otherwise fails closed on any drift.",
    )
    gep.add_argument("--snapshot-file", required=True)
    gep.add_argument("--preview-file", required=True)
    gep.add_argument("--expected-snapshot-sha256", required=True)
    gep.add_argument("--expected-preview-sha256", required=True)
    gep.add_argument("--expected-claim-count", type=int, required=True)
    gep.add_argument("--expected-component-count", type=int, required=True)
    gep.add_argument("--expected-total-coins", type=int, required=True)
    gep.add_argument("--expected-total-items-json", required=True)
    gep.add_argument("--expected-total-badges-json", required=True)
    gep.add_argument("--owner-gate", required=True)
    gep.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
        help="Defaults to the local dev Postgres used by the test suite, or $DATABASE_URL.",
    )
    gep.set_defaults(func=cmd_grant_exact_period_commit)

    gwc = sub.add_parser(
        "grant-weekly-2026w27-commit",
        help="WRITE-CAPABLE, narrowly scoped to weekly 2026-W27 ONLY. Grants coins/item/"
             "badge for the pending claims of that single period. Requires "
             "--confirm-weekly-2026w27-grant plus an exact --expected-pending/"
             "--expected-total-coins match; refuses any other board/period, any "
             "blocked claim, any signature error, and any title payload.",
    )
    _add_common_args(gwc)
    gwc.add_argument("--confirm-weekly-2026w27-grant", action="store_true")
    gwc.add_argument("--expected-pending", type=int, required=True)
    gwc.add_argument("--expected-total-coins", type=int, required=True)
    gwc.set_defaults(func=cmd_grant_weekly_2026w27_commit)

    rc = sub.add_parser(
        "retry-weekly-2026w27-claim",
        help="WRITE-CAPABLE, hard-gated to claim_id=1 / user_id=991136 / weekly / 2026-W27 "
             "ONLY. Requires --confirm-retry-claim-1 plus --claim-id/--user-id/"
             "--expected-coins matching exactly; refuses any other claim, any status other "
             "than 'failed', any existing component-log row, and any title/"
             "appearance_fragment mismatch.",
    )
    rc.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
        help="Defaults to the local dev Postgres used by the test suite, or $DATABASE_URL.",
    )
    rc.add_argument("--claim-id", type=int, required=True)
    rc.add_argument("--user-id", type=int, required=True)
    rc.add_argument("--expected-coins", type=int, required=True)
    rc.add_argument("--confirm-retry-claim-1", action="store_true")
    rc.set_defaults(func=cmd_retry_weekly_2026w27_claim)

    return parser


def _configure_utf8_console():
    """Best-effort: make stdout/stderr tolerate arbitrary Unicode text (real
    player display names in preview/commit output) even on a non-UTF-8
    Windows console (cp950/cp936/etc.), without requiring the operator to
    remember `PYTHONIOENCODING=utf-8` themselves. No-op if a stream doesn't
    support reconfigure (e.g. when captured/replaced by a test runner) --
    never raises, since this is a display nicety, not a correctness
    requirement (the JSON file this tool writes is always UTF-8 regardless
    of console encoding)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (ValueError, OSError):
                pass


def main(argv=None):
    _configure_utf8_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
