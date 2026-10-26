"""Positive/negative G027 reusable source-admission tests on disposable Git repos.

No mocked trust gate, and never uses protected G114 worktree or GitHub state.
"""
import base64,copy,datetime,importlib.util,json,subprocess
from pathlib import Path
import pytest

P=Path(__file__).resolve().parents[1]/"scripts/release/g027_reusable_trusted_source_gate.py"
spec=importlib.util.spec_from_file_location("g027_reusable_trusted_source_gate",P)
gate=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

def git(where,*args,input=None):
    p=subprocess.run(["git","-C",str(where),*args],input=input,text=True,
                     capture_output=True,timeout=45)
    assert p.returncode==0,(args,p.stdout[-400:],p.stderr[-500:])
    return p.stdout.strip()
def write(root,name,data):
    f=root/name
    f.parent.mkdir(parents=True,exist_ok=True)
    f.write_text(data,encoding="utf8")
def approval_encode(a):
    return base64.b64encode(json.dumps(a,sort_keys=True).encode()).decode()
@pytest.fixture
def provenance(tmp_path):
    repo=tmp_path/"objects"
    repo.mkdir()
    git(repo,"init","-q","-b","master")
    git(repo,"config","user.email","g027-test@invalid.example")
    git(repo,"config","user.name","G027 disposable test")
    write(repo,"README.md","shared base\n")
    git(repo,"add",".")
    git(repo,"commit","-qm","genesis")
    genesis=git(repo,"rev-parse","HEAD")
    git(repo,"checkout","-qb","product")
    write(repo,"app.py","G114 accepted immutable candidate\n")
    git(repo,"add","app.py")
    git(repo,"commit","-qm","reviewed product")
    product=git(repo,"rev-parse","HEAD")
    git(repo,"checkout","master")
    write(repo,".github/workflows/g027-vnext-trusted-source.yml","protected workflow v1\n")
    write(repo,"scripts/release/g027_reusable_trusted_source_gate.py","trusted base code\n")
    git(repo,"add",".")
    git(repo,"commit","-qm","protected governance")
    base=git(repo,"rev-parse","HEAD")
    tree=git(repo,"merge-tree","--write-tree",product,base)
    head=git(repo,"commit-tree",tree,"-p",product,"-p",base,
             input="approved product + protected base\n")
    trusted=tmp_path/"trusted"
    candidate=tmp_path/"candidate"
    git(repo,"worktree","add","--detach",str(trusted),base)
    git(repo,"worktree","add","--detach",str(candidate),head)
    now=datetime.datetime.now(datetime.timezone.utc)
    fmt=lambda d:d.isoformat().replace("+00:00","Z")
    a={"schema":gate.SCHEMA,"repository":gate.REPO,
       "pr_number":448,"base_sha":base,
       "base_tree":git(repo,"rev-parse",base+"^{tree}"),
       "product_sha":product,"product_tree":git(repo,"rev-parse",product+"^{tree}"),
       "head_sha":head,"head_tree":tree,
       "approver":"beatleswu","decision_id":"G027-TEST-DISPOSABLE-448",
       "issued_at":fmt(now-datetime.timedelta(minutes=1)),
       "expires_at":fmt(now+datetime.timedelta(hours=2)),
       "mode":"exact_two_parent_merge"}
    e={"repo":gate.REPO,"base_ref":"master","head_repo":gate.REPO,
       "pr_number":"448","head_sha":head,"base_sha":base,
       "workflow_sha":base,"workflow_ref":gate.REPO+
       "/.github/workflows/g027-vnext-trusted-source.yml@refs/heads/master"}
    return repo,trusted,candidate,a,e
def call(state,a=None,e=None,b64=None):
    repo,trusted,candidate,approved,event=state
    return gate.validate(trusted,candidate,e or event,
                         b64 if b64 is not None else approval_encode(a or approved))
def fails(state,code,a=None,e=None,b64=None):
    with pytest.raises(gate.Reject,match=code):
        call(state,a,e,b64)
def test_approved_exact_source_succeeds(provenance):
    result=call(provenance)
    assert result["verdict"]=="PASS_TRUSTED_OWNER_APPROVED_SOURCE"
    assert result["untrusted_code_executed"] is False
    assert result["product_sha"]==provenance[3]["product_sha"]
def test_missing_separate_admin_variable_is_fail_closed(provenance):
    fails(provenance,"OWNER_APPROVAL_MISSING",b64="")
def test_untrusted_pr_file_cannot_supply_admin_approval(provenance):
    # Candidate never provides the administrative variable; a PR-side
    # forged approve.json is therefore not an authorization source.
    write(provenance[2],"owner_approval.json",json.dumps(provenance[3]))
    fails(provenance,"OWNER_APPROVAL_MISSING",b64="")
def test_bad_or_expired_admin_approval_rejected(provenance):
    fails(provenance,"INVALID_ADMIN_APPROVAL",b64="%%%")
    a=copy.deepcopy(provenance[3]);a["expires_at"]="2020-01-01T00:00:00Z"
    fails(provenance,"APPROVAL_NOT_CURRENT",a=a)
def test_pr_number_or_head_sha_forged(provenance):
    a=copy.deepcopy(provenance[3]);a["pr_number"]=445
    fails(provenance,"PR_NOT_OWNER_APPROVED",a=a)
    e=copy.deepcopy(provenance[4]);e["head_sha"]="a"*40
    fails(provenance,"EVENT_SHA_NOT_OWNER_APPROVED",e=e)
def test_product_tree_forged(provenance):
    a=copy.deepcopy(provenance[3]);a["product_tree"]="0"*40
    fails(provenance,"APPROVED_PRODUCT_TREE_MISMATCH",a=a)
def test_untrusted_workflow_reference_or_base_changed(provenance):
    e=copy.deepcopy(provenance[4]);e["workflow_ref"]+="@untrusted"
    fails(provenance,"UNTRUSTED_WORKFLOW_REF",e=e)
    e=copy.deepcopy(provenance[4]);e["workflow_sha"]="f"*40
    fails(provenance,"NOT_CURRENT_PROTECTED_WORKFLOW",e=e)
def test_pr_cannot_add_injected_code_even_if_approval_packet_changed(provenance):
    repo,trusted,candidate,a,e=provenance
    write(candidate,"app.py","approved code plus malicious injection\n")
    git(candidate,"add","app.py")
    bad_tree=git(candidate,"write-tree")
    bad_head=git(candidate,"commit-tree",bad_tree,
                 "-p",a["product_sha"],"-p",a["base_sha"],
                 input="injected file never approved as Product\n")
    git(candidate,"reset","--hard",bad_head)
    a=copy.deepcopy(a);e=copy.deepcopy(e)
    a["head_sha"]=e["head_sha"]=bad_head
    a["head_tree"]=bad_tree
    fails(provenance,"UNREVIEWED_MERGE_TREE",a=a,e=e)
def test_pr_cannot_replace_protected_workflow_even_with_forged_owner_packet(provenance):
    repo,trusted,candidate,a,e=provenance
    git(repo,"checkout","-qb","evil-product",a["base_sha"])
    write(repo,".github/workflows/g027-vnext-trusted-source.yml",
          "untrusted candidate-self-approval\n")
    git(repo,"add",".github/workflows/g027-vnext-trusted-source.yml")
    git(repo,"commit","-qm","fake product edits trusted workflow")
    evil_prod=git(repo,"rev-parse","HEAD")
    evil_tree=git(repo,"merge-tree","--write-tree",evil_prod,a["base_sha"])
    evil_head=git(repo,"commit-tree",evil_tree,
                  "-p",evil_prod,"-p",a["base_sha"],input="evil-head\n")
    git(candidate,"reset","--hard",evil_head)
    a=copy.deepcopy(a);e=copy.deepcopy(e)
    a["product_sha"]=evil_prod
    a["product_tree"]=git(repo,"rev-parse",evil_prod+"^{tree}")
    a["head_sha"]=e["head_sha"]=evil_head
    a["head_tree"]=evil_tree
    fails(provenance,"PR_CHANGED_CONTROL_PLANE",a=a,e=e)
def test_fork_pr_or_wrong_approver_denied(provenance):
    e=copy.deepcopy(provenance[4]);e["head_repo"]="evil/clone"
    fails(provenance,"EVENT_REPOSITORY_OR_REF_UNTRUSTED",e=e)
    a=copy.deepcopy(provenance[3]);a["approver"]="attacker"
    fails(provenance,"MISSING_REAL_OWNER_DECISION",a=a)
def test_unapproved_parent_reordering_denied(provenance):
    repo,trusted,candidate,a,e=provenance
    head=git(repo,"commit-tree",a["head_tree"],
             "-p",a["base_sha"],"-p",a["product_sha"],input="inverted parents\n")
    git(candidate,"reset","--hard",head)
    a=copy.deepcopy(a);e=copy.deepcopy(e)
    a["head_sha"]=e["head_sha"]=head
    fails(provenance,"HEAD_PARENTS_NOT_APPROVED",a=a,e=e)
