#!/usr/bin/env python3
"""Fail-closed, run-bound external authority verification before ANY product Docker operation.

This code cannot issue an authorization. An independently administered signer
must publish and Sigstore-attest release-decision.json after this run's challenge
has appeared. No candidate workflow or local environment variable is an issuer.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

REPO = "beatleswu/beatleswu.github.io"
WORKFLOW = ".github/workflows/g009-authorized-product-build.yml"
PRODUCT_SHA = "69dbe57aa535112b1759e3f3bdcf9ecbe1680efb"
PREDICATE = "https://go-odyssey.invalid/attestations/build-authorization/v1"
ISSUER = "https://token.actions.githubusercontent.com"
PROFILE_KEYS = {"schema", "repository", "workflow", "ref", "commit", "evidence_sha256"}
DECISION_KEYS = {"schema", "action", "decision_id", "gate_sha", "product_sha",
                 "github_build_run_id", "github_build_run_attempt", "challenge",
                 "issued_at", "expires_at", "evidence_sha256"}
SHA40 = re.compile(r"^[a-f0-9]{40}$")
SHA64 = re.compile(r"^[a-f0-9]{64}$")

class Rejected(Exception):
    pass

def strict_json(raw: bytes, max_bytes=65536):
    if len(raw) > max_bytes:
        raise Rejected("JSON_TOO_LARGE")
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise Rejected("DUPLICATE_JSON_KEY")
            out[key] = value
        return out
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(Rejected("NONFINITE_JSON")))
    except (UnicodeDecodeError, ValueError) as exc:
        raise Rejected("MALFORMED_JSON") from exc

def profile_from_environment(env):
    value = env.get("G009_APPROVED_ISSUER_PROFILE_B64", "")
    pin = env.get("G009_APPROVED_ISSUER_PROFILE_SHA256", "")
    if not value or not SHA64.fullmatch(pin):
        raise Rejected("EXTERNAL_ISSUER_PROFILE_UNPROVISIONED")
    try:
        raw = base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise Rejected("EXTERNAL_ISSUER_PROFILE_ENCODING_INVALID") from exc
    if hashlib.sha256(raw).hexdigest() != pin:
        raise Rejected("EXTERNAL_ISSUER_PROFILE_HASH_MISMATCH")
    p = strict_json(raw)
    if not isinstance(p, dict) or set(p) != PROFILE_KEYS:
        raise Rejected("EXTERNAL_ISSUER_PROFILE_SCHEMA_INVALID")
    if (p["schema"] != "g009-github-approved-issuer-v1" or
            not all(isinstance(v, str) and v for v in p.values()) or
            not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", p["repository"]) or
            p["repository"].split("/")[0].lower() == "beatleswu" or
            not re.fullmatch(r"[a-zA-Z0-9._/-]+\.ya?ml", p["workflow"]) or
            not p["workflow"].startswith(p["repository"] + "/.github/workflows/") or
            not p["ref"].startswith("refs/heads/") or
            not SHA40.fullmatch(p["commit"]) or
            not SHA64.fullmatch(p["evidence_sha256"])):
        raise Rejected("INDEPENDENT_ISSUER_IDENTITY_INVALID")
    return p

def prepared_challenge(env):
    challenge = env.get('G009_PREPARED_CHALLENGE', '')
    if not SHA64.fullmatch(challenge):
        raise Rejected('COMPLETED_PREPARATION_JOB_CHALLENGE_REQUIRED')
    return challenge

def require_runner(env):
    if (env.get("GITHUB_REPOSITORY") != REPO or
            env.get("GITHUB_EVENT_NAME") != "workflow_dispatch" or
            env.get("RUNNER_ENVIRONMENT") != "github-hosted" or
            not env.get("GITHUB_REF", "").startswith("refs/heads/") or
            not SHA40.fullmatch(env.get("GITHUB_SHA", "")) or
            not re.fullmatch(r"[1-9][0-9]*", env.get("GITHUB_RUN_ID", "")) or
            not re.fullmatch(r"[1-9][0-9]*", env.get("GITHUB_RUN_ATTEMPT", "")) or
            not env.get("GITHUB_WORKFLOW_REF", "").startswith(REPO + "/" + WORKFLOW + "@")):
        raise Rejected("UNTRUSTED_GITHUB_RUNNER_EVENT_OR_SOURCE")

def utc(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise Rejected("DECISION_UTC_TIMESTAMP_INVALID")
    try:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except ValueError as exc:
        raise Rejected("DECISION_UTC_TIMESTAMP_INVALID") from exc

def validate_decision(raw, env, profile, challenge, now=None):
    decision = strict_json(raw)
    if not isinstance(decision, dict) or set(decision) != DECISION_KEYS or not all(
        isinstance(v, str) for v in decision.values()
    ):
        raise Rejected("SIGNED_DECISION_SCHEMA_INVALID")
    if (decision["schema"] != "g009-github-run-bound-build-authorization-v1"
            or decision["action"] != "AUTHORIZE_BUILD_APP"
            or decision["gate_sha"] != env["GITHUB_SHA"]
            or decision["product_sha"] != PRODUCT_SHA
            or decision["github_build_run_id"] != env["GITHUB_RUN_ID"]
            or decision["github_build_run_attempt"] != env["GITHUB_RUN_ATTEMPT"]
            or decision["challenge"] != challenge
            or decision["evidence_sha256"] != profile["evidence_sha256"]
            or not SHA64.fullmatch(decision["challenge"])
            or not SHA64.fullmatch(decision["evidence_sha256"])
            or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", decision["decision_id"])):
        raise Rejected("SIGNED_DECISION_BINDING_MISMATCH")
    start, end = utc(decision["issued_at"]), utc(decision["expires_at"])
    now = now or dt.datetime.now(dt.timezone.utc)
    if not (start <= now < end and 0 < (end-start).total_seconds() <= 600):
        raise Rejected("SIGNED_DECISION_EXPIRED_OR_NOT_YET_VALID")
    return decision

def cmd(args, *, timeout=90):
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=timeout)
    if result.returncode:
        raise Rejected("EXTERNAL_GITHUB_COMMAND_FAILED")
    return result.stdout.strip()

def verify_sigstore(data_path, profile, issuer_run, issuer_attempt):
    argv = ["gh", "attestation", "verify", str(data_path),
            "--repo", profile["repository"], "--hostname", "github.com",
            "--cert-oidc-issuer", ISSUER,
            "--cert-identity", "https://github.com/" + profile["workflow"] + "@" + profile["ref"],
            "--source-ref", profile["ref"], "--source-digest", profile["commit"],
            "--signer-digest", profile["commit"], "--deny-self-hosted-runners",
            "--predicate-type", PREDICATE, "--format", "json"]
    # The gh CLI verifies the Sigstore chain and attested subject. We separately
    # check the exact signer, source, invocation and subject fields in its output.
    records = strict_json(cmd(argv, timeout=120).encode("utf-8"), max_bytes=8*1024*1024)
    expected_uri = (f"https://github.com/{profile['repository']}/actions/runs/"
                    f"{issuer_run}/attempts/{issuer_attempt}")
    expected = {"issuer": ISSUER,
                "sourceRepositoryURI": "https://github.com/" + profile["repository"],
                "sourceRepositoryRef": profile["ref"],
                "sourceRepositoryDigest": profile["commit"],
                "buildSignerURI": "https://github.com/" + profile["workflow"] + "@" + profile["ref"],
                "buildSignerDigest": profile["commit"],
                "runnerEnvironment": "github-hosted", "runInvocationURI": expected_uri}
    if not isinstance(records, list) or not records:
        raise Rejected("SIGNED_DECISION_ATTESTATION_MISSING")
    subject = [{"name": "release-decision.json", "digest": {
        "sha256": hashlib.sha256(data_path.read_bytes()).hexdigest()}}]
    if not any(
        r.get("verificationResult", {}).get("statement", {}).get("predicateType") == PREDICATE
        and r.get("verificationResult", {}).get("statement", {}).get("subject") == subject
        and all(r.get("verificationResult", {}).get("signature", {}).get("certificate", {}).get(k) == v
                for k, v in expected.items())
        for r in records if isinstance(r, dict)
    ):
        raise Rejected("SIGNED_DECISION_CERTIFICATE_RUN_OR_SUBJECT_MISMATCH")

def verified_release_decision(profile, env, challenge):
    name = f"g009-authorize-{env['GITHUB_RUN_ID']}-{env['GITHUB_RUN_ATTEMPT']}"
    repo = profile["repository"]
    timeout = time.monotonic() + 360
    while True:
        response = strict_json(cmd(["gh", "api", f"repos/{repo}/actions/artifacts?name={name}&per_page=100"]).encode("utf-8"))
        found = [a for a in response.get("artifacts", []) if a.get("name") == name and not a.get("expired")]
        if len(found) > 1:
            raise Rejected("AMBIGUOUS_SIGNER_ARTIFACT")
        if found:
            artifact = found[0]
            break
        if time.monotonic() >= timeout:
            raise Rejected("EXTERNAL_SIGNED_DECISION_NOT_ISSUED")
        time.sleep(8)
    issuer_run = str(artifact.get("workflow_run", {}).get("id", ""))
    issuer_attempt = str(artifact.get("workflow_run", {}).get("run_attempt", ""))
    if not re.fullmatch(r"[1-9][0-9]*", issuer_run):
        raise Rejected("ISSUER_WORKFLOW_RUN_ID_UNAVAILABLE")
    # GET specific issuer run's named artifact; not the most recent arbitrary run.
    with tempfile.TemporaryDirectory(prefix="g009-signed-decision-") as tmp:
        cmd(["gh", "run", "download", issuer_run, "-R", repo, "-n", name, "-D", tmp])
        entries = list(Path(tmp).iterdir())
        if len(entries) != 1 or entries[0].name != "release-decision.json" or entries[0].is_symlink():
            raise Rejected("ISSUER_ARTIFACT_CONTENT_INVALID")
        path = entries[0]
        raw = path.read_bytes()
        decision = validate_decision(raw, env, profile, challenge)
        # If GitHub artifact response omitted attempt, get exact run attempt from
        # the attestation certificate only when it is bound to a real positive ID.
        if not re.fullmatch(r"[1-9][0-9]*", issuer_attempt):
            run = strict_json(cmd(["gh", "api", f"repos/{repo}/actions/runs/{issuer_run}"]).encode("utf-8"))
            issuer_attempt = str(run.get("run_attempt", ""))
        if not re.fullmatch(r"[1-9][0-9]*", issuer_attempt):
            raise Rejected("ISSUER_ATTEMPT_UNAVAILABLE")
        verify_sigstore(path, profile, issuer_run, issuer_attempt)
        validate_decision(raw, env, profile, challenge)
        return decision, hashlib.sha256(raw).hexdigest()

def main():
    env = os.environ
    require_runner(env)
    # Source identity self-check; this checkout is ONLY the broker control plane.
    if cmd(["git", "rev-parse", "HEAD"]) != env["GITHUB_SHA"]:
        raise Rejected("GATE_WORKTREE_SOURCE_MISMATCH")
    if cmd(["git", "status", "--porcelain=v1", "--untracked-files=normal"]):
        raise Rejected("GATE_WORKTREE_DIRTY")
    profile = profile_from_environment(env)
    # Preparation is a different, ALREADY COMPLETED workflow job. Its immutable
    # run/attempt-specific artifact is available to the independent issuer.
    # Do not mint a second challenge inside the waiting authorization job.
    challenge = prepared_challenge(env)
    print("G009_SIGNER_CHALLENGE_FROM_COMPLETED_PREPARATION:", challenge, flush=True)
    print("G009_BUILD_RUN_BINDING:", env["GITHUB_RUN_ID"], env["GITHUB_RUN_ATTEMPT"], env["GITHUB_SHA"], PRODUCT_SHA, flush=True)
    signed, sha = verified_release_decision(profile, env, challenge)
    if not env.get("GITHUB_OUTPUT"):
        raise Rejected("GITHUB_OUTPUT_MISSING")
    with open(env["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
        f.write("product_sha=" + PRODUCT_SHA + "\n")
        f.write("gate_sha=" + env["GITHUB_SHA"] + "\n")
        f.write("decision_sha256=" + sha + "\n")
        f.write("authorized=true\n")
    print(json.dumps({"status":"AUTHENTIC_SIGNED_BUILD_APP_DECISION_VERIFIED",
                      "gate_sha":env["GITHUB_SHA"],"product_sha":PRODUCT_SHA,
                      "decision_id":signed["decision_id"],
                      "decision_sha256":sha,
                      "release_authorized":False,"deploy_authorized":False}))

if __name__ == "__main__":
    try:
        main()
    except (Rejected, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        print("G009_AUTHORIZED_BUILD_REJECTED: " + str(exc), file=sys.stderr)
        sys.exit(1)
