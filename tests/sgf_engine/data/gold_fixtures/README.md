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
9. Do not use docs/testing YAML as active test data.
10. The next commit should add pytest coverage for READY fixtures only.
