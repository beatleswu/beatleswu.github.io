# A021A — E10 Six-Spirit Canonical Runtime Asset Package

## Status and provenance

- Task: `A021A`
- Lane: `A`
- Start master: `2fa78d0d8be90da3c5a01571f8d455c2d2780635`
- Source authority: A020-R2 Owner-approved clean forms
- Runtime directory: `assets/pets`
- Operation: deterministic alpha cleanup, padding normalization, format conversion and manifesting
- Redesign/generation: none

The three existing Spirits remain on their current runtime asset authority:
`ink_drop_kelpie`, `whispering_void_kit`, and `star_shell_hatchling`. Their
stage paths are adapted from the current `app.py` and `hero.html` presentation
paths; no second copy or replacement asset set is created.

The nine new forms are promoted from the nine A020-R2 clean form PNGs to
512×512 RGBA lossless WebP files under the established `assets/pets` directory.
The visible character pixels are not redrawn. Fully transparent RGB values are
cleared during packaging so the source checkerboard cannot appear as a baked
matte in a decoder or review tool.

## Canonical IDs and manifest

The new presentation IDs are:

- `starpath_antlerling` — Starpath Antlerling — `EXPLORATION`
- `fatty` — 阿肥 / Fatty — `PRECISION`
- `obsidian_bastion` — Obsidian Bastion — `SUPPORT`

No D008 identity/catalog authority was present on the start master, and no
parallel identity authority was created here. If D008 later establishes a
conflicting ID, the asset manifest must stop for explicit reconciliation rather
than silently creating aliases.

Machine-readable output:
[`e10_six_spirit_canonical_runtime_asset_manifest_a021a.json`](e10_six_spirit_canonical_runtime_asset_manifest_a021a.json)

The manifest includes all six Spirits, three stages per Spirit, the Hero and
World Map presentation references, an 18-record SHA-256 asset manifest, source
provenance for the nine new forms, and same-Spirit Stage-I fail-closed fallback
metadata. It is presentation metadata only; it is not ownership, unlock,
active-Spirit, evolution, combat, reward, or catalog authority.

## QA evidence

- [`A021A_NINE_FORM_VISUAL_QA.png`](../review/a021a/A021A_NINE_FORM_VISUAL_QA.png)
  shows all nine new runtime forms in a 3×3 Stage I/II/III progression sheet.
- [`A021A_SIX_SPIRIT_FOLLOWER_SCALE_QA.png`](../review/a021a/A021A_SIX_SPIRIT_FOLLOWER_SCALE_QA.png)
  compares the existing three with the new Stage-III trio at follower scale.

The QA sheets are review evidence only and are not referenced as runtime
assets. New and existing stage assets decode successfully, have non-zero
dimensions, and preserve alpha. The new nine use a shared 512×512 canvas with
consistent baseline/padding so they are suitable for Hero portraits and small
World Map followers across desktop, iPad landscape, iPad portrait, and mobile.

## Fail-closed and ownership boundaries

If a Stage-II or Stage-III presentation asset is unavailable, the manifest
allows only the same Spirit's Stage-I presentation asset as a safe visual
fallback. It cannot change Spirit identity, ownership, active selection, or
stage authority, and it must not trigger infinite retry. Consumer/runtime
integration remains responsible for the safe empty/unavailable state.

No `app.py`, route, runtime catalog, ownership, unlock, feed/train, evolution
authority, combat, Monster, payment, database, or Production file is changed
by this package. `sw.js` is unchanged; the existing `assets/pets` static
directory is already a governed delivery location, while release/deploy
activation remains outside Lane A.

## Acceptance summary

| Check | Result |
| --- | --- |
| New runtime forms | 9/9 |
| Canonical Spirit records | 6/6 |
| Existing three duplicated | No |
| Transparent alpha / decode | Pass |
| Baked checkerboard / card frame / text | 0 / 0 / 0 |
| Rejected A020 identity runtime references | 0 |
| Spirit state authority changed | No |
| Combat runtime changed | No |
| Monster files changed | 0 |
| Service worker changed | No |
| Runtime asset references review screenshot | No |
