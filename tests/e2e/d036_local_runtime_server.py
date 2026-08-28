"""Disposable local Flask server for the D036 browser journey proof.

This harness uses the real D035 boss-finish route and the real static pages.
It creates only an in-memory SQLite database and a one-shot login/attempt
fixture; it never contacts a production service or database.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

from flask import redirect, session
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


USER_ID = 36036
QUESTION_IDS = list(range(360360, 360380))
ATTEMPT_ID = "d036-browser-first-clear"
conn = d030._new_db()
prepared = False


def _get_db():
    return d030._DbContext(conn)


def _adventure_state(_uid):
    return [{
        "key": "k11_15",
        "seen": 50,
        "unlocked": True,
        "cleared": False,
    }]


app_module.get_db = _get_db
app_module._adventure_state = _adventure_state
app_module._adventure_map_state = lambda *args, **kwargs: {}
app_module.app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)


@app_module.app.route("/__d036_login")
def d036_login():
    global prepared
    session["user_id"] = USER_ID
    if not prepared:
        started_at = (dt.datetime.now() - dt.timedelta(minutes=5)).isoformat()
        session["adventure_boss_exam"] = {
            "zone_key": "k11_15",
            "question_ids": QUESTION_IDS,
            "started_at": started_at,
            "attempt_id": ATTEMPT_ID,
        }
        d030._seed_pass(conn, USER_ID, ATTEMPT_ID, QUESTION_IDS, started_at)
        prepared = True
    return redirect("/")


@app_module.app.route("/__d036_control")
def d036_control():
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>D036 local runtime journey</title>
  <link rel="stylesheet" href="/css/e9/adventure_spirit_unlock.css?v=20260828d036">
</head>
<body>
  <main>
    <h1>D036 local server-backed journey</h1>
    <button id="d036-finish" type="button">Finish eligible boss</button>
    <p id="d036-state">READY</p>
    <pre id="d036-response"></pre>
  </main>
  <script src="/js/e9/adventure_spirit_unlock_presentation.js?v=20260828d036r2"></script>
  <script>
    document.getElementById('d036-finish').addEventListener('click', async () => {
      const response = await fetch('/api/adventure/boss/finish', {
        credentials: 'include',
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: '{}',
      });
      const data = await response.json();
      document.getElementById('d036-response').textContent = JSON.stringify(data, null, 2);
      document.getElementById('d036-state').textContent = data.ok ? 'SERVER_RESPONSE_RECEIVED' : 'SERVER_RESPONSE_FAILED';
      if (data.ok && window.AdventureSpiritUnlockPresentation) {
        window.AdventureSpiritUnlockPresentation.present(data.adventure_spirit_unlock_results);
      }
    });
    window.addEventListener('adventure-spirit-unlock-complete', () => {
      document.getElementById('d036-state').textContent = 'PRESENTATION_COMPLETED';
    });
  </script>
</body>
</html>"""


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5081)
    args = parser.parse_args()
    server = make_server("127.0.0.1", args.port, app_module.app)
    try:
        server.serve_forever()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
