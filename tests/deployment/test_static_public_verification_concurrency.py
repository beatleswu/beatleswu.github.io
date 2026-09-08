from pathlib import Path
import json
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[2]
DEPLOY = (ROOT / "scripts/release/deploy-static-release.ps1").read_text(encoding="utf-8")
PSM1 = ROOT / "scripts/release/ReleaseTooling.psm1"


def _ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def _run_powershell(script):
    executable = shutil.which("pwsh") or shutil.which("powershell")
    assert executable, "PowerShell is required for public-verifier contract tests"
    return subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-Command", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_public_verification_is_bounded_and_deadline_limited():
    assert "$PublicVerificationConcurrency = 8" in DEPLOY
    assert "$PublicVerificationRequestTimeoutSeconds = 15" in DEPLOY
    assert "Get-StaticPublicVerificationDeadlineSeconds" in DEPLOY
    assert "$PublicVerificationAttempts = 1" in DEPLOY
    assert "Invoke-BoundedPublicVerification" in DEPLOY
    assert "Start-Job -ScriptBlock $worker" in DEPLOY
    assert "Wait-Job -Job $jobs -Timeout" in DEPLOY
    assert "Stop-Job -Job $job" in DEPLOY
    assert "Remove-Job -Job $job -Force" in DEPLOY


def test_public_verification_keeps_complete_fail_closed_result_aggregation():
    assert "sha_mismatch" in DEPLOY
    assert "http_non_200" in DEPLOY
    assert "request_timeout" in DEPLOY
    assert "unexpected_exception" in DEPLOY
    assert "tls_trust_failure" in DEPLOY
    assert "connection_failure" in DEPLOY
    assert "transport_failure" in DEPLOY
    assert "malformed_response" in DEPLOY
    assert "failure_samples" in DEPLOY
    assert "cancelled_deadline" in DEPLOY
    assert "worker_exception" in DEPLOY
    assert "Public content verification failed" in DEPLOY
    assert "$publicResults.Count -ne $publicEntries.Count" in DEPLOY
    assert "SkipCertificateCheck" not in DEPLOY


def test_raw_public_worker_hashes_response_bytes_without_text_reencoding():
    worker = DEPLOY.split("$worker = {", 1)[1].split("$jobs = @()", 1)[0]
    assert "[System.Net.HttpWebRequest]::Create($Url)" in worker
    assert "ComputeHash($stream)" in worker
    assert "Encoding]::UTF8.GetBytes" not in worker
    assert "AllowAutoRedirect = $false" in worker


def test_public_verifier_preserves_tls_timeout_connection_and_transport_classes():
    script = f"""
Import-Module {_ps_quote(PSM1)} -Force -DisableNameChecking
$trust = New-Object System.Net.WebException('certificate trust failed', [System.Net.WebExceptionStatus]::TrustFailure)
$timeout = New-Object System.Net.WebException('request timed out', [System.Net.WebExceptionStatus]::Timeout)
$connection = New-Object System.Net.WebException('could not connect', [System.Net.WebExceptionStatus]::ConnectFailure)
$transport = New-Object System.Net.WebException('connection closed', [System.Net.WebExceptionStatus]::ConnectionClosed)
$malformed = New-Object System.Exception('ConvertFrom-Json: invalid JSON response')
[ordered]@{{
    trust = (Get-PublicVerificationFailureRecord -Exception $trust -Path 'trust.js' -VerificationMode 'RAW_PUBLIC_BYTES')
    timeout = (Get-PublicVerificationFailureRecord -Exception $timeout -Path 'timeout.js' -VerificationMode 'RAW_PUBLIC_BYTES')
    connection = (Get-PublicVerificationFailureRecord -Exception $connection -Path 'connection.js' -VerificationMode 'RAW_PUBLIC_BYTES')
    transport = (Get-PublicVerificationFailureRecord -Exception $transport -Path 'transport.js' -VerificationMode 'RAW_PUBLIC_BYTES')
    malformed = (Get-PublicVerificationFailureRecord -Exception $malformed -Path 'provenance' -VerificationMode 'STATIC_RELEASE_PROVENANCE')
}} | ConvertTo-Json -Compress
"""
    result = _run_powershell(script)
    assert result.returncode == 0, f"failure classifier probe failed:\n{result.stdout}\n{result.stderr}"
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["trust"]["status"] == "tls_trust_failure"
    assert payload["timeout"]["status"] == "request_timeout"
    assert payload["connection"]["status"] == "connection_failure"
    assert payload["transport"]["status"] == "transport_failure"
    assert payload["malformed"]["status"] == "malformed_response"
    assert "certificate trust failed" in payload["trust"]["error"]
    assert payload["trust"]["web_exception_status"] == "TrustFailure"


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
