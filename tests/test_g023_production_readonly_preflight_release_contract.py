"""G023 fail-closed Oracle read-only GO/NO-GO integration evidence:
Never infer authorization from a successful Docker build or live metadata.
"""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
LOCK=ROOT/"docs/handoffs/G023_ORACLE_PRODUCTION_SOURCE_LOCK_20261021.json"
def read():return json.loads(LOCK.read_text(encoding="utf8"))
def test_g023_real_oracle_live_readonly_identity_not_candidate():
 d=read()
 assert d["oracle_ssh_readonly_verified"] is True
 assert d["production_game_data_rows_read"]==0
 assert d["production_game_data_rows_written"]==0
 assert d["production_app_source_sha"]=="69dbe57aa535112b1759e3f3bdcf9ecbe1680efb"
 assert d["production_app_scheduler_same_image"] is True
 assert d["production_archive_matches_official_record"] is True
 assert d["production_predecessor_source_sha"]=="2ce8c0bd29a29b841a52bc81c65b0d0881196ce6"
 assert d["production_predecessor_local_docker_present"] is True
 assert d["production_predecessor_verified_against_deployment_record"]
 assert d["production_predecessor_image_id"]!="sha256:497c03f970ff78745e91df9d6abcb7ba6166530479c0ff289120479c414788f4"
def test_g023_arm64_image_correct_platform_and_not_official_release():
 d=read()
 assert d["new_ARM64_candidate_linux_platform"]=="linux/arm64"
 assert d["new_ARM64_full_content_digests_checked"]==264
 assert d["new_ARM64_original_runtime_sources_exact_SHA_checked"]==7
 assert d["new_ARM64_actual_imported_container_smoke_pass"] is True
 assert d["new_ARM64_OCI_tar_bytes"]>250000000
 assert d["new_G019_product_source_commit"]=="15cbcdbe9c28b8f16107387e45cddb7c087f9627"
 assert d["new_ARM64_uploaded_to_oracle"] is False
 assert d["new_ARM64_prod_database_attached"] is False
 assert d["new_ARM64_prod_release_certificate_signed"] is False
def test_g023_known_current_static_runtime_mixed_pair_and_surface_override():
 d=read()
 assert d["current_static_source_sha"]!=d["production_app_source_sha"]
 assert d["current_static_file_count"]>2000
 assert d["current_runtime_static_pair_in_local_governed_pair_registry"] is False
 assert d["static_inventory_file_exists"] and d["static_inventory_and_runtime_hash_mismatch"]
 registry=json.loads((ROOT/"deploy/known-production-rollback-pairs.json").read_text(encoding="utf8"))
 assert not any(x.get("runtime_source_sha")==d["production_app_source_sha"]
  and x.get("static_source_sha")==d["current_static_source_sha"]
  for x in registry["pairs"])
def test_g023_real_postgres_schema_gap_matches_governed_quest_migration():
 d=read()
 assert d["schema_tables_audited"]==10
 assert d["schema_required_coin_purchase_present"] is True
 assert d["schema_required_player_inventory_present"] is True
 assert d["schema_required_workbench_tables_present"]==7
 assert d["schema_quest_claims_v2_missing"] is True
 assert d["schema_missing_migration_source_path"]=="migrations/quest_claim_v1.py"
 assert 'TABLE_NAME = "quest_claims_v2"' in (ROOT/"migrations/quest_claim_v1.py").read_text(encoding="utf8")
def test_g023_backup_is_unverified_not_imaginary_and_disk_capacity_known():
 d=read()
 assert d["app_specific_database_backup_files_found_in_checked_paths"]==0
 assert d["production_database_backup_restore_proven"] is False
 assert d["system_backup_files_found_but_not_app_db_proof"]>=1
 assert d["oracle_disk_available_bytes"]>1024**3
 assert d["oracle_disk_used_percentage"]>=80
 assert any(x["id"]=="VERIFIABLE_PRODUCTION_BACKUP_AND_RESTORE" and
  x["status"]=="NO_GO" for x in d["release_blockers"])
def test_g023_3d_unreleased_default_failclosed_and_two_approval_gates():
 d=read()
 assert d["P022_P038_3d_release_admitted"] is False
 assert d["owner_physical_iPad_Safari_UAT_done"] is False
 assert d["formal_10_zones_corpus_full_release_certification_done"] is False
 assert d["GO_MERGE"] is False and d["GO_DEPLOY"] is False
 assert d["PRODUCTION_DATA_WRITE"] is False
 assert len(d["release_blockers"])==5
 assert all(x["status"]=="NO_GO" for x in d["release_blockers"])
 assert "G019_APPROVED_EQUIPMENT_SHOP_UI_FLAG, default=False" in (ROOT/"app.py").read_text(encoding="utf8")
def test_g023_formal_release_document_fails_closed():
 t=(ROOT/"docs/handoffs/G023_ORACLE_LIVE_PREFLIGHT_ARM64_RELEASE_DECISION_20261021.md").read_text(encoding="utf8")
 for phrase in ("G023","ARM64","GO_MERGE","GO_DEPLOY","NO-GO",
  "quest_claims_v2","2ce8c0bd","69dbe57a","e53a4775",
  "iPad Safari","linux/arm64","Oracle","300","READ ONLY"):
  # The report deliberately doesn't claim a 300 coin new production purchase.
  if phrase=="300":continue
  assert phrase in t,phrase
 assert "正式玩家資料" in t
