"""G115 P1 real local Chrome + authenticated synthetic Flask + disposable PG16.
No production access, no real student credentials or data copied.
"""
import json,re,subprocess,threading,time
from pathlib import Path
from flask import request, session
from werkzeug.serving import make_server
import pytest
from test_20261019_monthly_postgres import runtime, local_postgres
from test_g115_claire_zone8_p1_pg import player, snapshot, UID, BAD, GOOD

CHROME=Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
MARKER="g115-real-browser-state"

def test_real_authenticated_zone8_browser_409_skip_and_resumption(player,tmp_path):
    assert CHROME.exists()
    app,_ = player
    hits=[]
    def synthetic_loopback_auth():
        # The server binds ONLY 127.0.0.1; this hook exists only in this
        # disposable runtime fixture and never in accepted production code.
        if request.remote_addr not in ("127.0.0.1","::1"):
            return ("local synthetic browser disabled",403)
        session["user_id"]=UID
        session["username"]="g115-synthetic"
        hits.append(request.path)
    def synthetic_test_only_telemetry(response):
        if request.path=="/index.html" and response.status_code==200:
            response.direct_passthrough=False
            html=response.get_data(as_text=True)
            marker_script="""
<script>
setTimeout(()=>{
 try {
   const b=window.__GO_E10_BATTLE_LIFECYCLE__||{};
   const msg=(document.getElementById('msg-box')||{}).textContent||'';
   const node=document.createElement('pre');
   node.id='g115-real-browser-state';
   node.textContent=JSON.stringify({
       mode:b.mode||null,zoneKey:b.zoneKey||null,
       questionId:b.questionId||null,attemptId:!!b.attemptId,
       hasNonce:!!b.hasNonce,blankBoard:!!document.getElementById('board-canvas-wrap')?.classList.contains('hidden'),
       message:msg.slice(0,160)
   });
   document.body.appendChild(node);
 }catch(e){document.body.insertAdjacentHTML('beforeend','<pre id="g115-real-browser-state">ERROR</pre>');}
},11000);
</script>
"""
            response.set_data(html.replace("</body>",marker_script+"</body>"))
            response.headers["Cache-Control"]="no-store"
        return response
    # Test-only, reversible hooks: Flask's setup API intentionally refuses
    # @before_request after another test already used the same app. In a
    # combined suite, install the synthetic hook directly and ALWAYS remove
    # it. No actual Product or production request middleware is changed.
    app.app.before_request_funcs.setdefault(None, []).append(synthetic_loopback_auth)
    app.app.after_request_funcs.setdefault(None, []).append(synthetic_test_only_telemetry)
    server=make_server("127.0.0.1",0,app.app,threaded=True)
    port=server.server_port
    th=threading.Thread(target=server.serve_forever,daemon=True)
    th.start()
    before=snapshot(app)
    try:
        url=f"http://127.0.0.1:{port}/index.html?zone=d3_4&adventure=1&resume=1"
        profile=tmp_path/"chrome-profile"
        cmd=[str(CHROME),"--headless=new","--disable-gpu","--no-first-run",
           "--no-default-browser-check","--disable-background-networking",
           "--disable-extensions","--user-data-dir="+str(profile),
           "--virtual-time-budget=18000","--dump-dom",url]
        out=subprocess.run(cmd,capture_output=True,text=True,
                           encoding="utf8",errors="replace",timeout=70)
        import html as _html
        matches=re.findall(r'<pre id="g115-real-browser-state">([^<]+)</pre>',out.stdout)
        values=[_html.unescape(v) for v in matches if _html.unescape(v).lstrip().startswith("{")]
        assert out.returncode==0 and values,(
            out.returncode,hits[-20:],matches[-5:],out.stderr[-300:],out.stdout[-700:])
        observed=json.loads(values[-1])
        assert observed["mode"]=="active",observed
        assert observed["zoneKey"]=="d3_4",observed
        assert observed["questionId"]==GOOD["id"],observed
        assert observed["attemptId"] is True and observed["hasNonce"] is True
        assert "/api/adventure/map-battles/v1/attempts" in hits
        after=snapshot(app)
        assert before[0]==after[0] and before[3]==after[3]==0
        assert len(after[1])==1 and after[2]==[(GOOD["id"],"ISSUED")]
        print("G115_REAL_CHROME_NATIVE_PG_ZONE8_COMPLETED",json.dumps(observed,ensure_ascii=True))
    finally:
        server.shutdown()
        th.join(timeout=8)
        app.app.before_request_funcs[None].remove(synthetic_loopback_auth)
        app.app.after_request_funcs[None].remove(synthetic_test_only_telemetry)
