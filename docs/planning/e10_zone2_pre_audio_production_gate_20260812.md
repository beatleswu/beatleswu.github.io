# E10 Zone 2 Pre-Audio Production Gate 001

`E10_ZONE2_PRE_AUDIO_PRODUCTION_GATE_001`

This evidence is intentionally stopped after Phase 0–2. It does not generate
audio, wire the new art into runtime, change progression, or touch Production.

## Repository identity

| Field | Value |
|---|---|
| `BASE` | `fc8cd5dfe9451a7df872ef8866566b785acc6a70` |
| `BASE_TREE` | `f9a40542ae8a84a04eb86eed695d693713d7aaae` |
| `WORKTREE` | `D:/e10-zone2-complete-production-20260812-01` |
| `BRANCH` | `codex/e10-zone2-complete-production-001` |
| `WORKTREE_COMMON_DIR` | `D:/go-website/.git` |
| `CANONICAL_CHECKOUT` | preserved; existing dirty/untracked content untouched |

## Phase 0 — Zone 1 voice/audio canon

The actual current runtime has three presentation phases:

1. Zone Entry / `PRE_PLAY`: Shots 1–6. `finishIntroFilm()` marks the server
   intro-seen record for `first_entry`, then returns to the Zone Card. A seen
   first-entry request stops at the Zone Card rather than replaying the film.
2. Boss Ready: Shots 7–8. `_maybeTriggerZone1BossReadyFilm()` reacts to the
   server-derived readiness predicate, marks a separate account-scoped
   presentation flag, plays the two-shot announcement, and returns to the map.
   It never starts the Lord Trial.
3. Post-Clear: Shots 9–10. `_triggerZone1PostClearFromBossWin()` is the
   authoritative Lord-success entry. A pending/seen pair makes this
   presentation recoverable and idempotent; `finishPostClearFilm()` records the
   presentational seen state and then visualizes the already-server-derived next
   zone.

The replay button is presentational: it replays the currently active phase or,
for Zone 1/2, starts `manual_replay`; it never re-submits the intro-seen marker,
progress, rewards, settlement, unlock, or cinematic authority.

Zone 1 canon recovered:

- `ZONE1_DIALOGUE_RECOVERED=28/28` bilingual dialogue entries, mapped in the
  runtime to `assets/e10/audio/zone1/dialogue/`.
- `ZONE1_RUNTIME_AUDIO_RECOVERED=43/43` governed files; all manifest hashes and
  sizes matched in the isolated worktree.
- `PROTAGONIST_VOICE=Hero; en Anvay (6aOpkucJD6a4vTXyUKon), zh-TW Roy (XXxvxx0YUt8icTEFE3c6)`.
- `ELDER_VOICE=en Daniel (onwK4e9ZLuTAKqWW03F9), zh-TW Christopher (NdEhweaiOdufFIiyNPdk)`.
- `MESSENGER_VOICE=en Liam (TX3LPaxmHKxFdv7VOQHJ), zh-TW Jun (5s3UifUu3OJ90z17rRMA)`.
- `WATER_SPIRIT_HORSE_AUDIO_IDENTITY=NONVERBAL`; Shui is addressed in Shot 2,
  but the shipped script/runtime gives the companion no human line and no
  creature-vocal asset.
- `VOICE_PROVIDER_DATA_AVAILABLE=PARTIAL`: ElevenLabs is established by the
  local Zone 1 tooling and lock, but no provider field is stored per asset.
- `VOICE_ID_DATA_AVAILABLE=YES`.
- `VOICE_SETTINGS_AVAILABLE=NO` in the committed lock records.
- BGM/ambience/SFX are listed in `e10_voice_cast_bible_v1.md` and governed by
  the committed Zone 1 package/locks.

## Phase 1 — final-art intake

Attachment order was used exactly as supplied: attachment 01 → Shot 1 through
attachment 10 → Shot 10. All ten sources were JPEG, 1280×720, and were converted
without crop, resize, recompose, or creative alteration using the existing E10
runtime convention (`PIL WEBP quality=82, method=6`). The resulting files are
uncommitted intake artifacts at stable paths; `index.html` was not rewired.

| Shot | Source attachment | Source SHA-256 | Source bytes | Final repo path | Final SHA-256 | Final bytes | Visual/semantic intake note |
|---:|---|---|---:|---|---|---:|---|
| 1 | `.../1-照片-1.jpg` | `b929b3d7989cce10954df7eadfe0f5c1b0b5f2c22a5c58c34efc9c7a929962cb` | 269835 | `assets/storyboards/e10_z2_shot01.webp` | `cfcb2c6b45c9ced4708a982bdab6c799b496169b2d24768997a4cc85ee90c2f5` | 135686 | Arrival / plains / Hero + small Water Spirit Horse; no Herder |
| 2 | `.../2-照片-2.jpg` | `8554edf70d2dfa80392fdef837a5165bdfc4f745304943cf2146f4b728dd0215` | 206104 | `assets/storyboards/e10_z2_shot02.webp` | `d90ac3ffd9d4ba391ba49279d88e6f5b8fc60c53ce77935a5865930cb90ba11f` | 91622 | Empathy / frightened slime; Hero crouches; companion present |
| 3 | `.../3-照片-3.jpg` | `d615d39a03d31e2e6837d864ee132920b22774d15d49dc2339efe6f03ff3b984` | 233340 | `assets/storyboards/e10_z2_shot03.webp` | `4bc0b672e627422cb0e4c159cf2cf98d26d9ede0ceab79faa557e383a9322c8d` | 110872 | Young Herder arrives with frightened slime and points toward the hive |
| 4 | `.../4-照片-4.jpg` | `9686b865b6d9f6bee86dd3a953dc5b9b0fdd33426ff117ebee343e438e92e1b0` | 316037 | `assets/storyboards/e10_z2_shot04.webp` | `5b993885c5167bf275117916ca83c8e1b15fa5d90a0d2b473094d76d75dd3e77` | 170300 | Full honeycomb-invaded cliff cave reveal; ends FIRST_ENTRY |
| 5 | `.../5-照片-5.jpg` | `0508fab1049209cf52a966c14b72db40b0f9f5fa04ff766e0c08d4debc67422b` | 293282 | `assets/storyboards/e10_z2_shot05.webp` | `155e483a6ac5f9c0107a9ee2b38ede22d034ad3056ceebba7c478ac8c2602153` | 156526 | Escalation; fleeing slimes and intensified swarm; no Herder required |
| 6 | `.../6-照片-6.jpg` | `3692197a54245f70bb277b7598c6bbce453ec8d1f86cf055a728fa2d28458268` | 317550 | `assets/storyboards/e10_z2_shot06.webp` | `5440d67a82ae5d0d742956486aee0289b7f8ef86b4a2da9d8e9481594fb396ac` | 170266 | Giant blue Slime Lord emerges from the hive; not a bee humanoid |
| 7 | `.../7-照片-7.jpg` | `ad968c107a438bd8d54b6aed4e4d01fb5fe66c40f1d34f363ae25624b1c691ee` | 299245 | `assets/storyboards/e10_z2_shot07.webp` | `e869291c301d225fb4e449c03adeb587eb25b50b50f16af37747008cf3e6df0e` | 156582 | Hero advances for challenge handoff; visible circular/taiji-like torso mark is flagged, not altered |
| 8 | `.../8-照片-8.jpg` | `cfe4acd88552c1a9a8ad6f9cb3b3f00933ee5010efc8abc0acc324ab108d36e0` | 328536 | `assets/storyboards/e10_z2_shot08.webp` | `e6a4baa3630024a2aff01104a8bc545d4e72c8cc5a76e72b54d48d5cc483b95c` | 173096 | Lord defeat / fall; no celebratory dialogue required; same mark remains visible |
| 9 | `.../9-照片-9.jpg` | `1e6f668f39905a84aa7698288f631fa461cc37285f0fc327a214b3a5068cb537` | 313950 | `assets/storyboards/e10_z2_shot09.webp` | `459e18af2bb892c8e1a8d26701d37f486903058075f85e515b0469cba5ca2cb2` | 168048 | Plains recover; slimes calm; emotional release |
| 10 | `.../10-照片-10.jpg` | `ebfd2079f6120f7b329a0809242a33d891a24a35fa4fd97cdd622c056979a7ca` | 269797 | `assets/storyboards/e10_z2_shot10.webp` | `0b891452628efc985eea25766569b10c51a593276035e994a10d3b0584f23324` | 133430 | Forward route hook; not a finale or final destination |

`ZONE2_FINAL_ART_COUNT=10` and `SHOT_MAPPING_UNAMBIGUOUS=YES`.
The four existing `go_slime_plains_scene_01.webp`–`04.webp` files were not
overwritten, and the new `e10_z2_shot01.webp`–`10.webp` files are not yet runtime
wired. This keeps Phase 1 separate from Phase 5 integration.

The current `k21_25` base locale still contains the older legacy
`assets/storyboards/go_slime_plains_scene_01.webp`–`04.webp` and
`go_slime_plains_voice[_en]_01.mp3`–`04.mp3` mapping. The merged Zone 2
foundation overlays its pending 4/3/3 phase slots but does not silently promote
those legacy bytes to the new Owner-selected canon. They were not changed,
auditioned, or copied in this execution. `ZONE2_AUDIO_GENERATED=NO` therefore
means no new or locked Zone 2 audio was generated; it does not claim that the
repository contains no historical Zone 2 audio bytes.

## Phase 2 — script recovery and art comparison

Sources recovered:

1. Tracked `docs/planning/e10_final_screenplay_v1.md`: READY_FOR_OWNER_REVIEW,
   with an explicit warning that some master-screenplay dialogue is pending and
   recovered storyboard text is not canonical dialogue.
2. Local-only planning source in the preserved canonical checkout,
   `docs/planning/e10_adventure_cinematic_script_v2.md` (`v2.2`,
   `STORYBOARD_READY`) and its detailed
   `e10_zone2_storyboard_notes_v0.1.md`. These are not in the audited
   `origin/master`; they are historical planning evidence, not a silent runtime
   lock.
3. Current `index.html` `_zone2CinematicPhaseSlots()`: stable 4/3/3 slots with
   `ownerAudioPending=true`, `ownerArtPending=true`, placeholder images before
   this intake, and current provisional text. The older base-locale 4-shot
   timeline remains a legacy mapping until Phase 5 integration.

| Shot | Historical story function | Historical speaker/dialogue recovered | Final art fit | Recommendation / change required |
|---:|---|---|---|---|
| 1 | Arrival / establish the weeping field | v1 and v2: `SILENCE`; Hero and Shui enter the plains | PASS — wide golden plains, Hero + companion | Keep silent unless Owner Script Lock explicitly chooses a short arrival line. |
| 2 | Empathy / frightened slime | v1: Hero — `等等……牠在發抖。牠不是要咬我們……牠在怕。`; v2: Hero — `牠們在發抖。不是想攻擊我們。是在害怕什麼。` | PASS — exact empathy composition | Candidate empathy line belongs here visually. Current runtime provisional slot repeats the v2 idea in Shot 6; do not ship that placement without Owner decision. |
| 3 | Herder brings the local clue | v1: Herder — `小心鞋子。這幾天，連地都怪怪的。` / Hero — `牠們也是最近開始的嗎？`; v2 storyboard: no spoken line | PASS — young Herder, frightened slime, and hive direction are readable | Owner must choose silent visual introduction or a minimal testimony line; do not revive v1 wording automatically. |
| 4 | Cause testimony / transition to the hive | v1: Herder — `這些小傢伙以前可黏人了。趕都趕不走。直到幾天前……蜂巢裡開始傳出那個聲音。然後，牠們就成這樣了。`; v2: Herder — `以前這片草原不是這樣的。自從蜂巢那邊出了問題，牠們就沒睡過一天安穩覺。` | PASS — the selected image is a full honeycomb-overgrown cliff cave reveal and therefore advances the historical reveal one shot earlier | This is both a dialogue conflict and a shot-role shift. Owner must lock the line/placement before audio; the current 4/3/3 runtime phase is not historical screenplay proof. |
| 5 | Infected hive escalation | v1/v2 historical image role: the hollow hive / cave core reveal, with silent environmental escalation | PASS — Hero/companion approach, bees and fleeing slimes, blue cave glow | The Owner-selected art moves the full cave reveal to Shot 4; keep Shot 5 silent and use environmental audio only after Audio Lock. |
| 6 | Swarm Lord reveal | v1/v2: silent visual reveal; current runtime provisional copy includes the Shot 2 empathy line plus reveal text | PASS — giant Slime Lord, not bee humanoid | Keep the reveal nonverbal unless Script Lock says otherwise; do not let provisional runtime text become canon. |
| 7 | Challenge handoff; then return control | v1/v2: Swarm Lord — `為什麼要在意平衡？吞噬一切，才是真正的自由。` (the v1 screenplay also contains an older hunger-line variant) | PASS — Hero confronts the giant Lord | Preserve the Owner-selected line/variant only after Script Lock; no automatic Lord Trial. Flag the visible torso mark for Owner art decision. |
| 8 | Lord defeat / shared sickness begins to lift | v1/v2: silent visual resolution; current runtime has descriptive, audio-pending copy | PASS — defeat/fall without a victory pose | Keep silent or nonverbal unless Owner approves a line; no post-clear authority is created by the shot. |
| 9 | Plains recover / Hero states theme | v2: Hero — `牠們不是我們的敵人。我們只是，遇到了同一場病。`; tracked v1 explicitly says the earlier optional Hero line `好多了。` was cut and Shot 9 is silent | PASS — peaceful recovery | This is a real script conflict; Owner must choose v1 silence or v2 Hero line before audio generation. |
| 10 | Forward journey / northeast hook | v1/v2: silent; hive-crystal fragment pulses northeast toward the next wound/Goblin Caves | PASS — forward-looking valley, not finale | Keep silent; show the visual hook only. Do not implement Zone 3. |

### Script conflicts and gaps

- The tracked v1 screenplay and local v2.2 planning source disagree on dialogue
  placement/content for Shots 2–4, 6, 7, and 9. They also use an older
  `Shots 1–7 PRE_PLAY → Shots 8–10 POST_CLEAR` playback grouping, whereas the
  current Owner/runtime contract is `FIRST_ENTRY 1–4 → gameplay → BOSS_READY
  5–7 → Lord → POST_CLEAR 8–10`. The current art moves the full cave reveal
  from the historical Shot 5 role into selected Shot 4. The integration contract
  gives higher authority to a later dialogue/continuity polish pass, but no
  Owner `ZONE2_SCRIPT_LOCK` has been recorded in this execution.
- Current runtime stable slots are intentionally provisional: they set
  `ownerAudioPending=true`, use placeholder art before this intake, and are not
  evidence that their text placement is locked.
- The final images themselves are semantically coherent with the requested
  functions, but Shot 7–8 carry a visible circular/taiji-like mark on the Lord's
  torso. This was preserved exactly and is an Owner visual review item, not a
  silent cleanup.

### Proposed minimal adaptations (pending Owner Script Lock)

1. Keep the attachment order and all ten image identities unchanged.
2. Use the already-merged current runtime phase slots only as the implementation
   boundary: FIRST_ENTRY 1–4, gameplay, BOSS_READY 5–7, explicit Lord challenge,
   Lord Trial, then POST_CLEAR 8–10. This is an Owner/runtime contract, not a
   claim that the historical v1/v2 screenplay already used that grouping.
3. Resolve the Shot 2 empathy line, Herder line placement, and Shot 9 line/silence
   conflict in the Owner Script Lock. Do not regenerate or rewrite the story.
4. Remove the current provisional Shot 6 empathy wording if the Owner assigns it
   to Shot 2; this is a later runtime integration change, not performed here.

## Gate state

```text
ZONE1_VOICE_AUDIO_AUDIT=PASS (read-only)
ZONE1_DIALOGUE_RECOVERED=28/28
ZONE1_RUNTIME_AUDIO_RECOVERED=43/43
VOICE_CAST_BIBLE_V1=CREATED (worktree-only, uncommitted)
ZONE2_FINAL_ART_COUNT=10
ZONE2_SHOT_MAPPING=1..10 exact attachment order
ZONE2_ASSET_INTAKE_STATUS=PASS (uncommitted deterministic WebP derivatives)
ZONE2_AUDIO_GENERATED=NO
ZONE2_RUNTIME_INTEGRATED=NO
ZONE2_MAP_HANDOFF_CHANGED=NO
ZONE3_STARTED=NO
OWNER_ZONE1_VOICE_CANON_CONFIRMED=PENDING
ZONE2_SCRIPT_LOCK=PENDING
ZONE2_AUDIO_LOCK=NOT_STARTED
```

No `secret_key.txt` was read, hashed, moved, copied, staged, or modified.
