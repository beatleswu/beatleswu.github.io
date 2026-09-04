# W2-04 Website UX navigation vertical slice

## Scope and boundary

Base: `1e967c5e7416d225a0bc137d66b9cfecc40ca660`

This slice closes a presentation-only mobile navigation gap. The existing
mobile rail exposed only Lobby, Guild, Scrolls, Record, and Hero. The shared
desktop navigation already had additional served destinations, but those
destinations were not consistently available from the fixed mobile entry
point. The rail now exposes every existing primary destination and remains
horizontal-scrollable on narrow screens.

No gameplay, progression, Shop, Loadout, payment, database, Zone3, or
onboarding authority is changed. The rail contains links only; it does not
fetch data or issue mutations.

## Surface and route inventory

| Product surface | Existing route | Mobile entry | Primary next action | Return/home |
| --- | --- | --- | --- | --- |
| Home / Lobby | `/` | Lobby | choose a guild or practice entry | brand / Lobby |
| Learn | `/curriculum` | Guild | accept a training quest | Lobby |
| World / Adventure | `/` authenticated adventure map | Lobby | select an available map node | Lobby |
| Community | `/community` | Tavern | open a community tab or profile | Lobby |
| Rewards | `/badges` (redirects to Hero badges) | Badges | inspect earned/available badges | Lobby |
| Equipment / Loadout | `/inventory` | Pack | inspect owned equipment | Lobby |
| Shop | `/shop` | Shop | view canonical catalog | Lobby |
| Review / record | `/mistakes`, `/stats` | Scrolls / Record | review mistakes or progress | Lobby |
| Rating / Arena | `/rating_test`, `/play` | Rating / Arena | start a rating test or match | Lobby |
| Premium presentation | `/upgrade` | Pass | inspect the existing offer | Lobby |

All twelve mobile destinations are existing Flask routes. `/badges` retains
its existing redirect behavior; this change does not alter that authority.

## Acceptance contract

- Mobile rail destinations contain no placeholder `#` links.
- Exactly one destination receives `aria-current="page"` when the path is a
  known destination.
- The rail has a localized accessible label and localized labels for `zh` and
  `en`, matching the current project locale model (`zh-TW` / `en-US` display
  contexts are represented by the existing `zh` / `en` runtime keys).
- Narrow layouts can scroll the rail horizontally without creating page-wide
  horizontal overflow.
- Each destination remains a native keyboard-focusable link with a visible
  `:focus-visible` outline.
- The existing primary CTA can transition to Guild and browser Back returns to
  Lobby.
- No API call, purchase, equip, reward, progression, or payment mutation is
  introduced by the navigation script.

## Ownership and protected lanes

`app.py` is unchanged. W2-02-owned onboarding files, W2-03-owned equipment
files, and W1-03/W1-05 Zone3 files are not modified. The only product source
change is `mobile-nav.js`; the remaining files are this lane's bounded
contract, fixture, and tests. The browser fixture maps existing route paths to
the fixture only for deterministic Chromium interaction testing and is not a
runtime route implementation.

## Verification

```text
pytest -q tests/test_w2_04_website_ux_navigation.py
node tests/e2e/run_w2_04_website_ux_navigation.mjs
```

The browser contract covers desktop, iPad landscape, iPad portrait, and
mobile portrait Chromium viewports, locale switching, pointer navigation,
keyboard focus, primary CTA transition, browser Back, and access to the
previously absent Shop destination. Physical-device acceptance is separate.
