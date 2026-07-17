"""Read-only canonical puzzle identity resolution.

The alias table is the only canonical mapping source.  This module never
creates aliases and never derives identity from a route, mode, file, or
content fingerprint.
"""

from dataclasses import dataclass
from typing import Optional
import re
import uuid


@dataclass(frozen=True)
class IdentityResolution:
    """The fail-safe result of a canonical identity lookup."""

    canonical_puzzle_id: Optional[str]
    invalid_identity: bool


_INTEGER_RE = re.compile(r"-?\d+\Z")


def _coerce_integer(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if _INTEGER_RE.fullmatch(candidate):
            try:
                return int(candidate)
            except ValueError:
                return None
    return None


def _valid_uuid4(value):
    try:
        candidate = str(value).strip()
    except (AttributeError, TypeError, ValueError):
        return None
    try:
        parsed = uuid.UUID(candidate)
    except (AttributeError, TypeError, ValueError):
        return None
    canonical = str(parsed)
    if (
        parsed.version != 4
        or parsed.variant != uuid.RFC_4122
        or candidate != canonical
    ):
        return None
    return canonical


def _row_canonical_puzzle_id(row):
    try:
        return row["canonical_puzzle_id"]
    except (KeyError, TypeError, IndexError):
        try:
            return row[0]
        except (KeyError, TypeError, IndexError):
            return None


def _invalid_resolution():
    return IdentityResolution(canonical_puzzle_id=None, invalid_identity=True)


def resolve_puzzle_identity(
    connection_factory,
    *,
    record_index=None,
    legacy_question_id=None,
):
    """Resolve one immutable alias without writing or lazily creating it.

    When both key parts are supplied, only that exact composite alias may
    resolve.  When only ``legacy_question_id`` is available, a bounded lookup
    accepts it only if exactly one alias row exists.  Missing, ambiguous,
    malformed, and failed lookups all fail closed.
    """

    legacy_id = _coerce_integer(legacy_question_id)
    if legacy_id is None:
        return _invalid_resolution()

    exact_lookup = record_index is not None
    record = _coerce_integer(record_index) if exact_lookup else None
    if exact_lookup and (record is None or record < 0):
        return _invalid_resolution()

    if exact_lookup:
        statement = """
            SELECT canonical_puzzle_id
              FROM puzzle_identity_alias
             WHERE record_index=? AND legacy_question_id=?
             LIMIT 2
        """
        parameters = (record, legacy_id)
    else:
        statement = """
            SELECT canonical_puzzle_id
              FROM puzzle_identity_alias
             WHERE legacy_question_id=?
             LIMIT 2
        """
        parameters = (legacy_id,)

    try:
        with connection_factory() as connection:
            rows = connection.execute(statement, parameters).fetchall()
    except Exception:
        return _invalid_resolution()

    try:
        if len(rows) != 1:
            return _invalid_resolution()
        canonical_id = _valid_uuid4(_row_canonical_puzzle_id(rows[0]))
    except Exception:
        return _invalid_resolution()
    if canonical_id is None:
        return _invalid_resolution()
    return IdentityResolution(
        canonical_puzzle_id=canonical_id,
        invalid_identity=False,
    )
