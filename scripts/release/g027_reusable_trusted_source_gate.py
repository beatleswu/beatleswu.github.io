"""G027 reusable trusted-source gate. Run ONLY from protected base in pull_request_target.

Owner approval MUST be an admin-controlled GitHub Actions repository variable,
never a checked-in PR/branch file. PR content is inspected as static Git data;
no scripts or hooks are run from the candidate checkout.
"""
from __future__ import annotations
import argparse,base64,binascii,datetime,hashlib,json,os,re,subprocess
from pathlib import Path

REPO="beatleswu/beatleswu.github.io"
SCHEMA="G027_REUSABLE_OWNER_SOURCE_APPROVAL_V1"
OID=re.compile(r"^[0-9a-f]{40}$")
PROTECTED={"CODEOWNERS","docs/CODEOWNERS",
 "scripts/release/g112_protected_source_verifier.py",
 "scripts/release/g027_reusable_trusted_source_gate.py",
 "deploy/G112_G027_VNEXT_OWNER_APPROVED_SOURCE_ANCHOR_20261026.json.b64"}

class Reject(Exception):pass
def must(ok,code):
    if not ok:raise Reject(code)
def git(repo,*args):
    try:
        p=subprocess.run(["git","-C",str(repo),*args],capture_output=True,timeout=120)
    except (OSError,subprocess.TimeoutExpired):
        raise Reject("GIT_UNAVAILABLE")
    must(p.returncode==0,"GIT_ERROR")
    return p.stdout.decode("utf-8","strict").strip()
def oid(value):
    return type(value) is str and OID.fullmatch(value) is not None
def utc(raw):
    try:d=datetime.datetime.fromisoformat(raw.replace("Z","+00:00"))
    except (ValueError,TypeError,AttributeError):raise Reject("BAD_OWNER_DATE")
    must(d.tzinfo is not None,"UNZONED_OWNER_DATE")
    return d.astimezone(datetime.timezone.utc)
def approval_from_admin_variable(encoded):
    must(type(encoded) is str and bool(encoded) and len(encoded)<12000,
         "OWNER_APPROVAL_MISSING_OR_TOO_LARGE")
    try:
        raw=base64.b64decode(encoded,validate=True)
        a=json.loads(raw)
    except (binascii.Error,ValueError,UnicodeError,TypeError):
        raise Reject("INVALID_ADMIN_APPROVAL")
    must(type(a) is dict,"INVALID_ADMIN_APPROVAL_TYPE")
    fields={"schema","repository","pr_number","base_sha","base_tree",
            "head_sha","head_tree","product_sha","product_tree",
            "approver","decision_id","issued_at","expires_at","mode"}
    must(set(a)==fields,"ADMIN_APPROVAL_SCHEMA_DRIFT")
    must(a["schema"]==SCHEMA and a["repository"]==REPO,"ADMIN_APPROVAL_WRONG_REPO")
    must(type(a["pr_number"]) is int and a["pr_number"]>0,"ADMIN_APPROVAL_BAD_PR")
    for name in ["base_sha","base_tree","head_sha","head_tree","product_sha","product_tree"]:
        must(oid(a[name]),"ADMIN_APPROVAL_BAD_"+name.upper())
    must(a["mode"]=="exact_two_parent_merge","ADMIN_APPROVAL_WRONG_MODE")
    must(a["approver"]=="beatleswu" and
         type(a["decision_id"]) is str and
         re.fullmatch(r"G027-[A-Za-z0-9_.-]{6,96}",a["decision_id"]) is not None,
         "MISSING_REAL_OWNER_DECISION")
    now=datetime.datetime.now(datetime.timezone.utc)
    issued,expires=utc(a["issued_at"]),utc(a["expires_at"])
    must(issued<=now<expires and expires-issued<=datetime.timedelta(days=14),
         "APPROVAL_NOT_CURRENT")
    return a,hashlib.sha256(raw).hexdigest()
def control_paths(repo,revision):
    paths={}
    for entry in git(repo,"ls-tree","-r","-z","--full-tree",revision).split("\0"):
        if not entry:continue
        try:
            attributes,name=entry.split("\t",1)
            mode,kind,obj=attributes.split(" ")
        except ValueError:raise Reject("BAD_GIT_TREE_FORMAT")
        if name.startswith(".github/") or name.startswith("scripts/release/g027_") or name in PROTECTED:
            must(kind=="blob","NON_BLOB_CONTROL_FILE")
            paths[name]=(mode,obj)
    return paths
def validate(trusted,candidate,event,approval_b64):
    a,approval_sha=approval_from_admin_variable(approval_b64)
    must(event["repo"]==REPO and event["base_ref"]=="master" and
         event["head_repo"]==REPO,"EVENT_REPOSITORY_OR_REF_UNTRUSTED")
    must(str(event["pr_number"])==str(a["pr_number"]),"PR_NOT_OWNER_APPROVED")
    must(event["head_sha"]==a["head_sha"] and event["base_sha"]==a["base_sha"],
         "EVENT_SHA_NOT_OWNER_APPROVED")
    must(oid(event["workflow_sha"]) and
         event["workflow_sha"]==event["base_sha"],"NOT_CURRENT_PROTECTED_WORKFLOW")
    must(event["workflow_ref"]==
         REPO+"/.github/workflows/g027-vnext-trusted-source.yml@refs/heads/master",
         "UNTRUSTED_WORKFLOW_REF")
    must(git(trusted,"rev-parse","HEAD")==event["workflow_sha"],
         "PROTECTED_BASE_CHECKOUT_MISMATCH")
    must(git(candidate,"rev-parse","HEAD")==event["head_sha"],
         "CANDIDATE_CHECKOUT_MISMATCH")
    must(not git(trusted,"status","--porcelain=v1") and
         not git(candidate,"status","--porcelain=v1"),
         "CHECKOUT_NOT_CLEAN")
    must(git(trusted,"rev-parse","HEAD^{tree}")==a["base_tree"],
         "APPROVED_BASE_TREE_MISMATCH")
    for commit,key in ((a["base_sha"],"base_tree"),(a["product_sha"],"product_tree"),
                       (a["head_sha"],"head_tree")):
        must(git(candidate,"rev-parse",commit+"^{tree}")==a[key],
             "APPROVED_"+key.upper()+"_MISMATCH")
    must(git(candidate,"show","-s","--format=%P",a["head_sha"]).split()==
         [a["product_sha"],a["base_sha"]],"HEAD_PARENTS_NOT_APPROVED")
    # Deterministic source-only merge: no hidden manual file injections.
    must(git(candidate,"merge-tree","--write-tree",a["product_sha"],a["base_sha"])==
         a["head_tree"],"UNREVIEWED_MERGE_TREE")
    protected=control_paths(candidate,a["base_sha"])
    must(control_paths(candidate,a["head_sha"])==protected,
         "PR_CHANGED_CONTROL_PLANE")
    must(control_paths(trusted,a["base_sha"])==protected,
         "PROTECTED_CHECKOUT_DISAGREES")
    return {"verdict":"PASS_TRUSTED_OWNER_APPROVED_SOURCE",
            "pr_number":a["pr_number"],"product_sha":a["product_sha"],
            "product_tree":a["product_tree"],"head_sha":a["head_sha"],
            "head_tree":a["head_tree"],"base_sha":a["base_sha"],
            "decision_id":a["decision_id"],"approval_sha256":approval_sha,
            "control_paths":len(protected),"untrusted_code_executed":False}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--trusted",type=Path,required=True)
    p.add_argument("--candidate",type=Path,required=True)
    a=p.parse_args()
    e={k:os.environ.get(v,"") for k,v in {
        "repo":"G027_EVENT_REPO","base_ref":"G027_EVENT_BASE_REF",
        "head_repo":"G027_EVENT_HEAD_REPO","pr_number":"G027_EVENT_PR_NUMBER",
        "head_sha":"G027_EVENT_HEAD_SHA","base_sha":"G027_EVENT_BASE_SHA",
        "workflow_sha":"G027_WORKFLOW_SHA","workflow_ref":"G027_WORKFLOW_REF"}.items()}
    try:
        result=validate(a.trusted,a.candidate,e,os.environ.get("G027_OWNER_APPROVAL_B64",""))
        print(json.dumps(result,sort_keys=True))
    except (Reject,KeyError,TypeError,ValueError) as exc:
        print(json.dumps({"verdict":"REJECTED","code":str(exc) if isinstance(exc,Reject)
                          else "INVALID_INPUT"}))
        raise SystemExit(3)
if __name__=="__main__":main()
