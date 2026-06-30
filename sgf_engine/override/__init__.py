"""Variation override package."""

from .override_identity import build_override_index, find_override
from .override_loader_integration import (
    build_loader_override_index,
    lookup_loader_runtime_override,
)
from .override_runtime import (
    adapt_override_record_for_engine,
    lookup_active_runtime_override,
)
from .override_schema import (
    OverrideRecord,
    RUNTIME_DISABLED,
    RUNTIME_ENABLED,
    validate_override_record,
    validate_override_records,
)

__all__ = [
    "OverrideRecord",
    "RUNTIME_DISABLED",
    "RUNTIME_ENABLED",
    "adapt_override_record_for_engine",
    "build_override_index",
    "build_loader_override_index",
    "find_override",
    "lookup_loader_runtime_override",
    "lookup_active_runtime_override",
    "validate_override_record",
    "validate_override_records",
]
