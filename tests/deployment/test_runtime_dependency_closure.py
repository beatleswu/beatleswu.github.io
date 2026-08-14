"""Production-image runtime dependency closure regression.

The Production image deliberately uses an explicit Python COPY contract.  A
normal ``import app`` check is not enough: Workbench, payment, Map Battle and
other paths contain lazy imports.  This test resolves repository-local imports
from the governed entrypoints with the AST (without executing application
code), then compares the resulting closure with Dockerfile and build-manifest
coverage.  Optional community-reward code remains separately classified and
must still be packaged when present.

Real image and disposable PostgreSQL checks are opt-in through environment
variables so the canonical source-only deployment suite remains deterministic.
They are release gates when a formal image is supplied.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib
import re
import shutil
import socket
import subprocess
import time
import uuid
from dataclasses import dataclass

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "Dockerfile"
BUILD_MANIFEST = REPO_ROOT / "deploy" / "build-manifest.json"
COMPOSE_PROD = REPO_ROOT / "docker-compose.prod.yml"
ENTRYPOINTS = ("app.py", "scheduler.py", "shadow_judging.py")

# These two roots are guarded by the explicit COMMUNITY_LEADERBOARD_REWARDS
# flag and are not wired into canonical docker-compose.prod.yml.  Their local
# descendants are included in the closure and must remain packaged, but are
# reported as OPTIONAL rather than silently treated as missing Production
# startup dependencies.
OPTIONAL_ROOTS = {
    "community_leaderboard_rewards_scheduler",
    "tools.community_leaderboard_rewards_exact_period",
}

IMAGE_TAG = os.environ.get("E10_RUNTIME_DEPENDENCY_TEST_IMAGE", "").strip()
RUN_POSTGRES_CANARY = os.environ.get("E10_RUN_POSTGRES_CANARY", "").strip() == "1"
SKIP_IMAGE_REASON = (
    "E10_RUNTIME_DEPENDENCY_TEST_IMAGE is not set; real image evidence is "
    "skipped, not passed"
)


@dataclass(frozen=True)
class LocalModule:
    name: str
    path: pathlib.Path


@dataclass(frozen=True)
class ImportObservation:
    source: pathlib.Path
    name: str
    kind: str
    line: int


def _tracked_python_files() -> list[pathlib.Path]:
    result = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [REPO_ROOT / line for line in result.stdout.splitlines() if line]


def _module_name(path: pathlib.Path) -> str:
    relative = path.relative_to(REPO_ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _module_index() -> dict[str, LocalModule]:
    index: dict[str, LocalModule] = {}
    for path in _tracked_python_files():
        name = _module_name(path)
        index[name] = LocalModule(name=name, path=path)
    return index


def _parent_package_names(name: str) -> list[str]:
    parts = name.split(".")
    return [".".join(parts[:index]) for index in range(1, len(parts))]


def _resolve_local(name: str, index: dict[str, LocalModule]) -> list[LocalModule]:
    """Resolve a module and every existing package __init__ parent."""
    if not name:
        return []
    found: list[LocalModule] = []
    exact = index.get(name)
    if exact is not None:
        found.append(exact)
    for parent in _parent_package_names(name):
        candidate = index.get(parent)
        if candidate is not None:
            found.append(candidate)
    return found


def _current_package(module_name: str, index: dict[str, LocalModule]) -> list[str]:
    module = index[module_name]
    if module.path.name == "__init__.py":
        return module_name.split(".") if module_name else []
    return module_name.split(".")[:-1]


def _absolute_import_names(node: ast.ImportFrom, module_name: str, index: dict[str, LocalModule]) -> list[str]:
    if node.level == 0:
        prefix = (node.module or "").split(".") if node.module else []
    else:
        package = _current_package(module_name, index)
        if node.level > len(package) + 1:
            return []
        prefix = package[: len(package) - (node.level - 1)]
        if node.module:
            prefix += node.module.split(".")
    names: list[str] = []
    base = ".".join(prefix)
    if base:
        names.append(base)
    for alias in node.names:
        if alias.name == "*":
            continue
        child = ".".join(prefix + [alias.name])
        if child:
            names.append(child)
    return names


def _dynamic_import_aliases(tree: ast.AST) -> tuple[set[str], set[str]]:
    """Return imported names that can invoke importlib.import_module.

    The callable has two common AST shapes:

    * ``importlib.import_module(...)`` is an Attribute whose value is a
      Name (not another Attribute).
    * ``from importlib import import_module`` is a direct Name call.

    Track aliases explicitly so neither form becomes an unobserved dynamic
    import, while unrelated functions named ``import_module`` remain outside
    this special case.
    """
    importlib_module_aliases: set[str] = set()
    import_module_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    importlib_module_aliases.add(alias.asname or "importlib")
        elif (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module == "importlib"
        ):
            for alias in node.names:
                if alias.name == "import_module":
                    import_module_aliases.add(alias.asname or "import_module")
    return importlib_module_aliases, import_module_aliases


def _scan_module(
    module: LocalModule,
    index: dict[str, LocalModule],
) -> tuple[list[ImportObservation], list[LocalModule]]:
    tree = ast.parse(module.path.read_text(encoding="utf-8"), filename=str(module.path))
    importlib_module_aliases, import_module_aliases = _dynamic_import_aliases(tree)
    observations: list[ImportObservation] = []
    resolved: list[LocalModule] = []
    for node in ast.walk(tree):
        names: list[tuple[str, str]] = []
        if isinstance(node, ast.Import):
            names = [(alias.name, "AST_IMPORT") for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(name, "AST_IMPORT") for name in _absolute_import_names(node, module.name, index)]
        elif isinstance(node, ast.Call):
            is_builtin_import = isinstance(node.func, ast.Name) and node.func.id == "__import__"
            is_importlib_import = (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "import_module"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in importlib_module_aliases
            ) or (
                isinstance(node.func, ast.Name)
                and node.func.id in import_module_aliases
            )
            if is_builtin_import or is_importlib_import:
                argument = node.args[0] if node.args else None
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    names = [(argument.value, "DYNAMIC_LITERAL")]
                elif isinstance(argument, ast.Name) and argument.id == "__name__":
                    # This is an intentional self-module handoff used by the
                    # community scheduler, not an unresolved dependency.
                    continue
                else:
                    observations.append(
                        ImportObservation(module.path, "<dynamic-unresolved>", "DYNAMIC_UNRESOLVED", node.lineno)
                    )
                    continue
        for name, kind in names:
            observations.append(ImportObservation(module.path, name, kind, node.lineno))
            resolved.extend(_resolve_local(name, index))
    return observations, resolved


def _scan_fixture(source: str, tmp_path: pathlib.Path) -> tuple[list[ImportObservation], list[LocalModule]]:
    """Run the real AST scanner against a deterministic temporary module."""
    fixture_path = tmp_path / "dynamic_import_fixture.py"
    fixture_path.write_text(source, encoding="utf-8")
    fixture = LocalModule(name="dynamic_import_fixture", path=fixture_path)
    index = _module_index()
    index[fixture.name] = fixture
    return _scan_module(fixture, index)


def test_scanner_detects_standard_importlib_literal_and_resolves_local_module(tmp_path):
    observations, resolved = _scan_fixture(
        "import importlib\n"
        "importlib.import_module('migrations.sgf_admin_workbench_v1')\n",
        tmp_path,
    )
    assert any(
        observation.kind == "DYNAMIC_LITERAL"
        and observation.name == "migrations.sgf_admin_workbench_v1"
        for observation in observations
    )
    assert any(module.name == "migrations.sgf_admin_workbench_v1" for module in resolved)


def test_scanner_classifies_standard_importlib_dynamic_argument_as_unresolved(tmp_path):
    observations, _resolved = _scan_fixture(
        "import importlib\n"
        "name = 'migrations.sgf_admin_workbench_v1'\n"
        "importlib.import_module(name)\n",
        tmp_path,
    )
    assert any(observation.kind == "DYNAMIC_UNRESOLVED" for observation in observations)


def test_scanner_detects_builtin_import_literal_and_resolves_local_module(tmp_path):
    observations, resolved = _scan_fixture(
        "__import__('migrations.sgf_admin_workbench_v1')\n",
        tmp_path,
    )
    assert any(
        observation.kind == "DYNAMIC_LITERAL"
        and observation.name == "migrations.sgf_admin_workbench_v1"
        for observation in observations
    )
    assert any(module.name == "migrations.sgf_admin_workbench_v1" for module in resolved)


def test_scanner_classifies_builtin_import_dynamic_argument_as_unresolved(tmp_path):
    observations, _resolved = _scan_fixture(
        "name = 'migrations.sgf_admin_workbench_v1'\n"
        "__import__(name)\n",
        tmp_path,
    )
    assert any(observation.kind == "DYNAMIC_UNRESOLVED" for observation in observations)


def test_scanner_accepts_intentional_self_module_import_handoff(tmp_path):
    observations, resolved = _scan_fixture("__import__(__name__)\n", tmp_path)
    assert not any(observation.kind == "DYNAMIC_UNRESOLVED" for observation in observations)
    assert not any(observation.kind == "DYNAMIC_LITERAL" for observation in observations)
    assert resolved == []


def test_scanner_supports_importlib_import_module_alias_form(tmp_path):
    observations, resolved = _scan_fixture(
        "from importlib import import_module\n"
        "import_module('migrations.sgf_admin_workbench_v1')\n",
        tmp_path,
    )
    assert any(
        observation.kind == "DYNAMIC_LITERAL"
        and observation.name == "migrations.sgf_admin_workbench_v1"
        for observation in observations
    )
    assert any(module.name == "migrations.sgf_admin_workbench_v1" for module in resolved)


def dependency_closure() -> tuple[dict[str, LocalModule], list[ImportObservation]]:
    index = _module_index()
    queue = [index[pathlib.Path(entry).stem] for entry in ENTRYPOINTS]
    seen: dict[str, LocalModule] = {}
    observations: list[ImportObservation] = []
    while queue:
        module = queue.pop()
        if module.name in seen:
            continue
        seen[module.name] = module
        current_observations, children = _scan_module(module, index)
        observations.extend(current_observations)
        for child in children:
            if child.name not in seen:
                queue.append(child)
    return seen, observations


def _optional_module(module: LocalModule) -> bool:
    return any(module.name == root or module.name.startswith(root + ".") for root in OPTIONAL_ROOTS)


def _docker_copy_sources() -> list[str]:
    # Dockerfile COPY instructions are deliberately explicit.  Preserve
    # directory coverage (sgf_engine) while rejecting wildcard expansion.
    content = DOCKERFILE.read_text(encoding="utf-8").replace("\\\n", " ")
    sources: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("COPY "):
            sources.extend(stripped.split()[1:-1])
    return sources


def _docker_covers(path: pathlib.Path, sources: list[str]) -> bool:
    relative = path.relative_to(REPO_ROOT).as_posix()
    for source in sources:
        source = source.replace("\\", "/")
        if "*" in source or "?" in source:
            continue
        if source == relative or source == path.name:
            return True
        source_path = pathlib.PurePosixPath(source.rstrip("/"))
        if source_path.parts and pathlib.PurePosixPath(relative).parts[: len(source_path.parts)] == source_path.parts:
            return True
    return False


def _manifest() -> dict:
    return json.loads(BUILD_MANIFEST.read_text(encoding="utf-8"))


def _image_exec(*args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "python", IMAGE_TAG, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_dependency_closure_has_no_unresolved_dynamic_local_imports():
    _closure, observations = dependency_closure()
    unresolved = [observation for observation in observations if observation.kind == "DYNAMIC_UNRESOLVED"]
    assert unresolved == [], "all Production-reachable dynamic imports must be literal or intentional self-imports"
    assert not any(observation.name == "premium_weekly_job" for observation in observations)


def test_dependency_closure_is_explicitly_packaged_and_governed():
    closure, _observations = dependency_closure()
    assert len(closure) >= 30, "the governed entrypoints must resolve a substantial runtime closure"

    sources = _docker_copy_sources()
    manifest = _manifest()
    tracked = set(manifest["build_inputs"]["tracked_in_canonical_branch_this_sprint"])
    verified = set(manifest["post_build_verification_files"])
    missing_docker: list[str] = []
    missing_manifest: list[str] = []
    missing_verification: list[str] = []
    for module in closure.values():
        relative = module.path.relative_to(REPO_ROOT).as_posix()
        if not _docker_covers(module.path, sources):
            missing_docker.append(relative)
        if relative not in tracked:
            missing_manifest.append(relative)
        if not _optional_module(module) and f"/app/{relative}" not in verified:
            missing_verification.append(relative)
    assert missing_docker == [], f"local runtime modules omitted from Dockerfile: {missing_docker}"
    assert missing_manifest == [], f"local runtime modules omitted from build manifest: {missing_manifest}"
    assert missing_verification == [], f"required local runtime modules lack post-build verification: {missing_verification}"

    for required in (
        "migrations/__init__.py",
        "migrations/sgf_admin_workbench_v1.py",
        "map_battle_runtime.py",
        "map_battle_persistence.py",
    ):
        assert required in tracked
        assert f"/app/{required}" in verified


def test_canonical_production_compose_does_not_wire_unsupported_premium_scheduler():
    content = COMPOSE_PROD.read_text(encoding="utf-8")
    assert "PREMIUM_WEEKLY_SCHEDULER_ENABLED" not in content


def test_premium_weekly_source_is_deterministically_fail_closed():
    content = (REPO_ROOT / "app.py").read_text(encoding="utf-8")
    assert "from premium_weekly_job import" not in content
    assert "unsupported in this release" in content
    assert "threading.Thread(target=worker, name='premium-weekly'" not in content


@pytest.mark.skipif(not IMAGE_TAG, reason=SKIP_IMAGE_REASON)
def test_formal_image_contains_every_closure_path_and_imports_all_required_modules():
    closure, _observations = dependency_closure()
    paths = [module.path.relative_to(REPO_ROOT).as_posix() for module in closure.values()]
    module_names = [module.name for module in closure.values()]
    script = (
        "import hashlib, importlib, pathlib; "
        f"paths={paths!r}; "
        f"module_names={module_names!r}; "
        "missing=[p for p in paths if not (pathlib.Path('/app')/p).is_file()]; "
        "assert not missing, missing; "
        "[importlib.import_module(name) for name in module_names]; "
        "print('FINAL_IMAGE_REQUIRED_DEPENDENCIES_MISSING=[]')"
    )
    result = _image_exec("-c", script, timeout=180)
    assert result.returncode == 0, result.stderr
    assert "FINAL_IMAGE_REQUIRED_DEPENDENCIES_MISSING=[]" in result.stdout


@pytest.mark.skipif(not IMAGE_TAG, reason=SKIP_IMAGE_REASON)
def test_formal_image_migrations_are_exact_and_xp_locks_remain_off():
    migration_files = ("migrations/__init__.py", "migrations/sgf_admin_workbench_v1.py")
    expected = {path: _sha256(REPO_ROOT / path) for path in migration_files}
    script = (
        "import hashlib, pathlib; "
        f"expected={expected!r}; "
        "actual={p:hashlib.sha256((pathlib.Path('/app')/p).read_bytes()).hexdigest() for p in expected}; "
        "assert actual == expected, (actual, expected); "
        "import migrations, migrations.sgf_admin_workbench_v1, xp_settlement; "
        "assert not xp_settlement.xp_ledger_schema_enabled(); "
        "assert not xp_settlement.xp_settlement_enabled(); "
        "assert not xp_settlement.xp_shadow_enabled(); "
        "print('MIGRATIONS_EXACT_BYTES=PASS'); print('ALL_REQUIRED_IMPORTS=PASS')"
    )
    result = subprocess.run(
        [
            "docker", "run", "--rm",
            "--env", "SECRET_KEY=non-production-runtime-closure-test",
            "--entrypoint", "python", IMAGE_TAG, "-c", script,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    assert "MIGRATIONS_EXACT_BYTES=PASS" in result.stdout
    assert "ALL_REQUIRED_IMPORTS=PASS" in result.stdout


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _docker_run(args: list[str], *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", "run", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout)


def _wait_for_postgres(port: int, timeout: int = 90) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = subprocess.run(
            ["docker", "exec", _CANARY_PG_NAME, "pg_isready", "-U", "closure", "-d", "closure"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return
        time.sleep(1)
    raise AssertionError(f"disposable PostgreSQL did not become ready on port {port}")


_CANARY_PG_NAME = f"e10-runtime-closure-pg-{uuid.uuid4().hex[:10]}"


@pytest.mark.skipif(not IMAGE_TAG or not RUN_POSTGRES_CANARY, reason="set E10_RUNTIME_DEPENDENCY_TEST_IMAGE and E10_RUN_POSTGRES_CANARY=1 for the disposable canary")
def test_disposable_postgres_workbench_and_scheduler_canaries():
    if not _docker_available():
        pytest.skip("docker is unavailable")
    pg_port = _free_port()
    app_container = f"e10-runtime-closure-app-{uuid.uuid4().hex[:10]}"
    scheduler_container = f"e10-runtime-closure-scheduler-{uuid.uuid4().hex[:10]}"
    database_url = f"postgresql://closure:closure@host.docker.internal:{pg_port}/closure"
    pg_started = _docker_run(
        [
            "--platform", "linux/arm64", "-d", "--rm", "--name", _CANARY_PG_NAME,
            "-p", f"127.0.0.1:{pg_port}:5432", "-e", "POSTGRES_USER=closure",
            "-e", "POSTGRES_PASSWORD=closure", "-e", "POSTGRES_DB=closure", "postgres:16-alpine",
        ],
        timeout=180,
    )
    assert pg_started.returncode == 0, pg_started.stderr
    common_env = [
        "--env", f"DATABASE_URL={database_url}",
        "--env", "SECRET_KEY=non-production-runtime-closure-test",
        "--env", "SOCKETIO_ASYNC_MODE=threading",
        "--env", "PRODUCTION=0",
        "--env", "COMMUNITY_LEADERBOARD_REWARDS_ENABLED=false",
        "--add-host", "host.docker.internal:host-gateway",
    ]
    try:
        _wait_for_postgres(pg_port)
        migrate = _docker_run(
            common_env + ["--entrypoint", "python", IMAGE_TAG, "-c", (
                "import os, psycopg2; "
                "from migrations.sgf_admin_workbench_v1 import upgrade, validate_schema; "
                "conn=psycopg2.connect(os.environ['DATABASE_URL']); upgrade(conn); conn.commit(); "
                "assert validate_schema(conn)['valid']; print('MIGRATIONS_RUNTIME_IMPORT=PASS')"
            )],
            timeout=180,
        )
        assert migrate.returncode == 0, migrate.stderr
        assert "MIGRATIONS_RUNTIME_IMPORT=PASS" in migrate.stdout

        safe = _docker_run(
            common_env + ["--entrypoint", "python", IMAGE_TAG, "-c", (
                "import os, psycopg2; import app, scheduler, migrations, migrations.sgf_admin_workbench_v1; "
                "import xp_settlement, map_battle_runtime, map_battle_persistence, sgf_admin_workbench; "
                "from migrations.sgf_admin_workbench_v1 import validate_schema; "
                "conn=psycopg2.connect(os.environ['DATABASE_URL']); assert validate_schema(conn)['valid']; "
                "assert not xp_settlement.xp_ledger_schema_enabled(); assert not xp_settlement.xp_settlement_enabled(); "
                "assert not xp_settlement.xp_shadow_enabled(); assert not app._direct_apply_enabled(); "
                "app._start_premium_weekly_scheduler(); print('SAFE_LAZY_RUNTIME_CANARY=PASS')"
            )],
            timeout=180,
        )
        assert safe.returncode == 0, safe.stderr
        assert "SAFE_LAZY_RUNTIME_CANARY=PASS" in safe.stdout

        premium = _docker_run(
            common_env + ["--env", "PREMIUM_WEEKLY_SCHEDULER_ENABLED=1", "--entrypoint", "python", IMAGE_TAG, "-c", (
                "import app\n"
                "try:\n"
                "    app._start_premium_weekly_scheduler()\n"
                "except RuntimeError as exc:\n"
                "    assert 'unsupported in this release' in str(exc); print('PREMIUM_WEEKLY_UNSUPPORTED_ENABLE_CONTRACT=PASS')\n"
                "else: raise AssertionError('unsupported premium scheduler unexpectedly started')"
            )],
            timeout=180,
        )
        assert premium.returncode == 0, premium.stderr
        assert "PREMIUM_WEEKLY_UNSUPPORTED_ENABLE_CONTRACT=PASS" in premium.stdout

        app_port = _free_port()
        app_started = _docker_run(
            common_env + [
                "-d", "--rm", "--name", app_container, "-p", f"127.0.0.1:{app_port}:8080",
                "--env", "PORT=8080", "--entrypoint", "python", IMAGE_TAG, "app.py",
            ],
            timeout=180,
        )
        assert app_started.returncode == 0, app_started.stderr
        deadline = time.time() + 90
        while time.time() < deadline:
            health = subprocess.run(
                ["curl", "--silent", "--show-error", "--fail", f"http://127.0.0.1:{app_port}/healthz"],
                capture_output=True,
                text=True,
            ) if shutil.which("curl") else None
            if health is not None and health.returncode == 0:
                break
            time.sleep(1)
        else:
            logs = subprocess.run(["docker", "logs", app_container], capture_output=True, text=True)
            raise AssertionError(f"app startup canary failed:\n{logs.stdout}\n{logs.stderr}")

        scheduler_started = _docker_run(
            common_env + ["-d", "--rm", "--name", scheduler_container, "--entrypoint", "python", IMAGE_TAG, "scheduler.py"],
            timeout=180,
        )
        assert scheduler_started.returncode == 0, scheduler_started.stderr
        scheduler_deadline = time.time() + 90
        scheduler_output = ""
        while time.time() < scheduler_deadline:
            scheduler_state = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Running}}", scheduler_container],
                capture_output=True,
                text=True,
            )
            scheduler_logs = subprocess.run(
                ["docker", "logs", scheduler_container], capture_output=True, text=True
            )
            scheduler_output = scheduler_logs.stdout + scheduler_logs.stderr
            if "ModuleNotFoundError" in scheduler_output:
                raise AssertionError(f"scheduler startup imported a missing module:\n{scheduler_output}")
            if "scheduler threads started" in scheduler_output:
                break
            assert scheduler_state.returncode == 0 and scheduler_state.stdout.strip() == "true", scheduler_output
            time.sleep(2)
        else:
            raise AssertionError(f"scheduler did not reach its bounded startup marker:\n{scheduler_output}")
    finally:
        for container in (app_container, scheduler_container, _CANARY_PG_NAME):
            subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=30)
