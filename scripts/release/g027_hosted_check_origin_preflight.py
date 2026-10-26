"""G027 procedural pre-GO_MERGE GitHub check-origin verification.

GitHub Ruleset check name + App ID does NOT bind a workflow. This independent
read-only GitHub REST probe maps each Check Run ID to the exact Workflow Run
and Job, requiring protected workflow identity, event, PR/base/head, and
current administrative Owner approval. It is a supplemental Owner Gate,
NOT a new GitHub-native Required Check or a guarantee of non-bypassability.
"""
from __future__ import annotations
import argparse,datetime,hashlib,json,subprocess,sys
from pathlib import Path
from g027_reusable_trusted_source_gate import approval_from_admin_variable,Reject

REPO="beatleswu/beatleswu.github.io"
NAME="g027-vnext-trusted-source"
WF_ID=396547662
WF_PATH=".github/workflows/g027-vnext-trusted-source.yml"
APP_ID=15368
VAR="G027_OWNER_APPROVED_RELEASE_V1_B64"
def iso(s):
    if not isinstance(s,str):return None
    try:
        d=datetime.datetime.fromisoformat(s.replace("Z","+00:00"))
        if d.tzinfo is not None:return d.astimezone(datetime.timezone.utc)
    except ValueError:pass
    return None
def compare(snapshot,now=None):
    now=now or datetime.datetime.now(datetime.timezone.utc)
    pr=snapshot["pr"]; master=snapshot["master"]
    checks=snapshot["checks"]; runs=snapshot["runs"]
    errors=[]
    head=pr["head"]; base=pr["base"]; number=pr["number"]
    if pr.get("draft"):errors.append("PR_IS_DRAFT")
    if pr.get("state")!="open":errors.append("PR_NOT_OPEN")
    if master!=base:errors.append("BASE_NOT_LATEST_MASTER")
    eligible=[c for c in checks if c.get("name")==NAME]
    if len(eligible)!=1:errors.append("DUPLICATE_OR_MISSING_SAME_NAME_CHECK")
    trusted=[]
    for run in runs:
        matching=[j for j in run.get("jobs",[]) if j.get("name")==NAME]
        if matching:trusted.append({"run":run,"jobs":matching})
    if len(trusted)!=1:errors.append("DUPLICATE_OR_MISSING_NAME_SOURCE_RUN")
    if len(eligible)==1 and len(trusted)==1:
        c=eligible[0];run=trusted[0]["run"]; jobs=trusted[0]["jobs"]
        if len(jobs)!=1:errors.append("MULTIPLE_JOBS_WITH_NAME")
        else:
            j=jobs[0]
            if c.get("id")!=j.get("id"):errors.append("JOB_CHECK_RUN_ID_MISMATCH")
            if c.get("head_sha")!=head:errors.append("CHECK_HEAD_MISMATCH")
            if (c.get("app") or {}).get("id")!=APP_ID:errors.append("CHECK_APP_UNTRUSTED")
            if (c.get("status")!="completed" or c.get("conclusion")!="success"
                or j.get("status")!="completed" or j.get("conclusion")!="success"):
                errors.append("REQUIRED_TRUSTED_JOB_NOT_SUCCESS")
            if (run.get("workflow_id")!=WF_ID or run.get("path")!=WF_PATH
                or run.get("event")!="pull_request_target"):
                errors.append("WORKFLOW_PROVENANCE_UNTRUSTED")
            if run.get("head_sha")!=head:errors.append("RUN_HEAD_MISMATCH")
            if run.get("conclusion")!="success" or run.get("status")!="completed":
                errors.append("TRUSTED_WORKFLOW_RUN_NOT_SUCCESS")
            # A check result not from this exact Job ID and trusted Workflow ID is NO proof.
            if c.get("details_url") and "/actions/runs/"+str(run.get("run_id"))+"/job/"+str(j.get("id")) not in c["details_url"]:
                errors.append("CHECK_DETAILS_SOURCE_MISMATCH")
    var=snapshot.get("variable")
    approved=None
    if var is None:errors.append("OWNER_ACTIONS_APPROVAL_MISSING")
    else:
        try:
            approved,approval_sha=approval_from_admin_variable(var.get("value"))
        except (Reject,KeyError,ValueError):
            errors.append("OWNER_ACTIONS_APPROVAL_INVALID")
        if approved is not None:
            if approved["pr_number"]!=number:errors.append("OWNER_PR_MISMATCH")
            if approved["head_sha"]!=head or approved["base_sha"]!=base:
                errors.append("OWNER_SOURCE_SHA_STALE")
            if approved["mode"] not in ("exact_two_parent_merge",
                                       "reviewed_product_merge_chain"):
                errors.append("OWNER_INTEGRATION_MODE_CHANGED")
            var_updated=iso(var.get("updated_at"))
            issued=iso(approved["issued_at"]); expiry=iso(approved["expires_at"])
            if var_updated is None:errors.append("ADMIN_VARIABLE_AUDIT_TIMESTAMP_MISSING")
            if (not issued or not expiry or not issued<=now<expiry):
                errors.append("APPROVAL_EXPIRED_OR_NOT_YET_VALID")
            if len(trusted)==1 and len(trusted[0]["jobs"])==1:
                run=trusted[0]["run"];j=trusted[0]["jobs"][0]
                start=iso(j.get("started_at"));run_created=iso(run.get("created_at"))
                if not start or not run_created:errors.append("RUN_PROVENANCE_TIMESTAMPS_MISSING")
                if var_updated and start and run_created:
                    if run_created<var_updated or start<var_updated:
                        errors.append("HOSTED_PASS_PRECEDES_LATEST_OWNER_VARIABLE")
                    if issued and (run_created<issued or start<issued):
                        errors.append("HOSTED_PASS_PRECEDES_OWNER_DECISION")
                    if expiry and start>=expiry:errors.append("HOSTED_PASS_AFTER_EXPIRY")
    # Check SHA/tree of master, Product and two-parent PR integration only from
    # actual GitHub git-data or dedicated known-good local source preflight.
    if snapshot.get("trees_verified") is not True:
        errors.append("APPROVED_GIT_TREES_NOT_INDEPENDENTLY_VERIFIED")
    return {
        "verdict":"GO_MERGE_SOURCE_PREFLIGHT_PASS" if not errors else "HOLD",
        "errors":sorted(set(errors)),"pr_number":number,
        "head_sha":head,"base_sha":base,"master_sha":master,
        "matching_checks":len(eligible),"same_named_workflow_runs":len(trusted),
        "expected_workflow_id":WF_ID,"expected_workflow_path":WF_PATH,
        "owner_approval_sha256":approval_sha if approved is not None else None,
        "not_a_native_ruleset_provenance_guarantee":True}
def gh(endpoint,missing_ok=False):
    p=subprocess.run(["gh","api","repos/"+REPO+"/"+endpoint],capture_output=True,
       encoding="utf8",errors="replace",text=True,timeout=60)
    if p.returncode:
        if missing_ok and ("404" in p.stderr or "Not Found" in p.stderr):return None
        raise RuntimeError("GITHUB_API_NOT_READABLE "+endpoint)
    return json.loads(p.stdout)
def gather(pr_number):
    pr=gh("pulls/"+str(pr_number))
    head=pr["head"]["sha"]
    sha=gh("git/ref/heads/master")["object"]["sha"]
    checks=gh("commits/"+head+"/check-runs?per_page=100")["check_runs"]
    allruns=gh("actions/runs?head_sha="+head+"&per_page=100")["workflow_runs"]
    runs=[]
    for r in allruns:
        if r.get("head_sha")!=head:continue
        jobs=gh("actions/runs/"+str(r["id"])+"/jobs?per_page=100")["jobs"]
        runs.append({
          "run_id":r["id"],"workflow_id":r.get("workflow_id"),
          "path":r.get("path"),"event":r.get("event"),
          "head_sha":r.get("head_sha"),"status":r.get("status"),
          "conclusion":r.get("conclusion"),"created_at":r.get("created_at"),
          "jobs":[{"id":x["id"],"name":x.get("name"),
            "status":x.get("status"),"conclusion":x.get("conclusion"),
            "started_at":x.get("started_at")} for x in jobs]})
    variable=gh("actions/variables/"+VAR,missing_ok=True)
    tree_verified=False
    if variable is not None:
        try:
            approved,_digest=approval_from_admin_variable(variable.get("value"))
            desired={"base_sha":"base_tree","product_sha":"product_tree",
                     "head_sha":"head_tree"}
            commits={label:gh("git/commits/"+approved[label])
                     for label in desired}
            parents=[x["sha"] for x in commits["head_sha"]["parents"]]
            if approved["mode"]=="exact_two_parent_merge":
                correct_history=parents==[approved["product_sha"],approved["base_sha"]]
            else:
                correct_history=(len(parents)==2 and parents[1]==approved["base_sha"])
                current=parents[0] if correct_history else ""
                for depth in range(12):
                    if current==approved["product_sha"]:break
                    older=gh("git/commits/"+current)
                    ps=[p["sha"] for p in older["parents"]]
                    if len(ps)!=2:
                        correct_history=False;break
                    cmp=gh("compare/"+ps[1]+"..."+approved["base_sha"])
                    if cmp.get("status") not in ("ahead","identical"):
                        correct_history=False;break
                    current=ps[0]
                else:correct_history=False
                correct_history=correct_history and current==approved["product_sha"]
            tree_verified=(
                all(commits[label]["tree"]["sha"]==approved[tree_key]
                    for label,tree_key in desired.items())
                and correct_history
                and approved["head_sha"]==head and approved["base_sha"]==sha)
        except (Reject,KeyError,ValueError):
            tree_verified=False
    return {"pr":{"number":pr_number,"head":head,"base":pr["base"]["sha"],
                  "draft":pr["draft"],"state":pr["state"]},
            "master":sha,"checks":[{"id":c["id"],"name":c["name"],
              "head_sha":c.get("head_sha"),"app":{"id":(c.get("app") or {}).get("id")},
              "status":c.get("status"),"conclusion":c.get("conclusion"),
              "details_url":c.get("details_url")} for c in checks],
            "runs":runs,"variable":variable,"trees_verified":tree_verified}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--pr",type=int,required=True)
    p.add_argument("--receipt",type=Path,required=True)
    a=p.parse_args()
    data=gather(a.pr)
    result=compare(data)
    out={"schema":"G027_OWNER_PREMERGE_WORKFLOW_ORIGIN_PREFLIGHT_V1",
         "observed_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
         "result":result,
         "observed_check_ids":[c["id"] for c in data["checks"] if c["name"]==NAME],
         "observed_run_ids":[r["run_id"] for r in data["runs"]],
         "owner_variable_metadata":None if data["variable"] is None else {
            "name":data["variable"].get("name"),
            "created_at":data["variable"].get("created_at"),
            "updated_at":data["variable"].get("updated_at")}}
    a.receipt.write_text(json.dumps(out,indent=2)+"\n",encoding="utf8")
    print(json.dumps(result,ensure_ascii=True))
    print("RECEIPT_SHA256",hashlib.sha256(a.receipt.read_bytes()).hexdigest())
    if result["verdict"]!="GO_MERGE_SOURCE_PREFLIGHT_PASS":raise SystemExit(3)
if __name__=="__main__":main()
