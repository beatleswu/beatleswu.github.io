# LC007 — Terminal-Verdict Marker Semantics + False-Positive Elimination

Branch base: `c655366f3ac293df97a72629c94ebeddcb74c35e` (LC006 head)
Canonical master at task time: `c2a1dab3125cdef0cff381815d3d995bdd340538`
Type: **judge-semantics contract + owner decision packet**. No corpus mutation.
No bulk annotation. No policy wired into `canonical_learning_judge` or `app.py`.

Artifacts:
- `tools/lc007_marker_policy_simulation.py` — read-only policy simulator (5 policies, 5 buckets, vs-current diff, hash-gated)
- `docs/planning/lc007_marker_policy_impact.json` — full-snapshot impact (sha256 in §7)
- `tests/test_lc007_terminal_verdict_marker_semantics.py` — 8023 reproduction, adversarial marker corpus, fail-closed invariants, determinism
- LC7 swarm scratch reports: `lc7a_signal_inventory.md`, `lc7b_record_8023_forensics.md`, `lc7e_independent_recount.md`

## 1. Snapshot

`sha256 88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff`,
42,804 records. Independently hash-verified by the simulator and by all three
swarm tracks. Hash mismatch → STOP, no substitution.

## 2. The defect — record 8023 (record_index 17147) — REPRODUCED

`FALSE_POSITIVE_REPRODUCED = PASS` · `EXPLANATORY_NOUN_USAGE_CONFIRMED = PASS`

- `content_sha256 = 2037f3a163e8eb55994b6e4aa3e719b3719cedaa54d465eb9469c87775973490`
- Current classification: `ALREADY_EXPLICIT / TERMINAL_SUCCESS_MARKER /
  explicit_success`, `manual_review_required = False`.
- The record has two root variations, both first move `W[ob]`:

| | Variation 1 = `root.children[0]` | Variation 2 = `root.children[1]` |
|---|---|---|
| first-move node name | `N[正解]` ("correct solution") | `N[参考]` ("reference") |
| author intent | THE SOLUTION | inferior comparison line |
| White line → terminal | `ob oc na kb oa ma` → `B[ra]` | `ob pb nb` → `B[qb]` |
| terminal markers | none (bare) | `C[黑地虽然和正解一样，但白增加4目。]` |
| `_explicit_terminal_is_correct` | `None` | **`True`** — via `正解` substring |

- The honoured token `正解` sits at offsets 5–6 of variation 2's terminal
  comment, in `和<正解>一样` = "the same as the correct solution". It is a
  **noun** naming the model answer inside a comparison sentence ("Black's
  territory is the same as the correct solution, but White gains 4 points"),
  not a verdict label for this line. The author's machine-readable intent
  (`N[正解]` vs `N[参考]`) is never read by the judge.

### Runtime vs census — where the false positive actually bites

`judge_answer` walks the submitted line linearly via `_child_for_colour_and_coord`
(first matching child), so it always descends variation 1 and returns
`UNVERIFIABLE` (`reply_leaf_without_explicit_verdict`) — it **never reaches**
variation 2's comment. So the number of records the *runtime judge* would grade
`CORRECT` from an explicit terminal marker is effectively **0** today.

The false positive lives in the **census / classification layer**
(`lc005.classify_record → _analyze_answer_tree`), which evaluates every reachable
terminal in both variations. Its concrete harm: record 8023 is tagged
`explicit_success / manual_review_required=False` and is therefore **wrongly
excluded from the 41,830-record MANUAL_SEMANTIC_REVIEW remediation population**
(LC006). It is also a latent authoring landmine: any future terminal comment
that mentions 正解 in prose silently becomes a "solved" verdict.

`SUBSTRING_ONLY_SUCCESS` is the root cause.

## 3. Current signal inventory (derived from code — LC7-A)

The entire explicit terminal-verdict mechanism is
`canonical_learning_judge._explicit_terminal_is_correct(node)` (clj.py:213-240),
called only from `judge_answer` at clj.py:347 and clj.py:388, only on a leaf.
It reads exactly three fields off that leaf: `metadata["game_result"]` (from
`RE[...]`), `metadata["properties"]["TE"]`, `metadata["comment"]` (from `C[...]`,
first value). It does **not** read `N[...]`, `GC[...]`, or any other property.

| # | SIGNAL_TYPE | NODE_SCOPE | MATCH_RULE | S/F | CORPUS_COUNT | FALSE_POS_RISK | AMBIGUITY_RISK |
|---|---|---|---|---|---|---|---|
| 1 | node `game_result` / `RE`, non-failure | reachable terminal **move node** (game-info-root `RE[]` folded onto the root container is invisible) | `str(meta["game_result"]).strip()` truthy, lowercased, no `_FAILURE_RESULT_TOKENS` substring → `True`. **No valid-RE whitelist.** Checked first. | SUCCESS | **0** | **HIGH** — any non-empty value passes; terminal `RE[W+R]` on a Black problem, `RE[0]`/`RE[?]`/`RE[Void]` all score SUCCESS. Latent (0 corpus). | LOW |
| 2 | node `RE`, failure value | same | same block: `any(tok in low for tok in _FAILURE_RESULT_TOKENS)` → `False`. Tokens: `fail,wrong,incorrect,失敗,錯誤,×`. | FAILURE | **0** | LOW | LOW |
| 3 | `TE` property presence | reachable terminal move node's own `properties` | `if "TE" in props: return True` — bare key, any value incl. `TE[]`. Only if `game_result` empty. | SUCCESS | **0** (no `TE[` anywhere in corpus) | **MED** — `TE` marks any strong move, not only a solved terminal. Latent. | LOW |
| 4 | success comment token | reachable terminal move node's `C[...]` comment | **unanchored case-insensitive substring** `any(tok.lower() in comment for tok in _SUCCESS_COMMENT_TOKENS)` → `True`. Tokens: `正解,正確,成功,correct,success,✓,✔`. Only if `game_result` empty & `TE` absent & no failure token. | SUCCESS | **1** — record 8023, token `正解` | **HIGH** — the sole corpus hit is a misfire (§2). | **HIGH** — Go commentary routinely compares lines *to* "the correct answer". |
| 5 | failure comment token | same as 4 | checked **before** success: `any(tok in comment for tok in _FAILURE_RESULT_TOKENS)` → `False`. | FAILURE | **0** | MED — same unanchored weakness. | MED — mixed comment always resolves FAILURE. |
| 6 | `accepted_moves` / `accepted_answers` | **not an SGF node** — corpus record dict key; reviewer/admin `{x,y}` list | judge: single-move attempt, transform-mapped point ∈ set → `CORRECT`. classify_record: `record.get("accepted_moves")` truthy → `explicit_success`. | SUCCESS | **0** (neither key truthy in snapshot; runtime-populatable by admin) | LOW | LOW |

Parsed-but-never-read (not signals): `N`, `GB`, `GW`, `BM`, `DO`, `TR`, `MA`,
`SQ`, `CR`, `LB`, `DM`, `HO`, `IT`, `GC`, `AN`, … Raw corpus scan: `GB[` 0,
`GW[` 0, `BM[` 1 (unread), `TE[` 0.

**CURRENT_EXPLICIT_SUCCESS_COUNT = 1** (record 8023, signal 4).
**CURRENT_EXPLICIT_FAILURE_COUNT = 0.** Cross-checks LC006's value of 1.

### Adjacent adapter that grants terminal success independently

`map_battle_runtime.judge_map_battle_answer_v1` (map_battle_runtime.py:518-559)
grants `CORRECT` on a **bare answer-tree leaf** ("answer_tree_leaf" /
"answer_tree_reply_leaf") plus an accepted-moves fast path. It does **not** read
`RE`/`TE`/`C`. It is the Map Battle / rating-test consumer — a *different* path
from `/api/srs/review`, and `canonical_learning_judge`'s docstring (clj.py:26-27)
states this additive-accept behaviour is deliberately OFF in the learning judge.
**Out of scope for this marker contract** (different consumer, different product
decision) but recorded here so the owner sees the whole picture. `app.py
srs_review()` and `js/game/review_transport.js` grant no independent verdict.

## 4. Policy candidates

All policies keep the LC003 walk, colour enforcement, ambiguity fail-close, and
bare-leaf fail-close unchanged. They differ **only** in the terminal-verdict
function.

| ID | Definition |
|---|---|
| **A** | **Current.** Node RE (non-failure, no whitelist) → success; else terminal `TE` presence → success; else terminal comment: failure-token substring → failure, success-token substring (unanchored) → success; else None. |
| **B** | **Anchored comment.** Node RE + terminal `TE` unchanged. Comment yields SUCCESS only if, after stripping wrapping decoration (`【】（）「」*_#…` quotes) and trailing punctuation (`。．.!！?？:：;；、,…` ws), it is **exactly** a success token — no prose, no comparison marker. A comment that is exactly a failure token (judge list **+ simplified-CJK / 不- gaps**: `不正解 不正確 不正确 错误 错 失败`) → FAILURE. Anything else → None. |
| **C** | **Node-name.** Node RE + terminal `TE` unchanged. Comments **not read**. An `N[...]` on the **reachable terminal** whose trimmed value is exactly a success token → success (exactly a failure token → failure). `N` on a non-terminal node is ignored. |
| **D** | **Structured-only.** SUCCESS / FAILURE **only** from a move-node RE or a terminal `TE`. Comments and `N` not read. Most fail-closed. |
| **RECOMMENDED** | move-node RE **OR** terminal `TE` **OR** anchored-exact terminal comment (B) **OR** exact terminal `N[...]` (C). Fail-closed on everything else. |

`NEW_FORMAT_REQUIRES_OWNER_APPROVAL`: none of B/C/D invents an SGF extension —
each restricts or re-points existing parsed properties. Policy C promotes
`N[...]` from "parsed, unread" to "read, exact-match only"; `N[正解]` is already
the idiomatic correct-line label used in the corpus (e.g. record 8023
variation 1) so this is recognition of existing authoring, not a new format.

### Secondary hardening (0 corpus impact, recommended alongside any safe policy)

Signal 1 has **no valid-RE whitelist** (LC7-A: HIGH latent risk). Independently
of the comment fix, restrict a terminal RE success to a decisive-result shape
(`^[bw]\+` after strip — the SGF RE grammar for "a side won"), so `RE[0]` /
`RE[?]` / `RE[Void]` / a wrong-side `RE[W+R]` on a Black problem do not score
SUCCESS. Signal 3 (`TE` bare presence) similarly grants SUCCESS for any `TE[]`;
consider requiring the `TE` to sit on the *final* solution node only. Both are
latent (0 corpus records) — hardening, not urgent.

## 5. Adversarial marker corpus (LC007 §5) — result

`tests/test_lc007_terminal_verdict_marker_semantics.py::TestAdversarialMarkerCorpus`.
Under the anchored rule (B / RECOMMENDED):

| terminal comment | verdict | note |
|---|---|---|
| `正解` / `　正解　` / `【正解】` / `（正解）` / `「正解」` / `正解。` / `正解！` / `正解\n` / `正解：` / `*正解*` | **SUCCESS** | clean label — wrapping decoration & trailing `。．.!！:：;；、,` stripped |
| `成功` / `correct` / `success` | **SUCCESS** | other clean labels |
| `正解？` | None | interrogative ("correct?") — `?`/`？` deliberately **not** stripped, stays fail-closed (LC7-E) |
| `正解です` | None | affirmative sentence, not a bare label — fail-closed (discriminating case; see §9 false-negative risk) |
| `これは正解` | None | " this is correct" — not anchored |
| `正解と同じ` / `正解より悪い` / `正解図参照` / `参考：正解では...` | None | explanatory reference |
| `黒地は正解と同じだが白が4目増える` / `黑地虽然和正解一样，但白增加4目。` | None | the 8023 comment (JP + ZH) |
| `正解ではない` / `not the correct answer` | None | negation |
| `不正解` / `incorrect` / `×` | FAILURE | exact failure token |
| `これは不正解です` | None | mixed (`正解` + `不正解` substrings) → fail-closed |

**EXPLANATORY_REFERENCE_FALSE_POSITIVES = 0.** A terminal never becomes correct
because explanatory prose mentions the concept "correct answer".

## 6. Record 8023 under each policy

| | reference-variation terminal verdict | POLICY_SAFE |
|---|---|---|
| **RECORD_8023_CURRENT** / A | `explicit_success` (the defect) | **NO** |
| **RECORD_8023_POLICY_B** | not success → `MANUAL_SEMANTIC_REVIEW` / `bare_terminal` | YES |
| **RECORD_8023_POLICY_C** | not success (N is on move 1, not the terminal) | YES |
| **RECORD_8023_POLICY_D** | not success (no RE/TE) | YES |
| **RECORD_8023_RECOMMENDED** | not success | YES |

No safe policy auto-recovers variation 1 — its terminal is genuinely bare, so
the record correctly routes to human review. That is the fail-closed outcome.

## 7. Corpus-wide impact simulation (full snapshot, in memory only)

`docs/planning/lc007_marker_policy_impact.json`
sha256 `db215a864842c54767c193360766997534b3c3c1c2dd5820c431ac53a502bd30`.

| policy | MALFORMED | AMBIGUOUS | EXPLICIT_SUCCESS | EXPLICIT_FAILURE | UNVERIFIABLE |
|---|---:|---:|---:|---:|---:|
| **A (current)** | 163 | 731 | **1** | 0 | 41,909 |
| **B** | 163 | 731 | **0** | 0 | 41,910 |
| **C** | 163 | 731 | **0** | 0 | 41,910 |
| **D** | 163 | 731 | **0** | 0 | 41,910 |
| **RECOMMENDED** | 163 | 731 | **0** | 0 | 41,910 |

vs current (every safe policy, identical):

- `NEWLY_ACCEPTED = 0`
- `NEWLY_REJECTED = [17147]` (record 8023)
- `CHANGED_FROM_CURRENT = [17147]` — one record, `EXPLICIT_SUCCESS → UNVERIFIABLE`
- `CHANGED_RECORD_COUNT = 1`

`RECOMMENDED_EXPLICIT_SUCCESS_COUNT = 0`, `RECOMMENDED_EXPLICIT_FAILURE_COUNT = 0`.
The corpus genuinely carries **zero** valid explicit terminal markers (LC006
already established RE/TE = 0; the one comment token was the false positive).
`SAFE_AUTO` stays **0** — no safe policy manufactures a candidate (§10 honoured).

`MALFORMED` (163) and `AMBIGUOUS` (731) are untouched by every policy — the
change is confined to the terminal-verdict function.

### Independent recount (LC7-E) — all figures reproduced

A separate track re-derived every number from scratch (own bucket walk, own
policy reimplementation, no import of the simulator) and got byte-identical
results: every cell of the 5×5 bucket table, the dedup-by-content table, all
four vs-current diffs, and the `changed_rows` array — **zero mismatches**.
It further proved no other record *can* change: only 17 records contain a
success token anywhere in raw `content` — 2 MALFORMED, 1 on a reachable terminal
(17147), 6 with `N[正解]` on the first move (read by neither A nor C there),
8 with the token only in `GN[]` / root free-text the parser never surfaces; the
7 failure-token records are all mojibake `×` in garbled game-name fields.
`DETERMINISTIC_RERUN = PASS` on both the simulator and the independent script.

## 8. Fail-closed invariants (LC007 §8) — all hold under B / C / D / RECOMMENDED

- `BARE_LEAF_CORRECT = NO` — a childless node with no marker → UNVERIFIABLE.
- `SUBSTRING_ONLY_SUCCESS = NO` — RECOMMENDED requires an exact anchored token;
  `C[白は正解より2目多い]` → None (was `True` under A).
- `UNKNOWN_MARKER_FAIL_CLOSED = PASS` — `GB` / `GW` / `BM` / `DO` / `N[参考]` /
  `TR` / `LB` on a terminal → not success.

## 9. Owner decision packet

| POLICY_ID | DESCRIPTION | FALSE_POSITIVE_RISK | FALSE_NEGATIVE_RISK | CORPUS_COMPATIBILITY | MIGRATION_COST | AUTHORING_CLARITY | BACKWARD_COMPAT | RECOMMENDED |
|---|---|---|---|---|---|---|---|---|
| **A** | keep unanchored substring | **HIGH** — 正解-in-prose = success; `不正解` = success; wrong-side `RE` = success | none | 1 record (a false positive) | 0 | poor — "any comment mentioning 正解" | n/a (status quo) | **NO** |
| **B** | anchored-exact comment token (+ 不- / simplified-CJK failure tokens) | LOW — exact label only | MED — `正解です` / `これは正解` / decorated variants not matched | removes the 1 false positive; 0 true losses | tiny (swap one primitive) | good — "comment is exactly 正解" | 1 record changes (defect → review) | viable |
| **C** | exact `N[...]` on terminal; comments unread | LOW | HIGH — drops the entire comment channel; today's corpus has 0 terminal `N` | removes the false positive; 0 true losses | tiny | good — `N[正解]` on the solving move | 1 record changes | partial (best combined) |
| **D** | structured-only (RE/TE) | **LOWEST** | HIGHEST — no comment / no `N` channel at all | removes the false positive; 0 true losses | tiny | requires RE/TE authoring discipline | 1 record changes | conservative fallback |
| **RECOMMENDED** | RE ∨ terminal TE ∨ anchored comment (B) ∨ exact terminal `N` (C), else fail-closed; + RE decisive-shape whitelist (§4 secondary) | LOW | LOW — keeps every legitimate channel, just anchored | removes the false positive; 0 true losses; 0 newly-accepted | small | best — one clear rule per channel | 1 record changes (17147: defect → UNVERIFIABLE) | **YES (technical recommendation)** |

`RECOMMENDED_POLICY = RECOMMENDED`. Rationale: it is the narrowest change that
(a) eliminates `SUBSTRING_ONLY_SUCCESS`, (b) closes the record-8023 false
positive and its whole class, (c) regresses **nothing** (0 newly-rejected beyond
the defect, 0 newly-accepted), (d) keeps every authoring channel available in an
unambiguous form, and (e) folds in the latent RE-whitelist hardening at no
corpus cost.

**OWNER_MARKER_DECISION_REQUIRED = YES.** LC007 does not wire any policy into
`canonical_learning_judge`, `_explicit_terminal_is_correct`, `classify_record`,
or `app.py`. Enabling the chosen policy is a separate, owner-gated change.

### Open contract questions for the owner (all 0 corpus records today — LC7-E review)

1. **False-negative boundary.** `正解です` ("it is correct"), `これは正解`
   ("this is correct"), `正解、正着` all fall to fail-closed under the
   exact-anchored rule. Accept a success token followed only by a copula
   (`です`/`だ`/`。`) or a leading-token label (`正解:` … prefix)? The stricter
   the rule, the more it leans on clean authoring.
2. **Vocabulary.** `正着` / `正著` (standard Chinese "the correct move") is in no
   success-token list — it fails under **both** A and every safe policy. Adding
   it is a content-vocabulary decision, not a semantics fix; LC007 does not add
   it (would be scope creep per §4).
3. **`_strip_decoration` reach.** "exactly a token" means "exactly a token after
   stripping wrapping decoration + trailing `。．.!！:：;；、,` " — so `N[正解 ]`,
   `N[ 正解]`, `N[正解。]` all match under C. `?` / `？` are intentionally not
   stripped (an interrogative is not an assertion).

## 10. No manual corpus apply

`MANUAL_RECORDS_MUTATED = 0` · `CORPUS_MUTATION = NO` · `LC004_ENABLED = NO` ·
`SAFE_AUTO = 0`. The 41,830 MANUAL_SEMANTIC_REVIEW records are untouched. No
rule was broadened to create SAFE_AUTO candidates.

## 11. Content-duplicate impact (LC007 §11)

LC006: 42,268 distinct `content_sha256` / 404 content-duplicate groups. Marker
buckets computed full vs deduped-by-content:

| | EXPLICIT_SUCCESS | EXPLICIT_FAILURE |
|---|---:|---:|
| A, full 42,804 | 1 | 0 |
| A, deduped 42,268 | 1 | 0 |
| RECOMMENDED, full | 0 | 0 |
| RECOMMENDED, deduped | 0 | 0 |

`CONTENT_DUPLICATE_POLICY_IMPACT = NONE.` Every duplicate group falls in
`MALFORMED` / `AMBIGUOUS` / `UNVERIFIABLE`; **zero** marker-bearing records are
duplicated, so duplication does not distort any marker-policy count. Content
deduplication remains a separate identity task, out of scope here.

## 12. Scope

`APP_PY_CHANGED = NO` · `INDEX_HTML_CHANGED = NO` · `SCHEMA_CHANGED = NO` ·
`MIGRATION_CHANGED = NO`. Work is confined to a new sibling tool, a new test
file, this doc, and the impact JSON. `PRODUCTION_QUERY = NO` ·
`PRODUCTION_MUTATION = NO` · `DEPLOY = NO` · `MASTER_MERGE = NO`.
