"""Governed, narrowly scoped Option C PostgreSQL migration runner.

This tool is intentionally not a migration framework. It knows exactly two
accepted migrations and never discovers or runs any other migration:

1. equipment_canonical_slot_v1
2. coin_purchase_operations_v1

The default mode is read-only preflight. Mutation requires both -Execute and
the exact -OwnerGate GO_PRODUCTION_DB_MIGRATION argument. Production
credentials are read only from the existing runtime DATABASE_URL environment;
the URL is never accepted as a CLI argument or emitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from collections import Counter
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "C036_CANONICAL_OPTION_C_PRODUCTION_MIGRATION_RUNNER_V1"
OWNER_GATE = "GO_PRODUCTION_DB_MIGRATION"
SUPPORTED_TARGETS = frozenset({"disposable", "production"})
MIGRATION_ORDER = (
    "migrations.equipment_canonical_slot_v1",
    "migrations.coin_purchase_operations_v1",
)
MIGRATION_PATHS = (
    "migrations/equipment_canonical_slot_v1.py",
    "migrations/coin_purchase_operations_v1.py",
)
OUTBOX_PATH = "migrations/domain_event_outbox_v1.py"

# These are the C035-approved bytes. A changed migration requires a separate
# migration review; this runner must never silently bless a new hash.
EXPECTED_MIGRATION_HASHES = {
    MIGRATION_PATHS[0]: "C4338B9270E68D0D32278A278426601A242B138A44352B828869374D213BEE06",
    MIGRATION_PATHS[1]: "7A314D0817960B1C6D50A6AA94E0762BDB3E9D6E7091270BD0969162CD13AC8D",
    OUTBOX_PATH: "446D9FE251C94ED43B5F2B1C6E0B6C1619AEFD1439EC2DF004F3BD5F2F294955",
}

GATE_NAMES = {
    "canonical_shop": "CANONICAL_COIN_SHOP_PURCHASE_ENABLED",
    "canonical_equipment_loadout": "EQUIPMENT_CANONICAL_LOADOUT_ENABLED",
}
FALSE_VALUES = frozenset({"", "0", "false", "off", "no", "unset"})
TRUE_VALUES = frozenset({"1", "true", "on", "yes"})
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")

REQUIRED_TABLE_COLUMNS = {
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


class RunnerError(RuntimeError):
    """A sanitized, fail-closed runner error."""


class PostcheckFailure(RunnerError):
    """A migration returned but its required postcheck failed."""


def _safe_error(error: BaseException) -> dict[str, Any]:
    """Return only non-sensitive error identity."""

    result: dict[str, Any] = {"error_class": type(error).__name__}
    sqlstate = getattr(error, "pgcode", None)
    if isinstance(sqlstate, str) and re.fullmatch(r"[0-9A-Z]{5}", sqlstate):
        result["sqlstate"] = sqlstate
    return result


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _git(repo_root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=str(repo_root),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RunnerError("git_command_failed")
    return result.stdout.decode("utf-8", errors="replace").strip()


def _git_blob_bytes(repo_root: Path, revision: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=str(repo_root),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RunnerError("git_blob_unavailable")
    return result.stdout


def _check_source_binding(repo_root: Path, expected_git_sha: str) -> dict[str, Any]:
    expected = expected_git_sha.strip()
    if not SHA_RE.fullmatch(expected):
        return {
            "status": "FAIL",
            "reason": "expected_git_sha_invalid",
            "expected_git_sha": expected,
        }

    try:
        observed = _git(repo_root, "rev-parse", "HEAD")
        _git(repo_root, "cat-file", "-e", f"{expected}^{{commit}}")
        commit_exists = True
    except RunnerError as error:
        return {"status": "BLOCKED", "reason": "git_identity_unavailable", **_safe_error(error)}

    if observed.lower() != expected.lower():
        return {
            "status": "FAIL",
            "reason": "git_sha_mismatch",
            "expected_git_sha": expected,
            "observed_git_sha": observed,
            "commit_exists": commit_exists,
        }

    hashes: dict[str, Any] = {}
    all_match = True
    for path, expected_hash in EXPECTED_MIGRATION_HASHES.items():
        file_path = repo_root / path
        if not file_path.is_file():
            hashes[path] = {"status": "FAIL", "reason": "file_missing"}
            all_match = False
            continue
        try:
            working_hash = _sha256_file(file_path)
            git_hash = _sha256_bytes(_git_blob_bytes(repo_root, expected, path))
        except RunnerError as error:
            hashes[path] = {"status": "BLOCKED", **_safe_error(error)}
            all_match = False
            continue
        matches = working_hash == expected_hash and git_hash == expected_hash
        hashes[path] = {
            "status": "PASS" if matches else "FAIL",
            "sha256": working_hash,
            "git_blob_sha256": git_hash,
            "expected_sha256": expected_hash,
        }
        all_match = all_match and matches

    relevant_dirty = False
    tracked_tree_dirty = False
    try:
        unstaged = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", *EXPECTED_MIGRATION_HASHES],
            cwd=str(repo_root),
            check=False,
        )
        staged = subprocess.run(
            ["git", "diff", "--cached", "--quiet", "--", *EXPECTED_MIGRATION_HASHES],
            cwd=str(repo_root),
            check=False,
        )
        relevant_dirty = unstaged.returncode != 0 or staged.returncode != 0
        tracked_unstaged = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--"],
            cwd=str(repo_root),
            check=False,
        )
        tracked_staged = subprocess.run(
            ["git", "diff", "--cached", "--quiet", "--"],
            cwd=str(repo_root),
            check=False,
        )
        tracked_tree_dirty = (
            tracked_unstaged.returncode != 0 or tracked_staged.returncode != 0
        )
    except OSError:
        relevant_dirty = True
        tracked_tree_dirty = True

    return {
        "status": "PASS" if all_match and not relevant_dirty and not tracked_tree_dirty else "FAIL",
        "expected_git_sha": expected,
        "observed_git_sha": observed,
        "commit_exists": commit_exists,
        "migration_hashes": hashes,
        "relevant_worktree_dirty": relevant_dirty,
        "tracked_worktree_dirty": tracked_tree_dirty,
    }


def _effective_gate(name: str) -> dict[str, Any]:
    raw = os.environ.get(name)
    if raw is None:
        return {"status": "PASS", "effective": "OFF", "source": "runtime_default"}
    normalized = raw.strip().lower()
    if normalized in FALSE_VALUES:
        return {"status": "PASS", "effective": "OFF", "source": "runtime_environment"}
    if normalized in TRUE_VALUES:
        return {"status": "FAIL", "effective": "ON", "source": "runtime_environment"}
    return {"status": "BLOCKED", "effective": "UNKNOWN", "source": "runtime_environment"}


def _load_equipment_definitions() -> tuple[Mapping[str, Any], ...]:
    """Load the sole server Equipment registry; never duplicate it here."""

    from app import EQUIPMENT_DEFS

    if not isinstance(EQUIPMENT_DEFS, (list, tuple)) or not EQUIPMENT_DEFS:
        raise RunnerError("canonical_equipment_definitions_unavailable")
    definitions = tuple(EQUIPMENT_DEFS)
    ids = [str(item.get("id") or "") for item in definitions]
    if any(not item_id for item_id in ids) or len(ids) != len(set(ids)):
        raise RunnerError("canonical_equipment_definitions_invalid")
    return definitions


def _row_value(row: Any, index: int, name: str) -> Any:
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _scalar(conn: Any, sql: str, parameters: Iterable[Any] = ()) -> Any:
    row = conn.execute(sql, tuple(parameters)).fetchone()
    return _row_value(row, 0, "value") if row is not None else None


def _table_columns(conn: Any, table: str) -> set[str]:
    rows = conn.execute(
        """SELECT column_name
             FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ?
            ORDER BY ordinal_position""",
        (table,),
    ).fetchall()
    return {str(_row_value(row, 0, "column_name")) for row in rows}


def _relation_exists(conn: Any, table: str) -> bool:
    value = _scalar(
        conn,
        """SELECT COUNT(*) AS value
             FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = ?""",
        (table,),
    )
    return int(value or 0) == 1


def _named_constraint_exists(conn: Any, name: str) -> bool:
    value = _scalar(
        conn,
        """SELECT COUNT(*) AS value
             FROM pg_constraint c
             JOIN pg_class t ON t.oid = c.conrelid
             JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public' AND c.conname = ?""",
        (name,),
    )
    return int(value or 0) == 1


def _named_index_exists(conn: Any, name: str) -> bool:
    value = _scalar(
        conn,
        """SELECT COUNT(*) AS value
             FROM pg_class c
             JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relkind = 'i'
              AND c.relname = ?""",
        (name,),
    )
    return int(value or 0) == 1


def _status(ok: bool, *, observed: Any = None, reason: str | None = None) -> dict[str, Any]:
    result = {"status": "PASS" if ok else "FAIL"}
    if observed is not None:
        result["observed"] = observed
    if reason:
        result["reason"] = reason
    return result


def _summarize_malformed(report: Mapping[str, Any]) -> dict[str, Any]:
    blockers = report.get("blockers")
    counts: dict[str, int] = {}
    if isinstance(blockers, Mapping):
        for key, value in blockers.items():
            counts[str(key)] = len(value) if isinstance(value, (list, tuple)) else 1
    categories = report.get("blocking_categories")
    if isinstance(categories, (list, tuple)) and not counts:
        counts = {str(category): 1 for category in categories}
    clean = bool(report.get("clean"))
    return {
        "status": "PASS" if clean else "FAIL",
        "clean": clean,
        "blocking_categories": sorted(counts),
        "blocking_counts": counts,
    }


def _equipped_state(
    conn: Any,
    equipment_definitions: Iterable[Mapping[str, Any]],
    *,
    canonical_slot_present: bool,
) -> dict[str, Any]:
    definitions = {str(item.get("id")): item for item in equipment_definitions}
    functional_slots = {
        item_id: str(item.get("slot"))
        for item_id, item in definitions.items()
        if item_id not in {"xp_amulet", "go_stone_black"}
        and item.get("slot") in {"weapon", "armor", "accessory"}
    }

    invalid_equipped = int(
        _scalar(
            conn,
            """SELECT COUNT(*) AS value
                 FROM public.player_inventory
                WHERE equipped IS NULL OR equipped NOT IN (0, 1)""",
        )
        or 0
    )
    xp_amulet_count = int(
        _scalar(
            conn,
            """SELECT COUNT(*) AS value
                 FROM public.player_inventory
                WHERE equipped = 1
                  AND equip_id = 'xp_amulet'""",
        )
        or 0
    )
    go_stone_black_count = int(
        _scalar(
            conn,
            """SELECT COUNT(*) AS value
                 FROM public.player_inventory
                WHERE equipped = 1
                  AND equip_id = 'go_stone_black'""",
        )
        or 0
    )
    locked = xp_amulet_count + go_stone_black_count
    rows = conn.execute(
        """SELECT user_id, equip_id
             FROM public.player_inventory
            WHERE equipped = 1""",
    ).fetchall()
    unknown = 0
    slot_groups: Counter[tuple[Any, str]] = Counter()
    for row in rows:
        user_id = _row_value(row, 0, "user_id")
        equip_id = str(_row_value(row, 1, "equip_id"))
        slot = functional_slots.get(equip_id)
        if slot is None:
            if equip_id not in definitions:
                unknown += 1
            continue
        slot_groups[(user_id, slot)] += 1
    duplicate_groups = sum(1 for count in slot_groups.values() if count > 1)

    if canonical_slot_present:
        null_slots = int(
            _scalar(
                conn,
                """SELECT COUNT(*) AS value
                     FROM public.player_inventory
                    WHERE equipped = 1 AND canonical_slot IS NULL""",
            )
            or 0
        )
        try:
            from migrations.equipment_canonical_slot_v1 import detect_malformed_rows

            malformed = _summarize_malformed(
                detect_malformed_rows(conn, equipment_definitions)
            )
        except Exception as error:
            malformed = {"status": "BLOCKED", **_safe_error(error)}
    else:
        null_slots = 0
        malformed = _status(
            invalid_equipped == 0
            and locked == 0
            and unknown == 0
            and duplicate_groups == 0,
            observed="pre_b033_projection_not_present",
        )

    return {
        "unknown_equipment_ids": _status(unknown == 0, observed=unknown),
        "malformed_equipped_values": _status(invalid_equipped == 0, observed=invalid_equipped),
        "null_equipped_slots": _status(null_slots == 0, observed=null_slots),
        "duplicate_equipped_slots": _status(duplicate_groups == 0, observed=duplicate_groups),
        "equipped_xp_amulet": _status(xp_amulet_count == 0, observed=xp_amulet_count),
        "equipped_go_stone_black": _status(
            go_stone_black_count == 0,
            observed=go_stone_black_count,
        ),
        "malformed_equipped_rows": malformed,
    }


def _all_pass(checks: Mapping[str, Any]) -> bool:
    for value in checks.values():
        if isinstance(value, Mapping):
            if "status" in value and value.get("status") != "PASS":
                return False
            nested = {
                str(key): nested_value
                for key, nested_value in value.items()
                if isinstance(nested_value, Mapping)
            }
            if nested and not _all_pass(nested):
                return False
    return True


def _schema_states(conn: Any) -> dict[str, Any]:
    from migrations.coin_purchase_operations_v1 import validate_schema as validate_purchase
    from migrations.domain_event_outbox_v1 import validate_schema as validate_outbox
    from migrations.equipment_canonical_slot_v1 import validate_schema as validate_b033

    b033_report = validate_b033(conn)
    b033_column = "canonical_slot" in _table_columns(conn, "player_inventory")
    b033_constraint = _named_constraint_exists(
        conn, "ck_player_inventory_equipped_requires_slot"
    )
    b033_index = _named_index_exists(
        conn, "uq_player_inventory_user_equipped_slot"
    )
    if b033_report.get("valid"):
        b033_state = "B033_ALREADY_VALID"
    elif not b033_column and not b033_constraint and not b033_index:
        b033_state = "LEGACY_SCHEMA"
    else:
        b033_state = "B033_PARTIAL_OR_INCOMPATIBLE"

    c019_present = _relation_exists(conn, "coin_purchase_operations")
    c019_error: BaseException | None = None
    try:
        purchase_report = validate_purchase(conn)
    except Exception as error:
        purchase_report = None
        c019_error = error
    if not c019_present:
        c019_state = "C019_ABSENT"
    elif purchase_report is not None and purchase_report.get("present") and not purchase_report.get("missing"):
        c019_state = "C019_ALREADY_VALID"
    else:
        c019_state = "C019_PARTIAL_OR_INCOMPATIBLE"

    outbox_error: BaseException | None = None
    try:
        outbox_report = validate_outbox(conn)
    except Exception as error:
        outbox_report = None
        outbox_error = error
    outbox_valid = bool(
        outbox_report
        and outbox_report.get("present")
        and not outbox_report.get("missing")
    )

    return {
        "b033": {
            "state": b033_state,
            "canonical_slot": b033_column,
            "validity_constraint": b033_constraint,
            "partial_unique_index": b033_index,
            "valid": bool(b033_report.get("valid")),
        },
        "c019": {
            "state": c019_state,
            "present": c019_present,
            "valid": c019_state == "C019_ALREADY_VALID",
            **({"error": _safe_error(c019_error)} if c019_error else {}),
        },
        "domain_event_outbox": {
            "status": "PASS" if outbox_valid else "FAIL",
            "valid": outbox_valid,
            **({"error": _safe_error(outbox_error)} if outbox_error else {}),
        },
    }


def _base_schema_checks(conn: Any) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    for table, required in REQUIRED_TABLE_COLUMNS.items():
        columns = _table_columns(conn, table)
        missing = sorted(set(required) - columns)
        checks[f"{table}_schema"] = {
            "status": "PASS" if not missing else "FAIL",
            "missing_columns": missing,
        }
    return checks


def _postgres_version_check(conn: Any, expected: str) -> dict[str, Any]:
    version = str(_scalar(conn, "SELECT version()") or "")
    return {
        "status": "PASS" if expected.lower() in version.lower() else "FAIL",
        "expected_contains": expected,
        "observed": version,
    }


def _preflight(
    conn: Any,
    *,
    repo_root: Path,
    expected_git_sha: str,
    target_environment: str,
    equipment_definitions: tuple[Mapping[str, Any], ...],
    expected_postgres_version: str,
) -> dict[str, Any]:
    source = _check_source_binding(repo_root, expected_git_sha)
    gates = {
        key: _effective_gate(name)
        for key, name in GATE_NAMES.items()
    }
    checks: dict[str, Any] = {
        "source_binding": source,
        "feature_gates": gates,
        "target_environment": {
            "status": "PASS" if target_environment in SUPPORTED_TARGETS else "BLOCKED",
            "observed": target_environment,
        },
        "postgres_version": _postgres_version_check(conn, expected_postgres_version),
    }
    checks.update(_base_schema_checks(conn))
    states = _schema_states(conn)
    checks["schema_states"] = states
    canonical_slot_present = states["b033"]["canonical_slot"]
    checks["equipped_state"] = _equipped_state(
        conn,
        equipment_definitions,
        canonical_slot_present=canonical_slot_present,
    )
    checks["equipment_definition_count"] = {
        "status": "PASS",
        "observed": len(equipment_definitions),
    }

    required_ok = (
        source.get("status") == "PASS"
        and all(
            gate.get("effective") == "OFF" and gate.get("status") == "PASS"
            for gate in gates.values()
        )
        and checks["target_environment"]["status"] == "PASS"
        and checks["postgres_version"]["status"] == "PASS"
        and all(
            checks[f"{table}_schema"].get("status") == "PASS"
            for table in REQUIRED_TABLE_COLUMNS
        )
        and states["domain_event_outbox"]["valid"]
        and states["b033"]["state"] in {"LEGACY_SCHEMA", "B033_ALREADY_VALID"}
        and states["c019"]["state"] in {"C019_ABSENT", "C019_ALREADY_VALID"}
        and not (
            states["b033"]["state"] == "LEGACY_SCHEMA"
            and states["c019"]["state"] == "C019_ALREADY_VALID"
        )
        and _all_pass(checks["equipped_state"])
    )
    if required_ok:
        if (
            states["b033"]["state"] == "B033_ALREADY_VALID"
            and states["c019"]["state"] == "C019_ALREADY_VALID"
        ):
            sequence_plan = "ALREADY_VALID"
        else:
            sequence_plan = "RUN_MISSING_APPROVED_MIGRATIONS"
    else:
        sequence_plan = "BLOCKED"
    return {
        "checks": checks,
        "sequence_plan": sequence_plan,
        "ready": required_ok,
        "migration_order": list(MIGRATION_ORDER),
        "existing_inventory_mutation_freeze_mechanism": False,
    }


def _open_connection(database_url: str | None, *, read_only: bool) -> tuple[Any, bool]:
    """Open the canonical wrapper; a direct URL is test-only injection."""

    if database_url is None:
        if not os.environ.get("DATABASE_URL", "").strip():
            raise RunnerError("DATABASE_URL_runtime_configuration_missing")
        from db import get_db

        conn = get_db()
        pooled = True
    else:
        import psycopg2
        from psycopg2.extras import DictCursor
        from db import PostgresConnectionWrapper

        raw = psycopg2.connect(database_url, cursor_factory=DictCursor)
        conn = PostgresConnectionWrapper(raw, pooled=False)
        pooled = False

    raw = getattr(conn, "_conn", conn)
    raw.autocommit = False
    if read_only:
        raw.set_session(readonly=True)
    return conn, pooled


def _close_connection(conn: Any, *, pooled: bool, read_only: bool) -> None:
    raw = getattr(conn, "_conn", conn)
    try:
        if read_only:
            try:
                conn.rollback()
            finally:
                if not getattr(raw, "closed", False):
                    raw.set_session(readonly=False, autocommit=False)
    finally:
        conn.close()


def _b033_postchecks(
    conn: Any,
    equipment_definitions: tuple[Mapping[str, Any], ...],
) -> dict[str, Any]:
    from migrations.equipment_canonical_slot_v1 import validate_schema

    schema = validate_schema(conn)
    equipped = _equipped_state(
        conn,
        equipment_definitions,
        canonical_slot_present=True,
    )
    if not schema.get("valid") or not _all_pass(equipped):
        raise PostcheckFailure("b033_postcheck_failed")
    return {
        "schema_valid": True,
        "canonical_slot": True,
        "validity_constraint": True,
        "partial_unique_index": True,
        "equipped_state": equipped,
    }


def _c019_postchecks(conn: Any) -> dict[str, Any]:
    from migrations.coin_purchase_operations_v1 import (
        COLUMNS,
        INDEX_SPECS,
        PRIMARY_KEY_COLUMNS,
        validate_schema,
    )

    schema = validate_schema(conn)
    if not schema.get("present") or schema.get("missing"):
        raise PostcheckFailure("coin_purchase_schema_postcheck_failed")
    expected_columns = len(COLUMNS)
    if len(schema.get("columns", ())) != expected_columns:
        raise PostcheckFailure("coin_purchase_column_count_postcheck_failed")
    return {
        "schema_valid": True,
        "expected_column_count": expected_columns,
        "primary_key": list(PRIMARY_KEY_COLUMNS),
        "required_indexes": [name for name, _columns in INDEX_SPECS],
        "positive_price_constraint": True,
        "positive_quantity_constraint": True,
        "operation_status_constraint": True,
        "result_payload_jsonb_not_null": True,
    }


def _migration_result(result: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key in ("schema_version", "valid", "present", "dry_run"):
        if key in result:
            safe[key] = result[key]
    if isinstance(result.get("created"), (list, tuple)):
        safe["created"] = [str(item) for item in result["created"]]
    if isinstance(result.get("backfilled_rows"), int):
        safe["backfilled_rows"] = result["backfilled_rows"]
    malformed = result.get("malformed_preflight")
    if isinstance(malformed, Mapping):
        safe["malformed_preflight"] = _summarize_malformed(malformed)
    return safe


def _run_b033(
    *,
    database_url: str | None,
    equipment_definitions: tuple[Mapping[str, Any], ...],
) -> dict[str, Any]:
    from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_b033

    conn, _pooled = _open_connection(database_url, read_only=False)
    try:
        try:
            result = upgrade_b033(
                conn,
                equipment_defs=equipment_definitions,
                dry_run=False,
            )
            postchecks = _b033_postchecks(conn, equipment_definitions)
        except PostcheckFailure as error:
            conn.rollback()
            return {
                "status": "B033_POSTCHECK_FAIL",
                "transaction": "ROLLED_BACK",
                **_safe_error(error),
            }
        except Exception as error:
            conn.rollback()
            return {
                "status": "B033_MIGRATION_FAIL",
                "transaction": "ROLLED_BACK",
                **_safe_error(error),
            }
        try:
            conn.commit()
        except Exception as error:
            return {
                "status": "B033_COMMIT_UNKNOWN",
                "transaction": "UNKNOWN",
                "commit_outcome": "UNKNOWN",
                "automatic_retry": False,
                **_safe_error(error),
            }
        return {
            "status": "COMMITTED",
            "transaction": "COMMITTED",
            "result": _migration_result(result),
            "postchecks": postchecks,
        }
    finally:
        conn.close()


def _run_c019(
    *,
    database_url: str | None,
) -> dict[str, Any]:
    from migrations.coin_purchase_operations_v1 import upgrade as upgrade_purchase_operations

    conn, _pooled = _open_connection(database_url, read_only=False)
    try:
        try:
            result = upgrade_purchase_operations(conn, dry_run=False)
            postchecks = _c019_postchecks(conn)
        except PostcheckFailure as error:
            conn.rollback()
            return {
                "status": "C019_POSTCHECK_FAIL",
                "transaction": "ROLLED_BACK",
                **_safe_error(error),
            }
        except Exception as error:
            conn.rollback()
            return {
                "status": "C019_MIGRATION_FAIL",
                "transaction": "ROLLED_BACK",
                **_safe_error(error),
            }
        try:
            conn.commit()
        except Exception as error:
            return {
                "status": "C019_COMMIT_UNKNOWN",
                "transaction": "UNKNOWN",
                "commit_outcome": "UNKNOWN",
                "automatic_retry": False,
                **_safe_error(error),
            }
        return {
            "status": "COMMITTED",
            "transaction": "COMMITTED",
            "result": _migration_result(result),
            "postchecks": postchecks,
        }
    finally:
        conn.close()


def run_option_c_migration(
    *,
    repo_root: Path,
    expected_git_sha: str,
    target_environment: str,
    execute: bool = False,
    owner_gate: str | None = None,
    inventory_mutation_freeze_confirmed: bool = False,
    database_url: str | None = None,
    expected_postgres_version: str = "PostgreSQL 16",
) -> dict[str, Any]:
    """Run read-only preflight or the two approved migrations.

    database_url is intentionally an in-process test seam and is not a CLI
    option. Production CLI execution reads only DATABASE_URL.
    """

    base: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "target_environment": target_environment,
        "execute_requested": execute,
        "owner_gate_required": OWNER_GATE,
        "migration_order": list(MIGRATION_ORDER),
        "migration_hashes": EXPECTED_MIGRATION_HASHES,
        "database_connection_authority": (
            "test_injected_database_url"
            if database_url is not None
            else "DATABASE_URL_runtime_environment_via_db_wrapper"
        ),
        "equipment_defs_authority": "app.EQUIPMENT_DEFS",
        "existing_inventory_mutation_freeze_mechanism": False,
        "mutation_guard": {
            "database_queries": 0,
            "writes": 0,
            "commits": 0,
            "rollbacks": 0,
            "migration_execution": 0,
        },
    }
    if target_environment not in SUPPORTED_TARGETS:
        return {**base, "status": "BLOCKED_TARGET_ENVIRONMENT"}
    if owner_gate is not None and owner_gate != OWNER_GATE:
        return {
            **base,
            "status": "BLOCKED_OWNER_GATE",
            "gate_check": "FAIL",
            "wrong_gate_rejected": True,
        }
    if execute and owner_gate != OWNER_GATE:
        return {
            **base,
            "status": "BLOCKED_OWNER_GATE",
            "gate_check": "FAIL",
            "wrong_gate_rejected": True,
        }
    if execute and target_environment == "production" and not inventory_mutation_freeze_confirmed:
        return {
            **base,
            "status": "BLOCKED_INVENTORY_MUTATION_FREEZE_REQUIRED",
            "gate_check": "PASS",
            "inventory_mutation_freeze": "NOT_CONFIRMED",
        }

    source = _check_source_binding(repo_root, expected_git_sha)
    base["source_binding"] = source
    if source.get("status") != "PASS":
        return {**base, "status": "BLOCKED_SOURCE_BINDING"}

    try:
        equipment_definitions = _load_equipment_definitions()
        conn, pooled = _open_connection(database_url, read_only=True)
    except Exception as error:
        return {**base, "status": "BLOCKED_CONNECTION_OR_AUTHORITY", **_safe_error(error)}

    try:
        preflight = _preflight(
            conn,
            repo_root=repo_root,
            expected_git_sha=expected_git_sha,
            target_environment=target_environment,
            equipment_definitions=equipment_definitions,
            expected_postgres_version=expected_postgres_version,
        )
    except Exception as error:
        _close_connection(conn, pooled=pooled, read_only=True)
        return {**base, "status": "BLOCKED_PREFLIGHT", **_safe_error(error)}
    _close_connection(conn, pooled=pooled, read_only=True)
    base["preflight"] = preflight

    if not preflight["ready"]:
        base["status"] = "PRECHECK_FAIL"
        base["mutation_guard"]["database_queries"] = "YES"
        return base
    if not execute:
        base["status"] = (
            "ALREADY_VALID"
            if preflight["sequence_plan"] == "ALREADY_VALID"
            else "DRY_RUN_READY"
        )
        base["mutation_guard"]["database_queries"] = "YES"
        return base

    if preflight["sequence_plan"] == "ALREADY_VALID":
        base["status"] = "ALREADY_VALID"
        base["mutation_guard"]["database_queries"] = "YES"
        return base

    phase_results: list[dict[str, Any]] = []
    b033_state = preflight["checks"]["schema_states"]["b033"]["state"]
    if b033_state == "B033_ALREADY_VALID":
        phase_results.append(
            {
                "migration": MIGRATION_ORDER[0],
                "status": "ALREADY_VALID",
                "transaction": "NOT_STARTED",
            }
        )
    else:
        b033 = _run_b033(
            database_url=database_url,
            equipment_definitions=equipment_definitions,
        )
        phase_results.append({"migration": MIGRATION_ORDER[0], **b033})
        if b033["status"] != "COMMITTED":
            base["status"] = b033["status"]
            base["phases"] = phase_results
            base["mutation_guard"].update(
                {
                    "database_queries": "YES",
                    "rollbacks": 1 if b033["transaction"] == "ROLLED_BACK" else 0,
                    "migration_execution": 1,
                }
            )
            return base

    c019 = _run_c019(database_url=database_url)
    phase_results.append({"migration": MIGRATION_ORDER[1], **c019})
    base["phases"] = phase_results
    base["mutation_guard"].update(
        {
            "database_queries": "YES",
            "commits": sum(phase.get("transaction") == "COMMITTED" for phase in phase_results),
            "rollbacks": sum(phase.get("transaction") == "ROLLED_BACK" for phase in phase_results),
            "migration_execution": 2 if b033_state != "B033_ALREADY_VALID" else 1,
        }
    )
    if c019["status"] != "COMMITTED":
        base["status"] = "B033_COMMITTED_COIN_PURCHASE_FAILED"
        base["partial_sequence"] = {
            "b033": "COMMITTED",
            "coin_purchase_operations": "ABSENT_OR_UNVERIFIED",
            "canonical_shop_gate": "OFF",
            "canonical_equipment_loadout_gate": "OFF",
            "b033_compatible_runtime_required": True,
            "old_c32_runtime_rollback": False,
            "automatic_retry": False,
        }
        return base

    base["status"] = "EXECUTED"
    return base


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Narrow, Owner-gated Option C schema migration runner"
    )
    parser.add_argument("-RepoRoot", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("-ExpectedGitSha", required=True)
    parser.add_argument("-TargetEnvironment", choices=sorted(SUPPORTED_TARGETS), required=True)
    parser.add_argument("-ExpectedPostgresVersion", default="PostgreSQL 16")
    parser.add_argument("-Execute", action="store_true")
    parser.add_argument("-OwnerGate")
    parser.add_argument(
        "-InventoryMutationFreezeConfirmed",
        action="store_true",
        help="External evidence only; the runner does not provide a freeze mechanism.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_option_c_migration(
        repo_root=args.RepoRoot.resolve(),
        expected_git_sha=args.ExpectedGitSha,
        target_environment=args.TargetEnvironment,
        execute=args.Execute,
        owner_gate=args.OwnerGate,
        inventory_mutation_freeze_confirmed=args.InventoryMutationFreezeConfirmed,
        expected_postgres_version=args.ExpectedPostgresVersion,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in {"DRY_RUN_READY", "ALREADY_VALID", "EXECUTED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "EXPECTED_MIGRATION_HASHES",
    "MIGRATION_ORDER",
    "OWNER_GATE",
    "SCHEMA_VERSION",
    "main",
    "run_option_c_migration",
]
