# P0 non-admin review toolbar root cause

The defect predates the current D1/global and Adventure forward-fix work. The
fresh pre-fix public widget hash was
`cea1d1ee034de49d51c04307173a4df700a5c07b1fc928e75663cb3d1d09c0a7`, equal to
the canonical `ba31` widget bytes.

In the user's authenticated `test01` Chrome tab, read-only DOM inspection
found:

```text
surface=main_practice
inlineReviewCount=1
hidden=true
display=flex
adminControls=6
text=快速檢查 ✓ 沒問題 ✎ 改答案 ✎ 改題目 ＋ 補正解 ⏭ 稍後
```

The server did not authorize the controls: `test01` is `users.id=991111,
is_admin=0`, and all privileged endpoint probes reject ordinary non-admin
sessions. The problem was that `ensureHost()` inserted the full privileged
markup into the live document before asynchronous capability resolution and
relied on a mutable `hidden` flag in `renderInlineReview()`. That allowed
privileged controls to exist in the DOM and made the result vulnerable to
first-paint, stale-document, or browser-state visibility leakage.

The bounded fix is therefore not CSS-only: privileged markup is quarantined in
inert `<template>` content at host construction and is mounted only after both
the authoritative `/api/auth/me` response (`logged_in === true` and
`is_admin === true`) and the admin bootstrap security object succeed.

Normal `回報這題` remains available to players. Answer submission,
Adventure progression, Map Battle settlement, SRS, D1, and server
authorization are unchanged.
