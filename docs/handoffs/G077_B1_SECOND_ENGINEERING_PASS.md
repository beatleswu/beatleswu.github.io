# G077 B1 second engineering pass — implementation, HOLD

Pinned HEAD `8a5101fae1ac685ce2c05b76fa330155b9631052`. Sole writer; no
push/merge/deploy, production DB/schema access or app.py changes. Previous
audit/proposal/receipts are retained. This is an uncommitted implementation.

`g077_mistakes_settlement.py:build_settlement` implements the existing
MistakesServices.settle signature. It borrows the caller connection and validates
the persisted session, canonical move history, terminal judgement and stable ID.
It uses the actual canonical review identity primitive and SRS core, writes the
Product mistake_log analytics, and returns the narrow terminal receipt. The
existing step bridge persists cursor/event in that SAME transaction; retries
return its durable response. Orphaned review identities fail closed rather than
pretending a partial commit is a successful replay. No Battle settlement is minted.

The bounded implemented subset is review/SRS/correction plus existing terminal
replay. It is NOT complete Product progression. Both admission/rating facts and
progression are mandatory connection-scoped providers. Unknown policy or invalid
XP output raises HOLD; no default zero reward exists. Full XP/rank/HP, equipment,
shield, quest/pet/coin ledger, badges/appearance and current rights/quota admission
remain provider dependencies. Fixture XP uses the actual app.py pure formula via
AST extraction; that fixture does not implement those Product dependencies.

Added `tests/test_g077_mistakes_settlement.py`: disposable SQLite, actual step and
MistakesServices HTTP paths, first/repeated correct, wrong/SRS, canonical legacy
correction/SRS parity, duplicate/conflicting replay, same/distinct-attempt
concurrency, failure at each durable stage and precommit rollback/retry, unknown
policy/revoked fixture rights/invalid reward rollback. **All pytest cases remain
NOT_EXECUTED**: Python absent from sandbox PATH; isolated Python 3.13 has no pytest
or Flask and dependency installation found no available distributions.

Executed `tools/check_g077_mistakes_settlement_static.py` with Blender's bundled
Python 3.13.13: **6 PASS**. Checks compile syntax, absence of writer lifecycle/DDL,
services=None effective default, real review identity and SRS SQLite primitives,
and executes source-extracted new/legacy correction SQL blocks for parity.
This does NOT execute/import the full settlement port. Initial static run had one
test assertion failure because app.py omits services (the default is None), rather
than explicitly passing None; the check was corrected, then final six passed.

G MASTER native next command (from this worktree, installed Python 3.12):

```powershell
python -B -m pytest -q -p no:cacheprovider tests/test_g077_mistakes_settlement.py tests/test_g076_mistakes_steps_isolated.py tests/test_g076_mistakes_product_readiness.py --junitxml=docs/handoffs/G077_B1_SECOND_PASS_NATIVE.xml
```

Native behavioral execution, full policy integration, disposable PostgreSQL
locking/migration and mixed-domain quota/coin concurrency are still required.
`app.py` continues to omit services, hence defaults to None and stays HOLD.
NOT_PLAYABLE / NO_GO. No historical result is promoted to fresh PASS.

Nothing staged. Automatic approval review rejected removal of the generated,
Git-ignored `.tmp/g077-test-venv` with `blocked by policy`; it remains local and
must not be staged. No bytecode/profile was staged.
