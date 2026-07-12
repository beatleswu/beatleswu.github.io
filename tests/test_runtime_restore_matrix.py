from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "build_runtime_restore_matrix.py"
SPEC = importlib.util.spec_from_file_location("build_runtime_restore_matrix", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

build_matrix = MODULE.build_matrix
load_inventory = MODULE.load_inventory


def row_by_path(matrix, path: str):
    return next(row for row in matrix if row.path == path)


def test_restore_matrix_classifies_key_runtime_files_correctly():
    inventory = load_inventory(Path("docs/testing/runtime_integrity_inventory_2026-07-12.csv"))
    matrix = build_matrix(inventory)

    assert len(matrix) == 1301

    admin = row_by_path(matrix, "admin.html")
    assert admin.classification == "RESTORE"
    assert admin.owner == "Git Runtime"

    login = row_by_path(matrix, "login.html")
    assert login.classification == "RESTORE"
    assert login.owner == "Git Runtime"

    upgrade = row_by_path(matrix, "upgrade.html")
    assert upgrade.classification == "RESTORE"
    assert upgrade.owner == "Git Runtime"

    i18n = row_by_path(matrix, "i18n.js")
    assert i18n.classification == "RESTORE"
    assert i18n.owner == "Static Current"

    sw = row_by_path(matrix, "sw.js")
    assert sw.classification == "RESTORE"
    assert sw.owner == "Static Current"

    questions = row_by_path(matrix, "questions.json")
    assert questions.classification == "GENERATED"
    assert questions.owner == "Generated Runtime"

    chapter_overrides = row_by_path(matrix, "chapter_overrides.json")
    assert chapter_overrides.classification == "GENERATED"
    assert chapter_overrides.owner == "Generated Runtime"

    assets_png = row_by_path(matrix, "assets/boards/board_classic.webp")
    assert assets_png.classification == "KEEP"
    assert assets_png.owner == "Static Current"

    static_override_asset = row_by_path(matrix, "assets/hero/chibi_rpg_fullbody_pixel_avatar.html")
    assert static_override_asset.classification == "RESTORE"
    assert static_override_asset.owner == "Static Current"
