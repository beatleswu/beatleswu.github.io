# G078 Lane D/E cross-mode regression receipt

2026-10-23, isolated worktree `D:\go-odyssey-g076-b1b2r5-integration-20261023`.

HEAD: `fe696e87806a177d74e3ebfd4e3bd37cd2571a64`.
TREE: `a5c8842c9cfedfc964d90913b45fd4ecd4b6e8ac`.

**B4 = HOLD. Python native run pending; sandbox Chrome FAIL before first check.**
The candidate's **887 PASS + 2,544 subtests** is user-supplied prior developer
evidence, not a fresh execution of this lane. Do not add this lane's unexecuted
cases to that receipt or relabel prior evidence.

## Owned changes and isolation

Only new files owned by D/E:

- `tests/test_g078_cross_mode_matrix.py`
- `tests/test_g078_cross_mode_sessions.py`
- `tests/e2e/g078_cross_mode_chrome.mjs`
- this handoff

No changes to app.py, Dockerfile, shared modules, existing tests, other
worktrees or existing artifacts. No cherry-pick, GitHub push/merge/deploy,
production DDL, production connections or player operations. Existing untracked
`.g076-daily-tmp/`, `.g076-r5-disposable-pg.json`, `artifacts/g076-p0a/`,
`artifacts/g076-r5-product-adapter-1792753518820/`, and `artifacts/g076-rating/`
were present before this work and left alone. Tests use synthetic session keys,
in-memory SQLite or pytest-owned temporary SQLite. Chrome creates only a fresh
OS temporary profile and test HTML, binds its synthetic Node server to loopback,
and closes its own browser/server; it does not reuse a user's Chrome profile.

## Measurable additional coverage (implemented, NOT_EXECUTED in Python)

The new matrix defines 128 configurations: all 64 combinations of the six
`G076_{MISTAKES,RATING,GRIMOIRE,FRIEND,LORD,GUILD}_STEPS_ENABLED` flags crossed
with site-wide privacy OFF/ON. Each configuration performs 14 real Flask
`test_client` requests for each of anonymous and synthetic uid=101, a planned
**3,584 requests**, rather than 128 calls to the pure selector. Requests cover:

- Mistakes capability, attempt, step start, step submit, and answer disclosure.
- Current app.py Mistakes listing with `view=full&include_answers=1`.
- Current legacy Rating answer, Friend answer, Boss finish, and Grimoire training answer.
- Current SRS review route -> real ReviewService -> unedited current operation
  body for reserved source, forged Guild envelope, and forged Boss envelope.
- Product Grimoire admission with no admitted provider, requiring honest HOLD.

Every denied/private response is checked recursively for `solution`,
`answer_tree`, `accepted_moves`, `katago_answer`, SGF solution moves, and the
synthetic secret. Matrix requests must make zero SQLite writes. Explicit OFF
legacy compatibility still returns full legacy SGF on Mistakes: this is an
observed compatibility expectation, **not a privacy guarantee with privacy OFF**.

Additional tests cover 21 malformed configuration combinations at Mistakes
capability, malformed private SGF, default OFF, 404/405, and source installation
order. Rating fixture coverage adds anonymous/logged-in real authoritative
multi-step rounds with global privacy OFF and ON; exact terminal replay must
leave the full response/event/mistake/user snapshots unchanged. Four separate
negative paths check account switch, foreign-owner resume, conflicting replay,
and revoked rights before cached replay, plus malformed Rating/privacy flags.

Two **strict XFAIL** tests preserve unmet requirements, separately from passing
checks: single Grimoire ON blocks another normal mode, and malformed Grimoire
configuration does not engage its legacy-transport containment. XFAIL is an
unresolved finding, never PASS. Unexpected fixes become XPASS/failed-suite and
require review; remove the marker only after the integrator fixes the product.

## Actual application boundary and route authority

**OFFICIAL_APP_BOOT=NOT_EXECUTED. ISOLATED_FLASK_HARNESS=YES.** No Python
executable is exposed in this Codex sandbox (`Get-Command python,py,python3`
found none). No official application import was attempted. Current app.py
defaults APP_ENV to production, forwards get_db to db.get_db, can read/create a
repository secret, and installs SocketIO and unrelated product dependencies.
There is no certified disposable SQLite app factory used by this lane. We do
not infer safe full boot from a test source extraction.

The fallback explicitly reuses the official containment installers and
Mistakes blueprint. It AST-compiles unedited current app.py function bodies
with original login_required, and the real training-answer body from
grimoire_api.py. Synthetic providers replace only external dependencies;
incident logging is inert. Function decorators are removed and authentication
is reapplied explicitly. Boss's diagnostic decorator is omitted. This is real
Flask dispatch but **not official application registration or full startup**.

Rating reuses existing `g076_rating_fixture`: original Rating function AST
removes internal commit statements, routes through its synthetic connection,
and substitutes SQLite BEGIN IMMEDIATE for PostgreSQL FOR UPDATE. These are
material fixture changes. Positive Rating results cannot establish official
Flask/PG integration, canonical corpus or production entitlement readiness.

Current source facts at the pinned HEAD, superseding older handoff prose only
for this exact source checkpoint:

| Route / mode | Current policy and bounded test meaning |
| --- | --- |
| Mistakes secure routes | Official app registers blueprint without services; authenticated ON is 503 HOLD, anonymous 401. No Product XP settlement claim. |
| Rating secure routes | `create_rating_blueprint` is absent from app.py. The module/SQLite fixture works independently; formal route installation is still missing. |
| Grimoire | `install_product_grimoire` IS installed immediately after othermode guard, using official lookup. No trusted Product service is supplied by this harness; admission is 503 HOLD. |
| Grimoire single ON | Contains get_mistakes, Rating legacy aggregate, Friend aggregate, Daily/Map transports regardless of site-wide privacy. This is honest containment but violates independent-mode serviceability. |
| Global privacy ON | Official othermode guard returns 409 for training and Friend answer before view execution. 409 is HOLD, not playable success. |
| SRS / Guild / Lord spoof | Only early request-authority rejection is exercised: reserved source and mismatched envelopes cannot write. A full valid Guild/Lord replay or real reward transaction is NOT established. |
| Boss finish | Claimed correct/total/grade with no server exam returns 400 (anonymous 401). A live complete exam/reward replay is NOT tested. |
| Legacy Rating / Friend / training OFF | Matrix exercises malformed/empty request rejection, not valid authenticated game settlement. It cannot establish that a complete forged legacy submission is safe. |
| Malformed Grimoire flag | `enabled()` recognizes only true values and otherwise returns disabled. A malformed flag alone leaves old training transport outside containment; strict XFAIL records this configuration-policy gap. |

Thus the matrix covers real requests through multiple boundaries, not all
six full playable routes. Friend/Guild/Boss valid fixture settlement, all
normal modes remaining playable with each independent switch, global privacy
with every consumer migrated, and official startup remain **HOLD / NOT_EVALUATED**.

## Browser attempt and scope

`node --check tests/e2e/g078_cross_mode_chrome.mjs`: **PASS, exit 0**.

`node tests/e2e/g078_cross_mode_chrome.mjs`: **FAIL, exit 1, 0 checks** in
Codex sandbox. Chrome did launch and publish a loopback DevTools endpoint;
`Runtime.enable` timed out after 15 seconds. Chrome stderr repeatedly recorded
GPU subprocess exit `-1073741790` and ended with
`FATAL: GPU process isn't usable. Goodbye.` Also reported access denied/cache
failures. Preserve this failure; do not describe it as a WGo/test assertion
failure or a Chrome PASS. Attempt profile:
`C:\Users\beatl\AppData\Local\Temp\g078-chrome-KTkndD\profile`.
No sandbox-disabling browser flags or external browser packages were added.

The ready-to-run harness uses the existing local Chrome/Node/CDP approach and
actual repository WGo plus nonmap client, crossing file:// offline and loopback
HTTP. It checks a real board, offline fail-closed, lost response exact retry,
resume, exactly-once **synthetic** settlement, account rejection and mode HOLD
clearing the old cursor. It waits for a changed document identity after every
navigation. Backend is **SYNTHETIC_NODE_ONLY**, not Flask. HTML is a dedicated
test page, not official gameplay pages. Full six-mode Chrome browser matrix,
Chrome-to-official-Flask, PostgreSQL and real iPad Safari are NOT_EXECUTED.

## Native beatles execution (pending)

Run from the exact worktree, with no other process modifying tracked baseline:

```powershell
python -B -m pytest -q -p no:cacheprovider tests/test_g078_cross_mode_matrix.py tests/test_g078_cross_mode_sessions.py --tb=short
node tests/e2e/g078_cross_mode_chrome.mjs
```

Native results were requested through the user input channel; no result was
available when this receipt was written. Integrator should preserve stdout,
stderr, exit status, interpreter/Flask version, timestamps and these file hashes
in their own evidence location. No native Python collection, PASS count or
Chrome pass is claimed here. Both Python modules and the browser runner check
the pinned HEAD; Python also refuses a changed tracked baseline. Native run
must not replace this historical sandbox failure.

## SHA-256 source binding

| File | SHA-256 |
| --- | --- |
| app.py | A5152BF8B045D98F011DF168BDF83D407E53D4B02671EFD4C1652BE9B538B9F4 |
| grimoire_api.py | F3B6FE00C1C50C642682467304C797D023FF84D42F46C1FDEF4FFBAE2F1EB658 |
| g076_mistakes_product.py | C896EF0B624BD5B4BE3C3C27499AEDF444876E889C6C1384510D542EC1FE8D70 |
| g076_rating_steps.py | F6898C8BC128002083E42A74A1FE74E6E8924661AB205166F604EE5A41C67388 |
| g076_grimoire_product.py | 171C1440D09EDF003C1007C9C1D3E1A027898EFBE8132DC2FD59A0C8BAEFA2F5 |
| g076_othermode_authority.py | CC151CB03AA0C43E30D07EAC33B2C4ED6492F36A36761476D1BE5C066C50D9C2 |
| tests/g076_rating_fixture.py | 18B08CCCCDE698BF927D372F577B1740D7D13F44FE26FD7676858BCBC7E12A19 |
| tests/test_g076_rating_steps.py | ADC09207BF01C6D728575ECD1F051A6EA5F98ED2303A3A473608D41482F43383 |
| tests/test_g078_cross_mode_matrix.py | 27754A06B5F97A569C31B518ECF8C254DBAE1E45B43AFA61443E28DF3D9E8939 |
| tests/test_g078_cross_mode_sessions.py | E9E8B4A9FC3D7EBCED2A637EFD0B3D3E848555CB57098DE795C44716056CA2B8 |
| tests/e2e/g078_cross_mode_chrome.mjs | 2F33ABC77A98D074369209F3CECC21EF60C354EFBA9D00E7F653BA14DF4D134D |

Local tracked diff is empty; Node syntax check passes. New source file
whitespace was checked separately because git diff does not inspect untracked
files. This receipt conveys regression work and exact limitations, not
security admission, BUILD_APP, merge/deploy authorization or Owner acceptance.
