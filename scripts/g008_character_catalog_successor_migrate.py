"""Run the normal application database initialization for G008 acceptance."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import get_db, init_db
from migrations.sgf_admin_workbench_v1 import upgrade as upgrade_sgf_workbench


with get_db() as conn:
    sgf_workbench = upgrade_sgf_workbench(conn)
    conn.commit()

init_db()
print(
    "G008_CHARACTER_CATALOG_MIGRATION=PASS "
    f"sgf_workbench_tables={len(sgf_workbench['created'])}"
)
