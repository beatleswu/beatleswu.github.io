#!/usr/bin/env python3
"""G111 offline source admission PROPOSAL, NOT a trusted Hosted source policy.

The attestation is held OUTSIDE the evaluated PR worktree. Its SHA and
candidate full HEAD must be supplied by an independently protected Owner
workflow to become a valid authority. Self-supplied values are NOT trusted.
No GitHub actions, no network, no Git mutations, no production DB access.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,subprocess
from pathlib import Path

G110_ACCEPTED = "35d3b5e843243ee3c1ce2b6974f1262cd9afaeee"
REVIEWED_PR = "aca38a85f1d407303ef3957ad864b583e2ffa0ac"
G108_MANIFEST_SHA = "f5edab377f1b8446684c3acdfb465ea3ba2d5d7e4087b82ffae2f76d640f4209"
G110_NEW_FILES = (
    "deploy/g110-pr445-frozen-source-inventory.json",
    "docs/deployment/G110_source_and_migration_local_proposal.md",
    "migrations/g110_step_ledger_atomic_v1.py",
    "migrations/g110_step_ledger_atomic_v1.sql",
    "scripts/release/g110_local_admission_candidate.py",
    "tests/test_g110_migration_and_admission_contract.py",
)
ALLOWED_G111_CHANGES = frozenset((
    "tests/test_g076_step_http_isolated.py",
    "migrations/g111_nonmap_practice_mistakes_atomic_v1.py",
    "migrations/g111_nonmap_practice_mistakes_atomic_v1.sql",
    "tests/test_g111_nonmap_portable_contract.py",
    "scripts/release/g111_source_admission_draft.py",
    "docs/deployment/G111_PORTABLE_CI_AND_NONMAP_ROLLBACK_LOCAL_PROPOSAL.md",
))

class G111AdmissionRejected(RuntimeError):
    def __init__(self,code):
        super().__init__(code)
        self.code=code

def must(cond,code):
    if not cond:raise G111AdmissionRejected(code)

def git(root,*args):
    p=subprocess.run(["git","-C",str(root),*args],capture_output=True,timeout=70)
    must(p.returncode==0,"GIT_CHECK_FAILED")
    return p.stdout

def tree_entry(root,commit,path):
    raw=git(root,"ls-tree",commit,"--",path).decode("utf8","replace").strip()
    if not raw:return None
    split=raw.split(None,3)
    must(len(split)==4 and split[1]=="blob","NOT_BLOB")
    return {"mode":split[0],"oid":split[2]}

def fixed_inventory(root):
    f=root/"deploy/g110-pr445-frozen-source-inventory.json"
    b=f.read_bytes()
    must(hashlib.sha256(b).hexdigest()==G108_MANIFEST_SHA,"G108_MANIFEST_UNTRUSTED")
    obj=json.loads(b)
    must(len(obj.get("entries",[]))==283,"G108_REVIEWED_PATH_COUNT")
    return obj

def verify_old_source_untouched(root,full):
    manifest=fixed_inventory(root)
    accepted=set()
    change_permitted={"tests/test_g076_step_http_isolated.py"}
    for item in manifest["entries"]:
        path=item["path"]; entry=tree_entry(root,full,path)
        if path in change_permitted:
            prior=tree_entry(root,G110_ACCEPTED,path)
            must(prior is not None,"CLOCK_FIX_PRIOR_MISSING")
            # The only permitted modification of legacy reviewed source is
            # this one test module; the exact new bytes are attested separately.
            must(entry is not None,"PORTABLE_TEST_MISSING")
            accepted.add(path)
            continue
        if item["status"]=="DELETED_FROM_HEAD":
            must(entry is None,"OLD_DELETED_FILE_REINTRODUCED")
            continue
        must(entry is not None and entry["oid"]==item["git_blob_oid"]
             and entry["mode"]==item["mode"],"ORIGINAL_283_BLOB_DRIFT")
        accepted.add(path)
    must(len(manifest["entries"])==283,"REVIEWED_283_SCOPE")
    for path in G110_NEW_FILES:
        must(tree_entry(root,full,path)==tree_entry(root,G110_ACCEPTED,path),
             "OLD_G110_ACCEPTED_FILE_CHANGED")
    must(git(root,"show",full+":.github/workflows/g009-source-snapshot.yml")==
         git(root,"show",G110_ACCEPTED+":.github/workflows/g009-source-snapshot.yml"),
         "HISTORICAL_G027_WORKFLOW_CHANGED")
    return 283

def signed_expected(sha_manifest,candidate_head):
    must(sha_manifest.get("schema")=="G111_LOCAL_OWNER_UNADOPTED_SOURCE_PIN_V1","ATTESTATION_SCHEMA")
    must(sha_manifest.get("base_G110")==G110_ACCEPTED,"ATTESTATION_BASE")
    must(sha_manifest.get("candidate_G111")==candidate_head,"ATTESTATION_HEAD")
    entries=sha_manifest.get("entries")
    must(isinstance(entries,list) and len(entries)==len(ALLOWED_G111_CHANGES),"ATTESTATION_COUNT")
    names=[x.get("path") for x in entries]
    must(len(set(names))==len(names),"ATTESTATION_DUPLICATE")
    must(set(names)==ALLOWED_G111_CHANGES,"ATTESTATION_PATH_SCOPE")
    return {entry["path"]:entry for entry in entries}

def verify_delta_attestation(expected,actual):
    must(set(expected)==set(actual),"EXPECTED_DELTA_PATH_MISMATCH")
    for path in sorted(actual):
        claim=expected[path];real=actual[path]
        must(claim.get("mode")==real["mode"],"FILE_MODE_MISMATCH")
        must(claim.get("git_oid")==real["git_oid"],"GIT_OBJECT_MISMATCH")
        must(claim.get("content_sha256")==real["content_sha256"],"CONTENT_SHA_MISMATCH")
        must(claim.get("bytes")==real["bytes"],"SIZE_MISMATCH")
    return len(actual)

def negative_cases(expected,actual):
    cases=[
      ("fake_content","CONTENT_SHA_MISMATCH",lambda x:x[next(iter(x))].update(content_sha256="0"*64)),
      ("fake_oid","GIT_OBJECT_MISMATCH",lambda x:x[next(iter(x))].update(git_oid="0"*40)),
      ("fake_mode","FILE_MODE_MISMATCH",lambda x:x[next(iter(x))].update(mode="100755")),
      ("fake_size","SIZE_MISMATCH",lambda x:x[next(iter(x))].update(bytes=-1)),
      ("add_extra_path","EXPECTED_DELTA_PATH_MISMATCH",lambda x:x.update({"evil.txt":{"path":"evil.txt"}})),
      ("delete_path","EXPECTED_DELTA_PATH_MISMATCH",lambda x:x.pop(next(iter(x)))),
    ]
    results=[]
    for title,code,modify in cases:
        obj=copy.deepcopy(expected);modify(obj)
        try:verify_delta_attestation(obj,actual)
        except G111AdmissionRejected as err:
            must(err.code==code,"WRONG_NEGATIVE_REJECTION_"+title)
            results.append({"case":title,"expected_rejection":code})
        else:raise G111AdmissionRejected("FORGED_DELTA_ACCEPTED_"+title)
    return results

def verify(root,expected_head,external_manifest,expected_external_sha):
    must(len(expected_head)==40,"EXPECTED_SHA_REQUIRED")
    must(git(root,"rev-parse","HEAD").decode().strip()==expected_head,"HEAD_CHANGED")
    must(not git(root,"status","--porcelain=v1").strip(),"DIRTY_WORKTREE")
    must(git(root,"merge-base",G110_ACCEPTED,expected_head).decode().strip()==G110_ACCEPTED,"G110_NOT_ANCESTOR")
    diff={x.decode("utf8") for x in git(root,"diff","--name-only","-z",G110_ACCEPTED,expected_head).split(b"\0") if x}
    must(diff==ALLOWED_G111_CHANGES,"G111_DELTA_PATHS")
    must(not git(root,"diff","--check",G110_ACCEPTED,expected_head).strip(),"DIFF_WHITESPACE")
    old=verify_old_source_untouched(root,expected_head)
    att_bytes=external_manifest.read_bytes()
    must(hashlib.sha256(att_bytes).hexdigest()==expected_external_sha,"EXTERNAL_MANIFEST_SHA")
    obj=json.loads(att_bytes)
    claims=signed_expected(obj,expected_head)
    actual={}
    for name in sorted(ALLOWED_G111_CHANGES):
        entry=tree_entry(root,expected_head,name)
        must(entry is not None,"MISSING_ATTACHED_SOURCE")
        contents=git(root,"cat-file","blob",entry["oid"])
        actual[name]={"mode":entry["mode"],"git_oid":entry["oid"],
                      "content_sha256":hashlib.sha256(contents).hexdigest(),
                      "bytes":len(contents)}
    count=verify_delta_attestation(claims,actual)
    rejected=negative_cases(claims,actual)
    return {"verdict":"LOCAL_ONLY_NOT_OWNER_ADOPTED",
            "G111_head":expected_head,"unchanged_G110_parent":G110_ACCEPTED,
            "reviewed_legacy_source_entries":old,
            "new_exact_delta_count":count,"negative_exact_rejections":rejected,
            "external_manifest_sha256":expected_external_sha,
            "old_hosted_G027":"FAIL","new_hosted_source_policy":"NOT_AUTHORIZED",
            "GO_MERGE":False,"GO_DEPLOY":False,"production_data_writes":0,
            "release":"NO_GO"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--expected-head",required=True)
    p.add_argument("--external-manifest",type=Path,required=True)
    p.add_argument("--external-manifest-sha256",required=True)
    p.add_argument("--receipt",type=Path,required=True)
    a=p.parse_args()
    must(not a.receipt.exists(),"RECEIPT_ALREADY_EXISTS")
    must(not a.external_manifest.resolve().is_relative_to(a.root.resolve()),
         "EXTERNAL_POLICY_CANNOT_LIVE_IN_UNTRUSTED_SOURCE")
    result=verify(a.root,a.expected_head,a.external_manifest,a.external_manifest_sha256)
    a.receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8",newline="\n")
    print(json.dumps({"status":result["verdict"],"reviewed_legacy":result["reviewed_legacy_source_entries"],
      "new_delta_files":result["new_exact_delta_count"],"spoof_rejections":len(result["negative_exact_rejections"]),
      "G027":"FAIL","Product_release":"NO_GO"},ensure_ascii=False))
if __name__=="__main__":main()
