# SGF Answer Repair Batch 001 — Phase 2C Canonical Corpus Provenance Audit

Status: `READY_FOR_OWNER_CANONICAL_CORPUS_SOURCE_REVIEW`

This phase is read-only provenance research. It does not authorize or perform
question, SGF, fallback, Review Queue, database, merge, deployment, or
Production mutation.

## Decision

The exact governed source artifact for the current 41,591-record corpus is
not available in the authorized local/offline locations inspected in this
phase. The application repository does not own that corpus. Runtime reads it
from a persistent external Docker volume at `/app/data/questions.json`.

A same-count historical local candidate and the four historical SGF source
files were found under `D:\go website`, but that directory is not a Git
worktree, has no content release manifest, and does not byte-match the current
runtime corpus. It is source-history evidence, not an established canonical
content authority.

Resolving the exact current artifact, volume identity, backup coverage, and
content rollback target therefore requires a separately authorized read-only
Production provenance gate.

## Current corpus identity

Existing bounded evidence captured before this phase records:

- runtime path: `/app/data/questions.json`
- records: `41591`
- bytes: `71534726`
- SHA-256: `4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28`
- evidence file:
  `D:\go-website-sgf-answer-repair-batch-001-artifacts\current_canonical_targets.json`
- evidence scope: 118 requested Review Queue records plus runtime dataset
  readiness metadata; it is not a complete questions corpus copy

Local/offline search results:

- 24 large `questions*.json*` candidates under `D:\go-website*` were hashed;
  exact matches: `0`.
- 15 large `questions*.json*` candidates under the historical
  `D:\go website` tree were hashed; exact matches: `0`.
- `C:\Users\beatl\Downloads` contained no questions-named candidate.
- Targeted SGF Sprint and release-artifact directories contained no exact
  full-corpus artifact. Both current governed application image archives
  contain zero `questions.json` entries, as required by the image/content
  boundary.
- The historical `D:\go website\go-odyssey-deploy.tar.gz` is incomplete
  (`EOFError`) and cannot serve as a readable or governed artifact.

The closest same-count local candidate is:

- path: `D:\go website\questions.json`
- records: `41591`
- bytes: `61305616`
- SHA-256: `55ea08f94be08ac2d11e86dc6d5b2b4e83d73288631e5aa5b4d94876da7dfac7`
- last modified UTC: `2026-06-16T07:58:46`
- exact current match: `NO`

The Owner-review snapshot remains separately identified as:

- path: `D:\go-website\questions.json`
- records: `42804`
- bytes: `75675637`
- SHA-256: `88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff`
- canonical status: historical review evidence only

Neither local file may be promoted or mutated as the current canonical corpus.

## Runtime and deployment trace

### Runtime load path

`app.py` sets `DATA_FILE` from `QUESTIONS_JSON_PATH` and loads that JSON
directly. `docker-compose.release.yml` defaults the variable to
`/app/data/questions.json` and mounts an external named Docker volume at
`/app/data`.

`deploy/release-layout.production.json` declares:

- `questions_content_source_path=/opt/go-odyssey-data`
- `questions_content_mount_destination=/app/data`

However, the governed deploy and rollback scripts do not copy
`/opt/go-odyssey-data` into the runtime. They inspect the currently running app
container, recover the existing named-volume identity, and pass that identity
back to Compose as `QUESTIONS_CONTENT_VOLUME_NAME`. The source-path declaration
is release-manifest metadata, not a proved content publication source.

Therefore:

- `QUESTIONS_RUNTIME_PATH=/app/data/questions.json`
- `QUESTIONS_RUNTIME_MOUNT_OR_COPY_SOURCE=EXTERNAL_NAMED_DOCKER_VOLUME_DISCOVERED_FROM_LIVE_APP`
- physical volume name/source: `UNKNOWN_WITHOUT_PRODUCTION_READ`
- application image contains questions corpus: `NO`
- normal application-image deploy replaces questions corpus: `NO`
- normal application-image rollback restores questions corpus: `NO`

### Build source and historical generation

The historical local `D:\go website\build_questions.py` provides a concrete
generation trace:

- input root: sibling `SGF題庫`
- output: sibling `questions.json`
- SGFs are read with supported legacy encodings and `.strip()`
- existing IDs and non-source fields are preserved where possible
- `content` and `source` are refreshed from the SGF tree
- the result is serialized as an indented JSON list

This explains the four source paths and the normalized equality documented
below. It does not reproduce the exact current runtime artifact: the local
same-count output has a different size and SHA-256, and Production/admin
mutation can subsequently rewrite the persistent runtime file.

### Publish/update workflow

Two different eras are visible:

1. The historical ungoverned `D:\go website\deploy.ps1` packaged
   `questions.json` with the application source while excluding the SGF tree.
2. The current governed image flow deliberately excludes `questions.json` and
   retains the existing external named volume. Repository comments describe a
   one-time operator copy of a baseline “out of band,” but no governed baseline
   copy/publish command or immutable content manifest was found.

Current application Admin question-management endpoints call
`_save_questions()`, which serializes the complete list to a temporary file,
copies the previous runtime file to one rolling `questions.json.bak`, and then
atomically replaces `questions.json`. This is an in-place persistent-data
update, not an immutable content release workflow.

Accordingly:

- `QUESTIONS_BUILD_SOURCE=HISTORICAL_LOCAL_SGF_TREE_PLUS_BUILD_QUESTIONS_PY_NOT_CURRENT_EXACT_AUTHORITY`
- `QUESTIONS_PUBLISH_WORKFLOW=OUT_OF_BAND_BASELINE_PLUS_IN_PLACE_ADMIN_API_WRITES; NO_GOVERNED_CONTENT_PUBLISH_COMMAND_FOUND`
- `QUESTIONS_VERSIONING_MECHANISM=NO_CONTENT_LEVEL_VERSION_REGISTRY; ONE_ROLLING_BAK_AND_INFRASTRUCTURE_BACKUP_EVIDENCE_ONLY`
- `QUESTIONS_ROLLBACK_MECHANISM=NO_GOVERNED_CONTENT_ROLLBACK; APP_IMAGE_ROLLBACK_REUSES_THE_SAME_VOLUME`

Historical backup documentation describes daily site archives and weekly OCI
boot-volume snapshots. The archived site root is `/opt/go-odyssey`, while the
current corpus is in a Docker named volume. Weekly block-volume recovery may
capture it, but exact current coverage and a content-only restore target were
not proved in this phase. These backups are not a substitute for an immutable,
hashed content release.

## Four native SGF source traces

For all four records, the existing bounded current-target evidence contains a
relative `current_source_path` and embedded `current_content`. A matching local
path exists under the historical `D:\go website\SGF題庫` tree. Raw file bytes
differ only because the historical builder reads and strips surrounding line
breaks: normalized/trimmed text is exactly equal to current embedded content.

### Question 7998

- current relative source:
  `天道殘卷：中盤妙手與鬼手全書 ｜ Go - Cosmic Fragments Encyclopedia of Divine Moves\官子部\120.sgf`
- local source-history candidate:
  `D:\go website\SGF題庫\天道殘卷：中盤妙手與鬼手全書 ｜ Go - Cosmic Fragments Encyclopedia of Divine Moves\官子部\120.sgf`
- local raw SHA-256:
  `50b66e6505fb7d55d2de983de4bae3950165aebe31e7336a3297376546ebf0db`
- current embedded-content SHA-256:
  `73c9e4777e69d48b007ec249db78148a581fffafda76cbfaee75151a6a6bd358`
- normalized text match: `YES`

### Question 8057

- current relative source:
  `天道殘卷：中盤妙手與鬼手全書 ｜ Go - Cosmic Fragments Encyclopedia of Divine Moves\官子部\179.sgf`
- local source-history candidate:
  `D:\go website\SGF題庫\天道殘卷：中盤妙手與鬼手全書 ｜ Go - Cosmic Fragments Encyclopedia of Divine Moves\官子部\179.sgf`
- local raw SHA-256:
  `6489eaf4b35796087f469463322b2f6adc30af6855a542b02cd51ac05859accc`
- current embedded-content SHA-256:
  `d11bb70ad4dc559f5db834ed0ffb60da61f9f11c5ec414d1425acae3445b8386`
- normalized text match: `YES`

### Question 8092

- current relative source:
  `天道殘卷：中盤妙手與鬼手全書 ｜ Go - Cosmic Fragments Encyclopedia of Divine Moves\官子部\30.sgf`
- local source-history candidate:
  `D:\go website\SGF題庫\天道殘卷：中盤妙手與鬼手全書 ｜ Go - Cosmic Fragments Encyclopedia of Divine Moves\官子部\30.sgf`
- local raw SHA-256:
  `05b611207fcf342ece02307df140cc2d3f3c5c4d76330f101c068512249a83d0`
- current embedded-content SHA-256:
  `98480f03bdcfdea84846f15f873e10eeafc14a7a1ff10f559d5bb0547259bc27`
- normalized text match: `YES`

### Question 8100

- current relative source:
  `天道殘卷：中盤妙手與鬼手全書 ｜ Go - Cosmic Fragments Encyclopedia of Divine Moves\官子部\38.sgf`
- local source-history candidate:
  `D:\go website\SGF題庫\天道殘卷：中盤妙手與鬼手全書 ｜ Go - Cosmic Fragments Encyclopedia of Divine Moves\官子部\38.sgf`
- local raw SHA-256:
  `81476c4650caf8d3d8f2f8ba3fe0bbbd76ecaa1028ce96d2ba40549656b2627c`
- current embedded-content SHA-256:
  `7e809d745cbd120631a4495c86b10a16321a0090c0fd18f4a5de7e2993484285`
- normalized text match: `YES`

For every record:

- local source candidate exists: `YES`
- local candidate is Git-versioned: `NO`
- local candidate has timestamped backup siblings: `YES`
- current `questions.json` content is demonstrably derived from that source:
  `YES`, for the bounded record
- candidate is proved as the governed canonical mutation authority: `NO`

## Governance classification and PR boundary

`CONTENT_GOVERNANCE_MODEL=E_OTHER`

Evidence-based description: Production persistent named-volume content with an
out-of-band historical baseline, in-place Admin mutation, a single rolling
`.bak`, and infrastructure-backup evidence, but no established immutable
content version/artifact or governed content-only publish/rollback procedure.

PR #302 can continue to own repair logic, dry-run evidence, immutable proposed
mutations, and provenance documentation. It must not claim that repository
files are the canonical corpus or contain the actual 65-record repair.

`RECOMMENDED_EXISTING_REPAIR_WORKFLOW=SEPARATE_CONTENT_ARTIFACT_WORKFLOW_REQUIRED; NONE_CURRENTLY_ESTABLISHED`

The next authorization should be an
`OWNER_READ_ONLY_PRODUCTION_PROVENANCE_GATE`, limited to:

1. byte-for-byte read-only acquisition and hashing of the exact current
   `/app/data/questions.json` without printing corpus contents;
2. read-only identification of the external Docker volume and its source;
3. read-only inventory of the current `questions.json.bak` identity and
   applicable backup/snapshot coverage;
4. confirmation of a recoverable, exact pre-mutation content artifact and
   rollback target.

Only after that evidence exists should the Owner choose or authorize a
separate governed content-artifact apply workflow. No Production access was
performed in this phase.

## Required assertions

```text
CURRENT_CORPUS_LOCAL_PATH=NOT_FOUND_EXACT; NEAREST_SAME_COUNT=D:\go website\questions.json
CURRENT_CORPUS_RECORDS=41591
CURRENT_CORPUS_SHA256=4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28
CURRENT_CORPUS_EXACT_MATCH=NO
QUESTIONS_RUNTIME_PATH=/app/data/questions.json
QUESTIONS_RUNTIME_MOUNT_OR_COPY_SOURCE=EXTERNAL_NAMED_DOCKER_VOLUME_DISCOVERED_FROM_LIVE_APP
QUESTIONS_BUILD_SOURCE=HISTORICAL_LOCAL_SGF_TREE_PLUS_BUILD_QUESTIONS_PY_NOT_CURRENT_EXACT_AUTHORITY
QUESTIONS_PUBLISH_WORKFLOW=OUT_OF_BAND_BASELINE_PLUS_IN_PLACE_ADMIN_API_WRITES; NO_GOVERNED_CONTENT_PUBLISH_COMMAND_FOUND
QUESTIONS_VERSIONING_MECHANISM=NO_CONTENT_LEVEL_VERSION_REGISTRY; ONE_ROLLING_BAK_AND_INFRASTRUCTURE_BACKUP_EVIDENCE_ONLY
QUESTIONS_ROLLBACK_MECHANISM=NO_GOVERNED_CONTENT_ROLLBACK; APP_IMAGE_ROLLBACK_REUSES_THE_SAME_VOLUME
Q7998_CANONICAL_SGF_SOURCE=UNRESOLVED; LOCAL_SOURCE_HISTORY_CANDIDATE=D:\go website\SGF題庫\天道殘卷：中盤妙手與鬼手全書 ｜ Go - Cosmic Fragments Encyclopedia of Divine Moves\官子部\120.sgf
Q8057_CANONICAL_SGF_SOURCE=UNRESOLVED; LOCAL_SOURCE_HISTORY_CANDIDATE=D:\go website\SGF題庫\天道殘卷：中盤妙手與鬼手全書 ｜ Go - Cosmic Fragments Encyclopedia of Divine Moves\官子部\179.sgf
Q8092_CANONICAL_SGF_SOURCE=UNRESOLVED; LOCAL_SOURCE_HISTORY_CANDIDATE=D:\go website\SGF題庫\天道殘卷：中盤妙手與鬼手全書 ｜ Go - Cosmic Fragments Encyclopedia of Divine Moves\官子部\30.sgf
Q8100_CANONICAL_SGF_SOURCE=UNRESOLVED; LOCAL_SOURCE_HISTORY_CANDIDATE=D:\go website\SGF題庫\天道殘卷：中盤妙手與鬼手全書 ｜ Go - Cosmic Fragments Encyclopedia of Divine Moves\官子部\38.sgf
CONTENT_GOVERNANCE_MODEL=E_OTHER
RECOMMENDED_EXISTING_REPAIR_WORKFLOW=SEPARATE_CONTENT_ARTIFACT_WORKFLOW_REQUIRED; NONE_CURRENTLY_ESTABLISHED
PRODUCTION_READ_REQUIRED_TO_RESOLVE=YES
CANONICAL_SGF_MUTATED=NO
QUESTIONS_JSON_MUTATED=NO
FALLBACK_DATA_MUTATED=NO
PRODUCTION_CONTACT=NONE
MERGE=NO
DEPLOY=NO
```
