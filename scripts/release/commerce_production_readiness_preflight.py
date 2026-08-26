"""Read-only preflight auditor for the canonical Commerce release gate.

The auditor is deliberately narrower than a migration runner or a release
cutover command.  It reads PostgreSQL metadata and current source contracts,
then returns one JSON-safe report.  It never creates a table, changes a row,
commits, rolls back, enables a feature, or decides whether an Owner may run a
Production migration.

The database connection must be the repository's ``PostgresConnectionWrapper``
(or an equivalent ``execute``/``fetchall`` read-only adapter).  The wrapper is
used because the canonical migration validators use the repository's ``?``
placeholder convention.
"""

from __future__ import annotations

import argparse
import ast
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


SCHEMA_VERSION = "C031_COMMERCE_PRODUCTION_READINESS_PREFLIGHT_V1"

READY_FOR_OPTION_C_MAINTENANCE = "READY_FOR_OPTION_C_MAINTENANCE"
NOT_READY = "NOT_READY"
BLOCKED = "BLOCKED"

PASS = "PASS"
FAIL = "FAIL"
CHECK_BLOCKED = "BLOCKED"

DEFAULT_MIGRATION_PATHS = (
    "migrations/equipment_canonical_slot_v1.py",
    "migrations/coin_purchase_operations_v1.py",
    "migrations/domain_event_outbox_v1.py",
)

REQUIRED_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "user_stats": ("user_id", "coins"),
    "currency_log": ("user_id", "delta", "balance_after", "reason", "created_at"),
    "player_inventory": (
        "id",
        "user_id",
        "equip_id",
        "equipped",
        "obtained_at",
        "source",
    ),
    "shop_inventory": ("user_id", "item_key", "qty"),
    "player_wardrobe": ("user_id", "item_id", "obtained_at", "source"),
}

_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_CANONICAL_SLOTS = frozenset({"weapon", "armor", "accessory"})
_LOCKED_EQUIPMENT = frozenset({"xp_amulet", "go_stone_black"})


@dataclass(frozen=True)
class EquipmentDefinition:
    item_id: str
    slot: str | None


def _check(
    status: str,
    *,
    expected: Any = None,
    observed: Any = None,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"status": status}
    if expected is not None:
        result["expected"] = expected
    if observed is not None:
        result["observed"] = observed
    if details:
        result["details"] = dict(details)
    return result


def _row_value(row: Any, index: int, name: str) -> Any:
    if row is None:
        return None
    if hasattr(row, "keys"):
        return row[name]
    return row[index]


def _rows(conn: Any, sql: str, parameters: Iterable[Any] = ()) -> list[Any]:
    return conn.execute(sql, tuple(parameters)).fetchall()


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA_RE.fullmatch(value.strip()))


def _safe_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        check=False,
    )


def _git_text(repo_root: Path, *args: str) -> str:
    result = _safe_git(repo_root, *args)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or f"git command failed: git {' '.join(args)}")
    return result.stdout.decode("utf-8", errors="replace").strip()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_equipment_definitions_from_source(repo_root: Path) -> tuple[EquipmentDefinition, ...]:
    """Read the literal ``app.EQUIPMENT_DEFS`` without importing ``app.py``.

    This is a source-contract read, not a second Equipment registry.  The
    preflight must fail closed if the authoritative registry stops being a
    literal source contract that can be inspected without executing the app.
    """

    source_path = repo_root / "app.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets.extend(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets.append(node.target)
        if not any(isinstance(target, ast.Name) and target.id == "EQUIPMENT_DEFS" for target in targets):
            continue
        raw = ast.literal_eval(node.value)
        if not isinstance(raw, list):
            raise ValueError("EQUIPMENT_DEFS source contract is not a list")
        definitions: list[EquipmentDefinition] = []
        seen: set[str] = set()
        for entry in raw:
            if not isinstance(entry, dict):
                raise ValueError("EQUIPMENT_DEFS contains a non-mapping entry")
            item_id = entry.get("id")
            slot = entry.get("slot")
            if not isinstance(item_id, str) or not item_id.strip():
                raise ValueError("EQUIPMENT_DEFS contains an invalid id")
            item_id = item_id.strip()
            if item_id in seen:
                raise ValueError(f"EQUIPMENT_DEFS contains duplicate id: {item_id}")
            seen.add(item_id)
            if slot is not None and not isinstance(slot, str):
                raise ValueError(f"EQUIPMENT_DEFS contains an invalid slot: {item_id}")
            definitions.append(
                EquipmentDefinition(item_id=item_id, slot=slot.strip().lower() if slot else None)
            )
        return tuple(definitions)
    raise ValueError("EQUIPMENT_DEFS assignment was not found in app.py")


def _verify_migration_manifest(
    repo_root: Path,
    *,
    current_master_sha: str | None,
    migration_paths: Iterable[str],
) -> dict[str, Any]:
    paths = tuple(str(path).replace("\\", "/") for path in migration_paths)
    if not _is_sha(current_master_sha):
        return _check(
            CHECK_BLOCKED,
            expected="40-character current master commit SHA",
            observed=current_master_sha,
            details={"reason": "current master SHA input is missing or malformed"},
        )

    try:
        _git_text(repo_root, "cat-file", "-e", f"{current_master_sha}^{{commit}}")
    except Exception as exc:
        return _check(
            CHECK_BLOCKED,
            expected=current_master_sha,
            details={"reason": "current master commit is not available", "error": str(exc)},
        )

    local_head: str | None = None
    ancestry: bool | None = None
    try:
        local_head = _git_text(repo_root, "rev-parse", "HEAD")
        ancestry = _safe_git(
            repo_root, "merge-base", "--is-ancestor", current_master_sha, "HEAD"
        ).returncode == 0
    except Exception:
        ancestry = None

    entries: list[dict[str, Any]] = []
    all_match = True
    for relative_path in paths:
        local_path = repo_root / Path(relative_path)
        if not local_path.is_file():
            all_match = False
            entries.append(
                {
                    "path": relative_path,
                    "status": CHECK_BLOCKED,
                    "reason": "local migration file is missing",
                }
            )
            continue
        try:
            master_bytes = _safe_git(
                repo_root, "show", f"{current_master_sha}:{relative_path}"
            )
            if master_bytes.returncode != 0:
                raise RuntimeError(
                    master_bytes.stderr.decode("utf-8", errors="replace").strip()
                )
            local_sha = _sha256_file(local_path)
            master_sha = _sha256_bytes(master_bytes.stdout)
            matches = local_sha == master_sha
            all_match = all_match and matches
            entries.append(
                {
                    "path": relative_path,
                    "status": PASS if matches else FAIL,
                    "local_sha256": local_sha,
                    "current_master_sha256": master_sha,
                    "matches": matches,
                }
            )
        except Exception as exc:
            all_match = False
            entries.append(
                {
                    "path": relative_path,
                    "status": CHECK_BLOCKED,
                    "reason": str(exc) or "unable to read migration from current master",
                }
            )

    if not all_match:
        status = FAIL if any(entry.get("status") == FAIL for entry in entries) else CHECK_BLOCKED
    elif ancestry is False:
        status = CHECK_BLOCKED
    else:
        status = PASS
    return _check(
        status,
        expected={"current_master_sha": current_master_sha, "paths": list(paths)},
        observed={"local_head": local_head, "current_master_is_ancestor": ancestry},
        details={"files": entries},
    )


def _verify_legacy_writer_contract(
    repo_root: Path,
    supplied_status: str | None,
) -> dict[str, Any]:
    if not isinstance(supplied_status, str) or not supplied_status.strip():
        return _check(
            CHECK_BLOCKED,
            expected="PASS supplied from the legacy-writer source contract",
            details={"reason": "legacy writer compatibility status was not supplied"},
        )
    normalized = supplied_status.strip().upper()
    if normalized != PASS:
        return _check(
            FAIL if normalized in {FAIL, "FAILED"} else CHECK_BLOCKED,
            expected=PASS,
            observed=normalized,
            details={"reason": "legacy writer compatibility is not approved"},
        )

    path = repo_root / "coin_purchase_authority.py"
    if not path.is_file():
        return _check(
            CHECK_BLOCKED,
            expected="coin_purchase_authority.py",
            details={"reason": "legacy writer source contract is missing"},
        )
    text = path.read_text(encoding="utf-8")
    required_markers = (
        "def _timestamp",
        "value.tzinfo",
        "value.isoformat()",
        "else value",
        "currency_log",
        "obtained_at",
        "player_wardrobe",
    )
    missing = [marker for marker in required_markers if marker not in text]
    status = PASS if not missing else FAIL
    return _check(
        status,
        expected={"supplied_status": PASS, "source_markers": list(required_markers)},
        observed={"supplied_status": normalized, "source_path": "coin_purchase_authority.py"},
        details={"missing_source_markers": missing},
    )


def audit_source_contract(
    *,
    repo_root: Path,
    expected_application_source_sha: str | None,
    observed_application_source_sha: str | None,
    current_master_sha: str | None,
    feature_gate_facts: Mapping[str, Any] | None,
    legacy_writer_compatibility: str | None,
    migration_paths: Iterable[str] = DEFAULT_MIGRATION_PATHS,
) -> dict[str, dict[str, Any]]:
    """Audit source identity and explicit release facts without executing app.py."""

    if not _is_sha(expected_application_source_sha) or not _is_sha(
        observed_application_source_sha
    ):
        source_sha_check = _check(
            CHECK_BLOCKED,
            expected="two valid 40-character application source SHAs",
            observed={
                "expected": expected_application_source_sha,
                "observed": observed_application_source_sha,
            },
            details={"reason": "application source SHA input is missing or malformed"},
        )
    elif expected_application_source_sha.lower() != observed_application_source_sha.lower():
        source_sha_check = _check(
            CHECK_BLOCKED,
            expected=expected_application_source_sha,
            observed=observed_application_source_sha,
            details={"reason": "observed application source SHA does not match expected SHA"},
        )
    else:
        source_sha_check = _check(
            PASS,
            expected=expected_application_source_sha.lower(),
            observed=observed_application_source_sha.lower(),
        )

    try:
        definitions = load_equipment_definitions_from_source(repo_root)
        equipment_contract = _check(
            PASS,
            expected="literal app.EQUIPMENT_DEFS source contract",
            observed={
                "count": len(definitions),
                "functional_slots": sum(
                    definition.slot in _CANONICAL_SLOTS for definition in definitions
                ),
            },
        )
    except Exception as exc:
        equipment_contract = _check(
            CHECK_BLOCKED,
            expected="readable app.EQUIPMENT_DEFS source contract",
            details={"error": str(exc)},
        )

    gates = feature_gate_facts or {}

    def gate_check(key: str, label: str) -> dict[str, Any]:
        value = gates.get(key)
        if value is None:
            return _check(
                CHECK_BLOCKED,
                expected="OFF",
                details={"reason": f"{label} gate state was not supplied"},
            )
        if isinstance(value, bool):
            is_off = value is False
            observed = "ON" if value else "OFF"
        elif isinstance(value, str) and value.strip().upper() in {"OFF", "ON"}:
            observed = value.strip().upper()
            is_off = observed == "OFF"
        else:
            return _check(
                CHECK_BLOCKED,
                expected="OFF",
                observed=value,
                details={"reason": f"{label} gate state is not a boolean or ON/OFF"},
            )
        return _check(
            PASS if is_off else FAIL,
            expected="OFF",
            observed=observed,
            details={"gate": key},
        )

    return {
        "application_source_sha": source_sha_check,
        "equipment_definition_source_contract": equipment_contract,
        "canonical_shop_feature_gate": gate_check(
            "canonical_shop", "canonical Shop"
        ),
        "canonical_equipment_loadout_feature_gate": gate_check(
            "canonical_equipment_loadout", "canonical Equipment loadout"
        ),
        "legacy_writer_compatibility": _verify_legacy_writer_contract(
            repo_root, legacy_writer_compatibility
        ),
        "migration_manifest": _verify_migration_manifest(
            repo_root,
            current_master_sha=current_master_sha,
            migration_paths=migration_paths,
        ),
        "no_revenue_enablement_implied": _check(
            PASS,
            expected="C031 performs no Revenue enablement",
            observed=False,
            details={"revenue_policy": "PREMIUM_ONLY_SEPARATE", "mutation_path": None},
        ),
    }


def _table_columns(conn: Any, table_name: str) -> dict[str, dict[str, Any]]:
    rows = _rows(
        conn,
        """SELECT column_name, data_type, is_nullable, ordinal_position
             FROM information_schema.columns
            WHERE table_schema='public' AND table_name=?
            ORDER BY ordinal_position""",
        (table_name,),
    )
    return {
        str(_row_value(row, 0, "column_name")): {
            "data_type": str(_row_value(row, 1, "data_type")),
            "is_nullable": str(_row_value(row, 2, "is_nullable")),
            "ordinal_position": int(_row_value(row, 3, "ordinal_position")),
        }
        for row in rows
    }


def _table_check(
    conn: Any,
    table_name: str,
    required_columns: Iterable[str],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    columns = _table_columns(conn, table_name)
    required = tuple(required_columns)
    missing = sorted(set(required) - set(columns))
    present = bool(columns)
    status = PASS if present and not missing else FAIL
    return (
        _check(
            status,
            expected={"table": table_name, "required_columns": list(required)},
            observed={"present": present, "columns": sorted(columns)},
            details={"missing_columns": missing},
        ),
        columns,
    )


def _count_equipped(conn: Any, item_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM player_inventory WHERE equipped=1 AND equip_id=?",
        (item_id,),
    ).fetchone()
    return int(_row_value(row, 0, "count") or 0)


def _equipped_rows(conn: Any) -> list[dict[str, Any]]:
    rows = _rows(
        conn,
        """SELECT id, user_id, equip_id, equipped, canonical_slot
             FROM player_inventory
            WHERE equipped=1
            ORDER BY user_id, id""",
    )
    return [
        {
            "id": _row_value(row, 0, "id"),
            "user_id": _row_value(row, 1, "user_id"),
            "equip_id": _row_value(row, 2, "equip_id"),
            "equipped": _row_value(row, 3, "equipped"),
            "canonical_slot": _row_value(row, 4, "canonical_slot"),
        }
        for row in rows
    ]


def _audit_equipped_state(
    conn: Any,
    *,
    equipment_definitions: Iterable[EquipmentDefinition] | None,
    canonical_slot_present: bool,
) -> dict[str, dict[str, Any]]:
    if not canonical_slot_present:
        blocked = _check(
            FAIL,
            expected="player_inventory.canonical_slot",
            details={"reason": "equipped canonical-slot checks cannot run before B033 projection"},
        )
        return {
            "equipped_xp_amulet_count": _check(
                FAIL,
                expected=0,
                observed="not evaluated",
                details={"reason": "canonical player_inventory schema is incomplete"},
            ),
            "equipped_go_stone_black_count": _check(
                FAIL,
                expected=0,
                observed="not evaluated",
                details={"reason": "canonical player_inventory schema is incomplete"},
            ),
            "duplicate_equipped_canonical_slot_groups": blocked,
            "malformed_equipped_rows": blocked,
        }

    try:
        equipped_rows = _equipped_rows(conn)
    except Exception as exc:
        blocked = _check(
            CHECK_BLOCKED,
            details={"reason": "equipped row inspection failed", "error": str(exc)},
        )
        return {
            "equipped_xp_amulet_count": blocked,
            "equipped_go_stone_black_count": blocked,
            "duplicate_equipped_canonical_slot_groups": blocked,
            "malformed_equipped_rows": blocked,
        }

    xp_count = sum(row["equip_id"] == "xp_amulet" for row in equipped_rows)
    go_count = sum(row["equip_id"] == "go_stone_black" for row in equipped_rows)

    grouped: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
    for row in equipped_rows:
        grouped.setdefault((row["user_id"], row["canonical_slot"]), []).append(row)
    duplicate_groups = [
        {"user_id": user_id, "canonical_slot": slot, "rows": rows}
        for (user_id, slot), rows in sorted(
            grouped.items(), key=lambda entry: (str(entry[0][0]), str(entry[0][1]))
        )
        if len(rows) > 1
    ]

    definitions = {definition.item_id: definition for definition in (equipment_definitions or ())}
    malformed: dict[str, list[dict[str, Any]]] = {}
    for row in equipped_rows:
        item_id = str(row["equip_id"])
        slot = row["canonical_slot"]
        if item_id not in definitions:
            malformed.setdefault("UNKNOWN_EQUIPPED_EQUIP_ID", []).append(row)
            continue
        if slot is None:
            malformed.setdefault("EQUIPPED_WITH_NULL_CANONICAL_SLOT", []).append(row)
        elif str(slot).lower() not in _CANONICAL_SLOTS:
            malformed.setdefault("EQUIPPED_WITH_INVALID_CANONICAL_SLOT", []).append(row)
        expected_slot = definitions[item_id].slot
        if expected_slot in _CANONICAL_SLOTS and str(slot).lower() != expected_slot:
            malformed.setdefault("EQUIPPED_CANONICAL_SLOT_MISMATCH", []).append(
                {**row, "expected_slot": expected_slot}
            )
        if item_id == "xp_amulet":
            malformed.setdefault("XP_AMULET_EQUIPPED", []).append(row)
        if item_id == "go_stone_black":
            malformed.setdefault("GO_STONE_BLACK_EQUIPPED", []).append(row)
    if duplicate_groups:
        malformed["DUPLICATE_EQUIPPED_CANONICAL_SLOT"] = duplicate_groups

    return {
        "equipped_xp_amulet_count": _check(
            PASS if xp_count == 0 else FAIL,
            expected=0,
            observed=xp_count,
        ),
        "equipped_go_stone_black_count": _check(
            PASS if go_count == 0 else FAIL,
            expected=0,
            observed=go_count,
        ),
        "duplicate_equipped_canonical_slot_groups": _check(
            PASS if not duplicate_groups else FAIL,
            expected=0,
            observed=len(duplicate_groups),
            details={"groups": duplicate_groups},
        ),
        "malformed_equipped_rows": _check(
            PASS if not malformed else FAIL,
            expected="no malformed equipped rows",
            observed={"equipped_row_count": len(equipped_rows), "blocking_categories": sorted(malformed)},
            details={"rows": malformed},
        ),
    }


def audit_database(
    conn: Any,
    *,
    equipment_definitions: Iterable[EquipmentDefinition] | None = None,
    expected_postgres_version: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Run SELECT-only checks against a PostgreSQL connection."""

    checks: dict[str, dict[str, Any]] = {}
    try:
        version_row = conn.execute("SELECT version()").fetchone()
        version = str(_row_value(version_row, 0, "version")) if version_row else ""
        version_ok = bool(version)
        if expected_postgres_version:
            version_ok = expected_postgres_version in version
        checks["postgres_version"] = _check(
            PASS if version_ok else FAIL,
            expected=expected_postgres_version or "non-empty PostgreSQL version",
            observed=version,
        )
    except Exception as exc:
        checks["postgres_version"] = _check(
            CHECK_BLOCKED,
            details={"reason": "PostgreSQL version query failed", "error": str(exc)},
        )

    table_columns: dict[str, dict[str, dict[str, Any]]] = {}
    for table_name, required_columns in REQUIRED_TABLE_COLUMNS.items():
        try:
            check, columns = _table_check(conn, table_name, required_columns)
            checks[f"{table_name}_schema"] = check
            table_columns[table_name] = columns
        except Exception as exc:
            checks[f"{table_name}_schema"] = _check(
                CHECK_BLOCKED,
                expected={"table": table_name, "required_columns": list(required_columns)},
                details={"reason": "schema metadata query failed", "error": str(exc)},
            )

    player_columns = table_columns.get("player_inventory", {})
    canonical_slot_present = "canonical_slot" in player_columns
    checks["player_inventory_canonical_slot"] = _check(
        PASS if canonical_slot_present else FAIL,
        expected="present",
        observed="present" if canonical_slot_present else "absent",
    )

    try:
        from migrations.equipment_canonical_slot_v1 import validate_schema as validate_b033

        b033 = validate_b033(conn)
        checks["b033_invariant_index_state"] = _check(
            PASS if b033.get("valid") else FAIL,
            expected={"validity_constraint": True, "partial_unique_index": True},
            observed=b033,
        )
    except Exception as exc:
        checks["b033_invariant_index_state"] = _check(
            CHECK_BLOCKED,
            expected="read-only B033 schema validation",
            details={"error": str(exc)},
        )

    if table_columns.get("player_inventory") and {
        "equipped",
        "equip_id",
    }.issubset(player_columns):
        try:
            checks.update(
                _audit_equipped_state(
                    conn,
                    equipment_definitions=equipment_definitions,
                    canonical_slot_present=canonical_slot_present,
                )
            )
        except Exception as exc:
            for key in (
                "equipped_xp_amulet_count",
                "equipped_go_stone_black_count",
                "duplicate_equipped_canonical_slot_groups",
                "malformed_equipped_rows",
            ):
                checks[key] = _check(
                    CHECK_BLOCKED,
                    details={"reason": "equipped state query failed", "error": str(exc)},
                )
    else:
            for key in (
                "equipped_xp_amulet_count",
                "equipped_go_stone_black_count",
                "duplicate_equipped_canonical_slot_groups",
                "malformed_equipped_rows",
            ):
                checks[key] = _check(
                    FAIL,
                    details={"reason": "player_inventory equipped columns are unavailable"},
                )

    try:
        from migrations.coin_purchase_operations_v1 import validate_schema as validate_purchase

        purchase = validate_purchase(conn)
        checks["coin_purchase_operations_schema"] = _check(
            PASS if purchase.get("present") and not purchase.get("missing") else FAIL,
            expected="present and compatible",
            observed=purchase,
        )
    except Exception as exc:
        checks["coin_purchase_operations_schema"] = _check(
            FAIL,
            expected="present and compatible",
            details={"error": str(exc)},
        )

    try:
        from migrations.domain_event_outbox_v1 import validate_schema as validate_outbox

        outbox = validate_outbox(conn)
        checks["domain_event_outbox_schema"] = _check(
            PASS if outbox.get("present") and not outbox.get("missing") else FAIL,
            expected="present and compatible",
            observed=outbox,
        )
    except Exception as exc:
        checks["domain_event_outbox_schema"] = _check(
            FAIL,
            expected="present and compatible",
            details={"error": str(exc)},
        )

    # C030 proved legacy TEXT timestamp columns are accepted by the current
    # C026 writer.  This is reported, not mutated or normalized here.
    for table_name, column_name in (
        ("currency_log", "created_at"),
        ("player_inventory", "obtained_at"),
        ("player_wardrobe", "obtained_at"),
    ):
        column = table_columns.get(table_name, {}).get(column_name)
        if column is None:
            checks[f"{table_name}_{column_name}_type"] = _check(
                FAIL,
                expected="column present",
                observed="absent",
            )
        else:
            checks[f"{table_name}_{column_name}_type"] = _check(
                PASS,
                expected="present; TEXT is accepted by the current C026 writer",
                observed=column["data_type"],
            )
    return checks


def _overall_status(checks: Mapping[str, Mapping[str, Any]]) -> str:
    statuses = [str(value.get("status")) for value in checks.values()]
    if CHECK_BLOCKED in statuses:
        return BLOCKED
    if FAIL in statuses:
        return NOT_READY
    return READY_FOR_OPTION_C_MAINTENANCE


def _human_summary(status: str, checks: Mapping[str, Mapping[str, Any]]) -> str:
    counts = {value: 0 for value in (PASS, FAIL, CHECK_BLOCKED)}
    issues: list[str] = []
    for name, check in checks.items():
        check_status = str(check.get("status"))
        counts[check_status] = counts.get(check_status, 0) + 1
        if check_status != PASS:
            issues.append(f"{name}={check_status}")
    lines = [
        f"C031 status: {status}",
        f"Checks: PASS={counts.get(PASS, 0)} FAIL={counts.get(FAIL, 0)} BLOCKED={counts.get(CHECK_BLOCKED, 0)}.",
        "GO_PRODUCTION_DB_MIGRATION: DEFERRED_TO_OWNER_COORDINATOR (not decided by this auditor).",
        "Revenue enablement: not implied; C031 has no enablement or mutation path.",
    ]
    if issues:
        lines.append("Non-passing checks: " + ", ".join(issues))
    else:
        lines.append("All supplied source, gate, and database checks passed.")
    return "\n".join(lines)


def run_preflight(
    *,
    repo_root: Path,
    expected_application_source_sha: str | None,
    observed_application_source_sha: str | None,
    current_master_sha: str | None,
    feature_gate_facts: Mapping[str, Any] | None,
    legacy_writer_compatibility: str | None,
    conn: Any | None,
    equipment_definitions: Iterable[EquipmentDefinition] | None = None,
    expected_postgres_version: str | None = None,
    migration_paths: Iterable[str] = DEFAULT_MIGRATION_PATHS,
) -> dict[str, Any]:
    source_checks = audit_source_contract(
        repo_root=repo_root,
        expected_application_source_sha=expected_application_source_sha,
        observed_application_source_sha=observed_application_source_sha,
        current_master_sha=current_master_sha,
        feature_gate_facts=feature_gate_facts,
        legacy_writer_compatibility=legacy_writer_compatibility,
        migration_paths=migration_paths,
    )

    definitions = equipment_definitions
    if definitions is None:
        try:
            definitions = load_equipment_definitions_from_source(repo_root)
        except Exception:
            definitions = None

    if conn is None:
        database_checks = {
            key: _check(
                CHECK_BLOCKED,
                details={"reason": "no caller-supplied PostgreSQL connection; no database query was attempted"},
            )
            for key in (
                "postgres_version",
                *[f"{table}_schema" for table in REQUIRED_TABLE_COLUMNS],
                "player_inventory_canonical_slot",
                "b033_invariant_index_state",
                "equipped_xp_amulet_count",
                "equipped_go_stone_black_count",
                "duplicate_equipped_canonical_slot_groups",
                "malformed_equipped_rows",
                "coin_purchase_operations_schema",
                "domain_event_outbox_schema",
                "currency_log_created_at_type",
                "player_inventory_obtained_at_type",
                "player_wardrobe_obtained_at_type",
            )
        }
    else:
        try:
            database_checks = audit_database(
                conn,
                equipment_definitions=definitions,
                expected_postgres_version=expected_postgres_version,
            )
        except Exception as exc:
            database_checks = {
                "postgres_version": _check(
                    CHECK_BLOCKED,
                    details={"reason": "database audit failed before completion", "error": str(exc)},
                )
            }

    checks = {**source_checks, **database_checks}
    status = _overall_status(checks)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "checks": checks,
        "provenance": {
            "expected_application_source_sha": expected_application_source_sha,
            "observed_application_source_sha": observed_application_source_sha,
            "current_master_sha": current_master_sha,
            "repository_root": str(repo_root),
            "database_target": "caller_supplied; not serialized",
        },
        "policy": {
            "go_production_db_migration": "DEFERRED_TO_OWNER_COORDINATOR",
            "revenue_enablement_implied": False,
            "production_query_performed_by_c031": False,
            "production_mutation_performed_by_c031": False,
            "feature_enablement_performed_by_c031": False,
        },
        "mutation_guard": {
            "writes": 0,
            "commits": 0,
            "rollbacks": 0,
            "migration_execution": 0,
        },
        "human_summary": _human_summary(status, checks),
    }


def _parse_gate(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if normalized == "OFF":
        return False
    if normalized == "ON":
        return True
    return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only C031 Commerce production-readiness preflight auditor"
    )
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--database-url", help="Explicit caller-supplied PostgreSQL URL; never defaulted")
    parser.add_argument("--expected-application-source-sha", required=True)
    parser.add_argument("--observed-application-source-sha", required=True)
    parser.add_argument("--current-master-sha", required=True)
    parser.add_argument("--canonical-shop-gate", choices=("OFF", "ON"))
    parser.add_argument("--canonical-equipment-loadout-gate", choices=("OFF", "ON"))
    parser.add_argument("--legacy-writer-compatibility", choices=("PASS", "FAIL"))
    parser.add_argument("--expected-postgres-version")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    conn: Any | None = None
    raw: Any | None = None
    connection_error: str | None = None
    if args.database_url:
        try:
            import psycopg2
            from psycopg2.extras import DictCursor

            from db import PostgresConnectionWrapper

            raw = psycopg2.connect(args.database_url, cursor_factory=DictCursor)
            conn = PostgresConnectionWrapper(raw, pooled=False)
        except Exception as exc:
            connection_error = str(exc)
    result = run_preflight(
        repo_root=args.repo_root.resolve(),
        expected_application_source_sha=args.expected_application_source_sha,
        observed_application_source_sha=args.observed_application_source_sha,
        current_master_sha=args.current_master_sha,
        feature_gate_facts={
            "canonical_shop": _parse_gate(args.canonical_shop_gate),
            "canonical_equipment_loadout": _parse_gate(
                args.canonical_equipment_loadout_gate
            ),
        },
        legacy_writer_compatibility=args.legacy_writer_compatibility,
        conn=conn,
        expected_postgres_version=args.expected_postgres_version,
    )
    if connection_error:
        result["checks"]["postgres_connection"] = _check(
            CHECK_BLOCKED,
            details={"reason": "caller-supplied PostgreSQL connection failed", "error": connection_error},
        )
        result["status"] = _overall_status(result["checks"])
        result["human_summary"] = _human_summary(result["status"], result["checks"])

    try:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        print(result["human_summary"], file=sys.stderr)
    finally:
        if conn is not None:
            conn.close()
        elif raw is not None:
            raw.close()
    return {READY_FOR_OPTION_C_MAINTENANCE: 0, NOT_READY: 2, BLOCKED: 3}[result["status"]]


if __name__ == "__main__":  # pragma: no cover - CLI dispatch
    raise SystemExit(main())


__all__ = [
    "BLOCKED",
    "DEFAULT_MIGRATION_PATHS",
    "EquipmentDefinition",
    "FAIL",
    "NOT_READY",
    "PASS",
    "READY_FOR_OPTION_C_MAINTENANCE",
    "SCHEMA_VERSION",
    "audit_database",
    "audit_source_contract",
    "load_equipment_definitions_from_source",
    "main",
    "run_preflight",
]
