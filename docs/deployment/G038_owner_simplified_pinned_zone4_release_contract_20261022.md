# G038｜BUILD_APP 真阻擋修復：精確凍結 Zone4 合約衝突及 Owner 簡化政策

2026-10-22 · Product 嚴格維持 `2ae01985ab716eb0175b292888ffdea570c80ca6`；正式 GitHub master Gate 基準 `a946d73f83b1d48e0a6b18f7feb5f329991bdb13`（G036 PR #438 已獲 Owner 正式核准並完成合併）。本 G038 是新、獨立、尚待 CI 與另外 Owner GO_MERGE 的控制面修正。不可因 G036 原有許可自行合併 G038。

## 兩項獨立阻擋的真證據

G037 真官方 `deploy-coordinated-release.ps1 -Execute -OwnerSimplifiedPolicy -OwnerGate GO_DEPLOY_WITH_BOUNDED_RECOVERY`，正式 Product 2ae01985，Gate a946d73f，證據已確認只有六個 control-plane diff、乾淨工作樹和初始 source binding/E10六路完整 PASS。BUILD_APP 進行超長 `python -X utf8 -m pytest -q tests/deployment/ -p g009_release_identity_plugin --junitxml ...`，整個測試輸出由 PowerShell `$pytestOutput=@(...)` **直到 pytest 結束才印出**，測試數量為 76個test檔、至少1170個test函式（含參數化後更多），故 user 長時間看不到逐測試進度。首次BUILD_APP子程序終止後正式Coordinator啟動第2次相同階段；未取得完整 pytest JUnit、未獲 BUILD_APP PASS，也未進PROMOTE_APP或PROMOTE_STATIC。為防 unattended prod deployment，在原Oracle App69dbe57a、Static e53a4775 確認不變時精確受控停止，G037 executor processes 0、未修改玩家資料。不能把長時診斷當作完整 QA PASS。

更實質的**確定阻擋**：新 G038 真用 clean Gate來源 `a946d73f` 跑 `tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py`，19 tests in 5.36s => **17 PASS、2 FAIL**，兩個失敗正是原已Owner接受的精確 `/css/e10/backpack.css` 第六路由。真 JUnit 重新計算 SHA256 failure signatures **2/2與原 pinned policy 完全一致**：
- extra route `a4a091ab34ae784a47e1f6004cf11a2c33b69de0563923ecab6f9dbf1d195066`
- status200,old expected404 `e4d0dc59ab812bca769492ad5b9dedc102f18511e49186f778df631327011de5`

但舊 `zone4_owner_b_policy.py` 內 `activation_status` 堅持額外獨立 reviewer host 簽章；真 baseline evaluator CLI 即使兩簽章完全一致，也報 `BLOCK unrecognized_or_changed_failure` 和 `PENDING_INDEPENDENT_REVIEW`。這與 Owner 2026-10-21 已取消額外簽署主機作為正式 Product 發布必要條件的決策相衝突，不應繞過正式來源驗證或自造任何外部 reviewer signature。

## G038 修正及不變安全邊界

僅針對原既有`-OwnerSimplifiedPolicy`，在 `build-release-image.ps1` 顯式傳 `--owner-simplified-policy` 給既有 `evaluate_build_app_test_baseline.py`；未設定 flag 時原外部 reviewer 模式繼續 fail-closed，**不修改原來的預設**。本新 evaluator 只在載入既有 `--owner-conflict-policy` 後才允許 flag，並傳到正式原 `zone4_owner_b_policy.py` 真評估器，不接受任何通用略過失敗或外部 reviewer 偽憑證。

新簡化模式在檢驗既有正式 Git commit policy`policy_source_sha` 祖先關係之外，要求**原 Owner policy 檔SHA256**完全等於事前固定的 `9a48e1887adffc27927305da7724bb6d7eb4bee7ae37d7a904550b0074208dbe`，再執行原本全部條件：原 Frozen 19節點集合完全一致、17節點真的PASS、2節點必須原來FAIL、兩原SHA256簽章一致、原因精確限 `/css/e10/backpack.css`、Frozen Python原來源bytes與Git HEAD一致、3-node原歷史baseline及其他任何unrecognized失敗仍Block。回報結果是 `PASS_WITH_OWNER_APPROVED_CONTRACT_CONFLICTS`，**保留原2 FAIL，不是一般 PASS，也不偽造獨立review receipt**。

隔離真實JUnit重新驗證：legacy仍`BLOCK`、簡化模式僅在2個原FAIL完全一致時`PASS_WITH_OWNER_APPROVED_CONTRACT_CONFLICTS`，原2個FAIL計數保留，沒有改任何玩家資料或產品3D/正式Oracle。反例測試覆蓋失敗訊息/Signature篡改、policy改寫、漏掉17 PASS、沒帶明確policy、legacy預設、CLI接線等；其它 tests/deployment 原版仍保留原始FAIL契約。

## 正式發布及治理

本 G038 只修改正式發布控制面 `scripts/release`、`tests/deployment`、`docs/deployment` 及唯一現有 GitHub CI Workflow exact allowlist，**不得改 Product App/GLB/QuestV2/Shop、不能改 D015 PostgreSQL、不能替代 Oracle 真Preflight和 post-deploy SHA/rollback**。本分支所有測試成功、GitHub required `g009-source-snapshot` Push與PR SUCCESS 後，應單獨請 Owner `GO_MERGE G038 PR #<actual-number>`。G036合併已真完成不重問，原 `GO_DEPLOY_WITH_BOUNDED_RECOVERY 2ae01985` product目標授權已存在，但完成實際全套 BUILD_APP/JUnit PASS before deploy仍為硬性階段關卡。


The actual G037 retry regression was also reproduced: 167 passed / 1 failed
in the focused 168-test suite. The sole failure was the authority-declaration
test in tests/deployment/test_release_source_separation.py, caused by the exact
approved GitHub CI workflow path in ReleaseTooling.psm1 but not in canonical
e10_development_workflow_v2.py. The former was fixed in G036; G038 adds ONLY
the same exact GitHub CI file to E10, never an .github/** wildcard, and runs
both affected regression modules in the mandatory GitHub CI. Scope grows to
12 exact release-control-plane files compared with original Product SHA.


PowerShell correctly normalizes .github/* to github/* with TrimStart('./').
After synchronizing the third E10 authority a second original consistency check
revealed a spelling-only difference between an advisory .github CI entry and
the enforcing canonical path. Corrected the E10 canonical exact path to the
normalized github/workflows/g009-source-snapshot.yml, and updated the original
consistency test to normalize both sides with the **existing** exact same rule.
It still compares full **exact sets** and rejects all other CI workflows.
G038 total scope is 13 release-control-plane files vs Product 2ae01985.
