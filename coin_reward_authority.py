"""ACT-C canonical Coin reward and settlement authority.

This module owns the Coin mutation contract for the Activation paths that are
being cut over by ACT-A.  It deliberately does not import :mod:`app`, does
not open or close database connections, and never commits or rolls back the
caller transaction.

``user_stats.coins`` remains the live balance authority and ``currency_log``
remains the append-only Coin ledger.  A normal grant locks the player's
``user_stats`` row before reading today's positive ordinary-gameplay ledger
total.  Friend Challenge rows remain auditable in ``currency_log`` but are
excluded from that ordinary-cap total by their explicit reason prefix.
PostgreSQL uses ``SELECT ... FOR UPDATE``; SQLite takes the equivalent write
lock with a no-op update.  The cap decision, balance update, and ledger insert
therefore share one caller-owned transaction.

Friend Challenge settlement has a separate claim table because the legacy
``friend_challenges`` and ``friend_challenge_answers`` rows cannot distinguish
"settled but response lost" from "not settled" for one player.  The claim
table stores only settlement state and timestamps; it intentionally stores no
random reward payload.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Any


DAILY_COIN_CAP = 500

CAP_POLICY_NORMAL = "NORMAL_DAILY_CAP"
CAP_POLICY_EXEMPT_FRIEND_CHALLENGE = "EXEMPT_FRIEND_CHALLENGE"
CAP_POLICIES = frozenset(
    {
        CAP_POLICY_NORMAL,
        CAP_POLICY_EXEMPT_FRIEND_CHALLENGE,
    }
)

FRIEND_CHALLENGE_CURRENCY_REASON_PREFIX = "friend_challenge_reward"
REWARDS_SYNC_CURRENCY_REASON_PREFIX = "rewards_sync"

FRIEND_CHALLENGE_SETTLED = "SETTLED"
FRIEND_CHALLENGE_ALREADY_SETTLED = "ALREADY_SETTLED"
FRIEND_CHALLENGE_SETTLED_NO_DETAIL = "SETTLED_NO_DETAIL"
FRIEND_CHALLENGE_SETTLEMENT_IN_PROGRESS = "SETTLEMENT_IN_PROGRESS"

REWARDS_SYNC_GRANTED = "GRANTED"
REWARDS_SYNC_ALREADY_CLAIMED = "ALREADY_CLAIMED"

_REASON_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


class CoinRewardError(RuntimeError):
    """Base class for fail-closed Coin reward errors."""

    code = "COIN_REWARD_FAILED"


class CoinRewardValidationError(CoinRewardError):
    code = "COIN_REWARD_INPUT_INVALID"


class CoinRewardSchemaUnavailable(CoinRewardError):
    code = "COIN_REWARD_SCHEMA_UNAVAILABLE"


class FriendChallengeSettlementInProgress(CoinRewardError):
    code = FRIEND_CHALLENGE_SETTLEMENT_IN_PROGRESS


@dataclass(frozen=True)
class CoinGrantResult:
    """The authoritative result of one in-transaction Coin grant."""

    user_id: int
    requested_amount: int
    granted_amount: int
    coins_before: int
    coins_after: int
    daily_earned_before: int
    daily_earned_after: int
    cap_policy: str
    reason: str
    created_at: Any

    @property
    def capped(self) -> bool:
        return self.granted_amount < self.requested_amount

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "requested_amount": self.requested_amount,
            "granted_amount": self.granted_amount,
            "coins_before": self.coins_before,
            "coins_after": self.coins_after,
            "daily_earned_before": self.daily_earned_before,
            "daily_earned_after": self.daily_earned_after,
            "cap_policy": self.cap_policy,
            "reason": self.reason,
            "created_at": self.created_at,
            "capped": self.capped,
        }


@dataclass(frozen=True)
class RewardsSyncSettlementResult:
    """Idempotent result for one existing ``reward_claimed`` stage key."""

    status: str
    user_id: int
    stage_key: str
    requested_coins: int
    granted_coins: int
    xp: int
    claim_created: bool
    coin_grant: CoinGrantResult | None = None

    @property
    def duplicate(self) -> bool:
        return not self.claim_created

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "user_id": self.user_id,
            "stage_key": self.stage_key,
            "requested_coins": self.requested_coins,
            "granted_coins": self.granted_coins,
            "xp": self.xp,
            "claim_created": self.claim_created,
            "duplicate": self.duplicate,
            "coin_grant": self.coin_grant.as_dict() if self.coin_grant else None,
        }


@dataclass(frozen=True)
class FriendChallengeSettlementResult:
    """Settlement result with explicit response-loss retry semantics.

    A newly settled call returns ``status=SETTLED`` and may carry the
    non-persistent first-response detail produced by the caller callback.  A
    retry after a committed settlement returns ``status=ALREADY_SETTLED`` and
    ``detail_status=SETTLED_NO_DETAIL``; no random reward payload is replayed.
    """

    status: str
    detail_status: str | None
    challenge_id: int
    user_id: int
    granted_coins: int | None
    claim_created: bool
    coin_grant: CoinGrantResult | None = None
    first_response_detail: Mapping[str, Any] | None = None

    @property
    def duplicate(self) -> bool:
        return not self.claim_created

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "detail_status": self.detail_status,
            "challenge_id": self.challenge_id,
            "user_id": self.user_id,
            "granted_coins": self.granted_coins,
            "claim_created": self.claim_created,
            "duplicate": self.duplicate,
            "coin_grant": self.coin_grant.as_dict() if self.coin_grant else None,
            # This is intentionally an in-memory first response only.  The
            # claim table never receives this mapping.
            "first_response_detail": (
                dict(self.first_response_detail)
                if self.first_response_detail is not None
                else None
            ),
        }


def _raw(conn: Any) -> Any:
    return getattr(conn, "_conn", conn)


def _is_sqlite(conn: Any) -> bool:
    return _raw(conn).__class__.__module__.lower().startswith("sqlite3")


def _execute(conn: Any, statement: str, params: Iterable[Any] = ()) -> Any:
    values = tuple(params)
    if hasattr(conn, "execute"):
        return conn.execute(statement, values)
    cursor = conn.cursor()
    cursor.execute(statement.replace("?", "%s"), values)
    return cursor


def _fetchone(conn: Any, statement: str, params: Iterable[Any] = ()) -> Any:
    cursor = _execute(conn, statement, params)
    try:
        return cursor.fetchone()
    finally:
        if not hasattr(conn, "execute"):
            cursor.close()


def _row_value(row: Any, index: int, key: str) -> Any:
    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _for_update(conn: Any) -> str:
    return "" if _is_sqlite(conn) else " FOR UPDATE"


def _is_missing_schema_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(
        marker in text
        for marker in (
            "no such table",
            "no such column",
            "does not exist",
            "undefined table",
            "undefined column",
            "relation ",
            "column ",
        )
    )


def _schema_error(message: str) -> CoinRewardSchemaUnavailable:
    return CoinRewardSchemaUnavailable(message)


def _normalize_user_id(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CoinRewardValidationError("user_id must be a positive authenticated integer")
    return value


def _normalize_positive_id(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CoinRewardValidationError(f"{name} must be a positive integer")
    return value


def _normalize_nonnegative_amount(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CoinRewardValidationError(f"{name} must be a non-negative integer")
    return value


def _normalize_stage_key(value: Any) -> str:
    if not isinstance(value, str):
        raise CoinRewardValidationError("stage_key must be text")
    normalized = value.strip()
    if not normalized or len(normalized) > 160:
        raise CoinRewardValidationError("stage_key must be non-empty text of at most 160 characters")
    return normalized


def _normalize_reason(value: Any) -> str:
    if not isinstance(value, str):
        raise CoinRewardValidationError("reason must be server-owned text")
    normalized = value.strip()
    if not normalized or len(normalized) > 240 or _REASON_CONTROL_RE.search(normalized):
        raise CoinRewardValidationError("reason must be safe server-owned text")
    return normalized


def _normalize_cap_policy(value: Any) -> str:
    if value not in CAP_POLICIES:
        raise CoinRewardValidationError(f"unsupported Coin cap policy: {value!r}")
    return str(value)


def _timestamp_and_day(value: datetime | date | None) -> tuple[Any, str]:
    if value is None:
        current = datetime.now()
    elif isinstance(value, datetime):
        current = value
    elif isinstance(value, date):
        current = datetime.combine(value, datetime.min.time())
    else:
        raise CoinRewardValidationError("timestamp must be a date or datetime")
    return current.isoformat(timespec="seconds"), current.date().isoformat()


def _json_mapping(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise CoinRewardError("non-coin reward callback must return a mapping")
    return dict(value)


def _ensure_and_lock_user_stats(conn: Any, user_id: int) -> int:
    """Ensure the balance row exists and serialize the cap decision.

    PostgreSQL's row lock is explicit.  SQLite has no row-level ``FOR
    UPDATE``; the no-op update starts/acquires the connection's write lock
    before the ledger total is read.  Neither branch commits or rolls back.
    """

    try:
        _execute(
            conn,
            "INSERT INTO user_stats(user_id) VALUES(?) "
            "ON CONFLICT(user_id) DO NOTHING",
            (user_id,),
        )
        if _is_sqlite(conn):
            _execute(
                conn,
                "UPDATE user_stats SET coins=COALESCE(coins,0) WHERE user_id=?",
                (user_id,),
            )
            row = _fetchone(
                conn,
                "SELECT coins FROM user_stats WHERE user_id=?",
                (user_id,),
            )
        else:
            row = _fetchone(
                conn,
                "SELECT coins FROM user_stats WHERE user_id=? FOR UPDATE",
                (user_id,),
            )
    except Exception as exc:
        if _is_missing_schema_error(exc):
            raise _schema_error("user_stats.coins authority is unavailable") from exc
        raise
    if row is None:
        raise CoinRewardSchemaUnavailable("authenticated user_stats row is unavailable")
    try:
        return int(_row_value(row, 0, "coins") or 0)
    except (TypeError, ValueError, KeyError, IndexError) as exc:
        raise CoinRewardSchemaUnavailable("user_stats.coins is not readable") from exc


def _positive_ledger_total_today(conn: Any, *, user_id: int, day_start: str) -> int:
    """Return positive ordinary-cap usage, excluding logged FC exemptions."""

    try:
        row = _fetchone(
            conn,
            "SELECT COALESCE(SUM(delta),0) AS earned FROM currency_log "
            "WHERE user_id=? AND delta>0 AND created_at>=? "
            "AND reason NOT LIKE ?",
            (
                user_id,
                day_start,
                f"{FRIEND_CHALLENGE_CURRENCY_REASON_PREFIX}:%",
            ),
        )
    except Exception as exc:
        if _is_missing_schema_error(exc):
            raise _schema_error("currency_log authority is unavailable") from exc
        raise
    try:
        return int(_row_value(row, 0, "earned") or 0)
    except (TypeError, ValueError, KeyError, IndexError) as exc:
        raise CoinRewardSchemaUnavailable("currency_log total is not readable") from exc


def grant_coins_in_transaction(
    conn: Any,
    *,
    user_id: int,
    server_computed_amount: int,
    server_owned_reason: str,
    cap_policy: str = CAP_POLICY_NORMAL,
    now: datetime | date | None = None,
) -> CoinGrantResult:
    """Grant server-computed Coins inside the caller-owned transaction.

    The function accepts no client reward fields.  ``server_computed_amount``
    and ``server_owned_reason`` are explicit names to make the route boundary
    auditable.  A normal grant is capped at :data:`DAILY_COIN_CAP`; the Friend
    Challenge exemption is an explicit policy value and still appends a
    ``currency_log`` row for every positive grant.
    """

    normalized_user_id = _normalize_user_id(user_id)
    amount = _normalize_nonnegative_amount(server_computed_amount, "server_computed_amount")
    reason = _normalize_reason(server_owned_reason)
    policy = _normalize_cap_policy(cap_policy)
    created_at, day_start = _timestamp_and_day(now)

    coins_before = _ensure_and_lock_user_stats(conn, normalized_user_id)
    earned_before = _positive_ledger_total_today(
        conn,
        user_id=normalized_user_id,
        day_start=day_start,
    )
    if policy == CAP_POLICY_NORMAL:
        granted = min(amount, max(0, DAILY_COIN_CAP - earned_before))
    else:
        granted = amount

    if granted == 0:
        return CoinGrantResult(
            user_id=normalized_user_id,
            requested_amount=amount,
            granted_amount=0,
            coins_before=coins_before,
            coins_after=coins_before,
            daily_earned_before=earned_before,
            daily_earned_after=earned_before,
            cap_policy=policy,
            reason=reason,
            created_at=created_at,
        )

    try:
        updated = _execute(
            conn,
            "UPDATE user_stats SET coins=COALESCE(coins,0)+? WHERE user_id=?",
            (granted, normalized_user_id),
        )
    except Exception as exc:
        if _is_missing_schema_error(exc):
            raise _schema_error("user_stats.coins authority is unavailable") from exc
        raise
    if int(getattr(updated, "rowcount", 0) or 0) != 1:
        raise CoinRewardSchemaUnavailable("user_stats.coins update did not affect one user")

    try:
        row = _fetchone(
            conn,
            "SELECT coins FROM user_stats WHERE user_id=?",
            (normalized_user_id,),
        )
        coins_after = int(_row_value(row, 0, "coins") or 0)
        if coins_after != coins_before + granted:
            raise CoinRewardError("user_stats.coins transition was not coherent")
        _execute(
            conn,
            "INSERT INTO currency_log(user_id,delta,balance_after,reason,created_at) "
            "VALUES(?,?,?,?,?)",
            (normalized_user_id, granted, coins_after, reason, created_at),
        )
    except CoinRewardError:
        raise
    except Exception as exc:
        if _is_missing_schema_error(exc):
            raise _schema_error("currency_log authority is unavailable") from exc
        raise

    return CoinGrantResult(
        user_id=normalized_user_id,
        requested_amount=amount,
        granted_amount=granted,
        coins_before=coins_before,
        coins_after=coins_after,
        daily_earned_before=earned_before,
        daily_earned_after=earned_before + granted,
        cap_policy=policy,
        reason=reason,
        created_at=created_at,
    )


def rewards_sync_currency_reason(stage_key: str) -> str:
    """Build the fixed, auditable reason for an existing stage claim."""

    return f"{REWARDS_SYNC_CURRENCY_REASON_PREFIX}:stage:{_normalize_stage_key(stage_key)}"


def friend_challenge_currency_reason(challenge_id: int, user_id: int) -> str:
    """Build the fixed, auditable Friend Challenge ledger reason."""

    normalized_challenge_id = _normalize_positive_id(challenge_id, "challenge_id")
    normalized_user_id = _normalize_user_id(user_id)
    return (
        f"{FRIEND_CHALLENGE_CURRENCY_REASON_PREFIX}:challenge:"
        f"{normalized_challenge_id}:user:{normalized_user_id}"
    )


def _reserve_rewards_sync_claim(
    conn: Any,
    *,
    user_id: int,
    stage_key: str,
    coins: int,
    xp: int,
    claimed_at: Any,
) -> bool:
    try:
        cursor = _execute(
            conn,
            "INSERT INTO reward_claimed(user_id,stage_key,coins,xp,claimed_at) "
            "VALUES(?,?,?,?,?) ON CONFLICT(user_id,stage_key) DO NOTHING",
            (user_id, stage_key, coins, xp, claimed_at),
        )
    except Exception as exc:
        if _is_missing_schema_error(exc):
            raise _schema_error("reward_claimed authority is unavailable") from exc
        raise
    return int(getattr(cursor, "rowcount", 0) or 0) == 1


def settle_rewards_sync_claim_in_transaction(
    conn: Any,
    *,
    user_id: int,
    stage_key: str,
    server_computed_coins: int,
    server_computed_xp: int,
    now: datetime | date | None = None,
) -> RewardsSyncSettlementResult:
    """Reserve one existing stage claim and grant its Coins canonically.

    ``reward_claimed(user_id, stage_key)`` remains scoped to the existing
    ``/rewards/sync`` stage-key contract; this helper does not use it for
    Friend Challenge identity.  XP is recorded in the legacy claim row but is
    intentionally left to the caller's existing XP mutation so that it can
    remain in the same transaction and preserve the route's external shape.
    """

    normalized_user_id = _normalize_user_id(user_id)
    normalized_stage_key = _normalize_stage_key(stage_key)
    coins = _normalize_nonnegative_amount(server_computed_coins, "server_computed_coins")
    xp = _normalize_nonnegative_amount(server_computed_xp, "server_computed_xp")
    claimed_at, _day_start = _timestamp_and_day(now)

    claim_created = _reserve_rewards_sync_claim(
        conn,
        user_id=normalized_user_id,
        stage_key=normalized_stage_key,
        coins=coins,
        xp=xp,
        claimed_at=claimed_at,
    )
    if not claim_created:
        return RewardsSyncSettlementResult(
            status=REWARDS_SYNC_ALREADY_CLAIMED,
            user_id=normalized_user_id,
            stage_key=normalized_stage_key,
            requested_coins=coins,
            granted_coins=0,
            xp=xp,
            claim_created=False,
        )

    coin_grant = grant_coins_in_transaction(
        conn,
        user_id=normalized_user_id,
        server_computed_amount=coins,
        server_owned_reason=rewards_sync_currency_reason(normalized_stage_key),
        cap_policy=CAP_POLICY_NORMAL,
        now=now,
    )
    # The legacy row is the durable stage claim.  Persist the actual capped
    # Coin result rather than a value the cap may have removed.  This update
    # remains in the caller transaction and is rolled back with the grant if
    # any downstream XP/quest-state operation fails.
    try:
        updated = _execute(
            conn,
            "UPDATE reward_claimed SET coins=?, claimed_at=? "
            "WHERE user_id=? AND stage_key=?",
            (
                coin_grant.granted_amount,
                claimed_at,
                normalized_user_id,
                normalized_stage_key,
            ),
        )
    except Exception as exc:
        if _is_missing_schema_error(exc):
            raise _schema_error("reward_claimed authority is unavailable") from exc
        raise
    if int(getattr(updated, "rowcount", 0) or 0) != 1:
        raise CoinRewardError("reward_claimed row was not finalized")

    return RewardsSyncSettlementResult(
        status=REWARDS_SYNC_GRANTED,
        user_id=normalized_user_id,
        stage_key=normalized_stage_key,
        requested_coins=coins,
        granted_coins=coin_grant.granted_amount,
        xp=xp,
        claim_created=True,
        coin_grant=coin_grant,
    )


def _friend_challenge_claim_row(
    conn: Any,
    *,
    challenge_id: int,
    user_id: int,
) -> Any:
    try:
        return _fetchone(
            conn,
            "SELECT settlement_status FROM friend_challenge_reward_settlements "
            "WHERE challenge_id=? AND user_id=?"
            + _for_update(conn),
            (challenge_id, user_id),
        )
    except Exception as exc:
        if _is_missing_schema_error(exc):
            raise _schema_error(
                "friend_challenge_reward_settlements authority is unavailable"
            ) from exc
        raise


def settle_friend_challenge_reward_in_transaction(
    conn: Any,
    *,
    challenge_id: int,
    user_id: int,
    server_computed_coins: int | None = None,
    apply_non_coin_rewards: Callable[[Any], Mapping[str, Any]] | None = None,
    now: datetime | date | None = None,
) -> FriendChallengeSettlementResult:
    """Settle one server-computed Friend Challenge reward exactly once.

    The claim identity is ``(challenge_id, user_id)``.  A duplicate committed
    claim never calls the non-Coin callback and never invokes the Coin
    authority; it returns ``ALREADY_SETTLED`` plus ``SETTLED_NO_DETAIL``.
    ``server_computed_coins`` may be omitted only on that duplicate path, so a
    response-loss retry does not need (and cannot replay) the random reward.

    ``apply_non_coin_rewards`` is a caller-owned callback for the existing XP,
    pet, badge, and outcome mutations.  It must not mutate Coins.  Its return
    value is returned only to the first response and is never persisted.
    """

    normalized_challenge_id = _normalize_positive_id(challenge_id, "challenge_id")
    normalized_user_id = _normalize_user_id(user_id)
    existing = _friend_challenge_claim_row(
        conn,
        challenge_id=normalized_challenge_id,
        user_id=normalized_user_id,
    )
    if existing is not None:
        status = str(_row_value(existing, 0, "settlement_status") or "")
        if status == "SETTLED":
            return FriendChallengeSettlementResult(
                status=FRIEND_CHALLENGE_ALREADY_SETTLED,
                detail_status=FRIEND_CHALLENGE_SETTLED_NO_DETAIL,
                challenge_id=normalized_challenge_id,
                user_id=normalized_user_id,
                granted_coins=None,
                claim_created=False,
            )
        if status == "PENDING":
            raise FriendChallengeSettlementInProgress(
                "Friend Challenge settlement is already in progress"
            )
        raise CoinRewardError("unsupported Friend Challenge settlement status")

    if server_computed_coins is None:
        raise CoinRewardValidationError(
            "server_computed_coins is required for an unsettled challenge"
        )
    coins = _normalize_nonnegative_amount(server_computed_coins, "server_computed_coins")
    created_at, _day_start = _timestamp_and_day(now)

    try:
        cursor = _execute(
            conn,
            "INSERT INTO friend_challenge_reward_settlements("
            "challenge_id,user_id,settlement_status,created_at,settled_at) "
            "VALUES(?,?, 'PENDING', ?, NULL) "
            "ON CONFLICT(challenge_id,user_id) DO NOTHING",
            (normalized_challenge_id, normalized_user_id, created_at),
        )
    except Exception as exc:
        if _is_missing_schema_error(exc):
            raise _schema_error(
                "friend_challenge_reward_settlements authority is unavailable"
            ) from exc
        raise

    if int(getattr(cursor, "rowcount", 0) or 0) != 1:
        # The unique claim gate may have been won by another transaction after
        # the read above.  Recover its committed state without guessing a
        # random reward payload.
        raced = _friend_challenge_claim_row(
            conn,
            challenge_id=normalized_challenge_id,
            user_id=normalized_user_id,
        )
        if raced is not None and str(_row_value(raced, 0, "settlement_status")) == "SETTLED":
            return FriendChallengeSettlementResult(
                status=FRIEND_CHALLENGE_ALREADY_SETTLED,
                detail_status=FRIEND_CHALLENGE_SETTLED_NO_DETAIL,
                challenge_id=normalized_challenge_id,
                user_id=normalized_user_id,
                granted_coins=None,
                claim_created=False,
            )
        raise FriendChallengeSettlementInProgress(
            "Friend Challenge settlement reservation was won by another transaction"
        )

    coin_grant = grant_coins_in_transaction(
        conn,
        user_id=normalized_user_id,
        server_computed_amount=coins,
        server_owned_reason=friend_challenge_currency_reason(
            normalized_challenge_id,
            normalized_user_id,
        ),
        cap_policy=CAP_POLICY_EXEMPT_FRIEND_CHALLENGE,
        now=now,
    )
    first_response_detail = (
        _json_mapping(apply_non_coin_rewards(conn))
        if apply_non_coin_rewards is not None
        else None
    )

    try:
        updated = _execute(
            conn,
            "UPDATE friend_challenge_reward_settlements "
            "SET settlement_status='SETTLED', settled_at=? "
            "WHERE challenge_id=? AND user_id=? AND settlement_status='PENDING'",
            (created_at, normalized_challenge_id, normalized_user_id),
        )
    except Exception as exc:
        if _is_missing_schema_error(exc):
            raise _schema_error(
                "friend_challenge_reward_settlements authority is unavailable"
            ) from exc
        raise
    if int(getattr(updated, "rowcount", 0) or 0) != 1:
        raise CoinRewardError("Friend Challenge settlement was not finalized")

    return FriendChallengeSettlementResult(
        status=FRIEND_CHALLENGE_SETTLED,
        detail_status=None,
        challenge_id=normalized_challenge_id,
        user_id=normalized_user_id,
        granted_coins=coin_grant.granted_amount,
        claim_created=True,
        coin_grant=coin_grant,
        first_response_detail=first_response_detail,
    )


__all__ = [
    "CAP_POLICIES",
    "CAP_POLICY_EXEMPT_FRIEND_CHALLENGE",
    "CAP_POLICY_NORMAL",
    "CoinGrantResult",
    "CoinRewardError",
    "CoinRewardSchemaUnavailable",
    "CoinRewardValidationError",
    "DAILY_COIN_CAP",
    "FRIEND_CHALLENGE_ALREADY_SETTLED",
    "FRIEND_CHALLENGE_CURRENCY_REASON_PREFIX",
    "FRIEND_CHALLENGE_SETTLED",
    "FRIEND_CHALLENGE_SETTLED_NO_DETAIL",
    "FRIEND_CHALLENGE_SETTLEMENT_IN_PROGRESS",
    "FriendChallengeSettlementInProgress",
    "FriendChallengeSettlementResult",
    "REWARDS_SYNC_ALREADY_CLAIMED",
    "REWARDS_SYNC_CURRENCY_REASON_PREFIX",
    "REWARDS_SYNC_GRANTED",
    "RewardsSyncSettlementResult",
    "friend_challenge_currency_reason",
    "grant_coins_in_transaction",
    "rewards_sync_currency_reason",
    "settle_friend_challenge_reward_in_transaction",
    "settle_rewards_sync_claim_in_transaction",
]
