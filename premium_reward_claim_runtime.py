"""Caller-owned, fail-closed Premium deterministic claim authority.

This is an isolated implementation candidate.  It has no Flask route and is
not imported by application startup.  A future route must resolve a server
owned period and invoke this service inside the existing request transaction.

Business authority is split deliberately:

* ``premium_claim_operations`` decides retry identity and stores the replay
  result;
* Premium claim/credit tables decide one benefit per period;
* ``player_wardrobe`` remains cosmetic ownership authority;
* D5A outbox rows are evidence/lineage only.
"""

from __future__ import annotations

import datetime as _datetime
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Iterable, Mapping

from event_outbox import DuplicateOutboxEvent, append_event
from migrations.domain_event_outbox_v1 import TABLE_NAME as OUTBOX_TABLE
from migrations.premium_claim_lineage_v1 import SOURCE_CLASSES, validate_schema
from premium_claim_operations import (
    CLAIM_FAMILY,
    PremiumClaimOperationConflict,
    PremiumClaimOperationInProgress,
    canonical_claim_request,
    complete_claim_operation,
    get_claim_operation,
    normalize_claim_operation_id,
    reserve_claim_operation,
)
from premium_reward_catalog_adapter import (
    PremiumRewardCatalogResolver,
    UnconfiguredPremiumRewardCatalog,
)


RECURRING_ELIGIBLE_SOURCE = "VERIFIED_PAID"
RECURRING_REWARD_TYPE = "MONTHLY_COLLECTION_CREDIT"
WARDROBE_AUTHORITY = "player_wardrobe"
OUTBOX_PREMIUM_EVENT = "PREMIUM_CLAIM"
OUTBOX_ITEM_EVENT = "ITEM_ACQUISITION"

_FORBIDDEN_EFFECT_KEYS = frozenset({
    "xp", "xp_delta", "coins", "coins_delta", "go_strength",
    "go_strength_delta", "attack", "attack_delta", "defense",
    "defense_delta", "combat_power", "functional_power",
    "functional_equipment", "boss_advantage", "retry_advantage",
    "rank_advantage",
})


class PremiumRewardClaimError(ValueError):
    """Base error for a rejected or unsafe claim."""


@dataclass(frozen=True)
class ClaimResult:
    status: str
    reason: str | None = None
    claim_id: int | None = None
    reward_id: str | None = None
    period_key: str | None = None
    credit_id: int | None = None
    claim_operation_id: str | None = None
    claim_idempotency_key: str | None = None
    ownership_reference: str | None = None
    premium_event_id: str | None = None
    item_acquisition_event_id: str | None = None
    created: bool = False
    ownership_created: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "claim_id": self.claim_id,
            "reward_id": self.reward_id,
            "period_key": self.period_key,
            "credit_id": self.credit_id,
            "claim_operation_id": self.claim_operation_id,
            "claim_idempotency_key": self.claim_idempotency_key,
            "ownership_reference": self.ownership_reference,
            "premium_event_id": self.premium_event_id,
            "item_acquisition_event_id": self.item_acquisition_event_id,
            "created": self.created,
            "ownership_created": self.ownership_created,
        }


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


def _row_dict(cursor: Any, row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    if hasattr(row, "keys"):
        result = {str(key): row[key] for key in row.keys()}
    else:
        result = {str(item[0]): row[index] for index, item in enumerate(cursor.description)}
    return result


def _fetchone(conn: Any, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    cursor = _execute(conn, sql, params)
    try:
        result = _row_dict(cursor, cursor.fetchone())
        if result and isinstance(result.get("result_payload"), str):
            try:
                result["result_payload"] = json.loads(result["result_payload"])
            except (TypeError, ValueError):
                result["result_payload"] = {}
        return result
    finally:
        if not hasattr(conn, "execute"):
            cursor.close()


def _fetchall(conn: Any, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    cursor = _execute(conn, sql, params)
    try:
        return [value for value in (_row_dict(cursor, row) for row in cursor.fetchall()) if value is not None]
    finally:
        if not hasattr(conn, "execute"):
            cursor.close()


def _now(value: _datetime.datetime | None = None) -> _datetime.datetime:
    current = value or _datetime.datetime.now(_datetime.timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=_datetime.timezone.utc)
    return current


def _now_text(value: _datetime.datetime | None = None) -> str:
    return _now(value).isoformat()


def _parse_time(value: Any) -> _datetime.datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = _datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=_datetime.timezone.utc)


def _schema_available(conn: Any) -> bool:
    if not validate_schema(conn).get("valid"):
        return False
    wardrobe_columns = {str(row[1]) for row in _execute(conn, "PRAGMA table_info(player_wardrobe)").fetchall()} if _is_sqlite(conn) else {
        str(row[0]) for row in _execute(
            conn,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s",
            (WARDROBE_AUTHORITY,),
        ).fetchall()
    }
    if not {"id", "user_id", "item_id", "obtained_at", "source"}.issubset(wardrobe_columns):
        return False
    if _is_sqlite(conn):
        outbox_present = _fetchone(
            conn,
            "SELECT 1 AS present FROM sqlite_master WHERE type='table' AND name=?",
            (OUTBOX_TABLE,),
        )
    else:
        outbox_present = _fetchone(
            conn,
            "SELECT 1 AS present FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=%s",
            (OUTBOX_TABLE,),
        )
    if not outbox_present:
        return False
    return True


def _current_access(conn: Any, user_id: int, now: _datetime.datetime) -> bool:
    row = _fetchone(conn, "SELECT plan,premium_until FROM users WHERE id=?", (user_id,))
    if not row or row.get("plan") != "premium":
        return False
    expiry = _parse_time(row.get("premium_until"))
    return expiry is None or expiry >= now


def _grant_covers_period(grant: Mapping[str, Any], period: Mapping[str, Any]) -> bool:
    valid_from = _parse_time(grant.get("valid_from"))
    valid_until = _parse_time(grant.get("valid_until"))
    start = _parse_time(period.get("period_starts_at"))
    end = _parse_time(period.get("period_ends_at"))
    return bool(valid_from and start and end and valid_from <= end and (valid_until is None or valid_until >= start))


def _grant_is_current(grant: Mapping[str, Any], now: _datetime.datetime) -> bool:
    valid_from = _parse_time(grant.get("valid_from"))
    valid_until = _parse_time(grant.get("valid_until"))
    return bool(valid_from and valid_from <= now and (valid_until is None or now <= valid_until))


def _grant_not_revoked(conn: Any, grant_id: int, now_text: str) -> bool:
    return not bool(_fetchone(
        conn,
        """SELECT 1 AS revoked FROM premium_entitlement_events
           WHERE entitlement_grant_id=? AND event_type='REVOKE_BY_AUTHORIZED_POLICY'
             AND (revoked_at IS NULL OR revoked_at<=?) LIMIT 1""",
        (grant_id, now_text),
    ))


def _entitlement_source_event(conn: Any, grant_id: int) -> str:
    row = _fetchone(
        conn,
        "SELECT id FROM premium_entitlement_events WHERE entitlement_grant_id=? ORDER BY id DESC LIMIT 1",
        (grant_id,),
    )
    return str(row["id"]) if row else f"premium-grant:{grant_id}"


def _nonzero(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, Mapping):
        return any(_nonzero(child) for child in value.values())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_nonzero(child) for child in value)
    if isinstance(value, (int, float, Decimal)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "none", "null"}
    return bool(value)


def validate_pure_cosmetic_reward(reward: Mapping[str, Any]) -> dict[str, Any]:
    """Reject functional/effect-bearing catalog entries before mutation."""

    if not isinstance(reward, Mapping):
        raise PremiumRewardClaimError("catalog reward is not an object")
    reward_id = str(reward.get("reward_id") or "").strip()
    if not reward_id:
        raise PremiumRewardClaimError("catalog reward has no reward_id")
    if reward.get("pure_presentation") is not True:
        raise PremiumRewardClaimError("reward is not marked pure presentation")
    if reward.get("ownership_authority") != WARDROBE_AUTHORITY:
        raise PremiumRewardClaimError("reward ownership authority is not player_wardrobe")
    if _nonzero(reward.get("functional_effect_count")):
        raise PremiumRewardClaimError("reward has functional effects")
    if str(reward.get("combat_authority") or "NO").upper() != "NO":
        raise PremiumRewardClaimError("reward has combat authority")
    if str(reward.get("reward_type") or "").upper() in {"FUNCTIONAL_EQUIPMENT", "EQUIPMENT", "POWER"}:
        raise PremiumRewardClaimError("functional reward type is forbidden")
    effect_flags = reward.get("effect_flags")
    if isinstance(effect_flags, Mapping):
        for key, value in effect_flags.items():
            if str(key).lower() in _FORBIDDEN_EFFECT_KEYS and _nonzero(value):
                raise PremiumRewardClaimError(f"forbidden effect: {key}")
    for key in _FORBIDDEN_EFFECT_KEYS:
        if key in reward and _nonzero(reward.get(key)):
            raise PremiumRewardClaimError(f"forbidden effect: {key}")
    return dict(reward)


def _claim_row(conn: Any, user_id: int, period_id: int) -> dict[str, Any] | None:
    return _fetchone(
        conn,
        """SELECT c.*,p.period_key FROM premium_reward_claims c
           JOIN premium_reward_periods p ON p.id=c.reward_period_id
          WHERE c.user_id=? AND c.reward_period_id=? ORDER BY c.id LIMIT 1""",
        (user_id, period_id),
    )


def _event_row(conn: Any, event_type: str, player_id: int, key: str) -> dict[str, Any] | None:
    row = _fetchone(
        conn,
        f"""SELECT event_id,event_type,idempotency_key,lineage_id,source_event_id,
                    outcome,payload FROM {OUTBOX_TABLE}
              WHERE player_id=? AND event_type=? AND idempotency_key=?""",
        (str(player_id), event_type, key),
    )
    if row and isinstance(row.get("payload"), str):
        try:
            row["payload"] = json.loads(row["payload"])
        except (TypeError, ValueError):
            row["payload"] = {}
    return row


def _claim_result_from_payload(payload: Mapping[str, Any], *, operation_id: str | None, created: bool) -> ClaimResult:
    status = str(payload.get("status") or "DENIED")
    if status == "SUCCESS":
        status = "GRANTED"
    return ClaimResult(
        status=status,
        reason=payload.get("reason"),
        claim_id=int(payload["claim_id"]) if payload.get("claim_id") is not None else None,
        reward_id=payload.get("reward_id"),
        period_key=payload.get("period_key"),
        credit_id=int(payload["credit_id"]) if payload.get("credit_id") is not None else None,
        claim_operation_id=operation_id,
        claim_idempotency_key=payload.get("claim_idempotency_key"),
        ownership_reference=payload.get("ownership_reference"),
        premium_event_id=payload.get("premium_event_id"),
        item_acquisition_event_id=payload.get("item_acquisition_event_id"),
        created=created,
        ownership_created=bool(payload.get("ownership_created")),
    )


def _operation_result(row: Mapping[str, Any]) -> ClaimResult:
    payload = row.get("result_payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            payload = {}
    return _claim_result_from_payload(
        payload,
        operation_id=str(row.get("operation_id")),
        created=False,
    )


class PremiumRewardClaimService:
    """One-period deterministic claim service; caller owns the transaction."""

    def __init__(
        self,
        conn: Any,
        *,
        catalog_resolver: PremiumRewardCatalogResolver | None = None,
    ) -> None:
        self.conn = conn
        self.catalog_resolver = catalog_resolver or UnconfiguredPremiumRewardCatalog()

    def _denied(
        self,
        *,
        user_id: int,
        operation_id: str,
        period_key: str | None,
        reason: str,
        reward_id: str | None = None,
    ) -> ClaimResult:
        payload = {
            "status": "DENIED",
            "reason": reason,
            "period_key": period_key,
            "reward_id": reward_id,
            "claim_operation_id": operation_id,
        }
        complete_claim_operation(
            self.conn,
            user_id=user_id,
            operation_id=operation_id,
            operation_status="DENIED",
            result_payload=payload,
            benefit_period_key=period_key,
            reward_id=reward_id,
            claim_id=None,
        )
        return _claim_result_from_payload(payload, operation_id=operation_id, created=True)

    def current_access(self, user_id: int, *, now: _datetime.datetime | None = None) -> bool:
        return _current_access(self.conn, int(user_id), _now(now))

    def _load_period(self, period_key: str) -> dict[str, Any] | None:
        return _fetchone(self.conn, "SELECT * FROM premium_reward_periods WHERE period_key=?", (period_key,))

    def _find_verified_grant(
        self,
        user_id: int,
        period: Mapping[str, Any],
        *,
        now: _datetime.datetime,
        allow_annual_grace: bool,
    ) -> dict[str, Any] | None:
        rows = _fetchall(
            self.conn,
            "SELECT * FROM premium_entitlement_grants WHERE user_id=? AND source_class=? ORDER BY valid_from DESC,id DESC",
            (user_id, RECURRING_ELIGIBLE_SOURCE),
        )
        now_text = _now_text(now)
        for grant in rows:
            if grant.get("commercial_reward_eligibility") != "ALLOWED":
                continue
            grant_id = int(grant["id"])
            if not _grant_not_revoked(self.conn, grant_id, now_text):
                continue
            if not _grant_covers_period(grant, period):
                continue
            if _grant_is_current(grant, now):
                grant["source_event_id"] = _entitlement_source_event(self.conn, grant_id)
                return grant
            if allow_annual_grace and str(grant.get("plan_term") or "").upper() == "ANNUAL":
                grant["source_event_id"] = _entitlement_source_event(self.conn, grant_id)
                return grant
        return None

    def _resolve_reward(self, period: Mapping[str, Any], requested_reward_id: str | None) -> dict[str, Any] | None:
        try:
            reward = self.catalog_resolver.resolve_period_reward(
                period_key=str(period["period_key"]),
                reward_catalog_key=str(period["reward_catalog_key"]),
                requested_reward_id=requested_reward_id,
            )
        except PremiumRewardClaimError:
            raise
        except Exception as exc:
            raise PremiumRewardClaimError("CATALOG_REWARD_INVALID") from exc
        if reward is None:
            return None
        validated = validate_pure_cosmetic_reward(reward)
        if requested_reward_id and str(validated["reward_id"]) != requested_reward_id:
            raise PremiumRewardClaimError("REWARD_SELECTION_NOT_CANONICAL")
        return validated

    def _ensure_credit(
        self,
        user_id: int,
        period: Mapping[str, Any],
        grant: Mapping[str, Any],
        *,
        now: _datetime.datetime,
    ) -> dict[str, Any]:
        period_id = int(period["id"])
        existing = _fetchone(
            self.conn,
            "SELECT c.*,p.period_key FROM premium_reward_credits c JOIN premium_reward_periods p ON p.id=c.reward_period_id WHERE c.user_id=? AND c.reward_period_id=?",
            (user_id, period_id),
        )
        if existing:
            if int(existing["entitlement_grant_id"]) != int(grant["id"]):
                raise PremiumRewardClaimError("period credit is bound to a different entitlement grant")
            return existing
        stamp = _now_text(now)
        _execute(
            self.conn,
            """INSERT INTO premium_reward_credits(
                   user_id,reward_period_id,entitlement_grant_id,source_class_snapshot,
                   plan_term_snapshot,earned_at,claim_window_starts_at,claim_window_ends_at,
                   credit_state,claim_id,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(user_id,reward_period_id) DO NOTHING""",
            (
                user_id, period_id, int(grant["id"]), RECURRING_ELIGIBLE_SOURCE,
                str(grant.get("plan_term") or "UNKNOWN").upper(), str(period["period_starts_at"]),
                str(period["claim_window_starts_at"]), str(period["claim_window_ends_at"]),
                "EARNED", None, stamp, stamp,
            ),
        )
        existing = _fetchone(
            self.conn,
            "SELECT c.*,p.period_key FROM premium_reward_credits c JOIN premium_reward_periods p ON p.id=c.reward_period_id WHERE c.user_id=? AND c.reward_period_id=?",
            (user_id, period_id),
        )
        if not existing:
            raise PremiumRewardClaimError("period credit insert was not recoverable")
        return existing

    def _existing_claim_result(
        self,
        *,
        user_id: int,
        claim: Mapping[str, Any],
        operation_id: str,
        claim_key: str,
    ) -> ClaimResult:
        premium_event = _event_row(self.conn, OUTBOX_PREMIUM_EVENT, user_id, claim_key)
        if not premium_event:
            raise PremiumRewardClaimError("existing Premium claim has no lineage event")
        item_key = f"premium-item-acquisition:{claim_key}"
        item_event = _event_row(self.conn, OUTBOX_ITEM_EVENT, user_id, item_key)
        payload = {
            "status": "SUCCESS",
            "reason": None,
            "claim_id": int(claim["id"]),
            "reward_id": claim.get("reward_id"),
            "period_key": claim.get("period_key"),
            "credit_id": int(claim["reward_credit_id"]),
            "claim_operation_id": operation_id,
            "claim_idempotency_key": claim_key,
            "ownership_reference": claim.get("ownership_reference"),
            "premium_event_id": premium_event.get("event_id"),
            "item_acquisition_event_id": item_event.get("event_id") if item_event else None,
            "ownership_created": bool(item_event),
        }
        complete_claim_operation(
            self.conn,
            user_id=user_id,
            operation_id=operation_id,
            operation_status="SUCCESS",
            result_payload=payload,
            benefit_period_key=str(claim.get("period_key") or ""),
            reward_id=str(claim.get("reward_id") or ""),
            claim_id=int(claim["id"]),
        )
        return _claim_result_from_payload(payload, operation_id=operation_id, created=False)

    def claim_period_reward(
        self,
        user_id: int,
        period_key: str,
        *,
        operation_id: str | None = None,
        requested_reward_id: str | None = None,
        now: _datetime.datetime | None = None,
        fault_hook: Callable[[str], None] | None = None,
    ) -> ClaimResult:
        """Claim a server-resolved period inside the caller's transaction.

        ``period_key`` is an internal server-selected value in the intended
        route.  There is no live route in this candidate, and this method
        never trusts it for eligibility: all period, entitlement, and catalog
        checks remain server/database-owned.
        """

        user_id = int(user_id)
        period_key = str(period_key or "").strip()
        requested_reward_id = str(requested_reward_id).strip() if requested_reward_id else None
        try:
            claim_operation_id, _generated = normalize_claim_operation_id(operation_id)
        except Exception as exc:
            raise PremiumRewardClaimError(str(exc)) from exc
        if not _schema_available(self.conn):
            return ClaimResult(status="DENIED", reason="PREMIUM_SCHEMA_UNAVAILABLE", period_key=period_key, claim_operation_id=claim_operation_id)

        try:
            reservation = reserve_claim_operation(
                self.conn,
                user_id=user_id,
                operation_id=claim_operation_id,
                claim_family=CLAIM_FAMILY,
                benefit_period_key=period_key or None,
                requested_reward_id=requested_reward_id,
            )
        except PremiumClaimOperationConflict:
            return ClaimResult(status="CONFLICT", reason="CLAIM_IDEMPOTENCY_CONFLICT", claim_operation_id=claim_operation_id)
        except PremiumClaimOperationInProgress:
            return ClaimResult(status="DENIED", reason="CLAIM_IN_PROGRESS", period_key=period_key, claim_operation_id=claim_operation_id)

        if reservation["duplicate"]:
            return _operation_result(reservation["operation"])

        current = _now(now)
        if not period_key:
            return self._denied(user_id=user_id, operation_id=claim_operation_id, period_key=None, reason="PERIOD_KEY_REQUIRED")
        period = self._load_period(period_key)
        if not period:
            return self._denied(user_id=user_id, operation_id=claim_operation_id, period_key=period_key, reason="UNKNOWN_REWARD_PERIOD")
        period_id = int(period["id"])
        if period.get("reward_type") != RECURRING_REWARD_TYPE:
            return self._denied(user_id=user_id, operation_id=claim_operation_id, period_key=period_key, reason="UNSUPPORTED_REWARD_PERIOD_TYPE")

        existing_claim = _claim_row(self.conn, user_id, period_id)
        if existing_claim:
            return self._existing_claim_result(
                user_id=user_id,
                claim=existing_claim,
                operation_id=claim_operation_id,
                claim_key=str(existing_claim["claim_idempotency_key"]),
            )

        period_start = _parse_time(period.get("period_starts_at"))
        window_start = _parse_time(period.get("claim_window_starts_at"))
        window_end = _parse_time(period.get("claim_window_ends_at"))
        if not period_start or not window_start or not window_end:
            return self._denied(user_id=user_id, operation_id=claim_operation_id, period_key=period_key, reason="MALFORMED_REWARD_PERIOD")
        if current < period_start or current < window_start:
            return self._denied(user_id=user_id, operation_id=claim_operation_id, period_key=period_key, reason="REWARD_PERIOD_NOT_EARNED")

        existing_credit = _fetchone(
            self.conn,
            "SELECT * FROM premium_reward_credits WHERE user_id=? AND reward_period_id=?",
            (user_id, period_id),
        )
        access_active = self.current_access(user_id, now=current)
        if not access_active and not existing_credit:
            return self._denied(user_id=user_id, operation_id=claim_operation_id, period_key=period_key, reason="PREMIUM_ACCESS_INACTIVE")

        allow_annual_grace = bool(existing_credit and str(existing_credit.get("plan_term_snapshot") or "").upper() == "ANNUAL")
        grant = self._find_verified_grant(
            user_id,
            period,
            now=current,
            allow_annual_grace=allow_annual_grace or access_active,
        )
        if not grant:
            return self._denied(user_id=user_id, operation_id=claim_operation_id, period_key=period_key, reason="RECURRING_REWARD_NOT_ELIGIBLE")

        annual_grace = int(period.get("annual_grace_days") or 0) if str(grant.get("plan_term") or "").upper() == "ANNUAL" else 0
        if current > window_end + _datetime.timedelta(days=max(0, annual_grace)):
            return self._denied(user_id=user_id, operation_id=claim_operation_id, period_key=period_key, reason="CLAIM_WINDOW_EXPIRED")

        try:
            reward = self._resolve_reward(period, requested_reward_id)
        except PremiumRewardClaimError as exc:
            reason = str(exc) if str(exc) in {"REWARD_SELECTION_NOT_CANONICAL", "CATALOG_REWARD_INVALID"} else "CATALOG_REWARD_INVALID"
            return self._denied(
                user_id=user_id,
                operation_id=claim_operation_id,
                period_key=period_key,
                reason=reason,
                reward_id=requested_reward_id,
            )
        if reward is None:
            return self._denied(user_id=user_id, operation_id=claim_operation_id, period_key=period_key, reason="CATALOG_REWARD_UNAVAILABLE")
        reward_id = str(reward["reward_id"])
        claim_key = f"premium:{user_id}:{CLAIM_FAMILY}:{period_key}:{reward_id}"

        credit = existing_credit or self._ensure_credit(user_id, period, grant, now=current)
        if str(credit.get("credit_state")) == "CLAIMED":
            existing_claim = _claim_row(self.conn, user_id, period_id)
            if existing_claim:
                return self._existing_claim_result(
                    user_id=user_id,
                    claim=existing_claim,
                    operation_id=claim_operation_id,
                    claim_key=str(existing_claim["claim_idempotency_key"]),
                )
            return self._denied(user_id=user_id, operation_id=claim_operation_id, period_key=period_key, reason="CLAIM_INVARIANT_BROKEN", reward_id=reward_id)

        stamp = _now_text(current)
        wardrobe_cursor = _execute(
            self.conn,
            "INSERT INTO player_wardrobe(user_id,item_id,obtained_at,source) VALUES(?,?,?,?) ON CONFLICT(user_id,item_id) DO NOTHING",
            (user_id, reward_id, stamp, f"premium_claim:{period_key}"),
        )
        ownership_created = int(getattr(wardrobe_cursor, "rowcount", 0) or 0) == 1
        wardrobe_row = _fetchone(
            self.conn,
            "SELECT id FROM player_wardrobe WHERE user_id=? AND item_id=?",
            (user_id, reward_id),
        )
        if not wardrobe_row:
            raise PremiumRewardClaimError("wardrobe ownership row was not recoverable")
        ownership_reference = f"player_wardrobe:{int(wardrobe_row['id'])}"
        if fault_hook:
            fault_hook("after_wardrobe_write")

        claim_cursor = _execute(
            self.conn,
            """INSERT INTO premium_reward_claims(
                   user_id,reward_credit_id,reward_period_id,entitlement_grant_id,
                   source_class_snapshot,reward_id,reward_type,ownership_authority,
                   ownership_reference,claim_idempotency_key,claim_status,denial_reason,
                   granted_at,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(user_id,reward_period_id,reward_id) DO NOTHING""",
            (
                user_id, int(credit["id"]), period_id, int(grant["id"]),
                RECURRING_ELIGIBLE_SOURCE, reward_id,
                str(reward.get("reward_type") or "COSMETIC"), WARDROBE_AUTHORITY,
                ownership_reference, claim_key, "GRANTED", None, stamp, stamp,
            ),
        )
        claim = _claim_row(self.conn, user_id, period_id)
        if not claim:
            raise PremiumRewardClaimError("Premium claim insert was not recoverable")
        if int(claim["user_id"]) != user_id or str(claim["reward_id"]) != reward_id:
            return self._existing_claim_result(
                user_id=user_id,
                claim=claim,
                operation_id=claim_operation_id,
                claim_key=str(claim["claim_idempotency_key"]),
            )
        if fault_hook:
            fault_hook("after_claim_write")

        _execute(
            self.conn,
            "UPDATE premium_reward_credits SET credit_state='CLAIMED',claim_id=?,updated_at=? WHERE id=? AND credit_state='EARNED' AND claim_id IS NULL",
            (int(claim["id"]), stamp, int(credit["id"])),
        )

        lineage_id = f"premium-claim:{int(claim['id'])}"
        premium_payload = {
            "operation": "CLAIM",
            "claim_id": int(claim["id"]),
            "claim_family": CLAIM_FAMILY,
            "benefit_period": period_key,
            "reward_type": str(reward.get("reward_type") or "COSMETIC"),
            "reward_id": reward_id,
            "premium_source": RECURRING_ELIGIBLE_SOURCE,
            "entitlement_grant_id": int(grant["id"]),
            "claim_idempotency_key": claim_key,
            "ownership_authority": WARDROBE_AUTHORITY,
            "ownership_reference": ownership_reference,
            "ownership_committed": True,
        }
        try:
            premium_event = append_event(
                self.conn,
                event_type=OUTBOX_PREMIUM_EVENT,
                player_id=str(user_id),
                lineage_id=lineage_id,
                source_event_id=str(grant.get("source_event_id") or f"premium-grant:{grant['id']}"),
                idempotency_key=claim_key,
                outcome="SUCCESS",
                payload=premium_payload,
                occurred_at=stamp,
            )
        except DuplicateOutboxEvent as duplicate:
            premium_event = duplicate.existing_event
        item_event = None
        if ownership_created:
            item_event = append_event(
                self.conn,
                event_type=OUTBOX_ITEM_EVENT,
                player_id=str(user_id),
                lineage_id=lineage_id,
                idempotency_key=f"premium-item-acquisition:{claim_key}",
                outcome="SUCCESS",
                payload={
                    "operation": "GRANT",
                    "grant_id": ownership_reference,
                    "item_id": reward_id,
                    "acquisition_source": "PREMIUM",
                    "premium_source": RECURRING_ELIGIBLE_SOURCE,
                    "source_reference": f"premium-claim:{int(claim['id'])}",
                    "ownership_authority": WARDROBE_AUTHORITY,
                    "ownership_committed": True,
                    "ownership_created": True,
                },
                source_event_id=str(premium_event["event_id"]),
                occurred_at=stamp,
            )

        payload = {
            "status": "SUCCESS",
            "reason": None,
            "claim_id": int(claim["id"]),
            "reward_id": reward_id,
            "period_key": period_key,
            "credit_id": int(credit["id"]),
            "claim_operation_id": claim_operation_id,
            "claim_idempotency_key": claim_key,
            "ownership_reference": ownership_reference,
            "premium_event_id": str(premium_event["event_id"]),
            "item_acquisition_event_id": str(item_event["event_id"]) if item_event else None,
            "ownership_created": ownership_created,
        }
        complete_claim_operation(
            self.conn,
            user_id=user_id,
            operation_id=claim_operation_id,
            operation_status="SUCCESS",
            result_payload=payload,
            benefit_period_key=period_key,
            reward_id=reward_id,
            claim_id=int(claim["id"]),
        )
        return _claim_result_from_payload(payload, operation_id=claim_operation_id, created=True)


__all__ = [
    "CLAIM_FAMILY",
    "ClaimResult",
    "PremiumRewardClaimError",
    "PremiumRewardClaimService",
    "RECURRING_ELIGIBLE_SOURCE",
    "RECURRING_REWARD_TYPE",
    "WARDROBE_AUTHORITY",
    "validate_pure_cosmetic_reward",
]
