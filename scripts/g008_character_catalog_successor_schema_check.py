"""Read-only Postgres schema and roster check for the G008 successor image."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import get_db
from future30_character_registry import (
    FUTURE30_CHARACTER_REGISTRY_VALID,
    FUTURE30_C005_MANIFEST_SHA256,
    future30_registry_diagnostics,
)
from future30_character_service import ensure_future30_catalog
from migrations.future30_character_catalog_v1 import (
    CATALOG_TABLE,
    ENTITLEMENT_TABLE,
    VISUAL_TABLE,
    validate_schema,
)


if not FUTURE30_CHARACTER_REGISTRY_VALID:
    raise SystemExit("G008_SCHEMA_CHECK=FAIL registry_unavailable")

with get_db() as conn:
    schema = validate_schema(conn)
    if not schema["valid"]:
        raise SystemExit("G008_SCHEMA_CHECK=FAIL schema_invalid")
    catalog = ensure_future30_catalog(conn)
    counts = {
        table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in (CATALOG_TABLE, VISUAL_TABLE, ENTITLEMENT_TABLE)
    }

if counts[CATALOG_TABLE] != 30 or counts[VISUAL_TABLE] != 33:
    raise SystemExit("G008_SCHEMA_CHECK=FAIL roster_count_mismatch")
if counts[ENTITLEMENT_TABLE] != 0:
    raise SystemExit("G008_SCHEMA_CHECK=FAIL fresh_entitlement_baseline_not_empty")
if catalog["c005_manifest_sha256"] != FUTURE30_C005_MANIFEST_SHA256:
    raise SystemExit("G008_SCHEMA_CHECK=FAIL manifest_identity_mismatch")

print(json.dumps({
    "gate": "G008_SCHEMA_CHECK",
    "result": "PASS",
    "schema_valid": schema["valid"],
    "catalog_rows": counts[CATALOG_TABLE],
    "visual_rows": counts[VISUAL_TABLE],
    "entitlement_rows_before_acceptance": counts[ENTITLEMENT_TABLE],
    "primary_keys": schema["primary_key_mismatches"],
    "indexes_valid": not schema["missing_indexes"],
    "checks_valid": schema["checks_valid"],
    "manifest": FUTURE30_C005_MANIFEST_SHA256,
    "registry": future30_registry_diagnostics()["valid"],
}, sort_keys=True))
