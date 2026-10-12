"""RC02 (index.html::_adventureQuestionSeen) in a real Chrome against real authenticated Flask + disposable PostgreSQL.

Prefix g009_claude_rc0102_20261012_<RUN_NONCE>. Hard BLOCKED_ENVIRONMENT (no skip) when Docker / Chrome / Playwright are absent.
The same module is the negative control: against 308+P1 (and RC01-only) the RC02 expectations must FAIL.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from test_g009_p1_public_due_only_real_pg import ROOT, Runtime, _json, body
from test_g009_rc0102_real_pg import RcRuntime

NODE = shutil.which("node")
CHROME = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
PLAYWRIGHT = Path("C:/Users/beatl/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright")


class BrowserRuntime(RcRuntime):
    def start(self):
        assert NODE and CHROME.exists() and PLAYWRIGHT.exists(), "BLOCKED_ENVIRONMENT: Node / Chrome / Playwright required"
        super().start()
        from werkzeug.serving import make_server
        self.server = make_server("127.0.0.1", 0, self.app_module.app, threaded=True)
        self.http_port = self.server.server_port
        assert self.http_port > 1024 and self.http_port != 5085
        self.url = f"http://127.0.0.1:{self.http_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        if getattr(self, "server", None):
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=10)
        super().close()


@pytest.fixture(scope="module")
def rt():
    value = BrowserRuntime()
    try:
        value.start()
        yield value
    finally:
        value.close()


RESULTS = []
IDS = [7201, 7202, 7203]


def run_case(rt, case, seed):
    uid, client = rt.user()
    seed(rt, uid, client)
    with client.session_transaction() as session:
        pass
    cookie = client.get_cookie("session").value
    config = {"baseURL": rt.url, "userId": uid, "cookie": cookie, "case": case, "ids": IDS,
              "profile": str(rt.tmp / f"chrome_{case}_{uid}")}
    config_path = rt.tmp / f"config_{case}_{uid}.json"
    config_path.write_text(_json(config), encoding="utf-8")
    before = rt.snapshot(uid)
    proc = subprocess.run([NODE, str(ROOT / "tests/e2e/run_g009_rc02_adventure_seen_browser.mjs"), str(config_path)], cwd=ROOT,
                          text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=240,
                          env={**os.environ, "TEMP": str(rt.tmp), "TMP": str(rt.tmp)})
    after = rt.snapshot(uid)
    events = [json.loads(l[len("RC02_EVENT "):]) for l in proc.stdout.splitlines() if l.startswith("RC02_EVENT ")]
    errors = [l for l in proc.stdout.splitlines() if "PAGE_ERROR" in l]
    record = {"case": case, "uid": uid, "exit": proc.returncode, "command": [NODE, "tests/e2e/run_g009_rc02_adventure_seen_browser.mjs", str(config_path)],
              "cwd": str(ROOT), "events": events, "page_errors": errors, "stderr_tail": proc.stderr[-1500:],
              "review_rows_before": len(before.get("review_log", [])), "review_rows_after": len(after.get("review_log", [])),
              "cards_after": {c["question_id"]: {k: c[k] for k in ("interval", "due_date", "last_grade", "repetitions")} for c in after.get("srs_cards", [])},
              "verdict": "PASS" if proc.returncode == 0 else "FAIL"}
    RESULTS.append(record)
    rt.save(f"BROWSER_{case}", record)
    return proc, record


def seed_wrong(ids):
    def seed(rt, uid, client):
        for n, q in enumerate(ids):
            assert client.post("/api/srs/review", json=body(f"rc02-seed-{uid}-{q}", 0, q)).status_code == 200
    return seed


def seed_none(rt, uid, client):
    return None


def test_r1_mixed_wrong_and_virgin_prefers_the_true_unseen(rt):
    proc, rec = run_case(rt, "R1", seed_wrong([7201]))
    assert proc.returncode == 0, proc.stdout[-1800:] + proc.stderr[-800:]


def test_r2_accepted_wrong_answer_marks_seen_across_init_and_reload(rt):
    proc, rec = run_case(rt, "R2", seed_none)
    assert proc.returncode == 0, proc.stdout[-1800:] + proc.stderr[-800:]
    assert rec["review_rows_after"] == 1


def test_r3_all_seen_wrong_reinforces_and_all_defeated_stops(rt):
    proc, rec = run_case(rt, "R3", seed_wrong(IDS))
    assert proc.returncode == 0, proc.stdout[-1800:] + proc.stderr[-800:]


def test_r5_two_real_clients_agree_with_the_server(rt):
    proc, rec = run_case(rt, "R5", seed_none)
    assert proc.returncode == 0, proc.stdout[-1800:] + proc.stderr[-800:]


def test_zz_summary(rt):
    rt.save("BROWSER_SUMMARY", {"cases": RESULTS})
    assert {r["case"] for r in RESULTS} == {"R1", "R2", "R3", "R5"}
