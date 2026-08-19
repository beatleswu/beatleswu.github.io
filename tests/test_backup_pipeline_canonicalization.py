"""Deterministic contract tests for the canonical Production backup source."""

from __future__ import annotations

import os
import hashlib
import json
import shutil
import stat
import subprocess
import tarfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_HELPER = ROOT / "ops" / "backup" / "remote" / "make_site_archive.sh"
BACKUP_SCRIPT = ROOT / "ops" / "backup" / "linux" / "backup.sh"
PROPAGATION_SCRIPT = ROOT / "ops" / "backup" / "install-production-backup-scripts.ps1"
PREIMAGE_CONTRACT = ROOT / "ops" / "backup" / "production-preimage.json"

# The exclusion set whose gap caused the 2026-08-19T08:50:36Z Production
# backup failure; the reproduction test asserts it still fails on the fixture.
BASELINE_SHA = "d5dce8bffbef966f2ea14e1d010c52a09f813e9c"

# The first canonical propagation installed the backup runtime exactly as it
# stood at BASELINE_SHA; PR #378 then changed make_site_archive.sh. That makes
# BASELINE_SHA the source of the *previous canonical* archive-helper identity
# Production now holds, and the identity a canonical-v1 -> canonical-v2
# propagation has to accept before it may activate anything.
PREVIOUS_CANONICAL_SOURCE_SHA = BASELINE_SHA

ARCHIVE_HELPER_RELATIVE_PATH = "ops/backup/remote/make_site_archive.sh"
ARCHIVE_HELPER_REMOTE_PATH = "/opt/go-odyssey/ops/backup/remote/make_site_archive.sh"
DB_DUMP_REMOTE_PATH = "/opt/go-odyssey/ops/backup/remote/make_db_dump.sh"

REMOTE_TO_RELATIVE_PATH = {
    "/opt/go-odyssey/ops/backup/linux/backup.sh": "ops/backup/linux/backup.sh",
    "/opt/go-odyssey/ops/backup/remote/make_db_dump.sh": "ops/backup/remote/make_db_dump.sh",
    ARCHIVE_HELPER_REMOTE_PATH: ARCHIVE_HELPER_RELATIVE_PATH,
    "/etc/systemd/system/godokro-backup-daily.service": "ops/backup/systemd/godokro-backup-daily.service",
    "/etc/systemd/system/godokro-backup-daily.timer": "ops/backup/systemd/godokro-backup-daily.timer",
    "/etc/systemd/system/godokro-backup-weekly.service": "ops/backup/systemd/godokro-backup-weekly.service",
    "/etc/systemd/system/godokro-backup-weekly.timer": "ops/backup/systemd/godokro-backup-weekly.timer",
}

# The original legacy Production pre-image for the archive helper. Pinned here
# so a future edit cannot quietly reinterpret the old contract fields as
# something other than the identity that predates canonical propagation.
LEGACY_ARCHIVE_HELPER_SHA = "300df554470dcdd4f02af82b7a7da3b61545650c08bad7813bd56d46f0cd5cd6"

# Real archive-helper versions reachable from Git history that were never
# declared as accepted previous canonical identities. Owner review, not
# reachability, is what makes an identity acceptable, so each of these must
# still be rejected as unknown drift.
UNDECLARED_HISTORY_SOURCE_SHAS = (
    "b03e3e427b5332c0724d920bcaeae5974af42910",
    "978ed8a389d721e95c936f6c06bb4b34ba854962",
    "8b910831e039e13500c0d95c2ac85cc00a97223c",
)

# The canonical protected-runtime exclusion contract, as written in EXCLUDES.
PROTECTED_EXCLUSIONS = (
    "'./.e9-rollout-backups'",
    "'./.shadow-judging-backups'",
    "'./releases/.shadow-judging-audit'",
    "'./releases/e9-rollout-audit.jsonl'",
    "'./reward-operations/2026-W28/grant-result.json'",
    "'./reward-operations/w29-c866f611-20260720T055453Z-c001bcd0'",
)

# Synthetic equivalents of every protected class observed in Production. The
# W29-shaped operation id mirrors the owner-gated grant wrapper's naming
# convention; no Production content is used as a fixture.
_OPERATION_DIR = "w29-c866f611-20260720T055453Z-c001bcd0"

PROTECTED_FIXTURES = (
    ".e9-rollout-backups",
    ".shadow-judging-backups",
    "releases/.shadow-judging-audit",
    "releases/e9-rollout-audit.jsonl",
    "reward-operations/2026-W28/grant-result.json",
    f"reward-operations/{_OPERATION_DIR}",
)

# Future-looking readable reward content. Both names would have been swallowed
# by the speculative wildcards this contract deliberately does not use:
# `w[0-9]*-*Z-*` would have matched the operation directory, and
# `*/grant-result.json` the period-keyed file. Under the literal policy they
# must survive, which is what makes the policy observable in the archive rather
# than only in the source text.
_FUTURE_OPERATION_DIR = "w30-example-20260820T000000Z-example"
FUTURE_READABLE_FIXTURES = (
    f"reward-operations/{_FUTURE_OPERATION_DIR}/readable.json",
    "reward-operations/2026-W30/grant-result.json",
)

# Negative controls: unrelated content the exclusion scope must never remove.
PRESERVED_FIXTURES = (
    "normal-site.txt",
    "questions.json",
    "releases/normal-release-file.txt",
    "reward-operations/normal-readable-operation.json",
    "reward-operations/2026-W28/snapshot.json",
    "reward-operations/2026-W28/preview.json",
) + FUTURE_READABLE_FIXTURES


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
        return {member.name[2:] if member.name.startswith("./") else member.name for member in handle.getmembers()}


def _member_bytes(archive: Path, wanted: str) -> bytes:
    with tarfile.open(archive, mode="r:gz") as handle:
        for member in handle.getmembers():
            name = member.name[2:] if member.name.startswith("./") else member.name
            if name == wanted:
                extracted = handle.extractfile(member)
                assert extracted is not None
                return extracted.read()
    raise AssertionError(f"archive member not found: {wanted}")


def _powershell() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def _git_status() -> str:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _current_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _render_remote_script(tmp_path: Path) -> tuple[str, Path]:
    pwsh = _powershell()
    if pwsh is None:
        pytest.skip("PowerShell is unavailable")
    if _git_status():
        pytest.skip("remote-script rendering requires a clean worktree")
    rendered = tmp_path / "remote-propagation.sh"
    result = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PROPAGATION_SCRIPT),
            "-ExpectedSourceSha",
            _current_head(),
            "-RenderRemoteScriptPath",
            str(rendered),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["mode"] == "plan"
    assert report["rendered_remote_script"] == str(rendered)
    return result.stdout, rendered


@dataclass(frozen=True)
class _RemoteIdentity:
    sha256: str
    owner: str
    group: str
    mode: str
    file_type: str = "regular file"
    is_symlink: bool = False


def _preimage_accepts(
    approved: _RemoteIdentity,
    canonical: _RemoteIdentity,
    actual: _RemoteIdentity,
    accepted_previous: tuple[_RemoteIdentity, ...] = (),
) -> bool:
    """Mirror the explicit remote gate for deterministic contract tests.

    The remote gate accepts exactly three classes of identity: the original
    legacy Production pre-image, any explicitly declared previous canonical
    identity, and the canonical identity being installed. Every class is an
    exact SHA256 + owner + group + mode + file-type match.
    """

    if actual.is_symlink or actual.file_type != "regular file":
        return False
    return actual == approved or actual in accepted_previous or actual == canonical


def _git_blob_sha256(commit_sha: str, relative_path: str) -> str:
    """SHA256 of a tracked file's exact bytes at a commit, read-only."""

    result = subprocess.run(
        ["git", "cat-file", "blob", f"{commit_sha}:{relative_path}"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    return hashlib.sha256(result.stdout).hexdigest()


def _contract_targets() -> dict:
    contract = json.loads(PREIMAGE_CONTRACT.read_text(encoding="utf-8"))
    return {entry["remote_path"]: entry for entry in contract["targets"]}


def _declared_identity(entry: dict) -> _RemoteIdentity:
    return _RemoteIdentity(
        entry["sha256"],
        entry["owner"],
        entry["group"],
        entry["mode"].lstrip("0") or "0",
        entry["file_type"],
    )


def _accepted_previous(entry: dict) -> tuple[_RemoteIdentity, ...]:
    return tuple(_declared_identity(item) for item in entry.get("accepted_previous_canonical", []))


def _canonical_identity(remote_path: str, owner: str, group: str, mode: str) -> _RemoteIdentity:
    local = ROOT / REMOTE_TO_RELATIVE_PATH[remote_path]
    return _RemoteIdentity(hashlib.sha256(local.read_bytes()).hexdigest(), owner, group, mode)


def _archive_helper_gate() -> tuple[_RemoteIdentity, tuple[_RemoteIdentity, ...], _RemoteIdentity]:
    """(legacy pre-image, declared previous canonical, current canonical)."""

    entry = _contract_targets()[ARCHIVE_HELPER_REMOTE_PATH]
    return (
        _declared_identity(entry),
        _accepted_previous(entry),
        _canonical_identity(ARCHIVE_HELPER_REMOTE_PATH, "ubuntu", "ubuntu", "644"),
    )


def test_archive_excludes_protected_directories_and_preserves_site_content(tmp_path: Path) -> None:
    (tmp_path / ".e9-rollout-backups" / "nested").mkdir(parents=True)
    (tmp_path / ".shadow-judging-backups" / "nested").mkdir(parents=True)
    (tmp_path / "ordinary").mkdir()
    (tmp_path / ".e9-rollout-backups" / "nested" / "private.json").write_text("private", encoding="utf-8")
    (tmp_path / ".shadow-judging-backups" / "nested" / "private.json").write_text("private", encoding="utf-8")
    (tmp_path / "ordinary" / ".e9-rollout-backups").write_text("ordinary", encoding="utf-8")
    (tmp_path / "ordinary" / ".shadow-judging-backups").write_text("ordinary", encoding="utf-8")
    (tmp_path / "normal-site.txt").write_text("normal", encoding="utf-8")
    (tmp_path / "questions.json").write_text("[]", encoding="utf-8")

    # Release- and reward-scoped protected artifacts.
    (tmp_path / "releases" / ".shadow-judging-audit").mkdir(parents=True)
    (tmp_path / "releases" / ".shadow-judging-audit" / "audit.jsonl").write_text("audit", encoding="utf-8")
    (tmp_path / "releases" / "e9-rollout-audit.jsonl").write_text("audit", encoding="utf-8")
    (tmp_path / "releases" / "normal-release-file.txt").write_text("release", encoding="utf-8")
    operation = tmp_path / "reward-operations" / _OPERATION_DIR
    operation.mkdir(parents=True)
    (operation / "grant-execution-evidence.jsonl").write_text("evidence", encoding="utf-8")
    (operation / "operation-manifest.json").write_text("{}", encoding="utf-8")
    period = tmp_path / "reward-operations" / "2026-W28"
    period.mkdir(parents=True)
    (period / "grant-result.json").write_text("grant", encoding="utf-8")
    (period / "snapshot.json").write_text("snapshot", encoding="utf-8")
    (period / "preview.json").write_text("preview", encoding="utf-8")
    (tmp_path / "reward-operations" / "normal-readable-operation.json").write_text("{}", encoding="utf-8")
    future_operation = tmp_path / "reward-operations" / _FUTURE_OPERATION_DIR
    future_operation.mkdir(parents=True)
    (future_operation / "readable.json").write_text("{}", encoding="utf-8")
    future_period = tmp_path / "reward-operations" / "2026-W30"
    future_period.mkdir(parents=True)
    (future_period / "grant-result.json").write_text("{}", encoding="utf-8")

    archive = tmp_path.parent / "site.tar.gz"

    result = _run_archive(tmp_path, archive)

    assert result.returncode == 0, result.stderr
    names = _members(archive)
    assert "ordinary/.e9-rollout-backups" in names
    assert "ordinary/.shadow-judging-backups" in names
    for protected in PROTECTED_FIXTURES:
        assert protected not in names, protected
        assert all(not name.startswith(f"{protected}/") for name in names), protected
    for preserved in PRESERVED_FIXTURES:
        assert preserved in names, preserved
    assert _member_bytes(archive, "questions.json") == b"[]"


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
    for entry in PROTECTED_EXCLUSIONS:
        assert f"  {entry}\n" in source, entry
    assert "'./.e9-rollout-backups/***'" not in source
    assert "'./.shadow-judging-backups/***'" not in source
    assert "--exclude=.e9-rollout-backups" not in source
    assert "--exclude=.shadow-judging-backups" not in source


def test_archive_does_not_use_forbidden_robustness_shortcuts() -> None:
    """The archive must stay fail-closed and unprivileged.

    A backup that silently drops unreadable files, or that reads them by
    escalating privilege, is a worse outcome than a loud failure.
    """

    source = ARCHIVE_HELPER.read_text(encoding="utf-8")
    assert "--ignore-failed-read" not in source
    assert "sudo" not in source
    assert "--one-file-system" not in source
    # tar itself must remain the fail-closed backstop, not `|| true`.
    assert "|| true" not in source
    assert "set -euo pipefail" in source


def test_reward_operations_tree_is_not_excluded_wholesale() -> None:
    """reward-operations holds backup-user-readable evidence that must persist.

    Only the artifacts written by the owner-gated root grant path are dropped;
    excluding the whole tree would newly discard restorable operational
    evidence that was never the cause of the failure.
    """

    source = ARCHIVE_HELPER.read_text(encoding="utf-8")
    assert "\n  './reward-operations'\n" not in source
    assert "\n  './reward-operations/'\n" not in source
    assert "\n  'reward-operations'\n" not in source
    assert "\n  './reward-operations/*'\n" not in source


def test_reward_exclusions_are_literal_not_speculative() -> None:
    """reward-operations entries must name observed artifacts, not predict names.

    Operation directory names come from a per-wrapper ValidateSet literal, so no
    pattern can safely anticipate them. A wildcard here would silently drop
    reward content nobody has inspected; an unmatched protected artifact is
    caught by the preflight instead, and added to the contract on review.
    """

    reward_entries = [entry for entry in PROTECTED_EXCLUSIONS if "reward-operations" in entry]
    assert reward_entries, "the reward exclusion contract must not be empty"
    for entry in reward_entries:
        for wildcard in ("*", "?", "["):
            assert wildcard not in entry, f"speculative wildcard {wildcard!r} in {entry}"


def test_future_looking_readable_reward_content_is_preserved(tmp_path: Path) -> None:
    """Prove the literal policy in the archive, not just in the source text.

    Absence of wildcard characters is a source-level claim. This runs the real
    archive helper over reward content named exactly the way the rejected
    wildcards would have matched, and requires both files to come back out of
    the tar.
    """

    operation = tmp_path / "reward-operations" / _FUTURE_OPERATION_DIR
    operation.mkdir(parents=True)
    (operation / "readable.json").write_text('{"future": true}', encoding="utf-8")
    period = tmp_path / "reward-operations" / "2026-W30"
    period.mkdir(parents=True)
    (period / "grant-result.json").write_text('{"future": true}', encoding="utf-8")
    (tmp_path / "questions.json").write_text("[]", encoding="utf-8")
    archive = tmp_path.parent / "future-reward-site.tar.gz"

    result = _run_archive(tmp_path, archive)

    assert result.returncode == 0, result.stderr
    names = _members(archive)
    for preserved in FUTURE_READABLE_FIXTURES:
        assert preserved in names, preserved
        assert _member_bytes(archive, preserved) == b'{"future": true}'


_POSIX_IMAGE = "debian:bookworm-slim"

# Root-owned 700 directories / 600 files, exactly as Production presents them.
_POSIX_FIXTURE_SETUP = f"""
set -eu
mkdir -p /site/.e9-rollout-backups/nested /site/.shadow-judging-backups/nested /site/ordinary
mkdir -p /site/releases/.shadow-judging-audit
mkdir -p /site/reward-operations/2026-W28
mkdir -p /site/reward-operations/{_OPERATION_DIR}
mkdir -p /site/reward-operations/{_FUTURE_OPERATION_DIR}
mkdir -p /site/reward-operations/2026-W30
printf protected > /site/.e9-rollout-backups/nested/private.json
printf protected > /site/.shadow-judging-backups/nested/private.json
printf ordinary > /site/ordinary/.e9-rollout-backups
printf ordinary > /site/ordinary/.shadow-judging-backups
printf audit > /site/releases/.shadow-judging-audit/audit.jsonl
printf audit > /site/releases/e9-rollout-audit.jsonl
printf grant > /site/reward-operations/2026-W28/grant-result.json
printf evidence > /site/reward-operations/{_OPERATION_DIR}/grant-execution-evidence.jsonl
printf manifest > /site/reward-operations/{_OPERATION_DIR}/operation-manifest.json
printf release > /site/releases/normal-release-file.txt
printf readable > /site/reward-operations/normal-readable-operation.json
printf future > /site/reward-operations/{_FUTURE_OPERATION_DIR}/readable.json
printf future > /site/reward-operations/2026-W30/grant-result.json
printf snapshot > /site/reward-operations/2026-W28/snapshot.json
printf preview > /site/reward-operations/2026-W28/preview.json
printf normal > /site/normal-site.txt
printf '[]' > /site/questions.json
chown -R root:root /site/.e9-rollout-backups /site/.shadow-judging-backups
chown -R root:root /site/releases/.shadow-judging-audit
chown -R root:root /site/reward-operations/{_OPERATION_DIR}
chown root:root /site/releases/e9-rollout-audit.jsonl
chown root:root /site/reward-operations/2026-W28/grant-result.json
chmod 700 /site/.e9-rollout-backups /site/.shadow-judging-backups
chmod 700 /site/releases/.shadow-judging-audit
chmod 700 /site/reward-operations/{_OPERATION_DIR}
chmod 600 /site/releases/e9-rollout-audit.jsonl
chmod 600 /site/reward-operations/2026-W28/grant-result.json
chmod 755 /site /site/ordinary /site/releases /site/reward-operations /site/reward-operations/2026-W28
chmod 755 /site/reward-operations/{_FUTURE_OPERATION_DIR} /site/reward-operations/2026-W30
chmod 644 /site/reward-operations/{_FUTURE_OPERATION_DIR}/readable.json
chmod 644 /site/reward-operations/2026-W30/grant-result.json
chmod 644 /site/normal-site.txt /site/questions.json
chmod 644 /site/ordinary/.e9-rollout-backups /site/ordinary/.shadow-judging-backups
chmod 644 /site/releases/normal-release-file.txt
chmod 644 /site/reward-operations/normal-readable-operation.json
chmod 644 /site/reward-operations/2026-W28/snapshot.json /site/reward-operations/2026-W28/preview.json
"""


def _docker_or_skip() -> str:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker is unavailable for the isolated POSIX permission test")
    return docker


@contextmanager
def _posix_site(docker: str, extra_setup: str = ""):
    """Yield a volume mount holding the protected-path fixture, built as root."""

    volume = f"backup-archive-posix-{uuid.uuid4().hex}"
    created = subprocess.run([docker, "volume", "create", volume], capture_output=True, text=True, check=False)
    assert created.returncode == 0, created.stdout + created.stderr
    try:
        setup_result = subprocess.run(
            [docker, "run", "--rm", "--user", "0:0", "-v", f"{volume}:/site", _POSIX_IMAGE,
             "sh", "-ceu", _POSIX_FIXTURE_SETUP + extra_setup],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert setup_result.returncode == 0, setup_result.stdout + setup_result.stderr
        yield f"{volume}:/site"
    finally:
        subprocess.run([docker, "volume", "rm", "-f", volume], capture_output=True, text=True, check=False)


def _run_archive_as_nonroot(docker: str, mount: str, script: str) -> subprocess.CompletedProcess[str]:
    """Run an archive helper inside the fixture as an unprivileged user."""

    return subprocess.run(
        [docker, "run", "--rm", "--user", "65532:65532", "-v", mount, "-v", f"{ROOT.as_posix()}:/repo:ro",
         _POSIX_IMAGE, "sh", "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_current_production_failure_is_reproduced_by_baseline_exclusions(tmp_path: Path) -> None:
    """The fixture must actually reproduce the reported Production failure.

    Without this, a passing fixed-path test proves nothing: it could be green
    because the fixture never exercised the protected paths at all.
    """

    docker = _docker_or_skip()
    # Bytes, not text: the exclusion list carries a CJK pattern that a non-UTF-8
    # default console codec cannot decode.
    baseline = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{BASELINE_SHA}:ops/backup/remote/make_site_archive.sh"],
        capture_output=True,
        check=False,
    )
    if baseline.returncode != 0:
        pytest.skip(f"Baseline {BASELINE_SHA} is unavailable in this clone")
    baseline_script = tmp_path / "baseline_make_site_archive.sh"
    baseline_script.write_bytes(baseline.stdout.replace(b"\r\n", b"\n"))

    with _posix_site(docker) as mount:
        result = subprocess.run(
            [docker, "run", "--rm", "--user", "65532:65532", "-v", mount,
             "-v", f"{tmp_path.as_posix()}:/baseline:ro", _POSIX_IMAGE, "sh", "-c",
             "export GO_ODYSSEY_BACKUP_ROOT=/site; bash /baseline/baseline_make_site_archive.sh /tmp/site.tar.gz"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    assert result.returncode != 0, "baseline exclusions unexpectedly succeeded: " + result.stdout + result.stderr
    combined = result.stdout + result.stderr
    assert "Permission denied" in combined
    # Every newly exposed path must be implicated, and the already-fixed roots
    # must not be -- that is what makes this the *current* failure class.
    assert "./releases/.shadow-judging-audit" in combined
    assert "./releases/e9-rollout-audit.jsonl" in combined
    assert "./reward-operations/2026-W28/grant-result.json" in combined
    assert f"./reward-operations/{_OPERATION_DIR}" in combined
    assert "./.e9-rollout-backups" not in combined
    assert "./.shadow-judging-backups" not in combined


def test_unreadable_protected_directory_real_posix_test() -> None:
    docker = _docker_or_skip()
    run = """
set -eu
export GO_ODYSSEY_BACKUP_ROOT=/site
/repo/ops/backup/remote/make_site_archive.sh /tmp/site.tar.gz
tar -tzf /tmp/site.tar.gz
"""
    with _posix_site(docker) as mount:
        result = _run_archive_as_nonroot(docker, mount, run)

    assert result.returncode == 0, result.stdout + result.stderr
    names = {line[2:] if line.startswith("./") else line for line in result.stdout.splitlines()}
    names = {name.rstrip("/") for name in names}
    for protected in PROTECTED_FIXTURES:
        assert protected not in names, protected
        assert not any(name.startswith(f"{protected}/") for name in names), protected
    for preserved in PRESERVED_FIXTURES:
        assert preserved in names, preserved
    # Same-named ordinary files elsewhere in the tree must survive.
    assert "ordinary/.e9-rollout-backups" in names
    assert "ordinary/.shadow-judging-backups" in names


def test_uncovered_unreadable_path_fails_before_tar() -> None:
    """A newly introduced protected path must fail fast, not after ~7 minutes."""

    docker = _docker_or_skip()
    extra = """
mkdir -p /site/brand-new-protected
printf secret > /site/brand-new-protected/secret.json
chown -R root:root /site/brand-new-protected
chmod 700 /site/brand-new-protected
"""
    run = """
export GO_ODYSSEY_BACKUP_ROOT=/site
/repo/ops/backup/remote/make_site_archive.sh /tmp/site.tar.gz
rc=$?
echo "EXIT=$rc"
if [ -e /tmp/site.tar.gz ]; then echo ARCHIVE_BUILT; else echo NO_ARCHIVE_BUILT; fi
"""
    with _posix_site(docker, extra_setup=extra) as mount:
        result = _run_archive_as_nonroot(docker, mount, run)

    combined = result.stdout + result.stderr
    assert "EXIT=1" in combined, combined
    # The whole point: it must abort *before* building the archive.
    assert "NO_ARCHIVE_BUILT" in combined, combined
    assert "./brand-new-protected" in combined, combined
    assert "not covered by the canonical exclusions" in combined, combined


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
        "production-preimage.json",
        "PreimageSha256",
        "PreimageOwner",
        "PreimageGroup",
        "PreimageMode",
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
        "REMOTE_PREIMAGE_MATCH=YES",
    ):
        assert required in source
    assert "activated_paths=(" not in source
    assert "[[" not in source
    assert "for ((" not in source
    assert "git add ." not in source
    assert "git add -A" not in source


def test_remote_preimage_contract_is_complete_and_secret_free() -> None:
    contract = json.loads(PREIMAGE_CONTRACT.read_text(encoding="utf-8"))
    targets = contract["targets"]
    assert len(targets) == 7
    assert {entry["file_type"] for entry in targets} == {"regular file"}
    for entry in targets:
        assert len(entry["sha256"]) == 64
        assert entry["owner"] and entry["group"]
        assert entry["mode"].isdigit()
    raw = PREIMAGE_CONTRACT.read_text(encoding="utf-8").lower()
    assert "password" not in raw
    assert "token" not in raw
    assert "private key" not in raw


def test_remote_script_is_posix_sh_and_preimage_gate_precedes_activation(tmp_path: Path) -> None:
    _, rendered = _render_remote_script(tmp_path)
    source = rendered.read_text(encoding="utf-8")
    shell = shutil.which("sh")
    if shell is None:
        bash = _git_bash()
        if bash is None:
            pytest.skip("POSIX sh is unavailable")
        command = [bash, "--posix", "-n", str(rendered)]
    else:
        command = [shell, "-n", str(rendered)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "activated_paths=(" not in source
    assert "[[" not in source
    assert "for ((" not in source
    assert source.index("REMOTE_PREIMAGE_MATCH=YES") < source.index("activated_1=1")
    assert source.count("remote pre-image identity mismatch") == 7


def test_remote_preimage_drift_contract_fails_closed() -> None:
    approved = _RemoteIdentity("approved", "ubuntu", "ubuntu", "775")
    canonical = _RemoteIdentity("canonical", "ubuntu", "ubuntu", "755")
    assert _preimage_accepts(approved, canonical, approved)
    assert _preimage_accepts(approved, canonical, canonical)

    assert not _preimage_accepts(approved, canonical, _RemoteIdentity("wrong-script", "ubuntu", "ubuntu", "775"))
    assert not _preimage_accepts(approved, canonical, _RemoteIdentity("wrong-unit", "root", "root", "644"))
    assert not _preimage_accepts(approved, canonical, _RemoteIdentity("approved", "ubuntu", "ubuntu", "775", is_symlink=True))
    assert not _preimage_accepts(approved, canonical, _RemoteIdentity("approved", "ubuntu", "ubuntu", "744"))
    assert not _preimage_accepts(approved, canonical, _RemoteIdentity("approved", "root", "ubuntu", "775"))
    assert not _preimage_accepts(approved, canonical, _RemoteIdentity("unknown", "nobody", "nogroup", "666"))


def test_propagation_plan_mode_uses_exact_head_and_does_not_contact_remote() -> None:
    pwsh = _powershell()
    if pwsh is None:
        pytest.skip("PowerShell is unavailable")
    if _git_status():
        pytest.skip("plan-mode execution requires a clean worktree")
    result = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PROPAGATION_SCRIPT),
            "-ExpectedSourceSha",
            _current_head(),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["mode"] == "plan"
    assert report["source_sha"] == _current_head()
    assert report["remote_execution_shell"] == "sh -s"
    assert len(report["files"]) == 7
    for item in report["files"]:
        local = ROOT / item["relative_path"]
        expected = __import__("hashlib").sha256(local.read_bytes()).hexdigest()
        assert item["sha256"] == expected
    assert "ssh" not in result.stdout.lower()
    assert "scp" not in result.stdout.lower()


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
    parsed = json.loads(example)
    assert set(parsed) == {
        "gcs_bucket",
        "oci_boot_volume_id",
        "oci_compartment_id",
        "oci_weekly_retention",
        "oci_backup_prefix",
    }
    assert "gcs_retention_days" not in example
    assert "<production-oci-boot-volume-id>" in example
    assert "-----BEGIN" not in example
    assert "password" not in example.lower()
    assert "token" not in example.lower()


def test_preimage_contract_declares_only_the_reviewed_sequential_transition() -> None:
    contract = json.loads(PREIMAGE_CONTRACT.read_text(encoding="utf-8"))
    assert contract["schema_version"] == 2

    targets = _contract_targets()
    assert len(targets) == 7

    # The original legacy Production pre-image keeps its original meaning; the
    # sequential transition is expressed only by the new explicit list.
    archive = targets[ARCHIVE_HELPER_REMOTE_PATH]
    assert archive["sha256"] == LEGACY_ARCHIVE_HELPER_SHA
    assert (archive["owner"], archive["group"], archive["mode"]) == ("ubuntu", "ubuntu", "664")

    declaring = [path for path, entry in targets.items() if entry.get("accepted_previous_canonical")]
    assert declaring == [ARCHIVE_HELPER_REMOTE_PATH]

    # The six unchanged runtime targets already match the canonical identity
    # and must not carry an unnecessary transition entry.
    for path, entry in targets.items():
        if path != ARCHIVE_HELPER_REMOTE_PATH:
            assert "accepted_previous_canonical" not in entry

    previous = archive["accepted_previous_canonical"]
    assert len(previous) == 1
    assert previous[0]["source_sha"] == PREVIOUS_CANONICAL_SOURCE_SHA
    assert previous[0]["sha256"] == _git_blob_sha256(
        PREVIOUS_CANONICAL_SOURCE_SHA, ARCHIVE_HELPER_RELATIVE_PATH
    )
    assert previous[0]["owner"] == "ubuntu"
    assert previous[0]["group"] == "ubuntu"
    assert previous[0]["mode"] == "644"
    assert previous[0]["file_type"] == "regular file"


def test_accepted_previous_canonical_identities_are_verifiable_history() -> None:
    declared_any = False
    for remote_path, entry in _contract_targets().items():
        relative = REMOTE_TO_RELATIVE_PATH[remote_path]
        for previous in entry.get("accepted_previous_canonical", []):
            declared_any = True
            # An accepted identity must name an exact commit and match that
            # commit's bytes -- a declared hash is never taken on trust.
            assert len(previous["source_sha"]) == 40
            assert previous["sha256"] == _git_blob_sha256(previous["source_sha"], relative)
            # ...and it must genuinely be a *previous* identity, not a second
            # spelling of the canonical identity being installed.
            assert previous["sha256"] != hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    assert declared_any


def test_sequential_canonical_transition_is_accepted() -> None:
    """CURRENT_PRODUCTION=d5dce8 helper, NEW_SOURCE=bb6f helper -> accepted."""

    legacy, previous, canonical = _archive_helper_gate()
    assert len(previous) == 1

    current_production = _RemoteIdentity(
        _git_blob_sha256(PREVIOUS_CANONICAL_SOURCE_SHA, ARCHIVE_HELPER_RELATIVE_PATH),
        "ubuntu",
        "ubuntu",
        "644",
    )
    assert current_production != canonical, "the transition under test must be a real change"

    preimage_accepted = _preimage_accepts(legacy, canonical, current_production, previous)
    assert preimage_accepted is True, "PREIMAGE_ACCEPTED"
    # Activation is gated on exactly this decision and nothing else.
    assert preimage_accepted is True, "ACTIVATION_ALLOWED"


def test_legacy_transition_and_idempotent_rerun_remain_accepted() -> None:
    legacy, previous, canonical = _archive_helper_gate()
    assert _preimage_accepts(legacy, canonical, legacy, previous), "legacy -> canonical"
    assert _preimage_accepts(legacy, canonical, canonical, previous), "canonical -> canonical"


def test_sequential_transition_rejects_undeclared_and_mismatched_identities() -> None:
    legacy, previous, canonical = _archive_helper_gate()
    declared = previous[0]

    wrong_hash = _RemoteIdentity("0" * 64, declared.owner, declared.group, declared.mode)
    wrong_owner = _RemoteIdentity(declared.sha256, "root", declared.group, declared.mode)
    wrong_group = _RemoteIdentity(declared.sha256, declared.owner, "root", declared.mode)
    wrong_mode = _RemoteIdentity(declared.sha256, declared.owner, declared.group, "664")
    wrong_type = _RemoteIdentity(declared.sha256, declared.owner, declared.group, declared.mode, "symbolic link")
    symlinked = _RemoteIdentity(declared.sha256, declared.owner, declared.group, declared.mode, is_symlink=True)
    unknown_drift = _RemoteIdentity("d" * 64, "nobody", "nogroup", "666")

    for actual in (wrong_hash, wrong_owner, wrong_group, wrong_mode, wrong_type, symlinked, unknown_drift):
        assert not _preimage_accepts(legacy, canonical, actual, previous)

    # Reachable-but-undeclared Git versions are still unknown drift.
    for source_sha in UNDECLARED_HISTORY_SOURCE_SHAS:
        undeclared = _RemoteIdentity(
            _git_blob_sha256(source_sha, ARCHIVE_HELPER_RELATIVE_PATH), "ubuntu", "ubuntu", "644"
        )
        assert undeclared.sha256 not in {legacy.sha256, canonical.sha256, declared.sha256}
        assert not _preimage_accepts(legacy, canonical, undeclared, previous)


def test_unchanged_targets_accept_only_legacy_and_canonical() -> None:
    entry = _contract_targets()[DB_DUMP_REMOTE_PATH]
    legacy = _declared_identity(entry)
    previous = _accepted_previous(entry)
    canonical = _canonical_identity(DB_DUMP_REMOTE_PATH, "ubuntu", "ubuntu", "644")

    assert previous == ()
    assert _preimage_accepts(legacy, canonical, legacy, previous)
    assert _preimage_accepts(legacy, canonical, canonical, previous)
    assert not _preimage_accepts(
        legacy, canonical, _RemoteIdentity("f" * 64, "ubuntu", "ubuntu", "644"), previous
    )
    # The archive helper's transition entry must not widen any other target.
    archive_previous = _accepted_previous(_contract_targets()[ARCHIVE_HELPER_REMOTE_PATH])[0]
    assert not _preimage_accepts(legacy, canonical, archive_previous, previous)


def test_propagation_tool_verifies_declared_previous_canonical_against_history() -> None:
    source = PROPAGATION_SCRIPT.read_text(encoding="utf-8")
    for required in (
        "accepted_previous_canonical",
        "AcceptedPreviousCanonical",
        "Get-DeclaredPreviousCanonical",
        "Get-GitBlobSha256",
        "cat-file blob",
        "does not match",
        "schema_version",
        "must name an exact source commit",
        "duplicate accepted previous canonical identity",
        'remote pre-image identity mismatch',
    ):
        assert required in source, required
    # Nothing may relax the gate to an owner/mode-only or "any master" check.
    assert "rev-list" not in source
    assert "merge-base" not in source
    assert "origin/master" not in source


def test_rendered_remote_script_accepts_only_declared_identities(tmp_path: Path) -> None:
    _, rendered = _render_remote_script(tmp_path)
    source = rendered.read_text(encoding="utf-8")
    legacy, previous, canonical = _archive_helper_gate()

    # Six unchanged targets keep two accepted identities each; the archive
    # helper gains exactly one reviewed transition identity.
    assert source.count('[ "$actual_sha" = ') == 7 * 2 + 1
    assert source.count(f"'{previous[0].sha256}'") == 1
    assert f"'{legacy.sha256}'" in source
    assert f"'{canonical.sha256}'" in source
    assert source.count("remote pre-image identity mismatch") == 7

    # Every target is validated before the first activation.
    first_activation = source.index("activated_1=1")
    assert source.rindex("remote pre-image identity mismatch") < first_activation
    assert source.index("REMOTE_PREIMAGE_MATCH=YES") < first_activation
    assert source.index("rollback_needed=1") < first_activation

    # No undeclared historical version leaks into the gate.
    for source_sha in UNDECLARED_HISTORY_SOURCE_SHAS:
        assert _git_blob_sha256(source_sha, ARCHIVE_HELPER_RELATIVE_PATH) not in source


def test_rendered_recovery_contract_is_unchanged_by_the_transition(tmp_path: Path) -> None:
    _, rendered = _render_remote_script(tmp_path)
    source = rendered.read_text(encoding="utf-8")

    assert "trap fail_closed EXIT" in source
    assert source.count("restore_target ") == 7
    assert "canonical backup propagation recovery failed" in source
    assert "systemctl daemon-reload" in source

    # Rollback restores in reverse activation order.
    restore_order = [
        source.index(f'if [ "$activated_{index}" -eq 1 ]; then restore_target ') for index in range(7, 0, -1)
    ]
    assert restore_order == sorted(restore_order)

    # Regression: iterating accepted previous identities must not shadow the
    # operation-scoped previous-copy directory the recovery path restores from.
    assert "@{" not in source
    for line in source.splitlines():
        if "restore_target '" in line:
            assert "/ops/backup/_backup_pipeline_previous_" in line


def test_propagation_plan_report_exposes_accepted_previous_canonical() -> None:
    pwsh = _powershell()
    if pwsh is None:
        pytest.skip("PowerShell is unavailable")
    if _git_status():
        pytest.skip("plan-mode execution requires a clean worktree")
    result = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PROPAGATION_SCRIPT),
            "-ExpectedSourceSha",
            _current_head(),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["mode"] == "plan"

    by_remote = {item["remote_path"]: item for item in report["files"]}
    assert len(by_remote) == 7
    for remote_path, item in by_remote.items():
        declared = item["accepted_previous_canonical"]
        if remote_path != ARCHIVE_HELPER_REMOTE_PATH:
            assert declared == []
            continue
        assert len(declared) == 1
        assert declared[0]["source_sha"] == PREVIOUS_CANONICAL_SOURCE_SHA
        assert declared[0]["sha256"] == _git_blob_sha256(
            PREVIOUS_CANONICAL_SOURCE_SHA, ARCHIVE_HELPER_RELATIVE_PATH
        )
        assert declared[0]["file_type"] == "regular file"

    # Plan mode still resolves the whole contract without touching the host.
    assert "ssh" not in result.stdout.lower()
    assert "scp" not in result.stdout.lower()
