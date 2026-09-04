# W2-04 secondary route recovery

## Chosen issue

`/premium/weekly` is an existing authenticated secondary route. At the
parent commit it loaded `site-nav.js` but had no non-hero `<header>` for the
shared script to replace, and it did not load the existing mobile navigation
rail. A user arriving at the weekly report therefore had no consistent
site-level Home/parent recovery action when the report had no next training
action or when they abandoned the page.

This is one affected route and one presentation-only UX issue class. The
route already exists in `app.py`; this slice does not add a route or alter
authentication, report APIs, training state, rewards, commerce, or gameplay.

## Bounded fix

`premium_weekly.html` now provides:

- an explicit localized recovery header with Home, Practice, and Hero
  fallback links;
- a localized language-switcher slot;
- a recovery header that the existing `site-nav.js` can safely replace with
  the shared desktop navigation;
- the existing `mobile-nav.js` rail, unchanged, for narrow layouts;
- reduced top spacing so the page does not reserve an empty nav gap twice.

The shared navigation remains the authority for its existing destinations;
the weekly page only supplies anchors. The fallback anchors are existing
routes and carry no mutation behavior.

## Acceptance evidence

The focused Python contract proves the issue existed at the exact parent
commit, the recovery shell uses existing routes, and the page includes the
shared rail. The standalone Chromium contract runs the actual page source in
an isolated mocked server across desktop, iPad landscape, iPad portrait, and
mobile portrait. It checks:

- Home and parent Pass transitions;
- shared/mobile destination integrity and no page-wide overflow;
- keyboard focus visibility and pointer navigation;
- zh-TW and en-US navigation labels;
- no misleading current-primary state on this secondary route.

Physical-device acceptance remains separate. This worktree does not access
Production and does not change `app.py`, Shop/Loadout, payment, database, or
Zone unlock authority.
