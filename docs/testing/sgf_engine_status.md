# SGF Engine Status

## Implemented modules

- `sgf_engine/core/coord_utils.py` — strict SGF coordinate and color helpers.
- `sgf_engine/core/tree.py` — `Move`, `SGFNode`, and pure child lookup.
- `sgf_engine/core/autoreply.py` — sole auto-reply rule.
- `sgf_engine/core/matcher.py` — branch/equivalent/off-tree classification only.
- `sgf_engine/parser/sgf_parser.py` — strict structural parser preserving variations.
- `sgf_engine/override/override_loader.py` — source-normalized JSON loading and canonical equivalent resolution.
- `sgf_engine/engine/engine.py` — sole five-step orchestrator and off-tree DB logger.
- `puzzle_variation_overrides.json` — empty authoritative exception file; malformed content raises.

No AI reasoning is present. No existing production module calls the engine yet; integration into `app.py`/frontend was outside the mission’s no-production-refactor boundary.

## Locked behavior

1. Load override.
2. Match structurally.
3. Traverse canonical tree branch or log/return off-tree.
4. Apply at most the one child allowed by the auto-reply rule.
5. Read `metadata["result"]`, defaulting to `continue`.

Matcher classification never reads result metadata. Override equivalence uses the documented JSON example’s canonical-to-alternatives shape:

```json
{
  "equivalent_moves": {
    "dd": ["pp"]
  }
}
```

Here `pp` is accepted as equivalent and resolves to canonical tree coordinate `dd`. Ambiguous alternatives raise `ValueError`.

## Fixture gate

Status: **PENDING**.

The repository did not contain `sgf_engine/data/fixtures/` or 10 manually verified gold files at discovery time. The directory is created empty, and no synthetic SGF was fabricated.

Integration remains skipped until all requirements are supplied:

- exactly 10 real, manually verified gold SGFs;
- at least 3 equivalent-move cases represented in reviewed override data;
- at least 1 off-tree scenario;
- at least 2 multi-move auto-reply chains.

Current tests are unit tests over data structures and invalid-parser inputs. The integration test automatically reports the fixture count and remains PENDING below 10.

## Validation evidence

Tests were run in the required dependency order:

1. coord utilities — 26 passed;
2. matcher — 5 passed;
3. tree — 5 passed;
4. override loader — 5 passed;
5. auto-reply — 5 passed;
6. parser invalid-input contract — 10 passed;
7. engine orchestration — 6 passed.

Final repository suite: **77 passed, 2 skipped**. The skips are the gold-fixture gate and the pre-existing documented full `/api/srs/review` success-path blocker.

## Determinism boundary

Given the same tree, override JSON, move and player color, `EngineResult` is deterministic. OFF_TREE additionally writes an audit row to `puzzle_unmatched_moves`; logging does not classify the move as valid or invalid.
