import datetime
import json
import os
import zlib

import community_leaderboard_rewards as lbr


_CLAIM_COLUMNS = [
    "id", "user_id", "board_type", "period_key", "rank", "rank_band", "score",
    "eligible", "ineligible_reason", "reward_bundle_key", "granted_coins",
    "granted_items_json", "granted_badges_json", "granted_titles_json",
    "status", "error_message", "created_at", "granted_at", "notification_acknowledged_at",
]

_SNAPSHOT_COLUMNS = [
    "board_type", "period_key", "period_start", "period_end", "user_id",
    "display_name_snapshot", "avatar_snapshot", "rank", "score", "eligible",
    "rank_band", "created_at",
]

COMMUNITY_LEADERBOARD_REWARDS_ENABLED = "COMMUNITY_LEADERBOARD_REWARDS_ENABLED"
_SCHEDULER_LOCK_NAMESPACE = "community_leaderboard_rewards"


class _SchedulerCommitAuthorization:
    __slots__ = ("board_type", "period_key", "flag_name", "flag_enabled")

    def __init__(self, *, board_type, period_key, flag_name, flag_enabled):
        self.board_type = str(board_type)
        self.period_key = str(period_key)
        self.flag_name = str(flag_name)
        self.flag_enabled = bool(flag_enabled)


def create_scheduler_commit_authorization(*, board_type, period_key, flag_enabled):
    return _SchedulerCommitAuthorization(
        board_type=board_type,
        period_key=period_key,
        flag_name=COMMUNITY_LEADERBOARD_REWARDS_ENABLED,
        flag_enabled=flag_enabled,
    )


def _advisory_lock_keys(board_type, period_key):
    namespace_key = zlib.crc32(_SCHEDULER_LOCK_NAMESPACE.encode("utf-8")) & 0x7FFFFFFF
    scope_key = zlib.crc32(f"{board_type}:{period_key}".encode("utf-8")) & 0x7FFFFFFF
    return namespace_key, scope_key


def scheduler_period_lock_is_held(conn, *, board_type, period_key):
    namespace_key, scope_key = _advisory_lock_keys(board_type, period_key)
    try:
        row = conn.execute(
            "SELECT EXISTS("
            "SELECT 1 FROM pg_locks "
            "WHERE locktype = 'advisory' "
            "AND classid = %s "
            "AND objid = %s "
            "AND pid = pg_backend_pid() "
            "AND granted = TRUE"
            ")",
            (int(namespace_key), int(scope_key)),
        ).fetchone()
    except Exception:
        return False
    return bool(row[0]) if row else False


def _validate_commit_authorization(
    conn,
    snapshot,
    *,
    owner_gate,
    required_owner_gate,
    scheduler_authorization,
):
    using_owner_gate = owner_gate is not None
    using_scheduler_auth = scheduler_authorization is not None
    if using_owner_gate == using_scheduler_auth:
        raise ValueError("exactly one authorization path must be provided")
    if using_owner_gate:
        if owner_gate != required_owner_gate:
            raise ValueError(f"owner gate mismatch: expected {required_owner_gate}")
        return "manual"
    if not isinstance(scheduler_authorization, _SchedulerCommitAuthorization):
        raise ValueError("scheduler authorization token mismatch")
    if scheduler_authorization.flag_name != COMMUNITY_LEADERBOARD_REWARDS_ENABLED:
        raise ValueError("scheduler authorization flag mismatch")
    if not scheduler_authorization.flag_enabled:
        raise ValueError("scheduler authorization requires the canonical enable flag")
    if str(os.environ.get(COMMUNITY_LEADERBOARD_REWARDS_ENABLED, "")).strip().lower() != "true":
        raise ValueError("scheduler authorization requires COMMUNITY_LEADERBOARD_REWARDS_ENABLED=true")
    if scheduler_authorization.board_type != snapshot["board_type"] or scheduler_authorization.period_key != snapshot["period_key"]:
        raise ValueError("scheduler authorization period mismatch")
    if not scheduler_period_lock_is_held(
        conn,
        board_type=snapshot["board_type"],
        period_key=snapshot["period_key"],
    ):
        raise ValueError("scheduler authorization requires a held advisory lock")
    return "scheduler"


def _parse_date(value, label):
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{label} must be YYYY-MM-DD")
    return datetime.date.fromisoformat(value)


def _period_bounds(board_type, period_key, period_start, period_end_exclusive, timezone):
    start_date = _parse_date(period_start, "period_start")
    end_date = _parse_date(period_end_exclusive, "period_end_exclusive")
    return lbr.validate_exact_period_bounds(
        board_type,
        period_key,
        start_date,
        end_date,
        timezone=timezone,
    )


def _utc_naive_iso(dt):
    return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None).isoformat()


def build_exact_period_snapshot(
    conn,
    *,
    board_type,
    period_key,
    period_start,
    period_end_exclusive,
    timezone="Asia/Taipei",
    limit=50,
):
    bounds = _period_bounds(board_type, period_key, period_start, period_end_exclusive, timezone)
    participants = lbr.fetch_leaderboard_participant_rows(
        conn,
        _utc_naive_iso(bounds["period_start_at"]),
        _utc_naive_iso(bounds["period_end_exclusive_at"]),
        limit=None,
    )
    ranked_rows = lbr.rank_leaderboard_participants(participants)
    top_rows = ranked_rows[:limit]
    entries = lbr.leaderboard_rows_to_entries(top_rows)
    reward_preview = lbr.finalize_leaderboard_reward_period(
        None,
        board_type,
        period_key,
        bounds["period_start_date"].isoformat(),
        (bounds["period_end_date"] - datetime.timedelta(days=1)).isoformat(),
        entries,
        dry_run=True,
    )
    summary = lbr.summarize_preview_rewards(reward_preview["preview"])
    rank_changes = []
    original_ranks = {int(dict(row)["id"]): index for index, row in enumerate(participants, start=1)}
    for row in top_rows:
        user_id = int(row["user_id"])
        rank_changes.append({
            "user_id": user_id,
            "display_name": row["display_name"],
            "original_rank": original_ranks.get(user_id),
            "revised_rank": int(row["rank"]),
            "rank_delta": None if original_ranks.get(user_id) is None else original_ranks[user_id] - int(row["rank"]),
        })
    return {
        "board_type": board_type,
        "period_key": period_key,
        "timezone": timezone,
        "period_start": bounds["period_start_date"].isoformat(),
        "period_end_exclusive": bounds["period_end_date"].isoformat(),
        "period_start_at": bounds["period_start_at"].isoformat(),
        "period_end_exclusive_at": bounds["period_end_exclusive_at"].isoformat(),
        "period_start_utc_naive": _utc_naive_iso(bounds["period_start_at"]),
        "period_end_utc_naive": _utc_naive_iso(bounds["period_end_exclusive_at"]),
        "policy": {
            "admin_accounts_eligible": True,
            "test_accounts_eligible": True,
            "ranking_order": [
                "score DESC",
                "final_counted_distinct_question_at ASC",
                "user_id ASC",
            ],
            "distinct_question_scoring": True,
        },
        "participant_counts": {
            "original_participant_count": len(participants),
            "ranked_participant_count": len(ranked_rows),
            "top_ranked_row_count": len(top_rows),
            "reward_eligible_count": summary["eligible_claim_count"],
        },
        "excluded_accounts": [],
        "rank_changes": rank_changes,
        "entries": entries,
        "top_rows": [
            {
                "rank": int(row["rank"]),
                "user_id": int(row["user_id"]),
                "username": row["username"],
                "display_name": row["display_name"],
                "score": int(row["score"]),
                "final_counted_at": row["final_counted_at"],
                "rank_level": row.get("rank_level"),
                "avatar": row.get("character_key") or None,
            }
            for row in top_rows
        ],
        "preview_summary": summary,
    }


def build_exact_period_preview(snapshot):
    preview = lbr.finalize_leaderboard_reward_period(
        None,
        snapshot["board_type"],
        snapshot["period_key"],
        snapshot["period_start"],
        (
            datetime.date.fromisoformat(snapshot["period_end_exclusive"])
            - datetime.timedelta(days=1)
        ).isoformat(),
        snapshot["entries"],
        dry_run=True,
    )
    summary = lbr.summarize_preview_rewards(preview["preview"])
    result = {
        "board_type": snapshot["board_type"],
        "period_key": snapshot["period_key"],
        "period_start": snapshot["period_start"],
        "period_end_exclusive": snapshot["period_end_exclusive"],
        "timezone": snapshot["timezone"],
        "participant_counts": snapshot["participant_counts"],
        "excluded_accounts": snapshot["excluded_accounts"],
        "preview": preview["preview"],
        "summary": summary,
    }
    result["snapshot_sha256"] = lbr.sha256_hex_from_value(snapshot)
    result["preview_sha256"] = lbr.sha256_hex_from_value(result)
    return result


def exact_period_component_totals_match(preview_summary, *, expected_component_count, expected_total_coins,
                                        expected_total_items, expected_total_badges):
    return (
        int(preview_summary["component_count"]) == int(expected_component_count)
        and int(preview_summary["total_coins"]) == int(expected_total_coins)
        and dict(preview_summary["total_items"]) == dict(expected_total_items)
        and dict(preview_summary["total_badges"]) == dict(expected_total_badges)
    )


def _snapshot_for_live_drift_check(snapshot):
    """Remove only mutable cosmetic fields from the live-source comparison.

    The persisted snapshot and preview hashes remain exact and unchanged.  This
    projection is used only when rebuilding the closed period from live source:
    avatar and rank level can legitimately change after the period closes, but
    neither affects ranking, eligibility, recipients, or reward amounts.
    """
    projected = dict(snapshot)
    projected["entries"] = [
        {key: value for key, value in entry.items() if key != "avatar"}
        for entry in snapshot.get("entries", [])
    ]
    projected["top_rows"] = [
        {
            key: value
            for key, value in row.items()
            if key not in {"avatar", "rank_level"}
        }
        for row in snapshot.get("top_rows", [])
    ]
    return projected


def _live_snapshot_matches_authorized_snapshot(live_snapshot, authorized_snapshot):
    return lbr.sha256_hex_from_value(
        _snapshot_for_live_drift_check(live_snapshot)
    ) == lbr.sha256_hex_from_value(
        _snapshot_for_live_drift_check(authorized_snapshot)
    )


def fetch_claims_for_period(conn, board_type, period_key):
    columns_sql = ", ".join(_CLAIM_COLUMNS)
    rows = conn.execute(
        f"SELECT {columns_sql} FROM leaderboard_reward_claims "
        "WHERE board_type = %(board_type)s AND period_key = %(period_key)s ORDER BY rank, id",
        {"board_type": board_type, "period_key": period_key},
    ).fetchall()
    claims = []
    for row in rows:
        claim = dict(zip(_CLAIM_COLUMNS, row))
        claim["claim_id"] = claim["id"]
        claims.append(claim)
    return claims


def fetch_snapshot_rows_for_period(conn, board_type, period_key):
    columns_sql = ", ".join(_SNAPSHOT_COLUMNS)
    rows = conn.execute(
        f"SELECT {columns_sql} FROM leaderboard_snapshots "
        "WHERE board_type = %(board_type)s AND period_key = %(period_key)s ORDER BY rank, user_id",
        {"board_type": board_type, "period_key": period_key},
    ).fetchall()
    return [dict(zip(_SNAPSHOT_COLUMNS, row)) for row in rows]


def fetch_component_logs_for_claim_ids(conn, claim_ids):
    if not claim_ids:
        return []
    placeholders = ",".join(["%s"] * len(claim_ids))
    sql = (
        "SELECT claim_id, component, reward_key, quantity, result, detail "
        f"FROM leaderboard_reward_component_log WHERE claim_id IN ({placeholders}) "
        "ORDER BY claim_id, component, reward_key"
    )
    return [dict(r) for r in conn.execute(sql, tuple(claim_ids)).fetchall()]


def expected_component_rows(preview_entries):
    rows = []
    for entry in preview_entries:
        if not entry.get("eligible"):
            continue
        claim_rank = int(entry["rank"])
        claim_user_id = int(entry["user_id"])
        payload = entry.get("reward_payload") or {}
        if payload.get("coins"):
            rows.append({
                "rank": claim_rank,
                "user_id": claim_user_id,
                "component": "coin",
                "reward_key": "coins",
                "quantity": int(payload["coins"]),
            })
        for item_key, qty in (payload.get("items") or {}).items():
            rows.append({
                "rank": claim_rank,
                "user_id": claim_user_id,
                "component": "item",
                "reward_key": item_key,
                "quantity": int(qty),
            })
        for badge_key in payload.get("badges") or []:
            rows.append({
                "rank": claim_rank,
                "user_id": claim_user_id,
                "component": "badge",
                "reward_key": badge_key,
                "quantity": 1,
            })
        for title_key in payload.get("titles") or []:
            rows.append({
                "rank": claim_rank,
                "user_id": claim_user_id,
                "component": "title",
                "reward_key": title_key,
                "quantity": 1,
            })
    return rows


def _preview_claim_expectations(preview_entries):
    expectations = []
    for entry in preview_entries:
        if not entry.get("eligible"):
            continue
        payload = entry.get("reward_payload") or {}
        expectations.append({
            "user_id": int(entry["user_id"]),
            "rank": int(entry["rank"]),
            "score": int(entry["score"]),
            "eligible": bool(entry["eligible"]),
            "rank_band": entry["rank_band"],
            "ineligible_reason": entry["ineligible_reason"],
            "reward_bundle_key": entry["reward_bundle_key"],
            "granted_coins": int(payload.get("coins") or 0),
            "granted_items_json": json.dumps(payload.get("items") or {}, ensure_ascii=False, sort_keys=True),
            "granted_badges_json": json.dumps(payload.get("badges") or [], ensure_ascii=False),
            "granted_titles_json": json.dumps(payload.get("titles") or [], ensure_ascii=False),
        })
    return expectations


def detect_existing_operation_state(conn, snapshot, preview_result):
    claims = fetch_claims_for_period(conn, snapshot["board_type"], snapshot["period_key"])
    snapshots = fetch_snapshot_rows_for_period(conn, snapshot["board_type"], snapshot["period_key"])
    if not claims and not snapshots:
        return {"state": "absent", "claims": [], "snapshots": [], "component_logs": []}
    if not claims or not snapshots:
        return {"state": "conflict", "reason": "partial snapshot/claim presence", "claims": claims, "snapshots": snapshots}
    expected_claims = _preview_claim_expectations(preview_result["preview"])
    expected_snapshot_rows = preview_result["summary"]["snapshot_row_count"]
    if len(claims) != len(expected_claims):
        return {"state": "conflict", "reason": "existing claim count mismatch", "claims": claims, "snapshots": snapshots}
    if len(snapshots) != int(expected_snapshot_rows):
        return {"state": "conflict", "reason": "existing snapshot count mismatch", "claims": claims, "snapshots": snapshots}
    by_rank = {int(item["rank"]): item for item in expected_claims}
    def _norm_scalar(key, value):
        if key in ("user_id", "rank", "granted_coins"):
            return int(value)
        if key == "score":
            return int(float(value))
        return value
    claim_ids = []
    for claim in claims:
        expected = by_rank.get(int(claim["rank"]))
        if expected is None:
            return {"state": "conflict", "reason": "unexpected existing claim rank", "claims": claims, "snapshots": snapshots}
        claim_ids.append(int(claim["id"]))
        for key in (
            "user_id", "rank", "score", "rank_band", "reward_bundle_key",
            "granted_coins", "granted_items_json", "granted_badges_json",
            "granted_titles_json",
        ):
            if _norm_scalar(key, claim.get(key)) != _norm_scalar(key, expected.get(key)):
                return {"state": "conflict", "reason": f"existing claim mismatch for rank={claim['rank']} key={key}"}
        if bool(claim["eligible"]) != bool(expected["eligible"]):
            return {"state": "conflict", "reason": f"existing claim eligibility mismatch for rank={claim['rank']}"}
        wanted_status = lbr.CLAIM_STATUS_GRANTED
        if claim["status"] != wanted_status:
            return {"state": "conflict", "reason": f"existing claim status is not fully settled for rank={claim['rank']}"}
    preview_by_rank = {int(item["rank"]): item for item in preview_result["preview"]}
    for snap in snapshots:
        expected = preview_by_rank.get(int(snap["rank"]))
        if expected is None:
            return {"state": "conflict", "reason": "unexpected existing snapshot rank"}
        if int(snap["user_id"]) != int(expected["user_id"]) or int(snap["score"]) != int(expected["score"]):
            return {"state": "conflict", "reason": f"existing snapshot mismatch for rank={snap['rank']}"}
    component_logs = fetch_component_logs_for_claim_ids(conn, claim_ids)
    expected_components = expected_component_rows(preview_result["preview"])
    actual_components = []
    claim_by_id = {int(c["id"]): c for c in claims}
    for item in component_logs:
        claim = claim_by_id.get(int(item["claim_id"]))
        if claim is None:
            return {"state": "conflict", "reason": "component log references an unexpected claim"}
        actual_components.append({
            "rank": int(claim["rank"]),
            "user_id": int(claim["user_id"]),
            "component": item["component"],
            "reward_key": item["reward_key"],
            "quantity": int(item["quantity"]),
            "result": item["result"],
        })
    expected_component_keys = sorted(
        (r["rank"], r["user_id"], r["component"], r["reward_key"], r["quantity"]) for r in expected_components
    )
    actual_component_keys = sorted(
        (r["rank"], r["user_id"], r["component"], r["reward_key"], r["quantity"])
        for r in actual_components if r["result"] == "granted"
    )
    if actual_component_keys != expected_component_keys:
        return {"state": "conflict", "reason": "existing component log mismatch"}
    return {
        "state": "already_granted_noop",
        "claims": claims,
        "snapshots": snapshots,
        "component_logs": component_logs,
    }


def commit_exact_period(
    conn,
    *,
    snapshot,
    expected_snapshot_sha256,
    expected_preview_sha256,
    expected_claim_count,
    expected_component_count,
    expected_total_coins,
    expected_total_items,
    expected_total_badges,
    owner_gate=None,
    required_owner_gate=None,
    scheduler_authorization=None,
    now=None,
):
    if required_owner_gate is None:
        required_owner_gate = lbr.EXACT_PERIOD_OWNER_GATE
    _validate_commit_authorization(
        conn,
        snapshot,
        owner_gate=owner_gate,
        required_owner_gate=required_owner_gate,
        scheduler_authorization=scheduler_authorization,
    )
    if snapshot["timezone"] != "Asia/Taipei":
        raise ValueError("exact-period commit only supports Asia/Taipei snapshots")
    if not lbr.is_exact_period_closed(
        snapshot["board_type"],
        datetime.date.fromisoformat(snapshot["period_start"]),
        datetime.date.fromisoformat(snapshot["period_end_exclusive"]),
        now=now,
        timezone=snapshot["timezone"],
    ):
        raise ValueError("refusing to commit an open leaderboard period")
    actual_snapshot_sha = lbr.sha256_hex_from_value(snapshot)
    if actual_snapshot_sha != expected_snapshot_sha256:
        raise ValueError("snapshot SHA-256 mismatch")
    preview_result = build_exact_period_preview(snapshot)
    if preview_result["preview_sha256"] != expected_preview_sha256:
        raise ValueError("preview SHA-256 mismatch")
    if int(preview_result["summary"]["claims_count"]) != int(expected_claim_count):
        raise ValueError("expected claim count mismatch")
    if not exact_period_component_totals_match(
        preview_result["summary"],
        expected_component_count=expected_component_count,
        expected_total_coins=expected_total_coins,
        expected_total_items=expected_total_items,
        expected_total_badges=expected_total_badges,
    ):
        raise ValueError("expected reward totals mismatch")
    live_snapshot = build_exact_period_snapshot(
        conn,
        board_type=snapshot["board_type"],
        period_key=snapshot["period_key"],
        period_start=snapshot["period_start"],
        period_end_exclusive=snapshot["period_end_exclusive"],
        timezone=snapshot["timezone"],
        limit=len(snapshot["entries"]),
    )
    if not _live_snapshot_matches_authorized_snapshot(live_snapshot, snapshot):
        raise ValueError("eligible ranking changed since preview")
    existing = detect_existing_operation_state(conn, snapshot, preview_result)
    if existing["state"] == "already_granted_noop":
        return {
            "result": "already_granted_noop",
            "snapshot_sha256": actual_snapshot_sha,
            "preview_sha256": preview_result["preview_sha256"],
            "summary": preview_result["summary"],
        }
    if existing["state"] != "absent":
        raise ValueError(existing.get("reason", "existing claims prevent exact-period commit"))
    from tools.community_leaderboard_rewards_real_grant_preview import (
        load_app_module, verify_real_grant_targets_for_claims,
    )
    from tools.community_leaderboard_rewards_real_grant_commit import execute_exact_period_grant_commit

    finalize_result = lbr.finalize_leaderboard_reward_period(
        conn,
        snapshot["board_type"],
        snapshot["period_key"],
        snapshot["period_start"],
        (
            datetime.date.fromisoformat(snapshot["period_end_exclusive"])
            - datetime.timedelta(days=1)
        ).isoformat(),
        snapshot["entries"],
        dry_run=False,
    )
    inserted_claim_count = int(finalize_result["claims"]["inserted"])
    existing_claim_count = int(finalize_result["claims"]["existing"])
    if existing_claim_count != 0 or inserted_claim_count != int(expected_claim_count):
        raise ValueError("finalize step did not create the exact expected claim set")
    claims = fetch_claims_for_period(conn, snapshot["board_type"], snapshot["period_key"])
    if fetch_component_logs_for_claim_ids(conn, [int(c["id"]) for c in claims]):
        raise ValueError("unexpected existing component-log rows present before grant")
    app_module = load_app_module()
    signature_errors = verify_real_grant_targets_for_claims(app_module, conn, claims)
    if signature_errors:
        raise ValueError(f"real grant target verification failed: {signature_errors}")
    grant_results = execute_exact_period_grant_commit(
        conn,
        app_module,
        claims,
        board_type=snapshot["board_type"],
        period_key=snapshot["period_key"],
    )
    unacked = sum(
        1 for claim in fetch_claims_for_period(conn, snapshot["board_type"], snapshot["period_key"])
        if claim["status"] == lbr.CLAIM_STATUS_GRANTED and claim["notification_acknowledged_at"] is None
    )
    return {
        "result": "committed",
        "snapshot_sha256": actual_snapshot_sha,
        "preview_sha256": preview_result["preview_sha256"],
        "summary": preview_result["summary"],
        "grant_results": grant_results,
        "unacknowledged_notification_count": unacked,
    }
