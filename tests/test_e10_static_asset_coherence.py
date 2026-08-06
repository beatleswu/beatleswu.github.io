"""Focused regression tests for the E10 static/service-worker coherence fix."""

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SW = ROOT / "sw.js"


def test_service_worker_update_discovery_headers_remain_non_immutable():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "@app.route('/sw.js')" in app
    assert "Service-Worker-Allowed" in app
    assert "Cache-Control" in app and "no-cache" in app


def test_service_worker_activation_retires_old_go_odyssey_caches_only():
    sw_text = SW.read_text(encoding="utf-8")
    identity = re.search(
        r"const ASSET_IDENTITY\s*=\s*'([^']+)'", sw_text
    ).group(1)
    version = re.search(r"const VERSION\s*=\s*'([^']+)'", sw_text).group(1)
    current_shell = f"cg-shell-{version}-{identity}"
    current_image = f"cg-img-{version}-{identity}"
    old_shell = "cg-shell-v227-e10-canonical-layout-contract-recovery-20260804e10navcache1"
    old_image = "cg-img-v227-e10-canonical-layout-contract-recovery-20260804e10navcache1"

    node_script = f"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync({str(SW)!r}, 'utf8');
const handlers = {{}};
const stores = new Map([
  [{old_shell!r}, new Map()],
  [{old_image!r}, new Map()],
  [{current_shell!r}, new Map()],
  [{current_image!r}, new Map()],
  ['unrelated-application-cache', new Map()],
]);
const caches = {{
  keys: async () => Array.from(stores.keys()),
  delete: async (key) => stores.delete(key),
  open: async (key) => {{
    if (!stores.has(key)) stores.set(key, new Map());
    return {{ match: async (request) => stores.get(key).get(String(request)),
      put: async (request, response) => stores.get(key).set(String(request), response) }};
  }},
}};
const self = {{
  addEventListener: (name, handler) => handlers[name] = handler,
  skipWaiting: async () => {{}},
  clients: {{ claim: async () => {{}} }},
  location: {{ origin: 'https://example.test' }},
}};
vm.runInNewContext(source, {{ self, caches, console, URL, Response: global.Response }});
(async () => {{
  const event = {{ promise: null, waitUntil(promise) {{ this.promise = promise; }} }};
  handlers.activate(event);
  await event.promise;
  console.log(JSON.stringify(Array.from(stores.keys()).sort()));
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
    result = subprocess.run(
        ["node", "-e", node_script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    remaining = set(__import__("json").loads(result.stdout))
    assert old_shell not in remaining
    assert old_image not in remaining
    assert current_shell in remaining
    assert current_image in remaining
    assert "unrelated-application-cache" in remaining
