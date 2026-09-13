"""Repository-wide EQ-F R5 product-flag closure.

This is intentionally a source-and-Compose test rather than a test of the
current number of scripts.  It discovers every release source containing an
app force-recreate and requires each discovered source to be backed by the
canonical release compose stack.  The small reviewed registry below gives the
operation-level evidence needed for the indirect Community Rewards module;
the discovery assertion fails if a future source is added without review.

No test in this module contacts SSH, Production, Docker Engine, or a live
database.  Compose checks use ``docker compose config`` only.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
RELEASE_ROOT = REPO_ROOT / "scripts" / "release"
COMPOSE_RELEASE = REPO_ROOT / "docker-compose.release.yml"
EQUIPMENT_OVERRIDE = REPO_ROOT / "docker-compose.release.equipment-enable.override.yml"

SHOP_KEY = "CANONICAL_COIN_SHOP_PURCHASE_ENABLED"
EQUIPMENT_KEY = "EQUIPMENT_CANONICAL_LOADOUT_ENABLED"

COMMUNITY_MODULE = RELEASE_ROOT / "CommunityRewardsExecutionControl.psm1"
DEPLOY_SCRIPT = RELEASE_ROOT / "deploy-release-image.ps1"
ROLLBACK_SCRIPT = RELEASE_ROOT / "rollback-release.ps1"
EQUIPMENT_SCRIPT = RELEASE_ROOT / "set-equipment-enable-state.ps1"
E9_SCRIPT = RELEASE_ROOT / "set-e9-rollout.ps1"
SHADOW_SCRIPT = RELEASE_ROOT / "set-shadow-judging.ps1"
RESUME_SCRIPT = RELEASE_ROOT / "resume-community-leaderboard-rewards.ps1"

# This registry is operation-level evidence, not the discovery mechanism.  A
# new direct recreate source cannot hide behind this list: the dynamic census
# below requires the discovered source set to match it, and source-specific
# checks then require canonical authority on every recreate command.
GOVERNED_APP_RECREATE_REGISTRY = {
    "NORMAL_DEPLOY": (DEPLOY_SCRIPT, "--force-recreate $appComposeService"),
    "RELEASE_ROLLBACK": (ROLLBACK_SCRIPT, "$rollbackAppCommand"),
    "COMMUNITY_FREEZE": (COMMUNITY_MODULE, "COMMUNITY_LEADERBOARD_REWARDS_ENABLED=false"),
    "COMMUNITY_RESUME": (COMMUNITY_MODULE, '__COMPOSE_PREFIX__ docker compose'),
    "E9_ROLLOUT": (E9_SCRIPT, "--force-recreate app scheduler"),
    "SHADOW_RECREATE": (SHADOW_SCRIPT, "--force-recreate app scheduler"),
    "EQUIPMENT_ENABLE": (EQUIPMENT_SCRIPT, "if ($State -eq 'Enable')"),
    "EQUIPMENT_DISABLE": (EQUIPMENT_SCRIPT, "if ($State -eq 'Enable')"),
}

EXPECTED_DIRECT_RECREATE_SOURCES = {
    DEPLOY_SCRIPT,
    ROLLBACK_SCRIPT,
    COMMUNITY_MODULE,
    EQUIPMENT_SCRIPT,
    E9_SCRIPT,
    SHADOW_SCRIPT,
}


def _compose_probe_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "GO_ODYSSEY_IMAGE": os.environ.get(
                "GO_ODYSSEY_CONFIG_TEST_IMAGE", "go-odyssey-app:fc82f210"
            ),
            "POSTGRES_PASSWORD": "synthetic-config-test-password",
            "ASSET_SOURCE_PATH": str(REPO_ROOT),
            "ASSET_CONTAINER_MOUNT_DESTINATION": "/opt/go-odyssey-static/current",
            "QUESTIONS_CONTENT_VOLUME_NAME": "unused-config-test-volume",
            "QUESTIONS_CONTENT_MOUNT_DESTINATION": "/app/data",
            "KATAGO_CACHE_SOURCE_PATH": str(REPO_ROOT / "Dockerfile"),
            "SECRET_KEY": "synthetic-config-test-secret",
        }
    )
    return environment


def _compose_config(extra_files: list[pathlib.Path]) -> dict:
    args = ["docker", "compose", "-f", str(COMPOSE_RELEASE)]
    for extra in extra_files:
        args += ["-f", str(extra)]
    args += ["config", "--format", "json"]
    result = subprocess.run(
        args,
        cwd=REPO_ROOT,
        env=_compose_probe_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _source_files_with_app_recreate() -> set[pathlib.Path]:
    discovered: set[pathlib.Path] = set()
    for path in RELEASE_ROOT.rglob("*"):
        if path.suffix.lower() not in {".ps1", ".psm1"}:
            continue
        content = path.read_text(encoding="utf-8")
        if "--force-recreate" not in content:
            continue
        # All current release templates identify the app either by a literal
        # service name or by an app-specific variable.  This intentionally
        # errs toward discovery: a new ambiguous force-recreate source is a
        # review failure, not an silently ignored path.
        if re.search(
            r"\b(?:app|APP_SERVICE|AppService|appComposeService|targetService|rollbackAppCommand)\b",
            content,
        ):
            discovered.add(path)
    return discovered


def test_all_governed_app_recreate_sources_are_discovered_and_registered():
    discovered = _source_files_with_app_recreate()
    assert discovered == EXPECTED_DIRECT_RECREATE_SOURCES, (
        "the governed app-recreate surface changed; review every new source "
        f"before updating the registry: discovered={sorted(str(p) for p in discovered)}"
    )
    assert len(GOVERNED_APP_RECREATE_REGISTRY) == 8
    for path, anchor in GOVERNED_APP_RECREATE_REGISTRY.values():
        content = path.read_text(encoding="utf-8")
        assert anchor in content, f"missing registry anchor in {path}: {anchor}"


def test_every_direct_recreate_source_uses_canonical_release_authority():
    for path in EXPECTED_DIRECT_RECREATE_SOURCES - {COMMUNITY_MODULE}:
        content = path.read_text(encoding="utf-8")
        assert "docker-compose.release.product-flags.yml" not in content
        assert "docker-compose.release.yml" in content

    module = COMMUNITY_MODULE.read_text(encoding="utf-8")
    assert ' -f \"$COMPOSE_FILE\"' in module or '-f \"$COMPOSE_FILE\"' in module
    assert "docker-compose.release.product-flags.yml" not in module

    # The module receives its compose file from both governed callers.  The
    # binding is checked at the call site, not inferred from the template.
    deploy = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert "$remoteComposePath = Join-RemotePath $layout.compose_directory 'docker-compose.release.yml'" in deploy
    assert "-ComposeFile $remoteComposePath" in deploy

    resume = RESUME_SCRIPT.read_text(encoding="utf-8")
    assert '-ComposeFile "$($layout.compose_directory.TrimEnd(\'/\'))/docker-compose.release.yml"' in resume

    # The direct scripts must put the canonical file on the same command path
    # that can reach --force-recreate, not only mention it in documentation.
    for path in (DEPLOY_SCRIPT, E9_SCRIPT, SHADOW_SCRIPT):
        content = path.read_text(encoding="utf-8")
        recreate_lines = [
            line for line in content.splitlines()
            if "force-recreate" in line
            and ("docker compose" in line or path is SHADOW_SCRIPT)
        ]
        assert recreate_lines, path
        if path is DEPLOY_SCRIPT:
            assert all("-f docker-compose.release.yml" in line for line in recreate_lines)
        elif path is E9_SCRIPT:
            assert "$releaseFile" in recreate_lines[0]
            assert "docker-compose.release.yml" in content.split("$releaseFile =", 1)[1].splitlines()[0]
        else:
            assert 'docker compose -p "$COMPOSE_PROJECT" --env-file "$ENV_PATH" -f "$RELEASE_FILE"' in content
            assert "docker-compose.release.yml" in content.split("'__RELEASE_FILE__'", 1)[1]

    rollback = ROLLBACK_SCRIPT.read_text(encoding="utf-8")
    assert "$localCanonicalComposeFile = Resolve-RepoPath 'docker-compose.release.yml'" in rollback
    assert "$canonicalComposeFile = Join-RemotePath $layout.compose_directory 'docker-compose.release.yml'" in rollback
    assert "-LocalPath $localCanonicalComposeFile" in rollback
    assert "-RemotePath $canonicalComposeFile" in rollback
    assert "$canonicalComposeFile" in rollback.split("$canonicalComposeFile =", 1)[1]

    equipment = EQUIPMENT_SCRIPT.read_text(encoding="utf-8")
    assert "'-f', 'docker-compose.release.yml'" in equipment
    assert "-LocalPath $composeFilePath -RemotePath $remoteComposePath" in equipment
    assert "remoteProductFlagsPath" not in equipment


def test_canonical_release_stack_is_explicit_and_equipment_override_isolated():
    config = _compose_config([])
    app = config["services"]["app"]["environment"]
    scheduler = config["services"]["scheduler"]["environment"]
    assert app[SHOP_KEY] == "true"
    assert app[EQUIPMENT_KEY] == "false"
    assert scheduler[SHOP_KEY] == "true"
    assert scheduler[EQUIPMENT_KEY] == "false"

    enabled = _compose_config([EQUIPMENT_OVERRIDE])
    enabled_app = enabled["services"]["app"]["environment"]
    enabled_scheduler = enabled["services"]["scheduler"]["environment"]
    assert enabled_app[SHOP_KEY] == "true"
    assert enabled_app[EQUIPMENT_KEY] == "true"
    assert enabled_scheduler[SHOP_KEY] == "true"
    assert enabled_scheduler[EQUIPMENT_KEY] == "false"

    # Disable and release rollback both omit the Equipment-only override and
    # therefore resolve to the same safe baseline.
    rollback = _compose_config([])["services"]["app"]["environment"]
    assert rollback[SHOP_KEY] == "true"
    assert rollback[EQUIPMENT_KEY] == "false"

    override = EQUIPMENT_OVERRIDE.read_text(encoding="utf-8")
    executable = re.sub(r"(?m)^\s*#.*(?:\r?\n|$)", "", override)
    assert SHOP_KEY not in executable
    assert "scheduler:" not in executable.lower()


def test_no_governed_path_depends_on_product_flags_sidecar_or_host_override():
    assert not (REPO_ROOT / "docker-compose.release.product-flags.yml").exists()
    for path in EXPECTED_DIRECT_RECREATE_SOURCES | {RESUME_SCRIPT}:
        content = path.read_text(encoding="utf-8")
        assert "docker-compose.release.product-flags.yml" not in content
    compose = COMPOSE_RELEASE.read_text(encoding="utf-8")
    assert SHOP_KEY in compose
    assert EQUIPMENT_KEY in compose


def test_remote_canonical_compose_upload_precedes_equipment_recreate():
    deploy = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_upload = deploy.index("-LocalPath $composeFilePath -RemotePath $remoteComposePath")
    deploy_recreate = deploy.index("--force-recreate $appComposeService")
    assert deploy_upload < deploy_recreate
    assert "$remoteComposePath = Join-RemotePath $layout.compose_directory 'docker-compose.release.yml'" in deploy

    control = EQUIPMENT_SCRIPT.read_text(encoding="utf-8")
    local = control.index("$composeFilePath = Resolve-RepoPath 'docker-compose.release.yml'")
    remote = control.index("$remoteComposePath = Join-RemotePath $layout.compose_directory 'docker-compose.release.yml'")
    upload = control.index("-LocalPath $composeFilePath -RemotePath $remoteComposePath")
    # Compose argument construction precedes the Execute-only upload, but the
    # upload still precedes the remote command that consumes it.
    assert local < remote < upload
    assert "'-f', 'docker-compose.release.yml'" in control
    rollback = ROLLBACK_SCRIPT.read_text(encoding="utf-8")
    rollback_upload = rollback.index("-LocalPath $localCanonicalComposeFile -RemotePath $canonicalComposeFile") if "-LocalPath $localCanonicalComposeFile -RemotePath $canonicalComposeFile" in rollback else rollback.index("-LocalPath $localCanonicalComposeFile")
    rollback_recreate = rollback.index("$rollbackAppCommand =")
    assert rollback_upload < rollback_recreate
    assert "remoteProductFlagsPath" not in deploy + control
