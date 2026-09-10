"""Execute rollback's real manifest and guarded execution path locally.

Only remote/process boundaries are replaced; manifest construction, checks,
execution ordering, and result serialization remain the production code.
"""
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/release/rollback-release.ps1'
FIELDS = (
    'questions_corpus_sha256', 'questions_corpus_record_count',
    'questions_corpus_bytes', 'questions_corpus_snapshot_id',
    'questions_corpus_source_identity', 'questions_corpus_source_sha256',
    'questions_corpus_source_record_count',
)


def run_path(tmp_path, *, missing=None, malformed=None, mismatch=None):
    manifest = json.loads((ROOT / 'deploy/release-manifest.example.json').read_text())
    manifest['rollback_image_identity'] = {
        'previous_app_image_tag': 'fixture:baseline',
        'previous_scheduler_image_tag': 'fixture:baseline',
        'previous_app_release_git_sha': 'd' * 40,
        'previous_scheduler_release_git_sha': 'd' * 40,
        'previous_app_image_id': 'sha256:' + 'e' * 64,
        'previous_scheduler_image_id': 'sha256:' + 'e' * 64,
    }
    expected = {k: manifest[k] for k in FIELDS}
    if missing:
        del manifest[missing]
    if malformed:
        manifest[malformed] = True
    record = tmp_path / 'record.json'
    record.write_text(json.dumps(manifest), encoding='utf-8')
    source = SCRIPT.read_text(encoding='utf-8')
    # Load actual functions, skipping only the script's top-level initialization.
    functions = source[source.index('function Invoke-RemoteCommandResult'):source.index('$rollbackManifestPath =')]
    execution = source[source.index("Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_ROLLBACK'"):]
    probe = dict(exists=True, readable=True, parseable=True, record_count_ok=True,
                 structural_record_check=True, sha256=expected[FIELDS[0]],
                 record_count=expected[FIELDS[1]], bytes=expected[FIELDS[2]])
    if mismatch:
        probe[mismatch] = 'f' * 64 if mismatch == 'sha256' else 1
    probe_path = tmp_path / 'probe.json'
    probe_path.write_text(json.dumps(probe), encoding='utf-8')
    harness = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{ROOT.as_posix()}/scripts/release/ReleaseTooling.psm1' -Force -DisableNameChecking
$repoRoot = '{ROOT.as_posix()}'
$PSScriptRoot = '{ROOT.as_posix()}/scripts/release'
$layout = Get-Content '{ROOT.as_posix()}/deploy/release-layout.example.json' -Raw | ConvertFrom-Json
$manifest = Get-Content '{record.as_posix()}' -Raw | ConvertFrom-Json
$probe = Get-Content '{probe_path.as_posix()}' -Raw | ConvertFrom-Json
$RollbackManifest = '{record.as_posix()}'
$LayoutFile = 'deploy/release-layout.example.json'
$rollbackVerificationManifestPath = '{tmp_path.as_posix()}/verify.json'
$rollbackManifestPath = '{tmp_path.as_posix()}/result.json'
$OwnerGate = 'GO_ROLLBACK'
$FramedResult = $false
$FreezeCommunityLeaderboardRewards = $false
$script:events = @()
{functions}
function Invoke-RemoteCommandResult {{
 param($Name,$Command,$StdinText)
 if ($Command -match '^docker run ') {{ $script:events += "corpus-volume:$Command" }}
 elseif ($Command -match '^docker exec ') {{ $script:events += "corpus-app:$Command" }}
 else {{ throw "Unexpected remote command: $Command" }}
 return @{{exit_code=0; stdout=($probe | ConvertTo-Json -Compress); output=($probe | ConvertTo-Json -Compress)}}
}}
function Enter-RemoteReleaseOperationLock {{ $script:events += 'lock' }}
function Exit-RemoteReleaseOperationLock {{ $script:events += 'unlock' }}
function Assert-ProtectedHostEnvCredentialAndTcpAuthentication {{}}
function Get-RemoteQuestionsVolumeName {{ return 'fixture-volume' }}
function Get-RemoteImageLabels {{ return @{{}} }}
function Get-RemoteContainerSnapshot {{
 param($ContainerName)
 return [ordered]@{{ image_tag='fixture:baseline'; image_id=('sha256:' + ('e'*64));
 state='running'; health='healthy'; compose_project=$layout.compose_project;
 compose_service=$ContainerName }}
}}
function Get-AppReadinessGateReport {{ return @{{readiness_mode='legacy_fallback'; questions=$probe}} }}
function Invoke-RemoteText {{ param($Command) $script:events += $Command; return '' }}
function Invoke-BoundedNativeCommand {{
 param($FileName,$ArgumentList,$WorkingDirectory,[switch]$RequireWorkingDirectory,$TimeoutSeconds,$OperationLabel)
 if ($OperationLabel -ne 'rollback production verification') {{ throw 'Unexpected process boundary' }}
 $m = Get-Content $rollbackVerificationManifestPath -Raw | ConvertFrom-Json
 if ($m.image_id -ne ('sha256:' + ('e'*64))) {{ throw 'Wrong rollback image' }}
 $script:events += 'verify'
 return @{{exit_code=0; stdout=(ConvertTo-FramedJsonRecord -InputObject @{{verified=$true}} -Prefix '__GO_ODYSSEY_POWERSHELL_RESULT_V1__:')}}
}}
try {{
{execution}
}} finally {{ ConvertTo-Json -InputObject @($script:events) | Set-Content '{tmp_path.as_posix()}/events.json' }}
"""
    harness_path = tmp_path / 'run.ps1'
    harness_path.write_text(harness, encoding='utf-8')
    result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(harness_path)],
                            cwd=ROOT, capture_output=True, text=True, timeout=45)
    return result, expected


def test_actual_rollback_execution_constructs_and_preserves_identity(tmp_path):
    result, expected = run_path(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((tmp_path / 'verify.json').read_text(encoding='utf-8-sig'))
    assert {k: manifest[k] for k in FIELDS} == expected
    assert manifest['release_git_sha'] == 'd' * 40
    assert manifest['image_id'] == 'sha256:' + 'e' * 64
    events = json.loads((tmp_path / 'events.json').read_text(encoding='utf-8-sig'))
    assert events[0] == 'lock'
    assert events[-2:] == ['verify', 'unlock']
    assert events[1].startswith('corpus-volume:docker run --rm --network none --read-only')
    assert '--entrypoint python' in events[1]
    assert 'fixture-volume:/app/data:ro' in events[1]
    assert 'fixture:baseline' in events[1]
    assert 'docker exec' not in events[1]
    assert 'up -d' in events[2]
    assert events[3].startswith('corpus-app:docker exec -i')
    assert 'up -d' in events[4]


@pytest.mark.parametrize('field', FIELDS)
def test_missing_corpus_field_blocks_before_remote_mutation(tmp_path, field):
    result, _ = run_path(tmp_path, missing=field)
    assert result.returncode != 0
    assert 'QuestionsCorpusIdentity' in result.stderr
    assert not (tmp_path / 'verify.json').exists()
    events = tmp_path / 'events.json'
    assert not events.exists() or json.loads(events.read_text()) == []


@pytest.mark.parametrize('field', FIELDS)
def test_malformed_corpus_field_blocks(tmp_path, field):
    result, _ = run_path(tmp_path, malformed=field)
    assert result.returncode != 0
    assert 'QuestionsCorpusIdentity' in result.stderr
    assert not (tmp_path / 'verify.json').exists()


@pytest.mark.parametrize('field', ['sha256', 'bytes', 'record_count'])
def test_live_corpus_mismatch_blocks_before_runtime_switch(tmp_path, field):
    result, _ = run_path(tmp_path, mismatch=field)
    assert result.returncode != 0
    assert 'Rollback corpus identity does not match' in result.stderr
    assert not (tmp_path / 'verify.json').exists()
    events = json.loads((tmp_path / 'events.json').read_text())
    assert events[0] == 'lock'
    assert events[1].startswith('corpus-volume:docker run --rm --network none --read-only')
    assert events[2] == 'unlock'
    assert not any('up -d' in event for event in events)


def test_coordinator_and_automatic_recovery_use_real_rollback_script():
    coordinator = (ROOT / 'scripts/release/deploy-coordinated-release.ps1').read_text()
    deploy = (ROOT / 'scripts/release/deploy-release-image.ps1').read_text()
    assert "'rollback-release.ps1'" in coordinator
    assert "'-RollbackManifest', $script:appDeploymentRecordPath" in coordinator
    assert "'rollback-release.ps1'" in deploy
    assert "'-RollbackManifest',$deploymentRecordPath" in deploy.replace(' ', '')
