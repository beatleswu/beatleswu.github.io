"""R13 scoped successor for the frozen E10 B4 GameSession boundary (sessionStorage exception)."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests" / "e2e" / "run_g009_r13_gamesession_storage_boundary_successor.mjs"


def test_gamesession_storage_exception_is_bounded_to_public_review_recovery():
    result = subprocess.run(["node", str(RUNNER)], cwd=ROOT, text=True, encoding="utf-8", capture_output=True)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["status"] == "PASS"
    assert len(payload["checks"]) == 9
