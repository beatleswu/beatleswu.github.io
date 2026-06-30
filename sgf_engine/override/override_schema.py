"""Override identity metadata contract and schema validation."""

from __future__ import annotations

from dataclasses import dataclass
from string import hexdigits


RUNTIME_ENABLED = "enabled"
RUNTIME_DISABLED = "disabled"
RUNTIME_STATUSES = frozenset({RUNTIME_ENABLED, RUNTIME_DISABLED})


def _require_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value.strip()


def normalize_source_path(value: object) -> str:
    source_path = _require_non_empty_string(value, "source_path")
    return source_path.replace("\\", "/")


def normalize_sgf_sha256(value: object) -> str:
    digest = _require_non_empty_string(value, "sgf_sha256").lower()
    if len(digest) != 64 or any(char not in hexdigits for char in digest):
        raise ValueError("sgf_sha256 must be a 64-character hex string.")
    return digest


def _normalize_external_ref(record: dict[str, object]) -> str | None:
    external_ref = record.get("external_ref")
    gold_fixture_id = record.get("gold_fixture_id")

    if external_ref is None and gold_fixture_id is None:
        return None

    if external_ref is None:
        return _require_non_empty_string(gold_fixture_id, "gold_fixture_id")

    normalized_external_ref = _require_non_empty_string(external_ref, "external_ref")
    if gold_fixture_id is None:
        return normalized_external_ref

    normalized_gold_fixture_id = _require_non_empty_string(
        gold_fixture_id,
        "gold_fixture_id",
    )
    if normalized_external_ref != normalized_gold_fixture_id:
        raise ValueError("external_ref and gold_fixture_id must match when both exist.")
    return normalized_external_ref


def _validate_equivalent_moves(value: object) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, dict):
        raise ValueError("equivalent_moves must be an object.")

    normalized: dict[str, tuple[str, ...]] = {}
    seen_alternatives: dict[str, str] = {}

    for canonical, alternatives in value.items():
        canonical_coord = _require_non_empty_string(canonical, "equivalent_moves key")
        if not isinstance(alternatives, list) or not alternatives:
            raise ValueError(
                "equivalent_moves must map each canonical move to a non-empty list."
            )

        normalized_alternatives: list[str] = []
        for alternative in alternatives:
            alternative_coord = _require_non_empty_string(
                alternative,
                "equivalent_moves alternative",
            )
            if alternative_coord == canonical_coord:
                raise ValueError(
                    "equivalent_moves alternatives must differ from the canonical move."
                )
            previous = seen_alternatives.get(alternative_coord)
            if previous is not None and previous != canonical_coord:
                raise ValueError(
                    "equivalent_moves alternatives must map to a single canonical move."
                )
            seen_alternatives[alternative_coord] = canonical_coord
            normalized_alternatives.append(alternative_coord)

        normalized[canonical_coord] = tuple(normalized_alternatives)

    return normalized


@dataclass(frozen=True, slots=True)
class OverrideRecord:
    puzzle_id: str
    puzzle_version_id: str
    sgf_sha256: str
    equivalent_moves: dict[str, tuple[str, ...]]
    runtime_status: str
    apply_automatically: bool
    external_ref: str | None = None
    source_path: str | None = None


def validate_override_record(record: object) -> OverrideRecord:
    if not isinstance(record, dict):
        raise ValueError("override record must be an object.")

    runtime_status = _require_non_empty_string(
        record.get("runtime_status"),
        "runtime_status",
    )
    if runtime_status not in RUNTIME_STATUSES:
        raise ValueError("runtime_status must be 'enabled' or 'disabled'.")

    apply_automatically = record.get("apply_automatically")
    if not isinstance(apply_automatically, bool):
        raise ValueError("apply_automatically must be a boolean.")

    source_path = record.get("source_path")
    normalized_source_path = (
        None if source_path is None else normalize_source_path(source_path)
    )

    return OverrideRecord(
        puzzle_id=_require_non_empty_string(record.get("puzzle_id"), "puzzle_id"),
        puzzle_version_id=_require_non_empty_string(
            record.get("puzzle_version_id"),
            "puzzle_version_id",
        ),
        sgf_sha256=normalize_sgf_sha256(record.get("sgf_sha256")),
        equivalent_moves=_validate_equivalent_moves(record.get("equivalent_moves")),
        runtime_status=runtime_status,
        apply_automatically=apply_automatically,
        external_ref=_normalize_external_ref(record),
        source_path=normalized_source_path,
    )


def validate_override_records(records: object) -> tuple[OverrideRecord, ...]:
    if not isinstance(records, list):
        raise ValueError("override records document must be a list.")
    return tuple(validate_override_record(record) for record in records)
