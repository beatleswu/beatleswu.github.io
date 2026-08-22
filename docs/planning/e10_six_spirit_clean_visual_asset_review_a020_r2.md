# E10 Six-Spirit Clean Visual Asset Review — A020-R2

## Authority and scope

- Source head: `b16362b232c0a5d4a41b1b72a09783b8d29b0cf3`
- Visual authority: `docs/review/a020r1/A020R1_OWNER_REFERENCE_PRIMARY.jpg`
- Source authority: Owner-selected A020-R1 reference image
- Operation: deterministic crop and alpha-matte cleanup only
- Generation/redesign: none
- Runtime/catalog promotion: none

The nine forms remain exactly the Owner-selected identities and stages:

- #4 Starpath Antlerling — Stage I / II / III
- #5 阿肥 / Fatty — Stage I / II / III
- #6 Obsidian Bastion — Stage I / II / III

The clean form files are review/evidence assets under
`docs/review/a020r2/clean_forms/`. They are not runtime assets.

## Cleanup contract

Each form is extracted from its corresponding region of the approved source
image. The deterministic matte removes the source poster's explanatory copy,
stage separators, decorative frame corners, and unrelated neighboring forms.
The source character pixels, pose, palette, markings, effects, and final-form
silhouettes are not redrawn or regenerated. Alpha transparency is used outside
the presentation matte; the source-native dark celestial/Go-board atmosphere
inside the form region is retained where it belongs to the approved design.

## Review packet

1. `A020R2_CLEAN_THREE_STAGE_MASTER_SHEET.png`
2. `A020R2_STARPATH_CLEAN_EVOLUTION_STRIP.png`
3. `A020R2_FATTY_CLEAN_EVOLUTION_STRIP.png`
4. `A020R2_OBSIDIAN_CLEAN_EVOLUTION_STRIP.png`
5. `A020R2_CLEAN_STAGE_III_FINAL_TRIO.png`
6. `A020R2_CLEAN_SIX_SPIRIT_FOLLOWER_SCALE.png`

The final trio uses the three clean Stage III extracts on a shared baseline.
The follower-scale view uses the three existing runtime Spirit sprites plus
the three clean Stage III extracts; the Hero marker remains visually primary.

## Explicit non-changes

- Existing three Spirits were not redrawn or renamed.
- No new Spirit runtime IDs were added.
- No runtime catalog, route, `app.py`, gameplay, payment, database, or
  production files were changed.
- No canonical runtime asset directory was changed.
