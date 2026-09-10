"""Contracts for scripts/release/deploy-coordinated-release.ps1, the
Deployment Workflow V3 CLI entrypoint.

Only the genuinely testable-without-Production surface is covered here:
argument validation, the OwnerGate contract, and the dry-run plan report
(which never builds, packages, promotes, or contacts Production -- exactly
like every other canonical release script's dry-run mode). The real
-Execute wiring to build-release-image.ps1/package-*.ps1/deploy-*.ps1/
rollback-*.ps1 is exercised indirectly by test_coordinated_release_state_machine.py
(which proves the underlying state machine those phase scriptblocks drive
is correct) and by source-level checks here that each phase is wrapped in
Invoke-BoundedNativeCommand -- not by an actual end-to-end -Execute run,
which this task is explicitly not authorized to perform against any real
host.

One qualification, added with the QuestionsCorpus forwarding contract: exactly
one test here passes -Execute together with the CORRECT owner gate, because
"corpus identity missing under -Execute" has no dry-run equivalent (a dry run
deliberately permits omitting it). That test asserts the exact fail-closed
message, so a loosened assertion fails the test rather than letting the suite
proceed into PRECHECK/BUILD_APP, and it uses the example layout whose hosts are
all example.invalid. test_only_one_test_crosses_the_owner_gate_in_execute_mode
pins that this stays a single case. Every other malformed-input case is
exercised through the dry run.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "release" / "deploy-coordinated-release.ps1"
EXAMPLE_LAYOUT = "deploy\\release-layout.example.json"
CANDIDATE_SHA = "aa3d56b369be72c74d79f5a3c0fd04b7e847475e"


def run_powershell(args: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    quoted_args = " ".join(
        f"'{a}'" if not a.startswith("-") else a for a in args
    )
    preamble = (
        "$OutputEncoding = [Console]::OutputEncoding = "
        "New-Object System.Text.UTF8Encoding($false);\n"
    )
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
         preamble + f"& '{SCRIPT.as_posix()}' {quoted_args}"],
        cwd=REPO_ROOT,
        env={**os.environ, "SECRET_KEY": "coordinated-release-cli-test-only"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )


def _last_json(stdout: str) -> dict:
    start = stdout.find("{")
    assert start >= 0, stdout
    return json.loads(stdout[start:])


def _json_extractor_function() -> str:
    content = SCRIPT.read_text(encoding="utf-8")
    start = content.index("function ConvertFrom-LastJsonObject {")
    end = content.index("function Invoke-GovernedScript {", start)
    return content[start:end]


def _run_json_extractor_probe(body: str) -> subprocess.CompletedProcess[str]:
    command = (
        "$ErrorActionPreference = 'Stop';\n"
        + _json_extractor_function()
        + "\n"
        + body
    )
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )


def test_coordinator_extracts_final_json_after_diagnostic_and_intermediate_records():
    result = _run_json_extractor_probe(
        r'''$payload = ConvertFrom-LastJsonObject -Text @'
diagnostic { this is not JSON }
{"stage":"intermediate","message":"literal brace } is noise"}
{"success":true,"image_id":"sha256:test","nested":{"key":"value"}}
'@ -OperationLabel 'parser probe'
$payload | ConvertTo-Json -Compress
'''
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "success": True,
        "image_id": "sha256:test",
        "nested": {"key": "value"},
    }


def test_coordinator_rejects_incomplete_final_json_instead_of_falling_back():
    result = _run_json_extractor_probe(
        r'''$payload = @'
{"success":true}
{"broken":{"nested":1}
'@
try {
    ConvertFrom-LastJsonObject -Text $payload -OperationLabel 'parser probe' | Out-Null
    Write-Output 'UNEXPECTED_PASS'
    exit 1
}
catch {
    Write-Output 'FAIL_CLOSED'
}
'''
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "FAIL_CLOSED"


def test_script_parses_as_valid_powershell():
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "$t=$null;$e=$null;"
         f"[System.Management.Automation.Language.Parser]::ParseFile('{SCRIPT.as_posix()}', [ref]$t, [ref]$e) | Out-Null;"
         "if ($e.Count -gt 0) { $e | ForEach-Object { Write-Host $_.Message }; exit 1 } else { Write-Host 'OK' }"],
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_dry_run_never_mutates_and_reports_the_full_phase_plan():
    result = run_powershell(["-ExpectedGitSha", CANDIDATE_SHA, "-LayoutFile", EXAMPLE_LAYOUT])
    assert result.returncode == 0, result.stdout + result.stderr
    payload = _last_json(result.stdout)
    assert payload["dry_run"] is True
    assert payload["execute_requested"] is False
    assert payload["expected_git_sha"] == CANDIDATE_SHA
    assert payload["required_owner_gate"] == "GO_DEPLOY_WITH_BOUNDED_RECOVERY"
    assert payload["result"] == "DRY_RUN_COMPLETE"
    assert payload["plan"] == [
        "PRECHECK", "BUILD_APP", "PACKAGE_APP", "PACKAGE_STATIC",
        "SNAPSHOT_BASELINE", "VERIFY_ROLLBACK_READY",
        "PROMOTE_APP", "VERIFY_APP", "PROMOTE_STATIC", "VERIFY_STATIC",
        "JOINT_PROVENANCE", "PRODUCTION_SMOKE",
    ]
    # The example layout's host/URLs are all example.invalid / a fake ssh
    # alias -- confirms dry-run only ever reads local config, never resolves
    # or contacts anything real.
    assert "example" in payload["release_layout"]["health_url"]


def test_execute_without_owner_gate_fails_closed():
    result = run_powershell(["-ExpectedGitSha", CANDIDATE_SHA, "-LayoutFile", EXAMPLE_LAYOUT, "-Execute"])
    assert result.returncode != 0
    assert "docker" not in (result.stdout + result.stderr).lower() or "ParameterBindingValidationException" in (result.stdout + result.stderr)


def test_execute_with_wrong_owner_gate_fails_closed_before_any_mutation():
    result = run_powershell([
        "-ExpectedGitSha", CANDIDATE_SHA, "-LayoutFile", EXAMPLE_LAYOUT,
        "-Execute", "-OwnerGate", "GO_DEPLOY",
    ])
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "Owner gate mismatch" in combined
    assert "GO_DEPLOY_WITH_BOUNDED_RECOVERY" in combined


def test_execute_rejects_arbitrary_gate_strings():
    result = run_powershell([
        "-ExpectedGitSha", CANDIDATE_SHA, "-LayoutFile", EXAMPLE_LAYOUT,
        "-Execute", "-OwnerGate", "totally-not-a-real-gate",
    ])
    assert result.returncode != 0
    assert "Owner gate mismatch" in (result.stdout + result.stderr)


def test_invalid_git_sha_fails_before_any_mutation():
    result = run_powershell(["-ExpectedGitSha", "not-a-real-commit-ish", "-LayoutFile", EXAMPLE_LAYOUT])
    assert result.returncode != 0


# ---------------------------------------------------------------------------
# Source-level: every phase must be bounded, and this script must not
# duplicate low-level build/deploy/rollback logic.
# ---------------------------------------------------------------------------

def test_every_governed_script_invocation_is_bounded():
    content = SCRIPT.read_text(encoding="utf-8")
    assert "function Invoke-GovernedScript" in content
    invoke_block_start = content.index("function Invoke-GovernedScript")
    invoke_block_end = content.index("$GetCurrentState = {", invoke_block_start)
    invoke_body = content[invoke_block_start:invoke_block_end]
    assert "Invoke-BoundedNativeCommand" in invoke_body
    assert "TimeoutSeconds" in invoke_body
    # One call site per phase that actually shells out to an existing
    # governed script: GetCurrentState, BuildApp, PackageApp, PackageStatic,
    # PromoteStatic, PromoteApp, RollbackStatic, RollbackApp, plus
    # VerifyApp's canonical production verification and VerifyStatic's TWO
    # canonical verifications (preflight -StaticManifest for live-generation
    # hashes/health, and deploy-static-release.ps1 -VerifyOnly for the public
    # acceptance contract).
    call_sites = [line for line in content.splitlines() if "Invoke-GovernedScript -ScriptPath" in line]
    assert len(call_sites) == 11
    # Every one of those call sites supplies an explicit bound (plus one
    # more -TimeoutSeconds inside Invoke-GovernedScript's own definition,
    # plus three more for GetCurrentState's two Get-RemoteImageSourceGitSha
    # reads (app + scheduler) and its Get-RemoteStaticGenerationSourceGitSha
    # read).
    assert content.count("-TimeoutSeconds") == 15


def test_static_public_acceptance_is_verified_through_the_canonical_read_only_entrypoint():
    # VerifyStatic must prove the public acceptance contract by invoking the
    # canonical owner of that contract in read-only mode -- never by
    # reimplementing it, and never by running a mutating deploy.
    content = SCRIPT.read_text(encoding="utf-8")
    start = content.index("$VerifyStatic = {")
    end = content.index("$PromoteApp = {", start)
    block = content[start:end]
    assert "-VerifyOnly" in block
    assert "$deployStaticScript" in block
    assert "PUBLIC_STATIC_ACCEPTANCE_VERIFIED" in block
    # ... and never with -Execute / an owner gate (that would be a mutation).
    assert "'-Execute'" not in block
    assert "GO_DEPLOY" not in block


def test_does_not_duplicate_low_level_release_logic():
    content = SCRIPT.read_text(encoding="utf-8")
    # This script must only ORCHESTRATE the existing governed scripts, never
    # reimplement their internals.
    assert "docker buildx build" not in content
    assert "docker save" not in content
    assert "ConvertTo-FramedJsonRecord" not in content
    for existing_script in [
        "build-release-image.ps1", "package-release-image.ps1",
        "package-static-release.ps1", "deploy-release-image.ps1",
        "deploy-static-release.ps1", "rollback-release.ps1",
        "rollback-static-release.ps1", "preflight-production.ps1",
    ]:
        assert existing_script in content, f"expected {existing_script} to be wired as a phase executor"


def test_gate_required_string_matches_state_machine_authority_model():
    content = SCRIPT.read_text(encoding="utf-8")
    assert "GO_DEPLOY_WITH_BOUNDED_RECOVERY" in content
    assert "Assert-OwnerGate" in content


# ---------------------------------------------------------------------------
# QuestionsCorpus eight-parameter forwarding.
#
# package-release-image.ps1 declares all eight QuestionsCorpus parameters as
# Mandatory = $true. Before this contract existed the coordinator neither
# accepted nor forwarded them, so PACKAGE_APP could not run noninteractively
# at all: PowerShell's mandatory-parameter binder would prompt (or hang) for
# eight values no caller could supply.
# ---------------------------------------------------------------------------

QUESTIONS_CORPUS_PARAMETERS = (
    "QuestionsCorpusPath",
    "QuestionsCorpusSha256",
    "QuestionsCorpusRecordCount",
    "QuestionsCorpusBytes",
    "QuestionsCorpusSnapshotId",
    "QuestionsCorpusSourceIdentity",
    "QuestionsCorpusSourceSha256",
    "QuestionsCorpusSourceRecordCount",
)

_SHA_A = "b7b4eedf72a87ab8fbc82ff51b658cd4dc0f08cb33426aee013e97814edae232"
_SHA_B = "4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28"


def _packager_mandatory_parameters() -> set[str]:
    """Parse the packager's ACTUAL [Parameter(Mandatory = $true)] declarations.

    Substring-matching '$QuestionsCorpusX' would pass even if every Mandatory
    attribute were deleted, because the packager references those variables all
    through its body. The forwarding contract's whole premise is that they are
    mandatory, so this must read the declarations.
    """
    packager = (REPO_ROOT / "scripts" / "release" / "package-release-image.ps1").read_text(
        encoding="utf-8"
    )
    param_block = packager[packager.index("param("):packager.index("$ErrorActionPreference")]
    declared = re.findall(
        r"\[Parameter\(\s*Mandatory\s*=\s*\$true\s*\)\]\s*\[[^\]]+\]\s*\$([A-Za-z0-9_]+)",
        param_block,
    )
    return {name for name in declared if name in QUESTIONS_CORPUS_PARAMETERS}


def _corpus_args(tmp_path, **overrides) -> list[str]:
    corpus = tmp_path / "questions.json"
    if not corpus.exists():
        corpus.write_text("[]", encoding="utf-8")
    values = {
        "QuestionsCorpusPath": str(corpus),
        "QuestionsCorpusSha256": _SHA_A,
        "QuestionsCorpusRecordCount": "41591",
        "QuestionsCorpusBytes": "71534621",
        "QuestionsCorpusSnapshotId": "snapshot-test-001",
        "QuestionsCorpusSourceIdentity": _SHA_B,
        "QuestionsCorpusSourceSha256": _SHA_B,
        "QuestionsCorpusSourceRecordCount": "41591",
    }
    values.update(overrides)
    args: list[str] = []
    for key, value in values.items():
        if value is None:
            continue
        args += [f"-{key}", value]
    return args


def test_packager_still_declares_all_eight_corpus_parameters_mandatory():
    # If this ever shrinks, the forwarding contract below must change with it.
    assert _packager_mandatory_parameters() == set(QUESTIONS_CORPUS_PARAMETERS)


def test_coordinator_accepts_all_eight_questions_corpus_parameters():
    content = SCRIPT.read_text(encoding="utf-8")
    param_block = content[content.index("param("):content.index("$ErrorActionPreference")]
    for name in QUESTIONS_CORPUS_PARAMETERS:
        assert f"${name}" in param_block, f"coordinator must accept -{name}"


def test_questions_corpus_parameters_are_not_mandatory_so_nothing_can_prompt():
    # A Mandatory parameter PROMPTS when omitted. On a Production release path
    # an interactive prompt is never acceptable, so presence is enforced by an
    # explicit fail-closed assertion instead of by the parameter binder.
    content = SCRIPT.read_text(encoding="utf-8")
    param_block = content[content.index("param("):content.index("$ErrorActionPreference")]
    for name in QUESTIONS_CORPUS_PARAMETERS:
        line = next(l for l in param_block.splitlines() if f"${name}" in l)
        assert "Mandatory" not in line, f"-{name} must not be Mandatory (would prompt)"
    assert "Assert-QuestionsCorpusParameters" in content


def test_package_app_forwards_all_eight_questions_corpus_parameters():
    content = SCRIPT.read_text(encoding="utf-8")
    start = content.index("$PackageApp = {")
    end = content.index("$PackageStatic = {", start)
    package_app = content[start:end]
    assert "$script:questionsCorpusArgs" in package_app
    assert "$packageAppScript" in package_app
    # The validated array is 8 name/value pairs; the guard must match that.
    assert "-ne 16" in package_app

    # And the array actually built by the validator must name all eight
    # switches -- a count guard alone would survive forwarding only seven.
    validator_start = content.index("function Assert-QuestionsCorpusParameters")
    validator_block = content[validator_start : content.index("\n}", validator_start)]
    returned = set(re.findall(r"'-(QuestionsCorpus[A-Za-z0-9]+)'", validator_block))
    assert returned == set(QUESTIONS_CORPUS_PARAMETERS), (
        f"forwarded switches {sorted(returned)} != {sorted(QUESTIONS_CORPUS_PARAMETERS)}"
    )


def test_corpus_identity_is_validated_before_any_build_or_package_work():
    content = SCRIPT.read_text(encoding="utf-8")
    gate = content.index("Assert-OwnerGate -Provided $OwnerGate")
    validated = content.index("Assert-QuestionsCorpusParameters -RequirePresent")
    build_script = content.index("$buildScript = Join-Path")
    assert gate < validated < build_script, (
        "corpus identity must fail closed after the owner gate but before any "
        "build/package phase wiring"
    )


# SAFETY NOTE for everything below.
#
# Only ONE test in this file passes -Execute together with the CORRECT owner
# gate, and it is the single case that cannot be expressed any other way: a dry
# run deliberately permits omitting the corpus identity entirely, so "missing
# under -Execute" has no dry-run equivalent. Every other malformed-input case is
# exercised through the dry run, which validates whatever is supplied.
#
# That one test asserts the exact fail-closed message. If
# Assert-QuestionsCorpusParameters is ever loosened, reordered or made
# non-fatal, this test fails loudly instead of letting pytest proceed into
# PRECHECK/BUILD_APP. It also uses the example layout, whose hosts are all
# example.invalid, so it cannot reach a real host even then.


def test_execute_blocks_when_corpus_parameters_are_missing():
    result = run_powershell([
        "-ExpectedGitSha", CANDIDATE_SHA, "-LayoutFile", EXAMPLE_LAYOUT,
        "-Execute", "-OwnerGate", "GO_DEPLOY_WITH_BOUNDED_RECOVERY",
    ])
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    # Exact message: proves we aborted at the corpus assertion and nowhere later.
    assert "QuestionsCorpus release identity is incomplete" in combined
    for name in QUESTIONS_CORPUS_PARAMETERS:
        assert name in combined
    # Nothing may have started: no build, package, or Production contact.
    assert "PRECHECK" not in combined
    assert "BUILD_APP" not in combined


def test_only_one_test_crosses_the_owner_gate_in_execute_mode():
    """Pin the safety property described in the note above."""
    text = pathlib.Path(__file__).read_text(encoding="utf-8")
    # Assembled from parts so this detector cannot match its own source line.
    needle = '"-Execute", "-OwnerGate", "' + "GO_DEPLOY_WITH" + '_BOUNDED_RECOVERY"'
    crossing = [line for line in text.splitlines() if needle in line]
    assert len(crossing) == 1, (
        "exactly one test may pass -Execute with the real owner gate; "
        f"found {len(crossing)}: {crossing}"
    )


def test_dry_run_blocks_malformed_corpus_sha256(tmp_path):
    result = run_powershell([
        "-ExpectedGitSha", CANDIDATE_SHA, "-LayoutFile", EXAMPLE_LAYOUT,
    ] + _corpus_args(tmp_path, QuestionsCorpusSha256="not-a-sha"))
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "QuestionsCorpus release identity is invalid" in combined
    assert "QuestionsCorpusSha256" in combined


def test_dry_run_blocks_non_numeric_record_count(tmp_path):
    result = run_powershell([
        "-ExpectedGitSha", CANDIDATE_SHA, "-LayoutFile", EXAMPLE_LAYOUT,
    ] + _corpus_args(tmp_path, QuestionsCorpusRecordCount="41,591"))
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "QuestionsCorpus release identity is invalid" in combined
    assert "QuestionsCorpusRecordCount" in combined


def test_dry_run_blocks_malformed_source_identity(tmp_path):
    result = run_powershell([
        "-ExpectedGitSha", CANDIDATE_SHA, "-LayoutFile", EXAMPLE_LAYOUT,
    ] + _corpus_args(tmp_path, QuestionsCorpusSourceIdentity="not-a-sha"))
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "QuestionsCorpus release identity is invalid" in combined
    assert "QuestionsCorpusSourceIdentity" in combined


def test_dry_run_blocks_snapshot_id_that_is_a_path_or_filename(tmp_path):
    for bad in ("releases/snap.json", "snapshot.json", "a\\b"):
        result = run_powershell([
            "-ExpectedGitSha", CANDIDATE_SHA, "-LayoutFile", EXAMPLE_LAYOUT,
        ] + _corpus_args(tmp_path, QuestionsCorpusSnapshotId=bad))
        assert result.returncode != 0, bad
        assert "QuestionsCorpusSnapshotId" in (result.stdout + result.stderr), bad


def test_dry_run_blocks_values_that_would_be_parsed_as_switches(tmp_path):
    # A value beginning with '-' would be forwarded verbatim and bound by the
    # child as a switch, leaving a mandatory parameter unbound -- which is
    # exactly how the packager's binder could still be made to prompt.
    result = run_powershell([
        "-ExpectedGitSha", CANDIDATE_SHA, "-LayoutFile", EXAMPLE_LAYOUT,
    ] + _corpus_args(tmp_path, QuestionsCorpusSnapshotId="-Verbose"))
    assert result.returncode != 0
    assert "QuestionsCorpusSnapshotId" in (result.stdout + result.stderr)


def test_dry_run_blocks_missing_corpus_file(tmp_path):
    missing = tmp_path / "absent-questions.json"
    result = run_powershell([
        "-ExpectedGitSha", CANDIDATE_SHA, "-LayoutFile", EXAMPLE_LAYOUT,
    ] + _corpus_args(tmp_path, QuestionsCorpusPath=str(missing)))
    assert result.returncode != 0
    # Exact fail-closed message, not a raw ItemNotFoundException: asserting only
    # a nonzero exit would also pass on code where the parameter does not exist.
    assert "must resolve to an existing regular file" in (result.stdout + result.stderr)


def test_dry_run_still_works_with_no_corpus_parameters():
    result = run_powershell(["-ExpectedGitSha", CANDIDATE_SHA, "-LayoutFile", EXAMPLE_LAYOUT])
    assert result.returncode == 0, result.stdout + result.stderr
    payload = _last_json(result.stdout)
    assert payload["questions_corpus_parameters_supplied"] is False
    assert payload["questions_corpus_parameter_count"] == 8


def test_dry_run_reports_supplied_corpus_parameters(tmp_path):
    result = run_powershell(
        ["-ExpectedGitSha", CANDIDATE_SHA, "-LayoutFile", EXAMPLE_LAYOUT]
        + _corpus_args(tmp_path)
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = _last_json(result.stdout)
    assert payload["questions_corpus_parameters_supplied"] is True
    assert payload["dry_run"] is True


def test_dry_run_surfaces_a_corpus_typo_instead_of_deferring_it(tmp_path):
    # Catching this in the dry run avoids discovering it 1800s into BUILD_APP.
    result = run_powershell(
        ["-ExpectedGitSha", CANDIDATE_SHA, "-LayoutFile", EXAMPLE_LAYOUT]
        + _corpus_args(tmp_path, QuestionsCorpusSourceSha256="deadbeef")
    )
    assert result.returncode != 0
    assert "QuestionsCorpus release identity is invalid" in (result.stdout + result.stderr)
