# W1-C1 Zone 3 reference vertical-slice template

Status: `PASS_Z3_CONTENT_CANDIDATE_READY`

This is the frozen Zone 3 closure contract for the L2 World and Content lane. It is the acceptance baseline for Zone 4 and later zones. It records presentation and content integration without becoming an authority for combat correctness, progression, rewards, or unlocks.

## Canonical identity

- Zone: `3 / k16_20 / 哥布林洞穴 / Goblin Cave`
- Stage: `LV3`, level band `16–20`
- Learning books: `5哥布林洞穴`, `6哥布林巡邏隊`
- Theme: goblin families retreat deeper into the cave; Grik gives testimony; the natural board-wall and last door establish a trust test rather than a raid.
- Lord: `goblin_centurion / 哥布林百夫長 / Goblin Centurion`
- Battlefield Boss: `legacy_bf_03_boss`, retained as a distinct `BATTLEFIELD_BOSS` identity.

## Frozen twelve-part contract

1. **Environment** — The player-facing Zone 3 map landmark is rebound to `/assets/e10/art/zone3/environment/zone3_map_landmark.webp`. The approved ten-shot package is the player-facing cinematic background; the environment master remains a support asset and does not carry state.
2. **Monster roster** — The server-owned Normal roster is exactly `M022–M033` plus `M060` (13 identities). Twelve use the existing canonical `/art/monsters` files; `M022` keeps its protected legacy runtime anchor. No Monster art is created or regenerated.
3. **Encounter profiles** — `e055.zone3.normal.v1` provides the explicit Normal profile mapping and existing Map Battle reachability. There are no Zone 3 Elites in this contract. Drop/reward references remain existing settlement references.
4. **Story/NPC** — The five canonical Z3 beats and the ten-shot sequence preserve Grik as a player-visible non-combat story actor. No unsupported Zone 3 World NPC registry record is invented.
5. **Cinematic** — The owner-approved ten-shot package is bound to `FIRST_ENTRY` (01–05), `BOSS_READY` (06–07), and `POST_CLEAR` (08–10). Text-safe fallback is allowed only for actual manifest/image failure and has no gameplay authority.
6. **Audio** — The current E10 package is retained and runtime-bound by the existing presentation bridge: 5 ambience, 3 BGM, 7 event SFX, 1 transition, and 97 dialogue files per locale. Owner audio lock and perceptual acceptance remain separate gates.
7. **Learning binding** — The two canonical books feed the existing server-backed question/answer route. W1-D1 semantics ruling and later W1-A2 implementation remain explicit dependencies; this contract changes no correctness semantics.
8. **Drops/rewards** — Normal encounters reference `drop_legacy_goblin` and `reward_battlefield_legacy`; Lord settlement is consumed by `BattlefieldBossRewardConsumer`. W1-C3 remains the drop reachability authority.
9. **Lord presentation** — `goblin_centurion` has six owner-approved runtime presentation slots under `lord_trial/`. The Lord is not the Battlefield Boss, and cinematic SHOT07 is not Lord eligibility authority.
10. **Progression** — Current zone, clear, star, reward, and Zone 4 unlock remain server/L3-owned. Selected zone, quest text, Monster defeat, cinematic completion, and replay do not grant progression.
11. **Replay** — Replay reuses the same localized presentation sources, cleans its presentation lifecycle, and cannot grant reward, consume items, clear the zone, or unlock Zone 4.
12. **Responsive/device acceptance** — Desktop, iPad landscape, iPad portrait, and mobile portrait contracts are recorded. Full-frame `contain` is the safe baseline; SHOT09/10 retain reviewed custom positions. Physical-device and authenticated walkthrough acceptance are not claimed here.

## Closure changes in this candidate

- Rebound the Z3 map-card landmark in `js/e9/world_stage.js` to the canonical World package path already present in the static pack.
- Removed the stale player-facing “assets pending style lock” wording from the Zone 3 rail and made the ready/fallback status reflect the actual asset slot.
- Added the machine-readable contract at [`w1_c1_zone3_reference_vertical_slice_template_001.json`](w1_c1_zone3_reference_vertical_slice_template_001.json).

## Explicit non-goals and open gates

`app.py` is untouched. No Monster art was created, no Zone 4 implementation started, and no Shop/Loadout/W1-A2 work was reopened. Merge, deploy, Production mutation, M2 acceptance, physical-device acceptance, authenticated walkthrough, and Owner audio lock are all separate gates and remain ungranted.

The canonical base and planning references are pinned in the JSON contract: `3dc517bfbf789da378f971b092980fb53e7a5e2f`, tree `f794a931c7243a5cea6655b2ab71313bd563c19a`, planning head `9dda8945e74cbda2902fa30ddd973ba125fbd203`.
