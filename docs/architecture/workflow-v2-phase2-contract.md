# Workflow V2 Phase 2: paired app/static coherence

Phase 2 adds a small release envelope around the existing app and static
release tooling. It binds the exact app artifact and the exact governed
live-static generation before an owner-authorized Production operation.

The envelope is evidence and decision logic, not a deployment framework. It
does not rebuild, copy, switch, or roll back anything. Existing
`preflight-production.ps1`, app build/package/deploy/verify/rollback scripts,
and static package/deploy/verify/rollback scripts remain the execution
boundary.

## Paired identity

`PAIRED_APP_STATIC` requires one envelope containing:

- `MERGED_SOURCE_SHA`;
- the app release-manifest digest, archive digest, image identity, image tag,
  and OCI revision;
- the static manifest digest, archive digest, generation identity, release
  source SHA, and Service Worker identity; and
- an explicit compatibility declaration with a deterministic `compatibility_id`.

The new pair is valid only when both artifact source identities equal the
merged source SHA and the declaration binds all of the above identities.
Preflight and deployment evidence must carry these same exact identities;
rebuilding or repackaging after approval is outside this contract.

## Immediate-predeploy rollback pair

Before a paired release is switched, the same `preflight-production.ps1`
observation must capture both the current app identity and current static
generation identity. The envelope records the observation ID, evidence digest,
capture scope, a verified old-pair compatibility identity, and both identities
under `OLD_COHERENT_PAIR`.

An app-only rollback record or a static-only `current → previous` pointer is
not sufficient for a paired release.

## Bounded convergence

The transition is guarded. The existing tools may perform their normal
owner-authorized switch operations, but external acceptance remains held until
the exact pair is verified. Objective failures are limited to mechanical or
runtime evidence such as health/readiness failure, container failure, artifact
identity mismatch, static integrity failure, and critical affected-path smoke
failure.

After a switch failure, the envelope produces a compensating plan using the
existing rollback tools and verifies both old identities. The only accepted
completed states are:

- `NEW_COHERENT_PAIR`; or
- `OLD_COHERENT_PAIR`.

The plan never treats a mixed app/static state as a release result. A
subjective Owner visual or product rejection holds the guarded transition for
manual review and never triggers automatic rollback.

## Release types preserved

`APP_ONLY` and `STATIC_ONLY` remain independent when the compatibility contract
does not require the other artifact. They do not acquire paired predeploy
requirements. `FAST_STATIC` remains a complete, manifest-bound live-static
generation; Phase 2 does not authorize arbitrary file promotion or widen its
serving boundary.

## Existing tooling reused

The envelope references, but does not replace:

- `scripts/release/preflight-production.ps1`;
- `scripts/release/build-release-image.ps1`,
  `build-production-image.ps1`, and `package-release-image.ps1`;
- `scripts/release/deploy-release-image.ps1`,
  `verify-production-release.ps1`, and `rollback-release.ps1`; and
- `scripts/release/package-static-release.ps1`,
  `deploy-static-release.ps1`, and `rollback-static-release.ps1`.

No Production operation was performed while establishing this contract.
