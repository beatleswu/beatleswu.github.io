"""Runtime boundary helpers for validated override records."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from sgf_engine.override.override_identity import (
    CanonicalIdentity,
    find_override,
)
from sgf_engine.override.override_schema import OverrideRecord


EngineOverridePayload = dict[str, dict[str, list[str]]]


def adapt_override_record_for_engine(record: OverrideRecord) -> EngineOverridePayload:
    """Convert one validated record into the engine's override payload shape."""
    return {
        "equivalent_moves": {
            canonical: list(alternatives)
            for canonical, alternatives in record.equivalent_moves.items()
        }
    }


def lookup_active_runtime_override(
    records: Mapping[CanonicalIdentity, OverrideRecord]
    | Iterable[OverrideRecord | dict[str, object]],
    *,
    puzzle_id: str,
    puzzle_version_id: str,
    sgf_sha256: str,
) -> EngineOverridePayload | None:
    """Return an engine-ready payload only for active automatic runtime overrides."""
    record = find_override(
        records,
        puzzle_id=puzzle_id,
        puzzle_version_id=puzzle_version_id,
        sgf_sha256=sgf_sha256,
    )
    if record is None or not record.apply_automatically:
        return None
    return adapt_override_record_for_engine(record)
