"""Reproducible Chrome + WGo Canvas + LOCAL HTTP + SQLite Map Battle E2E.

Creates fresh isolated DB by starting the fixture exactly once, then one
headless Chrome invocation, then stops the fixture in finally. Nothing here
uses Oracle, GitHub, production users or connected accounts.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(r"D:\g075-artifacts")
OUT.mkdir(exist_ok=True)
DOM=OUT/"G076_R2_CHROME_HTTP_DOM_FINAL.html"
ERRORS=OUT/"G076_R2_CHROME_HTTP_STDERR_FINAL.txt"
SERVER=OUT/"G076_R2_CHROME_HTTP_SERVER_FINAL.log"
RESULT=OUT/"G076_R2_CHROME_HTTP_RESULT.json"
URL="http://127.0.0.1:5067/"
CHROME=Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
assert CHROME.exists(),"Chrome not installed"
with socket.socket() as sock:
    assert sock.connect_ex(("127.0.0.1",5067))!=0, "G076 test port 5067 already in use"
profile=Path(tempfile.mkdtemp(prefix="g076-headless-"))
server=None
result={"status":"FAIL","sandbox_only":True,"url":URL}
try:
    with SERVER.open("w",encoding="utf-8") as logs:
        server=subprocess.Popen(
            [sys.executable,"-B",str(ROOT/"tests/e2e/g076_live_fixture_server.py")],
            cwd=ROOT,stdout=logs,stderr=subprocess.STDOUT,
            env={**os.environ, "PYTHONUNBUFFERED":"1"})
        for attempt in range(80):
            if server.poll() is not None:
                raise RuntimeError("fixture server unexpectedly exited")
            try:
                with urllib.request.urlopen(URL+"healthz",timeout=1) as response:
                    if response.status==200:break
            except Exception:time.sleep(0.1)
        else:
            raise RuntimeError("localhost fixture health check timeout")
        args=[str(CHROME),"--headless=new","--disable-gpu",
            "--no-first-run","--no-default-browser-check",
            "--disable-extensions","--virtual-time-budget=15000",
            "--window-size=1100,900","--user-data-dir="+str(profile),
            "--dump-dom",URL]
        completed=subprocess.run(args,cwd=ROOT,
                                 capture_output=True,text=True,
                                 errors="replace",timeout=55)
        DOM.write_text(completed.stdout,encoding="utf-8")
        ERRORS.write_text(completed.stderr,encoding="utf-8")
        import re
        matched=re.search(r'<p id="result">([^<]*)</p>',completed.stdout)
        verdict=matched.group(1) if matched else "NO_RENDERED_RESULT"
        passed='data-g076="PASS"' in completed.stdout and "PASS " in verdict
        result.update(
            status="PASS" if passed else "FAIL",
            exit_code=completed.returncode,
            browser_verdict=verdict,
            real_wgo_canvas=True if passed else "UNCONFIRMED",
            local_http_authenticated=True if passed else "UNCONFIRMED",
            schema_fresh_each_run=True,
            result_count=int(re.search(r"PASS (\d+)",verdict).group(1))
                if passed else 0,
            source_revision="g076-local-candidate",
        )
        print("G076_CHROME_FINAL",json.dumps(result),flush=True)
        if not passed:
            raise AssertionError("G076 Chrome localhost browser E2E failed: "+verdict)
finally:
    if server is not None and server.poll() is None:
        server.terminate()
        try:server.wait(timeout=7)
        except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
    shutil.rmtree(profile,ignore_errors=True)
    result["server_stopped"]=server is None or server.poll() is not None
    RESULT.write_text(json.dumps(result,indent=2),encoding="utf-8")
