"""Run D015/D017 concurrent Quest reward proofs on isolated disposable PG.

Creates two throwaway PostgreSQL databases in a newly initialized,
loopback-only native cluster. Refuses any existing/provided DATABASE_URL,
production database, or privileged external connections. Deletes cluster
on exit. Never writes Oracle, customer data, or release configuration.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile

def main() -> int:
    assert os.environ.get("PRODUCTION", "").lower() != "true", "production execution forbidden"
    db_bin = os.environ.get("MONTHLY_TEST_PG_BIN")
    initdb = str(Path(db_bin) / "initdb") if db_bin else shutil.which("initdb")
    pg_ctl = str(Path(db_bin) / "pg_ctl") if db_bin else shutil.which("pg_ctl")
    assert initdb and pg_ctl, "Native initdb / pg_ctl not present"
    with tempfile.TemporaryDirectory(prefix="go-g010-m2-disposable-pg-") as root_text:
        root = Path(root_text)
        data = root / "pgdata"
        log = root / "postgres.log"
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        def run_control(args):
            with (root / "control.log").open("a", encoding="utf-8") as output:
                p = subprocess.run(args, stdin=subprocess.DEVNULL,
                                   stdout=output, stderr=subprocess.STDOUT,
                                   timeout=75)
            if p.returncode:
                raise RuntimeError((root / "control.log").read_text(
                    encoding="utf-8", errors="replace")[-4000:])
        run_control([initdb, "-D", str(data), "-U", "g010_test",
                     "-A", "trust", "--no-locale", "-E", "UTF8"])
        started = False
        try:
            run_control([pg_ctl, "-D", str(data), "-l", str(log),
                         "-o", f"-h 127.0.0.1 -p {port} -F", "-w", "start"])
            started = True
            import psycopg2
            conn = psycopg2.connect(
                f"postgresql://g010_test@127.0.0.1:{port}/postgres",
                connect_timeout=5)
            conn.autocommit = True
            try:
                for name in ("g010_test_d015", "g010_test_d017"):
                    with conn.cursor() as cur:
                        cur.execute(f"CREATE DATABASE {name}")
            finally:
                conn.close()

            env = dict(os.environ)
            env.pop("DATABASE_URL", None)
            env["PRODUCTION"] = "false"
            for stage in ("D015", "D017"):
                env[f"{stage}_QUEST_POSTGRES_URL"] = (
                    f"postgresql://g010_test@127.0.0.1:{port}/g010_test_{stage.lower()}")
                env[f"{stage}_QUEST_POSTGRES_DISPOSABLE"] = "1"
            print("G010_M2_CONCURRENCY_DISPOSABLE_CLUSTER_STARTED", flush=True)
            # D017 has a separate, immutably version-pinned preflight
            # requiring exactly PostgreSQL 16.14. The available native
            # server is 17.10. Do NOT spoof the server version or edit the
            # preflight; run the three version-agnostic integration tests
            # and leave the 16.14 certification explicitly UNVERIFIED.
            groups = [
                ("D015_NATIVE_PG", [
                    "tests/test_d015_quest_claim_reward_postgres.py"]),
                ("D017_NATIVE_PG_17_COMPAT", [
                    "tests/test_d017_quest_runtime_postgres.py",
                    "-k", "not preflight"]),
            ]
            for label, selected in groups:
                command = [
                    sys.executable, "-B", "-m", "pytest", "-q", *selected,
                    "--tb=short", "--show-capture=no",
                    "--disable-warnings", "--maxfail=1",
                ]
                result = subprocess.run(
                    command, env=env,
                    cwd=Path(__file__).resolve().parents[1],
                    text=True, encoding="utf-8", errors="replace",
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
                print(label, result.stdout, flush=True)
                if result.returncode:
                    return result.returncode
            print("G010_M2_DISPOSABLE_PG_CONCURRENCY_PASS=TRUE", flush=True)
            print("D017_PG16_14_EXACT_PREFLIGHT=NOT_VERIFIED", flush=True)
            return 0
        finally:
            if started:
                run_control([pg_ctl, "-D", str(data), "-m", "fast", "-w", "stop"])
            print("G010_M2_DISPOSABLE_PG_DESTROYED=TRUE", flush=True)

if __name__ == "__main__":
    raise SystemExit(main())
