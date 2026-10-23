# G076-R2｜隔離核心作答閉環整合交接（2026-10-23）

**結案判定：R2-A/C/D 隔離核心作答閉環已完成及驗證；正式 Product 發布 Gate 仍 HOLD。** 此文件是已產出程式及測試證據的本輪收斂，不是正式 GitHub merge/Oracle deploy 許可，也不得將 isolated-browser PASS 當成 iPad 或玩家正式頁面 PASS。

## 1. 來源治理與工作區

- 工作區：`D:\go-odyssey-g075-integration-20261023`
- 本次工作分支：`g076-core-answer-privacy-20261023`
- 原始正式 baseline master：`b39b35481de43ee5de6f3dc70e215d2cf291c56b`（G074；部署已於 2026-10-22 完成）
- 父版 G076 先前 SHA：`ec99446976bdb5d9431bbb2256c76c73b9c39155`
- 所有 G076-R2 code/test/fixture/DDL 提案均**本地隔離**。無 GitHub push／PR／master merge；無 Oracle deploy、正式題庫改寫、玩家資料更新、正式 PostgreSQL migration。
- 舊主工作樹 `D:\go-website` 的大量未提交改動完全不觸碰。

## 2. 本輪真實已完成

1. `g076_step_ledger.py`：在原本的伺服器 Map Battle issued attempt/nonce/battle owner/revision 上建立 server-owned history；每一步 HMAC token、step_index、原子 CAS、不可替換落點的 idempotent replay。唯有真正 CORRECT/INCORRECT terminal 才呼叫現有 `settle_answer` 唯一戰鬥寫入者，CONTINUE 不改 HP/XP/SRS 或任務進度；後端權威不接受 client grade/HP/bonus。原 nonce hash 採用原有 Map Battle 契約。
2. PostgreSQL 路徑執行 `SELECT ... FOR UPDATE`；SQLite 測試由 caller `BEGIN IMMEDIATE` 串行，雙連線併發測試真正執行。下一步 raw step nonce 從回放 JSON 去除、以伺服器 HMAC 重新導出；原始 submission nonce 不進入 DB ledger。
3. `app.py` 新增 2 條 auth-gated endpoint：`/api/adventure/map-battles/v2/steps/start` 與 `/api/adventure/map-battles/v2/steps`。**同時要求** G076_STEP_RUNTIME_ENABLED=true 和 G076_ANSWER_PRIVACY_ENFORCED=true 才受理，兩個 flag 預設皆 OFF。依既有 `_activation_transaction`、MapBattle entitlement/eligibility、`settle_answer` 和後續已驗收 progression hook；正式 DDL **不會**被 runtime 自動執行。
4. `js/game/g076_authoritative_step_client.js`：可供後續 Product UI 接入的 fetch 接頭。玩家只送落點，不送判題結果；收到 server CONTINUE 才呈現玩家/電腦回手，terminal 必須有權威 battle_settlement，並支援網路失敗時同 token/落點重送。**目前還沒有嵌入正式 index.html**。
5. `migrations/g076_step_ledger_postgres_PROPOSED.sql`：PostgreSQL 參考的加法表結構、FK/unique/check/index 提案，**尚未執行，不能自行套用正式玩家 DB**。
6. `tests/test_g076_step_ledger_sqlite.py`、`test_g076_step_http_isolated.py`、`test_g076_step_concurrency.py`：原 SQLite 真資料交易、具 Session 的 Flask 真 route body、兩個獨立 SQLite connection 的競爭提交、原 MapBattle damage/reward idempotency。所有都是隔離帳號 101，與正式 Test02/正式 DB 無關。
7. `tests/e2e/g076_authoritative_step_client.mjs`、`g076_live_fixture_server.py`、`g076_live_browser.html`、`run_g076_live_http_chrome.py`：每次 fresh SQLite DB，將實際 app route function 以 AST 載入獨立 Flask server（127.0.0.1:5067），Headless Chrome/WGo Canvas HTTP 真執行，再停止 server／移除瀏覽器 profile。保留原始 DOM、stderr、結果與伺服器日誌在 `D:\g075-artifacts`。

## 3. 證據與驗收

- 全套選定 Python 回歸：**367 PASS／1 SKIP／0 FAIL**，`D:\g075-artifacts\G076_R2_COMBINED_FINAL_JUNIT.xml`。含 G076 分步協定、C/D/E、Map Battle 與 SRS／領主相關既有 tests；不是整個 repo 的所有測試。
- 真 Chrome + localhost Flask+SQLite+WGo Canvas：**15 PASS／0 FAIL**，`D:\g075-artifacts\G076_R2_CHROME_HTTP_RESULT.json`，DOM `G076_R2_CHROME_HTTP_DOM_FINAL.html`；自動停止 local server，無殘留正式服務。
- SGF 畫面原 G075 Chrome Canvas 72 PASS；新 G076 JS 接頭 Node 7 PASS；G075 裝備/物品圖鑑各 5 PASS。
- 以 G074 正式 Docker runtime 題庫只讀副本，SHA256 `b7b4eedf72a87ab8fbc82ff51b658cd4dc0f08cb33426aee013e97814edae232`，41,591 題中 41,587 題可生成不含答案樹安全題面，4 題 fail-closed（45566、67154、65156、65254）。原始報告 `D:\g075-artifacts\G076_FULL_CORPUS_PREVIEW_R3.json`。這不是正式題庫全部問答品質 PASS。
- **Claude 正式站問題 69853 在此 isolated Chrome/WGo + live HTTP 中驗收：**完整顯示 LB[dr:1][fj:N][bj:Y] 與第 10 路；合法 F10 經權威 Map Battle judge 回 CORRECT 並傷害怪物；B10 回 INCORRECT 並扣玩家 HP；作答前回覆只含 root 題面，不含答案 variation，所有作答均保存於新鮮隔離 SQLite。此測試不代表正式站已修復。

## 4. 原始碼關鍵限制與正式上線剩餘 Gate

- 目前 G076 接頭並未掛在正式 `index.html`：legacy `onBoardClick` 仍依賴 `currentProblem.tree`；正式網站 b39 仍會在作答前回完整答案。**G076/正式安全發布未完成**。必須一併改 main Map Battle、Practice、Lord 20 題、Guild/挑戰模式的正式 UI 與 post-settlement answer reveal，並避免其他 API/cache洩漏。
- G076 純 step judge 對需人工判定的 SGF 多分支以及 accepted_moves 未編入權威變化者仍 fail-closed；B 路題庫人工審查不可省略。切勿大量刪題或直接從 LB 的 Y/N 文字猜解答。
- 目前 PostgreSQL DDL 只在提案，尚未在獨立 PG 做實際 row-lock/concurrent/effect 測試；不可拿 SQLite 併發測試代替 Production PG 驗收。
- 並未進行 owner 真 iPad Safari、正式 Test02 安全環境完整 E2E、所有 Premium 及首次/重複答對 XP/任務政策驗收，亦未對此新 SHA 執行完整版 BUILD_APP（G074 正式 Build 曾耗時約 24 分鐘；候選在主要 UI 整合完成前不應誤判 Build Gate）。
- Owner GO_MERGE 與 GO_DEPLOY 必須各自使用**新的**明確核准；G074 #444 Gate 已消耗。正式玩家資料 NO_WRITE，課程/題庫正式公開/QuestV2/裝備旗標繼續 OFF。

## 5. 下一輪不中斷的具體銜接

A 作為 app.py 單一整合寫入者；C 接既有實際 index.html 棋盤/BoardRenderer/MapBattle lifecycle，從服務端真正取得安全題面再走 step client；D 完成正式 PG 隔離 DDL + concurrency / token / auth、終局才發獎／重複 anti-farming；B 人工裁定保留原本內容 Gate；E 課程持久化 PG 與教材；F 修 16/19/20 影片及 4/7/19 示範題。先以已完成 R2 隔離閉環為硬基線，切忌重新調查已完成路徑。
