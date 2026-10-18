"""Test-only ephemeral GitHub hosted Docker proof must never run product builds."""
import os,sys,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/".github"/"scripts"/"g009_ephemeral_docker_broker_smoke.py"
WORKFLOW=ROOT/".github"/"workflows"/"g009-ephemeral-docker-broker-smoke.yml"

def test_broker_is_a_real_isolated_nonproduct_docker_smoke():
    s=SCRIPT.read_text(encoding="utf-8")
    w=WORKFLOW.read_text(encoding="utf-8")
    for flag in ('"candidate_product_build": False','"BUILD_APP_authorized": False',
                 '"release_authorized": False','"deployment_performed": False',
                 '"secret_mounted": False','"FROM scratch','"--network", "none"'):
        assert flag in s, flag
    for field in ("runs-on: ubuntu-24.04","persist-credentials: false",
                  "id-token: write","attestations: write",
                  "https://slsa.dev/provenance/v1",
                  "https://go-odyssey.invalid/attestations/build-authorization/v1"):
        assert field in w, field
    assert "docker/login-action" not in w

def test_local_spoofed_github_metadata_is_rejected_before_docker():
    env=os.environ.copy()
    env.update({"GITHUB_REPOSITORY":"wrong-account/forged","GITHUB_EVENT_NAME":"push",
                "GITHUB_REF":"refs/heads/candidate/g009-build-broker-isolation-20261018-r11",
                "GITHUB_SHA":"0"*40,"RUNNER_ENVIRONMENT":"github-hosted"})
    p=subprocess.run([sys.executable,"-B","-I",str(SCRIPT)],cwd=ROOT,env=env,
                     capture_output=True,text=True,timeout=20)
    assert p.returncode!=0
    assert "WRONG_REPOSITORY" in p.stderr
