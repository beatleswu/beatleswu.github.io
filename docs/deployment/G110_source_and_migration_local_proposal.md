# G110｜隔離來源准入與 Step Ledger Migration 版本契約（候選，未授權）

Owner 尚未採納此來源治理策略；本文件不授權正式 GitHub CI 政策、GitHub master 合併、Oracle 部署或任何正式資料 DDL。正式 G027 舊版來源驗證保留並維持 FAIL。PR #445 仍 Draft。

## 固定來源
- 正式 master：`b39b35481de43ee5de6f3dc70e215d2cf291c56b`
- 已通過 G109 Reviewer 全數 283 Blob 核對的 PR HEAD：`aca38a85f1d407303ef3957ad864b583e2ffa0ac`
- 283 Blob 凍結 manifest SHA256：`f5edab377f1b8446684c3acdfb465ea3ba2d5d7e4087b82ffae2f76d640f4209`
- 僅隔離新增 G110 檔案白名單六個；不可變更原來 283 個來源內容及 G027 歷史工作流程。
- G110 local checker 須 externally supplied `--expected-head` 固定 40 字 SHA，重新讀取全部原 283 Blob／Git Tree 並檢查新六檔和 9 項精確錯誤碼拒絕。
- Checker 的 LOCAL PASS **不是**可信 Host / Owner G027 認領；由 PR 內容自我提供的 SHA 或腳本不能當成正式獨立治理。正式 Hosted Gate 必須有受保護分支或外部 pinned SHAs，再經 Owner 正式採納；此候選沒有修改既有 `.github/workflows/g009-source-snapshot.yml`。

## 本地 Product Migration 版本契約
- SQL `migrations/g110_step_ledger_atomic_v1.sql` 源自 G109 Reviewer 獨立認可的交易修正草案（source SHA256 `bb897a7e1275209f2160965bc6dd98b265581ebde00d1e6be4dceaf05c030251`）。
- 新模組 `migrations/g110_step_ledger_atomic_v1.py` 是**明確呼叫**的 Operator migration helper，沒有預設 DSN、不從 App startup 呼叫、沒有 commit/rollback，也沒有從 Oracle 或 G107 備份讀資料。
- 呼叫端提供正式授權交易和 `G110_STEP_LEDGER_MIGRATION_APPROVED=1` 前才允許 apply；光有檔案內字串不構成 Owner DDL 授權。
- 交易級 advisory lock 序列化同一 migration；對現有 map_battle_attempts 欄位型別/NOT NULL/複合唯一約束檢查。
- 不可跳過已存在但不受版本紀錄追蹤的 Step Tables；初次建立完整 FK/CHECK/Index 後於**同一個外部 transaction**記錄 `g110_schema_migrations` 的版本、SQL SHA256 及部署後 catalog fingerprint。
- 已套用版本在 retry 時，必須 version、SQL SHA、catalog/constraint/index fingerprint 全部吻合才能返回 `ALREADY_APPLIED_VERIFIED`；不允許用 `CREATE IF NOT EXISTS` 猜測 Schema 合法。
- **回滾限制**：正式 upgrade 前可以 caller `ROLLBACK` 撤銷全部 DDL；正式 COMMIT 後預設只允許先關閉 Step Runtime，再回舊版本且**保留 additive ledger/history／version marker**。絕不能直接執行破壞性 DROP 或刪玩家資料。當資料已產生，需要另行單獨授權完整正反向契約。
- G076／G079 Nonmap、Mistakes、Practice 為不同 migration，**不**包含在本輪 Step Ledger 適用範圍。舊版主遊戲 Schema 目前沒有上述新表，不表示所有 G076 模式無需後續 DDL。
- Feature Flag OFF：`G076_STEP_RUNTIME_ENABLED` 缺省為 off，且 Step API 還要求 answer privacy；要分別測試 OFF 的路由拒絕、既有玩家正常功能，不能單憑靜態程式碼就宣稱完整舊站相容。

## 授權 Gate
1. 獨立 Reviewer 可就本地新增六檔、實際 PG16 隔離單元測試及錯誤拒絕案例出具限定 ACCEPT，但不具 Owner 正式來源／DDL 採納權。
2. 新 Hosted CI 先要 Owner 限定核准來源政策與 Push 候選，且由獨立、不可被同一 PR 覆寫的來源 pin 驗證；**不能**為讓 G027 綠燈刪除原 G027。
3. Schema migration 正式執行必須有 Owner 額外 DDL 授權、最新正式備份可還原證據、Feature Flag gate、玩家權威資料庫相容性與回滾。
4. GO_MERGE 和 GO_DEPLOY 仍是各自另行取得 Owner 核准的 Gate。

目前正式 Release：NO-GO；GitHub master、Oracle Product、正式玩家資料均保持原狀。
