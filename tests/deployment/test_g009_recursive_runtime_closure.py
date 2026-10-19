"""Guard the complete browser module/package closure of the G009 candidate."""

import json
from pathlib import Path
import re
from urllib.parse import urljoin

import app as app_module


ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINTS = (
    "/js/formal_3d_character_equipment_runtime.js",
    "/js/g008_future30_hero_renderer.js",
    "/js/g009_d_r2_shared_host_bootstrap.js",
    "/js/g009_companion_formal18_bootstrap.mjs",
    "/js/g009_companion_360_viewer.mjs",
)
COMPANION_RUNTIME_PATHS = frozenset({
    "js/companion_formal_18_mapping.js",
    "js/g009_companion_child.mjs",
    "js/g009_companion_formal18_assets.mjs",
    "js/g009_companion_formal18_bootstrap.mjs",
    "js/g009_companion_360_viewer.mjs",
    "assets/3d_shop/p048/companion/formal_18/mapping_manifest.json",
    "assets/3d_shop/p048/companion/formal_18/fatty/stage_i.glb",
    "assets/3d_shop/p048/companion/formal_18/fatty/stage_ii.glb",
    "assets/3d_shop/p048/companion/formal_18/fatty/stage_iii.glb",
    "assets/3d_shop/p048/companion/formal_18/ink_drop_kelpie/stage_i.glb",
    "assets/3d_shop/p048/companion/formal_18/ink_drop_kelpie/stage_ii.glb",
    "assets/3d_shop/p048/companion/formal_18/ink_drop_kelpie/stage_iii.glb",
    "assets/3d_shop/p048/companion/formal_18/obsidian_bastion/stage_i.glb",
    "assets/3d_shop/p048/companion/formal_18/obsidian_bastion/stage_ii.glb",
    "assets/3d_shop/p048/companion/formal_18/obsidian_bastion/stage_iii.glb",
    "assets/3d_shop/p048/companion/formal_18/star_shell_hatchling/stage_i.glb",
    "assets/3d_shop/p048/companion/formal_18/star_shell_hatchling/stage_ii.glb",
    "assets/3d_shop/p048/companion/formal_18/star_shell_hatchling/stage_iii.glb",
    "assets/3d_shop/p048/companion/formal_18/starpath_antlerling/stage_i.glb",
    "assets/3d_shop/p048/companion/formal_18/starpath_antlerling/stage_ii.glb",
    "assets/3d_shop/p048/companion/formal_18/starpath_antlerling/stage_iii.glb",
    "assets/3d_shop/p048/companion/formal_18/whispering_void_kit/stage_i.glb",
    "assets/3d_shop/p048/companion/formal_18/whispering_void_kit/stage_ii.glb",
    "assets/3d_shop/p048/companion/formal_18/whispering_void_kit/stage_iii.glb",
})
THREE_URL = "/assets/3d_shop/p048/vendor/three.module.js"
IMPORT_STATEMENT = re.compile(r"^\s*(?:import|export)\b[\s\S]*?;", re.MULTILINE)
FROM_SPECIFIER = re.compile(r"\bfrom\s+['\"]([^'\"]+)['\"]")
BARE_SPECIFIER = re.compile(r"^\s*import\s+['\"]([^'\"]+)['\"]")


def _module_dependencies(url: str) -> set[str]:
    source = (ROOT / url.lstrip("/")).read_text(encoding="utf-8")
    result = set()
    for match in IMPORT_STATEMENT.finditer(source):
        statement = match.group()
        specifier = FROM_SPECIFIER.search(statement) or BARE_SPECIFIER.search(statement)
        if specifier:
            path = specifier.group(1)
            result.add(THREE_URL if path == "three" else urljoin(url, path))
    return result


def test_recursive_module_graph_is_baked_and_http_reachable():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    copy_sources = {
        source for line in dockerfile.replace("\\\n", " ").splitlines()
        if line.startswith("COPY ") for source in line.split()[1:-1]
    }
    manifest = json.loads((ROOT / "deploy/build-manifest.json").read_text(encoding="utf-8"))
    tracked = set(manifest["build_inputs"]["tracked_in_canonical_branch_this_sprint"])
    verified = set(manifest["post_build_verification_files"])
    client = app_module.app.test_client()
    seen = set()
    pending = list(ENTRYPOINTS)
    while pending:
        url = pending.pop()
        if url in seen:
            continue
        seen.add(url)
        relative = url.lstrip("/")
        assert (ROOT / relative).is_file(), url
        assert (
            relative in copy_sources
            or relative == "js/g008_future30_hero_renderer.js"
            or relative.startswith("assets/3d_shop/p048/companion/formal_18/")
        ), url
        # The established build manifest enumerates G009 application modules;
        # G008 and vendored modules have pre-existing Docker COPY authority.
        if relative.startswith("js/") and relative != "js/g008_future30_hero_renderer.js":
            assert relative in tracked, url
            assert "/app/" + relative in verified, url
        response = client.get(url)
        assert response.status_code == 200, url
        pending.extend(_module_dependencies(url) - seen)
    assert len(seen) == 21  # 18 application modules + three vendored modules.
    assert "/js/g009_shared_hero_attachment_host.js" in seen
    assert COMPANION_RUNTIME_PATHS <= tracked
    assert {"/app/" + path for path in COMPANION_RUNTIME_PATHS} <= verified
