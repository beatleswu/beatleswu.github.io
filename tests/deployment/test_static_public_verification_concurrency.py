from pathlib import Path
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[2]
DEPLOY = (ROOT / "scripts/release/deploy-static-release.ps1").read_text(encoding="utf-8")


def test_public_verification_is_bounded_and_deadline_limited():
    assert "$PublicVerificationConcurrency = 8" in DEPLOY
    assert "$PublicVerificationRequestTimeoutSeconds = 15" in DEPLOY
    assert "$PublicVerificationDeadlineSeconds = 240" in DEPLOY
    assert "Invoke-BoundedPublicVerification" in DEPLOY
    assert "Start-Job -ScriptBlock $worker" in DEPLOY
    assert "Wait-Job -Job $jobs -Timeout" in DEPLOY
    assert "Stop-Job -Job $job" in DEPLOY
    assert "Remove-Job -Job $job -Force" in DEPLOY


def test_public_verification_keeps_complete_fail_closed_result_aggregation():
    assert "sha_mismatch" in DEPLOY
    assert "http_failed" in DEPLOY
    assert "cancelled_deadline" in DEPLOY
    assert "worker_exception" in DEPLOY
    assert "Public content verification failed" in DEPLOY
    assert "$publicResults.Count -ne $manifest.files.Count" in DEPLOY


def test_public_verification_still_runs_before_service_worker_acceptance():
    assert DEPLOY.index("Invoke-BoundedPublicVerification") < DEPLOY.index("Get-SwVersionFromUrl")


def test_representative_local_benchmark_shows_bounded_concurrency_gain():
    request_count = 1390
    delay_seconds = 0.003

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib handler API
            time.sleep(delay_seconds)
            payload = b"ok"
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        urls = [f"http://127.0.0.1:{server.server_port}/{i}" for i in range(request_count)]

        def fetch(url):
            with urlopen(url, timeout=5) as response:
                return response.read()

        started = time.perf_counter()
        for url in urls:
            fetch(url)
        sequential_seconds = time.perf_counter() - started

        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(fetch, urls))
        concurrent_seconds = time.perf_counter() - started
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert concurrent_seconds < sequential_seconds * 0.8, (
        f"bounded benchmark did not improve enough: sequential={sequential_seconds:.3f}s, "
        f"concurrent={concurrent_seconds:.3f}s"
    )
