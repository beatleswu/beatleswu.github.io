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


SCHEMA_VERSION = "C031_COMMERCE_PRODUCTION_READINESS_PREFLIGHT_V2"

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
_TARGET_ENVIRONMENTS = frozenset({"disposable", "production", "other"})

_RUNTIME_SOURCE_CANDIDATES: dict[str, tuple[str, ...]] = {
    "monster": (
        "app.py",
        "monster_settlement.py",
        "monster_reward_runtime.py",
        "monster_runtime.py",
    ),
    "admin": (
        "app.py",
        "admin_equipment.py",
        "admin_grants.py",
        "admin_runtime.py",
    ),
    "equipment_route": (
        "app.py",
        "equipment_routes.py",
        "equipment_loadout_runtime.py",
        "routes/equipment.py",
    ),
    "shop": (
        "app.py",
        "shop_routes.py",
        "commerce_routes.py",
        "shop_runtime.py",
    ),
}

_SHOP_GATE_NAMES = frozenset(
    {
        "CANONICAL_SHOP_RUNTIME_ENABLED",
        "CANONICAL_SHOP_ENABLED",
        "SHOP_CANONICAL_RUNTIME_ENABLED",
        "CANONICAL_COIN_SHOP_PURCHASE_FLAG",
    }
)
_SHOP_GATE_VALUES = frozenset({"CANONICAL_COIN_SHOP_PURCHASE_ENABLED"})
_EQUIPMENT_GATE_NAMES = frozenset(
    {
        "CANONICAL_EQUIPMENT_LOADOUT_ENABLED",
        "CANONICAL_EQUIPMENT_LOADOUT_RUNTIME_ENABLED",
        "EQUIPMENT_LOADOUT_CANONICAL_ENABLED",
        "EQUIPMENT_CANONICAL_LOADOUT_FLAG",
    }
)
_EQUIPMENT_GATE_VALUES = frozenset({"EQUIPMENT_CANONICAL_LOADOUT_ENABLED"})
_OWNERSHIP_ROW_OBJECT_NAMES = frozenset(
    {"row", "ownership_row", "ownership_record", "inventory_row"}
)


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


def _source_texts(
    repo_root: Path,
    source_fixture: Mapping[str, str] | None,
) -> dict[str, str]:
    """Return source text for static contract inspection only.

    ``source_fixture`` is intentionally an in-memory mapping.  It lets tests
    prove the future E030-ready contract without changing or importing
    ``app.py``.  The production auditor path reads only known Python source
    files and never executes them.
    """

    if source_fixture is not None:
        return {
            str(relative_path).replace("\\", "/"): str(source)
            for relative_path, source in source_fixture.items()
        }

    paths: set[str] = set()
    for candidates in _RUNTIME_SOURCE_CANDIDATES.values():
        paths.update(candidates)
    paths.update(
        {
            "coin_purchase_authority.py",
            "equipment_ownership_service.py",
            "equipment_loadout_service.py",
            "shop_offer_identity_projection.py",
            "shop_acquisition_result_bridge.py",
            "canonical_acquisition_result.py",
        }
    )
    result: dict[str, str] = {}
    for relative_path in sorted(paths):
        path = repo_root / Path(relative_path)
        if path.is_file() and path.suffix == ".py":
            result[relative_path] = path.read_text(encoding="utf-8")
    return result


def _parsed_source_units(
    source_texts: Mapping[str, str],
) -> tuple[dict[str, ast.Module], dict[str, str]]:
    trees: dict[str, ast.Module] = {}
    errors: dict[str, str] = {}
    for relative_path, source in source_texts.items():
        if not relative_path.endswith(".py"):
            continue
        try:
            trees[relative_path] = ast.parse(source, filename=relative_path)
        except (SyntaxError, ValueError) as exc:
            errors[relative_path] = str(exc)
    return trees, errors


def _candidate_units(
    trees: Mapping[str, ast.Module],
    candidates: Iterable[str],
) -> dict[str, ast.Module]:
    candidate_set = {str(path).replace("\\", "/") for path in candidates}
    return {
        relative_path: tree
        for relative_path, tree in trees.items()
        if relative_path in candidate_set
    }


def _module_import_aliases(
    tree: ast.Module,
    module_name: str,
    function_name: str | None = None,
) -> tuple[set[str], set[str]]:
    """Return module aliases and only aliases for the requested function.

    A broad ``from module import ...`` alias set is unsafe for source
    contracts: ``from x import foo, bar`` must not make a call to ``foo``
    satisfy a check for ``bar``.  Keeping the requested name at import
    resolution time also handles ``as`` aliases without relying on text
    matching.
    """

    module_aliases: set[str] = set()
    function_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == module_name:
                    module_aliases.add(alias.asname or module_name.rsplit(".", 1)[-1])
        elif isinstance(node, ast.ImportFrom) and node.module == module_name:
            for alias in node.names:
                if alias.name == "*" or (
                    function_name is not None and alias.name != function_name
                ):
                    continue
                function_aliases.add(alias.asname or alias.name)
    return module_aliases, function_aliases


def _call_targets(
    tree: ast.Module,
    *,
    module_name: str,
    function_name: str,
) -> list[ast.Call]:
    module_aliases, function_aliases = _module_import_aliases(
        tree,
        module_name,
        function_name,
    )
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        matches = False
        if isinstance(function, ast.Name):
            matches = function.id in function_aliases
        elif isinstance(function, ast.Attribute) and isinstance(function.value, ast.Name):
            matches = (
                function.attr == function_name
                and function.value.id in module_aliases
            )
        if matches:
            calls.append(node)
    return calls


def _call_target_contexts(
    tree: ast.Module,
    *,
    module_name: str,
    function_name: str,
) -> list[tuple[ast.Call, tuple[str, ...], ast.FunctionDef | ast.AsyncFunctionDef | None]]:
    """Return target calls with their enclosing function scope.

    The scope is part of the evidence so a matching helper call in an
    unrelated function cannot satisfy a Monster/Admin/Shop route contract.
    """

    call_scopes: dict[int, tuple[str, ...]] = {}
    function_nodes: dict[tuple[str, ...], ast.FunctionDef | ast.AsyncFunctionDef] = {}

    class _ScopeVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.scope: list[str] = []

        def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            self.scope.append(node.name)
            scope = tuple(self.scope)
            function_nodes[scope] = node
            self.generic_visit(node)
            self.scope.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            self._visit_function(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
            self._visit_function(node)

        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            call_scopes[id(node)] = tuple(self.scope)
            self.generic_visit(node)

    _ScopeVisitor().visit(tree)
    return [
        (
            call,
            call_scopes.get(id(call), ()),
            function_nodes.get(call_scopes.get(id(call), ())),
        )
        for call in _call_targets(
            tree,
            module_name=module_name,
            function_name=function_name,
        )
    ]


def _function_parameter_names(
    function: ast.FunctionDef | ast.AsyncFunctionDef | None,
) -> set[str]:
    if function is None:
        return set()
    arguments = function.args
    names = {
        argument.arg
        for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)
    }
    if arguments.vararg:
        names.add(arguments.vararg.arg)
    if arguments.kwarg:
        names.add(arguments.kwarg.arg)
    return names


def _has_named_decorator(
    function: ast.FunctionDef | ast.AsyncFunctionDef | None,
    decorator_name: str,
) -> bool:
    if function is None:
        return False
    for decorator in function.decorator_list:
        expression = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(expression, ast.Name) and expression.id == decorator_name:
            return True
        if isinstance(expression, ast.Attribute) and expression.attr == decorator_name:
            return True
    return False


def _literal_keyword(call: ast.Call, keyword: str) -> Any:
    for argument in call.keywords:
        if argument.arg == keyword:
            try:
                return ast.literal_eval(argument.value)
            except (ValueError, TypeError):
                return None
    return None


def _is_exact_ownership_row_expression(
    expression: ast.expr,
    safe_names: set[str],
) -> bool:
    if isinstance(expression, ast.Name):
        return (
            expression.id in safe_names
            and expression.id not in _OWNERSHIP_ROW_OBJECT_NAMES
        )
    if isinstance(expression, ast.Attribute):
        return expression.attr == "id" and isinstance(expression.value, ast.Name) and expression.value.id in safe_names
    if isinstance(expression, ast.Subscript) and isinstance(expression.value, ast.Name):
        if expression.value.id not in safe_names:
            return False
        try:
            key = ast.literal_eval(expression.slice)
        except (ValueError, TypeError):
            return False
        return key == "id"
    return False


def _server_owned_inventory_names(
    function: ast.FunctionDef | ast.AsyncFunctionDef | None,
) -> tuple[set[str], bool]:
    """Find names that can safely represent an authenticated inventory row."""

    if function is None:
        return set(), False
    source_literals = [
        node.value
        for node in ast.walk(function)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    normalized = [" ".join(value.upper().split()) for value in source_literals]
    has_authenticated_lookup = any(
        "PLAYER_INVENTORY" in value
        and "WHERE" in value
        and re.search(r"\bID\b", value)
        and "USER_ID" in value
        for value in normalized
    )
    safe_names = {"row", "ownership_row", "ownership_record", "inventory_row"}
    if has_authenticated_lookup:
        safe_names.update({"inv_id", "row_id", "ownership_id", "ownership_row_id"})

    changed = True
    while changed:
        changed = False
        for node in ast.walk(function):
            if not isinstance(node, ast.Assign):
                continue
            if not _is_exact_ownership_row_expression(node.value, safe_names):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id not in safe_names:
                    safe_names.add(target.id)
                    changed = True
    return safe_names, has_authenticated_lookup


def _ownership_id_forwarded(
    call: ast.Call,
    *,
    safe_names: set[str],
) -> bool:
    for argument in call.keywords:
        if argument.arg != "ownership_row_id":
            continue
        if _is_exact_ownership_row_expression(argument.value, safe_names):
            return True
    return False


def _gate_default_off(
    units: Mapping[str, ast.Module],
    gate_names: Iterable[str],
    gate_values: Iterable[str] = (),
) -> tuple[bool, str | None]:
    names = set(gate_names)
    values = {str(value).strip().upper() for value in gate_values}
    flag_aliases: set[str] = set()
    for relative_path, tree in units.items():
        for node in ast.walk(tree):
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets.extend(node.targets)
            elif isinstance(node, ast.AnnAssign):
                targets.append(node.target)
            else:
                continue
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id in names:
                    if isinstance(value, str) and value.strip().upper() in values:
                        flag_aliases.add(target.id)
                    if value is False or (
                        isinstance(value, int)
                        and not isinstance(value, bool)
                        and value == 0
                    ):
                        return True, relative_path
                    if isinstance(value, str) and value.strip().upper() == "OFF":
                        return True, relative_path
                elif isinstance(value, str) and value.strip().upper() in values:
                    flag_aliases.add(target.id)

    for relative_path, tree in units.items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            is_env_helper = (
                isinstance(function, ast.Name) and function.id == "_env_flag_enabled"
            ) or (
                isinstance(function, ast.Attribute)
                and function.attr == "_env_flag_enabled"
            )
            if not is_env_helper or not node.args:
                continue
            default = _literal_keyword(node, "default")
            if default is not False:
                continue
            flag = node.args[0]
            if isinstance(flag, ast.Name) and flag.id in flag_aliases:
                return True, relative_path
            try:
                if isinstance(flag, ast.Constant) and str(flag.value).strip().upper() in values:
                    return True, relative_path
            except (AttributeError, TypeError):
                pass
    return False, None


def _delegation_check(
    *,
    trees: Mapping[str, ast.Module],
    parse_errors: Mapping[str, str],
    source_candidates: Iterable[str],
    source_value: str,
) -> dict[str, Any]:
    units = _candidate_units(trees, source_candidates)
    candidate_paths = tuple(str(path).replace("\\", "/") for path in source_candidates)
    candidate_errors = {
        path: parse_errors[path] for path in candidate_paths if path in parse_errors
    }
    if candidate_errors:
        return _check(
            CHECK_BLOCKED,
            expected=f"B040 grant_equipment_ownership(..., source={source_value!r})",
            details={"source_parse_errors": candidate_errors},
        )
    if not units:
        return _check(
            CHECK_BLOCKED,
            expected="source file for the runtime writer",
            details={"reason": "no candidate source file was available"},
        )

    evidence: list[dict[str, Any]] = []
    for relative_path, tree in units.items():
        for call, scope, function in _call_target_contexts(
            tree,
            module_name="equipment_ownership_service",
            function_name="grant_equipment_ownership",
        ):
            scope_names = set(scope)
            if source_value == "drop":
                in_expected_path = any(
                    name == "grant_functional_item"
                    or "monster" in name.lower()
                    or "settle" in name.lower()
                    for name in scope_names
                )
            else:
                in_expected_path = any(
                    name == "admin_set_equipment"
                    or name.lower().startswith("admin")
                    for name in scope_names
                )
            if not in_expected_path:
                continue

            source_argument: ast.expr | None = None
            for keyword in call.keywords:
                if keyword.arg == "source":
                    source_argument = keyword.value
                    break
            if source_argument is None and len(call.args) > 3:
                source_argument = call.args[3]
            parameter_names = _function_parameter_names(function)
            source_matches = False
            if source_argument is not None:
                try:
                    source_matches = ast.literal_eval(source_argument) == source_value
                except (ValueError, TypeError):
                    source_matches = (
                        isinstance(source_argument, ast.Name)
                        and source_argument.id in parameter_names
                    )
            unsafe_direct_writer = False
            if function is not None:
                for node in ast.walk(function):
                    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                        continue
                    normalized = " ".join(node.value.upper().split())
                    if re.search(r"\bINSERT\s+INTO\s+PLAYER_INVENTORY\b", normalized):
                        unsafe_direct_writer = True
                        break
            client_authority_keywords = {
                "canonical_slot",
                "slot",
                "equipped",
                "damage",
                "mitigation",
                "stat",
                "effect",
            }
            client_authority_present = any(
                keyword.arg in client_authority_keywords for keyword in call.keywords
            )
            admin_authentication_present = (
                source_value != "admin"
                or _has_named_decorator(function, "admin_required")
            )
            if (
                source_matches
                and not unsafe_direct_writer
                and not client_authority_present
                and admin_authentication_present
            ):
                evidence.append(
                    {
                        "path": relative_path,
                        "line": getattr(call, "lineno", None),
                        "scope": list(scope),
                        "source_argument": (
                            "positional_parameter"
                            if isinstance(source_argument, ast.Name)
                            else "literal"
                        ),
                        "admin_authentication": admin_authentication_present,
                    }
                )
    return _check(
        PASS if evidence else FAIL,
        expected={
            "service": "B040 grant_equipment_ownership",
            "source_semantics": source_value,
            "function_scoped": True,
            "direct_player_inventory_writer": False,
        },
        observed=evidence,
        details={
            "reason": None
            if evidence
            else "runtime writer does not source-verify delegation to B040",
            "candidate_paths": list(candidate_paths),
        },
    )


def _equipment_route_check(
    *,
    trees: Mapping[str, ast.Module],
    parse_errors: Mapping[str, str],
) -> dict[str, Any]:
    units = _candidate_units(trees, _RUNTIME_SOURCE_CANDIDATES["equipment_route"])
    candidate_paths = _RUNTIME_SOURCE_CANDIDATES["equipment_route"]
    candidate_errors = {
        path: parse_errors[path] for path in candidate_paths if path in parse_errors
    }
    if candidate_errors:
        return _check(
            CHECK_BLOCKED,
            expected="B034/B041 equip_owned_item and unequip_owned_item with exact ownership_row_id",
            details={"source_parse_errors": candidate_errors},
        )
    if not units:
        return _check(
            CHECK_BLOCKED,
            expected="canonical Equipment route source",
            details={"reason": "no candidate source file was available"},
        )

    calls_by_function: dict[str, list[dict[str, Any]]] = {
        "equip_owned_item": [],
        "unequip_owned_item": [],
    }
    for relative_path, tree in units.items():
        for function_name in calls_by_function:
            for call, scope, function in _call_target_contexts(
                tree,
                module_name="equipment_loadout_service",
                function_name=function_name,
            ):
                if not any("equip" in name.lower() for name in scope):
                    continue
                safe_names, authenticated_lookup = _server_owned_inventory_names(function)
                if authenticated_lookup and _ownership_id_forwarded(
                    call,
                    safe_names=safe_names,
                ):
                    calls_by_function[function_name].append(
                        {
                            "path": relative_path,
                            "line": getattr(call, "lineno", None),
                            "scope": list(scope),
                        }
                    )
    gate_off, gate_path = _gate_default_off(
        units,
        _EQUIPMENT_GATE_NAMES,
        _EQUIPMENT_GATE_VALUES,
    )
    missing = [name for name, evidence in calls_by_function.items() if not evidence]
    status = PASS if not missing and gate_off else FAIL
    return _check(
        status,
        expected={
            "delegation": "B034/B041",
            "functions": list(calls_by_function),
            "exact_ownership_row_id_forwarding": True,
            "default_gate": "OFF",
        },
        observed={
            "calls": calls_by_function,
            "gate_off": gate_off,
            "gate_source": gate_path,
        },
        details={
            "missing_contracts": missing,
            "reason": None
            if status == PASS
            else "canonical Equipment route is not source-verifiably B034/B041 compatible",
        },
    )


def _shop_runtime_check(
    *,
    trees: Mapping[str, ast.Module],
    parse_errors: Mapping[str, str],
) -> dict[str, Any]:
    units = _candidate_units(trees, _RUNTIME_SOURCE_CANDIDATES["shop"])
    candidate_paths = _RUNTIME_SOURCE_CANDIDATES["shop"]
    candidate_errors = {
        path: parse_errors[path] for path in candidate_paths if path in parse_errors
    }
    if candidate_errors:
        return _check(
            CHECK_BLOCKED,
            expected="C025/C029 -> C026 -> D024 canonical Shop route with default gate OFF",
            details={"source_parse_errors": candidate_errors},
        )
    if not units:
        return _check(
            CHECK_BLOCKED,
            expected="canonical Shop route source",
            details={"reason": "no candidate source file was available"},
        )

    required_calls = {
        "c025_projection": ("shop_offer_identity_projection", "normalize_shop_offer"),
        "c026_purchase": ("coin_purchase_authority", "purchase_with_coins"),
        "d024_result": ("shop_acquisition_result_bridge", "adapt_committed_shop_purchase"),
    }
    evidence: dict[str, list[dict[str, Any]]] = {name: [] for name in required_calls}
    for relative_path, tree in units.items():
        for evidence_name, (module_name, function_name) in required_calls.items():
            for call, scope, _function in _call_target_contexts(
                tree,
                module_name=module_name,
                function_name=function_name,
            ):
                expected_scope_markers = {
                    "c025_projection": ("classify_shop_request", "canonical_shop_offer"),
                    "c026_purchase": ("canonical_shop_purchase_response",),
                    "d024_result": ("canonical_shop_purchase_response",),
                }[evidence_name]
                if not any(
                    marker in scope_name.lower()
                    for scope_name in scope
                    for marker in expected_scope_markers
                ):
                    continue
                evidence[evidence_name].append(
                    {
                        "path": relative_path,
                        "line": getattr(call, "lineno", None),
                        "scope": list(scope),
                    }
                )
    gate_off, gate_path = _gate_default_off(
        units,
        _SHOP_GATE_NAMES,
        _SHOP_GATE_VALUES,
    )
    pre_mutation_dispatch = _shop_pre_mutation_dispatch_check(units)
    missing = [name for name, call_sites in evidence.items() if not call_sites]
    if not pre_mutation_dispatch["pass"]:
        missing.append("pre_mutation_dispatch")
    status = PASS if not missing and gate_off else FAIL
    return _check(
        status,
        expected={
            "calls": {
                "c025_projection": "normalize_shop_offer",
                "c026_purchase": "purchase_with_coins",
                "d024_result": "adapt_committed_shop_purchase",
            },
            "pre_mutation_dispatch": {
                "routes": ["shop_buy", "shop_buy_appearance"],
                "classifier": "_classify_shop_request",
            },
            "default_gate": "OFF",
        },
        observed={
            "calls": evidence,
            "gate_off": gate_off,
            "gate_source": gate_path,
            "pre_mutation_dispatch": pre_mutation_dispatch,
        },
        details={
            "missing_contracts": missing,
            "reason": None
            if status == PASS
            else "canonical Shop route is not source-verifiably C025/C026/D024 compatible",
        },
    )


def _shop_pre_mutation_dispatch_check(
    units: Mapping[str, ast.Module],
) -> dict[str, Any]:
    required_routes = ("shop_buy", "shop_buy_appearance")
    evidence: dict[str, dict[str, bool]] = {}
    for _relative_path, tree in units.items():
        _calls, functions = _function_contexts(tree)
        for route_name in required_routes:
            for scope, function in functions.items():
                if scope[-1:] != (route_name,):
                    continue
                called_names = {
                    call_name
                    for call in ast.walk(function)
                    if isinstance(call, ast.Call)
                    for call_name in (_called_name(call),)
                    if call_name
                }
                evidence[route_name] = {
                    "gate": "_canonical_coin_shop_purchase_enabled" in called_names,
                    "classifier": "_classify_shop_request" in called_names,
                    "canonical_dispatch": "_canonical_shop_purchase_response" in called_names,
                }
    # C048 closes the default /api/shop/buy legacy mutation seam, and C049
    # closes the separate appearance compatibility fallback.  Both routes
    # must classify and dispatch canonically regardless of the Shop UI gate;
    # keep the evidence shape stable for existing audit consumers while
    # expressing the two route contracts independently.
    complete = (
        evidence.get("shop_buy", {}).get("classifier") is True
        and evidence.get("shop_buy", {}).get("canonical_dispatch") is True
        and evidence.get("shop_buy_appearance", {}).get("classifier") is True
        and evidence.get("shop_buy_appearance", {}).get("canonical_dispatch") is True
    )
    return {"pass": complete, "routes": evidence}


def _called_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _function_contexts(
    tree: ast.Module,
) -> tuple[
    dict[int, tuple[str, ...]],
    dict[tuple[str, ...], ast.FunctionDef | ast.AsyncFunctionDef],
]:
    call_scopes: dict[int, tuple[str, ...]] = {}
    function_nodes: dict[tuple[str, ...], ast.FunctionDef | ast.AsyncFunctionDef] = {}

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.scope: list[str] = []

        def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            self.scope.append(node.name)
            scope = tuple(self.scope)
            function_nodes[scope] = node
            self.generic_visit(node)
            self.scope.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            self._visit_function(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
            self._visit_function(node)

        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            call_scopes[id(node)] = tuple(self.scope)
            self.generic_visit(node)

    _Visitor().visit(tree)
    return call_scopes, function_nodes


def _audit_runtime_source_contract(
    repo_root: Path,
    *,
    source_fixture: Mapping[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    try:
        source_texts = _source_texts(repo_root, source_fixture)
        trees, parse_errors = _parsed_source_units(source_texts)
    except Exception as exc:
        blocked = _check(
            CHECK_BLOCKED,
            expected="readable Python source contract",
            details={"error": str(exc)},
        )
        return {
            "monster_equipment_writer_source_compatibility": blocked,
            "admin_equipment_writer_source_compatibility": blocked,
            "equipment_route_source_compatibility": blocked,
            "canonical_shop_runtime_source_compatibility": blocked,
            "runtime_writer_compatibility": blocked,
        }

    checks = {
        "monster_equipment_writer_source_compatibility": _delegation_check(
            trees=trees,
            parse_errors=parse_errors,
            source_candidates=_RUNTIME_SOURCE_CANDIDATES["monster"],
            source_value="drop",
        ),
        "admin_equipment_writer_source_compatibility": _delegation_check(
            trees=trees,
            parse_errors=parse_errors,
            source_candidates=_RUNTIME_SOURCE_CANDIDATES["admin"],
            source_value="admin",
        ),
        "equipment_route_source_compatibility": _equipment_route_check(
            trees=trees,
            parse_errors=parse_errors,
        ),
        "canonical_shop_runtime_source_compatibility": _shop_runtime_check(
            trees=trees,
            parse_errors=parse_errors,
        ),
    }
    statuses = [str(check.get("status")) for check in checks.values()]
    if CHECK_BLOCKED in statuses:
        runtime_status = CHECK_BLOCKED
    elif FAIL in statuses:
        runtime_status = FAIL
    else:
        runtime_status = PASS
    checks["runtime_writer_compatibility"] = _check(
        runtime_status,
        expected="all four Option-C runtime seams source-verifiably compatible",
        observed={name: check["status"] for name, check in checks.items()},
        details={
            "caller_evidence_can_override_source_failure": False,
            "source_fixture_used": source_fixture is not None,
        },
    )
    return checks


def _verify_legacy_text_timestamp_contract(repo_root: Path) -> dict[str, Any]:
    """Report the independent C030 timestamp proof, never writer readiness."""

    source_path = repo_root / "coin_purchase_authority.py"
    test_path = repo_root / "tests/test_c030_c026_postgres_legacy_text_timestamp_compatibility.py"
    doc_path = repo_root / (
        "docs/planning/architecture/"
        "C030_C026_POSTGRES_LEGACY_TEXT_TIMESTAMP_COMPATIBILITY_PROOF_001.md"
    )
    missing_paths = [
        str(path.relative_to(repo_root)).replace("\\", "/")
        for path in (source_path, test_path, doc_path)
        if not path.is_file()
    ]
    if missing_paths:
        return _check(
            CHECK_BLOCKED,
            expected="C030 timestamp proof artifacts and current timestamp adapter",
            details={"missing_paths": missing_paths},
        )
    source_text = source_path.read_text(encoding="utf-8")
    test_text = test_path.read_text(encoding="utf-8")
    doc_text = doc_path.read_text(encoding="utf-8")
    required_source_markers = (
        "def _timestamp",
        "value.tzinfo",
        "value.isoformat()",
        "currency_log",
        "obtained_at",
        "player_wardrobe",
    )
    required_proof_markers = (
        "TEXT NOT NULL",
        "timezone-aware Python value",
        "Legacy TEXT timestamp compatibility is now proven",
    )
    missing = [marker for marker in required_source_markers if marker not in source_text]
    missing.extend(marker for marker in required_proof_markers if marker not in test_text + doc_text)
    return _check(
        PASS if not missing else FAIL,
        expected={
            "task": "C030_C026_POSTGRES_LEGACY_TEXT_TIMESTAMP_COMPATIBILITY_PROOF_001",
            "runtime_writer_compatibility": "not inferred",
        },
        observed={
            "source_path": "coin_purchase_authority.py",
            "test_path": str(test_path.relative_to(repo_root)).replace("\\", "/"),
            "doc_path": str(doc_path.relative_to(repo_root)).replace("\\", "/"),
            "proof_status": "PASS" if not missing else "INCOMPLETE",
        },
        details={
            "missing_markers": missing,
            "reported_separately_from_runtime_writer_compatibility": True,
        },
    )


def audit_source_contract(
    *,
    repo_root: Path,
    expected_application_source_sha: str | None,
    observed_application_source_sha: str | None,
    current_master_sha: str | None,
    feature_gate_facts: Mapping[str, Any] | None,
    legacy_writer_compatibility: str | None,
    target_environment: str | None = None,
    source_contract_fixture: Mapping[str, str] | None = None,
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

    runtime_checks = _audit_runtime_source_contract(
        repo_root,
        source_fixture=source_contract_fixture,
    )
    caller_evidence = (
        legacy_writer_compatibility.strip().upper()
        if isinstance(legacy_writer_compatibility, str)
        else None
    )
    runtime_checks["runtime_writer_compatibility"]["details"] = {
        **dict(runtime_checks["runtime_writer_compatibility"].get("details", {})),
        "caller_legacy_writer_compatibility": caller_evidence,
        "caller_evidence_role": "secondary_only_ignored_for_readiness",
    }
    return {
        "application_source_sha": source_sha_check,
        "equipment_definition_source_contract": equipment_contract,
        "canonical_shop_feature_gate": gate_check(
            "canonical_shop", "canonical Shop"
        ),
        "canonical_equipment_loadout_feature_gate": gate_check(
            "canonical_equipment_loadout", "canonical Equipment loadout"
        ),
        "legacy_text_timestamp_compatibility": _verify_legacy_text_timestamp_contract(
            repo_root
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
        **runtime_checks,
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


class _CountingCursor:
    def __init__(self, owner: "_CountingConnection", cursor: Any):
        self._owner = owner
        self._cursor = cursor

    def execute(self, sql: str, parameters: Any = None) -> Any:
        self._owner.database_queries += 1
        return self._cursor.execute(sql, parameters)

    def executemany(self, sql: str, parameters: Any) -> Any:
        self._owner.database_queries += 1
        return self._cursor.executemany(sql, parameters)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)

    def __enter__(self) -> "_CountingCursor":
        self._cursor.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any:
        return self._cursor.__exit__(exc_type, exc_val, exc_tb)


class _CountingConnection:
    """Transparent query accounting without changing the caller connection."""

    def __init__(self, connection: Any):
        self._connection = connection
        self.database_queries = 0

    def execute(self, sql: str, parameters: Any = None) -> Any:
        self.database_queries += 1
        return self._connection.execute(sql, parameters)

    def cursor(self, *args: Any, **kwargs: Any) -> _CountingCursor:
        return _CountingCursor(self, self._connection.cursor(*args, **kwargs))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


def _target_environment_check(target_environment: str | None) -> dict[str, Any]:
    if target_environment is None:
        return _check(
            CHECK_BLOCKED,
            expected=sorted(_TARGET_ENVIRONMENTS),
            details={"reason": "target environment must be caller-supplied"},
        )
    normalized = target_environment.strip().lower() if isinstance(target_environment, str) else None
    if normalized not in _TARGET_ENVIRONMENTS:
        return _check(
            CHECK_BLOCKED,
            expected=sorted(_TARGET_ENVIRONMENTS),
            observed=target_environment,
            details={"reason": "target environment is not an allowed explicit classification"},
        )
    return _check(
        PASS,
        expected=sorted(_TARGET_ENVIRONMENTS),
        observed=normalized,
        details={"caller_supplied": True, "hostname_inference": False},
    )


def _database_read_only_check(
    *,
    conn: Any | None,
    enforced: bool | None,
    error: str | None,
) -> dict[str, Any]:
    if conn is None:
        return _check(
            "NOT_APPLICABLE",
            expected="driver-level read-only session when a database connection is supplied",
            observed="no connection",
            details={"select_only_probe_still_required": True},
        )
    if enforced is True:
        return _check(
            PASS,
            expected="driver-level read-only session",
            observed="enforced",
            details={"select_only_probe_still_required": True},
        )
    if enforced is False:
        return _check(
            FAIL,
            expected="driver-level read-only session",
            observed="not enforced",
            details={
                "error": error,
                "select_only_probe_still_required": True,
            },
        )
    return _check(
        "NOT_APPLICABLE",
        expected="driver-level read-only session when a database connection is supplied",
        observed="caller-managed connection",
        details={
            "reason": "run_preflight did not create the connection; SELECT-only source probe remains enforced",
            "select_only_probe_still_required": True,
        },
    )


def _production_query_status(
    *,
    target_environment: str | None,
    database_queries: int,
) -> str:
    if database_queries == 0:
        return "NO"
    if target_environment == "production":
        return "YES"
    if target_environment == "disposable":
        return "NO"
    return "UNKNOWN"


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
    target_environment: str | None = None,
    database_read_only_enforced: bool | None = None,
    database_read_only_error: str | None = None,
    source_contract_fixture: Mapping[str, str] | None = None,
    migration_paths: Iterable[str] = DEFAULT_MIGRATION_PATHS,
) -> dict[str, Any]:
    source_checks = audit_source_contract(
        repo_root=repo_root,
        expected_application_source_sha=expected_application_source_sha,
        observed_application_source_sha=observed_application_source_sha,
        current_master_sha=current_master_sha,
        feature_gate_facts=feature_gate_facts,
        legacy_writer_compatibility=legacy_writer_compatibility,
        source_contract_fixture=source_contract_fixture,
        migration_paths=migration_paths,
    )

    definitions = equipment_definitions
    if definitions is None:
        try:
            definitions = load_equipment_definitions_from_source(repo_root)
        except Exception:
            definitions = None

    database_query_count = 0
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
        counted_conn = _CountingConnection(conn)
        try:
            database_checks = audit_database(
                counted_conn,
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
        database_query_count = counted_conn.database_queries

    normalized_target_environment = (
        target_environment.strip().lower()
        if isinstance(target_environment, str)
        else target_environment
    )
    database_checks["database_read_only_enforcement"] = _database_read_only_check(
        conn=conn,
        enforced=database_read_only_enforced,
        error=database_read_only_error,
    )
    checks = {
        "target_environment": _target_environment_check(target_environment),
        **source_checks,
        **database_checks,
    }
    status = _overall_status(checks)
    database_query_observed = "YES" if database_query_count else "NO"
    production_query_observed = _production_query_status(
        target_environment=normalized_target_environment
        if normalized_target_environment in _TARGET_ENVIRONMENTS
        else None,
        database_queries=database_query_count,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "checks": checks,
        "TARGET_ENVIRONMENT": normalized_target_environment,
        "DATABASE_QUERY_PERFORMED_BY_C031": database_query_observed,
        "PRODUCTION_QUERY_PERFORMED_BY_C031": production_query_observed,
        "provenance": {
            "expected_application_source_sha": expected_application_source_sha,
            "observed_application_source_sha": observed_application_source_sha,
            "current_master_sha": current_master_sha,
            "repository_root": str(repo_root),
            "database_target": normalized_target_environment,
        },
        "policy": {
            "go_production_db_migration": "DEFERRED_TO_OWNER_COORDINATOR",
            "revenue_enablement_implied": False,
            "target_environment": normalized_target_environment,
            "database_query_performed_by_c031": database_query_observed,
            "production_query_performed_by_c031": production_query_observed,
            "production_mutation_performed_by_c031": "NO",
            "feature_enablement_performed_by_c031": False,
        },
        "mutation_guard": {
            "database_queries": database_query_count,
            "database_query_performed": database_query_observed,
            "writes": 0,
            "commits": 0,
            "rollbacks": 0,
            "migration_execution": 0,
            "read_only_session_enforced": database_read_only_enforced,
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
    parser.add_argument(
        "--target-environment",
        choices=tuple(sorted(_TARGET_ENVIRONMENTS)),
        required=True,
        help="Explicit target classification; C031 never infers Production from a hostname",
    )
    parser.add_argument("--canonical-shop-gate", choices=("OFF", "ON"))
    parser.add_argument("--canonical-equipment-loadout-gate", choices=("OFF", "ON"))
    parser.add_argument(
        "--legacy-writer-compatibility",
        choices=("PASS", "FAIL"),
        help="Deprecated secondary caller evidence; it cannot override source compatibility",
    )
    parser.add_argument("--expected-postgres-version")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    conn: Any | None = None
    raw: Any | None = None
    connection_error: str | None = None
    database_read_only_enforced: bool | None = None
    database_read_only_error: str | None = None
    if args.database_url:
        try:
            import psycopg2
            from psycopg2.extras import DictCursor

            from db import PostgresConnectionWrapper

            raw = psycopg2.connect(args.database_url, cursor_factory=DictCursor)
            try:
                raw.set_session(readonly=True)
                database_read_only_enforced = True
            except Exception as exc:
                database_read_only_enforced = False
                database_read_only_error = str(exc)
            conn = PostgresConnectionWrapper(raw, pooled=False)
        except Exception as exc:
            connection_error = str(exc)
    result = run_preflight(
        repo_root=args.repo_root.resolve(),
        expected_application_source_sha=args.expected_application_source_sha,
        observed_application_source_sha=args.observed_application_source_sha,
        current_master_sha=args.current_master_sha,
        target_environment=args.target_environment,
        feature_gate_facts={
            "canonical_shop": _parse_gate(args.canonical_shop_gate),
            "canonical_equipment_loadout": _parse_gate(
                args.canonical_equipment_loadout_gate
            ),
        },
        legacy_writer_compatibility=args.legacy_writer_compatibility,
        conn=conn,
        database_read_only_enforced=database_read_only_enforced,
        database_read_only_error=database_read_only_error,
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
