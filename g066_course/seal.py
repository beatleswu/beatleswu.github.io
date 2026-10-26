"""Seal the candidate overlay and evidence; no Git staging or target mutation."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from .build_catalog import BASE_SHA, build

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode().strip()


def seal():
    assert git("rev-parse", "HEAD") == BASE_SHA
    assert git("branch", "--show-current") == "g066-curriculum-v1-20261022"
    # Existing untracked recon receipt is preserved; all tracked files stay d0.
    assert not git("diff", "--name-only", "HEAD")
    protected = {}
    for name in ("app.py", "curriculum.html", "quest_runtime_config.py"):
        assert (ROOT/name).read_bytes() == subprocess.check_output(["git", "show", f"{BASE_SHA}:{name}"], cwd=ROOT)
        protected[name] = sha(ROOT/name)
    catalog, media = build(Path(r"D:\go-website\course_syllabus_20261022"), Path(r"D:\go-website\course_video_sample_20261022"))
    assert catalog == json.loads((ROOT/"g066_course/data/catalog.json").read_text(encoding="utf-8"))
    assert media == json.loads((ROOT/"g066_course/data/media-manifest.json").read_text(encoding="utf-8"))
    for name in ("G066_D_ROUTE_PROPOSAL.patch", "G066_CURRICULUM_PROPOSAL.patch"):
        subprocess.run(["git", "apply", "--check", f"docs/handoffs/{name}"], cwd=ROOT, check=True)
    for name in ("course.js", "curriculum-embed.js"):
        subprocess.run(["node", "--check", f"g066_course/ui/{name}"], cwd=ROOT, check=True)
    paths = sorted(p for p in (ROOT/"g066_course").rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    paths += [ROOT/p for p in ("tests/test_g066_course_v1.py", "tests/e2e/g066_course_v1_fixture.mjs",
        "docs/handoffs/G066_INTERFACE_CONTRACT.md", "docs/handoffs/G066_D_ROUTE_PROPOSAL.patch",
        "docs/handoffs/G066_CURRICULUM_PROPOSAL.patch")]
    manifest = {str(p.relative_to(ROOT)).replace("\\", "/"):sha(p) for p in sorted(paths)}
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    primary = [q["legacy_question_id"] for l in catalog["lessons"] for role in ("demo","practice","quiz","graduation") for q in l["questions"][role]]
    practices = [q["legacy_question_id"] for l in catalog["lessons"] for q in l["questions"]["practice"]]
    evidence = {str(p.relative_to(ROOT)).replace("\\", "/"):sha(p) for p in sorted((ROOT/"artifacts/g066").rglob("*"))
                if p.is_file() and p.suffix in {".xml", ".json", ".png"} and not any(x.startswith("pytest-temp") for x in p.parts)}
    test_history = {}
    for p in sorted((ROOT/"artifacts/g066").glob("pytest-*.xml")):
        suite = ET.parse(p).getroot().find("testsuite")
        test_history[p.name] = {key:int(suite.attrib.get(key,0)) for key in ("tests","failures","errors","skipped")}
    receipt = {"schema":"G066_CANDIDATE_SEAL_V1", "utc":datetime.now(timezone.utc).isoformat(),
        "worktree":str(ROOT), "branch":git("branch","--show-current"),"head":BASE_SHA,
        "head_tree":git("rev-parse","HEAD^{tree}"),"candidate_commit":"NOT_CREATED",
        "candidate_code_sha256":hashlib.sha256(encoded).hexdigest(),"candidate_files":manifest,
        "protected_exact_d0_sha256":protected,"source_rebuild":"PASS","patch_dry_run":"PASS",
        "js_syntax":"PASS","primary_assignments":len(primary),"primary_unique_aliases":len(set(primary)),
        "practice_assignments":len(practices),"practice_unique_aliases":len(set(practices)),
        "practice_duplicate_aliases":{str(k):v for k,v in Counter(practices).items() if v>1},
        "pytest_history":test_history,"browser_final":json.loads((ROOT/"artifacts/g066/browser-results.json").read_text()),
        "evidence_sha256":evidence,"runtime_enabled":False,"rules_enabled":False,
        "production_db":"NOT_ACCESSED","merge":"NOT_EXECUTED","push":"NOT_EXECUTED","deploy":"NOT_EXECUTED"}
    (ROOT/"docs/handoffs/G066_CANDIDATE_SEAL.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:receipt[k] for k in ("head","head_tree","candidate_commit","candidate_code_sha256","source_rebuild","patch_dry_run","js_syntax")},indent=2))


if __name__=="__main__":seal()
