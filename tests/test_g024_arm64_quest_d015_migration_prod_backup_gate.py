"""G024 Oracle predeploy safety: actual ARM64+synthetic PG receipt is sealed
on beatles, PROD never mutated; additive quest D015 and backups fail closed.
"""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
DOC=ROOT/"docs/handoffs/G024_ORACLE_BACKUP_FAILURE_AND_QUEST_SCHEMA_ISOLATED_REHEARSAL_20261021.md"
G023=ROOT/"docs/handoffs/G023_ORACLE_PRODUCTION_SOURCE_LOCK_20261021.json"

def test_g024_real_migration_module_additive_explicit_transaction_only():
 from migrations.quest_claim_v1 import SCHEMA_VERSION,TABLE_NAME,ADVISORY_LOCK_KEY,upgrade,validate_schema
 assert SCHEMA_VERSION=="quest_claim_v1"
 assert TABLE_NAME=="quest_claims_v2"
 assert isinstance(ADVISORY_LOCK_KEY,int)
 assert callable(upgrade) and callable(validate_schema)
 s=(ROOT/"migrations/quest_claim_v1.py").read_text(encoding="utf8")
 assert "never commits" in s and "pg_advisory_xact_lock" in s
 assert "if dry_run" in s and "IF NOT EXISTS" in s

def test_g024_12_columns_and_dual_idempotency_uniqueness_contract():
 from migrations.quest_claim_v1 import COLUMNS,CLAIM_BUSINESS_UNIQUE_KEY,CLAIM_OPERATION_UNIQUE_KEY,INDEX_SPECS
 assert len(COLUMNS)==12
 assert CLAIM_BUSINESS_UNIQUE_KEY==("user_id","quest_id","period_key")
 assert CLAIM_OPERATION_UNIQUE_KEY==("user_id","claim_operation_id")
 assert INDEX_SPECS==(("idx_quest_claims_v2_user_period",("user_id","period_key")),)
 assert any(x.name=="result_payload" and x.postgres_type=="jsonb" for x in COLUMNS)

def test_g024_prod_quest_table_missing_is_strict_prior_live_evidence():
 d=json.loads(G023.read_text(encoding="utf8"))
 assert d["oracle_ssh_readonly_verified"]
 assert d["schema_quest_claims_v2_missing"] is True
 assert d["schema_required_player_inventory_present"]
 assert d["schema_required_workbench_tables_present"]==7
 assert not d["GO_DEPLOY"] and not d["GO_MERGE"] and not d["PRODUCTION_DATA_WRITE"]

def test_g024_backup_failure_gate_is_still_formal_no_go():
 s=DOC.read_text(encoding="utf8")
 for token in ("2026-10-21","godokro-backup-daily.service","ExecMainStatus=1",
   "godokro-backup-weekly.service","Exit 0","NO-GO","pg_dump",
   "正式資料庫未碰","還原","D015","Oracle Cloud"):
  assert token in s,token
 assert "timer successful" in s
 assert "不能猜根因" in s

def test_g024_genuine_arm64_isolated_DB_scope_and_no_claimed_prod_change():
 t=DOC.read_text(encoding="utf8")
 for token in ("linux/arm64","16","715 Coins","41 XP","Workbench",
               "pg_restore","c61d6f25089f2584a99945447da67384cd9aa85b11544842260f64e9204fba62",
               "GO_MERGE","GO_DEPLOY","e53a4775"):
  assert token in t,token
 assert "正式玩家資料列" in t

def test_g024_static_and_equipment_release_gates_remain_off_by_default():
 code=(ROOT/"app.py").read_text(encoding="utf8")
 shop=(ROOT/"shop.html").read_text(encoding="utf8")
 assert "G019_APPROVED_EQUIPMENT_SHOP_UI_FLAG, default=False" in code
 assert "const G009_SHOP_BROWSE_PREVIEW_ONLY = true;" in shop
 formal=json.loads((ROOT/"schemas/g009_formal9_rights_cleared_replacement_v1.json").read_text(encoding="utf8"))
 assert formal["release_eligibility_value"]=="RIGHTS_CLEARED_RELEASE_NOT_ADMITTED"
 assert not formal["rights"]["PRODUCTION_ASSET_ADMISSION"]
