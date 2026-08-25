"""Server-owned Quest V2 period resolution.

This module is the only D014 period resolver.  It uses an authoritative
event's occurrence timestamp and the fixed Asia/Taipei business timezone; it
never reads browser/session time and never uses processing time to choose a
period key.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from quest_catalog import QuestDefinition, QUEST_PERIOD_SET


PERIOD_TIMEZONE_NAME = "Asia/Taipei"
PERIOD_TIMEZONE = ZoneInfo(PERIOD_TIMEZONE_NAME)
UTC = timezone.utc
SUPPORTED_PERIODS = tuple(QUEST_PERIOD_SET)
MAX_FUTURE_SKEW = timedelta(minutes=5)


class PeriodResolutionError(ValueError):
    """Raised when an event timestamp or catalog window is unsafe."""


class MalformedTimestamp(PeriodResolutionError):
    """The authoritative occurrence timestamp is missing or malformed."""


class FutureTimestampRejected(PeriodResolutionError):
    """The event is too far in the future to create progress safely."""


class EventOutsideWindow(PeriodResolutionError):
    """The event is not inside the Quest's authoritative event window."""


@dataclass(frozen=True)
class ResolvedPeriod:
    period: str
    period_key: str
    occurred_at_utc: datetime
    occurred_at_local: datetime
    period_start_utc: datetime | None = None
    period_end_exclusive_utc: datetime | None = None


def _parse_timestamp(value: Any, *, field: str, assume_timezone: ZoneInfo | None = None) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except (TypeError, ValueError) as exc:
            raise MalformedTimestamp(f"{field}_must_be_iso8601") from exc
    else:
        raise MalformedTimestamp(f"{field}_required")
    if parsed.tzinfo is None:
        if assume_timezone is None:
            raise MalformedTimestamp(f"{field}_must_include_timezone")
        parsed = parsed.replace(tzinfo=assume_timezone)
    try:
        return parsed.astimezone(UTC)
    except (TypeError, ValueError, OverflowError) as exc:
        raise MalformedTimestamp(f"{field}_timezone_invalid") from exc


def _future_checked_timestamp(value: Any, *, server_now: datetime | None) -> datetime:
    occurred_at = _parse_timestamp(value, field="occurred_at")
    if server_now is None:
        raise PeriodResolutionError("server_now_required")
    now = _parse_timestamp(server_now, field="server_now")
    if occurred_at > now + MAX_FUTURE_SKEW:
        raise FutureTimestampRejected("occurred_at_exceeds_future_tolerance")
    return occurred_at


def _event_window_key(start_utc: datetime, end_utc: datetime) -> str:
    def stamp(value: datetime) -> str:
        return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")

    return f"event_window:{stamp(start_utc)}:{stamp(end_utc)}"


class QuestPeriodResolver:
    """The single server-owned period authority for Quest V2."""

    timezone_name = PERIOD_TIMEZONE_NAME
    timezone = PERIOD_TIMEZONE
    max_future_skew = MAX_FUTURE_SKEW

    def validate_occurrence(
        self,
        occurred_at: Any,
        *,
        server_now: datetime | None = None,
    ) -> datetime:
        """Validate an authoritative timestamp without resolving a period."""

        return _future_checked_timestamp(occurred_at, server_now=server_now)

    def resolve(
        self,
        period: str,
        occurred_at: Any,
        *,
        availability: Mapping[str, Any] | None = None,
        server_now: datetime | None = None,
    ) -> ResolvedPeriod | None:
        """Resolve one period from event time, or return ``None`` outside a window.

        ``server_now`` is used only to reject an unsafe future event.  It never
        selects a daily/weekly key, so replay uses the original occurred_at.
        """

        if period not in SUPPORTED_PERIODS:
            raise PeriodResolutionError("unknown_period")
        occurred_at_utc = _future_checked_timestamp(occurred_at, server_now=server_now)
        occurred_at_local = occurred_at_utc.astimezone(self.timezone)

        if period == "daily":
            key = occurred_at_local.date().isoformat()
            start_local = datetime.combine(occurred_at_local.date(), datetime.min.time(), tzinfo=self.timezone)
            end_local = start_local + timedelta(days=1)
            period_start_utc = start_local.astimezone(UTC)
            period_end_utc = end_local.astimezone(UTC)
        elif period == "weekly":
            iso = occurred_at_local.date().isocalendar()
            key = f"{iso.year:04d}-W{iso.week:02d}"
            start_date = occurred_at_local.date() - timedelta(days=occurred_at_local.weekday())
            start_local = datetime.combine(start_date, datetime.min.time(), tzinfo=self.timezone)
            end_local = start_local + timedelta(days=7)
            period_start_utc = start_local.astimezone(UTC)
            period_end_utc = end_local.astimezone(UTC)
        elif period == "lifetime":
            key = "lifetime"
            period_start_utc = None
            period_end_utc = None
        elif period == "one_time":
            key = "once"
            period_start_utc = None
            period_end_utc = None
        else:
            start_utc, end_utc = self._event_window_bounds(availability)
            if not start_utc <= occurred_at_utc < end_utc:
                return None
            key = _event_window_key(start_utc, end_utc)
            period_start_utc = start_utc
            period_end_utc = end_utc

        return ResolvedPeriod(
            period=period,
            period_key=key,
            occurred_at_utc=occurred_at_utc,
            occurred_at_local=occurred_at_local,
            period_start_utc=period_start_utc,
            period_end_exclusive_utc=period_end_utc,
        )

    def resolve_definition(
        self,
        definition: QuestDefinition,
        occurred_at: Any,
        *,
        server_now: datetime | None = None,
    ) -> ResolvedPeriod | None:
        if not isinstance(definition, QuestDefinition):
            raise PeriodResolutionError("quest_definition_required")
        return self.resolve(
            definition.period,
            occurred_at,
            availability=definition.availability,
            server_now=server_now,
        )

    def _event_window_bounds(self, availability: Mapping[str, Any] | None) -> tuple[datetime, datetime]:
        if not isinstance(availability, Mapping):
            raise PeriodResolutionError("event_window_availability_required")
        window = availability.get("event_window")
        if not isinstance(window, Mapping):
            raise PeriodResolutionError("event_window_required")
        window_timezone = window.get("timezone", self.timezone_name)
        if window_timezone != self.timezone_name:
            raise PeriodResolutionError("event_window_timezone_must_be_asia_taipei")
        try:
            start = _parse_timestamp(
                window.get("start"),
                field="event_window_start",
                assume_timezone=self.timezone,
            )
            end = _parse_timestamp(
                window.get("end"),
                field="event_window_end",
                assume_timezone=self.timezone,
            )
        except MalformedTimestamp:
            raise
        if start >= end:
            raise PeriodResolutionError("event_window_start_must_precede_end")
        return start, end


QUEST_PERIOD_RESOLVER = QuestPeriodResolver()


__all__ = [
    "EventOutsideWindow",
    "FutureTimestampRejected",
    "MAX_FUTURE_SKEW",
    "MalformedTimestamp",
    "PERIOD_TIMEZONE",
    "PERIOD_TIMEZONE_NAME",
    "PeriodResolutionError",
    "QuestPeriodResolver",
    "QUEST_PERIOD_RESOLVER",
    "ResolvedPeriod",
    "SUPPORTED_PERIODS",
]
