"""G106 GitHub read-only provenance verification. Does not access deployment secrets."""
import hashlib
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_PRODUCT_SHA = "8d9fedcdb7c57b9e88febb03e38d0827267cfb8d"
ALLOWED_CI_ONLY = {
    ".github/workflows/g106-fastrelease-ci.yml",
    "scripts/g106_ci_provenance_gate.py",
}

def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], stderr=subprocess.PIPE)

def ensure(condition, message):
    if not condition:
        raise RuntimeError(message)

def main():
    if os.environ.get("GITHUB_REPOSITORY"):
        ensure(os.environ["GITHUB_REPOSITORY"] == "beatleswu/beatleswu.github.io", "WRONG_REPO")
    head = git("rev-parse", "HEAD").decode("ascii").strip()
    ensure(git("status", "--porcelain=v1").strip() == b"", "CHECKOUT_DIRTY")
    git("merge-base", "--is-ancestor", EXPECTED_PRODUCT_SHA, head)
    changed = set(git("diff", "--name-only", EXPECTED_PRODUCT_SHA, head).decode("utf8").splitlines())
    ensure(changed == ALLOWED_CI_ONLY, "CI_GATE_CHANGED_PRODUCT_FILES:"+repr(sorted(changed)))
    manifest = json.loads((ROOT/"deploy/runtime-source-provenance.json").read_text(encoding="utf8"))
    entries = manifest["files"]
    paths=set()
    for entry in entries:
        path = entry["path"]
        parsed = pathlib.PurePosixPath(path)
        ensure(path and path not in paths and not parsed.is_absolute() and ".." not in parsed.parts, "BAD_PATH")
        paths.add(path)
        content=(ROOT/path).read_bytes()
        ensure(hashlib.sha256(content).hexdigest()==entry["content_sha256"],"CONTENT_SHA_DRIFT:"+path)
        if "content_size_bytes" in entry:
            ensure(len(content)==entry["content_size_bytes"],"SIZE_DRIFT:"+path)
        source_commit=entry["source_commit"]
        git("merge-base", "--is-ancestor",source_commit,head)
        blob=git("cat-file","blob",source_commit+":"+path)
        ensure(content==blob,"SOURCE_BLOB_DRIFT:"+path)
        subject=git("show","-s","--format=%s",source_commit).decode("utf8").strip()
        date=git("show","-s","--format=%cs",source_commit).decode("ascii").strip()
        ensure(entry["source_commit_subject"]==subject,"SUBJECT_DRIFT:"+path)
        ensure(entry["source_date"]==date,"DATE_DRIFT:"+path)
        if entry["line_ending_policy"]=="LF":
            ensure(b"\r\n" not in content,"CRLF_DRIFT:"+path)
    result={
        "schema":"G106_GITHUB_CI_SOURCE_INDEPENDENT_RUNTIME_BLOB_GATE_V1",
        "ci_commit":head,"product_content_parent":EXPECTED_PRODUCT_SHA,
        "manifest_file_count":len(entries),
        "git_object_bytes_and_ancestry":"ALL_MATCH",
        "product_changes_after_parent":0,
        "ci_only_paths":sorted(changed),
        "hosted_CI_production_access":0,
        "formal_release_attestation":False,
    }
    print(json.dumps(result,sort_keys=True,ensure_ascii=True))
    return 0

if __name__=="__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("G106_CI_FAIL_CLOSED:"+type(e).__name__+":"+str(e)[:250],file=sys.stderr)
        sys.exit(1)
