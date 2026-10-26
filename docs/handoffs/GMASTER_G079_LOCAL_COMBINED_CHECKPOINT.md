# G079 G MASTER | Combined Product checkpoint 2026-10-23

Source base: G079 B containment commits c203bef61 and 951afad81; A atomic Mistakes f80f3b9dd729762bcd7b400de4931f079d8b556b; C Rating predecessor c6c2194dee99ad64522265bdc679d7256693358a and final B2 6f587a8ad2f6ddd8fd81c5a7d4433ed27acb6959, in D:\go-odyssey-g079-integration.

## Proven integration recovery
A and C have predecessor WIP commits not present in f3c1 base. Picking only final A omitted _review_learning_in_transaction. G MASTER compared top-level AST with A checkout and restored precisely missing _review_learning_in_transaction and replacement _srs_review_operation, with invariant asserting C _rt_forfeit_on_connection AST unchanged. Current C rating service, B containment and registration survived.
Docker curated COPY explicitly includes g079_mistakes_services.py, g078_rating_integration.py and migration g079_mistakes_steps_v1.py; packaging never runs DDL. Cross-mode old source test now requires exact new trusted G079 services factory rather than stale services=None.

## Actual native test evidence
- Independent A Product original app.py + PostgreSQL 22 PASS; Chrome+Flask+PG original mistakes.html 27/27 checks (D:\g079-artifacts\a).
- Independent C Product app.py + PostgreSQL 9 PASS; Chrome+Flask+PG WGo Rating 111 checks (D:\g079-artifacts\c).
- COMBINED Product tree: A native app.py/PG 22 PASS/0 FAIL (D:\g079-artifacts\g079-integrated-a-pg-fixed.log and JUnit). C native app.py/PG 9 PASS/0 FAIL (g079-integrated-c-pg.log and JUnit); PG ephemeral DB removed, 0 remaining. Combined A+C unit 105 PASS/0 FAIL (g079-integrated-ac-unit.log).
- Docker curated image source closure and G077 manifest 35 PASS/0 FAIL in g079-integrated-image-source.log; NOT an ARM64 image Build.
- Cross mode 248 PASS/1 historical stale source assert pre-fix; mandatory rerun after clean final SHA.
- Historical baseline f3c1 full suite: 7963 PASS, 227 FAIL, 334 ERR, 345 SKIP +2544 subtests. Independent A/C full runs had additional old strict source-diff-scope freeze failures and need detailed triage, cannot be counted fully clean.

## Strict release HOLD
R5 lacks actual approved production corpus SHA, per-question UUID import receipts, member and lesson entitlements: keep OFF. B1 production migration schema not applied and is Owner-gated; mixed Map Battle + Mistakes reward concurrency needs explicit check. Full same-SHA browser/PG/iPad Safari, ARM64 Build, rollback with migrated empty PG, GO_MERGE and GO_DEPLOY remain NO-GO until separately evidenced/authorized. No production data changed.


## 2026-10-23 final G079 checkpoint
- Full ARM64 Docker build of Product SHA 70659e446892f37d2843054ba00d50d432db016a succeeded Exit0, platform linux/arm64, local image go-odyssey-app:g079-local-70659e44, digest/id sha256:4b184bf97e9f3893d0798fe7b72466bc539083b2fbd2baa18a648aa9ee02f3f0. Complete image build, not just --check.
- Hardened loopback rollback rehearsal G079 candidate -> known official production image b39b35481de43ee5de6f3dc70e215d2cf291c56b -> same candidate succeeded Exit0 at D:\g079-artifacts\rollback\g079arm-70659/result.txt; all 3 stages healthz=200, /login=200, /=200, route policy responses expected, zero error lines; isolated tmpfs PostgreSQL 16 pre-migrated seven SGF workbench tables (workbench_created 7), no remote/prod DB. Strict runner D:\g079-artifacts\rollback\run_rehearsal_strict.sh.
- Combined committed Product B1 app+PG 22 PASS, B2 app+PG 9 PASS, B1+B2 shared unit 105 PASS, final 6-mode B/D/E real Flask route matrix and source closure 277 PASS/0 FAIL in D:\g079-artifacts\g079-final-b-same-sha.log. Original G077 parity tests now compare original extracted _review_learning_in_transaction and preserve old Rating _rt/rt functions, separately 30 PASS+12 subtests/0 FAIL. Two test-file corrections are test-only and do not change Product runtime.
- IMPORTANT HOLD: full 590-file suite baseline already 561 failing IDs, A/C expanded suites show further frozen-scope/AST tests; not yet certified no true new regressions, mixed Map Battle + Mistakes reward writer user-lock concurrency unresolved, production B1 migration Owner-gated and not applied, Grimoire real corpus and entitlements absent (keep OFF), iPad Safari unverified, no Oracle deploy, no GitHub Push/Merge.
