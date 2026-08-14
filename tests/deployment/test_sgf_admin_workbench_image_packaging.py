"""Regression contract for the SGF Admin Workbench app-image package.

The Production candidate built from ae25fdfa passed its image build but failed
the deployment canary at process startup: app.py imports
``sgf_admin_workbench`` while the Dockerfile's explicit COPY list omitted the
module. Source-only application tests could not detect that image boundary.

The same explicit-copy boundary also protects ``xp_settlement.py``: app.py
imports it during process startup, while the XP writer/shadow/schema flags
remain dormant by default. Keeping both checks in this existing image
packaging architecture prevents a second, weaker packaging test framework.

The fast tests below keep the explicit Dockerfile and build-manifest contracts
in sync. Built-image and built-container checks run when
``SGF_WORKBENCH_PACKAGING_TEST_IMAGE`` names a real validation image; without
that variable they are explicitly skipped and are not packaging evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "Dockerfile"
BUILD_MANIFEST = REPO_ROOT / "deploy" / "build-manifest.json"
MODULE = REPO_ROOT / "sgf_admin_workbench.py"
XP_MODULE = REPO_ROOT / "xp_settlement.py"
IMAGE_TAG = os.environ.get("SGF_WORKBENCH_PACKAGING_TEST_IMAGE")
BUILT_IMAGE_SKIP_REASON = (
    "SGF_WORKBENCH_PACKAGING_TEST_IMAGE not set; real built-image and "
    "built-container validation is skipped, not passed"
)


def _read(path: pathlib.Path) -> str:
    assert path.is_file(), f"expected file to exist: {path}"
    return path.read_text(encoding="utf-8")


def _docker_copy_sources(content: str) -> list[str]:
    sources: list[str] = []
    for line in content.replace("\\\n", " ").splitlines():
        stripped = line.strip()
        if stripped.startswith("COPY "):
            sources.extend(stripped.split()[1:-1])
    return sources


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_in_image(*arguments: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "python", IMAGE_TAG, *arguments],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _healthz(url: str) -> tuple[int | None, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except (urllib.error.URLError, ConnectionError, OSError):
        return None, b""


def test_dockerfile_explicitly_copies_sgf_admin_workbench_module():
    content = _read(DOCKERFILE)
    sources = _docker_copy_sources(content)
    assert "sgf_admin_workbench.py" in sources
    assert "." not in sources and "*.py" not in sources, (
        "the packaging fix must preserve the explicit COPY boundary"
    )


def test_build_manifest_tracks_and_verifies_sgf_admin_workbench_module():
    manifest = json.loads(_read(BUILD_MANIFEST))
    tracked = set(manifest["build_inputs"]["tracked_in_canonical_branch_this_sprint"])
    verified = set(manifest["post_build_verification_files"])
    assert "sgf_admin_workbench.py" in tracked
    assert "/app/sgf_admin_workbench.py" in verified


def test_dockerfile_explicitly_copies_xp_settlement_module():
    content = _read(DOCKERFILE)
    sources = _docker_copy_sources(content)
    assert "xp_settlement.py" in sources
    assert "." not in sources and "*.py" not in sources, (
        "xp settlement packaging must preserve the explicit COPY boundary"
    )


def test_build_manifest_tracks_and_verifies_xp_settlement_module():
    manifest = json.loads(_read(BUILD_MANIFEST))
    tracked = set(manifest["build_inputs"]["tracked_in_canonical_branch_this_sprint"])
    verified = set(manifest["post_build_verification_files"])
    assert "xp_settlement.py" in tracked
    assert "/app/xp_settlement.py" in verified


@pytest.mark.skipif(not IMAGE_TAG, reason=BUILT_IMAGE_SKIP_REASON)
def test_built_image_contains_exact_sgf_admin_workbench_module_bytes():
    script = (
        "import hashlib,pathlib; "
        "p=pathlib.Path('/app/sgf_admin_workbench.py'); "
        "assert p.is_file() and p.stat().st_size > 0; "
        "print(hashlib.sha256(p.read_bytes()).hexdigest())"
    )
    result = _run_in_image("-c", script)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == _sha256(MODULE)


@pytest.mark.skipif(not IMAGE_TAG, reason=BUILT_IMAGE_SKIP_REASON)
def test_built_image_contains_exact_xp_settlement_module_bytes():
    script = (
        "import hashlib,pathlib; "
        "p=pathlib.Path('/app/xp_settlement.py'); "
        "assert p.is_file() and p.stat().st_size > 0; "
        "print(hashlib.sha256(p.read_bytes()).hexdigest())"
    )
    result = _run_in_image("-c", script)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == _sha256(XP_MODULE)


@pytest.mark.skipif(not IMAGE_TAG, reason=BUILT_IMAGE_SKIP_REASON)
def test_built_image_imports_workbench_and_app_with_direct_apply_off_by_default():
    script = (
        "import os; "
        "assert 'GO_ODYSSEY_ADMIN_DIRECT_APPLY_ENABLED' not in os.environ; "
        "import sgf_admin_workbench; "
        "import app as application; "
        "assert application._direct_apply_enabled() is False; "
        "print('SGF_ADMIN_WORKBENCH_IMPORT=PASS'); "
        "print('DIRECT_APPLY_DEFAULT_ENABLED=NO')"
    )
    result = subprocess.run(
        [
            "docker", "run", "--rm",
            "--env", "SECRET_KEY=non-production-packaging-test",
            "--env", "SOCKETIO_ASYNC_MODE=threading",
            "--entrypoint", "python", IMAGE_TAG, "-c", script,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "SGF_ADMIN_WORKBENCH_IMPORT=PASS" in result.stdout
    assert "DIRECT_APPLY_DEFAULT_ENABLED=NO" in result.stdout


@pytest.mark.skipif(not IMAGE_TAG, reason=BUILT_IMAGE_SKIP_REASON)
def test_built_image_imports_xp_settlement_and_app_with_xp_locks_off():
    script = (
        "import os; "
        "assert all(os.environ.get(name, '').strip().lower() not in {'1','true','yes','on'} "
        "for name in ('XP_LEDGER_SCHEMA_ENABLED','XP_SETTLEMENT_ENABLED','XP_SHADOW_ENABLED')); "
        "import xp_settlement; "
        "assert xp_settlement.xp_ledger_schema_enabled() is False; "
        "assert xp_settlement.xp_settlement_enabled() is False; "
        "assert xp_settlement.xp_shadow_enabled() is False; "
        "import app as application; "
        "print('XP_SETTLEMENT_IMPORT=PASS'); "
        "print('APP_IMPORT=PASS'); "
        "print('XP_DEFAULTS=OFF')"
    )
    result = subprocess.run(
        [
            "docker", "run", "--rm",
            "--env", "SECRET_KEY=non-production-packaging-test",
            "--env", "SOCKETIO_ASYNC_MODE=threading",
            "--entrypoint", "python", IMAGE_TAG, "-c", script,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "XP_SETTLEMENT_IMPORT=PASS" in result.stdout
    assert "APP_IMPORT=PASS" in result.stdout
    assert "XP_DEFAULTS=OFF" in result.stdout


@pytest.mark.skipif(not IMAGE_TAG, reason=BUILT_IMAGE_SKIP_REASON)
def test_built_container_starts_and_serves_healthz():
    port = _free_port()
    container = f"sgf-workbench-packaging-{uuid.uuid4().hex[:12]}"
    command = [
        "docker", "run", "-d", "--rm",
        "--name", container,
        "--publish", f"127.0.0.1:{port}:8080",
        "--env", "SECRET_KEY=non-production-packaging-test",
        "--env", "SOCKETIO_ASYNC_MODE=threading",
        "--entrypoint", "python",
        IMAGE_TAG,
        "-c", "from app import app; app.run(host='0.0.0.0', port=8080)",
    ]
    started = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert started.returncode == 0, started.stderr
    try:
        deadline = time.time() + 45
        status, body = None, b""
        while time.time() < deadline:
            status, body = _healthz(f"http://127.0.0.1:{port}/healthz")
            if status is not None:
                break
            time.sleep(1)
        if status != 200:
            logs = subprocess.run(
                ["docker", "logs", container], capture_output=True, text=True, timeout=15
            )
            pytest.fail(
                f"validation container did not serve /healthz: status={status}\n"
                f"stdout:\n{logs.stdout}\nstderr:\n{logs.stderr}"
            )
        assert json.loads(body) == {"ok": True}
        running = subprocess.run(
            ["docker", "inspect", container, "--format", "{{.State.Running}}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert running.returncode == 0
        assert running.stdout.strip() == "true"
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=30)
