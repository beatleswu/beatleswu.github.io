# E10 Final Screenplay — Integration Contract v1

Status: `READY_FOR_OWNER_REVIEW`. Documentation only. No runtime, DB, art, audio, or SGF changes accompany
this file. Produced under Sprint `E10-SCREENPLAY-CANON-001`, authorized for planning/documentation files
only.

## 1. Story authority hierarchy

1. **Dialogue & Character Voice Polish Pass 01** — wins on exact wording wherever it speaks.
2. **Continuity Pass 01 / Owner Decisions (this mapping-and-review process)** — wins on continuity,
   structure, and any correction to the recovered pre-screenplay storyboards.
3. **Master Screenplay Part 1/3–3/3** — the underlying structural authority (scene function, shot
   sequence, lifecycle) wherever the two passes above are silent.
4. **Recovered pre-screenplay storyboards** (`docs/planning/e10_zone{1-10}_storyboard_notes_v0.1.md`,
   Class C, untracked) — lowest authority. Used only as structural/visual reference (composition, camera,
   audio cues, VFX direction) where nothing above has revised it. **Never used as a source of canonical
   dialogue** — several of its lines have been explicitly superseded (see
   `e10_final_screenplay_mapping_closure_v1.md`, Superseded Findings).

**Working limitation, stated plainly:** this integration process was never handed the full text of Master
Screenplay Parts 1/3–3/3 as standalone documents — only the excerpts embedded in the original Mapping
Contract, plus corrections issued directly by the Owner across this review. `e10_final_screenplay_v1.md`
marks every shot whose Final Dialogue was never supplied as `[MASTER SCREENPLAY TEXT PENDING]` rather than
filling the gap with recovered-storyboard text or inventing new lines. Closing those gaps requires the
actual Master Screenplay documents, not further mapping work.

## 2. Protected Dialogue Set

Lines below may not be altered, shortened, or reassigned without a new Owner Decision.

**Correction (post Fill Pack A):** an earlier draft of this table mislabeled Zone 1 Shot 10's full Runner
line as superseding "DL-02." That was a numbering misread — 「商隊三天未歸。」 was never a Protected
Dialogue Set member; it was Zone 1's protected *story beat / summary wording* only. The Runner's full line
at Zone 1 Shot 10 is confirmed Final Dialogue but is **not** a DL-numbered protected line and does not
supersede any DL ID. The correct, complete Protected Dialogue Set is:

| ID | Line | Zone / Shot |
|---|---|---|
| DL-01 | 「看清楚，再落子。」 | Zone 1, Shot 8 |
| DL-02 | 「小水。帶我走。」 | Zone 4, Shot 7 — **ACTIVE, not superseded** |
| DL-03 | 「我不知道。」 | Zone 5, Shot 6 |
| DL-04 | 「那你和我，有什麼不同？」 | Zone 6, Shot 6 (`MID_PLAY`) |
| DL-05 | 「命令沒有改。」 | Zone 6, Shot 9 |
| DL-06 | 「可棋不是考卷。」 | Zone 7, Shot 5 |
| DL-07 | 「……我們錯了。」 | Zone 9, Shot 8 |
| DL-08 | 「可我不能因為怕錯，就替所有人把選擇拿走。」 | Zone 9, Shot 6 |
| DL-09 | 「一色的棋盤，是死的。」 | **Zone 9, Shot 10** (relocated from the recovered storyboard's Shot 11 per Owner correction — see §9) |

Additional locked (non-DL-numbered) corrections:

| Line | Zone / Shot |
|---|---|
| 「走吧。」 | Zone 10, Shot 10 — the approved final spoken line of the entire script |
| Full silence, both Hero and Source | Zone 10, Shot 6 — no dialogue at all, replacing the recovered 「黑不吞白——白不奪黑——共，生！」 |

Zone 1 Shot 10's Runner line (「村長！史萊姆平原的商隊……三天了，還沒回來！」) is confirmed Final Dialogue,
not part of this protected set.

## 3. Two relic chains — kept structurally separate

**Hero Journey Relics** (the four objects Heartstone fuses at Zone 7):

| Relic | Zone obtained | Fused at |
|---|---|---|
| Wooden Sword | Zone 1 | Zone 7, Shot 7 |
| Stone Shard | Zone 3 | Zone 7, Shot 7 |
| Black/White Fruit | Zone 4 | Zone 7, Shot 7 |
| Dragon Scale | Zone 6 | Zone 7, Shot 7 |

**Naming lock:** canonical English term is **Stone Shard**. "Stone-mark" / "stone sigil" are not
canonical and must not appear in any new content.

**Corruption Evidence** (a separate chain — never enters Heartstone's memory sequence):

| Item | Zone obtained | Read again at |
|---|---|---|
| Corrupted Crystal Fragment | Zone 2 | Zone 5, Shot 3 (resonance) |
| Wrong-colored Ore | Zone 5 | Zone 6, Shots 1–2 (warms in hand) |

These two chains do not merge. The Corruption Evidence chain terminates at Zone 6 — it never becomes part
of the Heartstone's four-relic fusion.

## 4. Heartstone lifecycle

```
ABSENT/UNFORMED
  → CARRIED        (formed at Zone 7, Shot 7)
  → remains CARRIED through Zones 8 and 9
  → used as the FINAL STONE at Zone 10 (Shots 4, 7–8)
  → returns as ORDINARY_STONE (Zone 10, Shot 9 onward)
```

No `thrown` state. No destroyed/removed/"spent" state. The physical object never disappears — it loses
its Heartstone/interface function permanently and becomes the ordinary stone laid down at Zone 10's
closing image (Shot 11).

**Persistence:** no new schema, table, or booleans required. `JOURNEY_MEMORY_ELIGIBILITY` and Heartstone
state are both derived at read time from existing per-user, per-zone completion records
(`adventure_boss_progress.cleared`, `app.py:3185-3198`) — see §7.

## 5. Hero arc (across all ten zones)

The character-arc beats, in the order the recovered storyboards and Owner corrections establish them:

1. **Zone 1** — willingness, not confidence, to begin.
2. **Zone 4** — first doubt seed: choosing to trust (水靈馬) over out-calculating an illusion.
3. **Zone 7** — the doubt reframed gently by a mentor: "not every game is meant to prove you saw
   correctly."
4. **Zone 8** — a status-upgrade line is planted in the recovered storyboard at Shot 2, but that specific
   line (「我不再是棋子。我，是執棋的人。」) is confirmed superseded with no replacement supplied — the
   beat's function (claiming agency mid-war) stands; its wording does not.
5. **Zone 9** — the central acknowledgment: "I always thought if I saw clearly enough, I could fix
   everything." Answered not by combat but by refusal of a false, simpler solution (the Gods' one-color
   demand).
6. **Zone 10** — the thesis is now demonstrated through silent action (Zone 10 Shot 6 is wordless) rather
   than stated aloud, closing on 「走吧。」 — the arc's final register is quiet, not triumphant.

## 6. Zone gameplay meanings (thematic fit, not mechanical requirement)

| Zone | Books | Skill category | Fit |
|---|---|---|---|
| 1 | tutorial trial board | — | N/A |
| 2 | 史萊姆平原, 史萊姆討伐戰 | life_death, capture_escape | PARTIAL |
| 3 | 哥布林洞穴, 哥布林巡邏隊 | endgame_counting, capture_escape | **PASS** — source itself ties endgame-counting to "shrinking territory" |
| 4 | 迷霧森林, 迷霧森林深處 | life_death, capture_escape | PARTIAL |
| 5 | 獸人部落, 獸人角鬥場 | tesuji, capture_escape | PARTIAL |
| 6 | 飛龍討伐, 龍之谷守衛 | life_death, capture_escape | PARTIAL |
| 7 | 賢者之塔, 大魔法師試煉 | life_death, shape_weakness | WEAK/PARTIAL |
| 8 | 皇家騎士團遠征, 魔王城前線, 混沌領主的考驗 | life_death, endgame_counting, life_death | PARTIAL-PASS |
| 9 | 諸神黃昏 | not found in reviewed taxonomy | UNKNOWN |
| 10 | 東方神祕結界, 上古終焉神殿 | not found in reviewed taxonomy | UNKNOWN |

Gameplay questions are generic Go tactics puzzles and cannot themselves narrate story content — "fit"
measures thematic resonance of the assigned skill category only.

## 7. Adventure combat framing — resolved, no runtime fix required

`ADVENTURE_COMBAT_FRAMING_RUNTIME_FIX: NOT_REQUIRED`. Verified this session: `monsterSpeakTaunt`/`Hurt`/
`Die` ([index.html:8020-8041](index.html:8020)) are gated off during all Adventure Zone gameplay by
`_isAdventureZonePractice()` ([index.html:8363](index.html:8363)) and fire only in the unrelated generic
daily-training minigame. The actual Adventure Zone boss-completion UI is `showBossResultCinematic()`
([index.html:13827](index.html:13827)), already narratively neutral — "領主通關"/"Boss Cleared" on
success, "領主逃走了"/"Boss Fled" on failure ([i18n.js:1585-1594](i18n.js:1585)). No shared
resolution-presentation runtime system is being built in this sprint. Each zone's actual narrative
resolution (below) is expressed by its own not-yet-built `POST_CLEAR` cinematic content, not by any
runtime combat-framing fix:

| Zone | Resolution |
|---|---|
| 2 | Slimes calmed |
| 3 | Centurion's people released, truce |
| 4 | Navigate uncertainty via trust, not kill |
| 5 | Chieftain survives, voluntarily marks the pillar |
| 6 | Knight stops enforcing the ancient order — see §8 for exact fate rule |
| 8 | Chaos Lord dissolves once the underlying distortion stabilizes — **not killed by Hero** |
| 9 | War-God releases the loop ("……我們錯了。"), not killed |
| 10 | Source's correction-loop stops; a failed mechanism, not a monster |

`resolution_style` is zone-fixed content metadata (belongs with `ADVENTURE_BOSS_META` or future cinematic
timeline data), never per-user state — it does not vary by player and must not be added to any per-user
table.

## 8. Zone 6 fate rules (locked)

```
KNIGHT_KILLED_BY_HERO   = FALSE
KNIGHT_DEATH_ANIMATION  = FORBIDDEN
KNIGHT_FINAL_FATE       = INTENTIONALLY_UNRESOLVED
```

The Knight lowers his sword; the ancient command stops; the Hero leaves. The Finale callback (if any) may
show the lowered/abandoned sword. Whether the Knight is alive or not afterward is deliberately never
shown or stated — do not stage a survival beat, do not stage a death beat.

## 9. Zone 8 fate rules (locked)

```
CHAOS_LORD_KILLED_BY_HERO = FALSE
CHAOS_LORD_RESOLUTION     = DISSOLUTION_AFTER_DISTORTION_STABILIZES
```

Classification: `NON_LETHAL_RESOLUTION_REQUIRED`. Confrontation may still be staged as a real
confrontation; only the outcome is non-lethal by the Hero's hand — the distortion sustaining Chaos Lord's
form is what stabilizes/resolves, and his form dissolves as a consequence, not as a combat kill.

## 10. Zone 6 `MID_PLAY` requirement

Shots 6–7 are the script's one interruption of an already-running gameplay encounter: the encounter
pauses mid-fight, the Knight delivers his accusation, the Hero answers with scripted silence, then the
*same* encounter resumes with changed understanding. No pause/resume capability exists in production
today (`activate()`, [index.html:13567](index.html:13567), is a linear one-directional shot walker; the
only "checkpoint" concept anywhere, `NEWBIE_CHECKPOINT_TASKS` [index.html:13967](index.html:13967), is an
unrelated onboarding feature).

```
ZONE6_MID_PLAY_OWNER_DECISION = TRUE_PAUSE_RESUME_REQUIRED
```

Approved as a future high-risk dedicated runtime sprint. Restaging as two separate short trial cycles was
considered and explicitly rejected — it would preserve the shot count but lose the actual reason
`MID_PLAY` exists (interrupting the player's own in-progress certainty, not just sequencing two fights).
Not authorized for implementation in this sprint.

## 11. Optional Guardian state

| Spirit | Internal ID | Unlock |
|---|---|---|
| 水靈馬 (Water Spirit Horse) | `ink_drop_kelpie` | **Guaranteed starter** — `PET_STARTER_KEY` (`app.py:2017`) |
| 棋罐龍 | `star_shell_hatchling` | 2nd/3rd slot via `PET_UNLOCK_THRESHOLDS = [1, 11, 16]` (`app.py:2287`) |
| 虛空貓 | `whispering_void_kit` | Same threshold mechanism |

Ownership source of truth: **`pet_collection`** table (`app.py:3660-3665`, composite key
`user_id, pet_key`) — this is the real ownership ledger, distinct from `user_pets` (which only snapshots
the single currently-equipped companion) and distinct from `PET_CATALOG` (static definitions, ownership-
agnostic). Query: **`_pet_owned_keys(conn, uid)`** (`app.py:2321-2323`).

Zone 10 Shot 10 rendering rule:

```
ink_drop_kelpie      : ALWAYS
star_shell_hatchling : SHOW IF OWNED (via _pet_owned_keys())
whispering_void_kit  : SHOW IF OWNED (via _pet_owned_keys())
```

Never derived from `PET_CATALOG` alone (ownership-agnostic) or from the currently-equipped pet in
`user_pets` (only reflects the active companion, not full ownership history).

## 12. Source / Eastern Guardian silence

Zone 10's Eastern guardian ("silent, gesture only") and the Source of Black-White Order ("structurally
incapable of ever speaking") both have **zero dialogue** anywhere in their appearances. As of the
correction in §2, Zone 10 Shot 6 extends this to the Hero as well — the entire confrontation is silent.
Production's existing narration fallback (`finishAudioSilently`, `computeShotHoldMs`,
[index.html:13472-13522](index.html:13472)) already supports a dialogue-free shot natively — no runtime
work required.

## 13. Zone 9 = THE CHOICE, Zone 10 = THE FINAL MOVE

The two climaxes are structurally distinct, not a duplication, despite both using "final move of a
thousand-year game" language:

- **Zone 9 — THE CHOICE.** The Gods demand the board collapse to one color; the Hero refuses. Protected
  line 「一色的棋盤，是死的。」 now lands at **Zone 9 Shot 10** (relocated from the recovered storyboard's
  Shot 11). Zone 9 Shot 11 is redefined: the visual consequence of failed convergence — black remains
  black, white remains white, neither disappears, the Gods' single-color overlay fails, the Source/wound
  becomes visible. **No five-relic narration in Zone 9** — the old "木劍、石痕、果實、龍鱗、棋心…整盤棋，
  終於，活了" language belongs to the recovered storyboard only and is not canonical here.
- **Zone 10 — THE FINAL MOVE.** The literal last empty point on the physical board is filled at the
  Source's own temple. The relic-chain/journey-memory payoff belongs here, at **Shots 7–8**, not Zone 9.

## 14. Go Logic Gate

`GO_LOGIC_GATE: OPEN`. Zone 10's half-point duel (Scene 3 / Shot 4) is confirmed cinematic-only, not a
disguised interactive encounter (`docs/planning/e10_zone10_lifecycle_decision_v1.md`, isolated branch) —
no legal half-point-margin SGF is required for that beat. What remains open per this sprint: the actual
half-point board state referenced in that vision/montage still needs real design/verification before any
visual asset depicting it is produced — it cannot be improvised art. Confirmed: the unrelated deferred SGF
`69816` does not exist anywhere in this repo and must not be reused for this or any other purpose.

## 15. Anna A/B Gate

`ANNA_AB_GATE: OPEN`. Candidate narrator line 「……半目。」 (voice: Anna) is proposed for **Zone 10 Shot 8**
(after the Final Stone / half-point resolution — corrected from an earlier, wrong placement at Shot 4).
Remains `A/B_TEST_ONLY`, not canonical, until an actual audio A/B test exists. Do not treat this line as
settled dialogue anywhere in `e10_final_screenplay_v1.md`.
