"""G110 local source + migration contract. No Docker, network, or production IO."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "migrations" / "g110_step_ledger_atomic_v1.sql"
MANIFEST = ROOT / "deploy" / "g110-pr445-frozen-source-inventory.json"
REVIEWED_SHA = "f5edab377f1b8446684c3acdfb465ea3ba2d5d7e4087b82ffae2f76d640f4209"
SQL_SHA = "bb897a7e1275209f2160965bc6dd98b265581ebde00d1e6be4dceaf05c030251"


def _import_candidate():
    f = ROOT / "scripts" / "release" / "g110_local_admission_candidate.py"
    spec = importlib.util.spec_from_file_location("g110_source_candidate", f)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest_fixture():
    m = json.loads(MANIFEST.read_text(encoding="utf8"))
    entries = {}
    for x in m["entries"]:
        entries[x["path"]] = {
            k: x[k] for k in ("status", "mode", "git_blob_oid", "canonical_sha256", "byte_size") if k in x
        }
    return m, {"paths": set(entries), "entries": entries, "total": m["changed_git_blob_bytes"]}


def test_source_frozen_G108_exactly_283():
    assert hashlib.sha256(MANIFEST.read_bytes()).hexdigest() == REVIEWED_SHA
    manifest = json.loads(MANIFEST.read_text(encoding="utf8"))
    assert manifest["changed_paths_count"] == len(manifest["entries"]) == 283


def test_new_product_migration_uses_reviewed_SQL_bytes():
    from migrations import g110_step_ledger_atomic_v1 as m
    assert m.EXPECTED_SQL_SHA256 == hashlib.sha256(SOURCE.read_bytes()).hexdigest() == SQL_SHA
    assert "CREATE TABLE g076_step_sessions" in m._source_sql()


def test_new_migration_no_embedded_transactions_or_weak_if_not_exists():
    sql = SOURCE.read_text(encoding="utf8")
    assert "\nBEGIN;\n" not in sql
    assert "\nCOMMIT;\n" not in sql
    assert "IF NOT EXISTS" not in sql
    assert "ON DELETE CASCADE" in sql
    assert "g076_step_sessions_owner_attempt_fk" in sql


def test_original_historical_G076_SQL_unchanged_and_risky():
    old = ROOT / "migrations" / "g076_step_ledger_postgres_PROPOSED.sql"
    s = old.read_text(encoding="utf8")
    assert "BEGIN;" in s and "COMMIT;" in s and "CREATE TABLE IF NOT EXISTS" in s


def test_migration_denies_without_explicit_flag_before_any_connection_use():
    from migrations import g110_step_ledger_atomic_v1 as module
    with pytest.raises(module.G110MigrationRejected, match="explicit owner-authorized"):
        module.upgrade(None, environ={})


@pytest.mark.parametrize("value",["on","true","1","unexpected"])
def test_old_runtime_rollback_rejects_steps_still_active(value):
    from migrations.g110_step_ledger_atomic_v1 import downgrade, G110MigrationRejected
    with pytest.raises(G110MigrationRejected, match="disable Step Runtime"):
        downgrade(environ={"G076_STEP_RUNTIME_ENABLED":value})


def test_disabled_runtime_rollback_preserves_additive_tables():
    from migrations.g110_step_ledger_atomic_v1 import downgrade
    x=downgrade(environ={"G076_STEP_RUNTIME_ENABLED":"off"})
    assert x["no_ddl"] is True and x["no_player_data_delete"] is True


def test_G076_map_battle_step_routes_default_off_require_privacy_gate():
    app = (ROOT / "app.py").read_text(encoding="utf8")
    chunk = app.split("def _g076_step_enabled():",1)[1].split("@app.route",1)[0]
    assert "G076_STEP_RUNTIME_ENABLED" in chunk
    assert "privacy_enforced(os.environ)" in chunk
    for endpoint in ("g076_map_battle_step_start", "g076_map_battle_step_submit"):
        region=app.split("def "+endpoint+"():",1)[1][:680]
        assert "if not _g076_step_enabled()" in region
        assert "return jsonify({'error': 'g076_step_runtime_disabled'}), 503" in region


def test_unconverted_nonmap_mode_legacy_allowed_when_privacy_off():
    from g076_mode_gate import select_mode
    assert select_mode({},"mistakes",adapter_ready=False).selected == "legacy"
    assert select_mode({"G076_ANSWER_PRIVACY_ENFORCED":"on"},
                       "mistakes",adapter_ready=False).selected == "hold"


def test_local_source_validator_matches_current_frozen_fixture():
    checker=_import_candidate()
    m,actual=_manifest_fixture()
    assert checker.validate_reviewed_payload(m,actual)==283
    assert checker.MASTER != checker.REVIEWED_PR445
    assert checker.REVIEWED_MANIFEST_SHA256==REVIEWED_SHA


@pytest.mark.parametrize("change,error",[
    ("SHA","GIT_BLOB_SHA256"),
    ("HEAD","BASE_OR_HEAD"),
    ("BASE","BASE_OR_HEAD"),
    ("ADD","CARDINALITY"),
    ("REMOVE","CARDINALITY"),
    ("DUPLICATE","DUPLICATE_PATH"),
    ("COUNT","COMMIT_COUNT"),
    ("MODE","GIT_MODE"),
    ("TOTAL","BLOB_TOTAL_BYTES"),
])
def test_local_admission_exact_negative_reason(change,error):
    checker=_import_candidate()
    m,actual=_manifest_fixture()
    m=copy.deepcopy(m)
    x=m["entries"]
    if change=="SHA":x[0]["canonical_sha256"]="0"*64
    elif change=="HEAD":m["candidate_ci_only_head"]="0"*40
    elif change=="BASE":m["origin_master_base"]="0"*40
    elif change=="ADD":x.append({"path":"new-unapproved.txt","status":"PRESENT"})
    elif change=="REMOVE":x.pop()
    elif change=="DUPLICATE":x[1]["path"]=x[0]["path"]
    elif change=="COUNT":m["ahead_commits"]=72
    elif change=="MODE":x[0]["mode"]="100755" if x[0]["mode"]=="100644" else "100644"
    elif change=="TOTAL":m["changed_git_blob_bytes"]=1
    with pytest.raises(checker.AdmissionRejected) as exc:
        checker.validate_reviewed_payload(m,actual)
    assert exc.value.code==error
