# F034-R2 Z9 to Z1 Final Owner Decision Candidate Reconciliation

Status: OWNER DECISION PACKET ONLY.

This packet re-evaluates the Z9 -> Z1 replacement pool against the complete remaining inventory. It does not modify or freeze the F034 assignment. Scope is `ART_CONTENT_PLANNING_ONLY`.

## Fresh authority

- Current origin master: `6829c4c528adf4800326e90534585a32e390ebec`
- F034 head: `ea6458318e73f9ef81ce0b6083a0a4729a05f994`
- F034-R1 head: `62e060961dfed0766763240bdea044a686c8d232`
- ART002 identity reference: `3e7034ef71c27ca00acf456d03f95301f30b8c64`

The five Owner-approved moves remain locked:

| M-ID | Name | Move | Status |
|---|---|---|---|
| M073 | Brass Golem | Z7 -> Z10 | LOCKED; unchanged |
| M088 | Stringwing Bat | Z8 -> Z2 | LOCKED; unchanged |
| M094 | Shieldshell Crab | Z8 -> Z2 | LOCKED; unchanged |
| M060 | Crystalhorn Lizard | Z6 -> Z3 | LOCKED; unchanged |
| M091 | Smokescreen Weasel | Z8 -> Z2 | LOCKED; unchanged |

The six rejected moves remain fixed and are not candidate options:

| M-ID | Name | Concept | Decision | Candidate status |
|---|---|---|---|---|
| M064 | Windspine Serpent | wind serpent | KEEP Z6 | NOT REPROPOSED |
| M086 | Breakshield Beetle | siege beetle | KEEP Z8 | NOT REPROPOSED |
| M099 | Aurora Serpent | aurora serpent | KEEP Z9 | NOT REPROPOSED |
| M102 | Star-ring Ape | orbit ape | KEEP Z9 | NOT REPROPOSED |
| M104 | Moon-eclipse Mantis | eclipse mantis | KEEP Z9 | NOT REPROPOSED |
| M109 | Firmament Jelly | sky jelly | KEEP Z9 | NOT REPROPOSED |

## Complete Z9 inventory boundary

The four rejected IDs are not eligible. `M098 Stormpray Bird` is also excluded because it is the existing runtime identity anchor; proposing it would violate the planning/runtime firewall. The remaining eligible planning candidates are ranked below, including `M101 Skyvault Whale` as the weakest option rather than silently omitting it.

| M-ID | Name | Concept | Current Zone | Exclusion reason |
|---|---|---|---|---|
| M098 | Stormpray Bird | storm bird | Z9 | Existing runtime identity anchor; excluded to preserve the runtime/planning firewall. |
| M099 | Aurora Serpent | aurora serpent | Z9 | Owner-rejected prior move; fixed in Z9 and must not be reproposed. |
| M102 | Star-ring Ape | orbit ape | Z9 | Owner-rejected prior move; fixed in Z9 and must not be reproposed. |
| M104 | Moon-eclipse Mantis | eclipse mantis | Z9 | Owner-rejected prior move; fixed in Z9 and must not be reproposed. |
| M109 | Firmament Jelly | sky jelly | Z9 | Owner-rejected prior move; fixed in Z9 and must not be reproposed. |

## Full eligible ranking

Exactly four selections are required. Every row is currently Z9 and would be proposed for Z1 only as planning metadata.

| Rank | M-ID | Name | Concept | Current Zone | Proposed Zone | Visual theme | Name theme | Current Z9 fit | Target Z1 fit | Theme cost if moved | Early readability | Recommendation |
|---:|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | M107 | Monolith Beetle | monument beetle | Z9 | Z1 | Grounded beetle with a stone/monument visual cue. | Monolith/monument; ancient relic language. | Fits Z9's monument and celestial-weather finale as a relic-associated insect. | Beetle is an ordinary garden/grass-edge creature and its grounded silhouette fits village outskirts. | MEDIUM | HIGH: familiar insect ecology plus a clear grounded silhouette; not based on size alone. | RECOMMENDED |
| 2 | M106 | Starsand Wolf | star wolf | Z9 | Z1 | Terrestrial wolf with a star-sand accent. | Star/sand; one explicit celestial cue. | Fits Z9's star and sky-fauna language. | Wolf is a familiar terrestrial animal that can fit grassland or village-edge ecology. | MEDIUM | HIGH: familiar terrestrial predator and grassland ecology, with the star cue retained as the main cost. | RECOMMENDED |
| 3 | M100 | Thundercrown Stag | storm grazer | Z9 | Z1 | Stag/grazer with storm and crown motifs. | Thunder/crown; elevated mythic authority. | Strong Z9 fit through storm, crown and celestial-grazer language. | Stag and grazer identity directly fits grassland, woodland edge and ordinary early fauna. | MEDIUM_HIGH | HIGH: familiar grazer ecology and readable woodland identity; the name remains elevated. | RECOMMENDED |
| 4 | M105 | Skydrum Tortoise | storm tortoise | Z9 | Z1 | Grounded tortoise with a sky/drum motif. | Sky/storm/drum; late-zone weather signal. | Fits Z9's storm and sky-fauna set. | Grounded tortoise can fit a stream, grass or village-outskirts ecology. | MEDIUM_HIGH | HIGH: familiar grounded reptile and stream-edge ecology; not justified only by readability. | RECOMMENDED |
| 5 | M110 | Dawnwing Serpent | dawn serpent | Z9 | Z1 | Serpent with a dawn/wing accent. | Dawn/wing; elevated sky-fauna language. | Fits Z9's dawn and aerial-serpent imagery. | Serpent can fit grass or small-stream ecology, but the wing cue weakens the fit. | HIGH | MEDIUM_HIGH: familiar serpent ecology, offset by aerial styling. | FIRST_ALTERNATE |
| 6 | M111 | Starshard Rhino | star rhino | Z9 | Z1 | Heavy rhino with starshard/elite cues. | Starshard; explicit celestial and endgame rarity signal. | Fits Z9's starshard and mythic fauna language. | Rhino is terrestrial, but its heavy elite-normal identity is a poor village-edge fit. | HIGH | MEDIUM: familiar animal identity, but mass and elite framing conflict with ordinary early ecology. | SECOND_ALTERNATE |
| 7 | M103 | Riftbow Eagle | storm eagle | Z9 | Z1 | Aerial eagle with rift/bow and storm motifs. | Rift/bow/storm; dramatic sky-combat language. | Strong Z9 storm and sky-fauna fit. | Eagle is familiar wild fauna, but aerial/rift identity conflicts with simple village-edge ecology. | VERY_HIGH | MEDIUM: familiar species, but aerial dramatic identity dominates. |  |
| 8 | M108 | Thundercrystal Mantis | crystal mantis | Z9 | Z1 | Mantis with thunder/crystal treatment. | Thunder/crystal; overt high-tier elemental cue. | Strong Z9 elemental and crystal-storm fit. | Mantis can fit garden ecology, but the thundercrystal treatment is too strongly late-game. | VERY_HIGH | MEDIUM_HIGH: familiar garden insect, outweighed by elemental identity conflict. |  |
| 9 | M101 | Skyvault Whale | cloud whale | Z9 | Z1 | Large cloud/sky whale. | Skyvault/cloud; monumental celestial scale. | Very strong Z9 sky and mythic-scale fit. | Whale and skyvault scale do not fit village outskirts, grassland or small-stream content. | VERY_HIGH | LOW: identity is legible but not compatible with ordinary early ecology. |  |

R1 recommendation was re-evaluated against all nine eligible options. The ranking remains: `M107, M106, M100, M105, M110, M111, M103, M108, M101`.

Recommended four: `M107, M106, M100, M105`.

First alternate: `M110 Dawnwing Serpent`.
Second alternate: `M111 Starshard Rhino`.

## Recommended move justification

| M-ID | Why Z1 fits | Z9 theme lost | Why the loss is acceptable |
|---|---|---|---|
| M107 | Beetle/garden-edge ecology is ordinary and grounded. | Monolith/monument relic framing. | The relic cue is less central than the explicit celestial cues retained by the rest of Z9; no runtime anchor is moved. |
| M106 | Wolf is familiar terrestrial grassland/edge fauna. | Star/sand celestial accent. | Only one explicit celestial prefix is lost while Z9 keeps its stronger sky/mythic identities. |
| M100 | Stag/grazer directly fits grassland and woodland-edge ecology. | Thunder/crown storm authority. | Its base ecology is materially better for Z1 than aerial/rift/skyvault alternatives. |
| M105 | Grounded tortoise can inhabit stream, grass and village outskirts. | Sky/storm/drum framing. | The grounded species identity reduces the move cost and preserves count without touching runtime. |

This recommendation uses ecological and naming fit together. Early readability is supporting evidence only; it is not the sole reason for any move.

## Count projection

Starting from the ART002 distribution `10,11,12,12,12,13,13,14,14,9`, applying the five locked moves and the four recommended Z9 -> Z1 proposals yields:

`14,14,13,12,12,12,12,11,10,10`, total 120.

If Owner selects an alternate, it must replace one recommended candidate from the same Z9 source pool; the count contract remains unchanged.

## Decision state and firewall

- `REMAINING_OWNER_DECISION_COUNT=4`
- `NEW_OWNER_APPROVED_Z9_TO_Z1=0`
- `EXACT_ASSIGNMENT_FREEZE=NO`
- `F035_STARTED=NO`
- No gameplay/runtime/stat/art/app.py changes.
- A043, B057, C050, E046, ART003 and LC015 scopes are untouched.
