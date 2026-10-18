"""Synthetic issuer output exercises policy; no test is a real authorization."""
import copy
from dataclasses import asdict, replace
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/release/verify_external_governance.py"
spec = importlib.util.spec_from_file_location("g009_governance_test", SCRIPT)
G = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = G
spec.loader.exec_module(G)


@pytest.fixture
def case(tmp_path):
    gh = tmp_path / "gh.exe"
    gh.write_bytes(b"synthetic cli: never executed")
    ledger = tmp_path / "ledger.sqlite"
    with closing(sqlite3.connect(ledger)) as db:
        db.execute(G.DDL)
    root = tmp_path / "trusted-root.jsonl"
    root.write_bytes(b'{"synthetic":"never a trust anchor"}\n')
    (tmp_path / "host-home" / "tmp").mkdir(parents=True)
    p = G.HostProfile("independent/governance", "independent/governance/.github/workflows/authorize.yml",
                      "refs/heads/protected", "a" * 40, "123", "1", gh, G.digest(gh.read_bytes()), ledger,
                      tmp_path / "host-home", tmp_path / "host-config", root, G.digest(root.read_bytes()))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    fmt = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")
    args = dict(gate="b" * 40, product="c" * 40, common=str(tmp_path.resolve()), challenge="d" * 64)
    d = dict(schema=G.SCHEMA, action="AUTHORIZE_BUILD_APP", decision_id="decision_00000001",
             gate_sha=args["gate"], product_sha=args["product"], git_common_dir=args["common"],
             challenge=args["challenge"], issued_at=fmt(now - timedelta(seconds=1)),
             expires_at=fmt(now + timedelta(minutes=3)), evidence_sha256="e" * 64)
    file = tmp_path / "untrusted.json"
    file.write_text(json.dumps(d), encoding="utf-8")
    def output(sha=None):
        return [{"verificationResult": {"signature": {"certificate": {
            "issuer": "https://token.actions.githubusercontent.com",
            "sourceRepositoryURI": "https://github.com/" + p.repository,
            "sourceRepositoryRef": p.ref, "sourceRepositoryDigest": p.commit,
            "buildSignerURI": f"https://github.com/{p.workflow}@{p.ref}", "buildSignerDigest": p.commit,
            "runnerEnvironment": "github-hosted",
            "runInvocationURI": "https://github.com/independent/governance/actions/runs/123/attempts/1"}},
            "statement": {"_type": "https://in-toto.io/Statement/v1", "predicateType": G.PREDICATE,
                          "subject": [{"name": "release-decision.json", "digest": {"sha256": sha or G.digest(file.read_bytes())}}]}}}]
    return SimpleNamespace(p=p, args=args, d=d, file=file, output=output, now=now)


def test_positive_authenticated_shape_is_only_mock_and_never_consumes(case):
    seen = []
    def runner(argv):
        seen.append(argv)
        return SimpleNamespace(returncode=0, stdout=json.dumps(case.output()))
    report = G.verify(case.file, case.p, **case.args, runner=runner)
    assert report == {"status": "MOCK_VERIFIED_NOT_AUTHORIZED", "build_authorized": False,
                      "evidence_admitted": False, "release_authorized": False}
    cmd = seen[0]
    for flag, value in (("--signer-digest", case.p.commit), ("--source-digest", case.p.commit),
                        ("--source-ref", case.p.ref), ("--repo", case.p.repository),
                        ("--predicate-type", G.PREDICATE)):
        assert cmd[cmd.index(flag) + 1] == value
    assert cmd[0] == str(case.p.gh_path) and "--deny-self-hosted-runners" in cmd
    assert "--custom-trusted-root" in cmd and "--bundle" not in cmd
    assert cmd[cmd.index("--cert-identity") + 1] == f"https://github.com/{case.p.workflow}@{case.p.ref}"
    # gh 2.95 mutually excludes --cert-identity and --signer-workflow; the
    # exact SAN is verified here and all certificate fields are checked again.
    assert "--signer-workflow" not in cmd and "--cert-identity-regex" not in cmd
    assert cmd.count("--cert-identity") == 1
    with closing(sqlite3.connect(case.p.ledger)) as db:
        assert db.execute("SELECT * FROM consumed").fetchall() == []


@pytest.mark.parametrize("field,value", [
    ("issuer", "https://evil.invalid"), ("sourceRepositoryURI", "https://github.com/candidate/self"),
    ("sourceRepositoryRef", "refs/pull/1/merge"), ("sourceRepositoryDigest", "f" * 40),
    ("buildSignerURI", "https://github.com/independent/governance/.github/workflows/other.yml@refs/heads/protected"),
    ("buildSignerDigest", "f" * 40), ("runnerEnvironment", "self-hosted"),
    ("runInvocationURI", "https://github.com/independent/governance/actions/runs/123/attempts/10"),
    ("runInvocationURI", "https://github.com/independent/governance/actions/runs/123/attempts/1?fake=1"),
])
def test_mismatched_or_replayed_issuer_source(case, field, value):
    rows = case.output()
    rows[0]["verificationResult"]["signature"]["certificate"][field] = value
    with pytest.raises(G.Rejected, match="IDENTITY_OR_SUBJECT"):
        G.verify(case.file, case.p, **case.args,
                 runner=lambda _: SimpleNamespace(returncode=0, stdout=json.dumps(rows)))


@pytest.mark.parametrize("field,value,reason", [
    ("gate_sha", "f" * 40, "SOURCE_MISMATCH"), ("product_sha", "f" * 40, "SOURCE_MISMATCH"),
    ("git_common_dir", "foreign", "REPOSITORY_IDENTITY"), ("challenge", "f" * 64, "CHALLENGE"),
    ("action", "EVIDENCE_ADMITTED_ATTESTED", "GOVERNANCE_ACTION"),
    ("action", "AUTHORIZE_DEPLOY", "GOVERNANCE_ACTION"),
    ("evidence_sha256", "", "EVIDENCE_BINDING"),
    ("issued_at", "2099-01-01T00:00:00Z", "EXPIRED_OR_NOT_YET"),
    ("expires_at", "2000-01-01T00:00:00Z", "EXPIRED_OR_NOT_YET"),
    ("expires_at", "2099-01-01T00:00:00Z", "EXPIRED_OR_NOT_YET"),
    ("expires_at", "2026-10-18T12:00:00", "UTC_TIMESTAMP"),
    ("release_authorized", True, "SCHEMA"),
])
def test_forged_decision_rejected_before_network(case, field, value, reason):
    case.d[field] = value
    case.file.write_text(json.dumps(case.d))
    with pytest.raises(G.Rejected, match=reason):
        G.verify(case.file, case.p, **case.args, runner=lambda _: pytest.fail("must reject before network"))


@pytest.mark.parametrize("payload", ["[]", "{}", "null", "garbage", '[{"verificationResult": null}]'])
def test_missing_or_malformed_attestation(case, payload):
    with pytest.raises((G.Rejected, ValueError)):
        G.verify(case.file, case.p, **case.args,
                 runner=lambda _: SimpleNamespace(returncode=0, stdout=payload))


def test_forged_json_even_perfect_shape_requires_successful_crypto_verifier(case):
    with pytest.raises(G.Rejected, match="VERIFY_FAILED"):
        G.verify(case.file, case.p, **case.args,
                 runner=lambda _: SimpleNamespace(returncode=1, stdout=json.dumps(case.output())))


@pytest.mark.parametrize("failure", [OSError("offline"), subprocess.TimeoutExpired("gh", 120)])
def test_offline_timeout_never_authorizes_or_consumes(case, failure):
    def runner(_):
        raise failure
    with pytest.raises(type(failure)):
        G.verify(case.file, case.p, **case.args, runner=runner)
    with closing(sqlite3.connect(case.p.ledger)) as db:
        assert db.execute("SELECT * FROM consumed").fetchall() == []


@pytest.mark.parametrize("fault", ["digest", "name", "predicate", "duplicate-subject", "duplicate-json-key"])
def test_subject_and_statement_substitution(case, fault):
    rows = case.output()
    s = rows[0]["verificationResult"]["statement"]
    if fault == "digest":
        s["subject"][0]["digest"]["sha256"] = "f" * 64
    elif fault == "name":
        s["subject"][0]["name"] = "evidence.zip"
    elif fault == "predicate":
        s["predicateType"] = "https://slsa.dev/provenance/v1"
    elif fault == "duplicate-subject":
        s["subject"].append(copy.deepcopy(s["subject"][0]))
    output = json.dumps(rows)
    if fault == "duplicate-json-key":
        output = output.replace('"issuer":', '"issuer": "forged", "issuer":')
    with pytest.raises(G.Rejected):
        G.verify(case.file, case.p, **case.args, runner=lambda _: SimpleNamespace(returncode=0, stdout=output))


def test_snapshot_avoids_candidate_file_reopen(case):
    rows = case.output()
    def runner(argv):
        case.file.write_bytes(b"forged after parse")
        assert Path(argv[3]).read_bytes() != case.file.read_bytes()
        return SimpleNamespace(returncode=0, stdout=json.dumps(rows))
    assert G.verify(case.file, case.p, **case.args, runner=runner)["status"] == "MOCK_VERIFIED_NOT_AUTHORIZED"


def test_replay_atomic_exactly_one_winner(case):
    def attempt(_):
        try:
            G.consume(case.p.ledger, case.d["decision_id"], "a" * 64)
            return "consumed"
        except G.Rejected as exc:
            return str(exc)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(8)))
    assert results.count("consumed") == 1
    assert results.count("DECISION_REPLAYED") == 7


@pytest.mark.parametrize("fault", ["missing", "corrupt", "trigger", "view", "wrong-schema"])
def test_untrusted_replay_storage(case, fault):
    if fault == "missing":
        case.p.ledger.unlink()
    elif fault == "corrupt":
        case.p.ledger.write_bytes(b"forged db")
    else:
        with closing(sqlite3.connect(case.p.ledger)) as db:
            if fault == "trigger":
                db.execute("CREATE TRIGGER erase AFTER INSERT ON consumed BEGIN DELETE FROM consumed; END")
            elif fault == "view":
                db.execute("CREATE VIEW fake AS SELECT * FROM consumed")
            else:
                db.execute("ALTER TABLE consumed ADD COLUMN ignored TEXT")
            db.commit()
    with pytest.raises((G.Rejected, sqlite3.Error)):
        G.consume(case.p.ledger, case.d["decision_id"], "a" * 64)


def test_cli_cannot_bootstrap_authority_from_json_flags_keys_or_environment(case, monkeypatch, capsys):
    monkeypatch.setenv("G009_TRUST_POLICY", str(case.file))
    monkeypatch.setenv("GH_HOST", "evil.invalid")
    rc = G.main(["--decision", str(case.file), "--gate-sha", case.args["gate"],
                 "--product-sha", case.args["product"], "--expected-common-dir", case.args["common"],
                 "--challenge", case.args["challenge"]])
    report = json.loads(capsys.readouterr().out)
    assert rc == 1 and report["status"] == "REJECTED"
    assert "TRUST_ANCHOR_UNPROVISIONED" in report["reason"]
    assert report["build_authorized"] is report["evidence_admitted"] is report["release_authorized"] is False


def test_altered_verifier_executable_rejected(case):
    case.p.gh_path.write_bytes(b"attacker cli")
    with pytest.raises(G.Rejected, match="GH_BYTES_MISMATCH"):
        G.verify(case.file, case.p, **case.args, runner=lambda _: pytest.fail("untrusted executable"))


@pytest.mark.parametrize("fault", ["missing", "oversized", "duplicate-key", "nonfinite"])
def test_untrusted_decision_file_rejected(case, fault):
    if fault == "missing":
        case.file.unlink()
    elif fault == "oversized":
        case.file.write_bytes(b"x" * (G.MAX_BYTES + 1))
    elif fault == "duplicate-key":
        case.file.write_text('{"action":"AUTHORIZE_BUILD_APP","action":"forged"}')
    else:
        case.file.write_text('{"action":NaN}')
    with pytest.raises((G.Rejected, OSError)):
        G.verify(case.file, case.p, **case.args, runner=lambda _: pytest.fail("invalid file"))


def test_candidate_environment_cannot_replace_host_identity_or_roots(case, monkeypatch):
    monkeypatch.setenv("GH_CONFIG_DIR", "attacker-config")
    monkeypatch.setenv("GH_TOKEN", "forged-token")
    monkeypatch.setenv("SIGSTORE_ROOT_FILE", "self-signed-root")
    monkeypatch.setenv("HOME", "attacker-home")
    captured = {}
    def run(argv, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(returncode=1, stdout="")
    monkeypatch.setattr(G.subprocess, "run", run)
    G.run_gh(G.command(case.p, case.file), case.p)
    env = captured["env"]
    assert env["GH_CONFIG_DIR"] == str(case.p.gh_config_dir)
    assert env["HOME"] == str(case.p.host_home)
    assert "GH_TOKEN" not in env and "SIGSTORE_ROOT_FILE" not in env
    assert captured["shell"] is False and captured["timeout"] == 120


def test_actual_build_entrypoint_rejects_before_worktree_setup(case, monkeypatch):
    import shutil
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    assert powershell, "native PowerShell required for this integration test"
    monkeypatch.setenv("PATH", str(Path(sys.executable).parent) + ";" + __import__("os").environ["PATH"])
    proc = subprocess.run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts/release/build-release-image.ps1"),
                           "-GovernanceExpectedGitCommonDirectory", case.args["common"],
                           "-GovernanceGateSourceSha", case.args["gate"], "-GovernanceProductSourceSha", case.args["product"],
                           "-GovernanceDecision", str(case.file), "-GovernanceChallenge", case.args["challenge"], "-DryRun"],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode != 0
    assert "TRUST_ANCHOR_UNPROVISIONED" in proc.stdout + proc.stderr


def test_build_authority_never_comes_from_candidate_python_or_path():
    text = (ROOT / "scripts/release/build-release-image.ps1").read_text(encoding="utf-8")
    boundary = text[:text.index("$expectedGitCommonDirectory = $GovernanceExpectedGitCommonDirectory")]
    assert "& python" not in boundary
    assert "$governanceVerifierSha256 = ''" in boundary
    assert boundary.index("TRUST_ANCHOR_UNPROVISIONED") < boundary.index("& $governanceVerifier")
    assert "Get-FileHash -LiteralPath $governanceVerifier" in boundary
    assert "C:\\Program Files\\Go Odyssey Governance\\verify-governance.exe" in boundary


def profile_file(case):
    values = {key: str(value) for key, value in asdict(case.p).items()}
    path = case.file.parent / "host-profile.json"
    path.write_text(json.dumps(values), encoding="utf-8")
    return path


def test_independently_pinned_profile_loads_exact_bytes(case, monkeypatch):
    path = profile_file(case)
    monkeypatch.setattr(G, "HOST_PROFILE_PATH", path)
    monkeypatch.setattr(G, "HOST_PROFILE_SHA256", G.digest(path.read_bytes()))
    assert G.production_profile() == case.p
    path.write_text(path.read_text() + " ")
    with pytest.raises(G.Rejected, match="PROFILE_BYTES_MISMATCH"):
        G.production_profile()


@pytest.mark.parametrize("fault", ["extra", "missing", "null", "duplicate", "relative", "oversized"])
def test_protected_profile_cannot_loosen_schema_or_paths(case, fault):
    path = profile_file(case)
    values = json.loads(path.read_text())
    if fault == "extra":
        values["allow_unsigned"] = "true"
    elif fault == "missing":
        del values["commit"]
    elif fault == "null":
        values["repository"] = None
    elif fault == "relative":
        values["gh_path"] = "candidate/gh.exe"
    path.write_text(json.dumps(values))
    if fault == "duplicate":
        path.write_text('{"commit":"fake",' + path.read_text()[1:])
    if fault == "oversized":
        path.write_bytes(b"x" * (G.MAX_BYTES + 1))
    with pytest.raises(G.Rejected):
        G.load_host_profile(path, G.digest(path.read_bytes()))


def test_requirements_is_read_only_and_names_missing_authority(monkeypatch, capsys):
    monkeypatch.setattr(G, "production_profile", lambda: pytest.fail("must not access protected state"))
    assert G.main(["--requirements"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["oidc_issuer"] == "https://token.actions.githubusercontent.com"
    assert report["authorized_governance_signer"] == "UNKNOWN_NOT_SUPPLIED"
    assert report["profile_pin_configured"] is False
    assert report["build_authorized"] is report["release_authorized"] is False


@pytest.mark.parametrize("fault", ["missing", "changed", "unterminated"])
def test_pinned_sigstore_root_required_before_verification(case, fault):
    p = case.p
    if fault == "missing":
        p.trusted_root.unlink()
    elif fault == "changed":
        p.trusted_root.write_bytes(b"attacker-root\n")
    else:
        p.trusted_root.write_bytes(b"{}")
        p = replace(p, trusted_root_sha256=G.digest(b"{}"))
    with pytest.raises((G.Rejected, OSError)):
        G.verify(case.file, p, **case.args, runner=lambda _: pytest.fail("untrusted root"))


@pytest.mark.parametrize("target", ["decision", "root"])
def test_snapshot_tampering_is_rejected_without_consumption(case, target):
    rows = case.output()
    def runner(argv):
        path = Path(argv[3] if target == "decision" else argv[argv.index("--custom-trusted-root") + 1])
        assert path.parent.parent == case.p.host_home / "tmp"
        path.write_bytes(b"tampered")
        return SimpleNamespace(returncode=0, stdout=json.dumps(rows))
    with pytest.raises(G.Rejected, match="SNAPSHOT_CHANGED"):
        G.verify(case.file, case.p, **case.args, runner=runner)
    with closing(sqlite3.connect(case.p.ledger)) as db:
        assert db.execute("SELECT * FROM consumed").fetchall() == []


def test_host_process_uses_protected_working_directory_and_temp(case, monkeypatch):
    captured = {}
    monkeypatch.setenv("TEMP", "candidate-temp")
    monkeypatch.setenv("SSL_CERT_FILE", "candidate-ca")
    monkeypatch.setenv("HTTPS_PROXY", "https://candidate-proxy")
    def run(argv, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(returncode=1, stdout="")
    monkeypatch.setattr(G.subprocess, "run", run)
    G.run_gh(G.command(case.p, case.file), case.p)
    assert captured["cwd"] == case.p.host_home
    assert captured["env"]["TEMP"] == str(case.p.host_home / "tmp")
    assert "SSL_CERT_FILE" not in captured["env"] and "HTTPS_PROXY" not in captured["env"]


def test_verification_output_size_is_bounded(case):
    with pytest.raises(G.Rejected, match="OUTPUT_TOO_LARGE"):
        G.check_verified_output(" " * (8 * 1024 * 1024 + 1), case.p, "a" * 64, "release-decision.json")


def test_expiry_is_rechecked_after_network(case, monkeypatch):
    rows = case.output()
    class Clock:
        count = 0
        @classmethod
        def now(cls, tz):
            cls.count += 1
            return case.now if cls.count == 1 else case.now + timedelta(minutes=11)
    monkeypatch.setattr(G, "datetime", SimpleNamespace(now=Clock.now, strptime=datetime.strptime))
    with pytest.raises(G.Rejected, match="EXPIRED"):
        G.verify(case.file, case.p, **case.args,
                 runner=lambda _: SimpleNamespace(returncode=0, stdout=json.dumps(rows)))


def test_build_requires_bound_affirmative_report_even_on_zero_exit():
    text = (ROOT / "scripts/release/build-release-image.ps1").read_text(encoding="utf-8")
    report_check = text[text.index("$governanceExitCode ="):text.index("$expectedGitCommonDirectory =")]
    assert "ConvertFrom-Json" in report_check
    for field in ("status", "build_authorized", "evidence_admitted", "release_authorized",
                  "gate_sha", "product_sha", "git_common_dir", "challenge", "decision_sha256"):
        assert "$governanceReport." + field in report_check
