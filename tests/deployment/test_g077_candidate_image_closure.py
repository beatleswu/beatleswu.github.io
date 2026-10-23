"""G077 candidate curated Docker image closure. This does not authorize deploy."""
from pathlib import Path
import importlib.util
import re
import pytest

ROOT=Path(__file__).resolve().parents[2]
DOCKER=(ROOT/"Dockerfile").read_text(encoding="utf-8")
MODULES=(
 "g076_mode_gate.py","g076_mistakes_product.py","g076_rating_steps.py",
 "g076_grimoire_adapter.py","g076_grimoire_catalog.py",
 "g076_grimoire_pg_service.py","g076_grimoire_product.py")
STATIC=("grimoire_player.html","js/game/g076_rating_step_client.js",
        "js/game/g076_grimoire_product_client.js")
ALL=MODULES+STATIC

@pytest.mark.parametrize("source",ALL)
def test_candidate_runtime_file_exists_and_is_exactly_copied(source):
    assert (ROOT/source).is_file(),source
    # A safe image requires an explicit Dockerfile copy, never COPY . .
    assert re.search(r"(?m)^COPY\s+([^\n]+)",DOCKER)
    if source.endswith(".py") or source.startswith("js/"):
        expected=f"COPY {source} ./"+("" if source.endswith(".py") else source)
        assert expected in DOCKER,source
    else:
        assert DOCKER.count(source)==1

def test_no_broad_copy_all_source():
    assert "COPY . ." not in DOCKER
    assert "COPY tests/" not in DOCKER

def test_build_does_not_enable_new_modes():
    # Runtime gating is by the trustworthy server and must remain OFF by default.
    forbidden=("ENV G076_MISTAKES_STEPS_ENABLED=on",
               "ENV G076_RATING_STEPS_ENABLED=on",
               "ENV G076_GRIMOIRE_STEPS_ENABLED=on",
               "ENV G076_ANSWER_PRIVACY_ENFORCED=on")
    assert all(text not in DOCKER for text in forbidden)

@pytest.mark.parametrize("mod",MODULES)
def test_python_modules_parse_without_app_import(mod):
    import ast
    ast.parse((ROOT/mod).read_text(encoding="utf-8"),filename=mod)
