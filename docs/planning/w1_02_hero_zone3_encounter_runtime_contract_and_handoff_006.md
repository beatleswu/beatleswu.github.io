# W1-02 Zone 3 encounter runtime contract and handoff

This handoff is a presentation contract for the future final Journey
integration. The machine-readable source is
`w1_02_hero_zone3_encounter_runtime_contract_and_handoff_006.json`.

The contract preserves the current canonical authority:

- 13 existing Zone 3 Normal Monsters: `M022`–`M033` plus `M060`.
- Zero Elites; no missing Elite is created or inferred.
- Battlefield Boss `legacy_bf_03_boss`, using
  `/assets/monsters/orc_shield_chibi.png`.
- Lord `goblin_centurion`, with six distinct Owner-approved presentation
  slots from `zone3_runtime_asset_bindings.py`.

`BATTLEFIELD_BOSS != LORD` is an invariant. Lord presentation assets are
never ordinary Monster fallbacks, and presentation availability does not
create combat, reward, progression, acquisition, or equipment authority.
The manifest records the existing asset paths and state conditions only; it
does not modify the Journey controller or perform final runtime binding.

Centurion remains a middle-aged, seasoned, restrained protector. Grik remains
a young, slim, tired, guarded civilian/scout. This task adds no dialogue.

## Boundaries

No `app.py`, Journey controller, WORLD FX, audio, BGM, voice, gameplay,
database, Production, or shared-shell changes are part of this handoff.
