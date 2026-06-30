"""Canonical identity lookup helpers for override metadata records."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from sgf_engine.override.override_schema import (
    OverrideRecord,
    RUNTIME_ENABLED,
    normalize_sgf_sha256,
    validate_override_record,
)


CanonicalIdentity = tuple[str, str]


def canonical_identity_for(record: OverrideRecord) -> CanonicalIdentity:
    return (record.puzzle_id, record.puzzle_version_id)


def build_override_index(
    records: Iterable[OverrideRecord | dict[str, object]],
) -> dict[CanonicalIdentity, OverrideRecord]:
    index: dict[CanonicalIdentity, OverrideRecord] = {}

    for candidate in records:
        record = (
            candidate
            if isinstance(candidate, OverrideRecord)
            else validate_override_record(candidate)
        )
        identity = canonical_identity_for(record)
        if identity in index:
            raise ValueError(
                "duplicate override canonical identity: "
                f"{record.puzzle_id}/{record.puzzle_version_id}"
            )
        index[identity] = record

    return index


def find_override(
    records: Mapping[CanonicalIdentity, OverrideRecord]
    | Iterable[OverrideRecord | dict[str, object]],
    *,
    puzzle_id: str,
    puzzle_version_id: str,
    sgf_sha256: str,
) -> OverrideRecord | None:
    index = records if isinstance(records, Mapping) else build_override_index(records)
    record = index.get((puzzle_id, puzzle_version_id))
    if record is None:
        return None
    if record.runtime_status != RUNTIME_ENABLED:
        return None
    if record.sgf_sha256 != normalize_sgf_sha256(sgf_sha256):
        return None
    return record
