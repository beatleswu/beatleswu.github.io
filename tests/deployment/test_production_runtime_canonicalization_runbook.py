"""Contract tests for the Production Runtime Canonicalization runbook.

Static-content assertions only (matching this project's existing
convention in test_release_tooling.py / test_compose_secret_boundaries.py).
Deliberately does not assert on any secret, production password, or
complete DATABASE_URL -- the runbook itself must never contain one either.
"""
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNBOOK = REPO_ROOT / "docs" / "deployment" / "production_runtime_canonicalization_runbook.md"


def read_text():
    return RUNBOOK.read_text(encoding="utf-8")


def assert_tokens_in_order(content, *tokens):
    cursor = 0
    for token in tokens:
        index = content.find(token, cursor)
        assert index != -1, f"missing ordered token: {token}"
        cursor = index + len(token)


def test_runbook_exists():
    assert RUNBOOK.is_file()


def test_runbook_does_not_contain_secrets():
    content = read_text()
    assert "POSTGRES_PASSWORD=" not in content, (
        "runbook must not embed a literal credential assignment"
    )
    assert not re.search(r"postgresql://\S+:\S+@", content), (
        "runbook must not embed a complete DATABASE_URL with credentials"
    )
    for forbidden in ("BEGIN PRIVATE KEY", "BEGIN RSA PRIVATE KEY", "ssh-rsa AAAA"):
        assert forbidden not in content


def test_runbook_declares_the_owner_gate_string():
    content = read_text()
    assert "GO_DEPLOY — PRODUCTION RUNTIME CANONICALIZATION" in content


def test_runbook_declares_phase_c_as_separate_and_out_of_scope():
    content = read_text()
    assert "COMMUNITY REWARDS PRODUCTION ENABLEMENT" in content
    assert "not this one" in content or "explicitly NOT part of this runbook" in content


def test_runbook_uses_canonical_script_and_compose_only():
    content = read_text()
    assert "scripts/release/deploy-release-image.ps1" in content
    assert "scripts/release/rollback-release.ps1" in content
    assert "docker-compose.release.yml" in content
    assert "Never use:" in content
    assert_tokens_in_order(content, "Never use:", "docker-compose.prod.yml")


def test_runbook_forbids_docker_restart_as_compose_substitute():
    content = read_text()
    assert "docker restart" in content
    assert "as a substitute for a Compose recreate" in content


def test_runbook_recreate_scope_is_app_and_scheduler_only():
    content = read_text()
    assert "Recreate scope: **`app` and `scheduler` only.**" in content


def test_runbook_forbids_postgres_mutation():
    content = read_text()
    for token in ("do not restart", "do not recreate", "ALTER ROLE", "do not run\nany migration"):
        assert token in content or token.replace("\n", " ") in content.replace("\n", " ")


def test_runbook_forbids_reward_flags_enabled_during_realignment():
    content = read_text()
    assert "COMMUNITY_LEADERBOARD_REWARDS_ENABLED=true" in content
    assert "must never itself set" in content
    assert "PREMIUM_WEEKLY_SCHEDULER_ENABLED" in content


def test_runbook_forbids_e9_changes():
    content = read_text()
    assert "do not modify E9 code, do not enable it" in content
    assert "Flags must read the same" in content


def test_runbook_covers_nginx_refresh_and_public_http_reverification():
    content = read_text()
    assert "upstream-refresh" in content or "upstream refresh" in content
    assert "re-verify public HTTP" in content or "not sufficient proof by\nitself" in content


def test_runbook_post_deploy_provenance_check_is_the_primary_success_condition():
    content = read_text()
    assert "com.docker.compose.project.config_files" in content
    assert "docker-compose.release.yml" in content
    assert "primary success condition" in content


def test_runbook_checks_effective_container_env_not_only_dotenv():
    content = read_text()
    assert "alone is not sufficient proof" in content, (
        "the runbook must require checking the live scheduler container's "
        "effective environment for the reward flags, not just the host .env "
        "-- a compose-wiring gap can leave .env correct but never applied"
    )


def test_runbook_data_invariants_compare_against_captured_baseline_not_hardcoded_numbers():
    content = read_text()
    assert "captured in this run" in content or "not a number hardcoded in this document" in content
    assert "not against any number\nfixed in this document" in content or "not a hardcoded historical number" in content


def test_runbook_rollback_never_uses_snapshot_compose_path():
    content = read_text()
    assert "rollback-release.ps1" in content
    assert "compose_config_files" in content
    assert "must never fall back to" in content


def test_runbook_rollback_never_reverts_to_prod_yml():
    content = read_text()
    assert "Rollback must never leave the runtime back on `docker-compose.prod.yml`." in content


def test_runbook_forbids_reward_preview_or_grant():
    content = read_text()
    assert "do not run a preview, do not grant" in content


def test_runbook_lists_stop_conditions_and_fail_closed_response():
    content = read_text()
    assert "## Stop Conditions" in content
    for stop_reason in (
        "TCP password authentication fails",
        "Postgres is unhealthy",
        "E9 flags are not in the expected",
    ):
        assert stop_reason in content
    assert "Do not self-repair the database." in content
    assert "Do not fall back to `docker-compose.prod.yml`." in content


def test_runbook_orders_execution_phases_correctly():
    content = read_text()
    # preflight -> TCP authentication -> app/scheduler recreate -> nginx
    # refresh -> public HTTP verification -> provenance verification
    assert_tokens_in_order(
        content,
        "## Production Preflight Checklist",
        "TCP password",
        "## Realignment Execution Contract",
        "Recreate scope: **`app` and `scheduler` only.**",
        "upstream-refresh",
        "## Post-Deploy Verification Checklist",
        "### Public HTTP",
        "### Canonical provenance",
    )


def test_runbook_does_not_reference_deployment_evidence_schema_changes():
    content = read_text()
    for forbidden in ("schema_version", "operation_id", "failed_step"):
        assert forbidden not in content, (
            "this runbook is scoped to the runtime realignment procedure, "
            "not the separate deployment-evidence-JSON hardening work"
        )
