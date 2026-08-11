# Project OS v2

This document captures the durable workflow that governs Go Odyssey change
delivery.

Workflow V2 Phase 1 operational classes and evidence contracts are defined in
docs/architecture/workflow-v2-phase1-contract.md. The A/B/C labels below
remain useful legacy impact labels, but they do not replace the authority-
based NORMAL, HOTFIX, and HEAVY classification.

## Workflow V2 delivery path

Normal and Hotfix work should ordinarily follow:

1. development
2. focused PR validation and machine-readable PR evidence
3. owner merge decision
4. merge
5. merged-source release evidence and exact artifact preparation, when needed
6. owner deploy decision, when needed
7. deployment and objective verification

Heavy work retains the stronger existing lifecycle and may require broader
validation. The final release declaration is APP_ONLY, STATIC_ONLY, or
PAIRED_APP_STATIC. Paired app/static coherence and rollback remain a Phase 2
requirement.

## Risk Classes

- `A` - docs/config-only
- `B` - tests/UI/non-authoritative runtime
- `C` - database, parser, judging, infrastructure, Production

## Standard Sprint Lifecycle

1. preflight
2. isolated branch
3. implementation
4. focused tests
5. clean checkout build
6. local smoke
7. PR
8. review gate
9. merge
10. immutable release build
11. owner deploy gate
12. Production verification
13. rollback when required
14. final report

## Fast Mode

- Low- and medium-risk work may combine implementation, tests, merge,
  deploy, and verify.
- High-risk work must retain explicit safety gates.

## Mandatory Production Gates

- immutable image identity
- architecture verification
- rollback identity
- health
- readiness
- real feature smoke
- no secret exposure
- no user-data mutation without explicit migration plan

## Gameplay Deployment Definition

A Go Odyssey deployment is not successful until:

- questions load
- board renders
- move submission works
- answer evaluation works
- SRS persistence works
- feedback appears
- next question remains functional

## AI Roles

- AI explains
- SGF Engine judges
- deployment tooling verifies
- owner authorizes irreversible Production actions

## Owner Strings

- `GO MERGE`
- `GO DEPLOY`
- `GO_ROLLBACK`

Conditional advance authorization may be given in a Sprint task, but it does
not remove the mandatory gates above.
