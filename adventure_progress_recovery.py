"""Fail-closed candidate authority for P0 Adventure make-whole recovery.

The recovery path consumes an explicit, server-owned correctness fact.  It
does not treat an SRS grade, a card flag, or a Practice label as correctness
authority.  A historical ``source_context='practice'`` value is preserved as
provenance and is neither an inclusion nor an exclusion rule.

This module is intentionally additive.  It does not write ``review_log``,
``srs_cards``, Map Battle rows, boss progress, stars, rewards, or history.
Ledger writes are caller-transaction-owned and therefore suitable for a
future separately gated Production apply.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import datetime as _datetime
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence

from migrations.adventure_progress_recovery_v1 import (
    HISTORICAL_CORRECTNESS_SERVER_CORRECT,
    HISTORICAL_CORRECTNESS_UNRESOLVED_DUE_TO_INCIDENT,
    OWNER_POLICY_RECOVERY_REASON,
    POLICY_CLASSIFICATION_ALREADY_CREDITED,
    POLICY_CLASSIFICATION_CANONICAL_IDENTITY_UNRESOLVED,
    POLICY_CLASSIFICATION_CORRECTNESS_AUTHORITY_MISSING,
    POLICY_CLASSIFICATION_SERVER_CORRECT,
    TABLE_NAME,
)


RECOVERY_REASON = "P0_ADVENTURE_PROGRESS_MAKE_WHOLE_2026"
OWNER_POLICY_REASON = OWNER_POLICY_RECOVERY_REASON
NORMAL_ADVENTURE_ORIGIN = "normal_authenticated_adventure"
EVIDENCE_CLASS_PROVEN_RECOVERABLE = "PROVEN_RECOVERABLE"
EVIDENCE_CLASS_ALREADY_CREDITED = "ALREADY_CREDITED"
EVIDENCE_CLASS_UNRESOLVED_GAP = "UNRESOLVED_EVIDENCE_GAP"
GAP_REASON_ALREADY_CREDITED = "ALREADY_CREDITED"
GAP_REASON_CORRECTNESS_AUTHORITY_MISSING = "CORRECTNESS_AUTHORITY_MISSING"
GAP_REASON_CANONICAL_IDENTITY_UNRESOLVED = "CANONICAL_IDENTITY_UNRESOLVED"
GAP_REASONS = frozenset(
    {
        "",
        GAP_REASON_ALREADY_CREDITED,
        GAP_REASON_CORRECTNESS_AUTHORITY_MISSING,
        GAP_REASON_CANONICAL_IDENTITY_UNRESOLVED,
    }
)
EVIDENCE_CLASSES = frozenset(
    {
        EVIDENCE_CLASS_PROVEN_RECOVERABLE,
        EVIDENCE_CLASS_ALREADY_CREDITED,
        EVIDENCE_CLASS_UNRESOLVED_GAP,
    }
)


class RecoveryCandidateError(ValueError):
    """Raised when a proposed recovery record is not canonical and complete."""


@dataclass(frozen=True, slots=True)
class RecoveryRecord:
    """One distinct user/canonical-question/Zone credit to be restored."""

    user_id: int
    zone_key: str
    canonical_question_id: str
    legacy_question_id: int
    existing_credit: bool
    proposed_recovery_credit: int
    recovery_reason: str
    operation_id: str
    provenance: str
    evidence_class: str = EVIDENCE_CLASS_PROVEN_RECOVERABLE
    apply_eligible: bool = True
    gap_reason: str = ""
    policy_classification: str = ""
    credit_delta: int = 0
    historical_correctness_status: str = ""

    def __post_init__(self) -> None:
        if self.evidence_class not in EVIDENCE_CLASSES:
            raise RecoveryCandidateError(
                f"unsupported recovery evidence class: {self.evidence_class}"
            )
        if self.gap_reason not in GAP_REASONS:
            raise RecoveryCandidateError(
                f"unsupported recovery gap reason: {self.gap_reason}"
            )
        if not self.policy_classification:
            default_policy = {
                EVIDENCE_CLASS_PROVEN_RECOVERABLE: POLICY_CLASSIFICATION_SERVER_CORRECT,
                EVIDENCE_CLASS_ALREADY_CREDITED: POLICY_CLASSIFICATION_ALREADY_CREDITED,
                EVIDENCE_CLASS_UNRESOLVED_GAP: (
                    POLICY_CLASSIFICATION_CANONICAL_IDENTITY_UNRESOLVED
                    if self.gap_reason == GAP_REASON_CANONICAL_IDENTITY_UNRESOLVED
                    else POLICY_CLASSIFICATION_CORRECTNESS_AUTHORITY_MISSING
                ),
            }
            object.__setattr__(self, "policy_classification", default_policy[self.evidence_class])
        if not self.historical_correctness_status:
            default_status = (
                HISTORICAL_CORRECTNESS_SERVER_CORRECT
                if self.evidence_class == EVIDENCE_CLASS_PROVEN_RECOVERABLE
                else (
                    "ALREADY_CREDITED"
                    if self.evidence_class == EVIDENCE_CLASS_ALREADY_CREDITED
                    else HISTORICAL_CORRECTNESS_UNRESOLVED_DUE_TO_INCIDENT
                )
            )
            object.__setattr__(self, "historical_correctness_status", default_status)
        if self.evidence_class == EVIDENCE_CLASS_PROVEN_RECOVERABLE and self.credit_delta == 0:
            object.__setattr__(self, "credit_delta", 1)
        if self.evidence_class == EVIDENCE_CLASS_ALREADY_CREDITED and not self.gap_reason:
            object.__setattr__(self, "gap_reason", GAP_REASON_ALREADY_CREDITED)
        if self.evidence_class == EVIDENCE_CLASS_UNRESOLVED_GAP and not self.gap_reason:
            object.__setattr__(
                self, "gap_reason", GAP_REASON_CORRECTNESS_AUTHORITY_MISSING
            )
        if self.evidence_class == EVIDENCE_CLASS_PROVEN_RECOVERABLE:
            if self.gap_reason:
                raise RecoveryCandidateError(
                    "proven recovery records cannot carry a gap reason"
                )
            if not self.apply_eligible or self.proposed_recovery_credit != 1:
                raise RecoveryCandidateError(
                    "proven recovery records must be apply eligible with credit 1"
                )
            if (
                self.policy_classification != POLICY_CLASSIFICATION_SERVER_CORRECT
                or self.credit_delta != 1
                or self.historical_correctness_status != HISTORICAL_CORRECTNESS_SERVER_CORRECT
            ):
                raise RecoveryCandidateError("proven records must assert server correctness")
        elif self.evidence_class == EVIDENCE_CLASS_ALREADY_CREDITED and self.gap_reason != GAP_REASON_ALREADY_CREDITED:
            raise RecoveryCandidateError(
                "already-credited records require the ALREADY_CREDITED reason"
            )
        elif self.evidence_class == EVIDENCE_CLASS_UNRESOLVED_GAP and self.gap_reason not in {
            GAP_REASON_CORRECTNESS_AUTHORITY_MISSING,
            GAP_REASON_CANONICAL_IDENTITY_UNRESOLVED,
        }:
            raise RecoveryCandidateError(
                "unresolved records require an explicit evidence-gap reason"
            )
        if self.evidence_class == EVIDENCE_CLASS_ALREADY_CREDITED:
            if (
                self.policy_classification != POLICY_CLASSIFICATION_ALREADY_CREDITED
                or self.credit_delta != 0
                or self.historical_correctness_status != "ALREADY_CREDITED"
            ):
                raise RecoveryCandidateError("already-credited records cannot carry recovery credit")
        elif self.evidence_class == EVIDENCE_CLASS_UNRESOLVED_GAP:
            expected_policy = (
                POLICY_CLASSIFICATION_CANONICAL_IDENTITY_UNRESOLVED
                if self.gap_reason == GAP_REASON_CANONICAL_IDENTITY_UNRESOLVED
                else POLICY_CLASSIFICATION_CORRECTNESS_AUTHORITY_MISSING
            )
            if (
                self.policy_classification != expected_policy
                or self.historical_correctness_status != HISTORICAL_CORRECTNESS_UNRESOLVED_DUE_TO_INCIDENT
                or self.credit_delta != self.proposed_recovery_credit
            ):
                raise RecoveryCandidateError("unresolved record policy fields are inconsistent")
            if self.gap_reason == GAP_REASON_CANONICAL_IDENTITY_UNRESOLVED and (
                self.apply_eligible or self.proposed_recovery_credit != 0
            ):
                raise RecoveryCandidateError("identity-unresolved records cannot be applied")
            if self.apply_eligible and (
                self.recovery_reason != OWNER_POLICY_REASON
                or self.proposed_recovery_credit != 1
                or self.credit_delta != 1
            ):
                raise RecoveryCandidateError("only Owner-policy rows may apply unresolved correctness gaps")
        if self.credit_delta not in (0, 1):
            raise RecoveryCandidateError("credit_delta must be 0 or 1")
        if self.credit_delta != self.proposed_recovery_credit:
            raise RecoveryCandidateError("credit_delta must equal proposed_recovery_credit")

    def key(self) -> tuple[int, str, str, str]:
        return (
            int(self.user_id),
            str(self.canonical_question_id),
            str(self.zone_key),
            str(self.recovery_reason),
        )

    def pair_key(self) -> tuple[int, str]:
        return int(self.user_id), str(self.canonical_question_id)

    def as_package_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_sqlite(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _table_exists(conn: Any) -> bool:
    if _is_sqlite(conn):
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE_NAME,),
        ).fetchone()
    else:
        row = conn.execute(
            """SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name=?""",
            (TABLE_NAME,),
        ).fetchone()
    return row is not None


def _parse_timestamp(value: Any) -> _datetime.datetime:
    text = str(value or "").strip()
    if not text:
        raise RecoveryCandidateError("event_at is required")
    try:
        parsed = _datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise RecoveryCandidateError("event_at is not ISO-8601") from error
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(_datetime.timezone.utc).replace(tzinfo=None)
    return parsed


def _timestamp_bounds(
    incident_start: Any,
    incident_end: Any | None,
) -> tuple[_datetime.datetime, _datetime.datetime | None]:
    start = _parse_timestamp(incident_start)
    end = None if incident_end in (None, "", "STILL_ACTIVE") else _parse_timestamp(incident_end)
    if end is not None and end <= start:
        raise RecoveryCandidateError("incident_end must be after incident_start")
    return start, end


def _boundary_text(value: Any | None) -> str | None:
    """Validate a package boundary while preserving the supplied precision."""

    if value in (None, "", "STILL_ACTIVE"):
        return None
    text = str(value).strip()
    _parse_timestamp(text)
    return text


def _stable_provenance(value: Any) -> str:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
    if isinstance(value, Mapping):
        return json.dumps(
            dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    raise RecoveryCandidateError("server evidence provenance is required")


def _canonical_zone_identity(
    zone_question_identity: Mapping[str, Mapping[Any, Any]],
    zone_key: Any,
    question_id: Any,
) -> tuple[str, int]:
    zone = str(zone_key or "")
    if not zone or zone not in zone_question_identity:
        raise RecoveryCandidateError("question is not in an exact canonical Zone pool")
    try:
        legacy_id = int(question_id)
    except (TypeError, ValueError) as error:
        raise RecoveryCandidateError("question_id is not an integer") from error
    mapping = zone_question_identity[zone]
    canonical = mapping.get(legacy_id, mapping.get(str(legacy_id)))
    if not isinstance(canonical, str) or not canonical.strip():
        raise RecoveryCandidateError("question identity is missing or unresolved")
    return canonical.strip(), legacy_id


def _existing_key_set(existing_credit: Iterable[Any] | None) -> set[tuple[int, str, str, str]]:
    result: set[tuple[int, str, str, str]] = set()
    for value in existing_credit or ():
        if isinstance(value, Mapping):
            result.add(
                (
                    int(value["user_id"]),
                    str(value["canonical_question_id"]),
                    str(value["zone_key"]),
                    str(value.get("recovery_reason", RECOVERY_REASON)),
                )
            )
            continue
        if not isinstance(value, Sequence) or len(value) != 4:
            raise RecoveryCandidateError("existing_credit has an invalid key")
        result.add((int(value[0]), str(value[1]), str(value[2]), str(value[3])))
    return result


def build_recovery_candidates(
    evidence_rows: Iterable[Mapping[str, Any]],
    *,
    affected_user_ids: Iterable[Any],
    zone_question_identity: Mapping[str, Mapping[Any, Any]],
    existing_credit: Iterable[Any] | None = None,
    incident_start: Any,
    incident_end: Any | None,
    operation_id: str,
    recovery_reason: str = RECOVERY_REASON,
) -> dict[str, Any]:
    """Build a deterministic candidate set from explicit server evidence.

    ``server_correct`` must be an actual boolean supplied by the authority
    adapter.  This function deliberately does not inspect ``grade`` or
    ``source_context``.  ``incident_route`` must be the separately proven
    normal Adventure route, which prevents rating-test/daily/challenge
    evidence from being silently promoted into Adventure credit.

    An open incident has ``incident_end=None``/``STILL_ACTIVE`` and accepts
    evidence after the server-judged Practice boundary.  A future final run
    supplies the verified hotfix activation timestamp as the end bound.
    """

    operation_id = str(operation_id or "").strip()
    recovery_reason = str(recovery_reason or "").strip()
    if not operation_id or not recovery_reason:
        raise RecoveryCandidateError("operation_id and recovery_reason are required")
    start, end = _timestamp_bounds(incident_start, incident_end)
    affected = {int(uid) for uid in affected_user_ids}
    existing = _existing_key_set(existing_credit)
    records: dict[tuple[int, str, str, str], RecoveryRecord] = {}
    already_credited: set[tuple[int, str, str, str]] = set()
    skipped: dict[str, int] = {}

    def skip(reason: str) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1

    for row in evidence_rows:
        if not isinstance(row, Mapping):
            skip("row_not_mapping")
            continue
        try:
            uid = int(row["user_id"])
        except (KeyError, TypeError, ValueError):
            skip("user_identity_missing")
            continue
        if uid not in affected:
            skip("user_not_in_affected_population")
            continue
        if row.get("server_correct") is not True:
            skip("server_correctness_not_proven")
            continue
        if row.get("incident_route") != NORMAL_ADVENTURE_ORIGIN:
            skip("incident_route_not_proven")
            continue
        try:
            event_at = _parse_timestamp(row.get("event_at"))
        except RecoveryCandidateError:
            skip("event_time_missing_or_invalid")
            continue
        if event_at < start or (end is not None and event_at >= end):
            skip("outside_incident_window")
            continue
        try:
            canonical_id, legacy_id = _canonical_zone_identity(
                zone_question_identity, row.get("zone_key"), row.get("question_id")
            )
            provenance = _stable_provenance(row.get("provenance"))
        except RecoveryCandidateError as error:
            skip(str(error))
            continue
        zone_key = str(row["zone_key"])
        key = (uid, canonical_id, zone_key, recovery_reason)
        if key in existing:
            already_credited.add(key)
            continue
        if key in records:
            skip("duplicate_evidence_deduplicated")
            continue
        records[key] = RecoveryRecord(
            user_id=uid,
            zone_key=zone_key,
            canonical_question_id=canonical_id,
            legacy_question_id=legacy_id,
            existing_credit=False,
            proposed_recovery_credit=1,
            recovery_reason=recovery_reason,
            operation_id=operation_id,
            provenance=provenance,
        )

    ordered = tuple(records[key] for key in sorted(records))
    return {
        "records": ordered,
        "already_credited": tuple(sorted(already_credited)),
        "skipped": dict(sorted(skipped.items())),
        "incident_start": start.isoformat(timespec="seconds"),
        "incident_end": None if end is None else end.isoformat(timespec="seconds"),
        "affected_user_count": len(affected),
    }


def build_recovery_decision_set(
    evidence_rows: Iterable[Mapping[str, Any]],
    *,
    gap_rows: Iterable[Mapping[str, Any]],
    affected_user_ids: Iterable[Any],
    zone_question_identity: Mapping[str, Mapping[Any, Any]],
    existing_credit: Iterable[Any] | None = None,
    incident_start: Any,
    incident_end: Any | None,
    operation_id: str,
    recovery_reason: str = RECOVERY_REASON,
) -> dict[str, Any]:
    """Build the strict recovery set and the visible Owner-policy gap set.

    ``evidence_rows`` must carry an explicit server-owned boolean
    ``server_correct=True`` and the proven normal Adventure route.  ``gap_rows``
    is an incident inventory only: its correctness is intentionally unresolved
    and is never made apply-eligible.  Neither ``grade`` nor ``source_context``
    is used to establish correctness.
    """

    operation_id = str(operation_id or "").strip()
    recovery_reason = str(recovery_reason or "").strip()
    if not operation_id or not recovery_reason:
        raise RecoveryCandidateError("operation_id and recovery_reason are required")
    start, end = _timestamp_bounds(incident_start, incident_end)
    affected = {int(uid) for uid in affected_user_ids}
    existing = _existing_key_set(existing_credit)
    records: dict[tuple[int, str, str, str], RecoveryRecord] = {}
    skipped: dict[str, int] = {}

    def skip(reason: str) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1

    def add_row(row: Mapping[str, Any], *, strict: bool) -> None:
        try:
            uid = int(row["user_id"])
        except (KeyError, TypeError, ValueError):
            skip("user_identity_missing")
            return
        if uid not in affected:
            skip("user_not_in_affected_population")
            return
        if strict:
            if row.get("server_correct") is not True:
                skip("server_correctness_not_proven")
                return
            if row.get("incident_route") != NORMAL_ADVENTURE_ORIGIN:
                skip("incident_route_not_proven")
                return
        elif row.get("incident_route") not in (None, NORMAL_ADVENTURE_ORIGIN):
            skip("gap_route_not_proven")
            return
        try:
            event_at = _parse_timestamp(row.get("event_at"))
        except RecoveryCandidateError:
            skip("event_time_missing_or_invalid")
            return
        if event_at < start or (end is not None and event_at >= end):
            skip("outside_incident_window")
            return
        try:
            canonical_id, legacy_id = _canonical_zone_identity(
                zone_question_identity, row.get("zone_key"), row.get("question_id")
            )
            provenance = _stable_provenance(row.get("provenance"))
        except RecoveryCandidateError as error:
            skip(str(error))
            return
        zone_key = str(row["zone_key"])
        key = (uid, canonical_id, zone_key, recovery_reason)
        if key in existing:
            evidence_class = EVIDENCE_CLASS_ALREADY_CREDITED
            apply_eligible = False
            proposed = 0
            gap_reason = GAP_REASON_ALREADY_CREDITED
        elif strict:
            evidence_class = EVIDENCE_CLASS_PROVEN_RECOVERABLE
            apply_eligible = True
            proposed = 1
            gap_reason = ""
        else:
            evidence_class = EVIDENCE_CLASS_UNRESOLVED_GAP
            apply_eligible = False
            proposed = 0
            gap_reason = GAP_REASON_CORRECTNESS_AUTHORITY_MISSING
        record = RecoveryRecord(
            user_id=uid,
            zone_key=zone_key,
            canonical_question_id=canonical_id,
            legacy_question_id=legacy_id,
            existing_credit=key in existing,
            proposed_recovery_credit=proposed,
            recovery_reason=recovery_reason,
            operation_id=operation_id,
            provenance=provenance,
            evidence_class=evidence_class,
            apply_eligible=apply_eligible,
            gap_reason=gap_reason,
        )
        prior = records.get(key)
        if prior is None:
            records[key] = record
            return
        # A strict, explicit server result outranks a historical unresolved
        # inventory row for the same canonical pair.  Already-credited always
        # remains non-applicable.
        rank = {
            EVIDENCE_CLASS_UNRESOLVED_GAP: 0,
            EVIDENCE_CLASS_ALREADY_CREDITED: 1,
            EVIDENCE_CLASS_PROVEN_RECOVERABLE: 2,
        }
        if rank[record.evidence_class] > rank[prior.evidence_class]:
            records[key] = record
        else:
            skip("duplicate_evidence_deduplicated")

    for row in evidence_rows:
        if isinstance(row, Mapping):
            add_row(row, strict=True)
        else:
            skip("row_not_mapping")
    for row in gap_rows:
        if isinstance(row, Mapping):
            add_row(row, strict=False)
        else:
            skip("row_not_mapping")

    ordered = tuple(records[key] for key in sorted(records))
    return {
        "records": ordered,
        "strict_proven_records": tuple(
            record
            for record in ordered
            if record.evidence_class == EVIDENCE_CLASS_PROVEN_RECOVERABLE
        ),
        "owner_policy_gap_records": tuple(
            record
            for record in ordered
            if record.evidence_class == EVIDENCE_CLASS_UNRESOLVED_GAP
        ),
        "already_credited_records": tuple(
            record
            for record in ordered
            if record.evidence_class == EVIDENCE_CLASS_ALREADY_CREDITED
        ),
        "skipped": dict(sorted(skipped.items())),
        "incident_start": start.isoformat(timespec="seconds"),
        "incident_end": None if end is None else end.isoformat(timespec="seconds"),
        "affected_user_count": len(affected),
    }


def build_owner_policy_recovery_set(
    inventory_rows: Iterable[Mapping[str, Any]],
    *,
    identity_rows: Iterable[Mapping[str, Any]] | None = None,
    affected_user_ids: Iterable[Any] | None = None,
    incident_start: Any,
    incident_end: Any | None,
    operation_id: str,
) -> dict[str, Any]:
    """Build the Owner-approved make-whole set from a frozen decision inventory.

    This function consumes classification already established by Lane C.  It
    does not inspect ``grade`` or ``source_context`` and it never promotes an
    identity-unresolved row.  The Owner policy changes only the treatment of
    the exact ``CORRECTNESS_AUTHORITY_MISSING`` class: one additive credit per
    unique ``(user_id, canonical_question_id)`` pair.
    """

    operation_id = str(operation_id or "").strip()
    if not operation_id:
        raise RecoveryCandidateError("operation_id is required")
    start, end = _timestamp_bounds(incident_start, incident_end)
    affected = None if affected_user_ids is None else {int(uid) for uid in affected_user_ids}
    records: dict[tuple[int, str], RecoveryRecord] = {}
    pair_zones: dict[tuple[int, str], str] = {}
    skipped: dict[str, int] = {}
    already_excluded = 0
    identity_excluded = 0
    duplicate_excluded = 0

    def skip(reason: str) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1

    def integer_flag(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        try:
            return bool(int(value or 0))
        except (TypeError, ValueError):
            return False

    for row in inventory_rows:
        if not isinstance(row, Mapping):
            skip("row_not_mapping")
            continue
        try:
            uid = int(row["user_id"])
        except (KeyError, TypeError, ValueError):
            skip("user_identity_missing")
            continue
        if affected is not None and uid not in affected:
            skip("user_not_in_affected_population")
            continue
        evidence_class = str(row.get("evidence_class") or "")
        gap_reason = str(row.get("gap_reason") or "")
        if evidence_class == EVIDENCE_CLASS_ALREADY_CREDITED or integer_flag(row.get("existing_credit")):
            already_excluded += 1
            continue
        if evidence_class != EVIDENCE_CLASS_UNRESOLVED_GAP or gap_reason != GAP_REASON_CORRECTNESS_AUTHORITY_MISSING:
            if gap_reason == GAP_REASON_CANONICAL_IDENTITY_UNRESOLVED or not str(row.get("canonical_question_id") or "").strip():
                identity_excluded += 1
            else:
                skip("row_not_owner_policy_class")
            continue
        canonical = str(row.get("canonical_question_id") or "").strip()
        if not canonical:
            identity_excluded += 1
            continue
        zone_key = str(row.get("zone_key") or "").strip()
        if not zone_key:
            skip("zone_identity_missing")
            continue
        try:
            legacy_id = int(row["legacy_question_id"] if "legacy_question_id" in row else row["question_id"])
        except (KeyError, TypeError, ValueError):
            skip("legacy_question_identity_missing")
            continue
        event_at = row.get("event_at") or row.get("first_event_at")
        try:
            parsed_event = _parse_timestamp(event_at)
        except RecoveryCandidateError:
            skip("event_time_missing_or_invalid")
            continue
        if parsed_event < start or (end is not None and parsed_event >= end):
            skip("outside_incident_window")
            continue
        try:
            provenance = _stable_provenance(row.get("provenance"))
        except RecoveryCandidateError:
            skip("provenance_missing")
            continue
        key = (uid, canonical)
        prior_zone = pair_zones.get(key)
        if prior_zone is not None and prior_zone != zone_key:
            raise RecoveryCandidateError("canonical pair maps to multiple Zones")
        if key in records:
            duplicate_excluded += 1
            continue
        pair_zones[key] = zone_key
        records[key] = RecoveryRecord(
            user_id=uid,
            zone_key=zone_key,
            canonical_question_id=canonical,
            legacy_question_id=legacy_id,
            existing_credit=False,
            proposed_recovery_credit=1,
            recovery_reason=OWNER_POLICY_REASON,
            operation_id=operation_id,
            provenance=provenance,
            evidence_class=EVIDENCE_CLASS_UNRESOLVED_GAP,
            apply_eligible=True,
            gap_reason=GAP_REASON_CORRECTNESS_AUTHORITY_MISSING,
            policy_classification=POLICY_CLASSIFICATION_CORRECTNESS_AUTHORITY_MISSING,
            credit_delta=1,
            historical_correctness_status=HISTORICAL_CORRECTNESS_UNRESOLVED_DUE_TO_INCIDENT,
        )

    for row in identity_rows or ():
        if isinstance(row, Mapping):
            identity_excluded += 1
        else:
            skip("identity_row_not_mapping")

    ordered = tuple(records[key] for key in sorted(records))
    return {
        "records": ordered,
        "policy_records": ordered,
        "preliminary_policy_users": len({record.user_id for record in ordered}),
        "preliminary_policy_pairs": len(ordered),
        "already_credited_excluded": already_excluded,
        "identity_unresolved_excluded": identity_excluded,
        "duplicate_pairs_excluded": duplicate_excluded,
        "skipped": dict(sorted(skipped.items())),
        "incident_start": start.isoformat(timespec="seconds"),
        "incident_end": None if end is None else end.isoformat(timespec="seconds"),
        "affected_user_count": None if affected is None else len(affected),
    }


def build_recovery_package(
    candidate_result: Mapping[str, Any],
    *,
    operation_id: str,
    recovery_reason: str = RECOVERY_REASON,
) -> dict[str, Any]:
    """Serialize and hash a candidate package without any database write."""

    records = [
        record.as_package_dict()
        if isinstance(record, RecoveryRecord)
        else dict(record)
        for record in candidate_result.get("records", ())
    ]
    records.sort(
        key=lambda row: (
            int(row["user_id"]),
            str(row["zone_key"]),
            str(row["canonical_question_id"]),
        )
    )
    strict_records = [
        row for row in records if row.get("evidence_class") == EVIDENCE_CLASS_PROVEN_RECOVERABLE
    ]
    gap_records = [
        row for row in records if row.get("evidence_class") == EVIDENCE_CLASS_UNRESOLVED_GAP
    ]
    already_records = [
        row for row in records if row.get("evidence_class") == EVIDENCE_CLASS_ALREADY_CREDITED
    ]
    core = {
        "package_version": "p0-lane-c-adventure-recovery-v1",
        "operation_id": str(operation_id),
        "recovery_reason": str(recovery_reason),
        "incident_start": candidate_result.get("incident_start"),
        "incident_end": candidate_result.get("incident_end"),
        "records": records,
    }
    encoded = json.dumps(
        core, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    strict_core = {**core, "records": strict_records}
    gap_core = {**core, "records": gap_records}
    return {
        **core,
        "record_count": len(records),
        "already_credited_count": len(
            candidate_result.get(
                "already_credited",
                candidate_result.get("already_credited_records", ()),
            )
        ),
        "skipped": dict(candidate_result.get("skipped", {})),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "strict_proven_record_count": len(strict_records),
        "strict_proven_sha256": hashlib.sha256(
            json.dumps(strict_core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "owner_policy_gap_record_count": len(gap_records),
        "owner_policy_gap_sha256": hashlib.sha256(
            json.dumps(gap_core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "already_credited_record_count": len(already_records),
    }


def build_owner_policy_package(
    candidate_result: Mapping[str, Any],
    *,
    operation_id: str,
    incident_start: Any,
    incident_end: Any | None,
) -> dict[str, Any]:
    """Serialize and hash the Owner-policy package deterministically."""

    records = [
        record.as_package_dict()
        if isinstance(record, RecoveryRecord)
        else dict(record)
        for record in candidate_result.get("policy_records", candidate_result.get("records", ()))
    ]
    records.sort(key=lambda row: (int(row["user_id"]), str(row["canonical_question_id"])))
    for row in records:
        if (
            row.get("evidence_class") != EVIDENCE_CLASS_UNRESOLVED_GAP
            or row.get("gap_reason") != GAP_REASON_CORRECTNESS_AUTHORITY_MISSING
            or row.get("policy_classification") != POLICY_CLASSIFICATION_CORRECTNESS_AUTHORITY_MISSING
            or row.get("historical_correctness_status") != HISTORICAL_CORRECTNESS_UNRESOLVED_DUE_TO_INCIDENT
            or int(row.get("credit_delta", 0)) != 1
            or int(row.get("proposed_recovery_credit", 0)) != 1
            or not row.get("apply_eligible")
        ):
            raise RecoveryCandidateError("Owner-policy package contains a non-policy row")
    core = {
        "package_version": "p0-lane-c-owner-policy-recovery-v1",
        "operation_id": str(operation_id),
        "recovery_reason": OWNER_POLICY_REASON,
        "policy_classification": POLICY_CLASSIFICATION_CORRECTNESS_AUTHORITY_MISSING,
        "historical_correctness_status": HISTORICAL_CORRECTNESS_UNRESOLVED_DUE_TO_INCIDENT,
        "incident_start": _boundary_text(incident_start),
        "incident_end": _boundary_text(incident_end),
        "records": records,
    }
    encoded = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        **core,
        "record_count": len(records),
        "user_count": len({int(row["user_id"]) for row in records}),
        "package_sha256": hashlib.sha256(encoded).hexdigest(),
        "already_credited_excluded": int(candidate_result.get("already_credited_excluded", 0)),
        "identity_unresolved_excluded": int(candidate_result.get("identity_unresolved_excluded", 0)),
        "duplicate_pairs_excluded": int(candidate_result.get("duplicate_pairs_excluded", 0)),
        "skipped": dict(candidate_result.get("skipped", {})),
    }


def write_recovery_records(conn: Any, records: Iterable[RecoveryRecord]) -> dict[str, int]:
    """Insert strict or Owner-policy records idempotently.

    The caller owns the transaction.  For Owner-policy rows the ledger itself
    is the additive progression authority; no separate progress mutation is
    performed.
    """

    ordered = tuple(records)
    for record in ordered:
        if not isinstance(record, RecoveryRecord):
            raise RecoveryCandidateError("write_recovery_records requires RecoveryRecord values")
        is_strict = (
            record.evidence_class == EVIDENCE_CLASS_PROVEN_RECOVERABLE
            and record.apply_eligible is True
            and record.existing_credit is False
            and record.proposed_recovery_credit == 1
        )
        is_owner_policy = (
            record.evidence_class == EVIDENCE_CLASS_UNRESOLVED_GAP
            and record.gap_reason == GAP_REASON_CORRECTNESS_AUTHORITY_MISSING
            and record.policy_classification == POLICY_CLASSIFICATION_CORRECTNESS_AUTHORITY_MISSING
            and record.historical_correctness_status == HISTORICAL_CORRECTNESS_UNRESOLVED_DUE_TO_INCIDENT
            and record.apply_eligible is True
            and record.existing_credit is False
            and record.proposed_recovery_credit == 1
            and record.credit_delta == 1
            and record.recovery_reason == OWNER_POLICY_REASON
        )
        if not (is_strict or is_owner_policy):
            raise RecoveryCandidateError("only new proposed recovery credits may be written")
        if not record.provenance.strip():
            raise RecoveryCandidateError("provenance is required")
    inserted = 0
    duplicates = 0
    for record in ordered:
        result = conn.execute(
            f"""INSERT INTO {TABLE_NAME}(
                    operation_id,user_id,canonical_question_id,legacy_question_id,
                    zone_key,recovery_reason,provenance,evidence_class,gap_reason,apply_eligible,
                    existing_credit,proposed_recovery_credit,policy_classification,
                    credit_delta,historical_correctness_status,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT DO NOTHING""",
            (
                record.operation_id,
                record.user_id,
                record.canonical_question_id,
                record.legacy_question_id,
                record.zone_key,
                record.recovery_reason,
                record.provenance,
                record.evidence_class,
                record.gap_reason,
                1 if record.apply_eligible else 0,
                1 if record.existing_credit else 0,
                record.proposed_recovery_credit,
                record.policy_classification,
                record.credit_delta,
                record.historical_correctness_status,
                _datetime.datetime.now(_datetime.timezone.utc).isoformat(),
            ),
        )
        if getattr(result, "rowcount", 0) == 1:
            inserted += 1
        else:
            duplicates += 1
    return {"inserted": inserted, "duplicates": duplicates}


def write_owner_policy_records(conn: Any, records: Iterable[RecoveryRecord]) -> dict[str, int]:
    """Write only Owner-policy rows; transaction ownership remains with caller."""

    ordered = tuple(records)
    for record in ordered:
        if not isinstance(record, RecoveryRecord):
            raise RecoveryCandidateError("write_owner_policy_records requires RecoveryRecord values")
        if not (
            record.evidence_class == EVIDENCE_CLASS_UNRESOLVED_GAP
            and record.gap_reason == GAP_REASON_CORRECTNESS_AUTHORITY_MISSING
            and record.policy_classification == POLICY_CLASSIFICATION_CORRECTNESS_AUTHORITY_MISSING
            and record.historical_correctness_status == HISTORICAL_CORRECTNESS_UNRESOLVED_DUE_TO_INCIDENT
            and record.recovery_reason == OWNER_POLICY_REASON
            and record.apply_eligible is True
            and record.credit_delta == 1
            and record.proposed_recovery_credit == 1
            and record.existing_credit is False
        ):
            raise RecoveryCandidateError("only Owner-policy correctness-gap rows may be written")
    return write_recovery_records(conn, ordered)


def write_decision_records(conn: Any, records: Iterable[RecoveryRecord]) -> dict[str, int]:
    """Persist a complete decision inventory in a disposable/test ledger.

    This function is intentionally separate from ``write_recovery_records``:
    unresolved and already-credited rows are auditable inventory only and are
    never accepted by the production-applicable writer.
    """

    ordered = tuple(records)
    for record in ordered:
        if not isinstance(record, RecoveryRecord):
            raise RecoveryCandidateError("write_decision_records requires RecoveryRecord values")
        if not record.provenance.strip():
            raise RecoveryCandidateError("provenance is required")
    inserted = 0
    duplicates = 0
    for record in ordered:
        result = conn.execute(
            f"""INSERT INTO {TABLE_NAME}(
                    operation_id,user_id,canonical_question_id,legacy_question_id,
                    zone_key,recovery_reason,provenance,evidence_class,gap_reason,apply_eligible,
                    existing_credit,proposed_recovery_credit,policy_classification,
                    credit_delta,historical_correctness_status,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT DO NOTHING""",
            (
                record.operation_id,
                record.user_id,
                record.canonical_question_id,
                record.legacy_question_id,
                record.zone_key,
                record.recovery_reason,
                record.provenance,
                record.evidence_class,
                record.gap_reason,
                1 if record.apply_eligible else 0,
                1 if record.existing_credit else 0,
                record.proposed_recovery_credit,
                record.policy_classification,
                record.credit_delta,
                record.historical_correctness_status,
                _datetime.datetime.now(_datetime.timezone.utc).isoformat(),
            ),
        )
        if getattr(result, "rowcount", 0) == 1:
            inserted += 1
        else:
            duplicates += 1
    return {"inserted": inserted, "duplicates": duplicates}


def rollback_operation(conn: Any, operation_id: str) -> int:
    """Delete only one exact recovery operation; caller owns commit/rollback."""

    operation_id = str(operation_id or "").strip()
    if not operation_id:
        raise RecoveryCandidateError("operation_id is required for rollback")
    result = conn.execute(
        f"DELETE FROM {TABLE_NAME} WHERE operation_id=?", (operation_id,)
    )
    return int(getattr(result, "rowcount", 0) or 0)


def rollback_owner_policy_operation(conn: Any, operation_id: str) -> int:
    """Rollback only one exact Owner-policy operation."""

    operation_id = str(operation_id or "").strip()
    if not operation_id:
        raise RecoveryCandidateError("operation_id is required for Owner-policy rollback")
    result = conn.execute(
        f"DELETE FROM {TABLE_NAME} WHERE operation_id=? AND recovery_reason=? "
        "AND policy_classification=?",
        (
            operation_id,
            OWNER_POLICY_REASON,
            POLICY_CLASSIFICATION_CORRECTNESS_AUTHORITY_MISSING,
        ),
    )
    return int(getattr(result, "rowcount", 0) or 0)


def owner_policy_reward_deltas() -> dict[str, int]:
    """Return the hard zero-delta reward boundary for policy recovery."""

    return {
        "coins": 0,
        "xp": 0,
        "stars": 0,
        "lord_defeat": 0,
        "zone_clear": 0,
        "first_clear": 0,
        "first_clear_reward": 0,
        "leaderboard_reward": 0,
        "event_achievement": 0,
        "boss_settlement": 0,
        "quest_reward": 0,
    }


def build_owner_policy_progression_dry_run(
    current_progress_by_user_zone: Mapping[Any, Any],
    records: Iterable[RecoveryRecord | Mapping[str, Any]],
    *,
    zone_thresholds: Mapping[str, int],
) -> dict[str, Any]:
    """Calculate additive progress/threshold effects without writing state."""

    current: dict[tuple[int, str], int] = {}
    for key, value in current_progress_by_user_zone.items():
        if isinstance(key, tuple) and len(key) == 2:
            uid, zone = key
        else:
            uid, zone = str(key).split("|", 1)
        current[(int(uid), str(zone))] = int(value or 0)
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for record in records:
        row = record.as_package_dict() if isinstance(record, RecoveryRecord) else dict(record)
        pair = (int(row["user_id"]), str(row["canonical_question_id"]))
        if pair in seen:
            continue
        seen.add(pair)
        normalized.append(row)
    deltas: dict[tuple[int, str], int] = {}
    for row in normalized:
        key = (int(row["user_id"]), str(row["zone_key"]))
        deltas[key] = deltas.get(key, 0) + int(row.get("credit_delta", row.get("proposed_recovery_credit", 0)))
    crossers: set[int] = set()
    per_zone: dict[str, dict[str, int]] = {}
    for zone, threshold in zone_thresholds.items():
        zone_rows = {key: value for key, value in deltas.items() if key[1] == str(zone)}
        users = {key[0] for key in zone_rows}
        zone_crossers = 0
        for uid in users:
            before = current.get((uid, str(zone)), 0)
            after = before + zone_rows[(uid, str(zone))]
            if before < int(threshold) <= after:
                crossers.add(uid)
                zone_crossers += 1
        per_zone[str(zone)] = {
            "pairs_gaining_progress": sum(zone_rows.values()),
            "users_gaining_progress": len(users),
            "players_crossing_lord_threshold": zone_crossers,
            "max_progress_delta": max(zone_rows.values(), default=0),
        }
    return {
        "users_gaining_progress": len({int(row["user_id"]) for row in normalized}),
        "pairs_gaining_progress": len(normalized),
        "total_progress_delta": sum(deltas.values()),
        "players_crossing_lord_threshold": len(crossers),
        "per_zone": per_zone,
        "reward_deltas": owner_policy_reward_deltas(),
        "lord_defeated_delta": 0,
        "zone_clear_delta": 0,
        "star_grant_delta": 0,
    }


def build_owner_policy_reported_player_dry_run(
    username: str,
    user_authority: Iterable[Mapping[str, Any]],
    current_progress_by_user_zone: Mapping[Any, Any],
    records: Iterable[RecoveryRecord | Mapping[str, Any]],
    *,
    zone_key: str,
    lord_threshold: int,
) -> dict[str, Any]:
    """Resolve one reported player by username and calculate policy-only state."""

    matches = [
        row
        for row in user_authority
        if str(row.get("username") or "") == str(username)
    ]
    if len(matches) != 1:
        raise RecoveryCandidateError("reported username does not resolve uniquely")
    if bool(matches[0].get("is_admin")):
        raise RecoveryCandidateError("reported username resolves to an admin")
    user_id = int(matches[0]["user_id"])
    current = 0
    for key, value in current_progress_by_user_zone.items():
        if isinstance(key, tuple) and len(key) == 2:
            uid, zone = key
        else:
            uid, zone = str(key).split("|", 1)
        if int(uid) == user_id and str(zone) == str(zone_key):
            current = int(value or 0)
            break
    policy_pairs = {
        str((record.as_package_dict() if isinstance(record, RecoveryRecord) else record)["canonical_question_id"])
        for record in records
        if int((record.as_package_dict() if isinstance(record, RecoveryRecord) else record)["user_id"]) == user_id
        and str((record.as_package_dict() if isinstance(record, RecoveryRecord) else record)["zone_key"]) == str(zone_key)
    }
    post = current + len(policy_pairs)
    return {
        "username": str(username),
        "user_id": user_id,
        "zone_key": str(zone_key),
        "current_progress": current,
        "policy_pair_count": len(policy_pairs),
        "post_policy_progress": post,
        "lord_threshold": int(lord_threshold),
        "can_challenge_lord": post >= int(lord_threshold),
        "lord_defeated": False,
        "coins_delta": 0,
        "xp_delta": 0,
        "star_delta": 0,
    }


def recovery_question_ids(conn: Any, user_id: int) -> set[int]:
    """Read only the additive legacy aliases needed by the existing consumer."""

    if not _table_exists(conn):
        return set()
    rows = conn.execute(
        f"""SELECT DISTINCT legacy_question_id
               FROM {TABLE_NAME}
              WHERE user_id=? AND apply_eligible=1""",
        (int(user_id),),
    ).fetchall()
    return {int(row[0]) for row in rows}


def union_current_with_recovery(
    conn: Any,
    user_id: int,
    current_question_ids: Iterable[Any],
) -> set[int]:
    """Return current legitimate IDs plus explicit recovery ledger IDs."""

    return {int(value) for value in current_question_ids} | recovery_question_ids(
        conn, user_id
    )


__all__ = [
    "EVIDENCE_CLASS_ALREADY_CREDITED",
    "EVIDENCE_CLASS_PROVEN_RECOVERABLE",
    "EVIDENCE_CLASS_UNRESOLVED_GAP",
    "EVIDENCE_CLASSES",
    "GAP_REASON_ALREADY_CREDITED",
    "GAP_REASON_CANONICAL_IDENTITY_UNRESOLVED",
    "GAP_REASON_CORRECTNESS_AUTHORITY_MISSING",
    "GAP_REASONS",
    "NORMAL_ADVENTURE_ORIGIN",
    "OWNER_POLICY_REASON",
    "RECOVERY_REASON",
    "RecoveryCandidateError",
    "RecoveryRecord",
    "build_recovery_candidates",
    "build_recovery_decision_set",
    "build_owner_policy_package",
    "build_owner_policy_progression_dry_run",
    "build_owner_policy_reported_player_dry_run",
    "build_owner_policy_recovery_set",
    "build_recovery_package",
    "recovery_question_ids",
    "rollback_operation",
    "rollback_owner_policy_operation",
    "owner_policy_reward_deltas",
    "union_current_with_recovery",
    "write_owner_policy_records",
    "write_recovery_records",
    "write_decision_records",
]
