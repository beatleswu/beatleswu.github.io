# P0 A+B cross-lane acceptance

## Boundary proof

Lane A owns js/e9/world_stage.js; Lane B owns its corrective behavior in
index.html. The combined Product diff has no shared Product file and no
server authority change. Therefore the candidate cannot make the Zone4
cinematic mapping itself select a question, settle an answer, or create
progression.

The inspected flow remains:

~~~text
World Stage Continue Adventure
  -> Zone4 intro key/guard selection
  -> Adventure question pool is bound by the existing entry path
  -> Map Battle initialization
       -> active: existing authoritative Map Battle answer path
       -> disabled/pending/not-eligible/runtime failure: blocked/unavailable
  -> no Practice fallback and no client progression credit
~~~

The Zone4 entry mapping is a presentation/entry guard only. It does not bypass
_adventureActiveQuestions, _mapBattleV1IsActive(), the server-created mbv1
settlement marker, or the duplicate guard. Lane B's final submitSRS()/load
guards run after Adventure origin is known and therefore do not suppress a
legitimate Zone4 cinematic before Map Battle initialization.

## Fresh evidence

The Zone4 Node harness passed all six assertions, including unchanged Zones
1–3, distinct wired keys/guards, and Zone5+ unwired. The Lane B Node contract
passed disabled, pending, not-eligible, runtime-failure, active Map Battle,
and ordinary Practice cases. The combined Python/source and server suites are
listed in P0_AB_COMBINED_REGRESSION.md.

~~~text
LANE_A_BREAKS_LANE_B=NO
LANE_B_BREAKS_LANE_A=NO
CROSS_LANE_INTERFERENCE=NONE
~~~

No asset/audio/story, database, reward, or progression writer was changed by
either lane.
