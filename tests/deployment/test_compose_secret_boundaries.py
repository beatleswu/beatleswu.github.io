"""Verify docker-compose.prod.yml keeps secrets out of tracked content and
uses an explicit image identity, not only `latest`."""
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.prod.yml"

# The one literal, non-sensitive value historically present in production
# (`POSTGRES_PASSWORD=go`) must not reappear as a literal in the canonical
# compose file -- it must be sourced from the environment instead.
KNOWN_LITERAL_PASSWORD_PATTERN = re.compile(r"POSTGRES_PASSWORD\s*=\s*go\b")


def read_compose():
    return COMPOSE.read_text(encoding="utf-8")


def test_compose_exists():
    assert COMPOSE.is_file()


def test_compose_has_no_literal_known_password():
    content = read_compose()
    assert not KNOWN_LITERAL_PASSWORD_PATTERN.search(content), (
        "docker-compose.prod.yml must not hardcode POSTGRES_PASSWORD as a literal value"
    )


def test_compose_postgres_password_sourced_from_env():
    content = read_compose()
    assert "POSTGRES_PASSWORD:?" in content or "POSTGRES_PASSWORD:-" in content, (
        "POSTGRES_PASSWORD must be deferred to an environment variable"
    )


def test_compose_uses_explicit_image_variable_not_only_latest():
    content = read_compose()
    assert "GO_ODYSSEY_IMAGE" in content, (
        "app/scheduler services must reference an explicit image variable, "
        "not a hardcoded `latest` tag"
    )


def test_compose_defines_all_required_services():
    content = read_compose()
    for service in ("postgres:", "app:", "scheduler:", "nginx:"):
        assert service in content, f"docker-compose.prod.yml must define service {service.rstrip(':')}"


def test_compose_no_other_literal_secret_values():
    content = read_compose()
    # Every secret-looking env var line must use ${VAR...} substitution, not
    # a bare literal value (POSTGRES_USER/DB names and NEWEBPAY_TEST/PAYPAL_TEST
    # feature flags are not secrets and are allowed to be literal).
    secret_names = (
        "SECRET_KEY", "RESEND_API_KEY", "TURNSTILE_SECRET", "GOOGLE_CLIENT_ID",
        "OPENAI_API_KEY", "NEWEBPAY_MERCHANT_ID", "NEWEBPAY_HASH_KEY",
        "NEWEBPAY_HASH_IV", "PAYPAL_CLIENT_ID", "PAYPAL_SECRET",
    )
    for name in secret_names:
        for line in content.splitlines():
            if line.strip().startswith(f"- {name}="):
                assert f"${{{name}" in line, f"{name} must be sourced via ${{{name}...}}, found: {line.strip()}"
