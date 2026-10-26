# G111｜Hosted CI 可攜測試與多模式資料庫升級候選

**工程性質**：2026-10-25 G Product 隔離實作／Owner 未採納的來源治理草案。非正式資料 DDL、非 GitHub CI Policy Adoption、非 GO_MERGE、非 GO_DEPLOY。Product NO-GO。

## 來源基準與隔離
- 已由 G110 Reviewer 獨立 ACCEPT 的完整 Commit：`35d3b5e843243ee3c1ce2b6974f1262cd9afaeee`。
- G111 為新 worktree 的純本地後繼；原 G107/G108/G109/G110 封存、原 PR #445 283 個歷史 Blob（除了本輪**明確**對一份既有測試檔的變更）、正式 G027 workflow、Oracle 玩家資料都不改動。
- 相對 G110，G111 只允許 `tests/test_g076_step_http_isolated.py` 這份既有檔的**可攜測試時間**修正，以及 G111 atomic Nonmap/Practice/Mistakes 模組、SQL、source-admission local draft、Unit tests 和本文件。
- 任何新的 GitHub Hosted 流程都須由 Owner 先明確採納、使用 PR 無法覆寫的固定來源 SHA/外部 attestation，必須保留原 G027 FAIL 的獨立安全證據。未被採納的本地 manifest 非可信 Owner policy。

## A｜不依賴 beatles 外部測試插件

- 原 2026/10/23 Test Attempt 在 2026/10/24 到期；以 2026/10/25 真時鐘執行舊 G076 HTTP happy-path，正確得到 409，不是玩家安全 Bug。
- G110 依賴未進 Git 的 `D:\g079-artifacts\g110_http_fixture_clock_plugin.py`；在 Hosted runner 無法重現。
- G111 **只**在 `tests/test_g076_step_http_isolated.py::api` 的 pytest fixture 中直接 `monkeypatch.setattr(map_battle_runtime, "datetime", FixtureDatetime)`，固定此套**歷史假題**於 2026/10/23 11:00 UTC。Pytest fixture 自動復原，不影響其它測試、程式正式到期判斷或被審 Product app.py。
- 新 `tests/test_g111_nonmap_portable_contract.py` 再明確檢查正確期限邊界；測試 `test_g110_migration_and_admission_contract.py` 原四項直接傳入 now 的真 expiry predicate 仍不使用插件。
- CI runner 僅用 repository 已包含的 pytest，不再加 beatles 本機 -p plugin；這是**源碼攜帶的歷史 fixture**，不是正式站時間替代。

## B｜新版 G111 Nonmap/Practice/Mistakes 原子 DDL（獨立、嚴格）

原始提案：
- `g076_practice_steps_v1.py` 會先建 Nonmap Sessions/Events 與 Practice Attempts。
- `g079_mistakes_steps_v1.py` 如果 Nonmap 表不存在則自己建，已存在時用 `DROP CONSTRAINT IF EXISTS` 改寫 flow CHECK，後建 Mistakes Attempts。
- `g077_mistakes_flow_PROPOSED.sql` 含內部 BEGIN/COMMIT，與外部單一交易意圖衝突。
- 因此 **Practice-first、Mistakes-first 與原 SQL 並非可任意交叉重跑**。G110 Step Ledger 是獨立第三路。

G111 另新增**嚴格全新安裝型** `migrations/g111_nonmap_practice_mistakes_atomic_v1.py/.sql`：
- 使用不帶 IF NOT EXISTS、不帶 BEGIN/COMMIT 的單一 SQL；同交易安裝 Nonmap Sessions/Events、Practice Attempts、Mistakes Attempts 共四表，Nonmap flow 一開始就包含 practice/daily/mistakes，避免中途擴充 CHECK。
- 明確 operator `G111_NONMAP_MIGRATION_APPROVED=1`、非 autocommit、PostgreSQL16/17、public schema、五份歷史 source hash 完整匹配、Transaction advisory lock、DB/catalog Constraints fingerprint，版本與 SQL SHA 同交易寫至獨立 `g111_nonmap_schema_versions`。
- 只在 Registry 已存在、來源及 catalog 全相符時允許 same-version retry；若發現 Practice-first/Mistakes-first 的**未版本化舊表**、不相容表、缺失約束或雜湊被竄改，一律 FAIL-CLOSED，**不自動轉換、不 DROP 舊資料**。舊版路徑有資料的實際升級，需另行授權與 reconciliation 計畫。
- `downgrade()` 在相關 Step 模式關閉時保留所有既有資料、版本紀錄；關閉 Feature Flag 不等於能重新接受缺表或私隱門控錯誤。正式已寫玩家資料的可逆升級／降版仍待完整 E2E。
- G110 Map Battle Step Ledger 的版本表 `g110_schema_migrations` 與 G111 Nonmap `g111_nonmap_schema_versions` 各自獨立，不使用 G110 不支援的「同一版本表兩條紀錄」。
- 這是**隔離新安裝**的兼容性證據，不是已採納舊 Practice/Mistakes 真資料或正在運行的 Oracle。

## C｜執行與驗收標準
- 使用全新本機隔離 PostgreSQL 16 假資料，測 G110→G111／G111→G110 雙安裝順序、外部 commit/rollback、三個 Nonmap 流程紀錄與 Tokens 共存、安裝版本記錄、重試、歷史既有表拒絕、錯誤 SQLSTATE、不刪除資料。
- 使用乾淨 Commit 的 repository-only pytest 完整 G110 379 相關測試＋G111 新測試，**不得**提供任何本機外部 clock plugin；保留原 G110 369/4 及 157 ERROR 歷史收據。
- 新 local G111 source admission 需由外部固定 G110 base、新 G111 HEAD、可信內容目錄雜湊驗證，不能接受 PR 內自我宣稱的 Host Gate；正式 G027 維持 FAIL，Owner 政策尚未採納。

## D｜仍需 Owner Gate
新 Hosted CI 首先須 Owner 明確採納 PR 不可控制的獨立 trust anchor，並允許受控 CI-only candidate/PR 更新；現在不能 Push。
正式資料 DDL／玩家資料 NO_WRITE、GO_MERGE、GO_DEPLOY 仍需分別再核准。
G107 DPAPI 異機金鑰 escrow／Oracle 每日備份 HTTP403、全站 Schema／Chrome／ARM64 Deploy 證據及原 117 OPEN/20 P0 不因本地回歸自動解除。
