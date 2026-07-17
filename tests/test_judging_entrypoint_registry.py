from pathlib import Path


REGISTRY = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "planning"
    / "judging_entrypoint_registry.md"
)


def _registry_rows():
    rows = []
    for line in REGISTRY.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| JEP-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows.append(cells)
    return rows


def test_registry_is_complete_unique_and_has_all_required_columns():
    rows = _registry_rows()

    assert len(rows) == 16
    assert [row[0] for row in rows] == [f"JEP-{index:03d}" for index in range(1, 17)]
    assert all(len(row) == 14 for row in rows)
    assert len({row[0] for row in rows}) == len(rows)


def test_registry_classification_totals_and_eligibility_gate_are_explicit():
    rows = _registry_rows()
    classifications = [row[9].strip("`") for row in rows]

    assert classifications.count("ALREADY_COVERED") == 3
    assert classifications.count("ELIGIBLE") == 0
    assert classifications.count("EXCLUDED") == 13
    assert all(row[10] for row in rows if row[9].strip("`") == "EXCLUDED")
    assert all(row[11] and row[12] for row in rows)


def test_registry_preserves_diagnostic_and_protected_data_boundaries():
    text = REGISTRY.read_text(encoding="utf-8")

    assert "Player-facing judging changed: No" in text
    assert "must not be repaired in this work item" in text
    assert "actual player move sequence, not a result-derived synthetic path" in text
    assert "without reading protected question corpus payloads" in text
    assert "phase23_analysis_20260717.md` is absent" in text
