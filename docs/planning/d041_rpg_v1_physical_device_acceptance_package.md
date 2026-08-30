# D041 RPG V1 Physical-Device Acceptance Package

Status: preparation only. This package does not claim physical-device acceptance.

## Gate and authority

Run this package only after B056 reports:

```text
READY_FOR_RPG_V1_RELEASE_CANDIDATE_RECHECK=YES
```

Use the B056-approved release-candidate URL and record the exact source SHA and
static-generation identity supplied with that build. Do not use browser state,
client-selected zones, or local storage as progression or ownership authority.
Do not edit a database, seed data manually, or use a Production URL without a
separate Owner authorization.

The single automated Owner acceptance authority is:

```text
tests/e2e/run_e10_owner_ipad_acceptance_hotfix_002.mjs
```

From a checkout with the declared E2E dependency available, run:

```powershell
$env:E10_PLAYWRIGHT_CORE='D:\go-website\node_modules\playwright-core'
node tests/e2e/run_e10_owner_ipad_acceptance_hotfix_002.mjs
```

The historical `run_e10_lord_trial_owner_acceptance_regression.mjs` path is a
deprecated compatibility alias. It delegates to the current runner and must
not be used as a separate release gate.

## Owner device procedure

Use one Owner-provided account and the release-candidate data/state prepared by
the release process. Do not change local storage, call private APIs, or alter
the database. Run the checklist on:

- iPad landscape;
- iPad portrait;
- iPhone/mobile portrait.

For each device, start from a fresh browser session, sign in, and open the
B056-approved release-candidate URL. Mark each item `PASS` or `FAIL`; `N/A` is
allowed only where the item is explicitly conditional below.

1. Login succeeds and the authenticated shell is shown.
2. Adventure entry succeeds.
3. The Adventure map renders with its zone cards and player marker.
4. A question can be opened and answered.
5. Correct-answer feedback completes its normal transition.
6. Incorrect-answer feedback completes its normal transition without freezing.
7. Hero opens and shows the authenticated avatar.
8. Hero shows the server-projected equipped item.
9. Equipment replacement updates the Hero projection.
10. Unequip removes the item projection without inventing a replacement.
11. Hero stats/presentation remain coherent after equipment changes.
12. Backpack shows server-owned items.
13. Backpack marks the server-equipped item correctly.
14. Reload keeps Backpack ownership and equipped state consistent with the server.
15. Spirit Collection shows the owned canonical Spirits.
16. The active Spirit is shown on the relevant Hero/Adventure surface.
17. Selecting an owned Spirit leaves at most one active Spirit.
18. Reload/login preserves the selected active Spirit.
19. Boss/Lord entry opens from the server-backed Adventure action.
20. The cinematic starts and completes its accepted lifecycle.
21. Continue/close controls are visible, reachable, and dismiss the presentation.
22. First-clear reward presentation appears after the authoritative completion.
23. Replay is available only where the server-backed completion state permits it.
24. Replay does not duplicate the first-clear reward.
25. Replay does not duplicate Spirit acquisition or presentation.
26. Reload after clear/replay preserves progression and ownership.
27. Orientation change between landscape and portrait does not lose state.
28. No horizontal overflow hides content or controls.
29. Every required CTA is enabled when its server-backed action is available.
30. No required image is broken or replaced by an unexplained blank.
31. Required CSS and JS load; no blank or frozen screen appears.
32. Equipment purchase, if exposed in the candidate, does not auto-equip the item.
33. Equipment acquisition does not auto-equip the item.
34. Shop remains disabled for this acceptance package.
35. Loadout remains disabled for this acceptance package.
36. If combat/stat numbers are visibly exposed, confirm baseline damage `80`,
    Wooden Sword `84`, and Iron Sword `90`; otherwise record `N/A` here and
    rely on the automated same-source proof, without fabricating numbers.

The final candidate adds the following seven E055 Zone 3 checks to the base
36-item package. Record them as items 37-43, for a final checklist count of
43:

37. Zone 3 entry opens the server-backed Goblin Cave journey.
38. The displayed Zone 3 normal-monster art matches the server-authored
    monster-art binding.
39. A correct Zone 3 answer completes the accepted answer lifecycle.
40. An incorrect Zone 3 answer completes the accepted failure lifecycle
    without freezing or granting a reward.
41. An ordinary Zone 3 encounter continues normally after its encounter
    flow completes.
42. An ordinary Zone 3 encounter does not falsely mark the zone clear.
43. Zone 3 progression and reward invariants remain server-authoritative:
    no client-selected state creates a clear, unlock, or duplicate reward.

The Owner must specifically exercise the accepted Adventure Spirit cases when
the release account/state permits them: Zone 4 → `starpath_antlerling`, Zone 6
→ `fatty`, and Zone 8 → `obsidian_bastion`. A non-eligible clear and a failed
Boss must show neither a Spirit grant nor an unlock presentation. An already
owned Spirit must remain idempotent.

## Allowed outcomes

Use exactly one outcome per device run:

- `OWNER_DEVICE_PASS`: all applicable checklist items pass and no unexplained
  failure remains.
- `OWNER_DEVICE_PARTIAL_PASS`: the tested flow is usable, but one or more
  explicitly identified applicable items remain unresolved; list every item.
- `OWNER_DEVICE_BLOCKED`: the release candidate cannot complete the required
  flow, the build/static identity is unavailable, B056 is not ready, or a
  critical failure prevents meaningful testing.

Browser emulation, automated runner success, and this prepared protocol are
supporting evidence only. They never set `PHYSICAL_DEVICE_PROOF=YES`.

## Evidence Owner must return

Copy this template once per physical device/orientation run. Do not include
serial numbers, account passwords, cookies, or other personally identifying
device identifiers.

```text
DEVICE=
OS_VERSION=
BROWSER=
ORIENTATION=
BUILD/SOURCE_SHA=
STATIC_GENERATION=
TIMESTAMP=

CHECKLIST_PASS_COUNT=
CHECKLIST_FAIL_COUNT=
OUTCOME=OWNER_DEVICE_PASS|OWNER_DEVICE_PARTIAL_PASS|OWNER_DEVICE_BLOCKED
FAILURES=
SCREENSHOTS_OR_RECORDING=
NOTES=
```

Attach screenshots or a recording for every failed item and for the key
unlock/replay/reload/orientation states. The Owner evidence is the first point
at which `PHYSICAL_DEVICE_PROOF` may be assessed; D041 itself leaves it `NO`.
