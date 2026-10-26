# G066 V1 啟蒙班離線候選

20 課／4 週，主課表 240 筆、每課 8 題 practice，保留 quiz／graduation metadata。預設 feature OFF；無 app.py／現有 Curriculum 直接變更，無正式 DB 連線，無影片打包。

完整接口與尚未核准的規則見 [handoff contract](../docs/handoffs/G066_INTERFACE_CONTRACT.md)。所有 source_record_uuid／entitlement／KataGo／播放證據／判題／獎勵權威均由既有伺服器適配，fixture 中的 UUID 與 APPROVED 不代表正式證據。

在工作樹根目錄 PowerShell 重現本次環境（`python` 未在 PATH，故使用已確認存在的 runtime）：

```powershell
$coursePython = 'C:\Users\beatl\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $coursePython -m pip install --target .g066-test-deps -r g066_course/test-requirements.txt
$env:PYTHONPATH = "$pwd\.g066-test-deps;$pwd"
New-Item -ItemType Directory -Path artifacts/g066 -Force | Out-Null
# basetemp 使用新的 attempt 名稱，保留既有 receipt。
& $coursePython -m pytest tests/test_g066_course_v1.py -q --basetemp artifacts/g066/pytest-temp-new --junitxml artifacts/g066/pytest-new.xml
& $coursePython -m g066_course.fixture_server
```

另開 terminal（server 固定 loopback 5066）：

```powershell
node tests/e2e/g066_course_v1_fixture.mjs
```

每次 browser 完整重跑前，先停止並重啟 fixture server，取得新的 temporary DB；同一 server 的進度會持久保留，不能把已完成課程當成新帳號測初始鎖定。既有失敗 receipt 不覆寫，重跑前另存其輸出。

測試 browser runner 使用機器上既有 `D:/go-odyssey-sixroute-20261019/g/tests/e2e/node_modules/playwright-core/index.mjs`（唯讀 import）與 Chrome 路徑；未修改該工作樹。不同機器請更換測試 runner import／可執行檔路徑。fixture 是同一固定測試 principal，**不是正式登入實測**；登入／CSRF 邊界另由 Flask client 測試。影片 fixture 為 server-evidence stub，沒有假造已看片證據。

只讀重建資料與產生 proposal：

```powershell
& $coursePython -m g066_course.build_catalog --syllabus D:\go-website\course_syllabus_20261022 --videos D:\go-website\course_video_sample_20261022 --output g066_course/data
& $coursePython -m g066_course.make_proposals
git apply --check docs/handoffs/G066_D_ROUTE_PROPOSAL.patch
git apply --check docs/handoffs/G066_CURRICULUM_PROPOSAL.patch
```

不執行 `git apply`，不啟用旗標。SQLite schema 僅由測試使用 disposable database 建立；不接入全站 migration runner。正式 PostgreSQL 交易與實際媒體 server evidence 仍需 G 協調，不可把本離線服務直接指向 Oracle／正式玩家資料。
