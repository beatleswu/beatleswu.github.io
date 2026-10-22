# G046｜正式 BUILD_APP 的 Owner 單一旗標傳參錯誤修復

2026-10-22｜新正式 Product 已依 Owner 核准 G043 PR #442 真合併至 master `d0f16e6ed1f7283ea39a1826d52a464a8a981cba`，69 個正式 GLB ＋ G043 獨立 2 Bonus GLB／1 PNG 准入、Player NO_WRITE。G046 只修改**發布 Gate control-plane**，不修改此 Product 的 App、Static manifest、GLB、玩家資料或正式 Oracle。

## 以完整測試定位的真正來源

G045 正式 BUILD_APP 使用同一乾淨 GitHub master／Product `d0f16e6...` 執行原完整 `tests/deployment/`，不是 Dry Run。原始 JUnit 封存 `D:\g045-artifacts\G045_REAL_FULL_DEPLOYMENT_JUNIT.xml` SHA256 `c9c151857dfec1d90a8ddf23b6db346ae7bbd002083ffb0d188d68a4c4d946bb`。測試：**1717 案例，1575 PASS，2 原核准 Frozen Zone4 FAIL，140 SKIP；0 新失敗**。75／75 E10 六路PASS，Gate/Product binding PASS，Static 2346／2346正式SHA／來源SHA d0f16e6 verified，2組Rollback及offhost PG加密還原PASS，Oracle真實App/Static無異動。

正式 JUnit結束後，仍由官方 Gate `scripts/release/build-release-image.ps1` 在步驟4失敗：單一 `--owner-simplified-policy` 的 `$identityModeArgs = if ($OwnerSimplifiedPolicy) { @('--owner-simplified-policy') } else { @() }` 寫法在 PowerShell 的 if statement輸出下退化為字串，對外部 Python `@identityModeArgs` **逐字符 splat**，實際 STDERR 為 `unrecognized arguments: - - o w n e r - s i m p l i f i e d - p o l i c y`。Step5 `$ownerConflictArgs`使用相同寫法，若僅修第一個必遭第二個阻擋。**這是 CLI 引數陣列型別 bug，不是173x產品測試或模型失敗；本輪正式映像未建，沒有Oracle部署。**

## 唯一範圍與 fail-closed 驗收

G046將兩個選用參數都宣告為 `[string[]]$... = @()`，只有 `-OwnerSimplifiedPolicy` 真時才**直接把單元素陣列 `@('--owner-simplified-policy')` 指定給變數**，維持原外部治理模式、Frozen Zone4 兩項原FAIL准入政策與全部QA檢查、來源SHA+Git clean+原Junit身份、產品與玩家資料的NO_WRITE，不引入新壓制或略過任何測試。原 G038 驗收測試曾誤以 bug 的 `if` 寫法本身為必要契約，現在把原驗收也修改成要求真正 array，避免下次回歸。新增 `test_g046_owner_cli_array_handoff.py`（GitHub Linux 可做純靜態精確陣列檢查；授權 Windows runner 則使用兩個真實 Python CLI parser 跑 `--help` 以證明單元素flag沒有拆字元）。PowerShell AST parse、實際 Windows負例及來源比對完成後，再交 GitHub required g009-source-snapshot CI。

本候選**G046 PR 若完成 CI，仍須獨立 Owner `GO_MERGE G046 PR #...` 才可合併**；本次Owner已授權的 Product `d0f16e6...` 不變，Gate-only候選不能偷換新Product SHA，更不能用未合併 Gate直接上 Oracle。之後重新執行完整官方 BUILD_APP/JUnit＋ARM64映像驗收；有條件通過才依先前Owner對新Product d0f16e6 的受控部署授權執行正式12階段協調器、回滾和玩家NO_WRITE。
