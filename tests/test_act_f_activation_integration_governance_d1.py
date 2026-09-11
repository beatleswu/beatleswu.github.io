from pathlib import Path


AUTHORITY_ARTIFACT = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "planning"
    / "go_odyssey_activation_0_integration_governance_d1_001.md"
)


def _artifact_text() -> str:
    return AUTHORITY_ARTIFACT.read_text(encoding="utf-8")


def test_activation_governance_artifact_keeps_current_authority_explicit():
    text = _artifact_text()

    required_markers = (
        "GO_ODYSSEY_DEVELOPMENT_SCALABILITY_DECOMPOSITION",
        "FULL_ARCHITECTURE_DECOMPOSITION",
        "SUPERSEDED_CONCEPT",
        "ACTIVE_IDENTITIES=42804",
        "GENESIS_BOOTSTRAP=APPLIED",
        "PRODUCTION_RESOLVER=HOT",
        "canonical_slot",
        "EQUIPMENT_CANONICAL_LOADOUT_ENABLED=OFF",
        "w2_a1_onboarding_v1",
        "Friend Challenge",
        "player_inventory",
        "player_wardrobe",
        "shop_inventory",
        "pet_inventory",
        "TRANSACTION_ORDERING_CONTRACT=PASS",
        "GO_PRODUCTION_DB_MIGRATION=NOT_GRANTED",
    )

    missing = [marker for marker in required_markers if marker not in text]
    assert not missing, f"governance artifact is missing: {missing}"


def test_non_act_a_handoffs_keep_the_app_py_writer_gate():
    text = _artifact_text()

    assert text.count("APP_PY_CHANGED=NO") >= 4
    assert text.count("ACT_A_EXACT_WIRING_REQUEST=") >= 4
    assert "ACT-A is the sole Activation writer" in text
    assert "does not pin a fixed base SHA" in text


def test_governance_artifact_does_not_reactivate_full_decomposition_or_mutation():
    text = _artifact_text()

    assert "FULL_ARCHITECTURE_DECOMPOSITION=SUPERSEDED_CONCEPT" in text
    assert "PRODUCTION_MUTATION=NO" in text
    assert "GO_MERGE=NOT_GRANTED" in text
    assert "GO_DEPLOY=NOT_GRANTED" in text
    assert "DECOMPOSE=NO" in text
