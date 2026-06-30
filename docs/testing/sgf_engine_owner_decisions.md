# SGF Engine Owner Decisions

## OFF_TREE Logging DB Boundary Exception

Date: 2026-06-29

Decision:

1. OFF_TREE logging is required product behavior.
2. Current `sgf_engine/engine/engine.py::log_off_tree` directly depends on production `db.get_db`.
3. This is accepted temporarily as a documented boundary exception, not as the desired long-term architecture.
4. No additional `sgf_engine/` code may import `db.py`, `app.py`, Flask, routes, Redis, Socket.IO, or other production application modules.
5. Future cleanup should move OFF_TREE persistence to the application integration layer or use dependency injection via an `off_tree_logger` callback.
6. Unit tests may monkeypatch `log_off_tree` for isolation, but persistence behavior must be covered by a separate integration test.
7. This decision does not authorize further production dependencies inside `sgf_engine`.

Rationale:

The independent dependency-boundary review classified `log_off_tree` as needing owner decision because it performs a lazy `from db import get_db` import and writes unmatched moves through the production database helper. Product behavior requires OFF_TREE logging, so the current dependency is accepted only as a temporary, documented exception.
