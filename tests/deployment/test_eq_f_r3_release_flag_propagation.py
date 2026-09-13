"""EQ-F R5: release-stack safety contract for the Shop/Equipment flags.

Proves, using the repository's real Docker Compose files and real Compose
config resolution (not string-only assertions where a real resolution is
practical), that:

  A. the canonical release compose stack resolves CANONICAL_COIN_SHOP_PURCHASE_
     ENABLED=true and EQUIPMENT_CANONICAL_LOADOUT_ENABLED=false for `app`;
  B. layering the isolated, Owner-gated equipment-enable override resolves
     EQUIPMENT_CANONICAL_LOADOUT_ENABLED=true while Shop stays true, and
     leaves `scheduler` untouched (scheduler is not a consumer);
  C. omitting that override (the Disable/rollback path) resolves back to the
     baseline (Shop=true, Equipment=false);
  D. scripts/release/deploy-release-image.ps1 uses the canonical release
     compose file directly for every governed config/recreate invocation;
  E. scripts/release/set-equipment-enable-state.ps1 fails closed on a
     missing or incorrect Owner gate, for both States, entirely via its
     dry-run/gate-validation path (no SSH, no Docker, no host contact);
  F. the Enable path's tracked override never mentions
     CANONICAL_COIN_SHOP_PURCHASE_ENABLED at all (source fact) -- consistent
     with A/B/C's resolved evidence that Shop is never altered by an
     Equipment state change;
  G. neither product flag is read by scheduler.py, and the Equipment-enable
     override never adds a `scheduler:` block -- no test in this repository
     needs scheduler to be a consumer of either flag;
  H. set-equipment-enable-state.ps1 never emits a full environment dump or
     any secret-shaped value -- its only remote read targets exactly the two
     named flags, and its dry-run JSON contains none of the repository's
     known secret environment variable names.

No test in this file executes -Execute against a real host: the dry-run
plan path returns before any SSH/Docker call, and Assert-OwnerGate is a pure
string comparison that throws before that point is ever reached.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
COMPOSE_RELEASE = REPO_ROOT / "docker-compose.release.yml"
EQUIPMENT_ENABLE_OVERRIDE = REPO_ROOT / "docker-compose.release.equipment-enable.override.yml"
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "release" / "deploy-release-image.ps1"
CONTROL_SCRIPT = REPO_ROOT / "scripts" / "release" / "set-equipment-enable-state.ps1"
EXAMPLE_LAYOUT = "deploy\\release-layout.example.json"

SHOP_KEY = "CANONICAL_COIN_SHOP_PURCHASE_ENABLED"
EQUIPMENT_KEY = "EQUIPMENT_CANONICAL_LOADOUT_ENABLED"

_SECRET_NAME_MARKERS = (
    "SECRET_KEY", "PASSWORD", "API_KEY", "HASH_KEY", "HASH_IV",
    "TURNSTILE_SECRET", "PAYPAL_SECRET", "DATABASE_URL",
)


def _compose_probe_environment() -> dict[str, str]:
    """The known-good local resolution recipe already established by
    test_map_battle_configuration_wiring.py's _compose_probe_environment --
    duplicated here per this test suite's one-file-is-self-contained
    convention, not because the recipe differs."""
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
    assert result.returncode == 0, f"docker compose config failed: {result.stderr}"
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# A/B/C: real Compose config resolution
# ---------------------------------------------------------------------------

def test_a_normal_governed_deploy_resolves_shop_true_equipment_false():
    config = _compose_config([])
    app_env = config["services"]["app"]["environment"]
    assert app_env.get(SHOP_KEY) == "true"
    assert app_env.get(EQUIPMENT_KEY) == "false"


def test_b_equipment_enabled_resolution_flips_only_equipment_for_app():
    config = _compose_config([EQUIPMENT_ENABLE_OVERRIDE])
    app_env = config["services"]["app"]["environment"]
    assert app_env.get(SHOP_KEY) == "true"
    assert app_env.get(EQUIPMENT_KEY) == "true"
    # scheduler is not a consumer and the enable override never targets it --
    # its Equipment value must stay at the baseline "false".
    scheduler_env = config["services"]["scheduler"]["environment"]
    assert scheduler_env.get(EQUIPMENT_KEY) == "false"
    assert scheduler_env.get(SHOP_KEY) == "true"


def test_c_equipment_disable_rollback_resolution_restores_baseline():
    # Disable/rollback is "omit the enable override" -- prove that resolving
    # without it reproduces exactly the Test A baseline, not some other state.
    config = _compose_config([])
    app_env = config["services"]["app"]["environment"]
    assert app_env.get(SHOP_KEY) == "true"
    assert app_env.get(EQUIPMENT_KEY) == "false"


def test_shop_flag_appears_exactly_once_per_service_no_duplicate_authority():
    # The canonical release stack is the single normal-state authority. The
    # values must be explicit for both services, while the Equipment override
    # remains the only layer that changes Equipment for app.
    content = COMPOSE_RELEASE.read_text(encoding="utf-8")
    assert content.count(f"{SHOP_KEY}: \"true\"") == 2
    assert content.count(f"{EQUIPMENT_KEY}: \"false\"") == 2
    assert COMPOSE_RELEASE.is_file()


# ---------------------------------------------------------------------------
# D: deploy-release-image.ps1 mechanically uses the canonical authority
# ---------------------------------------------------------------------------

def test_d_every_governed_compose_invocation_uses_canonical_release_file():
    content = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert "productFlagsPath" not in content
    assert "remoteProductFlagsPath" not in content

    compose_invocation_lines = [
        line for line in content.splitlines()
        if "docker compose" in line
        and ("config --services" in line or "config --images" in line or "--force-recreate" in line)
    ]
    # Four expected call sites: services check, images check, app recreate,
    # scheduler recreate -- every one must use the self-contained canonical
    # release compose file.
    assert len(compose_invocation_lines) == 4, compose_invocation_lines
    for line in compose_invocation_lines:
        assert "remoteHealthcheckOverridePath" in line, line
        assert "-f docker-compose.release.yml" in line, (
            "a governed compose/config or --force-recreate invocation omits "
            "the canonical release-stack authority: " + line
        )


def test_d_recreate_cannot_omit_the_canonical_authority():
    # Both recreate call sites have the canonical release file literally in
    # the command, so no optional sidecar can be forgotten by a caller.
    content = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    recreate_blocks = re.findall(
        r"Invoke-RemoteText\s+\"[^\"]*--force-recreate[^\"]*\"", content
    )
    assert len(recreate_blocks) == 2, recreate_blocks
    for block in recreate_blocks:
        assert "-f docker-compose.release.yml" in block


# ---------------------------------------------------------------------------
# E: Owner-gate fail-closed contract for the control script
# ---------------------------------------------------------------------------

def run_powershell(args: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    quoted = []
    previous_was_switch_or_name = False
    switches = {"-Execute"}
    for arg in args:
        if arg in switches:
            quoted.append(arg)
            previous_was_switch_or_name = False
        elif arg.startswith("-") and not previous_was_switch_or_name:
            quoted.append(arg)
            previous_was_switch_or_name = True
        else:
            quoted.append("'" + arg.replace("'", "''") + "'")
            previous_was_switch_or_name = False
    preamble = (
        "$OutputEncoding = [Console]::OutputEncoding = "
        "New-Object System.Text.UTF8Encoding($false);\n"
    )
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
         preamble + f"& '{CONTROL_SCRIPT.as_posix()}' " + " ".join(quoted)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )


def _last_json(stdout: str) -> dict:
    start = stdout.find("{")
    assert start >= 0, stdout
    return json.loads(stdout[start:])


def test_script_parses_as_valid_powershell():
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "$t=$null;$e=$null;"
         f"[System.Management.Automation.Language.Parser]::ParseFile('{CONTROL_SCRIPT.as_posix()}', [ref]$t, [ref]$e) | Out-Null;"
         "if ($e.Count -gt 0) { $e | ForEach-Object { Write-Host $_.Message } ; exit 1 } else { Write-Host 'OK' }"],
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


@pytest.mark.parametrize("state", ["Enable", "Disable"])
def test_e_dry_run_never_executes_and_reports_correct_gate(state: str):
    result = run_powershell(["-State", state, "-LayoutFile", EXAMPLE_LAYOUT])
    assert result.returncode == 0, result.stdout + result.stderr
    payload = _last_json(result.stdout)
    assert payload["dry_run"] is True
    assert payload["execute_requested"] is False
    assert payload["target_service"] == "go-odyssey-app"
    assert payload["expected_shop_value_after"] == "true"
    if state == "Enable":
        assert payload["required_owner_gate"] == "GO_EQUIPMENT_ENABLE"
        assert payload["expected_equipment_value_after"] == "true"
        assert any("equipment-enable.override.yml" in f for f in payload["compose_files"])
    else:
        assert payload["required_owner_gate"] == "GO_ROLLBACK"
        assert payload["expected_equipment_value_after"] == "false"
        assert not any("equipment-enable.override.yml" in f for f in payload["compose_files"])


def test_e_execute_without_owner_gate_fails_closed():
    result = run_powershell(["-State", "Enable", "-LayoutFile", EXAMPLE_LAYOUT, "-Execute"])
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "docker" not in combined.lower() or "ParameterBindingValidationException" in combined


def test_e_execute_with_wrong_owner_gate_fails_closed_before_any_mutation():
    result = run_powershell([
        "-State", "Enable", "-LayoutFile", EXAMPLE_LAYOUT,
        "-Execute", "-OwnerGate", "GO_ROLLBACK",
    ])
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "Owner gate mismatch" in combined
    assert "GO_EQUIPMENT_ENABLE" in combined


def test_e_disable_with_equipment_enable_gate_fails_closed():
    result = run_powershell([
        "-State", "Disable", "-LayoutFile", EXAMPLE_LAYOUT,
        "-Execute", "-OwnerGate", "GO_EQUIPMENT_ENABLE",
    ])
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "Owner gate mismatch" in combined
    assert "GO_ROLLBACK" in combined


def test_e_execute_rejects_arbitrary_gate_strings():
    result = run_powershell([
        "-State", "Enable", "-LayoutFile", EXAMPLE_LAYOUT,
        "-Execute", "-OwnerGate", "totally-not-a-real-gate",
    ])
    assert result.returncode != 0
    assert "Owner gate mismatch" in (result.stdout + result.stderr)


def test_only_two_owner_gates_exist_in_the_control_script():
    content = CONTROL_SCRIPT.read_text(encoding="utf-8")
    gates = set(re.findall(r"'(GO_[A-Z_]+)'", content))
    assert gates == {"GO_EQUIPMENT_ENABLE", "GO_ROLLBACK"}


# ---------------------------------------------------------------------------
# F: the Enable override never touches Shop (source fact, backed by A/B/C)
# ---------------------------------------------------------------------------

def _strip_yaml_comments(content: str) -> str:
    return re.sub(r"(?m)^\s*#.*(?:\r?\n|$)", "", content)


def test_f_equipment_enable_override_never_mentions_shop_key():
    executable = _strip_yaml_comments(EQUIPMENT_ENABLE_OVERRIDE.read_text(encoding="utf-8"))
    assert SHOP_KEY not in executable


def test_f_equipment_enable_override_touches_no_other_configuration():
    content = EQUIPMENT_ENABLE_OVERRIDE.read_text(encoding="utf-8")
    for forbidden in ("PAYPAL", "NEWEBPAY", "TURNSTILE", "DATABASE_URL", "POSTGRES_"):
        assert forbidden not in content


# ---------------------------------------------------------------------------
# G: scheduler is not, and must not be assumed to be, a consumer
# ---------------------------------------------------------------------------

def test_g_scheduler_source_never_reads_either_product_flag():
    scheduler_source = (REPO_ROOT / "scheduler.py").read_text(encoding="utf-8")
    assert SHOP_KEY not in scheduler_source
    assert EQUIPMENT_KEY not in scheduler_source


def test_g_equipment_enable_override_has_no_scheduler_block():
    executable = _strip_yaml_comments(EQUIPMENT_ENABLE_OVERRIDE.read_text(encoding="utf-8"))
    assert "scheduler" not in executable.lower()


def test_g_control_script_targets_only_the_app_service():
    content = CONTROL_SCRIPT.read_text(encoding="utf-8")
    assert "$targetService = $layout.app_service_name" in content
    assert "scheduler_service_name" not in content


# ---------------------------------------------------------------------------
# H: no secrets, no full environment dump
# ---------------------------------------------------------------------------

def test_h_control_script_never_dumps_a_bare_environment():
    content = CONTROL_SCRIPT.read_text(encoding="utf-8")
    # The only remote read of container environment must be the two named
    # flags via printf -- never a bare `env` or `printenv` with no arguments.
    assert re.search(r"\bprintenv\s*[\"';\n]", content) is None
    assert re.search(r"(?<!\$)\benv\b\s*[\"';\n]", content) is None
    assert "CANONICAL_COIN_SHOP_PURCHASE_ENABLED" in content
    assert "EQUIPMENT_CANONICAL_LOADOUT_ENABLED" in content


def test_h_dry_run_json_never_contains_a_known_secret_name():
    for state in ("Enable", "Disable"):
        result = run_powershell(["-State", state, "-LayoutFile", EXAMPLE_LAYOUT])
        assert result.returncode == 0
        for marker in _SECRET_NAME_MARKERS:
            assert marker not in result.stdout, f"{marker} leaked into {state} dry-run output"


def test_h_equipment_override_contains_no_secret_shaped_values():
    # docker-compose.release.yml is the normal production stack and therefore
    # legitimately names environment-backed secrets.  The isolated override
    # must not introduce any secret material or additional configuration.
    content = EQUIPMENT_ENABLE_OVERRIDE.read_text(encoding="utf-8")
    for marker in _SECRET_NAME_MARKERS:
        assert marker not in content
