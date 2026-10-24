"""G090 P0-C: the server COMMITTED a real canonical Shop purchase and emitted
a successful HTTP response, but an actual loopback TCP proxy drops that
response before the client can receive any status/headers/body.
A fresh authenticated client reconnects after an HTTP server restart and
replays the same operation ID. Native disposable PostgreSQL only.
No Product runtime changes; never uses Oracle or real player accounts.
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import socketserver
import threading

from werkzeug.serving import make_server

from test_g090b_shop_late_fault_native_pg import (
    shop, local_postgres, runtime, signed_client, snapshot, UID, SKU, _events,
)

OPERATION="g090c-postcommit-tcp-lost-response-001"
REQUEST={"item_id":SKU,"purchase_operation_id":OPERATION,"price":1,"coins":999999}
MAX_REQUEST=32768
MAX_REPLY=1048576


def _http_post(port, session_cookie):
    conn=http.client.HTTPConnection("127.0.0.1",port,timeout=15)
    try:
        conn.request("POST","/api/shop/buy",body=json.dumps(REQUEST),headers={
            "Content-Type":"application/json",
            "Cookie":f"session={session_cookie}",
            "Connection":"close",
        })
        resp=conn.getresponse()
        payload=resp.read()
        return resp.status,json.loads(payload)
    finally:
        conn.close()


def _ledger(app):
    with app.get_db() as conn:
        return [dict(row) for row in conn.execute(
            "SELECT id,delta,balance_after,reason FROM currency_log "
            "WHERE user_id=? ORDER BY id",(UID,)).fetchall()]


def test_real_tcp_response_lost_after_commit_replay_on_new_http_server(shop,tmp_path):
    assert os.environ.get("PRODUCTION","").lower()!="true"
    signed=signed_client(shop)
    cookie=signed.get_cookie("session")
    assert cookie and cookie.value
    catalog=signed.get("/api/shop/catalog")
    assert catalog.status_code==200 and catalog.get_json()["purchase_enabled"] is True

    before=snapshot(shop)
    before_events=_events(shop)
    before_ledger=_ledger(shop)
    assert before["stats"]=={"coins":1000,"xp":0}
    assert not before["operations"] and not before["owned"]
    assert not before_events and not before_ledger

    backend=make_server("127.0.0.1",0,shop.app.wsgi_app,threaded=True)
    backend_thread=threading.Thread(target=backend.serve_forever,daemon=True)
    backend_thread.start()
    backend_port=backend.server_port
    dropped={}
    forwarded=threading.Event()

    class OneShotDroppedSuccessfulResponse(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(20)
            request=b""
            while b"\r\n\r\n" not in request:
                part=self.request.recv(8192)
                assert part,"Client closed before headers"
                request+=part
                assert len(request)<MAX_REQUEST
            headers,body=request.split(b"\r\n\r\n",1)
            first=headers.split(b"\r\n",1)[0]
            assert first.startswith(b"POST /api/shop/buy ")
            lengths=[
                int(line.split(b":",1)[1].strip())
                for line in headers.split(b"\r\n")
                if line.lower().startswith(b"content-length:")
            ]
            assert len(lengths)==1
            content_length=lengths[0]
            assert 0<content_length<MAX_REQUEST
            while len(body)<content_length:
                part=self.request.recv(8192)
                assert part,"Client closed before request body"
                body+=part
            assert len(body)==content_length
            reply=bytearray()
            with socket.create_connection(("127.0.0.1",backend_port),timeout=20) as upstream:
                upstream.settimeout(20)
                upstream.sendall(headers+b"\r\n\r\n"+body)
                upstream.shutdown(socket.SHUT_WR)
                while True:
                    part=upstream.recv(8192)
                    if not part:
                        break
                    reply.extend(part)
                    assert len(reply)<MAX_REPLY
            status_line=bytes(reply).split(b"\r\n",1)[0]
            dropped["upstream_status_line"]=status_line.decode("ascii","replace")
            dropped["upstream_response_length"]=len(reply)
            dropped["forwarded_response_bytes"]=0
            forwarded.set()
            # Deliberately return without sending ANY backend response bytes.
            # TCP FIN/RST occurs after the DB COMMIT and the backend's HTTP 200.

    class LocalOnlyProxy(socketserver.ThreadingTCPServer):
        allow_reuse_address=True
        daemon_threads=True

    proxy=LocalOnlyProxy(("127.0.0.1",0),OneShotDroppedSuccessfulResponse)
    proxy_thread=threading.Thread(target=proxy.serve_forever,daemon=True)
    proxy_thread.start()
    error_type=None
    try:
        conn=http.client.HTTPConnection("127.0.0.1",proxy.server_address[1],timeout=20)
        try:
            conn.request("POST","/api/shop/buy",body=json.dumps(REQUEST),headers={
                "Content-Type":"application/json",
                "Cookie":f"session={cookie.value}",
                "Connection":"close",
            })
            try:
                response=conn.getresponse()
            except (http.client.RemoteDisconnected,ConnectionResetError,ConnectionAbortedError) as error:
                error_type=type(error).__name__
            else:
                response.read()
                raise AssertionError("Expected real missing HTTP response, got HTTP status "+
                                     str(response.status))
        finally:
            conn.close()

        assert error_type,"TCP transport must fail to deliver response"
        assert forwarded.wait(timeout=15),"Proxy did not receive committed upstream response"
        assert dropped["upstream_status_line"].startswith("HTTP/1.") and " 200 " in dropped["upstream_status_line"],dropped

        after_lost=snapshot(shop)
        events_lost=_events(shop)
        ledger_lost=_ledger(shop)
        assert after_lost["stats"]=={"coins":700,"xp":0}
        assert len(after_lost["operations"])==len(after_lost["debits"])==len(after_lost["owned"])==1
        assert after_lost["debits"][0]["delta"]==-300
        assert after_lost["owned"][0]["equip_id"]==SKU
        assert len(ledger_lost)==1
        assert ledger_lost[0]["delta"]==-300 and ledger_lost[0]["balance_after"]==700
        assert ledger_lost[0]["reason"]==f"coin_purchase:shop.static.{SKU}:{OPERATION}"
        assert len(events_lost)==1
        event=events_lost[0]
        assert event["event_type"]=="ITEM_ACQUISITION" and event["outcome"]=="SUCCESS"
        assert event["source_event_id"]==f"purchase:{UID}:{OPERATION}"
        assert event["idempotency_key"]==f"coin-purchase-acquisition:{OPERATION}"
        payload=event["payload"]
        if isinstance(payload,str):
            payload=json.loads(payload)
        assert payload["source"]=="SHOP" and payload["item_id"]==SKU
        assert payload["coins_spent"]==300 and payload["coins_after"]==700

        # Restart only the disposable HTTP server; no OS process crash claimed.
        backend.shutdown()
        backend_thread.join(timeout=10)
        backend.server_close()
        backend=None
        restarted=make_server("127.0.0.1",0,shop.app.wsgi_app,threaded=True)
        restarted_thread=threading.Thread(target=restarted.serve_forever,daemon=True)
        restarted_thread.start()
        try:
            fresh_cookie=signed_client(shop).get_cookie("session")
            assert fresh_cookie and fresh_cookie.value
            attempts=[]
            for _ in range(3):
                status,body=_http_post(restarted.server_port,fresh_cookie.value)
                assert status==200,(status,body)
                assert body.get("replayed") is True,body
                attempts.append(status)
            assert snapshot(shop)==after_lost
            assert _events(shop)==events_lost
            assert _ledger(shop)==ledger_lost
            check=signed_client(shop).get("/api/shop/catalog")
            assert check.status_code==200 and check.get_json()["coins"]==700
        finally:
            restarted.shutdown()
            restarted_thread.join(timeout=10)
            restarted.server_close()
        receipt={
          "schema":"G090_P0C_COMMIT_THEN_REAL_TCP_RESPONSE_LOST_NATIVE_PG_V1",
          "test_only":True,"original_backend_http_status":200,
          "upstream_complete_response_bytes":dropped["upstream_response_length"],
          "proxy_forwarded_bytes_to_client":0,
          "client_transport_failure":error_type,
          "backend_commit_verified_by_postgresql":True,
          "coins_before":1000,"coins_after_commit":700,
          "currency_ledger_delta":-300,"purchase_operation_count":1,
          "equipment_owned_count":1,"outbox_event_count":1,
          "http_server_restarted_after_commit":True,
          "process_kill_tested":False,
          "post_restart_retries":len(attempts),
          "post_restart_statuses":attempts,
          "post_restart_replayed":True,
          "post_restart_snapshots_identical":True,
          "native_disposable_postgresql":True,
          "unmodified_product_wsgi":True,
          "production_data_write":False,
        }
        (tmp_path/"G090_P0C_REAL_TCP_LOST_SUCCESS_RECEIPT.json").write_text(
            json.dumps(receipt,ensure_ascii=False,indent=2),encoding="utf8")
    finally:
        proxy.shutdown()
        proxy_thread.join(timeout=10)
        proxy.server_close()
        if backend is not None:
            backend.shutdown()
            backend_thread.join(timeout=10)
            backend.server_close()
