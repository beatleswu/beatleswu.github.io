#!/usr/bin/env python3
"""Run the Owner Review Queue locally with isolated, disposable state.

This harness binds to 127.0.0.1 only, sets an in-memory-style QA secret before
the application import (so secret_key.txt is never read), and redirects a
local QA login endpoint into the real admin-protected review route.  It never
opens Production or canonical puzzle data.
"""

from __future__ import annotations

import argparse
from contextlib import AbstractContextManager
import os
from pathlib import Path
import sqlite3
import tempfile
import sys


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "review_data" / "sgf_answer_review_queue_v1.json"


sys.path.insert(0, str(ROOT))
class SQLiteRequestConnection(AbstractContextManager):
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.connection = None

    def __enter__(self):
        self.connection = sqlite3.connect(self.database_path, timeout=15)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        return self.connection

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()
        self.connection.close()
        return False


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    return parser.parse_args()


def main():
    args = parse_args()
    source = args.source.resolve()
    if not source.is_file():
        raise SystemExit(f"review source is missing: {source}")

    qa_directory = Path(tempfile.mkdtemp(prefix="sgf-answer-review-qa-"))
    database_path = qa_directory / "review-state.sqlite3"
    os.environ["SECRET_KEY"] = "local-sgf-answer-review-qa-only"
    os.environ["SITE_URL"] = f"http://127.0.0.1:{args.port}"
    os.environ["SGF_ANSWER_REVIEW_QUEUE_SOURCE_PATH"] = str(source)

    import app as site_app  # noqa: PLC0415 - environment must be set first
    from flask import redirect, session  # noqa: PLC0415
    from sgf_answer_review_queue import ensure_review_queue_tables  # noqa: PLC0415

    def get_qa_db():
        return SQLiteRequestConnection(database_path)

    with get_qa_db() as connection:
        connection.execute(
            """CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0
            )"""
        )
        connection.execute(
            "INSERT INTO users(id, username, is_admin) VALUES(1, 'owner-qa', 1)"
        )
        ensure_review_queue_tables(connection)

    site_app.get_db = get_qa_db

    def qa_owner_login():
        session.clear()
        session.permanent = True
        session["user_id"] = 1
        session["username"] = "owner-qa"
        session["nickname"] = "Owner QA"
        session["is_admin"] = True
        session["plan"] = "free"
        return redirect("/admin/sgf-answer-review")

    site_app.app.add_url_rule(
        "/__local_qa__/owner-login",
        endpoint="sgf_answer_review_local_qa_login",
        view_func=qa_owner_login,
    )

    print("SGF Answer Review Queue local QA")
    print(f"URL=http://127.0.0.1:{args.port}/__local_qa__/owner-login")
    print(f"STATE_DB={database_path}")
    print(f"REVIEW_SOURCE={source}")
    print("NETWORK_SCOPE=127.0.0.1_ONLY")
    print("PRODUCTION_CONTACT=NONE")
    site_app.app.run(
        host="127.0.0.1",
        port=args.port,
        debug=False,
        threaded=True,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()
