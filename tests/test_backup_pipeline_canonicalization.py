"""Deterministic contract tests for the canonical Production backup source."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tarfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_HELPER = ROOT / "ops" / "backup" / "remote" / "make_site_archive.sh"
BACKUP_SCRIPT = ROOT / "ops" / "backup" / "linux" / "backup.sh"
PROPAGATION_SCRIPT = ROOT / "ops" / "backup" / "install-production-backup-scripts.ps1"


def _git_bash() -> str | None:
    """Return a working Bash with GNU tar where the Windows host has WSL absent."""

    candidates = [shutil.which("bash")]
    if os.name == "nt":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        candidates.extend(
            [
                str(Path(program_files) / "Git" / "bin" / "bash.exe"),
                r"C:\Program Files\Git\bin\bash.exe",
            ]
        )
    for candidate in candidates:
        if not candidate or not Path(candidate).exists():
            continue
        probe = subprocess.run(
            [candidate, "-lc", "command -v tar && tar --version | head -n 1"],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode == 0 and "tar" in probe.stdout.lower():
            return candidate
    return None


def _posix_path(path: Path) -> str:
    value = path.as_posix()
    if os.name == "nt" and len(value) >= 2 and value[1] == ":":
        return f"/{value[0].lower()}{value[2:]}"
    return value


def _run_archive(root: Path, output: Path) -> subprocess.CompletedProcess[str]:
    bash = _git_bash()
    if bash is None:
        pytest.skip("A working Bash/GNU tar runtime is unavailable")
    env = os.environ.copy()
    env["GO_ODYSSEY_BACKUP_ROOT"] = _posix_path(root)
    return subprocess.run(
        [bash, _posix_path(ARCHIVE_HELPER), _posix_path(output)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _members(archive: Path) -> set[str]:
    with tarfile.open(archive, mode="r:gz") as handle:
        return {member.name.lstrip("./") for member in handle.getmembers()}


def test_archive_excludes_protected_directories_and_preserves_site_content(tmp_path: Path) -> None:
    (tmp_path / ".e9-rollout-backups" / "nested").mkdir(parents=True)
    (tmp_path / ".shadow-judging-backups" / "nested").mkdir(parents=True)
    (tmp_path / "ordinary").mkdir()
    (tmp_path / ".e9-rollout-backups" / "nested" / "private.json").write_text("private", encoding="utf-8")
    (tmp_path / ".shadow-judging-backups" / "nested" / "private.json").write_text("private", encoding="utf-8")
    (tmp_path / "ordinary" / ".e9-rollout-backups").write_text("ordinary", encoding="utf-8")
    (tmp_path / "normal-site.txt").write_text("normal", encoding="utf-8")
    (tmp_path / "questions.json").write_text("[]", encoding="utf-8")
    archive = tmp_path.parent / "site.tar.gz"

    result = _run_archive(tmp_path, archive)

    assert result.returncode == 0, result.stderr
    names = _members(archive)
    assert "normal-site.txt" in names
    assert "questions.json" in names
    assert "ordinary/.e9-rollout-backups" in names
    assert all(not name.startswith(".e9-rollout-backups/") for name in names)
    assert all(not name.startswith(".shadow-judging-backups/") for name in names)


@pytest.mark.skipif(os.name == "nt" or not hasattr(os, "geteuid"), reason="POSIX permission test only")
def test_unreadable_excluded_directory_does_not_fail_archive(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("root can read the synthetic directory")
    protected = tmp_path / ".e9-rollout-backups"
    protected.mkdir()
    (protected / "private.json").write_text("private", encoding="utf-8")
    protected.chmod(0)
    archive = tmp_path.parent / "unreadable-site.tar.gz"
    try:
        result = _run_archive(tmp_path, archive)
    finally:
        protected.chmod(stat.S_IRWXU)
    assert result.returncode == 0, result.stderr


def test_archive_exclusion_contract_is_directory_scoped() -> None:
    source = ARCHIVE_HELPER.read_text(encoding="utf-8")
    assert "--exclude='./.e9-rollout-backups/***'" in source
    assert "--exclude='./.shadow-judging-backups/***'" in source
    assert "--exclude=.e9-rollout-backups" not in source
    assert "--exclude=.shadow-judging-backups" not in source


def test_existing_backup_flow_and_systemd_contract_are_preserved() -> None:
    source = BACKUP_SCRIPT.read_text(encoding="utf-8")
    assert "make_db_dump.sh" in source
    assert "make_site_archive.sh" in source
    assert 'storage cp' in source
    assert "oci.core.BlockstorageClient" in source
    assert "retention" in source

    daily = (ROOT / "ops" / "backup" / "systemd" / "godokro-backup-daily.service").read_text(encoding="utf-8")
    weekly = (ROOT / "ops" / "backup" / "systemd" / "godokro-backup-weekly.service").read_text(encoding="utf-8")
    assert "User=ubuntu" in daily and "Group=ubuntu" in daily
    assert "WorkingDirectory=/opt/go-odyssey" in daily
    assert "ExecStart=/opt/go-odyssey/ops/backup/linux/backup.sh daily" in daily
    assert "ExecStart=/opt/go-odyssey/ops/backup/linux/backup.sh weekly" in weekly


def test_propagation_tool_is_sha_guarded_and_fail_closed() -> None:
    source = PROPAGATION_SCRIPT.read_text(encoding="utf-8")
    for required in (
        "ExpectedSourceSha",
        "GO_BACKUP_PROPAGATION",
        "Assert-CompleteWorktreeClean",
        "Get-FileHash",
        "Invoke-BoundedScpUpload",
        "Invoke-BoundedSshCommand",
        'sha256sum -- "$target"',
        "sha256sum --check --strict",
        "systemd-analyze verify",
        "mv -Tf",
        "_backup_pipeline_previous_",
        "remote staging path already exists",
        "systemctl daemon-reload",
        "trap fail_closed EXIT",
    ):
        assert required in source
    assert "git add ." not in source
    assert "git add -A" not in source


def test_propagation_wrong_source_sha_fails_before_remote_access() -> None:
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if pwsh is None:
        pytest.skip("PowerShell is unavailable")
    result = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-File",
            str(PROPAGATION_SCRIPT),
            "-ExpectedSourceSha",
            "0" * 40,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0
    assert "source SHA mismatch" in output
    assert "ssh" not in output.lower()


def test_canonical_config_example_contains_no_runtime_credentials() -> None:
    example = (ROOT / "ops" / "backup" / "backup-config.example.json").read_text(encoding="utf-8")
    assert "<provisioned-by-operator>" in example
    assert "<production-oci-boot-volume-id>" in example
    assert "-----BEGIN" not in example
    assert "password" not in example.lower()
    assert "token" not in example.lower()
