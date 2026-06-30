"""Loader-facing integration helpers for validated runtime override payloads."""

from __future__ import annotations

from collections.abc import Mapping

from sgf_engine.override.override_identity import (
    CanonicalIdentity,
    build_override_index,
)
from sgf_engine.override.override_runtime import (
    EngineOverridePayload,
    lookup_active_runtime_override,
)
from sgf_engine.override.override_schema import (
    OverrideRecord,
    validate_override_records,
)


def build_loader_override_index(
    records_document: object,
) -> dict[CanonicalIdentity, OverrideRecord]:
    """Validate a loader-style records document and index it canonically."""
    return build_override_index(validate_override_records(records_document))


def lookup_loader_runtime_override(
    records: Mapping[CanonicalIdentity, OverrideRecord] | object,
    *,
    puzzle_id: str,
    puzzle_version_id: str,
    sgf_sha256: str,
) -> EngineOverridePayload | None:
    """Bridge loader records into the Phase 2 runtime lookup contract."""
    index = (
        records
        if isinstance(records, Mapping)
        else build_loader_override_index(records)
    )
    return lookup_active_runtime_override(
        index,
        puzzle_id=puzzle_id,
        puzzle_version_id=puzzle_version_id,
        sgf_sha256=sgf_sha256,
    )
