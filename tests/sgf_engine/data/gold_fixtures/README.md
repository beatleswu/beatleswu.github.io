# SGF Gold Fixtures

This directory contains test-only SGF gold fixture data.

The source package was owner-approved via:

D:\sgf-gold-fixture-source-input\OWNER_APPROVED_SOURCE_PACKAGE.txt

Original source folder:

C:\go-website\SGF題庫

Rules:

1. These files are test-only data.
2. Do not modify SGF semantics.
3. Do not use these files as production runtime data.
4. GF-001 and GF-005 share 163.sgf.
5. GF-008 / 186.sgf preserves original gb18030 bytes.
6. GF-002 owner truth uses no-skip-I lettering: W[of] is recorded as 白 O14 and B[ne] is recorded as 黑 N15.
7. Under standard skip-I board notation, the same GF-002 moves would be 白 P14 and 黑 O15.
8. GF-003, GF-004, GF-006, and GF-007 are excluded from this import batch.
9. GF-003 candidate note: 431.sgf is imported as test-only candidate fixture source data.
10. GF-003 remains CANDIDATE_REQUIRES_OVERRIDE.
11. Owner-approved equivalent candidate: B[sd] / 黑 T16.
12. Canonical answer: B[sf] / 黑 T14.
13. Without active override, B[sd] / 黑 T16 remains OFF_TREE.
14. This import does not modify puzzle_variation_overrides.json.
15. This import does not activate GF-003.
16. This import does not add GF-003 to READY behavior tests.
17. GF-003 test-only override validation can use a tmp_path override to map B[sd] / 黑 T16 to canonical B[sf] / 黑 T14.
18. This validates the override design only; it does not activate production runtime behavior.
19. Production puzzle_variation_overrides.json remains unchanged.
20. GF-003 remains CANDIDATE_REQUIRES_OVERRIDE and is not added to READY_IDS.
21. Do not use docs/testing YAML as active test data.
22. The next commit should add pytest coverage for READY fixtures only.
