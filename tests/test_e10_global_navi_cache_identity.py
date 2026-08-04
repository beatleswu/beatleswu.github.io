import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")
INVENTORY = json.loads(
    (ROOT / "deploy" / "live-static-asset-inventory.json").read_text(encoding="utf-8")
)


ASSET_IDENTITY = "20260804e10navcache1"


def _script_identity(path: str) -> str:
    match = re.search(rf'<script src="/{re.escape(path)}\?v=([^"]+)"></script>', INDEX)
    assert match, f"missing cache-busted script reference for {path}"
    return match.group(1)


def test_e10_navigation_scripts_share_one_cache_identity():
    assert _script_identity("site-nav.js") == ASSET_IDENTITY
    assert _script_identity("js/e9/shell.js") == ASSET_IDENTITY
    assert f"const ASSET_IDENTITY = '{ASSET_IDENTITY}';" in SW
    assert "cg-shell-${VERSION}-${ASSET_IDENTITY}" in SW
    assert "cg-img-${VERSION}-${ASSET_IDENTITY}" in SW


def test_e10_navigation_scripts_are_required_in_the_same_static_generation():
    eligible = set(INVENTORY["eligible_files"]["entries"])
    required = set(INVENTORY["required_in_generation"]["entries"])
    expected = {"site-nav.js", "js/e9/shell.js"}
    assert expected <= eligible
    assert expected <= required
    assert (ROOT / "site-nav.js").is_file()
    assert (ROOT / "js" / "e9" / "shell.js").is_file()


def test_e10_reconciliation_event_has_one_runtime_producer_and_one_listener():
    site_nav = (ROOT / "site-nav.js").read_text(encoding="utf-8")
    shell = (ROOT / "js" / "e9" / "shell.js").read_text(encoding="utf-8")
    event_name = "e9:shell-state-changed"
    assert site_nav.count(f"addEventListener('{event_name}'") == 1
    assert shell.count(f"new CustomEvent('{event_name}'") == 1
