"""G009 dual delivery: live-static first, baked image copy as the fallback.

Owner authority: every new public G009 asset (Hero CSS/JS, the 84 Derived84
identity assets, the ten World Map zone previews and the release-required
Hero models) has both a baked image copy and a governed static-generation
copy with the same accepted bytes, served by the existing
``_serve_live_static_or_baked_subpath`` resolver.

The closure tests read the tracked source and manifests.  The source-selection
tests prove WHICH copy the resolver serves using test-only fixture bytes in
temporary directories; no governed asset, manifest or application behaviour is
changed to make the selection observable.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess

import pytest

import app as app_module

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
INVENTORY = REPO_ROOT / "deploy" / "live-static-asset-inventory.json"
BUILD_MANIFEST = REPO_ROOT / "deploy" / "build-manifest.json"
DOCKERFILE = REPO_ROOT / "Dockerfile"

HERO_CSS = "css/g009_hero_hub_batch_a.css"
HERO_JS = "js/g009_hero_hub_batch_a.js"
DERIVED_MANIFEST = "assets/world-map-identity/runtime_manifest.json"
PREVIEW_PREFIX = "assets/maps/e10-vs1f-zone-previews/"
PREVIEW_MANIFEST = PREVIEW_PREFIX + "WORLD_MAP_ZONE_PREVIEW_MANIFEST.json"

DERIVED_PACK = "deploy/g009-derived84-static-pack-manifest.json"
PREVIEW_PACK = "deploy/g009-world-map-zone-preview-static-pack-manifest.json"
MODEL_PACK = "deploy/g009-hero-model-static-pack-manifest.json"
COMPANION_PACK = "deploy/g009-companion-formal18-static-pack-manifest.json"
FORMAL9_PACK = "deploy/g009-formal9-replacement-static-pack-manifest.json"
BONUS_PACK = "deploy/g043-bonus-companion-supplemental-static-pack-manifest.json"

DIAGNOSTIC_HEADERS = ("X-Served-From", "X-Static-Source", "X-Asset-Source")


def _json(relative: str):
    return json.loads((REPO_ROOT / relative).read_text(encoding="utf-8"))


def _sha256(relative: str) -> str:
    return hashlib.sha256((REPO_ROOT / relative).read_bytes()).hexdigest()


def _tracked() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    )
    return {line for line in result.stdout.splitlines() if line}


def _docker_sources() -> list[str]:
    sources: list[str] = []
    text = DOCKERFILE.read_text(encoding="utf-8").replace("\\\n", " ")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("COPY "):
            tokens = [t for t in stripped.split()[1:] if not t.startswith("--")]
            sources.extend(tokens[:-1])
    return sources


def _baked(tracked: set[str]) -> set[str]:
    baked: set[str] = set()
    for source in _docker_sources():
        if source.endswith("/") or (REPO_ROOT / source).is_dir():
            prefix = source.rstrip("/") + "/"
            baked |= {path for path in tracked if path.startswith(prefix)}
        else:
            baked.add(source)
    return baked


def _static_governed() -> dict[str, dict]:
    """Every path a static generation stages, with its declared size/hash."""
    inventory = _json("deploy/live-static-asset-inventory.json")
    governed: dict[str, dict] = {}
    seen_casefold: set[str] = set()
    for entry in inventory["required_subtrees"]["entries"]:
        manifest = _json(entry["manifest"])
        for row in manifest["files"]:
            path = row["path"]
            assert path.startswith(entry["prefix"]), (entry["manifest"], path)
            assert path.casefold() not in seen_casefold, f"duplicate normalized path: {path}"
            seen_casefold.add(path.casefold())
            governed[path] = row
    for path in inventory["required_in_generation"]["entries"]:
        assert path.casefold() not in seen_casefold, f"duplicate normalized path: {path}"
        seen_casefold.add(path.casefold())
        governed[path] = {"path": path}
    return governed


def _pack_rows(manifest_relative: str) -> list[dict]:
    manifest = _json(manifest_relative)
    rows = manifest["files"]
    assert manifest["total_files"] == len(rows)
    assert manifest["total_bytes"] == sum(row["size"] for row in rows)
    return rows


def _assert_pack_matches_tracked_bytes(manifest_relative: str) -> list[dict]:
    tracked = _tracked()
    rows = _pack_rows(manifest_relative)
    assert len({row["path"] for row in rows}) == len(rows)
    for row in rows:
        path = row["path"]
        assert path in tracked, f"{path} is not a tracked source file"
        assert ".." not in path.split("/") and not path.startswith("/")
        assert (REPO_ROOT / path).stat().st_size == row["size"], path
        assert _sha256(path) == row["sha256"], path
    return rows


# --------------------------------------------------------------------------
# Hero CSS / JS
# --------------------------------------------------------------------------
def test_hero_bundle_has_baked_copy_static_copy_and_resolver_route():
    tracked = _tracked()
    baked = _baked(tracked)
    inventory = _json("deploy/live-static-asset-inventory.json")
    build = _json("deploy/build-manifest.json")
    for path in (HERO_CSS, HERO_JS):
        assert path in tracked
        assert path in baked, f"{path} has no baked image copy"
        assert path in build["build_inputs"]["tracked_in_canonical_branch_this_sprint"]
        assert f"/app/{path}" in build["post_build_verification_files"]
        assert path in inventory["eligible_files"]["entries"]
        assert path in inventory["required_in_generation"]["entries"], f"{path} is not staged"

    source = (REPO_ROOT / "app.py").read_text(encoding="utf-8")
    assert "'g009_hero_hub_batch_a.js'," in source
    assert "@app.route('/css/g009_hero_hub_batch_a.css')" in source
    hero_html = (REPO_ROOT / "hero.html").read_text(encoding="utf-8")
    assert '/css/g009_hero_hub_batch_a.css' in hero_html
    assert '/js/g009_hero_hub_batch_a.js' in hero_html


def test_hero_bundle_canonical_urls_serve_accepted_bytes():
    client = app_module.app.test_client()
    for url, path in (("/" + HERO_CSS, HERO_CSS), ("/" + HERO_JS, HERO_JS)):
        response = client.get(url)
        assert response.status_code == 200, url
        assert hashlib.sha256(response.data).hexdigest() == _sha256(path)


# --------------------------------------------------------------------------
# Derived84
# --------------------------------------------------------------------------
def test_derived84_image_validation_inputs_and_dual_closure_are_84_of_84():
    import derived84_asset_registry as registry

    assert registry.DERIVED84_RUNTIME_AVAILABLE is True, registry.DERIVED84_RUNTIME_ERROR
    manifest = _json(DERIVED_MANIFEST)
    entries = manifest["entries"]
    assert len(entries) == 84
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["asset_role"]] = counts.get(entry["asset_role"], 0) + 1
    assert counts == {"AVATAR": 33, "STANDING": 33, "COMPANION": 18}

    baked = _baked(_tracked())
    rows = {row["path"]: row for row in _assert_pack_matches_tracked_bytes(DERIVED_PACK)}
    assert DERIVED_MANIFEST in baked and DERIVED_MANIFEST in rows
    assert len(rows) == 85  # 84 accepted assets + the runtime manifest the client reads
    for entry in entries:
        path = entry["target_runtime_path"]
        accepted = entry["expected_runtime_sha256"].lower()
        assert path in baked, f"{path} has no baked image copy"
        assert path in rows, f"{path} has no static-generation copy"
        assert _sha256(path) == accepted, f"baked bytes differ from accepted authority: {path}"
        assert rows[path]["sha256"] == accepted, f"static bytes differ from accepted authority: {path}"
    build = _json("deploy/build-manifest.json")
    for path in rows:
        assert path in build["build_inputs"]["tracked_in_canonical_branch_this_sprint"]
        assert f"/app/{path}" in build["post_build_verification_files"]


# --------------------------------------------------------------------------
# World Map zone previews
# --------------------------------------------------------------------------
def test_world_map_previews_dual_closure_is_10_of_10():
    locked = {zone["output_sha256"] for zone in _json(PREVIEW_MANIFEST)["zones"]}
    assert len(locked) == 10
    baked = _baked(_tracked())
    rows = _assert_pack_matches_tracked_bytes(PREVIEW_PACK)
    assert len(rows) == 10
    assert {row["sha256"] for row in rows} == locked
    build = _json("deploy/build-manifest.json")
    for row in rows:
        assert row["path"].startswith(PREVIEW_PREFIX) and row["path"].endswith("_preview_v1.png")
        assert row["path"] in baked, f"{row['path']} has no baked image copy"
        assert f"/app/{row['path']}" in build["post_build_verification_files"]
    # The derivation manifest and alias copies are not public assets.
    assert PREVIEW_MANIFEST not in baked
    assert not any("/aliases/" in path for path in baked)
    assert not any("/aliases/" in row["path"] for row in rows)


# --------------------------------------------------------------------------
# G009 Hero models
# --------------------------------------------------------------------------
def test_every_baked_g009_model_has_exactly_one_static_generation_copy():
    tracked = _tracked()
    baked_models = sorted(
        path for path in _baked(tracked)
        if path.startswith("assets/3d_shop/") and path.endswith(".glb")
    )
    packs = {name: {row["path"]: row for row in _assert_pack_matches_tracked_bytes(name)}
             for name in (MODEL_PACK, COMPANION_PACK, FORMAL9_PACK, BONUS_PACK)}
    hero_models = packs[MODEL_PACK]
    assert len(hero_models) == 47
    assert all(path.endswith(".glb") for path in hero_models)

    membership = {
        path: [name for name, rows in packs.items() if path in rows] for path in baked_models
    }
    assert all(len(owners) == 1 for owners in membership.values()), {
        path: owners for path, owners in membership.items() if len(owners) != 1
    }
    assert len(baked_models) == 47 + 18 + 4 + 2
    # Bonus assets are a separately approved G043 supplemental visual pack;
    # they never increase the canonical formal_69 GLB count or grant ownership.
    assert len(packs[BONUS_PACK]) == 3
    assert sum(path.endswith(".glb") for path in packs[BONUS_PACK]) == 2
    assert sum(path.endswith(".png") for path in packs[BONUS_PACK]) == 1
    assert sum(path.endswith(".glb") for pack in (MODEL_PACK, COMPANION_PACK, FORMAL9_PACK)
               for path in packs[pack]) == 69
    assert set(packs[BONUS_PACK]).isdisjoint(
        set(packs[MODEL_PACK]) | set(packs[COMPANION_PACK]) | set(packs[FORMAL9_PACK])
    )

    future30 = {
        model["runtime_glb"]: model["runtime_sha256"]
        for model in _json("schemas/future30_c005_real_asset_runtime_mapping_manifest.json")["visual_models"]
    }
    assert len(future30) == 33
    for path, accepted in future30.items():
        assert hero_models[path]["sha256"] == accepted, path
    prerequisite = json.dumps(_json("schemas/g009_d007_runtime_prerequisite_v1.json"))
    for path in hero_models:
        if path not in future30:
            assert path in prerequisite, f"{path} is not a declared D007 runtime asset"

    # Retired-asset refusal: nothing the Formal9 replacement retired is staged.
    retired = json.dumps(_json("deploy/g009-formal9-replacement-asset-rollback-inventory.json"))
    assert not [path for path in hero_models if path in retired]


def test_static_generation_has_no_duplicate_or_untracked_governed_path():
    tracked = _tracked()
    governed = _static_governed()
    missing = sorted(path for path in governed if path not in tracked)
    assert missing == [], f"governed static paths missing from the source tree: {missing[:5]}"
    for path, row in governed.items():
        if "sha256" in row:
            assert row["size"] > 0
            assert len(row["sha256"]) == 64


# --------------------------------------------------------------------------
# Source selection: which copy does the existing resolver actually serve?
# --------------------------------------------------------------------------
REPRESENTATIVES = (
    ("hero_css", "/" + HERO_CSS, HERO_CSS, "text"),
    ("hero_js", "/" + HERO_JS, HERO_JS, "text"),
    ("derived84", "/assets/world-map-identity/avatars/avatar_FUTURE30_MODEL_A1_RED.png",
     "assets/world-map-identity/avatars/avatar_FUTURE30_MODEL_A1_RED.png", "binary"),
    ("world_map_preview", "/" + PREVIEW_PREFIX + "01_zone_01_preview_v1.png",
     PREVIEW_PREFIX + "01_zone_01_preview_v1.png", "binary"),
    ("g009_model", "/assets/3d_shop/p048/hero/a1_basic_adventurer.glb",
     "assets/3d_shop/p048/hero/a1_basic_adventurer.glb", "binary"),
)


def _fixture_bytes(kind: str, relative: str, origin: str) -> bytes:
    """Test-only content.  Text assets keep the accepted bytes and add a
    harmless marker comment; binary assets use a small standalone fixture so
    no accepted asset is ever altered."""
    if kind == "text":
        accepted = (REPO_ROOT / relative).read_bytes()
        if origin == "baked":
            return accepted
        return accepted + b"\n/* test-only external-static marker */\n"
    return f"TEST-ONLY-{origin.upper()}-FIXTURE:{relative}".encode("utf-8")


@pytest.fixture()
def dual_roots(tmp_path, monkeypatch):
    baked_root = tmp_path / "baked-image-root"
    static_root = tmp_path / "external-static-generation"
    for _name, _url, relative, kind in REPRESENTATIVES:
        for root, origin in ((baked_root, "baked"), (static_root, "external")):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_fixture_bytes(kind, relative, origin))
    monkeypatch.setattr(app_module, "_BASE", str(baked_root))
    monkeypatch.setenv(app_module.LIVE_STATIC_ROOT_ENV_VAR, str(static_root))
    return baked_root, static_root


@pytest.mark.parametrize("name,url,relative,kind", REPRESENTATIVES)
def test_mode_a_live_static_copy_is_selected_when_both_copies_exist(
    dual_roots, name, url, relative, kind
):
    baked_root, static_root = dual_roots
    baked_bytes = (baked_root / relative).read_bytes()
    external_bytes = (static_root / relative).read_bytes()
    assert baked_bytes != external_bytes  # the two copies are distinguishable

    response = app_module.app.test_client().get(url)
    assert response.status_code == 200
    assert response.data == external_bytes, f"{name}: live-static copy was not preferred"
    assert response.data != baked_bytes
    for header in DIAGNOSTIC_HEADERS:
        assert header not in response.headers


@pytest.mark.parametrize("name,url,relative,kind", REPRESENTATIVES)
def test_mode_b_baked_copy_is_selected_when_external_asset_is_missing(
    dual_roots, name, url, relative, kind
):
    baked_root, static_root = dual_roots
    baked_bytes = (baked_root / relative).read_bytes()
    (static_root / relative).unlink()  # only this external test asset is unavailable

    response = app_module.app.test_client().get(url)
    assert response.status_code == 200
    assert response.data == baked_bytes, f"{name}: baked fallback was not used"


@pytest.mark.parametrize("name,url,relative,kind", REPRESENTATIVES)
def test_mode_b_baked_copy_is_selected_when_static_mount_is_absent(
    dual_roots, monkeypatch, name, url, relative, kind
):
    baked_root, _static_root = dual_roots
    monkeypatch.delenv(app_module.LIVE_STATIC_ROOT_ENV_VAR, raising=False)

    response = app_module.app.test_client().get(url)
    assert response.status_code == 200
    assert response.data == (baked_root / relative).read_bytes()


def test_selection_fixtures_never_touch_governed_bytes(dual_roots):
    baked_root, static_root = dual_roots
    for root in (baked_root, static_root):
        assert REPO_ROOT not in root.parents and root != REPO_ROOT
    for _name, _url, relative, _kind in REPRESENTATIVES:
        governed = _static_governed().get(relative) or {}
        if "sha256" in governed:
            assert _sha256(relative) == governed["sha256"]


# --------------------------------------------------------------------------
# Delivery safety
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    (
        "/assets/../app.py",
        "/assets/%2e%2e/app.py",
        "/assets/world-map-identity/../../app.py",
        "/assets/.hidden/secret.png",
        "/css/../app.py",
        "/css/app.py",
        "/css/g009_hero_hub_batch_a.css/../../app.py",
        "/js/app.py",
        "/js/..%2fapp.py",
        "/js/g009_hero_hub_batch_a.css",
    ),
)
def test_traversal_and_unauthorized_static_paths_are_not_served(dual_roots, url):
    _baked_root, static_root = dual_roots
    (static_root / "app.py").write_text("SECRET = 'external'", encoding="utf-8")
    (static_root / "css").mkdir(exist_ok=True)
    (static_root / "css" / "app.py").write_text("SECRET = 'external-css'", encoding="utf-8")
    (static_root / "js" / "app.py").write_text("SECRET = 'external-js'", encoding="utf-8")
    hidden = static_root / "assets" / ".hidden"
    hidden.mkdir(parents=True, exist_ok=True)
    (hidden / "secret.png").write_bytes(b"hidden")

    response = app_module.app.test_client().get(url)
    assert b"SECRET" not in response.data and response.data != b"hidden"
    assert response.status_code in (301, 302, 308, 400, 404)


def test_one_resolver_and_no_production_source_diagnostics():
    source = (REPO_ROOT / "app.py").read_text(encoding="utf-8")
    assert source.count("def _serve_live_static_or_baked_subpath(") == 1
    assert source.count("def _serve_live_static_or_baked(") == 1
    assert source.count("def _resolve_live_static_path(") == 1
    for header in DIAGNOSTIC_HEADERS:
        assert header not in source
    route = source.split("def serve_g009_hero_hub_batch_a_css():", 1)[1].split("@app.route", 1)[0]
    assert "_serve_live_static_or_baked_subpath(" in route
    assert "send_file(" not in route and "send_from_directory(" not in route
