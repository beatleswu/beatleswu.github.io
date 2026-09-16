# P0 A+B combined diff

## Product boundary

Against 8b21c2f6e4d3ba2bb3ed227870b60078b1547213, the Product-code diff is
exactly two files:

~~~text
M index.html
M js/e9/world_stage.js
~~~

The measured code delta is:

~~~text
index.html           43 insertions(+), 5 deletions(-)
js/e9/world_stage.js  2 insertions(+), 0 deletions(-)
~~~

The full accepted A+B diff contains 18 paths: the two Product files, five
Lane A evidence files, two Lane A regression files, six Lane B planning files,
one Lane B E2E runner, and two Lane B Python/test-support files. The exact
path manifests are recorded in P0_AB_ACCEPTED_CANDIDATE_LINEAGE.md.

## Included behavior

Lane A adds only the Zone4 mapping/guard entries in world_stage.js:

~~~text
k11_15 -> e10_zone4_intro_v1
k11_15 -> zone4EntryInFlight
~~~

Lane B adds only the client-side Adventure boundary in index.html: an
Adventure question without active Map Battle is explicitly unavailable and
cannot use Practice or legacy review transport; normal Practice and the
successful authoritative Map Battle path remain intact.

## Explicit exclusions

~~~text
APP_PY_CHANGED=NO
DB_CHANGED=NO
SCHEMA_OR_MIGRATION_CHANGED=NO
PAYMENT_CHANGED=NO
REWARD_SETTLEMENT_CHANGED=NO
ZONE4_ASSET_AUDIO_STORY_CHANGED=NO
ZONE5_WIRING_CHANGED=NO
MBV1_AUTHORITY_REDESIGN_CHANGED=NO
HISTORICAL_RECOVERY_INCLUDED=NO
~~~

The Product-code scoped git diff --check was clean before the governance
reports were added. A full base-to-branch diff still reports only the three
pre-existing accepted Lane A evidence reports' blank-at-EOF warnings; no
Product-code whitespace warning is present.
