# Go Odyssey｜G076-R3-A 真正玩家棋盤接線｜2026-10-23

**階段判定：R3-A（Map Battle 實際 `index.html` 程式接線）隔離工程 PASS；G076-R3 整體與正式發布仍 HOLD。**

## 來源與 Owner Gates

- 原正式 G074 master / 正式 Oracle site baseline：`b39b35481de43ee5de6f3dc70e215d2cf291c56b`。
- R2 已驗收父 SHA：`0e133b74832fb136542f395af21a40263c4b58eb`。
- beatles 隔離工作樹 `D:\go-odyssey-g075-integration-20261023`，新分支 `g076-r3-player-ui-20261023`。
- **未 push／未建立 PR／未 merge master／未部署 Oracle／未改正式玩家或題庫，也未執行正式 PostgreSQL 遷移。**
- 正式 G076 兩旗標 `G076_STEP_RUNTIME_ENABLED` 與 `G076_ANSWER_PRIVACY_ENFORCED` 保持 OFF，不能因 R3-A PASS 開啟。

## R3-A 已實際修改

1. 真正的 `index.html` 引用已驗收的 `js/game/g076_authoritative_step_client.js`，`app.py` 新增對應靜態 JS 正式路由。未修改舊 G074 JS 引用的正常順序。
2. 伺服器新的 `GET /api/adventure/map-battles/v2/steps/capability`，登入後只回傳 `enabled` 和協定版本，no-store；必須兩旗標皆 ON 才返回 true，不能由 query param 或 LocalStorage 偽造功能。
3. `_loadQuestionImplementation` 在 Adventure 先讀伺服器 capability；當啟用時**無條件**重新取得 `/api/question/:id?view=board`，必須 `board_only=true`、`accepted_moves=[]` 且有 SGF，否則 fail-closed。覆寫任何舊 q.content／solution／native_answer 避免誤用本地全解答。
4. `_prepareMapBattleV1ForQuestion` 在原有 authoritative attempt/nonce 建立後，使用 `GoOdysseyG076Steps.createClient` 開啟逐手伺服器 session；只有 `READY`、版本/身分仍新鮮且返回的歷史數量正確才可進入正式棋盤。SGF initial root 顯示棋子、裁切及 LB 等 marker；本地 answer tree 無正解節點。
5. `onBoardClick` 在 SGF 本地 `currentNode.children.find` 前交給 `_g076StepOnBoardClick`；玩家的落點先送伺服器，**僅伺服器回覆** CONTINUE/terminal 才繪製玩家與唯一對手回手。真正終局則以 `battle_settlement` 交給舊 Map Battle 動畫、HP、SRS、戰鬥進度路徑；不重送舊 `adapter.submit`。
6. 跨題 async response 有問題/attempt/generation 防護。無法確認的網路請求只能重送原落點與原 token，禁止在不確定是否已結算時換答案；已取得 terminal 回覆後如果 UI 呈現出錯，不會再重送已消耗 token。
7. 斷線重整由原生 `g076_step_ledger.open_steps` 返回**已經提交**的前綴玩家落點與伺服器唯一回手，供真實 `index.html` 重建可見棋盤；不提供未來正解變化。
8. 安全模式阻止本地 `resetProblem` 清除已保存伺服器狀態、`showAnswer` 在作答前播放全樹、`useHintTicket` 從答案樹取得提示扣券。旗標 OFF 時原 G074 舊功能路徑保持不變。

## 原始驗收

- 修正後選定 Python Regression：**369 PASS、1 SKIP、0 FAIL**；JUnit `D:\g075-artifacts\G076_R3_FULL_CDE_JUNIT.xml`（包含 C/D/E、Map Battle、SRS、領主既有測試，新版 Capability HTTP+resume）。
- 直接抽取現有 `index.html` 真實主 script 語法解析、真 `_g076StepOnBoardClick` 和 `onBoardClick` 委派的 Node VM 驗證：**13 PASS、0 FAIL**；腳本 `tests/e2e/g076_r3_real_index_adapter.mjs`。涵蓋逐手、原位重送、斷線、已確認答案後 UI 故障、拒絕 nonce、切題與隱藏/阻擋傳統答案樹功能。
- G076 JS client 獨立：**7 PASS**；G075 SGF Canvas Chrome：**72 PASS**。
- localhost 隔離 Flask SQLite＋WGo 真 Chrome：**15 PASS**，完整兩手戰鬥及 G074 runtime corpus 真題 69853，F10 = CORRECT、B10 = INCORRECT，標記 1／N／Y 均正確。原始 `D:\g075-artifacts\G076_R2_CHROME_HTTP_RESULT.json`，每次全新 DB、測試服務自動關閉。
- R2 真 Docker PostgreSQL 16 隔離 DDL/row lock/duplicate terminal：**7 PASS**；本輪未重新執行容器（R2 原始收據 `D:\g075-artifacts\G076_R2_PG_ACTUAL_RESULTS.json`）。

**驗收層級注意：** 以上的真 Chrome 是有真 SQLite/Flask HTTP 的**獨立驗收頁面**，Node VM 使用實際 `index.html` 函式切片，而非已登入正式 Product 整頁 Chrome DOM 的操作。因此不得宣稱 iPad Safari、正式 godokoro.com 或正式 `index.html` 全頁實機 E2E 已通過。

## R3-B/C/D 必須完成的剩餘 P1（請不要跳過或重做 R3-A）

- 答案洩漏面至少包括：`GET /api/mistakes` 會回舊題 `content` 全 SGF、`GET /api/daily-challenge/today` 作答前回完整 `content`、評級/Rating Trial 的 `_strip_question` 回變換後完整 SGF；另要核對 Practice、Boss/Lord、Guild、SRS、quest 初始化／JSON、Public Review 及 CDN/Service Worker 快取。Admin-only 題目檢視與已結案 Premium 歷史題面應依授權另行區分，不能粗暴全關。**正式 privacy flag 仍不可打開**。
- R3-B 需把非 Map Battle 模式遷移至伺服器權威的多步判題與結算，作答後才依權限解答揭露。不要單純刪 SGF 造成老師和學生無法作答。
- 進入 release 前需隔離 PG 真帳號功能／Premium 權益／重複 XP／Boss cooldown／Guild 任務／完整 iPad Safari 真機驗收；正式 DDL+rollback 預演，完整 BUILD_APP、JUnit、GitHub CI、真正新 GO_MERGE 和獨立 GO_DEPLOY。
- B 題庫 41,591 安全預覽已有 41,587、4 失敗 fail-closed，但「預覽可讀」不是判題品質，題目人工裁定仍需獨立進行；不大量下架。

## 接管最短步驟

1. beatles 切到 `g076-r3-player-ui-20261023`，對新 HEAD 及 `git status --porcelain -uno` 唯讀核對。
2. 使用 `docs/handoffs/G076_R2_ISOLATED_END_TO_END_20261023.md`、本 R3-A 文件以及 Notion 同頁最新 append，不要重新追查已完成 R2 PostgreSQL 交易。
3. 先收斂 R3-B 答案存取／非 Map Battle 模式，再進入 R3-C/D，正式 flags OFF，Owner Gate 不變。
