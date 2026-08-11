# SGF Answer Repair Batch 001 — Phase 2E Content Release Dry Run

Status: `FAIL_CLOSED_PENDING_OWNER_RUNTIME_SCOPE_DECISION`

Authorization: local/offline analysis and package preparation only. Production
contact, Production content mutation, merge, and deployment remained forbidden.

## Result

The exact Production baseline was re-verified successfully, and the two locked
repair lanes can be applied in memory with an exact semantic mutation boundary:

- baseline records: `41591`
- baseline bytes: `71534726`
- baseline SHA-256:
  `4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28`
- target records changed in the in-memory candidate: `65`
- non-target records changed: `0`
- native SGF content fields changed: `4`
- `katago_best_move` fields cleared: `61`
- any `accepted_moves` field changed: `NO`
- whole-corpus JSON reserialization: `NO`

The builder patches only the selected top-level string value inside each locked
record. All other record bytes and every non-target record remain untouched.

No repaired candidate, release manifest, or rollback manifest was emitted,
because the required strict final-player-verdict gate did not pass.

## Locked inputs

- `SAFE_NATIVE_SGF_BATCH_SHA256`:
  `6fd56597f599ce1be117ac2558aaa6a2e19ffb2531d802278cedc3d97f1d1b0a`
- `SAFE_NATIVE_SGF_BATCH_FILE_SHA256`:
  `47d08829116ffb60bd5e29062c228c394cc81ee6a0758dc9e4a1394cd5c3a69a`
- `FALLBACK_CANDIDATE_BATCH_SHA256`:
  `8f86e709306d5f6c0e46d6cad9b5094bebb9eaf618bf0c0d16ab12c237e2d422`
- `FALLBACK_CANDIDATE_BATCH_FILE_SHA256`:
  `8db0585194e7b8f33f012a5e8f091e0090d3cfbaae1b0c5116fbfeead866a0f8`

Membership remained exactly `4 + 61` records with no overlap. Questions
15436, 15388, and 65095 remained excluded and unchanged.

The corpus contains 12 unrelated duplicate legacy-ID records across 12 ID
values. None of the 65 targets or three known fallback conflicts is ambiguous.
The content builder therefore resolves each target using the locked record
index, legacy ID, and current content/fallback preconditions instead of
incorrectly assuming global legacy-ID uniqueness. This remains
`AUDIT_LOCATOR_ONLY`; canonical identity was not implemented.

## Runtime verdict validation

The validator uses complete authored player-move witnesses rather than treating
one first move as a complete multi-move solution. It exercised:

- strict SGF Engine parsing and exhaustive native first-move matching;
- the actual Rating Test `_rt_server_verify` adapter;
- the actual Map Battle V1 `judge_map_battle_answer_v1` adapter;
- main-practice, daily, and friend native-answer surfaces;
- final effective native, accepted-move, and stored-fallback layers.

Results against the in-memory repaired candidate:

| Gate | Result |
|---|---:|
| SGF Engine native answer set equals Owner desired | 65 / 65 |
| Rating Test final verdict equals Owner desired | 65 / 65 |
| Main/daily/friend native verdict equals Owner desired | 65 / 65 |
| Map Battle V1 equals Owner desired | 54 / 65 |
| Native-SGF lane Map Battle V1 | 4 / 4 |
| Fallback-only lane Map Battle V1 | 50 / 61 records overall; 11 records retain an existing traversal limitation |
| Strict all-surface final effective match | `NO` |

The 11 strict Map Battle mismatches are:

```text
37624
64952
65063
65106
72868
73069
73096
73121
73212
73581
73632
```

All 11 belong only to the fallback-remediation lane. Their SGF `content` is
byte-identical before and after the proposed fallback clear, and Map Battle V1
does not consume `katago_best_move`. Therefore the candidate would not create
this Map Battle behavior, but the strict Phase 2E requirement that every
player-facing surface equal the Owner desired answer is not currently true.

## Runtime discrepancy

These SGFs contain valid authored first moves followed by points where more
than one opponent reply is authored. Rating Test replay deterministically
follows its first authored opponent reply. Map Battle V1 advances an opponent
reply only when exactly one opponent child exists. At a multi-reply node it
does not advance, so the next submitted player move is checked at the wrong
tree level and returns `off_answer_tree`.

No Map Battle, judging-precedence, SGF, fallback, or gameplay code was changed
to work around this finding. Such a behavior change is outside the authorized
Phase 2E scope.

## Content publisher and rollback tooling

`tools/sgf_answer_content_release.py` now provides locally tested primitives
for a later gate:

1. exact baseline hash/size/count verification;
2. locked batch and membership verification;
3. targeted non-reserializing record-field patching;
4. semantic diff enforcement;
5. actual judging validation before artifact emission;
6. hash-preconditioned, same-directory atomic replacement;
7. exact content-only rollback;
8. local wrong-hash, interrupted-stage, publish, and rollback simulation;
9. explicit `GO_CONTENT_PUBLISH` or `GO_CONTENT_ROLLBACK` plus `--execute`
   execution gates.

Synthetic/local atomic-operation tests passed, including wrong-hash refusal,
pre-replace interruption safety, and byte-exact rollback. They are not a
substitute for an actual 65-record package simulation, which was correctly not
run because no valid candidate artifact was emitted.

## Validation

```text
DEDICATED_CONTENT_RELEASE_TESTS=10_PASS
RELEVANT_REGRESSION_TESTS=170_PASS
PYTHON_COMPILE=PASS
DETERMINISTIC_STRICT_BUILD_FAILURE=PASS
STRICT_BUILD_BLOCKER_IDS=37624,64952,65063,65106,72868,73069,73096,73121,73212,73581,73632
OUTPUT_DIRECTORY_CREATED=NO
REPAIRED_CANDIDATE_CREATED=NO
CONTENT_RELEASE_MANIFEST_CREATED=NO
CONTENT_ROLLBACK_MANIFEST_CREATED=NO
```

## Owner decision required

Phase 2E cannot truthfully stop at
`READY_FOR_OWNER_CONTENT_RELEASE_PACKAGE_REVIEW` under the current strict
all-surface criterion. A later Owner instruction would need to choose one of
these boundaries without Codex inferring it:

1. explicitly restore the Phase 2B fallback-lane criterion
   `GAMEPLAY_PLAYER_VERDICT=UNCHANGED_OR_CORRECT`, while retaining strict
   Rating/native checks and strict Map Battle checks for the four native SGF
   repairs;
2. re-lock a smaller fallback batch that excludes the 11 records; or
3. authorize a separate Map Battle traversal-semantics Sprint before package
   creation.

No option was selected or implemented in this phase.

## Safety assertions

```text
BASELINE_SHA256=4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28
BASELINE_HASH_MATCH=YES
TARGET_RECORDS_CHANGED_IN_MEMORY=65
NON_TARGET_RECORDS_CHANGED_IN_MEMORY=0
FALLBACK_FIELDS_CLEARED_IN_MEMORY=61
NATIVE_REPAIR_RECORDS_IN_MEMORY=4
ALL_65_FINAL_EFFECTIVE_MATCH=NO
REPAIRED_CANDIDATE_PATH=NOT_CREATED_FAIL_CLOSED
CONTENT_RELEASE_MANIFEST=NOT_CREATED_FAIL_CLOSED
CONTENT_ROLLBACK_MANIFEST=NOT_CREATED_FAIL_CLOSED
PUBLISHER_PRECONDITION_HASH_LOCK=4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28
PUBLISHER_LOCAL_SIMULATION=PASS_SYNTHETIC_ONLY
WRONG_HASH_FAIL_CLOSED_TEST=PASS
ROLLBACK_LOCAL_SIMULATION=PASS_SYNTHETIC_ONLY
ROLLBACK_BYTE_EXACT=PASS_SYNTHETIC_ONLY
PRODUCTION_CONTACT=NONE
PRODUCTION_MUTATION=NO
MERGE=NO
DEPLOY=NO
KATAGO_RUN=NONE
IDENTITY_IMPLEMENTED=NO
```
