import io
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from startup_diagnostics import StartupDiagnostics


PREFIX = "[startup-diagnostic] "


def events(stream):
    return [
        json.loads(line[len(PREFIX) :])
        for line in stream.getvalue().splitlines()
        if line.startswith(PREFIX)
    ]


def test_successful_phases_and_readiness_are_structured_and_correlated():
    stream = io.StringIO()
    diagnostics = StartupDiagnostics(stream=stream, boot_id="12345678-1234-5678-1234-567812345678")
    diagnostics.mark("python_start")
    with diagnostics.phase("database_initialization"):
        pass
    diagnostics.mark_ready("healthz_readiness")

    rows = events(stream)
    assert {row["phase"] for row in rows} == {
        "python_start",
        "database_initialization",
        "healthz_readiness",
    }
    assert all(row["boot_id"] == "12345678-1234-5678-1234-567812345678" for row in rows)
    assert all(row["timestamp_utc"].endswith("+00:00") for row in rows)
    assert all(row["elapsed_seconds"] >= 0 for row in rows)
    assert rows[-1]["status"] == "ready"


def test_delayed_stack_diagnostics_are_bounded_stack_only_and_cancel_on_readiness():
    stream = io.StringIO()
    diagnostics = StartupDiagnostics(
        stream=stream,
        initial_delay_seconds=0.01,
        snapshot_interval_seconds=0.01,
        max_snapshots=3,
    )
    sentinel_secret_local_value = "never-serialize-this-value"
    assert sentinel_secret_local_value
    diagnostics.start_delayed_snapshots()
    deadline = time.monotonic() + 1
    while len([row for row in events(stream) if row["phase"] == "delayed_start_stack"]) < 2:
        assert time.monotonic() < deadline
        time.sleep(0.005)
    diagnostics.mark_ready()
    count_after_ready = len([row for row in events(stream) if row["phase"] == "delayed_start_stack"])
    time.sleep(0.04)

    output = stream.getvalue()
    rows = [row for row in events(stream) if row["phase"] == "delayed_start_stack"]
    assert 1 <= len(rows) <= 3
    assert len(rows) == count_after_ready
    assert "never-serialize-this-value" not in output
    assert "locals" not in output
    assert rows[0]["threads"]
    assert set(rows[0]["threads"][0]["frames"][0]) == {"file", "function", "line"}


def test_readiness_before_threshold_prevents_snapshots():
    stream = io.StringIO()
    diagnostics = StartupDiagnostics(stream=stream, initial_delay_seconds=0.05, max_snapshots=3)
    diagnostics.start_delayed_snapshots()
    diagnostics.mark_ready()
    time.sleep(0.08)
    assert not [row for row in events(stream) if row["phase"] == "delayed_start_stack"]


def test_startup_exception_is_re_raised_without_message_or_secret_values():
    stream = io.StringIO()
    diagnostics = StartupDiagnostics(stream=stream)
    with pytest.raises(RuntimeError, match="sentinel-private-value"):
        with diagnostics.phase("database_initialization"):
            raise RuntimeError("sentinel-private-value")
    output = stream.getvalue()
    assert "sentinel-private-value" not in output
    failure = events(stream)[-1]
    assert failure["status"] == "failure"
    assert failure["exception_type"] == "RuntimeError"


@pytest.mark.parametrize("flag", ["true", "false"])
def test_real_app_import_and_healthz_succeed_in_both_shadow_modes(flag, tmp_path):
    code = "import app; r=app.app.test_client().get('/healthz'); print(r.status_code)"
    environment = os.environ.copy()
    environment.update(
        {
            "SECRET_KEY": "synthetic-test-only",
            "SHADOW_JUDGING_ENABLED": flag,
            "QUESTIONS_JSON_PATH": str(tmp_path / "absent-synthetic-content"),
            "SHADOW_EVENTS_PATH": str(tmp_path / "synthetic-events"),
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "200"
    diagnostics = [json.loads(line[len(PREFIX) :]) for line in result.stderr.splitlines() if line.startswith(PREFIX)]
    assert any(row["phase"] == "app_module_import" and row["status"] == "success" for row in diagnostics)
    assert any(row["phase"].endswith("healthz_readiness") and row["status"] == "ready" for row in diagnostics)
    assert "synthetic-test-only" not in result.stderr
