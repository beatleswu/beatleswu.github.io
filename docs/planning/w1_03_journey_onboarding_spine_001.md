# W1_03 — First-session journey onboarding spine

Status: implementation prepared; shell wiring and Zone 3 presentation remain separately gated.

Task: `W1_03_JOURNEY_ONBOARDING_SPINE_001`

Canonical base: `616d51b17abe010de1e862382ca4db7bec65936f`

Canonical tree: `f3882ecee3980d310817096e3a15bc469683e9cd`

## Audit of the connected journey at the canonical base

The default production path is the legacy Learn/Adventure shell. The E9
component shell is wired into the page but its production flags are false, so
it is not the connected first-session path at this base.

The actual path is:

1. Existing account onboarding resolves through the naming/profile flow in
   `index.html`; the flow is not a journey guide and does not introduce the
   first Adventure sequence.
2. `window.onload` initializes the existing question/SRS runtime and the
   legacy home/map surface. `loadMapProgressStatus()` reads
   `/api/adventure/bootstrap`; the server response supplies zone state.
3. A ready map node calls the existing `startAdventureStage()` and the
   existing intro-film path, then `enterAdventureZoneInPage()` selects a
   server-issued/eligible question and calls the canonical question loader.
4. `onBoardClick()` submits through the existing review and Map Battle paths.
   Committed results drive the existing explanation, hit/defeat presentation,
   XP, loot, appearance, pet, and quest surfaces.
5. The existing encounter continuation returns the player to the map or to
   the existing Lord/boss flow. `finishBossBattle()` consumes the server
   reward projection and refreshes authoritative Adventure state.

This is functional, but it is not an authored first-session spine: there is no
single connected presentation for world reveal, hero/companion introduction,
first question feedback, first victory, reward/growth explanation, and the
next server-owned action. The existing Zone 1/2/3 surfaces remain the source
of gameplay truth. Existing Zone 3–10 intro-story details are deliberately not
re-authored here; they remain blocked by the WORLD style lock.

## Smallest safe spine

`journey_onboarding_spine.js` is a presentation-only finite-state controller.
It accepts only bridge events that identify the existing authority source and
returns a render state. It never writes progression, creates rewards, equips
items, chooses a question, or settles battle state.

The state is the latest contextual card being shown. An accepted event proves
the preceding boundary and advances the card to the next authored step. The
first `opening-ready` event activates the card without advancing it, so the
opening can be seen before the world-reveal boundary arrives.

| Card | Accepted boundary | Required authority | Safe output |
| --- | --- | --- | --- |
| Opening | Existing authenticated first-session signal | Existing onboarding/profile state | Short opening hint |
| World reveal | Existing shell is visible | Legacy or E9 shell state | Map-orientation hint |
| Hero / companion | Existing profile/avatar and companion are ready | Existing profile presentation | Character introduction |
| First Adventure | Canonical Zone 1 entry started | Existing Adventure entry | One clear action |
| First question | Canonical question and board are ready | Existing question runtime | Board-first prompt |
| Answer feedback | Review result is committed | Existing SRS review | Feedback hint |
| Attack / hit | Canonical battle result is correct with positive damage | Map Battle V1 | Hit explanation |
| First victory | Canonical battle result says the monster is defeated | Map Battle V1 | Victory pause |
| Reward reveal | Server reward projection is committed and non-replay | Existing Battlefield reward consumer | Show only returned reward/status |
| XP / growth | Server XP/appearance projection is committed | Existing presentation effects | Explain returned growth |
| Next action | Bootstrap returns a primary/next action | Existing Adventure bootstrap | Point to that action |
| Zone progression | Bootstrap says Zone 2 is enterable | Existing Adventure bootstrap | Route guidance |
| Zone 3 arrival | Bootstrap says Zone 3 is enterable/current | Existing Adventure bootstrap | Boundary only; no style details |

The module uses the canonical first three keys only for authority checks:
`k26_30`, `k21_25`, and `k16_20`. It does not add a Zone 3 visual name,
monster, biome, palette, asset, cinematic, or layout.

## Replay and skip contract

- Skip hides the current contextual hint only. It does not advance the state,
  mark a cinematic seen, write storage, settle an encounter, or grant a
  reward.
- Replay re-renders a previously completed contextual hint only. It does not
  call the generic cinematic replay model and does not change progression.
- Existing intro-film and post-clear replay behavior stays in
  `js/game/cinematic_replay.js` and the established `index.html` bridge.
- Reward events require an existing non-replay server projection and a stable
  `rewardEventId`. The controller remembers accepted IDs in memory only and
  rejects a repeated ID; it never synthesizes a second reward.
- A replay or reward event that lacks the required server facts is ignored.

## Exact later shell-wiring patch

This opening task intentionally leaves the three shared-shell files unchanged.
The Coordinator/shell-writer pass can apply this bounded patch:

1. `index.html`

   - Add the versioned stylesheet `/css/e9/journey_onboarding.css?v=w1-03-v1`.
   - Load, in order, `journey_onboarding_content.js`,
     `journey_onboarding_spine.js`, and `journey_onboarding_view.js` after the
     existing E9 scripts.
   - Add `#e9-journey-onboarding-slot` inside `#e9-adventure-shell` near the
     world-stage slot. Do not change the legacy map markup.
   - At existing, already server-backed boundaries, dispatch
     `journey:onboarding-event` with `{type, detail}` for the events listed in
     `content.eventTypes`: session-ready, shell-visible, avatar/companion
     ready, canonical Adventure start, question/board ready, committed review,
     Map Battle hit/defeat, committed reward projection, committed XP
     projection, bootstrap next action, bootstrap Zone 2 progression, and
     bootstrap Zone 3 arrival.
   - Use one small bridge helper so the view receives no raw application
     callbacks:

     ```js
     function emitJourneyEvent(type, detail) {
       document.dispatchEvent(new CustomEvent('journey:onboarding-event', {
         detail: { type: type, detail: detail }
       }));
     }
     ```

     The detail contract is exact and intentionally redundant with the
     existing authority source so a client-only claim cannot advance a card:

     ```text
     opening-ready: authenticated=true, firstSession=true,
       authoritySource='existing_onboarding'
     world-revealed: visible=true, presentationState='legacy'|'e9',
       authoritySource='existing_shell'
     hero-companion-introduced: heroReady=true, companionReady=true,
       authoritySource='existing_profile'
     adventure-started: started=true, authoritative=true, zoneKey='k26_30',
       source='canonical_adventure'
     question-ready: authoritative=true, boardReady=true, questionId,
       zoneKey='k26_30', source='canonical_question_runtime'
     review-committed: committed=true, authoritative=true, questionId, grade,
       source='canonical_srs_review'
     attack-resolved: authoritative=true, result='CORRECT',
       damage_to_monster > 0, source='map_battle_v1'
     encounter-victory: authoritative=true, monster_defeated=true,
       source='map_battle_v1'
     reward-revealed: authoritative=true, rewardProjection=true,
       rewardEventId, replay=false, reward or explicit rewardStatus,
       source='battlefield_reward_consumer'
     growth-feedback: authoritative=true, xpProjection=true, xpGain or
       ranked_up, source='committed_review_presentation'
     next-action: authoritative=true, nextAction or primaryAction with kind,
       source='adventure_bootstrap'
     zone-progressed: authoritative=true, zones containing enterable 'k21_25',
       source='adventure_bootstrap'
     zone3-arrived: authoritative=true, zoneKey/currentZoneKey='k16_20',
       zones containing enterable 'k16_20', source='adventure_bootstrap'
     ```
   - The opening bridge must pass `authenticated: true`,
     `firstSession: true`, and `authoritySource: 'existing_onboarding'` from
     existing server/profile state. It must not infer first session from
     browser storage.

2. `js/e9/shell.js`

   Add one non-critical slot entry using the existing `e9Shell` gate:

   ```js
   { flag: 'e9Shell', component: 'journey_onboarding',
     selector: '#e9-journey-onboarding-slot',
     src: '/components/adventure/journey_onboarding.html' }
   ```

   Keep the existing five-slot count contract updated in that shell-writer
   change. A fragment failure must remain non-critical and must not recover or
   alter the legacy shell.

3. `i18n.js`

   Add the shared catalog entries for the copy keys below, in the existing
   locale structure. Do not create a dictionary in `js/e9/`.

   ```text
   e9.journey.opening.kicker: A NEW PATH / 新路線開啟
   e9.journey.opening.title: Your first move starts here / 你的第一步，從這裡開始
   e9.journey.opening.body: A short guide will stay beside you while you make the first journey. / 短短的提示會陪你完成第一次旅程。
   e9.journey.world_reveal.kicker: THE WORLD OPENS / 世界展開
   e9.journey.world_reveal.title: Choose one clear next step / 只看一個清楚的下一步
   e9.journey.world_reveal.body: The map shows where you are; your next action stays tied to the server's adventure state. / 地圖會顯示你的位置；下一步只依照伺服器的冒險狀態。
   e9.journey.hero_companion.kicker: YOUR PARTY / 你的隊伍
   e9.journey.hero_companion.title: Meet your hero and companion / 認識你的英雄與夥伴
   e9.journey.hero_companion.body: Your appearance and companion come from your existing profile. They will react while you learn. / 外觀與夥伴來自既有角色資料；修行時他們會回應你。
   e9.journey.first_adventure.kicker: FIRST ADVENTURE / 第一次冒險
   e9.journey.first_adventure.title: Start with Beginner Village / 從圍棋新手村開始
   e9.journey.first_adventure.body: Select the ready Zone 1 action to enter the first encounter. / 選擇已開放的第 1 區行動，進入第一次遭遇。
   e9.journey.first_question.kicker: THE FIRST TEST / 第一次試煉
   e9.journey.first_question.title: Read the board, then choose a move / 看懂棋盤，再選一手
   e9.journey.first_question.body: The board is the lesson. Try the move that gives your stones a way forward. / 棋盤就是課題；試著找出讓棋子繼續前進的一手。
   e9.journey.answer_feedback.kicker: FEEDBACK / 回饋
   e9.journey.answer_feedback.title: See what your move changed / 看看這一手改變了什麼
   e9.journey.answer_feedback.body: The result comes from the canonical review path. / 結果來自既有的正式判定流程。
   e9.journey.attack_hit.kicker: ON THE BOARD / 棋盤交鋒
   e9.journey.attack_hit.title: A correct read creates an opening / 答對，就能打出破口
   e9.journey.attack_hit.body: Your hit and the encounter state are shown by the battle runtime. / 命中與遭遇狀態由戰鬥執行系統顯示。
   e9.journey.first_victory.kicker: FIRST VICTORY / 首次勝利
   e9.journey.first_victory.title: The path is open / 道路開啟
   e9.journey.first_victory.body: Take a breath. Your first encounter is complete. / 喘口氣；你的第一次遭遇完成了。
   e9.journey.reward_reveal.kicker: A REWARD FOR THIS RUN / 這次修行的獎勵
   e9.journey.reward_reveal.title: See what the server granted / 查看伺服器發放的內容
   e9.journey.reward_reveal.body: Rewards appear only from the committed result; a replay never grants them again. / 獎勵只會來自已提交的結果；重播不會再次發放。
   e9.journey.growth_feedback.kicker: GROWTH / 成長
   e9.journey.growth_feedback.title: Your practice is adding up / 你的修行正在累積
   e9.journey.growth_feedback.body: XP and appearance updates are read from the committed response. / XP 與外觀更新只讀取已提交的回應。
   e9.journey.next_action.kicker: NEXT STEP / 下一步
   e9.journey.next_action.title: Keep the path moving / 讓旅程繼續
   e9.journey.next_action.body: Follow the server-owned next action when you are ready. / 準備好後，依照伺服器提供的下一個行動前進。
   e9.journey.zone_progression.kicker: THE ROAD AHEAD / 前方的道路
   e9.journey.zone_progression.title: The route opens one step at a time / 道路一步一步展開
   e9.journey.zone_progression.body: Use the map's current action to move from one region to the next. / 用地圖上的目前行動，從一個區域走向下一個區域。
   e9.journey.aria_label: First-session journey guide / 首次旅程指引
   e9.journey.actions_aria_label: Journey guide actions / 旅程指引操作
   e9.journey.skip: Skip this hint / 略過這段提示
   e9.journey.replay: Replay this hint / 重播這段提示
   ```

   The body copy remains in the same shared catalog and should retain the
   short, contextual tone specified by this document. Zone 3 has no copy key
   until WORLD style lock supplies the approved presentation language.

4. `js/game/cinematic_replay.js`

   No change is required. Existing replay remains the only cinematic replay
   authority and remains presentation-only.

## Explicit non-goals

- No `app.py` change.
- No database migration or new endpoint.
- No production mutation, deploy, payment change, merge, or self-merge.
- No change to `index.html`, `i18n.js`, or `cinematic_replay.js` in this lane.
- No Zone 3–10 art/style/story invention before WORLD style lock.
