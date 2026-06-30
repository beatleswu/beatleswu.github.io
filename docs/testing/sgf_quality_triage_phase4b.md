# Phase 4B SGF Quality Triage Packet

## Scope

This document is a docs-only owner triage packet based on Phase 4A scanner output.
It does not repair, delete, move, or activate any SGF or override behavior.

## Source Reports

- `docs/testing/sgf_inventory_known_quality_issues_report.json`
- `docs/testing/sgf_inventory_known_quality_issues_report.md`

Phase 4B copies scanner findings from Phase 4A reports and does not recompute scanner heuristics.

## Summary

- missing answers count: 0
- possible board crop / coordinate mismatch count: 3
- possible global AI tenuki count: 0
- multiple root children count: 0
- has variations count: 1
- parse errors count: 0

Counts are copied from the Phase 4A JSON report.

## Owner Decision Legend

- default owner decision: `OWNER_REVIEW_REQUIRED`
- available owner decisions: `OWNER_REVIEW_REQUIRED`, `CONFIRMED_CROP_OR_COORDINATE_MISMATCH`, `FALSE_POSITIVE_NORMAL_EDGE_PROBLEM`, `CONFIRMED_GLOBAL_AI_TENUKI`, `CONFIRMED_MISSING_ANSWER`, `NEEDS_SGF_REPAIR`, `NEEDS_ARCHIVE_OR_REMOVAL`, `NEEDS_GOLD_FIXTURE`, `NO_ACTION_NEEDED`

If a field is missing, null, empty, or not present in the Phase 4A JSON report, this packet renders it as `not present in Phase 4A report`.

## Missing Answers

No missing-answer candidates were reported in the current Phase 4A scan scope.
This does not prove the full SGF corpus has no missing-answer problems.

## Possible Board Crop / Coordinate Mismatch

### Candidate 1

- source_path: `tests/sgf_engine/data/gold_fixtures/163.sgf`
- sha256: `55231BF237F4813113B4094F4B97F4868BCDC6C40CAA419123AF7AA733E17C21`
- detected category: `Possible board crop / coordinate mismatch`
- quality_flags: `TERMINAL_TOO_SHALLOW`, `ANSWER_ON_EDGE_LINE`, `POSSIBLE_BOARD_CROP_COORDINATE_MISMATCH`
- root_child_moves: `B[sb]`
- root_child_moves_go_coords: `B[sb] / T18`
- setup summary / bounding box: `{'min_x': 15, 'max_x': 18, 'min_y': 0, 'max_y': 7, 'min_go': 'Q19', 'max_go': 'T12', 'stone_count': 14}`
- scanner reason: `SGF answer line ends at or near the first move.; root answer B[sb] / T18 is on board edge.; root answer B[sb] / T18 is a board crop review candidate.`
- owner decision: `FALSE_POSITIVE_NORMAL_EDGE_PROBLEM`
- owner notes:
- suggested review questions:
  - Is this a confirmed board-crop or coordinate-mismatch issue?
  - Is the edge answer normal for this local problem type?
  - Does the root answer belong to the intended local region?
  - Is there a better SGF variation that should replace this one?
  - Should this candidate be repaired, archived, or removed?
  - Should this candidate become a future gold fixture?

### Candidate 2

- source_path: `tests/sgf_engine/data/gold_fixtures/186.sgf`
- sha256: `AE93FABAB9A0DC5A23EF495875CD18662AB9871DAEAD487DED55BCFF1B6CE64A`
- detected category: `Possible board crop / coordinate mismatch`
- quality_flags: `TERMINAL_TOO_SHALLOW`, `ANSWER_ON_EDGE_LINE`, `POSSIBLE_BOARD_CROP_COORDINATE_MISMATCH`
- root_child_moves: `B[ea]`
- root_child_moves_go_coords: `B[ea] / E19`
- setup summary / bounding box: `{'min_x': 0, 'max_x': 7, 'min_y': 0, 'max_y': 5, 'min_go': 'A19', 'max_go': 'H14', 'stone_count': 26}`
- scanner reason: `SGF answer line ends at or near the first move.; root answer B[ea] / E19 is on board edge.; root answer B[ea] / E19 is a board crop review candidate.`
- owner decision: `FALSE_POSITIVE_NORMAL_EDGE_PROBLEM`
- owner notes:
- suggested review questions:
  - Is this a confirmed board-crop or coordinate-mismatch issue?
  - Is the edge answer normal for this local problem type?
  - Does the root answer belong to the intended local region?
  - Is there a better SGF variation that should replace this one?
  - Should this candidate be repaired, archived, or removed?
  - Should this candidate become a future gold fixture?

### Candidate 3

- source_path: `tests/sgf_engine/data/gold_fixtures/431.sgf`
- sha256: `0713176F21C7A23133014A5956D935311B9AA8AA5A483A87CCF8100FEA5C7D29`
- detected category: `Possible board crop / coordinate mismatch`
- quality_flags: `TERMINAL_TOO_SHALLOW`, `ANSWER_ON_EDGE_LINE`, `POSSIBLE_BOARD_CROP_COORDINATE_MISMATCH`
- root_child_moves: `B[sf]`
- root_child_moves_go_coords: `B[sf] / T14`
- setup summary / bounding box: `{'min_x': 14, 'max_x': 17, 'min_y': 1, 'max_y': 6, 'min_go': 'P18', 'max_go': 'S13', 'stone_count': 12}`
- scanner reason: `SGF answer line ends at or near the first move.; root answer B[sf] / T14 is on board edge.; root answer B[sf] / T14 is a board crop review candidate.`
- owner decision: `NEEDS_GOLD_FIXTURE`
- owner notes:
- suggested review questions:
  - Is this a confirmed board-crop or coordinate-mismatch issue?
  - Is the edge answer normal for this local problem type?
  - Does the root answer belong to the intended local region?
  - Is there a better SGF variation that should replace this one?
  - Should this candidate be repaired, archived, or removed?
  - Should this candidate become a future gold fixture?

## Possible Global AI Tenuki Answers

No possible global-AI-tenuki candidates were reported in the current Phase 4A scan scope.
This does not prove the full SGF corpus has no global-AI-tenuki problems.
The Chinese path-hint regression coverage was added in Phase 4A, but this triage document only reflects the current scanned report.

## GF-003 / 431.sgf Note

- GF-003 = `431.sgf`
- native root answer: `B[sf] / T14`
- owner-approved equivalent candidate: `B[sd] / T16`
- 431.sgf SHA256: `0713176F21C7A23133014A5956D935311B9AA8AA5A483A87CCF8100FEA5C7D29`
- status: `CANDIDATE_REQUIRES_OVERRIDE`
- runtime_status: `disabled`
- apply_automatically: `false`
- production override: `not active`
- READY promotion: `no`

`B[sd] / T16` remains candidate-only.
No runtime override is activated.
No SGF bytes are changed.
No READY promotion is performed.

## Recommended Next Actions

- Owner reviews each board-crop candidate.
- Owner marks each candidate as confirmed issue or false positive.
- Confirmed repair candidates should be handled in a separate future SGF repair PR.
- Confirmed archive/removal candidates should be handled in a separate future cleanup PR.
- No SGF repair is performed in Phase 4B.

## Read-only Safety Statement

Phase 4B is documentation-only.
No SGF files were edited, deleted, or moved.
No override behavior was activated.
No runtime judging behavior was changed.
