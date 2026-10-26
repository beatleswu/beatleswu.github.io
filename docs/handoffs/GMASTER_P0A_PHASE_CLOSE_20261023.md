# G076 P0-A Daily default-OFF | G MASTER isolated phase close | 2026-10-23

## Status
**P0-A isolated engineering verification PASS; G076 full release remains NO-GO.** This does not authorize a GitHub Push, merge, deploy, PostgreSQL DDL, production player write or question/content mutation. Source baseline `f414db82b5c1aa45f8b7086c1defb1bfe0f307eb`, worktree `D:\go-odyssey-g076-p0-daily-20261023`.

## Preserved previous evidence
- Existing R3: f414 / Python 671 PASS, 18 SKIP, ARM64 original 422/422; DO NOT count as fresh result.
- Previous R4 78d2534ef and R5 b664ff53a201ae7afb6e6f5900d51434b7b4c17a, independent Grimoire lane.
- Chrome previous FAILED runs preserved within `artifacts/g076-p0a/` as `*.FIRST_FAIL`, `*.SECOND_FAIL`, `*.THIRD_FAIL`, `*.FOURTH_FAIL`, `*.FIFTH_FAIL`, `*.SEVENTH_FAIL`, etc; not erased/recast as successes.
- Real failure discovered: server granted 50 XP and daily_first/daily_ace but legacy `showResultPanel()` dereferenced absent optional header, so UI misleadingly said report failed. Guarded the TWO optional header elements only. Legacy HTML is **not** byte-identical to b39; its SGF, judge token, submission, rewards remain unchanged. Source parity Node assertion reverses only that precise null guard before comparing b39 Git blob.

## New observed acceptance
1. Real Chrome + real loopback HTTP + disposable SQLite, `python -B tests/e2e/run_g076_daily_p0a.py`: exit 0. New secure steps ON: **21 checks PASS**; flags all OFF restored legacy: **39 checks PASS**. Test readback in `artifacts/g076-p0a/browser-run.json`; raw `on-stdout.log`, `off-stdout.log`, `on-server.log`, `off-server.log`; DOM evidence at `.g076-daily-tmp/steps-completed-dom.html`, `artifacts/g076-p0a/chrome-local/legacy-completed-dom.html` and `blocked-dom.html`, and loopback SQLite effects in `legacy-effects.json`. All tests are disposable, zero production data writes.
2. Final targeted Python+Flask+SQLite+manifest regression, exit 0: **221 PASS/0 FAIL**. Command:
```powershell
python -B -m pytest -q -p no:cacheprovider tests/test_g076_daily_p0a.py tests/test_g076_daily_integration.py tests/test_g076_r3b_exposure.py tests/test_g076_nonmap_steps.py tests/deployment/test_g076_r3_image_closure.py tests/deployment/test_build_manifest.py --basetemp=artifacts/g076-p0a/gmaster-pytest-phaseclose --junitxml=artifacts/g076-p0a/gmaster-pytest-phaseclose.xml
```
Log: `D:\gmaster-handoffs\GMASTER_INCREMENTAL_20261023_R1\GMASTER_P0A_PHASECLOSE_PYTEST.log`.
3. `node tests/e2e/g076_daily_capability.mjs` 48 PASS, `node tests/e2e/g076_daily_client.mjs` 15 PASS; `git diff --check` exit 0.

## Security contract and matrix evidence
- 3 daily gates all OFF means **server-chosen legacy**, three all ON means **server-chosen steps**. Partial and unrecognized values mean **capability HOLD**; browser never chooses via its own flag or drops to legacy on HTTP timeout/error. The legacy POST refuses NEW settlement in mixed or ON mode and preserves idempotent exact historical receipt replay; client `correct` is non-authoritative.
- Historical legacy read-only board-only projection remains safe with global privacy ON and partial mode (accepted R3 exposure tests); with unknown raw privacy value the legacy Daily GET refuses any unsafe raw question preview (409).
- Direct legacy path authentication and packaging (Dockerfile and manifest), network errors, cross-account tokens, daily replays, same-day uniqueness, two real Chrome users, historical already-submitted, badge and XP once-only, Chrome reload and response-loss covered in this isolated fixture.

## Remaining higher release gates
P0-B other-mode independent server authority, full 8-row Daily flag matrix plus cross-mode ON/OFF coexistence, disposable PostgreSQL transaction/concurrency proof, actual owner iPad Safari, new Product final arm64 image/manifest/rollback, CI and Owner GO_MERGE/GO_DEPLOY not satisfied. No production rollout is approved. The P0-A Commit SHALL be local to isolated branch only, then tracked by SHA in Notion and an incremental Git Bundle.
