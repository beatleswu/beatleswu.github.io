"""Shared disposable PostgreSQL harness for integration tests.

The application never imports this module.  It deliberately keeps Docker
startup and database readiness separate: a published TCP port is not proof
that PostgreSQL has completed initialization, and one successful connection
is not enough evidence that a container stayed healthy under a busy Docker
daemon.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import socket
import subprocess
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest


DEFAULT_IMAGE = "postgres:16-alpine"
DEFAULT_USER = "go"
DEFAULT_PASSWORD = "go"
DEFAULT_DATABASE = "go_odyssey"
DOCKER_COMMAND_TIMEOUT = 180.0
CONTAINER_STARTUP_TIMEOUT = 240.0
POSTGRES_CONNECT_TIMEOUT = 5
READINESS_STABLE_PROBES = 3


def _timeout_from_environment(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(1.0, value)


def _docker_timeout() -> float:
    return _timeout_from_environment(
        "GO_ODYSSEY_POSTGRES_DOCKER_TIMEOUT_SECONDS",
        DOCKER_COMMAND_TIMEOUT,
    )


def _startup_timeout() -> float:
    return _timeout_from_environment(
        "GO_ODYSSEY_POSTGRES_STARTUP_TIMEOUT_SECONDS",
        CONTAINER_STARTUP_TIMEOUT,
    )


def _run_docker(*args: str, timeout: float | None = None, check: bool = False):
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=_docker_timeout() if timeout is None else timeout,
        check=check,
    )


def docker_available() -> bool:
    """Return true only when Docker responds with a server identity.

    Docker Desktop can be temporarily busy while old test workloads are
    being reaped.  A bounded retry avoids treating that transient API delay
    as a PostgreSQL/application result while still failing closed when the
    daemon never responds.
    """

    if shutil.which("docker") is None:
        return False
    for _ in range(2):
        try:
            result = _run_docker(
                "info",
                "--format",
                "{{.ServerVersion}}",
                timeout=_docker_timeout(),
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and result.stdout.strip():
            return True
    return False


def wait_for_port(host: str, port: int, timeout: float | None = None) -> None:
    deadline = time.monotonic() + (_startup_timeout() if timeout is None else timeout)
    while time.monotonic() < deadline:
        with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(1.0)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.25)
    raise TimeoutError(f"timed out waiting for {host}:{port}")


def wait_for_postgres(
    database_url: str,
    timeout: float | None = None,
    *,
    stable_probes: int = READINESS_STABLE_PROBES,
) -> None:
    """Require repeated successful SQL probes, not merely an open socket."""

    import psycopg2

    deadline = time.monotonic() + (_startup_timeout() if timeout is None else timeout)
    stable = 0
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            conn = psycopg2.connect(
                database_url,
                connect_timeout=POSTGRES_CONNECT_TIMEOUT,
            )
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                assert cursor.fetchone()[0] == 1
            conn.close()
            stable += 1
            if stable >= stable_probes:
                return
        except Exception as exc:  # pragma: no cover - timing dependent
            last_error = exc
            stable = 0
        time.sleep(0.5)
    raise RuntimeError(f"PostgreSQL did not reach stable readiness: {last_error}")


def _container_state(container_id: str) -> str:
    result = _run_docker(
        "inspect",
        "--format",
        "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
        container_id,
        timeout=min(_docker_timeout(), 30.0),
    )
    if result.returncode != 0:
        return f"inspect-error:{result.stderr.strip() or result.stdout.strip()}"
    return result.stdout.strip()


def _container_diagnostics(container_id: str) -> str:
    try:
        inspect = _run_docker(
            "inspect",
            "--format",
            "{{json .State}}",
            container_id,
            timeout=min(_docker_timeout(), 30.0),
        )
        inspect_text = (inspect.stdout or inspect.stderr).strip()
    except Exception as exc:  # pragma: no cover - daemon failure path
        inspect_text = f"inspect unavailable: {exc}"
    try:
        logs = _run_docker(
            "logs",
            "--tail",
            "80",
            container_id,
            timeout=min(_docker_timeout(), 30.0),
        )
        logs_text = (logs.stdout + logs.stderr).strip()
    except Exception as exc:  # pragma: no cover - daemon failure path
        logs_text = f"logs unavailable: {exc}"
    return f"state={inspect_text}\nlogs:\n{logs_text}"


def _remove_container(container_id_or_name: str) -> None:
    try:
        _run_docker(
            "rm",
            "--force",
            container_id_or_name,
            timeout=min(_docker_timeout(), 60.0),
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _wait_for_container_health(container_id: str) -> None:
    deadline = time.monotonic() + _startup_timeout()
    last_state = "unknown"
    while time.monotonic() < deadline:
        try:
            last_state = _container_state(container_id)
        except (OSError, subprocess.TimeoutExpired) as exc:
            last_state = f"inspect-error:{exc}"
        status, _, health = last_state.partition("|")
        if status in {"exited", "dead"}:
            raise RuntimeError(
                f"disposable PostgreSQL container stopped before readiness: {last_state}\n"
                f"{_container_diagnostics(container_id)}"
            )
        if status == "running" and health == "healthy":
            return
        time.sleep(0.5)
    raise TimeoutError(
        f"disposable PostgreSQL health timeout: {last_state}\n"
        f"{_container_diagnostics(container_id)}"
    )


def _wait_for_host_port(container_id: str) -> int:
    deadline = time.monotonic() + _startup_timeout()
    last_output = ""
    while time.monotonic() < deadline:
        try:
            result = _run_docker(
                "port",
                container_id,
                "5432/tcp",
                timeout=min(_docker_timeout(), 30.0),
            )
            last_output = (result.stdout or result.stderr).strip()
            if result.returncode == 0 and last_output:
                endpoint = last_output.splitlines()[0].rsplit(":", 1)
                if len(endpoint) == 2 and endpoint[1].isdigit():
                    return int(endpoint[1])
        except (OSError, subprocess.TimeoutExpired) as exc:
            last_output = str(exc)
        time.sleep(0.5)
    raise TimeoutError(f"disposable PostgreSQL port timeout: {last_output}")


@contextmanager
def disposable_postgres(
    *,
    name_prefix: str = "go-odyssey-pg-test",
    user: str = DEFAULT_USER,
    password: str = DEFAULT_PASSWORD,
    database: str = DEFAULT_DATABASE,
    image: str = DEFAULT_IMAGE,
) -> Iterator[dict[str, str | int]]:
    """Yield a disposable PostgreSQL connection record after stable readiness."""

    if not docker_available():
        pytest.skip("Docker daemon unavailable for disposable PostgreSQL")

    container_name = f"{name_prefix}-{uuid.uuid4().hex[:12]}"
    container_id = ""
    try:
        run = _run_docker(
            "run",
            "--rm",
            "--detach",
            "--name",
            container_name,
            "--env",
            f"POSTGRES_PASSWORD={password}",
            "--env",
            f"POSTGRES_USER={user}",
            "--env",
            f"POSTGRES_DB={database}",
            "--publish",
            "127.0.0.1::5432",
            "--health-cmd",
            f"pg_isready -U {user} -d {database}",
            "--health-interval",
            "1s",
            "--health-timeout",
            "5s",
            "--health-retries",
            "120",
            "--health-start-period",
            "2s",
            image,
            check=True,
        )
        container_id = run.stdout.strip()
        if not container_id:
            raise RuntimeError("Docker returned no disposable PostgreSQL container id")

        _wait_for_host_port(container_id)
        _wait_for_container_health(container_id)
        port = _wait_for_host_port(container_id)
        database_url = f"postgresql://{user}:{password}@127.0.0.1:{port}/{database}"
        wait_for_port("127.0.0.1", port)
        wait_for_postgres(database_url)
        yield {
            "container_id": container_id,
            "host": "127.0.0.1",
            "port": port,
            "database_url": database_url,
            "image": image,
        }
    except Exception as exc:
        diagnostics = _container_diagnostics(container_id or container_name)
        raise RuntimeError(
            f"disposable PostgreSQL harness failed for {container_name}: {exc}\n{diagnostics}"
        ) from exc
    finally:
        # Use the name when docker run timed out before returning an id.  The
        # name is unique to this context, so this cannot remove another test's
        # container and prevents an orphaned disposable database.
        _remove_container(container_id or container_name)
