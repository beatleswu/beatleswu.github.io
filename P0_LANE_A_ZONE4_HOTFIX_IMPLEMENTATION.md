# P0 Lane A Zone4 hotfix implementation

## Candidate identity

IMPLEMENTATION_COMMIT=f2e89da2d1eccf673e1f3d9ab16ec99c214728a9
IMPLEMENTATION_TREE=de7391393aaba4d1920e9cccfda768c1b94bfb46
BASE=8b21c2f6e4d3ba2bb3ed227870b60078b1547213

## Exact production change

Production source changed only in:

js/e9/world_stage.js

At the existing intro mapping functions, the candidate adds:

- introCinematicKeyForZone('k11_15') returns e10_zone4_intro_v1.
- introEntryInFlightKey('k11_15') returns zone4EntryInFlight.

The fallback remains null for an unwired cinematic and remains the existing
Zone2 guard fallback for unknown in-flight lookups. The Zone4 cinematic path
uses its own guard and never shares Zone2's guard.

## Runtime contract

| Zone | Cinematic key | In-flight guard |
| --- | --- | --- |
| k26_30 | e10_zone1_intro_v1 | zone1EntryInFlight |
| k21_25 | e10_zone2_intro_v1 | zone2EntryInFlight |
| k16_20 | e10_zone3_intro_v1 | zone3EntryInFlight |
| k11_15 | e10_zone4_intro_v1 | zone4EntryInFlight |
| k6_10 and below | null | not called because no cinematic key |
| unknown | null | not called because no cinematic key |

The accepted prior runtime patch's two semantic additions match this
candidate exactly. No generic Zone5-10 enablement was introduced.

## Boundaries

EXACT_PRODUCTION_SOURCE_FILES=js/e9/world_stage.js
APP_PY_CHANGED=NO
DB_CHANGED=NO
ZONE4_ASSET_OR_CONTENT_CHANGED=NO
AUDIO_CHANGED=NO
STORY_ORDER_CHANGED=NO
PROGRESSION_REWARD_LORD_BEHAVIOR_CHANGED=NO
ZONE5_CHANGED=NO

The two regression files are bounded evidence only:

- tests/e9_node_tests/run_zone4_intro_cinematic_wiring_tests.js
- tests/test_post007c_008_zone4_intro_cinematic_wiring.py

