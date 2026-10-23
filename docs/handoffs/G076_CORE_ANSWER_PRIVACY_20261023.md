# G076｜安全題面與核心作答閉環｜2026-10-23（隔離候選）

## 來源與權限

- Git branch: `g076-core-answer-privacy-20261023`，從本地已驗收 G075 `7ff2fa6ba1621a411486a4ccbb709d4f92d1736a` 建立。
- 正式 GitHub master 仍應以 `b39b35481de43ee5de6f3dc70e215d2cf291c56b` 唯讀核對，G074 部署已驗收，不重做。
- 本輪不 push、不建立 PR、不 merge master、不部署 Oracle、不修改正式玩家或題庫資料；新增 Owner Gate 尚不存在。

## 已完成的原始開發

- 新增 `g076_question_privacy.py` 的 `board_only_sgf`。使用既有 SGF 值域 tokenizer 讀完整資料，再只輸出根節點的棋盤尺寸、AB/AW/AE、PL、LB/TR/SQ/CR/MA，不回傳任何解答子分支、SGF 註解、KataGo 答案或 accepted_moves。SGF 不合法時 fail closed。
- 依現行 JS `readSgfRoot` 允許 2–25 路；原 SGF 省略 SZ 時依既有瀏覽器規則補預設 19 路；原 SGF 省略 PL 時，僅安全推得答案樹第一手**顏色**作為先手方，不揭露答案座標。
- 既有 `/api/question/<id>` 加上 `view=board` 的安全唯讀輸出及 Cache-Control no-store、entitlement 保護。明確特性 `board_only` 讓新前端識別權威契約。
- 提供 `G076_ANSWER_PRIVACY_ENFORCED` 的**預設 OFF** 強制遮蔽門檻，且即使使用者移除 view=board 查詢參數也不可繞過；但**此旗標禁止正式打開**，直到多步判題/領主/一般練習及其他可能洩漏端點均整合且端到端驗收。
- 全量題目目錄 `/api/questions` 移除不需要的 `katago_best_move` 正解提示，不改伺服器實際權威判題。
- G075 的 69853 SGF 標記與裁切、裝備不誤導、推薦已鎖區、物品圖鑑修正原樣保留。

## 原始測試與題庫稽核

- `D:\g075-artifacts\G076_CDE_R3_JUNIT.xml`：**332 PASS／1 SKIP／0 FAIL**（含 G076 新安全題面路由與既有 G075 C/D/E、Map Battle／SRS／領主權威等相關測試）。
- `tests/e2e/run_g064_sgf_annotations.mjs`：Chrome Canvas **72 PASS**（沿用 G075 C 的已驗收案例，非本輪額外的完整網路實機測試）。
- G075 裝備與物品圖鑑獨立 Node：各 **5 PASS**。
- 已使用實際 G074 app/scheduler runtime 題庫唯讀 SHA `b7b4eedf72a87ab8fbc82ff51b658cd4dc0f08cb33426aee013e97814edae232`、41,591 題做全量結構檢查：
  - **41,587 題可生成安全題面**（99.99% 結構預覽相容，*不代表 41,587 題全部判題無誤或完成 Owner 題庫審核*）。
  - 四題暫時 fail closed：SGF 格式 2 題（45566、67154）；先手方欄位異常 2 題（65156、65254）。
  - 正式驗收問題 **69853** 的 `LB[dr:1][fj:N][bj:Y]` 初始題面保留。
  - 原始收據：`D:\g075-artifacts\G076_FULL_CORPUS_PREVIEW_R3.json`；該題庫副本不納入 Git。

## 尚未完成的真正 P1 發布阻擋

1. 現行瀏覽器的 `onBoardClick` 仍使用前端 `currentNode.children` 與 SGF 完整答案樹決定互動；直接改成只載入初始盤面將讓舊客戶端誤判，不得上線。
2. 既有 `judge_map_battle_answer_v1` 對正確**但未完成**的多手解答序列回 `INCORRECT/partial_answer_sequence`。若將每次點棋直接提交，正確中途步會被視為錯誤並結算；必須建立伺服器持續授權、一次性進度與安全的對手回手／終局判定契約。這是多步死活題核心，不可偷用前端解答樹。
3. 同步完成一般 Practice／領主 20 題/16 題門檻、回放、解答結束後授權檢視；確保舊客戶端不能從其他 API、預載快取、Service Worker、公開題目清單回收答案。
4. 使用真實已隔離帳號／資料庫完整端到端驗收，至少覆蓋 69853、正確與錯誤首步、二至多步棋、分支、不同棋盤大小、Premium、每日額度、重送 nonce、stale revision、補星 First Correct/XP，以及 Chrome/iPad Safari。
5. 通過完整 Build／JUnit／正式來源與回滾驗證後，重新申請特定的新 GO_MERGE 與 GO_DEPLOY。

## 目前 Gate

**G076 P1 = HOLD；尚未正式發布。** 上述實測、靜態題面、安全資料縮減成果不是整個遊戲防作弊漏洞已消除的證據。C、D 持續收斂權威契約；E/F 的課程/影片和 B 題庫人工審核可以在隔離環境平行準備；V4 真正自主派工仍須端到端證據才能宣稱完成。


## G076 第二步增量｜伺服器分步判題純核心（未接線）

- 新增 `g076_server_step_authority.py`，使用既有 authoritative SGF parser 與 G065 terminal_verdict，區分「正確中途手＝CONTINUE」「真正終局＝CORRECT」「錯誤/失敗分支＝INCORRECT」「對手多分支或權威不足＝fail closed」。
- 每手回應只含 `status`、可在已驗證作答後顯示的**唯一對手回手**及 reason，不回傳下一手正確候選集合。歷史序列只允許由**伺服器持久化狀態**提供；純引擎本身**沒有 HTTP route，也沒有資料庫寫入與一次性提交功能**。
- 測試 `tests/test_g076_server_step_authority.py`：**15 PASS、0 FAIL**。覆蓋正確中途手與對手回手、第二手真正終局、錯誤與顯式失敗分支、偽造歷史拒絕、權威不足拒絕、非法座標與邊界。
- 尚不得啟用或將其當成正式 Multi-step judge。下一步必須接持久化一次性 token / server-owned history / transaction version CAS / duplicate submission idempotency / 正式權益 / 第一手錯誤立即結算及成功後可授權揭示正解；否則每步 judge 可能變成新的可重試答案 oracle。
