#!/usr/bin/env python3
"""Produce the actual ARM64 Product image from a pinned immutable Git commit ONLY after
GHA's approved build-authority verification job step succeeds. No deploy/SSH/push.
"""
from __future__ import annotations
import datetime as dt
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

REPO = "beatleswu/beatleswu.github.io"
PRODUCT = "69dbe57aa535112b1759e3f3bdcf9ecbe1680efb"
SGF = "d729645c0ae267be6d89a5b49c007bc64284bbcc"
IMAGE = "go-odyssey-app:" + PRODUCT[:8]

def cmd(args, *, cwd=None, timeout=7200):
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    if p.returncode:
        print(p.stdout[-2000:] if p.stdout else "", file=sys.stderr)
        raise RuntimeError(f"BUILD_COMMAND_FAILED({args[0:3]}): {p.stderr[-900:]}")
    return p.stdout.strip()

def sha_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    e = os.environ
    if (e.get("GITHUB_REPOSITORY") != REPO or
            e.get("GITHUB_EVENT_NAME") != "workflow_dispatch" or
            e.get("RUNNER_ENVIRONMENT") != "github-hosted" or
            e.get("G009_AUTHORIZED") != "true" or
            e.get("G009_PRODUCT_SHA") != PRODUCT or
            e.get("G009_GATE_SHA") != e.get("GITHUB_SHA") or
            not e.get("G009_DECISION_SHA256") or
            len(e["G009_DECISION_SHA256"]) != 64):
        raise RuntimeError("REAL_SIGNED_BUILD_APP_AUTHORITY_OR_EXACT_SOURCE_MISSING")
    root = Path.cwd()
    product = root / "product"
    if (cmd(["git", "-C", str(product), "rev-parse", "HEAD"]) != PRODUCT
            or cmd(["git", "-C", str(product), "status", "--porcelain=v1", "--untracked-files=normal"])):
        raise RuntimeError("PRODUCT_SOURCE_NOT_THE_CLEAN_EXACT_COMMIT")
    if not all((product / x).is_file() for x in ("Dockerfile", "requirements.txt",
                                                   "sgf_engine/VENDORED_FROM.txt", "sgf_engine/__init__.py")):
        raise RuntimeError("PRODUCT_RUNTIME_DOCKER_INPUTS_MISSING")
    build_utc = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # This invokes the original, curated Product Dockerfile. The GitHub runner
    # holds Docker; the Windows candidate child script has no Docker capability.
    # No application credentials or secret mounts are supplied to this build.
    args = ["docker", "buildx", "build", "--platform", "linux/arm64",
            "--progress", "plain", "--load",
            "--build-arg", "APP_GIT_SHA=" + PRODUCT,
            "--build-arg", "APP_BUILD_DATE=" + build_utc,
            "--build-arg", "SGF_ENGINE_SOURCE_COMMIT=" + SGF,
            "-t", IMAGE, str(product)]
    # Stream build progress to Actions logs; never print environment secrets.
    process = subprocess.run(args, check=False, timeout=7200)
    if process.returncode:
        raise RuntimeError("REAL_ARM64_PRODUCT_DOCKER_BUILD_FAILED")
    meta = json.loads(cmd(["docker", "image", "inspect", IMAGE]))
    if len(meta) != 1 or meta[0]["Architecture"] != "arm64" or meta[0]["Os"] != "linux":
        raise RuntimeError("BUILT_IMAGE_NOT_REAL_LINUX_ARM64")
    labels = meta[0]["Config"]["Labels"]
    if (labels.get("org.opencontainers.image.revision") != PRODUCT
            or labels.get("com.godokoro.sgf-engine.source-commit") != SGF):
        raise RuntimeError("BUILT_IMAGE_REVISION_OR_SGF_LABEL_MISMATCH")
    # Export a self-contained candidate image without publishing or loading it
    # into production. Gzip is streamed so the uncompressed tar isn't duplicated.
    output = Path(e["RUNNER_TEMP"]) / ("go-odyssey-app-" + PRODUCT[:8] + "-linux-arm64.tar.gz")
    producer = subprocess.Popen(["docker", "save", IMAGE], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        with output.open("wb") as fp:
            with gzip.GzipFile(filename="", mode="wb", fileobj=fp, compresslevel=5) as z:
                while True:
                    chunk = producer.stdout.read(1024 * 1024)
                    if not chunk:
                        break
                    z.write(chunk)
        err = producer.stderr.read()
        if producer.wait(timeout=300) != 0:
            raise RuntimeError("DOCKER_SAVE_FAILED:" + err.decode("utf-8", "replace")[-400:])
    finally:
        if producer.poll() is None:
            producer.kill()
    rec = {
        "schema": "g009-real-authorized-product-build-v1",
        "github_run_id": e["GITHUB_RUN_ID"],
        "github_run_attempt": e["GITHUB_RUN_ATTEMPT"],
        "gate_sha": e["G009_GATE_SHA"],
        "product_sha": PRODUCT,
        "signed_decision_sha256": e["G009_DECISION_SHA256"],
        "build_platform": "linux/arm64",
        "image_tag": IMAGE,
        "image_id": meta[0]["Id"],
        "sgf_commit": SGF,
        "archive_name": output.name,
        "archive_sha256": sha_file(output),
        "archive_bytes": output.stat().st_size,
        "no_deploy_performed": True,
        "no_image_registry_push": True,
        "signed_BUILD_APP_accepted_by_external_verifier": True,
        "release_authorized": False,
    }
    receipt = Path(e["RUNNER_TEMP"]) / "G009_REAL_PRODUCT_BUILD_RECEIPT.json"
    receipt.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with open(e["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
        f.write("archive=" + output.as_posix() + "\n")
        f.write("receipt=" + receipt.as_posix() + "\n")
    print(json.dumps({"image_tag": IMAGE, "archive_sha256": rec["archive_sha256"],
                      "archive_bytes": rec["archive_bytes"], "release_authorized": False}))

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("G009_PRODUCT_BUILD_FAILED_CLOSED: " + str(exc), file=sys.stderr)
        sys.exit(1)
