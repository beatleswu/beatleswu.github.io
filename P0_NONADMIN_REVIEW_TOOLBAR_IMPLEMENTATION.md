# P0 non-admin review toolbar implementation

## Exact change

`sgf_report_widget.js` only:

1. `quarantineAdminControls(host)` moves the inline review bar/panel and
   admin workbench controls into inert templates before the host is appended.
2. `loadAdminCapabilities()` requires strict `logged_in === true` and
   `is_admin === true`, then requires admin bootstrap security evidence.
3. `mountAdminControls(host)` clones the templates only after that authority
   gate and `bindAdminControls(host)` attaches the existing handlers.
4. The existing admin action handlers and server endpoints are unchanged.

This preserves the prior admin layout and the player report control while
removing privileged controls from the non-admin live DOM entirely. No
`app.py`, DB, schema, D1, Map Battle, SRS, Zone4 content, Zone5, reward, or
progression file changed.

## Candidate identity

- Branch: `codex/p0-nonadmin-review-toolbar-bounded-hotfix-001`
- Implementation commit: `c2023160497f5502fb361c997117c559c0ff9bb7`
- Implementation tree: `bdc0fc2291c03cf666f757bd7dd8c59f264f2ccc`
- Changed files at this checkpoint: `sgf_report_widget.js`,
  `tests/test_p0_nonadmin_review_toolbar.py`,
  `tests/e2e/run_p0_nonadmin_review_toolbar_contract.mjs`
- Product semantic change outside visibility: `NO`

