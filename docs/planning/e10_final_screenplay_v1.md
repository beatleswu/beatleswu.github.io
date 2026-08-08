# E10 Final Screenplay v1.0 — Canonical Shot Document

Status: `READY_FOR_OWNER_REVIEW`. See `e10_final_screenplay_integration_contract_v1.md` for authority
hierarchy, protected dialogue, relic chains, Heartstone lifecycle, and all locked Owner corrections. See
`e10_final_screenplay_mapping_closure_v1.md` for the full decision history and superseded findings.

**Dialogue completeness — read before use.** This process was never handed the full Master Screenplay
Part 1/3–3/3 text, only excerpts embedded in the original Mapping Contract plus corrections issued
directly through this review. Every shot's **Final Dialogue** cell below is one of three states:

- An exact line from the Protected Dialogue Set or a locked Owner correction — usable as-is.
- **`[MASTER SCREENPLAY TEXT PENDING]`** — no canonical text has been supplied to this process for this
  shot. This is not the same as "no dialogue" — silence is only marked where a shot is explicitly
  confirmed dialogue-free (Zone 10 Shot 6; the Source and Eastern Guardian throughout).
- Confirmed silent by design.

**Do not fill `[MASTER SCREENPLAY TEXT PENDING]` cells with the recovered pre-screenplay storyboard's old
lines.** Several of those lines are confirmed superseded (see mapping closure, Superseded Findings) and
reusing them would reintroduce exactly what this process was built to prevent. Visual/Camera/Audio/VFX/
Transition/Gameplay Contract fields below are carried from the recovered storyboards as structural
reference and were not contested by any Owner correction — only dialogue text carries this gap.

---

## Zone 1 — Newbie Village (willingness to begin)

Lifecycle: Shots 1–8 `PRE_PLAY` → `HANDOFF_TO_GAMEPLAY_AFTER_SHOT` → Shots 9–10 `POST_CLEAR`/
`POST_CLEAR_HOOK`. Only zone with repo-secured candidate art (Shot 1) and a working isolated prototype
(commits `6567da373`/`539b1cdb8`, this worktree).

| Shot | Visual | Camera | Character Action | Final Dialogue | Audio | Ambient VFX | Story VFX | Transition | Gameplay Contract | Continuity Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Bedroom window, morning light, ordinary stillness before the story begins | Static, held | Hero, off-screen | **(Anna Narration)** 清晨的鐘聲還沒響起，村子的風，已經帶來一絲……不尋常的氣息。 No other spoken dialogue. | Village-dawn ambience; soft BGM | Sunlight rays, dust motes, warm bloom (built in prototype) | None | Fade-in (cinema open) | None | `KEEP_EXACT` relative to the already-built, browser-verified prototype |
| 2 | Hero + 水靈馬 waking | — | Elder (off-screen), Hero, 水靈馬 (addressed, does not speak) | 村長「孩子，天亮了。」／主角「早啊，小水。」 | — | — | — | Cut | None | Confirms 水靈馬's given name: 小水 |
| 3 | Elder + Hero overlook village, storm cloud | — | Elder, Hero | Silent — no narration, no dialogue | — | — | — | Cut | None | — |
| 4 | Elder points at cloud, close-up | — | Elder | 村長「你看，那片雲。它已經停在那裡三天了。而且……每天都更近一點。」（Hero does not answer） | — | — | Black/white current FX (restrained, not a storm) | Cut | None | Prior compliance flag: candidate art reads as a literal storm, not the intended restrained current |
| 5 | Hero grips wooden sword | — | Hero | Silent — no dialogue. The Wooden-Sword grip is carried entirely by visual/action/SFX | — | — | — | Cut | None | Prior compliance flag: candidate sword reads as a long staff, not forearm-to-shoulder length |
| 6 | Hero + 水靈馬 + sword, farmyard | — | Hero, 水靈馬 | 主角「我不知道自己行不行……但我想去看看。」 | — | — | — | Cut | None | Character-arc starting point |
| 7 | 19×19 stone board, Elder gesturing | — | Elder, Hero | Silent — no dialogue. Only ritual stone-placement sound/action | — | — | — | Cut | None | — |
| 8 | Board covered in scattered stones | — | Elder, Hero | 村長「想出村，就先陪我下一局。別急。」then **看清楚，再落子。** (DL-01, protected) | — | — | — | Cut to gameplay | `HANDOFF_TO_GAMEPLAY_AFTER_SHOT` | Boss-identity thesis line |
| 9 | Board after trial, silence intentional | — | Hero | Silent (intentional) | — | — | `sealUnlockPulse` real production candidate | Cut | None | Elder acknowledges the clear visually only |
| 10 | Runner/messenger arrives | — | Runner, Hero, Elder | Runner「村長！史萊姆平原的商隊……三天了，還沒回來！」（Hero and Elder do not add a response line before the cut） | — | — | — | Hard cut to black | `END_CINEMATIC_SEQUENCE_AFTER_SHOT` | Final Dialogue, confirmed — **not** a Protected Dialogue Set member and does not supersede any DL ID (correction: an earlier note here mislabeled this as superseding "DL-02"; 「商隊三天未歸。」 was never DL-02, only Zone 1's protected story-beat wording). Prior compliance flag: candidate figure reads as a ragged wanderer, not a village messenger with satchel/sash |

## Zone 2 — Slime Plains (suffering, not monstrosity)

Lifecycle: Shots 1–7 `PRE_PLAY` → `HANDOFF_TO_GAMEPLAY_AFTER_SHOT` → Shots 8–10 `POST_CLEAR`/
`POST_CLEAR_HOOK`.

| Shot | Visual | Camera | Character Action | Final Dialogue | Audio | Ambient VFX | Story VFX | Transition | Gameplay Contract | Continuity Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Green plains at scale, scattered slime-mounds, visual wrongness | Wide, static, slow push-in begins | Hero, 水靈馬 enter | Silent — no narration, no dialogue | Quiet uneasy strings; wind through grass | — | — | Cut in from Z1 | None | — |
| 2 | Slime centered, trembling | Push-in settles close | Hero crouches, watches | 主角「等等……牠在發抖。牠不是要咬我們……牠在怕。」 | Strings hold | Subtle tremble on slime | — | Cut | None | States the real subject: suffering, not monstrosity |
| 3 | Herder's cart stuck in mire | Medium, static | Herder turns, Hero approaches | 牧人「小心鞋子。這幾天，連地都怪怪的。」／主角「牠們也是最近開始的嗎？」 | Folk instrument enters; cart creak, mud squelch | — | — | Cut | None | — |
| 4 | Herder testimony | Close on herder | Herder gestures toward hive | 牧人「這些小傢伙以前可黏人了。趕都趕不走。直到幾天前……蜂巢裡開始傳出那個聲音。然後，牠們就成這樣了。」 | Instrument holds | — | — | Cut | None | Sets up investigation, not ambush |
| 5 | The hollow hive, this zone's core image | Low angle, looking up | Hero, 水靈馬 approach | Silent — hive corruption communicated visually and through the corruption pulse/hum | String tension rises; distant hive-hum | — | Wrong-colored static glow, deliberately withheld Go motif (corruption, not a Go-trial site) | Cut | None | — |
| 6 | Swarm Lord's form gathers | Tight on hive-crystal core | Swarm Lord assembles | Silent — Swarm Lord formation is entirely visual/audio | Tension peaks; wing-hum swells | — | Swarm-particle assembly (new) | Cut | None | — |
| 7 | Core Belief delivered, unsettling not battle-cry | Close on Swarm Lord | Swarm Lord still, Hero small at edge | Swarm Lord「……好餓。明明吃了這麼多……怎麼還是不夠？那就……再一點。」 | Single sustained dissonant note | — | Static glow (same) | Cut to gameplay | `HANDOFF_TO_GAMEPLAY_AFTER_SHOT` | Core Belief reframed as hunger/vulnerability, not a battle cry — consistent with "suffering, not monstrosity" applying to the Boss as well as the slimes |
| 8 | Slimes calm, hive quiet | Wide, static | Hero, 水靈馬, Herder (background) | Silent — the return of wind and the slimes calming carry the resolution | Theme softens; wind returns | — | Go-boundary seal (first reuse after Z1) | Cut | None | Resolution shown before Hero speaks; `POST_CLEAR` content not yet built |
| 9 | Hero states the zone's theme | Medium, close | Hero, 水靈馬 | Silent | Theme settles gently | — | — | Cut | None | **Authoritative correction (Dialogue Polish Pass 01): the earlier optional Hero line 「好多了。」 is CUT and must not be restored.** |
| 10 | Crystal fragment in hero's palm | Close on open palm | Hero | Silent — the corrupted crystal fragment reacts subtly; Hero does not explain the reaction | Theme fades to one held note; faint crystal hum | — | Fragment pulse, directional toward Zone 3 (Corruption Evidence, not Go energy) | Hard cut to black | `END_CINEMATIC_SEQUENCE_AFTER_SHOT` | `JOURNEY_MEMORY_ELIGIBILITY`: this is Corruption Evidence, not a Hero Journey Relic — read again at Z5 Shot 3 |

## Zone 3 — Goblin Cave (retreat, not raid)

Lifecycle: Shots 1–7 `PRE_PLAY` → `HANDOFF_TO_GAMEPLAY_AFTER_SHOT` → Shots 8–10 `POST_CLEAR`/
`POST_CLEAR_HOOK`.

| Shot | Visual | Camera | Character Action | Final Dialogue | Audio | Ambient VFX | Story VFX | Transition | Gameplay Contract | Continuity Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Cave mouth, goblins fleeing with supplies | Handheld-feel, unsteady | Goblins move away, Hero enters, hand moves toward the Wooden Sword then away | Silent — the restraint gesture is visual only | Tense, held low; urgent goblin voices | Torch flicker | — | Cut in from Z2 | None | Subverts "monster ambush" expectation |
| 2 | Hero watches goblins recede | POV-adjacent | Hero, goblins (bg) | 主角「……他們要搬家？」 | Held note; fading footsteps | — | — | Cut | None | States real subject: retreat, not raid |
| 3 | Grik cornered, facing Hero directly | Level camera, matched eyelines | Grik holds ground, Hero | Grik「別再過來。今天已經搬第三次了。沒力氣再跟你打了。」／主角「我不是來打你的。」／Grik「拿著劍進來的人，都這麼說。」 | Quiet folk instrument | — | — | Cut | None | Grik introduced at eye level, not as a captured enemy |
| 4 | Grik's testimony, cave wall gestured at | Close on Grik | Grik gestures at wall, Hero listens | 主角「這些是什麼？」／Grik「去年，牆在那裡。上個月，在這裡。今天……在這裡。」 | Instrument holds | — | Held for Shot 5's reveal | Cut | None | Shrinking-territory reveal, tied to endgame-counting theme |
| 5 | Cave wall resolves into a natural Go board | Push in on cracked wall | Hero reaches toward wall | Silent | Quiet realization swell; stone settling | — | Stone-board dais, first *found* (non-constructed) use of this motif; reveal is photographic (lighting), not magical | Cut | None | Zone's core image. Continuity note: the cracks may read as a Go-board structure through composition/camera only — no magical grid dialogue or explanation |
| 6 | Centurion, completely still | Level angle (not the low-angle "unveiling" Z2 got) | Centurion stands, spear planted | 主角「你是這裡的首領？」／Centurion「不是。我是最後一道門。」 | Tension drops to stillness; near-silence | — | — | Cut | None | Introduced as recognition, not a creature reveal |
| 7 | Core Belief, one chance to turn back | Close on Centurion | Centurion, Hero at edge | Centurion「Grik願意相信你。我不能。」／主角「那我要怎麼做？」／Centurion「讓我看看。你看見的，是不是只有自己的地。你現在還可以回頭。」 | Single low sustained note | — | — | Cut to gameplay | `HANDOFF_TO_GAMEPLAY_AFTER_SHOT` | Polished version; supersedes the earlier draft wording 「證明你看得見的，不只有自己的地。」 |
| 8 | Ceasefire before anyone speaks | Wide, static | Hero, Grik, Centurion (distant), none in combat stance | Silent — Centurion's decision to allow passage is shown through action | Theme softens | — | Go-boundary seal, second reuse | Cut | None | — |
| 9 | Stone Shard handoff | Close on hands passing shard | Grik extends shard, Hero receives | Grik「這個給你。」／主角「這是什麼？」／Grik「不知道。但每次牆往前……它就會多一道。」 | Gentle resolve; stone-on-stone | — | None — story prop, not a shared visual-language element | Cut | None | Canonical object name: **STONE SHARD** — "stone-mark" and equivalent variants are superseded. `JOURNEY_MEMORY_ELIGIBILITY`: Hero Journey Relic — fused at Z7 Shot 7 |
| 10 | Grik gestures toward deeper cave/forest | Medium, static on Grik | Grik, Hero | 主角「你在哪裡找到它的？」／Grik「森林那邊。很久以前。在霧變得這麼厚以前。」 | Theme fades to one held note; distant wind | — | None — Stone Shard does not glow or point toward Zone 4 | Hard cut to black | `END_CINEMATIC_SEQUENCE_AFTER_SHOT` | No extra navigation explanation; points toward Zone 4 through the goblins' own history, not a magical pointer |

## Zone 4 — Misty Forest (trust, not out-calculation)

Lifecycle: Shots 1–7 `PRE_PLAY` → `HANDOFF_TO_GAMEPLAY_AFTER_SHOT` → Shots 8–10 `POST_CLEAR`/
`POST_CLEAR_HOOK`.

| Shot | Visual | Camera | Character Action | Final Dialogue | Audio | Ambient VFX | Story VFX | Transition | Gameplay Contract | Continuity Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Forest edge, mist rolling in; background: violet eyes catch light briefly | Wide, static, silhouette swallowed by mist | Hero, 水靈馬 enter; 虛空貓 unresolved eye-glint only | Silent — no narration, no dialogue | Uneasy sustained drone; muffled forest ambience | Mist volumetric effect | Small eye-glint/vanish effect (虛空貓 first-glimpse, never framed centrally) | Cut in from Z3 | None | Glimpse remains background-only — no Hero reaction, no SFX sting, no dialogue. Requires reading real ownership at render time — see integration contract §11 |
| 2 | 水靈馬's quiet resistance to the fog | Medium; Hero nearly swallowed, 水靈馬 sharper | Hero stops disoriented, 水靈馬 stands firm | 主角「奇怪……我們剛才，是從哪邊進來的？」 | Drone holds | Mist parts subtly around 水靈馬 only | — | Cut | None | 水靈馬 must stay visually stable, no new magic aura |
| 3 | Phantom copies emerge from fog | Slow circling shot | Copies drift into a loose ring | Silent — first Hero phantom-copy reveal carried entirely by visual/audio | Drone turns dissonant; overlapping whispers | Phantom-copy translucency/shimmer (new) | — | Cut | None | No existing runtime duplication-rendering technique confirmed — may require new compositing, not just new art |
| 4 | Ring of copies, real Hero indistinguishable | Circling continues, faster | Copies gesture identically | Silent — the multiplying/mirroring Hero copies remain visual | Dissonance peaks; whispers overlap more | Same shimmer, intensified | — | Cut | None | Same technique gap as Shot 3 |
| 5 | Phantom King's riddle, voice from everywhere | Close, no single face held | Rabbit King (voice only) | Misty Phantom Rabbit King「哪一個……才是你？還是……連你自己也不知道？」 | Single sustained uncanny tone; line echoes | Same shimmer | — | Cut | None | Still `PRE_PLAY` — the riddle, not the trial, is this shot. Polished wording supersedes the earlier variant 「還是……你自己也不知道了？」 |
| 6 | 水靈馬 as the one steady thing | Tight on 水靈馬, sharp against soft-focus copies | 水靈馬 stands still | Silent — 水靈馬 remains visually stable, no magical aura or explanatory line | Dissonance recedes; whispers quiet | None on 水靈馬 — its clarity is the effect | — | Cut | None | — |
| 7 | Hero's first doubt seed, chooses trust | Close on Hero, 水靈馬 at edge | Hero resolves into quiet decision | 主角「小水。」 **帶我走。** (DL-02, protected) — canonical protected beat represented together as 「小水。帶我走。」 Do not add an explanation such as 「因為只有你不會騙我。」 | Single clear note emerges from dissonance | — | — | Cut to gameplay | `HANDOFF_TO_GAMEPLAY_AFTER_SHOT` | Protected line — see integration contract §2 |
| 8 | Ancient tree, fruit gleaming black and white | Upward tilt to canopy | Hero tilts head back | Silent — fog clears gradually; Rabbit King does not deliver a defeat/acceptance speech | Theme opens up; leaves rustle, fog dissipating | — | Go-boundary seal, third reuse (marks the puzzle's resolution) | Cut | None | — |
| 9 | Fruit falls into Hero's hand | Close on open hand | Hero catches without reaching | Silent — Black/White Fruit is received visually | Quiet relief, not triumph; soft landing sound | — | Already used in Shot 8 | Cut | None | `JOURNEY_MEMORY_ELIGIBILITY`: Hero Journey Relic — **BLACK_WHITE_FRUIT** — fused at Z7 Shot 7. Do not restore the old thesis line about black/white being the only truth in the mist |
| 10 | Scorched trail toward the horizon, distant drums | Wide, static at fog's edge | Hero, 水靈馬 | Silent — scorched trail and distant drums carry the Zone 5 hook | Theme fades to low rhythmic pulse; faint distant drums | — | — | Hard cut to black | `END_CINEMATIC_SEQUENCE_AFTER_SHOT` | Deeper doubt from Shot 7 deliberately left open for later zones |

## Zone 5 — Orc Tribe (earned respect, not humiliation)

Lifecycle: Shots 1–6 `PRE_PLAY` → `HANDOFF_TO_GAMEPLAY_AFTER_SHOT` → Shots 7–9 `POST_CLEAR`/
`POST_CLEAR_HOOK`.

| Shot | Visual | Camera | Character Action | Final Dialogue | Audio | Ambient VFX | Story VFX | Transition | Gameplay Contract | Continuity Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Arena at full scale, red-earth desert, crowd tiers | Wide, static, holds on scale | Hero small, entering; crowd | Silent — crowd chant only | Percussive drums building; wordless rhythmic chant, wind | Heat-shimmer over red earth | — | Cut in from Z4 (scorched trail leads here); arena drums continue the audio match-cut | None | Stone pillars with pre-existing axe marks must already be visible as setup |
| 2 | Hero threads through cheering crowd | Medium, tracking | Hero moves toward arena floor | Silent | Drums continue; chant grows louder | Dust kicked up by crowd | — | Cut | None | Crowd and an Orc child establish the Chieftain as genuinely admired |
| 3 | Smith-elder's warning, corrupted ore | Close, static, isolated from crowd noise | Smith-elder turns the ore slowly | 鐵匠長老「那把斧頭，是我替他打的。以前，他每天練到太陽下山。這幾天，他幾乎沒放下過。」／主角「不會累嗎？因為這個？」／鐵匠長老「這就是我怕的。他說，它讓自己變得更強。我只知道……我越來越認不出他。」 | Drums drop out; single low worried string note; muffled crowd distant | Ore glow, faint and unstable | — | Hard cut from arena scale to this quiet | None | Plants the corrupted-ore motive before the fight. **Continuity action, no extra dialogue:** Hero briefly brings out the Zone 2 Corrupted Crystal Fragment; it and the wrong-colored ore resonate once with the same unstable pulse signature — nobody states they're the same thing or explains their origin. Corruption Evidence chain only; neither item belongs to the four Hero Journey Relics |
| 4 | Chieftain enters, axe not yet raised | Wide, crowd roaring | Chieftain strides in, Hero small at edge | Silent — entrance carried visually; he is not villain-framed | Drums return full intensity; sharper crowd roar | Dust from Chieftain's footfalls | — | Cut | None | — |
| 5 | The dramatized swing | Tight on swing | Chieftain full-body torque | Silent — Chieftain strikes the arena ground, not Hero; his lack of fatigue is communicated visually | Drums peak; axe whoosh, crowd roar swells | Motion blur; faint ore-glow trail on blade | — | Cut | None | Dramatizes stakes before gameplay begins |
| 6 | Core Belief at full sincerity | Close on Chieftain | Chieftain stands still to speak, Hero small at edge | 酋長「長老叫你來的？」／主角「他只是很擔心你。」／酋長「擔心？我比以前更快。更強。也更能護住我的人。哪裡不好？」／主角「**我不知道。**（DL-03, protected）但我想請你先把那把斧頭放下。」／酋長「想叫一個戰士放下武器？那就進來。讓我看看，我為什麼該聽你的。」 | Drums cut to single sustained low tone; crowd recedes | — | None — no effect competes with the line | Cut to gameplay | `HANDOFF_TO_GAMEPLAY_AFTER_SHOT` | Polished version supersedes the more formal earlier variants ("也更能保護我的族人。" / "你告訴我，哪裡不好？") |
| 7 | Mark on the pillar | Close, static, axe against stone | Chieftain single deliberate motion | Silent — Chieftain adds one new axe mark to the already-established stone pillar; no defeat speech here | Theme softens, drums silent; single carving strike | — | None — Script's own specific resolution image, not a cross-zone signature | Cut | None | Marks the fight's end through action, not narration |
| 8 | Respect-earned ending, no kneel-as-humiliation | Medium, level with kneeling Chieftain (not looking down) | Chieftain does not kneel; voluntarily releases the axe | 酋長「你贏了。而且……我已經很久，沒覺得累了。」 | Theme resolves, gentle; crowd's silence is part of the shot | — | Held back deliberately (see Shot 7) | Cut | None | **Character/fate lock:** Chieftain does not kneel; he voluntarily releases the axe. No Hero victory speech |
| 9 | Smith-elder, cooling ore shard, looks north | Medium, static | Smith-elder alone | 主角「這些礦，是從哪裡來的？」／鐵匠長老「山那頭。而且……還在流。」 | Theme fades to one held low note; distant wind | Faint ore glow, unsteady | None — corrupted-ore material, should not borrow Go-energy visual language | Hard cut to black | `END_CINEMATIC_SEQUENCE_AFTER_SHOT` | Ore may react subtly; it does not become a magical navigation arrow — actual geographic information comes from the Smith-Elder's dialogue. `JOURNEY_MEMORY_ELIGIBILITY`: Corruption Evidence, read again at Z6 Shots 1-2 |

## Zone 6 — Dragon Valley (order without exception, questioned)

Lifecycle: Shots 1–5 `PRE_PLAY` → `HANDOFF_TO_GAMEPLAY_AFTER_SHOT` → **Gameplay Phase 1** begins → Shots
6–7 **`MID_PLAY`** interrupts the *same* encounter, not a reset or a second independent trial →
`RETURN_TO_GAMEPLAY_AFTER_SHOT` → **Gameplay Phase 2** resumes the same encounter → Shots 8–10
`POST_CLEAR`/`POST_CLEAR_HOOK`. `MID_PLAY` requires new runtime capability — see integration contract
§10. Not built in this sprint.

| Shot | Visual | Camera | Character Action | Final Dialogue | Audio | Ambient VFX | Story VFX | Transition | Gameplay Contract | Continuity Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Valley entrance, wyverns avoid one fixed point near a distant tower | Wide, static | Hero, 水靈馬 enter; wyverns visibly avoid the ruined tower area | Silent | Quiet tension, no percussion; wind, distant wyvern cries | — | Ore glow intensifying | Cut in from Z5 | None | Reads Zone 5's ore state directly |
| 2 | Ore fills lower frame, Hero wary above | Close on ore, tilt to face | Hero | 主角「好燙……又開始了。」 | Tension holds; ambient wind only | — | — | Cut | None | Direct Zone 5 continuity, no gap. No line suggesting the Ore is sentient or "recognizes" the location |
| 3 | Ruined watchtower; background: worn dragon-engraved Go-jar catches light | Wide/low, static at tower base | Hero approaches; 棋罐龍 unresolved background detail | Silent — clue remains background-only | Tension holds; wind through ruin | Dust drifting | Small, separate glint effect on the jar (棋罐龍 first-glimpse, static prop only) | Cut | None | No camera acknowledgment, SFX sting, Hero reaction, or UI. Lower bar than Z4's glimpse — static prop, not conditional render |
| 4 | Knight's philosophy shown against a wyvern, before he speaks | A wyvern strays close; single silent strike | Wyvern recoils and flees; no attacker visible yet | Grand Temple Knight「停下。」／主角「我只是想進那座塔。」／Grand Temple Knight「沒有人可以靠近。」／主角「連牠們也不行？」／Grand Temple Knight「任何人。沒有例外。」 | Composed tension, no percussion; single sharp impact then silence | — | Fast, minimal strike-flash, deliberately unspectacular | Cut | None | — |
| 5 | Knight descends in total silence | Close/medium as Knight descends | Knight lands, composed, still; Hero small at edge | 主角「這東西，是從山那頭流出去的。外面有人因為它出事。」／Grand Temple Knight「所以？」／主角「所以我得進去。」／Grand Temple Knight「不行。我的命令，是不讓任何人靠近。」／主角「你明明知道外面——」／Grand Temple Knight「退後。」 | Single sustained composed tone; silence | — | None — his stillness is the effect | Cut to gameplay | `HANDOFF_TO_GAMEPLAY_AFTER_SHOT` | Polished wording supersedes the longer earlier draft. **Gameplay Phase 1 begins after this shot** |
| 6 | Encounter interrupted mid-fight | Close on both faces, encounter visibly paused around them | Knight, Hero both still | Grand Temple Knight「你一直要我讓開。因為你覺得，塔裡有答案。」／主角「外面真的有人在受傷。」／Grand Temple Knight「我知道。」（Pause.）「所以呢？因為你看見得比我多……就能替我決定，這道門該不該開？如果可以——**那你和我，有什麼不同？**」（DL-04, protected） | Composed tone cuts through gameplay's rhythm as a pause; ambient encounter sound held under | — | — | Cut | **`MID_PLAY`** — no return trigger yet (sits on Shot 7) | Polished version supersedes the earlier more essay-like wording about "資格." The question must derive only from the present encounter, not from the Knight magically knowing Hero's previous journey. Requires new pause/resume capability, not built |
| 7 | Scripted silence lands, then resumes | Close on Hero alone, Knight at frame edge waiting | Hero stands with the accusation, doesn't answer aloud | **Silent — structurally protected.** Hero says nothing: no subtitle, no internal monologue, no placeholder response. No Knight follow-up line. The encounter resumes only after the silence has had room to land | Sustained tone holds through silence, unresolved; ambient sound returns | — | — | Cut to gameplay | `RETURN_TO_GAMEPLAY_AFTER_SHOT`, `TRUE_PAUSE_RESUME_REQUIRED` | Same runtime gap as Shot 6. **Gameplay Phase 2 resumes the same encounter — not a reset or a second independent trial** |
| 8 | Core cracks open, reveal as tragic guardian | Tight on fading light as chestplate cracks | Knight stands motionless as crack spreads | 主角「你……」（Knight does not answer verbally） | Theme opens into grief/recontextualization; faint stone-cracking | — | Crack-spread effect; star-map glow (both new, Zone-6-specific) | Cut | None | **Knight fate contract:** `KILLED_BY_HERO = FALSE`, `DEATH_ANIMATION = FORBIDDEN`, `FINAL_FATE = INTENTIONALLY_UNRESOLVED` — see integration contract §8; the core/armor revelation is not a conventional death beat |
| 9 | Hero's realization, Dragon Scale at tower base | Hero's line first, then close on scale | Hero speaks, crouches to pick up scale | Grand Temple Knight「以前……每一盞，都亮著。後來，一盞一盞地熄了。」／主角「你一直守在這裡？」／Grand Temple Knight「**命令沒有改。**」（DL-05, protected） | Grief settling; soft lift sound | — | — | Cut | None | Knight voluntarily lowers/abandons the sword. Dragon Scale enters the Journey Relic chain through the reopened boundary/Wyvern beat, not as Boss loot. `JOURNEY_MEMORY_ELIGIBILITY`: Hero Journey Relic (Dragon Scale) — fused at Z7 Shot 7 |
| 10 | Ancient star-map, many dead nodes, one lights | Wide, on the star-map's lit node | Hero looks toward it, matches it visually to the real distant Sage Tower | Grand Temple Knight「……還有一座。」 — **optional, not a Protected Dialogue Set member.** If omitted, the star-map node + real distant Sage Tower visual must carry the hook alone | Theme fades to one held note; distant wind | — | Star-map projection, brief | Hard cut to black | `END_CINEMATIC_SEQUENCE_AFTER_SHOT` | **Absolute hook rule:** no relic points toward Zone 7. The map shows many dead nodes; one node lights; Hero visually matches it to the real distant tower |

## Zone 7 — Sage Tower (the Heartstone forms)

Lifecycle: Shots 1–4 `PRE_PLAY` → `HANDOFF_TO_GAMEPLAY_AFTER_SHOT` → Shots 5–8 `POST_CLEAR`/
`POST_CLEAR_HOOK`.

| Shot | Visual | Camera | Character Action | Final Dialogue | Audio | Ambient VFX | Story VFX | Transition | Gameplay Contract | Continuity Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Stairwell spirals upward, starlight through walls, drifting runes | Upward spiral, slow, continuous | Hero climbs, small against scale | Silent — ascent carried by footsteps, starlight, architecture, and atmosphere | Reverent, slow, building; soft footsteps, faint high tone | Drifting-rune animation; starlight wall glow | — | Cut in from Z6 | None | — |
| 2 | Rune drifts past, catches light on Hero's face | Continues spiral, closer on Hero | Hero glances up as rune passes | After an offscreen Go-stone sound: 主角「……有人？」（No reply） | Continues building; faint tone swells as rune passes | — | — | Cut | None | — |
| 3 | Tower peak opens onto cosmic scale, Archmage revealed | Wide, cosmic scale — breaks from stairwell intimacy | Archmage doesn't move to greet; Hero arrives, small | Archmage「你比我想的……晚了一點。」／主角「你在等我？」／Archmage「不。我在等有人走到這裡。」 | Warmth enters reverent theme (mentor, slightly sorrowful); low cosmic hum | — | Early star-to-stone transformation at frame edges | Cut | None | Polished wording supersedes 「我在等一個，願意走到這裡的人。」 |
| 4 | Star-to-board transformation completes | Wide, following sweep of sleeve | Archmage one deliberate sweeping gesture | Archmage「一路上，下過不少了吧？」／主角「嗯。」／Archmage「那這一次……別只看眼前。」 | Theme swells to full scale; deep resonant tone as board settles | — | Zone's core image: vast star-board, bespoke; full transformation completing. No existing runtime transform/morph technique — likely needs new compositing capability, not just new art | Cut to gameplay | `HANDOFF_TO_GAMEPLAY_AFTER_SHOT` | Gameplay framing must not falsely claim the engine has no correct/wrong answers — the broader lesson concerns guaranteed life/world answers, not denial of local Go correctness |
| 5 | Gentle reframe of Hero's flaw | Close on Archmage, deliberately intimate, no cosmic wide shot | Archmage and Hero neither moves | Archmage「你一路走到這裡，都在找一樣東西。」／主角「什麼？」／Archmage「正確答案。哪邊對。哪一步最好。怎麼下，才不會後悔。**可棋不是考卷。**」（DL-06, protected）（Pause.）「有些局，沒人能先替你保證結果。」／主角「那要怎麼下？」／Archmage「看。想。自己選。」／主角「如果選錯呢？」／Archmage「那就記住。下一次，再下。」 | Swell recedes to quieter, warm but serious; cosmic hum gone silent | — | None — deliberately not the shared seal | Cut | None | Central turning point, retargeted gently, not as attack. Authoritative polished version |
| 6 | Heartstone offered, hesitant acceptance | Close on Hero's hand, hesitant | Archmage opens hand to reveal heartstone | Archmage「伸手。」／主角「什麼？」／Archmage「手。」（Heartstone is placed in Hero's hand）／主角「這是……？」／Archmage「棋心。」／主角「它能做什麼？」／Archmage「先別急。看看它記得什麼。」 | Resolve tempered by self-knowledge, not triumphant | — | Held for Shot 7 (heartstone glow, steady — persists through Zones 8-10) | Cut | None | Heartstone `ABSENT/UNFORMED → CARRIED` begins here. Naming: scene is **The Heartstone**, not "Heartstone Returns," unless a future explicit ancient-history basis is separately approved |
| 7 | Relic-chain fusion payoff | Close on heartstone completing, slow push-in | Hero's hand closes around stone, watching it change | 主角「它們……」／Archmage「都記得。你走過的地方。還有你下過的那些手。」 (Heartstone responds only to Journey Relics the player is eligible to remember) | Theme resolves, weighty not light; four soft chimes converge to one tone | — | Heartstone fully formed, zone's payoff image; fusion-effects converging for whichever relics are eligible | Cut | None | **Journey Relic contract — canonical four:** Wooden Sword (Z1), Stone Shard (Z3), Black/White Fruit (Z4), Dragon Scale (Z6). Does **not** include the Zone 2 Crystal or Zone 5 Ore. **Placement-skip rule:** render only Journey Relic memories whose corresponding zone has `cleared = true`; dialogue stays generic and does not fabricate missing memories. No physical relic is consumed |
| 8 | Scale/darkness toward Zone 8, no named object | Wide, Hero and Archmage looking outward/upward | Both look outward, still | 主角「那邊是什麼？」／Archmage「走到那裡，你就知道了。這次，我不替你下。」 | Theme fades to low, uneasy sustained tone, no resolution chord | — | Distant darkness/storm-texture on horizon | Hard cut to black | `END_CINEMATIC_SEQUENCE_AFTER_SHOT` | Authoritative polished dialogue but not a DL-01–DL-09 Protected Dialogue Set member. No further mentor explanation |

## Zone 8 — Demon Castle Front (Chaos Lord dissolves, not killed)

Lifecycle: Shots 1–6 `PRE_PLAY` → `HANDOFF_TO_GAMEPLAY_AFTER_SHOT` → Shots 7–9 `POST_CLEAR`/
`POST_CLEAR_HOOK`. Locked: `CHAOS_LORD_KILLED_BY_HERO = FALSE`; classification
`NON_LETHAL_RESOLUTION_REQUIRED` — see integration contract §9. Hero does not become army commander;
Serel remains responsible for the actual soldiers throughout.

| Shot | Visual | Camera | Character Action | Final Dialogue | Audio | Ambient VFX | Story VFX | Transition | Gameplay Contract | Continuity Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | War-scale march, Demon Castle first seen as a black spire | Wide, static, army in motion | Hero and 水靈馬 enter as only two figures among a much larger functioning frontline | Silent | Martial, building — grimmer than Z5's drums; horns, footfalls, wind | Dust/haze over marching column; faint dark corona around distant spire | — | Cut in from Z7 | None | — |
| 2 | Serel introduced; the blue command flag | Medium, Serel and Hero | Serel indicates the blue flag | Serel「賢者之塔那邊來的？」／主角「嗯。」／Serel「那你應該也看見了。看見那面藍旗嗎？下面三百二十七個人。旗往前，他們就往前。旗退，他們就退。所以，別只看旗。」 | Martial theme continues | — | — | Cut | None | No exact arrival-duration dialogue — do not restore 「三天前。」 Serel is a working frontline officer, not a philosophical mentor |
| 3 | Heartstone first reveals faint battlefield relationships | Close on Hero's hand around heartstone | Hero | 主角「這是……」（No explanation follows） | Tension rises under martial theme; distant wyvern shriek, fire crackle | — | Heartstone glow (reused prop from Z7), revealing faint relationship-lines only — a subtler beat than a full battlefield-grid transform | Cut | None | **Heartstone function:** `REVEALS_RELATIONSHIPS = TRUE`, `CONTROLS_PEOPLE = FALSE`, `COMMANDS_ARMY = FALSE`. Heartstone remains `CARRIED` |
| 4 | The blue flag moves through ordinary command flow; real soldiers move | Medium, on the flag and the responding formation | Hero instinctively retracts his hand | Serel「怎麼了？」／主角「沒事。」 | Theme shifts martial → internal/uncertain | — | — | Cut | None | No line such as 「人不是棋子。」 — the visual beat carries that realization |
| 5 | Chaos Lord steps through the gate directly, seen and heard | Battle noise cuts to silence; static hold on gate | Chaos Lord steps forward once, stops | Silent | Hard cut to near-silence — sharpest tonal contrast since Z1's runner; faint rune hum | — | Living-rune circling effect (new) | Cut | None | No conventional villain entrance speech |
| 6 | Core Belief at full persuasive force | Close on Chaos Lord, no cutaway | Chaos Lord studies the battlefield, a formation shifts | Chaos Lord「排得真整齊。人。旗。道路。每一個，都待在該在的位置。」（Pause.）「這樣就叫秩序？」（A formation shifts.）「那如果有人不肯呢？你們只是把還沒崩潰的混沌——叫成秩序。」 | Single sustained cold tone | — | Same rune circling | Cut to gameplay | `HANDOFF_TO_GAMEPLAY_AFTER_SHOT` | Hero does not become army commander; Serel remains responsible for the actual soldiers |
| 7 | Resolution via a single placed stone, explicit confrontation without a kill | Camera holds as Hero sets one stone at the critical underlying relation point | Hero, one deliberate, unhurried placement | Silent — 喀 (SFX only) | Martial/tension themes drop away; chaos-storm roar drops near the stone | — | Golden lines gathering Chaos Lord's power into shape; chaos-storm FX (new) | Cut | None | `NON_LETHAL_RESOLUTION_REQUIRED` — confrontation staged, outcome is not a kill. The battlefield distortion stabilizes; it does not become a perfect grid |
| 8 | Chaos Lord dissolves as the distortion sustaining him stabilizes | Close on Chaos Lord as he scatters | Chaos Lord dissolving — **not falling, not a combat-defeat posture**; looks upward | Chaos Lord「原來……是這樣。」／主角「什麼？」／Chaos Lord「我一直以為，只要再亂一點……最後，就什麼都不用選了。」（He looks upward.）「可是……真正不讓你們選的……在天上。」 | No triumphant swell — low unresolved tone under the line; faint ash-wind | — | Ash-scatter dissolve (new) — his own dissolution, not a shared resolution signature | Cut | None | **`CHAOS_LORD_KILLED_BY_HERO = FALSE`, `CHAOS_LORD_RESOLUTION = DISSOLUTION_AFTER_DISTORTION_STABILIZES`** — do not describe this as a combat kill |
| 9 | Castle collapses; a buried stone eye begins to light | Wide on collapsing castle, slow push toward splitting ground | Serel orders withdrawal/protection of troops; Hero watches | Silent — Heartstone recognition may sound: 嗡 (no spoken explanation) | Theme fades to one low ancient tone; distant collapse rumble, then stone-grinding | — | Castle collapse (new); ground-splitting FX (new); stone-eye ignition, minimal and restrained | Hard cut to black | `END_CINEMATIC_SEQUENCE_AFTER_SHOT` | Direct continuity into Zone 9's opening Statue image |

## Zone 9 — Ragnarök (THE CHOICE)

Lifecycle: Shots 1–6 `PRE_PLAY` → `HANDOFF_TO_GAMEPLAY_AFTER_SHOT` → Shots 7–12 `POST_CLEAR`/
`POST_CLEAR_HOOK`. Corrected structure per integration contract §13: protected line relocated to Shot 10;
Shot 11 redefined; no five-relic narration in this zone; Heartstone is not thrown here.

| Shot | Visual | Camera | Character Action | Final Dialogue | Audio | Ambient VFX | Story VFX | Transition | Gameplay Contract | Continuity Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Old, settled ash — ancient grief, not the fight just finished | Wide, static, beyond ruined castle | Hero enters, dwarfed by Statue's scale | Silent | Ancient grief, not battle; near-silence, faint low ancient hum | Settled-ash texture (new) | — | Cut in from Z8 | None | — |
| 2 | Statue begins to stir | Close on the Statue, then slow reveal | Statue's eyes flicker | Fallen War-God (fragmented) 「必須……純粹……不能再……只剩……一種……」 | Ancient-grief theme deepens; faint ancient stone grinding | Statue eye-flicker (new); subtle stone-groan | — | Cut | None | **Absolute rule: do not allow 「……我們錯了」 yet — that full line belongs only to Shot 8** |
| 3 | Statue's memory bleeds into the ruins — a well-intentioned mistake, not malice | Dreamlike, slow drift, vision overlaying physical ruin | Hero stands still, watching; translucent Ancients gather | Different Ancient civilians, incomplete and distant: 「……還要多久……」／「……又有人沒回來……」／「……夠了……」 | Warm, not sinister — the seduction of a well-intentioned mistake; faint indistinct voices | Vision-overlay translucency (new) | Go Visual Motif deliberately withheld — Ancients are never detailed | Cut | None | **Memory contract:** these are fragments, not formal exposition — Zone 9 memory answers WHY, not the technical mechanism |
| 4 | The Ancients' reasoning fragment | Close on the ancient board within the vision | Gathered silhouettes, no single figure moves independently | Different ordinary Ancient voices: 「如果……不用再分呢？不用再爭。不用再有人輸。是不是……就不會再有人痛了？」 | Warm seduction continues, one layer more unsettling; line carries faint echo/overlap | Same vision-overlay with line-echo treatment | — | Cut | None | Tone: sincere exhaustion and hope, not sinister |
| 5 | Hero's illusions rise, unattacked | Illusions surging from every side, camera holds on Hero | Hero doesn't flinch or attack; three hero-illusion variants (failed/weeping/aged) | Failed Hero「如果你選錯呢？」／Weeping Hero「如果有人，因為你那一手受傷呢？」／Aged Hero「如果很多年以後……你還是不知道，今天是不是對的呢？」 | Raw tension, sharper than prior scenes; glass-shard chime, overlapping voices | Shattered-glass illusion rise (new); three silhouette variants | — | Cut | None | Central character-arc turn, met by acknowledgment not combat |
| 6 | Hero's quiet acknowledgment lands in words, not action | Close on Hero, illusions no longer surrounding aggressively | Hero stands unguarded, no combat stance; illusions soften | 主角「我會選錯。也可能有人，因為我的選擇受傷。也許很多年以後……我還是不知道，今天是不是對的。**可我不能因為怕錯，就替所有人把選擇拿走。**」（DL-08, protected） | Raw tension resolves into quiet acknowledgment; glass-shard chime quiets | Illusion-softening (new, subtle) | — | Cut to gameplay | `HANDOFF_TO_GAMEPLAY_AFTER_SHOT` | Gameplay resolves the repeating ancient regret loop — it is not a giant-monster execution |
| 7 | The Hero-visions return into / merge back with the Statue | Wide, watching illusions drift, no longer surging | Illusions drift back, one by one, merging into the Statue rather than being destroyed | Silent | Theme opens toward release, still restrained; faint resonant tone per illusion merged | — | Illusion-merge into the Statue (new) — bespoke resolution imagery | Cut | None | — |
| 8 | The Statue's actual completion — not exposition, a real resolution | Close on the Statue's fist, clenched for a thousand years | One slow, deliberate loosening — no sudden collapse; music stops | Fallen War-God「**……我們錯了。**」（DL-07, protected. No further confession.） | Release, not triumph; low final stone-groan, then silence | — | Fist-loosening, fine dust falling away | Cut | None | Statue is not killed — it stops executing the old command. `NON_LETHAL_RESOLUTION_REQUIRED` |
| 9 | Gods introduced, broken Statue still visibly present | Wide, both Statue and Gods' descending light in the same frame | Statue still, resolved; Hero; Gods' light descending | Gods / Collective Voice「你已經走得夠遠了。你看見了爭鬥、失去……還有那些，再也收不回來的選擇。」（Pause.）「夠了，孩子。把棋收起來吧。不再分黑。不再分白。就不會再有人輸了。」 | Dread through certainty, serene not ominous; clear resonant tone as light descends | Descending-light effect (new) | — | Cut | None | **Voice contract:** the Gods are serene, beautiful, comforting, sincere — not angry, monstrous, or villain-roaring |
| 10 | THE CHOICE — Hero's refusal, board stays alive | Wide, close on Hero's raised hand, then its deliberate lowering | Heartstone resonates with the ancient convergence system; Hero raises his hand, then deliberately lowers it and keeps the Heartstone | Gods「孩子？」（Hero looks up calmly.）「**一色的棋盤，是死的。**」（DL-09, protected） | Theme rises, quiet resolve rather than a triumphant swell | — | Single-color overlay visibly destabilizing as a *consequence* of the refusal — no explosive binding-light effect; the line itself has no magical destructive power | Cut | None | **Causality lock:** `HERO_REFUSES_CONVERGENCE → COMPLETION_FAILS → SINGLE_COLOR_OVERLAY_DESTABILIZES`, not `HERO_SAYS_LINE → GODS_MAGICALLY_SHATTER`. Heartstone remains `CARRIED` — no throwing, no consumption |
| 11 | Failed convergence, made visible | Close, then wide as the fracture spreads | One black stone remains black, one white stone remains white; neither disappears | Silent — no narration | — | — | A fine fracture appears across the Gods' single-color overlay; corruption/wrong-tone signature becomes perceptible underneath | Cut | None | **Absolute correction:** no five-relic narration, no Final Stone, no Heartstone use here. The recovered storyboard's old "protect exactly as-is" instruction for this shot is `SUPERSEDED` |
| 12 | Ending hook toward Zone 10 | Wide, on the receding light and the exposed wound | Hero and 水靈馬 approach | Silent — no narration, no dialogue | — | — | Gods' light withdraws/recedes, exposing the world wound / path to the true Source | Hard cut to black | `END_CINEMATIC_SEQUENCE_AFTER_SHOT` | Do not use 「走吧。」 here — that line belongs only to Zone 10 Shot 10. World orientation becomes unstable/dreamlike, transitioning into Zone 10 |

## Zone 10 — Ancient Doom Temple (THE FINAL MOVE)

Lifecycle: Shots 1–6 `PRE_PLAY` (five-scene length, still one `PRE_PLAY` band) →
`HANDOFF_TO_FINAL_GAMEPLAY_AFTER_SHOT` → **Final Gameplay — Break the Loop** (narrative meaning:
`STOP_OVER_CORRECTION`, not `KILL_SOURCE`) → Shots 7–10 `POST_CLEAR` → Shot 11 `POST_CLEAR_HOOK`,
closing on a fade to black (the only zone to end this way). Confirmed non-`MID_PLAY`, single-cycle
(`docs/planning/e10_zone10_lifecycle_decision_v1.md`).

| Shot | Visual | Camera | Character Action | Final Dialogue | Audio | Ambient VFX | Story VFX | Transition | Gameplay Contract | Continuity Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Dream-logic open, mist, endless lotus pond, circling dragon-shadow | Drifting, dreamlike, no fixed anchor | Hero and 水靈馬 enter the dream-logic lotus-pond space | Silent — the heartstone's glow shows the way | Dreamlike, vast — most atmospheric opening of any zone; ancient whispers | Mist drift; lotus-pond reflection; dragon-shadow silhouette | — | Cut in from Z9, wound now resolved into this dream | None | Heartstone `CARRIED`. `ANNA_DIALOGUE = 0` for this shot |
| 2 | Eastern guardian introduced, silent, gesture only | Wide, archway resolves, push toward guardian | Hero, Eastern guardian (doesn't move until the gesture) | **Silent — absolute.** Eastern Guardian says nothing; Hero says nothing | Reverence, building; faint resonant tone as archway resolves | Archway flicker-in (new) | — | Cut | None | **Eastern Guardian contract:** `DIALOGUE = 0`, `VOICE = 0`, `SUBTITLE = 0`, `EXPOSITION = 0`. Guardian communicates only through looking, gesture, and image |
| 3 | The Answer, delivered through pure image — the mechanism (HOW), not a restatement of Zone 9's WHY | Guardian lifts a hand; pond transforms; vision shows Ancients activating the Order Engine | Eastern guardian, single gesture; vision may show: Ancients activating the Order Engine, Gods' light, black/white currents, temporary stability, over-correction, brief downstream anomaly callbacks | Silent — no dialogue, no narration | Revelation, not exposition — quiet; stones settling faintly | — | Black-and-white stones circling in the air (new, rhymes with Z7's star-to-stone) — no existing runtime technique | Cut | None | **Memory contract:** this vision answers HOW, not Zone 9's emotional WHY — do not restate that through dialogue here |
| 4 | The unfinished Ancient game, ghost endgame possibilities | Continues the vision from Shot 3 | An Ancient hand hesitates and does not complete the game; the Gods' single-color solution overlays the unfinished choice | Silent — no spoken dialogue, no Anna narration | Tense precision within the vision | — | Ghost endgame possibilities layered over the unfinished position (new) | Cut | None | **Half-point setup:** the vision establishes that a normal completion leads to a final result by 半目, but does not identify the winning color. `GO_LOGIC_GATE_01 = OPEN` — no production board/sequence may be invented merely to satisfy this visual |
| 5 | The Gate of the End, road paved with stars, old-god statues | Slow push forward, continuous, unhurried | Hero walks, steady; Hero does not draw the Wooden Sword | Silent — Guardian remains silent | Solemn ascent; footsteps, faint rhythmic "breath" pulse | Star-paved road glow (new) | — | Cut | None | — |
| 6 | Boss manifests, wholly silent confrontation | Wide, temple's heart, vast black crystal hanging above | Hero small, facing it, still; Source silent by design | **Silent — absolute / resolved.** Hero says nothing; Source says nothing. **Remove permanently:** do not restore 「黑不吞白——白不奪黑——共，生！」; no one-to-one replacement exists | The confrontation stated through silence — no swell competing | — | Shadow-pour effect (new); crystal ambient darkness (new) — held for Shot 7's crack | Cut to gameplay | `HANDOFF_TO_FINAL_GAMEPLAY_AFTER_SHOT` | **Source contract:** `FACE = NONE`, `VOICE = NONE`, `DIALOGUE = NONE`, `PERSONALITY = NONE`, `VILLAIN_SPEECH = NONE` — the Source is a failed world-order mechanism, not a character. See integration contract §12 |
| 7 | Crystal cracks open, an empty point waits | Camera holds on the widening crack | Hero steps closer, drawn toward the opening; Source stops, cracks slowly | Silent | Theme opens toward completion; resonant crystal-crack | — | Crystal-crack spreading (new); light-spill (new) — bespoke resolution image, not the shared seal | Cut | None | Inside is revealed the same unfinished Ancient board/unresolved position from Shots 3–4. Heartstone carries faint traces of the Hero Journey Relics (Z1 Wooden Sword, Z3 Stone Shard, Z4 Black/White Fruit, Z6 Dragon Scale — not the Zone 2/5 Corruption Evidence). Journey memory only; no relic is physically consumed |
| 8 | THE FINAL MOVE — Hero places the Heartstone as the Final Stone; the ancient game resolves; the world responds; the Heartstone becomes an ordinary stone | Close on Hero's hand placing the final stone, then a brief hold on near-nothing, then rapid, dialogue-free glimpses across the ten zones, then close again as the stone loosens and falls | Hero pauses, places the Heartstone as the Final Stone (喀); the Ancient game settles — final result: 半目, winning color unspecified; after the Source/Ancient board begins dissolving, the Final Stone loosens and falls, Hero catches it (嗒) | **Version A (`A/B_TEST_ONLY`, not canonical):** after the half-point result settles, Anna「……半目。」 **Version B:** silence — no narrator voice at all, only board/room/breathing/environmental sound | Quiet completion, explicitly not Z9's triumphant register; single soft resonant tone; world-response montage carries no additional dialogue | — | Living board (echo of Z9 Shot 10, not a new motif); Heartstone-to-ordinary-stone transition (new, quiet) at the shot's end | Cut | None | **`ANNA_Z10_HALF_POINT: A_B_TEST_ONLY, NOT_CANONICAL`, located at Zone 10 Shot 8 (corrected from an earlier wrong placement at Shot 4).** **World Response Montage (still Shot 8, no additional dialogue):** Z2 — slimes calm, ordinary wind/grass returns. Z3 — cave damage does not magically reverse; Stone Shard gains no new crack. Z4 — natural fog can remain, phantom duplication is gone; optional 虛空貓 callback only if legitimately owned/unlocked. Z5 — wrong-colored ore flickers once then goes inert; Chieftain finally feels fatigue. Z6 — ancient nodes stop being forced into one frequency; wyverns cross the old boundary; Knight's lowered/abandoned sword may appear (his final fate remains unresolved — do not resolve it here). Z7 — Archmage's board responds subtly, no dialogue. Z8 — Serel sees real people and flags without the Heartstone overlay. Z9 — War-God's hand remains open; the single-color wash no longer dominates the sky. **Heartstone final override:** `ABSENT/UNFORMED → CARRIED after Z7 → CARRIED through Z8 → CARRIED through Z9 → FINAL_STONE at Z10 Shot 8 → ORDINARY_STONE`. Forbidden canonical states: `THROWN`, `DESTROYED`, `REMOVED`, `SPENT_AS_GONE`. The same physical stone continues into Shots 9–11 |
| 9 | Walk out into ordinary daylight; the stone is now completely ordinary | Wide, walking out, then settling; close on Hero's open hand | Hero returns to ordinary ground; opens his hand | Silent — no narration | Quiet, settled, forward-looking; first ordinary-world sound — birdsong, matching/calling back to Zone 1's morning ambience | — | None — the stone is now completely ordinary, no glow or resonance | Cut | None | — |
| 10 | The closing line; Guardian roster rendered by real ownership | Wide, then close on Hero crouching | Hero looks to the companions; 水靈馬 (guaranteed), 虛空貓/棋罐龍 (conditional on real ownership) | 主角「**走吧。**」 | Quiet, settled, matching Shot 9, no swell | — | None — no effect should compete with this line | Cut | None | `FINAL_SPOKEN_LINE = 走吧。`, approved/locked for E10 Final Screenplay v1.0. **Remove permanently:** do not restore 「世界從來不需要新的英雄。世界真正需要的，是新的守護者。」 — no thesis-line replacement beyond 走吧。 **Optional Guardian state:** guaranteed `ink_drop_kelpie`; `star_shell_hatchling`/`whispering_void_kit` conditional on ownership via `pet_collection`/`_pet_owned_keys()` — do not render merely because the pet exists in `PET_CATALOG`. See integration contract §11 |
| 11 | The Next First Move — Hero lays one opening stone directly on the open ground | Wide, then close on the ground | Hero crouches on ordinary open ground; places the same ordinary black stone directly on the earth (喀), then stillness | Silent — no dialogue, no narration | Theme settles to one open, unresolved note — an ellipsis, not a cadence; quiet wind | — | **Absolute visual contract: `GOBAN = NONE`, `MAGIC_GRID = NONE`, `STORY_VFX = ZERO`, `GLOW = NONE`, `WORLD_RESPONSE_EFFECT = NONE`. Only ordinary ground, grass, wind, companions in background** | **Hold, then fade to black — the only zone in the script to end this way, no hard cut. This is the true ending** | `END_CINEMATIC_SEQUENCE_AFTER_SHOT` | Series end state |

---

## Validation

**Fill Pack completion:**

```
FILL_PACK_A: 30/30
FILL_PACK_B: 37/37
FILL_PACK_C: 32/32
TOTAL_ZONES: 10/10
TOTAL_SHOTS: 99/99
MASTER_SCREENPLAY_TEXT_PENDING: 0
CONFIRM_AGAINST_MASTER_SCREENPLAY: 0
```

**Dialogue / continuity checks:**

- All DL-01 through DL-09 present exactly and located correctly: DL-01 (Z1 S8), DL-02 (Z4 S7, active, not
  superseded), DL-03 (Z5 S6), DL-04 (Z6 S6), DL-05 (Z6 S9), DL-06 (Z7 S5), DL-07 (Z9 S8), DL-08 (Z9 S6),
  DL-09 (Z9 S10). Plus the locked non-DL line 走吧。 (Z10 S10). Zone 1 Shot 10's Runner line is confirmed
  Final Dialogue but was never DL-02 and supersedes no DL ID — see integration contract §2.
- 「黑不吞白——白不奪黑——共，生！」 — absent as canonical dialogue (Z10 S6 is fully silent; no
  replacement exists).
- 「世界從來不需要新的英雄。世界真正需要的，是新的守護者。」 — absent; replaced by 走吧。 at Z10 S10.
- 「我不再是棋子。我，是執棋的人。」 — absent; Zone 8 Shot 2 now carries Fill Pack C's actual Serel/Hero
  exchange, no residual marker.
- "Stone-mark" / "stone sigil" — 0 occurrences anywhere in this document; canonical term is **Stone
  Shard** (Zone 3 Shot 9).
- Zone 2 Shot 9's optional 「好多了。」 — absent, logged only as a removal record.
- `HEARTSTONE_THROWN` / `HEARTSTONE_DESTROYED` — 0 occurrences. Full corrected lifecycle:
  `ABSENT/UNFORMED → CARRIED (Z7 S6–7) → CARRIED through Z8–Z9 → FINAL_STONE at Z10 S8 →
  ORDINARY_STONE (Z10 S9 onward)`.
- `Z10_FINAL_STONE_USE`: exactly 1 (Zone 10 Shot 8). Zone 9 does not use a Final Stone and does not
  consume the Heartstone — Shot 10's note confirms it remains `CARRIED` through Shot 12.
- Eastern Guardian dialogue: 0 (Z10 Shots 2–5, contract explicit at Shot 2).
- Source of Black-White Order dialogue: 0 (Z10 Shot 6 onward, contract explicit at Shot 6).
- Zone 6 Shot 7 Hero dialogue: 0 (structurally protected silence).
- Zone 10 Shot 11 dialogue/narration: 0; Story VFX explicitly `ZERO` per the absolute visual contract.
- Anna「……半目。」 marked `A/B_TEST_ONLY`, located at **Zone 10 Shot 8** (corrected from an earlier wrong
  placement at Shot 4), not treated as canonical anywhere.
- Journey Relics (canonical four): Z1 Wooden Sword, Z3 Stone Shard, Z4 Black/White Fruit, Z6 Dragon
  Scale. Corruption Evidence (separate chain): Z2 Corrupted Crystal, Z5 Wrong-colored Ore. No merge
  between the two chains anywhere in this document.
- `CHAOS_LORD_KILLED_BY_HERO = FALSE`; `KNIGHT_KILLED_BY_HERO = FALSE`; `KNIGHT_FINAL_FATE =
  INTENTIONALLY_UNRESOLVED` (reaffirmed at Zone 10 Shot 8's world-response montage — explicitly not
  resolved there either).
- `RECOVERED_DIALOGUE_USED_AS_FILLER`: 0. `NEW_DIALOGUE_INVENTED`: 0.
- No runtime, DB, art, or audio files were changed to produce this document.

**Gates remain explicitly open (content/engineering, not story blockers):**

```
GO_LOGIC_GATE_01: OPEN
ANNA_AB_GATE: OPEN
ZONE6_TRUE_MID_PLAY_PAUSE_RESUME: REQUIRED / DEFERRED_TO_DEDICATED_HIGH_RISK_SPRINT
ADVENTURE_COMBAT_FRAMING_RUNTIME_FIX: NOT_REQUIRED
```

**Fill Pack status:**

| Pack | Zones | Shots | Status |
|---|---|---|---|
| A | 1–3 | 30/30 | **Applied** |
| B | 4–7 | 37/37 | **Applied** |
| C | 8–10 + overrides | 32/32 | **Applied** |

**All three Fill Packs applied. 99/99 shots filled, 0 pending, 0 confirm-against-master markers
remaining.** One residual note carried from Zone 8 Shot 2: the earlier `[REMOVED — ...]` marker
documenting the superseded 「我不再是棋子。我，是執棋的人。」 line has been replaced by Fill Pack C's
actual Serel/Hero exchange at that shot — see the Zone 8 table.
