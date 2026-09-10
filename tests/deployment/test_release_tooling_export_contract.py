"""Runtime invocation contracts for the release tooling.

Every ReleaseTooling function a release script calls must be exported, and the
questions-corpus validator must actually run the way the packager invokes it.

Invoke-ProcessWithSeparateOutput was defined in ReleaseTooling.psm1 but omitted
from Export-ModuleMember. package-release-image.ps1 calls it to run the
questions-corpus validator, so real packaging failed with
CommandNotFoundException before any validation could run -- a failure invisible
to every test that did not actually execute the packager.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts" / "release" / "ReleaseTooling.psm1"
RELEASE_SCRIPTS = sorted((ROOT / "scripts" / "release").glob("*.ps1"))

_FUNCTION_DEF = re.compile(r"^function\s+([A-Za-z]+-[A-Za-z0-9]+)", re.M)
_QUOTED_NAME = re.compile(r"'([A-Za-z]+-[A-Za-z0-9]+)'")
_INVOCATION = re.compile(r"(?<![\w-])([A-Za-z]+-[A-Za-z0-9]+)(?=\s|\()")


def _defined_functions(text: str) -> set[str]:
    return set(_FUNCTION_DEF.findall(text))


def _exported_functions(text: str) -> set[str]:
    index = text.index("Export-ModuleMember")
    return set(_QUOTED_NAME.findall(text[index:]))


def test_release_scripts_only_call_exported_module_functions():
    module_text = MODULE.read_text(encoding="utf-8")
    defined = _defined_functions(module_text)
    exported = _exported_functions(module_text)

    unexported_usages: dict[str, list[str]] = {}
    for script in RELEASE_SCRIPTS:
        used = set(_INVOCATION.findall(script.read_text(encoding="utf-8")))
        gap = sorted((used & defined) - exported)
        if gap:
            unexported_usages[script.name] = gap

    assert not unexported_usages, (
        "release scripts call ReleaseTooling functions that are not exported "
        "(they will fail at runtime with CommandNotFoundException): "
        + repr(unexported_usages)
    )


def test_packager_helper_is_exported():
    module_text = MODULE.read_text(encoding="utf-8")
    assert "function Invoke-ProcessWithSeparateOutput" in module_text
    assert "'Invoke-ProcessWithSeparateOutput'" in module_text[
        module_text.index("Export-ModuleMember") :
    ]


def test_every_exported_name_actually_exists():
    module_text = MODULE.read_text(encoding="utf-8")
    defined = _defined_functions(module_text)
    exported = _exported_functions(module_text)
    missing = sorted(exported - defined)
    assert not missing, "exported but undefined: " + repr(missing)


def test_corpus_validator_runs_standalone_the_way_the_packager_invokes_it(tmp_path):
    """package-release-image.ps1 runs the validator BY PATH.

    That puts tools/ on sys.path instead of the repository root, so
    `import tools.content_release_core` raised ModuleNotFoundError, the packager
    captured an empty stdout, and the failure surfaced only as "Questions corpus
    release validation failed closed:" with no diagnosis. The validator must
    resolve its own repo root and work from any working directory.
    """
    import json
    import os
    import subprocess

    validator = ROOT / "tools" / "questions_corpus_validation.py"
    corpus = tmp_path / "questions.json"
    corpus.write_text(
        json.dumps([{"id": 1, "content": "(;GM[1]SZ[19];B[aa])"}], separators=(",", ":")),
        encoding="utf-8",
    )

    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    # Deliberately run from a directory that is NOT the repository root.
    result = subprocess.run(
        ["python", "-B", str(validator), "validate",
         "--corpus-path", str(corpus), "--mode", "REPORT_ONLY"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        check=False,
    )
    assert "ModuleNotFoundError" not in (result.stderr or "")
    assert result.returncode in (0, 2), result.stderr
    assert result.stdout.strip(), "validator must emit its JSON report on stdout"
    payload = json.loads(result.stdout[result.stdout.index("{"):])
    assert "summary" in payload and "gates" in payload


# ---------------------------------------------------------------------------
# New-ReleaseManifestObject must accept both identity shapes its callers pass.
#
# package-release-image.ps1 builds an [ordered]@{} (an OrderedDictionary);
# anything read back through ConvertFrom-Json arrives as a PSCustomObject. The
# field check read only through .PSObject.Properties, which on an
# OrderedDictionary exposes Count/Keys/Values/IsReadOnly and never the entries,
# so every field looked "missing" and real packaging could not produce a
# manifest at all. Unreachable for any test that did not run the packager.
# ---------------------------------------------------------------------------

_VALID_CORPUS_FIELDS = {
    "questions_corpus_sha256": "b" * 64,
    "questions_corpus_record_count": 41591,
    "questions_corpus_bytes": 71534621,
    "questions_corpus_snapshot_id": "snapshot-identity-001",
    "questions_corpus_source_identity": "c" * 64,
    "questions_corpus_source_sha256": "d" * 64,
    "questions_corpus_source_record_count": 41591,
}


def _manifest_probe(identity_expression: str) -> "subprocess.CompletedProcess[str]":
    import subprocess

    script = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{(ROOT / "scripts" / "release" / "ReleaseTooling.psm1").as_posix()}' -Force -DisableNameChecking
$identity = {identity_expression}
$m = New-ReleaseManifestObject `
    -GitSha '{"a" * 40}' -ImageTag 'go-odyssey-app:aaaaaaaa' `
    -ImageId 'sha256:{"e" * 64}' -ArchiveFilename 'x.tar' -ArchiveSha256 '{"f" * 64}' `
    -BuildTimestamp '2026-09-10T00:00:00Z' -BuildMachineIdentityClass 'test' `
    -TargetServiceNames @('app') -ExternalContentRequirements ([ordered]@{{}}) `
    -QuestionsCorpusIdentity $identity -ExpectedHealthEndpoints @('https://example.invalid/healthz') `
    -RollbackImageIdentity ([ordered]@{{}}) -VerificationResult 'test' `
    -DeploymentTimestamp $null -OCIRevision '{"a" * 40}'
$m.questions_corpus_sha256
"""
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        # PowerShell emits localized error text in the console codepage, which is
        # not necessarily UTF-8; decoding must never mask the assertion.
        errors="replace",
        timeout=300,
        check=False,
    )


def _ordered_literal() -> str:
    parts = []
    for key, value in _VALID_CORPUS_FIELDS.items():
        parts.append(f"{key} = {value!r}" if isinstance(value, str) else f"{key} = {value}")
    body = "; ".join(parts).replace("'", "'")
    return "[ordered]@{" + body + "}"


def test_manifest_accepts_ordered_dictionary_identity():
    """The exact shape package-release-image.ps1 passes."""
    result = _manifest_probe(_ordered_literal())
    assert result.returncode == 0, result.stdout + result.stderr
    assert "missing required field" not in (result.stdout + result.stderr)
    assert "b" * 64 in result.stdout


def test_manifest_accepts_pscustomobject_identity():
    """The shape any ConvertFrom-Json round trip produces."""
    result = _manifest_probe("[pscustomobject]" + _ordered_literal()[len("[ordered]"):])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "b" * 64 in result.stdout


def test_manifest_still_rejects_a_missing_corpus_field():
    """Fail-closed behaviour must survive the shape fix."""
    literal = _ordered_literal().replace(
        f"questions_corpus_source_sha256 = '{'d' * 64}'; ", ""
    )
    result = _manifest_probe(literal)
    assert result.returncode != 0
    assert "missing required field" in (result.stdout + result.stderr)
