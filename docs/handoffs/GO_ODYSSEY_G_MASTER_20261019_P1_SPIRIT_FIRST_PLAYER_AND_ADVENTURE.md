# Go Odyssey｜G MASTER 首次棋靈取得 → 冒險 WGo → XP／主角升級／地圖｜2026-10-19

## 安全基準、結論
- 起點：本機候選 `1ce919efb21a0071c6d6c6ab83bc482f9a6cc9ba`，分支 `candidate/go-product-integrated-20261019`，工作樹 `D:\go-odyssey-sixroute-20261019\g`。
- 範圍：經授權 beatles 的本機隔離資料，沒有改 GitHub `master`，沒有寫 Oracle 正式站、Test02，沒有正式 Build／Push／Merge／Deploy。
- **結論：首次棋靈授權問題已定位；在明確受控遷移的一次性 PostgreSQL 下，新玩家首次選取棋靈、原版 WGo 落子、伺服器判題、XP、LV2、地圖進度以及正式 G009 英雄殿夥伴分頁，桌面和觸控模擬均 PASS。**
- 這是 Product 的隔離測試／本機候選；真 iPad Safari、真 Test02 與正式部署仍是獨立 Owner Gates，不得以 Chrome 模擬取代。

## 503 的唯一可重現原因與正確處置
- 以前 `POST /api/pet/choose` 503，返回 `COMPANION_OPERATION_SCHEMA_UNAVAILABLE`。經正式 `app.init_db()` 建立的一次性 PostgreSQL **不含** `companion_operations`；`migrations/companion_operations_v1.py` 註明必須由受控釋出程序套用，不得擅自加進 app 每次啟動的自動遷移流程。
- 修復 **隔離測試環境**：明確呼叫既有 `migrations.companion_operations_v1.upgrade` 與 `migrations.spirit_evolution_events_v1.upgrade`；驗證 schema 完整性及重跑冪等。這不是放寬權限、更改 Production DB，也沒有造假伺服器授權。
- 真 Flask + native PostgreSQL：未遷移時 503 且資料未寫入；遷移後 200 獲得真正 `ink_drop_kelpie`，相同 operation_id 再送 200 回放原結果，不重發資源；不同用途重用同一 operation_id 為 409，不准第二次起始領取；`user_pets` 一筆、贈品各正確、兩筆權威獎勵 outbox，操作狀態一筆 COMPLETED 加一筆預期 FAILED。
- **正式站是否缺乏此 schema 仍未檢查。** 上線前需由具權限的 DB 管理者透過獨立受控遷移／核驗執行；未核驗前不可宣稱 Production 503 已消除。

## 找到並修正另一個實際產品問題
- 原本 `index.html` 的 `loadQuizPet()` 可由首頁閒置初始化與冒險棋盤初始化同時呼叫。兩個呼叫共用舊 `/api/pet/status` 快照（尚未取得棋靈），因而對 `/api/pet/choose` 發出 **兩次不同 operation_id**：測到 `[200,409]`。後端拒絕正確，但前端仍送出多餘請求。
- 修改 `index.html`：只增加單次執行的 `_starterSpiritAutoChoosePromise`，等待同一個伺服器確認的授權回覆，先公布後端已確認的 `_petStatusPromise` 快照再釋放單次執行狀態；失敗仍保留既有 fail-closed，絕不在瀏覽器自行標記擁有棋靈。
- 原版 `index.html` 重新驗證，真正的 POST 由 `[200,409]` 收斂為 **`[200]`**，無 503／409，`companion_operations` 完成一次、`user_pets` 一筆；桌面與平板均 PASS，沒有因成功而略過原後端。

## 玩家路徑驗收
1. 一次性 PG 初始化隔離玩家、隔離 SGF 題，並**明確核准式套用**上述受控 migration（不改 `app.init_db` 原有政策）。
2. 瀏覽器載入真正 `index.html`，透過原有 `loadQuizPet` 初始化取得正式伺服器 `PET_STARTER_KEY`，只有一次 POST 200；不存在 503／409。
3. 原版冒險開場動畫由玩家可見的「略過動畫」→「開始修行」操作，原版 WGo 的 D4 由滑鼠點擊／Chrome 平板觸控觸發真正 `POST /api/adventure/map-battles/v1/answers`，伺服器回 CORRECT。
4. 玩家累積 XP **119 → 135**，等級 **LV1 → LV2**，本級 **15／160 XP**、進度條 **9%**；相較未持有棋靈時的 **119 → 134**，多出的 1 XP 是原有墨滴水靈馬正常答題 XP 加成（`_pet_player_xp_bonus`），**不是重複入帳**。
5. 伺服器新手村 seen／correct 均 **0 → 1**，Boss cleared 仍 false；完整重新整理後仍一致。
6. 進入真 `/hero?tab=character`，由伺服器資料渲染 LV2、15／160 XP、累積 135；再**點選真正可見的 G009 `[data-g009-hub-tab="pet"]`**，伺服器授權的 `ink_drop_kelpie` 夥伴卡可見。這不是隱藏的舊 `#hero-tab-pet` 或另造 DOM。
7. 分離的無棋靈／純 API 用例仍驗證 119 → 134、同一答案重送去重、重新登入 Session 狀態保留。

## 驗收結果與收據
- 新 E2E 完整回歸：**140 PASS、2 SKIP、0 FAIL**，見 `docs/handoffs/GO_ODYSSEY_P1_SPIRIT_AND_WGO_FULL_REGRESSION_R2_20261019.xml`。
- 原版 Chrome Desktop／Chrome Tablet Emulation：各 **10／10** 真 UI 路徑檢查通過，包含獲得棋靈與 G009 夥伴分頁。10 項畫面檢查包含在 pytest 測試內，不應額外加總當作獨立測試案例。
- R1 `GO_ODYSSEY_P1_GOVERNED_SPIRIT_NEW_PLAYER_E2E_20261019.xml` 留存首次英雄殿分頁測試指向已隱藏舊按鈕的誤選結果（新式 G009 才是玩家可見分頁），R2 已修正測試操作並全面通過；**沒有因此修改 G009 產品程式**。
- 新增 `tests/test_20261019_first_player_companion_native_pg.py`：正反遷移、重送防重、操作 ID 衝突、獎勵 outbox 真資料測試。
- 更新 `tests/test_20261019_adventure_answer_level_e2e.py` 隔離 B023 設備準備與首位玩家帶棋靈真瀏覽器檢查。
- 更新 `tests/e2e/run_20261019_real_index_adventure_probe.mjs`，涵蓋原版 index、實際 WGo 點擊、原版 G009 夥伴顯示。
- 更新 `index.html` 以處理單次執行，其他產品檔案如 `app.py`、`hero.html`、`map_battle_v1_adapter.js`、安全 Gate 均未修改。

## 接續 Owner Gates
- Production/schema preflight：**只讀檢查**正式資料庫是否具有 B023 `companion_operations`、D5A outbox 與 evolution 及其保護索引／約束，再由具授權主體決定是否執行受控遷移。隔離 DB 成功不等於正式環境已備妥。
- 真實 iPad Safari + Test02 需要 Owner 在明確准入的非正式環境進行驗收；不要以模擬器宣告實機通過。
- 真 20 題 Boss first-clear 與獎勵／下一關解鎖仍是獨立後續流程，這輪僅一題冒險／XP／棋靈。全域部署不得由測試驗收自動啟動。
- 產品 GO_MERGE／GO_DEPLOY 需 Owner 獨立核准；V4 自主 Goal Loop 仍 NO_GO。

### A–F 狀態
- A 棋靈 503 已定位，受控隔離 migration + 初始選取單次執行 **PASS**；正式 schema preflight 待 Owner。
- B 真 WGo → XP → LV2 → 英雄殿 **PASS**。
- C Map Battle 去重、Companion operation-id 去重 **PASS**。
- D Adventure 新手村一般進度與不誤宣稱 Boss CLEAR **PASS**；實機／領主完整流程待驗。
- E 排行榜與月榜候選保留，正式 Test02 重新登入待驗。
- F 商店／背包候選保留，來源准入與正式部署未開始。
