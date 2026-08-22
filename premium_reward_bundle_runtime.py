"""Atomic Premium deterministic bundle claim authority.

The parent ``premium_reward_claims`` row is the one period-level claim.  The
bundle component table is only a support/readback record.  Question capacity
is applied through the D5B caller-owned authority; optional cosmetics use the
existing ``player_wardrobe`` ownership authority and D5C acquisition event
shape.  No route imports this candidate and the service never commits.
"""

from __future__ import annotations

import datetime as _datetime
import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from event_outbox import append_event
from migrations.premium_reward_bundle_v1 import TABLE_NAME as BUNDLE_TABLE, validate_schema as validate_bundle_schema
from premium_claim_operations import (
    CLAIM_FAMILY,
    PremiumClaimOperationConflict,
    PremiumClaimOperationInProgress,
    complete_claim_operation,
    normalize_claim_operation_id,
    reserve_claim_operation,
)
from premium_reward_claim_runtime import (
    OUTBOX_ITEM_EVENT,
    OUTBOX_PREMIUM_EVENT,
    RECURRING_ELIGIBLE_SOURCE,
    RECURRING_REWARD_TYPE,
    WARDROBE_AUTHORITY,
    PremiumRewardClaimError,
    PremiumRewardClaimService,
    _claim_row,
    _now,
    _now_text,
    _parse_time,
    _schema_available,
    _event_row,
)
from question_capacity_authority import apply_question_capacity_in_transaction


BUNDLE_VERSION = "premium-deterministic-bundle-v1"
BUNDLE_REQUEST_PREFIX = f"{BUNDLE_VERSION}:"
QUESTION_BENEFIT_ITEM = "extra_questions_small"
QUESTION_COMPONENT_KEY = f"QUESTION_CAPACITY:{QUESTION_BENEFIT_ITEM}"
CLAIM_OWNERSHIP_AUTHORITY = "premium_bundle"


@dataclass(frozen=True)
class BundleClaimResult:
    status: str
    reason: str | None = None
    claim_id: int | None = None
    period_key: str | None = None
    claim_operation_id: str | None = None
    claim_idempotency_key: str | None = None
    premium_event_id: str | None = None
    components: tuple[dict[str, Any], ...] = ()
    created: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "claim_id": self.claim_id,
            "period_key": self.period_key,
            "claim_operation_id": self.claim_operation_id,
            "claim_idempotency_key": self.claim_idempotency_key,
            "premium_event_id": self.premium_event_id,
            "components": [dict(component) for component in self.components],
            "created": self.created,
        }


def _raw(conn: Any) -> Any:
    return getattr(conn, "_conn", conn)


def _is_sqlite(conn: Any) -> bool:
    return _raw(conn).__class__.__module__.lower().startswith("sqlite3")


def _execute(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
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
    if isinstance(result.get("result_payload"), str):
        try:
            result["result_payload"] = json.loads(result["result_payload"])
        except (TypeError, ValueError):
            result["result_payload"] = {}
    return result


def _fetchone(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    cursor = _execute(conn, sql, params)
    try:
        return _row_dict(cursor, cursor.fetchone())
    finally:
        if not hasattr(conn, "execute"):
            cursor.close()


def _fetchall(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor = _execute(conn, sql, params)
    try:
        return [value for value in (_row_dict(cursor, row) for row in cursor.fetchall()) if value is not None]
    finally:
        if not hasattr(conn, "execute"):
            cursor.close()


def _json_value(conn: Any, payload: Mapping[str, Any]) -> Any:
    if _is_sqlite(conn):
        return json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    from psycopg2.extras import Json

    return Json(dict(payload))


def _bundle_claim_row(conn: Any, user_id: int, period_id: int) -> dict[str, Any] | None:
    return _fetchone(
        conn,
        """SELECT c.*,p.period_key FROM premium_reward_claims c
           JOIN premium_reward_periods p ON p.id=c.reward_period_id
          WHERE c.user_id=? AND c.reward_period_id=? ORDER BY c.id LIMIT 1""",
        (user_id, period_id),
    )


def _bundle_components(conn: Any, user_id: int, period_id: int) -> list[dict[str, Any]]:
    return _fetchall(
        conn,
        f"""SELECT component_key,component_type,component_status,item_id,
                    capacity_delta,operation_id,result_payload,event_id
                FROM {BUNDLE_TABLE}
               WHERE user_id=? AND reward_period_id=?
               ORDER BY id""",
        (user_id, period_id),
    )


def _bundle_request_token(*, include_cosmetic: bool, requested_cosmetic_id: str | None) -> str:
    if not include_cosmetic:
        return f"{BUNDLE_REQUEST_PREFIX}question-only"
    cosmetic = str(requested_cosmetic_id or "server-selected").strip()
    return f"{BUNDLE_REQUEST_PREFIX}question-plus-cosmetic:{cosmetic}"


def _result_from_payload(payload: Mapping[str, Any], *, operation_id: str | None, created: bool) -> BundleClaimResult:
    components = payload.get("components") or []
    return BundleClaimResult(
        status=str(payload.get("status") or "DENIED"),
        reason=payload.get("reason"),
        claim_id=int(payload["claim_id"]) if payload.get("claim_id") is not None else None,
        period_key=payload.get("period_key"),
        claim_operation_id=operation_id,
        claim_idempotency_key=payload.get("claim_idempotency_key"),
        premium_event_id=payload.get("premium_event_id"),
        components=tuple(dict(component) for component in components),
        created=created,
    )


def _operation_result(row: Mapping[str, Any]) -> BundleClaimResult:
    payload = row.get("result_payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            payload = {}
    return _result_from_payload(
        payload,
        operation_id=str(row.get("operation_id")),
        created=False,
    )


class PremiumRewardBundleClaimService(PremiumRewardClaimService):
    """One authoritative period claim that atomically applies its components."""

    def _schema_available(self) -> bool:
        return _schema_available(self.conn) and validate_bundle_schema(self.conn).get("valid", False)

    def _denied_bundle(
        self,
        *,
        user_id: int,
        operation_id: str,
        period_key: str | None,
        request_token: str,
        reason: str,
    ) -> BundleClaimResult:
        payload = {
            "status": "DENIED",
            "reason": reason,
            "period_key": period_key,
            "claim_operation_id": operation_id,
            "bundle_version": BUNDLE_VERSION,
            "components": [],
        }
        complete_claim_operation(
            self.conn,
            user_id=user_id,
            operation_id=operation_id,
            operation_status="DENIED",
            result_payload=payload,
            benefit_period_key=period_key,
            reward_id=request_token,
            claim_id=None,
        )
        return _result_from_payload(payload, operation_id=operation_id, created=True)

    def _replay_claim(
        self,
        *,
        user_id: int,
        claim: Mapping[str, Any],
        operation_id: str,
    ) -> BundleClaimResult:
        if str(claim.get("ownership_authority")) != CLAIM_OWNERSHIP_AUTHORITY:
            return BundleClaimResult(
                status="CONFLICT",
                reason="PERIOD_ALREADY_CLAIMED_DIFFERENT_CONTRACT",
                claim_id=int(claim["id"]),
                period_key=str(claim.get("period_key") or ""),
                claim_operation_id=operation_id,
            )
        claim_key = str(claim["claim_idempotency_key"])
        event = _event_row(self.conn, OUTBOX_PREMIUM_EVENT, user_id, claim_key)
        if not event:
            raise PremiumRewardClaimError("existing Premium bundle claim has no lineage event")
        components = _bundle_components(self.conn, user_id, int(claim["reward_period_id"]))
        if not components:
            raise PremiumRewardClaimError("existing Premium bundle claim has no component records")
        payload = {
            "status": "GRANTED",
            "reason": None,
            "claim_id": int(claim["id"]),
            "period_key": claim.get("period_key"),
            "claim_operation_id": operation_id,
            "claim_idempotency_key": claim_key,
            "premium_event_id": str(event["event_id"]),
            "bundle_version": BUNDLE_VERSION,
            "components": [dict(component) for component in components],
        }
        complete_claim_operation(
            self.conn,
            user_id=user_id,
            operation_id=operation_id,
            operation_status="SUCCESS",
            result_payload=payload,
            benefit_period_key=str(claim.get("period_key") or ""),
            reward_id=str(claim.get("reward_id") or BUNDLE_VERSION),
            claim_id=int(claim["id"]),
        )
        return _result_from_payload(payload, operation_id=operation_id, created=False)

    def claim_period_bundle(
        self,
        user_id: int,
        period_key: str,
        *,
        operation_id: str | None = None,
        include_cosmetic: bool = False,
        requested_cosmetic_id: str | None = None,
        now: _datetime.datetime | None = None,
        fault_hook: Callable[[str], None] | None = None,
    ) -> BundleClaimResult:
        user_id = int(user_id)
        period_key = str(period_key or "").strip()
        requested_cosmetic_id = str(requested_cosmetic_id).strip() if requested_cosmetic_id else None
        request_token = _bundle_request_token(
            include_cosmetic=include_cosmetic,
            requested_cosmetic_id=requested_cosmetic_id,
        )
        try:
            claim_operation_id, _generated = normalize_claim_operation_id(operation_id)
        except Exception as exc:
            raise PremiumRewardClaimError(str(exc)) from exc
        if not self._schema_available():
            return BundleClaimResult(status="DENIED", reason="PREMIUM_BUNDLE_SCHEMA_UNAVAILABLE", period_key=period_key, claim_operation_id=claim_operation_id)

        try:
            reservation = reserve_claim_operation(
                self.conn,
                user_id=user_id,
                operation_id=claim_operation_id,
                claim_family=CLAIM_FAMILY,
                benefit_period_key=period_key or None,
                requested_reward_id=request_token,
            )
        except PremiumClaimOperationConflict:
            return BundleClaimResult(status="CONFLICT", reason="CLAIM_IDEMPOTENCY_CONFLICT", claim_operation_id=claim_operation_id)
        except PremiumClaimOperationInProgress:
            return BundleClaimResult(status="DENIED", reason="CLAIM_IN_PROGRESS", period_key=period_key, claim_operation_id=claim_operation_id)
        if reservation["duplicate"]:
            return _operation_result(reservation["operation"])

        current = _now(now)
        if not period_key:
            return self._denied_bundle(user_id=user_id, operation_id=claim_operation_id, period_key=None, request_token=request_token, reason="PERIOD_KEY_REQUIRED")
        period = self._load_period(period_key)
        if not period:
            return self._denied_bundle(user_id=user_id, operation_id=claim_operation_id, period_key=period_key, request_token=request_token, reason="UNKNOWN_REWARD_PERIOD")
        period_id = int(period["id"])
        if period.get("reward_type") != RECURRING_REWARD_TYPE:
            return self._denied_bundle(user_id=user_id, operation_id=claim_operation_id, period_key=period_key, request_token=request_token, reason="UNSUPPORTED_REWARD_PERIOD_TYPE")
        existing_claim = _bundle_claim_row(self.conn, user_id, period_id)
        if existing_claim:
            return self._replay_claim(user_id=user_id, claim=existing_claim, operation_id=claim_operation_id)

        period_start = _parse_time(period.get("period_starts_at"))
        window_start = _parse_time(period.get("claim_window_starts_at"))
        window_end = _parse_time(period.get("claim_window_ends_at"))
        if not period_start or not window_start or not window_end:
            return self._denied_bundle(user_id=user_id, operation_id=claim_operation_id, period_key=period_key, request_token=request_token, reason="MALFORMED_REWARD_PERIOD")
        if current < period_start or current < window_start:
            return self._denied_bundle(user_id=user_id, operation_id=claim_operation_id, period_key=period_key, request_token=request_token, reason="REWARD_PERIOD_NOT_EARNED")

        existing_credit = _fetchone(
            self.conn,
            "SELECT * FROM premium_reward_credits WHERE user_id=? AND reward_period_id=?",
            (user_id, period_id),
        )
        access_active = self.current_access(user_id, now=current)
        if not access_active and not existing_credit:
            return self._denied_bundle(user_id=user_id, operation_id=claim_operation_id, period_key=period_key, request_token=request_token, reason="PREMIUM_ACCESS_INACTIVE")
        allow_annual_grace = bool(existing_credit and str(existing_credit.get("plan_term_snapshot") or "").upper() == "ANNUAL")
        grant = self._find_verified_grant(user_id, period, now=current, allow_annual_grace=allow_annual_grace or access_active)
        if not grant:
            return self._denied_bundle(user_id=user_id, operation_id=claim_operation_id, period_key=period_key, request_token=request_token, reason="RECURRING_REWARD_NOT_ELIGIBLE")
        annual_grace = int(period.get("annual_grace_days") or 0) if str(grant.get("plan_term") or "").upper() == "ANNUAL" else 0
        if current > window_end + _datetime.timedelta(days=max(0, annual_grace)):
            return self._denied_bundle(user_id=user_id, operation_id=claim_operation_id, period_key=period_key, request_token=request_token, reason="CLAIM_WINDOW_EXPIRED")

        cosmetic = None
        if include_cosmetic:
            try:
                cosmetic = self._resolve_reward(period, requested_cosmetic_id)
            except PremiumRewardClaimError as exc:
                return self._denied_bundle(user_id=user_id, operation_id=claim_operation_id, period_key=period_key, request_token=request_token, reason=str(exc))
            if cosmetic is None:
                return self._denied_bundle(user_id=user_id, operation_id=claim_operation_id, period_key=period_key, request_token=request_token, reason="CATALOG_REWARD_UNAVAILABLE")

        credit = existing_credit or self._ensure_credit(user_id, period, grant, now=current)
        if str(credit.get("credit_state")) == "CLAIMED":
            existing_claim = _bundle_claim_row(self.conn, user_id, period_id)
            if existing_claim:
                return self._replay_claim(user_id=user_id, claim=existing_claim, operation_id=claim_operation_id)
            return self._denied_bundle(user_id=user_id, operation_id=claim_operation_id, period_key=period_key, request_token=request_token, reason="CLAIM_INVARIANT_BROKEN")

        stamp = _now_text(current)
        claim_key = f"premium:{user_id}:{CLAIM_FAMILY}:{period_key}:bundle:v1"
        claim_cursor = _execute(
            self.conn,
            """INSERT INTO premium_reward_claims(
                   user_id,reward_credit_id,reward_period_id,entitlement_grant_id,
                   source_class_snapshot,reward_id,reward_type,ownership_authority,
                   ownership_reference,claim_idempotency_key,claim_status,denial_reason,
                   granted_at,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(user_id,reward_credit_id) DO NOTHING""",
            (
                user_id, int(credit["id"]), period_id, int(grant["id"]),
                RECURRING_ELIGIBLE_SOURCE, BUNDLE_VERSION, "DETERMINISTIC_BUNDLE",
                CLAIM_OWNERSHIP_AUTHORITY, None, claim_key, "GRANTED", None, stamp, stamp,
            ),
        )
        claim = _bundle_claim_row(self.conn, user_id, period_id)
        if not claim:
            raise PremiumRewardClaimError("Premium bundle claim insert was not recoverable")
        if int(getattr(claim_cursor, "rowcount", 0) or 0) != 1:
            return self._replay_claim(user_id=user_id, claim=claim, operation_id=claim_operation_id)
        if str(claim.get("reward_id")) != BUNDLE_VERSION or str(claim.get("claim_idempotency_key")) != claim_key:
            return self._replay_claim(user_id=user_id, claim=claim, operation_id=claim_operation_id)
        claim_id = int(claim["id"])
        lineage_id = f"premium-claim:{claim_id}"
        if fault_hook:
            fault_hook("after_claim_write")

        capacity_operation_id = f"premium-capacity:{claim_id}"
        capacity = apply_question_capacity_in_transaction(
            self.conn,
            user_id=user_id,
            item_id=QUESTION_BENEFIT_ITEM,
            operation_id=capacity_operation_id,
            source="PREMIUM_CLAIM",
            source_reference=claim_key,
            lineage_id=lineage_id,
            source_event_id=lineage_id,
            consume_inventory=False,
            now=current,
        )
        components: list[dict[str, Any]] = [{
            "component_key": QUESTION_COMPONENT_KEY,
            "component_type": "QUESTION_CAPACITY",
            "component_status": "GRANTED",
            "item_id": QUESTION_BENEFIT_ITEM,
            "capacity_delta": capacity.capacity_delta,
            "operation_id": capacity.operation_id,
            "event_id": capacity.event_id,
            "effective_capacity_after": capacity.effective_capacity_after,
            "business_date": capacity.business_date,
        }]

        cosmetic_ownership_reference = None
        cosmetic_ownership_created = False
        if cosmetic is not None:
            cosmetic_id = str(cosmetic["reward_id"])
            wardrobe_cursor = _execute(
                self.conn,
                "INSERT INTO player_wardrobe(user_id,item_id,obtained_at,source) VALUES(?,?,?,?) ON CONFLICT(user_id,item_id) DO NOTHING",
                (user_id, cosmetic_id, stamp, f"premium_bundle:{period_key}"),
            )
            cosmetic_ownership_created = int(getattr(wardrobe_cursor, "rowcount", 0) or 0) == 1
            wardrobe = _fetchone(self.conn, "SELECT id FROM player_wardrobe WHERE user_id=? AND item_id=?", (user_id, cosmetic_id))
            if not wardrobe:
                raise PremiumRewardClaimError("bundle cosmetic ownership row was not recoverable")
            cosmetic_ownership_reference = f"player_wardrobe:{int(wardrobe['id'])}"
            components.append({
                "component_key": f"PURE_COSMETIC:{cosmetic_id}",
                "component_type": "PURE_COSMETIC",
                "component_status": "GRANTED",
                "item_id": cosmetic_id,
                "operation_id": f"premium-cosmetic:{claim_id}:{cosmetic_id}",
                "ownership_reference": cosmetic_ownership_reference,
                "ownership_created": cosmetic_ownership_created,
            })
            if fault_hook:
                fault_hook("after_cosmetic_write")

        premium_payload = {
            "operation": "CLAIM_BUNDLE",
            "bundle_version": BUNDLE_VERSION,
            "claim_id": claim_id,
            "claim_family": CLAIM_FAMILY,
            "benefit_period": period_key,
            "premium_source": RECURRING_ELIGIBLE_SOURCE,
            "entitlement_grant_id": int(grant["id"]),
            "claim_idempotency_key": claim_key,
            "components": components,
            "claim_authority": "premium_reward_claims",
            "outbox_authority": False,
        }
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
        if fault_hook:
            fault_hook("after_premium_event")

        for component in components:
            if component["component_type"] != "PURE_COSMETIC":
                continue
            if not component.get("ownership_created"):
                continue
            item_event = append_event(
                self.conn,
                event_type=OUTBOX_ITEM_EVENT,
                player_id=str(user_id),
                lineage_id=lineage_id,
                idempotency_key=f"premium-item-acquisition:{claim_key}:{component['item_id']}",
                outcome="SUCCESS",
                payload={
                    "operation": "GRANT",
                    "grant_id": component["ownership_reference"],
                    "item_id": component["item_id"],
                    "acquisition_source": "PREMIUM",
                    "premium_source": RECURRING_ELIGIBLE_SOURCE,
                    "source_reference": lineage_id,
                    "ownership_authority": WARDROBE_AUTHORITY,
                    "ownership_committed": True,
                    "ownership_created": True,
                },
                source_event_id=str(premium_event["event_id"]),
                occurred_at=stamp,
            )
            component["event_id"] = str(item_event["event_id"])

        for component in components:
            _execute(
                self.conn,
                f"""INSERT INTO {BUNDLE_TABLE}(
                       claim_id,user_id,reward_period_id,component_key,
                       component_type,component_status,item_id,capacity_delta,
                       operation_id,result_payload,event_id,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    claim_id, user_id, period_id, component["component_key"],
                    component["component_type"], component["component_status"],
                    component.get("item_id"), component.get("capacity_delta"),
                    component["operation_id"], _json_value(self.conn, component),
                    component.get("event_id"), stamp,
                ),
            )

        _execute(
            self.conn,
            "UPDATE premium_reward_credits SET credit_state='CLAIMED',claim_id=?,updated_at=? WHERE id=? AND credit_state='EARNED' AND claim_id IS NULL",
            (claim_id, stamp, int(credit["id"])),
        )
        payload = {
            "status": "GRANTED",
            "reason": None,
            "claim_id": claim_id,
            "period_key": period_key,
            "claim_operation_id": claim_operation_id,
            "claim_idempotency_key": claim_key,
            "premium_event_id": str(premium_event["event_id"]),
            "bundle_version": BUNDLE_VERSION,
            "components": components,
        }
        complete_claim_operation(
            self.conn,
            user_id=user_id,
            operation_id=claim_operation_id,
            operation_status="SUCCESS",
            result_payload=payload,
            benefit_period_key=period_key,
            reward_id=BUNDLE_VERSION,
            claim_id=claim_id,
        )
        return _result_from_payload(payload, operation_id=claim_operation_id, created=True)


__all__ = [
    "BUNDLE_VERSION",
    "BundleClaimResult",
    "PremiumRewardBundleClaimService",
    "QUESTION_BENEFIT_ITEM",
    "QUESTION_COMPONENT_KEY",
]
