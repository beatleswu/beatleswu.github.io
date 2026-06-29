import json

import pytest

from sgf_engine.override import override_loader


def _write_override(tmp_path, document):
    path = tmp_path / "puzzle_variation_overrides.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_load_override_normalizes_source_and_returns_copy(tmp_path, monkeypatch):
    path = _write_override(
        tmp_path,
        {
            "SGF/path/11.sgf": {
                "quality": "gold",
                "accepted_first_moves": ["dd"],
                "equivalent_moves": {"dd": ["pp"]},
                "review_status": "reviewed",
            }
        },
    )
    monkeypatch.setattr(override_loader, "OVERRIDES_FILE", path)

    loaded = override_loader.load_override(r"SGF\path\11.sgf")
    assert loaded["quality"] == "gold"
    assert loaded["equivalent_moves"] == {"dd": ["pp"]}

    loaded["quality"] = "mutated"
    assert override_loader.load_override("SGF/path/11.sgf")["quality"] == "gold"


def test_load_override_returns_nested_defensive_copy(tmp_path, monkeypatch):
    path = _write_override(
        tmp_path,
        {
            "SGF/path/11.sgf": {
                "equivalent_moves": {"dd": ["pp", "qq"]},
            }
        },
    )
    monkeypatch.setattr(override_loader, "OVERRIDES_FILE", path)

    loaded = override_loader.load_override("SGF/path/11.sgf")
    loaded["equivalent_moves"]["dd"][0] = "cc"

    reloaded = override_loader.load_override("SGF/path/11.sgf")
    assert reloaded["equivalent_moves"]["dd"] == ["pp", "qq"]


def test_missing_source_returns_none(tmp_path, monkeypatch):
    path = _write_override(tmp_path, {})
    monkeypatch.setattr(override_loader, "OVERRIDES_FILE", path)

    assert override_loader.load_override("SGF/path/missing.sgf") is None


def test_malformed_json_raises(tmp_path, monkeypatch):
    path = tmp_path / "puzzle_variation_overrides.json"
    path.write_text("{malformed", encoding="utf-8")
    monkeypatch.setattr(override_loader, "OVERRIDES_FILE", path)

    with pytest.raises(json.JSONDecodeError):
        override_loader.load_override("SGF/path/11.sgf")


def test_ambiguous_equivalent_raises(tmp_path, monkeypatch):
    path = _write_override(
        tmp_path,
        {
            "SGF/path/11.sgf": {
                "equivalent_moves": {"dd": ["pp"], "cc": ["pp"]}
            }
        },
    )
    monkeypatch.setattr(override_loader, "OVERRIDES_FILE", path)

    with pytest.raises(ValueError, match="multiple canonical"):
        override_loader.load_override("SGF/path/11.sgf")


def test_canonical_coord_for_resolves_declared_alternative():
    override = {"equivalent_moves": {"dd": ["pp", "qq"]}}

    assert override_loader.canonical_coord_for(override, "pp") == "dd"
