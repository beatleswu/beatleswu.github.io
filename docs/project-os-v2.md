# Project OS v2

This document captures the durable workflow that governs Go Odyssey change
delivery.

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
