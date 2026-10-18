"""Only run-bound authorization denial and pure contract tests; NO Docker or 407 regression."""
import base64
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github/scripts/g009_authorized_product_build.py"
BUILDER = ROOT / ".github/scripts/g009_product_build_package.py"
WORKFLOW = ROOT / ".github/workflows/g009-authorized-product-build.yml"
spec = importlib.util.spec_from_file_location("g009_auth_test_target", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
NOW = dt.datetime(2026, 10, 18, 9, 0, 0, tzinfo=dt.timezone.utc)

def fake_env():
    return {"GITHUB_REPOSITORY": mod.REPO,
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "RUNNER_ENVIRONMENT": "github-hosted",
            "GITHUB_WORKFLOW_REF": mod.REPO + "/" + mod.WORKFLOW + "@refs/heads/master",
            "GITHUB_REF": "refs/heads/master",
            "GITHUB_SHA": "a"*40,
            "GITHUB_RUN_ID": "1234567",
            "GITHUB_RUN_ATTEMPT": "1"}

def fake_profile():
    return {"schema": "g009-github-approved-issuer-v1",
            "repository": "independent-example-organization/test-issuer",
            "workflow": "independent-example-organization/test-issuer/.github/workflows/authorize.yml",
            "ref": "refs/heads/approved",
            "commit": "b"*40,
            "evidence_sha256": "c"*64}

def fake_decision():
    return {"schema": "g009-github-run-bound-build-authorization-v1",
            "action": "AUTHORIZE_BUILD_APP",
            "decision_id": "TEST_DECISION_NOT_ACTUAL_123",
            "gate_sha": "a"*40,
            "product_sha": mod.PRODUCT_SHA,
            "github_build_run_id": "1234567",
            "github_build_run_attempt": "1",
            "challenge": "d"*64,
            "issued_at": "2026-10-18T08:59:00Z",
            "expires_at": "2026-10-18T09:03:00Z",
            "evidence_sha256": "c"*64}

class TestAuthorizationContract(unittest.TestCase):
    def test_prepared_challenge_must_come_from_completed_job(self):
        with self.assertRaisesRegex(mod.Rejected, "COMPLETED_PREPARATION"):
            mod.prepared_challenge({})
        with self.assertRaisesRegex(mod.Rejected, "COMPLETED_PREPARATION"):
            mod.prepared_challenge({"G009_PREPARED_CHALLENGE": "wrong"})
        self.assertEqual(mod.prepared_challenge({"G009_PREPARED_CHALLENGE":"e"*64}),"e"*64)

    def test_cross_repo_read_token_only_in_authorization_not_docker(self):
        source=WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("GH_TOKEN: ${{ secrets.G009_ISSUER_ACTIONS_READ_TOKEN }}",source)
        self.assertIn("G009_PREPARED_CHALLENGE: ${{ needs['prepare-run-challenge'].outputs.challenge }}",source)
        builder=source.split("      - name: Build and package actual immutable linux ARM64 Product image")[1]
        self.assertNotIn("G009_ISSUER_ACTIONS_READ_TOKEN", builder)
        self.assertNotIn("GH_TOKEN:", builder)

    def test_completed_prepare_job_must_publish_challenge_artifact(self):
        y=WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  prepare-run-challenge:", y)
        self.assertIn("needs: prepare-run-challenge", y)
        self.assertIn("g009-build-challenge-${{ github.run_id }}-${{ github.run_attempt }}",y)
        self.assertIn("Generate unique run-and-attempt-bound 32-byte challenge",y)

    def test_no_profile_fails_closed(self):
        with self.assertRaisesRegex(mod.Rejected, "UNPROVISIONED"):
            mod.profile_from_environment({})

    def test_not_github_hosted_runner_fails_closed(self):
        e = fake_env()
        e["RUNNER_ENVIRONMENT"] = "self-hosted"
        with self.assertRaises(mod.Rejected):
            mod.require_runner(e)

    def test_push_may_only_run_negative_tests(self):
        e = fake_env()
        e["GITHUB_EVENT_NAME"] = "push"
        with self.assertRaises(mod.Rejected):
            mod.require_runner(e)

    def test_profile_can_not_nominate_same_ownership(self):
        p = fake_profile()
        p["repository"] = "beatleswu/another-issuer"
        p["workflow"] = "beatleswu/another-issuer/.github/workflows/authorize.yml"
        raw = json.dumps(p).encode()
        e = {"G009_APPROVED_ISSUER_PROFILE_B64": base64.b64encode(raw).decode(),
             "G009_APPROVED_ISSUER_PROFILE_SHA256": hashlib.sha256(raw).hexdigest()}
        with self.assertRaisesRegex(mod.Rejected, "INDEPENDENT_ISSUER"):
            mod.profile_from_environment(e)

    def test_external_profile_bytes_exact_pin_required(self):
        raw = json.dumps(fake_profile()).encode()
        env = {"G009_APPROVED_ISSUER_PROFILE_B64": base64.b64encode(raw).decode(),
               "G009_APPROVED_ISSUER_PROFILE_SHA256": hashlib.sha256(raw).hexdigest()}
        self.assertEqual(mod.profile_from_environment(env)["commit"], "b"*40)
        env["G009_APPROVED_ISSUER_PROFILE_SHA256"] = "0"*64
        with self.assertRaisesRegex(mod.Rejected, "HASH_MISMATCH"):
            mod.profile_from_environment(env)

    def test_unsigned_matching_json_is_only_parsed_not_authorized(self):
        data=json.dumps(fake_decision()).encode()
        decision=mod.validate_decision(data, fake_env(), fake_profile(), "d"*64, NOW)
        self.assertEqual(decision["action"], "AUTHORIZE_BUILD_APP")
        self.assertIn("verify_sigstore", dir(mod))
        # Parsing and local JSON matching NEVER issue the authorization output.
        self.assertEqual(mod.PREDICATE, "https://go-odyssey.invalid/attestations/build-authorization/v1")

    def test_foreign_run_rejected(self):
        d=fake_decision()
        d["github_build_run_id"] = "7654321"
        with self.assertRaisesRegex(mod.Rejected, "BINDING_MISMATCH"):
            mod.validate_decision(json.dumps(d).encode(), fake_env(), fake_profile(), "d"*64, NOW)

    def test_rerun_same_run_rejected(self):
        e=fake_env()
        e["GITHUB_RUN_ATTEMPT"]="2"
        with self.assertRaisesRegex(mod.Rejected, "BINDING_MISMATCH"):
            mod.validate_decision(json.dumps(fake_decision()).encode(), e, fake_profile(), "d"*64, NOW)

    def test_stolen_or_wrong_challenge_rejected(self):
        with self.assertRaisesRegex(mod.Rejected, "BINDING_MISMATCH"):
            mod.validate_decision(json.dumps(fake_decision()).encode(), fake_env(), fake_profile(), "f"*64, NOW)

    def test_wrong_source_rejected(self):
        d=fake_decision()
        d["product_sha"] = "e"*40
        with self.assertRaisesRegex(mod.Rejected, "BINDING_MISMATCH"):
            mod.validate_decision(json.dumps(d).encode(), fake_env(), fake_profile(), "d"*64, NOW)

    def test_expired_decision_rejected(self):
        now=NOW+dt.timedelta(minutes=5)
        with self.assertRaisesRegex(mod.Rejected, "EXPIRED"):
            mod.validate_decision(json.dumps(fake_decision()).encode(), fake_env(), fake_profile(), "d"*64, now)

    def test_overlong_authority_rejected(self):
        d=fake_decision()
        d["expires_at"]="2026-10-18T09:15:00Z"
        with self.assertRaisesRegex(mod.Rejected, "EXPIRED"):
            mod.validate_decision(json.dumps(d).encode(), fake_env(), fake_profile(), "d"*64, NOW)

    def test_duplicate_json_key_rejected(self):
        raw=b'{"action":"AUTHORIZE_BUILD_APP","action":"AUTHORIZE_BUILD_APP"}'
        with self.assertRaisesRegex(mod.Rejected, "DUPLICATE"):
            mod.validate_decision(raw, fake_env(), fake_profile(), "d"*64, NOW)

    def test_product_builder_rejects_before_docker_without_real_authorization(self):
        e=os.environ.copy()
        e.update({"GITHUB_REPOSITORY": mod.REPO, "GITHUB_EVENT_NAME": "workflow_dispatch",
                  "RUNNER_ENVIRONMENT": "github-hosted",
                  "G009_GATE_SHA": "a"*40, "G009_PRODUCT_SHA": mod.PRODUCT_SHA,
                  "GITHUB_SHA": "a"*40, "G009_DECISION_SHA256": "d"*64})
        e.pop("G009_AUTHORIZED", None)
        p=subprocess.run([sys.executable, "-B", "-I", str(BUILDER)],
                         cwd=ROOT, env=e, capture_output=True, text=True, timeout=12)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("REAL_SIGNED_BUILD_APP_AUTHORITY_OR_EXACT_SOURCE_MISSING", p.stderr)

    def test_absent_real_attestation_cannot_authorize(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"release-decision.json"
            path.write_text(json.dumps(fake_decision()))
            with patch.object(mod, "cmd", return_value="[]"):
                with self.assertRaisesRegex(mod.Rejected, "ATTESTATION_MISSING"):
                    mod.verify_sigstore(path, fake_profile(), "998877", "1")

    def test_existing_slsa_test_predicate_cannot_be_formal_build_authority(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"release-decision.json"
            path.write_text(json.dumps(fake_decision()))
            source={"verificationResult":{"signature":{"certificate":{
                "issuer":mod.ISSUER,"buildSignerDigest":"b"*40}},
                "statement":{"predicateType":"https://slsa.dev/provenance/v1",
                             "subject":[{"name":path.name,"digest":{"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}}]}}}
            with patch.object(mod, "cmd", return_value=json.dumps([source])):
                with self.assertRaisesRegex(mod.Rejected, "CERTIFICATE_RUN_OR_SUBJECT_MISMATCH"):
                    mod.verify_sigstore(path, fake_profile(), "998877", "1")

    def test_workflow_never_exposes_token_to_docker_build_step(self):
        y=WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("github.event_name == 'workflow_dispatch'", y)
        self.assertIn("environment: g009-build-authority", y)
        self.assertIn("steps.authorize.outputs.authorized == 'true'", y)
        self.assertIn("ref: " + mod.PRODUCT_SHA, y)
        self.assertIn("id-token: write", y)
        self.assertIn("G009_APPROVED_ISSUER_PROFILE_B64: ${{ vars.G009_APPROVED_ISSUER_PROFILE_B64 }}", y)
        build_step=y.split("      - name: Build and package actual immutable linux ARM64 Product image")[1].split("      - name: Preserve")[0]
        self.assertNotIn("GH_TOKEN:", build_step)
        self.assertNotIn("secrets.", build_step)
        self.assertNotIn("docker login", y.lower())
        self.assertNotIn("docker push", y.lower())

if __name__ == "__main__":
    unittest.main()
