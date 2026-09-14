import hashlib
import re
import sqlite3
from pathlib import Path

import pytest

import admin_question_center as center
import sgf_admin_workbench as workbench


ROOT = Path(__file__).resolve().parents[1]


def _records():
    return [
        {
            "id": 101,
            "topic": "活棋",
            "level": "初級",
            "source": "test-corpus",
            "content": "(;SZ[19]PL[B];AB[dd])",
            "accepted_moves": [{"x": 3, "y": 3}],
        },
        {
            "id": 202,
            "topic": "死活",
            "level": "中級",
            "source": "test-corpus",
            "content": "(;SZ[19]PL[W];AW[pp])",
            "accepted_moves": [{"x": 15, "y": 15}],
        },
        {
            "id": 202,
            "topic": "死活（舊版本）",
            "level": "中級",
            "source": "legacy-corpus",
            "content": "(;SZ[19]PL[W];AW[qq])",
            "accepted_moves": [{"x": 16, "y": 16}],
        },
    ]


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE question_problem_reports (
            id INTEGER PRIMARY KEY, question_id INTEGER NOT NULL,
            reason_code TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'open', admin_note TEXT,
            created_at TEXT NOT NULL, reviewed_at TEXT, reviewed_by INTEGER
        );
        CREATE TABLE question_alternative_reports (
            id INTEGER PRIMARY KEY, question_id INTEGER NOT NULL,
            wrong_move_x INTEGER NOT NULL, wrong_move_y INTEGER NOT NULL,
            note TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'open',
            admin_note TEXT, created_at TEXT NOT NULL, reviewed_at TEXT,
            reviewed_by INTEGER
        );
        CREATE TABLE corpus_review_queue (
            id INTEGER PRIMARY KEY, source_type TEXT NOT NULL, source_ref INTEGER,
            record_index INTEGER NOT NULL, legacy_question_id INTEGER NOT NULL,
            content_sha256 TEXT, reason TEXT NOT NULL, status TEXT NOT NULL,
            resolution_action TEXT, admin_note TEXT, created_at TEXT NOT NULL,
            reviewed_at TEXT
        );
        INSERT INTO question_problem_reports
          (id, question_id, reason_code, note, status, created_at)
          VALUES (1, 101, 'QUESTION_CONTENT_PROBLEM', '題面需要確認', 'open', '2026-09-13');
        INSERT INTO question_alternative_reports
          (id, question_id, wrong_move_x, wrong_move_y, note, status, created_at)
          VALUES (2, 101, 4, 4, '可能有另一個正解', 'open', '2026-09-13');
        INSERT INTO corpus_review_queue
          (id, source_type, source_ref, record_index, legacy_question_id,
           content_sha256, reason, status, created_at)
          VALUES (3, 'manual_flag', 1, 0, 101, 'not-used', '待確認', 'pending', '2026-09-13');
        """
    )
    return conn


class _ConnectionContext:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, _value, _traceback):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        return False


class _CountingConnection:
    def __init__(self, conn):
        self._conn = conn
        self.statements = []

    def execute(self, statement, parameters=()):
        self.statements.append(str(statement))
        return self._conn.execute(statement, parameters)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _review_source(records):
    digest = hashlib.sha256(records[0]["content"].encode("utf-8")).hexdigest()
    return (
        {
            "duplicate_group_count": 1,
            "source_record_count": 3,
            "groups": [
                {
                    "review_group_key": "dup-101",
                    "group_size": 2,
                    "priority_tier": "P1",
                    "linked_records": [
                        {
                            "legacy_question_id": 101,
                            "audit_locator": {"record_index": 0, "content_sha256": digest},
                        },
                        {"legacy_question_id": 202},
                    ],
                }
            ],
        },
        {"sha256": "evidence-sha"},
    )


def test_identity_adapter_is_exact_and_fails_closed_for_ambiguous_or_stale_rows():
    records = _records()
    assert center._identity(records, 101)["status"] == "EXACT"
    assert center._identity(records, 202)["status"] == "AMBIGUOUS"
    assert center._identity(records, 202, record_index=1)["status"] == "EXACT"
    assert center._identity(records, 202, record_index=99)["status"] == "STALE"
    assert center._identity(records, 101, expected_content_sha256="0" * 64)["status"] == "STALE"


def test_center_projects_a_to_f_without_creating_a_new_write_authority():
    records = _records()
    conn = _db()
    workbench.ensure_sgf_workbench_tables(conn)
    conn.execute(
        """
        INSERT INTO sgf_workbench_review_items
          (group_key, question_id, record_index, issue_type, position_identity,
           source_types_json, first_report_at, last_report_at, updated_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("c-101", 101, 0, "SYSTEM_ANSWER_INCORRECT", "c-position-101",
         '["ADMIN_PLAY"]', "2026-09-13", "2026-09-13", "2026-09-13", "2026-09-13"),
    )
    conn.commit()
    before = conn.execute("SELECT COUNT(*) FROM corpus_review_queue").fetchone()[0]
    payload = center.build_center_bootstrap(
        conn=conn,
        records=records,
        review_source_loader=lambda: _review_source(records),
    )
    after = conn.execute("SELECT COUNT(*) FROM corpus_review_queue").fetchone()[0]

    assert payload["route"] == "/admin/questions"
    assert len(payload["sections"]["duplicates"]) == 1
    assert len(payload["sections"]["reports"]) == 2
    assert {item["technical"]["system"] for item in payload["sections"]["reports"]} == {"D", "E"}
    assert {item["technical"]["system"] for item in payload["sections"]["pending"]} == {"C", "F"}
    assert {item["technical"]["system"] for item in payload["sections"]["duplicates"]} == {"A"}
    assert payload["sections"]["browse"][0]["technical"]["system"] == "B"
    assert payload["metadata"]["system_f_new_writes"] is False
    assert payload["metadata"]["canonical_question_mutation"] is False
    assert before == after
    assert "INSERT INTO corpus_review_queue" not in (ROOT / "admin_question_center.py").read_text(encoding="utf-8")


def test_history_projection_uses_bounded_bulk_reads_for_a_full_corpus():
    inner = _db()
    conn = _CountingConnection(inner)
    records = [
        {
            "id": index,
            "topic": "活棋",
            "level": "初級",
            "source": "test-corpus",
            "content": "(;SZ[19]PL[B];AB[dd])",
            "accepted_moves": [{"x": 3, "y": 3}],
        }
        for index in range(1, 1202)
    ]

    payload = center.build_center_bootstrap(
        conn=conn,
        records=records,
        review_source_loader=lambda: ({
            "duplicate_group_count": 0,
            "source_record_count": len(records),
            "groups": [],
        }, {"sha256": "evidence-sha"}),
        reviewer_id=42,
    )

    history_queries = [
        statement for statement in conn.statements
        if "FROM sgf_workbench_direct_versions" in statement
    ]
    # 1201 ids are fetched in 500-id chunks, rather than once per question.
    assert len(history_queries) == 3
    assert payload["sections"]["history"] == []


def test_bulk_history_read_preserves_per_question_order_and_limit():
    conn = _db()
    workbench.ensure_sgf_workbench_tables(conn)
    for index in range(55):
        conn.execute(
            """
            INSERT INTO sgf_workbench_direct_versions
              (question_id, record_index, predecessor_hash, new_hash,
               predecessor_version, new_version, operation_id, action_type,
               actor_id, old_record_json, new_record_json,
               validation_result_json, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                101, 0, "a" * 64, "b" * 64, f"v{index}", f"v{index + 1}",
                f"bulk-history-{index}", "EDIT_QUESTION", 42, "{}", "{}",
                "{}", "test", f"2026-09-14T00:00:{index:02d}",
            ),
        )
    conn.commit()

    direct = workbench.list_direct_versions(conn, question_id=101, limit=50)
    bulk = workbench.list_direct_versions_for_questions(
        conn, question_ids=[101, 101, 202], limit=50,
    )

    assert [row["id"] for row in bulk[101]] == [row["id"] for row in direct]
    assert len(bulk[101]) == 50
    assert bulk[202] == []


def test_admin_questions_repeated_initialization_keeps_public_surfaces_responsive(monkeypatch):
    application = pytest.importorskip("app")
    admin = application.app.test_client()
    public = application.app.test_client()
    with admin.session_transaction() as session:
        session["user_id"] = 42
        session["is_admin"] = True
    conn = _db()
    records = _records()
    monkeypatch.setattr(application, "get_db", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(application, "_load_questions", lambda: records)

    for _ in range(25):
        assert public.get("/").status_code == 200
        assert public.get("/healthz").status_code == 200
        assert public.get("/login").status_code == 200
        assert admin.get("/admin/questions").status_code == 200
        assert admin.get("/admin/questions.js").status_code == 200
        assert admin.get("/api/admin/questions/bootstrap").status_code == 200

    assert conn.in_transaction is False


def test_center_routes_are_admin_only_and_bootstrap_is_get_only(monkeypatch):
    application = pytest.importorskip("app")
    client = application.app.test_client()

    assert client.get("/admin/questions").status_code == 302
    assert client.get("/api/admin/questions/bootstrap").status_code == 401
    with client.session_transaction() as session:
        session["user_id"] = 42
        session["is_admin"] = False
    assert client.get("/admin/questions").status_code == 302
    assert client.get("/api/admin/questions/bootstrap").status_code == 403
    with client.session_transaction() as session:
        session["is_admin"] = True
    conn = _db()
    monkeypatch.setattr(application, "get_db", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(application, "_load_questions", lambda: _records())
    page = client.get("/admin/questions")
    script = client.get("/admin/questions.js")
    assert page.status_code == 200
    assert script.status_code == 200
    assert "題目管理中心" in page.get_data(as_text=True)
    bootstrap = client.get("/api/admin/questions/bootstrap")
    assert bootstrap.status_code == 200
    assert bootstrap.get_json()["metadata"]["direct_apply_enabled"] is False
    assert bootstrap.get_json()["metadata"]["real_question_surfaces"] == 7
    assert client.post("/api/admin/questions/bootstrap").status_code == 405

    rules = [rule for rule in application.app.url_map.iter_rules() if rule.rule == "/api/admin/questions/bootstrap"]
    assert len(rules) == 1
    assert rules[0].methods == {"GET", "HEAD", "OPTIONS"}


def test_center_and_inline_share_exact_deep_link_and_existing_correction_routes():
    widget = (ROOT / "sgf_report_widget.js").read_text(encoding="utf-8")
    center_js = (ROOT / "admin_questions.js").read_text(encoding="utf-8")
    page = (ROOT / "admin_questions.html").read_text(encoding="utf-8")
    assert "window.location.href = '/admin/questions?'" in widget
    assert "new URLSearchParams({ question_id: String(state.context.question_id) })" in widget
    assert "direct-context/" in center_js
    assert "selectExactDeepLink" in center_js
    assert "/api/admin/sgf-workbench/flag" in widget
    assert "/api/admin/sgf-workbench/items/" in widget
    assert "/api/admin/sgf-workbench/direct-apply" in widget
    assert "data-sgf-report-surface=\"admin_questions\"" in page
    assert re.search(r'<script src="/sgf_report_widget\.js(?:\?[^\"]*)?"', page)
    assert "system_f_new_writes" in (ROOT / "admin_question_center.py").read_text(encoding="utf-8")


def test_center_has_tablet_mobile_and_unsaved_change_contracts():
    page = (ROOT / "admin_questions.html").read_text(encoding="utf-8")
    widget = (ROOT / "sgf_report_widget.js").read_text(encoding="utf-8")
    assert "viewport-fit=cover" in page
    # iPad landscape (three-region app layout) vs. narrow/portrait (single-region) breakpoint.
    assert "@media(min-width:1024px)" in page
    assert "@media(max-width:1023px)" in page
    # Phone-width refinement within the narrow layout.
    assert "@media(max-width:640px)" in page
    assert "--tap:48px" in page
    assert "touch-action:none" in page
    assert "修改還沒儲存，要離開嗎？" in widget
    assert "data-sgf-report-surface=\"admin_questions\"" in page
    assert "[data-sgf-admin-tools]').hidden = true" in widget
