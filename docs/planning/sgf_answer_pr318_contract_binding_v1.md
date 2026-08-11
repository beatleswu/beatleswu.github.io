# SGF Answer Repair Batch 001 — PR318 Contract Binding

This record binds the already-approved, staged repair package to the
current-master content-release contract. It is evidence-only: it does not
apply `questions.json`, publish a Release, contact Production, or change SGF
Engine semantics.

## Exact package identities

The byte-exact baseline and candidate are retained in the immutable release
evidence directory used by the local verification command:

- baseline: `4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28`,
  71,534,726 bytes, 41,591 records
- candidate: `b7b4eedf72a87ab8fbc82ff51b658cd4dc0f08cb33426aee013e97814edae232`,
  71,534,621 bytes, 41,591 records
- repair groups: 43
- changed records: 54
- Map Battle exclusions: 11
- fallback conflict records excluded from the approved package: 3
- final effective verdict mismatches: 0

The corpus bytes are not committed to this repository. The checked-in
contract artifacts contain their exact identities and fail closed when the
supplied immutable evidence does not match.

## Contract artifacts

`docs/planning/sgf_answer_pr318_contract/` contains the derived, immutable
binding envelope:

- `source-provenance.json`
- `review-binding.json`
- `repair-batch-manifest.json`
- `mutation-audit.json`
- `acceptance-evidence.json`
- `rollback-manifest.json`
- `release-manifest.json`

The acceptance evidence requires all six existing player-facing surfaces and
records the precedence inputs (`accepted_moves`, native SGF, and historical
`katago_best_move`) without changing their runtime semantics.

## Reproduction / verification

From the repository root, run the existing local artifact builder first, then:

```text
python -B -m tools.sgf_pr318_binding \
  --baseline <immutable-release-evidence>/questions.pre-mutation.4d13fa98af8c.json \
  --candidate <immutable-release-evidence>/questions.repaired-candidate.b7b4eedf72a8.json \
  --historical-release-manifest <immutable-release-evidence>/content-release-manifest.b7b4eedf72a8.json \
  --historical-rollback-manifest <immutable-release-evidence>/content-rollback-manifest.b7b4eedf72a8.json \
  --rollback-simulation <immutable-release-evidence>/local-publish-rollback-simulation.json \
  --review-queue review_data/sgf_answer_review_queue_v1.json \
  --proposal-snapshot docs/planning/sgf_answer_repair_batch_001_proposal_snapshot.json \
  --repair-manifest docs/planning/sgf_answer_repair_batch_001_manifest.json \
  --safe-release-batch docs/planning/sgf_answer_repair_batch_001_safe_release_batch_001.json \
  --output-dir docs/planning/sgf_answer_pr318_contract
```

The command derives all contract hashes from the supplied bytes, validates the
same relationships PR318 validates during release-bundle construction, and
refuses to overwrite a different existing artifact.

Safety state remains `mutation_performed=false`,
`production_publish_authorized=false`, `SGF_SEMANTIC_MUTATION=NO`,
`CANONICAL_SGF_MUTATION=NO`, and `GF-003 runtime_status=disabled`.
