"""PRODUCTION-RUNTIME-CANONICALIZATION: contract tests for the credential
data-flow and canonical-compose fixes in deploy-release-image.ps1 and
rollback-release.ps1.

Audit finding (2026-07-14 godokoro.com 502 incident follow-up): both scripts
used to derive POSTGRES_PASSWORD/DATABASE_URL by `docker inspect`-ing the
*existing* scheduler container's live environment, then splice the raw
password into a `KEY=value docker compose ...` command string sent over
SSH. That silently propagated a stale/incorrect credential on every future
deploy/rollback, and the raw password transited as a visible process
argument. rollback-release.ps1 additionally fell back to whatever compose
file the *previous* container happened to use, letting a non-canonical
`docker-compose.prod.yml` drift survive a rollback instead of being
corrected back to the ADR-0001 canonical `docker-compose.release.yml`.

The fix, `Assert-ProtectedHostEnvCredentialAndTcpAuthentication` in
ReleaseTooling.psm1, sends a single Python payload over SSH stdin that does
everything -- reading the protected .env, validating it, resolving the
Postgres container's non-secret network/image provenance, and running a
real TCP `SELECT 1` password-auth check -- entirely on the production host.
It returns only a sanitized `{"status": ..., "reason": ...}` JSON line; the
raw credential never returns to the local PowerShell process, an exception
message, a transcript, or a captured command result.

These tests are intentionally static-analysis style (matching this
project's existing convention in test_release_tooling.py /
test_compose_secret_boundaries.py) rather than full mocked-ssh execution.
"""
import json
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "release" / "deploy-release-image.ps1"
ROLLBACK_SCRIPT = REPO_ROOT / "scripts" / "release" / "rollback-release.ps1"
MODULE = REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1"
LAYOUT_SCHEMA = REPO_ROOT / "deploy" / "release-layout.schema.json"
LAYOUT_EXAMPLE = REPO_ROOT / "deploy" / "release-layout.example.json"
COMPOSE_RELEASE = REPO_ROOT / "docker-compose.release.yml"

CREDENTIAL_ENV_PATH_FIELD = "production_env_path"
GATE_FUNCTION = "Assert-ProtectedHostEnvCredentialAndTcpAuthentication"


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


def _get_gate_function_body():
    module = read_text(MODULE)
    match = re.search(
        rf"function {GATE_FUNCTION}.*?(?=\nfunction |\Z)",
        module,
        re.DOTALL,
    )
    assert match, f"{GATE_FUNCTION} must be defined in ReleaseTooling.psm1"
    return match.group(0)


def _get_remote_python_payload():
    """Extract just the embedded Python heredoc (between the `@'` / `'@`
    single-quoted here-string markers) inside the gate function -- this is
    the part that actually runs on the production host."""
    body = _get_gate_function_body()
    match = re.search(r"@'\n(.*?)\n'@", body, re.DOTALL)
    assert match, "gate function must embed a Python payload via a here-string"
    return match.group(1)


def _get_powershell_wrapper_only():
    """The gate function's PowerShell-side code, excluding the embedded
    Python payload -- this is what runs locally and must never touch the
    raw credential."""
    body = _get_gate_function_body()
    return re.sub(r"@'\n.*?\n'@", "<<PYTHON_PAYLOAD_REMOVED>>", body, flags=re.DOTALL)


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


def test_release_layout_declares_postgres_service_name():
    # app_service_name/scheduler_service_name/nginx_service_name are all
    # documented as literal container names (matching each service's
    # `container_name:` in compose) -- postgres_service_name follows the
    # same convention so the TCP auth gate never has to guess it.
    schema = load_json(LAYOUT_SCHEMA)
    assert "postgres_service_name" in schema["properties"]
    assert "postgres_service_name" in schema.get("required", [])
    example = load_json(LAYOUT_EXAMPLE)
    assert "postgres_service_name" in example


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
    assert "Get-DatabaseUrlComponents -DatabaseUrl $schedulerEnv" not in content
    assert "Get-RemoteContainerEnvMap -ContainerName $layout.scheduler_service_name" not in content, (
        "deploy-release-image.ps1 must not docker-inspect the existing "
        "scheduler container's live environment for DB credentials"
    )
    assert GATE_FUNCTION in content, (
        "deploy-release-image.ps1 must run the protected-host-env credential "
        "and TCP auth gate, not derive credentials from container introspection"
    )


def test_rollback_does_not_derive_credentials_from_scheduler_container_env():
    content = read_text(ROLLBACK_SCRIPT)
    assert "Get-DatabaseUrlComponents -DatabaseUrl $schedulerEnv" not in content
    assert "Get-RemoteContainerEnvMap -ContainerName $layout.scheduler_service_name" not in content, (
        "rollback-release.ps1 must not docker-inspect the existing scheduler "
        "container's live environment for DB credentials"
    )
    assert GATE_FUNCTION in content


def test_release_credential_gate_is_shared_not_duplicated():
    # Both scripts must call the same ReleaseTooling.psm1-exported gate so
    # the credential contract can't drift between deploy and rollback again.
    module = read_text(MODULE)
    assert f"function {GATE_FUNCTION}" in module, (
        f"{GATE_FUNCTION} must live once in ReleaseTooling.psm1 and be "
        "imported by both deploy and rollback, not reimplemented twice"
    )
    assert f"'{GATE_FUNCTION}'" in module, f"{GATE_FUNCTION} must be exported"


# ---------------------------------------------------------------------------
# 3. The host .env is parsed as data, never executed as shell code.
# ---------------------------------------------------------------------------

def test_release_host_env_is_not_sourced_as_shell_code():
    payload = _get_remote_python_payload()
    dangerous_patterns = (
        re.compile(r"\bos\.system\("),
        re.compile(r"subprocess\.[a-zA-Z_]+\(\s*\[?[\"']?(?:bash|sh)\s+-c"),
        re.compile(r"\bsource\s+"),
    )
    for pattern in dangerous_patterns:
        assert not pattern.search(payload), (
            "the protected host .env must be read as KEY=VALUE data via a "
            "plain file open(), never `source`d, dot-executed, or passed to "
            "a shell for interpretation"
        )
    assert 'open(ENV_PATH' in payload, (
        "the protected host env must be opened as a plain file, not read "
        "via a shell command"
    )


# ---------------------------------------------------------------------------
# 4. Fail-closed on missing/empty/duplicate host env assignments.
# ---------------------------------------------------------------------------

def test_release_fails_closed_on_missing_or_empty_host_env_password():
    payload = _get_remote_python_payload()
    assert 'fail("postgres_password_missing")' in payload
    assert 'fail("postgres_password_empty")' in payload
    assert 'fail("env_path_missing_or_not_regular_file")' in payload


def test_release_fails_closed_on_duplicate_host_env_assignment():
    payload = _get_remote_python_payload()
    assert 'fail("duplicate_assignment")' in payload, (
        "the remote helper must fail closed if the protected .env defines "
        "the same credential key more than once, rather than silently "
        "taking the first or last assignment"
    )


def test_release_fails_when_database_url_and_password_disagree():
    payload = _get_remote_python_payload()
    assert 'fail("database_url_disagrees_with_fields")' in payload, (
        "the remote helper must fail closed if DATABASE_URL's embedded "
        "credential fields and the standalone POSTGRES_* fields in the same "
        "protected .env disagree -- it must never silently pick one"
    )


def test_release_pgpass_rejects_newline_or_nul():
    payload = _get_remote_python_payload()
    assert 'fail("credential_contains_unsafe_control_character")' in payload
    for unsafe in ('"\\r"', '"\\n"', '"\\x00"'):
        assert unsafe in payload, (
            f"the remote helper must reject a credential containing {unsafe} "
            "before ever writing it into a pgpass file"
        )


def test_release_pgpass_escapes_colon_and_backslash():
    payload = _get_remote_python_payload()
    assert 'def pgpass_escape(value):' in payload
    assert 'replace("\\\\", "\\\\\\\\")' in payload, (
        "pgpass_escape must escape backslash first (per the .pgpass format)"
    )
    assert 'replace(":", "\\\\:")' in payload, (
        "pgpass_escape must escape literal colons -- unescaped colons are "
        "field separators in the .pgpass format"
    )


# ---------------------------------------------------------------------------
# 5. No fail-open fallback to runtime container environment.
# ---------------------------------------------------------------------------

def test_release_credential_gate_has_no_container_env_fallback():
    body = _get_gate_function_body()
    assert "Get-RemoteContainerEnvMap" not in body, (
        f"{GATE_FUNCTION} must never fall back to reading container "
        "environment if the protected host env read fails or is incomplete"
    )


# ---------------------------------------------------------------------------
# 6. Raw password never returns to the local PowerShell process.
# ---------------------------------------------------------------------------

def test_release_raw_password_never_returns_over_ssh_stdout():
    payload = _get_remote_python_payload()
    # Every stdout write in the remote helper must be one of the two
    # sanitized JSON forms -- never one that could carry the password,
    # user, or database value.
    print_calls = re.findall(r"print\(([^\n]*)\)", payload)
    assert print_calls, "expected at least the ok/fail sanitized print() calls"
    for call in print_calls:
        for forbidden in ("password", "pgpass_line", "conn_str"):
            assert forbidden not in call, (
                f"remote helper print() call `{call}` must not be able to "
                f"carry `{forbidden}` to stdout"
            )


def test_release_local_process_never_receives_raw_db_password():
    # This checks for a PowerShell *variable* holding the credential value
    # (e.g. $password, $Credential.password) in the local-side code --
    # NOT for mentions of the POSTGRES_PASSWORD *key name*, which is a
    # non-secret identifier and legitimately appears in prose/params.
    wrapper_only = _get_powershell_wrapper_only()
    assert not re.search(r"\.password\b|\$password\b|\$Credential\b", wrapper_only), (
        f"{GATE_FUNCTION}'s PowerShell-side code (outside the embedded "
        "Python payload) must never hold a password value in a local "
        "variable -- all credential handling must happen inside the "
        "remote payload, and only a sanitized status/reason may cross "
        "back to this process"
    )
    assert "return [ordered]@{" not in wrapper_only, (
        "the gate function must not return a credential object to its "
        "caller -- it must only throw on failure or return nothing on success"
    )


def test_release_remote_helper_outputs_only_sanitized_metadata():
    payload = _get_remote_python_payload()
    json_dumps_calls = re.findall(r"json\.dumps\((\{[^}]*\})\)", payload)
    assert json_dumps_calls, "expected sanitized json.dumps(...) status payloads"
    for call in json_dumps_calls:
        allowed_keys = {"status", "reason"}
        found_keys = set(re.findall(r'"(\w+)":', call))
        assert found_keys <= allowed_keys, (
            f"remote helper status payload `{call}` must only ever contain "
            f"keys from {allowed_keys}, found {found_keys}"
        )


# ---------------------------------------------------------------------------
# 7. TCP password authentication gate runs before ANY service mutation.
# ---------------------------------------------------------------------------

def test_deploy_runs_tcp_auth_gate_before_any_recreate_or_restart():
    content = read_text(DEPLOY_SCRIPT)
    for target in (
        "--force-recreate $appComposeService",
        "--force-recreate $schedulerComposeService",
        'docker restart $(Quote-PosixShellArgument $layout.nginx_service_name)',
    ):
        assert_tokens_in_order(content, GATE_FUNCTION, target)


def test_rollback_runs_tcp_auth_gate_before_any_recreate_or_restart():
    content = read_text(ROLLBACK_SCRIPT)
    assert_tokens_in_order(content, GATE_FUNCTION, "--force-recreate $appComposeService")


def test_release_dry_run_does_not_execute_remote_tcp_preflight():
    # The dry-run early-return (`if (-not $Execute) { ... return }`) must
    # come BEFORE the credential/TCP gate call in both scripts, so a dry
    # run never touches Production SSH, TCP auth, or any mutation.
    for script, dry_run_marker in (
        (DEPLOY_SCRIPT, "dry_run = $true"),
        (ROLLBACK_SCRIPT, "dry_run = $true"),
    ):
        content = read_text(script)
        assert_tokens_in_order(content, dry_run_marker, GATE_FUNCTION)


def test_tcp_auth_gate_uses_tcp_password_not_socket_trust():
    payload = _get_remote_python_payload()
    assert "host={}" in payload or "host=" in payload, (
        "the auth gate must connect over TCP (explicit host=), not rely on "
        "a local Unix socket trust/peer connection"
    )
    assert "SELECT 1" in payload
    assert "unix_socket" not in payload.lower()
    assert "sslmode=disable" in payload or "sslmode=" in payload


def test_tcp_auth_gate_failure_blocks_every_mutation():
    body = _get_gate_function_body()
    assert "throw" in body, (
        f"{GATE_FUNCTION} must throw (stopping the whole deploy/rollback) "
        "on authentication failure"
    )
    for token in ("ALTER ROLE", "ALTER USER"):
        assert token not in body, (
            "release tooling must fail closed, never auto-repair the DB role "
            "password -- credential rotation is a separate owner-gated SOP"
        )


# ---------------------------------------------------------------------------
# 8. Ephemeral Postgres client: pinned identity, no floating pull, RO mount.
# ---------------------------------------------------------------------------

def test_release_tcp_helper_uses_pull_never():
    payload = _get_remote_python_payload()
    assert '"--pull=never"' in payload, (
        "the throwaway psql client container must never implicitly pull an "
        "image during a production deploy/rollback"
    )


def test_release_tcp_helper_does_not_use_floating_unverified_image():
    payload = _get_remote_python_payload()
    assert "postgres:16-alpine" not in payload, (
        "the helper must not reference a floating tag literal -- it must "
        "use the exact image ID already running as the Postgres container "
        "(non-secret provenance via `docker inspect`), never pull a new one"
    )
    assert 'image_id = item.get("Image")' in payload
    assert 'fail("postgres_image_identity_unavailable")' in payload


def test_release_pgpass_is_mounted_read_only_into_helper():
    payload = _get_remote_python_payload()
    assert re.search(r'"\{\}:/tmp/\.pgpass:ro"', payload), (
        "PGPASSFILE must be bind-mounted read-only (:ro) into the "
        "throwaway psql client container"
    )


def test_release_tcp_network_is_not_guessed():
    payload = _get_remote_python_payload()
    assert "len(networks) != 1" in payload, (
        "the Postgres container's Docker network must resolve to exactly "
        "one candidate; zero or multiple candidates must fail closed "
        "instead of guessing (e.g. taking the first result)"
    )
    assert 'fail("postgres_network_not_uniquely_determined")' in payload
    assert 'fail("postgres_container_not_found")' in payload


# ---------------------------------------------------------------------------
# 9. Raw secret never transits as a visible command-line argument.
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
    module = read_text(MODULE)
    assert not re.search(r"docker exec.{0,80}-e\s+PGPASSWORD=", module), (
        "must not pass PGPASSWORD via a visible `docker exec -e "
        "PGPASSWORD=<value>` argument"
    )
    assert not re.search(r'"-e",\s*"PGPASSWORD=', module), (
        "must not pass PGPASSWORD via a visible `docker run -e "
        "PGPASSWORD=<value>` argument list entry either -- PGPASSFILE (a "
        "0600 file path, not the password itself) is the only permitted "
        "-e value"
    )


# ---------------------------------------------------------------------------
# 10. Rollback must use the canonical compose file only, never inherit drift.
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
    assert "docker-compose.release.yml" in content


def test_rollback_compose_snapshot_is_evidence_only():
    content = read_text(ROLLBACK_SCRIPT)
    # The snapshot field may still be read for the rollback record, but must
    # never control which compose file is actually executed.
    assert "$schedulerBefore.compose_config_files)) { (Join-RemotePath" not in content
    assert re.search(r"\$canonicalComposeFile\s*=\s*Join-RemotePath \$layout\.compose_directory 'docker-compose\.release\.yml'", content), (
        "the executable compose path must be unconditionally the canonical "
        "docker-compose.release.yml, never derived from a snapshot"
    )


# ---------------------------------------------------------------------------
# 11. Nginx refresh regression coverage (existing behavior -- do not remove).
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
# 12. Scheduler flags: wired, disabled by default, correct parser semantics.
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
# 13. E9 foundation sanity check (NOT proof this PR left E9 untouched --
#     that is verified separately via the changed-files allowlist and
#     `git diff --name-only <base>...HEAD`, not by a test in this file).
# ---------------------------------------------------------------------------

def test_e9_foundation_remains_present():
    for path in (
        REPO_ROOT / "js" / "e9",
        REPO_ROOT / "css" / "e9",
    ):
        assert path.is_dir(), f"expected {path} to exist"
