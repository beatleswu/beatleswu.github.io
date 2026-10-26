"""G111 local-only portable clock and additive Nonmap migration contract tests.
This module never connects to any external database or service.
"""
from pathlib import Path
import hashlib
import importlib
import pytest

ROOT=Path(__file__).resolve().parents[1]
OLD_TEST=ROOT/"tests/test_g076_step_http_isolated.py"


def test_historic_HTTP_fixture_clock_is_in_source_control_not_plugin():
    test_source=OLD_TEST.read_text(encoding="utf8")
    assert "_G111HTTPFixtureDateTime" in test_source
    assert 'monkeypatch.setattr(_map_battle_runtime, "datetime", _G111HTTPFixtureDateTime)' in test_source
    assert '2026-10-23T11:00:00+00:00' in test_source
    assert "g110_http_fixture_clock_plugin" not in test_source


def test_source_portable_fixture_does_not_modify_product_expiry_predicate():
    from map_battle_runtime import _attempt_expired
    attempt={"state":"ISSUED","expires_at":"2026-10-24T10:00:00+00:00"}
    assert _attempt_expired(attempt,now="2026-10-23T11:00:00+00:00") is False
    assert _attempt_expired(attempt,now="2026-10-24T10:00:00+00:00") is True
    assert _attempt_expired(attempt,now="2026-10-25T13:00:00+00:00") is True


def test_G111_sql_canonical_hash_and_four_additive_tables():
    module=importlib.import_module("migrations.g111_nonmap_practice_mistakes_atomic_v1")
    source=(ROOT/"migrations/g111_nonmap_practice_mistakes_atomic_v1.sql").read_bytes()
    assert hashlib.sha256(source).hexdigest()==module.SQL_SHA256
    assert len(module.TABLES)==4
    for table in module.TABLES:
        assert ("CREATE TABLE "+table).encode() in source
    text=source.decode("utf8")
    assert "('practice', 'daily', 'mistakes')" in text
    assert "IF NOT EXISTS" not in "\n".join(x for x in text.splitlines() if not x.strip().startswith("--"))
    assert "DROP TABLE" not in text
    assert "\nCOMMIT;" not in text and "\nBEGIN;" not in text


def test_G111_source_checks_historical_legacy_migrations_exact():
    module=importlib.import_module("migrations.g111_nonmap_practice_mistakes_atomic_v1")
    for name,expected in module.HISTORICAL_SHA256.items():
        f=ROOT/"migrations"/name
        assert hashlib.sha256(f.read_bytes()).hexdigest()==expected
    assert len(module.HISTORICAL_SHA256)==5


def test_G111_operator_explicit_approval_refuses_without_DB_access():
    from migrations.g111_nonmap_practice_mistakes_atomic_v1 import (
        upgrade,G111MigrationRejected
    )
    with pytest.raises(G111MigrationRejected,match="explicit operator approval"):
        upgrade(None,environ={})


@pytest.mark.parametrize("kind",["autocommit","opaque"])
def test_G111_disallows_nontransactional_callers_before_queries(kind):
    from migrations.g111_nonmap_practice_mistakes_atomic_v1 import (
        upgrade,G111MigrationRejected,FLAG
    )
    class NoSQLConnection:
        autocommit = (True if kind=="autocommit" else None)
        def execute(self,*args,**kwargs):
            raise AssertionError("No SQL allowed before reject")
    with pytest.raises(G111MigrationRejected,match="non-autocommit"):
        upgrade(NoSQLConnection(),environ={FLAG:"1"})


@pytest.mark.parametrize("name",[
    "G076_NONMAP_STEPS_ENABLED",
    "G076_PRACTICE_STEPS_ENABLED",
    "G076_DAILY_STEPS_ENABLED",
    "G076_MISTAKES_STEPS_ENABLED",
])
def test_G111_rollback_requires_all_relevant_step_modes_off(name):
    from migrations.g111_nonmap_practice_mistakes_atomic_v1 import (
        downgrade,G111MigrationRejected
    )
    with pytest.raises(G111MigrationRejected,match="disable step feature"):
        downgrade(environ={name:"on"})


def test_G111_rollback_keeps_existing_history():
    from migrations.g111_nonmap_practice_mistakes_atomic_v1 import downgrade,VERSION
    result=downgrade(environ={"G076_MISTAKES_STEPS_ENABLED":"off"})
    assert result["no_ddl"] is True
    assert result["no_player_records_deleted"] is True
    assert result["version"]==VERSION


def test_G110_map_ledger_and_G111_nonmap_use_distinct_version_markers():
    from migrations.g110_step_ledger_atomic_v1 import REGISTRY as MAP_REGISTRY
    from migrations.g111_nonmap_practice_mistakes_atomic_v1 import REGISTRY as OTHER_REGISTRY
    assert MAP_REGISTRY != OTHER_REGISTRY
    assert MAP_REGISTRY == "g110_schema_migrations"
    assert OTHER_REGISTRY == "g111_nonmap_schema_versions"


def test_app_does_not_automatically_execute_G111_migration():
    app=(ROOT/"app.py").read_text(encoding="utf8")
    assert "g111_nonmap_practice_mistakes_atomic_v1" not in app
