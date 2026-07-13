# E9.1D2 Layout Summary

Base commit: `d464d5651006a8c3d60c65e44fa27e6b8209e1cf`

Artifacts:
- Baseline metrics: `docs/testing/e9_1d2/baseline/layout_metrics.json`
- Baseline screenshots: `docs/testing/e9_1d2/baseline/screenshots/`
- Implementation metrics: `docs/testing/e9_1d2/layout_metrics.json`
- Implementation screenshots: `docs/testing/e9_1d2/screenshots/`

Proven root causes:
- `#e9-adventure-shell` lived inside `#welcome-state`, but `#welcome-state` kept the legacy Adventure `grid` / `flex` contract while E9 was active.
- At desktop/tablet widths, E9 was treated as an anonymous legacy grid item, so the shell collapsed into the first column instead of owning the full Adventure region.
- At narrow mobile widths, E9 stayed in the legacy single-column flow after the visible hero / entry / map blocks, which pushed the shell far below the fold.
- The layout contract for `main`, `.practice`, `#main-left`, and `#welcome-state` still followed legacy focus-layout selectors with higher specificity than the original E9 CSS.

Key before/after checkpoints:

| Viewport | Before shell top | After shell top | Before shell width | After shell width | Before stage width | After stage width |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1366x768 | 66.00 | 66.00 | 320.70 | 1326.00 | 32.00 | 747.61 |
| 1024x768 | -257.36 | 72.00 | 243.70 | 980.00 | 243.70 | 980.00 |
| 640x960 | 739.59 | 72.00 | 596.00 | 596.00 | 596.00 | 596.00 |
| 320x568 | 532.59 | 66.00 | 276.00 | 276.00 | 276.00 | 276.00 |

Final responsive contract:
- Desktop (`>=1280px`): top HUD spans the shell; nav / stage / cards are three deliberate columns; world stage is the primary flexible column.
- Narrow desktop / tablet (`<=1279px`): nav + stage stay primary; right cards move into a full-width secondary row.
- Tablet / mobile stack (`<=1024px`): nav, stage, cards, then dock become a single vertical flow.
- Mobile (`<=767px`): dock stays in normal flow, not as an overlay; extra bottom padding keeps the last controls reachable without covering content.

Non-regression checks captured in `layout_metrics.json`:
- OFF state: `activeShell=legacy`, zero E9 fragment requests, zero E9 focusables.
- ON state: `activeShell=e9`, `legacyFocusables=0`, shell top stays inside the visible region, world stage width/height stay positive, no document-level horizontal overflow.
