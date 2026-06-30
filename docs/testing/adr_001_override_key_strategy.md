# ADR 001: Production Override Key Strategy

## Status

Accepted for implementation planning.

Important wording:
This ADR is the current accepted baseline for production override identity.
Future DB/API/teacher-backend implementation may supersede this ADR through a new ADR.
Do not silently rewrite this decision record for incompatible future changes.

## Context

* Current override loader uses caller-provided source path string.
* `puzzle_variation_overrides.json` is currently `{}`.
* DB / API / teacher backend / student progress model are absent in the clean baseline.
* GF-003 is the first owner-approved equivalent-answer candidate.
* GF-003 production runtime override is not active.

## Problem

* Multi-answer / equivalent-move semantics cannot safely depend on file path.
* File rename, file move, duplicate filename, duplicated SGF bytes, and curated SGF revisions can break or misapply overrides.
* Student attempts and analytics need stable logical puzzle identity plus version identity.

## Critical Evidence

GF-001 and GF-005 share the same `163.sgf` file, source path, and SHA256.
Therefore file path / filename / SHA256 are physical source identities, not logical puzzle identities.

## Decision

* Canonical production override identity is `(puzzle_id, puzzle_version_id)`.
* `sgf_sha256` is an integrity guard.
* `source_path` and filename are migration/debug metadata only.
* GF id is a gold-fixture / external reference only.
* `override_id` identifies a specific override rule.
* SGF files should not be edited merely to encode owner-approved equivalent answers.

## Data Contract Baseline

Production-ready Schema B example:

```json
{
  "schema_version": 3,
  "overrides": [
    {
      "override_id": "ovr-gf003-sd-equivalent",
      "puzzle": {
        "puzzle_id": "colorful-go-tsumego-000431",
        "external_refs": {
          "gold_fixture_id": "GF-003"
        }
      },
      "version": {
        "puzzle_version_id": "pv-000431-001",
        "sgf_source_filename": "431.sgf",
        "sgf_sha256": "0713176f21c7a23133014a5956d935311b9aa8aa5a483a87ccf8100fea5c7d29"
      },
      "rules": {
        "equivalent_moves": [
          {
            "color": "B",
            "canonical_sgf": "sf",
            "canonical_label": "黑 T14",
            "equivalent_sgf": "sd",
            "equivalent_label": "黑 T16"
          }
        ]
      },
      "approval": {
        "status": "owner_approved",
        "reason": "Owner-approved equivalent answer; canonical branch is B[sf]."
      },
      "lifecycle": {
        "fixture_status": "CANDIDATE_REQUIRES_OVERRIDE",
        "runtime_status": "disabled",
        "apply_automatically": false
      }
    }
  ]
}
```

This schema is a data contract baseline, not active runtime configuration.
It does not activate GF-003.
It does not promote GF-003 to READY_WITH_OVERRIDE.

## GF-003 Example

canonical: `B[sf]` / 黑 T14
equivalent: `B[sd]` / 黑 T16

* Do not modify `431.sgf` for this equivalent answer.
* Do not activate production override in this ADR.
* GF-003 remains `CANDIDATE_REQUIRES_OVERRIDE` until schema validator, lookup tests, runtime integration, and owner activation review are complete.

## Engine Boundary

* SGF Engine should remain framework-neutral.
* Engine should consume validated override data structures.
* Engine should not be coupled to ORM, DB table names, API routes, or teacher backend implementation.
* Future JSON / DB / API sources should all adapt into the same validated override contract.

## Migration Plan

1. Add identity metadata contract.
2. Add schema validator.
3. Add puzzle_id + puzzle_version_id lookup tests.
4. Preserve file-path fallback only as deprecated compatibility alias.
5. Add sgf_sha256 mismatch tests.
6. Add disabled GF-003 production metadata.
7. Add runtime integration only after schema validator and tests.
8. Promote GF-003 to READY_WITH_OVERRIDE only after owner activation review.

## Non-goals

* No production override activation.
* No GF-003 promotion.
* No READY_IDS change.
* No SGF edit.
* No DB schema.
* No API route.
* No teacher backend.
* No student progress model.
* No schema validator in this ADR.
* No engine implementation change.

## Risks

* direct file path key risk
* filename-only risk
* sha256-only risk
* GF-id-only risk
* direct SGF edit risk
* premature DB schema risk
* storing student attempts by file path only risk
* curated SGF versioning risk

## Consequences

* Implementation cost is higher than path-key lookup.
* The model requires stable `puzzle_id` and immutable `puzzle_version_id` metadata.
* Overrides become auditable, version-safe, and compatible with future DB/API/teacher backend.
* Existing file-path temp override tests may remain as compatibility tests, but not as production identity.
