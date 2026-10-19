"""P1 true server-judged map answer -> XP -> Hero -> Adventure, native PG.

All requests traverse real Flask routes, battle persistence, SGF judge and
progression settlement. Only the question catalog is replaced with one
deterministic, synthetic (valid SGF) fixture. No live account, internet or
production DB. This does NOT assert human iPad UAT or a boss clear.
"""
from __future__ import annotations

import json
import os
import pytest

from test_20261019_monthly_postgres import (  # noqa: F401
    local_postgres,
    runtime as native_runtime,
)
from test_20261019_hero_xp_adventure_native_pg import _check_live_hero_renderer

QUESTION = {
    "id": 710019,
    "topic": "1圍棋新手村",
    "stage": "LV1",
    "rank": "30k",
    "source": "isolated/adventure-answer-level-journey.sgf",
    "content": "(;SZ[19];B[dd];W[ee])",
    "accepted_moves": [{"x": 3, "y": 3}],
    "monster_hp": 40,
    "monster_atk": 6,
    "enabled": True,
}
ZONE = "k26_30"
UID = 710019
PROTOCOL = {"X-Map-Battle-Client-Protocol": "v1"}


def get_json(client, route):
    response = client.get(route)
    assert response.status_code == 200, (route, response.status_code, response.get_json())
    return response.get_json()


@pytest.fixture
def journey(native_runtime, monkeypatch):
    app = native_runtime
    # This mode applies exclusively to the new disposable native PG fixture
    # and the local Flask test process. No global dispatch/repair or live flag.
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE", "global")
    monkeypatch.setattr(app, "_load_questions", lambda: [dict(QUESTION)])
    with app.get_db() as conn:
        conn.execute(
            """INSERT INTO users
               (id,username,nickname,password_hash,is_admin,plan,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (UID, "disposable-p1-map", "P1 map journey", "never-used", 0,
             "free", "2026-10-19T00:00:00"),
        )
        conn.execute(
            "INSERT INTO user_stats(user_id,coins,xp,rank_level,rank_xp,"
            "player_hp,player_max_hp) VALUES(?,0,119,'LV1',119,60,60)",
            (UID,),
        )
        conn.execute(
            "INSERT INTO player_appearance(user_id,character_key) "
            "VALUES(?,'apprentice')", (UID,),
        )
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = UID
        session["username"] = "disposable-p1-map"
    return app, client


def answer_payload(issued, moves):
    return {
        "battle_id": issued["battle_id"],
        "attempt_id": issued["attempt_id"],
        "submission_nonce": issued["submission_nonce"],
        "battle_revision": issued["battle"]["battle_revision"],
        "question_revision": issued["question_revision"],
        "player_color": issued["player_color"],
        "transform_id": issued["transform_id"],
        "transform_version": issued["transform_version"],
        "moves": moves,
    }


def test_actual_adventure_answer_levels_up_and_updates_map_without_double_credit(journey):
    app, client = journey
    before = {
        "hero": get_json(client, "/api/player/presentation"),
        "xp": get_json(client, "/api/xp/status"),
        "profile": get_json(client, "/api/skills/profile"),
        "map": get_json(client, "/api/adventure/bootstrap"),
    }
    assert before["hero"]["progression"]["xp"] == 119
    assert before["xp"]["lv"] == 1
    assert _check_live_hero_renderer(before["hero"], before["profile"])["xp_bar_percent"] == 99
    beginning = next(z for z in before["map"]["zones"] if z["key"] == ZONE)
    assert beginning["unlocked"] and not beginning["cleared"]

    created = client.post(
        "/api/adventure/map-battles/v1/attempts",
        json={"zone_key": ZONE, "question_id": QUESTION["id"]},
        headers=PROTOCOL,
    )
    assert created.status_code == 200, created.get_json()
    issued = created.get_json()
    assert issued["ok"] is True and issued["question_id"] == QUESTION["id"]
    assert issued["attempt_id"] and issued["submission_nonce"]

    correct = answer_payload(issued, [{"x": 3, "y": 3}])
    answered = client.post(
        "/api/adventure/map-battles/v1/answers",
        json=correct, headers=PROTOCOL,
    )
    assert answered.status_code == 200, answered.get_json()
    settled = answered.get_json()
    assert settled["result"] == "CORRECT"
    assert settled["progression"]["status"] == "applied"
    assert settled["accepted"] is True and settled["duplicate"] is False
    assert settled["submission_id"]

    after = {
        "hero": get_json(client, "/api/player/presentation"),
        "xp": get_json(client, "/api/xp/status"),
        "profile": get_json(client, "/api/skills/profile"),
        "map": get_json(client, "/api/adventure/bootstrap"),
    }
    gained = after["xp"]["xp"] - before["xp"]["xp"]
    assert gained > 0, "server-judged real answer must credit XP"
    assert after["xp"]["xp"] == after["hero"]["progression"]["xp"]
    assert after["xp"]["lv"] == after["hero"]["progression"]["level"]
    assert after["xp"]["rank_xp"] == after["hero"]["progression"]["rank_xp"]
    assert after["xp"]["lv"] >= 2, "real answer must cross an XP threshold"
    assert after["profile"]["total_xp"] == after["xp"]["xp"]
    assert after["profile"]["lv_xp"] == after["xp"]["rank_xp"]
    display = _check_live_hero_renderer(after["hero"], after["profile"])
    assert display["level"] >= 2
    assert display["xp_bar_percent"] < 100
    zone_after = next(z for z in after["map"]["zones"] if z["key"] == ZONE)
    assert not zone_after["cleared"], "one ordinary question is not a boss clear"
    assert zone_after != beginning, "adventure progress should move after a settled answer"

    with app.get_db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM review_log "
            "WHERE user_id=? AND source_context LIKE ?",
            (UID, "mbv1:%"),
        ).fetchone()["n"]
        assert int(count) == 1
        row = conn.execute(
            "SELECT xp,rank_level,rank_xp FROM user_stats WHERE user_id=?",
            (UID,),
        ).fetchone()
        assert row["xp"] == after["xp"]["xp"]

    replay = client.post(
        "/api/adventure/map-battles/v1/answers",
        json=correct, headers=PROTOCOL,
    )
    assert replay.status_code == 200, replay.get_json()
    repeated = replay.get_json()
    assert repeated["duplicate"] is True
    assert repeated["progression"]["status"] == "duplicate"
    assert get_json(client, "/api/xp/status")["xp"] == after["xp"]["xp"]
    with app.get_db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM review_log "
            "WHERE user_id=? AND source_context LIKE ?", (UID, "mbv1:%"),
        ).fetchone()["n"]
    assert int(count) == 1

    new_client = app.app.test_client()
    with new_client.session_transaction() as session:
        session["user_id"] = UID
        session["username"] = "disposable-p1-map"
    relog_hero = get_json(new_client, "/api/player/presentation")
    relog_profile = get_json(new_client, "/api/skills/profile")
    relog_map = get_json(new_client, "/api/adventure/bootstrap")
    assert relog_hero["progression"] == after["hero"]["progression"]
    assert _check_live_hero_renderer(relog_hero, relog_profile)["level"] == display["level"]
    final_zone = next(z for z in relog_map["zones"] if z["key"] == ZONE)
    for key in ("cleared", "unlocked", "correct_count", "stars"):
        assert final_zone.get(key) == zone_after.get(key), key
    print("ACTUAL_MAP_ANSWER_E2E", json.dumps({
        "route": "/api/adventure/map-battles/v1/answers",
        "grade": settled["result"], "xp_before": before["xp"]["xp"],
        "xp_after": after["xp"]["xp"], "level_before": 1,
        "level_after": after["xp"]["lv"], "zone": ZONE,
        "zone_before": {
            "correct_count": beginning.get("correct_count"),
            "seen": beginning.get("seen")},
        "zone_after": {
            "correct_count": zone_after.get("correct_count"),
            "seen": zone_after.get("seen")},
        "duplicate_blocked": True, "new_session_rehydrated": True,
        "production": False,
    }, ensure_ascii=False))


# Browser-level E2E: a local fixture page that clicks through the shipped
# map_battle_v1_adapter.js and real Flask routes, not a mocked fetcher.
# This does not purport to be the actual index.html Adventure UI.
BROWSER_HTML = """<!doctype html>
<html lang="zh-TW"><head><meta charset="utf-8"><title>Isolated Go Odyssey Map Battle</title>
<meta name="viewport" content="width=device-width,initial-scale=1"></head><body>
<h1>Local Adventure API Browser Acceptance</h1>
<div id="stage" role="status">LOCAL_READY</div>
<button type="button" id="enter">進入冒險</button>
<button type="button" id="play">在 D4 下棋</button>
<button type="button" id="retry">重送相同答案</button>
<div id="attempt"></div><div id="result"></div><div id="level"></div>
<div id="xp"></div><div id="zone"></div>
<script src="/__p1_map_battle_adapter.js"></script>
<script>
'use strict';
let state, originalState;
const $ = (id) => document.getElementById(id);
async function get(path) {
  const r = await fetch(path,{credentials:'include',cache:'no-store'});
  if(!r.ok) throw new Error('read '+path+':'+r.status);
  return r.json();
}
async function renderServerTruth() {
  const [xp,hero,map] = await Promise.all([
    get('/api/xp/status'),get('/api/player/presentation'),
    get('/api/adventure/bootstrap')
  ]);
  if (xp.xp !== hero.progression.xp || xp.lv !== hero.progression.level ||
      xp.rank_xp !== hero.progression.rank_xp)
    throw new Error('XP/hero projections disagreed');
  const z = map.zones.find(x=>x.key==='k26_30');
  if(!z) throw new Error('canonical map zone unavailable');
  $('level').textContent='LV'+xp.lv;
  $('xp').textContent=xp.xp+' XP';
  $('zone').textContent=z.key+' correct='+z.correct_count;
}
async function stage(fn){
  try { await fn() }catch(error){ $('stage').textContent='ERROR';
    $('result').textContent=error.message||String(error); }
}
$('enter').addEventListener('click',()=>stage(async()=>{
  state=await window.MapBattleV1.legacy.prepare({
    zoneKey:'k26_30',questionId:710019
  });
  originalState={...state};
  $('attempt').textContent='battle='+state.battleId;
  $('stage').textContent='ATTEMPT_ISSUED';
}));
$('play').addEventListener('click',()=>stage(async()=>{
  if(!state||!originalState) throw new Error('no server-issued attempt');
  const response=await window.MapBattleV1.legacy.submit(state,[{x:3,y:3}]);
  if(response.result!=='CORRECT'||response.progression?.status!=='applied')
    throw new Error('settlement not correct/credited');
  $('result').textContent=response.result;
  await renderServerTruth();
  sessionStorage.setItem('p1_map_journey_answered','yes');
  $('stage').textContent='ANSWER_CORRECT';
}));
$('retry').addEventListener('click',()=>stage(async()=>{
  if(!originalState) throw new Error('no original nonce');
  const response=await window.MapBattleV1.legacy.retry(originalState,[{x:3,y:3}]);
  if(response.duplicate!==true||response.progression?.status!=='duplicate')
    throw new Error('server failed to identify duplicate');
  await renderServerTruth();
  $('stage').textContent='DUPLICATE_IGNORED';
}));
if(sessionStorage.getItem('p1_map_journey_answered')==='yes'){
  stage(async()=>{
    await renderServerTruth();
    $('stage').textContent='RELOADED_PLAYER_STATE';
  });
}
</script></body></html>
"""


def test_actual_shipped_map_adapter_chrome_click_to_real_flask_pg(journey):
    import subprocess
    import threading
    from pathlib import Path
    from werkzeug.serving import make_server

    app, client = journey
    cookie = client.get_cookie("session")
    assert cookie and cookie.value
    actual_js = (Path(__file__).resolve().parents[1] /
                 "js" / "map_battle_v1_adapter.js").read_bytes()

    def local_wsgi(environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path == "/__p1_adventure_browser":
            start_response("200 OK", [("Content-Type","text/html; charset=utf-8"),
                                     ("Cache-Control","no-store")])
            return [BROWSER_HTML.encode("utf-8")]
        if path == "/__p1_map_battle_adapter.js":
            start_response("200 OK", [("Content-Type","application/javascript"),
                                     ("Cache-Control","no-store")])
            return [actual_js]
        return app.app.wsgi_app(environ, start_response)

    server = make_server("127.0.0.1", 0, local_wsgi, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        node = __import__("shutil").which("node")
        assert node, "Node and Chrome are required; do not fake browser PASS"
        runner = (Path(__file__).resolve().parent / "e2e" /
                  "run_20261019_real_map_answer_browser.mjs")
        result = subprocess.run(
            [node, str(runner)],
            input=json.dumps({
                "origin": f"http://127.0.0.1:{server.server_port}",
                "sessionCookie": cookie.value,
            }),
            text=True, capture_output=True, encoding="utf-8", timeout=80,
            cwd=Path(__file__).resolve().parents[1],
        )
        assert result.returncode == 0, result.stderr + result.stdout
        report = json.loads(result.stdout)
        assert report["passed"] == 5
        assert report["product_adventure_view_used"] is False
        assert report["real_iPad"] is False
        with app.get_db() as conn:
            row = conn.execute(
                "SELECT xp,rank_level,rank_xp FROM user_stats WHERE user_id=?",
                (UID,),
            ).fetchone()
            total = conn.execute(
                "SELECT COUNT(*) AS n FROM review_log WHERE user_id=? "
                "AND source_context LIKE ?",(UID, "mbv1:%"),
            ).fetchone()["n"]
        assert row["xp"] == 134
        assert row["rank_level"] == "LV2"
        assert row["rank_xp"] == 14
        assert int(total) == 1
        print("BROWSER_ADAPTER_REAL_PG_E2E",json.dumps(report,ensure_ascii=False))
    finally:
        server.shutdown()
        thread.join(timeout=8)
        server.server_close()


@pytest.mark.parametrize('input_mode', ('desktop_mouse', 'chrome_tablet_touch'))
def test_actual_index_html_wgo_click_judge_xp_level_and_map(journey, input_mode):
    """Real Chrome pointer -> shipped WGo board -> Flask Map answer -> PG -> LV2.

    No route interceptions or synthetic client grades; synthetic question
    catalog remains isolated to the new disposable native database.
    """
    import subprocess
    import threading
    from pathlib import Path
    from werkzeug.serving import make_server

    app, client = journey
    cookie = client.get_cookie("session")
    assert cookie and cookie.value
    server = make_server("127.0.0.1", 0, app.app.wsgi_app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        runner = (Path(__file__).resolve().parent / "e2e" /
                  "run_20261019_real_index_adventure_probe.mjs")
        result = subprocess.run(
            ["node", str(runner)],
            input=json.dumps({
                "origin": f"http://127.0.0.1:{server.server_port}",
                "sessionCookie": cookie.value,
            }),
            text=True, encoding="utf-8", capture_output=True, timeout=65,
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ,
                 'GO_P1_TOUCH_EMULATION': '1' if input_mode == 'chrome_tablet_touch' else '0'},
        )
        assert result.returncode == 0, result.stderr + result.stdout
        info = json.loads(result.stdout)
        print("ACTUAL_INDEX_WGO_JOURNEY", json.dumps(info,ensure_ascii=False))
        assert info["verdict"] == "REAL_INDEX_REAL_WGO_REAL_MAP_ANSWER_PG_PASS"
        assert info["passed"] == 8
        assert info["actual_shipped_index_used"] is True
        assert info["actual_wgo_pointer_event_used"] is True
        assert info['emulated_touch_mode'] == (input_mode == 'chrome_tablet_touch')
        assert info['real_ipad'] is False
        with app.get_db() as conn:
            row = conn.execute(
                "SELECT xp,rank_level,rank_xp FROM user_stats WHERE user_id=?",
                (UID,),
            ).fetchone()
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM review_log "
                "WHERE user_id=? AND source_context LIKE ?",
                (UID, "mbv1:%"),
            ).fetchone()["n"]
        assert row["xp"] == 134 and row["rank_level"] == "LV2"
        assert int(count) == 1
    finally:
        server.shutdown()
        thread.join(timeout=8)
        server.server_close()
