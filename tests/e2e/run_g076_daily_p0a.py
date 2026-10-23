"""Run both Chrome protocols with fresh, loopback-only disposable servers."""
import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'artifacts/g076-p0a'


def run_browser(server_path, browser_path, port, label):
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1', port)) == 0:
            raise RuntimeError(f'Fixture port {port} already occupied; refusing reuse')
    with (OUT/(label+'-server.log')).open('w', encoding='utf-8') as log:
        server = subprocess.Popen([sys.executable, '-B', server_path], cwd=ROOT,
                                  stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(80):
                if server.poll() is not None:
                    raise RuntimeError('Fixture exited: '+label)
                try:
                    urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=1).close()
                    break
                except Exception:
                    time.sleep(0.1)
            else:
                raise RuntimeError('Fixture not ready: '+label)
            result = subprocess.run(['node', browser_path], cwd=ROOT, timeout=180,
                                    capture_output=True, text=True, encoding='utf-8', errors='replace')
            (OUT/(label+'-stdout.log')).write_text(result.stdout, encoding='utf-8')
            (OUT/(label+'-stderr.log')).write_text(result.stderr, encoding='utf-8')
            return {'command':['node',browser_path], 'exit':result.returncode,
                    'status':'PASS' if result.returncode == 0 else 'FAIL'}
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    # Refuse to overwrite a prior browser receipt; archive it explicitly first.
    receipt = OUT/'browser-run.json'
    if receipt.exists():
        raise RuntimeError('Preserve existing browser-run.json before rerunning')
    results = []
    try:
        for server, browser, port, label in (
            ('tests/e2e/g076_daily_fixture_server.py','tests/e2e/g076_daily_chrome.mjs',5079,'on'),
            ('tests/e2e/g076_daily_p0a_fixture_server.py','tests/e2e/g076_daily_legacy_chrome.mjs',5081,'off'),
        ):
            results.append(run_browser(server,browser,port,label))
    except Exception as error:
        results.append({'status':'FAIL', 'error':str(error)})
    receipt.write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(results,indent=2))
    sys.exit(0 if len(results)==2 and all(r['status']=='PASS' for r in results) else 1)
