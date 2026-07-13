"""PRODUCTION-RUNTIME-CANONICALIZATION: contract tests for the credential
data-flow and canonical-compose fixes in deploy-release-image.ps1 and
rollback-release.ps1.

Audit finding (2026-07-14 godokoro.com 502 incident follow-up): both scripts
currently derive POSTGRES_PASSWORD/DATABASE_URL by `docker inspect`-ing the
*existing* scheduler container's live environment (Get-RemoteContainerEnvMap
-> Get-DatabaseUrlComponents), then splice the raw password into a
`KEY=value docker compose ...` command string sent over SSH. That means (a)
a stale/incorrect credential on the running container is silently
propagated forward by every future deploy/rollback instead of ever being
corrected, and (b) the raw password transits as a visible process argument.
rollback-release.ps1 additionally falls back to whatever compose file the
*previous* container happened to use, so a non-canonical `docker-compose.
prod.yml` drift survives a rollback instead of being corrected back to the
ADR-0001 canonical `docker-compose.release.yml`.

These tests are intentionally static-analysis style (matching this
project's existing convention in test_release_tooling.py /
test_compose_secret_boundaries.py) rather than full mocked-ssh execution.
They are written RED against the current scripts; Commit 2 makes them pass.
"""
import json
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "release" / "deploy-release-image.ps1"
ROLLBACK_SCRIPT = REPO_ROOT / "scripts" / "release" / "rollback-release.ps1"
LAYOUT_SCHEMA = REPO_ROOT / "deploy" / "release-layout.schema.json"
LAYOUT_EXAMPLE = REPO_ROOT / "deploy" / "release-layout.example.json"
COMPOSE_RELEASE = REPO_ROOT / "docker-compose.release.yml"

CREDENTIAL_ENV_PATH_FIELD = "production_env_path"


def read_text(path):
    return path.read_text(encoding="utf-8")


def load_json(path):
    return json.loads(read_text(path))


def assert_tokens_in_order(content, *tokens):
    cursor = 0
    for token in tokens:
        index = content.find(token, cursor)
        assert index != -1, f"missing ordered token: {token}"
        cursor = index + len(token)


# ---------------------------------------------------------------------------
# 1. Canonical host env path is a layout contract field, not hardcoded.
# ---------------------------------------------------------------------------

def test_release_layout_schema_declares_protected_credential_env_path():
    schema = load_json(LAYOUT_SCHEMA)
    assert CREDENTIAL_ENV_PATH_FIELD in schema["properties"], (
        "release-layout.schema.json must declare a production_env_path field "
        "so the protected host .env location is an explicit, reviewed contract "
        "value -- not hardcoded inline in multiple scripts"
    )
    assert CREDENTIAL_ENV_PATH_FIELD in schema.get("required", []), (
        "production_env_path must be required, not optional -- deploy/rollback "
        "must not silently operate without a declared credential source"
    )


def test_release_layout_example_documents_credential_env_path():
    example = load_json(LAYOUT_EXAMPLE)
    assert CREDENTIAL_ENV_PATH_FIELD in example


def test_release_scripts_read_env_path_from_layout_not_hardcoded():
    for script in (DEPLOY_SCRIPT, ROLLBACK_SCRIPT):
        content = read_text(script)
        assert "$layout.production_env_path" in content, (
            f"{script.name} must source the protected env path from "
            "$layout.production_env_path, not a literal '/opt/go-odyssey/.env'"
        )
        assert "/opt/go-odyssey/.env" not in content, (
            f"{script.name} must not hardcode the production .env path -- "
            "route it through the layout contract"
        )


# ---------------------------------------------------------------------------
# 2. Credentials must not be derived from the running app/scheduler container.
# ---------------------------------------------------------------------------

def test_deploy_does_not_derive_credentials_from_scheduler_container_env():
    content = read_text(DEPLOY_SCRIPT)
    assert "Get-DatabaseUrlComponents -DatabaseUrl $schedulerEnv" not in content, (
        "deploy-release-image.ps1 must not parse POSTGRES_PASSWORD out of the "
        "existing scheduler container's live environment -- that silently "
        "propagates a stale/incorrect credential forward on every deploy"
    )
    assert "Get-ProtectedHostEnvCredential" in content, (
        "deploy-release-image.ps1 must read DB credentials via a dedicated "
        "protected-host-env credential reader, not container introspection"
    )


def test_rollback_does_not_derive_credentials_from_scheduler_container_env():
    content = read_text(ROLLBACK_SCRIPT)
    assert "Get-DatabaseUrlComponents -DatabaseUrl $schedulerEnv" not in content, (
        "rollback-release.ps1 must not parse POSTGRES_PASSWORD out of the "
        "existing scheduler container's live environment"
    )
    assert "Get-ProtectedHostEnvCredential" in content, (
        "rollback-release.ps1 must read DB credentials via a dedicated "
        "protected-host-env credential reader, not container introspection"
    )


def test_release_credential_reader_is_shared_not_duplicated():
    # Both scripts must call the same ReleaseTooling.psm1-exported helper so
    # the credential contract can't drift between deploy and rollback again.
    module = read_text(REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1")
    assert "function Get-ProtectedHostEnvCredential" in module, (
        "Get-ProtectedHostEnvCredential must live once in ReleaseTooling.psm1 "
        "and be imported by both deploy and rollback, not reimplemented twice"
    )


# ---------------------------------------------------------------------------
# 3. The host .env is parsed as data, never executed as shell code.
# ---------------------------------------------------------------------------

def test_release_host_env_is_not_sourced_as_shell_code():
    module = read_text(REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1")
    dangerous_patterns = (
        re.compile(r"bash -c\s+.{0,40}\.\s+" + re.escape("$")),
        re.compile(r"\bsource\s+\$\w*[Ee]nv[Pp]ath"),
        re.compile(r"^\s*\.\s+\$\w*[Ee]nv[Pp]ath", re.MULTILINE),
    )
    for pattern in dangerous_patterns:
        assert not pattern.search(module), (
            "the protected host .env must be parsed as KEY=VALUE data on the "
            "PowerShell/Python side, never `source`d or dot-executed as shell "
            "code on the remote host"
        )
    assert "function Get-ProtectedHostEnvCredential" in module


# ---------------------------------------------------------------------------
# 4. Fail-closed on missing/empty/duplicate host env assignments.
# ---------------------------------------------------------------------------

def test_release_fails_closed_on_missing_or_empty_host_env_password():
    module = read_text(REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1")
    for token in (
        "must not be missing",
        "must not be empty",
    ):
        assert token in module, (
            f"Get-ProtectedHostEnvCredential must throw with a message "
            f"containing '{token}' when POSTGRES_PASSWORD/DATABASE_URL is "
            f"absent or blank in the protected host env"
        )


def _get_protected_host_env_credential_body():
    module = read_text(REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1")
    match = re.search(
        r"function Get-ProtectedHostEnvCredential.*?(?=\nfunction |\Z)",
        module,
        re.DOTALL,
    )
    assert match, "Get-ProtectedHostEnvCredential must be defined in ReleaseTooling.psm1"
    return match.group(0)


def test_release_fails_closed_on_duplicate_host_env_assignment():
    body = _get_protected_host_env_credential_body()
    assert "duplicate" in body.lower(), (
        "Get-ProtectedHostEnvCredential must fail closed if the protected "
        ".env defines the same credential key more than once, rather than "
        "silently taking the first or last assignment"
    )


def test_release_fails_when_database_url_and_password_disagree():
    body = _get_protected_host_env_credential_body()
    assert "disagree" in body.lower() or "does not match" in body.lower(), (
        "Get-ProtectedHostEnvCredential must fail closed if DATABASE_URL's "
        "embedded password and a standalone POSTGRES_PASSWORD in the same "
        "protected .env disagree -- it must never silently pick one"
    )


# ---------------------------------------------------------------------------
# 5. No fail-open fallback to runtime container environment.
# ---------------------------------------------------------------------------

def test_release_credential_reader_has_no_container_fallback():
    module = read_text(REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1")
    match = re.search(
        r"function Get-ProtectedHostEnvCredential.*?(?=\nfunction |\Z)",
        module,
        re.DOTALL,
    )
    assert match, "Get-ProtectedHostEnvCredential must be defined in ReleaseTooling.psm1"
    body = match.group(0)
    assert "Get-RemoteContainerEnvMap" not in body, (
        "Get-ProtectedHostEnvCredential must never fall back to reading "
        "container environment if the host env read fails or is incomplete"
    )


# ---------------------------------------------------------------------------
# 6. TCP password authentication gate runs before ANY service mutation.
# ---------------------------------------------------------------------------

def test_deploy_runs_tcp_auth_gate_before_any_recreate_or_restart():
    content = read_text(DEPLOY_SCRIPT)
    assert "Assert-ProtectedCredentialTcpAuthentication" in content, (
        "deploy-release-image.ps1 must run an explicit TCP password-auth "
        "SELECT 1 gate against the protected host env credential before any "
        "docker compose up / restart"
    )
    assert_tokens_in_order(
        content,
        "Assert-ProtectedCredentialTcpAuthentication",
        "--force-recreate $appComposeService",
    )
    assert_tokens_in_order(
        content,
        "Assert-ProtectedCredentialTcpAuthentication",
        "--force-recreate $schedulerComposeService",
    )
    assert_tokens_in_order(
        content,
        "Assert-ProtectedCredentialTcpAuthentication",
        'docker restart $(Quote-PosixShellArgument $layout.nginx_service_name)',
    )


def test_rollback_runs_tcp_auth_gate_before_any_recreate_or_restart():
    content = read_text(ROLLBACK_SCRIPT)
    assert "Assert-ProtectedCredentialTcpAuthentication" in content, (
        "rollback-release.ps1 must run the same TCP password-auth gate "
        "before any docker compose up / restart"
    )
    assert_tokens_in_order(
        content,
        "Assert-ProtectedCredentialTcpAuthentication",
        "--force-recreate $appComposeService",
    )


def test_tcp_auth_gate_uses_tcp_password_not_socket_trust():
    module = read_text(REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1")
    match = re.search(
        r"function Assert-ProtectedCredentialTcpAuthentication.*?(?=\nfunction |\Z)",
        module,
        re.DOTALL,
    )
    assert match, "Assert-ProtectedCredentialTcpAuthentication must be defined in ReleaseTooling.psm1"
    body = match.group(0)
    assert "host=" in body or "-h " in body or "PGHOST" in body, (
        "the auth gate must connect over TCP (explicit host), not rely on "
        "a local Unix socket trust/peer connection"
    )
    assert "SELECT 1" in body
    assert "unix_socket" not in body.lower()


def test_tcp_auth_gate_failure_blocks_every_mutation():
    module = read_text(REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1")
    match = re.search(
        r"function Assert-ProtectedCredentialTcpAuthentication.*?(?=\nfunction |\Z)",
        module,
        re.DOTALL,
    )
    assert match
    body = match.group(0)
    assert "throw" in body, (
        "Assert-ProtectedCredentialTcpAuthentication must throw (stopping "
        "the whole deploy/rollback) on authentication failure -- it must "
        "not attempt ALTER ROLE, .env edits, or any other auto-repair"
    )
    for token in ("ALTER ROLE", "ALTER USER"):
        assert token not in body, (
            "release tooling must fail closed, never auto-repair the DB role "
            "password -- credential rotation is a separate owner-gated SOP"
        )


# ---------------------------------------------------------------------------
# 7. Raw secret never transits as a visible command-line argument.
# ---------------------------------------------------------------------------

def test_release_secret_not_spliced_into_compose_command_prefix():
    for script in (DEPLOY_SCRIPT, ROLLBACK_SCRIPT):
        content = read_text(script)
        assert not re.search(r'"POSTGRES_PASSWORD=\{0\}"', content), (
            f"{script.name} must not build a POSTGRES_PASSWORD=<value> "
            f"literal into a command-line string"
        )
        assert "--env-file" in content, (
            f"{script.name} must pass the protected host .env to docker "
            f"compose via --env-file so secrets are read by compose itself, "
            f"not interpolated into command text"
        )


def test_release_secret_not_passed_via_docker_exec_environment_argument():
    module = read_text(REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1")
    assert not re.search(r"docker exec.{0,80}-e\s+PGPASSWORD=", module), (
        "the TCP auth gate must not pass PGPASSWORD via a visible `docker "
        "exec -e PGPASSWORD=<value>` argument -- use stdin/piped delivery "
        "instead so the raw password never appears in process argv"
    )


# ---------------------------------------------------------------------------
# 8. Rollback must use the canonical compose file only, never inherit drift.
# ---------------------------------------------------------------------------

def test_rollback_does_not_inherit_non_canonical_compose_file():
    content = read_text(ROLLBACK_SCRIPT)
    assert "$useReleaseCompose" not in content, (
        "rollback-release.ps1 must not conditionally decide whether to use "
        "docker-compose.release.yml based on what the previous container "
        "happened to use -- that lets a non-canonical docker-compose.prod.yml "
        "drift survive a rollback instead of being corrected"
    )
    assert "compose_config_files" in content, (
        "the previous container's compose_config_files should still be "
        "captured as rollback-record provenance evidence"
    )
    # It must be evidence-only: never fed into the executable -f path.
    assert not re.search(
        r"-f\s+\$\(Quote-PosixShellArgument\s+\$rollbackComposeFile\)",
        content,
    ), (
        "rollback must not execute `docker compose -f` against a path "
        "derived from the previous container's snapshot"
    )
    assert "docker-compose.release.yml" in content


def test_rollback_compose_snapshot_is_evidence_only():
    content = read_text(ROLLBACK_SCRIPT)
    # The snapshot field may still be read for the rollback record, but must
    # not flow into $rollbackComposeFile / any compose -f argument anymore.
    assert "$rollbackComposeFile = if ([string]::IsNullOrWhiteSpace($schedulerBefore.compose_config_files))" not in content


# ---------------------------------------------------------------------------
# 9. Nginx refresh regression coverage (existing behavior -- do not remove).
# ---------------------------------------------------------------------------

def test_deploy_still_restarts_nginx_after_app_recreate():
    content = read_text(DEPLOY_SCRIPT)
    assert_tokens_in_order(
        content,
        "--force-recreate $appComposeService",
        'docker restart $(Quote-PosixShellArgument $layout.nginx_service_name)',
    )


def test_rollback_still_restarts_nginx_after_app_recreate():
    content = read_text(ROLLBACK_SCRIPT)
    assert_tokens_in_order(
        content,
        "--force-recreate $appComposeService",
        'docker restart $(Quote-PosixShellArgument $layout.nginx_service_name)',
    )


# ---------------------------------------------------------------------------
# 10. Scheduler flags: wired, disabled by default, correct parser semantics.
# ---------------------------------------------------------------------------

def test_compose_wires_community_leaderboard_flag_disabled_by_default():
    content = read_text(COMPOSE_RELEASE)
    assert "COMMUNITY_LEADERBOARD_REWARDS_ENABLED" in content, (
        "docker-compose.release.yml must wire COMMUNITY_LEADERBOARD_REWARDS_ENABLED "
        "into both app and scheduler services"
    )
    # app.py's _env_flag_exact_true only ever treats the literal string
    # "true" as enabled -- any other default (including "0") is already
    # safe, but the default must not itself be "true".
    for match in re.finditer(
        r"COMMUNITY_LEADERBOARD_REWARDS_ENABLED:\s*\$\{COMMUNITY_LEADERBOARD_REWARDS_ENABLED:-([^}]*)\}",
        content,
    ):
        assert match.group(1).strip().lower() != "true", (
            "COMMUNITY_LEADERBOARD_REWARDS_ENABLED must not default to true"
        )
    assert content.count("COMMUNITY_LEADERBOARD_REWARDS_ENABLED") >= 2, (
        "the flag must be wired into both the app and scheduler service "
        "environment blocks"
    )


def test_compose_premium_weekly_flag_default_unchanged():
    # PREMIUM_WEEKLY_SCHEDULER_ENABLED is read with the looser
    # _env_flag_enabled() truthy parser (not exact-true) -- its existing
    # ":-0" default is already a legitimate disabled value for that parser.
    # This test pins the current, already-correct default so a future edit
    # doesn't change Premium's semantics while touching Community's.
    content = read_text(COMPOSE_RELEASE)
    assert "PREMIUM_WEEKLY_SCHEDULER_ENABLED: ${PREMIUM_WEEKLY_SCHEDULER_ENABLED:-0}" in content


# ---------------------------------------------------------------------------
# 11. E9 foundation sanity check (NOT proof this PR left E9 untouched --
#     that is verified separately via the changed-files allowlist and
#     `git diff --name-only <base>...HEAD`, not by a test in this file).
# ---------------------------------------------------------------------------

def test_e9_foundation_remains_present():
    for path in (
        REPO_ROOT / "js" / "e9",
        REPO_ROOT / "css" / "e9",
    ):
        assert path.is_dir(), f"expected {path} to exist"
