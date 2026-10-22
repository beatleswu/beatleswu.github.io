# G041｜完整 JUnit 身分來源與正式回滾配對修復

2026-10-22｜隔離 Gate 候選；正式 Product 維持 `2ae01985ab716eb0175b292888ffdea570c80ca6`，現役 GitHub master 基準 `5111b0fd8237277d3fb1fbe5d2c30d4ba102586c`。此文件不是合併或部署授權。

## 真實證據與修復

G040 真官方 BUILD_APP 產生 1,695 個 JUnit 案例、1,546 PASS、9 FAIL、140 SKIP；完整 JUnit SHA256 `4898b999bdd4b9c7f088bc42be8c39ed7d01ab8aa04c9743a00b8084b24fdda9`。兩個 Zone4 失敗屬既有 Owner 承認簽章，其他七項未准入，必須維持 BLOCK。正式 Oracle 沒有切換。

原 `verify_release_candidate_binding.py` 誤把 class-based JUnit classname `tests.deployment.test_mod.TestClass` 變成 `tests/deployment/test_mod/TestClass.py`，而真 pytest 收集節點是 `tests/deployment/test_mod.py::TestClass::test_name`。G041 在 Gate 原始目錄上從最長存在的真 `.py` 模組辨識路徑，再附上測試類別；不認識的 module、損壞 classname、空 name、重複測試識別仍拒絕。G040 實際封存 JUnit 與獨立 1,695 個 pytest collect-only 節點逐項比對：**1,695/1,695 完全一致、沒有未識別或重複**。

Owner 先前已取消額外的獨立簽署主機作為正式 Build/Deploy 的硬性前置條件，因此只有顯式 `-OwnerSimplifiedPolicy` 時，將原無條件的外部 attestation 拒絕轉成真 Gate/Product 來源、完全乾淨、確切 ancestor/control-plane、runtime bytes、nonce、JUnit SHA、Frozen19、載入來源 SHA、實際 collection 等原有完整本機交叉驗證。**這不是外部獨立可信簽章，回報 assurance 明確寫 `OWNER_SIMPLIFIED_LOCAL_SOURCE_CHECK_NOT_EXTERNAL_ATTESTATION`；不允許用候選 plugin 自稱 cryptographic trusted identity**。未傳 Owner flag 的原 external 模式仍必然拒絕。

原三個回滾契約測試死認只一組歷史回滾配對，但 G028 Owner 已核准且合併的正式 `deploy/known-production-rollback-pairs.json` 確有兩個真實配對。G041 不改該配對文件，新增兩個精確 IDs 及現役SHA／imageID／schema fingerprint 正向驗證，也保留負面篡改配對的拒絕邏輯；Windows 原三項測試已 **3/3 PASS**。Owner 額外簡化 JUnit負例 **11/11 PASS**，G041 對來源及發布相關擴大回歸 **106/106 PASS**，PowerShell AST parse PASS、`git diff --check` PASS。

## 尚未放行項目

正式 69 個GLB應原樣發布；`C01/animal-bunny.glb`, `C04/Corgi.glb`、其貼圖屬原G010來源清單的**額外Bonus 影像**，已在 Docker image 和原runtime_manifest，G010證據明示 `release_admission:false`，不得偷偷加進69正式Static manifest或不檢查即假稱已核准。G040另兩項 dual-delivery FAIL **維持未解**。

原Product `hero.html` G030 被Owner准入的合法新內容SHA為 `da938c6a08c99ebea3affd860b7c8b0a5192a14503936cd0eb6af24738dff221`，Git最後修改者是 `c52fb0efd2b8e5562be2aaac09c5c1eb1d86ac1a`，但原`deploy/runtime-source-provenance.json`紀錄仍是較舊的 SHA。這是 Product 的正式來源履歷編輯，不能藏在 Gate-only 變更，也不能繼續用只鎖定原 Product SHA2ae01985的正式部署核准來上新 Product，須有新Product commit及Owner准入。

**本輪G041僅交付 Gate 來源身分與Rollback合理修正，不能認定整份官方BUILD_APP、69資產雙通道及新Product正式部署已完成。** 合併G041需Owner明確另授權GO_MERGE；若發布Product SHA變更需要明確Product GO_MERGE與相符GO_DEPLOY授權。
