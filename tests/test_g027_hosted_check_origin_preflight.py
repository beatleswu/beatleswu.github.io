"""C1/C2 source provenance: synthetic pass, forged hosted check and replay MUST HOLD."""
import sys,datetime,json,base64,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/release"))
import g027_hosted_check_origin_preflight as c
import g027_reusable_trusted_source_gate as g

def stamp(dt):return dt.isoformat().replace("+00:00","Z")
def sample():
    now=datetime.datetime.now(datetime.timezone.utc)
    issued=now-datetime.timedelta(minutes=12)
    updated=now-datetime.timedelta(minutes=10)
    started=now-datetime.timedelta(minutes=5)
    approved={
       "schema":g.SCHEMA,"repository":g.REPO,"pr_number":448,
       "base_sha":"a"*40,"base_tree":"b"*40,"product_sha":"c"*40,
       "product_tree":"d"*40,"head_sha":"e"*40,"head_tree":"f"*40,
       "approver":"beatleswu","decision_id":"G027-SYNTHETIC-REVIEW-448",
       "issued_at":stamp(issued),"expires_at":stamp(now+datetime.timedelta(hours=2)),
       "mode":"exact_two_parent_merge"}
    check={"id":101,"name":c.NAME,"head_sha":"e"*40,
           "app":{"id":c.APP_ID},"status":"completed","conclusion":"success",
           "details_url":"https://github.com/beatleswu/beatleswu.github.io/actions/runs/505/job/101"}
    job={"id":101,"name":c.NAME,"status":"completed","conclusion":"success",
         "started_at":stamp(started)}
    run={"run_id":505,"workflow_id":c.WF_ID,"path":c.WF_PATH,
         "event":"pull_request_target","head_sha":"e"*40,
         "status":"completed","conclusion":"success",
         "created_at":stamp(started),"jobs":[job]}
    variable={"value":base64.b64encode(json.dumps(approved).encode()).decode(),
              "updated_at":stamp(updated)}
    return {"pr":{"number":448,"head":"e"*40,"base":"a"*40,"draft":False,"state":"open"},
       "master":"a"*40,"checks":[check],"runs":[run],
       "variable":variable,"trees_verified":True},now
def failure(data,expected):
    result=c.compare(*data)
    assert result["verdict"]=="HOLD"
    assert expected in result["errors"],result
def test_one_trusted_job_current_owner_variable_passes():
    state=sample()
    assert c.compare(*state)["verdict"]=="GO_MERGE_SOURCE_PREFLIGHT_PASS"
def test_same_named_success_from_another_workflow_is_not_accepted():
    s,now=sample()
    fake=copy.deepcopy(s["checks"][0]);fake["id"]=102
    s["checks"].append(fake)
    run=copy.deepcopy(s["runs"][0]);run["run_id"]=506
    run["workflow_id"]=397286037
    run["path"]=".github/workflows/fake.yml"
    run["event"]="push"
    run["jobs"][0]["id"]=102
    s["runs"].append(run)
    failure((s,now),"DUPLICATE_OR_MISSING_SAME_NAME_CHECK")
    failure((s,now),"DUPLICATE_OR_MISSING_NAME_SOURCE_RUN")
def test_forged_only_same_named_check_fails_workflow_identity():
    s,now=sample();s["runs"][0]["workflow_id"]=397286037
    failure((s,now),"WORKFLOW_PROVENANCE_UNTRUSTED")
def test_check_run_id_must_map_to_original_trusted_job():
    s,now=sample();s["checks"][0]["id"]=102
    failure((s,now),"JOB_CHECK_RUN_ID_MISMATCH")
def test_owner_variable_missing_or_changed_after_success_fails():
    s,now=sample();s["variable"]=None
    failure((s,now),"OWNER_ACTIONS_APPROVAL_MISSING")
    s,now=sample();s["variable"]["updated_at"]=stamp(now)
    failure((s,now),"HOSTED_PASS_PRECEDES_LATEST_OWNER_VARIABLE")
def test_stale_base_or_expired_owner_approval_fails():
    s,now=sample();s["master"]="0"*40
    failure((s,now),"BASE_NOT_LATEST_MASTER")
    s,now=sample();s["variable"]["value"]=base64.b64encode(
      json.dumps({**json.loads(base64.b64decode(s["variable"]["value"])),
                  "expires_at":stamp(now-datetime.timedelta(seconds=1))}).encode()).decode()
    failure((s,now),"OWNER_ACTIONS_APPROVAL_INVALID")
def test_draft_and_tree_unverified_cannot_merge():
    s,now=sample();s["pr"]["draft"]=True
    failure((s,now),"PR_IS_DRAFT")
    s,now=sample();s["trees_verified"]=False
    failure((s,now),"APPROVED_GIT_TREES_NOT_INDEPENDENTLY_VERIFIED")
def test_old_success_before_real_decision_cannot_replay():
    s,now=sample()
    owner=json.loads(base64.b64decode(s["variable"]["value"]))
    owner["issued_at"]=stamp(now-datetime.timedelta(minutes=2))
    s["variable"]["value"]=base64.b64encode(json.dumps(owner).encode()).decode()
    s["variable"]["updated_at"]=stamp(now-datetime.timedelta(minutes=2))
    failure((s,now),"HOSTED_PASS_PRECEDES_OWNER_DECISION")
