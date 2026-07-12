# RELEASE-FIX-B — E9 Missing-Key Fallback Hardening

```
Sprint: RELEASE-FIX-B / E9-I18N-FALLBACK
Branch: feature/release-fix-b-e9-i18n-fallback
Base: master @ c7c719e7d297a95384da7dc8ce81eeba55965273
Positioning: preventive hardening -- not incident recovery, not an E9
rollout, not E9.1C. e9Shell stays false in production after this Sprint.
```

## Confirmed defect

`i18n.js`'s `I18n.t(key)` returns the key itself when the key is missing
from the dictionary:

```js
function t(key) {
    const entry = dict[key];
    if (!entry) return key;
    ...
}
```

Three E9 components each define a local fallback wrapper of the same
defective shape:

```js
function t(key, fallback) {
  if (window.I18n && typeof window.I18n.t === 'function') {
    var val = window.I18n.t(key);
    return val || fallback;
  }
  return fallback;
}
```

Because a missing key returns the key string itself (truthy), `val ||
fallback` never reaches `fallback` -- a missing key renders the raw
dictionary key (e.g. `e9.top_hud.error`) instead of the intended fallback
text.

## Discovery Gate — full call-site inventory

Searched: `js/e9/**/*.js`, `components/adventure/**/*.html`, `index.html`.

| File | Helper / call site | Current behavior | Missing-key behavior (before fix) | Needs change? |
|---|---|---|---|---|
| `js/e9/top_hud.js:29-35` | local `t(key, fallback)` — 5 call sites (lines 49, 56, 58, 64, 82) | `window.I18n.t(key) \|\| fallback` | Renders raw key (e.g. `e9.top_hud.error`) | **Yes** — replace with shared helper |
| `js/e9/right_cards.js:15-21` | local `t(key, fallback)` — 13 call sites (lines 36-107), incl. 2 with post-`.replace()` interpolation (`index.adv.summary`) | same pattern | same raw-key leak | **Yes** — replace with shared helper; preserve return-then-`.replace()` contract (fallback text keeps `{n}`/`{t}` placeholders) |
| `js/e9/world_stage.js:27-33` | local `t(key, fallback)` — 4 call sites (lines 52, 73, 106), incl. 1 with post-`.split(':')[0]` and 1 with post-`.replace()` | same pattern | same raw-key leak | **Yes** — replace with shared helper; preserve post-processing contract |
| `js/e9/shell.js:79` | direct `global.I18n.t('e9.shell.critical_error')`, no local wrapper at all | sets `aria-label` to whatever `I18n.t()` returns, no fallback | Raw key would be set as `aria-label` for a screen reader on the critical-recovery path (cosmetic best-effort, wrapped in try/catch, but still a raw-key leak into the accessibility tree) | **Yes** — same shared helper, with an explicit fallback string, even though this call site never had the `\|\| fallback` bug pattern |
| `js/e9/bottom_dock.js` | no `I18n` reference | n/a | n/a | No — out of scope, nothing to hardened |
| `js/e9/left_nav.js` | no `I18n` reference | n/a | n/a | No — out of scope |
| `js/e9/component_loader.js:79-80` | calls `global.I18n.apply()`, not `.t()` | full-document `data-i18n` rescan (existing, working contract) | n/a — `I18n.apply()` only touches elements still carrying `data-i18n`; not the defect class in scope | No — different mechanism, not a `t(key, fallback)` call site |
| `js/e9/adapters/{player_state,adventure_state,activity_state}.js` | no `I18n` reference | pure data normalization, zero UI text | n/a | No — must not be touched (adapters are out of scope per task boundary) |
| `components/adventure/*.html` (5 files) | `data-i18n="..."` attributes only | static markup, resolved by `I18n.apply()` at component-inject time | governed by the existing E9.1A2 "remove `data-i18n` after dynamic set" contract, unaffected by this defect | No — no JS call sites here |
| `index.html` (~200+ `I18n.t(...)` call sites, legacy Adventure Map / site-wide UI) | direct `I18n.t(key)` calls, no fallback wrapper, some with `.replace('{n}', ...)` chaining | same global `t()` semantics as always | legacy code has never wrapped these in a fallback helper — it treats `I18n.t()`'s own "return the key" behavior as its de facto worst case, and every legacy key is long-lived/stable | **No** — explicitly out of scope (Global i18n Boundary, task Section 9); not part of E9, not touched by this Sprint |
| `i18n.js`'s global `t(key)` | dictionary lookup + fallback-to-`key` | n/a | this IS the global missing-key semantic | **No** — must not be modified by default. If a global fix ever looked safer, the correct action is to STOP and report an impact analysis, not silently expand this PR. Not done in this Sprint. |

## Conclusion

Four call sites need hardening: `top_hud.js`, `right_cards.js`,
`world_stage.js` (the known `t(key, fallback)` defect), and `shell.js`
(a distinct call shape — no fallback wrapper at all — but the same class
of raw-key leak on a rarely-exercised accessibility path). All four will
delegate to one new shared helper. Everything else (adapters, legacy
`index.html`, the global `i18n.js` `t()` function, `data-i18n` static
markup, `component_loader.js`'s `I18n.apply()`) is out of scope and
unmodified.

## Shared helper design

New file `js/e9/i18n_fallback.js`, loaded once, right after
`component_loader.js` and before any component that calls it. Exposes
`global.E9.I18nFallback.t(key, fallback)`, following the existing E9
adapter module pattern (`(function (global) {...})(typeof window !==
'undefined' ? window : global)`, dual `window`/`module.exports`).

Semantics (distinguishing every case explicitly, per task Section 7.2):

| Input condition | Result |
|---|---|
| `window.I18n` missing, or `.t` not a function | `fallback` (I18n unavailable) |
| `I18n.t(key)` throws | `fallback` (safe — never an uncaught error) |
| `I18n.t(key)` returns `null`/`undefined`/`''` | `fallback` (empty result treated as missing) |
| `I18n.t(key)` returns the key itself (`=== key`) | `fallback` (this is the actual missing-key signal from `i18n.js`) |
| `I18n.t(key)` returns any other string, including `"0"` or a string that happens to equal `fallback` | that translated string, unchanged (valid data is never overridden) |

`I18n.t()` takes only a `key` argument (confirmed — no `params`/
interpolation argument exists in the real implementation; all
interpolation across the codebase, both legacy and E9, is done by the
*caller* via chained `.replace('{n}', value)` after `t()` returns). The
shared helper therefore does **not** invent a `params` argument — it
keeps the existing two-argument `(key, fallback)` shape every call site
already uses, and callers keep doing their own `.replace()` chaining on
the returned string exactly as before.
