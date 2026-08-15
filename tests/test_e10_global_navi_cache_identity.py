import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")
INVENTORY = json.loads(
    (ROOT / "deploy" / "live-static-asset-inventory.json").read_text(encoding="utf-8")
)


SOURCE_ASSET_IDENTITY = "source-v230-e10-lord-trial-safari-recovery"


def _script_identity(path: str) -> str:
    match = re.search(rf'<script src="/{re.escape(path)}\?v=([^"]+)"></script>', INDEX)
    assert match, f"missing cache-busted script reference for {path}"
    return match.group(1)


def test_e10_navigation_scripts_and_service_worker_have_explicit_release_identity():
    # Query-busted script URLs remain their existing source-level contract;
    # the generated worker receives a release-<full-git-sha> identity during
    # static packaging, so the two layers no longer share a fixed literal.
    assert _script_identity("site-nav.js")
    assert _script_identity("js/e9/shell.js")
    assert f"const ASSET_IDENTITY = '{SOURCE_ASSET_IDENTITY}';" in SW
    assert "Get-StaticReleaseAssetIdentity" in (ROOT / "scripts" / "release" / "ReleaseTooling.psm1").read_text(encoding="utf-8")
    assert "cg-shell-${VERSION}-${ASSET_IDENTITY}" in SW
    assert "cg-img-${VERSION}-${ASSET_IDENTITY}" in SW


def test_service_worker_retires_only_old_go_odyssey_caches_and_uses_named_cache_reads():
    assert "const APP_CACHE_PREFIXES = ['cg-shell-', 'cg-img-'];" in SW
    assert ".filter(k => APP_CACHE_PREFIXES.some(prefix => k.startsWith(prefix)))" in SW
    assert "const cache = await caches.open(cacheName);" in SW
    assert "const cached = await cache.match(request);" in SW
    assert "caches.match(request)" not in SW


def test_e10_navigation_scripts_are_required_in_the_same_static_generation():
    eligible = set(INVENTORY["eligible_files"]["entries"])
    required = set(INVENTORY["required_in_generation"]["entries"])
    expected = {"site-nav.js", "js/e9/shell.js"}
    assert expected <= eligible
    assert expected <= required
    assert (ROOT / "site-nav.js").is_file()
    assert (ROOT / "js" / "e9" / "shell.js").is_file()


def test_e10_runtime_dependency_closure_declares_all_live_runtime_subtrees():
    closure = INVENTORY["runtime_dependency_closure"]
    assert closure["entrypoints"] == ["index.html"]
    assert {item["prefix"] for item in closure["subtrees"]} == {
        "js/e9/", "css/e9/", "components/adventure/"
    }
    for path in (
        "js/e9/world_stage.js",
        "js/e9/adapters/adventure_state.js",
        "css/e9/world_stage.css",
        "components/adventure/world_stage.html",
    ):
        assert path in INVENTORY["eligible_files"]["entries"]
        assert (ROOT / path).is_file()


def test_e10_reconciliation_event_has_one_runtime_producer_and_one_listener():
    site_nav = (ROOT / "site-nav.js").read_text(encoding="utf-8")
    shell = (ROOT / "js" / "e9" / "shell.js").read_text(encoding="utf-8")
    event_name = "e9:shell-state-changed"
    assert site_nav.count(f"addEventListener('{event_name}'") == 1
    assert shell.count(f"new CustomEvent('{event_name}'") == 1
