"""Create exact d0 integration proposals without touching their target files."""
import difflib
from pathlib import Path
import subprocess

from .build_catalog import BASE_SHA


def make():
    output=Path("docs/handoffs")
    app=subprocess.check_output(["git","show",f"{BASE_SHA}:app.py"]).decode("utf-8")
    curriculum=subprocess.check_output(["git","show",f"{BASE_SHA}:curriculum.html"]).decode("utf-8")
    anchor="@app.route('/curriculum')\n"
    addition=("# G066 proposal: default OFF; adapters/Owner gate must be provided by G/D.\n"
              "from g066_course.integration import install_course_v1\n"
              "install_course_v1(app)\n\n")
    assert app.count(anchor)==1
    modified=app.replace(anchor,addition+anchor)
    bootstrap=('<!-- G066 proposal: read-only probe; no DOM changes while course is OFF. -->\n'
        '<script>\n'
        "fetch('/api/course-v1/summary', {credentials:'same-origin',cache:'no-store'})\n"
        ".then(r => { if (!r.ok) return; const s=document.createElement('script');\n"
        "s.src='/course-v1/curriculum-embed.js'; document.body.appendChild(s); })\n"
        '.catch(() => {});\n</script>\n')
    assert curriculum.count('</body>')==1
    for name,target,old,new in (
        ("G066_D_ROUTE_PROPOSAL.patch","app.py",app,modified),
        ("G066_CURRICULUM_PROPOSAL.patch","curriculum.html",curriculum,curriculum.replace('</body>',bootstrap+'</body>'))):
        patch=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+target,tofile='b/'+target))
        (output/name).write_text(patch,encoding='utf-8',newline='\n')


if __name__=='__main__':make()
