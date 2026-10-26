"""Additive, explicitly invoked migration. Never called by application startup.

The supplied connection/DSN belongs to the migration operator. No default DSN.
Use an isolated database for tests; production application is a separate gate.
"""
from pathlib import Path


def upgrade(conn, *, environ):
    if environ.get('G076_PRACTICE_STEPS_MIGRATION_APPROVED') != '1':
        raise RuntimeError('explicit Practice migration approval required')
    # Migration tracking is operator-owned. Intentionally fails on reapplication
    # instead of silently admitting a partially incompatible existing schema.
    source = Path(__file__).with_name('g076_nonmap_steps_PROPOSED.sql').read_text()
    source = '\n'.join(line for line in source.splitlines() if not line.lstrip().startswith('--'))
    for statement in source.split(';'):
        if statement.strip():
            conn.execute(statement)
    conn.execute('''CREATE TABLE g076_practice_attempts (
        user_id BIGINT NOT NULL,
        question_id BIGINT NOT NULL,
        slot_date TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        attempt_token TEXT NOT NULL,
        PRIMARY KEY (user_id, question_id, slot_date)
    )''')
