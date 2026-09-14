from pathlib import Path
import json
import hashlib
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
ROLLBACK = (ROOT / "scripts/release/rollback-static-release.ps1").read_text(encoding="utf-8")


def _ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def _run_powershell(script):
    executable = shutil.which("pwsh") or shutil.which("powershell")
    assert executable, "PowerShell is required for public-verifier contract tests"
    return subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_public_verification_is_bounded_and_deadline_limited():
    tooling = PSM1.read_text(encoding="utf-8")
    assert "$PublicVerificationConcurrency = 8" in DEPLOY
    assert "$PublicVerificationRequestTimeoutSeconds = Get-StaticPublicVerificationRequestTimeoutSeconds" in DEPLOY
    assert "function Get-StaticPublicVerificationRequestTimeoutSeconds" in tooling
    assert "Get-StaticPublicVerificationDeadlineSeconds" in DEPLOY
    assert "$PublicVerificationAttempts = 1" in DEPLOY
    assert "Invoke-BoundedPublicVerification" in DEPLOY
    assert "Invoke-BoundedPublicStaticVerification" in DEPLOY
    assert "Invoke-BoundedPublicStaticVerification" in ROLLBACK
    assert "Start-Job -ScriptBlock $worker" in tooling
    assert "Wait-Job -Job $jobs -Timeout" in tooling
    assert "Stop-Job -Job $job" in tooling
    assert "Remove-Job -Job $job -Force" in tooling


def test_public_verifier_uses_at_most_one_job_per_bounded_worker():
    tooling = PSM1.read_text(encoding="utf-8")
    assert "if ($Concurrency -gt 8)" in tooling
    assert "$workerCount = [Math]::Min($Concurrency, $prepared.Count)" in tooling
    assert "$chunkSize = [int][Math]::Ceiling" in tooling
    assert "for ($workerIndex = 0; $workerIndex -lt $workerCount; $workerIndex++)" in tooling
    assert "param([object[]]$Items, [int]$TimeoutSeconds, [long]$DeadlineTicks)" in tooling
    assert "Start-Job -ScriptBlock $worker -ArgumentList (,$chunkItems)" in tooling
    assert "Start-Job -ScriptBlock $worker -ArgumentList $item.url" not in tooling
    assert "for ($offset = 0; $offset -lt $prepared.Count; $offset += $Concurrency)" not in tooling


def test_public_verification_keeps_complete_fail_closed_result_aggregation():
    tooling = PSM1.read_text(encoding="utf-8")
    assert "sha_mismatch" in tooling
    assert "http_non_200" in tooling
    assert "request_timeout" in tooling
    assert "unexpected_exception" in tooling
    assert "tls_trust_failure" in tooling
    assert "connection_failure" in tooling
    assert "transport_failure" in tooling
    assert "malformed_response" in tooling
    assert "failure_samples" in DEPLOY
    assert "cancelled_deadline" in tooling
    assert "worker_exception" in tooling
    assert "Public content verification failed" in DEPLOY
    assert "$publicResults.Count -ne $publicEntries.Count" in DEPLOY
    assert "SkipCertificateCheck" not in DEPLOY


def test_raw_public_worker_hashes_response_bytes_without_text_reencoding():
    tooling = PSM1.read_text(encoding="utf-8")
    worker = tooling.split("$worker = {", 1)[1].split("$prepared = @()", 1)[0]
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


def test_rollback_uses_the_same_finite_verifier_contract():
    tooling = PSM1.read_text(encoding="utf-8")
    assert "$rollbackPublicVerificationConcurrency = 8" in ROLLBACK
    assert "$rollbackPublicVerificationAttempts = 1" in ROLLBACK
    assert "Get-StaticPublicVerificationDeadlineSeconds" in ROLLBACK
    assert "-DeadlineSeconds $rollbackPublicVerificationDeadlineSeconds" in ROLLBACK
    assert "Invoke-BoundedPublicStaticVerification" in ROLLBACK
    assert "Start-Job -ScriptBlock $worker" in tooling
    assert "finally" in tooling
    assert "Remove-Job -Job $job -Force" in tooling


def test_public_verifier_deadline_is_global_not_multiplied_per_asset():
    script = f"""
Import-Module {_ps_quote(PSM1)} -Force -DisableNameChecking
[ordered]@{{ deadline_2011 = Get-StaticPublicVerificationDeadlineSeconds -FileCount 2011 -Concurrency 8 -RequestTimeoutSeconds 60 -AttemptCount 1; deadline_1 = Get-StaticPublicVerificationDeadlineSeconds -FileCount 1 -Concurrency 8 -RequestTimeoutSeconds 60 -AttemptCount 1 }} | ConvertTo-Json -Compress
"""
    result = _run_powershell(script)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["deadline_2011"] == 7200
    assert payload["deadline_1"] < 7200


def test_shared_verifier_covers_raw_and_authenticated_entries_fail_closed(tmp_path):
    raw_payload = b"shared-verifier-bytes"
    raw_hash = hashlib.sha256(raw_payload).hexdigest()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib handler API
            if self.path == "/inventory":
                self.send_response(302)
                self.send_header("Location", "/login")
                self.end_headers()
                return
            if self.path == "/asset.bin":
                self.send_response(200)
                self.send_header("Content-Length", str(len(raw_payload)))
                self.end_headers()
                self.wfile.write(raw_payload)
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        script = f"""
Import-Module {_ps_quote(PSM1)} -Force -DisableNameChecking
$entries = @(
    [pscustomobject]@{{ path = 'asset.bin'; sha256 = '{raw_hash}' }},
    [pscustomobject]@{{ path = 'inventory.html'; sha256 = ('0' * 64) }}
)
$result = @(Invoke-BoundedPublicStaticVerification -Entries $entries -PublicBase 'http://127.0.0.1:{server.server_port}' -Concurrency 2 -RequestTimeoutSeconds 5 -DeadlineSeconds 30 -AttemptCount 1)
$result | ConvertTo-Json -Compress
"""
        result = _run_powershell(script)
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        assert {item["path"]: item["status"] for item in payload} == {
            "asset.bin": "passed",
            "inventory.html": "passed",
        }
        auth = next(item for item in payload if item["path"] == "inventory.html")
        assert auth["verification_mode"] == "AUTHENTICATED_ROUTE"
        assert auth["login_body_hashed"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_shared_verifier_global_deadline_fails_and_cleans_workers(tmp_path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib handler API
            time.sleep(5)
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        script = f"""
Import-Module {_ps_quote(PSM1)} -Force -DisableNameChecking
$entries = @(
    [pscustomobject]@{{ path = 'one.bin'; sha256 = ('0' * 64) }},
    [pscustomobject]@{{ path = 'two.bin'; sha256 = ('0' * 64) }},
    [pscustomobject]@{{ path = 'three.bin'; sha256 = ('0' * 64) }}
)
$result = @(Invoke-BoundedPublicStaticVerification -Entries $entries -PublicBase 'http://127.0.0.1:{server.server_port}' -Concurrency 2 -RequestTimeoutSeconds 10 -DeadlineSeconds 2 -AttemptCount 1)
[ordered]@{{ result = $result; outstanding_jobs = @(@(Get-Job)).Count }} | ConvertTo-Json -Compress
"""
        started = time.perf_counter()
        result = _run_powershell(script)
        elapsed = time.perf_counter() - started
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        assert elapsed < 15, f"global deadline probe exceeded bounded test window: {elapsed:.2f}s"
        assert payload["outstanding_jobs"] == 0
        statuses = {item["status"] for item in payload["result"]}
        assert "passed" not in statuses
        assert statuses & {"cancelled_deadline", "timeout", "request_timeout"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


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
