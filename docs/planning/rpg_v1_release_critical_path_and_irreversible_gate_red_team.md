# RPG V1 — Release Critical Path and Irreversible-Gate Red Team

`TASK=GO_ODYSSEY_RPG_V1_RELEASE_CRITICAL_PATH_AND_IRREVERSIBLE_GATE_RED_TEAM_001`

`SLOT=CLAUDE-1`  `MODE=READ_ONLY_INDEPENDENT_VERIFICATION`

`SOURCE_WRITE=NO`  `APP_PY_WRITE=NO`  `SCHEMA_WRITE=NO`
`PRODUCTION_MUTATION=NO`  `MERGE=NO`  `DEPLOY=NO`  `ROLLBACK=NO`

Re-derived from a fresh `git fetch origin --prune` plus the GitHub API on
2026-08-31. Codex lane reports were read as *claims* and re-verified against
git objects wherever mechanical verification was possible.

---

## 0. Verified anchors

| Field | Value | Class |
| --- | --- | --- |
| `CURRENT_MASTER_HEAD` | `b3d37e22e7471d0429d882c43c3ee16049c68ea1` | `VERIFIED_SHA_BACKED` |
| `CURRENT_MASTER_TREE` | `39392e8c0df272fb3b0d3df2ec0c1f4f21ab7a93` | `VERIFIED_SHA_BACKED` |
| GitHub API master | identical | `VERIFIED_SHA_BACKED` |
| Production app source | `cc6b7915e4a70677ac7e1bafacff69fc70e33b84` | `VERIFIED_SHA_BACKED` (object found) |
| Production image | `go-odyssey-app:cc6b7915`, digest `sha256:0805b691…` | `PRODUCTION_ONLY_NOT_REPO_VERIFIABLE` |

### Production is not on the canonical line

```
cc6b7915  origin/release/b071-historical-leaderboard-consumer-exact-candidate
merge-base with master = 574b3eeb  (PR #428, 2026-08-29)
commits on production not in master = 3
commits on master not in production = 49
```

CODEX-5's RC lane records `source_sha_provenance = "Git object unavailable in
current repository"`. That is wrong — the object exists on the release branch
above. That lane could not diff production against master, which is how the
regression in §5 went unseen.

Content check of the three production-only commits:

| Commit | Carried forward to master? |
| --- | --- |
| `cc6b7915` B071 historical leaderboard consumer | **YES** — `migrations/historical_leaderboard_evidence_v1.py` + app wiring present |
| `7028649a` B065 hero cache guard static route | **YES** — route present at `app.py:26527`, test tracked |
| `d0b39a34` B061 item journal in static generation | **NO** — see §5 |

---

## 1. Incident019B — gate separation

### Mechanical result

```
app.py:30013     init_db()          inside `if __name__ == '__main__':`
Dockerfile:338   CMD ["python", "app.py"]      -> __name__ == '__main__'
scheduler.py:15  app.init_db()
```

`init_db()` runs on **every ordinary container start**, in both the app and
scheduler containers.

`INCIDENT019B_DB_GATE_COUPLING` — for **R3** (`d24062467`): **CONFIRMED**.
`upgrade_adventure_historical_mastery_schema(conn)` is invoked inside
`init_db()`, so `GO_DEPLOY` would execute DDL.

### Correction to my previous turn — the coupling is systemic, not 019B-specific

`init_db()` spans `app.py:4550`–`5754` and **already** invokes four migrations
on canonical master, all of which ship in production today:

```
app.py:4744  upgrade_review_log_submission_schema(conn)
app.py:5122  upgrade_question_capacity_schema(conn)
app.py:5716  upgrade_domain_event_outbox(conn)
app.py:5735  upgrade_historical_leaderboard_evidence_schema(conn)
```

R3 was conforming to an established, already-deployed pattern. Singling out
019B while four identical couplings ship unremarked would be inconsistent.
`GO_DEPLOY` on this codebase has *always* implied additive-DDL authority.

### R5B already fixes it

`7a0f1f94e` (`origin/codex/incident-019b-r5b-pre-merge-gate`) removes both the
import and the `init_db()` call, and routes creation through
`tools/incident_019b_progression_continuity.py`, which requires
`--capture-baseline --execute --owner-gate GO_PRODUCTION_DB_MIGRATION`. Its
test file pins the invariant (`test_incident019b_migration_is_not_reachable_from_app_init_db`,
`test_ordinary_deploy_gate_cannot_be_reused_for_baseline_capture`).

The read path is safe with the tables absent:
`adventure_progress_compatibility.py:207` guards on `_table_exists` for both
tables and falls back to trusted-only evidence.

The migration is DDL-only — no `INSERT`, no `ALTER` of existing tables, PG
advisory-locked, caller owns the transaction.

### The three requested distinctions

| Concept | Status |
| --- | --- |
| `SOURCE_ADMISSION_SAFETY` | **R3 = NO** (startup DDL). **R5B = YES**, conditional on the §2 decision and a rebase onto master head. |
| `PRODUCTION_MIGRATION_AUTHORIZATION` | Separate `GO_PRODUCTION_DB_MIGRATION`, consumed only by the gated runner. Not implied by deploy under R5B. |
| `PRODUCTION_COMPATIBILITY_EXECUTION` | The baseline capture itself. Not executed. Independently gated, and safe to defer past deploy — the feature stays dormant while the tables are absent. |

### Residual risk

`upgrade()` raises `SchemaMismatch` on an incomplete schema. Because the
runner owns it rather than `init_db()`, a failure aborts the *capture*, not
application start-up. Under R3 it would have aborted start-up. One more reason
R5B, not R3, is the admissible head.

---

## 2. Incident019B — player-visible star continuity

### What "computed stars removed" actually means

Stars have exactly two server writers, both in the boss-finish path:

```
app.py:12765   INSERT ... stars = 1 if passed else 0
app.py:12781   UPDATE ... stars = GREATEST(stars, 1)
```

**Stored `adventure_boss_progress.stars` can only ever be 0 or 1.** Two and
three stars are *purely derived at read time* by the pre-019B formula:

```
stars = 0; if cleared: 1; if pct >= 60: 2; if defeated >= total: 3
stars = max(stars, stored)
```

R3 and R5B both replace that with `stars = max(0, int(row.get('stars') or 0))`.
Verified in `7a0f1f94e:app.py:12004`, with the writers unchanged.

### Can currently visible values decrease? — NO

From the R5A production before-state (`e589bceba`, read-only, stability
double-checked):

```
users                                            220
players_with_current_nonzero_adventure_mastery     1
current_trusted_membership_pairs                 228
largest per-zone trusted numerator          84 / 1939  = 4.3%
BOSS_UNLOCK_PCT = 30      two-star threshold = 60%
```

Production `cc6b7915:app.py` already restricts correctness evidence to the
trusted Map-Battle marker — byte-identical logic to master's pre-019B version.
So `pct >= 60` and `defeated >= total` are **already unreachable for every
account in production today**. Derived 2★/3★ are not currently displayed.

`INCIDENT019B_STAR_CONTINUITY_RISK = LOW_FOR_DECREASE`.

### But two consequences are real, and neither has been flagged

**(a) Restoration without star restoration.** R5B restores the mastery
numerator from 228 trusted pairs to a frozen union of ~83,942
(`current_expected_frozen_union`). A player whose display showed 2★/3★ *before*
the original regression gets the numerator back but not the stars, because the
new rule caps at the stored value.

**(b) 2★ and 3★ become structurally unreachable — forever, for everyone.**
This is not a migration artifact; it is a permanent property of the new rule
combined with the unchanged writers. Downstream consequences, all verified:

| Consumer | Effect |
| --- | --- |
| `js/e9/quest_definitions.js:13` — `main.complete_three_star_zone`, `progressType: numeric, target: 3, source: adventure.maxStars` | Permanently capped at 1/3. **Never completable.** Players who already completed it regress. |
| `app.py:12109` `stars_complete = stars >= 3` | Always `False`. |
| `app.py:12264`, `12283` `refill = next(z for z in ordered if _stars(z) < 3)` | Always matches the *first* zone, so the `replenish_stars` recommendation degenerates to a constant. |

R5B's `test_r5b_star_code_reads_only_server_owned_boss_state` shows this was a
deliberate choice, framed as a correctness invariant. It is really a **product
decision**, and as written it breaks a shipped quest and a shipped
recommendation surface. `OWNER_PRODUCT_DECISION_REQUIRED`.

### Can grandfathering infer unauthorized progress? — NO

`stars` is read only by display and recommendation code. It gates nothing:

- unlock = `previous_cleared or cleared or placement_unlocked` — no `stars`
- `boss_ready` = `pct >= BOSS_UNLOCK_PCT` — no `stars`
- rewards / Spirit / Coins / equipment — separate tables, corroborated by the
  R5A `authority_firewall` block (`reward_claimed`, `currency_log`,
  `spirit_evolution_events`, `player_inventory`, `player_wardrobe`, …)

So a display-only grandfathered star cannot imply a Boss clear, unlock, reward,
Spirit, Coin, or equipment grant — **provided it is stored in the compatibility
baseline, never written into `adventure_boss_progress.stars`.** Writing it into
the authority column would corrupt Boss-state authority and is the one thing
that must not happen.

### The three-way separation

| Layer | Definition | Storage | Mutability |
| --- | --- | --- | --- |
| `GRANDFATHERED_VISIBLE_ENTITLEMENT` | pre-cutoff derived stars, replayed once with the old formula against pre-cutoff evidence | compatibility baseline table, frozen | write-once at capture; never increases |
| `CURRENT_SERVER_AUTHORITY` | `adventure_boss_progress.stars` ∈ {0,1} | authority table | boss-finish path only |
| `NEWLY_EARNED_PROGRESS` | anything after `CUTOFF_LITERAL = 2026-08-29T13:17:30` | authority table | authority path only |

Display becomes `max(authority, grandfathered)`; every gate keeps reading
`authority` alone. This satisfies the hard invariant without granting anything.

`INCIDENT019B_REQUIRED_FIX`:
1. Rebase R5B onto master head (0 path overlap with `b3d37e22e`; trivial).
2. Owner decision on stars — grandfather, or accept a permanent 1★ ceiling.
3. If the ceiling is accepted, `main.complete_three_star_zone` and the
   `replenish_stars` selector must be repaired in the same change; shipping an
   uncompletable quest is not acceptable either way.

---

## 3. LC020 — version-skew architecture

### The R9 receipt now exists

My previous turn recorded the R9 Production Genesis receipt as
`MISSING_EVIDENCE_ARTIFACT`. It has since been published:
`origin/codex/lc020-r10-post-genesis-acceptance` @ `1c4f23f94`,
`docs/planning/lc020_r10_post_genesis_production_baseline.json`.

The repo-side bindings in it are `VERIFIED_SHA_BACKED` (they reproduce
`834eb17f…`, `ee7b1bc4…`, `cb47e9d6…`, `473a80a3…`,
`migrations/puzzle_identity_registry_v1.py` = `ad5bd5bc…`). The production
observations remain `PRODUCTION_ONLY_NOT_REPO_VERIFIABLE`, but they are now
*evidenced, internally consistent, and reproducible in method* — a materially
stronger state than an unbacked self-report.

### Source status of the read adapter — canonical

```
master  identity_read_adapter.py        342c0d3e   app.py:197, grimoire_api.py:24
        puzzle_identity_read_window.py  109a15a5
        puzzle_identity_store.py        336937f4
        migrations/puzzle_identity_registry_v1.py  931109e3
Dockerfile:125-127, 183  -> all four packaged
puzzle_identity_genesis_bootstrap.py     NOT packaged (executor deliberately excluded)
```

`LC020_FULL_RC_SOURCE_READY = YES` (`VERIFIED_SHA_BACKED`).

### Production has none of it

`cc6b7915` predates the LC017 merge `3f98c204`; all five identity modules are
absent from the production source, matching the R10 artifact's
`live_lc020_modules_missing` and `live_runtime_lc020_references_found: false`.

### Is HOT + old image safely additive, or incidentally surviving? — **safely additive, by construction**

`migrations/puzzle_identity_registry_v1.py` creates four new tables
(`puzzle_identity_registry`, `_alias`, `_lineage`, `_bootstrap_receipt`), all
foreign keys internal, all five triggers on its own tables, **zero `ALTER
TABLE` against any pre-existing table**. The old image cannot observe them.
This is namespace isolation, not luck.

`LC020_CURRENT_VERSION_SKEW_SAFE = YES`.

### Will deploying the adapter against a HOT DB change behaviour? — **NO, and this is provable**

The gate is `_identity_tables_present(conn) and reader.hot`
(`app.py:3281`–`3286`). Both become true on the first deploy, so
`_identity_group_key_map` stops returning `{}` for the first time in
production. The question is whether any two legacy ids can then share a
`group_key` and fold two rows into one.

`IdentityKey.group_key` (`identity_read_adapter.py:50`) folds only on
`("uuid", value)`. `UNRESOLVED` / `UNAVAILABLE` / `LEGACY` each get a
per-legacy-id bucket. So folding requires two distinct legacy ids resolving
`EXACT` to the *same* `source_record_uuid`.

Production state from the R10 artifact:

```
identity_registry_count              42804
LEGACY_QUESTION_ID_current           42782
LEGACY_QUESTION_ID_not_current          22
legacy_collision_group_count            11
current_legacy_collision_group_count     0     <-- decisive
alias_distinct_identity_count        42804
collision sample 40479: 2 distinct identities, 0 current rows (fail-closed)
```

`current_legacy_collision_group_count = 0`, combined with the partial unique
index `uq_pia_current_alias` on `(alias_kind, alias_value, alias_context) WHERE
is_current`, means the current legacy alias set is a **strict bijection**:
42,782 legacy ids ↔ 42,782 distinct identities. The 22 collided rows carry
`legacy_question_id_is_current = false`, so they resolve non-`EXACT` and keep
their own buckets. Ids outside the corpus resolve `MISSING` → `("legacy", id)`.

**No two legacy question ids can share a group key.** Every aggregate reader —
the 11 `_IdentityKeyedSet` sites in `app.py` and the `grimoire_api` daily
training path — produces byte-identical output before and after the flip.

`LC020_SEPARATE_HOTFIX_REQUIRED = NO`. Full RC inclusion is sufficient; the
adapter is already canonical and already packaged.

### R10 `FAIL` is a sequencing artifact, not a defect

Every database-side check passes: table count, registry 42,804, alias, lineage,
receipt `APPLIED`, `hot_mode`, object inventory, corpus unchanged, pre-genesis
backup retained and hash-verified, no deploy, no feature enablement. The only
two failures are `read_adapter_pass` and `unknown_fail_open_pass`, both because
the live image has no adapter to accept. Acceptance was attempted before the
implementing code was deployed.

`ROLLBACK_REQUIRED = NO`. A verified pre-genesis dump exists
(`lc020_pre_genesis_20260831T050307Z.dump`, sha256 matched, 823 entries).

### Deploy-ordering constraint caused by HOT

One, and it is mild: **the RC must contain the read adapter.** It does. There
is no ordering constraint in the other direction, because the DB is inert to
the old image. Do not deploy an RC that strips the identity modules.

### New P1 — runtime corpus differs from the frozen genesis corpus

```
production /app/data/questions.json   41591 records, sha256 b7b4eedf…
frozen genesis corpus                 42804 records, sha256 88da3e43…
frozen_genesis_substituted_into_runtime: false
```

The identity registry was frozen against a corpus that production does not
serve — a 1,213-record difference. This is *safe* (unmatched ids fall to the
`("legacy", id)` bucket, still a bijection) but it means a fraction of live
questions will never resolve to a canonical identity. The direction of the
difference has not been established. Add to the next production read:
count runtime ids absent from `puzzle_identity_alias` where
`alias_kind='LEGACY_QUESTION_ID' AND is_current`, and the reverse.

---

## 4. ART003 canonical-master test baseline

Measured at `b3d37e22e` (master unchanged since):

```
python -m pytest tests/ -k art003   ->  20 failed, 85 passed
```

Root cause, unchanged from my previous artifact: `admission_base()` returns
`origin/master` when `origin/master` is an ancestor of `HEAD`. On a branch that
is the branch delta and the scope assertion passes; once the branch *becomes*
master the diff is empty and the assertion compares `set()` against a non-empty
allow-list. Guaranteed green in review, guaranteed red after merge.

| Question | Answer |
| --- | --- |
| Must it be repaired before Full RC lock? | **YES.** A full-suite gate cannot pass, so the RC would either fail to lock or be locked against a weakened gate. |
| Is it test-only? | **YES** for the ART003 family — the published assets and manifests are byte-identical to the Owner-pass branches. |
| Can it mask real regressions? | **YES — and it already has.** See §5. |
| Does fixing it touch source provenance? | **NO.** Test infrastructure only; no art, manifest, or runtime file changes. |

`ART003_TEST_REPAIR_REQUIRED_BEFORE_RC = YES`

---

## 5. NEW P0 — master has never carried B061's static-generation fix

Production commit `d0b39a345` ("fix(release): include item journal in static
generation") added `item_journal.html` to
`deploy/live-static-asset-inventory.json` → `required_in_generation.entries`,
plus the assertion `entries.count("item_journal.html") == 1` in
`tests/deployment/test_static_release_tooling.py`.

Neither exists on master. Traced through the last twelve master commits that
touched that file, back to 2026-08-12 — `item_journal.html` has **never** been
in master's `required_in_generation`:

```
d59ba805a  2026-08-29  chore: assemble RPG V1 release candidate packaging   False
a73e58d3c  2026-08-29  fix RPG release dependency packaging closure         False
18f8af38a  2026-08-20  feat(e10): generic Zone 1-10 cinematic replay        False
…  (all False)
```

`item_journal.html` is still in `eligible_files` and the page is tracked, so
this is a contract regression, not a missing file. `required_in_generation` is
the set the static tooling "stages, ships, and verifies in every generation" —
the mechanism whose own description cites `i18n.js` and `sw.js` as governed
"because they were observed stale in live-static".

**An RC built from master today would stop governing `item_journal.html` and
could serve a stale copy — regressing a fix that is live in production.**

And nothing catches it:

```
python -m pytest tests/deployment/test_static_release_tooling.py
->  74 passed
```

The guard was deleted along with the contract entry. This is a second,
independent instance of the §4 class of problem: a test adjusted to fit the
payload, hiding a real regression.

`REQUIRED`: restore both the entry and the assertion before the source SHA is
locked. No branch exists for this yet.

---

## 6. Owner gate inventory

| Gate | Status | Basis |
| --- | --- | --- |
| `GO_MERGE_INCIDENT019B` | **NOT GRANTED — and not yet requestable.** Head should be R5B `7a0f1f94e`, not R3 `d24062467`; blocked on the §2 star decision and a rebase. | repo + R5B tests |
| `GO_MERGE_OTHER_RELEASE_REQUIRED_SOURCE` | **REQUIRED** for (a) ART003 test repair, (b) B061 item-journal restoration. No branch exists for (b). | §4, §5 |
| `GO_PRODUCTION_DB_MIGRATION_REQUIRED_BEFORE_DEPLOY` | **NO** under R5B. The feature is dormant while the tables are absent; the capture can follow the deploy under its own gate. | `_table_exists` guard, gated runner |
| `GO_GENESIS_BOOTSTRAP_REQUIRED_AGAIN` | **NO.** Receipt `APPLIED`, singleton enforced by `bootstrap_singleton … UNIQUE`; once-only by construction. | R10 artifact |
| `GO_DEPLOY_READY` | **NO.** §4 and §5 unresolved; no locked source SHA; Incident018 acceptance unexecuted. | — |
| `GO_ROLLBACK_REQUIRED` | **NO.** DB additive and inert to the running image; verified pre-genesis dump retained. | §3 |
| `GO_ENABLE_SHOP` | **NOT GRANTED.** `CANONICAL_COIN_SHOP_PURCHASE_ENABLED` unset, evaluates false in production. | R10 `feature_firewall` |
| `GO_ENABLE_LOADOUT` | **NOT GRANTED.** `EQUIPMENT_CANONICAL_LOADOUT_ENABLED` unset, evaluates false. | R10 `feature_firewall` |
| `GO_REVENUE_LIVE` | **NOT GRANTED.** `GO_REVENUE_V1_PREMIUM_CLAIM_ENABLED` unset. Note: `NEWEBPAY_TEST=0` and `PAYPAL_TEST=0` — both providers are configured in **live** mode. Provider configuration is not authorization and must not be read as one. | R10 `feature_firewall` |

---

## 7. Codex lane red team

| Lane | Release-critical? | Merge before freeze? | Finding |
| --- | --- | --- | --- |
| **CODEX-1** 019B R5B gate + star continuity | **YES** | **YES**, after rebase + star decision | Gate separation is done and well built. **Star continuity is NOT addressed** — `7a0f1f94e:app.py:12004` is unchanged from R3, and the lane's own test pins the 1★ ceiling as intended. §2(b) is unflagged by the lane. |
| **CODEX-2** LC020 R11 read-adapter provenance + RC inclusion | **NO** — already satisfied | Docs may merge any time | The adapter is already canonical and already packaged (§3). This lane's real remaining value is the §3 corpus-drift check, not RC inclusion. |
| **CODEX-3** A051 hero equipment admission preflight | **NO** | Owner's call | `4d57be170`: preflight doc + `inventory.html` + test. Player-visible and small, but a runtime change. Admit only by explicit pre-freeze decision. |
| **CODEX-4** ART003 admission test infrastructure repair | **YES — highest-priority source lane** | **YES** | No branch pushed yet; local branch sits at master head with no commits. This blocks the RC gate (§4). |
| **CODEX-5** Wave2 Zone3 template + Zone4 | **NO** | **NO** | Pure Wave 2. Must not enter the V1 RC. Note the *previous* CODEX-5 RC-reconciliation lane (`334d50328`) is complete and now unassigned. |

### Errors found in lane output

1. **`334d50328` claims `incident019b.before_snapshot_status = MISSING`.** The
   snapshot exists (`e589bceba`) with status `PARTIAL`. The *global* before-state
   is fully captured — 220 users, per-zone numerators, authority-table
   separation. Only the single R1 safe pseudonym `7167b6214d65` is unresolved,
   and it maps to no live account under the reviewed `md5(user_id)[:12]`
   convention. Elevating one unresolvable pseudonym to a full RC blocker — as
   that lane's `next_task` does — is a **false blocker**. The global snapshot
   supplies everything needed to measure regression.
2. **`334d50328` records the production source SHA as "Git object unavailable".**
   It is available (§0). That lane worked from a stale fetch and therefore could
   not perform the production-vs-master diff that surfaces §5.
3. **`334d50328` lists "community leaderboard rewards enabled" and "payment
   providers configured live" as production blockers.** Both are pre-existing
   facts of the running system, unchanged by this release. They are context, not
   gates.

### App.py

`APP_PY_ACTIVE_WRITER = codex/incident-019b-r5b-pre-merge-gate (7a0f1f94e)`
`APP_PY_CONFLICTS = NONE` — verified across all seven active lane branches;
only R5B touches `app.py`. A051 touches `inventory.html`; every other active
lane is docs-only.

---

## 8. Release scope firewall

`RPG_V1_REQUIRED_BRANCHES`
- `codex/incident-019b-r5b-pre-merge-gate` (`7a0f1f94e`) — after rebase + star decision
- ART003 admission-test repair — **branch does not exist yet**
- B061 item-journal restoration — **branch does not exist yet**

`SAFE_OPTIONAL_PRE_FREEZE_BRANCHES` (docs-only, zero runtime risk)
- `codex/incident-019b-r5a-production-before-state` (`e589bceba`)
- `codex/lc020-r10-post-genesis-acceptance` (`1c4f23f94`)
- `codex/art003-post-b11-monster-roster-gap-reconciliation-001` (`bdf56401c`)
- `codex/rpg-v1-full-canonical-catch-up-rc-reconciliation-001` (`334d50328`)
- `codex/a057-r2-one-hand-sword-canonical-preflight` (`5047ffe4f`)
- `codex/art003-b12-scope-definition-and-content-planning` (`f3bc5e96e`) —
  **still unpushed after a full day**
- `codex/a051-hero-equipment-admission-preflight` (`4d57be170`) — only the doc;
  `inventory.html` is a deliberate admission decision

`POST_RPG_V1_WAVE2_BRANCHES`
- `a052` … `a057-r1` hero-pose prototypes (`cd07fb54b`, `69a667f8f`, `691f47d3d`,
  `776afd240`, `8650b23ee`, `693b8ec61`, `d8bda7c50`, `d7439fd0c`, `ac4c7ea49`,
  `90127f9a4`) — still zero merges across the whole line
- CODEX-5 Zone 3 template / Zone 4 Misty Forest work

`DO_NOT_ADMIT_BRANCHES`
- Any new Wave 2 zone content after the freeze
- `origin/release/b071-…` as a merge source — it is the production baseline;
  cherry-pick B061 rather than merging the branch

**Already-admitted Wave 2 content, for the record:** E055 Zone 3 (`c1a55daeb`)
is in master and its eleven monster PNGs are in the Dockerfile. Zone 3 ships in
the V1 RC whether or not it is called V1 scope. Excluding it would require a
revert, which I do not recommend.

---

## 9. Critical path and gate sequence

### `EXACT_CRITICAL_PATH`

```
S1  ART003 admission-test repair                    SOURCE   CODEX-4   blocks RC gate
S2  B061 item_journal restoration (entry + assert)  SOURCE   unassigned
S3  Owner star-continuity decision                  OWNER    blocks S4
S4  019B R5B: rebase + star outcome + quest repair  SOURCE   CODEX-1
S5  Review S1, S2, S4
S6  GO_MERGE x3  (order: S1, S2, then S4 last -- app.py writer)
S7  Green full-suite run on canonical master
S8  GLOBAL SOURCE FREEZE
S9  Lock exact RC source SHA
S10 RC build: image + static + SW  (release-<LOCKED_SHA>)
S11 Predeploy production read-only verification
S12 GO_DEPLOY
S13 Production acceptance: Incident018 Lord matrix
S14 Device acceptance: D041, 43 checks, 3 form factors
S15 GO_PRODUCTION_DB_MIGRATION -> 019B baseline capture   (separate, after deploy)
S16 LC020 R10 re-run against the deployed adapter
S17 Incident018 observability sunset
S18 RPG V1 closeout
```

**Must not be reordered**

- S7 before S8 — freezing a red master locks a false-green RC.
- S8 before S9 — an SHA locked while merges continue is not the built SHA.
- S9 before S10 — static and SW identity derive from the locked SHA.
- S12 before S13 and S16 — both test code that is not yet running. This is
  exactly why R10 reported FAIL.
- S15 **after** S12 — the capture must run against the deployed schema, and
  R5B keeps it dormant until then.
- S17 last — observability is the instrument for S13; retiring it earlier
  removes the evidence channel. `incident_018_observability.py` is imported at
  module level (`app.py:223`) and packaged (`Dockerfile:133`), so its removal
  is a coordinated source + Dockerfile change, never a deletion alone.

**Safe to run in parallel**: S1, S2, S3 are mutually independent. R5A and R10
production reads are read-only and already complete.

### `EXACT_OWNER_GATE_SEQUENCE`

```
1  Star-continuity product decision              (not a gate; blocks S4)
2  GO_MERGE  ART003 test repair
3  GO_MERGE  B061 item-journal restoration
4  GO_MERGE  Incident019B R5B                    (app.py writer last)
5  Source freeze declaration                     (governance)
6  GO_DEPLOY  release-<LOCKED_SHA>               (no DB gate consumed)
7  GO_PRODUCTION_DB_MIGRATION                    019B baseline capture only
8  --- RPG V1 closeout boundary ---
9  GO_ENABLE_LOADOUT / GO_ENABLE_SHOP / GO_REVENUE_LIVE   separate, later, each on its own evidence
```

`GO_GENESIS_BOOTSTRAP` does not appear — it is spent and once-only.

### Readiness

```
READY_TO_LOCK_FULL_RC_SOURCE_SHA = NO
READY_FOR_FULL_RC_BUILD          = NO
READY_FOR_GO_DEPLOY              = NO
```

`REMAINING_P0_BLOCKERS`
1. ART003 admission-test class defect — 20 failures on canonical master (§4)
2. B061 `item_journal.html` static-generation regression, silently untested (§5)
3. Owner star-continuity decision, plus the uncompletable three-star quest (§2)
4. Incident019B R5B not rebased and not merged
5. Incident018 production acceptance unexecuted

`REMAINING_P1_BLOCKERS`
1. Runtime corpus / frozen genesis corpus divergence of 1,213 records (§3)
2. Four pre-existing `init_db()` migration couplings (§1) — systemic, post-V1
3. D041 physical-device acceptance unexecuted
4. B12 analysis unpushed
5. Production runs a release branch three commits off the canonical line; no
   process returns production hotfixes to master — §5 is the proof

---

## 10. Final acceptance matrix

**Incident018** — production, post-deploy
1. Full 20-question Lord trial, single session, completes and settles
2. Resume **before** `BOSS_ATTEMPT_MAX_MINUTES` — same attempt continues
3. Resume **after** expiry — `409 boss_attempt_expired`, expired-trial copy, **not** the save-failure string
4. Free player at `FREE_DAILY_LIMIT`: in-scope Lord answers exempt; ordinary practice still capped
5. Out-of-queue question → `400 invalid_boss_attempt_question`
6. Observability records every stage with no account or answer payload

**Incident019B** — production, after the S15 capture
7. Global before/after: per-zone `seen` for all 220 accounts
8. No account's visible mastery numerator decreases
9. Stars: outcome matches the Owner decision exactly
10. `main.complete_three_star_zone` reachable, or explicitly retired
11. `replenish_stars` selects a meaningful zone, not always the first
12. No new Boss clear, unlock, reward, Spirit, Coin, or equipment row —
    diff `adventure_boss_progress`, `adventure_zone_unlocks`, `reward_claimed`,
    `currency_log`, `spirit_evolution_events`, `player_inventory`
13. Baseline frozen: status `FROZEN`, `BASELINE_VERSION`
    `INCIDENT019B_B050_COMPAT_V1`, capture is once-only
14. `CUTOFF_LITERAL 2026-08-29T13:17:30` agrees between migration and runner

**LC020** — production, post-deploy
15. Known identity: a current legacy id resolves `EXACT` to its `source_record_uuid`
16. Alias: `HISTORICAL_SOURCE_PATH` reverse lookup returns the right identity
17. Unknown id → `MISSING` → `("legacy", id)`; no fabrication, no exception
18. Collided id (e.g. `40479`) → non-`EXACT`, own bucket, never merged
19. Aggregate parity: Adventure and daily-training outputs **byte-identical**
    to the pre-deploy capture — the §3 bijection made observable
20. Corpus drift: count runtime ids absent from the current alias set, and the reverse
21. `bootstrap_state().hot == True`; no second bootstrap possible

**RPG V1 device** — D041, 43 checklist items, `run_e10_owner_ipad_acceptance_hotfix_002.mjs`
22. iPad landscape · 23. iPad portrait · 24. iPhone/mobile portrait
25. Fresh session per device against the locked RC URL; no local-storage authority

**Release identity**
26. Deployed image revision label == locked source SHA
27. Image digest recorded
28. Static generation `release-<LOCKED_SHA>`; SW version recorded with sha256
29. `required_in_generation` staged, shipped and verified — **including
    `item_journal.html`**
30. `verify-production-release.ps1` clean
31. Full suite green on the locked SHA; zero unexplained failures

---

## 11. `NEXT_CLAUDE_TASK`

`GO_ODYSSEY_RC_FREEZE_PREFLIGHT_AND_POST_MERGE_TRUTH_RECHECK_001` — after S6,
before S8: re-verify master head and tree; confirm the ART003 family and the
full suite are green; confirm `required_in_generation` contains
`item_journal.html` and its assertion is restored; confirm the merged 019B head
is byte-identical to the Owner-authorized head; confirm no Wave 2 content
entered the tree between the last audit and the freeze; then certify the exact
SHA for lock.

Dependencies that would change conclusions in this document:
- CODEX-4's repair may alter §4's "test-only" classification if it turns out to
  touch manifests.
- A star-continuity capture would supply the per-account regression counts §2
  currently reasons about only in aggregate.
- The §3 corpus-drift query may promote that P1.
