import calendar
import datetime
import hashlib
import json
import re
from zoneinfo import ZoneInfo

WEEKLY_REWARD_MIN_SCORE = 30
MONTHLY_REWARD_MIN_SCORE = 150

BOARD_TYPE_WEEKLY = "weekly"
BOARD_TYPE_MONTHLY = "monthly"
BOARD_TYPES = (BOARD_TYPE_WEEKLY, BOARD_TYPE_MONTHLY)

RANK_BAND_NONE = "none"
RANK_BAND_TOP1 = "top1"
RANK_BAND_TOP3 = "top3"
RANK_BAND_TOP10 = "top10"
RANK_BAND_TOP25 = "top25"
RANK_BAND_TOP50 = "top50"
RANK_BANDS = (
    RANK_BAND_TOP1,
    RANK_BAND_TOP3,
    RANK_BAND_TOP10,
    RANK_BAND_TOP25,
    RANK_BAND_TOP50,
    RANK_BAND_NONE,
)

CLAIM_STATUS_PENDING = "pending"
CLAIM_STATUS_GRANTED = "granted"
CLAIM_STATUS_FAILED = "failed"
CLAIM_STATUS_SKIPPED = "skipped"
CLAIM_STATUSES = (
    CLAIM_STATUS_PENDING,
    CLAIM_STATUS_GRANTED,
    CLAIM_STATUS_FAILED,
    CLAIM_STATUS_SKIPPED,
)

# Phase 1 reward bundles must not include ai_explain_ticket (explanation
# quality is not stable enough yet to hand out as a leaderboard reward).
FORBIDDEN_REWARD_ITEM_KEYS = frozenset({"ai_explain_ticket"})

EXACT_PERIOD_OWNER_GATE = "GO_COMMUNITY_LEADERBOARD_REWARD_GRANT"

_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_GOOGLE_SUB_RE = re.compile(r"^\d{9,30}$")
_GENERATED_GOOGLE_USERNAME_RE = re.compile(r"^g_.+_\d+$")

_WEEKLY_REWARD_BUNDLES = {
    RANK_BAND_TOP1: {
        "coins": 500,
        "xp_potion": 2,
        "badge_lb_weekly_1": 1,
    },
    RANK_BAND_TOP3: {
        "coins": 350,
        "xp_potion": 1,
    },
    RANK_BAND_TOP10: {
        "coins": 220,
        "small_xp_potion": 2,
    },
    RANK_BAND_TOP25: {
        "coins": 120,
        "small_xp_potion": 1,
    },
    RANK_BAND_TOP50: {
        "coins": 60,
    },
}

_MONTHLY_REWARD_BUNDLES = {
    RANK_BAND_TOP1: {
        "coins": 1500,
        "rare_appearance_fragment": 2,
        "badge_lb_monthly_1": 1,
        "title_monthly_master": 1,
    },
    RANK_BAND_TOP3: {
        "coins": 1000,
        "rare_appearance_fragment": 1,
        "badge_lb_monthly_top3": 1,
    },
    RANK_BAND_TOP10: {
        "coins": 600,
        "appearance_fragment": 2,
        "badge_lb_monthly_top10": 1,
    },
    RANK_BAND_TOP25: {
        "coins": 300,
        "appearance_fragment": 1,
    },
    RANK_BAND_TOP50: {
        "coins": 150,
    },
}


def canonical_json_dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_hex_from_value(value):
    return hashlib.sha256(canonical_json_dumps(value).encode("utf-8")).hexdigest()


def determine_leaderboard_rank_band(rank):
    if not isinstance(rank, int) or rank < 1:
        return RANK_BAND_NONE
    if rank == 1:
        return RANK_BAND_TOP1
    if rank <= 3:
        return RANK_BAND_TOP3
    if rank <= 10:
        return RANK_BAND_TOP10
    if rank <= 25:
        return RANK_BAND_TOP25
    if rank <= 50:
        return RANK_BAND_TOP50
    return RANK_BAND_NONE


def get_weekly_reward_bundle(rank_band):
    bundle = _WEEKLY_REWARD_BUNDLES.get(rank_band)
    return dict(bundle) if bundle else {}


def get_monthly_reward_bundle(rank_band):
    bundle = _MONTHLY_REWARD_BUNDLES.get(rank_band)
    return dict(bundle) if bundle else {}


_WEEKLY_RULES_RANK_BANDS_ORDER = (
    RANK_BAND_TOP1, RANK_BAND_TOP3, RANK_BAND_TOP10, RANK_BAND_TOP25, RANK_BAND_TOP50,
)


def _weekly_rank_band_bounds():
    """Derive (rank_min, rank_max) per rank band directly from
    determine_leaderboard_rank_band's own logic, by scanning ranks 1..50
    -- this guarantees the rules display can never drift out of sync
    with the actual rank-band boundaries used to grant rewards, even if
    those boundaries are changed later."""
    bounds = {}
    for rank in range(1, 51):
        band = determine_leaderboard_rank_band(rank)
        if band == RANK_BAND_NONE:
            continue
        if band not in bounds:
            bounds[band] = [rank, rank]
        else:
            bounds[band][1] = rank
    return {band: tuple(r) for band, r in bounds.items()}


def get_weekly_leaderboard_reward_rules():
    """Read-only, structured snapshot of the CURRENT weekly leaderboard
    reward policy -- derived directly from WEEKLY_REWARD_MIN_SCORE,
    _WEEKLY_REWARD_BUNDLES, and determine_leaderboard_rank_band's own
    rank-band boundaries (the exact same source of truth the real
    finalize/grant pipeline uses). Never grants anything, never touches
    the database, never changes any reward amount or bundle -- this is
    a pure, side-effect-free read of already-existing constants for
    display purposes only.

    Every reward entry is structured type/key/amount data, e.g.
    {"type": "coins", "amount": 500} or {"type": "item", "key":
    "xp_potion", "quantity": 2} -- never a pre-localized label. Callers
    (the API route, the frontend) are responsible for localization."""
    bounds = _weekly_rank_band_bounds()
    rank_bands = []
    for band in _WEEKLY_RULES_RANK_BANDS_ORDER:
        bundle = get_weekly_reward_bundle(band)
        coins, items, badges, _titles = _split_reward_bundle(bundle)
        rewards = []
        if coins:
            rewards.append({"type": "coins", "amount": coins})
        for item_key, qty in items.items():
            rewards.append({"type": "item", "key": item_key, "quantity": qty})
        for badge_key in badges:
            rewards.append({"type": "badge", "key": badge_key})
        rank_min, rank_max = bounds[band]
        rank_bands.append({
            "key": band, "rank_min": rank_min, "rank_max": rank_max, "rewards": rewards,
        })
    return {
        "period": {"type": BOARD_TYPE_WEEKLY, "starts_on": "Monday", "ends_on": "Sunday"},
        "minimum_score": WEEKLY_REWARD_MIN_SCORE,
        "coin_cap_policy": "leaderboard_rewards_bypass_daily_cap",
        "delivery": "automatic",
        "rank_bands": rank_bands,
    }


def is_leaderboard_reward_eligible(board_type, score):
    if not isinstance(score, (int, float)):
        return False
    if board_type == BOARD_TYPE_WEEKLY:
        return score >= WEEKLY_REWARD_MIN_SCORE
    if board_type == BOARD_TYPE_MONTHLY:
        return score >= MONTHLY_REWARD_MIN_SCORE
    return False


def validate_leaderboard_board_type(board_type):
    if board_type not in BOARD_TYPES:
        raise ValueError(f"invalid leaderboard board_type: {board_type!r}")
    return board_type


def validate_leaderboard_claim_status(status):
    if status not in CLAIM_STATUSES:
        raise ValueError(f"invalid leaderboard reward claim status: {status!r}")
    return status


def validate_leaderboard_display_name_snapshot(display_name_snapshot):
    """Reject values that look like an email, a raw Google sub id, or an
    unsafe auto-generated Google username. The snapshot is a display-only
    copy taken at settlement time, never an identity source."""
    if not isinstance(display_name_snapshot, str) or not display_name_snapshot.strip():
        raise ValueError("display_name_snapshot must be a non-empty string")
    if _EMAIL_RE.search(display_name_snapshot):
        raise ValueError("display_name_snapshot must not contain an email address")
    if _GOOGLE_SUB_RE.match(display_name_snapshot):
        raise ValueError("display_name_snapshot must not be a raw Google sub id")
    if _GENERATED_GOOGLE_USERNAME_RE.match(display_name_snapshot):
        raise ValueError("display_name_snapshot must not be an unsafe generated Google username")
    return display_name_snapshot


def _validate_no_forbidden_reward_items(items):
    if not items:
        return
    forbidden = FORBIDDEN_REWARD_ITEM_KEYS & set(items)
    if forbidden:
        raise ValueError(f"reward payload contains forbidden item(s): {sorted(forbidden)}")


def _last_day_of_month(d):
    last_day = calendar.monthrange(d.year, d.month)[1]
    return d.replace(day=last_day)


def _resolve_taipei_today(now, timezone):
    """Resolve `now` (naive or aware) to a calendar date in `timezone`."""
    tz = ZoneInfo(timezone)
    if now is None:
        now = datetime.datetime.now(tz)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)
    return now.date()


def get_leaderboard_period(board_type, now=None, timezone="Asia/Taipei"):
    """Return (period_start, period_end) date objects for the leaderboard
    period containing `now`, computed in `timezone` (default Asia/Taipei).

    Weekly periods start Monday 00:00 and end Sunday 23:59:59 (inclusive
    end date). Monthly periods start on the 1st and end on the last day
    of the month."""
    validate_leaderboard_board_type(board_type)
    today = _resolve_taipei_today(now, timezone)
    if board_type == BOARD_TYPE_WEEKLY:
        period_start = today - datetime.timedelta(days=today.weekday())
        period_end = period_start + datetime.timedelta(days=6)
    else:
        period_start = today.replace(day=1)
        period_end = _last_day_of_month(today)
    return period_start, period_end


def get_previous_leaderboard_period(board_type, now=None, timezone="Asia/Taipei"):
    """Return (period_start, period_end) for the period immediately before
    the one containing `now`."""
    validate_leaderboard_board_type(board_type)
    current_start, current_end = get_leaderboard_period(board_type, now=now, timezone=timezone)
    if board_type == BOARD_TYPE_WEEKLY:
        period_start = current_start - datetime.timedelta(days=7)
        period_end = current_end - datetime.timedelta(days=7)
    else:
        period_end = current_start - datetime.timedelta(days=1)
        period_start = period_end.replace(day=1)
    return period_start, period_end


def format_leaderboard_period_key(board_type, period_start):
    """Format a period_key from a period_start date: YYYY-Www for weekly
    (ISO week, matches the Monday-start period boundary), YYYY-MM for
    monthly."""
    validate_leaderboard_board_type(board_type)
    if board_type == BOARD_TYPE_WEEKLY:
        iso_year, iso_week, _ = period_start.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    return period_start.strftime("%Y-%m")


def get_exact_period_bounds(board_type, period_start, timezone="Asia/Taipei"):
    validate_leaderboard_board_type(board_type)
    if hasattr(period_start, "date"):
        period_start = period_start.date()
    if board_type == BOARD_TYPE_WEEKLY:
        period_end = period_start + datetime.timedelta(days=7)
    else:
        next_month = (period_start.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        period_end = next_month
    tz = ZoneInfo(timezone)
    start_dt = datetime.datetime.combine(period_start, datetime.time.min, tzinfo=tz)
    end_dt = datetime.datetime.combine(period_end, datetime.time.min, tzinfo=tz)
    return period_start, period_end, start_dt, end_dt


def validate_exact_period_bounds(board_type, period_key, period_start, period_end, timezone="Asia/Taipei"):
    validate_leaderboard_board_type(board_type)
    start_date, expected_end_date, start_dt, end_dt = get_exact_period_bounds(
        board_type, period_start, timezone=timezone)
    provided_end = period_end.date() if hasattr(period_end, "date") else period_end
    if provided_end != expected_end_date:
        raise ValueError(
            f"period_end {provided_end!r} does not match the exact {board_type} period end "
            f"for period_start {start_date!r}"
        )
    expected_key = format_leaderboard_period_key(board_type, start_date)
    if period_key != expected_key:
        raise ValueError(
            f"period_key {period_key!r} does not match board_type={board_type!r} "
            f"period_start={start_date!r} (expected {expected_key!r})"
        )
    return {
        "period_start_date": start_date,
        "period_end_date": expected_end_date,
        "period_start_at": start_dt,
        "period_end_exclusive_at": end_dt,
        "period_key": expected_key,
        "timezone": timezone,
    }


def is_exact_period_closed(board_type, period_start, period_end, *, now=None, timezone="Asia/Taipei"):
    bounds = validate_exact_period_bounds(board_type, format_leaderboard_period_key(
        board_type, period_start.date() if hasattr(period_start, "date") else period_start
    ), period_start, period_end, timezone=timezone)
    current = now or datetime.datetime.now(ZoneInfo(timezone))
    if current.tzinfo is None:
        current = current.replace(tzinfo=ZoneInfo(timezone))
    else:
        current = current.astimezone(ZoneInfo(timezone))
    return current >= bounds["period_end_exclusive_at"]


def fetch_leaderboard_participant_rows(conn, period_start_iso, period_end_iso=None, *, limit=None):
    sql = """
WITH qualifying_distinct AS (
    SELECT rl.user_id, rl.question_id, MIN(rl.reviewed_at) AS first_counted_at
      FROM review_log rl
     WHERE rl.reviewed_at >= ?
       {period_end_clause}
       AND rl.grade >= 3
     GROUP BY rl.user_id, rl.question_id
),
scored AS (
    SELECT q.user_id,
           COUNT(*) AS score,
           MAX(q.first_counted_at) AS final_counted_at
      FROM qualifying_distinct q
     GROUP BY q.user_id
)
SELECT u.id,
       u.username,
       COALESCE(u.nickname,u.username) AS display_name,
       scored.score AS score,
       scored.final_counted_at AS final_counted_at,
       COALESCE(MAX(us.rank_level),'LV1') AS rank_level,
       COALESCE(MAX(pa.character_key),'') AS character_key,
       COALESCE(MAX(pa.combat_armor),'') AS combat_armor,
       COALESCE(MAX(pa.combat_weapon),'') AS combat_weapon,
       COALESCE(MAX(pa.combat_cape),'') AS combat_cape,
       COALESCE(MAX(pa.combat_offhand),'') AS combat_offhand,
       COALESCE(MAX(pa.combat_hat),'') AS combat_hat,
       COALESCE(MAX(pa.combat_pet),'') AS combat_pet,
       COALESCE(MAX(pa.combat_aura),'') AS combat_aura,
       CASE WHEN u.plan='premium' THEN 1 ELSE 0 END AS is_premium,
       CASE WHEN COALESCE(u.is_admin,FALSE) THEN 1 ELSE 0 END AS is_admin
  FROM scored
  JOIN users u ON u.id = scored.user_id
  LEFT JOIN user_stats us ON us.user_id = u.id
  LEFT JOIN player_appearance pa ON pa.user_id = u.id
 GROUP BY u.id, u.username, u.nickname, u.plan, u.is_admin, scored.score, scored.final_counted_at
 ORDER BY scored.score DESC, scored.final_counted_at ASC, u.id ASC
{limit_clause}
""".format(
        period_end_clause="AND rl.reviewed_at < ?" if period_end_iso else "",
        limit_clause=(" LIMIT ?" if limit is not None else ""),
    )
    params = [period_start_iso]
    if period_end_iso:
        params.append(period_end_iso)
    if limit is not None:
        params.append(limit)
    return conn.execute(sql, tuple(params)).fetchall()


def rank_leaderboard_participants(rows):
    ranked = []
    for raw in rows:
        row = dict(raw)
        user_id = int(row["id"])
        row["user_id"] = user_id
        row["score"] = int(row["score"] or 0)
        row["final_counted_at"] = row.get("final_counted_at")
        ranked.append(row)
    ranked.sort(key=lambda r: (-int(r["score"]), str(r["final_counted_at"] or ""), int(r["user_id"])))
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
    return ranked


def leaderboard_rows_to_entries(rows, *, limit=None):
    entries = []
    for row in rows[:limit] if limit is not None else rows:
        entries.append({
            "user_id": int(row["user_id"]),
            "display_name": row["display_name"],
            "avatar": row.get("character_key") or None,
            "rank": int(row["rank"]),
            "score": int(row["score"]),
            "final_counted_at": row.get("final_counted_at"),
        })
    return entries


def summarize_preview_rewards(preview_entries):
    eligible_entries = [entry for entry in preview_entries if entry.get("eligible")]
    summary = {
        "claims_count": len(eligible_entries),
        "snapshot_row_count": len(preview_entries),
        "eligible_claim_count": len(eligible_entries),
        "non_rewarded_row_count": len(preview_entries) - len(eligible_entries),
        "component_count": 0,
        "total_coins": 0,
        "total_items": {},
        "total_badges": {},
        "total_titles": {},
    }
    for entry in preview_entries:
        if not entry.get("eligible"):
            continue
        payload = entry.get("reward_payload") or {}
        coins = int(payload.get("coins") or 0)
        if coins > 0:
            summary["component_count"] += 1
            summary["total_coins"] += coins
        for item_key, qty in (payload.get("items") or {}).items():
            summary["component_count"] += 1
            summary["total_items"][item_key] = summary["total_items"].get(item_key, 0) + int(qty)
        for badge_key in payload.get("badges") or []:
            summary["component_count"] += 1
            summary["total_badges"][badge_key] = summary["total_badges"].get(badge_key, 0) + 1
        for title_key in payload.get("titles") or []:
            summary["component_count"] += 1
            summary["total_titles"][title_key] = summary["total_titles"].get(title_key, 0) + 1
    return summary


def _split_reward_bundle(bundle):
    """Split a flat reward bundle dict (as returned by get_*_reward_bundle)
    into (coins, items, badges, titles) based on key naming convention."""
    coins = 0
    items = {}
    badges = []
    titles = []
    for key, value in bundle.items():
        if key == "coins":
            coins = value
        elif key.startswith("badge_"):
            badges.append(key)
        elif key.startswith("title_"):
            titles.append(key)
        else:
            items[key] = value
    return coins, items, badges, titles


def _process_leaderboard_entry(board_type, entry):
    """Pure data-shaping: derive rank_band/eligibility/reward preview for one
    leaderboard entry. Does not touch the DB and does not grant anything."""
    user_id = entry["user_id"]
    display_name = entry["display_name"]
    validate_leaderboard_display_name_snapshot(display_name)
    avatar = entry.get("avatar")
    rank = entry.get("rank")
    score = entry.get("score")

    rank_band = determine_leaderboard_rank_band(rank)
    meets_score_threshold = is_leaderboard_reward_eligible(board_type, score)
    outside_reward_rank = rank_band == RANK_BAND_NONE
    eligible = meets_score_threshold and not outside_reward_rank

    ineligible_reason = None
    if not eligible:
        if not meets_score_threshold:
            ineligible_reason = (
                "below_weekly_threshold"
                if board_type == BOARD_TYPE_WEEKLY
                else "below_monthly_threshold"
            )
        else:
            ineligible_reason = "outside_reward_rank"

    if eligible:
        bundle = (
            get_weekly_reward_bundle(rank_band)
            if board_type == BOARD_TYPE_WEEKLY
            else get_monthly_reward_bundle(rank_band)
        )
        reward_bundle_key = f"{board_type}_{rank_band}"
    else:
        bundle = {}
        reward_bundle_key = None

    coins, items, badges, titles = _split_reward_bundle(bundle)

    return {
        "user_id": user_id,
        "display_name": display_name,
        "avatar": avatar,
        "rank": rank,
        "rank_band": rank_band,
        "score": score,
        "eligible": eligible,
        "reward_bundle_key": reward_bundle_key,
        "reward_payload": {
            "coins": coins,
            "items": items,
            "badges": badges,
            "titles": titles,
        },
        "ineligible_reason": ineligible_reason,
    }


_SNAPSHOT_INSERT_SQL = """INSERT INTO leaderboard_snapshots
    (board_type, period_key, period_start, period_end, user_id,
     display_name_snapshot, avatar_snapshot, rank, score, eligible,
     rank_band, created_at)
    VALUES (%(board_type)s, %(period_key)s, %(period_start)s, %(period_end)s,
            %(user_id)s, %(display_name_snapshot)s, %(avatar_snapshot)s,
            %(rank)s, %(score)s, %(eligible)s, %(rank_band)s, %(created_at)s)
    ON CONFLICT (board_type, period_key, user_id) DO NOTHING
    RETURNING id"""

_CLAIM_INSERT_SQL = """INSERT INTO leaderboard_reward_claims
    (user_id, board_type, period_key, rank, rank_band, score, eligible,
     ineligible_reason, reward_bundle_key, granted_coins, granted_items_json,
     granted_badges_json, granted_titles_json, status, error_message,
     created_at, granted_at)
    VALUES (%(user_id)s, %(board_type)s, %(period_key)s, %(rank)s, %(rank_band)s,
            %(score)s, %(eligible)s, %(ineligible_reason)s, %(reward_bundle_key)s,
            %(granted_coins)s, %(granted_items_json)s, %(granted_badges_json)s,
            %(granted_titles_json)s, %(status)s, %(error_message)s,
            %(created_at)s, %(granted_at)s)
    ON CONFLICT (user_id, board_type, period_key) DO NOTHING
    RETURNING id"""


def finalize_leaderboard_reward_period(
    conn,
    board_type,
    period_key,
    period_start,
    period_end,
    entries,
    dry_run=True,
):
    """Settle one weekly/monthly leaderboard period into snapshots + reward
    claims, WITHOUT granting anything. Phase 1 / PR 3: only creates
    pending claims for reward-eligible rows, never granted claims. Does not invoke any
    coin-granting or shop-purchase-granting helper.

    entries: list of {"user_id", "display_name", "avatar", "rank", "score"}.
    display_name is validated via validate_leaderboard_display_name_snapshot
    (raises ValueError for email/Google-id-like/unsafe values).

    dry_run=True (default): pure preview, no DB writes at all.
    dry_run=False: idempotent upsert-by-ignore into leaderboard_snapshots /
    leaderboard_reward_claims. Re-running the same (board_type, period_key)
    never duplicates or overwrites existing rows — conflicts are reported
    as "existing", not replaced. Caller owns the transaction (this function
    never calls conn.commit()/conn.rollback()).
    """
    validate_leaderboard_board_type(board_type)
    period_start_str = (
        period_start.isoformat() if hasattr(period_start, "isoformat") else str(period_start)
    )
    period_end_str = (
        period_end.isoformat() if hasattr(period_end, "isoformat") else str(period_end)
    )

    processed = [_process_leaderboard_entry(board_type, entry) for entry in entries]

    if dry_run:
        return {
            "board_type": board_type,
            "period_key": period_key,
            "period_start": period_start_str,
            "period_end": period_end_str,
            "dry_run": True,
            "preview": processed,
        }

    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    snapshot_inserted = 0
    snapshot_existing = 0
    claim_inserted = 0
    claim_existing = 0
    claim_pending = 0
    result_entries = []

    for item in processed:
        snapshot_record = make_leaderboard_snapshot_record(
            board_type=board_type,
            period_key=period_key,
            period_start=period_start_str,
            period_end=period_end_str,
            user_id=item["user_id"],
            display_name_snapshot=item["display_name"],
            rank=item["rank"],
            score=item["score"],
            avatar_snapshot=item["avatar"],
            eligible=item["eligible"],
            rank_band=item["rank_band"],
            created_at=created_at,
        )
        snapshot_row = conn.execute(_SNAPSHOT_INSERT_SQL, snapshot_record).fetchone()
        if snapshot_row is None:
            snapshot_status = "existing"
            snapshot_existing += 1
        else:
            snapshot_status = "inserted"
            snapshot_inserted += 1

        claim_result_status = "not_created"
        if item["eligible"]:
            claim_record = make_leaderboard_reward_claim_record(
                user_id=item["user_id"],
                board_type=board_type,
                period_key=period_key,
                status=CLAIM_STATUS_PENDING,
                rank=item["rank"],
                rank_band=item["rank_band"],
                score=item["score"],
                eligible=item["eligible"],
                ineligible_reason=item["ineligible_reason"],
                reward_bundle_key=item["reward_bundle_key"],
                granted_coins=item["reward_payload"]["coins"],
                granted_items=item["reward_payload"]["items"],
                granted_badges=item["reward_payload"]["badges"],
                granted_titles=item["reward_payload"]["titles"],
                created_at=created_at,
            )
            claim_row = conn.execute(_CLAIM_INSERT_SQL, claim_record).fetchone()
            if claim_row is None:
                claim_result_status = "existing"
                claim_existing += 1
            else:
                claim_result_status = "inserted"
                claim_inserted += 1
                claim_pending += 1
        else:
            claim_row = None

        result_entries.append(
            {**item, "snapshot_status": snapshot_status, "claim_status": claim_result_status}
        )

    return {
        "board_type": board_type,
        "period_key": period_key,
        "period_start": period_start_str,
        "period_end": period_end_str,
        "dry_run": False,
        "snapshots": {"inserted": snapshot_inserted, "existing": snapshot_existing},
        "claims": {
            "inserted": claim_inserted,
            "existing": claim_existing,
            "pending": claim_pending,
            "not_created": len([entry for entry in processed if not entry["eligible"]]),
        },
        "entries": result_entries,
    }


def make_leaderboard_snapshot_record(
    board_type,
    period_key,
    period_start,
    period_end,
    user_id,
    display_name_snapshot,
    rank,
    score,
    avatar_snapshot=None,
    eligible=None,
    rank_band=None,
    created_at=None,
):
    """Build a leaderboard_snapshots row as a plain dict. Pure data shaping —
    does not touch the DB and does not grant anything."""
    validate_leaderboard_board_type(board_type)
    validate_leaderboard_display_name_snapshot(display_name_snapshot)
    if rank_band is None:
        rank_band = determine_leaderboard_rank_band(rank)
    if eligible is None:
        eligible = is_leaderboard_reward_eligible(board_type, score)
    return {
        "board_type": board_type,
        "period_key": period_key,
        "period_start": period_start,
        "period_end": period_end,
        "user_id": user_id,
        "display_name_snapshot": display_name_snapshot,
        "avatar_snapshot": avatar_snapshot,
        "rank": rank,
        "score": score,
        "eligible": int(bool(eligible)),
        "rank_band": rank_band,
        "created_at": created_at,
    }


def make_leaderboard_reward_claim_record(
    user_id,
    board_type,
    period_key,
    status=CLAIM_STATUS_PENDING,
    rank=None,
    rank_band=None,
    score=None,
    eligible=None,
    ineligible_reason=None,
    reward_bundle_key=None,
    granted_coins=0,
    granted_items=None,
    granted_badges=None,
    granted_titles=None,
    error_message=None,
    created_at=None,
    granted_at=None,
):
    """Build a leaderboard_reward_claims row as a plain dict. Pure data
    shaping only — this PR does not grant coins/items/badges/titles and does
    not invoke any coin-granting or shop-purchase-granting helper."""
    validate_leaderboard_board_type(board_type)
    validate_leaderboard_claim_status(status)
    granted_items = dict(granted_items) if granted_items else {}
    _validate_no_forbidden_reward_items(granted_items)
    granted_badges = list(granted_badges) if granted_badges else []
    granted_titles = list(granted_titles) if granted_titles else []
    if rank_band is None:
        rank_band = determine_leaderboard_rank_band(rank) if rank is not None else RANK_BAND_NONE
    return {
        "user_id": user_id,
        "board_type": board_type,
        "period_key": period_key,
        "rank": rank,
        "rank_band": rank_band,
        "score": score,
        "eligible": int(bool(eligible)) if eligible is not None else 0,
        "ineligible_reason": ineligible_reason,
        "reward_bundle_key": reward_bundle_key,
        "granted_coins": granted_coins,
        "granted_items_json": json.dumps(granted_items),
        "granted_badges_json": json.dumps(granted_badges),
        "granted_titles_json": json.dumps(granted_titles),
        "status": status,
        "error_message": error_message,
        "created_at": created_at,
        "granted_at": granted_at,
    }


# Dedicated advisory-lock key for this schema block only -- distinct from
# app.py's own init_db() lock (778899123) so this block never blocks on
# unrelated schema init and vice versa.
_SCHEMA_ADVISORY_LOCK_KEY = 778899456


def ensure_leaderboard_reward_tables(conn):
    """Create the leaderboard_snapshots / leaderboard_reward_claims tables.

    Schema only: no settlement job, no scheduler, and no reward granting
    lives here. Called from app.init_db(), mirroring how
    grimoire_api.ensure_node_mastery_table is wired in.

    Wrapped in a dedicated transaction-scoped advisory lock
    (pg_advisory_xact_lock) so concurrent callers -- e.g. the app and
    scheduler containers both calling app.init_db() on startup -- cannot
    race on CREATE TABLE IF NOT EXISTS. Postgres's catalog insert for a
    brand-new table/type is not fully race-safe even under IF NOT EXISTS:
    two concurrent callers can both pass the "does it exist" check and
    then collide inserting the same pg_type row, raising
    `psycopg2.errors.UniqueViolation: duplicate key value violates unique
    constraint "pg_type_typname_nsp_index"` (observed once during the
    Phase 1 schema-only production deploy on 2026-07-05, self-recovered
    via container restart). The lock serializes callers instead: whoever
    acquires it first fully creates (or no-ops over already-existing)
    both tables and commits before the next caller's CREATE TABLE
    statements even run, so the second caller only ever sees "already
    exists" and never races the catalog insert. Released automatically
    when the caller's transaction commits/rolls back -- same pattern as
    app.py's own init_db() advisory lock at pg_advisory_xact_lock(778899123).
    """
    conn.execute(f'SELECT pg_advisory_xact_lock({_SCHEMA_ADVISORY_LOCK_KEY})')
    conn.execute('''CREATE TABLE IF NOT EXISTS leaderboard_snapshots (
        id                    SERIAL PRIMARY KEY,
        board_type            TEXT    NOT NULL,
        period_key            TEXT    NOT NULL,
        period_start          TEXT    NOT NULL,
        period_end            TEXT    NOT NULL,
        user_id               INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        display_name_snapshot TEXT    NOT NULL,
        avatar_snapshot       TEXT,
        rank                  INTEGER NOT NULL,
        score                 REAL    NOT NULL,
        eligible              INTEGER NOT NULL DEFAULT 0,
        rank_band             TEXT    NOT NULL DEFAULT 'none',
        created_at            TEXT    NOT NULL,
        UNIQUE(board_type, period_key, user_id),
        CHECK(board_type IN ('weekly', 'monthly')),
        CHECK(rank_band IN ('top1', 'top3', 'top10', 'top25', 'top50', 'none')),
        CHECK(eligible IN (0, 1))
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_lb_snap_board_period '
                 'ON leaderboard_snapshots(board_type, period_key)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_lb_snap_user '
                 'ON leaderboard_snapshots(user_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_lb_snap_board_period_rank '
                 'ON leaderboard_snapshots(board_type, period_key, rank)')

    conn.execute('''CREATE TABLE IF NOT EXISTS leaderboard_reward_claims (
        id                  SERIAL PRIMARY KEY,
        user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        board_type          TEXT    NOT NULL,
        period_key          TEXT    NOT NULL,
        rank                INTEGER,
        rank_band           TEXT    NOT NULL DEFAULT 'none',
        score               REAL,
        eligible            INTEGER NOT NULL DEFAULT 0,
        ineligible_reason   TEXT,
        reward_bundle_key   TEXT,
        granted_coins       INTEGER NOT NULL DEFAULT 0,
        granted_items_json  TEXT    NOT NULL DEFAULT '{}',
        granted_badges_json TEXT    NOT NULL DEFAULT '[]',
        granted_titles_json TEXT    NOT NULL DEFAULT '[]',
        status              TEXT    NOT NULL DEFAULT 'pending',
        error_message       TEXT,
        created_at          TEXT    NOT NULL,
        granted_at          TEXT,
        UNIQUE(user_id, board_type, period_key),
        CHECK(board_type IN ('weekly', 'monthly')),
        CHECK(rank_band IN ('top1', 'top3', 'top10', 'top25', 'top50', 'none')),
        CHECK(status IN ('pending', 'granted', 'failed', 'skipped')),
        CHECK(eligible IN (0, 1))
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_lb_claim_board_period '
                 'ON leaderboard_reward_claims(board_type, period_key)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_lb_claim_user '
                 'ON leaderboard_reward_claims(user_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_lb_claim_status '
                 'ON leaderboard_reward_claims(status)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_lb_claim_board_period_band '
                 'ON leaderboard_reward_claims(board_type, period_key, rank_band)')

    # ── Phase 4A: reward notification acknowledgement (additive, schema
    # only) ── Records when the player has clicked "I saw this" on the
    # login-time reward notification for a claim. Never changes status,
    # never touches the reward payload, never issues anything -- purely
    # UI-acknowledgement bookkeeping. TEXT ISO timestamp, matching
    # created_at/granted_at's own convention on this table. Safe to run
    # against an already-existing table -- ADD COLUMN IF NOT EXISTS is a
    # no-op if the column is already there.
    conn.execute('ALTER TABLE leaderboard_reward_claims '
                 'ADD COLUMN IF NOT EXISTS notification_acknowledged_at TEXT')

    # ── Phase 3B: per-claim, per-component grant audit + idempotency log ──
    # One row per (claim_id, component, reward_key) that was actually
    # granted or failed. This is schema only -- nothing in Phase 3B writes
    # to this table outside of a real (non-dry-run) grant, and no code
    # path in this repo currently calls a real grant.
    conn.execute('''CREATE TABLE IF NOT EXISTS leaderboard_reward_component_log (
        id          SERIAL PRIMARY KEY,
        claim_id    INTEGER NOT NULL REFERENCES leaderboard_reward_claims(id) ON DELETE CASCADE,
        component   TEXT    NOT NULL,
        reward_key  TEXT    NOT NULL,
        quantity    INTEGER NOT NULL DEFAULT 1,
        result      TEXT    NOT NULL,
        detail      TEXT,
        created_at  TEXT    NOT NULL,
        UNIQUE(claim_id, component, reward_key),
        CHECK(component IN ('coin', 'item', 'badge', 'title')),
        CHECK(result IN ('granted', 'skipped_existing', 'failed'))
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_leaderboard_reward_component_log_claim_id '
                 'ON leaderboard_reward_component_log(claim_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_leaderboard_reward_component_log_component '
                 'ON leaderboard_reward_component_log(component)')
    conn.commit()


# ── Phase 1 / PR 4A: coins-only grant layer ─────────────────────────────
#
# This section only ever grants the `coins` component of a reward claim.
# It never touches granted_items_json / granted_badges_json /
# granted_titles_json content, and never marks a claim `granted` unless the
# coins component was actually processed. Per Phase 1A product decision,
# claim.status == 'granted' means "the coins component of this claim has
# been settled" — items/badges/titles remain in the stored payload for a
# later PR (4B/4C) to grant; this module does not claim to have granted
# them. This module never imports or calls app.py's real coin-granting or
# shop-purchase-granting helpers directly — the actual coin-granting
# callable is injected by the caller via `grant_coins_fn` so this module
# (and its tests) never touch real production coin-granting code.

_SELECT_PENDING_COIN_CLAIMS_SQL = """SELECT id, user_id, board_type, period_key, rank,
    rank_band, reward_bundle_key, granted_coins, status
    FROM leaderboard_reward_claims
    WHERE board_type = %(board_type)s AND period_key = %(period_key)s
      AND status = 'pending' AND eligible = 1
    ORDER BY id"""

_UPDATE_CLAIM_GRANTED_SQL = """UPDATE leaderboard_reward_claims
    SET status = 'granted', granted_at = %(granted_at)s, error_message = NULL
    WHERE id = %(id)s AND status = 'pending'"""

_UPDATE_CLAIM_FAILED_SQL = """UPDATE leaderboard_reward_claims
    SET status = 'failed', error_message = %(error_message)s
    WHERE id = %(id)s AND status = 'pending'"""


def _leaderboard_grant_reason(board_type, period_key, rank_band):
    return f"community_leaderboard:{board_type}:{period_key}:{rank_band}"


def mark_leaderboard_claim_granted(conn, claim_id):
    """Mark one claim as fully granted (every required reward component it
    carries has succeeded, per whichever caller decided that). Reuses the
    same guarded UPDATE as grant_leaderboard_reward_claims's own coins-only
    path -- only updates a row still in 'pending' status, so calling this
    on an already-granted/failed/skipped claim is a harmless no-op."""
    granted_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn.execute(_UPDATE_CLAIM_GRANTED_SQL, {"id": claim_id, "granted_at": granted_at})


def mark_leaderboard_claim_failed(conn, claim_id, error_message):
    """Mark one claim as failed (a required reward component failed to
    grant). Only updates a row still in 'pending' status -- a harmless
    no-op if the claim was already granted/failed/skipped."""
    conn.execute(
        _UPDATE_CLAIM_FAILED_SQL,
        {"id": claim_id, "error_message": str(error_message)[:500]},
    )


_RESET_CLAIM_TO_PENDING_FOR_RETRY_SQL = """UPDATE leaderboard_reward_claims
    SET status = 'pending', error_message = NULL
    WHERE id = %(id)s AND status = 'failed'"""


def reset_leaderboard_claim_to_pending_for_retry(conn, claim_id):
    """Explicitly transition ONE claim from 'failed' back to 'pending' so
    a narrowly-scoped retry command can reprocess it through the normal
    pending-claim grant path. Only ever updates a row currently in
    'failed' status -- a harmless no-op otherwise. Returns True if a row
    was actually updated (the claim was indeed 'failed' at the moment of
    this call), False if not -- callers must treat False as a gate
    failure, never proceed to grant anything in that case."""
    cur = conn.execute(_RESET_CLAIM_TO_PENDING_FOR_RETRY_SQL, {"id": claim_id})
    return cur.rowcount == 1


# ── Phase 4A: reward notification read/ack helpers ──────────────────────
#
# These never grant, change status, or touch the reward payload -- purely
# read-only fetch + a single UI-acknowledgement timestamp write.

_SELECT_UNACKED_GRANTED_CLAIMS_SQL = """SELECT id, board_type, period_key, rank, rank_band,
    granted_coins, granted_items_json, granted_badges_json, granted_titles_json, granted_at
    FROM leaderboard_reward_claims
    WHERE user_id = %(user_id)s AND status = 'granted'
      AND notification_acknowledged_at IS NULL
    ORDER BY granted_at ASC, id ASC"""

_UNACKED_CLAIM_COLUMNS = [
    "id", "board_type", "period_key", "rank", "rank_band",
    "granted_coins", "granted_items_json", "granted_badges_json",
    "granted_titles_json", "granted_at",
]


def fetch_unacknowledged_granted_reward_claims(conn, user_id):
    """Read-only fetch of `user_id`'s own granted leaderboard reward
    claims that have not yet had their notification acknowledged. Only
    ever reads rows belonging to the caller-provided user_id (never
    another user's), only status='granted' rows (never pending/failed/
    skipped), and never mutates anything."""
    rows = conn.execute(_SELECT_UNACKED_GRANTED_CLAIMS_SQL, {"user_id": user_id}).fetchall()
    return [dict(zip(_UNACKED_CLAIM_COLUMNS, row)) for row in rows]


def build_reward_notification_payload(claim):
    """Convert one claim row dict (as returned by
    fetch_unacknowledged_granted_reward_claims) into the structured,
    non-localized notification shape the frontend renders. Plain
    type/key/amount data only -- never a pre-localized label -- so the
    frontend can render it in whichever language the player has
    selected. Title payloads are never surfaced here (titles remain
    entirely unsupported end-to-end, matching every prior phase)."""
    rewards = []
    if claim.get("granted_coins"):
        rewards.append({"type": "coins", "amount": claim["granted_coins"]})
    items = _decode_leaderboard_item_payload(claim.get("granted_items_json"))
    for item_key, qty in items.items():
        rewards.append({"type": "item", "key": item_key, "quantity": qty})
    badges = _decode_leaderboard_reward_json_list(
        claim.get("granted_badges_json"), "granted_badges_json")
    for badge_key in badges:
        rewards.append({"type": "badge", "key": badge_key})
    return {
        "claim_id": claim["id"],
        "board": claim["board_type"],
        "period_key": claim["period_key"],
        "rank": claim["rank"],
        "rank_band": claim["rank_band"],
        "granted_at": claim["granted_at"],
        "rewards": rewards,
    }


_ACK_NOTIFICATION_SQL = """UPDATE leaderboard_reward_claims
    SET notification_acknowledged_at = %(now)s
    WHERE id = %(claim_id)s AND user_id = %(user_id)s AND status = 'granted'"""


def acknowledge_reward_notification(conn, claim_id, user_id):
    """Idempotently mark one claim's reward notification as acknowledged.
    Only ever updates a row that belongs to `user_id` AND is currently
    `status='granted'` -- never another user's claim, never a pending/
    failed/skipped claim. Never changes status, never touches the
    reward payload, never issues coins/items/badges. Re-acknowledging an
    already-acknowledged claim is a harmless overwrite of the same
    timestamp field and still returns True -- this is the idempotency
    the notification button relies on. Returns False if the claim
    doesn't exist, belongs to another user, or isn't 'granted' -- the
    caller should treat False as a rejection, not silently report
    success."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cur = conn.execute(
        _ACK_NOTIFICATION_SQL, {"now": now, "claim_id": claim_id, "user_id": user_id})
    return cur.rowcount == 1


def grant_leaderboard_reward_claims(
    conn,
    board_type,
    period_key,
    dry_run=True,
    grant_coins_fn=None,
):
    """Grant the coins component of pending, eligible reward claims for one
    board_type/period_key. Phase 1 / PR 4A: coins only — never grants
    items/badges/titles, never calls the shop-purchase-granting helper.

    Only claims with status == 'pending' and eligible == 1 are considered.
    'skipped', 'granted', and 'failed' claims are never touched (failed
    claims are not auto-retried by this function).

    Claims with granted_coins <= 0 are left untouched (still 'pending') —
    there is nothing for this coins-only layer to grant, and Phase 1A does
    not consider that a decision this function is allowed to make on its
    own for a claim that may still carry items/badges/titles.

    dry_run=True (default): pure preview, no DB writes, `grant_coins_fn` is
    never called (and may be omitted).

    dry_run=False: requires `grant_coins_fn(user_id, amount, reason=...)`.
    For each eligible pending claim with granted_coins > 0, calls
    grant_coins_fn and, only on success, updates the claim to status
    'granted' with granted_at set. If grant_coins_fn raises, the claim is
    marked 'failed' with error_message set and granted_at left null — it is
    never marked granted. Caller owns the transaction (this function never
    calls conn.commit()/conn.rollback()), so a caller that also wants
    idempotent behavior across process restarts should commit after this
    call returns.
    """
    validate_leaderboard_board_type(board_type)
    if not dry_run and grant_coins_fn is None:
        raise ValueError(
            "grant_coins_fn is required when dry_run=False"
        )

    rows = conn.execute(
        _SELECT_PENDING_COIN_CLAIMS_SQL,
        {"board_type": board_type, "period_key": period_key},
    ).fetchall()

    if dry_run:
        preview = []
        for (claim_id, user_id, row_board_type, row_period_key, rank,
             rank_band, reward_bundle_key, granted_coins, status) in rows:
            preview.append({
                "claim_id": claim_id,
                "user_id": user_id,
                "board_type": row_board_type,
                "period_key": row_period_key,
                "rank": rank,
                "rank_band": rank_band,
                "reward_bundle_key": reward_bundle_key,
                "granted_coins": granted_coins,
                "status": status,
                "would_grant": bool(granted_coins and granted_coins > 0),
            })
        return {
            "board_type": board_type,
            "period_key": period_key,
            "dry_run": True,
            "preview": preview,
        }

    granted = 0
    failed = 0
    skipped_zero_coins = 0
    entries = []

    for (claim_id, user_id, row_board_type, row_period_key, rank,
         rank_band, reward_bundle_key, granted_coins, status) in rows:
        if not granted_coins or granted_coins <= 0:
            skipped_zero_coins += 1
            entries.append({
                "claim_id": claim_id,
                "user_id": user_id,
                "granted_coins": granted_coins,
                "result": "skipped_zero_coins",
            })
            continue

        reason = _leaderboard_grant_reason(row_board_type, row_period_key, rank_band)
        try:
            grant_coins_fn(user_id, granted_coins, reason=reason)
        except Exception as exc:
            failed += 1
            conn.execute(
                _UPDATE_CLAIM_FAILED_SQL,
                {"id": claim_id, "error_message": str(exc)[:500]},
            )
            entries.append({
                "claim_id": claim_id,
                "user_id": user_id,
                "granted_coins": granted_coins,
                "result": "failed",
                "error_message": str(exc)[:500],
            })
            continue

        granted_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn.execute(
            _UPDATE_CLAIM_GRANTED_SQL,
            {"id": claim_id, "granted_at": granted_at},
        )
        granted += 1
        entries.append({
            "claim_id": claim_id,
            "user_id": user_id,
            "granted_coins": granted_coins,
            "result": "granted",
            "reason": reason,
        })

    return {
        "board_type": board_type,
        "period_key": period_key,
        "dry_run": False,
        "claims": {
            "granted": granted,
            "failed": failed,
            "skipped_zero_coins": skipped_zero_coins,
        },
        "entries": entries,
    }


# ── Phase 1 / PR 4A.1: claim status semantics guard rails ──────────────
#
# `leaderboard_reward_claims.status == 'granted'` is set exclusively by the
# Phase 1 / PR 4A coins-only grant layer above. It means "the coins
# component of this claim has been settled" — nothing more. It is NOT a
# signal that the whole reward bundle (coins + items + badges + titles) has
# been granted. As of Phase 1, no code path grants items/badges/titles at
# all: `granted_items_json` / `granted_badges_json` / `granted_titles_json`
# are only ever written once, at finalize time (PR 3), and are never
# cleared or consumed by anything.
#
# A future PR (4B / 4C) that adds item/badge/title granting MUST NOT read
# status == 'granted' as "this claim is fully done, skip it" — that would
# silently skip granting the item/badge/title payload for every claim PR
# 4A already processed. Use `is_leaderboard_claim_fully_granted` (or
# `leaderboard_claim_has_unsettled_non_coin_rewards`) instead of checking
# `status` directly for that decision.

def _leaderboard_reward_json_is_empty(value):
    """True if a granted_items_json/granted_badges_json/granted_titles_json
    value (either the raw DB string or an already-decoded dict/list)
    represents "nothing here" — None, '{}', '[]', or an empty container."""
    if value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return True
        try:
            value = json.loads(stripped)
        except ValueError:
            return False
    if isinstance(value, (dict, list, tuple, set)):
        return len(value) == 0
    return not bool(value)


def leaderboard_claim_has_unsettled_non_coin_rewards(claim):
    """True if `claim` (a mapping with granted_items_json/granted_badges_json/
    granted_titles_json keys, matching the leaderboard_reward_claims columns
    and the dict shape returned by make_leaderboard_reward_claim_record)
    still carries an items/badges/titles payload that has not been granted.

    This is independent of `status` — a claim already marked 'granted' by
    the Phase 1 / PR 4A coins-only grant layer can still have unsettled
    non-coin rewards, because that layer never touches these fields."""
    return (
        not _leaderboard_reward_json_is_empty(claim.get("granted_items_json"))
        or not _leaderboard_reward_json_is_empty(claim.get("granted_badges_json"))
        or not _leaderboard_reward_json_is_empty(claim.get("granted_titles_json"))
    )


def is_leaderboard_claim_coins_settled(claim):
    """True only if the coins component of `claim` has been processed by the
    Phase 1 / PR 4A grant layer. This does NOT mean the whole reward bundle
    (items/badges/titles) has been granted — see
    is_leaderboard_claim_fully_granted for that check.

    Phase 1A semantics: `status == 'granted'` means "coins component
    settled", nothing more. 'pending', 'skipped', and 'failed' are never
    coins-settled."""
    return claim.get("status") == CLAIM_STATUS_GRANTED


def is_leaderboard_claim_fully_granted(claim):
    """True only if the ENTIRE reward bundle for `claim` — coins AND any
    items/badges/titles — has been granted. As of Phase 1 (through PR 4A),
    no code path ever grants items/badges/titles, so this predicate can
    currently only be true for a claim whose reward bundle was coins-only
    to begin with (no items/badges/titles payload at all).

    Do not use `status == 'granted'` alone as a stand-in for this check: the
    Phase 1 / PR 4A coins-only grant layer sets status='granted' as soon as
    coins are settled, even if the claim still carries an unsettled items/
    badges/titles payload for a later PR (4B/4C) to grant."""
    return (
        is_leaderboard_claim_coins_settled(claim)
        and not leaderboard_claim_has_unsettled_non_coin_rewards(claim)
    )


# ── Phase 1 / PR 4B: badge/title grant planning (dry-run preview only) ──
#
# This section is read-only planning: it extracts and previews the
# badge/title portion of a claim's reward payload so a later PR can decide
# how to actually grant them. It never writes to any real badge or wardrobe
# storage table, never grants anything, and never calls any coin- or
# shop-purchase-granting helper. Every function here takes plain
# claim dicts/mappings (matching the leaderboard_reward_claims columns and
# the shape returned by make_leaderboard_reward_claim_record) and returns
# plain dicts — no DB access, no side effects.
#
# Per PR 4A.1 semantics: `status == 'granted'` only means the coins
# component has been settled. A claim can be 'granted' and still carry an
# unread badge/title payload — this module must keep previewing that
# payload rather than treating 'granted' as "nothing left to do here".

def _decode_leaderboard_reward_json_list(value, field_name):
    """Decode a granted_badges_json/granted_titles_json value into a list of
    reward key strings. Accepts the raw DB JSON string, an already-decoded
    list, or None/empty-string (both treated as "no rewards"). Raises
    ValueError on malformed JSON or a JSON value that isn't a list — this
    reads a real reward payload for planning purposes, so it must not
    silently drop badges/titles it fails to parse."""
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            value = json.loads(stripped)
        except ValueError as exc:
            raise ValueError(f"invalid JSON in {field_name}: {value!r}") from exc
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must decode to a list, got {type(value).__name__}")
    return list(value)


def extract_leaderboard_badge_title_payload(claim):
    """Read-only extraction of the badge/title reward payload from `claim`
    (a mapping with granted_badges_json / granted_titles_json keys). Pure
    data read — never writes anything, never grants anything.

    Returns {"badges": [...], "titles": [...]}, each a plain list of reward
    key strings in original order. Raises ValueError if either field
    contains a forbidden reward key (see FORBIDDEN_REWARD_ITEM_KEYS, e.g.
    ai_explain_ticket) or fails to decode as a JSON list.
    """
    badges = _decode_leaderboard_reward_json_list(
        claim.get("granted_badges_json"), "granted_badges_json")
    titles = _decode_leaderboard_reward_json_list(
        claim.get("granted_titles_json"), "granted_titles_json")
    forbidden = FORBIDDEN_REWARD_ITEM_KEYS & set(badges) | FORBIDDEN_REWARD_ITEM_KEYS & set(titles)
    if forbidden:
        raise ValueError(f"reward payload contains forbidden key(s): {sorted(forbidden)}")
    return {"badges": badges, "titles": titles}


def preview_leaderboard_badge_title_reward_claim(claim):
    """Dry-run-only preview of a single claim's badge/title reward status.
    Never writes to any real badge or wardrobe storage table, never grants
    anything, never calls any grant function — this is a pure read-only
    projection for a later PR (4C+) to act on.

    Does NOT treat status == 'granted' as "nothing left to do": PR 4A's
    coins-only grant layer sets status='granted' once coins are settled
    even when the badge/title payload is still unsettled, so a 'granted'
    claim with a non-empty granted_badges_json/granted_titles_json is
    previewed with would_grant_badges/would_grant_titles True.

    'skipped' and 'failed' claims never preview a grant — badges_to_preview
    / titles_to_preview are empty and would_grant_badges/would_grant_titles
    are False regardless of payload, since nothing should ever be granted
    for those claims. 'pending' claims ARE previewed (coins_settled will be
    False) — this PR does not decide whether a future grant step requires
    coins to be settled first; that policy is left to PR 4C.
    """
    payload = extract_leaderboard_badge_title_payload(claim)
    status = claim.get("status")
    blocks_preview = status in (CLAIM_STATUS_SKIPPED, CLAIM_STATUS_FAILED)
    badges_to_preview = [] if blocks_preview else payload["badges"]
    titles_to_preview = [] if blocks_preview else payload["titles"]
    items_json = claim.get("granted_items_json")

    return {
        "claim_id": claim.get("claim_id", claim.get("id")),
        "user_id": claim.get("user_id"),
        "board_type": claim.get("board_type"),
        "period_key": claim.get("period_key"),
        "rank": claim.get("rank"),
        "rank_band": claim.get("rank_band"),
        "reward_bundle_key": claim.get("reward_bundle_key"),
        "status": status,
        "coins_settled": is_leaderboard_claim_coins_settled(claim),
        "has_unsettled_non_coin_rewards": leaderboard_claim_has_unsettled_non_coin_rewards(claim),
        "items_pending": not _leaderboard_reward_json_is_empty(items_json),
        "badges_to_preview": badges_to_preview,
        "titles_to_preview": titles_to_preview,
        "would_grant_badges": bool(badges_to_preview),
        "would_grant_titles": bool(titles_to_preview),
        "dry_run_only": True,
    }


def preview_leaderboard_badge_title_rewards(claims):
    """Dry-run-only preview of badge/title reward status for a list of claim
    dicts. Preserves input order, never mutates the input claim dicts,
    writes nothing, and never calls any grant function — see
    preview_leaderboard_badge_title_reward_claim for the per-claim rules."""
    return [preview_leaderboard_badge_title_reward_claim(claim) for claim in claims]


# ── Phase 1 / PR 4C: non-coin (badge/title/item) grant helpers ─────────
#
# These helpers extend the read-only PR 4B preview layer with actual
# granting logic, but ONLY through injected callables — nothing here ever
# writes to a real badge, wardrobe, or item/inventory storage table, never
# touches leaderboard_reward_claims (no status update, no DB access at
# all — these functions take a plain in-memory list of claim dicts, not a
# DB connection), and is not wired into any live path, scheduler, or
# frontend. A future PR must explicitly wire these into a request path or
# job before they do anything in production.
#
# Ownership-check and grant callables are both injected by the caller
# (mirroring PR 4A's grant_coins_fn pattern), so this module never imports
# or calls the real coin-granting or shop-purchase-granting helpers, and
# tests never touch real granting code.
#
# Per PR 4A.1 / PR 4B semantics, `status == 'granted'` only means the coins
# component has been settled — it is NOT a signal to skip a claim here.
# Only 'skipped' and 'failed' claims are excluded from grant consideration;
# 'pending' and 'granted' claims are both eligible for badge/title/item
# granting, independent of whether their coins have been settled. This PR
# does not decide whether a future production wiring should require coins
# to be settled first — that policy is left to whichever PR actually wires
# these helpers into a live path.

def _decode_leaderboard_item_payload(value):
    """Decode a granted_items_json value into a dict of item_key -> qty.
    Accepts the raw DB JSON string, an already-decoded dict, or
    None/empty-string (both treated as "no items"). Raises ValueError on
    malformed JSON or a JSON value that isn't an object."""
    if value is None:
        return {}
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return {}
        try:
            value = json.loads(stripped)
        except ValueError as exc:
            raise ValueError(f"invalid JSON in granted_items_json: {value!r}") from exc
    if not isinstance(value, dict):
        raise ValueError(
            f"granted_items_json must decode to an object, got {type(value).__name__}")
    return dict(value)


def extract_leaderboard_item_payload(claim):
    """Read-only extraction of the item reward payload from `claim` (a
    mapping with a granted_items_json key). Pure data read — never writes
    anything, never grants anything.

    Returns a dict of item_key -> qty. Raises ValueError if the payload
    contains a forbidden reward key (see FORBIDDEN_REWARD_ITEM_KEYS, e.g.
    ai_explain_ticket) or fails to decode as a JSON object."""
    items = _decode_leaderboard_item_payload(claim.get("granted_items_json"))
    _validate_no_forbidden_reward_items(items)
    return items


def _leaderboard_non_coin_grant_reason(claim, reward_kind, reward_key):
    return (
        f"community_leaderboard:{claim.get('board_type')}:{claim.get('period_key')}:"
        f"{claim.get('rank_band')}:{reward_kind}:{reward_key}"
    )


def _leaderboard_claim_id(claim):
    return claim.get("claim_id", claim.get("id"))


def _process_leaderboard_keyed_reward_grants(
    claims, reward_kind, extract_keys_fn, dry_run, is_owned_fn, grant_fn,
):
    """Shared engine behind grant_leaderboard_badge_rewards and
    grant_leaderboard_title_rewards — both reward kinds are a flat list of
    string keys (no quantity), unlike items."""
    if not dry_run and grant_fn is None:
        raise ValueError(f"grant_fn is required when dry_run=False for {reward_kind} rewards")
    if not dry_run and is_owned_fn is None:
        raise ValueError(f"is_owned_fn is required when dry_run=False for {reward_kind} rewards")

    granted = 0
    failed = 0
    already_owned = 0
    skipped = 0
    entries = []

    for claim in claims:
        status = claim.get("status")
        user_id = claim.get("user_id")
        claim_id = _leaderboard_claim_id(claim)
        blocked = status in (CLAIM_STATUS_SKIPPED, CLAIM_STATUS_FAILED)
        keys = [] if blocked else extract_keys_fn(claim)

        if not keys:
            skipped += 1
            entries.append({
                "claim_id": claim_id,
                "user_id": user_id,
                "reward_kind": reward_kind,
                "reward_key": None,
                "result": "skipped_no_reward",
            })
            continue

        for key in keys:
            if dry_run:
                entries.append({
                    "claim_id": claim_id,
                    "user_id": user_id,
                    "reward_kind": reward_kind,
                    "reward_key": key,
                    "result": "would_grant",
                    "dry_run": True,
                })
                continue

            if is_owned_fn(user_id, key):
                already_owned += 1
                entries.append({
                    "claim_id": claim_id,
                    "user_id": user_id,
                    "reward_kind": reward_kind,
                    "reward_key": key,
                    "result": "already_owned",
                })
                continue

            reason = _leaderboard_non_coin_grant_reason(claim, reward_kind, key)
            try:
                grant_fn(user_id, key, reason=reason)
            except Exception as exc:
                failed += 1
                entries.append({
                    "claim_id": claim_id,
                    "user_id": user_id,
                    "reward_kind": reward_kind,
                    "reward_key": key,
                    "result": "failed",
                    "error_message": str(exc)[:500],
                })
                continue

            granted += 1
            entries.append({
                "claim_id": claim_id,
                "user_id": user_id,
                "reward_kind": reward_kind,
                "reward_key": key,
                "result": "granted",
                "reason": reason,
            })

    return {
        "dry_run": dry_run,
        "reward_kind": reward_kind,
        "granted": granted,
        "failed": failed,
        "already_owned": already_owned,
        "skipped": skipped,
        "entries": entries,
    }


def grant_leaderboard_badge_rewards(
    claims, dry_run=True, is_badge_owned_fn=None, grant_badge_fn=None,
):
    """Grant (or dry-run preview) the badge component of a list of claim
    dicts. Pure in-memory processing — takes no DB connection, performs no
    DB writes, and never updates claim status; the caller owns persisting
    any result.

    dry_run=True (default): no callable is invoked (both may be omitted),
    returns a 'would_grant' entry per badge key found.

    dry_run=False: requires both `is_badge_owned_fn(user_id, badge_key)`
    (return True to skip an already-owned badge without granting again)
    and `grant_badge_fn(user_id, badge_key, reason=...)`. If grant_badge_fn
    raises, that badge's entry is marked 'failed' with error_message set —
    it is never marked granted and the exception is not propagated.

    'skipped' and 'failed' claims are never granted. 'pending' and
    'granted' claims are both eligible (see the PR 4C module note above for
    why claim status alone does not gate badge/title/item granting).
    Claims with an empty or missing badge payload produce a
    'skipped_no_reward' entry. ai_explain_ticket can never appear as a
    badge key — extract_leaderboard_badge_title_payload raises ValueError
    first if it does.
    """
    return _process_leaderboard_keyed_reward_grants(
        claims, "badge",
        lambda claim: extract_leaderboard_badge_title_payload(claim)["badges"],
        dry_run, is_badge_owned_fn, grant_badge_fn,
    )


def grant_leaderboard_title_rewards(
    claims, dry_run=True, is_title_owned_fn=None, grant_title_fn=None,
):
    """Grant (or dry-run preview) the title component of a list of claim
    dicts. Same contract as grant_leaderboard_badge_rewards — pure
    in-memory processing, no DB writes, no claim status update.

    dry_run=False requires `is_title_owned_fn(user_id, title_key)` and
    `grant_title_fn(user_id, title_key, reason=...)`.
    """
    return _process_leaderboard_keyed_reward_grants(
        claims, "title",
        lambda claim: extract_leaderboard_badge_title_payload(claim)["titles"],
        dry_run, is_title_owned_fn, grant_title_fn,
    )


def grant_leaderboard_item_rewards(
    claims, dry_run=True, is_item_owned_fn=None, grant_item_fn=None,
):
    """Grant (or dry-run preview) the item component of a list of claim
    dicts. Pure in-memory processing — takes no DB connection, performs no
    DB writes, and never updates claim status.

    dry_run=True (default): no callable is invoked, returns a 'would_grant'
    entry per (item_key, qty) pair found.

    dry_run=False: requires both `is_item_owned_fn(user_id, item_key)`
    (return True to skip an item this user already owns/has already
    claimed) and `grant_item_fn(user_id, item_key, qty, reason=...)`. If
    grant_item_fn raises, that item's entry is marked 'failed' with
    error_message set — never marked granted, exception not propagated.

    'skipped' and 'failed' claims are never granted; 'pending' and
    'granted' claims are both eligible. ai_explain_ticket can never appear
    as an item key — extract_leaderboard_item_payload raises ValueError
    first if it does.
    """
    if not dry_run and grant_item_fn is None:
        raise ValueError("grant_item_fn is required when dry_run=False for item rewards")
    if not dry_run and is_item_owned_fn is None:
        raise ValueError("is_item_owned_fn is required when dry_run=False for item rewards")

    granted = 0
    failed = 0
    already_owned = 0
    skipped = 0
    entries = []

    for claim in claims:
        status = claim.get("status")
        user_id = claim.get("user_id")
        claim_id = _leaderboard_claim_id(claim)
        blocked = status in (CLAIM_STATUS_SKIPPED, CLAIM_STATUS_FAILED)
        items = {} if blocked else extract_leaderboard_item_payload(claim)

        if not items:
            skipped += 1
            entries.append({
                "claim_id": claim_id,
                "user_id": user_id,
                "reward_kind": "item",
                "item_key": None,
                "qty": 0,
                "result": "skipped_no_reward",
            })
            continue

        for item_key, qty in items.items():
            if dry_run:
                entries.append({
                    "claim_id": claim_id,
                    "user_id": user_id,
                    "reward_kind": "item",
                    "item_key": item_key,
                    "qty": qty,
                    "result": "would_grant",
                    "dry_run": True,
                })
                continue

            if is_item_owned_fn(user_id, item_key):
                already_owned += 1
                entries.append({
                    "claim_id": claim_id,
                    "user_id": user_id,
                    "reward_kind": "item",
                    "item_key": item_key,
                    "qty": qty,
                    "result": "already_owned",
                })
                continue

            reason = _leaderboard_non_coin_grant_reason(claim, "item", item_key)
            try:
                grant_item_fn(user_id, item_key, qty, reason=reason)
            except Exception as exc:
                failed += 1
                entries.append({
                    "claim_id": claim_id,
                    "user_id": user_id,
                    "reward_kind": "item",
                    "item_key": item_key,
                    "qty": qty,
                    "result": "failed",
                    "error_message": str(exc)[:500],
                })
                continue

            granted += 1
            entries.append({
                "claim_id": claim_id,
                "user_id": user_id,
                "reward_kind": "item",
                "item_key": item_key,
                "qty": qty,
                "result": "granted",
                "reason": reason,
            })

    return {
        "dry_run": dry_run,
        "reward_kind": "item",
        "granted": granted,
        "failed": failed,
        "already_owned": already_owned,
        "skipped": skipped,
        "entries": entries,
    }


# ── Phase 3A: unified reward-bundle grant contract (preview-only) ──────
#
# This is a pure aggregation layer over the four already-independently-
# tested component functions above (grant_leaderboard_reward_claims for
# coins, grant_leaderboard_item_rewards, grant_leaderboard_badge_rewards,
# grant_leaderboard_title_rewards). It does not reimplement any of their
# logic and does not change leaderboard_reward_claims.status semantics:
# per PR 4A.1, status == 'granted' still means only "the coins component
# has been settled" — this function's own `claims_granted` /
# `claims_failed` counters are a computed summary of THIS RUN's results
# across all four components, not a new persisted status value (adding
# one would require a schema migration to the CLAIM_STATUSES CHECK
# constraint, which is out of scope for Phase 3A).
#
# Not wired into grant-commit, the scheduler, or any route in Phase 3A —
# grant-commit remains hard-disabled regardless of this function's
# existence (see tools/community_leaderboard_rewards_manual.py's
# GRANT_COMMIT_DISABLED_MESSAGE, which this module does not touch).

_BUNDLE_CLAIM_COLUMNS = [
    "id", "user_id", "board_type", "period_key", "rank", "rank_band", "score",
    "eligible", "ineligible_reason", "reward_bundle_key", "granted_coins",
    "granted_items_json", "granted_badges_json", "granted_titles_json",
    "status", "error_message", "created_at", "granted_at",
]

_SELECT_ALL_CLAIMS_FOR_BUNDLE_SQL = """SELECT {columns}
    FROM leaderboard_reward_claims
    WHERE board_type = %(board_type)s AND period_key = %(period_key)s
    ORDER BY id""".format(columns=", ".join(_BUNDLE_CLAIM_COLUMNS))


def _fetch_claims_for_reward_bundle(conn, board_type, period_key):
    """Read-only fetch of every leaderboard_reward_claims row for one
    board_type/period_key, as plain dicts with a 'claim_id' alias of 'id'
    (matching what grant_leaderboard_badge_rewards / _title_rewards /
    _item_rewards expect). No writes."""
    rows = conn.execute(
        _SELECT_ALL_CLAIMS_FOR_BUNDLE_SQL,
        {"board_type": board_type, "period_key": period_key},
    ).fetchall()
    claims = []
    for row in rows:
        claim = dict(zip(_BUNDLE_CLAIM_COLUMNS, row))
        claim["claim_id"] = claim["id"]
        claims.append(claim)
    return claims


def grant_leaderboard_reward_bundle(
    conn,
    *,
    board_type,
    period_key,
    dry_run=True,
    grant_coins_fn=None,
    grant_item_fn=None,
    grant_badge_fn=None,
    grant_title_fn=None,
    is_item_owned_fn=None,
    is_badge_owned_fn=None,
    is_title_owned_fn=None,
):
    """Unified preview/grant summary across all four reward components
    (coins, items, badges, titles) for one board_type/period_key.

    dry_run=True (default): every component is previewed only (no grant
    function is ever called, no DB write). Safe to call with every
    grant_*_fn/is_*_owned_fn left as None.

    dry_run=False: requires ALL of grant_coins_fn, grant_item_fn,
    grant_badge_fn, grant_title_fn, is_item_owned_fn, is_badge_owned_fn,
    and is_title_owned_fn (raises ValueError naming whichever are
    missing) -- a real, idempotent, ownership-aware grant cannot safely
    run without all seven. Only 'pending' and 'granted' claims are
    considered for the non-coin components (matching
    grant_leaderboard_badge_rewards's own rule); only 'pending' claims
    with eligible=1 are considered for coins (matching
    grant_leaderboard_reward_claims's own rule). 'skipped' and 'failed'
    claims are never touched by any component, and failed claims are
    never automatically retried in Phase 3A.

    A claim is counted in `claims_granted` only if every reward component
    it actually carries a non-empty payload for succeeded in this run
    (coins, and/or items, and/or badges, and/or titles, whichever this
    specific claim's reward_payload includes); if any of those succeeded
    but at least one failed, it is counted in `claims_failed` instead, and
    its per-component error is recorded in `errors`. This is a computed
    judgement over the four components' own per-run results -- it does
    not read or write any single persisted "fully granted" status value.

    Returns a dict with claims_seen, claims_grantable, claims_would_grant,
    claims_granted, claims_failed, coins_would_grant, coins_granted,
    items_would_grant, items_granted, badges_would_grant, badges_granted,
    titles_would_grant, titles_granted, errors, dry_run, and the four raw
    component results under coins_result/item_result/badge_result/
    title_result for callers that want the full detail.
    """
    validate_leaderboard_board_type(board_type)

    if not dry_run:
        required = {
            "grant_coins_fn": grant_coins_fn,
            "grant_item_fn": grant_item_fn,
            "grant_badge_fn": grant_badge_fn,
            "grant_title_fn": grant_title_fn,
            "is_item_owned_fn": is_item_owned_fn,
            "is_badge_owned_fn": is_badge_owned_fn,
            "is_title_owned_fn": is_title_owned_fn,
        }
        missing = [name for name, fn in required.items() if fn is None]
        if missing:
            raise ValueError(
                "dry_run=False requires all grant/ownership functions; missing: "
                + ", ".join(missing)
            )

    coins_result = grant_leaderboard_reward_claims(
        conn, board_type, period_key, dry_run=dry_run, grant_coins_fn=grant_coins_fn)

    claims = _fetch_claims_for_reward_bundle(conn, board_type, period_key)

    item_result = grant_leaderboard_item_rewards(
        claims, dry_run=dry_run, is_item_owned_fn=is_item_owned_fn, grant_item_fn=grant_item_fn)
    badge_result = grant_leaderboard_badge_rewards(
        claims, dry_run=dry_run, is_badge_owned_fn=is_badge_owned_fn, grant_badge_fn=grant_badge_fn)
    title_result = grant_leaderboard_title_rewards(
        claims, dry_run=dry_run, is_title_owned_fn=is_title_owned_fn, grant_title_fn=grant_title_fn)

    # Per-claim outcome across all four components, keyed by claim_id.
    per_claim = {claim["claim_id"]: {"attempted": False, "failed": False} for claim in claims}

    coins_entries = coins_result.get("preview") if dry_run else coins_result.get("entries", [])
    for entry in coins_entries or []:
        claim_id = entry.get("claim_id")
        if claim_id not in per_claim:
            continue
        if dry_run:
            if entry.get("would_grant"):
                per_claim[claim_id]["attempted"] = True
        else:
            result = entry.get("result")
            if result == "granted":
                per_claim[claim_id]["attempted"] = True
            elif result == "failed":
                per_claim[claim_id]["attempted"] = True
                per_claim[claim_id]["failed"] = True

    errors = []

    def _fold_non_coin_component(component_result, reward_kind):
        for entry in component_result.get("entries", []):
            claim_id = entry.get("claim_id")
            if claim_id not in per_claim:
                continue
            result = entry.get("result")
            if result in ("would_grant",):
                per_claim[claim_id]["attempted"] = True
            elif result == "granted":
                per_claim[claim_id]["attempted"] = True
            elif result == "failed":
                per_claim[claim_id]["attempted"] = True
                per_claim[claim_id]["failed"] = True
                errors.append({
                    "claim_id": claim_id,
                    "component": reward_kind,
                    "error_message": entry.get("error_message"),
                })
            # "already_owned" / "skipped_no_reward" / "duplicate_user_id" /
            # "missing_score" do not count as an attempt for this claim.

    _fold_non_coin_component(item_result, "item")
    _fold_non_coin_component(badge_result, "badge")
    _fold_non_coin_component(title_result, "title")

    claims_grantable = sum(
        1 for claim in claims if claim["status"] not in (CLAIM_STATUS_SKIPPED, CLAIM_STATUS_FAILED)
    )
    claims_would_grant = sum(1 for v in per_claim.values() if dry_run and v["attempted"])
    claims_granted = sum(
        1 for v in per_claim.values() if not dry_run and v["attempted"] and not v["failed"]
    )
    claims_failed = sum(1 for v in per_claim.values() if not dry_run and v["failed"])

    def _would_grant_count(component_result, is_coins=False):
        if is_coins:
            return sum(1 for e in component_result.get("preview", []) if e.get("would_grant"))
        return sum(1 for e in component_result.get("entries", []) if e.get("result") == "would_grant")

    def _granted_count(component_result, is_coins=False):
        if is_coins:
            return sum(1 for e in component_result.get("entries", []) if e.get("result") == "granted")
        return component_result.get("granted", 0)

    return {
        "board_type": board_type,
        "period_key": period_key,
        "dry_run": dry_run,
        "claims_seen": len(claims),
        "claims_grantable": claims_grantable,
        "claims_would_grant": claims_would_grant,
        "claims_granted": claims_granted,
        "claims_failed": claims_failed,
        "coins_would_grant": _would_grant_count(coins_result, is_coins=True) if dry_run else None,
        "coins_granted": _granted_count(coins_result, is_coins=True) if not dry_run else None,
        "items_would_grant": _would_grant_count(item_result) if dry_run else None,
        "items_granted": _granted_count(item_result) if not dry_run else None,
        "badges_would_grant": _would_grant_count(badge_result) if dry_run else None,
        "badges_granted": _granted_count(badge_result) if not dry_run else None,
        "titles_would_grant": _would_grant_count(title_result) if dry_run else None,
        "titles_granted": _granted_count(title_result) if not dry_run else None,
        "errors": errors,
        "coins_result": coins_result,
        "item_result": item_result,
        "badge_result": badge_result,
        "title_result": title_result,
    }


# ── Phase 3B: real backend adapters (fail-on-shortfall, weekly-scope) ───
#
# These adapters are thin, defensive wrappers meant to sit between
# grant_leaderboard_reward_bundle's injection points and the real
# production coin-granting / shop-purchase-granting / badge-storage
# helpers discovered in Phase 3B-0
# (docs/deployment/community_leaderboard_rewards_phase3b0_grant_backend_discovery.md).
# None of them import app.py or call any real production helper directly
# -- `grant_coins_fn` / `grant_item_fn` / `grant_badge_fn` are still
# injected by the caller (mirroring every prior PR in this series), so
# this module never touches real production granting code and stays
# fully testable with fakes.
#
# As of Phase 3B, NOTHING calls these adapters with real functions in
# production -- they exist so a real, reviewed wiring step (and the
# actual production grant-commit decision) can happen later, entirely
# separately from this commit.

_WEEKLY_SAFE_ITEM_KEYS = frozenset({"small_xp_potion", "xp_potion"})
# Phase 3B badge allowlist is deliberately narrow (weekly only). Monthly
# badge keys (badge_lb_monthly_1, badge_lb_monthly_top3,
# badge_lb_monthly_top10) are not yet in app.py's BADGE_DEFS and are
# explicitly deferred -- see the Phase 3B-0 discovery doc. Whoever adds a
# new reward badge to BADGE_DEFS must also add it here.
_PHASE_3B_ALLOWED_BADGE_KEYS = frozenset({"badge_lb_weekly_1"})


def is_phase_3b_item_key_allowed(item_key):
    """True if `item_key` is on the Phase 3B weekly-safe item allowlist
    (see grant_community_leaderboard_item's docstring for why this is
    narrower than the full reward-bundle item space)."""
    return item_key in _WEEKLY_SAFE_ITEM_KEYS


def is_phase_3b_badge_key_allowed(badge_key):
    """True if `badge_key` is on the Phase 3B weekly-safe badge allowlist
    (see grant_community_leaderboard_badge's docstring)."""
    return badge_key in _PHASE_3B_ALLOWED_BADGE_KEYS


def is_leaderboard_reward_component_logged(conn, claim_id, component, reward_key):
    """Read-only check against leaderboard_reward_component_log: has this
    exact (claim_id, component, reward_key) already been logged as
    'granted'? This is the idempotency mechanism for items in particular
    -- unlike badges/titles (which have a natural ownership table with a
    UNIQUE constraint), stackable inventory quantities accumulate and
    have no per-claim "already granted" signal on their own."""
    row = conn.execute(
        "SELECT result FROM leaderboard_reward_component_log "
        "WHERE claim_id = %(claim_id)s AND component = %(component)s "
        "AND reward_key = %(reward_key)s",
        {"claim_id": claim_id, "component": component, "reward_key": reward_key},
    ).fetchone()
    return row is not None and row[0] == "granted"


def log_leaderboard_reward_component(
    conn, claim_id, component, reward_key, quantity, result, detail=None,
):
    """Insert one leaderboard_reward_component_log row. Idempotent: a
    duplicate (claim_id, component, reward_key) is a silent no-op (`ON
    CONFLICT DO NOTHING`), matching the table's own UNIQUE constraint --
    calling this twice for the same successful grant can never create a
    second row or overwrite the first outcome."""
    conn.execute(
        """INSERT INTO leaderboard_reward_component_log
           (claim_id, component, reward_key, quantity, result, detail, created_at)
           VALUES (%(claim_id)s, %(component)s, %(reward_key)s, %(quantity)s,
                   %(result)s, %(detail)s, %(created_at)s)
           ON CONFLICT (claim_id, component, reward_key) DO NOTHING""",
        {
            "claim_id": claim_id,
            "component": component,
            "reward_key": reward_key,
            "quantity": quantity,
            "result": result,
            "detail": detail,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
    )


def grant_community_leaderboard_coins(
    conn,
    *,
    user_id,
    amount,
    reason,
    claim_id,
    grant_coins_fn,
):
    """Wrap an injected coin-granting callable with fail-on-shortfall
    behavior. Phase 3B-0 found that app.py's real coin-granting helper
    silently clamps to a daily income cap and returns the *actual* amount
    granted (which can be less than requested, or 0) without raising -- if
    a caller only checks for an exception, a capped/blocked grant would be
    invisible. This adapter makes that impossible to miss: any amount
    granted that doesn't exactly equal the requested amount is treated as
    a failure, not a partial success.

    Requires `grant_coins_fn(user_id, amount, reason=...)` -- no default,
    since there is no safe generic coin-granting behavior to fall back to.
    `grant_coins_fn` is expected to return the actual amount granted (an
    int), matching the real coin-granting helper's contract; returning
    `None` is treated as a contract violation and raises, since this
    adapter cannot tell whether the full amount was actually granted.

    Never commits (caller owns the transaction), never updates
    `leaderboard_reward_claims.status` itself -- that remains the
    responsibility of whichever code actually persists this claim's
    outcome, matching every other component adapter in this module.
    """
    if grant_coins_fn is None:
        raise ValueError("grant_coins_fn is required")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        raise ValueError(f"amount must be a positive int, got {amount!r}")

    granted = grant_coins_fn(user_id, amount, reason=reason)
    if granted is None:
        raise ValueError(
            f"grant_coins_fn returned None for claim_id={claim_id} user_id={user_id} "
            f"-- expected the actual amount granted (int), per the real coin-granting "
            f"helper's contract"
        )
    if granted != amount:
        raise ValueError(
            f"coin_cap_reached: requested {amount}, granted {granted} "
            f"(claim_id={claim_id}, user_id={user_id})"
        )
    return {
        "claim_id": claim_id,
        "user_id": user_id,
        "component": "coin",
        "reward_key": "coins",
        "quantity": amount,
        "result": "granted",
        "detail": reason,
    }


def grant_community_leaderboard_item(
    conn,
    *,
    user_id,
    item_key,
    quantity,
    claim_id,
    context=None,
    grant_item_fn,
    is_component_logged_fn=None,
    log_component_fn=None,
):
    """Grant one item reward for one claim, restricted to the Phase 3B
    weekly-safe allowlist (`small_xp_potion`, `xp_potion` -- both real,
    confirmed `SHOP_ITEMS` keys). Rejects `appearance_fragment` (the
    monthly-board key that has no real shop-item backend -- see Phase
    3B-0) and any other unrecognized key.

    Idempotency: since the real inventory storage's item quantities
    accumulate (owning some amount of an item doesn't mean "this specific
    claim's reward was already granted"), this checks
    `leaderboard_reward_component_log` for an existing 'granted' row for
    this exact (claim_id, 'item', item_key) *before* calling
    `grant_item_fn`, and logs the outcome (granted/failed) afterward.
    `is_component_logged_fn`/`log_component_fn` default to the real
    read/write helpers above (bound to `conn`), and can be overridden by
    tests.

    Requires `grant_item_fn(user_id, item_key, quantity, context=...)` --
    no default. If it raises, the failure is logged to
    leaderboard_reward_component_log (result='failed') and the exception
    is re-raised -- never silently swallowed.

    Never commits, never updates claim status.
    """
    if item_key not in _WEEKLY_SAFE_ITEM_KEYS:
        raise ValueError(
            f"item_key {item_key!r} is not an allowed Phase 3B reward item "
            f"(allowed: {sorted(_WEEKLY_SAFE_ITEM_KEYS)}); monthly-only keys like "
            "'appearance_fragment' have no real shop-item backend and are "
            "explicitly deferred -- see the Phase 3B-0 discovery doc"
        )
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        raise ValueError(f"quantity must be a positive int, got {quantity!r}")
    if grant_item_fn is None:
        raise ValueError("grant_item_fn is required")

    check_logged = is_component_logged_fn or (
        lambda: is_leaderboard_reward_component_logged(conn, claim_id, "item", item_key))
    write_log = log_component_fn or (
        lambda result, detail=None: log_leaderboard_reward_component(
            conn, claim_id, "item", item_key, quantity, result, detail))

    if check_logged():
        return {
            "claim_id": claim_id,
            "user_id": user_id,
            "component": "item",
            "reward_key": item_key,
            "quantity": quantity,
            "result": "skipped_existing",
            "detail": "already logged in leaderboard_reward_component_log",
        }

    try:
        grant_item_fn(user_id, item_key, quantity, context=context)
    except Exception as exc:
        write_log("failed", str(exc)[:500])
        raise

    write_log("granted", None)
    return {
        "claim_id": claim_id,
        "user_id": user_id,
        "component": "item",
        "reward_key": item_key,
        "quantity": quantity,
        "result": "granted",
        "detail": None,
    }


def grant_community_leaderboard_badge(
    conn,
    *,
    user_id,
    badge_key,
    claim_id,
    grant_badge_fn,
    is_badge_owned_fn=None,
):
    """Grant one badge reward for one claim, restricted to the Phase 3B
    weekly-safe allowlist (`badge_lb_weekly_1` -- the only reward badge
    key actually present in any currently-committed claim). Rejects any
    other badge key; monthly badge keys are deferred until they're added
    to both app.py's `BADGE_DEFS` and `_PHASE_3B_ALLOWED_BADGE_KEYS`.

    Idempotency: the real badge storage table already enforces a
    `PRIMARY KEY(user_id, badge_id)`, so a duplicate grant is inherently
    harmless -- but this still checks `is_badge_owned_fn(user_id, badge_key)` first (when
    supplied) so a caller can distinguish "already owned, nothing to do"
    from "newly granted" without relying on catching a constraint error.

    Requires `grant_badge_fn(user_id, badge_key)` -- no default. If it
    raises, the exception propagates (never silently swallowed).

    Never commits, never updates claim status.
    """
    if badge_key not in _PHASE_3B_ALLOWED_BADGE_KEYS:
        raise ValueError(
            f"badge_key {badge_key!r} is not an allowed Phase 3B reward badge "
            f"(allowed: {sorted(_PHASE_3B_ALLOWED_BADGE_KEYS)}); monthly badge keys "
            "are deferred -- see the Phase 3B-0 discovery doc"
        )
    if grant_badge_fn is None:
        raise ValueError("grant_badge_fn is required")

    if is_badge_owned_fn is not None and is_badge_owned_fn(user_id, badge_key):
        return {
            "claim_id": claim_id,
            "user_id": user_id,
            "component": "badge",
            "reward_key": badge_key,
            "quantity": 1,
            "result": "skipped_existing",
            "detail": "already owned",
        }

    grant_badge_fn(user_id, badge_key)

    return {
        "claim_id": claim_id,
        "user_id": user_id,
        "component": "badge",
        "reward_key": badge_key,
        "quantity": 1,
        "result": "granted",
        "detail": None,
    }
