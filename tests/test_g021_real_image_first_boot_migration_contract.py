"""G021 first-empty-PostgreSQL Docker installation is governed and fail closed.
G021 live image and PG browser evidence is captured separately on beatles.
"""
from pathlib import Path
import ast
ROOT=Path(__file__).resolve().parents[1]
HANDOFF=ROOT/"docs/handoffs/G021_REAL_ATTESTED_DOCKER_PG_PLAYER_AND_RESTORE_20261021.md"
def test_g021_missing_workbench_schema_protected_by_governed_migration():
 from migrations.sgf_admin_workbench_v1 import TABLE_SPECS, upgrade, SCHEMA_VERSION
 assert len(TABLE_SPECS)==7
 assert SCHEMA_VERSION=="sgf_admin_workbench_v1"
 assert callable(upgrade)
 assert all(key.startswith("sgf_workbench_") for key in TABLE_SPECS)
 app=(ROOT/"app.py").read_text(encoding="utf8")
 workbench=(ROOT/"sgf_admin_workbench.py").read_text(encoding="utf8")
 assert "ensure_sgf_workbench_tables(conn)" in app
 assert "workbench schema missing:" in workbench
 assert "SchemaMismatch" in workbench
def test_g021_source_image_includes_governed_migration_and_no_general_wildcard():
 dockerfile=(ROOT/"Dockerfile").read_text(encoding="utf8")
 assert "COPY migrations/sgf_admin_workbench_v1.py" in dockerfile
 assert "COPY app.py ./" in dockerfile
 assert all(not line.strip().startswith("COPY *.py") for line in dockerfile.splitlines())
def test_g021_product_still_default_closed_after_stage_test():
 source=(ROOT/"app.py").read_text(encoding="utf8")
 shop=(ROOT/"shop.html").read_text(encoding="utf8")
 inv=(ROOT/"inventory.html").read_text(encoding="utf8")
 assert "'G019_APPROVED_EQUIPMENT_SHOP_UI_ENABLED'" in source
 assert "G019_APPROVED_EQUIPMENT_SHOP_UI_FLAG, default=False" in source
 assert "const G009_SHOP_BROWSE_PREVIEW_ONLY = true" in shop
 assert "g019ServerApprovedEquipmentUi" in shop
 assert "const G009_BACKPACK_READ_ONLY = true" in inv
 assert "g019ServerApprovedEquipmentActionsUi" in inv
def test_g021_evidence_handoff_release_scope_does_not_conflate_qa_deployment():
 s=HANDOFF.read_text(encoding="utf8")
 for phrase in ("127.0.0.1:5097","SchemaMismatch","七張",
  "G021_FLAG_ROLLBACK_LIVE_PG_PERSISTENCE_20261021.json",
  "G021_RESTORED_BACKUP_INTEGRITY_20261021.json",
  "GO_MERGE","GO_DEPLOY","沒有任何對主機公開的埠","正式 Oracle"):
  assert phrase in s,phrase
 assert "stage.env" in s  # only forbidden as a redistributable secret
 assert "G021_REAL_OCI_PLAYER_SHOP_BACKPACK_HERO_20261021.json" not in s or "300" in s
