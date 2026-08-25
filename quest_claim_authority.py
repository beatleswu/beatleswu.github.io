"""D015 server-authoritative Quest V2 claim and reward settlement.

This service consumes D014 progress and D012 definitions.  It does not
create progress, calculate periods, or wire a route.  A caller supplies an
open transaction and server-bound reward callbacks; the service never
commits or rolls back that transaction.

``quest_claims_v2`` is the business correctness authority.  D5A
``ITEM_ACQUISITION`` rows are append-only evidence for committed item or
cosmetic ownership mutations and never decide whether a claim is allowed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Callable, Iterable, Mapping
from uuid import uuid4

from event_outbox import append_event
from migrations.quest_claim_v1 import TABLE_NAME
from migrations.quest_progress_v2 import APPLICATION_TABLE_NAME, PROGRESS_TABLE_NAME
from quest_catalog import CANONICAL_QUEST_CATALOG, QuestCatalog, QuestDefinition
from quest_identity import UnknownQuestIdentity, resolve_quest_id
from quest_reward_adapters import (
    CURRENT_QUEST_REWARD_CATALOG,
    DEFAULT_QUEST_REWARD_AUTHORITIES,
    QuestRewardAuthorities,
    QuestRewardCatalog,
    QuestRewardProfile,
    QuestRewardSettlementError,
)
from question_idempotency import canonical_payload_digest, normalize_identity


CLAIM_FAMILY = "QUEST_V2"
CLAIM_STATUS_PENDING = "PENDING"
CLAIM_STATUS_SETTLED = "SETTLED"


class QuestClaimError(RuntimeError):
    """Base class for fail-closed Quest claim errors."""


class QuestClaimConflict(QuestClaimError):
    """The same operation identity was bound to another logical claim."""


class QuestClaimInProgress(QuestClaimError):
    """A previously committed reservation requires reconciliation."""


@dataclass(frozen=True)
class QuestClaimResult:
    status: str
    reason: str | None = None
    claim_id: str | None = None
    quest_id: str | None = None
    period_key: str | None = None
    claim_operation_id: str | None = None
    reward_profile_id: str | None = None
    quest_definition_version: int | None = None
    completion_source_event_id: str | None = None
    components: tuple[dict[str, Any], ...] = ()
    acquisition_event_ids: tuple[str, ...] = ()
    created: bool = False
    duplicate: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "claim_id": self.claim_id,
            "quest_id": self.quest_id,
            "period_key": self.period_key,
            "claim_operation_id": self.claim_operation_id,
            "reward_profile_id": self.reward_profile_id,
            "quest_definition_version": self.quest_definition_version,
            "completion_source_event_id": self.completion_source_event_id,
            "components": [dict(component) for component in self.components],
            "acquisition_event_ids": list(self.acquisition_event_ids),
            "created": self.created,
            "duplicate": self.duplicate,
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


def _fetchone(conn: Any, sql: str, params: Iterable[Any] = ()) -> Any:
    cursor = _execute(conn, sql, params)
    try:
        return cursor.fetchone()
    finally:
        if not hasattr(conn, "execute"):
            cursor.close()


def _row_dict(cursor: Any, row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    if hasattr(row, "keys"):
        result = {str(key): row[key] for key in row.keys()}
    else:
        result = {str(item[0]): row[index] for index, item in enumerate(cursor.description)}
    payload = result.get("result_payload")
    if isinstance(payload, str):
        try:
            result["result_payload"] = json.loads(payload)
        except (TypeError, ValueError):
            result["result_payload"] = {}
    return result


def _fetchone_dict(conn: Any, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    cursor = _execute(conn, sql, params)
    try:
        return _row_dict(cursor, cursor.fetchone())
    finally:
        if not hasattr(conn, "execute"):
            cursor.close()


def _user_key(user_id: Any) -> str:
    if isinstance(user_id, bool) or user_id is None:
        raise QuestClaimError("user_id_invalid")
    value = str(user_id).strip()
    if not value:
        raise QuestClaimError("user_id_required")
    return value


def _period_key(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 128:
        raise QuestClaimError("period_key_invalid")
    return value.strip()


def _timestamp(conn: Any, value: datetime | None = None) -> Any:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise QuestClaimError("settlement_timestamp_must_be_timezone_aware")
    if _is_sqlite(conn):
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    return value.astimezone(timezone.utc)


def _json_parameter(conn: Any, payload: Mapping[str, Any]) -> Any:
    if _is_sqlite(conn):
        return json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    from psycopg2.extras import Json

    return Json(dict(payload))


def _for_update(conn: Any) -> str:
    return "" if _is_sqlite(conn) else " FOR UPDATE"


def _result_from_payload(
    payload: Mapping[str, Any],
    *,
    operation_id: str | None = None,
    created: bool,
    duplicate: bool,
) -> QuestClaimResult:
    components = payload.get("components") or ()
    event_ids = payload.get("acquisition_event_ids") or ()
    return QuestClaimResult(
        status=str(payload.get("status") or "DENIED"),
        reason=payload.get("reason"),
        claim_id=str(payload["claim_id"]) if payload.get("claim_id") is not None else None,
        quest_id=payload.get("quest_id"),
        period_key=payload.get("period_key"),
        claim_operation_id=operation_id or payload.get("claim_operation_id"),
        reward_profile_id=payload.get("reward_profile_id"),
        quest_definition_version=(
            int(payload["quest_definition_version"])
            if payload.get("quest_definition_version") is not None
            else None
        ),
        completion_source_event_id=payload.get("completion_source_event_id"),
        components=tuple(dict(component) for component in components),
        acquisition_event_ids=tuple(str(event_id) for event_id in event_ids),
        created=created,
        duplicate=duplicate,
    )


def _result_from_claim_row(
    row: Mapping[str, Any],
    *,
    created: bool,
    duplicate: bool,
) -> QuestClaimResult:
    payload = row.get("result_payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            payload = {}
    return _result_from_payload(payload, created=created, duplicate=duplicate)


def _safe_component_result(result: Mapping[str, Any], *, default_quantity: int) -> dict[str, Any]:
    """Keep adapter output replay-safe and exclude arbitrary/private fields."""

    allowed = {
        "ownership_authority",
        "ownership_reference",
        "granted_quantity",
        "resulting_quantity",
        "item_id",
        "cosmetic_id",
    }
    normalized = {key: result[key] for key in allowed if key in result}
    if not normalized.get("ownership_authority") or not normalized.get("ownership_reference"):
        raise QuestRewardSettlementError("ownership_evidence_missing")
    granted = normalized.get("granted_quantity", default_quantity)
    if isinstance(granted, bool) or not isinstance(granted, int) or granted != default_quantity:
        raise QuestRewardSettlementError("ownership_quantity_mismatch")
    normalized["granted_quantity"] = granted
    return normalized


class QuestClaimService:
    """Exactly-once Quest claim authority in caller-owned transaction scope."""

    def __init__(
        self,
        conn: Any,
        *,
        catalog: QuestCatalog | None = None,
        reward_catalog: QuestRewardCatalog | None = None,
        reward_authorities: QuestRewardAuthorities | None = None,
    ) -> None:
        self.conn = conn
        self.catalog = catalog or CANONICAL_QUEST_CATALOG
        self.reward_catalog = reward_catalog or CURRENT_QUEST_REWARD_CATALOG
        self.reward_authorities = reward_authorities or DEFAULT_QUEST_REWARD_AUTHORITIES

    def _operation_row(self, user_key: str, operation_id: str) -> dict[str, Any] | None:
        return _fetchone_dict(
            self.conn,
            f"""SELECT claim_id,user_id,quest_id,period_key,claim_operation_id,
                              request_fingerprint,quest_definition_version,
                              reward_profile_id,claim_status,result_payload,
                              created_at,settled_at
                         FROM {TABLE_NAME}
                        WHERE user_id=? AND claim_operation_id=?{_for_update(self.conn)}""",
            (user_key, operation_id),
        )

    def _business_row(self, user_key: str, quest_id: str, period_key: str) -> dict[str, Any] | None:
        return _fetchone_dict(
            self.conn,
            f"""SELECT claim_id,user_id,quest_id,period_key,claim_operation_id,
                              request_fingerprint,quest_definition_version,
                              reward_profile_id,claim_status,result_payload,
                              created_at,settled_at
                         FROM {TABLE_NAME}
                        WHERE user_id=? AND quest_id=? AND period_key=?{_for_update(self.conn)}""",
            (user_key, quest_id, period_key),
        )

    def _progress_row(self, user_key: str, quest_id: str, period_key: str) -> dict[str, Any] | None:
        return _fetchone_dict(
            self.conn,
            f"""SELECT user_id,quest_id,period_key,progress,completed,
                              definition_version,target_snapshot,created_at,updated_at
                         FROM {PROGRESS_TABLE_NAME}
                        WHERE user_id=? AND quest_id=? AND period_key=?{_for_update(self.conn)}""",
            (user_key, quest_id, period_key),
        )

    def _reserve(
        self,
        *,
        user_key: str,
        quest_id: str,
        period_key: str,
        operation_id: str,
        request_fingerprint: str,
        definition: QuestDefinition,
        created_at: Any,
    ) -> tuple[dict[str, Any], bool]:
        claim_id = str(uuid4())
        cursor = _execute(
            self.conn,
            f"""INSERT INTO {TABLE_NAME}(
                         claim_id,user_id,quest_id,period_key,claim_operation_id,
                         request_fingerprint,quest_definition_version,reward_profile_id,
                         claim_status,result_payload,created_at,settled_at)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,NULL)
                 ON CONFLICT DO NOTHING""",
            (
                claim_id,
                user_key,
                quest_id,
                period_key,
                operation_id,
                request_fingerprint,
                definition.version,
                str(definition.reward_profile_id),
                CLAIM_STATUS_PENDING,
                _json_parameter(self.conn, {}),
                created_at,
            ),
        )
        inserted = int(getattr(cursor, "rowcount", 0) or 0) == 1
        existing = self._operation_row(user_key, operation_id)
        if existing is None:
            # A different operation may already own this Quest period.  The
            # business unique key is authoritative for the no-second-reward
            # result, so recover that row instead of surfacing a raw unique
            # violation to the caller.
            existing = self._business_row(user_key, quest_id, period_key)
        if existing is None:
            raise QuestClaimError("claim_reservation_not_recoverable")
        return existing, inserted

    def _delete_pending(self, user_key: str, operation_id: str) -> None:
        _execute(
            self.conn,
            f"DELETE FROM {TABLE_NAME} WHERE user_id=? AND claim_operation_id=? AND claim_status=?",
            (user_key, operation_id, CLAIM_STATUS_PENDING),
        )

    @staticmethod
    def _operation_replay_or_conflict(
        row: Mapping[str, Any],
        *,
        user_key: str,
        quest_id: str,
        period_key: str,
        request_fingerprint: str,
        operation_id: str,
    ) -> QuestClaimResult | None:
        if (
            str(row.get("user_id")) != user_key
            or str(row.get("quest_id")) != quest_id
            or str(row.get("period_key")) != period_key
            or str(row.get("request_fingerprint")) != request_fingerprint
        ):
            return QuestClaimResult(
                status="CONFLICT",
                reason="CLAIM_IDEMPOTENCY_CONFLICT",
                claim_operation_id=operation_id,
                quest_id=quest_id,
                period_key=period_key,
                duplicate=True,
            )
        status = str(row.get("claim_status") or "")
        if status == CLAIM_STATUS_SETTLED:
            return _result_from_claim_row(row, created=False, duplicate=True)
        if status == CLAIM_STATUS_PENDING:
            return QuestClaimResult(
                status="IN_PROGRESS",
                reason="CLAIM_IN_PROGRESS",
                claim_id=str(row.get("claim_id")),
                quest_id=quest_id,
                period_key=period_key,
                claim_operation_id=operation_id,
                duplicate=True,
            )
        raise QuestClaimError("unsupported_claim_status")

    def _validate_all_complete(self, user_key: str, period_key: str) -> bool:
        primary_ids = (
            "daily:kill_monsters",
            "daily:streak_correct",
            "daily:challenge_dragon",
        )
        for quest_id in primary_ids:
            definition = self.catalog.canonical_map.get(quest_id)
            if definition is None:
                return False
            row = _fetchone_dict(
                self.conn,
                f"""SELECT progress,completed,definition_version,target_snapshot
                             FROM {PROGRESS_TABLE_NAME}
                            WHERE user_id=? AND quest_id=? AND period_key=?""",
                (user_key, quest_id, period_key),
            )
            if row is None:
                return False
            if int(row.get("progress") or 0) < int(definition.target or 0):
                return False
            if not bool(row.get("completed")):
                return False
            if int(row.get("definition_version") or 0) != int(definition.version):
                return False
            if int(row.get("target_snapshot") or 0) != int(definition.target or 0):
                return False
        return True

    def _completion_source_event_id(
        self,
        *,
        user_key: str,
        quest_id: str,
        period_key: str,
        target: int,
    ) -> str | None:
        """Return the D014 event that durably proved Quest completion."""

        row = _fetchone_dict(
            self.conn,
            f"""SELECT source_event_id
                         FROM {APPLICATION_TABLE_NAME}
                        WHERE user_id=? AND quest_id=? AND period_key=?
                          AND resulting_progress>=? AND completed=?
                     ORDER BY source_occurred_at DESC,source_event_id DESC
                        LIMIT 1""",
            (
                user_key,
                quest_id,
                period_key,
                target,
                True if not _is_sqlite(self.conn) else 1,
            ),
        )
        if row is None or not row.get("source_event_id"):
            return None
        return str(row["source_event_id"])

    def _append_acquisition_event(
        self,
        *,
        user_id: int | str,
        claim_id: str,
        operation_id: str,
        completion_source_event_id: str,
        definition: QuestDefinition,
        period_key: str,
        profile: QuestRewardProfile,
        component_index: int,
        item_id: str,
        quantity: int,
        evidence: Mapping[str, Any],
        occurred_at: Any,
    ) -> dict[str, Any]:
        evidence = _safe_component_result(evidence, default_quantity=quantity)
        event = append_event(
            self.conn,
            event_type="ITEM_ACQUISITION",
            player_id=str(user_id),
            lineage_id=f"quest-claim:{claim_id}",
            source_event_id=completion_source_event_id,
            idempotency_key=f"quest-item-acquisition:{claim_id}:{component_index}:{item_id}",
            outcome="SUCCESS",
            payload={
                "operation": "GRANT",
                "claim_id": claim_id,
                "claim_operation_id": operation_id,
                "completion_source_event_id": completion_source_event_id,
                "quest_id": definition.quest_id,
                "period_key": period_key,
                "quest_definition_version": definition.version,
                "reward_profile_id": profile.profile_id,
                "item_id": item_id,
                "quantity": quantity,
                "acquisition_source": "QUEST",
                "source_reference": f"quest-claim:{claim_id}",
                "ownership_authority": evidence["ownership_authority"],
                "ownership_reference": evidence["ownership_reference"],
                "ownership_committed": True,
                "granted_quantity": evidence["granted_quantity"],
            },
            occurred_at=occurred_at,
        )
        return event

    @staticmethod
    def _fault(fault_hook: Callable[[str], None] | None, stage: str) -> None:
        if fault_hook:
            fault_hook(stage)

    def _settle_components(
        self,
        *,
        user_id: int | str,
        claim_id: str,
        operation_id: str,
        definition: QuestDefinition,
        period_key: str,
        completion_source_event_id: str,
        profile: QuestRewardProfile,
        settled_at: Any,
        fault_hook: Callable[[str], None] | None,
    ) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
        components: list[dict[str, Any]] = []
        acquisition_event_ids: list[str] = []
        reason_prefix = f"quest_claim:{definition.quest_id}:{period_key}"

        if profile.xp:
            granted_xp = self.reward_authorities.grant_xp(
                self.conn,
                user_id,
                profile.xp,
                reason_prefix,
                profile.profile_id,
            )
            components.append(
                {
                    "component_type": "XP",
                    "base_amount": profile.xp,
                    "granted_amount": granted_xp,
                }
            )
            self._fault(fault_hook, "after_xp")

        if profile.coins:
            granted_coins = self.reward_authorities.grant_coins(
                self.conn,
                user_id,
                profile.coins,
                reason_prefix,
                profile.profile_id,
            )
            components.append(
                {
                    "component_type": "COINS",
                    "base_amount": profile.coins,
                    "granted_amount": granted_coins,
                }
            )
            self._fault(fault_hook, "after_coins")

        component_index = 0
        for item in profile.items:
            evidence = self.reward_authorities.grant_item(
                self.conn,
                user_id,
                item.item_id,
                item.quantity,
                reason_prefix,
                profile.profile_id,
            )
            safe_evidence = _safe_component_result(evidence, default_quantity=item.quantity)
            event = self._append_acquisition_event(
                user_id=user_id,
                claim_id=claim_id,
                operation_id=operation_id,
                completion_source_event_id=completion_source_event_id,
                definition=definition,
                period_key=period_key,
                profile=profile,
                component_index=component_index,
                item_id=item.item_id,
                quantity=item.quantity,
                evidence=safe_evidence,
                occurred_at=settled_at,
            )
            acquisition_event_ids.append(str(event["event_id"]))
            components.append(
                {
                    "component_type": "ITEM",
                    "item_id": item.item_id,
                    "quantity": item.quantity,
                    "ownership_authority": safe_evidence["ownership_authority"],
                    "ownership_reference": safe_evidence["ownership_reference"],
                    "acquisition_event_id": str(event["event_id"]),
                }
            )
            component_index += 1
            self._fault(fault_hook, "after_item")
            self._fault(fault_hook, "after_lineage")

        for cosmetic_id in profile.cosmetics:
            evidence = self.reward_authorities.grant_cosmetic(
                self.conn,
                user_id,
                cosmetic_id,
                reason_prefix,
                profile.profile_id,
            )
            safe_evidence = _safe_component_result(evidence, default_quantity=1)
            event = self._append_acquisition_event(
                user_id=user_id,
                claim_id=claim_id,
                operation_id=operation_id,
                completion_source_event_id=completion_source_event_id,
                definition=definition,
                period_key=period_key,
                profile=profile,
                component_index=component_index,
                item_id=cosmetic_id,
                quantity=1,
                evidence=safe_evidence,
                occurred_at=settled_at,
            )
            acquisition_event_ids.append(str(event["event_id"]))
            components.append(
                {
                    "component_type": "COSMETIC",
                    "item_id": cosmetic_id,
                    "ownership_authority": safe_evidence["ownership_authority"],
                    "ownership_reference": safe_evidence["ownership_reference"],
                    "acquisition_event_id": str(event["event_id"]),
                }
            )
            component_index += 1
            self._fault(fault_hook, "after_cosmetic")
            self._fault(fault_hook, "after_lineage")

        return tuple(components), tuple(acquisition_event_ids)

    def claim(
        self,
        user_id: int | str,
        quest_id: str,
        period_key: str,
        *,
        claim_operation_id: str | None = None,
        now: datetime | None = None,
        fault_hook: Callable[[str], None] | None = None,
        client_claimed: Any = None,
        client_target: Any = None,
        client_progress: Any = None,
        client_reward_profile_id: Any = None,
    ) -> QuestClaimResult:
        """Settle one canonical Quest period without committing the caller.

        The optional ``client_*`` arguments exist only to make the forgery
        boundary explicit in tests.  Any attempt to supply them is rejected;
        server progress/catalog state is always the authority.
        """

        if any(
            value is not None
            for value in (client_claimed, client_target, client_progress, client_reward_profile_id)
        ):
            return QuestClaimResult(status="DENIED", reason="CLIENT_AUTHORITY_FIELD_REJECTED")

        user_key = _user_key(user_id)
        try:
            canonical_quest_id = resolve_quest_id(quest_id, self.catalog)
            period_key = _period_key(period_key)
            operation_id, _generated = normalize_identity(
                claim_operation_id,
                field="claim_operation_id",
                generate_if_missing=True,
            )
        except (QuestClaimError, UnknownQuestIdentity, ValueError) as exc:
            return QuestClaimResult(status="DENIED", reason=str(exc) or "INVALID_CLAIM_REQUEST")

        definition = self.catalog.canonical_map[canonical_quest_id]
        try:
            profile = self.reward_catalog.resolve(definition.reward_profile_id)
        except QuestRewardSettlementError as exc:
            return QuestClaimResult(
                status="DENIED",
                reason=str(exc),
                quest_id=canonical_quest_id,
                period_key=period_key,
                claim_operation_id=operation_id,
            )
        request_fingerprint = canonical_payload_digest(
            {
                "claim_family": CLAIM_FAMILY,
                "quest_id": canonical_quest_id,
                "period_key": period_key,
                "quest_definition_version": definition.version,
                "reward_profile_id": profile.profile_id,
            }
        )

        existing_operation = self._operation_row(user_key, operation_id)
        if existing_operation is not None:
            replay = self._operation_replay_or_conflict(
                existing_operation,
                user_key=user_key,
                quest_id=canonical_quest_id,
                period_key=period_key,
                request_fingerprint=request_fingerprint,
                operation_id=operation_id,
            )
            if replay is not None:
                return replay

        if not definition.enabled or str(definition.availability.get("catalog_status")) in {"disabled", "retired"}:
            return QuestClaimResult(
                status="DENIED",
                reason="QUEST_DISABLED",
                quest_id=canonical_quest_id,
                period_key=period_key,
                claim_operation_id=operation_id,
            )

        created_at = _timestamp(self.conn, now)
        reservation, inserted = self._reserve(
            user_key=user_key,
            quest_id=canonical_quest_id,
            period_key=period_key,
            operation_id=operation_id,
            request_fingerprint=request_fingerprint,
            definition=definition,
            created_at=created_at,
        )
        if not inserted:
            if str(reservation.get("claim_operation_id")) == operation_id:
                replay = self._operation_replay_or_conflict(
                    reservation,
                    user_key=user_key,
                    quest_id=canonical_quest_id,
                    period_key=period_key,
                    request_fingerprint=request_fingerprint,
                    operation_id=operation_id,
                )
                if replay is None:
                    raise QuestClaimError("claim_operation_replay_not_recoverable")
                return replay
            # A distinct operation lost the business-key race.  Once the
            # winner is settled, replay its committed result rather than
            # granting a second reward; a still-pending winner is explicitly
            # reported as in progress and remains caller-transaction-owned.
            if (
                str(reservation.get("user_id")) == user_key
                and str(reservation.get("quest_id")) == canonical_quest_id
                and str(reservation.get("period_key")) == period_key
            ):
                if str(reservation.get("claim_status")) == CLAIM_STATUS_SETTLED:
                    return _result_from_claim_row(reservation, created=False, duplicate=True)
                return QuestClaimResult(
                    status="IN_PROGRESS",
                    reason="CLAIM_IN_PROGRESS",
                    claim_id=str(reservation.get("claim_id")),
                    quest_id=canonical_quest_id,
                    period_key=period_key,
                    claim_operation_id=operation_id,
                    duplicate=True,
                )
            raise QuestClaimError("claim_operation_replay_not_recoverable")
        if str(reservation.get("claim_status")) != CLAIM_STATUS_PENDING:
            raise QuestClaimError("claim_reservation_status_invalid")

        progress = self._progress_row(user_key, canonical_quest_id, period_key)
        if progress is None:
            self._delete_pending(user_key, operation_id)
            return QuestClaimResult(
                status="DENIED",
                reason="QUEST_NOT_COMPLETED",
                quest_id=canonical_quest_id,
                period_key=period_key,
                claim_operation_id=operation_id,
            )

        progress_version = int(progress.get("definition_version") or 0)
        progress_target = int(progress.get("target_snapshot") or 0)
        canonical_target = int(definition.target or 0)
        if (
            progress_version != definition.version
            or progress_target != canonical_target
            or canonical_target <= 0
        ):
            self._delete_pending(user_key, operation_id)
            return QuestClaimResult(
                status="DENIED",
                reason="QUEST_DEFINITION_VERSION_UNAVAILABLE",
                quest_id=canonical_quest_id,
                period_key=period_key,
                claim_operation_id=operation_id,
            )

        if (
            not bool(progress.get("completed"))
            or int(progress.get("progress") or 0) < canonical_target
        ):
            self._delete_pending(user_key, operation_id)
            return QuestClaimResult(
                status="DENIED",
                reason="QUEST_NOT_COMPLETED",
                quest_id=canonical_quest_id,
                period_key=period_key,
                claim_operation_id=operation_id,
            )

        if definition.condition == "QUEST_SET_COMPLETED" and definition.filters.get("quest_group") == "daily_primary":
            if not self._validate_all_complete(user_key, period_key):
                self._delete_pending(user_key, operation_id)
                return QuestClaimResult(
                    status="DENIED",
                    reason="QUEST_SET_COMPLETION_EVIDENCE_MISSING",
                    quest_id=canonical_quest_id,
                    period_key=period_key,
                    claim_operation_id=operation_id,
                )

        existing_business = self._business_row(user_key, canonical_quest_id, period_key)
        # The reservation itself satisfies the business unique key.  Only a
        # different claim row represents a competing operation for this Quest
        # period; treating our own PENDING row as a competitor would make the
        # first claim return CLAIM_IN_PROGRESS and delete its reservation.
        if (
            existing_business is not None
            and str(existing_business.get("claim_id")) != str(reservation.get("claim_id"))
        ):
            self._delete_pending(user_key, operation_id)
            if str(existing_business.get("claim_status")) == CLAIM_STATUS_SETTLED:
                return _result_from_claim_row(existing_business, created=False, duplicate=True)
            return QuestClaimResult(
                status="IN_PROGRESS",
                reason="CLAIM_IN_PROGRESS",
                claim_id=str(existing_business.get("claim_id")),
                quest_id=canonical_quest_id,
                period_key=period_key,
                claim_operation_id=operation_id,
                duplicate=True,
            )

        completion_source_event_id = self._completion_source_event_id(
            user_key=user_key,
            quest_id=canonical_quest_id,
            period_key=period_key,
            target=canonical_target,
        )
        if completion_source_event_id is None:
            self._delete_pending(user_key, operation_id)
            return QuestClaimResult(
                status="DENIED",
                reason="COMPLETION_LINEAGE_UNAVAILABLE",
                quest_id=canonical_quest_id,
                period_key=period_key,
                claim_operation_id=operation_id,
            )

        settled_at = _timestamp(self.conn, now)
        components, acquisition_event_ids = self._settle_components(
            user_id=user_id,
            claim_id=str(reservation["claim_id"]),
            operation_id=operation_id,
            definition=definition,
            period_key=period_key,
            completion_source_event_id=completion_source_event_id,
            profile=profile,
            settled_at=settled_at,
            fault_hook=fault_hook,
        )
        self._fault(fault_hook, "before_claim_settle")
        payload = {
            "status": "GRANTED",
            "reason": None,
            "claim_id": str(reservation["claim_id"]),
            "quest_id": canonical_quest_id,
            "period_key": period_key,
            "claim_operation_id": operation_id,
            "quest_definition_version": definition.version,
            "reward_profile_id": profile.profile_id,
            "completion_source_event_id": completion_source_event_id,
            "components": [dict(component) for component in components],
            "acquisition_event_ids": list(acquisition_event_ids),
        }
        cursor = _execute(
            self.conn,
            f"""UPDATE {TABLE_NAME}
                   SET claim_status=?,result_payload=?,settled_at=?
                 WHERE user_id=? AND claim_operation_id=? AND claim_status=?""",
            (
                CLAIM_STATUS_SETTLED,
                _json_parameter(self.conn, payload),
                settled_at,
                user_key,
                operation_id,
                CLAIM_STATUS_PENDING,
            ),
        )
        if int(getattr(cursor, "rowcount", 0) or 0) != 1:
            raise QuestClaimError("claim_settlement_row_not_recoverable")
        self._fault(fault_hook, "after_claim_settle")
        return _result_from_payload(payload, created=True, duplicate=False)

    claim_quest = claim


__all__ = [
    "CLAIM_FAMILY",
    "CLAIM_STATUS_PENDING",
    "CLAIM_STATUS_SETTLED",
    "QuestClaimConflict",
    "QuestClaimError",
    "QuestClaimInProgress",
    "QuestClaimResult",
    "QuestClaimService",
]
