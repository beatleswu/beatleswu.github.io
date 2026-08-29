# F034-R1 Owner Decision Replacement Candidate Packet

Status: OWNER DECISION PACKET ONLY

This packet reconciles Owner decisions against F034. It does not mutate the F034 exact assignment artifact and does not approve any new replacement. Scope is `ART_CONTENT_PLANNING_ONLY`.

## Fresh authority

- Current origin master: `6829c4c528adf4800326e90534585a32e390ebec`
- F034 head: `ea6458318e73f9ef81ce0b6083a0a4729a05f994`
- ART002 reference: `3e7034ef71c27ca00acf456d03f95301f30b8c64`
- F034 source artifact: `docs/planning/monster_art_content_zone_assignment_v1.json`

The three Owner-approved moves are preserved unchanged. The six rejected IDs are excluded from all replacement pools.

## Protected Owner decisions

| M-ID | Identity | Decision | Placement |
|---|---|---|---|
| M073 | Brass Golem | Z7 -> Z10 | LOCKED / unchanged |
| M088 | Stringwing Bat | Z8 -> Z2 | LOCKED / unchanged |
| M094 | Shieldshell Crab | Z8 -> Z2 | LOCKED / unchanged |

| Rejected M-ID | Decision | Replacement eligibility |
|---|---|---|
| M064 | KEEP existing Zone | NOT REPROPOSED |
| M086 | KEEP existing Zone | NOT REPROPOSED |
| M099 | KEEP existing Zone | NOT REPROPOSED |
| M102 | KEEP existing Zone | NOT REPROPOSED |
| M104 | KEEP existing Zone | NOT REPROPOSED |
| M109 | KEEP existing Zone | NOT REPROPOSED |

## Z6 -> Z3 candidates

Exactly one candidate will eventually be needed. These are ranked by lowest thematic cost, not combat or rarity.

| Rank | M-ID | Name | Current | Proposed | Why it fits | Theme lost | Visual/name conflict | Recommendation |
|---:|---|---|---|---|---|---|---|---|
| 1 | M060 | Crystalhorn Lizard | Z6 | Z3 | Crystal/mineral identity plus lizard form fits Z3 ore and cave ecology. | Z6 crystal-valley association. | Crystal remains a Z6-adjacent visual cue, but no wind/sky encoding. | RECOMMENDED |
| 2 | M070 | Molten Gold Centipede | Z6 | Z3 | Crawler form and mineral/gold surface fit underground ore ecology. | Z6 lava-dragon-valley association. | Molten/lava language keeps a strong Z6 fire signature. |  |
| 3 | M067 | Sulfur Salamander | Z6 | Z3 | Sulfur and salamander ecology can plausibly inhabit a dark mineral interior. | Z6 fire-valley association. | Sulfur/fire palette still carries volcanic rather than ordinary cave tone. |  |
| 4 | M063 | Basalt Shellbeast | Z6 | Z3 | Basalt/rock identity directly fits stone and underground ecology. | Z6 basalt valley association. | Heavy shellbeast silhouette reads as a later, tougher identity. |  |

Recommended: `M060 Crystalhorn Lizard`.

## Z8 -> Z2 candidates

Exactly one candidate will eventually be needed. The approved `M088` and `M094` moves are not reconsidered; this packet supplies one additional replacement.

| Rank | M-ID | Name | Current | Proposed | Why it fits | Theme lost | Visual/name conflict | Recommendation |
|---:|---|---|---|---|---|---|---|---|
| 1 | M091 | Smokescreen Weasel | Z8 | Z2 | Weasel form fits field, lowland or small-woodland ecology and is not intrinsically military. | Z8 scout/frontier pressure identity. | Smokescreen/scout naming still carries a tactical residue. | RECOMMENDED |
| 2 | M093 | Beacon Scorpion | Z8 | Z2 | Scorpion can fit dry field or lowland edge ecology. | Z8 signal/beacon frontier identity. | Beacon/signal language is strongly fortification-coded. |  |
| 3 | M085 | Blackgate Hound | Z8 | Z2 | Hound can fit village outskirts or ordinary terrestrial ecology. | Z8 gate/frontier identity. | Blackgate/gate naming is an explicit fortress cue. |  |
| 4 | M089 | Steelfang Hyena | Z8 | Z2 | Hyena is a plausible lowland scavenger. | Z8 frontier pressure identity. | Steelfang/frontier naming gives a strong hostile-war tone. |  |

Recommended: `M091 Smokescreen Weasel`.

## Z9 -> Z1 candidates

Exactly four candidates will eventually be needed. The rejected `M099,M102,M104,M109` remain in Z9 and are not listed.

| Rank | M-ID | Name | Current | Proposed | Why it fits | Theme lost | Visual/name conflict | Recommendation |
|---:|---|---|---|---|---|---|---|---|
| 1 | M107 | Monolith Beetle | Z9 | Z1 | Beetle is an ordinary readable creature form that can fit village-edge grass or garden ecology. | Z9 monument/storm-celestial framing. | Monolith/monument still implies an ancient relic. | RECOMMENDED |
| 2 | M100 | Thundercrown Stag | Z9 | Z1 | Stag/grazer is the strongest woodland and ordinary early-fauna fit among the remaining Z9 pool. | Z9 storm and crown mythic framing. | Thunder/crown remains overtly elevated. | RECOMMENDED |
| 3 | M106 | Starsand Wolf | Z9 | Z1 | Wolf is a familiar terrestrial predator suitable for an early readable ecology. | Z9 star-sand mythic framing. | Star language remains celestial-coded. | RECOMMENDED |
| 4 | M105 | Skydrum Tortoise | Z9 | Z1 | Grounded tortoise form can fit stream, grass or village-outskirts content. | Z9 sky/storm framing. | Sky/drum naming remains a late-zone signal. | RECOMMENDED |
| 5 | M110 | Dawnwing Serpent | Z9 | Z1 | Serpent can fit grass or stream edge ecology. | Z9 dawn/sky fauna framing. | Winged serpent reads as elevated and aerial. |  |
| 6 | M108 | Thundercrystal Mantis | Z9 | Z1 | Mantis is a small insect form. | Z9 thunder/crystal framing. | Both thunder and crystal are strong high-tier visual signals. |  |
| 7 | M103 | Riftbow Eagle | Z9 | Z1 | Eagle is a familiar wild creature. | Z9 storm/rift framing. | Aerial eagle plus rift language strongly conflicts with Z1. |  |
| 8 | M111 | Starshard Rhino | Z9 | Z1 | Rhino is terrestrial and readable. | Z9 starshard/elite framing. | Starshard and elite-normal framing create the highest remaining endgame cost. |  |

Recommended four: `M107 Monolith Beetle`, `M100 Thundercrown Stag`, `M106 Starsand Wolf`, `M105 Skydrum Tortoise`.

`M098 Stormpray Bird` is excluded because it is the Z9 runtime identity anchor. `M101 Skyvault Whale` is not shortlisted because its skyvault/whale identity has the highest target-Z1 thematic cost among the remaining unprotected candidates.

## Count projection

Starting from the ART002 distribution `10,11,12,12,12,13,13,14,14,9`:

- approved: M073 Z7 -> Z10; M088 and M094 Z8 -> Z2;
- proposed replacements: M060 Z6 -> Z3; M091 Z8 -> Z2; M107, M100, M106 and M105 Z9 -> Z1.

Projected result: `14,14,13,12,12,12,12,11,10,10`, total 120. No hidden cascade.

## Decision and authority lock

- `NEW_OWNER_APPROVED_REPLACEMENTS=0`
- `EXACT_ASSIGNMENT_FREEZE=NO`
- `F035_NOT_STARTED=YES`
- No gameplay, runtime, stat, asset or app.py authority changes.
- E046, ART003 and B057 scopes untouched.

Owner decision is requested only for the three packet groups above. If a recommended row is rejected, select another row from the same source pool so the source/target delta remains unchanged.

