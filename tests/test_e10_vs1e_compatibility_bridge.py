"""Fail-closed static/runtime handshake for the VS1E visual shell."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
WORLD_JS = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
FLAGS = (ROOT / "js/e9/feature_flags.js").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")

CONTRACT = "e10-vs1f-integrated-world-map"
MARKER = f'<meta name="go-odyssey-static-contract" content="{CONTRACT}">'


def test_target_static_carries_one_exact_contract_marker():
    assert INDEX.count(MARKER) == 1
    assert INDEX.index(MARKER) < INDEX.index("/js/e9/world_stage.js")


def test_runtime_contract_is_private_exact_and_fail_closed():
    assert f"var VS1E_STATIC_CONTRACT = '{CONTRACT}';" in WORLD_JS
    assert (
        """document.querySelector(
    'meta[name="go-odyssey-static-contract"]'
  )"""
        in WORLD_JS
    )
    assert (
        "staticContractMarker.getAttribute('content') === VS1E_STATIC_CONTRACT"
        in WORLD_JS
    )
    assert "if (!VS1E_STATIC_CONTRACT_ACTIVE)" in WORLD_JS
    guard = WORLD_JS.index("if (!VS1E_STATIC_CONTRACT_ACTIVE)")
    skin_write = WORLD_JS.index(
        "shell.setAttribute('data-e10-visual-skin', 'immersive-rpg')"
    )
    assert guard < skin_write


def test_query_host_storage_and_mutable_globals_are_not_contract_inputs():
    contract_block = WORLD_JS[
        WORLD_JS.index("var VS1E_STATIC_CONTRACT =")
        : WORLD_JS.index("function t(")
    ]
    for forbidden in (
        "location",
        "hostname",
        "search",
        "URLSearchParams",
        "localStorage",
        "sessionStorage",
        "window.E9",
        "__GO_",
    ):
        assert forbidden not in contract_block


def test_vs1d_render_path_is_preserved_without_the_contract():
    assert "function prepareVs1dDom(root)" in WORLD_JS
    assert "mapStage.parentNode.insertBefore(status, mapStage);" in WORLD_JS
    assert "if (VS1E_STATIC_CONTRACT_ACTIVE)" in WORLD_JS
    assert "tile.appendChild(label);" in WORLD_JS
    assert "else if (VS1E_STATIC_CONTRACT_ACTIVE)" in WORLD_JS
    assert (
        "VS1E_STATIC_CONTRACT_ACTIVE ? !isPortraitTablet : isMobile"
        in WORLD_JS
    )


def test_bridge_versions_are_exactly_coupled():
    assert "ASSET_VERSION = 'e10-art-directed-runtime-ui'" in FLAGS
    assert "const VERSION     = 'v223-e10-final-visual-refinement'" in SW
    assert "e10-vs1e-review-closure" not in FLAGS
    assert "v213-e10-vs1e-review-closure" not in SW
    queries = re.findall(
        r'(?:i18n\.js|immersive_rpg\.css|feature_flags\.js|right_cards\.js|world_stage\.js)'
        r'\?v=([^"\']+)',
        INDEX,
    )
    assert queries == ["20260801e10art1"] * 5
