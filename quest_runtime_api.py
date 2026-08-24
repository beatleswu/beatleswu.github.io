"""Read-only Quest V2 projection used by the D017 API boundary."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from migrations.login_journey_v1 import JOURNEY_LENGTH, JOURNEY_TABLE_NAME
from migrations.quest_claim_v1 import TABLE_NAME as CLAIM_TABLE_NAME
from migrations.quest_progress_v2 import PROGRESS_TABLE_NAME
from quest_catalog import CANONICAL_QUEST_CATALOG, QuestCatalog
from quest_claim_authority import CLAIM_STATUS_SETTLED
from quest_period_authority import QuestPeriodResolver, QUEST_PERIOD_RESOLVER
from quest_reward_adapters import CURRENT_QUEST_REWARD_CATALOG
from login_journey_authority import LoginSchemaUnavailable, get_login_state


class QuestRuntimeReadError(RuntimeError):
    """A Quest V2 read could not be reconstructed safely."""


class QuestRuntimeSchemaUnavailable(QuestRuntimeReadError):
    """D014/D015/D016 candidate schema is not installed."""


def _raw(conn: Any) -> Any:
    return getattr(conn, "_conn", conn)


def _is_sqlite(conn: Any) -> bool:
    return _raw(conn).__class__.__module__.lower().startswith("sqlite3")


def _execute(conn: Any, sql: str, params: Iterable[Any] = ()) -> Any:
    params = tuple(params)
    if hasattr(conn, "execute"):
        return conn.execute(sql, params)
    cursor = conn.cursor()
    cursor.execute(sql.replace("?", "%s"), params)
    return cursor


def _fetchone(conn: Any, sql: str, params: Iterable[Any] = ()) -> Any:
    cursor = _execute(conn, sql, params)
    try:
        return cursor.fetchone()
    finally:
        if not hasattr(conn, "execute"):
            cursor.close()


def _fetchall(conn: Any, sql: str, params: Iterable[Any] = ()) -> list[Any]:
    cursor = _execute(conn, sql, params)
    try:
        return list(cursor.fetchall())
    finally:
        if not hasattr(conn, "execute"):
            cursor.close()


def _row_value(row: Any, key: str, index: int) -> Any:
    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _ensure_schema(conn: Any) -> None:
    try:
        _fetchone(conn, f"SELECT 1 FROM {PROGRESS_TABLE_NAME} LIMIT 1")
        _fetchone(conn, f"SELECT 1 FROM {CLAIM_TABLE_NAME} LIMIT 1")
    except Exception as exc:
        raise QuestRuntimeSchemaUnavailable("D014/D015 schema is not installed") from exc


def _tab_for_family(family: str) -> str:
    return {
        "daily": "Daily",
        "weekly": "Weekly",
        "adventure": "Adventure",
        "achievement": "Chronicles",
        "event": "Event",
        "onboarding": "Onboarding",
    }.get(family, family)


def _reward_metadata(reward_profile_id: str | None) -> dict[str, Any] | None:
    try:
        profile = CURRENT_QUEST_REWARD_CATALOG.resolve(reward_profile_id)
    except Exception:
        return None
    return {
        "profile_id": profile.profile_id,
        "xp": profile.xp,
        "coins": profile.coins,
        "items": [{"item_id": item.item_id, "quantity": item.quantity} for item in profile.items],
        "cosmetics": list(profile.cosmetics),
    }


def _current_period(
    resolver: QuestPeriodResolver,
    definition: Any,
    now: datetime,
) -> str:
    resolved = resolver.resolve_definition(definition, now, server_now=now)
    if resolved is None:
        raise QuestRuntimeReadError("quest_not_in_current_event_window")
    return resolved.period_key


def _login_payload(snapshot: Any, *, completed_at: Any = None) -> dict[str, Any]:
    if hasattr(completed_at, "isoformat"):
        completed_at = completed_at.isoformat()
    return {
        "journey_id": snapshot.journey_id,
        "journey_version": snapshot.journey_version,
        "completed_day_count": snapshot.journey_day_completed,
        "journey_length": JOURNEY_LENGTH,
        "status": "COMPLETED" if snapshot.journey_completed else "ACTIVE",
        "first_login_date": snapshot.first_login_date,
        "last_progress_date": snapshot.last_progress_date,
        "completed_at": completed_at,
        "current_login_streak": snapshot.current_streak_days,
        "best_login_streak": snapshot.best_streak_days,
        "total_login_days": snapshot.total_login_days,
        "last_login_date": snapshot.last_login_date,
        "reward_count": 0,
    }


def build_quest_v2_read_state(
    conn: Any,
    *,
    user_id: int | str,
    now: datetime | None = None,
    catalog: QuestCatalog | None = None,
    period_resolver: QuestPeriodResolver = QUEST_PERIOD_RESOLVER,
) -> dict[str, Any]:
    """Return normalized server-owned Quest and engagement state."""

    _ensure_schema(conn)
    active_catalog = catalog or CANONICAL_QUEST_CATALOG
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise QuestRuntimeReadError("server_now_must_be_timezone_aware")
    user_key = str(user_id)
    tabs = {name: [] for name in ("Daily", "Weekly", "Adventure", "Chronicles")}
    flattened: list[dict[str, Any]] = []
    for definition in sorted(active_catalog.definitions, key=lambda item: item.quest_id):
        period_key = _current_period(period_resolver, definition, now)
        progress = _fetchone(
            conn,
            f"""SELECT progress, completed, definition_version, target_snapshot
                       FROM {PROGRESS_TABLE_NAME}
                      WHERE user_id=? AND quest_id=? AND period_key=?""",
            (user_key, definition.quest_id, period_key),
        )
        claim = _fetchone(
            conn,
            f"""SELECT claim_status, quest_definition_version, reward_profile_id
                       FROM {CLAIM_TABLE_NAME}
                      WHERE user_id=? AND quest_id=? AND period_key=?""",
            (user_key, definition.quest_id, period_key),
        )
        current = int(_row_value(progress, "progress", 0) or 0) if progress else 0
        completed = bool(_row_value(progress, "completed", 1)) if progress else False
        version_matches = bool(
            progress
            and int(_row_value(progress, "definition_version", 2) or 0) == int(definition.version)
            and int(_row_value(progress, "target_snapshot", 3) or 0) == int(definition.target or 0)
        )
        claimed = bool(claim and str(_row_value(claim, "claim_status", 0)) == CLAIM_STATUS_SETTLED)
        claimable = bool(definition.enabled and completed and version_matches and not claimed)
        if not definition.enabled:
            status = "DISABLED"
        elif claimed:
            status = "CLAIMED"
        elif claimable:
            status = "CLAIMABLE"
        elif completed and not version_matches:
            status = "VERSION_DRIFT"
        else:
            status = "ACTIVE"
        item = {
            "quest_id": definition.quest_id,
            "definition_version": definition.version,
            "category": definition.quest_family,
            "tab": _tab_for_family(definition.quest_family),
            "display_metadata_key": definition.display_key,
            "target": definition.target,
            "progress": current,
            "completed": bool(completed and version_matches),
            "claimed": claimed,
            "claimable": claimable,
            "period_key": period_key,
            "reward_profile": _reward_metadata(definition.reward_profile_id),
            "status": status,
            "enabled": bool(definition.enabled),
            "aliases": list(definition.aliases),
        }
        flattened.append(item)
        if item["tab"] in tabs:
            tabs[item["tab"]].append(item)

    try:
        snapshot = get_login_state(conn, user_id=user_id)
        journey_row = _fetchone(
            conn,
            f"SELECT completed_at FROM {JOURNEY_TABLE_NAME} WHERE user_id=? AND journey_id=?",
            (int(user_id), snapshot.journey_id),
        )
        completed_at = _row_value(journey_row, "completed_at", 0) if journey_row else None
        login_state = _login_payload(snapshot, completed_at=completed_at)
    except LoginSchemaUnavailable as exc:
        raise QuestRuntimeSchemaUnavailable("D016 login schema is not installed") from exc
    return {
        "enabled": True,
        "tabs": tabs,
        "quests": flattened,
        "login_journey": login_state,
        "client_calculates_completion": False,
        "period_timezone": period_resolver.timezone_name,
    }


__all__ = [
    "QuestRuntimeReadError",
    "QuestRuntimeSchemaUnavailable",
    "build_quest_v2_read_state",
]
