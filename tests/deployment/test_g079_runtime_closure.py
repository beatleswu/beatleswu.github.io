"""G079 Product ARM64 image closure. Tests only exact explicit packaging."""
from pathlib import Path
import ast
import re
import pytest

ROOT=Path(__file__).resolve().parents[2]
DOCKER=(ROOT/"Dockerfile").read_text(encoding="utf-8")
FILES=("g079_mistakes_services.py","g078_rating_integration.py",
       "migrations/g079_mistakes_steps_v1.py")

@pytest.mark.parametrize("rel",FILES)
def test_curated_image_includes_admitted_runtime(rel):
    assert (ROOT/rel).is_file()
    assert DOCKER.count(f"COPY {rel} ./") == 1
    ast.parse((ROOT/rel).read_text(encoding="utf-8-sig"),filename=rel)

def test_g079_mode_flags_stay_off_by_default():
    assert not re.search(r"(?mi)^\s*ENV\s+(?:G076_(?:MISTAKES|RATING|GRIMOIRE)_STEPS_ENABLED|G076_ANSWER_PRIVACY_ENFORCED)\s*=",DOCKER)
    assert "COPY . ." not in DOCKER

def test_no_test_credentials_or_browser_artifacts_in_context():
    ignore=(ROOT/".dockerignore").read_text(encoding="utf-8")
    for item in ("artifacts/","**/artifacts/",".g076-*",".g077-*"):
        assert item in ignore
    assert "COPY tests/" not in DOCKER

def test_app_wires_exactly_one_canonical_port_for_each_mode():
    app=(ROOT/"app.py").read_text(encoding="utf-8-sig")
    assert app.count("from g079_mistakes_services import build_mistakes_services") == 1
    assert app.count("from g078_rating_integration import install") == 1
    assert "services=_g079_mistakes_services(globals(), secret=app.secret_key)))" in app
