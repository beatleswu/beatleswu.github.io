# SGF Inventory / Known Quality Issues Report

## Scope

- Root scanned: `tests/sgf_engine/data/gold_fixtures`
- This report is read-only and records owner-review candidates only.

## Summary

- total SGF files: 6
- parse success count: 6
- parse error count: 0
- missing answers count: 0
- possible board crop / coordinate mismatch count: 3
- possible global AI tenuki count: 0
- multiple root children count: 0
- has variations count: 1

## Missing answers

None detected.

## Possible board crop / coordinate mismatch

- `tests/sgf_engine/data/gold_fixtures/163.sgf`
  - sha256: `55231BF237F4813113B4094F4B97F4868BCDC6C40CAA419123AF7AA733E17C21`
  - parse_status: `ok`
  - root_child_moves: B[sb]
  - root_child_moves_go_coords: B[sb] / T18
  - setup_bounding_box: `{'min_x': 15, 'max_x': 18, 'min_y': 0, 'max_y': 7, 'min_go': 'Q19', 'max_go': 'T12', 'stone_count': 14}`
  - quality_flags: TERMINAL_TOO_SHALLOW, ANSWER_ON_EDGE_LINE, POSSIBLE_BOARD_CROP_COORDINATE_MISMATCH
  - reason: SGF answer line ends at or near the first move.; root answer B[sb] / T18 is on board edge.; root answer B[sb] / T18 is a board crop review candidate.
- `tests/sgf_engine/data/gold_fixtures/186.sgf`
  - sha256: `AE93FABAB9A0DC5A23EF495875CD18662AB9871DAEAD487DED55BCFF1B6CE64A`
  - parse_status: `ok`
  - root_child_moves: B[ea]
  - root_child_moves_go_coords: B[ea] / E19
  - setup_bounding_box: `{'min_x': 0, 'max_x': 7, 'min_y': 0, 'max_y': 5, 'min_go': 'A19', 'max_go': 'H14', 'stone_count': 26}`
  - quality_flags: TERMINAL_TOO_SHALLOW, ANSWER_ON_EDGE_LINE, POSSIBLE_BOARD_CROP_COORDINATE_MISMATCH
  - reason: SGF answer line ends at or near the first move.; root answer B[ea] / E19 is on board edge.; root answer B[ea] / E19 is a board crop review candidate.
- `tests/sgf_engine/data/gold_fixtures/431.sgf`
  - sha256: `0713176F21C7A23133014A5956D935311B9AA8AA5A483A87CCF8100FEA5C7D29`
  - parse_status: `ok`
  - root_child_moves: B[sf]
  - root_child_moves_go_coords: B[sf] / T14
  - setup_bounding_box: `{'min_x': 14, 'max_x': 17, 'min_y': 1, 'max_y': 6, 'min_go': 'P18', 'max_go': 'S13', 'stone_count': 12}`
  - quality_flags: TERMINAL_TOO_SHALLOW, ANSWER_ON_EDGE_LINE, POSSIBLE_BOARD_CROP_COORDINATE_MISMATCH
  - reason: SGF answer line ends at or near the first move.; root answer B[sf] / T14 is on board edge.; root answer B[sf] / T14 is a board crop review candidate.

## Possible global AI tenuki answers

None detected.

## Other quality flags

- `tests/sgf_engine/data/gold_fixtures/163.sgf`
  - sha256: `55231BF237F4813113B4094F4B97F4868BCDC6C40CAA419123AF7AA733E17C21`
  - parse_status: `ok`
  - root_child_moves: B[sb]
  - root_child_moves_go_coords: B[sb] / T18
  - setup_bounding_box: `{'min_x': 15, 'max_x': 18, 'min_y': 0, 'max_y': 7, 'min_go': 'Q19', 'max_go': 'T12', 'stone_count': 14}`
  - quality_flags: TERMINAL_TOO_SHALLOW, ANSWER_ON_EDGE_LINE, POSSIBLE_BOARD_CROP_COORDINATE_MISMATCH
  - reason: SGF answer line ends at or near the first move.; root answer B[sb] / T18 is on board edge.; root answer B[sb] / T18 is a board crop review candidate.
- `tests/sgf_engine/data/gold_fixtures/186.sgf`
  - sha256: `AE93FABAB9A0DC5A23EF495875CD18662AB9871DAEAD487DED55BCFF1B6CE64A`
  - parse_status: `ok`
  - root_child_moves: B[ea]
  - root_child_moves_go_coords: B[ea] / E19
  - setup_bounding_box: `{'min_x': 0, 'max_x': 7, 'min_y': 0, 'max_y': 5, 'min_go': 'A19', 'max_go': 'H14', 'stone_count': 26}`
  - quality_flags: TERMINAL_TOO_SHALLOW, ANSWER_ON_EDGE_LINE, POSSIBLE_BOARD_CROP_COORDINATE_MISMATCH
  - reason: SGF answer line ends at or near the first move.; root answer B[ea] / E19 is on board edge.; root answer B[ea] / E19 is a board crop review candidate.
- `tests/sgf_engine/data/gold_fixtures/35.sgf`
  - sha256: `E888ECB2BE0E219960723A4991DBD7BC1AD144BB261003B4ABE70C02B97918DC`
  - parse_status: `ok`
  - root_child_moves: W[of]
  - root_child_moves_go_coords: W[of] / P14
  - setup_bounding_box: `{'min_x': 9, 'max_x': 16, 'min_y': 1, 'max_y': 7, 'min_go': 'K18', 'max_go': 'R12', 'stone_count': 21}`
  - quality_flags: POSSIBLE_AUTO_REPLY_PATTERN
  - reason: A root answer has a single opponent child that may be an auto-reply.
- `tests/sgf_engine/data/gold_fixtures/431.sgf`
  - sha256: `0713176F21C7A23133014A5956D935311B9AA8AA5A483A87CCF8100FEA5C7D29`
  - parse_status: `ok`
  - root_child_moves: B[sf]
  - root_child_moves_go_coords: B[sf] / T14
  - setup_bounding_box: `{'min_x': 14, 'max_x': 17, 'min_y': 1, 'max_y': 6, 'min_go': 'P18', 'max_go': 'S13', 'stone_count': 12}`
  - quality_flags: TERMINAL_TOO_SHALLOW, ANSWER_ON_EDGE_LINE, POSSIBLE_BOARD_CROP_COORDINATE_MISMATCH
  - reason: SGF answer line ends at or near the first move.; root answer B[sf] / T14 is on board edge.; root answer B[sf] / T14 is a board crop review candidate.
- `tests/sgf_engine/data/gold_fixtures/881.sgf`
  - sha256: `AB1A454AEE792A172D78218621B8E965FF3A1D818A2DC2D7E7CB9F7688FF257F`
  - parse_status: `ok`
  - root_child_moves: B[gb]
  - root_child_moves_go_coords: B[gb] / G18
  - setup_bounding_box: `{'min_x': 1, 'max_x': 7, 'min_y': 0, 'max_y': 5, 'min_go': 'B19', 'max_go': 'H14', 'stone_count': 28}`
  - quality_flags: HAS_VARIATIONS
  - reason: SGF contains at least one branching node.

## Read-only safety statement

- SGF bytes changed: no
- SGF deleted: no
- SGF moved: no
- GF-003 production override enabled: no
- GF-003 active runtime payload enabled: no
- candidate override active behavior enabled: no
- READY_IDS changed: no
- puzzle_variation_overrides.json active config changed: no
- DB/API/backend/fake app.py added: no
- SGF engine judging semantics changed: no
- C:\go-website touched: no
