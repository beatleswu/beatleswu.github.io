# E029-R1 — Post-PR401 Current-State and Merge-Wave Overlay

Status: DOCS_ONLY / OWNER_REVIEW_REQUIRED

Task: E029_R1_POST_PR401_CURRENT_STATE_AND_MERGE_WAVE_OVERLAY_001

This document is a narrow overlay on the historical E029 reconciliation. It
does not rewrite the original E029 artifacts and does not repeat the complete
PR400 file audit.

## 1. Current canonical source

git fetch origin verified:

| Field | Evidence |
| --- | --- |
| origin/master | a1ad78154858b9369e90c748f842401c40fb18cd |
| PR401 merge | a1ad78154858b9369e90c748f842401c40fb18cd |
| PR401 parents | e2669bfa8582239dd001dbb41b2cd134923e9e27, b5f7738b806d6ed521c140754f18fa1053c5d9e1 |
| PR401 tree | 2983e3f6d383681403198d1182f21564dca4d288 |
| overlay branch | codex/e029-r1-post-pr401-overlay |
| overlay base | a1ad78154858b9369e90c748f842401c40fb18cd |

The canonical checkout at D:\go-website was not modified. This overlay was
prepared in the isolated worktree D:\go-website-e029-r1-post-pr401-overlay.

## 2. Retained E029 locks

The current-master source shows no contradiction to the E029 PR400 core-file
collision review. The following findings are retained without a full repeat
of that historical audit:

| Lock | Current result |
| --- | --- |
| PR400_CORE_COLLISION_B | NONE — retained from E029 |
| PR400_CORE_COLLISION_C | NONE — retained from E029 |
| PR400_CORE_COLLISION_D | NONE — retained from E029 |
| PR400_CORE_COLLISION_F | NONE — retained from E029 |
| APP_PY_SERIAL_INTEGRATION_REQUIRED | YES |
| LANE_E_SINGLE_APP_PY_WRITER | YES |

PR400's Player Presentation route remains a distinct current app.py seam.
PR401 adds the narrow xp_amulet guard in the legacy equipment route; it does
not invalidate the PR400 B/C/D/F core-file conclusions.

## 3. Candidate state after PR401

Topology was recomputed against a1ad78154858b9369e90c748f842401c40fb18cd.
ahead_by and behind_by are commit counts from the exact candidate SHA to the
current master, not claims about merge readiness.

| Candidate | Exact SHA | State | Parent / merge-base | Ahead / behind | Current-master relation | Changed-file evidence |
| --- | --- | --- | --- | ---: | --- | --- |
| A028 | 9ae3cedcf4902bc792c17db4757c478d41d636a2 | OWNER_ACCEPTED_UNMERGED | parent e2669bfa; merge-base e2669bfa | 1 / 2 | neither ancestor | hero.html, sw.js, A028 browser test; no app.py |
| B033 | 15f665f656418ab189d32aa809c163f3e27fa92c | SCHEMA_CANDIDATE_UNMIGRATED | parent b75308d4; merge-base b75308d4 | 1 / 6 | neither ancestor | migration plus B033 schema tests |
| B034 | e7235ef74bcf2a31c190e3a6ce320bc8ee6c3e74 | OWNER_ACCEPTED_UNMERGED | parent B033; merge-base b75308d4 | 2 / 6 | neither ancestor | equipment_loadout_service.py plus tests; no app.py |
| B035 | 9361f7de31c0f1a189b19202ce20dd21c6cd690b | DOCS_ONLY_ACCEPTED | parent b75308d4; merge-base b75308d4 | 1 / 6 | neither ancestor | three planning documents |
| B036 | b5f7738b806d6ed521c140754f18fa1053c5d9e1 | MERGED_CURRENT_RUNTIME | parent e2669bfa; merge-base B036 | 0 / 1 | candidate is ancestor of master | app.py guard plus B036 test, merged by PR401 |
| C023 | ab588aa28cbae92a8c29bffe575b67b1f3207793 | OWNER_ACCEPTED_UNMERGED | parent f3ee9a6f; merge-base b75308d4 | 8 / 6 | neither ancestor | Commerce writer, tests, planning evidence; no app.py |
| C024-R1 | a1ad78154858b9369e90c748f842401c40fb18cd | ACTIVE_UNREVIEWED_NO_RESULT_VISIBLE | current master | 0 / 0 | exact current-master ref, no visible R1 delta | no result-bearing commit observed |
| D020 | d251ed92c46ebf6e7806ba4258ba6ba6b032e4a6 | OWNER_ACCEPTED_UNMERGED | parent 200fe541; merge-base b75308d4 | 3 / 6 | neither ancestor | acquisition adapter, docs, matrix, tests; no app.py |
| D022 | 7ab57ee78c74aa4526bfa29b6a8a0aa998604882 | DOCS_ONLY_ACCEPTED | parent b75308d4; merge-base b75308d4 | 1 / 6 | neither ancestor | three planning documents |
| D023 | ed8580efa2623bc2a43e585faa8af416648663ba | ACTIVE_UNREVIEWED_CURRENT_MASTER_BASED | parent 1aeaa59d; merge-base current master | 3 / 0 | current master is ancestor | acquisition adapter/docs/tests; local ref only at audit time |
| F014 | 9dda188a7a52b02d680cd6ff7aedaf891169bb12 | OWNER_ACCEPTED_UNMERGED | parent b75308d4; merge-base b75308d4 | 1 / 6 | neither ancestor | pure World/Boss adapter, contract, docs, tests |
| F015 | e0a28dedcac1b4cfddfde32e0474de26a1be4b02 | PENDING_OWNER_REVIEW_OR_ACTIVE_CURRENT_STATE | parent b75308d4; merge-base b75308d4 | 1 / 6 | neither ancestor | F014 stack plus milestone module/migration/tests |

A029 is an active task overlay, but no exact A029 branch/ref was visible in
the observed local/ref namespace. Its acceptance result is therefore not
assumed.

The D023 branch was visible locally as
codex/d023-shop-acquisition-result-bridge, but no matching remote branch was
visible during this audit. D023 is not treated as accepted or remotely
published.

## 4. PR401 / B036 overlay

The PR401 merge contains the exact B036 behavior in app.py and
tests/test_b036_xp_amulet_hold_guard.py:

1. a new xp_amulet equip request is rejected with
   XP_AMULET_HOLD_FOR_AUTHORITY;
2. a legacy row that is already equipped is still allowed through the legacy
   unequip path;
3. normal functional equipment behavior is unchanged.

B034 is not semantically equivalent at its current accepted SHA. Its
equipment_loadout_service.py rejects xp_amulet during equip_owned_item, which
is compatible with B036, but its unequip_owned_item treats every
non-functional identity as NON_FUNCTIONAL_EQUIPMENT. That would reject the
legacy already-equipped xp_amulet unequip that B036 explicitly preserves.

Therefore:

    B034_CUTOVER_MUST_PRESERVE_B036_XP_AMULET_HOLD=YES
    B034_SERVICE_HOLD_SEMANTICS_COMPATIBLE_WITH_B036=NO

This is a future B034 cutover blocker, not an implementation performed by
E029-R1. The eventual single-owner integration must preserve both halves of
the B036 contract before replacing the legacy app.py equipment route.

## 5. A028 overlay and direct gate

A028 is Owner-pass, unmerged, and does not modify app.py. Its exact changed
files are:

    hero.html
    sw.js
    tests/e9_node_tests/run_a028_hero_overview_player_presentation_tests.js

The A028 adoption is deliberately narrow: it reads Player Presentation for
Hero identity, XP, level, and rank. It does not consume Equipment, Spirit,
Premium, World, combat, or effect authority. Other legacy Hero-tab API calls
remain outside the A028 adoption scope and are not silently reclassified.

Because A028's parent is the pre-PR401 e2669bfa tree, it must be refreshed or
recreated from current a1ad7815 before GO_MERGE readiness. This is a
provenance requirement, not a product dependency.

    A028_MUST_WAIT_FOR_B033_B034=NO
    A028_MUST_WAIT_FOR_COMMERCE=NO
    A028_MUST_WAIT_FOR_WORLD_MONSTER=NO
    A028_DIRECT_GATE=A029_BROWSER_ACCEPTANCE_AFTER_CURRENT_MASTER_REFRESH

A028 may therefore be the first remaining merge wave, provided its fresh
current-master candidate preserves PR401 and its A029 browser acceptance
passes.

## 6. B035, Commerce, Acquisition, and World overlays

### Equipment / B035

B035 is documentation-only Owner-pass evidence. It records one legacy
equipped=true writer, the future B034 cutover requirement, and the separate
retirement of legacy player_appearance combat fields. Ownership-only writers
are not B033 hard blockers. The former xp_amulet gap in the B035 baseline is
superseded by the merged B036 guard; B034 must still preserve that behavior.

### Commerce / C023 and C024-R1

C023 remains Owner-pass but unmerged. It changes the pure Commerce acquisition
writer, not the Shop route. Its evidence confirms that player_inventory is
the functional ownership authority and that the Shop writer must receive a
server-owned slot projection. C024-R1 is active, but the exact observed ref is
the current PR401 merge commit and exposes no result-bearing R1 delta; its
outcome is not assumed.

D022 remains a valid cross-lane prerequisite: a future Shop result bridge must
persist and return the exact inserted player_inventory row identity. A
generic MAX(id), latest-row, timestamp, purchase-operation, or canonical_slot
fallback is not acceptable.

### Acquisition / D020, D022, D023

D020 is accepted/unmerged acquisition foundation evidence. D022 is accepted
documentation. D023 is active and limited to read-only acquisition-result
bridging for shop_inventory and player_wardrobe; it does not own the Commerce
player_inventory writer extension. D023 must not be treated as a complete
Commerce-to-Equipment bridge until that exact-row-identity prerequisite exists
and D023 receives review.

### World / Monster / F014 and F015

F014 remains accepted/unmerged pure boundary/adapter work. F015 adds a
milestone projection and migration but remains pending Owner status. Both
preserve:

    BATTLEFIELD_BOSS != LORD
    MONSTER_DEFEATED != WORLD_PROGRESSION

F012/F014 do not decide Zone clear, Star, Lord readiness, or next-Zone unlock;
future milestone storage remains a separately visible decision.

## 7. Current app.py collision map

The PR401 xp_amulet guard is in the legacy equipment route's equip/unequip
function seam. Future integrations remain serial even where exact route seams
do not overlap.

| Future seam | Current relationship to PR401 | Classification | Integration rule |
| --- | --- | --- | --- |
| B034 Equipment route cutover | Replaces/rewires the same legacy equip function that contains the B036 guard | SAME_FUNCTION_REPLACEMENT | One Lane E writer; preserve new-equip rejection and legacy-equipped unequip |
| Commerce Shop route cutover | New Shop/purchase route seam; no Player Presentation or B036 function replacement proven | SAME_FILE_NON_OVERLAPPING_SEAM | Serialize after C023/C024 result contract is accepted |
| Acquisition producer/event bridge | Future app-level bridge around committed D018 results; no PR400 core-file collision | SAME_FILE_NON_OVERLAPPING_SEAM | Serialize after D020 and exact ownership-result prerequisites |
| World/Boss binding | Future Adventure/Boss route adapter; boundary modules are pure and separate from Player Presentation | SAME_FILE_NON_OVERLAPPING_SEAM | Serialize after F014/F015 status is settled; never grant World progression from Monster defeat alone |

The classification does not authorize any route change. app.py remains
untouched in this overlay.

## 8. Canonical schema ownership

    CANONICAL_SLOT_SCHEMA_OWNER=B033_IS_CANONICAL_SLOT_SCHEMA_OWNER

B033 owns the equipment_canonical_slot_v1 migration candidate and its
constraint tests. C023 contains compatible writer/test evidence and refers to
pre-/post-B033 storage, but its Git ancestry is not B033's ancestry and it is
not a second schema owner. The eventual integration must import one canonical
B033 migration history, then reconcile C023's writer against that schema. No
Production migration is implied.

## 9. Stale-master policy

The E029 policy remains:

* a docs-only candidate may remain reviewable when its source-stable findings
  are explicitly overlaid onto the current master;
* a runtime candidate must either have current master as an ancestor or be
  recreated as a fresh current-master integration candidate before GO_MERGE
  readiness;
* an old-base accepted SHA is behavioral/provenance evidence, not a current
  merge source by default;
* no candidate is called current runtime merely because it is Owner-pass.

This overlay applies that rule to A028, B033/B034, C023, D020, F014/F015, and
the active C024-R1/D023/A029 tasks.

## 10. Remaining merge waves

Already merged and therefore excluded from the remaining-wave count:

* PR400 Player Presentation backend/read foundation;
* PR401 B036 narrow xp_amulet guard.

Recommended remaining waves:

| Wave | Candidate/input | Why this order | Required gate |
| --- | --- | --- | --- |
| 1 | A028 current-master refresh + A029 acceptance | Independent frontend adoption of an already merged read route; no Equipment/Commerce/World dependency | Fresh A028 candidate from a1ad; A029 browser acceptance; preserve PR401 |
| 2 | B033 schema + B034 service/current-master reconciliation | Establish one canonical slot projection before Equipment route cutover | B034 must close the B036 legacy-unequip incompatibility; disposable schema tests; no Production migration |
| 3 | D020 acquisition foundation + D022 contract evidence | Establish committed-result and ownership-reference boundaries before producer bridges | Current-master D020 candidate; D022 retained as contract; no writer duplication |
| 4 | C023 Commerce writer + reviewed C024-R1 result | Commerce must produce truthful ownership results and obey B033 slot authority | C024-R1 actual review result; exact player_inventory row identity extension; no route enable |
| 5 | D023 read-only Shop acquisition bridge | Consume committed Shop results only after Commerce exposes exact ownership identity | D023 review pass; D020/C023 prerequisites; no player_inventory writer in D023 |
| 6 | F014 boundary adapter + F015 only after Owner status settles | Keep World/Boss boundary isolated from acquisition and Player Presentation | F015 Owner PASS or explicit exclusion; milestone storage decision; Boss != Lord |
| 7 | Final serial app.py cutovers and combined acceptance | Wire B034, Shop, acquisition, and World/Boss seams under one owner after pure foundations settle | GO_MERGE per reviewed current-master candidate; full cross-system acceptance |

    REMAINING_MERGE_WAVES=7
    NEXT_INTEGRATION_OWNER=LANE_E
    APP_PY_SERIAL_INTEGRATION_REQUIRED=YES

Wave 1 may precede Equipment, Commerce, and World/Monster because A028 uses
only the merged Player Presentation read contract. It still requires a
current-master provenance refresh because its Owner-pass SHA predates PR401.

## 11. Current-state labels

The artifacts use these labels consistently:

* MERGED_CURRENT_RUNTIME — present in current master, such as B036;
* OWNER_ACCEPTED_UNMERGED — Owner-pass behavior not in current master;
* ACTIVE_UNREVIEWED — active work with no Owner-pass conclusion;
* DOCS_ONLY_ACCEPTED — accepted evidence with no runtime cutover;
* SCHEMA_CANDIDATE_UNMIGRATED — schema code exists only as candidate;
* PENDING_OWNER_REVIEW_OR_ACTIVE_CURRENT_STATE — exact status is unresolved
  at this audit and is not promoted to accepted.

## 12. Scope and result

This overlay changed only the three new documentation artifacts listed in the
task. It did not modify app.py, runtime modules, frontend files, schema,
Production, active candidate branches, flags, or migrations.

The current roadmap is reviewable, but B034 is not cutover-ready until its
service preserves the B036 legacy-equipped xp_amulet unequip behavior. This
is intentionally surfaced as a precise integration blocker rather than
silently normalized.
