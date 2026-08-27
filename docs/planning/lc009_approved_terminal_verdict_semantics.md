# LC009 — Approved Terminal-Verdict Marker Semantics (implemented)

Branch base: `7afc8f853096e7c5175e46b9251288f1352e6e7c` (LC007 head)
Canonical master at task time: `c2a1dab3125cdef0cff381815d3d995bdd340538`
Owner policy: **LC007 RECOMMENDED — APPROVED**. This task WIRES it into the
live judge (LC007 only simulated). No corpus mutation. `LC004_ENABLED = NO`.

Files changed:
- `canonical_learning_judge.py` — `_explicit_terminal_is_correct` rewritten to the 4 approved channels; new helpers `_re_is_decisive`, `_exact_marker_verdict`, `_terminal_name_verdict`, `_strip_marker_decoration`; `CANONICAL_JUDGE_VERSION` `v1 → v2`
- `tools/lc005_terminal_verdict_census.py` — `_re_is_non_failure_success` now delegates to `_re_is_decisive(...) is True` (SAFE_AUTO gate coherence; 0 corpus impact)
- `tools/lc007_marker_policy_simulation.py` — `_re_or_te` uses `_re_is_decisive` so the sim's RECOMMENDED == the shipped judge (impact JSON byte-identical)
- `tools/lc009_live_judge_snapshot_recount.py` — NEW, full-snapshot recount against the *live* judge primitive
- `tests/test_lc009_approved_terminal_verdict_semantics.py` — NEW (114 tests)
- `tests/test_lc003_canonical_judge.py`, `tests/test_lc003_srs_review_wiring.py`, `tests/test_lc004_attempt_transport_cutover.py` — fixture migration `RE[Correct]` → `RE[B+]` / `RE[W+]` (see §5); one `judge_version` assertion `v1 → v2`
- `docs/planning/lc009_live_judge_snapshot_impact.json` — recount output

## 1. The implemented contract

`_explicit_terminal_is_correct(node)` — called only on the terminal of a walked
line (`judge_answer` after `_is_leaf`; `_analyze_answer_tree` on leaves / the
end-of-authored-line node). Returns `True` / `False` / `None`; `None` fails
closed to `UNVERIFIABLE`.

| # | channel | rule | on hit |
|---|---|---|---|
| 1 | move-node RE (`game_result`) | failure token (`fail wrong incorrect 失敗 錯誤 ×`) in the value → **False**; else `_RE_DECISIVE_SHAPE.fullmatch(value.strip())` → **True**; else fall through | verdict |
| 2 | `TE` property on the node | key present (any value) → **True** | verdict |
| 3 | comment (`C[...]`) | `_strip_marker_decoration(comment.strip().lower())` **exactly ==** a failure marker → **False**; exactly == a success marker → **True**; else fall through | verdict |
| 4 | node name `N[...]` | same exact-match as (3) over each `N` value | verdict or `None` |

Anything else → `None`.

### RE_DECISIVE_SHAPE_WHITELIST — exact accepted forms

```
_RE_DECISIVE_SHAPE = re.compile(
    r"[bw]\+(?:r|resign|t|time|f|forfeit|(?!0+(?:\.0+)?\Z)\d+(?:\.\d+)?)?",
    re.IGNORECASE | re.ASCII,
)   # applied with .fullmatch() to value.strip()
```

**Accepted (DECISIVE_SUCCESS):** `B+` / `W+` (names the winner), optionally
followed by exactly one of — `R` `Resign` `T` `Time` `F` `Forfeit` (case-
insensitive), or a positive score `\d+` / `\d+.\d+` that is not all-zero
(`B+3`, `B+3.5`, `W+65.5`). Leading/trailing ASCII whitespace is stripped
first (`\n` `\t` included).

**Rejected → `None` (fail closed):** empty, `0`, `Draw`, `Void`, `?`, `-`,
`B` (no `+`), `+R` (no side), `B+0` / `B+0.0` / `B+00` (all-zero score),
`B+-3` (negative), `B+?` `B+Q` `B+Resigns` `B+timeout` `B+score` (non-spec
detail), `B+ R` (inner space), `B++R`, `BW+R`, `3.5` (no side), `correct`
`right` `best` `unknown` `jigo` (non-standard text), full-width `B＋R` /
`B+３`, any trailing junk (`B+R;` `B+R.` `B+R extra` `(B+R)`).

**Rejected → `False` (INCORRECT):** any value whose lower-case contains a
`_FAILURE_RESULT_TOKENS` substring (`B+R fail`, `W+R (wrong side)`,
`B+1 incorrect`, `×`, `失敗`, `B+R 錯誤`). Checked **before** the decisive
match; no decisive lexeme (`resign` `time` `forfeit`) contains a failure token.

### ANCHORED_COMMENT_MARKERS

Success only from an **exact** token after normalization — never a substring.
Decoration trimmed from both ends: `　 \t\r\n 【】〔〕［］[]（）() 「」『』〈〉《》 " ' “”‘’ * _ # - — ― · ・`
then trailing punctuation `。．.!！:：;；、,，…~〜` + whitespace, then decoration
again. **`?` / `？` are NOT trimmed** — `正解？` ("correct?") is a question,
stays `None`. Success set: `正解 正確 成功 correct success ✓ ✔`. Failure set
(judge list **plus** `不正解 不正確 不正确 错误 错 失败` — 不- negation and
simplified-CJK gaps): exact-match → `False`.

Natural-language references stay fail-closed: `和正解一樣`, `正解より悪い`,
`請參考正解`, `不正解` (→ `False`), `正解？`, `黑地虽然和正解一样，但白增加4目。`,
`正解と同じ`, `これは正解`, `正解図参照`, `正解ではない`, `not the correct answer`
— all `not True`.

### TERMINAL_N_MARKERS

`N[...]` on the terminal node, exact-match against the same success/failure
sets. An `N[正解]` on an **earlier** move node is never passed to this function
(call-site invariant), so it is never read as a terminal verdict.

### TERMINAL_TE

Preserved unchanged: a `TE` property on the terminal node → `True`.

## 2. Hard requirements

| requirement | status |
|---|---|
| `BARE_LEAF_CORRECT` | **NO** — a childless node with no approved marker → `None` → UNVERIFIABLE |
| `SUBSTRING_ONLY_SUCCESS` | **NO** — `C[白は正解より2目多い]` → `None` (was `True`) |
| `UNKNOWN_MARKER_FAIL_CLOSED` | `GB GW BM DO CR TR LB MA SQ HO IT DM GC AN N[参考]` on a terminal → not success |
| record 8023 (index 17147) `EXPLICIT_SUCCESS → UNVERIFIABLE` | **PASS** — `FALSE_POSITIVE_8023_FIXED = PASS` |
| no other corpus record changes classification | **PASS** — full-snapshot recount: `CHANGED_RECORD_INDEXES = [17147]`, `NEWLY_ACCEPTED = 0` |

## 3. Full-snapshot result (`tools/lc009_live_judge_snapshot_recount.py`)

`docs/planning/lc009_live_judge_snapshot_impact.json`
sha256 `83e971236f2b474e13f1ea10b8283d90005af886e4533156f3913b63c78cc633`.
Snapshot `88da3e43…f654ff`, 42,804 records, hash-verified.

| bucket | pre-LC009 (LC007 Policy A) | **LC009 live judge** | approved |
|---|---:|---:|---:|
| MALFORMED | 163 | **163** | 163 |
| AMBIGUOUS | 731 | **731** | 731 |
| EXPLICIT_SUCCESS | 1 | **0** | 0 |
| EXPLICIT_FAILURE | 0 | **0** | 0 |
| UNVERIFIABLE | 41,909 | **41,910** | 41,910 |

`CHANGED_RECORD_COUNT = 1` · `CHANGED_RECORD_INDEXES = [17147]` ·
`NEWLY_ACCEPTED = 0` · `NEWLY_REJECTED = [17147]` (EXPLICIT_SUCCESS →
UNVERIFIABLE). `buckets_match_approved = true`, deterministic on rerun.

Why nothing else moves (LC9-B / LC7-A / LC7-E, independently reconfirmed):
0 records carry a move-node RE; 0 a game-info-root RE value (the 9 `RE[` are
all `RE[]` empty); 0 a `TE[`; 0 a terminal `N[...]` = a success token (the six
`N[正解]` sit on move 1); 0 a terminal comment that is *exactly* a marker
token except index 17147, whose comment is a comparison sentence, not a label.

### 9-class census (`lc005.run_census`)

| class | pre-LC009 | LC009 |
|---|---:|---:|
| ALREADY_EXPLICIT | 1 | **0** |
| MANUAL_SEMANTIC_REVIEW | 41,830 | **41,831** |
| SAFE_AUTO_CANDIDATE | 0 | 0 |
| AMBIGUOUS_AUTOREPLY / MALFORMED_SOURCE / EMPTY_OR_UNANSWERABLE / DUPLICATE_IDENTITY_BLOCKED / COLOR_AUTHORITY_INCOMPLETE / OTHER_BLOCKED | 731 / 163 / 66 / 13 / 0 / 0 | unchanged |
| classification_total | 42,804 | 42,804 |
| current_explicit_success_records | 1 | **0** |

Record 17147 moves `ALREADY_EXPLICIT / explicit_success` →
`MANUAL_SEMANTIC_REVIEW / bare_terminal` — it now correctly joins the human-
review population. `SAFE_AUTO` stays 0; the tightened `_re_is_non_failure_success`
can only narrow that gate, and there is no game-info-root RE value to feed it.

## 4. `judge_answer` end-to-end

- decisive-RE terminal (`RE[B+]`) → `CORRECT`
- non-decisive RE (`RE[Void]`) → `UNVERIFIABLE`
- prose comment mentioning 正解 → `UNVERIFIABLE`
- exact `C[正解]` / `C[成功]` / `N[正解]` → `CORRECT`
- the runtime judge already never reached record 8023's reference variation
  (linear first-match walk); it now also cannot mis-classify it in the census.

## 5. Test-fixture migration

`RE[Correct]` is not a valid SGF result and is exactly the loose marker the
approved contract removes. 29 occurrences across the LC003/LC004 suites — all
used as "this terminal is the answer" — were migrated to a valid decisive
result: `RE[B+]` (Black-to-play fixtures) / `RE[W+]` (the `PL[W]` / white-to-
play fixtures). No test asserts on the literal RE string; each test's intent
(marker → CORRECT) is preserved. The migration was verified behaviour-neutral
under the *old* judge before the semantics change landed.

## 6. Scope

`APP_PY_CHANGED = NO` · `INDEX_HTML_CHANGED = NO` · `SCHEMA_CHANGED = NO` ·
`MIGRATION_CHANGED = NO` · `CORPUS_MUTATION = NO` · `LC004_ENABLED = NO` ·
`PRODUCTION_QUERY = NO` · `PRODUCTION_MUTATION = NO` · `DEPLOY = NO` ·
`MASTER_MERGE = NO`. `app.py` consumes `judge_version` only as an opaque string
in a response body — the `v2` bump flows through untouched.

## 7. Swarm (LC9-A … LC9-E)

- **LC9-B** RE decisive-shape whitelist — designed the regex + 84 verified
  vectors; confirmed 0 corpus RE values so the whitelist is pure latent
  hardening.
- **LC9-A** judge implementation review — adversarial review of the
  `_explicit_terminal_is_correct` diff, call-site audit, RE-regex fuzzing,
  invariant checks.
- **LC9-C** classifier alignment — full 9-class census diff, SAFE_AUTO gate,
  LC006 dry-run, LC007 impact-JSON byte-identity, cross-tool 0-agreement.
- **LC9-D** adversarial regression — folded into
  `tests/test_lc009_approved_terminal_verdict_semantics.py` (RE vectors,
  non-success prose corpus, fail-closed sweep) + LC9-A's fuzzing.
- **LC9-E** independent full-snapshot recount — from-scratch reimplementation
  of the approved contract and bucket walk, diffed against the live primitive.

### Verification results

**LC9-C (classifier alignment) — PASS.** Full 9-class census on this branch:
`ALREADY_EXPLICIT 0` (was 1), `MANUAL_SEMANTIC_REVIEW 41,831` (was 41,830),
every other class identical, `classification_total 42,804`, accounting PASS,
`current_explicit_success_records 0`. Reconstructing the pre-LC009 census by
monkeypatching the two changed primitives with their verbatim HEAD bodies
reproduces the baseline exactly; the OLD→LIVE diff is **exactly one record** —
`record_index 17147 (id 8023): ALREADY_EXPLICIT → MANUAL_SEMANTIC_REVIEW`.
`_re_is_non_failure_success` (now `_re_is_decisive(v) is True`) is a strict
subset of the old gate — every LIVE-True is OLD-True, so SAFE_AUTO can only
narrow; 0 records carry a non-empty root `game_result` so SAFE_AUTO stays 0.
0 of 45,779 reachable terminals carry `game_result` or `TE`. LC006 dry-run
exit 0, SAFE_AUTO 0, accounting PASS. `lc007_marker_policy_impact.json`
regenerated byte-identical (`db215a86…`). LC009 recount deterministic
(`83e97123…`), matches the checked-in file. Cross-tool: lc005 / lc006 / lc009
all report explicit-success = **0**. 313 tests pass.

**LC9-A (adversarial judge-diff review) — PASS.** Call-site audit: both
`judge_answer` sites (clj.py:437, :478) are `_is_leaf`-guarded; the `lc005`
sites (108/121 leaf-guarded; 129 = the opponent node that ends the authored
line with no player continuation). Channel 4 (terminal `N[...]`) can therefore
**never** read an `N` on a node that has authored player continuation — 0
corpus records exploit the line-129 path (0 terminal `N` success tokens; the
six `N[正解]` sit on move 1, which always has continuation). RE-regex fuzz
(`b+resignation`, `B+1e3`, `B+.5`, `B+000.000`, `B+D`, `\tB+R`, `W+0.0`,
`B+9999999999`, …): 0 false accepts, 0 false rejects; no ReDoS (20 000-digit
input < 1 ms). `_exact_marker_verdict` edge sweep: every interrogative
(`正解？` `正解?` `正解!?`), comparison (`黑地…正解一样…`), parenthetical
(`正解（best）`), spaced (`不 正解`), full-width (`ＣＯＲＲＥＣＴ`) and prose case
fails closed; `正解！！！` / `正解...` resolve to `True` (emphatic label after
approved trailing-punctuation normalisation — not a reference, defensible).
`正着 / 正著` are absent from the token set (owner vocabulary decision, hits
the old judge equally). Invariants BARE_LEAF_CORRECT / SUBSTRING_ONLY_SUCCESS
/ UNKNOWN_MARKER_FAIL_CLOSED / DETERMINISM all PASS. Regression surface:
`app.py` imports only `resolve_srs_review_authority` and forwards
`judge_version` as an opaque response string — no version-conditional logic;
`map_battle_*` uses its own `MAP_BATTLE_JUDGE_VERSION`; nothing else reads the
changed symbols.

**LC9-E (independent from-scratch recount) — PASS.** A reimplementation of the
approved contract + bucket walk sharing **no** code with the repo helpers:
pre-LC009 buckets `{163, 731, 1, 0, 41909}` → LC009 buckets
`{163, 731, 0, 0, 41910}`; `CHANGED = [(17147, id 8023, EXPLICIT_SUCCESS →
UNVERIFIABLE)]`; `NEWLY_ACCEPTED = []`. Running the same independent bucket
walk with the **live** `_explicit_terminal_is_correct` as the verdict function
produces byte-identical per-record buckets across all 42,804 records. Over the
whole corpus, **0** reachable terminals (of 45,779) score `True` and **0**
score `False` under the approved semantics.

(LC9-A and LC9-E were run by the Lead after the two subagents were killed
mid-run by an unrelated account spend-limit; LC9-B, LC9-C, LC9-D completed as
dispatched.)
