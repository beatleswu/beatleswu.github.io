"""Server-owned Adventure Zone-star authority.

Boss attempts and historical compatibility are not inputs to normal new
Zone-star earning.  A Zone star can only be added by a caller that has already
received a server-settled Adventure answer identity.  The separate event
ledger makes retries idempotent and keeps the Zone-star write out of
``adventure_boss_progress.stars``.  A separately Owner-gated catch-up policy
may project an already-persisted legacy star level without replaying its
ledger event.
"""

from __future__ import annotations

import os
from typing import Any

from migrations.adventure_zone_star_progression_v1 import (
    EARNINGS_TABLE_NAME,
    PROGRESS_TABLE_NAME,
)


MAX_ZONE_STARS = 3
# The star a Lord clear owns.  Map milestones may only build on top of it.
FIRST_MAP_MILESTONE_STAR = 1
AUTHORITATIVE_ZONE_STAR_SOURCE = "authoritative_adventure_answer"
AUTHORITATIVE_BOSS_CLEAR_SOURCE = "authoritative_boss_clear"

# Restoring the historical Map baseline is deliberately independent from
# granting new milestone state.  An Owner must choose the retroactive policy
# after the dry-run blast radius is reviewed; until then a missing/invalid
# value is fail-closed.  This is configuration-only and is never read from a
# request body or a client projection.
RETROACTIVE_MILESTONE_POLICY_ENV = "GO_ADVENTURE_RETROACTIVE_MILESTONE_POLICY"
RETROACTIVE_POLICY_HOLD = "hold"
RETROACTIVE_POLICY_FULL = "full"
RETROACTIVE_POLICY_LORD_ONLY = "lord_only"
RETROACTIVE_MILESTONE_POLICIES = frozenset(
    {
        RETROACTIVE_POLICY_HOLD,
        RETROACTIVE_POLICY_FULL,
        RETROACTIVE_POLICY_LORD_ONLY,
    }
)


def retroactive_milestone_policy(value: Any = None) -> str:
    """Return the server-owned policy for restored-history star catch-up.

    ``hold`` is the safe default.  The optional argument is useful to a
    separately owner-gated policy seam and tests; production callers use the
    environment value, which is outside client control.  Unknown values
    intentionally become ``hold`` rather than enabling an irreversible write.
    """

    raw = os.environ.get(RETROACTIVE_MILESTONE_POLICY_ENV, RETROACTIVE_POLICY_HOLD)
    if value is not None:
        raw = value
    normalized = str(raw or "").strip().lower()
    return normalized if normalized in RETROACTIVE_MILESTONE_POLICIES else RETROACTIVE_POLICY_HOLD


def retroactive_milestones_allowed(value: Any = None) -> bool:
    """Whether restored historical coverage may drive 2★/3★ writes."""

    return retroactive_milestone_policy(value) == RETROACTIVE_POLICY_FULL


class ZoneStarSchemaUnavailable(RuntimeError):
    """The explicit Zone-star migration has not been admitted/executed."""


def _is_sqlite(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _table_exists(conn: Any, table_name: str) -> bool:
    if _is_sqlite(conn):
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
    else:
        row = conn.execute(
            """SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name=?""",
            (table_name,),
        ).fetchone()
    return row is not None


def _schema_available(conn: Any) -> bool:
    return _table_exists(conn, PROGRESS_TABLE_NAME) and _table_exists(
        conn, EARNINGS_TABLE_NAME
    )


def _clamp_stars(value: Any) -> int:
    try:
        return max(0, min(MAX_ZONE_STARS, int(value or 0)))
    except (TypeError, ValueError):
        return 0


def legacy_visible_star_entitlement(boss_row: Any) -> int:
    """Read the old public projection without treating it as a new award.

    Before R6 the public Adventure ``stars`` field was sourced from the Boss
    row.  The value remains a read-only compatibility entitlement.  It is not
    a normal Zone-star writer input; only the explicit Owner-gated catch-up
    seam may project its already-earned level without a historical ledger
    event.
    """

    if not boss_row:
        return 0
    try:
        return _clamp_stars(boss_row["stars"])
    except (KeyError, IndexError, TypeError):
        return 0


def load_zone_star_rows(conn: Any, user_id: int) -> dict[str, dict[str, Any]]:
    """Read only server-owned Zone-star rows; missing migration is fail-closed.

    The compatibility read path must remain available before the explicit
    production migration runs, so an absent schema is represented as an empty
    authority set rather than as a derived value from questions or Boss rows.
    """

    if not _schema_available(conn):
        return {}
    rows = conn.execute(
        f"SELECT user_id, zone_key, earned_stars, updated_at "
        f"FROM {PROGRESS_TABLE_NAME} WHERE user_id=?",
        (int(user_id),),
    ).fetchall()
    return {
        str(row["zone_key"]): {
            "user_id": int(row["user_id"]),
            "zone_key": str(row["zone_key"]),
            "earned_stars": _clamp_stars(row["earned_stars"]),
            "updated_at": row["updated_at"],
        }
        for row in rows
    }


def zone_star_value(rows: dict[str, dict[str, Any]], zone_key: str) -> int:
    """Return only the first-class Zone-star authority value."""

    row = rows.get(str(zone_key)) or {}
    return _clamp_stars(row.get("earned_stars"))


def _rowcount(cursor: Any) -> int:
    value = getattr(cursor, "rowcount", 0)
    return int(value) if value not in (None, -1) else 0


def _select_progress_row(conn: Any, user_id: int, zone_key: str) -> Any:
    statement = (
        f"SELECT earned_stars FROM {PROGRESS_TABLE_NAME} "
        "WHERE user_id=? AND zone_key=?"
    )
    if not _is_sqlite(conn):
        statement += " FOR UPDATE"
    return conn.execute(statement, (user_id, zone_key)).fetchone()


def _legacy_star_entitlement(conn: Any, user_id: int, zone_key: str) -> int:
    """Read the persisted legacy star entitlement from server-owned state.

    A legacy Boss row is a read-only compatibility entitlement.  It is not
    copied during the historical baseline migration, and it is consulted here
    only when an explicitly Owner-selected retroactive milestone policy asks
    to let an already-entitled player catch up to 2★/3★.  Missing/invalid
    legacy state fails closed.  The complete persisted level is returned so an
    existing legacy 2★/3★ is preserved without replaying its ledger event.
    """

    try:
        row = conn.execute(
            "SELECT stars FROM adventure_boss_progress "
            "WHERE user_id=? AND zone_key=?",
            (int(user_id), str(zone_key)),
        ).fetchone()
    except Exception:
        # The compatibility path must remain safe in isolated databases where
        # the old Boss table is not present.
        return 0
    if not row:
        return 0
    try:
        value = row["stars"]
    except (KeyError, IndexError, TypeError):
        try:
            value = row[0]
        except (IndexError, TypeError):
            return 0
    return _clamp_stars(value)


def _legacy_first_star_is_server_owned(conn: Any, user_id: int, zone_key: str) -> bool:
    """Check whether the persisted legacy Boss row owns at least 1★."""

    return _legacy_star_entitlement(conn, user_id, zone_key) >= FIRST_MAP_MILESTONE_STAR


def award_zone_star_up_to_map_milestone(
    conn: Any,
    user_id: int,
    zone_key: str,
    submission_id: str,
    earned_at: str,
    *,
    milestone_star: int,
    allow_legacy_first_star_entitlement: bool = False,
) -> dict[str, Any]:
    """Raise a Zone to the star level its Map coverage has legitimately earned.

    Map coverage is never a substitute for the Lord Challenge.  The second and
    third stars are Map milestones, but both require the first star -- which
    only a Lord clear grants -- to already exist.  A Zone still at zero stars
    is therefore left untouched no matter how complete its coverage is.

    This deliberately replaces the earlier "+1 star per settled answer"
    behaviour, under which the first three correct Map answers in a Zone
    walked it straight to three stars without any Lord clear.

    Coverage may jump a milestone (below 60% straight to 100%), so every star
    from the current level up to ``milestone_star`` is written, each as its own
    ledger row under a derived event id.  The caller is responsible for proving
    that ``submission_id`` belongs to a server-settled correct Adventure
    answer; a client grade, historical count, Boss clear, or reward instruction
  can never reach this writer.  The optional legacy entitlement flag is an
  internal, server-owned policy seam: when enabled, the persisted legacy
  Boss ``stars >= 1`` value may seed the separate new authority at its
  already-persisted level so a later 2★/3★ catch-up does not mint a
  historical first-, second-, or third-star event.
    """

    if not _schema_available(conn):
        raise ZoneStarSchemaUnavailable(
            "adventure Zone-star migration is not available"
        )
    normalized_zone = str(zone_key or "").strip()
    normalized_event = str(submission_id or "").strip()
    if not normalized_zone or not normalized_event:
        raise ValueError("zone_key and submission_id are required")
    target = _clamp_stars(milestone_star)
    if target <= FIRST_MAP_MILESTONE_STAR:
        # Nothing above the Lord-owned first star is claimed by this event.
        current_row = _select_progress_row(conn, int(user_id), normalized_zone)
        return {
            "status": "no_milestone",
            "zone_key": normalized_zone,
            "stars": _clamp_stars(current_row["earned_stars"] if current_row else 0),
            "awarded": False,
        }

    uid = int(user_id)
    progress = _select_progress_row(conn, uid, normalized_zone)
    current = _clamp_stars(progress["earned_stars"] if progress else 0)
    if current < FIRST_MAP_MILESTONE_STAR:
        legacy_stars = (
            _legacy_star_entitlement(conn, uid, normalized_zone)
            if allow_legacy_first_star_entitlement
            else 0
        )
        if legacy_stars < FIRST_MAP_MILESTONE_STAR:
            # No first star yet: the Lord has not been cleared, so Map
            # coverage earns nothing.  The progress row is not even created
            # here.
            return {
                "status": "first_star_required",
                "zone_key": normalized_zone,
                "stars": current,
                "awarded": False,
            }
        # This is a compatibility projection of an already persisted,
        # server-owned legacy entitlement, not a newly earned star.  Do not
        # write a ledger event for any already-persisted level; only subsequent
        # 2★/3★ milestones are eligible for this Owner-selected catch-up path.
        conn.execute(
            f"INSERT INTO {PROGRESS_TABLE_NAME} "
            "(user_id, zone_key, earned_stars, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(user_id, zone_key) DO UPDATE SET "
            "earned_stars=CASE WHEN earned_stars < excluded.earned_stars "
            "THEN excluded.earned_stars ELSE earned_stars END, "
            "updated_at=excluded.updated_at",
            (uid, normalized_zone, legacy_stars, earned_at),
        )
        progress = _select_progress_row(conn, uid, normalized_zone)
        current = _clamp_stars(progress["earned_stars"] if progress else 0)
        if current < FIRST_MAP_MILESTONE_STAR:
            return {
                "status": "first_star_required",
                "zone_key": normalized_zone,
                "stars": current,
                "awarded": False,
            }
    if current >= target:
        return {
            "status": "already_earned",
            "zone_key": normalized_zone,
            "stars": current,
            "awarded": False,
        }

    awarded_stars: list[int] = []
    for star_number in range(current + 1, target + 1):
        # One ledger event per star keeps every award individually idempotent
        # even when a single settlement crosses two milestones at once.
        star_event = f"{normalized_event}:star{star_number}"
        inserted = conn.execute(
            f"INSERT INTO {EARNINGS_TABLE_NAME} "
            "(user_id, zone_key, event_id, star_number, source, earned_at) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            (
                uid,
                normalized_zone,
                star_event,
                star_number,
                AUTHORITATIVE_ZONE_STAR_SOURCE,
                earned_at,
            ),
        )
        if _rowcount(inserted) != 1:
            # A concurrent or earlier event already owns this star number.
            # Stop here; never manufacture a different star.
            break
        conn.execute(
            f"UPDATE {PROGRESS_TABLE_NAME} SET earned_stars=?, updated_at=? "
            "WHERE user_id=? AND zone_key=? AND earned_stars < ?",
            (star_number, earned_at, uid, normalized_zone, star_number),
        )
        awarded_stars.append(star_number)

    final_row = _select_progress_row(conn, uid, normalized_zone)
    final = _clamp_stars(final_row["earned_stars"] if final_row else current)
    if not awarded_stars:
        return {
            "status": "already_earned",
            "zone_key": normalized_zone,
            "stars": final,
            "awarded": False,
        }
    return {
        "status": "awarded",
        "zone_key": normalized_zone,
        "stars": final,
        "awarded": True,
        "awarded_stars": awarded_stars,
        "source": AUTHORITATIVE_ZONE_STAR_SOURCE,
        "event_id": normalized_event,
    }


def award_zone_star_from_boss_clear(
    conn: Any,
    user_id: int,
    zone_key: str,
    operation_id: str,
    earned_at: str,
) -> dict[str, Any]:
    """Record the explicit first Zone star earned by a new Boss clear.

    Boss clear remains owned by ``adventure_boss_progress``.  This is only an
    explicit cross-domain event into the separate Zone-star authority; it does
    not copy or update the Boss row's ``stars`` column.
    """

    if not _schema_available(conn):
        raise ZoneStarSchemaUnavailable(
            "adventure Zone-star migration is not available"
        )
    normalized_zone = str(zone_key or "").strip()
    normalized_event = str(operation_id or "").strip()
    if not normalized_zone or not normalized_event:
        raise ValueError("zone_key and operation_id are required")

    uid = int(user_id)
    duplicate = conn.execute(
        f"SELECT zone_key, star_number FROM {EARNINGS_TABLE_NAME} "
        "WHERE user_id=? AND event_id=?",
        (uid, normalized_event),
    ).fetchone()
    if duplicate:
        current_duplicate = _select_progress_row(conn, uid, str(duplicate["zone_key"]))
        return {
            "status": "duplicate",
            "zone_key": str(duplicate["zone_key"]),
            "stars": _clamp_stars(
                current_duplicate["earned_stars"]
                if current_duplicate else duplicate["star_number"]
            ),
            "awarded": False,
        }

    conn.execute(
        f"INSERT INTO {PROGRESS_TABLE_NAME} "
        "(user_id, zone_key, earned_stars, updated_at) VALUES (?,?,0,?) "
        "ON CONFLICT(user_id, zone_key) DO NOTHING",
        (uid, normalized_zone, earned_at),
    )
    progress = _select_progress_row(conn, uid, normalized_zone)
    current = _clamp_stars(progress["earned_stars"] if progress else 0)
    if current >= 1:
        return {
            "status": "already_earned",
            "zone_key": normalized_zone,
            "stars": current,
            "awarded": False,
        }

    inserted = conn.execute(
        f"INSERT INTO {EARNINGS_TABLE_NAME} "
        "(user_id, zone_key, event_id, star_number, source, earned_at) "
        "VALUES (?,?,?,?,?,?) ON CONFLICT DO NOTHING",
        (
            uid,
            normalized_zone,
            normalized_event,
            1,
            AUTHORITATIVE_BOSS_CLEAR_SOURCE,
            earned_at,
        ),
    )
    if _rowcount(inserted) != 1:
        current_row = _select_progress_row(conn, uid, normalized_zone)
        return {
            "status": "already_earned",
            "zone_key": normalized_zone,
            "stars": _clamp_stars(current_row["earned_stars"] if current_row else 0),
            "awarded": False,
        }
    conn.execute(
        f"UPDATE {PROGRESS_TABLE_NAME} SET earned_stars=1, updated_at=? "
        "WHERE user_id=? AND zone_key=? AND earned_stars < 1",
        (earned_at, uid, normalized_zone),
    )
    return {
        "status": "awarded",
        "zone_key": normalized_zone,
        "stars": 1,
        "awarded": True,
        "source": AUTHORITATIVE_BOSS_CLEAR_SOURCE,
        "event_id": normalized_event,
    }


__all__ = [
    "AUTHORITATIVE_ZONE_STAR_SOURCE",
    "AUTHORITATIVE_BOSS_CLEAR_SOURCE",
    "EARNINGS_TABLE_NAME",
    "FIRST_MAP_MILESTONE_STAR",
    "MAX_ZONE_STARS",
    "PROGRESS_TABLE_NAME",
    "RETROACTIVE_MILESTONE_POLICY_ENV",
    "RETROACTIVE_MILESTONE_POLICIES",
    "RETROACTIVE_POLICY_FULL",
    "RETROACTIVE_POLICY_HOLD",
    "RETROACTIVE_POLICY_LORD_ONLY",
    "ZoneStarSchemaUnavailable",
    "award_zone_star_from_boss_clear",
    "award_zone_star_up_to_map_milestone",
    "legacy_visible_star_entitlement",
    "load_zone_star_rows",
    "retroactive_milestone_policy",
    "retroactive_milestones_allowed",
    "zone_star_value",
]
