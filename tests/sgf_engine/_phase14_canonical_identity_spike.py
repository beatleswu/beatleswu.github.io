"""Test-local canonical puzzle identity implementation spike.

This module deliberately has no production runtime integration. It models the
smallest persistence boundary needed to test future canonical identity rules.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4


@dataclass(frozen=True)
class CanonicalPuzzleIdentityInput:
    """An ingestion-like row whose metadata is not canonical identity."""

    record_key: str
    source_path: str | None = None
    fixture_path: str | None = None
    gold_fixture_id: str | None = None
    content_sha256: str | None = None


def _validated_uuid4(value: object, *, context: str) -> str:
    try:
        parsed = value if isinstance(value, UUID) else UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{context} must be a valid UUID v4") from exc

    if parsed.version != 4:
        raise ValueError(f"{context} must be a valid UUID v4")

    return str(parsed)


def assign_canonical_puzzle_ids(
    records: Iterable[CanonicalPuzzleIdentityInput],
    existing_mapping: Mapping[str, str | UUID] | None = None,
    uuid_factory: Callable[[], str | UUID] | None = None,
) -> dict[str, str]:
    """Assign UUID v4 identities by stable record key.

    Existing assignments are retained. Metadata fields never participate in
    assignment, comparison, or lookup.
    """

    mapping: dict[str, str] = {}
    canonical_ids: set[str] = set()

    for record_key, canonical_puzzle_id in (existing_mapping or {}).items():
        validated_id = _validated_uuid4(
            canonical_puzzle_id,
            context=f"canonical_puzzle_id for {record_key!r}",
        )
        if validated_id in canonical_ids:
            raise ValueError(
                f"duplicate canonical_puzzle_id in existing mapping: {validated_id}"
            )
        mapping[record_key] = validated_id
        canonical_ids.add(validated_id)

    records_by_key: dict[str, CanonicalPuzzleIdentityInput] = {}
    for record in records:
        if record.record_key in records_by_key:
            raise ValueError(f"duplicate record_key: {record.record_key!r}")
        records_by_key[record.record_key] = record

    make_uuid = uuid_factory or uuid4
    for record_key in records_by_key:
        if record_key in mapping:
            continue

        canonical_puzzle_id = _validated_uuid4(
            make_uuid(),
            context=f"generated canonical_puzzle_id for {record_key!r}",
        )
        if canonical_puzzle_id in canonical_ids:
            raise ValueError(
                f"duplicate canonical_puzzle_id generated: {canonical_puzzle_id}"
            )
        mapping[record_key] = canonical_puzzle_id
        canonical_ids.add(canonical_puzzle_id)

    return mapping


def dump_identity_mapping(mapping: Mapping[str, str | UUID], path: Path) -> None:
    """Write a deterministic, UTF-8, LF-only test mapping."""

    validated = {
        record_key: _validated_uuid4(
            canonical_puzzle_id,
            context=f"canonical_puzzle_id for {record_key!r}",
        )
        for record_key, canonical_puzzle_id in mapping.items()
    }
    content = json.dumps(
        validated,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    path.write_bytes(f"{content}\n".encode("utf-8"))


def load_identity_mapping(path: Path) -> dict[str, str]:
    """Load and validate a mapping written by ``dump_identity_mapping``."""

    raw_mapping = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_mapping, dict):
        raise ValueError("identity mapping must be a JSON object")

    mapping: dict[str, str] = {}
    canonical_ids: set[str] = set()
    for record_key, canonical_puzzle_id in raw_mapping.items():
        if not isinstance(record_key, str):
            raise ValueError("identity mapping keys must be strings")
        validated_id = _validated_uuid4(
            canonical_puzzle_id,
            context=f"canonical_puzzle_id for {record_key!r}",
        )
        if validated_id in canonical_ids:
            raise ValueError(f"duplicate canonical_puzzle_id: {validated_id}")
        mapping[record_key] = validated_id
        canonical_ids.add(validated_id)

    return mapping
