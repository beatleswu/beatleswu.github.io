import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

RUNTIME_FILES = {
    "sgf_answer_review_queue.py": "/app/sgf_answer_review_queue.py",
    "sgf_answer_review_routes.py": "/app/sgf_answer_review_routes.py",
    "sgf_answer_review.html": "/app/sgf_answer_review.html",
    "sgf_answer_review.js": "/app/sgf_answer_review.js",
    "review_data/sgf_answer_review_queue_v1.json": "/app/review_data/sgf_answer_review_queue_v1.json",
}


def test_review_queue_runtime_files_are_explicit_build_inputs_and_verified():
    manifest = json.loads((ROOT / "deploy" / "build-manifest.json").read_text(encoding="utf-8"))
    inputs = set(manifest["build_inputs"]["tracked_in_canonical_branch_this_sprint"])
    verification = set(manifest["post_build_verification_files"])

    assert RUNTIME_FILES.keys() <= inputs
    assert set(RUNTIME_FILES.values()) <= verification


def test_dockerfile_explicitly_packages_review_queue_without_canonical_questions():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY sgf_answer_review_queue.py ./" in dockerfile
    assert "COPY sgf_answer_review_routes.py ./" in dockerfile
    assert "sgf_answer_review.html" in dockerfile
    assert "sgf_answer_review.js" in dockerfile
    assert "COPY review_data/sgf_answer_review_queue_v1.json" in dockerfile
    assert "COPY questions.json" not in dockerfile


def test_local_qa_bootstrap_harness_is_not_packaged_in_runtime_image():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / "deploy" / "build-manifest.json").read_text(encoding="utf-8"))
    serialized_manifest = json.dumps(manifest, sort_keys=True)

    assert "run_sgf_answer_review_queue_qa.py" not in dockerfile
    assert "run_sgf_answer_review_queue_qa.py" not in serialized_manifest


def test_bundled_review_source_has_reviewed_detector_hash():
    source = ROOT / "review_data" / "sgf_answer_review_queue_v1.json"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == (
        "ccfb20ca81a4daaa83b7b172426c490a7c732287810521caedc5782a8052b51e"
    )
