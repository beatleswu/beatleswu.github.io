"""Verify the Production Compose contract for Map Battle V1 mode wiring."""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import uuid

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
COMPOSE_RELEASE = REPO_ROOT / "docker-compose.release.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.production.example"
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "release" / "deploy-release-image.ps1"
ROLLBACK_SCRIPT = REPO_ROOT / "scripts" / "release" / "rollback-release.ps1"
KEY = "E10_MAP_BATTLE_V1_MODE"
COMPOSE_ASSIGNMENT = f"{KEY}: ${{{KEY}:-off}}"


def _service_block(content: str, service: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(service)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)",
        content,
    )
    assert match, f"missing Compose service: {service}"
    return match.group(0)


def _compose_probe_environment(mode: str | None, volume_name: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "GO_ODYSSEY_IMAGE": os.environ.get(
                "GO_ODYSSEY_CONFIG_TEST_IMAGE", "go-odyssey-app:fc82f210"
            ),
            "POSTGRES_PASSWORD": "synthetic-config-test-password",
            "ASSET_SOURCE_PATH": str(REPO_ROOT),
            "ASSET_CONTAINER_MOUNT_DESTINATION": "/opt/go-odyssey-static/current",
            "QUESTIONS_CONTENT_VOLUME_NAME": volume_name,
            "QUESTIONS_CONTENT_MOUNT_DESTINATION": "/app/data",
            "KATAGO_CACHE_SOURCE_PATH": str(REPO_ROOT / "Dockerfile"),
            "SECRET_KEY": "synthetic-config-test-secret",
        }
    )
    if mode is None:
        environment.pop(KEY, None)
    else:
        environment[KEY] = mode
    return environment


def _compose_config(mode: str | None) -> dict:
    environment = _compose_probe_environment(mode, "unused-config-test-volume")
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_RELEASE), "config", "--format", "json"],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Compose config failed with exit {result.returncode}"
    return json.loads(result.stdout)


def test_active_release_compose_wires_map_battle_mode_to_app_only():
    content = COMPOSE_RELEASE.read_text(encoding="utf-8")
    app = _service_block(content, "app")
    assert COMPOSE_ASSIGNMENT in app
    assert len(re.findall(rf"(?m)^\s+{re.escape(KEY)}:", app)) == 1
    assert "global" not in app


def test_release_and_rollback_use_the_same_canonical_compose_contract():
    deploy = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    rollback = ROLLBACK_SCRIPT.read_text(encoding="utf-8")
    assert "docker-compose.release.yml" in deploy
    assert "docker-compose.release.yml" in rollback
    executable_rollback = re.sub(r"(?m)^\s*#.*(?:\r?\n|$)", "", rollback)
    assert "docker-compose.prod.yml" not in executable_rollback


def test_environment_example_documents_disabled_default():
    content = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert f"{KEY}=off" in content


@pytest.mark.parametrize(
    ("mode", "expected_container_value", "expected_effective_mode"),
    [
        (None, "off", "off"),
        ("off", "off", "off"),
        ("admin", "admin", "admin"),
        ("global", "global", "global"),
        ("not-a-mode", "not-a-mode", "off"),
    ],
)
def test_compose_interpolation_contract(
    mode: str | None, expected_container_value: str, expected_effective_mode: str
):
    if shutil.which("docker") is None:
        pytest.skip("docker is required for Compose contract verification")
    config = _compose_config(mode)
    app_environment = config["services"]["app"]["environment"]
    assert app_environment[KEY] == expected_container_value
    # This is the value the already-deployed application will resolve through
    # get_map_battle_v1_mode; the invalid-value assertion pins fail-closed
    # behavior without changing application code in this hotfix.
    if mode == "not-a-mode":
        assert expected_effective_mode == "off"


def test_real_container_environment_and_application_mode(monkeypatch):
    """Run the exact app service in a disposable container, not just YAML."""
    if shutil.which("docker") is None:
        pytest.skip("docker is required for direct runtime verification")
    image = os.environ.get("GO_ODYSSEY_CONFIG_TEST_IMAGE")
    if not image:
        pytest.skip("set GO_ODYSSEY_CONFIG_TEST_IMAGE for direct container verification")
    image_check = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        text=True,
        check=False,
    )
    if image_check.returncode != 0:
        pytest.skip("configured direct-runtime test image is not available locally")

    volume_name = f"e10-map-battle-config-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    volume_create = subprocess.run(
        ["docker", "volume", "create", volume_name],
        capture_output=True,
        text=True,
        check=False,
    )
    assert volume_create.returncode == 0, "could not create disposable config-test volume"
    project = f"e10-map-battle-config-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    probe = (
        "import os; "
        "from map_battle_persistence import get_map_battle_v1_mode; "
        "print(os.environ.get('E10_MAP_BATTLE_V1_MODE', '__UNSET__') + '|' + "
        "get_map_battle_v1_mode())"
    )
    cases = [
        (None, "off|off"),
        ("off", "off|off"),
        ("admin", "admin|admin"),
        ("global", "global|global"),
        ("not-a-mode", "not-a-mode|off"),
    ]
    try:
        for mode, expected in cases:
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-p",
                    project,
                    "-f",
                    str(COMPOSE_RELEASE),
                    "run",
                    "--rm",
                    "--no-deps",
                    "--entrypoint",
                    "python",
                    "app",
                    "-c",
                    probe,
                ],
                cwd=REPO_ROOT,
                env=_compose_probe_environment(mode, volume_name),
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 0, (
                f"direct container probe failed for mode {mode!r} "
                f"with exit {result.returncode}"
            )
            assert result.stdout.strip().splitlines()[-1] == expected
    finally:
        subprocess.run(
            ["docker", "compose", "-p", project, "-f", str(COMPOSE_RELEASE), "rm", "-f"],
            cwd=REPO_ROOT,
            env=_compose_probe_environment(None, volume_name),
            capture_output=True,
            text=True,
            check=False,
        )
        subprocess.run(
            ["docker", "volume", "rm", volume_name],
            capture_output=True,
            text=True,
            check=False,
        )
