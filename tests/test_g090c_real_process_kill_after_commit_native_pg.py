"""G090 P0-C: true OS worker-process termination AFTER DB commit and BEFORE
the client gets any server response. Disposable native PG17 + real loopback
HTTP + actual independent Python subprocess; no change to production code.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import socketserver
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

from test_g090b_shop_late_fault_native_pg import (
    shop, local_postgres, runtime, signed_client, snapshot, UID, SKU, _events,
)

OPERATION="g090c-real-os-worker-kill-after-commit-001"
REQUEST={"item_id":SKU,"purchase_operation_id":OPERATION,"price":1,"coins":999999}


def _find_free_loopback_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        return sock.getsockname()[1]


def _worker_main(port, hold_precommit=False):
    url=os.environ.get("DATABASE_URL","")
    parsed=urlsplit(url)
    assert parsed.scheme in {"postgresql","postgres"}
    assert parsed.hostname=="127.0.0.1"
    assert parsed.username=="monthly_test"
    assert (parsed.path or "")=="/postgres"
    assert os.environ.get("PRODUCTION","").lower()!="true"
    assert os.environ.get("SECRET_KEY")=="monthly-disposable-test-only"
    import app
    from werkzeug.serving import make_server
    if hold_precommit:
        real_purchase=app.purchase_equipment_with_coins
        def hold_after_real_mutation(*args,**kwargs):
            result=real_purchase(*args,**kwargs)
            print("G090_UNCOMMITTED_MUTATIONS_READY",flush=True)
            # Test-only fault pause: DB transaction is open and uncommitted.
            # OS TerminateProcess from parent must release & roll it back.
            threading.Event().wait(timeout=80)
            return result
        app.purchase_equipment_with_coins=hold_after_real_mutation
    httpd=make_server("127.0.0.1",port,app.app.wsgi_app,threaded=True)
    print(f"G090_OS_WORKER_READY:{os.getpid()}:{port}",flush=True)
    httpd.serve_forever()


if __name__=="__main__" and len(sys.argv) in (3,4) and sys.argv[1]=="--worker":
    _worker_main(int(sys.argv[2]), hold_precommit=(
        len(sys.argv)==4 and sys.argv[3]=="--hold-precommit"
    ))


def _request(port,cookie,body):
    c=http.client.HTTPConnection("127.0.0.1",port,timeout=20)
    try:
        c.request("POST","/api/shop/buy",body=json.dumps(body),headers={
            "Content-Type":"application/json",
            "Cookie":f"session={cookie}",
            "Connection":"close",
        })
        res=c.getresponse()
        return res.status,json.loads(res.read())
    finally:
        c.close()


def _receive_no_response(port,cookie):
    try:
        return _request(port,cookie,REQUEST)
    except (http.client.RemoteDisconnected,ConnectionResetError,ConnectionAbortedError) as e:
        return "TRANSPORT_LOST",type(e).__name__


def _probe_worker(port,cookie):
    c=http.client.HTTPConnection("127.0.0.1",port,timeout=1.5)
    try:
        c.request("GET","/api/shop/catalog",headers={
            "Cookie":f"session={cookie}","Connection":"close",
        })
        res=c.getresponse()
        res.read()
        return res.status==200
    finally:
        c.close()


def _ledger(app):
    with app.get_db() as conn:
        return [dict(row) for row in conn.execute(
            "SELECT id,delta,balance_after,reason FROM currency_log "
            "WHERE user_id=? ORDER BY id",(UID,)).fetchall()]


def test_killed_real_worker_after_purchase_commit_before_response_disclosed(shop,tmp_path):
    assert os.environ.get("PRODUCTION","").lower()!="true"
    parent_client=signed_client(shop)
    cookie=parent_client.get_cookie("session")
    assert cookie and cookie.value
    before=snapshot(shop)
    before_events=_events(shop)
    before_ledger=_ledger(shop)
    assert before["stats"]=={"coins":1000,"xp":0}
    assert not before["owned"] and not before["operations"]
    assert not before_events and not before_ledger

    worker_log1=tmp_path/"G090_P0C_WORKER1.log"
    worker_log2=tmp_path/"G090_P0C_WORKER2.log"
    workers=[]
    log_handles=[]
    def launch(port,logpath):
        env=dict(os.environ)
        env["PYTHONPATH"]=str(Path(__file__).resolve().parents[1])
        assert urlsplit(env["DATABASE_URL"]).hostname=="127.0.0.1"
        output=logpath.open("wb")
        log_handles.append(output)
        process=subprocess.Popen(
            [sys.executable,"-B",str(Path(__file__).resolve()),"--worker",str(port)],
            cwd=str(Path(__file__).resolve().parents[1]),
            env=env,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,
        )
        workers.append(process)
        for attempt in range(180):
            if process.poll() is not None:
                raise AssertionError(f"Worker died at startup: {process.returncode}")
            try:
                if _probe_worker(port,cookie.value):
                    return process
            except (OSError,http.client.HTTPException):
                pass
            time.sleep(0.1)
        raise AssertionError("Worker not ready within bounded loopback startup")

    port1=_find_free_loopback_port()
    proxy_finished=threading.Event()
    allow_client_disconnect=threading.Event()
    observed={}
    proxy=None
    proxy_thread=None
    try:
        worker1=launch(port1,worker_log1)
        assert worker1.poll() is None

        class HoldAfterRealSuccessfulBackendResponse(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.settimeout(25)
                raw=b""
                while b"\r\n\r\n" not in raw:
                    chunk=self.request.recv(8192)
                    assert chunk
                    raw+=chunk
                    assert len(raw)<32768
                header,body=raw.split(b"\r\n\r\n",1)
                assert header.split(b"\r\n",1)[0].startswith(b"POST /api/shop/buy ")
                lengths=[int(line.split(b":",1)[1].strip()) for line in header.split(b"\r\n")
                         if line.lower().startswith(b"content-length:")]
                assert len(lengths)==1 and 0<lengths[0]<32768
                while len(body)<lengths[0]:
                    chunk=self.request.recv(8192)
                    assert chunk
                    body+=chunk
                assert len(body)==lengths[0]
                output=bytearray()
                with socket.create_connection(("127.0.0.1",port1),timeout=20) as backend:
                    backend.settimeout(20)
                    backend.sendall(header+b"\r\n\r\n"+body)
                    backend.shutdown(socket.SHUT_WR)
                    while True:
                        part=backend.recv(8192)
                        if not part:
                            break
                        output.extend(part)
                        assert len(output)<1048576
                observed["upstream_status"]=bytes(output).split(b"\r\n",1)[0].decode("ascii","replace")
                observed["upstream_bytes"]=len(output)
                observed["forwarded_bytes"]=0
                proxy_finished.set()
                # Parent kills the actual backend OS process before
                # permitting this transport connection to disconnect.
                assert allow_client_disconnect.wait(timeout=20)
                # Close without sending a single byte of the committed HTTP 200.

        class LoopbackProxy(socketserver.ThreadingTCPServer):
            allow_reuse_address=True
            daemon_threads=True

        proxy=LoopbackProxy(("127.0.0.1",0),HoldAfterRealSuccessfulBackendResponse)
        proxy_thread=threading.Thread(target=proxy.serve_forever,daemon=True)
        proxy_thread.start()

        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(_receive_no_response,proxy.server_address[1],cookie.value)
            assert proxy_finished.wait(timeout=25),"Backend commit/reply never reached proxy"
            assert observed["upstream_status"].startswith("HTTP/1.") and " 200 " in observed["upstream_status"],observed
            assert worker1.poll() is None,"Worker already died before deliberate kill"
            # Prove actual database COMMIT independent from backend process.
            committed=snapshot(shop)
            committed_events=_events(shop)
            committed_ledger=_ledger(shop)
            assert committed["stats"]=={"coins":700,"xp":0}
            assert len(committed["operations"])==len(committed["owned"])==len(committed["debits"])==1
            assert committed["owned"][0]["equip_id"]==SKU
            assert len(committed_events)==len(committed_ledger)==1
            assert committed_ledger[0]["delta"]==-300
            assert committed_ledger[0]["balance_after"]==700
            assert committed_ledger[0]["reason"]==f"coin_purchase:shop.static.{SKU}:{OPERATION}"
            event=committed_events[0]
            assert event["event_type"]=="ITEM_ACQUISITION" and event["outcome"]=="SUCCESS"
            assert event["source_event_id"]==f"purchase:{UID}:{OPERATION}"
            assert event["idempotency_key"]==f"coin-purchase-acquisition:{OPERATION}"

            worker1.kill() # Windows TerminateProcess, not a Python exception simulation.
            exit1=worker1.wait(timeout=12)
            assert exit1!=0
            assert worker1.poll() is not None
            allow_client_disconnect.set()
            failure=future.result(timeout=18)
            assert failure==("TRANSPORT_LOST","RemoteDisconnected"),failure

        # This is a genuinely DIFFERENT operating-system PID, same durable PG.
        port2=_find_free_loopback_port()
        worker2=launch(port2,worker_log2)
        assert worker2.pid!=worker1.pid and worker2.poll() is None
        fresh=signed_client(shop).get_cookie("session")
        assert fresh and fresh.value
        statuses=[]
        for _ in range(3):
            status,answer=_request(port2,fresh.value,REQUEST)
            assert status==200,(status,answer)
            assert answer.get("replayed") is True,answer
            statuses.append(status)
        assert snapshot(shop)==committed
        assert _events(shop)==committed_events
        assert _ledger(shop)==committed_ledger
        assert _probe_worker(port2,fresh.value)

        receipt={
            "schema":"G090_P0C_REAL_PROCESS_KILL_AFTER_COMMIT_RESPONSE_LOST_V1",
            "native_disposable_postgresql":True,"original_flask_product_api":True,
            "worker1_pid":worker1.pid,"worker2_pid":worker2.pid,
            "worker1_exit_after_forced_os_kill":exit1,
            "worker1_alive_until_successful_backend_200":True,
            "backend_response_status":200,
            "backend_response_bytes_held_by_proxy":observed["upstream_bytes"],
            "client_response_bytes_forwarded":0,
            "client_error":failure[1],
            "committed_postgres_coins_before":1000,
            "committed_postgres_coins_after":700,
            "committed_ledger_delta":-300,
            "committed_purchase_count":1,
            "committed_equipment_count":1,
            "committed_outbox_count":1,
            "worker_restarted_in_new_os_process":True,
            "post_restart_replays":3,
            "post_restart_statuses":statuses,
            "post_restart_snapshot_identical":True,
            "limitations":[
                "OS kill occurred after the transaction committed and backend returned 200 to proxy; this does NOT test mid-transaction kill",
                "Only canonical Shop wooden_sword source, not quest/lord/daily cross-source process kill",
                "Real loopback HTTP proxy dropped all response bytes; no WAN or Oracle failover",
            ],
            "production_data_write":False,"product_code_modified":False
        }
        (tmp_path/"G090_P0C_REAL_OS_KILL_PG_RECEIPT.json").write_text(
            json.dumps(receipt,ensure_ascii=False,indent=2),encoding="utf8")
    finally:
        allow_client_disconnect.set()
        if proxy is not None:
            proxy.shutdown()
            proxy.server_close()
            if proxy_thread is not None:
                proxy_thread.join(timeout=8)
        for worker in workers:
            if worker.poll() is None:
                worker.kill()
            worker.wait(timeout=10)
        for handle in log_handles:
            handle.close()


def test_real_os_kill_before_outer_commit_rolls_back_and_same_operation_can_retry(shop,tmp_path):
    """Worker dies while its genuine purchase transaction is still open.

    This differs from the post-commit response-loss test: termination happens
    immediately after purchase_with_coins returns, before app.py conn.commit.
    """
    operation="g090c-midtransaction-os-kill-rollback-001"
    payload={"item_id":SKU,"purchase_operation_id":operation,
             "price":1,"coins":999999}
    cookie=signed_client(shop).get_cookie("session")
    assert cookie and cookie.value
    original=snapshot(shop)
    events_before=_events(shop)
    ledger_before=_ledger(shop)
    assert original["stats"]=={"coins":1000,"xp":0}
    assert not original["operations"] and not original["owned"]
    assert not events_before and not ledger_before
    workers=[]
    logs=[]
    def start(hold):
        port=_find_free_loopback_port()
        path=tmp_path/("G090_P0C_PRECOMMIT_FAULT_WORKER.log" if hold
                       else "G090_P0C_PRECOMMIT_RECOVERY_WORKER.log")
        output=path.open("wb")
        logs.append(output)
        cmd=[sys.executable,"-B",str(Path(__file__).resolve()),
             "--worker",str(port)]
        if hold:
            cmd.append("--hold-precommit")
        env=dict(os.environ)
        env["PYTHONPATH"]=str(Path(__file__).resolve().parents[1])
        assert urlsplit(env["DATABASE_URL"]).hostname=="127.0.0.1"
        proc=subprocess.Popen(cmd,cwd=str(Path(__file__).resolve().parents[1]),
             env=env,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT)
        workers.append(proc)
        for _ in range(180):
            if proc.poll() is not None:
                raise AssertionError("Worker exited during startup, code "+str(proc.returncode))
            try:
                if _probe_worker(port,cookie.value):
                    return proc,port,path
            except (OSError,http.client.HTTPException):
                pass
            time.sleep(0.1)
        raise AssertionError("Worker failed loopback readiness check")

    try:
        dying,port1,worker_log=start(hold=True)
        def request_and_expect_transport_loss():
            try:
                return _request(port1,cookie.value,payload)
            except (http.client.RemoteDisconnected,
                    ConnectionResetError,ConnectionAbortedError) as exc:
                return "TRANSPORT_LOST",type(exc).__name__

        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(request_and_expect_transport_loss)
            fault_seen=False
            for _ in range(200):
                if "G090_UNCOMMITTED_MUTATIONS_READY" in worker_log.read_text(
                    encoding="utf-8",errors="replace"):
                    fault_seen=True
                    break
                assert dying.poll() is None, "Worker died before completing real uncommitted mutation"
                time.sleep(0.1)
            assert fault_seen, "Purchase mutation never reached pre-commit fault marker"
            assert dying.poll() is None
            # Another PG session MUST NOT see its not-yet-committed writes.
            assert snapshot(shop)==original
            assert _events(shop)==events_before
            assert _ledger(shop)==ledger_before
            dying.kill()
            dead_code=dying.wait(timeout=12)
            assert dead_code!=0
            network=future.result(timeout=15)
            assert network[0]=="TRANSPORT_LOST" and network[1] in {
                "RemoteDisconnected","ConnectionResetError"
            },network

        # PostgreSQL must now roll back the forcibly killed worker's
        # uncommitted transaction and release its unique-operation reservation.
        assert snapshot(shop)==original, "Process death leaked uncommitted purchase"
        assert _events(shop)==events_before, "Process death leaked uncommitted outbox"
        assert _ledger(shop)==ledger_before, "Process death leaked uncommitted currency ledger"

        recovering,port2,_=start(hold=False)
        assert recovering.pid!=dying.pid and recovering.poll() is None
        fresh=signed_client(shop).get_cookie("session")
        assert fresh and fresh.value
        recovered_status,recovered_body=_request(port2,fresh.value,payload)
        assert recovered_status==200,(recovered_status,recovered_body)
        assert recovered_body.get("replayed") is not True,recovered_body
        after=snapshot(shop)
        events_after=_events(shop)
        ledger_after=_ledger(shop)
        assert after["stats"]=={"coins":700,"xp":0}
        assert len(after["operations"])==len(after["owned"])==len(after["debits"])==1
        assert after["owned"][0]["equip_id"]==SKU
        assert len(events_after)==len(ledger_after)==1
        assert events_after[0]["source_event_id"]==f"purchase:{UID}:{operation}"
        assert events_after[0]["idempotency_key"]==f"coin-purchase-acquisition:{operation}"
        assert events_after[0]["outcome"]=="SUCCESS"
        assert ledger_after[0]["delta"]==-300 and ledger_after[0]["balance_after"]==700
        for _ in range(3):
            status,answer=_request(port2,fresh.value,payload)
            assert status==200 and answer.get("replayed") is True,(status,answer)
        assert snapshot(shop)==after
        assert _events(shop)==events_after
        assert _ledger(shop)==ledger_after
        receipt={
            "schema":"G090_P0C_TRUE_PRECOMMIT_OS_KILL_ROLLBACK_NATIVE_PG_V1",
            "original_product_purchase_executed":True,
            "fault_boundary":"after_real_purchase_mutation_before_outer_commit",
            "uncommitted_mutation_marker_seen":True,
            "real_os_process_terminated":True,
            "worker1_pid":dying.pid,"worker1_killed_exit_code":dead_code,
            "lost_connection":network[1],
            "data_before_kill_visible_to_other_connection":False,
            "data_after_kill_rolled_back":True,
            "same_operation_recovery_worker_pid":recovering.pid,
            "recovery_http_status":recovered_status,
            "coins_before":1000,"coins_after_recovery":700,
            "committed_operations":1,"committed_equipment":1,
            "committed_ledger_rows":1,"committed_outbox_rows":1,
            "post_recovery_replays":3,"post_recovery_snapshot_unchanged":True,
            "native_disposable_postgresql":True,"test_only_worker_hook":True,
            "production_data_write":False,
            "limits":[
                "Test-only block inserted in isolated worker after the genuine purchase mutation, not an arbitrary production power loss",
                "Only one canonical Shop SKU; this is not cross-source mid-transaction crash",
                "Not Oracle/database server termination or WAN failover"
            ]
        }
        (tmp_path/"G090_P0C_PRECOMMIT_KILL_ROLLBACK_RECEIPT.json").write_text(
            json.dumps(receipt,ensure_ascii=False,indent=2),encoding="utf8")
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.kill()
            worker.wait(timeout=12)
        for output in logs:
            output.close()
