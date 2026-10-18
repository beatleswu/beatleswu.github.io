#!/usr/bin/env python3
"""Real Docker execution in an ephemeral GitHub-hosted runner, WITHOUT product authority."""
from __future__ import annotations
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

REPO = "beatleswu/beatleswu.github.io"
REF = "refs/heads/candidate/g009-build-broker-isolation-20261018-r11"
PARENT = "f1c317de5242d3a93520d160330eeba7bdb2d203"

def invoke(argv, *, cwd=None):
    p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=240)
    if p.returncode:
        raise RuntimeError(f"failed {argv!r}, exit={p.returncode}: {p.stderr[-900:]}")
    return p.stdout.strip()

def main():
    if os.environ.get("GITHUB_REPOSITORY") != REPO:
        raise ValueError("WRONG_REPOSITORY")
    if os.environ.get("GITHUB_REF") != REF or os.environ.get("GITHUB_EVENT_NAME") != "push":
        raise ValueError("NOT_THE_APPROVED_BROKER_CANDIDATE_BRANCH_PUSH")
    if os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
        raise ValueError("NOT_GITHUB_HOSTED_RUNNER")
    head = invoke(["git", "rev-parse", "HEAD"])
    if head != os.environ.get("GITHUB_SHA"):
        raise ValueError("CHECKOUT_COMMIT_DOES_NOT_MATCH_GITHUB_EVENT")
    if invoke(["git", "rev-parse", "HEAD^"]) != PARENT:
        raise ValueError("BROKER_PARENT_COMMIT_CHANGED")
    if invoke(["git", "status", "--porcelain=v1", "--untracked-files=normal"]):
        raise ValueError("CHECKOUT_DIRTY")
    if not os.environ.get("RUNNER_TEMP"):
        raise ValueError("RUNNER_TEMP_MISSING")
    temp = Path(os.environ["RUNNER_TEMP"])
    context = temp / "g009-ephemeral-smoke-context"
    context.mkdir(mode=0o700, exist_ok=False)
    data = b"G009 isolated Docker build smoke fixture, NOT production artifact.\n"
    (context / "fixture.txt").write_bytes(data)
    (context / "Dockerfile").write_text(
        "FROM scratch\nCOPY fixture.txt /g009-smoke-fixture.txt\n"
        f"LABEL org.opencontainers.image.revision=\"{head}\"\n"
        "LABEL com.godokoro.g009.authority=\"test-only-NO-BUILD_APP\"\n",
        encoding="utf-8")
    image = "g009-ephemeral-broker-smoke:" + head[:12]
    # FROM scratch and a known fixture; no external registry, BuildKit network,
    # code execution from the product, secrets, staging, or deployment.
    invoke(["docker", "buildx", "build", "--platform", "linux/amd64",
            "--network", "none", "--load", "--pull=false", "--progress", "plain",
            "-t", image, str(context)])
    meta = json.loads(invoke(["docker", "image", "inspect", image]))
    if len(meta) != 1 or meta[0]["Architecture"] != "amd64" or meta[0]["Os"] != "linux":
        raise ValueError("IMAGE_PLATFORM_VERIFICATION_FAILED")
    labels = meta[0]["Config"]["Labels"]
    if (labels.get("org.opencontainers.image.revision") != head
            or labels.get("com.godokoro.g009.authority") != "test-only-NO-BUILD_APP"):
        raise ValueError("IMAGE_SOURCE_OR_AUTHORITY_LABEL_MISMATCH")
    if not invoke(["docker", "image", "inspect", "--format", "{{.Id}}", image]).startswith("sha256:"):
        raise ValueError("IMAGE_DIGEST_MISSING")
    # The real production image is linux/arm64, not the host's amd64. Prove
    # that QEMU can execute ARM64 instructions rather than simply packaging
    # scratch layers whose architecture metadata could be falsified.
    arm_file = context / "Dockerfile.arm64"
    arm_file.write_text(
        "FROM alpine:3.20\n"
        "RUN test \"$(uname -m)\" = \"aarch64\"\n"
        "COPY fixture.txt /g009-smoke-fixture.txt\n"
        f"LABEL org.opencontainers.image.revision=\"{head}\"\n"
        "LABEL com.godokoro.g009.authority=\"test-only-NO-BUILD_APP\"\n",
        encoding="utf-8")
    arm_image = "g009-ephemeral-broker-arm64:" + head[:12]
    invoke(["docker", "buildx", "build", "--platform", "linux/arm64",
            "--network", "none", "--load", "--progress", "plain",
            "--file", str(arm_file), "-t", arm_image, str(context)])
    arm = json.loads(invoke(["docker", "image", "inspect", arm_image]))
    if (len(arm) != 1 or arm[0]["Architecture"] != "arm64"
            or arm[0]["Os"] != "linux"
            or arm[0]["Config"]["Labels"].get("org.opencontainers.image.revision") != head
            or arm[0]["Config"]["Labels"].get("com.godokoro.g009.authority") != "test-only-NO-BUILD_APP"):
        raise ValueError("ARM64_IMAGE_SOURCE_OR_ARCH_MISMATCH")
    execution = invoke(["docker", "run", "--rm", "--platform", "linux/arm64",
                        "--network", "none", "--entrypoint", "uname",
                        arm_image, "-m"])
    if execution != "aarch64":
        raise ValueError("QEMU_ARM64_EXECUTION_MISMATCH")
    record = {
        "schema": "g009-ephemeral-docker-broker-test-only-v1",
        "repo": REPO, "git_ref": REF, "git_head": head,
        "run_id": os.environ["GITHUB_RUN_ID"],
        "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "runner_environment": os.environ["RUNNER_ENVIRONMENT"],
        "docker_isolated_runner": True,
        "docker_build_execution": "PASS",
        "build_context_sha256": hashlib.sha256(data).hexdigest(),
        "output_image_id": meta[0]["Id"],
        "output_platform": "linux/amd64",
        "arm64_output_image_id": arm[0]["Id"],
        "arm64_output_platform": "linux/arm64",
        "arm64_instruction_execution": execution,
        "candidate_product_build": False, "BUILD_APP_authorized": False,
        "source_signoff_admitted": False, "release_authorized": False,
        "deployment_performed": False, "secret_mounted": False,
        "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    receipt = temp / "G009_EPHEMERAL_DOCKER_BROKER_TEST_ONLY_RECEIPT.json"
    receipt.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
        f.write("receipt=" + receipt.as_posix() + "\n")
    print(json.dumps({"stage": "REAL_EPHEMERAL_DOCKER_BUILD_AND_IMAGE_PROVENANCE_PASS",
                      "source": head, "image": meta[0]["Id"],
                      "formal_BUILD_APP": False, "receipt": str(receipt)}))

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("G009_EPHEMERAL_BROKER_SMOKE_REJECTED: " + repr(exc), file=sys.stderr)
        sys.exit(1)
