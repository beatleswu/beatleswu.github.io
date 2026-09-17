# P0 non-admin review toolbar tests

## Focused results

| Gate | Result |
|---|---:|
| Python toolbar/auth contract | 14 passed |
| Browser toolbar contract, Adventure/Practice × admin/non-admin | PASS, 4 scenarios |
| Existing SGF/workbench/direct-apply/security suite | 45 passed, 2 skipped |
| Existing answer-review auth/ordinary/CSRF selection | 2 passed, 22 deselected |
| Lane B Python forward-repair tests | 10 passed |
| Lane B browser contract | PASS |
| Map Battle/provider runtime contract | 16 passed |
| D1 configuration wiring | 8 passed, 1 existing skip |
| Zone4 004 Lord-state executable acceptance | 34 checks PASS |
| Zone4 005/003 compatibility executable acceptance | PASS |
| Static release tooling | 91 passed |
| Release source separation | 24 passed |
| Runtime dependency provenance | 41 passed |

The first release-source run on the intentionally dirty implementation
worktree was stopped by the release tool's required clean-worktree gate. After
the exact three implementation/test files were committed, the authoritative
clean-worktree run passed 24/24. This was an environment precondition, not a
Product failure.

The browser contract uses the actual `sgf_report_widget.js` runtime in a real
Chromium instance. Non-admin Adventure and Practice contexts have zero live
toolbar/action/admin-tool nodes and retain one normal report control. Admin
contexts mount five action buttons and the admin tools only after bootstrap.

No test was skipped, xfailed, deleted, or weakened by this candidate.

