"""Real loopback HTTP and real Chrome JS execution; synthetic providers only."""
import http.cookiejar
import json
from pathlib import Path
import re
import subprocess
import threading
import urllib.error
import urllib.request

import pytest
from werkzeug.serving import make_server

from g076_nonmap_fixture import make_fixture, ROOT

CHROME = Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')


@pytest.fixture
def live(tmp_path):
    fixture = make_fixture(tmp_path/'http.sqlite')
    server = make_server('127.0.0.1', 0, fixture[0], threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = 'http://127.0.0.1:' + str(server.server_port)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(path, body=None):
        req = urllib.request.Request(url + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type': 'application/json'} if body is not None else {})
        try:
            with opener.open(req, timeout=10) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)
    try:
        yield request, fixture, url
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.mark.parametrize('flow', ['practice', 'daily'])
def test_true_loopback_http_authoritative_answer(live, flow):
    request, fixture, _ = live
    assert request('/fixture/login', {'uid': 101})[0] == 200
    token = request('/fixture/token/' + flow)[1]['attempt_token']
    identity = {'flow': flow, 'attempt_token': token}
    status, ready = request('/api/g076/nonmap/steps/start', identity)
    assert status == 200 and ready['board_only']
    body = {**identity, 'step_index': 0, 'step_nonce': ready['step_nonce'], 'move': {'x': 0, 'y': 0}}
    status, first = request('/api/g076/nonmap/steps', body)
    assert status == 200 and first['opponent_reply'] == [1, 1]
    body.update(step_index=1, step_nonce=first['step_nonce'], move={'x': 2, 'y': 2})
    status, terminal = request('/api/g076/nonmap/steps', body)
    assert status == 200 and terminal['status'] == 'CORRECT'
    status, duplicate = request('/api/g076/nonmap/steps', body)
    assert status == 200 and duplicate == {**terminal, 'duplicate': True}
    assert request('/api/g076/nonmap/steps', {**body, 'grade': 5})[0] == 400
    with fixture[3]() as conn:
        assert conn.execute('SELECT COUNT(*) FROM fixture_receipts').fetchone()[0] == 1


@pytest.mark.skipif(not CHROME.exists(), reason='local Chrome is unavailable')
def test_real_chrome_client_response_loss_and_resume(live, tmp_path):
    _, fixture, url = live
    profile = tmp_path/'chrome-profile'
    run = subprocess.run([str(CHROME), '--headless=new', '--disable-gpu',
        '--no-first-run', '--no-default-browser-check', '--disable-extensions',
        '--disable-background-networking', '--disable-component-update', '--disable-sync',
        '--no-proxy-server', '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1',
        '--virtual-time-budget=15000', '--user-data-dir=' + str(profile), '--dump-dom', url],
        capture_output=True, text=True, errors='replace', timeout=50)
    (tmp_path/'chrome-dom.html').write_text(run.stdout, encoding='utf-8')
    (tmp_path/'chrome-stderr.txt').write_text(run.stderr, encoding='utf-8')
    assert run.returncode == 0
    assert 'data-g076-nonmap="PASS"' in run.stdout, run.stdout[-2500:]
    assert '<p id="result">PASS 20</p>' in run.stdout
    with fixture[3]() as conn:
        assert conn.execute('SELECT COUNT(*) FROM fixture_receipts').fetchone()[0] == 2
        assert conn.execute('SELECT repetitions FROM srs_cards').fetchone()[0] == 1
        assert conn.execute('SELECT xp FROM fixture_daily').fetchone()[0] == 75


def test_browser_script_syntax_for_existing_pages_and_new_client(tmp_path):
    # Parse each classic inline browser script without executing the application
    # or loading remote scripts. Real client execution is exercised above.
    sources = []
    for name in ('index.html', 'daily_challenge.html', 'rating_test.html'):
        html = (ROOT/name).read_text(encoding='utf-8')
        for attrs, code in re.findall(r'<script\b([^>]*)>([\s\S]*?)</script\s*>', html, re.I):
            if not re.search(r'\bsrc\s*=|application/ld\+json|type\s*=\s*[\'"]module', attrs, re.I) and code.strip():
                sources.append({'name': name, 'code': code})
    sources.append({'name': 'g076_nonmap_step_client.js',
                    'code': (ROOT/'js/game/g076_nonmap_step_client.js').read_text()})
    source_file = tmp_path/'browser-scripts.json'
    source_file.write_text(json.dumps(sources), encoding='utf-8')
    script = "const fs=require('fs');const s=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));for(const x of s){try{new Function(x.code);}catch(e){throw new Error(x.name+': '+e.message);}}process.stdout.write('PARSED '+s.length);"
    run = subprocess.run(['node', '-e', script, str(source_file)], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, run.stderr
    assert {item['name'] for item in sources} == {
        'index.html', 'daily_challenge.html', 'rating_test.html', 'g076_nonmap_step_client.js'}
