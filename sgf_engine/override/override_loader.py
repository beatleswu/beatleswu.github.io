"""Load and resolve explicit puzzle variation exceptions."""

from __future__ import annotations

import copy
import json
from pathlib import Path


OVERRIDES_FILE = (
    Path(__file__).resolve().parents[2] / "puzzle_variation_overrides.json"
)


def _normalize_source(source: str) -> str:
    if not isinstance(source, str):
        raise ValueError("source must be a string.")
    return source.replace("\\", "/").strip()


def _validate_entry(source: str, entry: object) -> dict:
    if not isinstance(entry, dict):
        raise ValueError(f"Override entry for {source!r} must be an object.")

    equivalents = entry.get("equivalent_moves", {})
    if not isinstance(equivalents, dict):
        raise ValueError(
            f"Override equivalent_moves for {source!r} must be an object."
        )

    seen_alternatives: dict[str, str] = {}
    for canonical, alternatives in equivalents.items():
        if not isinstance(canonical, str) or not isinstance(alternatives, list):
            raise ValueError(
                f"Override equivalent_moves for {source!r} must map strings to lists."
            )
        for alternative in alternatives:
            if not isinstance(alternative, str):
                raise ValueError(
                    f"Override alternatives for {source!r} must be strings."
                )
            previous = seen_alternatives.get(alternative)
            if previous is not None and previous != canonical:
                raise ValueError(
                    f"Equivalent move {alternative!r} maps to multiple canonical moves."
                )
            seen_alternatives[alternative] = canonical

    return entry


def load_override(source: str) -> dict | None:
    """Return the normalized-source override entry, or ``None``."""
    normalized_source = _normalize_source(source)
    with OVERRIDES_FILE.open("r", encoding="utf-8") as handle:
        document = json.load(handle)

    if not isinstance(document, dict):
        raise ValueError("puzzle_variation_overrides.json must contain an object.")

    normalized_document: dict[str, object] = {}
    for key, value in document.items():
        if not isinstance(key, str):
            raise ValueError("Override source keys must be strings.")
        normalized_key = _normalize_source(key)
        if normalized_key in normalized_document:
            raise ValueError(f"Duplicate normalized override source: {normalized_key}")
        normalized_document[normalized_key] = value

    entry = normalized_document.get(normalized_source)
    if entry is None:
        return None
    return copy.deepcopy(_validate_entry(normalized_source, entry))


def canonical_coord_for(override: dict, equivalent_coord: str) -> str:
    """Resolve one declared equivalent coordinate to its canonical SGF coordinate."""
    equivalents = override.get("equivalent_moves") or {}
    matches = [
        canonical
        for canonical, alternatives in equivalents.items()
        if equivalent_coord in alternatives
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Override has no unique canonical move for {equivalent_coord}."
        )
    return matches[0]

