"""G112 offline G027-vNext proof-of-design; never claims owner adoption or hosted PASS.
The immutable approved anchor hash MUST be injected from outside an untrusted PR
by an Owner-protected workflow. Here it is provided only for offline exercises.
"""
from __future__ import annotations
import argparse,hashlib,json,subprocess
from pathlib import Path

BASE_G062="fb07cea2d9fe20ebfc46b1093a9f86ecf680c985"
ACCEPTED_G110="35d3b5e843243ee3c1ce2b6974f1262cd9afaeee"
FINAL_G111="b01dfb0f285742a029e45924fcaef1e47aa210a5"
PR_HEAD_AT_LAST_LIVE_CHECK="aca38a85f1d407303ef3957ad864b583e2ffa0ac"
G027=".github/workflows/g009-source-snapshot.yml"

class Rejected(RuntimeError):
    def __init__(self,code):
        self.code=code
        super().__init__(code)

def insist(ok,code):
    if not ok:raise Rejected(code)

def git(root,*args):
    p=subprocess.run(["git","-C",str(root),*args],capture_output=True,timeout=120)
    insist(p.returncode==0,"GIT_COMMAND_FAILED")
    return p.stdout

def identity(root):
    return {"head":git(root,"rev-parse","HEAD").decode().strip(),
            "tree_oid":git(root,"rev-parse","HEAD^{tree}").decode().strip(),
            "clean":not git(root,"status","--porcelain=v1").strip()}

def get_entry(root,commit,path):
    out=git(root,"ls-tree",commit,"--",path).decode("utf-8","strict").strip()
    if not out:return {"exists":False}
    cols=out.split(None,3)
    insist(len(cols)==4 and cols[1]=="blob" and cols[3]==path,"INVALID_GIT_BLOB")
    data=git(root,"cat-file","blob",cols[2])
    return {"exists":True,"mode":cols[0],"git_oid":cols[2],
            "sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data)}

def read_changed_paths(root):
    raw=git(root,"diff","--name-only","-z",BASE_G062,FINAL_G111)
    return sorted(x.decode("utf-8","strict") for x in raw.split(b"\0") if x)

def build_offline_anchor(root):
    ident=identity(root)
    insist(ident["head"]==FINAL_G111 and ident["clean"],"BASELINE_NOT_CLEAN")
    ancestor=subprocess.run(["git","-C",str(root),"merge-base","--is-ancestor",
                             ACCEPTED_G110,FINAL_G111],capture_output=True)
    insist(ancestor.returncode==0,"G110_NOT_ANCESTOR")
    paths=read_changed_paths(root)
    insist(len(paths)==295,"G062_DELTA_COUNT_CHANGED")
    rows=[{"path":name,**get_entry(root,FINAL_G111,name)} for name in paths]
    # This document is LOCAL UNADOPTED; it does not bind an actual protected workflow.
    return {"schema":"G112_G027_VNEXT_UNADOPTED_LOCAL_OWNER_CANDIDATE_V1",
            "adoption":"NOT_OWNER_APPROVED","repository":"beatleswu/beatleswu.github.io",
            "accepted_ancestor":ACCEPTED_G110,"approved_base":BASE_G062,
            "expected_full_head":FINAL_G111,"full_git_tree_oid":ident["tree_oid"],
            "legacy_G027_workflow_oid":get_entry(root,ACCEPTED_G110,G027)["git_oid"],
            "changed_count":len(rows),
            "pathset_sha256":hashlib.sha256(b"\0".join(x.encode() for x in paths)).hexdigest(),
            "entries":rows,
            "required_external_controls":{
                "protected_workflow_uri":"UNASSIGNED",
                "protected_workflow_commit":"UNASSIGNED",
                "required_check_name":"g027-vnext-trusted-admission",
                "required_check_app_id":None,
                "anchor_owner_approval_id":None}}

def compare(expected,actual):
    insist(expected.get("schema")=="G112_G027_VNEXT_UNADOPTED_LOCAL_OWNER_CANDIDATE_V1","ANCHOR_SCHEMA")
    insist(expected.get("expected_full_head")==actual.get("expected_full_head"),"HEAD_PIN_MISMATCH")
    insist(expected.get("full_git_tree_oid")==actual.get("full_git_tree_oid"),"FULL_TREE_MISMATCH")
    insist(expected.get("legacy_G027_workflow_oid")==actual.get("legacy_G027_workflow_oid"),"LEGACY_WORKFLOW_DRIFT")
    ee=expected["entries"];aa=actual["entries"]
    insist(len(ee)==295 and len(aa)==295,"DELTA_COUNT")
    x={p["path"]:p for p in ee};y={p["path"]:p for p in aa}
    insist(len(x)==len(ee) and len(y)==len(aa),"DUPLICATE_PATH")
    insist(set(x)==set(y),"DELTA_PATHSET_DRIFT")
    for path in sorted(x):
        a=x[path];b=y[path]
        insist(a["exists"]==b["exists"],"BLOB_PRESENCE_DRIFT")
        if a["exists"]:
            for key,code in (("mode","GIT_MODE_MISMATCH"),("git_oid","GIT_BLOB_OID_MISMATCH"),
                             ("sha256","CONTENT_SHA_MISMATCH"),("bytes","CONTENT_LENGTH_MISMATCH")):
                insist(a[key]==b[key],code)
    insist(expected.get("pathset_sha256")==actual.get("pathset_sha256"),"PATHSET_DIGEST_MISMATCH")
    return {"verified_changed_paths":len(x),"full_tree_oid":actual["full_git_tree_oid"]}

def source_verify(root,anchor,provided_external_digest):
    data=anchor.read_bytes()
    insist(hashlib.sha256(data).hexdigest()==provided_external_digest,"ANCHOR_DIGEST_MISMATCH")
    pinned=json.loads(data)
    insist(pinned.get("repository")=="beatleswu/beatleswu.github.io","WRONG_REPO")
    insist(pinned.get("approved_base")==BASE_G062,"WRONG_BASE")
    insist(pinned.get("accepted_ancestor")==ACCEPTED_G110,"WRONG_ANCESTOR")
    insist(pinned.get("expected_full_head")==FINAL_G111,"WRONG_HEAD")
    insist(identity(root)["clean"],"WORKTREE_DIRTY")
    insist(identity(root)["head"]==FINAL_G111,"HEAD_CHANGED")
    insist(subprocess.run(["git","-C",str(root),"merge-base","--is-ancestor",
                           ACCEPTED_G110,FINAL_G111],capture_output=True).returncode==0,
           "G110_NOT_ANCESTOR")
    actual=build_offline_anchor(root)
    verdict=compare(pinned,actual)
    return {"verdict":"LOCAL_SOURCE_MATCH_UNADOPTED_NOT_HOSTED",
            "head":FINAL_G111,"anchor_sha256":provided_external_digest,
            "exact_files":verdict["verified_changed_paths"],
            "git_tree_oid":verdict["full_tree_oid"],
            "owner_policy_adopted":False,"github_hosted":False,"product_release":"NO_GO"}

def validate_check_provenance(check,approval):
    """Input must be independently fetched from GitHub by protected verifier.
    This local function ONLY demonstrates that check-name alone is insufficient.
    """
    insist(approval.get("owner_approval_id"),"OWNER_ADOPTION_MISSING")
    insist(approval.get("protected_workflow_commit"),"TRUSTED_WORKFLOW_MISSING")
    insist(isinstance(approval.get("required_check_app_id"),int),"CHECK_PROVIDER_NOT_PINNED")
    insist(check.get("name")==approval.get("required_check_name"),"CHECK_NAME_MISMATCH")
    insist(check.get("head_sha")==FINAL_G111,"CHECK_WRONG_SOURCE_SHA")
    insist(check.get("app_id")==approval["required_check_app_id"],"CHECK_PROVIDER_MISMATCH")
    insist(check.get("workflow_commit")==approval["protected_workflow_commit"],
           "CHECK_WORKFLOW_ORIGIN_MISMATCH")
    insist(check.get("conclusion")=="success" and check.get("status")=="completed","CHECK_NOT_SUCCESS")
    return True

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repo",type=Path,required=True)
    p.add_argument("--generate-anchor",type=Path)
    p.add_argument("--verify-anchor",type=Path)
    p.add_argument("--externally-pinned-anchor-sha256")
    p.add_argument("--receipt",type=Path)
    a=p.parse_args()
    if a.generate_anchor:
        insist(not a.generate_anchor.exists(),"REFUSE_ANCHOR_OVERWRITE")
        data=build_offline_anchor(a.repo)
        a.generate_anchor.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print(json.dumps({"local_anchor_sha256":hashlib.sha256(a.generate_anchor.read_bytes()).hexdigest(),
          "changed_paths":len(data["entries"]),"tree":data["full_git_tree_oid"],
          "adoption":"NOT_OWNER_APPROVED"}))
    else:
        insist(a.verify_anchor is not None and a.externally_pinned_anchor_sha256,"PIN_REQUIRED")
        result=source_verify(a.repo,a.verify_anchor,a.externally_pinned_anchor_sha256)
        if a.receipt:
            insist(not a.receipt.exists(),"REFUSE_RECEIPT_OVERWRITE")
            a.receipt.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(result))
if __name__=="__main__":
    try:main()
    except Rejected as exc:
        print(json.dumps({"verdict":"REJECTED","code":exc.code}))
        raise SystemExit(3)
