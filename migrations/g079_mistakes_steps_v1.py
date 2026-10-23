"""G079 Mistakes server-step schema. Explicitly invoked; never called at startup.

The connection belongs to the migration operator (no default DSN). It adds:
* g076_nonmap_sessions/events when absent (Practice migration not yet run), with
  the flow constraint already admitting 'mistakes';
* when they exist (PostgreSQL), the flow CHECK is replaced to admit 'mistakes';
* g076_mistakes_attempts (one Product-issued attempt per user/question/day).
Re-application fails instead of silently admitting an unknown existing schema.
Production application is a separate owner gate.
"""
from pathlib import Path

APPROVAL = 'G079_MISTAKES_STEPS_MIGRATION_APPROVED'
FLOW_CHECK = "CHECK (flow IN ('practice','daily','mistakes'))"


def _sqlite(conn):
    raw = getattr(conn, '_conn', conn)
    return raw.__class__.__module__.startswith('sqlite3')


def _table_exists(conn, name):
    if _sqlite(conn):
        sql = "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?"
    else:
        sql = ("SELECT 1 FROM information_schema.tables "
               "WHERE table_schema=current_schema() AND table_name=?")
    return conn.execute(sql, (name,)).fetchone() is not None


def upgrade(conn, *, environ):
    if environ.get(APPROVAL) != '1':
        raise RuntimeError('explicit Mistakes steps migration approval required')
    if _table_exists(conn, 'g076_mistakes_attempts'):
        raise RuntimeError('g076_mistakes_attempts already exists; reconcile explicitly')
    if not _table_exists(conn, 'g076_nonmap_sessions'):
        source = Path(__file__).with_name('g076_nonmap_steps_PROPOSED.sql').read_text()
        source = '\n'.join(line for line in source.splitlines()
                           if not line.lstrip().startswith('--'))
        source = source.replace("CHECK (flow IN ('practice','daily'))", FLOW_CHECK)
        if FLOW_CHECK not in source:
            raise RuntimeError('unexpected nonmap session DDL')
        for statement in source.split(';'):
            if statement.strip():
                conn.execute(statement)
    elif _sqlite(conn):
        raise RuntimeError('SQLite cannot replace the existing flow constraint')
    else:
        conn.execute('ALTER TABLE g076_nonmap_sessions '
                     'DROP CONSTRAINT IF EXISTS g076_nonmap_sessions_flow_check')
        conn.execute('ALTER TABLE g076_nonmap_sessions ADD CONSTRAINT '
                     'g076_nonmap_sessions_flow_check ' + FLOW_CHECK)
    conn.execute('''CREATE TABLE g076_mistakes_attempts (
        user_id BIGINT NOT NULL,
        question_id BIGINT NOT NULL,
        slot_date TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        rights_hash TEXT NOT NULL,
        attempt_token TEXT NOT NULL,
        PRIMARY KEY (user_id, question_id, slot_date)
    )''')
