"""G080 H: REAL disposable PostgreSQL 16 WAL PITR and post-commit logical restore.

No production DSNs or release credentials. All Docker resources have unique
g080h labels; refuses collisions and never deletes pre-existing resources.
Source: exact local isolated G080 G/H worktree. Test-only engineering proof,
NOT authority for live restore, zero-data-loss or database cutover.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from psycopg2 import connect, sql
from psycopg2.extensions import make_dsn

RUN="g080h_20261024_pitr03"
ROOT=Path(r"D:\go-odyssey-g080-h-pitr-recovery")
OUT=Path(r"D:\g079-artifacts\g080-h-pitr03-20261024")
IMAGE="postgres:16"
PRIMARY=RUN+"_primary"
RECOVERY=RUN+"_recovery"
VOLUMES={kind:RUN+"_"+kind for kind in ("pgdata","walarchive","basebackup","recoverdata")}
PWD="g080_h_DISPOSABLE_no_production"
PORTS={}
records=[]
resources=[]
assert ROOT.is_dir() and not OUT.exists(), "Require exact new worktree, fresh evidence directory"
assert re.fullmatch(r"g080h_20261024_pitr\d+",RUN)
OUT.mkdir(parents=True,exist_ok=False)
def tool(*a,input=None,timeout=180,check=True):
    cmd=["docker",*a]
    before=dt.datetime.now(dt.timezone.utc).isoformat()
    p=subprocess.run(cmd,input=input,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
    rec={"command":["docker",*[str(x).replace(PWD,"[DISPOSABLE_PASSWORD]") for x in a]],
         "utc":before,"exit":p.returncode,"stderr_tail":p.stderr.decode("utf-8",errors="replace")[-950:]}
    records.append(rec)
    if check and p.returncode:
        raise RuntimeError(str(rec)+" stdout="+p.stdout.decode("utf-8",errors="replace")[-650:])
    return p
def pg(port,dbname="postgres",autocommit=False):
    assert port in PORTS.values() and isinstance(port,int) and port>1024
    c=connect(host="127.0.0.1",port=port,user="postgres",password=PWD,
              dbname=dbname,connect_timeout=4)
    c.autocommit=autocommit
    return c
def scalar(c,query,args=()):
    with c.cursor() as cur:
        cur.execute(query,args)
        return cur.fetchone()[0]
def wait_pg(port,seconds=85):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:
            c=pg(port)
            assert scalar(c,"SELECT current_database()")=="postgres"
            c.close()
            return
        except Exception:
            time.sleep(.6)
    raise RuntimeError("PostgreSQL not healthy within bounded startup window")
def port_of(container):
    port=tool("port",container,"5432/tcp").stdout.decode().strip().splitlines()[0]
    assert port.startswith("127.0.0.1:"),("UNSAFE_NETWORK_BIND",port)
    n=int(port.rsplit(":",1)[1])
    assert n!=5085 and 1024<n<=65535
    return n
def backup(label):
    path=OUT/(label+".dump")
    p=tool("exec",PRIMARY,"pg_dump","-U","postgres","-d","postgres",
           "-Fc","--no-owner","--no-acl",timeout=150)
    assert len(p.stdout)>1000
    with path.open("xb") as f: f.write(p.stdout)
    h=hashlib.sha256(p.stdout).hexdigest()
    print("LOGICAL_BACKUP",label,path.stat().st_size,h,flush=True)
    return path,h
def count_state(port,dbname="postgres"):
    with pg(port,dbname) as c:
        with c.cursor() as cur:
            cur.execute("SELECT coins,xp FROM user_stats WHERE user_id=983301")
            stats=cur.fetchone()
            assert stats is not None,("MISSING_SYNTHETIC_USER",port,dbname)
            cur.execute("SELECT COUNT(*) FROM review_log WHERE user_id=983301")
            reviews=cur.fetchone()[0]
            cur.execute("SELECT to_regclass('public.g076_mistakes_attempts') IS NOT NULL")
            has=cur.fetchone()[0]
            attempts=None
            if has:
                cur.execute("SELECT COUNT(*) FROM g076_mistakes_attempts WHERE user_id=983301")
                attempts=cur.fetchone()[0]
            return {"coins":stats[0],"xp":stats[1],"reviews":reviews,
                    "migration_committed":has,"mistakes_attempts":attempts}
def restore_logical(src,name):
    assert name in ("g080h_logical_pre","g080h_logical_post")
    admin=pg(PORTS[PRIMARY],autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    finally:
        admin.close()
    p=tool("exec","-i",PRIMARY,"pg_restore","-U","postgres","-d",name,
           "--no-owner","--no-acl","--exit-on-error",input=src.read_bytes(),timeout=160)
    return count_state(PORTS[PRIMARY],name)
def ensure_archive(min_files=2):
    deadline=time.monotonic()+80
    while time.monotonic()<deadline:
        p=tool("exec",PRIMARY,"sh","-c","find /walarchive -maxdepth 1 -type f | wc -l")
        n=int(p.stdout.strip())
        if n>=min_files:return n
        time.sleep(1)
    raise RuntimeError("WAL archive not complete")
def step(stage,**kwargs):
    v={"stage":stage,"timestamp_utc":dt.datetime.now(dt.timezone.utc).isoformat(),**kwargs}
    with (OUT/"progress.jsonl").open("a",encoding="utf-8") as f:
        f.write(json.dumps(v,ensure_ascii=False,default=str)+"\n")
    print("G080_H_STAGE",stage,json.dumps(kwargs,ensure_ascii=False,default=str),flush=True)

def run():
    # All resources must be new. Production hosts/Oracle never passed to docker/psycopg.
    for n in (PRIMARY,RECOVERY):
        assert tool("container","inspect",n,check=False).returncode!=0,"Collision: "+n
    for kind,name in VOLUMES.items():
        assert tool("volume","inspect",name,check=False).returncode!=0,"Volume collision: "+name
        tool("volume","create","--label",f"g080h.run={RUN}",
             "--label","g080h.isolation=disposable-no-production",name)
        resources.append(("volume",name))
    mounts=["--mount",f"type=volume,source={VOLUMES['pgdata']},target=/var/lib/postgresql/data",
            "--mount",f"type=volume,source={VOLUMES['walarchive']},target=/walarchive",
            "--mount",f"type=volume,source={VOLUMES['basebackup']},target=/backup",
            "--mount",f"type=volume,source={VOLUMES['recoverdata']},target=/restore"]
    tool("run","-d","--name",PRIMARY,"--label",f"g080h.run={RUN}",
         "--publish","127.0.0.1::5432",
         *mounts,"-e","POSTGRES_USER=postgres","-e","POSTGRES_PASSWORD="+PWD,
         "-e","POSTGRES_DB=postgres",
         IMAGE,"postgres","-c","archive_mode=on","-c","wal_level=replica",
         "-c","archive_timeout=5s",
         "-c","archive_command=cp %p /walarchive/%f")
    resources.append(("container",PRIMARY))
    PORTS[PRIMARY]=port_of(PRIMARY);wait_pg(PORTS[PRIMARY])
    tool("exec","--user","root",PRIMARY,"chown","postgres:postgres","/walarchive","/backup","/restore")
    with pg(PORTS[PRIMARY]) as c:
        assert scalar(c,"SHOW server_version_num").startswith("160")  # PG16
        assert scalar(c,"SHOW archive_mode")=="on"
        assert scalar(c,"SHOW wal_level")=="replica"
    step("PG16_ISOLATED_ARCHIVING_ON",primary_port=PORTS[PRIMARY])
    # Product source database bootstrap, not a synthetic stand-in schema.
    os.environ.update(DATABASE_URL=f"postgresql://postgres:{PWD}@127.0.0.1:{PORTS[PRIMARY]}/postgres",
                      PRODUCTION="false",SECRET_KEY="g080-h-nonproduction")
    sys.path.insert(0,str(ROOT))
    import db
    db.DATABASE_URL=os.environ["DATABASE_URL"]
    from migrations.sgf_admin_workbench_v1 import upgrade as workbench
    with db.get_db() as c:
        workbench(c);c.commit()
    import app
    app.init_db()
    from migrations.g079_mistakes_steps_v1 import upgrade,APPROVAL
    with pg(PORTS[PRIMARY]) as c:
        with c.cursor() as cur:
            cur.execute("INSERT INTO users(id,username,nickname,password_hash,is_admin,plan,created_at)"
                        " VALUES(983301,'g080-h-pitr-fixture','PITR Synthetic','unused',0,'free','2026-10-24T00:00:00')")
            cur.execute("INSERT INTO user_stats(user_id,coins,rank_level,xp)"
                        " VALUES(983301,500,'LV1',10)")
            cur.execute("INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context)"
                        " VALUES(983301,8001,3,'2026-10-24T00:01:00','pitr_fixture:pre')")
        c.commit()
    pre_state=count_state(PORTS[PRIMARY])
    assert pre_state=={"coins":500,"xp":10,"reviews":1,"migration_committed":False,"mistakes_attempts":None}
    step("PRE_MIGRATION_PRODUCT_SCHEMA_SEEDED",state=pre_state)
    pre,pre_hash=backup("pre_migration")
    # True physical base backup with WAL stream; no -R primary_conninfo.
    tool("exec","--user","postgres","-e","PGPASSWORD="+PWD,PRIMARY,
         "pg_basebackup","-h","127.0.0.1","-p","5432","-U","postgres",
         "-D","/backup","-Fp","-Xs","-c","fast",timeout=240)
    step("PHYSICAL_BASEBACKUP_COMPLETE")
    with pg(PORTS[PRIMARY]) as c:
        with c.cursor() as cur:
            cur.execute("SELECT pg_create_restore_point('g080_h_pre_migration')")
            restore_lsn=str(cur.fetchone()[0])
        c.commit()
    step("PITR_RESTORE_POINT_CREATED",restore_point="g080_h_pre_migration",lsn=restore_lsn)
    # G079 migration authorization controls are real: reject without approve,
    # then roll back *authorized* uncommitted DDL.
    with db.get_db() as c:
        try:
            upgrade(c,environ={})
            raise AssertionError("Missing explicit migration approval was admitted")
        except RuntimeError as e:
            assert "approval" in str(e).lower()
        c.rollback()
        upgrade(c,environ={APPROVAL:"1"})
        c.rollback()
    assert count_state(PORTS[PRIMARY])==pre_state
    step("UNAUTHORIZED_AND_ABORTED_MIGRATION_FAIL_CLOSED")
    # Post-commit state containing all data ledger changes.
    with db.get_db() as c:
        upgrade(c,environ={APPROVAL:"1"})
        c.execute("INSERT INTO g076_mistakes_attempts(user_id,question_id,slot_date,content_hash,rights_hash,attempt_token)"
                  " VALUES(?,?,?,?,?,?)",(983301,8001,'2026-10-24','h'*64,'r'*64,'g080-h-postcommit'))
        c.execute("UPDATE user_stats SET coins=?,xp=? WHERE user_id=?",(440,77,983301))
        c.execute("INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context)"
                  " VALUES(?,?,?,?,?)",(983301,8002,5,'2026-10-24T00:04:00','pitr_fixture:post'))
        c.commit()
    post_state=count_state(PORTS[PRIMARY])
    assert post_state=={"coins":440,"xp":77,"reviews":2,"migration_committed":True,"mistakes_attempts":1}
    with db.get_db() as c:
        try:upgrade(c,environ={APPROVAL:"1"});raise AssertionError("Non-idempotent reapply admitted")
        except RuntimeError as e:assert "already exists" in str(e).lower()
        c.rollback()
    step("AUTHORIZED_COMMIT_AND_REPEAT_FAIL_CLOSED",state=post_state)
    post,post_hash=backup("post_migration")
    logical_pre=restore_logical(pre,"g080h_logical_pre")
    logical_post=restore_logical(post,"g080h_logical_post")
    assert logical_pre==pre_state and logical_post==post_state
    step("TWO_LOGICAL_RESTORE_DATABASES_MATCH",pre=logical_pre,post=logical_post)
    # Force archive ALL WAL segments generated around restore point and post TX.
    with pg(PORTS[PRIMARY]) as c:
        with c.cursor() as cur:
            cur.execute("SELECT pg_switch_wal()")
        c.commit()
    count=ensure_archive(2)
    step("WAL_ARCHIVE_SEALED",wal_segments=count)
    # Copy actual physical backup into separate empty named restore volume.
    tool("exec","--user","root",PRIMARY,"sh","-c",
         "cp -a /backup/. /restore/ && chown -R postgres:postgres /restore",timeout=180)
    restoreconf=("restore_command = 'cp /walarchive/%f %p'\n"
                 "recovery_target_name = 'g080_h_pre_migration'\n"
                 "recovery_target_action = 'promote'\n"
                 "recovery_target_timeline = 'current'\n")
    tool("exec","--user","root","-i",PRIMARY,"sh","-c",
         "cat >> /restore/postgresql.auto.conf",input=restoreconf.encode())
    tool("exec","--user","root",PRIMARY,"touch","/restore/recovery.signal")
    tool("exec","--user","root",PRIMARY,"chown","postgres:postgres","/restore/recovery.signal",
         "/restore/postgresql.auto.conf")
    tool("run","-d","--name",RECOVERY,"--label",f"g080h.run={RUN}",
         "--publish","127.0.0.1::5432",
         "--mount",f"type=volume,source={VOLUMES['recoverdata']},target=/var/lib/postgresql/data",
         "--mount",f"type=volume,source={VOLUMES['walarchive']},target=/walarchive,readonly",
         IMAGE,"postgres","-c","archive_mode=off","-c","hot_standby=on")
    resources.append(("container",RECOVERY))
    PORTS[RECOVERY]=port_of(RECOVERY)
    wait_pg(PORTS[RECOVERY],seconds=95)
    deadline=time.monotonic()+70
    while True:
        with pg(PORTS[RECOVERY]) as c:
            in_recovery=scalar(c,"SELECT pg_is_in_recovery()")
        if not in_recovery:break
        assert time.monotonic()<deadline,"PITR recovery did not promote at named point"
        time.sleep(.75)
    pitr_state=count_state(PORTS[RECOVERY])
    assert pitr_state==pre_state,("PITR_WRONG_TARGET",pitr_state,pre_state)
    assert count_state(PORTS[PRIMARY])==post_state,("PRIMARY_CHANGED_AFTER_PITR")
    step("PHYSICAL_WAL_PITR_PROMOTED_PRE_MIGRATION",restored=pitr_state,primary_post=post_state)
    evidence={
       "schema":"G080_H_REAL_PG16_LOGICAL_PHYSICAL_PITR_V1",
       "source_worktree":str(ROOT),"source_sha":subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip(),"run":RUN,"db_image":IMAGE,
       "server_version_pg16":True,
       "production_db_access":False,"port_bind":"127.0.0.1 only",
       "pre_migration":pre_state,"post_migration":post_state,"pitr_at_named_restore_point":pitr_state,
       "logical_restored_pre":logical_pre,"logical_restored_post":logical_post,
       "pg_dump_custom_pre_sha256":pre_hash,"pg_dump_custom_post_sha256":post_hash,
       "physical_basebackup_performed":True,"WAL_archived_segments_min":count,
       "restore_point_lsn":restore_lsn,"pitr_promoted":True,
       "postcommit_backup_preserves_new_progress":True,
       "old_point_restore_excludes_post_cutover_changes":True,
       "zero_data_loss_claim":False,
       "formal_restore_authorized":False,
       "oracle_deploy":False,
       "cleanup_pending":True,
    }
    (OUT/"result.json").write_text(json.dumps(evidence,indent=2,ensure_ascii=False),encoding="utf-8")
    print("G080_H_REAL_POSTGRES16_PITR_PASSED",json.dumps({"pre":pre_state,"post":post_state,
          "pitr":pitr_state,"wal_archive_count":count}),flush=True)

try:
    run()
finally:
    for kind,name in reversed(resources):
        p=tool("rm","-f",name,check=False) if kind=="container" else tool("volume","rm",name,check=False)
        print("CLEANUP",kind,name,p.returncode,flush=True)
    with (OUT/"docker_command_audit.json").open("w",encoding="utf-8") as f:
        json.dump(records,f,indent=2,ensure_ascii=False)
    result=OUT/"result.json"
    if result.exists():
        data=json.loads(result.read_text(encoding="utf-8"))
        data["cleanup_pending"]=False
        data["owned_resources_cleaned"]=all(
           tool("container","inspect",name,check=False).returncode!=0
           if kind=="container" else tool("volume","inspect",name,check=False).returncode!=0
           for kind,name in resources)
        result.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")
        assert data["owned_resources_cleaned"],"Disposable Docker resources remain"
