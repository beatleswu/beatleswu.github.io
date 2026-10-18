#!/usr/bin/env python3
"""Independent BUILD_APP decision verification; never test-evidence admission.

The production host profile is intentionally unprovisioned. A candidate, CLI
argument, environment variable, local key or JSON policy cannot provision it.
This reference must be installed/reviewed by the governance host before use.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile

PREDICATE = "https://go-odyssey.invalid/attestations/build-authorization/v1"
SCHEMA = "g009-independent-build-decision-v1"
MAX_BYTES = 65536
DDL = "CREATE TABLE consumed (decision_id TEXT PRIMARY KEY NOT NULL, digest TEXT NOT NULL)"
OIDC_ISSUER = "https://token.actions.githubusercontent.com"
# Distribution pins: filled only in an independently reviewed host installation.
# Neither the candidate, CLI nor environment may select this file or its digest.
HOST_PROFILE_PATH = Path(r"C:\Program Files\Go Odyssey Governance\host-profile.json")
HOST_PROFILE_SHA256 = ""
MISSING_AUTHORITY = (
    "Owner-authorized BUILD_APP signer repository/workflow/ref/commit",
    "independently approved signer run_id/run_attempt",
    "authenticated verifier installation SHA256 and host-profile SHA256",
    "independently authenticated Sigstore trusted-root JSONL SHA256",
    "protected gh binary/home/config/temp and durable replay ledger",
    "signed unexpired decision bound to exact Gate/Product/common-dir/challenge",
)


class Rejected(ValueError):
    pass


@dataclass(frozen=True)
class HostProfile:
    # Only an independently administered host may provision these pins and files.
    repository: str
    workflow: str
    ref: str
    commit: str
    run_id: str
    run_attempt: str
    gh_path: Path
    gh_sha256: str
    ledger: Path
    host_home: Path
    gh_config_dir: Path
    trusted_root: Path
    trusted_root_sha256: str


def production_profile() -> HostProfile:
    if not re.fullmatch(r"[0-9a-f]{64}", HOST_PROFILE_SHA256):
        raise Rejected("EXTERNAL_GOVERNANCE_TRUST_ANCHOR_UNPROVISIONED: " + "; ".join(MISSING_AUTHORITY))
    return load_host_profile(HOST_PROFILE_PATH, HOST_PROFILE_SHA256)


def load_host_profile(path, expected_sha256):
    """Host installation only; this is deliberately not a CLI policy option."""
    if not path.is_absolute() or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise Rejected("HOST_PROFILE_PIN_INVALID")
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or digest(data) != expected_sha256:
        raise Rejected("HOST_PROFILE_BYTES_MISMATCH")
    fields = set(HostProfile.__dataclass_fields__)
    values = strict_json(data)
    if (not isinstance(values, dict) or set(values) != fields
            or not all(isinstance(v, str) and v for v in values.values())):
        raise Rejected("HOST_PROFILE_SCHEMA_INVALID")
    for key in ("gh_path", "ledger", "host_home", "gh_config_dir", "trusted_root"):
        values[key] = Path(values[key])
    profile = HostProfile(**values)
    check_profile(profile)
    return profile


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Rejected("DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(Rejected("NONFINITE_JSON")))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise Rejected("INVALID_UTC_TIMESTAMP")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def check_decision(data, *, gate, product, common, challenge, now):
    d = strict_json(data)
    keys = {"schema", "decision_id", "action", "gate_sha", "product_sha", "git_common_dir",
            "challenge", "issued_at", "expires_at", "evidence_sha256"}
    if not isinstance(d, dict) or set(d) != keys or not all(isinstance(v, str) for v in d.values()):
        raise Rejected("DECISION_SCHEMA_INVALID")
    if d["schema"] != SCHEMA or d["action"] != "AUTHORIZE_BUILD_APP":
        raise Rejected("GOVERNANCE_ACTION_REQUIRED")
    for value in (gate, product, d["gate_sha"], d["product_sha"]):
        if not re.fullmatch(r"[0-9a-f]{40}", value):
            raise Rejected("EXACT_SOURCE_REQUIRED")
    if d["gate_sha"] != gate or d["product_sha"] != product:
        raise Rejected("SOURCE_MISMATCH")
    if not Path(common).is_absolute() or d["git_common_dir"] != str(Path(common).resolve()):
        raise Rejected("REPOSITORY_IDENTITY_MISMATCH")
    if not re.fullmatch(r"[0-9a-f]{64}", challenge) or d["challenge"] != challenge:
        raise Rejected("CHALLENGE_MISMATCH")
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", d["decision_id"]):
        raise Rejected("DECISION_ID_INVALID")
    if not re.fullmatch(r"[0-9a-f]{64}", d["evidence_sha256"]):
        raise Rejected("EVIDENCE_BINDING_REQUIRED")
    issued, expires = timestamp(d["issued_at"]), timestamp(d["expires_at"])
    if not issued <= now < expires or not 0 < (expires - issued).total_seconds() <= 600:
        raise Rejected("DECISION_EXPIRED_OR_NOT_YET_VALID")
    return d


def check_profile(p):
    if (not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", p.repository)
            or not re.fullmatch(re.escape(p.repository) + r"/\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml", p.workflow)
            or not p.ref.startswith("refs/heads/")
            or not re.fullmatch(r"[0-9a-f]{40}", p.commit)
            or not re.fullmatch(r"[1-9][0-9]*", p.run_id)
            or not re.fullmatch(r"[1-9][0-9]*", p.run_attempt)
            or not all(v.is_absolute() for v in (p.gh_path, p.ledger, p.host_home, p.gh_config_dir, p.trusted_root))
            or not re.fullmatch(r"[0-9a-f]{64}", p.gh_sha256)
            or not re.fullmatch(r"[0-9a-f]{64}", p.trusted_root_sha256)):
        raise Rejected("HOST_PROFILE_INVALID")
    if digest(p.gh_path.read_bytes()) != p.gh_sha256:
        raise Rejected("TRUSTED_GH_BYTES_MISMATCH")
    if digest(p.trusted_root.read_bytes()) != p.trusted_root_sha256:
        raise Rejected("TRUSTED_SIGSTORE_ROOT_BYTES_MISMATCH")
    # gh 2.95 reads custom roots as JSONL; an unterminated last line is ignored.
    if not p.trusted_root.read_bytes().endswith(b"\n"):
        raise Rejected("TRUSTED_SIGSTORE_ROOT_JSONL_TERMINATOR_REQUIRED")


def command(p, snapshot, root_snapshot=None):
    return [str(p.gh_path), "attestation", "verify", str(snapshot), "--hostname", "github.com",
            "--repo", p.repository, "--signer-workflow", p.workflow,
            "--signer-digest", p.commit, "--source-ref", p.ref, "--source-digest", p.commit,
            "--cert-oidc-issuer", OIDC_ISSUER,
            "--cert-identity", f"https://github.com/{p.workflow}@{p.ref}",
            "--custom-trusted-root", str(root_snapshot or p.trusted_root),
            "--deny-self-hosted-runners", "--predicate-type", PREDICATE, "--format", "json"]


def check_verified_output(output, p, sha, name):
    if len(output) > 8 * 1024 * 1024:
        raise Rejected("ATTESTATION_OUTPUT_TOO_LARGE")
    rows = strict_json(output)
    if not isinstance(rows, list) or not rows:
        raise Rejected("ATTESTATION_MISSING")
    expected = {
        "issuer": OIDC_ISSUER,
        "sourceRepositoryURI": "https://github.com/" + p.repository,
        "sourceRepositoryRef": p.ref,
        "sourceRepositoryDigest": p.commit,
        "buildSignerURI": f"https://github.com/{p.workflow}@{p.ref}",
        "buildSignerDigest": p.commit,
        "runnerEnvironment": "github-hosted",
        "runInvocationURI": f"https://github.com/{p.repository}/actions/runs/{p.run_id}/attempts/{p.run_attempt}",
    }
    for row in rows:
        try:
            vr = row["verificationResult"]
            cert = vr["signature"]["certificate"]
            statement = vr["statement"]
            if (all(cert.get(k) == v for k, v in expected.items())
                    and statement["_type"] == "https://in-toto.io/Statement/v1"
                    and statement["predicateType"] == PREDICATE
                    and statement["subject"] == [{"name": name, "digest": {"sha256": sha}}]):
                return
        except (KeyError, TypeError, AttributeError):
            continue
    raise Rejected("ATTESTATION_IDENTITY_OR_SUBJECT_MISMATCH")


def consume(ledger, decision_id, sha):
    # Pre-provisioned protected local host storage. Never create/reset on admission.
    with closing(sqlite3.connect(ledger.as_uri() + "?mode=rw", uri=True, timeout=5)) as db:
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("PRAGMA synchronous=FULL")
        if db.execute("PRAGMA journal_mode").fetchone()[0] not in ("delete", "wal"):
            raise Rejected("REPLAY_LEDGER_UNSAFE")
        db.execute("BEGIN IMMEDIATE")
        if (db.execute("SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
                != [("table", "consumed", DDL)]
                or db.execute("PRAGMA quick_check").fetchall() != [("ok",)]):
            raise Rejected("REPLAY_LEDGER_INVALID")
        try:
            db.execute("INSERT INTO consumed VALUES (?, ?)", (decision_id, sha))
        except sqlite3.IntegrityError as exc:
            raise Rejected("DECISION_REPLAYED") from exc
        if db.execute("SELECT digest FROM consumed WHERE decision_id=?", (decision_id,)).fetchall() != [(sha,)]:
            raise Rejected("REPLAY_LEDGER_POSTCONDITION_FAILED")
        db.commit()


def run_gh(argv, p):
    # Ignore caller gh config/PATH/executable and Python import overrides.
    env = {k: v for k, v in os.environ.items() if k.upper() in
           {"SYSTEMROOT", "WINDIR"}}
    env.update({"GH_PROMPT_DISABLED": "1", "GH_HOST": "github.com",
                "GH_CONFIG_DIR": str(p.gh_config_dir), "HOME": str(p.host_home),
                "USERPROFILE": str(p.host_home), "XDG_CONFIG_HOME": str(p.host_home / ".config"),
                "APPDATA": str(p.host_home / "AppData/Roaming"),
                "LOCALAPPDATA": str(p.host_home / "AppData/Local")})
    env.update({"TEMP": str(p.host_home / "tmp"), "TMP": str(p.host_home / "tmp")})
    return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                          timeout=120, shell=False, env=env, cwd=p.host_home)


def verify(decision_path, p, *, gate, product, common, challenge, runner=None):
    """Test runners may exercise verification, but never authorize or consume production decisions."""
    check_profile(p)
    with decision_path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise Rejected("DECISION_TOO_LARGE")
    d = check_decision(data, gate=gate, product=product, common=common,
                       challenge=challenge, now=datetime.now(timezone.utc))
    # Authenticate precisely the same snapshot parsed above, never reopen candidate bytes.
    # Production scratch is in protected host storage, never caller TEMP/CWD.
    with tempfile.TemporaryDirectory(prefix="g009-governance-", dir=p.host_home / "tmp") as td:
        snapshot = Path(td) / "release-decision.json"
        snapshot.write_bytes(data)
        root_data = p.trusted_root.read_bytes()
        if digest(root_data) != p.trusted_root_sha256:
            raise Rejected("TRUSTED_SIGSTORE_ROOT_BYTES_MISMATCH")
        root_snapshot = Path(td) / "trusted-root.jsonl"
        root_snapshot.write_bytes(root_data)
        argv = command(p, snapshot, root_snapshot)
        result = runner(argv) if runner is not None else run_gh(argv, p)
        if result.returncode != 0:
            raise Rejected("ATTESTATION_VERIFY_FAILED_OR_UNAVAILABLE")
        check_verified_output(result.stdout, p, digest(data), snapshot.name)
        if snapshot.read_bytes() != data:
            raise Rejected("DECISION_SNAPSHOT_CHANGED")
        if root_snapshot.read_bytes() != root_data:
            raise Rejected("TRUSTED_SIGSTORE_ROOT_SNAPSHOT_CHANGED")
    # Recheck expiry after potentially slow network verification, before consumption.
    check_decision(data, gate=gate, product=product, common=common,
                   challenge=challenge, now=datetime.now(timezone.utc))
    if runner is not None:
        return {"status": "MOCK_VERIFIED_NOT_AUTHORIZED", "build_authorized": False,
                "evidence_admitted": False, "release_authorized": False}
    consume(p.ledger, d["decision_id"], digest(data))
    return {"status": "BUILD_APP_AUTHORIZED", "build_authorized": True,
            "evidence_admitted": False, "release_authorized": False,
            "decision_id": d["decision_id"], "decision_sha256": digest(data),
            "gate_sha": gate, "product_sha": product, "git_common_dir": common,
            "challenge": challenge}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--requirements", action="store_true", help="Read-only provisioning requirements; never authorizes")
    ap.add_argument("--decision", type=Path)
    ap.add_argument("--gate-sha")
    ap.add_argument("--product-sha")
    ap.add_argument("--expected-common-dir")
    ap.add_argument("--challenge")
    args = ap.parse_args(argv)
    if args.requirements:
        print(json.dumps({"status": "PROVISIONING_REQUIREMENTS", "oidc_issuer": OIDC_ISSUER,
                          "authorized_governance_signer": "UNKNOWN_NOT_SUPPLIED",
                          "host_profile_path": str(HOST_PROFILE_PATH),
                          "profile_pin_configured": bool(re.fullmatch(r"[0-9a-f]{64}", HOST_PROFILE_SHA256)),
                          "required": MISSING_AUTHORITY, "build_authorized": False,
                          "evidence_admitted": False, "release_authorized": False}, sort_keys=True))
        return 1
    if any(v is None for v in (args.decision, args.gate_sha, args.product_sha, args.expected_common_dir, args.challenge)):
        ap.error("--decision, --gate-sha, --product-sha, --expected-common-dir and --challenge are required")
    try:
        report = verify(args.decision, production_profile(), gate=args.gate_sha,
                        product=args.product_sha, common=args.expected_common_dir, challenge=args.challenge)
    except (Rejected, OSError, ValueError, TypeError, sqlite3.Error, subprocess.SubprocessError) as exc:
        report = {"status": "REJECTED", "build_authorized": False, "evidence_admitted": False,
                  "release_authorized": False, "reason": str(exc)}
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "BUILD_APP_AUTHORIZED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
