import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "planning" / "e10_six_spirit_new_identity_design_a020.json"
SPEC = ROOT / "docs" / "planning" / "e10_six_spirit_new_identity_design_a020.md"


def load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_owner_selected_identity_set_is_exactly_the_new_three():
    data = load_manifest()
    spirits = data["current_spirits"]
    assert [(spirit["slot"], spirit["name"], spirit["role"]) for spirit in spirits] == [
        (4, "Starpath Antlerling", "EXPLORATION"),
        (5, "Fatty", "PRECISION"),
        (6, "Obsidian Bastion", "SUPPORT"),
    ]
    assert all(spirit["identity_status"] == "OWNER_SELECTED" for spirit in spirits)
    assert data["invariants"]["new_form_count"] == 9


def test_rejected_a020_identities_are_historical_only():
    data = load_manifest()
    rejected = data["superseded_previous_a020"]
    assert len(rejected) == 3
    assert all(item["status"] == "REJECTED_BY_OWNER" for item in rejected)
    assert all(item["active_candidate"] is False for item in rejected)
    active_text = SPEC.read_text(encoding="utf-8").split("## Authoritative current set", 1)[1]
    active_text = active_text.split("## Shared evolution and readability contract", 1)[0]
    for item in rejected:
        assert item["previous_name"] not in active_text
        assert item["previous_name_zh"] not in active_text


def test_owner_reference_and_six_review_images_close():
    data = load_manifest()
    reference = ROOT / data["owner_reference"]["path"]
    assert reference.is_file()
    with Image.open(reference) as image:
        assert image.size == (1280, 853)
    assert len(data["review_images"]) == 6
    assert all((ROOT / item["path"]).is_file() for item in data["review_images"])
    assert all(len(spirit["stages"]) == 3 for spirit in data["current_spirits"])


def test_reference_crops_are_in_bounds_and_no_runtime_authority_changed():
    data = load_manifest()
    with Image.open(ROOT / data["owner_reference"]["path"]) as image:
        width, height = image.size
    for spirit in data["current_spirits"]:
        for stage in spirit["stages"]:
            x1, y1, x2, y2 = stage["source_crop"]
            assert 0 <= x1 < x2 <= width
            assert 0 <= y1 < y2 <= height
    invariants = data["invariants"]
    assert invariants["runtime_assets_added"] == 0
    assert invariants["runtime_catalog_changed"] is False
    assert invariants["app_py_changed"] is False
    assert invariants["route_changed"] is False
    assert invariants["stage_iii_unauthorized_exaggeration_count"] == 0
