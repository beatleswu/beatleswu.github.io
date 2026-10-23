# G MASTER G077 B2 Rating forfeit | isolated native validation
Date: 2026-10-23. Base source B2 6214f7b5f4f69c979da44d4ea989d3b03b6863f6.

## New candidate scope
- Implements trusted server-owned timeout, give_up, partial timeout and late move settlement without forging SGF moves, using extracted original Rating Elo/placement effects under same caller DB transaction and replay nonce. Independent per-mode Rating flag; OFF legacy behavior preserved. New candidate changes are isolated to Rating branch; no official Product merger, Oracle or production data writes.
- The original global Rating start/answer/result and session gates are complex; tested in a fixture with AST-extracted original writer and disposable SQLite. It is NOT the exact official production app.py/PG transaction acceptance yet.

## G MASTER actual Windows execution
- `python -B -m pytest -q -p no:cacheprovider tests/test_g077_rating_forfeit_writer.py tests/test_g076_rating_steps.py` => 63 PASS + 12 subtests PASS, 0 FAIL, native Exit0. JUnit G077_B_RATING_NATIVE_JUNIT.xml, log G077_B_RATING_NATIVE.log.
- True Chrome WGo exact rating_test.html + Flask/SQLite original Rating source seam on 127.0.0.1:15083 => 61 PASS, 0 FAIL, Exit0, in G077_B_CHROME_CLEAN_FINAL.log. Verified normal move, refresh, 2 accounts, all 4 forfeit kinds, no fabricated move, one original Elo settlement/nonce, lost response replay, and per-mode HOLD after test.
- First Chrome attempts were blocked by stale Flask child servers loading old source or cumulative receipt count in reused disposable fixture. Verified actual process command-lines for only g076_rating_fixture_server.py and stopped them, started new Python fixture, changed assertion to delta of THIS attempt, not absolute historical table count. Captured original FAILs separately; removed all temporary browser diagnostic output from final JS. Clean rerun 61 PASS.
- B2 Node client contract 24 PASS previously and candidate scripts syntactically valid. Original B2 52 Python PASS historical preserved.

## Strict release HOLD
Official Product app.py cross-writes with Grimoire shared routes and B1 have NOT been combined or independently PG tested in this branch; first integration requires one owner controlled local integrator. Full-mode chrome/PG Safari and ARM64 build remain HOLD. No GitHub push/merge, Oracle deploy or player/corpus writes.