"""Local-only UI fixture with temporary SQLite. Never imports app.py.

Authentication/media/identity/review are visibly synthetic. No players or
canonical questions are loaded, and no production configuration is read.
"""
import json
from pathlib import Path
import sqlite3
import tempfile

from flask import Flask, request

from .integration import install_course_v1
from .service import CourseService, create_temporary_schema


def create_fixture(database):
    import uuid
    catalog=json.loads(Path(__file__).with_name("data").joinpath("catalog.json").read_text(encoding="utf-8"))
    def resolve(alias):
        return {"canonical_id":str(uuid.uuid5(uuid.NAMESPACE_URL,f"FIXTURE/{alias}")),
                "revision":"fixture-r1","enabled":True,"identity_status":"EXACT",
                "katago_status":"APPROVED","katago_revision":"fixture-r1","katago_receipt":"FIXTURE_ONLY"}
    from .adapters import existing_practice_judge
    from map_battle_runtime import question_revision_for
    question={"content":"(;GM[1]FF[4]SZ[9]AB[ba]AW[aa];B[ab])","board_size":9,"player_color":"B"}
    def bound(alias):
        item=resolve(alias);item["revision"]=item["katago_revision"]=question_revision_for(question);return item
    service=CourseService(database,catalog,resolve=bound,entitled=lambda *a:True,
        judge=existing_practice_judge(lambda _:question),video_evidence=lambda *a:True,enabled=True)
    app=Flask(__name__)
    app.config.update(G066_COURSE_RUNTIME_ENABLED=True,G066_COURSE_OWNER_APPROVED=True,
        G066_COURSE_ADAPTERS={"service":service,"current_user":lambda:1,
            "csrf_valid":lambda:request.headers.get("X-Course-CSRF")=="fixture-csrf",
            "csrf_token":lambda:"fixture-csrf",
            "presenter":lambda *a:{"board_size":9,"stones":[{"x":1,"y":0,"color":"B"},{"x":0,"y":0,"color":"W"}]},
            "media":lambda *a:None})
    install_course_v1(app)

    @app.get("/fixture-host")
    def host():
        return '<!doctype html><meta charset="utf-8"><title>OFFLINE FIXTURE</title><main class="guild-main"><h1>離線整合 fixture</h1><section id="quest-board"><button id="quest-fixture">既有 Quest Board fixture</button></section></main><script src="/course-v1/curriculum-embed.js"></script>'

    return app


if __name__=="__main__":
    with tempfile.TemporaryDirectory(prefix="g066-course-fixture-") as directory:
        database=Path(directory)/"fixture.sqlite"
        with sqlite3.connect(database) as conn:create_temporary_schema(conn)
        create_fixture(database).run(host="127.0.0.1",port=5066,debug=False,use_reloader=False)
