import datetime
import hashlib
import json
import logging
import os
import socket
import stat
import subprocess
import time
import urllib.parse
import zlib
from pathlib import Path
from zoneinfo import ZoneInfo

import community_leaderboard_rewards as lbr
from tools.community_leaderboard_rewards_exact_period import (
    ComponentSettlementError,
    build_exact_period_preview,
    build_exact_period_snapshot,
    commit_exact_period,
    create_scheduler_commit_authorization,
    evaluate_settled_components,
    expected_component_rows,
    fetch_claims_for_period,
    fetch_component_logs_for_claim_ids,
)


COMMUNITY_LEADERBOARD_REWARDS_ENABLED = "COMMUNITY_LEADERBOARD_REWARDS_ENABLED"
DEFAULT_OPERATIONS_ROOT = Path("/opt/go-odyssey/reward-operations")
SCHEDULER_TIMEZONE = "Asia/Taipei"
SCHEDULE_WEEKDAY = 0  # Monday
SCHEDULE_HOUR = 0
SCHEDULE_MINUTE = 10
SCHEDULER_WAKE_INTERVAL_SECONDS = 60
LOCK_NAMESPACE = "community_leaderboard_rewards"
LOCK_BOARD_TYPE = lbr.BOARD_TYPE_WEEKLY
SNAPSHOT_FILENAME = "snapshot.json"
PREVIEW_FILENAME = "preview.json"
GRANT_RESULT_FILENAME = "grant-result.json"


def _logger_for(app_module):
    app_obj = getattr(app_module, "app", None)
    if app_obj is not None and getattr(app_obj, "logger", None) is not None:
        return app_obj.logger
    return logging.getLogger("community_leaderboard_rewards_scheduler")


def _community_rewards_flag_enabled(app_module):
    exact_reader = getattr(app_module, "_env_flag_exact_true", None)
    if callable(exact_reader):
        return bool(exact_reader(COMMUNITY_LEADERBOARD_REWARDS_ENABLED))
    raw = os.environ.get(COMMUNITY_LEADERBOARD_REWARDS_ENABLED)
    return bool(raw is not None and raw.strip().lower() == "true")


def resolve_scheduler_now(now=None, timezone=SCHEDULER_TIMEZONE):
    tz = ZoneInfo(timezone)
    if now is None:
        return datetime.datetime.now(tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def get_weekly_scheduler_target(now=None, timezone=SCHEDULER_TIMEZONE):
    now_at = resolve_scheduler_now(now=now, timezone=timezone)
    current_week_start_date = now_at.date() - datetime.timedelta(days=now_at.weekday())
    current_week_start_at = datetime.datetime.combine(
        current_week_start_date, datetime.time.min, tzinfo=now_at.tzinfo
    )
    due_at = current_week_start_at.replace(hour=SCHEDULE_HOUR, minute=SCHEDULE_MINUTE)
    period_end_exclusive = current_week_start_date
    period_start = period_end_exclusive - datetime.timedelta(days=7)
    return {
        "timezone": timezone,
        "now_at": now_at,
        "due_at": due_at,
        "is_due": now_at >= due_at,
        "board_type": lbr.BOARD_TYPE_WEEKLY,
        "period_key": lbr.format_leaderboard_period_key(lbr.BOARD_TYPE_WEEKLY, period_start),
        "period_start": period_start.isoformat(),
        "period_end_exclusive": period_end_exclusive.isoformat(),
    }


def next_scheduler_check_at(now=None, timezone=SCHEDULER_TIMEZONE):
    now_at = resolve_scheduler_now(now=now, timezone=timezone)
    target = get_weekly_scheduler_target(now=now_at, timezone=timezone)
    if not target["is_due"]:
        return target["due_at"]
    next_week_due = target["due_at"] + datetime.timedelta(days=7)
    return min(now_at + datetime.timedelta(seconds=SCHEDULER_WAKE_INTERVAL_SECONDS), next_week_due)


def advisory_lock_keys(board_type, period_key):
    namespace_key = zlib.crc32(LOCK_NAMESPACE.encode("utf-8")) & 0x7FFFFFFF
    scope_key = zlib.crc32(f"{board_type}:{period_key}".encode("utf-8")) & 0x7FFFFFFF
    return namespace_key, scope_key


def try_acquire_period_lock(conn, board_type, period_key):
    namespace_key, scope_key = advisory_lock_keys(board_type, period_key)
    row = conn.execute(
        "SELECT pg_try_advisory_lock(%s, %s)",
        (int(namespace_key), int(scope_key)),
    ).fetchone()
    return bool(row[0]) if row else False


def release_period_lock(conn, board_type, period_key):
    namespace_key, scope_key = advisory_lock_keys(board_type, period_key)
    conn.execute(
        "SELECT pg_advisory_unlock(%s, %s)",
        (int(namespace_key), int(scope_key)),
    )


def _database_identity(database_url):
    parsed = urllib.parse.urlsplit((database_url or "").strip())
    scheme = parsed.scheme or "unknown"
    host = parsed.hostname or "unknown-host"
    port = f":{parsed.port}" if parsed.port else ""
    dbname = (parsed.path or "").lstrip("/") or "unknown-db"
    return f"{scheme}://{host}{port}/{dbname}"


def _sha256_hex_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _environment_identity():
    return {
        "hostname": socket.gethostname(),
        "production_flag": str(os.environ.get("PRODUCTION", "")),
    }


def _reject_symlink_path(path):
    current = Path(path.anchor) if path.is_absolute() else Path(".")
    parts = path.parts[1:] if path.is_absolute() else path.parts
    for part in parts:
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


def _reject_git_worktree_path(path):
    probe = Path(path).resolve(strict=False)
    for candidate in (probe, *probe.parents):
        git_marker = candidate / ".git"
        if git_marker.exists():
            raise ValueError(f"git working-tree paths are forbidden for reward operations: {path}")
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(probe),
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return
    if result.returncode == 0 and result.stdout.strip():
        raise ValueError(f"git working-tree paths are forbidden for reward operations: {path}")


def _validate_operation_dir(root, period_key):
    root = Path(root)
    if not root.is_absolute():
        raise ValueError("operations root must be an absolute path")
    _reject_symlink_path(root)
    _reject_git_worktree_path(root)
    _ensure_restrictive_directory(root)
    target = root / period_key
    if target.exists():
        _reject_symlink_path(target)
    else:
        _reject_symlink_path(target.parent)
    _ensure_restrictive_directory(target)
    try:
        resolved_root = root.resolve(strict=True)
        resolved_target = target.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"operation directory missing unexpectedly: {exc}") from exc
    if resolved_target != resolved_root and resolved_root not in resolved_target.parents:
        raise ValueError("operation directory escaped the configured root")
    return target


def _write_exact_json(path, payload, *, replace=False):
    path = Path(path)
    _reject_symlink_path(path)
    data = lbr.canonical_json_dumps(payload).encode("utf-8")
    if replace and path.exists():
        if path.is_symlink():
            raise ValueError(f"symlink files are forbidden for reward operations: {path}")
        if _is_world_writable(path):
            raise ValueError(f"world-writable file is forbidden: {path}")
        tmp = path.with_name(f".{path.name}.tmp")
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(str(tmp), str(path))
        if os.name != "nt":
            os.chmod(path, 0o600)
    elif path.exists():
        existing = path.read_bytes()
        if existing != data:
            raise ValueError(f"existing operation file identity differs: {path}")
    else:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(str(path), flags, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        if os.name != "nt":
            os.chmod(path, 0o600)
    written = path.read_bytes()
    if written != data:
        raise ValueError(f"operation file bytes changed unexpectedly after write: {path}")
    return path


def build_preview_identity_record(snapshot, preview, *, database_url, snapshot_file):
    return {
        "board_type": snapshot["board_type"],
        "period_key": snapshot["period_key"],
        "period_start": snapshot["period_start"],
        "period_end_exclusive": snapshot["period_end_exclusive"],
        "timezone": snapshot["timezone"],
        "database_identity": _database_identity(database_url),
        "environment_identity": _environment_identity(),
        "snapshot_file": str(snapshot_file),
        "snapshot_file_sha256": _sha256_hex_bytes(snapshot_file.read_bytes()),
        "snapshot_sha256": preview["snapshot_sha256"],
        "preview_sha256": preview["preview_sha256"],
        "summary": preview["summary"],
    }


def validate_preview_identity(preview_identity, *, snapshot, snapshot_file, database_url):
    if preview_identity.get("snapshot_file_sha256") != _sha256_hex_bytes(snapshot_file.read_bytes()):
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


def build_grant_result_record(snapshot, preview_identity, result, *, duration_seconds):
    return {
        "board_type": snapshot["board_type"],
        "period_key": snapshot["period_key"],
        "period_start": snapshot["period_start"],
        "period_end_exclusive": snapshot["period_end_exclusive"],
        "timezone": snapshot["timezone"],
        "database_identity": preview_identity["database_identity"],
        "environment_identity": preview_identity["environment_identity"],
        "snapshot_sha256": result["snapshot_sha256"],
        "preview_sha256": result["preview_sha256"],
        "result": result["result"],
        "summary": result["summary"],
        "duration_seconds": round(float(duration_seconds), 3),
    }


def summarize_post_grant_state(
    conn,
    *,
    board_type,
    period_key,
    expected_components,
    badge_ownership_checker=None,
):
    claim_row = conn.execute(
        "SELECT COUNT(*), "
        "SUM(CASE WHEN status = 'granted' THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN status <> 'granted' THEN 1 ELSE 0 END), "
        "COALESCE(SUM(granted_coins), 0), "
        "SUM(CASE WHEN notification_acknowledged_at IS NULL THEN 1 ELSE 0 END) "
        "FROM leaderboard_reward_claims WHERE board_type = %s AND period_key = %s",
        (board_type, period_key),
    ).fetchone()
    claims = fetch_claims_for_period(conn, board_type, period_key)
    claim_by_id = {int(claim["id"]): claim for claim in claims}
    component_logs = fetch_component_logs_for_claim_ids(conn, list(claim_by_id))
    actual_components = []
    for item in component_logs:
        claim = claim_by_id.get(int(item["claim_id"]))
        if claim is None:
            continue
        actual_components.append({
            "rank": int(claim["rank"]),
            "user_id": int(claim["user_id"]),
            "component": item["component"],
            "reward_key": item["reward_key"],
            "quantity": int(item["quantity"]),
            "result": item["result"],
            "detail": item.get("detail"),
        })
    settlement = evaluate_settled_components(
        expected_components,
        actual_components,
        badge_ownership_checker=badge_ownership_checker,
    )
    satisfied = settlement.get("satisfied_components") or []
    total_items = {}
    total_badges = {}
    for component in satisfied:
        if component["component"] == "item":
            total_items[component["reward_key"]] = (
                total_items.get(component["reward_key"], 0) + int(component["quantity"])
            )
        elif component["component"] == "badge":
            total_badges[component["reward_key"]] = (
                total_badges.get(component["reward_key"], 0) + int(component["quantity"])
            )
    return {
        "claims_count": int(claim_row[0] or 0),
        "granted_claim_count": int(claim_row[1] or 0),
        "non_granted_claim_count": int(claim_row[2] or 0),
        "total_coins": int(claim_row[3] or 0),
        "unacknowledged_notification_count": int(claim_row[4] or 0),
        "component_count": len(component_logs),
        "total_items": total_items,
        "total_badges": total_badges,
        "component_settlement": settlement,
    }


def log_scheduler_result(logger, result):
    payload = {
        "result": result["result"],
        "period_key": result.get("period_key"),
        "board": result.get("board_type"),
        "claim_count": result.get("claim_count"),
        "component_count": result.get("component_count"),
        "total_coins": result.get("total_coins"),
        "items": result.get("total_items"),
        "badges": result.get("total_badges"),
        "snapshot_sha_prefix": (result.get("snapshot_sha256") or "")[:12],
        "preview_sha_prefix": (result.get("preview_sha256") or "")[:12],
        "duration_seconds": result.get("duration_seconds"),
    }
    logger.info("[community_leaderboard_weekly] %s", lbr.canonical_json_dumps(payload))


def log_scheduler_failure(logger, result):
    """Emit a Production-visible failure without exception or recipient data.

    Exception messages and tracebacks are deliberately excluded: errors raised by
    downstream reward adapters may contain user-level or database details.  The
    stable job/result/period/type fields are sufficient to alert operators while
    the transaction remains fail-closed.
    """
    payload = {
        "job": "community_leaderboard_weekly",
        "result": "failed_closed",
        "period_key": result.get("period_key"),
        "exception_type": result.get("error_type"),
    }
    if result.get("reason_code"):
        payload["reason_code"] = result["reason_code"]
    logger.error("[community_leaderboard_weekly] %s", lbr.canonical_json_dumps(payload))


def run_community_leaderboard_weekly_cycle(app_module, *, now=None, operations_root=None):
    logger = _logger_for(app_module)
    started_at = time.monotonic()
    flag_enabled = _community_rewards_flag_enabled(app_module)
    if not flag_enabled:
        result = {
            "result": "disabled_noop",
            "board_type": lbr.BOARD_TYPE_WEEKLY,
            "period_key": None,
            "claim_count": 0,
            "component_count": 0,
            "total_coins": 0,
            "total_items": {},
            "total_badges": {},
            "duration_seconds": round(time.monotonic() - started_at, 3),
        }
        log_scheduler_result(logger, result)
        return result

    target = get_weekly_scheduler_target(now=now, timezone=SCHEDULER_TIMEZONE)
    if not target["is_due"]:
        result = {
            "result": "not_due_noop",
            "board_type": target["board_type"],
            "period_key": target["period_key"],
            "claim_count": 0,
            "component_count": 0,
            "total_coins": 0,
            "total_items": {},
            "total_badges": {},
            "duration_seconds": round(time.monotonic() - started_at, 3),
        }
        log_scheduler_result(logger, result)
        return result

    database_url = os.environ.get("DATABASE_URL", "")
    operations_root = Path(operations_root or DEFAULT_OPERATIONS_ROOT)
    conn = app_module.get_db()
    badge_owned_fn = getattr(app_module, "is_community_reward_badge_owned", None)
    badge_ownership_checker = None
    if callable(badge_owned_fn):
        badge_ownership_checker = lambda user_id, badge_key: badge_owned_fn(
            conn, user_id=user_id, badge_key=badge_key
        )
    lock_acquired = False
    try:
        lock_acquired = try_acquire_period_lock(conn, target["board_type"], target["period_key"])
        if not lock_acquired:
            result = {
                "result": "lock_busy_noop",
                "board_type": target["board_type"],
                "period_key": target["period_key"],
                "claim_count": 0,
                "component_count": 0,
                "total_coins": 0,
                "total_items": {},
                "total_badges": {},
                "duration_seconds": round(time.monotonic() - started_at, 3),
            }
            conn.rollback()
            log_scheduler_result(logger, result)
            return result

        operation_dir = _validate_operation_dir(operations_root, target["period_key"])
        snapshot = build_exact_period_snapshot(
            conn,
            board_type=target["board_type"],
            period_key=target["period_key"],
            period_start=target["period_start"],
            period_end_exclusive=target["period_end_exclusive"],
            timezone=SCHEDULER_TIMEZONE,
            limit=50,
        )
        preview = build_exact_period_preview(snapshot)
        if preview["snapshot_sha256"] != lbr.sha256_hex_from_value(snapshot):
            raise ValueError("snapshot SHA verification failed")
        preview_payload = dict(preview)
        preview_payload.pop("preview_sha256", None)
        if preview["preview_sha256"] != lbr.sha256_hex_from_value(preview_payload):
            raise ValueError("preview SHA verification failed")

        snapshot_file = _write_exact_json(operation_dir / SNAPSHOT_FILENAME, snapshot)
        preview_identity = build_preview_identity_record(
            snapshot, preview, database_url=database_url, snapshot_file=snapshot_file
        )
        preview_file = _write_exact_json(operation_dir / PREVIEW_FILENAME, preview_identity)
        validate_preview_identity(
            json.loads(preview_file.read_text(encoding="utf-8")),
            snapshot=snapshot,
            snapshot_file=snapshot_file,
            database_url=database_url,
        )

        result = commit_exact_period(
            conn,
            snapshot=snapshot,
            expected_snapshot_sha256=preview["snapshot_sha256"],
            expected_preview_sha256=preview["preview_sha256"],
            expected_claim_count=preview["summary"]["claims_count"],
            expected_component_count=preview["summary"]["component_count"],
            expected_total_coins=preview["summary"]["total_coins"],
            expected_total_items=preview["summary"]["total_items"],
            expected_total_badges=preview["summary"]["total_badges"],
            scheduler_authorization=create_scheduler_commit_authorization(
                board_type=target["board_type"],
                period_key=target["period_key"],
                flag_enabled=flag_enabled,
            ),
            badge_ownership_checker=badge_ownership_checker,
            now=target["now_at"],
        )
        post_state = summarize_post_grant_state(
            conn,
            board_type=target["board_type"],
            period_key=target["period_key"],
            expected_components=expected_component_rows(preview["preview"]),
            badge_ownership_checker=badge_ownership_checker,
        )
        if not post_state["component_settlement"]["settled"]:
            raise ComponentSettlementError(
                post_state["component_settlement"]["reason_code"],
                post_state["component_settlement"]["reason"],
            )
        if post_state["claims_count"] != int(preview["summary"]["claims_count"]):
            raise ValueError("post-grant claims count mismatch")
        if post_state["component_count"] != int(preview["summary"]["component_count"]):
            raise ValueError("post-grant component count mismatch")
        if post_state["total_coins"] != int(preview["summary"]["total_coins"]):
            raise ValueError("post-grant total coins mismatch")
        if post_state["total_items"] != dict(preview["summary"]["total_items"]):
            raise ValueError("post-grant item totals mismatch")
        if post_state["total_badges"] != dict(preview["summary"]["total_badges"]):
            raise ValueError("post-grant badge totals mismatch")

        duration_seconds = round(time.monotonic() - started_at, 3)
        conn.commit()
        grant_result_record = build_grant_result_record(snapshot, preview_identity, result, duration_seconds=duration_seconds)
        _write_exact_json(operation_dir / GRANT_RESULT_FILENAME, grant_result_record, replace=True)
        scheduler_result_name = "granted" if result["result"] == "committed" else result["result"]
        scheduler_result = {
            "result": scheduler_result_name,
            "board_type": target["board_type"],
            "period_key": target["period_key"],
            "snapshot_sha256": result["snapshot_sha256"],
            "preview_sha256": result["preview_sha256"],
            "claim_count": post_state["claims_count"],
            "component_count": post_state["component_count"],
            "total_coins": post_state["total_coins"],
            "total_items": post_state["total_items"],
            "total_badges": post_state["total_badges"],
            "duration_seconds": duration_seconds,
        }
        log_scheduler_result(logger, scheduler_result)
        return scheduler_result
    except Exception as exc:
        conn.rollback()
        failed_result = {
            "result": "failed_closed",
            "board_type": target.get("board_type"),
            "period_key": target.get("period_key"),
            "claim_count": 0,
            "component_count": 0,
            "total_coins": 0,
            "total_items": {},
            "total_badges": {},
            "duration_seconds": round(time.monotonic() - started_at, 3),
            # Preserve the established public exception class while the
            # reason_code provides the new non-personal classification.
            "error_type": "ValueError" if isinstance(exc, ValueError) else type(exc).__name__,
            "reason_code": getattr(exc, "reason_code", None),
        }
        log_scheduler_failure(logger, failed_result)
        return failed_result
    finally:
        if lock_acquired:
            try:
                release_period_lock(conn, target["board_type"], target["period_key"])
            except Exception:
                logger.exception("[community_leaderboard_weekly] advisory unlock failed")
        conn.close()
