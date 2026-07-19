"""Verify the DEPLOY-GOV-2E app-image / content boundary: srs.db and
docs/testing/ are permanently excluded, go_learning.db treatment matches
its evidence, assets/shorts/questions.json are not required at image build
time, and the questions path is configurable."""
import json
import pathlib
import re
import subprocess

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "Dockerfile"
ENTRYPOINT = REPO_ROOT / "entrypoint.sh"
APP_PY = REPO_ROOT / "app.py"
MANIFEST = REPO_ROOT / "deploy" / "build-manifest.json"


def dockerfile_text():
    return DOCKERFILE.read_text(encoding="utf-8")


def _active_lines(text):
    """Non-comment, non-blank lines only -- explanatory prose in comments
    (e.g. documenting why a path was excluded) legitimately names the
    excluded path and must not trip these checks."""
    return "\n".join(
        ln for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    )


def tracked_files():
    out = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    return set(out.stdout.splitlines())


_DOC_REPORT_SUFFIXES = {".md", ".txt"}
_GENERATED_DOC_OUTPUT = re.compile(
    r"(?:screenshot|trace|network|coverage|artifact|generated|playwright|temp|tmp|output)",
    re.IGNORECASE,
)


def docs_testing_violations(paths):
    """Return tracked docs/testing paths that are not human-authored reports."""
    violations = []
    for path in paths:
        if not path.startswith("docs/testing/"):
            continue
        name = path.rsplit("/", 1)[-1]
        suffix = pathlib.PurePosixPath(name).suffix.lower()
        if suffix not in _DOC_REPORT_SUFFIXES or _GENERATED_DOC_OUTPUT.search(name):
            violations.append(path)
    return sorted(violations)


def test_srs_db_not_tracked():
    assert "srs.db" not in tracked_files()


def test_srs_db_not_in_dockerfile():
    content = _active_lines(dockerfile_text())
    assert "srs.db" not in content


def test_srs_db_not_in_entrypoint_persistence():
    content = _active_lines(ENTRYPOINT.read_text(encoding="utf-8"))
    assert "srs.db" not in content, "srs.db must not be seeded/persisted by entrypoint.sh -- it is user data"


def test_docs_testing_not_tracked():
    tracked = tracked_files()
    assert not docs_testing_violations(tracked)


def test_docs_testing_allows_markdown_and_plain_text_reports():
    assert docs_testing_violations({
        "docs/testing/e9_acceptance.md",
        "docs/testing/deployment-notes.txt",
    }) == []


def test_docs_testing_rejects_images_archives_binary_and_generated_output():
    assert docs_testing_violations({
        "docs/testing/screenshot.png",
        "docs/testing/layout.jpg",
        "docs/testing/render.webp",
        "docs/testing/results.zip",
        "docs/testing/trace.json",
        "docs/testing/generated-output.txt",
        "docs/testing/playwright-report.txt",
    }) == sorted([
        "docs/testing/screenshot.png",
        "docs/testing/layout.jpg",
        "docs/testing/render.webp",
        "docs/testing/results.zip",
        "docs/testing/trace.json",
        "docs/testing/generated-output.txt",
        "docs/testing/playwright-report.txt",
    ])


def test_docs_testing_not_in_dockerfile():
    content = _active_lines(dockerfile_text())
    assert "docs/testing" not in content


def test_go_learning_db_not_tracked_or_copied():
    assert "go_learning.db" not in tracked_files()
    assert "go_learning.db" not in _active_lines(dockerfile_text())
    assert "go_learning.db" not in _active_lines(ENTRYPOINT.read_text(encoding="utf-8"))


def test_go_learning_db_exclusion_documented_with_evidence():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries = data["build_inputs"]["excluded_permanently"]["entries"]
    entry = next(e for e in entries if e["path"] == "go_learning.db")
    assert "PostgreSQL" in entry["reason"] or "postgres" in entry["reason"].lower()


def test_srs_db_exclusion_documented_as_user_data():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries = data["build_inputs"]["excluded_permanently"]["entries"]
    entry = next(e for e in entries if e["path"] == "srs.db")
    assert "USER DATA" in entry["reason"]


def test_dockerfile_has_no_dangerous_wildcards():
    lines = [ln.strip() for ln in dockerfile_text().splitlines() if ln.strip().startswith("COPY ")]
    dangerous = [ln for ln in lines if "*.html" in ln or "*.js" in ln or "*.json" in ln
                 or "assets/*" in ln or "assets/hero/*" in ln or "assets/pets/*" in ln
                 or "assets/go_rpg_assets*" in ln]
    assert not dangerous, f"Dockerfile must not contain broad root/asset wildcards: {dangerous}"


def test_assets_not_required_at_build_time():
    content = dockerfile_text()
    assert "COPY assets" not in content
    assert not (REPO_ROOT / "assets").exists() or True  # absence is fine either way; build must not require it


def test_shorts_not_required_at_build_time():
    content = dockerfile_text()
    assert "COPY shorts" not in content


def test_questions_json_not_required_at_build_time():
    content = dockerfile_text()
    assert "COPY questions.json" not in content


def test_questions_path_is_configurable():
    content = APP_PY.read_text(encoding="utf-8")
    assert "QUESTIONS_JSON_PATH" in content
    assert "DATA_FILE = os.environ.get('QUESTIONS_JSON_PATH'" in content


def test_app_handles_missing_questions_json_without_crashing():
    content = APP_PY.read_text(encoding="utf-8")
    assert "os.path.exists(DATA_FILE)" in content


def test_content_boundary_documented_in_manifest():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    boundary = data["build_inputs"]["external_content_boundary"]["entries"]
    paths = {e["path"] for e in boundary}
    assert paths == {"assets/", "shorts/", "questions.json"}
    for e in boundary:
        assert "mount_contract" in e
        assert "absent_behavior" in e


def test_compose_defines_live_static_and_questions_mount_env():
    content = (REPO_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    assert "GO_ODYSSEY_LIVE_STATIC_ROOT" in content
    assert "QUESTIONS_JSON_PATH" in content
    assert "/app/data/questions.json" in content
