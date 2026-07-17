"""E9.1A2-FIX1 — Runtime Asset Packaging Contract.

Root cause of the bug this file guards against: app.py's narrow
/js/e9/, /css/e9/, /components/adventure/ static routes were added and
tested in E9.1A2, but the Dockerfile never COPYed those directories into
the production image. Every existing local test used Flask's
test_client(), which reads files from the host working tree -- so all
those tests passed while the real, built production image 404'd on every
single E9 asset request. This file has three tiers, matching that gap:

  1. Fast, source-level Dockerfile/manifest checks (always run, no Docker).
  2. Built-image filesystem verification -- must inspect the actual built
     image, not the host tree, or it proves nothing.
  3. Built-container HTTP route verification -- must run a real container
     and issue real HTTP requests, or it doesn't prove the Flask routes
     actually resolve inside that image.

Tiers 2/3 require a real Docker image tag. Set E9_PACKAGING_TEST_IMAGE to
an already-built `go-odyssey-app:<tag>` (or any image built from this
Dockerfile) to run them for real; without it they are SKIPPED with an
explicit reason -- never silently reported as passing.
"""
import hashlib
import json
import os
import pathlib
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "Dockerfile"
BUILD_MANIFEST = REPO_ROOT / "deploy" / "build-manifest.json"
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build-production-image.ps1"

E9_JS_FILES = [
    "bottom_dock.js", "component_loader.js", "feature_flags.js",
    "left_nav.js", "right_cards.js", "shell.js", "top_hud.js", "world_stage.js",
    "adapters/player_state.js", "adapters/adventure_state.js", "adapters/activity_state.js",
]
E9_CSS_FILES = [
    "cards.css", "navigation.css", "rwd.css", "shell.css", "top_hud.css", "world_stage.css",
]
E9_COMPONENT_FILES = [
    "bottom_dock.html", "left_nav.html", "right_cards.html", "top_hud.html", "world_stage.html",
]


def _read(path):
    assert path.is_file(), f"expected file to exist: {path}"
    return path.read_text(encoding="utf-8")


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Tier 1 -- fast, source-level Dockerfile/manifest checks
# ---------------------------------------------------------------------------

def test_dockerfile_copies_e9_js_directory():
    content = _read(DOCKERFILE)
    assert re.search(r"COPY\s+js/e9\s+\./js/e9", content), (
        "Dockerfile must COPY js/e9 into the image -- this is the exact gap "
        "that caused every /js/e9/*.js request to 404 in production"
    )


def test_dockerfile_copies_e9_css_directory():
    content = _read(DOCKERFILE)
    assert re.search(r"COPY\s+css/e9\s+\./css/e9", content)


def test_dockerfile_copies_e9_components_directory():
    content = _read(DOCKERFILE)
    assert re.search(r"COPY\s+components/adventure\s+\./components/adventure", content)


def test_dockerfile_e9_copies_appear_before_entrypoint():
    # Sanity: the new COPY lines must be real build steps, not just comment
    # text -- confirm they sit before the ENTRYPOINT/CMD lines.
    content = _read(DOCKERFILE)
    entrypoint_pos = content.index("ENTRYPOINT")
    js_copy_pos = content.index("COPY js/e9")
    css_copy_pos = content.index("COPY css/e9")
    components_copy_pos = content.index("COPY components/adventure")
    assert js_copy_pos < entrypoint_pos
    assert css_copy_pos < entrypoint_pos
    assert components_copy_pos < entrypoint_pos


def test_dockerfile_does_not_regress_to_broad_wildcard_copy():
    content = _read(DOCKERFILE)
    # This fix must not be implemented as a workaround that widens the
    # build context (e.g. `COPY . .`) -- that would silently bake in
    # secret_key.txt, .db files, backups/, etc. that are explicitly
    # excluded elsewhere in this same Dockerfile.
    assert not re.search(r"COPY\s+\.\s+\.", content), (
        "must not introduce a broad `COPY . .` to fix this -- explicit, "
        "narrow COPY targets only"
    )
    assert "COPY js/e9 ./js/e9" in content
    assert "COPY css/e9 ./css/e9" in content
    assert "COPY components/adventure ./components/adventure" in content


def test_build_manifest_tracks_all_e9_asset_files():
    manifest = json.loads(BUILD_MANIFEST.read_text(encoding="utf-8"))
    tracked = set(manifest["build_inputs"]["tracked_in_canonical_branch_this_sprint"])
    for f in E9_JS_FILES:
        assert f"js/e9/{f}" in tracked, f"js/e9/{f} missing from build-manifest.json tracked list"
    for f in E9_CSS_FILES:
        assert f"css/e9/{f}" in tracked, f"css/e9/{f} missing from build-manifest.json tracked list"
    for f in E9_COMPONENT_FILES:
        assert f"components/adventure/{f}" in tracked, (
            f"components/adventure/{f} missing from build-manifest.json tracked list"
        )


def test_build_manifest_post_build_verification_includes_e9_assets():
    manifest = json.loads(BUILD_MANIFEST.read_text(encoding="utf-8"))
    verify_list = set(manifest["post_build_verification_files"])
    for f in E9_JS_FILES:
        assert f"/app/js/e9/{f}" in verify_list
    for f in E9_CSS_FILES:
        assert f"/app/css/e9/{f}" in verify_list
    for f in E9_COMPONENT_FILES:
        assert f"/app/components/adventure/{f}" in verify_list


def test_all_e9_source_files_actually_exist_on_disk():
    # Guards the manifest/Dockerfile lists themselves against typos --
    # every path they reference must be real.
    for f in E9_JS_FILES:
        assert (REPO_ROOT / "js" / "e9" / f).is_file()
    for f in E9_CSS_FILES:
        assert (REPO_ROOT / "css" / "e9" / f).is_file()
    for f in E9_COMPONENT_FILES:
        assert (REPO_ROOT / "components" / "adventure" / f).is_file()


def test_build_script_platform_contract_unchanged_by_this_fix():
    # Preserve the ARM64/buildx contract established by RELEASE-TOOLING-HOTFIX-02
    # while allowing the invocation to use the stderr-safe native helper.
    content = _read(BUILD_SCRIPT)
    assert "'buildx', 'build'" in content
    assert "'--platform', $Platform" in content
    assert "--load" in content
    assert "'linux/arm64'" in content


# ---------------------------------------------------------------------------
# Tier 2/3 -- built-image filesystem + built-container HTTP verification.
# Require a real image. Skip (with an explicit reason) if none is provided --
# never silently pass.
# ---------------------------------------------------------------------------

def _docker_available():
    try:
        subprocess.run(["docker", "version"], capture_output=True, check=True, timeout=15)
        return True
    except Exception:
        return False


IMAGE_TAG = os.environ.get("E9_PACKAGING_TEST_IMAGE")
SKIP_REASON = (
    "E9_PACKAGING_TEST_IMAGE not set -- built-image/built-container tests "
    "require a real image tag (e.g. go-odyssey-app:<sha>) built from this "
    "Dockerfile. Skipped, not passed -- do not treat this as a verified "
    "packaging contract without setting this env var and re-running."
)

pytestmark_built = pytest.mark.skipif(not IMAGE_TAG, reason=SKIP_REASON)


def _run_in_image(image_tag, shell_cmd, timeout=30):
    """Run a throwaway container executing shell_cmd, return (rc, stdout, stderr)."""
    result = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "sh", image_tag, "-c", shell_cmd],
        capture_output=True, text=True, timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


@pytestmark_built
class TestBuiltImageFilesystem:
    def test_docker_is_actually_available(self):
        assert _docker_available(), "docker command unavailable even though E9_PACKAGING_TEST_IMAGE was set"

    @pytest.mark.parametrize("relpath", [f"js/e9/{f}" for f in E9_JS_FILES]
                             + [f"css/e9/{f}" for f in E9_CSS_FILES]
                             + [f"components/adventure/{f}" for f in E9_COMPONENT_FILES])
    def test_file_exists_and_is_non_empty_inside_built_image(self, relpath):
        rc, out, err = _run_in_image(
            IMAGE_TAG, f"test -s /app/{relpath} && echo PRESENT || echo MISSING"
        )
        assert rc == 0, f"docker run failed for {relpath}: {err}"
        assert "PRESENT" in out, f"/app/{relpath} missing or empty inside {IMAGE_TAG}: {out} {err}"

    @pytest.mark.parametrize("relpath", [f"js/e9/{f}" for f in E9_JS_FILES]
                             + [f"css/e9/{f}" for f in E9_CSS_FILES]
                             + [f"components/adventure/{f}" for f in E9_COMPONENT_FILES])
    def test_file_content_matches_source_tree_sha256(self, relpath):
        rc, out, err = _run_in_image(IMAGE_TAG, f"sha256sum /app/{relpath}")
        assert rc == 0, f"sha256sum failed for {relpath} in {IMAGE_TAG}: {err}"
        container_sha = out.strip().split()[0]
        local_sha = _sha256_file(REPO_ROOT / relpath)
        assert container_sha == local_sha, (
            f"{relpath}: container content ({container_sha}) does not match "
            f"source tree content ({local_sha})"
        )


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _http_get(url, timeout=10):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except (urllib.error.URLError, ConnectionError, OSError):
        # Includes http.client.RemoteDisconnected -- a container that's
        # still finishing its bind, not a route-level 404.
        return None, b""


@pytestmark_built
class TestBuiltContainerHttpRoutes:
    """Starts a real, throwaway container from IMAGE_TAG and issues real HTTP
    requests against it. Uses an entrypoint override that imports app.py's
    Flask `app` object directly and calls app.run() -- this exercises the
    exact same route registrations as production, but skips the
    `if __name__ == '__main__': init_db()` guard (see app.py), which would
    otherwise require a reachable Postgres just to serve a static file."""

    container_name = "e9_packaging_http_test"

    @classmethod
    def setup_class(cls):
        cls.port = _free_port()
        subprocess.run(["docker", "rm", "-f", cls.container_name], capture_output=True)
        cmd = [
            "docker", "run", "-d", "--rm",
            "--name", cls.container_name,
            "-p", f"{cls.port}:8080",
            "--entrypoint", "python",
            IMAGE_TAG,
            "-c", "from app import app; app.run(host='0.0.0.0', port=8080)",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, f"failed to start test container: {result.stderr}"

        base = f"http://127.0.0.1:{cls.port}"
        time.sleep(2)  # let the Flask dev server finish binding before the first attempt
        deadline = time.time() + 30
        ready = False
        while time.time() < deadline:
            status, _ = _http_get(f"{base}/js/e9/feature_flags.js", timeout=3)
            if status is not None:
                ready = True
                break
            time.sleep(1)
        if not ready:
            logs = subprocess.run(["docker", "logs", cls.container_name], capture_output=True, text=True)
            subprocess.run(["docker", "rm", "-f", cls.container_name], capture_output=True)
            pytest.fail(f"container never became reachable on port {cls.port}. Logs:\n{logs.stdout}\n{logs.stderr}")
        cls.base = base

    @classmethod
    def teardown_class(cls):
        subprocess.run(["docker", "rm", "-f", cls.container_name], capture_output=True)

    @pytest.mark.parametrize("relpath", [f"js/e9/{f}" for f in E9_JS_FILES])
    def test_e9_js_route_200(self, relpath):
        status, body = _http_get(f"{self.base}/{relpath}")
        assert status == 200, f"{relpath} returned {status}, expected 200"
        assert len(body) > 0

    @pytest.mark.parametrize("relpath", [f"css/e9/{f}" for f in E9_CSS_FILES])
    def test_e9_css_route_200(self, relpath):
        status, body = _http_get(f"{self.base}/{relpath}")
        assert status == 200, f"{relpath} returned {status}, expected 200"
        assert len(body) > 0

    @pytest.mark.parametrize("relpath", [f"components/adventure/{f}" for f in E9_COMPONENT_FILES])
    def test_e9_component_route_200(self, relpath):
        status, body = _http_get(f"{self.base}/{relpath}")
        assert status == 200, f"{relpath} returned {status}, expected 200"
        assert len(body) > 0

    def test_content_matches_source_over_http(self):
        status, body = _http_get(f"{self.base}/js/e9/shell.js")
        assert status == 200
        local = (REPO_ROOT / "js" / "e9" / "shell.js").read_bytes()
        assert body == local

    @pytest.mark.parametrize("relpath", [
        "js/e9/does_not_exist.js",
        "js/e9/feature_flags.css",
        "css/e9/shell.js",
        "components/adventure/top_hud.js",
    ])
    def test_missing_or_wrong_extension_returns_404(self, relpath):
        status, _ = _http_get(f"{self.base}/{relpath}")
        assert status == 404, f"{relpath} returned {status}, expected 404"

    @pytest.mark.parametrize("relpath", [
        "js/e9/../app.py",
        "js/e9/../../app.py",
        "js/e9/%2e%2e/app.py",
        "css/e9/../../secret_key.txt",
        "components/adventure/../../app.py",
    ])
    def test_traversal_paths_never_return_200(self, relpath):
        status, _ = _http_get(f"{self.base}/{relpath}")
        assert status != 200
        assert status in (301, 302, 404)
