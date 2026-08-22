"""C013 Revenue V1 adapter for deterministic Premium benefits.

This module deliberately sits on top of the D5A/D5B/D5E/D5F authorities:

* ``PremiumRewardBundleClaimService`` owns the period claim transaction.
* D5B owns the question-capacity mutation and lineage event.
* ``player_wardrobe`` remains cosmetic ownership authority.
* D5A owns the transactional outbox evidence.

The adapter contributes only C013 policy: the exact five-item cosmetic pool,
server-side period selection, the default-off route gate, and a read-only
support projection.  It does not create a claim table, wallet, migration, or
payment path.
"""

from __future__ import annotations

import datetime as _datetime
import json
import os
from typing import Any, Mapping, Sequence

from premium_claim_operations import get_claim_operation
from premium_reward_bundle_runtime import (
    BundleClaimResult,
    PremiumRewardBundleClaimService,
)
from premium_reward_claim_runtime import (
    RECURRING_REWARD_TYPE,
    PremiumRewardClaimError,
    _now,
    _parse_time,
)
from premium_reward_catalog_adapter import PremiumRewardCatalogResolver


C013_VERSION = "revenue-v1-premium-deterministic-benefit-v1"
C013_CLAIM_ROUTE_ENABLED_ENV = "GO_REVENUE_V1_PREMIUM_CLAIM_ENABLED"
C013_REWARD_CATALOG_KEY = "revenue_v1_locked_cosmetics_v1"
C013_QUESTION_ITEM_ID = "extra_questions_small"
C013_QUESTION_DELTA = 5
C013_CLAIM_GRACE_DAYS = 90

# Owner-locked C013 pool.  Keep this as policy IDs only; names, effects, and
# art metadata are resolved from the existing canonical appearance registry.
C013_LAUNCH_COSMETIC_IDS = (
    "robe_plain",
    "robe_bamboo",
    "robe_fox",
    "back_pack",
    "acc_dragon_pendant",
)
C013_HIDDEN_IDS = frozenset({
    "robe_snow",
    "hat_scholar",
    "back_lantern",
    "back_scroll",
    "acc_goban_seal",
})

C013_PLAN_PRICES = {
    "newebpay": {
        "monthly": {"currency": "TWD", "amount": 299},
        "annual": {"currency": "TWD", "amount": 2490},
    },
    "paypal": {
        "monthly": {"currency": "USD", "amount": "9.9"},
        "annual": {"currency": "USD", "amount": "84"},
    },
}


def c013_claim_route_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Return the explicit candidate flag; the absent/default state is off."""

    values = environ if environ is not None else os.environ
    return str(values.get(C013_CLAIM_ROUTE_ENABLED_ENV, "0")).strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _raw(conn: Any) -> Any:
    return getattr(conn, "_conn", conn)


def _is_sqlite(conn: Any) -> bool:
    return _raw(conn).__class__.__module__.lower().startswith("sqlite3")


def _execute(conn: Any, sql: str, params: Sequence[Any] = ()) -> Any:
    if hasattr(conn, "execute"):
        return conn.execute(sql, tuple(params))
    cursor = conn.cursor()
    cursor.execute(sql.replace("?", "%s"), tuple(params))
    return cursor


def _row_dict(cursor: Any, row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    if hasattr(row, "keys"):
        return {str(key): row[key] for key in row.keys()}
    return {str(item[0]): row[index] for index, item in enumerate(cursor.description)}


def _fetchone(conn: Any, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
    cursor = _execute(conn, sql, params)
    try:
        return _row_dict(cursor, cursor.fetchone())
    finally:
        if not hasattr(conn, "execute"):
            cursor.close()


def _fetchall(conn: Any, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    cursor = _execute(conn, sql, params)
    try:
        return [
            item
            for item in (_row_dict(cursor, row) for row in cursor.fetchall())
            if item is not None
        ]
    finally:
        if not hasattr(conn, "execute"):
            cursor.close()


def _decode(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    return value


def _effect_is_empty(effect: Any) -> bool:
    if not effect:
        return True
    if not isinstance(effect, Mapping):
        return False
    return not any(value not in (None, 0, 0.0, False, "", "0") for value in effect.values())


class C013AppearanceCatalogResolver(PremiumRewardCatalogResolver):
    """Resolve C013 IDs from the existing appearance/presentation registries.

    The resolver stores no copied product rows.  It receives the canonical
    registries from ``app.py`` at call time, so C013 cannot become a second
    catalog or art authority.
    """

    def __init__(
        self,
        *,
        appearance_defs: Sequence[Mapping[str, Any]],
        presentation_registry: Mapping[str, Mapping[str, Any]],
        hidden_ids: Sequence[str] = C013_HIDDEN_IDS,
        appearance_effects: Mapping[str, Mapping[str, Any]] | None = None,
        owned_ids: Sequence[str] = (),
    ) -> None:
        self._appearance_by_id = {
            str(item.get("id")): item for item in appearance_defs if item.get("id")
        }
        self._presentation = presentation_registry
        self._hidden_ids = frozenset(str(item) for item in hidden_ids)
        self._effects = appearance_effects or {}
        self._owned_ids = frozenset(str(item) for item in owned_ids)

    def resolve_period_reward(
        self,
        *,
        period_key: str,
        reward_catalog_key: str,
        requested_reward_id: str | None = None,
    ) -> Mapping[str, Any] | None:
        del period_key
        if reward_catalog_key != C013_REWARD_CATALOG_KEY:
            return None
        reward_id = str(requested_reward_id or "").strip()
        if reward_id not in C013_LAUNCH_COSMETIC_IDS or reward_id in self._hidden_ids:
            return None
        if reward_id in self._owned_ids:
            return None
        appearance = self._appearance_by_id.get(reward_id)
        presentation = self._presentation.get(reward_id)
        if not appearance or not presentation:
            return None
        if presentation.get("pure_presentation") is not True:
            return None
        if not presentation.get("asset") or presentation.get("asset_format") not in {"WEBP", "SVG"}:
            return None
        if not _effect_is_empty(self._effects.get(reward_id)):
            return None
        return {
            "reward_id": reward_id,
            "reward_type": "PURE_COSMETIC",
            "display_name": appearance.get("name", reward_id),
            "display_name_en": appearance.get("name_en", appearance.get("name", reward_id)),
            "category": appearance.get("slot", "appearance"),
            "rarity": appearance.get("rarity", "common"),
            "preview_asset": dict(presentation),
            "pure_presentation": True,
            "functional_effect_count": 0,
            "effect_flags": {},
            "combat_authority": "NO",
            "ownership_authority": "player_wardrobe",
            "asset_key": presentation.get("asset_id", reward_id),
            "source_policy": "C013_LOCKED_POOL",
        }


def build_c013_catalog_resolver(
    *,
    appearance_defs: Sequence[Mapping[str, Any]],
    presentation_registry: Mapping[str, Mapping[str, Any]],
    hidden_ids: Sequence[str] = C013_HIDDEN_IDS,
    appearance_effects: Mapping[str, Mapping[str, Any]] | None = None,
    owned_ids: Sequence[str] = (),
) -> C013AppearanceCatalogResolver:
    return C013AppearanceCatalogResolver(
        appearance_defs=appearance_defs,
        presentation_registry=presentation_registry,
        hidden_ids=hidden_ids,
        appearance_effects=appearance_effects,
        owned_ids=owned_ids,
    )


def build_c013_offer_projection(
    *,
    enabled: bool,
    premium_entitled: bool,
    catalog_resolver: C013AppearanceCatalogResolver,
    owned_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Build the player-facing candidate contract without mutating state."""

    owned = {str(item) for item in owned_ids}
    pool = []
    for reward_id in C013_LAUNCH_COSMETIC_IDS:
        reward = catalog_resolver.resolve_period_reward(
            period_key="offer",
            reward_catalog_key=C013_REWARD_CATALOG_KEY,
            requested_reward_id=reward_id,
        )
        if reward is None:
            continue
        pool.append({
            "item_id": reward_id,
            "display_name": reward["display_name"],
            "display_name_en": reward["display_name_en"],
            "category": reward["category"],
            "rarity": reward["rarity"],
            "preview_asset": reward["preview_asset"],
            "owned": reward_id in owned,
            "pure_presentation": True,
            "combat_authority": "NO",
        })
    return {
        "version": C013_VERSION,
        "enabled": bool(enabled),
        "default_off": not bool(enabled),
        "premium_entitled": bool(premium_entitled),
        "prices": C013_PLAN_PRICES,
        "benefits": [
            {
                "benefit_id": "monthly_question_capacity",
                "item_id": C013_QUESTION_ITEM_ID,
                "quantity": 1,
                "capacity_delta": C013_QUESTION_DELTA,
                "authority": "D5B.question_capacity_authority",
                "claim_cadence": "one_per_eligible_month",
            },
            {
                "benefit_id": "pure_cosmetic_collection_credit",
                "quantity": 1,
                "authority": "D5F.bundle_plus_player_wardrobe",
                "claim_cadence": "one_per_eligible_month",
                "selection_required": True,
            },
            {
                "benefit_id": "premium_identity_status",
                "authority": "existing_premium_projection",
                "claim_cadence": "active_entitlement",
            },
        ],
        "annual_policy": {
            "vesting": "MONTHLY",
            "grace_days_for_earned_credits": C013_CLAIM_GRACE_DAYS,
            "upfront_credit_count": 0,
            "subscription_gap_generates_backfill": False,
        },
        "cosmetic_pool": pool,
        "hidden_excluded_ids": sorted(C013_HIDDEN_IDS),
        "functional_appearance_excluded": True,
        "payment_provider_authority": "EXISTING_PROTECTED_BILLING",
    }


def _period_is_in_claim_window(
    period: Mapping[str, Any],
    *,
    current: _datetime.datetime,
    annual_grace_days: int = 0,
) -> bool:
    start = _parse_time(period.get("period_starts_at"))
    window_start = _parse_time(period.get("claim_window_starts_at"))
    window_end = _parse_time(period.get("claim_window_ends_at"))
    if not start or not window_start or not window_end:
        return False
    if current < start or current < window_start:
        return False
    return current <= window_end + _datetime.timedelta(days=max(0, annual_grace_days))


def _month_start(value: _datetime.date) -> _datetime.date:
    return value.replace(day=1)


def _add_months(value: _datetime.date, months: int) -> _datetime.date:
    index = value.year * 12 + (value.month - 1) + int(months)
    return _datetime.date(index // 12, index % 12 + 1, 1)


def _month_end(value: _datetime.date) -> _datetime.date:
    return _add_months(_month_start(value), 1) - _datetime.timedelta(days=1)


def build_c013_reward_period(
    period_start: _datetime.date,
    *,
    plan_term: str,
    created_at: _datetime.datetime | None = None,
) -> dict[str, Any]:
    """Build one deterministic monthly period; it never creates a credit."""

    start = _month_start(period_start)
    end = _month_end(start)
    claim_end = _month_end(_add_months(start, 2))
    stamp = _now(created_at).isoformat()
    return {
        "period_key": start.strftime("%Y-%m"),
        "reward_type": RECURRING_REWARD_TYPE,
        "reward_catalog_key": C013_REWARD_CATALOG_KEY,
        "period_starts_at": f"{start.isoformat()}T00:00:00+00:00",
        "period_ends_at": f"{end.isoformat()}T23:59:59+00:00",
        "claim_window_starts_at": f"{start.isoformat()}T00:00:00+00:00",
        "claim_window_ends_at": f"{claim_end.isoformat()}T23:59:59+00:00",
        "annual_grace_days": C013_CLAIM_GRACE_DAYS if str(plan_term).upper() == "ANNUAL" else 0,
        "eligibility_policy_version": "c013_verified_paid_v1",
        "created_at": stamp,
    }


def build_c013_annual_vesting_periods(
    valid_from: _datetime.date,
    *,
    created_at: _datetime.datetime | None = None,
) -> tuple[dict[str, Any], ...]:
    """Return exactly twelve monthly period rows for an annual grant."""

    start = _month_start(valid_from)
    return tuple(
        build_c013_reward_period(
            _add_months(start, offset),
            plan_term="ANNUAL",
            created_at=created_at,
        )
        for offset in range(12)
    )


def ensure_c013_reward_periods(
    conn: Any,
    periods: Sequence[Mapping[str, Any]],
) -> int:
    """Idempotently seed only period definitions; no credits or ownership.

    This helper is a separately callable candidate for a governed entitlement
    scheduler.  App startup and the default-off claim route never call it.
    Existing rows with a different C013 contract fail closed instead of being
    overwritten.
    """

    inserted = 0
    for period in periods:
        required = {
            "period_key": str(period["period_key"]),
            "reward_type": str(period["reward_type"]),
            "reward_catalog_key": str(period["reward_catalog_key"]),
            "period_starts_at": str(period["period_starts_at"]),
            "period_ends_at": str(period["period_ends_at"]),
            "claim_window_starts_at": str(period["claim_window_starts_at"]),
            "claim_window_ends_at": str(period["claim_window_ends_at"]),
            "annual_grace_days": int(period["annual_grace_days"]),
            "eligibility_policy_version": str(period["eligibility_policy_version"]),
            "created_at": str(period["created_at"]),
        }
        cursor = _execute(
            conn,
            """INSERT INTO premium_reward_periods(
                   period_key,reward_type,reward_catalog_key,period_starts_at,
                   period_ends_at,claim_window_starts_at,claim_window_ends_at,
                   annual_grace_days,eligibility_policy_version,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(period_key) DO NOTHING""",
            tuple(required.values()),
        )
        inserted += int(getattr(cursor, "rowcount", 0) or 0) == 1
        existing = _fetchone(
            conn,
            """SELECT period_key,reward_type,reward_catalog_key,period_starts_at,
                      period_ends_at,claim_window_starts_at,claim_window_ends_at,
                      annual_grace_days,eligibility_policy_version
                 FROM premium_reward_periods WHERE period_key=?""",
            (required["period_key"],),
        )
        if not existing or any(
            str(existing.get(key)) != str(required[key])
            for key in (
                "period_key",
                "reward_type",
                "reward_catalog_key",
                "period_starts_at",
                "period_ends_at",
                "claim_window_starts_at",
                "claim_window_ends_at",
                "annual_grace_days",
                "eligibility_policy_version",
            )
        ):
            raise PremiumRewardClaimError("C013 reward period contract conflict")
    return inserted


def select_server_claim_period(
    service: PremiumRewardBundleClaimService,
    *,
    user_id: int,
    operation_id: str | None = None,
    now: _datetime.datetime | None = None,
) -> str | None:
    """Select the earliest eligible unclaimed period using D5E evidence.

    The request body never supplies a period.  This read-only selection pass
    checks the existing D5E provenance and projection before the D5F claim
    transaction runs.  Period rows must be generated by the separately
    governed Premium schedule writer; C013 does not create them at startup.
    """

    if operation_id:
        existing_operation = get_claim_operation(
            service.conn,
            user_id=int(user_id),
            operation_id=str(operation_id),
        )
        if existing_operation and existing_operation.get("benefit_period_key"):
            # Preserve response-loss retry identity before selecting a newer
            # unclaimed period.  D5F will re-validate the exact request.
            return str(existing_operation["benefit_period_key"])

    current = _now(now)
    periods = _fetchall(
        service.conn,
        "SELECT * FROM premium_reward_periods WHERE reward_type=? "
        "ORDER BY period_starts_at ASC,id ASC",
        (RECURRING_REWARD_TYPE,),
    )
    for period in periods:
        period_id = int(period["id"])
        if _fetchone(
            service.conn,
            "SELECT 1 AS present FROM premium_reward_claims "
            "WHERE user_id=? AND reward_period_id=? LIMIT 1",
            (int(user_id), period_id),
        ):
            continue
        existing_credit = _fetchone(
            service.conn,
            "SELECT * FROM premium_reward_credits WHERE user_id=? AND reward_period_id=?",
            (int(user_id), period_id),
        )
        access_active = service.current_access(int(user_id), now=current)
        if not access_active and not existing_credit:
            continue
        allow_annual_grace = bool(
            existing_credit
            and str(existing_credit.get("plan_term_snapshot") or "").upper() == "ANNUAL"
        )
        grant = service._find_verified_grant(  # D5E canonical source evaluator
            int(user_id),
            period,
            now=current,
            allow_annual_grace=allow_annual_grace or access_active,
        )
        if not grant:
            continue
        grace = (
            int(period.get("annual_grace_days") or 0)
            if str(grant.get("plan_term") or "").upper() == "ANNUAL"
            else 0
        )
        if _period_is_in_claim_window(period, current=current, annual_grace_days=grace):
            return str(period["period_key"])
    return None


def c013_result_payload(result: BundleClaimResult) -> dict[str, Any]:
    payload = result.as_dict()
    payload["credit_consumed"] = result.status == "GRANTED"
    if result.reason == "CATALOG_REWARD_UNAVAILABLE":
        # The D5F service resolves the cosmetic before creating the credit.
        # C013 exposes the product contract's stable support-facing reason.
        payload["reason"] = "NO_AVAILABLE_REWARD"
        payload["credit_consumed"] = False
    return payload


def _evidence_events(conn: Any, user_id: int, claim_id: int | None, operation_id: str) -> list[dict[str, Any]]:
    lineage = f"premium-claim:{claim_id}" if claim_id is not None else ""
    rows = _fetchall(
        conn,
        """SELECT event_id,event_type,idempotency_key,lineage_id,source_event_id,
                         outcome,payload,occurred_at
                  FROM domain_event_outbox
                 WHERE player_id=?
                   AND (lineage_id=? OR idempotency_key=? OR idempotency_key LIKE ?)
                 ORDER BY occurred_at ASC,event_id ASC""",
        (str(user_id), lineage, operation_id, f"%{operation_id}%"),
    )
    for row in rows:
        row["payload"] = _decode(row.get("payload"))
    return rows


def read_c013_claim_evidence(conn: Any, *, user_id: int, operation_id: str) -> dict[str, Any]:
    """Read-only support reconstruction using D5 provenance and outbox rows."""

    operation = get_claim_operation(conn, user_id=int(user_id), operation_id=str(operation_id))
    if not operation:
        return {"status": "NOT_FOUND", "operation_id": str(operation_id)}
    claim_id = int(operation["claim_id"]) if operation.get("claim_id") is not None else None
    claim = None
    period = None
    credit = None
    grant = None
    components: list[dict[str, Any]] = []
    try:
        if claim_id is not None:
            claim = _fetchone(conn, "SELECT * FROM premium_reward_claims WHERE id=?", (claim_id,))
            if claim:
                period = _fetchone(conn, "SELECT * FROM premium_reward_periods WHERE id=?", (claim["reward_period_id"],))
                credit = _fetchone(conn, "SELECT * FROM premium_reward_credits WHERE id=?", (claim["reward_credit_id"],))
                grant = _fetchone(conn, "SELECT * FROM premium_entitlement_grants WHERE id=?", (claim["entitlement_grant_id"],))
                components = _fetchall(
                    conn,
                    "SELECT component_key,component_type,component_status,item_id,capacity_delta,operation_id,event_id,result_payload,created_at "
                    "FROM premium_reward_bundle_components WHERE claim_id=? ORDER BY id",
                    (claim_id,),
                )
                for component in components:
                    component["result_payload"] = _decode(component.get("result_payload"))
        return {
            "status": "OK",
            "operation": operation,
            "entitlement": grant,
            "period": period,
            "credit": credit,
            "claim": claim,
            "components": components,
            "outbox_events": _evidence_events(conn, int(user_id), claim_id, str(operation_id)),
            "mutation_authorities": {
                "question_capacity": "D5B.question_capacity_authority",
                "cosmetic_ownership": "player_wardrobe",
                "commercial_event": "D5A.domain_event_outbox",
            },
        }
    except Exception as exc:
        return {
            "status": "UNAVAILABLE",
            "operation_id": str(operation_id),
            "reason": "C013_EVIDENCE_SCHEMA_UNAVAILABLE",
            "error_type": type(exc).__name__,
        }


__all__ = [
    "C013_CLAIM_GRACE_DAYS",
    "C013_CLAIM_ROUTE_ENABLED_ENV",
    "C013_HIDDEN_IDS",
    "C013_LAUNCH_COSMETIC_IDS",
    "C013_PLAN_PRICES",
    "C013_QUESTION_DELTA",
    "C013_QUESTION_ITEM_ID",
    "C013_REWARD_CATALOG_KEY",
    "C013_VERSION",
    "C013AppearanceCatalogResolver",
    "build_c013_catalog_resolver",
    "build_c013_annual_vesting_periods",
    "build_c013_offer_projection",
    "build_c013_reward_period",
    "c013_claim_route_enabled",
    "c013_result_payload",
    "ensure_c013_reward_periods",
    "read_c013_claim_evidence",
    "select_server_claim_period",
]
