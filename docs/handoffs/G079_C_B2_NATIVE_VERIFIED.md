# G079 C | B2 Rating real Product candidate | 2026-10-23

Base G079 source: c6c2194dee99ad64522265bdc679d7256693358a (derived from f3c1361c). This commit stores implementation only within isolated worktree D:\go-odyssey-g079-c-b2. Formal GitHub merge, production data writes and deployment are not authorized.

## Verified real Windows native receipts
- Original unit/regression and new Rating candidate: 145 PASS +12 subtests PASS /0 FAIL in D:\g079-artifacts\c\native.log.
- Standalone native PostgreSQL 16 on exact disposable container: 16 PASS, 0 FAIL, D:\g079-artifacts\c\pg_live.log.
- Real Product app.py + isolated PostgreSQL schema: 9 PASS /0 FAIL in D:\g079-artifacts\c\realapp_pg.log, tests/test_g079_rating_real_app_pg.py.
- Headless Chrome+WGo+real Flask and native PG (loopback fixture only): 111 browser assertions PASS, Node exit0, D:\g079-artifacts\c\chrome.log. This includes old OFF behavior and protected ON paths, full manual/placement session and legacy claim gating. Isolated database dropped after test.
- Full 590-file regression on this WIP: 8015 PASS, 252 FAIL, 334 ERR, 375 SKIP, 2 XFAIL +2544 subtests PASS, D:\g079-artifacts\c\full.log. Baseline f3c1: 7963 PASS, 227 FAIL, 334 ERR, 345 SKIP; 561 known failing IDs. Comparison found 25 IDs absent baseline, mostly source-pinning/protected-scope legacy static governance tests; one static release tooling timeout. These must be classified; do not assert full clean. No production DB used.

## Release limitations
- B2 is not yet merged with B1 and cross-mode fixes into one canonical SHA. Full same-SHA Flask/PG/Chrome, ARM64 real Build, restore/rollback and Safari remain HOLD.
- No signing-host work required (Owner cancelled extra signing gate). Preserve source identity and exact single writer per shared Product app.py.
