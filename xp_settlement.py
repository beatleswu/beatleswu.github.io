"""R1A XP settlement foundation.

This module is intentionally dormant until an explicit server-side feature
flag is enabled.  R1A provides the additive ledger schema and deterministic
calculation primitives; current XP writers are not routed here yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP as DECIMAL_ROUND_HALF_UP
import json
import os
import re
from typing import Any, Callable, Iterable, Mapping, Optional

from psycopg2 import IntegrityError
from psycopg2.extras import Json


FACTOR_SCALE = 1_000_000
NO_PREMIUM_FACTOR_PPM = FACTOR_SCALE
PREMIUM_18_FACTOR_PPM = 1_180_000
ROUNDING_POLICY_VERSION = "r1a-round-half-up-v1"
SETTLEMENT_STATUS_SETTLED = "SETTLED"
MAX_RETRY_VALUE = 2
LOCK_TIMEOUT_VALUE = None

LEDGER_TABLE_NAME = "xp_settlement_ledger"
LEDGER_SCHEMA_FLAG = "XP_LEDGER_SCHEMA_ENABLED"
SETTLEMENT_FLAG = "XP_SETTLEMENT_ENABLED"
SHADOW_FLAG = "XP_SHADOW_ENABLED"

_CANONICAL_SAFE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_._:-]*$")
_MAX_KEY_LENGTHS = {
    "source_type": 64,
    "source_id": 255,
    "source_version": 32,
    "idempotency_key": 255,
    "request_correlation_id": 255,
}


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def xp_ledger_schema_enabled() -> bool:
    """Return the server-side schema flag; it is OFF unless explicitly set."""

    return _env_flag(LEDGER_SCHEMA_FLAG, False)


def xp_settlement_enabled() -> bool:
    """Return the server-side settlement mutation flag; it is OFF by default."""

    return _env_flag(SETTLEMENT_FLAG, False)


def xp_shadow_enabled() -> bool:
    """Return the observational shadow flag; it is OFF unless explicitly enabled."""

    return _env_flag(SHADOW_FLAG, False)


def _require_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    return value


def _require_nonnegative_int(value: Any, name: str) -> int:
    value = _require_int(value, name)
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _require_factor_ppm(value: Any, name: str = "factor_ppm") -> int:
    value = _require_int(value, name)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def factor_value_to_ppm(value: Any, name: str = "factor") -> int:
    """Convert a legacy decimal factor to canonical integer PPM.

    The calculation pipeline never uses the input decimal directly. Values
    that cannot be represented exactly at six decimal places fail closed so
    the conversion does not introduce a second rounding policy.
    """

    try:
        decimal_value = Decimal(str(value))
        scaled = decimal_value * Decimal(FACTOR_SCALE)
        integral = scaled.to_integral_value(rounding=DECIMAL_ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{name} must be a decimal factor") from None
    if scaled != integral:
        raise ValueError(f"{name} exceeds six decimal places")
    return _require_factor_ppm(int(integral), f"{name}_ppm")


def round_half_up_fraction(numerator: int, denominator: int) -> int:
    """Round an integer fraction half-up, without float or Decimal arithmetic.

    Positive values round ties away from zero.  Signed admin adjustments use
    the same absolute-value rule, so -1.5 becomes -2 rather than relying on
    language-specific banker rounding.
    """

    numerator = _require_int(numerator, "numerator")
    denominator = _require_int(denominator, "denominator")
    if denominator <= 0:
        raise ValueError("denominator must be positive")

    sign = -1 if numerator < 0 else 1
    magnitude = abs(numerator)
    rounded = (2 * magnitude + denominator) // (2 * denominator)
    return sign * rounded


def multiply_factors_final_round(value: int, factors_ppm: Iterable[int]) -> int:
    """Apply all fixed-point factors and round exactly once at the end."""

    value = _require_int(value, "value")
    numerator = value
    denominator = 1
    for index, factor in enumerate(factors_ppm):
        factor = _require_factor_ppm(factor, f"factors_ppm[{index}]")
        numerator *= factor
        denominator *= FACTOR_SCALE
    return round_half_up_fraction(numerator, denominator)


@dataclass(frozen=True)
class XPCalculation:
    """Auditable result of the R1A fixed-point calculation pipeline."""

    base_xp: int
    additive_learning_xp: int
    combo_factor_ppm: int
    support_factor_ppm: int
    support_factors_ppm: tuple[int, ...]
    premium_factor_ppm: int
    numerator: int
    denominator: int
    final_xp: int

    @property
    def modifier_payload(self) -> dict[str, Any]:
        payload = {
            "factor_scale": FACTOR_SCALE,
            "combo_factor_ppm": self.combo_factor_ppm,
            "support_factor_ppm": self.support_factor_ppm,
            "premium_factor_ppm": self.premium_factor_ppm,
        }
        if len(self.support_factors_ppm) > 1:
            payload["support_factors_ppm"] = list(self.support_factors_ppm)
        return payload


SHADOW_MISMATCH_CATEGORIES = (
    "MATCH",
    "ROUNDING_MISMATCH",
    "PREMIUM_MISMATCH",
    "BASE_XP_MISMATCH",
    "MODIFIER_MISMATCH",
    "EVENT_IDENTITY_MISMATCH",
    "UNSUPPORTED_WRITER",
    "LEGACY_SEMANTIC_DIFFERENCE",
    "ERROR_FAIL_CLOSED",
)


def _validate_shadow_text(value: Any, field_name: str, max_length: int = 255) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    if len(value) > max_length:
        raise ValueError(f"{field_name} exceeds {max_length} characters")
    return value


@dataclass(frozen=True)
class XPShadowComparison:
    """Read-only old-vs-new evidence for one already-authoritative reward event."""

    source_type: str
    source_id: str
    source_marker: str
    event_identity: str
    idempotency_key: str
    legacy_xp: int
    shadow_xp: int
    difference: int
    mismatch_category: str
    premium_eligibility: str
    legacy_premium_already_applied: bool
    base_xp: int
    additive_learning_xp: int
    combo_factor_ppm: int
    support_factor_ppm: int
    support_factors_ppm: tuple[int, ...]
    premium_factor_ppm: int
    numerator: int
    denominator: int

    def as_dict(self) -> dict[str, Any]:
        evidence = {
            "schema_version": "xp-shadow-v1",
            "source_type": self.source_type,
            "source_id": self.source_id,
            "source_marker": self.source_marker,
            "event_identity": self.event_identity,
            "idempotency_key": self.idempotency_key,
            "legacy_xp": self.legacy_xp,
            "shadow_xp": self.shadow_xp,
            "difference": self.difference,
            "mismatch_category": self.mismatch_category,
            "premium_eligibility": self.premium_eligibility,
            "legacy_premium_already_applied": self.legacy_premium_already_applied,
            "base_xp": self.base_xp,
            "additive_learning_xp": self.additive_learning_xp,
            "combo_factor_ppm": self.combo_factor_ppm,
            "support_factor_ppm": self.support_factor_ppm,
            "premium_factor_ppm": self.premium_factor_ppm,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "side_effect_free": True,
            "ledger_inserted": False,
            "idempotency_consumed": False,
        }
        if len(self.support_factors_ppm) > 1:
            evidence["support_factors_ppm"] = list(self.support_factors_ppm)
        return evidence


def compare_xp_shadow(
    *,
    source_type: str,
    source_id: str,
    source_marker: str,
    event_identity: str,
    idempotency_key: str,
    legacy_xp: int,
    base_xp: int,
    additive_learning_bonuses: Iterable[int] = (),
    combo_factor_ppm: int = FACTOR_SCALE,
    support_factor_ppm: int = FACTOR_SCALE,
    support_factors_ppm: Iterable[int] = (),
    premium_eligibility: str = "PREMIUM_INELIGIBLE",
    already_premium_adjusted: bool = False,
    legacy_premium_already_applied: bool = False,
    mismatch_hint: Optional[str] = None,
) -> XPShadowComparison:
    """Compare a legacy award with the R1A calculation without touching storage.

    The caller supplies the event identity and the amount the existing writer
    would award.  This function deliberately does not accept a database
    connection and cannot insert a ledger row, consume an idempotency key, or
    mutate player state.
    """

    source_type = _validate_key(source_type, "source_type")
    source_id = _validate_shadow_text(source_id, "source_id")
    source_marker = _validate_shadow_text(source_marker, "source_marker")
    event_identity = _validate_shadow_text(event_identity, "event_identity")
    idempotency_key = _validate_key(idempotency_key, "idempotency_key")
    legacy_xp = _require_nonnegative_int(legacy_xp, "legacy_xp")
    if mismatch_hint is not None and mismatch_hint not in SHADOW_MISMATCH_CATEGORIES:
        raise ValueError("invalid mismatch_hint")
    if premium_eligibility not in {
        "PREMIUM_ELIGIBLE",
        "PREMIUM_INELIGIBLE",
        "ALREADY_PREMIUM_ADJUSTED",
    }:
        raise ValueError("invalid premium_eligibility")
    if premium_eligibility == "PREMIUM_ELIGIBLE" and already_premium_adjusted:
        raise ValueError("Premium cannot be eligible and already adjusted")

    premium_factor_ppm = (
        PREMIUM_18_FACTOR_PPM
        if premium_eligibility == "PREMIUM_ELIGIBLE" and not already_premium_adjusted
        else NO_PREMIUM_FACTOR_PPM
    )
    calculation = calculate_xp(
        base_xp,
        additive_learning_bonuses,
        combo_factor_ppm=combo_factor_ppm,
        support_factor_ppm=support_factor_ppm,
        support_factors_ppm=support_factors_ppm,
        premium_factor_ppm=premium_factor_ppm,
    )
    difference = calculation.final_xp - legacy_xp
    if difference == 0:
        mismatch_category = "MATCH"
    elif mismatch_hint is not None:
        mismatch_category = mismatch_hint
    elif premium_eligibility != "PREMIUM_INELIGIBLE" or legacy_premium_already_applied:
        mismatch_category = "PREMIUM_MISMATCH"
    elif (
        calculation.base_xp != legacy_xp
        and not calculation.additive_learning_xp
        and combo_factor_ppm == FACTOR_SCALE
        and calculation.support_factors_ppm == (FACTOR_SCALE,)
    ):
        mismatch_category = "BASE_XP_MISMATCH"
    elif (
        calculation.additive_learning_xp
        or combo_factor_ppm != FACTOR_SCALE
        or calculation.support_factors_ppm != (FACTOR_SCALE,)
    ):
        mismatch_category = "MODIFIER_MISMATCH"
    else:
        mismatch_category = "LEGACY_SEMANTIC_DIFFERENCE"

    return XPShadowComparison(
        source_type=source_type,
        source_id=source_id,
        source_marker=source_marker,
        event_identity=event_identity,
        idempotency_key=idempotency_key,
        legacy_xp=legacy_xp,
        shadow_xp=calculation.final_xp,
        difference=difference,
        mismatch_category=mismatch_category,
        premium_eligibility=premium_eligibility,
        legacy_premium_already_applied=bool(legacy_premium_already_applied),
        base_xp=calculation.base_xp,
        additive_learning_xp=calculation.additive_learning_xp,
        combo_factor_ppm=calculation.combo_factor_ppm,
        support_factor_ppm=calculation.support_factor_ppm,
        support_factors_ppm=calculation.support_factors_ppm,
        premium_factor_ppm=calculation.premium_factor_ppm,
        numerator=calculation.numerator,
        denominator=calculation.denominator,
    )


def xp_shadow_error_evidence(
    *,
    source_type: str,
    source_id: str,
    source_marker: str,
    event_identity: str,
    error: BaseException,
) -> dict[str, Any]:
    """Return bounded failure evidence without serializing exception payloads."""

    return {
        "schema_version": "xp-shadow-v1",
        "source_type": str(source_type)[:64],
        "source_id": str(source_id)[:255],
        "source_marker": str(source_marker)[:255],
        "event_identity": str(event_identity)[:255],
        "mismatch_category": "ERROR_FAIL_CLOSED",
        "error_class": type(error).__name__,
        "side_effect_free": True,
        "ledger_inserted": False,
        "idempotency_consumed": False,
    }


def calculate_xp(
    base_xp: int,
    additive_learning_bonuses: Iterable[int] = (),
    *,
    combo_factor_ppm: int = FACTOR_SCALE,
    support_factor_ppm: int = FACTOR_SCALE,
    support_factors_ppm: Iterable[int] = (),
    premium_factor_ppm: int = FACTOR_SCALE,
) -> XPCalculation:
    """Calculate review-stage XP using the locked R1A modifier order.

    BASE_XP -> additive learning bonuses -> combo -> support -> Premium ->
    one final ROUND_HALF_UP.  Each factor is represented as integer PPM and
    no intermediate stage is rounded.
    """

    base_xp = _require_nonnegative_int(base_xp, "base_xp")
    bonuses = tuple(
        _require_nonnegative_int(value, "additive_learning_bonus")
        for value in additive_learning_bonuses
    )
    combo_factor_ppm = _require_factor_ppm(combo_factor_ppm, "combo_factor_ppm")
    support_factor_ppm = _require_factor_ppm(support_factor_ppm, "support_factor_ppm")
    supplied_support_factors = tuple(support_factors_ppm)
    if supplied_support_factors and support_factor_ppm != FACTOR_SCALE:
        raise ValueError("support_factor_ppm cannot be combined with support_factors_ppm")
    if supplied_support_factors:
        support_factors = tuple(
            _require_factor_ppm(value, f"support_factors_ppm[{index}]")
            for index, value in enumerate(supplied_support_factors)
        )
    else:
        support_factors = (support_factor_ppm,)
    premium_factor_ppm = _require_factor_ppm(premium_factor_ppm, "premium_factor_ppm")

    amount = base_xp + sum(bonuses)
    factors = (combo_factor_ppm, *support_factors, premium_factor_ppm)
    numerator = amount
    denominator = 1
    for factor in factors:
        numerator *= factor
        denominator *= FACTOR_SCALE
    final_xp = round_half_up_fraction(numerator, denominator)
    return XPCalculation(
        base_xp=base_xp,
        additive_learning_xp=sum(bonuses),
        combo_factor_ppm=combo_factor_ppm,
        support_factor_ppm=support_factors[0],
        support_factors_ppm=support_factors,
        premium_factor_ppm=premium_factor_ppm,
        numerator=numerator,
        denominator=denominator,
        final_xp=final_xp,
    )


def _validate_key(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    max_length = _MAX_KEY_LENGTHS[field_name]
    if len(value) > max_length:
        raise ValueError(f"{field_name} exceeds {max_length} characters")
    if not _CANONICAL_SAFE_RE.fullmatch(value):
        raise ValueError(f"{field_name} is not canonical ASCII-safe encoding")
    return value


@dataclass(frozen=True)
class SettlementRequest:
    """Validated input envelope for future XPSettlement callers.

    No current production writer constructs this envelope in R1A.  The
    explicit fields prevent future callers from silently adding a second
    Premium or rounding policy.
    """

    user_id: int
    source_type: str
    source_id: str
    idempotency_key: str
    base_xp: int = 0
    additive_learning_bonuses: tuple[int, ...] = ()
    combo_factor_ppm: int = FACTOR_SCALE
    support_factor_ppm: int = FACTOR_SCALE
    premium_eligibility: str = "PREMIUM_INELIGIBLE"
    already_premium_adjusted: bool = False
    settlement_kind: str = "NORMAL_GRANT"
    source_version: str = "v1"
    grant_policy_version: str = "r1a-v1"
    curve_version: str = "phase4b-v1"
    rounding_policy_version: str = ROUNDING_POLICY_VERSION
    source_context: Optional[str] = None
    request_correlation_id: Optional[str] = None
    actor_type: str = "SYSTEM"
    actor_id: Optional[int] = None
    reason_or_ticket: Optional[str] = None
    admin_xp_delta: Optional[int] = None
    opening_xp: Optional[int] = None
    modifier_payload: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        _require_int(self.user_id, "user_id")
        if self.user_id <= 0:
            raise ValueError("user_id must be positive")
        _validate_key(self.source_type, "source_type")
        _validate_key(self.source_id, "source_id")
        _validate_key(self.source_version, "source_version")
        _validate_key(self.idempotency_key, "idempotency_key")
        if self.request_correlation_id is not None:
            _validate_key(self.request_correlation_id, "request_correlation_id")
        _require_nonnegative_int(self.base_xp, "base_xp")
        for value in self.additive_learning_bonuses:
            _require_nonnegative_int(value, "additive_learning_bonus")
        _require_factor_ppm(self.combo_factor_ppm, "combo_factor_ppm")
        _require_factor_ppm(self.support_factor_ppm, "support_factor_ppm")
        if self.premium_eligibility not in {
            "PREMIUM_ELIGIBLE",
            "PREMIUM_INELIGIBLE",
            "ALREADY_PREMIUM_ADJUSTED",
        }:
            raise ValueError("invalid premium_eligibility")
        if self.premium_eligibility == "PREMIUM_ELIGIBLE":
            if self.already_premium_adjusted:
                raise ValueError("Premium-eligible source cannot be already adjusted")
            premium_factor = PREMIUM_18_FACTOR_PPM
        else:
            premium_factor = NO_PREMIUM_FACTOR_PPM
        if self.settlement_kind not in {
            "NORMAL_GRANT",
            "ADMIN_ADJUSTMENT",
            "OPENING_BALANCE",
        }:
            raise ValueError("invalid settlement_kind")
        if self.settlement_kind == "NORMAL_GRANT":
            if self.actor_type not in {"PLAYER", "SYSTEM"}:
                raise ValueError("normal grants require PLAYER or SYSTEM actor")
            if self.actor_id is not None:
                raise ValueError("normal grants do not accept actor_id")
        elif self.settlement_kind == "ADMIN_ADJUSTMENT":
            if self.actor_type != "ADMIN" or self.actor_id is None:
                raise ValueError("admin adjustments require an ADMIN actor")
            if not self.reason_or_ticket:
                raise ValueError("admin adjustments require reason_or_ticket")
            if self.premium_eligibility != "PREMIUM_INELIGIBLE":
                raise ValueError("admin adjustments are Premium-ineligible")
            if self.admin_xp_delta is None:
                raise ValueError("admin adjustments require signed admin_xp_delta")
            _require_int(self.admin_xp_delta, "admin_xp_delta")
        else:
            if self.actor_type != "MIGRATION" or self.actor_id is not None:
                raise ValueError("opening balances require MIGRATION without actor_id")
            if not self.reason_or_ticket:
                raise ValueError("opening balances require reason_or_ticket")
            if self.opening_xp is None:
                raise ValueError("opening balances require opening_xp")
            _require_nonnegative_int(self.opening_xp, "opening_xp")
            if self.base_xp != 0 or self.additive_learning_bonuses:
                raise ValueError("opening balances do not contain earned XP")
            if self.premium_eligibility != "PREMIUM_INELIGIBLE":
                raise ValueError("opening balances are Premium-ineligible")
        if self.already_premium_adjusted:
            premium_factor = NO_PREMIUM_FACTOR_PPM
        if self.premium_eligibility == "PREMIUM_ELIGIBLE":
            expected = PREMIUM_18_FACTOR_PPM
        else:
            expected = NO_PREMIUM_FACTOR_PPM
        if premium_factor != expected:
            raise ValueError("invalid Premium factor state")


@dataclass(frozen=True)
class SettlementResult:
    settlement_id: int
    duplicate: bool
    before_xp: int
    xp_delta: int
    after_xp: int


class XPSettlementDisabled(RuntimeError):
    """Raised when a future writer attempts to use the default-off foundation."""


class XPSettlementConflict(RuntimeError):
    """Raised when one idempotency key is replayed with a different source."""


class XPSettlementConfigurationError(RuntimeError):
    """Raised when a caller omits the deterministic rank-cache derivation."""


class XPSettlement:
    """Minimal server-side settlement foundation for future writer cutovers.

    The caller supplies a connection already inside the application's
    transaction context.  This class never commits or opens a second
    connection, so a future source marker can share the same transaction.
    R1A has no normal caller and leaves the feature flag OFF.
    """

    def __init__(
        self,
        conn: Any,
        *,
        enabled: Optional[bool] = None,
        rank_cache_deriver: Optional[Callable[[int], tuple[str, int]]] = None,
    ) -> None:
        self.conn = conn
        self.enabled = xp_settlement_enabled() if enabled is None else bool(enabled)
        self.rank_cache_deriver = rank_cache_deriver

    def settle(self, request: SettlementRequest) -> SettlementResult:
        if not self.enabled:
            raise XPSettlementDisabled("XP settlement foundation is disabled")
        request.validate()
        if request.settlement_kind != "OPENING_BALANCE" and self.rank_cache_deriver is None:
            raise XPSettlementConfigurationError(
                "rank_cache_deriver is required for XP mutation"
            )

        self.conn.execute(
            "INSERT INTO user_stats(user_id) VALUES(?) ON CONFLICT(user_id) DO NOTHING",
            (request.user_id,),
        )
        user_row = self.conn.execute(
            "SELECT xp FROM user_stats WHERE user_id=? FOR UPDATE",
            (request.user_id,),
        ).fetchone()
        if not user_row:
            raise ValueError("target user_stats row does not exist")
        before_xp = int(user_row["xp"] or 0)

        existing = self.conn.execute(
            "SELECT settlement_id, source_type, source_id, source_version, "
            "settlement_kind, before_xp, xp_delta, after_xp "
            "FROM xp_settlement_ledger "
            "WHERE user_id=? AND idempotency_key=?",
            (request.user_id, request.idempotency_key),
        ).fetchone()
        if existing:
            self._ensure_same_source(existing, request)
            return SettlementResult(
                settlement_id=int(existing["settlement_id"]),
                duplicate=True,
                before_xp=int(existing["before_xp"]),
                xp_delta=int(existing["xp_delta"]),
                after_xp=int(existing["after_xp"]),
            )

        premium_factor_ppm = (
            PREMIUM_18_FACTOR_PPM
            if request.premium_eligibility == "PREMIUM_ELIGIBLE"
            else NO_PREMIUM_FACTOR_PPM
        )
        if request.already_premium_adjusted:
            premium_factor_ppm = NO_PREMIUM_FACTOR_PPM

        if request.settlement_kind == "NORMAL_GRANT":
            calculation = calculate_xp(
                request.base_xp,
                request.additive_learning_bonuses,
                combo_factor_ppm=request.combo_factor_ppm,
                support_factor_ppm=request.support_factor_ppm,
                premium_factor_ppm=premium_factor_ppm,
            )
            xp_delta = calculation.final_xp
            payload = dict(request.modifier_payload)
            payload.update(calculation.modifier_payload)
        elif request.settlement_kind == "ADMIN_ADJUSTMENT":
            xp_delta = int(request.admin_xp_delta)
            payload = dict(request.modifier_payload)
        else:
            if before_xp != int(request.opening_xp):
                raise XPSettlementConflict(
                    "opening balance does not match locked current user_stats.xp"
                )
            xp_delta = 0
            payload = dict(request.modifier_payload)

        # Validate provenance before handing it to psycopg2's JSON adapter;
        # modifier factors must remain canonical integer PPM values.
        canonical_modifier_payload(payload)

        after_xp = before_xp + xp_delta
        if after_xp < 0:
            raise ValueError("settlement would reduce XP below zero")
        if request.settlement_kind == "OPENING_BALANCE":
            after_xp = before_xp

        row_values = (
            request.user_id,
            request.source_type,
            request.source_id,
            request.source_version,
            request.settlement_kind,
            request.base_xp,
            xp_delta,
            Json(payload),
            request.premium_eligibility,
            request.already_premium_adjusted,
            premium_factor_ppm,
            before_xp,
            after_xp,
            request.idempotency_key,
            SETTLEMENT_STATUS_SETTLED,
            request.grant_policy_version,
            request.curve_version,
            request.rounding_policy_version,
            request.source_context,
            request.request_correlation_id,
            request.actor_type,
            request.actor_id,
            request.reason_or_ticket,
        )
        self.conn.execute("SAVEPOINT xp_settlement_insert")
        try:
            inserted = self.conn.execute(
                """INSERT INTO xp_settlement_ledger (
                    user_id, source_type, source_id, source_version,
                    settlement_kind, base_xp, xp_delta, modifier_payload,
                    premium_eligibility, already_premium_adjusted,
                    premium_factor_ppm, before_xp, after_xp, idempotency_key,
                    settlement_status, grant_policy_version, curve_version,
                    rounding_policy_version, source_context,
                    request_correlation_id, actor_type, actor_id,
                    reason_or_ticket
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                RETURNING settlement_id""",
                row_values,
            ).fetchone()
        except IntegrityError:
            self.conn.execute("ROLLBACK TO SAVEPOINT xp_settlement_insert")
            existing = self.conn.execute(
                "SELECT settlement_id, source_type, source_id, source_version, "
                "settlement_kind, before_xp, xp_delta, after_xp "
                "FROM xp_settlement_ledger "
                "WHERE user_id=? AND idempotency_key=?",
                (request.user_id, request.idempotency_key),
            ).fetchone()
            if not existing:
                raise
            self._ensure_same_source(existing, request)
            return SettlementResult(
                settlement_id=int(existing["settlement_id"]),
                duplicate=True,
                before_xp=int(existing["before_xp"]),
                xp_delta=int(existing["xp_delta"]),
                after_xp=int(existing["after_xp"]),
            )
        finally:
            self.conn.execute("RELEASE SAVEPOINT xp_settlement_insert")

        if not inserted:
            raise RuntimeError("XP settlement insert did not return settlement_id")
        settlement_id = int(inserted["settlement_id"])

        if request.settlement_kind != "OPENING_BALANCE":
            rank_level, rank_xp = self.rank_cache_deriver(after_xp)
            self.conn.execute(
                "UPDATE user_stats SET xp=?, rank_level=?, rank_xp=? WHERE user_id=?",
                (after_xp, rank_level, rank_xp, request.user_id),
            )

        return SettlementResult(
            settlement_id=settlement_id,
            duplicate=False,
            before_xp=before_xp,
            xp_delta=xp_delta,
            after_xp=after_xp,
        )

    @staticmethod
    def _ensure_same_source(existing: Mapping[str, Any], request: SettlementRequest) -> None:
        fields = {
            "source_type": request.source_type,
            "source_id": request.source_id,
            "source_version": request.source_version,
            "settlement_kind": request.settlement_kind,
        }
        for field_name, expected in fields.items():
            if existing[field_name] != expected:
                raise XPSettlementConflict(
                    f"idempotency key conflicts on {field_name}"
                )


LEDGER_COLUMNS = {
    "settlement_id": ("bigint", None, "NO"),
    "user_id": ("integer", None, "NO"),
    "source_type": ("character varying", 64, "NO"),
    "source_id": ("character varying", 255, "NO"),
    "source_version": ("character varying", 32, "NO"),
    "settlement_kind": ("character varying", 32, "NO"),
    "base_xp": ("bigint", None, "NO"),
    "xp_delta": ("bigint", None, "NO"),
    "modifier_payload": ("jsonb", None, "NO"),
    "premium_eligibility": ("character varying", 32, "NO"),
    "already_premium_adjusted": ("boolean", None, "NO"),
    "premium_factor_ppm": ("bigint", None, "NO"),
    "before_xp": ("bigint", None, "NO"),
    "after_xp": ("bigint", None, "NO"),
    "idempotency_key": ("character varying", 255, "NO"),
    "settlement_status": ("character varying", 16, "NO"),
    "grant_policy_version": ("character varying", 64, "NO"),
    "curve_version": ("character varying", 64, "NO"),
    "rounding_policy_version": ("character varying", 64, "NO"),
    "source_context": ("character varying", 255, "YES"),
    "request_correlation_id": ("character varying", 255, "YES"),
    "actor_type": ("character varying", 16, "NO"),
    "actor_id": ("integer", None, "YES"),
    "reason_or_ticket": ("character varying", 255, "YES"),
    "error_code": ("character varying", 64, "YES"),
    "created_at": ("timestamp with time zone", None, "NO"),
    "settled_at": ("timestamp with time zone", None, "NO"),
}

LEDGER_CONSTRAINT_NAMES = {
    "xp_settlement_after_xp_check",
    "xp_settlement_nonnegative_total_check",
    "xp_settlement_base_xp_check",
    "xp_settlement_kind_check",
    "xp_settlement_status_v1_check",
    "xp_settlement_premium_state_check",
    "xp_settlement_premium_factor_check",
    "xp_settlement_normal_amount_check",
    "xp_settlement_normal_actor_check",
    "xp_settlement_opening_balance_check",
    "xp_settlement_admin_provenance_check",
    "xp_settlement_actor_type_check",
    "xp_settlement_actor_shape_check",
    "xp_settlement_key_chars_check",
    "xp_settlement_idempotency_unique",
}

LEDGER_INDEXES = {
    "idx_xp_settlement_user_created":
        "CREATE INDEX IF NOT EXISTS idx_xp_settlement_user_created "
        "ON xp_settlement_ledger (user_id, created_at DESC)",
    "idx_xp_settlement_source":
        "CREATE INDEX IF NOT EXISTS idx_xp_settlement_source "
        "ON xp_settlement_ledger (source_type, source_id)",
    "idx_xp_settlement_kind_created":
        "CREATE INDEX IF NOT EXISTS idx_xp_settlement_kind_created "
        "ON xp_settlement_ledger (settlement_kind, created_at DESC)",
    "idx_xp_settlement_correlation":
        "CREATE INDEX IF NOT EXISTS idx_xp_settlement_correlation "
        "ON xp_settlement_ledger (request_correlation_id)",
}

LEDGER_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS xp_settlement_ledger (
    settlement_id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    source_type VARCHAR(64) NOT NULL,
    source_id VARCHAR(255) NOT NULL,
    source_version VARCHAR(32) NOT NULL,
    settlement_kind VARCHAR(32) NOT NULL,
    base_xp BIGINT NOT NULL DEFAULT 0,
    xp_delta BIGINT NOT NULL DEFAULT 0,
    modifier_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    premium_eligibility VARCHAR(32) NOT NULL,
    already_premium_adjusted BOOLEAN NOT NULL DEFAULT FALSE,
    premium_factor_ppm BIGINT NOT NULL DEFAULT 1000000,
    before_xp BIGINT NOT NULL,
    after_xp BIGINT NOT NULL,
    idempotency_key VARCHAR(255) NOT NULL,
    settlement_status VARCHAR(16) NOT NULL DEFAULT 'SETTLED',
    grant_policy_version VARCHAR(64) NOT NULL,
    curve_version VARCHAR(64) NOT NULL,
    rounding_policy_version VARCHAR(64) NOT NULL,
    source_context VARCHAR(255),
    request_correlation_id VARCHAR(255),
    actor_type VARCHAR(16) NOT NULL,
    actor_id INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    reason_or_ticket VARCHAR(255),
    error_code VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    settled_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT xp_settlement_after_xp_check
        CHECK (after_xp = before_xp + xp_delta),
    CONSTRAINT xp_settlement_nonnegative_total_check
        CHECK (before_xp >= 0 AND after_xp >= 0),
    CONSTRAINT xp_settlement_base_xp_check
        CHECK (base_xp >= 0),
    CONSTRAINT xp_settlement_kind_check
        CHECK (settlement_kind IN
            ('NORMAL_GRANT', 'ADMIN_ADJUSTMENT', 'OPENING_BALANCE')),
    CONSTRAINT xp_settlement_status_v1_check
        CHECK (settlement_status = 'SETTLED'),
    CONSTRAINT xp_settlement_premium_state_check
        CHECK (premium_eligibility IN
            ('PREMIUM_ELIGIBLE', 'PREMIUM_INELIGIBLE',
             'ALREADY_PREMIUM_ADJUSTED')),
    CONSTRAINT xp_settlement_premium_factor_check
        CHECK (
            (premium_eligibility = 'PREMIUM_ELIGIBLE'
             AND already_premium_adjusted = FALSE
             AND premium_factor_ppm = 1180000)
            OR
            (premium_eligibility IN
                ('PREMIUM_INELIGIBLE', 'ALREADY_PREMIUM_ADJUSTED')
             AND premium_factor_ppm = 1000000)
        ),
    CONSTRAINT xp_settlement_normal_amount_check
        CHECK (settlement_kind <> 'NORMAL_GRANT' OR xp_delta >= 0),
    CONSTRAINT xp_settlement_normal_actor_check
        CHECK (settlement_kind <> 'NORMAL_GRANT'
               OR actor_type IN ('PLAYER', 'SYSTEM')),
    CONSTRAINT xp_settlement_opening_balance_check
        CHECK (
            settlement_kind <> 'OPENING_BALANCE'
            OR (
                base_xp = 0 AND xp_delta = 0 AND before_xp = after_xp
                AND actor_type = 'MIGRATION' AND actor_id IS NULL
                AND reason_or_ticket IS NOT NULL
                AND premium_eligibility = 'PREMIUM_INELIGIBLE'
                AND already_premium_adjusted = FALSE
                AND premium_factor_ppm = 1000000
            )
        ),
    CONSTRAINT xp_settlement_admin_provenance_check
        CHECK (
            settlement_kind <> 'ADMIN_ADJUSTMENT'
            OR (
                actor_type = 'ADMIN' AND actor_id IS NOT NULL
                AND reason_or_ticket IS NOT NULL
                AND premium_eligibility = 'PREMIUM_INELIGIBLE'
                AND already_premium_adjusted = FALSE
                AND premium_factor_ppm = 1000000
            )
        ),
    CONSTRAINT xp_settlement_actor_type_check
        CHECK (actor_type IN ('PLAYER', 'SYSTEM', 'ADMIN', 'MIGRATION')),
    CONSTRAINT xp_settlement_actor_shape_check
        CHECK (
            (actor_type = 'ADMIN' AND actor_id IS NOT NULL)
            OR
            (actor_type IN ('PLAYER', 'SYSTEM', 'MIGRATION')
             AND actor_id IS NULL)
        ),
    CONSTRAINT xp_settlement_key_chars_check
        CHECK (
            idempotency_key ~ '^[A-Za-z0-9][A-Za-z0-9_._:-]*$'
            AND source_type ~ '^[A-Za-z0-9][A-Za-z0-9_._:-]*$'
            AND source_id ~ '^[A-Za-z0-9][A-Za-z0-9_._:-]*$'
            AND source_version ~ '^[A-Za-z0-9][A-Za-z0-9_._:-]*$'
        ),
    CONSTRAINT xp_settlement_idempotency_unique
        UNIQUE (user_id, idempotency_key)
)
"""


def _row_value(row: Any, key: str) -> Any:
    if isinstance(row, Mapping):
        return row[key]
    return row[key]


def _validate_existing_schema(conn: Any) -> None:
    rows = conn.execute(
        """SELECT column_name, data_type, character_maximum_length, is_nullable
           FROM information_schema.columns
          WHERE table_schema = current_schema() AND table_name = %s""",
        (LEDGER_TABLE_NAME,),
    ).fetchall()
    actual = {
        _row_value(row, "column_name"): (
            _row_value(row, "data_type"),
            _row_value(row, "character_maximum_length"),
            _row_value(row, "is_nullable"),
        )
        for row in rows
    }
    missing = set(LEDGER_COLUMNS) - set(actual)
    if missing:
        raise RuntimeError(
            f"incompatible {LEDGER_TABLE_NAME}: missing columns {sorted(missing)}"
        )
    for column, expected in LEDGER_COLUMNS.items():
        if actual[column] != expected:
            raise RuntimeError(
                f"incompatible {LEDGER_TABLE_NAME}.{column}: "
                f"expected {expected!r}, got {actual[column]!r}"
            )

    constraints = conn.execute(
        """SELECT conname, contype, pg_get_constraintdef(oid) AS definition
             FROM pg_constraint
            WHERE conrelid = %s::regclass""",
        (LEDGER_TABLE_NAME,),
    ).fetchall()
    constraint_map = {
        _row_value(row, "conname"): (
            _row_value(row, "contype"),
            str(_row_value(row, "definition")).lower(),
        )
        for row in constraints
    }
    missing_constraints = LEDGER_CONSTRAINT_NAMES - set(constraint_map)
    if missing_constraints:
        raise RuntimeError(
            f"incompatible {LEDGER_TABLE_NAME}: missing constraints "
            f"{sorted(missing_constraints)}"
        )
    if constraint_map["xp_settlement_idempotency_unique"][0] != "u":
        raise RuntimeError("xp_settlement_idempotency_unique is not UNIQUE")
    foreign_definitions = [
        definition
        for contype, definition in constraint_map.values()
        if contype == "f"
    ]
    if not any("foreign key (user_id) references users(id)" in value for value in foreign_definitions):
        raise RuntimeError("xp_settlement_ledger.user_id foreign key is incompatible")
    if not any("foreign key (actor_id) references users(id)" in value for value in foreign_definitions):
        raise RuntimeError("xp_settlement_ledger.actor_id foreign key is incompatible")


def ensure_xp_settlement_schema(conn: Any) -> None:
    """Create/validate the additive R1A schema; never silently repair drift."""

    conn.execute(LEDGER_SCHEMA_SQL)
    _validate_existing_schema(conn)
    for statement in LEDGER_INDEXES.values():
        conn.execute(statement)


def canonical_modifier_payload(payload: Mapping[str, Any]) -> str:
    """Serialize modifier provenance without float ambiguity."""

    def reject_float(value: Any) -> None:
        if isinstance(value, float):
            raise TypeError("modifier_payload cannot contain floating-point values")
        if isinstance(value, Mapping):
            for nested in value.values():
                reject_float(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                reject_float(nested)

    reject_float(payload)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


__all__ = [
    "FACTOR_SCALE",
    "NO_PREMIUM_FACTOR_PPM",
    "PREMIUM_18_FACTOR_PPM",
    "ROUNDING_POLICY_VERSION",
    "MAX_RETRY_VALUE",
    "LOCK_TIMEOUT_VALUE",
    "LEDGER_SCHEMA_SQL",
    "LEDGER_COLUMNS",
    "LEDGER_CONSTRAINT_NAMES",
    "LEDGER_INDEXES",
    "SHADOW_MISMATCH_CATEGORIES",
    "xp_ledger_schema_enabled",
    "xp_settlement_enabled",
    "xp_shadow_enabled",
    "round_half_up_fraction",
    "multiply_factors_final_round",
    "factor_value_to_ppm",
    "calculate_xp",
    "compare_xp_shadow",
    "xp_shadow_error_evidence",
    "canonical_modifier_payload",
    "SettlementRequest",
    "SettlementResult",
    "XPCalculation",
    "XPShadowComparison",
    "XPSettlement",
    "XPSettlementDisabled",
    "XPSettlementConflict",
    "XPSettlementConfigurationError",
    "ensure_xp_settlement_schema",
]
