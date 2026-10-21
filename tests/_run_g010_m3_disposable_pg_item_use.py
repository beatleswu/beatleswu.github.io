"""D5C one-time native PostgreSQL concurrency proofs; destructive only to NEW loopback DB.

Never accepts DATABASE_URL or credentials/tokens for Product/Oracle. Temporary
cluster and the disposable g010_test_d5c database are destroyed on exit.
"""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile


def main():
    if os.environ.get("PRODUCTION","").lower()=="true":
        raise RuntimeError("Production environment forbidden")
    b=os.environ.get("MONTHLY_TEST_PG_BIN")
    initdb=str(Path(b)/"initdb") if b else shutil.which("initdb")
    ctl=str(Path(b)/"pg_ctl") if b else shutil.which("pg_ctl")
    assert initdb and ctl
    with tempfile.TemporaryDirectory(prefix="go-m3-d5c-isolated-") as folder:
        base=Path(folder)
        data=base/"data"
        with socket.socket() as s:
            s.bind(("127.0.0.1",0))
            port=s.getsockname()[1]
        def control(args):
            with (base/"control.log").open("a",encoding="utf-8") as log:
                result=subprocess.run(args,stdin=subprocess.DEVNULL,
                    stdout=log,stderr=subprocess.STDOUT,timeout=75)
            if result.returncode:
                raise RuntimeError((base/"control.log").read_text(
                    encoding="utf-8",errors="replace")[-3500:])
        control([initdb,"-D",str(data),"-U","g010_m3_test","-A","trust",
                 "--no-locale","-E","UTF8"])
        started=False
        try:
            control([ctl,"-D",str(data),"-l",str(base/"server.log"),
                     "-o",f"-h 127.0.0.1 -p {port} -F","-w","start"])
            started=True
            import psycopg2
            db=psycopg2.connect(
                f"postgresql://g010_m3_test@127.0.0.1:{port}/postgres",
                connect_timeout=5)
            db.autocommit=True
            try:
                with db.cursor() as cur:
                    cur.execute("CREATE DATABASE g010_test_d5c")
            finally:
                db.close()
            env=dict(os.environ)
            env.pop("DATABASE_URL",None)
            env["PRODUCTION"]="false"
            env["D5C_ITEM_LINEAGE_POSTGRES_URL"]=(
                f"postgresql://g010_m3_test@127.0.0.1:{port}/g010_test_d5c")
            env["D5C_ITEM_LINEAGE_POSTGRES_DISPOSABLE"]="1"
            result=subprocess.run([
                sys.executable,"-B","-m","pytest","-q",
                "tests/test_d5c_item_use_operation_lineage.py",
                "-k","postgres",
                "--tb=short","--show-capture=no",
                "--disable-warnings","--maxfail=1",
            ],cwd=Path(__file__).resolve().parents[1],env=env,
                capture_output=True,text=True,encoding="utf-8",errors="replace",
                timeout=155)
            print(result.stdout,flush=True)
            if result.returncode==0:
                print("G010_M3_D5C_REAL_PG_CONCURRENCY=PASS",flush=True)
            return result.returncode
        finally:
            if started:
                control([ctl,"-D",str(data),"-m","fast","-w","stop"])
            print("G010_M3_D5C_DISPOSABLE_PG_DESTROYED=TRUE",flush=True)


if __name__=="__main__":
    raise SystemExit(main())
