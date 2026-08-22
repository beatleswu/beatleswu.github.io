"""Minimal server-owned Premium provenance writer for the D5E candidate.

This module is intentionally not imported by application startup or payment
routes.  It records provenance and the existing ``users`` Premium access
projection in one caller-owned transaction.  It never grants a reward and it
never commits or rolls back the caller's transaction.
"""

from __future__ import annotations

import datetime as _datetime
import re
from typing import Any, Iterable

from migrations.premium_claim_lineage_v1 import SOURCE_CLASSES


class ProvenanceError(ValueError):
    """The requested provenance operation is unsafe or incomplete."""


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
        return {str(key): row[key] for key in row.keys()}
    return {str(item[0]): row[index] for index, item in enumerate(cursor.description)}


def _fetchone(conn: Any, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    cursor = _execute(conn, sql, params)
    try:
        return _row_dict(cursor, cursor.fetchone())
    finally:
        if not hasattr(conn, "execute"):
            cursor.close()


def _now_text(value: _datetime.datetime | None = None) -> str:
    stamp = value or _datetime.datetime.now(_datetime.timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=_datetime.timezone.utc)
    return stamp.isoformat()


def _parse_time(value: Any) -> _datetime.datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = _datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=_datetime.timezone.utc)


def _required(name: str, value: Any) -> str:
    if value is None or not str(value).strip():
        raise ProvenanceError(f"{name} is required")
    return str(value).strip()


def _validate_source(
    *,
    source_class: str,
    source_reference: Any,
    granted_by_or_system_source: Any,
    valid_from: Any,
    valid_until: Any,
    commercial_reward_eligibility: str,
    provider: Any = None,
    currency: Any = None,
    amount: Any = None,
    plan_key: Any = None,
    payment_order_id: Any = None,
    subscription_id: Any = None,
    trial_redemption_id: Any = None,
    classification_reason: Any = None,
    grant_policy_profile: Any = None,
) -> dict[str, Any]:
    if source_class not in SOURCE_CLASSES:
        raise ProvenanceError(f"unknown Premium source class: {source_class!r}")
    if commercial_reward_eligibility not in {"ALLOWED", "BLOCKED", "OWNER_POLICY_REQUIRED"}:
        raise ProvenanceError("invalid commercial_reward_eligibility")
    if source_class == "UNKNOWN" and commercial_reward_eligibility == "ALLOWED":
        raise ProvenanceError("UNKNOWN provenance cannot be reward-eligible")
    if source_class == "TRIAL" and commercial_reward_eligibility == "ALLOWED":
        raise ProvenanceError("TRIAL cannot receive recurring paid rewards")
    valid_from = _required("valid_from", valid_from)
    if _parse_time(valid_from) is None:
        raise ProvenanceError("valid_from must be an ISO timestamp")
    if valid_until is not None and _parse_time(valid_until) is None:
        raise ProvenanceError("valid_until must be an ISO timestamp or NULL")
    values = {
        "source_class": source_class,
        "source_reference": _required("source_reference", source_reference),
        "granted_by_or_system_source": _required("granted_by_or_system_source", granted_by_or_system_source),
        "valid_from": valid_from,
        "valid_until": valid_until,
        "commercial_reward_eligibility": commercial_reward_eligibility,
        "provider": provider,
        "currency": currency,
        "amount": amount,
        "plan_key": plan_key,
        "payment_order_id": payment_order_id,
        "subscription_id": subscription_id,
        "trial_redemption_id": trial_redemption_id,
        "classification_reason": classification_reason,
        "grant_policy_profile": grant_policy_profile,
    }
    if source_class == "VERIFIED_PAID":
        for field, value in (("provider", provider), ("currency", currency), ("amount", amount), ("plan_key", plan_key)):
            _required(field, value)
        if payment_order_id is None and subscription_id is None:
            raise ProvenanceError("VERIFIED_PAID requires payment_order_id or subscription_id")
    elif source_class == "TRIAL" and trial_redemption_id is None:
        raise ProvenanceError("TRIAL requires trial_redemption_id")
    elif source_class in {"LEGACY", "UNKNOWN"}:
        _required("classification_reason", classification_reason)
    elif source_class in {"ADMIN_GRANTED", "PERMANENT_COMP"}:
        _required("grant_policy_profile", grant_policy_profile)
    return values


def _projection_until(current_plan: Any, current: Any, requested: Any) -> Any:
    if current_plan == "premium" and current in (None, ""):
        return None
    if current in (None, "") or requested in (None, ""):
        return None if current in (None, "") and requested in (None, "") else (current if requested in (None, "") else requested)
    current_time = _parse_time(current)
    requested_time = _parse_time(requested)
    if not current_time or not requested_time:
        raise ProvenanceError("cannot compare Premium projection expiry")
    return current if current_time >= requested_time else requested


def grant_premium_with_provenance(
    conn: Any,
    *,
    user_id: int,
    source_class: str,
    source_reference: str,
    granted_by_or_system_source: str,
    valid_from: str,
    valid_until: str | None,
    commercial_reward_eligibility: str,
    plan_term: str | None = None,
    granted_at: str | None = None,
    provider: str | None = None,
    currency: str | None = None,
    amount: Any = None,
    plan_key: str | None = None,
    payment_order_id: int | None = None,
    subscription_id: int | None = None,
    trial_redemption_id: int | None = None,
    classification_reason: str | None = None,
    grant_policy_profile: str | None = None,
) -> dict[str, Any]:
    """Insert/recover one immutable entitlement grant in the caller transaction."""

    values = _validate_source(
        source_class=source_class,
        source_reference=source_reference,
        granted_by_or_system_source=granted_by_or_system_source,
        valid_from=valid_from,
        valid_until=valid_until,
        commercial_reward_eligibility=commercial_reward_eligibility,
        provider=provider,
        currency=currency,
        amount=amount,
        plan_key=plan_key,
        payment_order_id=payment_order_id,
        subscription_id=subscription_id,
        trial_redemption_id=trial_redemption_id,
        classification_reason=classification_reason,
        grant_policy_profile=grant_policy_profile,
    )
    user = _fetchone(conn, "SELECT id, plan, premium_until FROM users WHERE id=?", (user_id,))
    if not user:
        raise ProvenanceError("Premium grant user does not exist")
    stamp = granted_at or _now_text()
    cursor = _execute(
        conn,
        """INSERT INTO premium_entitlement_grants(
               user_id,source_class,source_reference,granted_at,
               granted_by_or_system_source,valid_from,valid_until,
               commercial_reward_eligibility,grant_policy_profile,provider,
               currency,amount,plan_key,plan_term,payment_order_id,
               subscription_id,trial_redemption_id,classification_reason,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(user_id,source_class,source_reference) DO NOTHING""",
        (
            user_id, values["source_class"], values["source_reference"], stamp,
            values["granted_by_or_system_source"], values["valid_from"], values["valid_until"],
            values["commercial_reward_eligibility"], values["grant_policy_profile"],
            values["provider"], values["currency"], values["amount"], values["plan_key"],
            plan_term, values["payment_order_id"], values["subscription_id"],
            values["trial_redemption_id"], values["classification_reason"], stamp,
        ),
    )
    grant = _fetchone(
        conn,
        "SELECT * FROM premium_entitlement_grants WHERE user_id=? AND source_class=? AND source_reference=?",
        (user_id, source_class, values["source_reference"]),
    )
    if not grant:
        raise ProvenanceError("Premium grant insert was not recoverable")
    immutable = ("user_id", "source_class", "source_reference", "valid_from", "valid_until", "commercial_reward_eligibility")
    expected = {"user_id": user_id, **values}
    if any(grant.get(field) != expected.get(field) for field in immutable):
        raise ProvenanceError("Premium grant identity conflicts with existing provenance")
    grant_id = int(grant["id"])
    event_key = f"premium-grant:{grant_id}:GRANT:{values['source_reference']}:{values['valid_from']}"
    event_cursor = _execute(
        conn,
        """INSERT INTO premium_entitlement_events(
               entitlement_grant_id,parent_entitlement_event_id,user_id,event_type,
               source_class,source_reference,granted_at,granted_by_or_system_source,
               valid_from,valid_until,commercial_reward_eligibility,
               grant_policy_profile,provider,currency,amount,plan_key,plan_term,
               payment_order_id,subscription_id,trial_redemption_id,
               classification_reason,idempotency_key,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(idempotency_key) DO NOTHING""",
        (
            grant_id, None, user_id, "GRANT", source_class, values["source_reference"],
            stamp, values["granted_by_or_system_source"], values["valid_from"],
            values["valid_until"], values["commercial_reward_eligibility"],
            values["grant_policy_profile"], values["provider"], values["currency"],
            values["amount"], values["plan_key"], plan_term,
            values["payment_order_id"], values["subscription_id"],
            values["trial_redemption_id"], values["classification_reason"],
            event_key, stamp,
        ),
    )
    event = _fetchone(conn, "SELECT id FROM premium_entitlement_events WHERE idempotency_key=?", (event_key,))
    if not event:
        raise ProvenanceError("Premium entitlement event was not recoverable")
    current_until = user.get("premium_until")
    requested_until = values["valid_until"]
    effective_until = _projection_until(user.get("plan"), current_until, requested_until)
    updated = _execute(
        conn,
        "UPDATE users SET plan='premium', premium_until=? WHERE id=?",
        (effective_until, user_id),
    )
    if int(getattr(updated, "rowcount", 0) or 0) != 1:
        raise ProvenanceError("Premium access projection update was not exact")
    return {
        "grant_id": grant_id,
        "event_id": int(event["id"]),
        "created": int(getattr(cursor, "rowcount", 0) or 0) == 1,
        "source_class": source_class,
        "commercial_reward_eligibility": values["commercial_reward_eligibility"],
    }


__all__ = ["ProvenanceError", "grant_premium_with_provenance"]
