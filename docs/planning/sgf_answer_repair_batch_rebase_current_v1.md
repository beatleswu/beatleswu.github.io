# SGF repair batch rebase on the current canonical corpus

This record binds the already-approved 43-group / 54-record repair batch to
the current canonical snapshot. It does not rediscover repairs and it is not a
canonical corpus change.

- Baseline: `88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff`
  (42,804 records).
- Candidate: `4ac424c4af4acf46d1df1dd4b4579b57b01a08745dd7f621c7f50ce21e78f125`
  (42,804 records; external staged artifact).
- Target classification: 54 `UNCHANGED_TARGET`, 0 `ALREADY_REPAIRED`, 0
  `DRIFTED_TARGET`, 0 `MISSING_TARGET`.
- Applied scope: 54 approved target records only; 11 exclusions and 3 fallback
  conflicts remain unchanged.
- Acceptance evidence: all six required surfaces are present and all 54
  `OWNER_DESIRED_VERDICT` values equal the `FINAL_EFFECTIVE_PLAYER_VERDICT`.
- Rollback proof: local disposable exact-byte simulation only; publication
  still requires the rollback proof and an owner gate.

The machine-readable contract artifacts are in
`docs/planning/sgf_answer_current_canonical_contract_v2/`. The historical
`b7b4eedf...` candidate hash is retained only as historical evidence; it is not
an expected hash for this current-base candidate.

`GF-003` remains disabled, no canonical bytes were changed, and no Production
publish or deployment was performed.
