# G025｜Oracle Daily Backup 連三日 HTTP 403：實際流程定位、離線拒絕測試與正式恢復 Gate

2026-10-21，beatles，獨立來源工作樹。**G025 階段驗收：授權失敗現象有原始 Oracle 唯讀證據、備份流程和 OCI SDK 可定位、可執行的受控排除方案及離線 fail-closed 測試完成；正式備份服務未修復、正式部署 NO-GO。**

## G024 之後真正取得的新證據

透過既有授權 SSH，遠端只執行 `systemctl show/cat`、`journalctl` 與對已存在 shell script 的唯讀 SHA、API 呼叫結構分析。沒有跑任何 OCI 寫入 API、`pg_dump` production、資料庫查詢/DDL、修改 unit、環境變數或金鑰。

- `godokro-backup-daily.service` **2026-10-19、2026-10-20、2026-10-21 日 UTC 均失敗**。每次恰好八個 journal messages，其中每次一個 HTTP **403**，3日該訊息的 SHA256 前12碼均為 `731c6e869207`、長度238，證實同一型態錯誤重複出現，不是因為只有單日備份偶發失敗。10月21日 systemd `Result=exit-code / ExecMainStatus=1`。
- `godokro-backup-weekly.service` 2026-10-18 **Exit0**，但**成功的服務退出碼不證明 Player PostgreSQL transaction-consistent backup 或 restore**。Daily/Weekly 指向相同一份 257行腳本、SHA256 `30490db056e3dde120df3684d6586c17a31a98039ce16646d9acec2a11256264`。
- 原腳本真正使用嵌入式 Python SDK：`oci.config.from_file`（189行）、`oci.core.BlockstorageClient`（190行）、`oci.pagination.list_call_get_all_results` / `list_boot_volume_backups`（192–193、227–228行）、`create_boot_volume_backup`（206行）、`get_boot_volume_backup`（215行）、`delete_boot_volume_backup`（238行）。主要目標是**Oracle Cloud Boot Volume Backup（開機卷備份）**與輪替，並非可直接宣稱的 PostgreSQL `pg_dump`。在這份 script 的 SDK 呼叫路徑中出現 HTTP403，符合 OCI Cloud IAM／資源範圍拒絕或驗證/可見性問題的特徵。
- **未確認 403 精確發生於 list/create/get/delete 哪一行**：Journal 的同一條238字元訊息沒有安全且足夠的 method/location 識別資訊；嚴禁逕自假設特定 IAM policy 不足，或直接授予 `manage all-resources in tenancy`。應採最小權限及精確資源範圍，比對 OCI audit event 的 request/action、principal、target compartment／Boot Volume（敏感 OCID 不傳到對話或證據），經管理者核准才能修正 policy/config。
- G024 先前廣域 filenames 掃描遇到上限，候選只有與已知 App OCI 發行包同大小的兩個 .gz 文件；不是可還原的玩家資料庫備份。OCI boot volume backup 可能存在雲端且可恢復**整卷**，但需要獨立另開 restored volume/instance 真演練；不能以備份排程成功替代 logical PostgreSQL 一致性備份。正式 off-host 快照真實覆蓋、加密、保留與 recovery point 尚未驗證。

已封存的 sanitized 原始證據（均僅提供分類／雜湊／API **方法名稱**，不輸出 raw script、完整 journal、Request ID、OCID、密碼、token、正式 Player data）：

- `G025_ORACLE_BACKUP_WORKFLOW_FAILURE_CLASSES_20261021.json`
- `G025_ORACLE_403_BACKUP_COMMAND_EVIDENCE_20261021.json`
- `G025_DAILY_403_COMMAND_STAGE_TAGS_20261021.json`
- `G025_OCI_BACKUP_SAFE_SDK_CALLS_20261021.json`
- `G025_403_ERROR_CATEGORY_DETAIL_20261021.json`

## 已實作並測試的非生產、只讀 Fail-Closed 診斷候選

新增 `scripts/release/g025_oci_backup_readonly_preflight.py`。這是**注入式 OCI provider 介面，沒有 import/使用真 OCI 憑證、沒有真外網 HTTP、沒有真 backup 操作**：

- 嚴格確認供核對的 `compartment` 與 `bootvolume` OCID 類型，無效範圍**不呼叫任何 provider**。
- 只允許 `list_boot_volume_backups` 的**唯讀**呼叫；401／403／404／429／500 一律 HOLD，不會補用更多權限或重試有副作用的 API。測試 Cloud error message 即便帶敏感文字也不轉傳。
- 即使 list 成功，也只能標記 `READONLY_LIST_PASS / CREATE_AND_RESTORE_UNVERIFIED`；**沒有證明 create、delete、off-host 保存、PostgreSQL Restore，更沒有 GO_DEPLOY**。
- 第二道 gate `permit_production_backup_gate` 每一項都是強制條件：每日備份健康、正式 PG 一致備份存在、獨立 PG 真還原、OCI boot volume backup 實際成功、Runtime/Static source 精準配對、Owner 正式部署批准；只要一項不符，就拒絕正式發布。
- 真實歷史 HTTP403 只用讀回證據寫入 Governance 文件；離線測試中的 provider/OCID 全為 synthetic。

`tests/test_g025_backup_iam_403_readonly_gate.py` 使用 FakeReadOnlyOCI 檢測多種 API failure/HTTP code、失敗後永不建立/刪除快照、非法 Scope 不呼叫、成功 list 仍不可誤放行。隨 G024、G023、G022 的安全測試一起回歸，Git commit 與總數以最終 Machine Seal 為準。

## 正式恢復必須另行授權的操作步驟（本階段全部 NOT EXECUTED）

1. **先在 OCI 審計紀錄定位拒絕的精確 action/principal/compartment**，再由 Owner／雲端帳戶管理者只允許必要資源的最小 IAM policy，不授予租戶全域管理／刪除權；對失效 token/profile 的修復也須依 credential 管理流程。**勿在 G025 自動修改 IAM、profile、OCI Instance Principal、unit、timer。**
2. 區分每日備份流程中「建立應用 Tar」「Boot Volume 查詢/建立」「遠端 snapshot」「輪替清除」四個互不等價階段；先在具備授權的環境使用只讀 OCI list 驗證權限，後續若要做**真快照 create/delete**，必須另有明確變更核准並明確限制允許清理的舊備份，避免一次 run 自動刪掉僅存的還原點。
3. 建立受治理、加密、限權存取、具保留期限的 **PostgreSQL 16 一致性邏輯備份**（例如 `pg_dump -Fc`；僅在管理者授權正式 backup change 後執行），儲存於可證明有效的 off-host 地點；在**隔離的另一個 PG16 實際 pg_restore**，驗證關鍵玩家資料、交易與 idempotency constraints（不可把正式玩家內容輸出到 chat/Notion/Git/證據 ZIP）。OCI Snapshot 另須證明整卷與 DB restore 可恢復，不得僅靠 daily timer Exit0。
4. 備份／恢復雙 Gate 都 PASS，再由正式變更權審核 G024 已在 ARM64 隔離 PG16 測過的 `quest_claims_v2` Migration；確立正式 Runtime/Static 來源配對、內容與 Owner iPad Safari UAT，分開請求 **GO_MERGE / GO_DEPLOY**。
5. G025 的完成僅表示**備份 403 已被定位至 OCI Boot Volume Backup SDK 工作流程，且有可測、會安全停止的診斷工具與修復准入契約**；OCI 生產備份本身仍是 FAILED，不可能宣稱「已修好正式備份」。

**階段交接**：G025 的獨立檔案、機器 Seal、Commit SHA 和封存 ZIP SHA256 由完成工具驗證後附入 Notion/append-only GMASTER；未取得任何正式 Production 修改許可，Oracle/GitHub master 保持不變。
