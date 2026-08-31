# Go Odyssey — Truth Layer and Wave 2 Architecture Rebase

`TASK=GO_ODYSSEY_TRUTH_LAYER_AND_WAVE2_ARCHITECTURE_REBASE_001`

`SLOT=CLAUDE-1`  `MODE=READ_ONLY_VERIFICATION_AND_PLANNING`

`SOURCE_WRITE=NO`  `APP_PY_WRITE=NO`  `SCHEMA_WRITE=NO`
`PRODUCTION_MUTATION=NO`  `MERGE=NO`  `DEPLOY=NO`

Every SHA below was re-derived from a fresh `git fetch origin --prune` plus the
GitHub API on 2026-08-31. Nothing here is carried over from another agent's
report.

---

## 1. Verified canonical state

| Field | Value |
| --- | --- |
| `VERIFIED_CURRENT_MASTER_HEAD` | `b3d37e22e7471d0429d882c43c3ee16049c68ea1` |
| `VERIFIED_CURRENT_MASTER_TREE` | `39392e8c0df272fb3b0d3df2ec0c1f4f21ab7a93` |
| GitHub API `refs/heads/master` | `b3d37e22e7471d0429d882c43c3ee16049c68ea1` |
| Local `origin/master` == GitHub | `YES` |
| Master subject | `preflight: synthetic B11 canonical admission` |
| Master parent | `6228de020dea513fe33b974a37444537738c0baa` |
| CI workflows in repo | `NONE` (`.github/workflows` absent) |

---

## 2. Truth board

| Task | Reported state | Verification class | Evidence |
| --- | --- | --- | --- |
| Canonical master | `b3d37e22e…` | `VERIFIED_SHA_BACKED` | rev-parse + GitHub API agree |
| Incident019B R3 | `d24062467…` | `VERIFIED_SHA_BACKED` | commit exists, pushed, tree `75dbfdee…`, parent `6228de020` |
| A057 R1 | `90127f9a4…` | `VERIFIED_SHA_BACKED` | commit exists, pushed, tree `787da965…`, parent = master head |
| ART003 B12 scope planning | `f3bc5e96e…` | `UNVERIFIED_SELF_REPORT` (**unpublished**) | object exists **locally only**; no remote ref; absent from GitHub branch list |
| LC020 R9 Production Genesis PASS | `PASS` | `PRODUCTION_ONLY_NOT_REPO_VERIFIABLE` | no R7/R8/R9 ref, doc, or receipt anywhere in the repo |
| Incident018 code fix | merged | `VERIFIED_SHA_BACKED` | `c5455923ad…` is an ancestor of master |
| Incident018 Production acceptance | not accepted | `PRODUCTION_ONLY_NOT_REPO_VERIFIABLE` | repo cannot prove a deployed image or a live trial |
| D044 final RC | pending on R2/R3 branches | `STALE_SUPERSEDED` | R2+R3 content already admitted to master via `988039df…`; all six R3 files blob-identical to master |
| B10 / B11 canonical assets | Owner-passed and published | `VERIFIED_SHA_BACKED` (content) | every art + manifest blob on master is byte-identical to the Owner-pass branches |
| B10 / B11 admission lineage | published | `UNVERIFIED_SELF_REPORT` | the Owner-pass commits `6acccc03…` / `8bafbe45…` are **not ancestors** of master |
| Canonical master test health | implied green | **`VERIFIED_SHA_BACKED` — RED** | 20 `art003` tests fail on master head (see §4) |
| Shop / Loadout / Payments Production state | unknown | `PRODUCTION_ONLY_NOT_REPO_VERIFIABLE` | both gates are env flags defaulting to off (`CANONICAL_COIN_SHOP_PURCHASE_ENABLED`, `EQUIPMENT_CANONICAL_LOADOUT_ENABLED`) |

### `STALE_REPORTS_FOUND`

- **D044** — any report treating `bca9eaaf…` (R2) or `62ecef05e…` (R3) as
  outstanding is stale. The payload is in master.
- **LC020 R6** — its `FRESH_ORIGIN_MASTER_HEAD` of `89fffca95…` was true on
  2026-08-30 and is now six commits behind.
- **ART003 B11 manifest** — records `current_origin_master`
  `62cd841a3af78a66c4c5aba16cdfebb7814513da`, historically true, now stale.
- **F035 zone assignment** — pinned to `574b3eeb…`, now stale but harmless
  (planning-only, `gameplay_authority=false`).

### `UNVERIFIED_HIGH_RISK_CLAIMS`

1. **LC020 R9 Production atomic Genesis PASS.** This is the single most
   irreversible operation on the board and it has **zero** repository evidence.
   The last repo-side word on the subject is LC020 R6, which states
   `PRODUCTION_READ_ONLY_STATE = NOT_QUERIED` and expects
   `PRODUCTION_GENESIS_HOT = EXPECTED_FALSE`, deferring the first live read to
   R7. R7, R8 and R9 do not exist as branches, docs, or receipts.
2. **"Owner-passed and published" for B10/B11** where publication was performed
   as a detached synthetic commit rather than a merge of the reviewed branch.
3. **ART003 B12 scope conclusion** — the analysis is sound, but it lives on an
   unpushed local branch and is therefore not board-visible truth yet.

### `PRODUCTION_ONLY_CLAIMS`

- LC020 R9 Genesis execution and resulting `bootstrap_state().hot`.
- Incident018 deployed-image identity and live Lord-trial behaviour.
- Incident019B production before-state (progression/stars as players see them).
- Shop / Loadout / commerce flag values in the live environment.
- Payment provider configuration (`NEWEBPAY_*`, `PAYPAL_*` are declared
  required secrets in `deploy/build-manifest.json`; values are not repo state).

### `MISSING_EVIDENCE_ARTIFACTS`

1. `docs/planning/lc020_r9_production_genesis_receipt.json` — or any equivalent
   receipt binding the production mutation to `lc012_p2_genesis_receipt.json`
   (`834eb17f…`), the 42,804 UUID list (`cb47e9d6…`), and the post-apply row
   counts. **This is the highest-priority missing artifact in the repository.**
2. LC020 R7 (first read-only production query) and R8 evidence.
3. A deployed-image record. `deploy/build-manifest.json` explicitly states
   `latest_alias_is_deployment_record: false`, and nothing else records what is
   actually running.
4. An Incident019B production before-state capture (CODEX-1's deliverable).
5. B10/B11 admission provenance receipts explaining the detached lineage.

---

## 3. Per-branch verification

### `INCIDENT019B_R3_VERIFICATION`

```
COMMIT   d24062467100790ce681d926da15e70ab304a2ad
TREE     75dbfdeebd1e2489eea075f8b77b12e7bd8c8176
PARENT   6228de020dea513fe33b974a37444537738c0baa
REMOTE   origin/codex/incident-019b-r3-progression-continuity-fix  (published)
BASE     one commit behind master; b3d37e22e is NOT an ancestor
CONFLICT path overlap with b3d37e22e = 0  -> rebase/merge is trivial
SCOPE    6 files, +1525/-31
         app.py (+78/-31)                                  <- APP_PY WRITER
         migrations/adventure_historical_mastery_v1.py     <- SCHEMA WRITER
         adventure_progress_compatibility.py
         tools/incident_019b_progression_continuity.py
         tests/test_incident_019b_progression_compatibility.py
         tests/test_e10_zone2_runtime_foundation.py
```

Two findings that are not visible from the SHA alone:

- **The migration is invoked from `init_db()`.**
  `upgrade_adventure_historical_mastery_schema(conn)` is called inline during
  application start-up. Deploying this branch therefore *performs* a production
  schema change as a side effect of `GO_DEPLOY`. Under the stated role
  boundary, `GO_PRODUCTION_DB_MIGRATION` is a separate Owner gate. **A
  `GO_DEPLOY` on this branch silently consumes a `GO_PRODUCTION_DB_MIGRATION`
  gate.** The migration itself is additive (no `DROP`/`ALTER`/`DELETE` outside
  the disposable-DB test helper), so the risk is governance, not data loss.
- **The change removes computed stars.** `_adventure_state` previously
  synthesised `stars` from clear state and defeat percentage; R3 reduces it to
  `max(0, row['stars'])`. Players whose displayed stars were derived rather
  than stored will visibly lose stars on deploy. This is exactly why the
  production before-state is required, and it makes CODEX-1 a hard
  prerequisite for deploying R3 — not a parallel task.

### `A057_R1_VERIFICATION`

```
COMMIT   90127f9a4b9eb2055cd9004733d27a9f7b9e8b10
TREE     787da96569d7b18beaadc093c7ec7dec2f981fa4
PARENT   b3d37e22e…  (current master head)
REMOTE   origin/codex/a057-r1-paladin-one-hand-sword-validation  (published)
SCOPE    10 files, +395, pure-add: 3 PNG, 4 SVG, 1 HTML, 1 JSON, 1 test
APP_PY   NO   SCHEMA  NO   RUNTIME  NO
```

Verified clean and collision-free. The concern is not this commit, it is the
line it belongs to — see §5.

### `ART003_B12_PLANNING_VERIFICATION`

```
COMMIT   f3bc5e96e4f45af17befed5b36bfbdebfd0d601d
TREE     2b47f14e745972956f4909bcba90c6c71248cd5d
PARENT   b3d37e22e…
REMOTE   NONE — local branch codex/art003-b12-scope-definition-and-content-planning only
SCOPE    2 docs, +394
```

`REMOTE_PUBLICATION=NO`. Confirmed against both `git for-each-ref` and the
GitHub branches API.

The content is verified correct and independently reproduced:

| Zone | Planned | ART003 art present | Missing |
| --- | ---: | ---: | --- |
| Z1 | 14 | 13 | M001 |
| Z2 | 14 | 13 | M011 |
| Z3 | 13 | 12 | M022 |
| Z4 | 12 | 11 | M034 |
| Z5 | 12 | 11 | M046 |
| Z6 | 12 | 11 | M058 |
| Z7 | 12 | 11 | M071 |
| Z8 | 11 | 10 | M084 |
| Z9 | 10 | 9 | M098 |
| Z10 | 10 | 9 | M112 |

110 of 120 published; the ten gaps are exactly one per zone and are the
protected legacy runtime anchors. They resolve to `/assets/monsters/*_chibi.png`
(verified for M022 in `adventure_zone3_monster_authority.py:86`), so they are
**served, not missing** — but they are chibi-era art inside otherwise canonical
ART003 zones. That is a visual-consistency item, not a production gap.

**Conclusion: the ART003 monster-art programme is functionally complete.**
`UNPUBLISHED_CANONICAL_MONSTER_COUNT=0` is correct. B12 should be closed as
`NO_SCOPE`, not opened.

### `LC020_R9_VERIFICATION_CLASS`

`PRODUCTION_ONLY_NOT_REPO_VERIFIABLE`

Explicitly **not** `FALSE`. The production mutation may well have executed
exactly as reported. The finding is that the repository cannot corroborate it,
and the last repo-side statement (LC020 R6) actively contradicts the
pre-conditions it assumed. Until an R9 receipt is pushed, no downstream task
may treat `bootstrap_state().hot == True` as established.

---

## 4. RED FINDING — canonical master does not pass its own tests

This was not reported by any lane and is mechanically reproducible at
`b3d37e22e`:

```
python -m pytest tests/ -k art003
-> 20 failed, 85 passed
```

Failing files span **B02 through B11** — nearly every batch:

```
test_art003_b02_owner_pass_freeze_publication.py   test_art003_b07_production.py
test_art003_b03_production.py (x2)                 test_art003_b08_production.py
test_art003_b04_production.py (x2)                 test_art003_b09_r1_publication.py
test_art003_b05_production.py (x2)                 test_art003_b10_production.py
test_art003_b05_r1_publication.py (x2)             test_art003_b10_publication.py
test_art003_b06_production.py (x2)                 test_art003_b11_production.py
test_art003_b06_r1_publication.py (x2)             test_art003_b11_r1_publication.py
```

### Root cause — a class defect, not a batch defect

These are "exact git scope" tests. They assert that the set of paths changed
between a base and `HEAD` equals a hard-coded allow-list. That invariant is
meaningful **on a feature branch** and meaningless **on master**, because on
master there is nothing left to diff against.

The B11 admission commit rewrote the base resolution to:

```python
def admission_base():
    if git_succeeds("merge-base", "--is-ancestor", "origin/master", "HEAD"):
        return "origin/master"
    if git_succeeds("merge-base", "--is-ancestor", HISTORICAL_BASE, "HEAD"):
        return HISTORICAL_BASE
    raise AssertionError("no valid canonical or reviewed B11 admission base")
```

On the branch, `origin/master` is a proper ancestor and the diff is the branch
delta — the test passes. Once the branch *becomes* master, `origin/master ==
HEAD`, the diff is empty, and the assertion compares `set()` against a
non-empty allow-list. **The test is guaranteed to pass in review and guaranteed
to fail after merge.**

The older batches fail for the mirror reason: their base is pinned to a
historical SHA, so every subsequent commit adds "extra" paths to the diff. Each
new batch therefore breaks all previous batches' scope tests.

### Why the reconciliation lanes cannot fix this

`origin/codex/art003-b11-test-contract-reconciliation` (`4191b266…`) and
`origin/codex/f045-r1-b10-test-contract-reconciliation` (`711fbb3e…`) contain
test blobs that are **already byte-identical to master's**:

```
tests/test_art003_b11_production.py    master 0fa2b5f2…  ==  b11-recon 0fa2b5f2…
tests/test_art003_b10_production.py    master 9ec19367…  ==  b10-recon 9ec19367…
```

They validate in the only context where the logic holds. This explains the
recurring reconciliation lanes — `f041-r1-b08`, `f041-r2`, `f043-r2-b09`,
`f045-r1-b10`, `art003-b11` — five lanes chasing one design defect.

### Recommendation

`RETIRE_ADMISSION_SCOPE_TESTS_FROM_MASTER`. A branch-scope assertion is a
**preflight check**, not a permanent test. Move it into the admission runbook
or a preflight script that takes the base as an explicit argument. Keep on
master only the invariants that remain true forever: byte-identity of published
assets, manifest/ID-set exactness, and prior-art hash firewalls (those 85 tests
already pass). Until this is done, no honest "full canonical catch-up RC" can
be locked, because the RC gate will trip on master's own history.

### Deployment suite — near-green, with an environment caveat

```
python -m pytest tests/deployment
-> 3 failed, 932 passed, 105 skipped  (877s)
```

All three failures are in `test_release_build_working_directory.py` and are
`subprocess.TimeoutExpired` after 90s on PowerShell `git worktree` operations.
They were run from inside a git worktree on a loaded machine, so they are
plausibly environmental rather than real defects — but they are **not** proven
green and must be re-run from the primary checkout before any RC lock.

### Missing guard

There is no CI. `.github/workflows` does not exist. Nothing would have caught a
red master, and nothing will catch the next one.

---

## 5. Codex slot red team

### CODEX-1 — Incident019B Production before-state

```
DUPLICATE_WORK=NO
SOURCE_COLLISION=NO
APP_PY_COLLISION=NO
PRODUCTION_COLLISION=YES  (read-only, but same DB as any LC020 R9 follow-up)
OWNER_GATE_AMBIGUITY=NO   (read-only capture needs no mutation gate)
UNNECESSARY_INFRASTRUCTURE=NO
MISSING_ACCEPTANCE_CONTRACT=YES
```

`RECOMMENDED_CORRECTION` — Promote this to the **highest-priority production
task on the board**, ahead of LC020 R10. Define the acceptance contract
explicitly before execution: the exact per-user star/zone/defeat distribution to
capture, the cutoff instant (the migration already pins
`CUTOFF_LITERAL = "2026-08-29T13:17:30"` — the capture must agree with it or the
baseline is wrong), and the read-only proof. Note that R3 removes computed
stars, so this capture is the only way to know how many players will visibly
regress. It is a **true dependency** of deploying R3, not a parallel activity.

### CODEX-2 — LC020 post-Genesis acceptance

```
DUPLICATE_WORK=NO
SOURCE_COLLISION=NO
APP_PY_COLLISION=NO
PRODUCTION_COLLISION=YES
OWNER_GATE_AMBIGUITY=YES
UNNECESSARY_INFRASTRUCTURE=NO
MISSING_ACCEPTANCE_CONTRACT=YES
```

`RECOMMENDED_CORRECTION` — **This slot is currently unexecutable as written.**
It is defined as accepting R9, but R9 has no repository evidence and R6 asserts
the opposite pre-conditions. Accepting an unevidenced production mutation would
make a self-report canonical, which is precisely the failure mode this truth
layer exists to prevent.

Split into two tasks and run them in order:

- **LC020-R9-RECEIPT** (read-only): query production, record whether the
  identity tables exist, the registry/alias row counts, `bootstrap_state().hot`,
  and the stored bootstrap receipt; bind them to `834eb17f…` / `ee7b1bc4…` /
  `cb47e9d6…` / `473a80a3…`; push the receipt. This *is* the deferred R7 read,
  and it either upgrades R9 to `VERIFIED_SHA_BACKED` or exposes it.
- **LC020-R10** (acceptance): only after the receipt exists.

The local branch `codex/lc020-r10-post-genesis-acceptance` currently sits at
master head with no commits; it should be renamed or re-scoped before any work
lands on it.

### CODEX-3 — A057 pose-family canonicalization

```
DUPLICATE_WORK=YES
SOURCE_COLLISION=NO
APP_PY_COLLISION=NO
PRODUCTION_COLLISION=NO
OWNER_GATE_AMBIGUITY=NO
UNNECESSARY_INFRASTRUCTURE=NO
MISSING_ACCEPTANCE_CONTRACT=YES
```

`RECOMMENDED_CORRECTION` — **Halt and escalate to an Owner product decision.**
Eleven consecutive branches have iterated on one-hand-sword hero posing and
**not one has reached master**:

```
cd07fb54b A052     weapon-free one-hand sword pose derivatives   NOT_IN_MASTER
69a667f8f A052-R1D handheld weapon overlay anchor contract       NOT_IN_MASTER
691f47d3d A052-R1D-R1 frame-safe handheld compositions           NOT_IN_MASTER
776afd240 A053     motion-ready Paper Doll Lite prototype        NOT_IN_MASTER
8650b23ee A053-R2  grip forearm integration                      NOT_IN_MASTER
693b8ec61 A053-R3  true handle grip anatomy                      NOT_IN_MASTER
d8bda7c50 A054-P0  split weapon true grip architecture           NOT_IN_MASTER
d7439fd0c A055-P0  Live2D single-character feasibility           NOT_IN_MASTER
ac4c7ea49 A056-P0  canonical one-hand sword pose family          NOT_IN_MASTER
90127f9a4 A057-R1  Paladin one-hand sword validation             NOT_IN_MASTER
c9d43fa16 A051     wooden sword equip -> hero projection slice   NOT_IN_MASTER
```

A057-R2 would be the twelfth round. Every round is pure prototype output with
no acceptance contract stating what "done" looks like, so there is no
terminating condition. Meanwhile `A051` — the only branch in this family that
touches a player-visible surface (`inventory.html`, 2 files, +236) — has been
sitting unmerged since 2026-08-30.

The correct next action is not another pose round. It is: merge A051 (or
formally reject it), then have the Owner choose one pose approach and state its
acceptance criteria. Until then this lane is the clearest violation of the
"prioritize player-visible progress" constraint on the board.

### CODEX-4 — post-B11 monster roster reconciliation

```
DUPLICATE_WORK=YES
SOURCE_COLLISION=NO
APP_PY_COLLISION=NO
PRODUCTION_COLLISION=NO
OWNER_GATE_AMBIGUITY=NO
UNNECESSARY_INFRASTRUCTURE=YES
MISSING_ACCEPTANCE_CONTRACT=NO
```

`RECOMMENDED_CORRECTION` — The work this slot exists to do is **already done**
and sitting unpushed on `f3bc5e96e…`. §3 independently confirms its central
finding: 110/120 published, 10 protected anchors, 0 unpublished, no post-M120
identity anywhere. Reduce this slot to two mechanical steps: (1) push
`f3bc5e96e…` so the analysis becomes board-visible truth; (2) close ART003 as
`COMPLETE`. Do not open a reconciliation investigation into a gap that has
already been proved empty.

The one genuinely open item it surfaces is a **product** question, not a roster
question: ten zone-anchor monsters render as legacy chibi art inside canonical
ART003 zones. That belongs in the Wave 2 polish backlog.

### CODEX-5 — Full Canonical Catch-up RC reconciliation

```
DUPLICATE_WORK=NO
SOURCE_COLLISION=YES
APP_PY_COLLISION=NO
PRODUCTION_COLLISION=NO
OWNER_GATE_AMBIGUITY=NO
UNNECESSARY_INFRASTRUCTURE=NO
MISSING_ACCEPTANCE_CONTRACT=YES
```

`RECOMMENDED_CORRECTION` — This slot has a hard **ordering** conflict with
CODEX-3 and CODEX-4 and a hard **content** conflict with §4. An RC lock demands
a global source freeze; CODEX-3 (art admission) and CODEX-4 (roster docs) both
intend to land commits on master. They cannot run concurrently with a freeze.

More importantly, the RC cannot pass a full-suite gate today: 20 `art003` tests
fail at master head. Fix §4 **first**, then freeze, then lock the RC. Sequencing
it the other way produces either a false-green RC (gate weakened to fit) or an
RC that cannot be locked at all.

### `CODEX_SLOT_CONFLICTS` summary

1. CODEX-5's freeze vs CODEX-3/CODEX-4's intent to merge — mutually exclusive.
2. CODEX-2 depends on evidence that does not exist (LC020 R9).
3. CODEX-1 and CODEX-2 both touch the production database; sequence them, and
   run CODEX-1 first so the before-state is captured before anything else
   perturbs production.
4. CODEX-4 duplicates completed unpublished work.
5. CODEX-3 continues a line with no terminating condition.

### `OWNER_GATE_CONFLICTS`

- **Incident019B R3 conflates `GO_DEPLOY` with `GO_PRODUCTION_DB_MIGRATION`.**
  The migration runs from `init_db()`. Either extract it behind an explicit
  gated runner, or have the Owner knowingly issue both gates for that deploy.
- **LC020 R9's `GO_GENESIS_BOOTSTRAP` is unaccounted for in the repo.** The
  irreversible gate that flips `hot` to True has no pushed receipt.
- CODEX-2 as written would consume an acceptance decision on an unproven
  mutation.

### `APP_PY_WRITER_CONFLICTS`

`NONE`. Verified: among the currently active lanes, **only** Incident019B R3
modifies `app.py`. A057/A056/A053–A055, B12, D044-R3 and LC020-R6 do not. The
planning assumption that Incident019B holds app.py writer priority is
**CORRECT and uncontested**.

Two forward risks: (a) `app.py` is 30,019 lines, so any second writer is an
immediate conflict; (b) LC019-W2 follow-on work is explicitly queued against
app.py and must not be dispatched while 019B holds the slot.

`CLAUDE-1 APP_PY_WRITE=NO` — honoured, nothing was written.

### `PRODUCTION_EXECUTION_CONFLICTS`

CODEX-1 (read) and CODEX-2 (read + acceptance) target the same production
database. Serialize: CODEX-1 before-state capture → LC020-R9 receipt read →
CODEX-2 acceptance. Never interleave.

---

## 6. Release critical path

### `CURRENT_RELEASE_CRITICAL_PATH`

```
1. Fix the master-red art003 scope-test class defect (§4).       REPO
2. Push the B12 analysis; close ART003 as COMPLETE.              REPO
3. Capture the Incident019B production before-state.             PROD, read-only
4. Push the LC020 R9 production Genesis receipt.                 PROD, read-only
5. Global source freeze.                                         GOVERNANCE
6. Lock the full canonical catch-up RC on a green master.        REPO
7. Owner GO_DEPLOY (+ explicit GO_PRODUCTION_DB_MIGRATION).      OWNER
8. Incident018 acceptance: full 20-question Lord trial + resume. PROD
9. LC020 R10 acceptance.                                         PROD
```

Steps 1, 2 and 3 have no dependency on each other and can run in parallel.

### `TRUE_DEPENDENCIES`

- §4 test fix **→** RC lock. A red master cannot produce an honest RC.
- Incident019B production before-state **→** Incident019B R3 deploy. Without it
  the star regression is unmeasured.
- LC020 R9 receipt **→** LC020 R10 acceptance.
- Source freeze **→** exact RC lock.
- Deploy **→** Incident018 acceptance. The fix is merged (`c5455923ad…`) but
  acceptance is a live-behaviour test; it cannot run against undeployed code.
- Incident019B R3 rebase onto master head — trivial (0 path overlap), but it
  must happen before admission.

### Falsely blocking

- **"Incident019B canonical gate pending" does not block CODEX-1.** Capturing a
  production before-state is read-only and needs no canonical admission. Run it
  now.
- **"Incident018 not yet Production accepted" does not block the RC.** The code
  is in master. Acceptance is post-deploy. Treating it as a merge blocker stalls
  the release behind a step that structurally comes after it.
- **The B12 gap does not block anything.** It is empty.
- **The full canonical catch-up RC does not require A057.** No art lane is on
  the release path.

---

## 7. Wave 2 architecture rebase

`CURRENT_MAJOR_SYSTEM_COUNT=10` is retained. The historical seven-domain V2
audit is not used as an architecture boundary.

### Verified content state per zone

All ten zones already exist in `app.py:11574` (`ADVENTURE_ZONES`) with a named
Lord in `ADVENTURE_BOSS_META`. The gap is not structural.

| Layer | Coverage | Evidence |
| --- | --- | --- |
| Zone rows + Lord identity | **10/10** | `ADVENTURE_ZONES`, `ADVENTURE_BOSS_META` |
| Story: intro film, storyboards, bilingual VO | **10/10** | `assets/storyboards/go_{starter_village,slime_plains,goblin_cave,misty_forest,orc_arena,dragon_valley,sage_tower,demon_castle,ragnarok,ancient_temple}_*` |
| Canonical ART003 monster art | **110/120** | one legacy chibi anchor per zone |
| Server-owned zone monster authority | **1/10** | `adventure_zone3_monster_authority.py` only |
| E10 premium art + audio package | **2/10** | `assets/e10/{art,audio}/zone1`, `zone2` |

**This inverts the usual assumption.** Story and monster art are essentially
done for all ten zones. The Wave 2 bottleneck is exactly two things per zone:
a server monster-authority module and a Lord-trial presentation package.

### Zone 3 is half-built

E055 delivered Zone 3's monster authority (M022–M033, M060) and its client
wiring, but **no** `assets/e10/art/zone3` or `audio/zone3`. Zone 3 therefore
sits between the Zone 1–2 bar and the Zone 4–10 bar. This must be resolved
before the pattern is repeated eight more times.

### `OWNER_PRODUCT_DECISIONS_REQUIRED`

1. **Zone content tier — the single highest-leverage decision on this board.**
   Zones 1–2 carry 13 art + ~50 audio files each. Repeating that for eight
   zones is roughly 100 art and 400 audio assets. Choose:
   - **Tier A** — match Zones 1–2 everywhere. Highest fidelity, likely a
     multi-quarter art programme.
   - **Tier B (recommended)** — per zone: Lord portrait, challenge/failure/
     success backplates, key art (~5 art files), reused BGM/ambience, existing
     storyboard VO, no new voiced dialogue. Roughly one tenth the asset cost and
     still a complete-feeling zone.

   Every slice below assumes Tier B. If the Owner picks Tier A, the slice count
   is unchanged but each slice's art cost grows about tenfold.
2. Retire or keep the ten legacy chibi zone-anchor monsters (M001, M011, M022,
   M034, M046, M058, M071, M084, M098, M112).
3. The A05x hero-pose line: pick one approach and its acceptance criteria, or
   stop it.
4. Commerce enablement: do Shop / Loadout flags turn on inside RPG V1, or after?
5. Zone 3: retro-fit to the chosen tier, or accept it as-is?

### Work classification

`TRUE_DEPENDENCY`
- Master test-health repair (§4)
- Incident019B production before-state
- LC020 R9 receipt
- Source freeze → RC lock
- Zone content tier decision → every Wave 2 zone slice
- A per-zone monster-authority pattern generalized from
  `adventure_zone3_monster_authority.py`

`SAFE_PARALLEL`
- Push the B12 analysis; close ART003
- Zone 4 monster-authority module (pure-add, no app.py)
- Zone 4/5 Lord-trial art packages (asset-only)
- Storyboard/VO wiring for Zones 4+ (assets already exist)
- Leaderboard, achievements, collections read-side work

`OPTIONAL_POLISH`
- Chibi-anchor art unification
- Live2D / Paper Doll Lite hero animation (A055)
- Cinematic replay beyond Zone 1
- Additional pose families

`DEFER_INFRASTRUCTURE`
- Quest & Engagement V2 runtime cutover — `quest_catalog.py` is an explicit
  read-only foundation with no runtime path; a cutover is invisible to players
  today
- Further identity-layer expansion beyond the R9 receipt and R10 acceptance
- Battlefield monster-catalog consumer migration beyond what is already merged
- Live events, guild systems, collections infrastructure
- Any new commerce surface before existing Shop/Loadout flags are enabled

### `WAVE2_VERTICAL_SLICE_PLAN`

The task book asks for Zone 4 onward. Slice 1 deviates deliberately: Zone 3 is
half-built, and finishing it is what produces the reusable template every later
slice depends on. It is the smallest possible slice and it ships player-visible
value immediately.

**`SLICE_1` — Zone 3 Goblin Cave completion (and the Zone Slice Template)**
- *Player experience*: Zone 3 looks and sounds like Zones 1–2 — a Lord portrait,
  a challenge backplate, a real Lord ritual, a success/failure screen.
- *Content*: `assets/e10/art/zone3/lord_trial/*` at the chosen tier; BGM and
  ambience reused from Zone 2.
- *Monsters*: already shipped (M022–M033, M060).
- *Boss*: `goblin_centurion` — identity exists, presentation does not.
- *NPC / story*: already shipped (`go_goblin_cave_*`).
- *Quest*: none new.
- *Drops / equipment*: existing registries; no new items.
- *Spirit*: not required.
- *Go content*: books 5–6, already mapped.
- *Progression gate*: unchanged.
- *Replay*: existing cleared-zone replay.
- *Acceptance*: a player clears Zone 3 end-to-end and the Lord trial is visually
  indistinguishable in structure from Zone 2's; the art package validates
  against a published zone-package contract; no `app.py` change.
- *Also delivers*: `docs/planning/zone_slice_template_v1.md` — the exact file
  list, contract and test shape every later zone reuses.

**`SLICE_2` — Zone 4 Misty Forest**
- *Player experience*: the first genuinely new zone in Wave 2.
- *Content*: `adventure_zone4_monster_authority.py` (M034–M045 pattern) +
  Zone 4 art package.
- *Monsters*: 11 canonical ART003 + 1 legacy anchor (M034).
- *Boss*: `misty_phantom_rabbit_king`.
- *Story*: `go_misty_forest_*` already present — wire it.
- *Drops / equipment*: existing registries; one zone-appropriate drop table.
- *Spirit*: not required.
- *Go content*: books 7–8.
- *Progression gate*: Zone 3 clear.
- *Acceptance*: full clear, Lord trial, replay, monster identity persisted
  server-side; template followed exactly; no `app.py` change beyond the registry
  hook that Slice 1 standardizes.

**`SLICE_3` — Equipment becomes visible on the hero**
- *Player experience*: buy a wooden sword, equip it, **see it** on the hero.
  This is the highest-value unmerged work in the repository.
- *Content*: land A051 (`inventory.html` hero projection, +236 lines) and one
  Owner-chosen pose approach from the A05x line.
- *Equipment*: enable `EQUIPMENT_CANONICAL_LOADOUT_ENABLED` behind the existing
  gate; `equipment_loadout_service` / `equipment_ownership_service` already
  exist.
- *Drops*: existing wooden/iron sword assets.
- *Acceptance*: end-to-end drop → inventory → equip → hero render, on iPad;
  legacy clients unaffected with the flag off.
- *Note*: this slice is what terminates the A05x loop. Sequence it before any
  further pose round.

**`SLICE_4` — Zone 5 Orc Tribe + the first Elite encounter**
- *Player experience*: a new zone plus a visibly harder mid-zone encounter.
- *Content*: `adventure_zone5_monster_authority.py` + Zone 5 art package.
- *Monsters*: 11 canonical + M046 anchor; promote 1–2 to Elite.
- *Boss*: `iron_orc_chieftain`.
- *Drops*: Elite drop table — the first meaningful reward differentiation.
- *Go content*: books 9–10.
- *Acceptance*: the Elite encounter is server-authoritative, distinguishable in
  the client, and its drops resolve through the existing settlement path.

**`SLICE_5` — Zone 6 Dragon Valley + drop→shop→equip loop closure**
- *Player experience*: the reward economy visibly closes — Zone 6 drops feed
  the shop, the shop feeds the loadout, the loadout shows on the hero.
- *Content*: `adventure_zone6_monster_authority.py` + Zone 6 art package.
- *Boss*: `grand_temple_knight`.
- *Commerce*: enable `CANONICAL_COIN_SHOP_PURCHASE_ENABLED` after a production
  readiness preflight
  (`scripts/release/commerce_production_readiness_preflight.py` already exists).
- *Go content*: books 11–12.
- *Acceptance*: a player can earn coins in Zone 6, spend them, equip the result,
  and see it — with rollback proven for both flags.

After Slice 5 the template is proven three times and Zones 7–10 become
repeatable content work rather than architecture work.

---

## 8. Red team findings

1. **Canonical master is red and nobody noticed.** 20 `art003` failures at
   `b3d37e22e`. No CI exists to catch it.
2. **A test class that is structurally guaranteed to break at merge.** The
   `admission_base()` heuristic passes on a branch and fails on master, by
   construction. Five reconciliation lanes have chased the symptom.
3. **Canonical admissions are lineage-detached.** B10, B11 and D044 were
   admitted as synthetic commits whose Owner-pass branches are not ancestors of
   master. Content is byte-identical and verified — so this is a traceability
   defect, not a content defect — but "Owner-passed and published" currently
   cannot be proved from master's history alone.
4. **The most irreversible operation on the board has the least evidence.**
   LC020 R9 claims a production Genesis while the last pushed artifact (R6)
   states production was never even queried.
5. **`GO_DEPLOY` silently consumes `GO_PRODUCTION_DB_MIGRATION`** for
   Incident019B R3, because the migration runs from `init_db()`.
6. **A prototype line with no terminating condition.** Eleven A05x branches,
   zero merges, and A057-R2 queued as the twelfth.
7. **A slot assigned to work that is already finished.** CODEX-4 duplicates
   `f3bc5e96e…`, which is complete but unpushed.
8. **Completed work is stranded off-remote.** The B12 analysis exists only on a
   local branch, so the board cannot see it.
9. **Freeze and merge slots are scheduled concurrently.** CODEX-5 cannot freeze
   while CODEX-3/4 intend to land commits.
10. **Player-visible work is consistently deprioritized.** A051 — the one branch
    that changes what a player sees — has been unmerged for a day while eleven
    prototype rounds ran.

---

## 9. Recommended board changes

1. Insert **RC-TEST-HEALTH-1**: retire the admission-scope test class from
   master and restore a green canonical branch. Blocks CODEX-5.
2. Add a minimal CI that runs the suite on every push to master.
3. Re-scope **CODEX-2** into LC020-R9-RECEIPT (read-only, first) and LC020-R10
   (acceptance, second).
4. Promote **CODEX-1** to the first production action on the board.
5. Reduce **CODEX-4** to: push `f3bc5e96e…`, close ART003 as COMPLETE.
6. Halt **CODEX-3**; replace it with an Owner decision packet on the A05x line,
   and land or reject A051.
7. Move **CODEX-5** behind items 1 and 3–6, and define the freeze window
   explicitly.
8. Put the **zone content tier** decision to the Owner before any Wave 2 slice
   is dispatched.
9. Require every future admission commit to record the reviewed branch head it
   replays, so lineage-detached admissions stay auditable.
10. Add an acceptance contract to every art/prototype lane. A lane with no
    terminating condition will not terminate.
