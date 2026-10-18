#!/usr/bin/env python3
"""Post-Build, pre-Deploy image acceptance for the Owner-admitted sixth E10 stylesheet (G009 Zone4 option B, cond. 4).

Run only after a separately authorised Build produced a real image. Every step must pass or the result is
REJECT_DEPLOY (exit 1):
  1. ``docker image inspect``: the image Id equals --expected-image-id (sha256:<64 hex>) and, if given,
     --expected-repo-digest is among RepoDigests and --expected-revision equals org.opencontainers.image.revision.
  2. A container is *created* from the exact image Id with no mounts and no network; its inspect shows no bind mount
     and no volume covering the asset; the asset is copied out of the container filesystem (``docker cp``) and must
     be a single regular file with the pinned SHA-256 and size.
  3. A container is *started* from the exact image Id (loopback port only, no bind mounts, optional --env for runtime
     configuration); GET and HEAD on the route must return 200 with ``text/css`` and the GET body must have the pinned
     SHA-256. Cleanup is attempted only for containers with proven ownership;
     unknown identities are retained and reported as cleanup failures. Volumes are never removed.

No host file can stand in for the image file: steps 2 and 3 read only from containers of the pinned image Id, and any
bind mount or covering volume is a rejection. Test doubles may exercise the rejection logic; such runs are never an
image acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import secrets
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import urllib.parse

TOOL_VERSION = "1.0.0"
IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
DEFAULT_ASSET_PATH = "/app/css/e10/backpack.css"
DEFAULT_ROUTE = "/css/e10/backpack.css"
DEFAULT_SHA = "a7bb0e14a24f8845c79f4850c36f37f7c69c49452d3699a93bbbfdd2fe93c888"
DEFAULT_SIZE = 25459
CLEANUP_TIMEOUT = 10.0
CLEANUP_COMMAND_TIMEOUT = 2.0
CLEANUP_ABSENCE_CHECKS = 5
CLEANUP_POLL_INTERVAL = 0.25


class DockerCli:
    def run(self, args, timeout=120):
        p = subprocess.run(["docker", *args], capture_output=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_request(url, method="GET", timeout=10):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
            or parsed.username is not None or parsed.password is not None
            or parsed.path != DEFAULT_ROUTE or parsed.query or parsed.fragment
            or not parsed.port or method not in {"GET", "HEAD"}):
        raise Rejected("only the exact original loopback HTTP route is permitted")
    # Ignore all ambient proxy configuration, and never follow any 3xx, for
    # either GET or HEAD (including redirects back onto loopback).
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    req = urllib.request.Request(url, method=method)
    try:
        with opener.open(req, timeout=timeout) as resp:
            if resp.geturl() != url or 300 <= resp.status < 400:
                raise Rejected("redirected HTTP response is forbidden")
            return resp.status, dict(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as exc:
        try:
            if 300 <= exc.code < 400:
                raise Rejected(f"HTTP {method} redirect {exc.code} is forbidden")
            return exc.code, dict(exc.headers.items()), exc.read()
        finally:
            exc.close()


class Rejected(Exception):
    pass


def _inspect(docker, ref, timeout=120):
    rc, out, err = docker.run(["inspect", "--format", "{{json .}}", ref], timeout=timeout)
    if rc != 0:
        raise Rejected(f"docker inspect {ref} failed: {err.decode('utf-8', 'replace').strip()[:300]}")
    try:
        return json.loads(out.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise Rejected(f"docker inspect {ref} returned non-JSON") from exc


def _check_mounts(info, asset_path, label):
    for mount in info.get("Mounts") or []:
        if mount.get("Type") == "bind":
            raise Rejected(f"{label}: bind mount present ({mount.get('Source')} -> {mount.get('Destination')})")
        dest = (mount.get("Destination") or "").rstrip("/") + "/"
        if (asset_path + "/").startswith(dest):
            raise Rejected(f"{label}: volume mounted over {mount.get('Destination')} covers {asset_path}")
    binds = (info.get("HostConfig") or {}).get("Binds")
    if binds:
        raise Rejected(f"{label}: HostConfig.Binds present {binds}")


def verify(args, docker=None, http=http_request, sleep=time.sleep):
    docker = docker or DockerCli()
    steps = []
    created = []
    removed = []
    cleanup_errors = []
    uncertain_creations = set()

    def step(name, ok, observed, expected=None):
        steps.append({"step": name, "pass": bool(ok), "observed": observed, "expected": expected})
        if not ok:
            raise Rejected(f"{name}: observed {observed!r}, expected {expected!r}")

    def container_ids(name, timeout=120):
        rc, out, err = docker.run(["container", "ls", "-a", "--no-trunc", "--filter",
                                   f"name=^/{name}$", "--format", "{{.ID}}"], timeout=timeout)
        if rc != 0:
            raise Rejected(f"cannot prove container name absence: {err.decode('utf-8', 'replace')[:200]}")
        return out.decode("utf-8").strip().splitlines()

    def reserve_name(prefix):
        name = prefix + secrets.token_hex(16)
        if container_ids(name):
            raise Rejected("container name already exists; no ownership or cleanup claimed")
        token = secrets.token_hex(32)
        # Register before invoking Docker: it may create then fail or time out.
        created.append((name, token))
        uncertain_creations.add(name)
        return name, token

    try:
        if (args.route != DEFAULT_ROUTE or args.asset_path != DEFAULT_ASSET_PATH
                or args.expected_sha != DEFAULT_SHA or args.expected_size != DEFAULT_SIZE):
            raise Rejected("only the original backpack image path, route, SHA and size are permitted")
        if not IMAGE_ID_RE.fullmatch(args.expected_image_id or ""):
            raise Rejected("--expected-image-id must be sha256:<64 lowercase hex>")
        image = _inspect(docker, args.image)
        step("image_id", image.get("Id") == args.expected_image_id, image.get("Id"), args.expected_image_id)
        if args.expected_repo_digest:
            step("repo_digest", args.expected_repo_digest in (image.get("RepoDigests") or []), image.get("RepoDigests"), args.expected_repo_digest)
        if args.expected_revision:
            labels = (image.get("Config") or {}).get("Labels") or {}
            step("oci_revision", labels.get("org.opencontainers.image.revision") == args.expected_revision,
                 labels.get("org.opencontainers.image.revision"), args.expected_revision)
        image_id = image["Id"]

        # 2. file inside the image filesystem
        name, token = reserve_name("g009-imgverify-")
        rc, out, err = docker.run(["create", "--name", name, "--label", f"g009.verifier.owner={token}", "--network", "none", image_id])
        if rc == 0:
            uncertain_creations.discard(name)
        step("create_container", rc == 0, err.decode("utf-8", "replace").strip()[:200] if rc else "created")
        cinfo = _inspect(docker, name)
        step("created_container_image", cinfo.get("Image") == image_id, cinfo.get("Image"), image_id)
        _check_mounts(cinfo, args.asset_path, "created container")
        steps.append({"step": "created_container_no_masking_mount", "pass": True, "observed": cinfo.get("Mounts") or []})
        rc, tar_bytes, err = docker.run(["cp", f"{name}:{args.asset_path}", "-"])
        step("copy_asset_from_image", rc == 0, err.decode("utf-8", "replace").strip()[:200] if rc else "copied")
        with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tar:
            members = tar.getmembers()
            step("asset_is_single_regular_file", len(members) == 1 and members[0].isreg(),
                 [(m.name, m.type.decode() if isinstance(m.type, bytes) else m.type) for m in members], "one regular file")
            data = tar.extractfile(members[0]).read()
        step("asset_sha256_in_image", hashlib.sha256(data).hexdigest() == args.expected_sha, hashlib.sha256(data).hexdigest(), args.expected_sha)
        step("asset_size_in_image", len(data) == args.expected_size, len(data), args.expected_size)

        # 3. served by a container of the same image
        run_name, run_token = reserve_name("g009-imgverify-run-")
        run_args = ["run", "-d", "--name", run_name, "--label", f"g009.verifier.owner={run_token}", "-p", f"127.0.0.1::{args.container_port}"]
        for item in args.env or []:
            run_args += ["--env", item]
        run_args.append(image_id)
        rc, out, err = docker.run(run_args)
        if rc == 0:
            uncertain_creations.discard(run_name)
        step("start_container", rc == 0, err.decode("utf-8", "replace").strip()[:200] if rc else "started")
        rinfo = _inspect(docker, run_name)
        step("running_container_image", rinfo.get("Image") == image_id, rinfo.get("Image"), image_id)
        _check_mounts(rinfo, args.asset_path, "running container")
        rc, out, _ = docker.run(["port", run_name, f"{args.container_port}/tcp"])
        mapping = out.decode("utf-8", "replace").strip().splitlines()
        host = mapping[0] if len(mapping) == 1 else None
        valid_host = host is not None and re.fullmatch(r"127\.0\.0\.1:[0-9]{1,5}", host) is not None
        valid_host = valid_host and 0 < int(host.rsplit(":", 1)[1]) <= 65535
        step("loopback_port_mapping", rc == 0 and valid_host, mapping, "127.0.0.1:<port>")
        url = f"http://{host}{args.route}"
        deadline = time.monotonic() + args.ready_timeout
        status, headers, body = None, {}, b""
        while True:
            try:
                status, headers, body = http(url, "GET")
                if 300 <= status < 400:
                    raise Rejected(f"HTTP GET redirect {status} is forbidden")
                if status == 200:
                    break
            except OSError:
                status = None
            if time.monotonic() >= deadline:
                break
            sleep(1)
        ctype = {k.lower(): v for k, v in headers.items()}.get("content-type", "")
        step("http_get_200", status == 200, status, 200)
        step("http_get_text_css", ctype.split(";")[0].strip() == "text/css", ctype, "text/css")
        step("http_get_body_sha256", hashlib.sha256(body).hexdigest() == args.expected_sha, hashlib.sha256(body).hexdigest(), args.expected_sha)
        hstatus, hheaders, hbody = http(url, "HEAD")
        if 300 <= hstatus < 400:
            raise Rejected(f"HTTP HEAD redirect {hstatus} is forbidden")
        hctype = {k.lower(): v for k, v in hheaders.items()}.get("content-type", "")
        step("http_head_200_text_css_empty", hstatus == 200 and hctype.split(";")[0].strip() == "text/css" and hbody == b"",
             {"status": hstatus, "content_type": hctype, "body_len": len(hbody)}, {"status": 200, "content_type": "text/css", "body_len": 0})
        verdict = "IMAGE_BACKPACK_VERIFIED"
        reason = None
    except Rejected as exc:
        verdict, reason = "REJECT_DEPLOY", str(exc)
    except Exception as exc:  # anything unexpected is a rejection, never an acceptance
        verdict, reason = "REJECT_DEPLOY", f"{type(exc).__name__}: {exc}"
    finally:
        # Killing a timed-out CLI does not cancel the daemon's pending create.
        # Bound the entire cleanup and each CLI call; absence after an uncertain
        # create is unresolved, never proof that a late container cannot appear.
        cleanup_deadline = time.monotonic() + CLEANUP_TIMEOUT

        def cleanup_timeout():
            remaining = cleanup_deadline - time.monotonic()
            if remaining <= 0:
                raise Rejected("cleanup deadline exceeded")
            return min(CLEANUP_COMMAND_TIMEOUT, remaining)

        for name, token in created:
            try:
                for attempt in range(CLEANUP_ABSENCE_CHECKS):
                    ids = container_ids(name, timeout=cleanup_timeout())
                    if ids or name not in uncertain_creations:
                        break
                    if attempt + 1 < CLEANUP_ABSENCE_CHECKS:
                        sleep(min(CLEANUP_POLL_INTERVAL, cleanup_timeout()))
                if not ids:
                    if name in uncertain_creations:
                        raise Rejected("unresolved late container creation after bounded absence checks")
                    continue  # proved absent; never claim it was removed
                if len(ids) != 1 or not re.fullmatch(r"[0-9a-f]{64}", ids[0]):
                    raise Rejected("ambiguous container identity; refusing cleanup")
                info = _inspect(docker, ids[0], timeout=cleanup_timeout())
                labels = (info.get("Config") or {}).get("Labels") or {}
                if (info.get("Id") != ids[0] or info.get("Name") != "/" + name
                        or info.get("Image") != image_id or labels.get("g009.verifier.owner") != token):
                    raise Rejected("container ownership unproven; refusing cleanup")
                # Remove the proven immutable ID, never a potentially rebound name.
                # No -v: anonymous volumes and unrelated resources are untouched.
                rc, _, err = docker.run(["rm", "-f", ids[0]], timeout=cleanup_timeout())
                if rc != 0:
                    raise Rejected(f"removal exit {rc}: {err.decode('utf-8', 'replace')[:200]}")
                else:
                    removed.append(name)
            except Exception as exc:
                cleanup_errors.append(f"{name}: {type(exc).__name__}: {exc}; manual follow-up required")
        if cleanup_errors:
            verdict, reason = "REJECT_DEPLOY", "container cleanup failed: " + "; ".join(cleanup_errors)
    return {"tool": "verify_release_image_backpack.py", "tool_version": TOOL_VERSION, "image": args.image,
            "expected_image_id": args.expected_image_id, "steps": steps, "status": verdict, "reason": reason,
            "containers_removed": removed, "cleanup_errors": cleanup_errors}


def parser():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--image", required=True, help="image reference (tag or id) produced by the authorised Build")
    ap.add_argument("--expected-image-id", required=True)
    ap.add_argument("--expected-repo-digest")
    ap.add_argument("--expected-revision", help="expected org.opencontainers.image.revision (product commit)")
    ap.add_argument("--asset-path", default=DEFAULT_ASSET_PATH)
    ap.add_argument("--route", default=DEFAULT_ROUTE)
    ap.add_argument("--expected-sha", default=DEFAULT_SHA)
    ap.add_argument("--expected-size", type=int, default=DEFAULT_SIZE)
    ap.add_argument("--container-port", default="8080")
    ap.add_argument("--env", action="append", help="KEY=VALUE runtime configuration for the started container")
    ap.add_argument("--ready-timeout", type=float, default=90)
    ap.add_argument("--out", required=True)
    return ap


def main(argv=None):
    args = parser().parse_args(argv)
    result = verify(args)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    print(json.dumps({"status": result["status"], "reason": result["reason"]}, indent=1))
    return 0 if result["status"] == "IMAGE_BACKPACK_VERIFIED" else 1


if __name__ == "__main__":
    sys.exit(main())
