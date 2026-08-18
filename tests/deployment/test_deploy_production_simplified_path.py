"""Executable regressions for the simplified canonical Production deploy path.

scripts/release/deploy-production.ps1 replaced a generic recovery state machine
as the primary deployment entrypoint. These tests hold it to the two rules that
replacement exists to guarantee:

  * it never parses a child script's human-readable stdout, and
  * it has no generic recovery machinery to get lost inside.

Most of the coverage here runs the REAL script. Get-RepoRoot resolves from the
module's own location ($PSScriptRoot/../.., ReleaseTooling.psm1:5-7), so a
sandbox containing scripts/release/ behaves like a repository root. Each test
builds a throwaway git repo holding the real deploy-production.ps1 and the real
ReleaseTooling.psm1, replaces only the CHILD release scripts and the docker/ssh
executables with fakes, and lets the production code drive itself. The fake
children mutate a JSON file standing in for Production; the fake ssh reads it
back. Rollback assertions therefore observe real control flow.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
RELEASE_DIR = ROOT / "scripts" / "release"
DEPLOY_PRODUCTION = RELEASE_DIR / "deploy-production.ps1"
TOOLING_MODULE = RELEASE_DIR / "ReleaseTooling.psm1"

RESULT_PREFIX = "__GO_ODYSSEY_POWERSHELL_RESULT_V1__:"

BASELINE_SHA = "45eef15ec259c6829bc38e57164109ad16950220"
BASELINE_GENERATION = "/opt/go-odyssey-static/releases/baseline-45eef15e"
CANDIDATE_GENERATION = "/opt/go-odyssey-static/releases/candidate"

LAYOUT = {
    "ssh_alias": "sandbox-host",
    "remote_release_staging_directory": "/opt/go-odyssey/releases",
    "compose_project": "go-odyssey",
    "compose_directory": "/opt/go-odyssey",
    "app_service_name": "go-odyssey-app",
    "scheduler_service_name": "go-odyssey-scheduler",
    "nginx_service_name": "go-odyssey-nginx",
    "postgres_service_name": "go-odyssey-postgres",
    "asset_source_path": "/opt/go-odyssey-static/current",
    "asset_container_mount_destination": "/opt/go-odyssey-static/current",
    "static_release_root": "/opt/go-odyssey-static",
    "questions_content_source_path": "/opt/go-odyssey-data",
    "questions_content_mount_destination": "/app/data",
    "shadow_event_log_path": "/app/data/shadow_events.jsonl",
    "production_env_path": "/opt/go-odyssey/.env",
    "health_url": "https://example.invalid/healthz",
    "login_url": "https://example.invalid/login",
    "homepage_url": "https://example.invalid/",
    "release_artifacts_directory": "release-artifacts",
}


def _require_tools() -> None:
    for tool in ("powershell", "git", "python"):
        if shutil.which(tool) is None:
            pytest.skip(f"{tool} is required for the simplified deploy path sandbox")


# ----------------------------------------------------------------------
# Fake docker / ssh
# ----------------------------------------------------------------------

FAKE_DOCKER_PY = r'''
import json, os, pathlib, sys

state_path = pathlib.Path(os.environ["SANDBOX_STATE"])
state = json.loads(state_path.read_text(encoding="utf-8-sig"))
args = sys.argv[1:]

if args[:1] == ["version"]:
    if not state.get("docker_engine_ready", True):
        sys.exit(1)
    print("29.7.2")
    sys.exit(0)

if args[:2] == ["buildx", "inspect"]:
    if "--bootstrap" in args:
        state["buildx_bootstrapped"] = True
        state_path.write_text(json.dumps(state), encoding="utf-8")
        print("Name: sandbox")
        sys.exit(0)
    mode = state.get("buildx", "ready")
    ready = mode == "ready" or (mode == "inactive_then_ready" and state.get("buildx_bootstrapped"))
    print("Name:          sandbox")
    print("Driver:        docker")
    if ready:
        print("Status:           running")
        print("Platforms:        linux/amd64, linux/arm64")
    else:
        print("Status:           inactive")
    sys.exit(0)

if args[:2] == ["image", "inspect"]:
    image = state.get("local_image")
    if not image:
        sys.exit(1)
    print("%s|%s|%s" % (image["revision"], image["platform"], image["id"]))
    sys.exit(0)

sys.exit(0)
'''

FAKE_SSH_PY = r'''
import json, os, pathlib, sys

state_path = pathlib.Path(os.environ["SANDBOX_STATE"])
state = json.loads(state_path.read_text(encoding="utf-8-sig"))
prod = state["production"]
joined = " ".join(sys.argv[1:])

def image_id_for(sha):
    return "sha256:" + sha[:12]

if "docker inspect" in joined and ".Image" in joined:
    if state["layout"]["scheduler_service_name"] in joined:
        print(image_id_for(prod["scheduler_sha"]))
        sys.exit(0)
    if state["layout"]["app_service_name"] in joined:
        print(image_id_for(prod["app_sha"]))
        sys.exit(0)
    sys.exit(1)

if "docker image inspect" in joined and "Config.Labels" in joined:
    for sha in (prod["app_sha"], prod["scheduler_sha"]):
        if image_id_for(sha) in joined:
            print(json.dumps({"org.opencontainers.image.revision": sha}))
            sys.exit(0)
    sys.exit(1)

if "readlink -f" in joined:
    print(prod["static_generation"])
    sys.exit(0)

if "manifest.json" in joined:
    print(json.dumps({"release_git_sha": prod["static_sha"]}))
    sys.exit(0)

sys.exit(0)
'''


def _write_fake_executables(fakebin: pathlib.Path) -> pathlib.Path:
    """Fake docker/ssh shims.

    These live OUTSIDE the sandbox repository on purpose: PRECHECK calls
    Assert-CompleteWorktreeClean, which rejects untracked AND ignored files
    (ReleaseTooling.psm1:267-286), so a fakebin inside the repo would fail the
    clean gate before the flow under test ever started.
    """
    fakebin.mkdir(parents=True, exist_ok=True)
    (fakebin / "docker_fake.py").write_text(FAKE_DOCKER_PY, encoding="utf-8")
    (fakebin / "ssh_fake.py").write_text(FAKE_SSH_PY, encoding="utf-8")
    (fakebin / "docker.cmd").write_text(
        "@echo off" + os.linesep + 'python "%~dp0docker_fake.py" %*' + os.linesep,
        encoding="utf-8",
    )
    (fakebin / "ssh.cmd").write_text(
        "@echo off" + os.linesep + 'python "%~dp0ssh_fake.py" %*' + os.linesep,
        encoding="utf-8",
    )
    return fakebin


# ----------------------------------------------------------------------
# Fake child release scripts
#
# Deliberately SHA-INDEPENDENT: each child reads the expected SHA and derives
# the artifact base name from the sandbox state file at runtime. Baking the SHA
# into their source would be circular -- committing them changes HEAD, so the
# embedded value could never match what PRECHECK requires.
# ----------------------------------------------------------------------

_CHILD_PREAMBLE = """param([Parameter(ValueFromRemainingArguments = $true)]$Rest)
$state = Get-Content -LiteralPath $env:SANDBOX_STATE -Raw | ConvertFrom-Json
function Save-State { $state | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $env:SANDBOX_STATE -Encoding utf8 }
$argText = ($Rest -join ' ')
$sha = $state.expected_sha
$base = 'go-odyssey-app_' + $sha.Substring(0, 8)
$art = $state.artifacts_directory
"""

_CHILD_BODIES = {
    "build-release-image.ps1": """
if ($state.exits.build -ne 0) { Write-Host 'BUILD FAILED (sandbox)'; exit $state.exits.build }
$state.local_image = [ordered]@{ revision = $sha; platform = 'linux/arm64'; id = 'sha256:candidateimage' }
Save-State
Write-Host 'sandbox build complete'
exit 0
""",
    "package-release-image.ps1": """
if ($state.exits.package_app -ne 0) { exit $state.exits.package_app }
New-Item -ItemType Directory -Force -Path $art | Out-Null
Set-Content -LiteralPath (Join-Path $art ($base + '.tar')) -Value 'archive' -Encoding utf8
[ordered]@{ git_sha = $state.package_app_sha } | ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $art ($base + '.release.json')) -Encoding utf8
exit 0
""",
    "package-static-release.ps1": """
if ($state.exits.package_static -ne 0) { exit $state.exits.package_static }
New-Item -ItemType Directory -Force -Path $art | Out-Null
Set-Content -LiteralPath (Join-Path $art ($base + '.static.tar')) -Value 'archive' -Encoding utf8
[ordered]@{ release_git_sha = $state.package_static_sha } | ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $art ($base + '.static.json')) -Encoding utf8
exit 0
""",
    "deploy-static-release.ps1": """
if ($argText -match '-VerifyOnly') { exit $state.exits.static_verify_only }
if ($state.static_promotes) {
    $state.production.static_sha = $sha
    $state.production.static_generation = $state.candidate_generation
    Save-State
}
exit $state.exits.deploy_static
""",
    "deploy-release-image.ps1": """
if ($state.app_promotes_app) { $state.production.app_sha = $sha }
if ($state.app_promotes_scheduler) { $state.production.scheduler_sha = $sha }
Save-State
New-Item -ItemType Directory -Force -Path $art | Out-Null
[ordered]@{ rollback_image_identity = 'sandbox' } | ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $art ($base + '.deployment.json')) -Encoding utf8
exit $state.exits.deploy_app
""",
    "rollback-static-release.ps1": """
$state.rollback_static_called = $true
if ($state.exits.rollback_static -eq 0) {
    $state.production.static_sha = $state.baseline_sha
    $state.production.static_generation = $state.baseline_generation
}
Save-State
exit $state.exits.rollback_static
""",
    "rollback-release.ps1": """
$state.rollback_app_called = $true
if ($state.exits.rollback_app -eq 0) {
    $state.production.app_sha = $state.baseline_sha
    $state.production.scheduler_sha = $state.baseline_sha
}
Save-State
exit $state.exits.rollback_app
""",
    "verify-production-release.ps1": """
exit $state.exits.verify
""",
}


def _fake_children(sandbox: pathlib.Path) -> None:
    release = sandbox / "scripts" / "release"
    for name, body in _CHILD_BODIES.items():
        (release / name).write_text(_CHILD_PREAMBLE + body, encoding="utf-8")


# ----------------------------------------------------------------------
# Sandbox construction
# ----------------------------------------------------------------------

def _git(sandbox: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(sandbox), *args],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout.strip()


def _build_sandbox(tmp_path: pathlib.Path, **overrides) -> dict:
    sandbox = tmp_path / "repo"
    fakebin = tmp_path / "fakebin"        # outside the repo -- see _write_fake_executables
    state_path = tmp_path / "state.json"  # outside the repo, same reason
    artifacts = sandbox / "release-artifacts"

    (sandbox / "scripts" / "release").mkdir(parents=True)
    (sandbox / "deploy").mkdir(parents=True)

    shutil.copy2(TOOLING_MODULE, sandbox / "scripts" / "release" / "ReleaseTooling.psm1")
    shutil.copy2(DEPLOY_PRODUCTION, sandbox / "scripts" / "release" / "deploy-production.ps1")
    (sandbox / "deploy" / "release-layout.test.json").write_text(
        json.dumps(LAYOUT, indent=2), encoding="utf-8"
    )
    _fake_children(sandbox)

    subprocess.run(["git", "init", "-q", str(sandbox)], check=True, capture_output=True)
    _git(sandbox, "config", "user.email", "sandbox@example.invalid")
    _git(sandbox, "config", "user.name", "sandbox")
    _git(sandbox, "add", "--", "deploy", "scripts")
    _git(sandbox, "commit", "-q", "-m", "sandbox base")
    head = _git(sandbox, "rev-parse", "HEAD")
    assert not _git(sandbox, "status", "--porcelain"), "sandbox tree must start clean"

    state = {
        "layout": LAYOUT,
        "expected_sha": head,
        "baseline_sha": BASELINE_SHA,
        "baseline_generation": BASELINE_GENERATION,
        "candidate_generation": CANDIDATE_GENERATION,
        "artifacts_directory": str(artifacts),
        "buildx": "ready",
        "buildx_bootstrapped": False,
        "docker_engine_ready": True,
        "local_image": None,
        "package_app_sha": head,
        "package_static_sha": head,
        "static_promotes": True,
        "app_promotes_app": True,
        "app_promotes_scheduler": True,
        "rollback_static_called": False,
        "rollback_app_called": False,
        "production": {
            "app_sha": BASELINE_SHA,
            "scheduler_sha": BASELINE_SHA,
            "static_sha": BASELINE_SHA,
            "static_generation": BASELINE_GENERATION,
        },
        "exits": {
            "build": 0, "package_app": 0, "package_static": 0,
            "deploy_static": 0, "deploy_app": 0, "verify": 0,
            "static_verify_only": 0, "rollback_static": 0, "rollback_app": 0,
        },
    }
    for key, value in overrides.items():
        if key in ("exits", "production"):
            state[key].update(value)
        else:
            state[key] = value

    state_path.write_text(json.dumps(state), encoding="utf-8")
    _write_fake_executables(fakebin)
    return {"sandbox": sandbox, "head": head, "state_path": state_path, "fakebin": fakebin}


def _run_deploy(ctx: dict, *, execute: bool = True, owner_gate: str = "GO_DEPLOY",
                timeout: int = 180) -> subprocess.CompletedProcess:
    sandbox = ctx["sandbox"]
    script = (sandbox / "scripts" / "release" / "deploy-production.ps1").as_posix()
    args = ["-ExpectedGitSha", ctx["head"], "-LayoutFile", "deploy/release-layout.test.json"]
    if execute:
        args += ["-Execute", "-OwnerGate", owner_gate]
    quoted = " ".join(a if a.startswith("-") else f"'{a}'" for a in args)
    # -Command (not -File) so the UTF-8 preamble applies: PowerShell emits
    # localized error text in the OEM codepage otherwise, and a stray non-UTF-8
    # byte would crash the test harness before it could read the real result.
    preamble = (
        "$OutputEncoding = [Console]::OutputEncoding = "
        "New-Object System.Text.UTF8Encoding($false);\n"
    )
    env = {
        **os.environ,
        "SECRET_KEY": "deploy-production-sandbox-test-only",
        "SANDBOX_STATE": str(ctx["state_path"]),
        "PATH": str(ctx["fakebin"]) + os.pathsep + os.environ.get("PATH", ""),
    }
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
         preamble + f"& '{script}' {quoted}; exit $LASTEXITCODE"],
        cwd=str(sandbox), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, check=False,
    )


def _framed_result(stdout: str) -> dict:
    lines = [ln for ln in stdout.splitlines() if ln.startswith(RESULT_PREFIX)]
    assert len(lines) == 1, f"expected exactly one framed result record, got {len(lines)}"
    return json.loads(base64.b64decode(lines[0][len(RESULT_PREFIX):]).decode("utf-8"))


def _phases(stdout: str) -> list:
    out = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("== [") and stripped.endswith("=="):
            out.append(stripped.split("] ", 1)[1].rstrip(" ="))
    return out


def _prod(ctx: dict) -> dict:
    # The fake children rewrite this file from PowerShell 5.1, whose
    # Set-Content -Encoding utf8 emits a BOM; utf-8-sig reads it either way.
    return json.loads(ctx["state_path"].read_text(encoding="utf-8-sig"))


# ======================================================================
# A. Happy path phase order is short and deterministic
# ======================================================================

def test_a_happy_path_phase_order_is_short_and_deterministic(tmp_path):
    _require_tools()
    ctx = _build_sandbox(tmp_path)
    result = _run_deploy(ctx)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _phases(result.stdout) == [
        "PRECHECK", "BUILD", "PACKAGE", "BASELINE", "STATIC", "APP", "VERIFY", "SUCCESS",
    ]


# ======================================================================
# B. buildx inactive -> one bounded readiness recovery -> build continues
# ======================================================================

def test_b_buildx_inactive_recovers_once_then_build_continues(tmp_path):
    _require_tools()
    ctx = _build_sandbox(tmp_path, buildx="inactive_then_ready")
    result = _run_deploy(ctx)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "attempting one bounded bootstrap" in result.stdout
    assert _prod(ctx)["buildx_bootstrapped"] is True
    assert _framed_result(result.stdout)["result"] == "DEPLOYMENT_VERIFIED"


# ======================================================================
# C. buildx still unusable -> stop pre-mutation
# ======================================================================

def test_c_buildx_never_ready_stops_before_any_mutation(tmp_path):
    _require_tools()
    ctx = _build_sandbox(tmp_path, buildx="never_ready")
    result = _run_deploy(ctx)
    assert result.returncode != 0
    assert "still not reporting platform capability" in (result.stdout + result.stderr)
    prod = _prod(ctx)["production"]
    assert prod["app_sha"] == BASELINE_SHA
    assert prod["scheduler_sha"] == BASELINE_SHA
    assert prod["static_sha"] == BASELINE_SHA
    assert "STATIC" not in _phases(result.stdout)


def test_c2_docker_engine_unreachable_stops_before_any_mutation(tmp_path):
    _require_tools()
    ctx = _build_sandbox(tmp_path, docker_engine_ready=False)
    result = _run_deploy(ctx)
    assert result.returncode != 0
    assert "Docker engine is not reachable" in (result.stdout + result.stderr)
    assert _prod(ctx)["production"]["static_sha"] == BASELINE_SHA


# ======================================================================
# D. build failure -> stop pre-mutation
# ======================================================================

def test_d_build_failure_stops_before_any_mutation(tmp_path):
    _require_tools()
    ctx = _build_sandbox(tmp_path, exits={"build": 4})
    result = _run_deploy(ctx)
    assert result.returncode != 0
    assert "BUILD failed" in (result.stdout + result.stderr)
    prod = _prod(ctx)["production"]
    assert prod["static_sha"] == BASELINE_SHA
    assert prod["app_sha"] == BASELINE_SHA
    assert _phases(result.stdout) == ["PRECHECK", "BUILD"]


# ======================================================================
# E. mixed Production baseline -> stop pre-mutation
# ======================================================================

def test_e_mixed_production_baseline_stops_before_any_mutation(tmp_path):
    _require_tools()
    ctx = _build_sandbox(
        tmp_path,
        production={"static_sha": "1111111111111111111111111111111111111111"},
    )
    result = _run_deploy(ctx)
    assert result.returncode != 0
    assert "MIXED" in (result.stdout + result.stderr)
    assert _phases(result.stdout) == ["PRECHECK", "BUILD", "PACKAGE", "BASELINE"]
    state = _prod(ctx)
    assert state["rollback_static_called"] is False
    assert state["rollback_app_called"] is False


# ======================================================================
# F. static failure before app deployment -> baseline restored
# ======================================================================

def test_f_static_failure_restores_baseline_and_never_reaches_app(tmp_path):
    _require_tools()
    ctx = _build_sandbox(tmp_path, static_promotes=False, exits={"deploy_static": 5})
    result = _run_deploy(ctx)
    assert result.returncode != 0
    payload = _framed_result(result.stdout)
    assert payload["result"] == "FAILED_BASELINE_RESTORED"
    assert payload["app_source_sha"] == BASELINE_SHA
    assert payload["scheduler_source_sha"] == BASELINE_SHA
    assert payload["static_source_sha"] == BASELINE_SHA
    assert "APP" not in _phases(result.stdout)


# ======================================================================
# G. app failure after static success -> app + static rollback -> baseline
# ======================================================================

def test_g_app_failure_after_static_success_rolls_back_both(tmp_path):
    _require_tools()
    ctx = _build_sandbox(tmp_path, exits={"deploy_app": 6})
    result = _run_deploy(ctx)
    assert result.returncode != 0
    payload = _framed_result(result.stdout)
    assert payload["result"] == "FAILED_BASELINE_RESTORED"
    state = _prod(ctx)
    assert state["rollback_app_called"] is True, "app must be rolled back"
    assert state["rollback_static_called"] is True, "static promoted by this run must roll back too"
    assert state["production"]["static_sha"] == BASELINE_SHA
    assert state["production"]["app_sha"] == BASELINE_SHA


def test_g2_unrecoverable_rollback_reports_mixed_or_unverified(tmp_path):
    _require_tools()
    ctx = _build_sandbox(
        tmp_path, exits={"deploy_app": 6, "rollback_app": 1, "rollback_static": 1}
    )
    result = _run_deploy(ctx)
    assert result.returncode != 0
    assert _framed_result(result.stdout)["result"] == "MIXED_OR_UNVERIFIED"


# ======================================================================
# H. final SHA mismatch -> not success
# ======================================================================

def test_h_partial_app_promotion_is_never_reported_as_success(tmp_path):
    _require_tools()
    # The app deploy exits 0 but only the app moved; the scheduler stayed on the
    # baseline image. A zero exit code alone must never be believed.
    ctx = _build_sandbox(tmp_path, app_promotes_scheduler=False)
    result = _run_deploy(ctx)
    assert result.returncode != 0
    payload = _framed_result(result.stdout)
    assert payload["result"] != "DEPLOYMENT_VERIFIED"
    assert payload["result"] in ("FAILED_BASELINE_RESTORED", "MIXED_OR_UNVERIFIED")
    assert "SUCCESS" not in _phases(result.stdout)


def test_h2_static_public_acceptance_failure_is_not_success(tmp_path):
    _require_tools()
    ctx = _build_sandbox(tmp_path, exits={"static_verify_only": 9})
    result = _run_deploy(ctx)
    assert result.returncode != 0
    assert _framed_result(result.stdout)["result"] != "DEPLOYMENT_VERIFIED"


def test_h3_canonical_verification_failure_is_not_success(tmp_path):
    _require_tools()
    ctx = _build_sandbox(tmp_path, exits={"verify": 3})
    result = _run_deploy(ctx)
    assert result.returncode != 0
    assert _framed_result(result.stdout)["result"] != "DEPLOYMENT_VERIFIED"


# ======================================================================
# I. all three exact SHA + verification pass -> success
# ======================================================================

def test_i_all_three_components_at_exact_sha_and_verified_is_success(tmp_path):
    _require_tools()
    ctx = _build_sandbox(tmp_path)
    result = _run_deploy(ctx)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = _framed_result(result.stdout)
    head = ctx["head"]
    assert payload["result"] == "DEPLOYMENT_VERIFIED"
    assert payload["app_source_sha"] == head
    assert payload["scheduler_source_sha"] == head
    assert payload["static_source_sha"] == head
    assert payload["previous_baseline_git_sha"] == BASELINE_SHA
    state = _prod(ctx)
    assert state["rollback_static_called"] is False
    assert state["rollback_app_called"] is False


def test_i2_without_execute_nothing_is_mutated(tmp_path):
    _require_tools()
    ctx = _build_sandbox(tmp_path)
    result = _run_deploy(ctx, execute=False)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = _framed_result(result.stdout)
    assert payload["result"] == "PREPARED_NOT_EXECUTED"
    assert payload["mutated"] is False
    prod = _prod(ctx)["production"]
    assert prod["app_sha"] == BASELINE_SHA
    assert prod["static_sha"] == BASELINE_SHA


def test_i3_execute_requires_the_canonical_owner_gate(tmp_path):
    _require_tools()
    ctx = _build_sandbox(tmp_path)
    result = _run_deploy(ctx, owner_gate="GO_DEPLOY_WITH_BOUNDED_RECOVERY")
    assert result.returncode != 0
    assert "Owner gate mismatch" in (result.stdout + result.stderr)
    assert _prod(ctx)["production"]["static_sha"] == BASELINE_SHA


# ======================================================================
# J. no arbitrary stdout JSON parsing in the primary orchestrator
# ======================================================================

def _strip_powershell_comments(source: str) -> str:
    """Drop block and line comments so source scans only see executable code."""
    out = []
    in_block = False
    for line in source.splitlines():
        stripped = line.strip()
        if in_block:
            if "#>" in stripped:
                in_block = False
            continue
        if stripped.startswith("<#"):
            if "#>" not in stripped:
                in_block = True
            continue
        if stripped.startswith("#"):
            continue
        out.append(line)
    return "\n".join(out)


def test_j_primary_path_never_parses_child_stdout_as_json():
    executable = _strip_powershell_comments(DEPLOY_PRODUCTION.read_text(encoding="utf-8"))
    # The exact defect class this path replaced: find a brace somewhere in a
    # human log and hand the remainder to a JSON parser.
    assert "ConvertFrom-Json" not in executable
    assert "IndexOf('{')" not in executable
    assert ".stdout" not in executable
    # Facts come from artifacts and direct identity reads instead.
    assert "Read-JsonFile" in executable
    assert "Get-ReleaseArtifactBaseName" in executable
    assert "Get-RemoteImageSourceGitSha" in executable
    assert "Get-RemoteStaticGenerationSourceGitSha" in executable


def test_j2_negative_control_detects_the_replaced_defect_shape():
    """The J scan must actually fire on the pattern it claims to forbid."""
    defective = "$data = $result.stdout.Substring($result.stdout.IndexOf('{')) | ConvertFrom-Json\n"
    executable = _strip_powershell_comments(defective)
    assert "ConvertFrom-Json" in executable
    assert "IndexOf('{')" in executable
    assert ".stdout" in executable


def test_j3_comment_stripper_does_not_hide_real_code():
    source = "<#\nConvertFrom-Json in a block comment\n#>\n# ConvertFrom-Json in a line comment\n$x = 1\n"
    stripped = _strip_powershell_comments(source)
    assert "ConvertFrom-Json" not in stripped
    assert "$x = 1" in stripped


# ======================================================================
# K. no generic state machine / root-cause taxonomy in the primary path
# ======================================================================

def test_k_primary_path_has_no_state_machine_or_root_cause_taxonomy():
    executable = _strip_powershell_comments(DEPLOY_PRODUCTION.read_text(encoding="utf-8"))
    for forbidden in (
        "CoordinatedReleaseStateMachine",
        "Invoke-CoordinatedReleaseStateMachine",
        "Get-OperationalFailureClassification",
        "New-RootCauseKey",
        "Update-RecoveryBudget",
        "New-RecoveryBudgetTracker",
        "root_cause_class",
        "recovery_budget",
    ):
        assert forbidden not in executable, f"primary deploy path must not depend on {forbidden}"


def test_k2_each_canonical_child_is_referenced_from_one_site():
    """No replay loop: every canonical child has exactly one invocation site."""
    executable = _strip_powershell_comments(DEPLOY_PRODUCTION.read_text(encoding="utf-8"))
    for script_name in (
        "build-release-image.ps1",
        "package-release-image.ps1",
        "package-static-release.ps1",
        "deploy-static-release.ps1",
        "deploy-release-image.ps1",
        "rollback-static-release.ps1",
        "rollback-release.ps1",
        "verify-production-release.ps1",
    ):
        assert executable.count("'" + script_name + "'") == 1, script_name


def test_k3_every_child_invocation_is_bounded():
    executable = _strip_powershell_comments(DEPLOY_PRODUCTION.read_text(encoding="utf-8"))
    invocations = executable.count("Invoke-ReleaseStep -ScriptPath")
    bounds = executable.count("-TimeoutSeconds $")
    assert invocations >= 8, "expected one bounded call per canonical child step"
    assert bounds >= invocations, "every child invocation must supply an explicit bound"
