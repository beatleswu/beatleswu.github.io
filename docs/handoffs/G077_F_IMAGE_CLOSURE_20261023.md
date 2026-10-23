# G077 F | Curated release runtime-closure phase | 2026-10-23

## Baseline and factual result
Derived solely from local integration SHA `a936cd19fe3aece1132977e7fee38988c71f86e9`, branch `g076-b1b2r5-local-integration-20261023`, with **no GitHub Push, GO_MERGE, Oracle deploy or production database writes**.

Previous Dockerfile curates only a limited set of source files. Although B1/B2/R5 independently passed tests in SOURCE checkout, Dockerfile was missing their Python import closure and explicit JS/Grimoire player page, so a later release image would NOT contain the new runtime. G MASTER added EXACT source-root runtime references, gated OFF by default:

- Python: g076_mode_gate.py, g076_mistakes_product.py, g076_rating_steps.py, g076_grimoire_adapter.py, g076_grimoire_catalog.py, g076_grimoire_pg_service.py, g076_grimoire_product.py
- Static Grimoire: grimoire_player.html
- Browser JS: js/game/g076_rating_step_client.js, js/game/g076_grimoire_product_client.js

No test fixture, artifact, credential or `COPY . .` was added. G MASTER authored `tests/deployment/test_g077_candidate_image_closure.py`: 10 explicit file tests, guarded static imports, Python syntax, and absent unsupported ON-default settings.
Actual beatles test:
`python -B -m pytest -q -p no:cacheprovider tests/deployment/test_g077_candidate_image_closure.py tests/deployment/test_build_manifest.py tests/deployment/test_g076_r3_image_closure.py`
=> **30 Python PASS, 0 FAIL, exit0**, raw `D:\gmaster-handoffs\GMASTER_INCREMENTAL_20261023_R1\G077_F_RUNTIME_CLOSURE.log`, JUnit `G077_F_RUNTIME_CLOSURE.xml`. First unchanged prior old-manifest baseline 62 PASS (`G077_F_RELEASE_MANIFEST_BASELINE.log`). No full BUILD_APP or ARM64 evidence for this new candidate yet.

## Important release HOLD
This only closes the **image's currently known file packaging**, not the actual mode implementations. B1 Product blueprint is still services=None; B2 forfeit still 503; R5 official trusted Product question/admission/entitlement adapter and route not installed in latest a936; Grimoire PG still gated by global privacy ON; Friend/Boss/Guild real ON remains incomplete. A new agent result may require additional COPY lines and a subsequent manifest retest; DO NOT assume this Dockerfile is final. Formal local ARM64 Build, rollback, real Chrome/PostgreSQL/Safari all-mode matrix and Owner merge/deploy remain NO-GO.

Never include temp PG credential config `.g076-r5-disposable-pg.json` or Chrome profiles in a commit. No actual Production DDL or player/question writes performed.
