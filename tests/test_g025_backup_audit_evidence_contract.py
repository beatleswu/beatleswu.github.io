"""G025 evidence discipline: cloud HTTP403 does NOT grant release authority."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
DOC=ROOT/"docs/handoffs/G025_ORACLE_DAILY_BACKUP_403_OCI_IAM_PREFLIGHT_20261021.md"
SRC=ROOT/"scripts/release/g025_oci_backup_readonly_preflight.py"
PRIOR=ROOT/"docs/handoffs/G023_ORACLE_PRODUCTION_SOURCE_LOCK_20261021.json"

def test_g025_three_day_403_and_bootvolume_sdk_classification_documented():
 s=DOC.read_text(encoding="utf8")
 for x in ("2026-10-19","2026-10-20","2026-10-21",
  "731c6e869207","403","oci.core.BlockstorageClient",
  "list_boot_volume_backups","create_boot_volume_backup",
  "delete_boot_volume_backup","get_boot_volume_backup"):
  assert x in s,x
 assert "未確認 403 精確發生" in s

def test_g025_diagnostics_do_not_override_previous_live_prod_schema_no_go():
 d=json.loads(PRIOR.read_text(encoding="utf8"))
 assert d["schema_quest_claims_v2_missing"] is True
 assert d["production_database_backup_restore_proven"] is False
 assert d["GO_MERGE"] is False and d["GO_DEPLOY"] is False
 assert d["P022_P038_3d_release_admitted"] is False

def test_g025_production_release_requires_pg_backup_independent_restore_and_owner_gate():
 s=SRC.read_text(encoding="utf8")
 for key in ("consistent_pg_backup_verified","independent_pg_restore_verified",
  "boot_volume_backup_verified","runtime_static_pair_admitted",
  "owner_deploy_approval"):
  assert key in s,key
 assert "return all((" in s

def test_g025_readonly_diagnostic_never_imports_cloud_sdk_or_writes_to_oci():
 s=SRC.read_text(encoding="utf8")
 assert "import oci" not in s
 assert "create_boot_volume_backup(" not in s
 assert "delete_boot_volume_backup(" not in s
 assert "list_boot_volume_backups" in s
 assert "READONLY_LIST_PASS" in s
 assert "CREATE_AND_RESTORE_UNVERIFIED" in s

def test_g025_runbook_distinguishes_system_snapshot_from_consistent_pg_restore():
 s=DOC.read_text(encoding="utf8")
 for x in ("pg_dump -Fc","pg_restore","OCI Snapshot",
  "PostgreSQL 16","Boot Volume", "GO_MERGE", "GO_DEPLOY",
  "NO-GO","不會安全停止" if False else "安全停止"):
  assert x in s,x
 assert "已修好正式備份" in s
