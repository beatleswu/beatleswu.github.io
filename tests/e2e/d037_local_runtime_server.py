"""Disposable local server for D037 active-Spirit browser proof.

The browser journey uses the real /api/pet/status and /api/pet/switch routes,
the real Hero/Adventure pages, and an in-memory SQLite database only.
"""

from __future__ import annotations

import sys
from pathlib import Path

from flask import redirect, request, session
from werkzeug.serving import make_server


TESTS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TESTS_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import test_d030_r2_spirit_adventure_milestone_wiring as d030  # noqa: E402


d030._install_app_import_stubs()
import app as app_module  # noqa: E402


USER_ID = 37037
conn = d030._new_db()
for column in (
    "last_pet_at",
    "last_train_at",
    "daily_key",
    "daily_bond",
    "daily_train_xp",
):
    definition = "TEXT" if column in {"last_pet_at", "last_train_at", "daily_key"} else "INTEGER NOT NULL DEFAULT 0"
    conn.execute(f"ALTER TABLE user_pets ADD COLUMN {column} {definition}")
conn.execute(
    "INSERT INTO pet_collection(user_id,pet_key,nickname,selected_at,level) VALUES(?,?,?,?,?)",
    (USER_ID, "ink_drop_kelpie", "Ink Drop", "2026-08-28T00:00:00", 1),
)
conn.execute(
    "INSERT INTO pet_collection(user_id,pet_key,nickname,selected_at,level) VALUES(?,?,?,?,?)",
    (USER_ID, "starpath_antlerling", "Starpath", "2026-08-28T00:00:01", 1),
)
conn.execute(
    "INSERT INTO user_pets(user_id,pet_key,nickname,selected_at,updated_at) VALUES(?,?,?,?,?)",
    (USER_ID, "ink_drop_kelpie", "Ink Drop", "2026-08-28T00:00:00", "2026-08-28T00:00:00"),
)
conn.commit()


class _DbContext:
    def __init__(self):
        self._conn = conn

    def execute(self, sql, params=None):
        return self._conn.execute(sql, params or ())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.rollback() if exc_type else self.commit()
        return False


app_module.get_db = lambda: _DbContext()
app_module._adventure_state = lambda _uid: [{
    "key": "k11_15", "seen": 50, "unlocked": True, "cleared": False,
}]
app_module._adventure_map_state = lambda *args, **kwargs: {}
app_module.app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)


@app_module.app.route("/__d037_login")
def d037_login():
    session["user_id"] = USER_ID
    target = request.args.get("next", "/__d037_control")
    if target not in {"/", "/hero?tab=pet", "/__d037_control"}:
        target = "/__d037_control"
    return redirect(target)


@app_module.app.route("/__d037_control")
def d037_control():
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>D037 active Spirit selection</title></head><body>
<main><h1>D037 active Spirit selection</h1>
<button id="d037-switch-b" type="button">Select Starpath Antlerling</button>
<button id="d037-switch-a" type="button">Select Ink Drop Kelpie</button>
<p id="d037-state">READY</p><pre id="d037-response"></pre></main>
<script>
const state = document.getElementById('d037-state');
const responseBox = document.getElementById('d037-response');
async function refresh() {
  const response = await fetch('/api/pet/status', {credentials:'include', cache:'no-store'});
  const data = await response.json();
  state.textContent = 'ACTIVE:' + (data.spirit_projection?.active_spirit_id || 'NONE');
  responseBox.textContent = JSON.stringify(data.spirit_projection, null, 2);
  return data;
}
async function selectSpirit(key, operationId) {
  const before = await refresh();
  const response = await fetch('/api/pet/switch', {
    method:'POST', credentials:'include', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({pet_key:key, operation_id:operationId,
      expected_active_spirit_id:before.spirit_projection.active_spirit_id}),
  });
  const data = await response.json();
  responseBox.textContent = JSON.stringify(data, null, 2);
  state.textContent = data.ok ? 'SELECTION_COMMITTED' : 'SELECTION_REJECTED';
  if (data.ok && typeof BroadcastChannel === 'function') {
    const channel = new BroadcastChannel('go-odyssey-spirit-sync-v1');
    channel.postMessage({type:'active-spirit-selection-complete'});
    channel.close();
  }
  await refresh();
}
document.getElementById('d037-switch-b').addEventListener('click', () =>
  selectSpirit('starpath_antlerling', 'd037-browser-switch-b'));
document.getElementById('d037-switch-a').addEventListener('click', () =>
  selectSpirit('ink_drop_kelpie', 'd037-browser-switch-a'));
refresh();
</script></body></html>"""


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5082)
    args = parser.parse_args()
    server = make_server("127.0.0.1", args.port, app_module.app)
    try:
        server.serve_forever()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
